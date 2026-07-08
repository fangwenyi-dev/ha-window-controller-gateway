"""设备管理器"""
import logging
import asyncio
import time
from typing import Dict, Any, List, Optional, Callable
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import async_get


from .const import (
    DOMAIN,
    CONF_GATEWAY_SN,
    CONF_GATEWAY_NAME,
    ATTR_DEVICE_SN,
    ATTR_DEVICE_NAME,
    DEVICE_TYPE_WINDOW_OPENER,  # 使用开窗器类型
    MANUFACTURER,
    MODEL,
    DEVICE_TO_GATEWAY_MAPPING,
    DEVICE_TO_GATEWAY_MAPPING_FILE,
    GLOBAL_MANUALLY_REMOVED_DEVICES,
    DEVICE_REGISTRATION_DELAY,
    GATEWAY_READY_DELAY,
    DEVICE_SETUP_DELAY,
    get_device_display_name,
)
from .persist import save_persistent_data

_LOGGER = logging.getLogger(__name__)

class WindowControllerDeviceManager:
    """设备管理器类"""
    
    # 需要重新创建的实体类型和平台映射
    entity_recreate_platforms = ["button", "sensor", "binary_sensor", "cover"]
    
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """初始化设备管理器"""
        self.hass = hass
        self.entry = entry
        self.gateway_sn = entry.data[CONF_GATEWAY_SN]
        self.gateway_name = entry.data.get(CONF_GATEWAY_NAME, f"慧尖网关 {self.gateway_sn[-4:]}")
        self.devices = {}
        self.gateway_device_id = None
        self._device_added_callbacks = []
        self._device_removed_callbacks = []
        self._device_update_callbacks = {}
        self._device_registry_cache = None
        self._entity_registry_cache = None
        self._is_migrating = False
        self._migration_lock = asyncio.Lock()
        self._status_query_semaphore = asyncio.Semaphore(3)  # 同时最多3个状态查询
        self._manually_removed_devices = self._load_manually_removed_devices()
        self._background_tasks = []
    
    def _load_manually_removed_devices(self) -> set:
        """从持久化存储中加载手动删除的设备SN列表"""
        # 从hass.data中加载
        if DOMAIN not in self.hass.data:
            self.hass.data[DOMAIN] = {}
        
        # 使用全局手动删除设备列表，而不是每个网关独立存储
        if GLOBAL_MANUALLY_REMOVED_DEVICES not in self.hass.data[DOMAIN]:
            self.hass.data[DOMAIN][GLOBAL_MANUALLY_REMOVED_DEVICES] = set()
        
        return self.hass.data[DOMAIN][GLOBAL_MANUALLY_REMOVED_DEVICES]
    
    def _save_manually_removed_devices(self) -> None:
        """将手动删除的设备SN列表保存到持久化存储中"""
        if DOMAIN not in self.hass.data:
            self.hass.data[DOMAIN] = {}
        
        if GLOBAL_MANUALLY_REMOVED_DEVICES not in self.hass.data[DOMAIN]:
            self.hass.data[DOMAIN][GLOBAL_MANUALLY_REMOVED_DEVICES] = set()
        
        self.hass.data[DOMAIN][GLOBAL_MANUALLY_REMOVED_DEVICES] = self._manually_removed_devices
        _LOGGER.debug("已保存全局手动删除设备列表: %s", self._manually_removed_devices)
        
        # 触发持久化保存
        self._trigger_persistent_save()
    
    def _trigger_persistent_save(self) -> None:
        """触发持久化保存（异步）"""
        try:
            self.hass.async_create_task(save_persistent_data(self.hass))
        except Exception as e:
            _LOGGER.warning("触发持久化保存失败: %s", e)
    
    def _load_device_to_gateway_mapping(self) -> dict:
        """从持久化存储中加载设备到网关的映射关系"""
        if DOMAIN not in self.hass.data:
            self.hass.data[DOMAIN] = {}
        
        if DEVICE_TO_GATEWAY_MAPPING not in self.hass.data[DOMAIN]:
            self.hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING] = {}
        
        return self.hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING]
    
    def _save_device_to_gateway_mapping(self) -> None:
        """将设备到网关的映射关系保存到持久化存储中"""
        if DOMAIN not in self.hass.data:
            self.hass.data[DOMAIN] = {}
        
        if DEVICE_TO_GATEWAY_MAPPING not in self.hass.data[DOMAIN]:
            self.hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING] = {}
        
        _LOGGER.debug("已保存设备到网关映射关系")
        
        # 触发持久化保存
        self._trigger_persistent_save()
    
    def is_device_manually_removed(self, device_sn: str) -> bool:
        """检查设备是否被手动删除过
        
        Args:
            device_sn: 设备序列号
            
        Returns:
            bool: 如果设备被手动删除过返回True，否则返回False
        """
        return device_sn in self._manually_removed_devices
        
    async def _get_device_registry(self):
        """获取设备注册表（带缓存）"""
        if not self._device_registry_cache:
            self._device_registry_cache = async_get(self.hass)
        return self._device_registry_cache
    
    async def _get_entity_registry(self):
        """获取实体注册表（带缓存）"""
        if not self._entity_registry_cache:
            from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
            self._entity_registry_cache = async_get_entity_registry(self.hass)
        return self._entity_registry_cache
    
    async def _notify_device_added_callbacks(self, device_sn: str, device_name: str, device_type: str) -> None:
        """批量通知所有设备添加回调，使用 gather 控制并发"""
        if not self._device_added_callbacks:
            return
        tasks = []
        for callback in self._device_added_callbacks:
            tasks.append(callback(device_sn, device_name, device_type))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _spawn_background_task(self, coro, name=None):
        """创建受追踪的后台任务"""
        task = asyncio.create_task(coro, name=name)
        self._background_tasks.append(task)
        return task

    async def setup(self) -> bool:
        """设置设备管理器"""
        start_time = time.time()
        _LOGGER.info("=== 设备管理器初始化: %s ===", self.gateway_sn)
        
        # 标准化网关SN（转小写以进行匹配）
        gateway_sn_lower = self.gateway_sn.lower()
        
        processed_count = 0
        
        # 调试：检查映射表是否存在
        if DEVICE_TO_GATEWAY_MAPPING in self.hass.data[DOMAIN]:
            device_to_gateway_mapping = self.hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING]
            _LOGGER.debug("设备映射表内容: %s", device_to_gateway_mapping)
            
            # 遍历映射表，加载属于当前网关的设备（忽略大小写）
            for device_sn, mapped_gateway_sn in device_to_gateway_mapping.items():
                # 标准化比较 - 支持多种匹配方式
                _LOGGER.debug("检查设备映射: device_sn=%s, mapped_gateway=%s, current_gateway=%s", device_sn, mapped_gateway_sn, self.gateway_sn)
                
                # 当前网关SN
                current_lower = self.gateway_sn.lower()
                mapped_lower = mapped_gateway_sn.lower()
                
                gateway_match = (mapped_lower == current_lower)
                
                if gateway_match and device_sn not in self.devices:
                    device_name = get_device_display_name(self.gateway_sn, device_sn)
                    
                    # 同步添加到内存字典中
                    self.devices[device_sn] = {
                        "sn": device_sn,
                        "name": device_name,
                        "type": DEVICE_TYPE_WINDOW_OPENER,
                        "status": "offline",
                        "attributes": {}
                    }
                    _LOGGER.info("同步加载设备到内存: %s", device_sn)
                    
                    # 异步触发设备注册
                    self._spawn_background_task(
                        self._async_fast_register_device(device_sn, device_name)
                    )
                    
                    processed_count += 1
            
            _LOGGER.info("当前网关 %s 共加载 %d 个设备", self.gateway_sn, processed_count)
        else:
            _LOGGER.info("设备到网关映射表不存在")
        
        if processed_count > 0:
            _LOGGER.info("已加载 %d 个设备", processed_count)
            # 触发MQTT状态查询
            self._spawn_background_task(self._trigger_immediate_status_query())
        
        # 2. 并行触发设备发现（后台任务）
        try:
            gateway_data = self.hass.data[DOMAIN].get(self.entry.entry_id)
            if gateway_data and isinstance(gateway_data, dict):
                mqtt_handler = gateway_data.get("mqtt_handler")
                if mqtt_handler:
                    # 立即发送快速设备发现命令（1秒延迟）
                    async def send_quick_discovery():
                        await asyncio.sleep(GATEWAY_READY_DELAY)  # 短暂延迟，确保网关就绪
                        try:
                            await mqtt_handler.send_command(self.gateway_sn, "discover")
                            _LOGGER.debug("已发送极速设备发现命令")
                        except Exception as e:
                            _LOGGER.debug("发送极速发现命令失败: %s", e)
                    
                    self._spawn_background_task(send_quick_discovery())
        except Exception as e:
            _LOGGER.debug("触发并行设备发现失败: %s", e)
        
        elapsed_time = time.time() - start_time
        _LOGGER.info("设备管理器极速初始化完成，耗时: %.2f 秒，设备数: %d",
                     elapsed_time, len(self.devices))
        
        # 3. 立即返回成功，让前端可以立即显示设备
        # 设备注册和状态查询在后台异步完成
        return True

    async def _quick_register_device(self, device_sn):
        """快速注册设备（不阻塞主流程）"""
        try:
            device_registry = await self._get_device_registry()
            device = device_registry.async_get_device(identifiers={(DOMAIN, device_sn)})
            
            if device:
                # 设备已存在，快速更新关联
                device_registry.async_update_device(
                    device.id,
                    via_device=(DOMAIN, self.gateway_sn)
                )
                _LOGGER.debug("快速更新设备 %s 的网关关联", device_sn)
        except Exception as e:
            _LOGGER.debug("快速注册设备失败（可忽略）: %s", e)

    async def _reassociate_device(self, device_sn, device):
        """重新关联设备到当前网关"""
        try:
            device_registry = await self._get_device_registry()
            
            # 更新设备关联
            updated_device = device_registry.async_get_or_create(
                config_entry_id=self.entry.entry_id,
                identifiers={(DOMAIN, device_sn)},
                name=device.name,
                manufacturer=MANUFACTURER,
                model=self._get_device_model(DEVICE_TYPE_WINDOW_OPENER),
                via_device=(DOMAIN, self.gateway_sn)
            )
            
            # 添加到设备列表
            self.devices[device_sn] = {
                "sn": device_sn,
                "name": device.name,
                "type": DEVICE_TYPE_WINDOW_OPENER,
                "status": "online",
                "attributes": {}
            }
            
            _LOGGER.info("设备重新关联成功: %s -> %s", device_sn, self.gateway_sn)
            
        except Exception as e:
            _LOGGER.error("重新关联设备失败 %s: %s", device_sn, e)
    
    async def _process_device_async(self, device_sn, device):
        """异步处理单个设备"""
        self.devices[device_sn] = {
            "sn": device_sn,
            "name": device.name,
            "type": DEVICE_TYPE_WINDOW_OPENER,
            "status": "online",
            "attributes": {}
        }
        _LOGGER.debug("加载设备: %s, 名称: %s", device_sn, device.name)
    
    async def _async_fast_register_device(self, device_sn: str, device_name: str):
        """异步快速注册设备（不阻塞主流程）"""
        try:
            # 不再延迟，因为设备已经在setup()开始时同步添加到内存了
            # 这里的异步注册只是更新设备注册表
            
            device_registry = await self._get_device_registry()
            config_entry = self.hass.config_entries.async_get_entry(self.entry.entry_id)
            
            if not config_entry:
                return
            
            # 快速创建设备注册
            device = device_registry.async_get_or_create(
                config_entry_id=self.entry.entry_id,
                identifiers={(DOMAIN, device_sn)},
                name=device_name,
                manufacturer=MANUFACTURER,
                model="开窗器",
                via_device=(DOMAIN, self.gateway_sn)
            )
            
            _LOGGER.debug("异步注册设备完成: %s", device_sn)
            
        except Exception as e:
            _LOGGER.debug("异步注册设备失败（可忽略）: %s", e)
    
    async def _trigger_immediate_status_query(self):
        """立即触发设备状态查询"""
        try:
            # 等待，确保MQTT处理器就绪
            await asyncio.sleep(DEVICE_SETUP_DELAY)
            
            gateway_data = self.hass.data[DOMAIN].get(self.entry.entry_id)
            if not gateway_data:
                return
                
            mqtt_handler = gateway_data.get("mqtt_handler")
            if not mqtt_handler:
                return
            
            # 查询所有设备状态（批量进行，使用自适应间隔）
            device_sns = list(self.devices.keys())
            if not device_sns:
                return
                
            _LOGGER.info("开始极速查询 %d 个设备状态", len(device_sns))
            
            # 计算自适应查询间隔
            query_interval = self._calculate_adaptive_query_interval(len(device_sns))
            _LOGGER.info("使用自适应查询间隔: %.2f秒", query_interval)
            
            # 实现批量查询
            batch_size = self._calculate_batch_size(len(device_sns))
            device_batches = [device_sns[i:i+batch_size] for i in range(0, len(device_sns), batch_size)]
            
            async def query_device_batch(batch):
                """查询一批设备状态"""
                for device_sn in batch:
                    async with self._status_query_semaphore:
                        try:
                            await mqtt_handler.send_command(device_sn, "status")
                            await asyncio.sleep(query_interval)  # 使用自适应查询间隔
                        except Exception as e:
                            _LOGGER.debug("极速查询设备状态失败 %s: %s", device_sn, e)
            
            # 并行执行批次查询
            batch_tasks = [query_device_batch(batch) for batch in device_batches]
            await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            _LOGGER.info("极速设备状态查询完成")
            
        except Exception as e:
            _LOGGER.error("触发极速状态查询失败: %s", e)
        
    async def register_gateway_device(self):
        """注册网关设备"""
        device_registry = await self._get_device_registry()
        
        device = device_registry.async_get_or_create(
            config_entry_id=self.entry.entry_id,
            identifiers={(DOMAIN, self.gateway_sn)},
            name=self.gateway_name,
            manufacturer=MANUFACTURER,
            model=MODEL,
            sw_version="1.0"
        )
        
        self.gateway_device_id = device.id
        _LOGGER.info("网关设备注册成功: %s (ID: %s)", self.gateway_name, self.gateway_device_id)
        
        return device.id
    
    async def update_gateway_status(self, status: str, attributes: dict = None):
        """更新网关状态"""
        _LOGGER.debug("更新网关 %s 状态为: %s", self.gateway_sn, status)
        
        # 这里可以添加网关状态的持久化存储
        # 目前主要依赖MQTT处理器的连接状态
        
        return True
    
    def get_gateway_info(self):
        """获取网关信息"""
        return {
            "sn": self.gateway_sn,
            "name": self.gateway_name,
            "device_id": self.gateway_device_id,
            "manufacturer": MANUFACTURER,
            "model": MODEL
        }
    
    def _format_device_name(self, device_sn: str, device_name: str) -> str:
        """格式化设备名称，如果设备名称不包含SN后4位，则添加
        
        Args:
            device_sn: 设备SN
            device_name: 设备名称
            
        Returns:
            str: 格式化后的设备名称
        """
        device_sn_suffix = device_sn[-4:]
        if device_sn_suffix not in device_name:
            return f"{device_name} ({device_sn_suffix})"
        return device_name
    
    def _get_optimal_concurrent_tasks(self):
        """获取固定并发任务数
        
        Returns:
            int: 固定并发任务数
        """
        return 5
    
    def _calculate_adaptive_query_interval(self, device_count: int) -> float:
        """根据设备数量计算自适应查询间隔
        
        Args:
            device_count: 设备数量
            
        Returns:
            float: 查询间隔（秒）
        """
        if device_count <= 3:
            return 0.1
        elif device_count <= 10:
            return 0.2
        else:
            return 0.3
    
    def _calculate_batch_size(self, device_count: int) -> int:
        """根据设备数量计算批处理大小
        
        Args:
            device_count: 设备数量
            
        Returns:
            int: 批处理大小
        """
        if device_count <= 5:
            return 5
        elif device_count <= 20:
            return 10
        else:
            return 15
        

    
    def set_device_added_callback(self, callback: Callable[[str, Dict[str, Any]], None]):
        """添加设备添加回调
        
        Args:
            callback: 回调函数，接收设备SN和设备信息作为参数
        """
        # 检查是否已经存在相同的回调
        callback_exists = False
        for existing_callback in self._device_added_callbacks:
            if existing_callback == callback:
                callback_exists = True
                break
        
        if not callback_exists:
            self._device_added_callbacks.append(callback)
            _LOGGER.debug("设备添加回调已添加")
    
    def set_device_removed_callback(self, callback: Callable[[str], None]):
        """添加设备移除回调
        
        Args:
            callback: 回调函数，接收设备SN作为参数
        """
        # 检查是否已经存在相同的回调
        callback_exists = False
        for existing_callback in self._device_removed_callbacks:
            if existing_callback == callback:
                callback_exists = True
                break
        
        if not callback_exists:
            self._device_removed_callbacks.append(callback)
            _LOGGER.debug("设备移除回调已添加")
    
    async def add_device(self, device_sn: str, device_name: str, device_type: str = None, force: bool = False, is_manual_pairing: bool = False):
        """添加设备 - 只支持开窗器类型
        
        Args:
            device_sn: 设备序列号
            device_name: 设备名称
            device_type: 设备类型（将被忽略，强制为开窗器）
            force: 是否强制添加（跳过设备存在检查）
            is_manual_pairing: 是否手动配对添加（手动配对时跳过手动删除列表检查）
        """
        # 检查设备是否是网关设备
        # 根据用户提供的信息：所有网关的SN前4位都是1001，所有窗控器的SN前3位都是500
        if device_sn.startswith("1001"):
            _LOGGER.debug("发现网关设备，跳过添加为子设备: %s", device_sn)
            return None
        
        # 保留原有检查逻辑作为备份
        device_name_lower = device_name.lower()
        if "gateway" in device_name_lower or "网关" in device_name_lower:
            _LOGGER.debug("发现网关设备，跳过添加为子设备: %s", device_sn)
            return None
        
        # 自动发现时检查手动删除列表（仅当不是手动配对时）
        # 手动删除的设备不应通过自动发现重新添加，但可以通过手动配对重新添加
        if not is_manual_pairing and device_sn in self._manually_removed_devices:
            _LOGGER.info("设备 %s 在手动删除列表中，自动发现跳过添加", device_sn)
            return None
        
        # 检查设备是否已经添加到其他网关中（迁移时跳过此检查）
        if not force and DEVICE_TO_GATEWAY_MAPPING in self.hass.data[DOMAIN]:
            device_to_gateway_mapping = self.hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING]
            if device_sn in device_to_gateway_mapping:
                existing_gateway_sn = device_to_gateway_mapping[device_sn]
                # 忽略大小写比较
                if existing_gateway_sn.lower() != self.gateway_sn.lower():
                    # 检查旧网关的配置条目是否仍然存在
                    old_gateway_exists = False
                    for entry in self.hass.config_entries.async_entries(DOMAIN):
                        if entry.data.get(CONF_GATEWAY_SN, "").lower() == existing_gateway_sn.lower():
                            old_gateway_exists = True
                            break

                    if not old_gateway_exists:
                        # 旧网关已删除，自动转移设备到当前网关
                        _LOGGER.info(
                            "设备 %s 的原网关 %s 已删除，自动转移到新网关 %s",
                            device_sn, existing_gateway_sn, self.gateway_sn
                        )
                        device_to_gateway_mapping[device_sn] = self.gateway_sn
                        self._save_device_to_gateway_mapping()
                        # 从手动删除列表中移除（如果有）
                        if device_sn in self._manually_removed_devices:
                            self._manually_removed_devices.discard(device_sn)
                            self._save_manually_removed_devices()
                        # 继续正常添加流程
                    else:
                        # 旧网关仍存在，通知用户并阻止自动添加
                        _LOGGER.warning(
                            "设备 %s 已绑定到网关 %s（仍存在），如需转移请使用 transfer_device 服务",
                            device_sn, existing_gateway_sn
                        )
                        await self._notify_device_conflict(device_sn, existing_gateway_sn)
                        return None
        
        # 强制设备类型为开窗器，忽略传入的其他类型
        device_type = DEVICE_TYPE_WINDOW_OPENER
        
        # 格式化设备名称
        device_name_with_sn = self._format_device_name(device_sn, device_name)
            
        device_existed = device_sn in self.devices
        if device_existed:
            _LOGGER.debug("设备已存在: %s", device_sn)
            
            # 如果是迁移模式（force=True），需要更新设备到网关映射表
            if force:
                _LOGGER.info("迁移模式：更新设备 %s 到当前网关 %s", device_sn, self.gateway_sn)
                
                # 更新设备到网关映射表
                if DEVICE_TO_GATEWAY_MAPPING in self.hass.data[DOMAIN]:
                    device_to_gateway_mapping = self.hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING]
                    device_to_gateway_mapping[device_sn] = self.gateway_sn
                    _LOGGER.info("已更新设备 %s 的网关映射到 %s", device_sn, self.gateway_sn)
                
                # 如果设备在手动删除列表中，从列表中移除
                if device_sn in self._manually_removed_devices:
                    self._manually_removed_devices.discard(device_sn)
                    self._save_manually_removed_devices()
                    _LOGGER.info("迁移模式：设备 %s 已从手动删除列表中移除", device_sn)
                
                # 更新设备在 self.devices 中的信息
                # P2 修复：使用与正常添加路径一致的设备结构（status/attributes），
                # 而非 online/last_update，避免其他代码访问不存在的键
                self.devices[device_sn] = {
                    "sn": device_sn,
                    "name": device_name_with_sn,
                    "type": device_type,
                    "status": "connected",
                    "attributes": {}
                }
                _LOGGER.info("已更新设备 %s 在设备管理器中的信息", device_sn)
                
                # 触发设备添加回调，确保实体被创建
                # 注意：即使设备已存在，也需要触发回调，因为设备可能已经迁移到新网关
                await self._notify_device_added_callbacks(device_sn, device_name_with_sn, device_type)
                _LOGGER.info("已触发设备 %s 的添加回调（迁移模式）", device_sn)
                
                return device_sn
            
            # 注意：此处无需再次检查设备归属，上方的智能冲突检测已处理所有情况
            # 如果执行到这里，说明设备属于当前网关（或已自动转移），可以安全更新
            
            # 更新设备类型为开窗器（保留用户自定义的设备名称）
            self.devices[device_sn]["type"] = device_type
            
            # 更新设备注册信息，确保config_entry_id和via_device正确
            try:
                device_registry = await self._get_device_registry()
                # 查找设备
                device = device_registry.async_get_device(
                    identifiers={(DOMAIN, device_sn)}
                )
                if device:
                    # 检查配置条目是否存在
                    config_entry = self.hass.config_entries.async_get_entry(self.entry.entry_id)
                    if config_entry:
                        # 直接使用async_get_or_create方法重新创建设备关联
                        # 这种方式可以确保设备被正确关联到新的配置条目和网关
                        updated_device = device_registry.async_get_or_create(
                            config_entry_id=self.entry.entry_id,
                            identifiers={(DOMAIN, device_sn)},
                            name=device_name_with_sn,
                            manufacturer=MANUFACTURER,
                            model=self._get_device_model(device_type),
                            via_device=(DOMAIN, self.gateway_sn)
                        )
                        
                        # 验证设备关联是否正确更新
                        if self.entry.entry_id in updated_device.config_entries:
                            _LOGGER.info("设备已成功关联到当前配置条目: %s", device_sn)
                        else:
                            _LOGGER.warning("设备未成功关联到当前配置条目: %s", device_sn)
                        
                        # 检查updated_device是否有via_device属性
                        if hasattr(updated_device, 'via_device'):
                            if updated_device.via_device and updated_device.via_device[1] == self.gateway_sn:
                                _LOGGER.info("设备已成功关联到当前网关: %s", device_sn)
                            else:
                                _LOGGER.warning("设备未成功关联到当前网关: %s", device_sn)
                        else:
                            _LOGGER.debug("设备没有via_device属性，跳过网关关联检查: %s", device_sn)
                        
                        _LOGGER.info("设备注册信息已更新: %s", device_sn)
                    else:
                        _LOGGER.debug("配置条目不存在，跳过更新设备注册信息: %s", self.entry.entry_id)
            except Exception as e:
                _LOGGER.error("更新设备注册信息失败: %s", e)
            
            # 即使设备已存在，也要调用回调，确保实体被重新创建
            await self._notify_device_added_callbacks(device_sn, device_name_with_sn, device_type)
            _LOGGER.info("设备已存在，重新触发回调: %s", device_sn)
            return self.devices[device_sn]
            
        device_info = {
            "sn": device_sn,
            "name": device_name_with_sn,
            "type": device_type,
            "status": "connected",
            "attributes": {}
        }
        
        self.devices[device_sn] = device_info
        
        # 创建设备注册
        device = None
        try:
            device_registry = await self._get_device_registry()
            # 检查配置条目是否存在
            config_entry = self.hass.config_entries.async_get_entry(self.entry.entry_id)
            if not config_entry:
                # 配置条目不存在是正常情况，可能是因为条目已被删除或尚未完全加载
                # 将警告日志改为调试日志，避免在正常操作中产生过多警告
                _LOGGER.debug("配置条目不存在，跳过创建设备注册: 配置条目ID=%s, 设备SN=%s", self.entry.entry_id, device_sn)
                # 即使配置条目不存在，也要返回设备信息，这样设备仍会被添加到内存中
                # 但不会创建Home Assistant设备注册
                # 调用设备添加回调，让其他组件知道设备已添加
                await self._notify_device_added_callbacks(device_sn, device_name_with_sn, device_type)
                _LOGGER.debug("开窗器设备添加成功 (内存中): %s (%s)", device_name_with_sn, device_sn)
                return device_sn
            
            device = device_registry.async_get_or_create(
                config_entry_id=self.entry.entry_id,
                identifiers={(DOMAIN, device_sn)},
                name=device_name_with_sn,
                manufacturer=MANUFACTURER,
                model=self._get_device_model(device_type),
                via_device=(DOMAIN, self.gateway_sn)
            )
        except Exception as e:
            _LOGGER.error("创建设备注册失败: %s", e)
            # 即使创建设备注册失败，也要返回设备信息
            # 调用设备添加回调，让其他组件知道设备已添加
            await self._notify_device_added_callbacks(device_sn, device_name_with_sn, device_type)
            _LOGGER.info("开窗器设备添加成功 (内存中): %s (%s)", device_name_with_sn, device_sn)
            return device_sn
        
        if device:
            _LOGGER.info("开窗器设备添加成功: %s (%s)", device_name_with_sn, device_sn)
            
            # 将设备SN和网关SN的映射关系存储到hass.data中
            if DEVICE_TO_GATEWAY_MAPPING not in self.hass.data[DOMAIN]:
                self.hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING] = {}
            self.hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING][device_sn] = self.gateway_sn
            _LOGGER.info("设备 %s 已添加到网关 %s，已更新映射关系", device_sn, self.gateway_sn)
            self._save_device_to_gateway_mapping()
            
            # 如果设备在手动删除列表中，添加成功后从列表中移除
            if device_sn in self._manually_removed_devices:
                self._manually_removed_devices.discard(device_sn)
                self._save_manually_removed_devices()
                _LOGGER.info("设备 %s 已从手动删除列表中移除", device_sn)
            
            # 调用所有设备添加回调，通知需要添加新实体
            await self._notify_device_added_callbacks(device_sn, device_name_with_sn, device_type)
            _LOGGER.debug("已通知所有设备添加回调: %s", device_name_with_sn)
            
            return device.id
        else:
            _LOGGER.error("创建设备失败，device 为 None: %s", device_sn)
            await self._notify_device_added_callbacks(device_sn, device_name_with_sn, device_type)
            _LOGGER.info("开窗器设备添加成功 (内存中): %s (%s)", device_name_with_sn, device_sn)
            return device_sn
    
    def _get_device_model(self, device_type: str) -> str:
        """根据设备类型获取模型名称"""
        # 只支持开窗器设备
        return "开窗器"
        
    async def remove_device(self, device_sn: str, is_manual: bool = True):
        """移除设备
        
        Args:
            device_sn: 设备SN号
            is_manual: 是否手动删除（默认为True）
        """
        if device_sn in self.devices:
            # 获取设备信息
            device_info = self.devices[device_sn]
            device_name = device_info.get("name")
            device_type = device_info.get("type")
            
            # 从内存中删除设备
            del self.devices[device_sn]
            _LOGGER.info("设备移除: %s", device_sn)
            
            # 如果是手动删除，将设备添加到手动删除列表中
            # 这样设备不会自动同步回来，除非重新添加
            if is_manual:
                if device_sn not in self._manually_removed_devices:
                    self._manually_removed_devices.add(device_sn)
                    # 保存到持久化存储
                    self._save_manually_removed_devices()
                    _LOGGER.info("设备已添加到手动删除列表: %s", device_sn)
                else:
                    _LOGGER.debug("设备已在手动删除列表中: %s", device_sn)
            
            # 改进：从设备到网关映射表中删除设备
            # 只有当设备在映射表中存在，且映射的网关是当前网关时，才从映射表中删除
            if DEVICE_TO_GATEWAY_MAPPING in self.hass.data[DOMAIN]:
                device_to_gateway_mapping = self.hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING]
                if device_sn in device_to_gateway_mapping:
                    existing_gateway_sn = device_to_gateway_mapping[device_sn]
                    # 忽略大小写比较
                    if existing_gateway_sn.lower() == self.gateway_sn.lower():
                        del device_to_gateway_mapping[device_sn]
                        _LOGGER.info("设备 %s 已从网关映射表中删除 (所属网关: %s)", 
                            device_sn, self.gateway_sn)
                    else:
                        # 改为调试日志，避免产生过多警告
                        _LOGGER.debug("设备 %s 映射到网关 %s，不是当前网关 %s，不从映射表中删除", 
                            device_sn, existing_gateway_sn, self.gateway_sn)
                else:
                    _LOGGER.debug("设备 %s 不在网关映射表中", device_sn)
            
            # 从 Home Assistant 设备注册表中删除设备
            try:
                device_registry = await self._get_device_registry()
                # 查找设备
                device = device_registry.async_get_device(
                    identifiers={(DOMAIN, device_sn)}
                )
                if device:
                    device_registry.async_remove_device(device.id)
                    _LOGGER.info("设备已从 Home Assistant 设备注册表中删除: %s", device_sn)
                else:
                    _LOGGER.debug("设备在注册表中未找到: %s", device_sn)
            except Exception as e:
                _LOGGER.error("从设备注册表中删除设备失败: %s", e)
            
            # 调用设备移除回调
            _LOGGER.info("正在通知设备移除回调，设备: %s", device_sn)
            for callback in self._device_removed_callbacks:
                try:
                    await callback(device_sn, device_name, device_type)
                    _LOGGER.info("设备移除回调执行成功")
                except Exception as e:
                    _LOGGER.error("执行设备移除回调失败: %s", e)
            
            _LOGGER.info("设备移除流程完成: %s", device_sn)
            
            # 通知MQTT处理器，设备已被删除
            # 这样当设备重新被发现时，可以重新添加
            try:
                # P2 修复：使用 hass.async_create_task（hass.create_task 已弃用），
                # 并直接通过 entry_id 查找 MQTT 处理器，避免不必要的迭代
                gateway_data = self.hass.data[DOMAIN].get(self.entry.entry_id)
                if gateway_data and isinstance(gateway_data, dict):
                    mqtt_handler = gateway_data.get("mqtt_handler")
                    if mqtt_handler:
                        self.hass.async_create_task(mqtt_handler.trigger_discovery())
            except KeyError as e:
                _LOGGER.error("访问DOMAIN数据失败: %s", e)
            except Exception as e:
                _LOGGER.error("通知MQTT处理器设备删除失败: %s", e)

    async def update_device_status(self, device_sn: str, status: str, attributes: Optional[Dict[str, Any]] = None):
        """更新设备状态

        Args:
            device_sn: 设备SN
            status: 设备状态，传 None 时只更新属性、不覆盖状态字段
            attributes: 要更新的属性字典
        """
        try:
            if device_sn in self.devices:
                if status is not None:
                    self.devices[device_sn]["status"] = status
                self.devices[device_sn]["last_update"] = time.time()
                if attributes:
                    # 直接更新属性，后收到的上报会覆盖先前的值
                    # 这样确保使用最后上报的r_travel值代表窗户当前状态
                    if "attributes" not in self.devices[device_sn]:
                        self.devices[device_sn]["attributes"] = {}
                    self.devices[device_sn]["attributes"].update(attributes)
                    # 特别记录r_travel的更新
                    if "r_travel" in attributes:
                        _LOGGER.debug("设备 %s 位置更新: %d", device_sn, attributes["r_travel"])
                    # 特别记录voltage的更新
                    if "voltage" in attributes:
                        _LOGGER.debug("设备 %s 电压更新: %.1fV", device_sn, attributes["voltage"])
                _LOGGER.debug("设备状态更新: %s -> %s", device_sn, status)
            else:
                # 设备不存在，尝试添加
                _LOGGER.debug("设备 %s 不存在，尝试添加", device_sn)
                device_name = get_device_display_name(self.gateway_sn, device_sn)
                # 添加设备
                await self.add_device(device_sn, device_name, DEVICE_TYPE_WINDOW_OPENER)
                # 再次尝试更新状态
                if device_sn in self.devices:
                    if status is not None:
                        self.devices[device_sn]["status"] = status
                    if attributes:
                        if "attributes" not in self.devices[device_sn]:
                            self.devices[device_sn]["attributes"] = {}
                        self.devices[device_sn]["attributes"].update(attributes)
                    _LOGGER.info("设备 %s 已添加并更新状态", device_sn)
        except Exception as e:
            _LOGGER.error("更新设备状态失败: %s", e)
            # 即使失败，也尝试记录错误状态
            try:
                if device_sn in self.devices:
                    self.devices[device_sn]["status"] = "error"
                    self.devices[device_sn]["last_update"] = time.time()
            except Exception:
                _LOGGER.debug("记录设备错误状态失败，可忽略")
            
    def get_device(self, device_sn: str) -> Optional[Dict[str, Any]]:
        """获取设备信息"""
        return self.devices.get(device_sn)
        
    def get_all_devices(self) -> List[Dict[str, Any]]:
        """获取所有设备"""
        # 返回设备列表的浅拷贝，避免外部修改影响内部状态
        return [device.copy() for device in self.devices.values()]

    async def rename_device(self, device_sn: str, new_name: str) -> bool:
        """重命名子设备并同步到HA注册表"""
        new_name = new_name.strip()
        if not new_name or len(new_name) > 50:
            _LOGGER.error("重命名失败：新名称长度必须为 1-50 个字符，当前输入 '%s' 长度为 %d", new_name, len(new_name))
            return False

        if device_sn not in self.devices:
            _LOGGER.error("重命名失败：设备 %s 不存在", device_sn)
            return False

        old_name = self.devices[device_sn]["name"]
        self.devices[device_sn]["name"] = new_name

        from homeassistant.helpers.device_registry import async_get as async_get_device_registry

        device_registry = async_get_device_registry(self.hass)
        # 直接通过 identifiers 查找设备，避免遍历整个设备注册表
        device_entry = device_registry.async_get_device(
            identifiers={(DOMAIN, device_sn)}
        )
        if device_entry:
            device_registry.async_update_device(
                device_entry.id,
                name_by_user=new_name
            )

        # 同步更新按钮别名（供语音集成精确匹配）
        from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

        entity_registry = async_get_entity_registry(self.hass)
        button_name_map = {"open": "开启", "stop": "暂停", "close": "关闭", "a": "内倒"}
        for button_type, button_name in button_name_map.items():
            unique_id = f"{self.gateway_sn}_{device_sn}_{button_type}"
            entity_id = entity_registry.async_get_entity_id("button", DOMAIN, unique_id)
            if entity_id:
                entity_registry.async_update_entity(
                    entity_id,
                    aliases={f"{new_name} {button_name}"}
                )
                _LOGGER.debug(
                    "已更新设备 %s 的 %s 按钮别名: %s",
                    device_sn, button_name, f"{new_name} {button_name}"
                )

        self._trigger_persistent_save()
        _LOGGER.info("设备 %s 重命名成功: %s → %s", device_sn, old_name, new_name)
        return True

    async def _notify_device_conflict(self, device_sn: str, existing_gateway_sn: str) -> None:
        """通知用户设备绑定冲突，需要手动确认转移
        
        当设备已绑定到另一个仍存在的网关时，创建持久化通知，
        提示用户通过 transfer_device 服务手动确认转移。
        
        Args:
            device_sn: 设备SN
            existing_gateway_sn: 设备当前绑定的网关SN
        """
        try:
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": "设备绑定冲突",
                    "message": (
                        f"设备 {device_sn} 已绑定到网关 {existing_gateway_sn}。\n\n"
                        f"如需将此设备转移到当前网关 {self.gateway_sn}，"
                        f"请调用 transfer_device 服务：\n\n"
                        f"  - device_id: {device_sn}\n"
                        f"  - new_gateway_sn: {self.gateway_sn}\n\n"
                        f"或在「开发者工具 → 服务」中执行转移。"
                    ),
                    "notification_id": f"device_conflict_{device_sn}"
                },
                blocking=False
            )
        except Exception as e:
            _LOGGER.error("发送设备冲突通知失败: %s", e)

    async def transfer_device(self, device_sn: str, new_gateway_sn: str) -> bool:
        """将设备从一个网关转移到另一个网关
        
        Args:
            device_sn: 要转移的设备SN
            new_gateway_sn: 目标网关SN
            
        Returns:
            bool: 转移是否成功
        """
        _LOGGER.info("开始转移设备 %s 到网关 %s", device_sn, new_gateway_sn)
        
        # 1. 检查设备是否在映射表中
        if DEVICE_TO_GATEWAY_MAPPING not in self.hass.data[DOMAIN]:
            _LOGGER.error("设备到网关映射表不存在")
            return False
        
        device_to_gateway_mapping = self.hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING]
        
        if device_sn not in device_to_gateway_mapping:
            _LOGGER.error("设备 %s 不在映射表中", device_sn)
            return False
        
        old_gateway_sn = device_to_gateway_mapping[device_sn]
        
        # 大小写不敏感比较
        if old_gateway_sn.lower() == new_gateway_sn.lower():
            _LOGGER.warning("设备 %s 已经在网关 %s 中，无需转移", device_sn, new_gateway_sn)
            return False
        
        # 2. 检查目标网关是否存在
        target_entry_id = None
        old_entry_id = None
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            entry_gw_sn = entry.data.get(CONF_GATEWAY_SN, "")
            if entry_gw_sn.lower() == new_gateway_sn.lower():
                target_entry_id = entry.entry_id
            if entry_gw_sn.lower() == old_gateway_sn.lower():
                old_entry_id = entry.entry_id
        
        if not target_entry_id:
            _LOGGER.error("目标网关 %s 不存在", new_gateway_sn)
            return False
        
        # 3. 更新设备到网关映射表
        device_to_gateway_mapping[device_sn] = new_gateway_sn
        self._save_device_to_gateway_mapping()
        _LOGGER.info("已更新设备 %s 的网关映射: %s -> %s", device_sn, old_gateway_sn, new_gateway_sn)
        
        # 4. 从手动删除列表中移除（如果有）
        if device_sn in self._manually_removed_devices:
            self._manually_removed_devices.discard(device_sn)
            self._save_manually_removed_devices()
            _LOGGER.info("设备 %s 已从手动删除列表中移除", device_sn)
        
        # 5. 更新设备注册表中的关联
        try:
            device_registry = await self._get_device_registry()
            target_entry = self.hass.config_entries.async_get_entry(target_entry_id)
            if target_entry:
                device_registry.async_get_or_create(
                    config_entry_id=target_entry_id,
                    identifiers={(DOMAIN, device_sn)},
                    manufacturer=MANUFACTURER,
                    model="开窗器",
                    via_device=(DOMAIN, new_gateway_sn)
                )
                _LOGGER.info("已更新设备 %s 的注册表关联到网关 %s", device_sn, new_gateway_sn)
        except Exception as e:
            _LOGGER.error("更新设备注册表失败: %s", e)
        
        # 6. 更新实体关联到目标网关的配置条目
        try:
            entity_registry = await self._get_entity_registry()
            device_registry = await self._get_device_registry()
            device = device_registry.async_get_device(identifiers={(DOMAIN, device_sn)})
            target_entry = self.hass.config_entries.async_get_entry(target_entry_id)
            
            if device and target_entry:
                for entity_id, entity_entry in list(entity_registry.entities.items()):
                    if entity_entry.device_id == device.id:
                        if entity_entry.config_entry_id != target_entry_id:
                            entity_registry.async_get_or_create(
                                domain=entity_entry.domain,
                                platform=DOMAIN,
                                unique_id=entity_entry.unique_id,
                                config_entry=target_entry,
                                device_id=device.id,
                            )
                            _LOGGER.debug("已更新实体 %s 的配置条目关联", entity_id)
        except Exception as e:
            _LOGGER.error("更新实体关联失败: %s", e)
        
        # 7. 清除冲突通知（如果有）
        try:
            await self.hass.services.async_call(
                "persistent_notification",
                "dismiss",
                {"notification_id": f"device_conflict_{device_sn}"},
                blocking=False
            )
        except Exception:
            _LOGGER.debug("清除冲突通知失败（可能不存在）")
        
        # 8. 重新加载源网关和目标网关，确保实体正确显示
        try:
            if old_entry_id and old_entry_id != target_entry_id:
                await self.hass.config_entries.async_reload(old_entry_id)
            await self.hass.config_entries.async_reload(target_entry_id)
        except Exception as e:
            _LOGGER.error("重新加载网关失败: %s", e)
        
        _LOGGER.info("设备 %s 转移完成: %s -> %s", device_sn, old_gateway_sn, new_gateway_sn)
        return True

    async def cleanup(self):
        """清理资源"""
        _LOGGER.info("清理设备管理器资源")
        # P1 修复：取消并 await 所有后台任务，避免任务在 cleanup 后访问已清理的状态
        for task in self._background_tasks:
            if not task.done():
                task.cancel()
        for task in self._background_tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                _LOGGER.debug("后台任务取消异常: %s", e)
        self._background_tasks.clear()
        self.devices.clear()
        self._device_registry_cache = None
        # 更彻底的回调清理
        self._device_added_callbacks = []
        self._device_removed_callbacks = []
        self._device_update_callbacks.clear()
        # 注意：不要清空手动删除设备列表，因为这是持久化的状态
        # 当网关重新添加时，需要知道哪些设备是被手动删除的

    async def _validate_gateways_for_migration(self, old_gateway_sn: str, new_gateway_sn: str) -> Dict[str, Any]:
        """验证网关状态是否适合迁移
        
        Args:
            old_gateway_sn: 旧网关的SN号
            new_gateway_sn: 新网关的SN号
        
        Returns:
            Dict: 包含验证结果的字典
                {
                    'valid': bool,  # 是否可以迁移
                    'warnings': List[str],  # 警告信息
                    'errors': List[str]  # 错误信息
                }
        """
        result = {
            'valid': True,
            'warnings': [],
            'errors': []
        }
        
        # 检查新网关是否与当前网关相同
        if new_gateway_sn == self.gateway_sn:
            _LOGGER.info("新网关与当前网关相同")
        
        # 检查旧网关是否在线（改为警告，不影响迁移）
        old_gateway_online = await self._check_gateway_online(old_gateway_sn)
        if not old_gateway_online:
            # 检查旧网关是否存在于设备注册表中
            device_registry = await self._get_device_registry()
            old_gateway_device = device_registry.async_get_device(
                identifiers={(DOMAIN, old_gateway_sn)}
            )
            
            if old_gateway_device:
                warning = f"旧网关 {old_gateway_sn[-6:]} 不在线，但在设备注册表中存在，将从注册表迁移"
                _LOGGER.warning(warning)
                result['warnings'].append(warning)
            else:
                # 检查配置条目是否存在
                old_entry_exists = False
                for entry in self.hass.config_entries.async_entries(DOMAIN):
                    if entry.data.get(CONF_GATEWAY_SN, "").lower() == old_gateway_sn.lower():
                        old_entry_exists = True
                        break
                
                if old_entry_exists:
                    warning = f"旧网关 {old_gateway_sn[-6:]} 不在线，但配置条目存在，将从配置迁移"
                    _LOGGER.warning(warning)
                    result['warnings'].append(warning)
                else:
                    error = f"旧网关 {old_gateway_sn[-6:]} 不在线且不存在于注册表中，无法迁移"
                    _LOGGER.error(error)
                    result['errors'].append(error)
                    result['valid'] = False
        
        # 检查新网关是否有足够容量
        new_gateway_devices = self._count_gateway_devices(new_gateway_sn)
        old_gateway_devices = self._count_gateway_devices(old_gateway_sn)
        
        from .const import MAX_DEVICES_PER_GATEWAY
        if new_gateway_devices + old_gateway_devices > MAX_DEVICES_PER_GATEWAY:
            error = f"新网关容量不足，无法迁移所有设备（当前: {new_gateway_devices}，需要迁移: {old_gateway_devices}，最大: {MAX_DEVICES_PER_GATEWAY}）"
            _LOGGER.error(error)
            result['errors'].append(error)
            result['valid'] = False
        
        # 检查设备兼容性
        incompatible_devices = await self._check_device_compatibility(old_gateway_sn, new_gateway_sn)
        if incompatible_devices:
            warning = f"发现 {len(incompatible_devices)} 个可能不兼容的设备"
            _LOGGER.warning(warning)
            result['warnings'].append(warning)
        
        # 检查设备SN格式合法性
        invalid_device_sns = await self._check_device_sn_format(old_gateway_sn)
        if invalid_device_sns:
            error = f"发现 {len(invalid_device_sns)} 个设备SN格式无效"
            _LOGGER.error(error)
            result['errors'].append(error)
            result['valid'] = False
        
        # 检查设备是否已被手动删除
        manually_removed_devices = await self._check_manually_removed_devices(old_gateway_sn)
        if manually_removed_devices:
            warning = f"发现 {len(manually_removed_devices)} 个设备已被手动删除，将被跳过"
            _LOGGER.warning(warning)
            result['warnings'].append(warning)
        
        return result
    
    async def _check_gateway_online(self, gateway_sn: str) -> bool:
        """检查网关是否在线"""
        try:
            # 查找网关的MQTT处理器
            gateway_sn_lower = gateway_sn.lower()
            for entry_id, data in self.hass.data[DOMAIN].items():
                if isinstance(data, dict) and data.get("gateway_sn", "").lower() == gateway_sn_lower:
                    if "mqtt_handler" in data:
                        mqtt_handler = data["mqtt_handler"]
                        # 检查连接状态
                        if hasattr(mqtt_handler, 'check_connection'):
                            return await mqtt_handler.check_connection()
            return False
        except Exception as e:
            _LOGGER.error("检查网关在线状态失败: %s", e)
            return False
    
    def _count_gateway_devices(self, gateway_sn: str) -> int:
        """统计网关下的设备数量"""
        count = 0
        
        # 从设备到网关映射表中统计
        if DEVICE_TO_GATEWAY_MAPPING in self.hass.data[DOMAIN]:
            device_to_gateway_mapping = self.hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING]
            # P1 修复：使用大小写不敏感比较，与 add_device/remove_device 保持一致
            gateway_sn_lower = gateway_sn.lower()
            for device_sn, mapped_gateway_sn in device_to_gateway_mapping.items():
                if mapped_gateway_sn.lower() == gateway_sn_lower:
                    count += 1
        
        return count
    
    async def _check_device_compatibility(self, old_gateway_sn: str, new_gateway_sn: str) -> List[str]:
        """检查设备兼容性"""
        incompatible_devices = []
        
        try:
            device_registry = await self._get_device_registry()
            
            for device in device_registry.devices.values():
                # 检查设备是否有此集成的标识符
                device_sn = None
                for identifier in device.identifiers:
                    if identifier[0] == DOMAIN:
                        device_sn = identifier[1]
                        break
                
                # 检查设备是否关联到旧网关
                if device_sn and device_sn != old_gateway_sn:
                    if hasattr(device, 'via_device') and device.via_device and device.via_device[1].lower() == old_gateway_sn.lower():
                        # 这里可以添加更详细的兼容性检查
                        # 例如：检查设备型号、固件版本等
                        pass
        except Exception as e:
            _LOGGER.error("检查设备兼容性失败: %s", e)
        
        return incompatible_devices
    
    async def _check_device_sn_format(self, gateway_sn: str) -> List[str]:
        """检查设备SN格式合法性"""
        invalid_device_sns = []
        
        try:
            device_registry = await self._get_device_registry()
            
            for device in device_registry.devices.values():
                # 检查设备是否有此集成的标识符
                device_sn = None
                for identifier in device.identifiers:
                    if identifier[0] == DOMAIN:
                        device_sn = identifier[1]
                        break
                
                # 检查设备是否关联到指定网关
                if device_sn and device_sn != gateway_sn:
                    if hasattr(device, 'via_device') and device.via_device and device.via_device[1].lower() == gateway_sn.lower():
                        # 检查设备SN格式（允许字母和数字）
                        import re
                        if not re.match(r'^[a-zA-Z0-9]+$', device_sn) or len(device_sn) < 10:
                            invalid_device_sns.append(device_sn)
        except Exception as e:
            _LOGGER.error("检查设备SN格式失败: %s", e)
        
        return invalid_device_sns
    
    async def _check_manually_removed_devices(self, gateway_sn: str) -> List[str]:
        """检查设备是否已被手动删除"""
        manually_removed_devices = []
        
        try:
            device_registry = await self._get_device_registry()
            
            for device in device_registry.devices.values():
                # 检查设备是否有此集成的标识符
                device_sn = None
                for identifier in device.identifiers:
                    if identifier[0] == DOMAIN:
                        device_sn = identifier[1]
                        break
                
                # 检查设备是否关联到指定网关
                if device_sn and device_sn != gateway_sn:
                    if hasattr(device, 'via_device') and device.via_device and device.via_device[1].lower() == gateway_sn.lower():
                        # 检查设备是否已被手动删除
                        if device_sn in self._manually_removed_devices:
                            manually_removed_devices.append(device_sn)
        except Exception as e:
            _LOGGER.error("检查手动删除设备失败: %s", e)
        
        return manually_removed_devices

    async def validate_migration(self, old_gateway_sn, new_gateway_sn):
        """执行迁移前的全面检查"""
        _LOGGER.info("执行迁移前检查，旧网关: %s, 新网关: %s", old_gateway_sn, new_gateway_sn)
        
        checks = {
            "gateways_exist": await self._check_gateways_exist(old_gateway_sn, new_gateway_sn),
            "gateways_online": await self._check_gateways_online(old_gateway_sn, new_gateway_sn),
            "device_compatibility": await self._check_device_compatibility_for_validate(old_gateway_sn),
            "capacity_check": self._check_gateway_capacity(new_gateway_sn),
        }
        
        errors = [k for k, v in checks.items() if not v.get("success")]
        warnings = [k for k, v in checks.items() if v.get("warning")]
        
        _LOGGER.info("迁移前检查完成，错误: %s, 警告: %s", errors, warnings)
        
        return {
            "can_proceed": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "details": checks
        }
    
    async def _check_gateways_exist(self, old_gateway_sn, new_gateway_sn):
        """检查网关是否存在（即使不在线）"""
        # 1. 检查配置条目是否存在
        old_entry_exists = False
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.data.get(CONF_GATEWAY_SN, "").lower() == old_gateway_sn.lower():
                old_entry_exists = True
                break
        
        # 2. 检查设备注册表中是否有旧网关设备
        device_registry = await self._get_device_registry()
        old_gateway_device = device_registry.async_get_device(
            identifiers={(DOMAIN, old_gateway_sn)}
        )
        
        return {
            "success": old_entry_exists or old_gateway_device is not None,
            "message": "网关存在" if old_entry_exists else "网关不存在"
        }
    
    async def _check_gateways_online(self, old_gateway_sn, new_gateway_sn):
        """检查网关是否在线"""
        # 这里可以实现检查网关是否在线的逻辑
        return {"success": True, "message": "网关在线"}
    
    async def _check_device_compatibility_for_validate(self, old_gateway_sn):
        """检查设备兼容性（用于验证）"""
        # 这里可以实现检查设备兼容性的逻辑
        return {"success": True, "message": "设备兼容"}
    
    def _check_gateway_capacity(self, new_gateway_sn):
        """检查网关容量"""
        # 这里可以实现检查网关容量的逻辑
        return {"success": True, "message": "容量足够"}
    
    async def _create_migration_snapshot(self, old_gateway_sn):
        """创建迁移快照"""
        # 创建包含更多信息的迁移快照
        old_gateway_devices = await self._get_gateway_devices_from_registry(old_gateway_sn)
        snapshot = {
            "old_gateway_sn": old_gateway_sn,
            "timestamp": time.time(),
            "old_gateway_devices": old_gateway_devices,
            "current_gateway_sn": self.gateway_sn
        }
        _LOGGER.info("创建迁移快照，旧网关: %s，设备数: %d", old_gateway_sn, len(old_gateway_devices))
        return snapshot
    
    async def _transfer_entities_complete(self, old_gateway_sn: str, new_gateway_sn: str):
        """完整转移实体从旧网关到新网关"""
        device_registry = await self._get_device_registry()
        entity_registry = await self._get_entity_registry()
        
        # 获取旧网关设备
        old_gateway_device = device_registry.async_get_device(
            identifiers={(DOMAIN, old_gateway_sn)}
        )
        
        # 获取新网关设备
        new_gateway_device = device_registry.async_get_device(
            identifiers={(DOMAIN, new_gateway_sn)}
        )
        
        if not old_gateway_device or not new_gateway_device:
            _LOGGER.error("无法获取网关设备信息")
            return
        
        # 获取旧网关的所有子设备
        old_gateway_devices = await self._get_gateway_devices_from_registry(old_gateway_sn)
        
        # 5.1 先转移设备关联（关键修复点）
        migrated_devices = []
        
        for device_sn in old_gateway_devices:
            # 查找设备在注册表中的记录
            device = device_registry.async_get_device(
                identifiers={(DOMAIN, device_sn)}
            )
            
            if not device:
                _LOGGER.warning("设备在注册表中未找到: %s，跳过", device_sn)
                continue
            
            # 检查设备是否已经关联到新网关（大小写不敏感）
            if hasattr(device, 'via_device') and device.via_device and device.via_device[1].lower() == new_gateway_sn.lower():
                _LOGGER.debug("设备 %s 已经关联到新网关，跳过", device_sn)
                migrated_devices.append(device_sn)
                continue
            
            # 更新设备关联到新网关
            try:
                device_registry.async_update_device(
                    device.id,
                    via_device=(DOMAIN, new_gateway_sn),  # 这是关键！
                    config_entry_id=self.entry.entry_id  # 更新配置条目ID
                )
                _LOGGER.info("已更新设备 %s 的网关关联到 %s，配置条目ID: %s", device_sn, new_gateway_sn, self.entry.entry_id)
                migrated_devices.append(device_sn)
                
                # 将设备添加到新网关的设备管理器中
                await self.add_device(device_sn, device.name, force=True)
                _LOGGER.info("已将设备 %s 添加到新网关的设备管理器中", device_sn)
            except Exception as e:
                _LOGGER.error("更新设备 %s 的网关关联失败: %s", device_sn, e)
                continue
        
        # 5.2 转移该子设备的所有实体
        transferred_count = 0
        skipped_count = 0
        
        for device_sn in migrated_devices:
            # 获取子设备在设备注册表中的设备ID
            child_device = device_registry.async_get_device(
                identifiers={(DOMAIN, device_sn)}
            )
            
            if not child_device:
                _LOGGER.warning("子设备在设备注册表中未找到: %s", device_sn)
                continue
            
            # 转移该子设备的所有实体
            entity_ids = []
            for entity_id, entity_entry in entity_registry.entities.items():
                if entity_entry.device_id == child_device.id:
                    entity_ids.append(entity_id)
            
            for entity_id in entity_ids:
                try:
                    # 获取实体当前配置
                    entity_entry = entity_registry.async_get(entity_id)
                    if entity_entry:
                        # 重新注册实体，确保与新网关关联
                        entity_registry.async_update_entity(
                            entity_id,
                            device_id=child_device.id
                        )
                        _LOGGER.debug("已转移实体: %s (设备: %s)",
                                     entity_id, child_device.id)
                        transferred_count += 1
                except Exception as e:
                    _LOGGER.error("转移实体失败 %s: %s", entity_id, e)
                    skipped_count += 1
        
        _LOGGER.info("实体转移完成: 成功 %d 个, 跳过 %d 个", transferred_count, skipped_count)
        
        # 5.3 更新设备到网关映射表
        if migrated_devices:
            if DEVICE_TO_GATEWAY_MAPPING not in self.hass.data[DOMAIN]:
                self.hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING] = {}
            
            device_to_gateway_mapping = self.hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING]
            for device_sn in migrated_devices:
                device_to_gateway_mapping[device_sn] = new_gateway_sn  # 更新映射！
            
            _LOGGER.info("已更新 %d 个设备的网关映射", len(migrated_devices))
        
        # 5.4 重新创建平台实体，确保按钮实体正确显示
        if migrated_devices:
            _LOGGER.info("开始重新创建平台实体...")
            await self._recreate_platform_entities(new_gateway_sn, migrated_devices)
            _LOGGER.info("平台实体重新创建完成")
    
    def _is_entity_belongs_to_device(self, entity_entry, device_sn):
        """检查实体是否属于指定设备"""
        # 检查实体的唯一标识符是否包含设备SN
        if entity_entry.unique_id and device_sn in entity_entry.unique_id:
            return True
        return False
    
    async def _recreate_platform_entities(self, new_gateway_sn: str, device_sns: List[str]):
        """重新创建平台实体 - 原地更新配置条目关联，避免删除重建造成的空窗期"""
        from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

        entity_registry = async_get_entity_registry(self.hass)
        device_registry = await self._get_device_registry()

        for platform in self.entity_recreate_platforms:
            for entity_id, entity_entry in entity_registry.entities.items():
                if entity_entry.platform == DOMAIN and entity_entry.domain == platform:
                    for device_sn in device_sns:
                        if device_sn in entity_entry.unique_id:
                            new_device = device_registry.async_get_device(
                                identifiers={(DOMAIN, device_sn)}
                            )
                            if new_device and entity_entry.config_entry_id != self.entry.entry_id:
                                entity_registry.async_get_or_create(
                                    domain=entity_entry.domain,
                                    platform=DOMAIN,
                                    unique_id=entity_entry.unique_id,
                                    config_entry=self.entry,
                                    device_id=new_device.id,
                                )
                                _LOGGER.debug(
                                    "已更新实体 %s 的配置条目关联", entity_id
                                )
                            break

        for device_sn in device_sns:
            device = device_registry.async_get_device(
                identifiers={(DOMAIN, device_sn)}
            )
            if device:
                await self._notify_device_added_callbacks(
                    device_sn, device.name, DEVICE_TYPE_WINDOW_OPENER
                )

    async def _verify_entity_migration(self, old_gateway_sn: str, new_gateway_sn: str) -> bool:
        """验证实体迁移是否成功"""
        entity_registry = await self._get_entity_registry()
        device_registry = await self._get_device_registry()
        
        # 获取新网关设备
        new_gateway_device = device_registry.async_get_device(
            identifiers={(DOMAIN, new_gateway_sn)}
        )
        
        if not new_gateway_device:
            _LOGGER.error("新网关设备未找到")
            return False
        
        # 获取旧网关的设备列表（用于验证迁移完整性）
        old_gateway_devices = await self._get_gateway_devices_from_registry(old_gateway_sn)
        _LOGGER.info("旧网关有 %d 个设备需要迁移", len(old_gateway_devices))
        
        # 检查所有与新网关关联的设备
        migrated_devices = []
        for device in device_registry.devices.values():
            if hasattr(device, 'via_device') and device.via_device:
                if device.via_device[1].lower() == new_gateway_sn.lower():
                    migrated_devices.append(device)
        
        _LOGGER.info("新网关关联了 %d 个设备", len(migrated_devices))
        
        # 如果没有设备关联到新网关，验证失败
        if len(migrated_devices) == 0:
            _LOGGER.warning("没有设备关联到新网关")
            return False
        
        # 验证旧网关的设备是否都已迁移到新网关
        migrated_device_sns = []
        for device in migrated_devices:
            for identifier in device.identifiers:
                if identifier[0] == DOMAIN:
                    migrated_device_sns.append(identifier[1])
                    break
        
        # 检查未迁移的设备
        not_migrated = []
        for device_sn in old_gateway_devices:
            if device_sn not in migrated_device_sns:
                not_migrated.append(device_sn)
        
        if not_migrated:
            _LOGGER.warning("以下设备未迁移: %s", not_migrated)
        else:
            _LOGGER.info("所有旧网关设备都已成功迁移")
        
        # 检查每个设备的实体
        total_entities = 0
        entities_with_issues = []
        
        for device in migrated_devices:
            device_entities = []
            for entity_id, entity_entry in entity_registry.entities.items():
                if entity_entry.device_id == device.id:
                    device_entities.append(entity_id)
            
            _LOGGER.info("设备 %s 有 %d 个实体", device.name, len(device_entities))
            total_entities += len(device_entities)
            
            # 检查设备是否有实体（某些设备可能没有实体，这是正常的）
            if len(device_entities) == 0:
                device_sn = None
                for identifier in device.identifiers:
                    if identifier[0] == DOMAIN:
                        device_sn = identifier[1]
                        break
                if device_sn:
                    _LOGGER.info("设备 %s 没有实体（这可能是正常的）", device_sn)
        
        _LOGGER.info("总共 %d 个实体已迁移到新网关", total_entities)
        
        # 检查实体关联问题
        if entities_with_issues:
            _LOGGER.warning("以下实体存在关联问题: %s", entities_with_issues)
        
        # 优化验证逻辑：
        # 1. 如果有旧网关设备需要迁移，至少要有一个设备成功迁移
        # 2. 如果没有旧网关设备需要迁移，验证通过
        # 3. 实体数量不是验证的必要条件，因为某些设备可能没有实体
        if old_gateway_devices:
            return len(migrated_devices) > 0
        else:
            # 没有旧网关设备需要迁移，验证通过
            _LOGGER.info("没有旧网关设备需要迁移，验证通过")
            return True
    
    async def _get_gateway_devices_from_registry(self, gateway_sn):
        """从设备注册表中获取网关的设备信息（即使不在线）"""
        device_registry = await self._get_device_registry()
        gateway_devices = []
        
        _LOGGER.info("开始查找网关 %s 的设备，总设备数: %d", gateway_sn, len(device_registry.devices))
        
        # 使用生成器表达式和内置函数优化查找过程
        for device in device_registry.devices.values():
            # 检查设备是否有此集成的标识符
            device_sn = next(
                (identifier[1] for identifier in device.identifiers if identifier[0] == DOMAIN),
                None
            )
            
            # 只有当设备有此集成的标识符且不是网关本身时才处理
            if device_sn and device_sn != gateway_sn:
                # 检查设备是否关联到指定网关
                via_device_info = getattr(device, 'via_device', None)
                if via_device_info and via_device_info[1].lower() == gateway_sn.lower():
                    gateway_devices.append(device_sn)
                    _LOGGER.info("找到关联到网关 %s 的设备: %s", gateway_sn, device_sn)
        
        _LOGGER.info("网关 %s 共找到 %d 个设备", gateway_sn, len(gateway_devices))
        return gateway_devices
    
    async def _validate_migration(self, old_gateway_devices, new_gateway_sn):
        """验证设备兼容性和容量"""
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": []
        }
        
        # 1. 验证设备类型兼容性
        for device_sn in old_gateway_devices:
            # 检查设备是否为开窗器类型
            device_info = self.devices.get(device_sn)
            if device_info and device_info.get("type") != DEVICE_TYPE_WINDOW_OPENER:
                error = f"设备 {device_sn} 类型不兼容，仅支持开窗器"
                _LOGGER.error(error)
                validation_result["errors"].append(error)
                validation_result["valid"] = False
        
        # 2. 验证新网关容量
        new_gateway_devices_count = self._count_gateway_devices(new_gateway_sn)
        total_devices_after_migration = new_gateway_devices_count + len(old_gateway_devices)
        
        from .const import MAX_DEVICES_PER_GATEWAY
        if total_devices_after_migration > MAX_DEVICES_PER_GATEWAY:
            error = f"新网关容量不足，迁移后设备数 {total_devices_after_migration} 超过最大限制 {MAX_DEVICES_PER_GATEWAY}"
            _LOGGER.error(error)
            validation_result["errors"].append(error)
            validation_result["valid"] = False
        
        # 3. 验证设备SN格式合法性
        invalid_device_sns = []
        import re
        for device_sn in old_gateway_devices:
            if not re.match(r'^[a-zA-Z0-9]+$', device_sn) or len(device_sn) < 10:
                invalid_device_sns.append(device_sn)
        
        if invalid_device_sns:
            error = f"发现 {len(invalid_device_sns)} 个设备SN格式无效"
            _LOGGER.error(error)
            validation_result["errors"].append(error)
            validation_result["valid"] = False
        
        # 4. 检查设备是否已被手动删除
        manually_removed_devices = []
        for device_sn in old_gateway_devices:
            if device_sn in self._manually_removed_devices:
                manually_removed_devices.append(device_sn)
        
        if manually_removed_devices:
            warning = f"发现 {len(manually_removed_devices)} 个设备已被手动删除，将被跳过"
            _LOGGER.warning(warning)
            validation_result["warnings"].append(warning)
        
        return validation_result
    
    async def _transfer_all_entities(self, old_gateway_sn, new_gateway_sn):
        """转移所有实体从旧网关到新网关"""
        # 使用新的完整实体转移方法
        await self._transfer_entities_complete(old_gateway_sn, new_gateway_sn)
    
    async def _update_config_entries(self, old_gateway_sn, new_gateway_sn):
        """更新配置条目"""
        # 更新配置条目的逻辑
        # 例如：更新设备到网关映射表等
        _LOGGER.info("更新配置条目，旧网关: %s, 新网关: %s", old_gateway_sn, new_gateway_sn)
        
        # 注意：设备到网关映射表的更新已经在 _transfer_entities_complete 方法中完成
        # 这里不需要重复更新，避免性能问题
    
    async def _cleanup_old_gateway(self, old_gateway_sn):
        """清理旧网关"""
        _LOGGER.info("开始清理旧网关: %s", old_gateway_sn)
        
        # 清理旧网关的逻辑
        # 例如：清理旧网关的设备关联、实体等
        
        # 清理设备到网关映射表中的旧网关映射 - 注意：只清理未迁移的设备
        if DEVICE_TO_GATEWAY_MAPPING in self.hass.data[DOMAIN]:
            device_to_gateway_mapping = self.hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING]
            old_gateway_devices = await self._get_gateway_devices_from_registry(old_gateway_sn)
            
            for device_sn in old_gateway_devices:
                if device_sn in device_to_gateway_mapping and device_to_gateway_mapping[device_sn].lower() == old_gateway_sn.lower():
                    del device_to_gateway_mapping[device_sn]
                    _LOGGER.info("已清理设备 %s 的旧网关映射", device_sn)
        
        # 清理旧网关设备本身
        try:
            device_registry = await self._get_device_registry()
            old_gateway_device = device_registry.async_get_device(
                identifiers={(DOMAIN, old_gateway_sn)}
            )
            
            if old_gateway_device:
                # 从设备注册表中删除旧网关设备
                device_registry.async_remove_device(old_gateway_device.id)
                _LOGGER.info("已从设备注册表中删除旧网关: %s", old_gateway_sn)
        except Exception as e:
            _LOGGER.error("删除旧网关设备失败: %s", e)
    
    async def safe_migrate_devices(self, old_gateway_sn, new_gateway_sn):
        """安全的设备迁移流程（支持旧网关不在线）"""
        _LOGGER.info("开始安全迁移流程，旧网关: %s, 新网关: %s", old_gateway_sn, new_gateway_sn)
        
        # 1. 验证新网关存在且在线
        if not await self._check_gateway_online(new_gateway_sn):
            raise Exception("新网关必须在线")
        
        # 2. 获取旧网关的设备信息（即使不在线）
        old_gateway_devices = await self._get_gateway_devices_from_registry(old_gateway_sn)
        
        if not old_gateway_devices:
            _LOGGER.info("旧网关 %s 没有设备需要迁移", old_gateway_sn)
            return True, []
        
        # 3. 验证设备兼容性和容量
        validation_result = await self._validate_migration(
            old_gateway_devices, new_gateway_sn
        )
        
        if not validation_result["valid"]:
            raise Exception(f"迁移验证失败: {validation_result['errors']}")
        
        # 4. 创建迁移快照，用于回滚
        snapshot = await self._create_migration_snapshot(old_gateway_sn)
        
        # 5. 执行迁移（使用数据库事务或回滚机制）
        try:
            # 5.1 转移实体（包括更新设备via_device和映射表）
            await self._transfer_all_entities(old_gateway_sn, new_gateway_sn)
            
            # 5.2 更新配置条目
            await self._update_config_entries(old_gateway_sn, new_gateway_sn)
            
            _LOGGER.info("安全迁移流程完成，成功迁移 %d 个设备", len(old_gateway_devices))
            return True, old_gateway_devices
            
        except Exception as e:
            # 6. 回滚机制
            _LOGGER.error("迁移失败，执行回滚: %s", e)
            await self._rollback_migration(snapshot)
            raise
    
    async def _rollback_migration(self, snapshot):
        """执行迁移回滚"""
        _LOGGER.info("执行迁移回滚，快照: %s", snapshot)
        
        # 这里可以实现真正的回滚逻辑
        # 例如：恢复设备到网关映射表、恢复设备关联等
        
        # 1. 从快照中获取旧网关SN
        old_gateway_sn = snapshot.get("old_gateway_sn")
        
        if not old_gateway_sn:
            _LOGGER.error("快照中缺少旧网关SN，无法回滚")
            return False
        
        # 2. 查找旧网关的 config_entry_id（回滚时必须使用旧网关的 entry_id，
        #    而非 self.entry.entry_id 即新网关的 entry_id，否则设备关联不一致）
        old_gateway_entry_id = None
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.data.get(CONF_GATEWAY_SN, "").lower() == old_gateway_sn.lower():
                old_gateway_entry_id = entry.entry_id
                break

        if not old_gateway_entry_id:
            _LOGGER.warning("旧网关 %s 的配置条目不存在，回滚时无法恢复 config_entry_id，"
                           "将使用新网关的 entry_id 作为回退", old_gateway_sn)
            old_gateway_entry_id = self.entry.entry_id

        # 3. 恢复设备到旧网关
        try:
            device_registry = await self._get_device_registry()

            # 查找所有需要回滚的设备
            for device in device_registry.devices.values():
                # 检查设备是否有此集成的标识符
                device_sn = None
                for identifier in device.identifiers:
                    if identifier[0] == DOMAIN:
                        device_sn = identifier[1]
                        break

                # 只有当设备有此集成的标识符且不是网关本身时才处理
                if device_sn and device_sn != old_gateway_sn:
                    # 检查设备是否关联到当前网关（新网关）
                    if hasattr(device, 'via_device') and device.via_device and device.via_device[1].lower() == self.gateway_sn.lower():
                        # 恢复设备关联到旧网关：使用旧网关的 config_entry_id 和 via_device
                        device_registry.async_get_or_create(
                            config_entry_id=old_gateway_entry_id,
                            identifiers={(DOMAIN, device_sn)},
                            name=device.name,
                            manufacturer=MANUFACTURER,
                            model=device.model,
                            via_device=(DOMAIN, old_gateway_sn)
                        )
                        _LOGGER.info("已回滚设备 %s 到旧网关 %s (entry_id=%s)",
                                     device_sn, old_gateway_sn, old_gateway_entry_id)
            
            # 4. 恢复设备到网关映射表
            if DEVICE_TO_GATEWAY_MAPPING in self.hass.data[DOMAIN]:
                device_to_gateway_mapping = self.hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING]
                
                # 查找所有需要回滚的设备
                old_gateway_devices = await self._get_gateway_devices_from_registry(self.gateway_sn)
                for device_sn in old_gateway_devices:
                    device_to_gateway_mapping[device_sn] = old_gateway_sn
                    _LOGGER.info("已恢复设备 %s 的网关映射到旧网关", device_sn)
            
            _LOGGER.info("迁移回滚完成")
            return True
            
        except Exception as e:
            _LOGGER.error("回滚失败: %s", e)
            return False

    async def migrate_devices(self, old_gateway_sn: str, delete_old_devices: bool = False):
        """将子设备从旧网关迁移到当前网关
        
        Args:
            old_gateway_sn: 旧网关的SN号
            delete_old_devices: 是否删除旧网关的子设备，默认为False
        
        Returns:
            bool: 迁移是否成功
        """
        # 双重检查避免不必要的锁获取
        if self._is_migrating:
            _LOGGER.warning("设备迁移正在进行中，请等待")
            return False
        
        async with self._migration_lock:
            if self._is_migrating:  # 再次检查
                return False
            
            self._is_migrating = True
            try:
                return await self._do_migrate(old_gateway_sn, delete_old_devices)
            finally:
                self._is_migrating = False
    
    async def _do_migrate(self, old_gateway_sn: str, delete_old_devices: bool = False):
        """执行实际的迁移逻辑"""
        _LOGGER.info("开始将设备从旧网关 %s 迁移到新网关 %s", old_gateway_sn, self.gateway_sn)
        
        # 验证网关状态
        validation_result = await self._validate_gateways_for_migration(old_gateway_sn, self.gateway_sn)
                
        # 记录验证结果
        if validation_result['warnings']:
            for warning in validation_result['warnings']:
                _LOGGER.warning("迁移警告: %s", warning)
        
        if validation_result['errors']:
            for error in validation_result['errors']:
                _LOGGER.error("迁移错误: %s", error)
            return False
        
        device_registry = await self._get_device_registry()
        migrated_devices = []
        old_devices = []
        
        # 创建备份，用于回滚
        backup = {
            'devices': self.devices.copy(),
            'mapping': self.hass.data[DOMAIN].get(DEVICE_TO_GATEWAY_MAPPING, {}).copy(),
            'migrated_devices': []
        }
        
        # 计算需要迁移的设备总数
        total_devices = 0
        for device in device_registry.devices.values():
            has_domain_identifier = False
            device_sn = None
            for identifier in device.identifiers:
                if identifier[0] == DOMAIN:
                    has_domain_identifier = True
                    device_sn = identifier[1]
                    break
            
            if has_domain_identifier and device_sn and device_sn != old_gateway_sn:
                if hasattr(device, 'via_device') and device.via_device and device.via_device[1].lower() == old_gateway_sn.lower():
                    total_devices += 1
        
        migrated_count = 0
        
        # 查找旧网关关联的所有子设备
        for device in device_registry.devices.values():
            # 检查设备是否有此集成的标识符
            has_domain_identifier = False
            device_sn = None
            
            for identifier in device.identifiers:
                if identifier[0] == DOMAIN:
                    has_domain_identifier = True
                    device_sn = identifier[1]
                    break
            
            # 只有当设备有此集成的标识符且不是网关本身时才处理
            if has_domain_identifier and device_sn and device_sn != old_gateway_sn:
                # 检查设备是否关联到旧网关
                if hasattr(device, 'via_device') and device.via_device and device.via_device[1].lower() == old_gateway_sn.lower():
                    _LOGGER.info("找到关联到旧网关的设备: %s", device_sn)
                    old_devices.append(device_sn)
                    
                    # 检查配置条目是否存在
                    config_entry = self.hass.config_entries.async_get_entry(self.entry.entry_id)
                    if not config_entry:
                        _LOGGER.error("配置条目不存在，无法迁移设备: %s", device_sn)
                        continue
                    
                    # 更新设备注册信息，将其关联到新网关
                    updated_device = device_registry.async_get_or_create(
                        config_entry_id=self.entry.entry_id,
                        identifiers={(DOMAIN, device_sn)},
                        name=device.name,
                        manufacturer=MANUFACTURER,
                        model=device.model,
                        via_device=(DOMAIN, self.gateway_sn)
                    )
                    
                    # 验证设备关联是否正确更新
                    if hasattr(updated_device, 'via_device') and updated_device.via_device and updated_device.via_device[1].lower() == self.gateway_sn.lower():
                        _LOGGER.info("设备 %s 已成功迁移到新网关", device_sn)
                        migrated_devices.append(device_sn)
                        backup['migrated_devices'].append(device_sn)
                        
                        # 先更新设备到网关映射表，将设备从旧网关映射到新网关
                        if DEVICE_TO_GATEWAY_MAPPING in self.hass.data[DOMAIN]:
                            device_to_gateway_mapping = self.hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING]
                            device_to_gateway_mapping[device_sn] = self.gateway_sn
                            _LOGGER.info("设备 %s 的网关映射已更新为 %s", device_sn, self.gateway_sn)
                        
                        # 将设备添加到当前网关的设备列表中（使用 force=True 跳过检查）
                        await self.add_device(device_sn, device.name, force=True)
                        
                        # 更新迁移计数并发送进度通知（仅在成功迁移时递增）
                        migrated_count += 1
                        
                        # 减少通知频率，每5个设备或每20%进度发送一次通知
                        # 检查是否需要发送进度通知
                        should_notify = self._should_notify_progress(migrated_count, total_devices)
                        
                        if should_notify:
                            try:
                                progress_percent = (migrated_count / total_devices) * 100 if total_devices > 0 else 100
                                await self.hass.services.async_call(
                                    "persistent_notification",
                                    "create",
                                    {
                                        "title": "设备迁移进度",
                                        "message": (
                                            f"迁移进度: {migrated_count}/{total_devices} ({progress_percent:.1f}%)\n"
                                            f"最新迁移: {device.name} ({device_sn[-6:]})\n"
                                            f"旧网关: {old_gateway_sn[-6:]} \n"
                                            f"新网关: {self.gateway_sn[-6:]}"
                                        ),
                                        "notification_id": "window_controller_migration"
                                    },
                                    blocking=False
                                )
                            except Exception as notify_error:
                                _LOGGER.warning("发送进度通知失败: %s", notify_error)
                else:
                    _LOGGER.warning("设备 %s 未成功迁移到新网关", device_sn)
        
        # 统一转移所有实体，避免重复处理
        if migrated_devices:
            try:
                _LOGGER.info("开始统一转移所有实体的关联")
                await self._transfer_entities_complete(
                    old_gateway_sn,
                    self.gateway_sn
                )
                _LOGGER.info("已统一转移所有实体的关联")
            except Exception as e:
                _LOGGER.error("统一转移实体失败: %s", e)
            
            # 如果需要删除旧网关的子设备
            if delete_old_devices and old_devices:
                _LOGGER.info("开始删除旧网关 %s 的子设备", old_gateway_sn)
                
                # 获取实体注册表，用于清理旧网关的实体
                entity_registry = await self._get_entity_registry()
                
                for device_sn in old_devices:
                    # 清理旧网关的实体
                    _LOGGER.info("开始清理设备 %s 的旧网关实体", device_sn)
                    
                    # 查找与该设备关联的所有实体
                    # P0 修复：使用 list() 创建副本再遍历，避免在遍历 entity_registry.entities 时
                    # 调用 async_remove 修改字典导致 RuntimeError: dictionary changed size during iteration
                    for entity_id, entity_entry in list(entity_registry.entities.items()):
                        if entity_entry.device_id:
                            # 检查实体是否属于当前设备
                            device = device_registry.async_get(entity_entry.device_id)
                            if device:
                                for identifier in device.identifiers:
                                    if identifier[0] == DOMAIN and identifier[1] == device_sn:
                                        # 从实体注册表中删除实体
                                        try:
                                            entity_registry.async_remove(entity_id)
                                            _LOGGER.info("已清理旧网关实体: %s", entity_id)
                                        except Exception as e:
                                            _LOGGER.error("清理旧网关实体失败: %s", e)
            
        # 发送迁移完成通知
        if migrated_devices:
            _LOGGER.info("设备迁移完成，成功迁移 %d 个设备", len(migrated_devices))
            try:
                await self.hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "title": "设备迁移完成",
                        "message": (
                            f"成功将 {len(migrated_devices)} 个设备从旧网关 {old_gateway_sn[-6:]} 迁移到新网关 {self.gateway_sn[-6:]}\n"
                            f"迁移的设备包括: {', '.join([d[-6:] for d in migrated_devices])}"
                        ),
                        "notification_id": "window_controller_migration"
                    },
                    blocking=False
                )
            except Exception as notify_error:
                _LOGGER.warning("发送迁移完成通知失败: %s", notify_error)
        else:
            _LOGGER.info("没有设备需要迁移")
        
        return True
    
    def _should_notify_progress(self, current_count, total_count):
        """检查是否需要发送进度通知
        
        减少通知频率，每5个设备或每20%进度发送一次通知
        """
        if total_count == 0:
            return False
        
        # 每5个设备发送一次通知
        if current_count % 5 == 0:
            return True
        
        # 每20%进度边界发送一次通知（使用整数除法判断是否跨越边界）
        # 例如 total=7: 20%边界在 2/7, 4/7（近似），此处用整数倍数检测
        prev_percent = ((current_count - 1) * 100) // total_count
        curr_percent = (current_count * 100) // total_count
        if prev_percent // 20 != curr_percent // 20:
            return True
        
        # 迁移完成时发送通知
        if current_count == total_count:
            return True
        
        return False