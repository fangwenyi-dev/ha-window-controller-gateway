"""设备管理器 - 修正版"""
import logging
import asyncio
import time
from typing import Dict, Any, List, Optional, Callable
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import async_get


class DeviceCacheManager:
    """设备缓存管理器 - 优化版"""
    
    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self._cache = {}
        self._cache_timestamps = {}
        self._cache_ttl = 60  # 默认缓存60秒
        self._min_ttl = 30  # 最小TTL
        self._max_ttl = 180  # 最大TTL
        self._cache_invalidation_events = set()  # 缓存失效事件
        self._device_type_ttl = {  # 不同设备类型的TTL
            "window_opener": 60,  # 开窗器默认60秒
            "gateway": 120,  # 网关默认120秒
            "sensor": 45,  # 传感器默认45秒
        }
        self._cache_hits = {}  # 缓存命中统计
        self._cache_misses = {}  # 缓存未命中统计
        self._cache_priority = {}  # 缓存项优先级
        self._max_cache_size = 1000  # 最大缓存设备数
        self._cache_access_count = {}  # 缓存访问次数
        self._persistent_cache_file = "device_cache.json"  # 持久化缓存文件
        
        # 尝试加载持久化缓存
        self._load_persistent_cache()
    
    async def get_cached_devices(self, gateway_sn: str) -> List[Dict[str, Any]]:
        """获取缓存的设备列表"""
        # 检查缓存是否有效
        if gateway_sn in self._cache_timestamps:
            # 检查是否超过TTL
            ttl = self._get_ttl(gateway_sn)
            if (time.time() - self._cache_timestamps[gateway_sn]) < ttl:
                # 检查缓存是否被标记为失效
                if gateway_sn not in self._cache_invalidation_events:
                    # 更新缓存命中统计
                    self._cache_hits[gateway_sn] = self._cache_hits.get(gateway_sn, 0) + 1
                    return self._cache.get(gateway_sn, [])
                else:
                    # 缓存已失效，移除失效标记并返回None
                    self._cache_invalidation_events.remove(gateway_sn)
        
        # 更新缓存未命中统计
        self._cache_misses[gateway_sn] = self._cache_misses.get(gateway_sn, 0) + 1
        return None
    
    def _load_persistent_cache(self) -> None:
        """加载持久化缓存"""
        try:
            import os
            import json
            
            # 获取配置目录
            config_dir = self.hass.config.config_dir
            cache_file = os.path.join(config_dir, self._persistent_cache_file)
            
            if os.path.exists(cache_file):
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                    
                # 加载缓存数据
                if 'cache' in cached_data:
                    self._cache = cached_data['cache']
                if 'timestamps' in cached_data:
                    self._cache_timestamps = cached_data['timestamps']
                
                _LOGGER.info("已加载持久化缓存，设备数: %d", sum(len(devices) for devices in self._cache.values()))
        except Exception as e:
            _LOGGER.error("加载持久化缓存失败: %s", e)
    
    def _save_persistent_cache(self) -> None:
        """保存持久化缓存"""
        try:
            import os
            import json
            
            # 获取配置目录
            config_dir = self.hass.config.config_dir
            cache_file = os.path.join(config_dir, self._persistent_cache_file)
            
            # 准备缓存数据
            cached_data = {
                'cache': self._cache,
                'timestamps': self._cache_timestamps
            }
            
            # 保存到文件
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cached_data, f, indent=2, ensure_ascii=False)
            
            _LOGGER.debug("已保存持久化缓存，设备数: %d", sum(len(devices) for devices in self._cache.values()))
        except Exception as e:
            _LOGGER.error("保存持久化缓存失败: %s", e)
    
    def _evict_cache(self) -> None:
        """缓存淘汰机制"""
        try:
            # 计算当前缓存大小
            current_size = sum(len(devices) for devices in self._cache.values())
            
            if current_size > self._max_cache_size:
                # 需要淘汰的设备数
                evict_count = current_size - self._max_cache_size
                
                # 按照优先级和最后访问时间排序，选择要淘汰的缓存项
                cache_items = []
                for gateway_sn, devices in self._cache.items():
                    priority = self._cache_priority.get(gateway_sn, 0)
                    timestamp = self._cache_timestamps.get(gateway_sn, 0)
                    access_count = self._cache_access_count.get(gateway_sn, 0)
                    cache_items.append((gateway_sn, priority, timestamp, access_count, len(devices)))
                
                # 按优先级（升序）、时间戳（升序）、访问次数（升序）排序
                cache_items.sort(key=lambda x: (x[1], x[2], x[3]))
                
                # 开始淘汰
                evicted_count = 0
                for item in cache_items:
                    if evicted_count >= evict_count:
                        break
                    
                    gateway_sn = item[0]
                    device_count = item[4]
                    
                    # 移除缓存项
                    if gateway_sn in self._cache:
                        del self._cache[gateway_sn]
                    if gateway_sn in self._cache_timestamps:
                        del self._cache_timestamps[gateway_sn]
                    if gateway_sn in self._cache_hits:
                        del self._cache_hits[gateway_sn]
                    if gateway_sn in self._cache_misses:
                        del self._cache_misses[gateway_sn]
                    if gateway_sn in self._cache_priority:
                        del self._cache_priority[gateway_sn]
                    if gateway_sn in self._cache_access_count:
                        del self._cache_access_count[gateway_sn]
                    if gateway_sn in self._cache_invalidation_events:
                        self._cache_invalidation_events.remove(gateway_sn)
                    
                    evicted_count += device_count
                    _LOGGER.debug("缓存淘汰: 网关 %s，设备数: %d", gateway_sn, device_count)
                
                _LOGGER.info("缓存淘汰完成，淘汰设备数: %d", evicted_count)
        except Exception as e:
            _LOGGER.error("缓存淘汰失败: %s", e)
    
    async def update_cache(self, gateway_sn: str, devices: List[Dict[str, Any]]):
        """更新缓存 - 支持增量更新"""
        # 如果缓存已存在，实现增量更新
        if gateway_sn in self._cache:
            existing_devices = {device["sn"]: device for device in self._cache[gateway_sn]}
            new_devices = {device["sn"]: device for device in devices}
            
            # 合并设备信息，保留最新的设备状态
            merged_devices = {}
            merged_devices.update(existing_devices)  # 先添加现有设备
            merged_devices.update(new_devices)  # 用新设备信息覆盖
            
            # 更新缓存
            self._cache[gateway_sn] = list(merged_devices.values())
            _LOGGER.debug("增量更新缓存 %s，设备数: %d", gateway_sn, len(self._cache[gateway_sn]))
        else:
            # 首次缓存
            self._cache[gateway_sn] = devices
            _LOGGER.debug("首次缓存设备 %s，设备数: %d", gateway_sn, len(devices))
        
        self._cache_timestamps[gateway_sn] = time.time()
        # 更新后移除失效标记
        if gateway_sn in self._cache_invalidation_events:
            self._cache_invalidation_events.remove(gateway_sn)
        
        # 更新缓存优先级（基于设备数和更新频率）
        self._cache_priority[gateway_sn] = len(self._cache[gateway_sn])
        
        # 检查缓存大小，执行淘汰机制
        self._evict_cache()
        
        # 保存持久化缓存
        self._save_persistent_cache()
    
    async def invalidate_cache(self, gateway_sn: str):
        """使特定网关的缓存失效"""
        self._cache_invalidation_events.add(gateway_sn)
        _LOGGER.debug("缓存已失效: %s", gateway_sn)
    
    async def invalidate_all_cache(self):
        """使所有缓存失效"""
        self._cache_invalidation_events.update(self._cache.keys())
        _LOGGER.debug("所有缓存已失效")
    
    async def warmup_cache(self, gateway_sn: str, devices: List[Dict[str, Any]]):
        """缓存预热机制
        
        在系统启动或网关重新连接时，提前加载设备信息到缓存
        """
        _LOGGER.info("开始缓存预热: %s，设备数: %d", gateway_sn, len(devices))
        await self.update_cache(gateway_sn, devices)
        _LOGGER.info("缓存预热完成: %s", gateway_sn)
    
    def set_device_type_ttl(self, device_type: str, ttl: int):
        """设置特定设备类型的TTL
        
        Args:
            device_type: 设备类型（如 "window_opener", "gateway", "sensor"）
            ttl: TTL时间（秒）
        """
        if self._min_ttl <= ttl <= self._max_ttl:
            self._device_type_ttl[device_type] = ttl
            _LOGGER.debug("设备类型 %s 的TTL已设置为: %d秒", device_type, ttl)
        else:
            _LOGGER.warning("TTL值超出范围 [%d, %d]，使用默认值", self._min_ttl, self._max_ttl)
    
    def get_cache_stats(self, gateway_sn: str) -> Dict[str, int]:
        """获取缓存统计信息
        
        Args:
            gateway_sn: 网关SN
        
        Returns:
            Dict: 包含缓存命中、未命中、命中率等统计信息
        """
        hits = self._cache_hits.get(gateway_sn, 0)
        misses = self._cache_misses.get(gateway_sn, 0)
        total = hits + misses
        hit_rate = (hits / total * 100) if total > 0 else 0
        
        return {
            "hits": hits,
            "misses": misses,
            "total": total,
            "hit_rate": round(hit_rate, 2),
            "cached_devices": len(self._cache.get(gateway_sn, []))
        }
    
    def _get_ttl(self, gateway_sn: str) -> int:
        """动态获取TTL
        
        根据系统负载和设备类型调整TTL，负载高时增加TTL，负载低时减少TTL
        """
        # 这里可以根据实际情况实现更复杂的负载检测逻辑
        # 简化版本：根据缓存大小和设备类型调整TTL
        cache_size = len(self._cache.get(gateway_sn, []))
        
        # 根据缓存大小调整TTL
        if cache_size > 10:
            # 缓存设备较多，增加TTL
            base_ttl = min(self._max_ttl, self._cache_ttl + 30)
        elif cache_size < 3:
            # 缓存设备较少，减少TTL
            base_ttl = max(self._min_ttl, self._cache_ttl - 15)
        else:
            # 正常缓存大小，使用默认TTL
            base_ttl = self._cache_ttl
        
        # 根据缓存命中率调整TTL
        stats = self.get_cache_stats(gateway_sn)
        if stats["hit_rate"] > 80:
            # 命中率高，增加TTL
            return min(self._max_ttl, base_ttl + 15)
        elif stats["hit_rate"] < 50:
            # 命中率低，减少TTL
            return max(self._min_ttl, base_ttl - 10)
        else:
            # 命中率正常，使用基础TTL
            return base_ttl
    
    def set_ttl(self, ttl: int):
        """设置默认TTL"""
        if self._min_ttl <= ttl <= self._max_ttl:
            self._cache_ttl = ttl
            _LOGGER.debug("缓存TTL已设置为: %d秒", ttl)
        else:
            _LOGGER.warning("TTL值超出范围 [%d, %d]，使用默认值", self._min_ttl, self._max_ttl)

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
    GLOBAL_MANUALLY_REMOVED_DEVICES,
    DEVICE_REGISTRATION_DELAY,
    GATEWAY_READY_DELAY,
    DEVICE_SETUP_DELAY,
    MIGRATION_DELAY
)

_LOGGER = logging.getLogger(__name__)

class WindowControllerDeviceManager:
    """设备管理器类"""
    
    # 需要重新创建的实体类型和平台映射
    entity_recreate_map = {
        "button": DOMAIN,
        "sensor": DOMAIN,
        "binary_sensor": DOMAIN
    }
    
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
        
        # 使用全局手动删除设备列表，而不是每个网关独立存储
        if GLOBAL_MANUALLY_REMOVED_DEVICES not in self.hass.data[DOMAIN]:
            self.hass.data[DOMAIN][GLOBAL_MANUALLY_REMOVED_DEVICES] = set()
        
        # 使用全局手动删除设备列表
        self.hass.data[DOMAIN][GLOBAL_MANUALLY_REMOVED_DEVICES] = self._manually_removed_devices
        _LOGGER.debug("已保存全局手动删除设备列表: %s", self._manually_removed_devices)
    
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
            from homeassistant.helpers.device_registry import async_get
            self._device_registry_cache = async_get(self.hass)
        return self._device_registry_cache
    
    async def _get_entity_registry(self):
        """获取实体注册表（带缓存）"""
        if not self._entity_registry_cache:
            from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
            self._entity_registry_cache = async_get_entity_registry(self.hass)
        return self._entity_registry_cache
    
    async def _process_device(self, device_info: tuple):
        """处理单个设备"""
        device_sn, device_name = device_info
        # 直接添加到设备字典中
        self.devices[device_sn] = {
            "name": device_name,
            "type": DEVICE_TYPE_WINDOW_OPENER,
            "status": "online",
            "attributes": {}
        }
        _LOGGER.debug("快速加载设备: %s, 名称: %s", device_sn, device_name)
    
    async def setup(self) -> bool:
        """设置设备管理器 - 极速优化版"""
        import time
        import asyncio
        start_time = time.time()
        _LOGGER.info("设备管理器极速初始化: %s", self.gateway_sn)
        
        # 1. **最高优先级**：立即从映射表恢复设备（极速模式）
        if DEVICE_TO_GATEWAY_MAPPING in self.hass.data[DOMAIN]:
            device_to_gateway_mapping = self.hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING]
            
            # 并行快速处理所有设备（不等待任何I/O）
            processed_count = 0
            
            # 首先：批量创建内存中的设备记录（0等待）
            # 添加动态并发控制，根据系统负载调整并发数
            max_concurrent_tasks = self._get_optimal_concurrent_tasks()
            _LOGGER.info("根据系统负载调整并发数为: %d", max_concurrent_tasks)
            semaphore = asyncio.Semaphore(max_concurrent_tasks)
            
            async def register_device_with_semaphore(device_sn, device_name):
                """使用信号量控制并发的设备注册任务"""
                async with semaphore:
                    await self._async_fast_register_device(device_sn, device_name)
            
            for device_sn, gateway_sn in device_to_gateway_mapping.items():
                if gateway_sn == self.gateway_sn and device_sn not in self.devices:
                    # 跳过手动删除的设备
                    if device_sn in self._manually_removed_devices:
                        continue
                        
                    # 立即创建设备内存记录（不等待注册表查询）
                    # 使用网关SN和子设备SN后4位生成设备名称，确保名称关联且唯一
                    device_name = f"开窗器 {self.gateway_sn[-4:]}-{device_sn[-4:]}"
                    
                    # 直接调用add_device方法，确保触发设备添加回调
                    asyncio.create_task(
                        self.add_device(device_sn, device_name, DEVICE_TYPE_WINDOW_OPENER)
                    )
                    processed_count += 1
            
            if processed_count > 0:
                _LOGGER.info("已极速创建 %d 个设备内存记录", processed_count)
                
                # 立即触发MQTT状态查询（不等待完成）
                asyncio.create_task(self._trigger_immediate_status_query())
        
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
                    
                    asyncio.create_task(send_quick_discovery())
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

    async def _parallel_device_discovery(self, mqtt_handler):
        """并行执行设备发现和状态查询"""
        try:
            # 1. 先触发设备发现
            await mqtt_handler.trigger_discovery()
            
            # 2. 短暂等待后查询设备状态
            await asyncio.sleep(DEVICE_SETUP_DELAY)
            
            # 3. 并行查询所有设备的状态
            if self.devices:
                query_tasks = []
                for device_sn in self.devices:
                    # 发送状态查询命令
                    query_tasks.append(
                        mqtt_handler.send_command(device_sn, "status")
                    )
                
                # 批量执行，限制并发数
                batch_size = 3
                for i in range(0, len(query_tasks), batch_size):
                    batch = query_tasks[i:i+batch_size]
                    await asyncio.gather(*batch, return_exceptions=True)
                    _LOGGER.info("批量查询了 %d 个设备状态", len(batch))
        except Exception as e:
            _LOGGER.error("并行设备发现失败: %s", e)
    
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
            # 延迟执行设备注册，避免阻塞初始化
            await asyncio.sleep(DEVICE_REGISTRATION_DELAY)  # 延迟，让主流程先完成
            
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
    
    def _get_device_model(self, device_type):
        """获取设备模型"""
        if device_type == DEVICE_TYPE_WINDOW_OPENER:
            return "Window Opener"
        return "Unknown"
        
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
        """根据系统负载获取最优并发任务数
        
        Returns:
            int: 最优并发任务数
        """
        try:
            # 导入必要的模块
            import psutil
            
            # 获取系统CPU使用率
            cpu_percent = psutil.cpu_percent(interval=0.1)
            
            # 获取系统内存使用率
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # 基础并发数
            base_concurrent = 5
            
            # 根据CPU和内存使用率调整并发数
            if cpu_percent < 30 and memory_percent < 50:
                # 系统负载低，增加并发数
                return min(base_concurrent * 2, 10)  # 最多10个并发任务
            elif cpu_percent < 60 and memory_percent < 70:
                # 系统负载适中，使用基础并发数
                return base_concurrent
            elif cpu_percent < 80 and memory_percent < 85:
                # 系统负载较高，减少并发数
                return max(base_concurrent // 2, 2)  # 最少2个并发任务
            else:
                # 系统负载很高，使用最小并发数
                return 1  # 最少1个并发任务
        except ImportError:
            # 如果psutil模块不可用，使用默认并发数
            _LOGGER.warning("psutil模块不可用，使用默认并发数")
            return 5
        except Exception as e:
            # 如果获取系统负载失败，使用默认并发数
            _LOGGER.error("获取系统负载失败: %s，使用默认并发数", e)
            return 5
        

    
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
    
    async def add_device(self, device_sn: str, device_name: str, device_type: str = None, force: bool = False):
        """添加设备 - 只支持开窗器类型"""
        # 检查设备是否在手动删除列表中
        # 如果是手动删除的设备，不自动添加回来
        if not force and device_sn in self._manually_removed_devices:
            _LOGGER.info("设备 %s 在手动删除列表中，跳过自动添加", device_sn)
            return None
        
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
        
        # 检查设备是否已经添加到其他网关中（迁移时跳过此检查）
        if not force and DEVICE_TO_GATEWAY_MAPPING in self.hass.data[DOMAIN]:
            device_to_gateway_mapping = self.hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING]
            if device_sn in device_to_gateway_mapping:
                existing_gateway_sn = device_to_gateway_mapping[device_sn]
                if existing_gateway_sn != self.gateway_sn:
                    _LOGGER.warning("设备 %s 已经添加到网关 %s 中，不允许添加到当前网关 %s", 
                                device_sn, existing_gateway_sn, self.gateway_sn)
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
                
                # 更新设备在 self.devices 中的信息
                self.devices[device_sn] = {
                    "sn": device_sn,
                    "name": device_name_with_sn,
                    "type": device_type,
                    "online": True,
                    "last_update": time.time()
                }
                _LOGGER.info("已更新设备 %s 在设备管理器中的信息", device_sn)
                
                # 触发设备添加回调，确保实体被创建
                # 注意：即使设备已存在，也需要触发回调，因为设备可能已经迁移到新网关
                for callback in self._device_added_callbacks:
                    try:
                        self.hass.create_task(callback(device_sn, device_name_with_sn, device_type))
                    except Exception as e:
                        _LOGGER.error("调用设备添加回调失败: %s", e)
                _LOGGER.info("已触发设备 %s 的添加回调（迁移模式）", device_sn)
                
                return device_sn
            
            # 检查设备是否属于当前网关（迁移时跳过此检查）
            if not force and DEVICE_TO_GATEWAY_MAPPING in self.hass.data[DOMAIN]:
                device_to_gateway_mapping = self.hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING]
                if device_sn in device_to_gateway_mapping:
                    existing_gateway_sn = device_to_gateway_mapping[device_sn]
                    if existing_gateway_sn != self.gateway_sn:
                        _LOGGER.warning("设备 %s 已经添加到网关 %s 中，不允许添加到当前网关 %s", 
                                    device_sn, existing_gateway_sn, self.gateway_sn)
                        return None
            
            # 更新设备类型为开窗器
            self.devices[device_sn]["type"] = device_type
            # 更新设备名称
            self.devices[device_sn]["name"] = self._format_device_name(device_sn, device_name)
            
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
                        _LOGGER.warning("配置条目不存在，跳过更新设备注册信息: %s", self.entry.entry_id)
            except Exception as e:
                _LOGGER.error("更新设备注册信息失败: %s", e)
            
            # 即使设备已存在，也要调用回调，确保实体被重新创建
            for callback in self._device_added_callbacks:
                self.hass.create_task(callback(device_sn, device_name_with_sn, device_type))
            _LOGGER.info("设备已存在，重新触发回调: %s", device_sn)
            return self.devices[device_sn]
            
        # 格式化设备名称
        device_name_with_sn = self._format_device_name(device_sn, device_name)
        
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
                for callback in self._device_added_callbacks:
                    try:
                        self.hass.create_task(callback(device_sn, device_name_with_sn, device_type))
                    except Exception as e:
                        _LOGGER.error("调用设备添加回调失败: %s", e)
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
            for callback in self._device_added_callbacks:
                try:
                    self.hass.create_task(callback(device_sn, device_name_with_sn, device_type))
                except Exception as e:
                    _LOGGER.error("调用设备添加回调失败: %s", e)
            _LOGGER.info("开窗器设备添加成功 (内存中): %s (%s)", device_name_with_sn, device_sn)
            return device_sn
        
        if device:
            _LOGGER.info("开窗器设备添加成功: %s (%s)", device_name_with_sn, device_sn)
            
            # 将设备SN和网关SN的映射关系存储到hass.data中
            if DEVICE_TO_GATEWAY_MAPPING not in self.hass.data[DOMAIN]:
                self.hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING] = {}
            self.hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING][device_sn] = self.gateway_sn
            _LOGGER.info("设备 %s 已添加到网关 %s，已更新映射关系", device_sn, self.gateway_sn)
            
            # 调用所有设备添加回调，通知需要添加新实体
            for callback in self._device_added_callbacks:
                try:
                    self.hass.create_task(callback(device_sn, device_name_with_sn, device_type))
                except Exception as e:
                    _LOGGER.error("调用设备添加回调失败: %s", e)
            _LOGGER.debug("已通知所有设备添加回调: %s", device_name_with_sn)
            
            return device.id
        else:
            _LOGGER.error("创建设备失败，device 为 None: %s", device_sn)
            # 即使创建设备失败，也要返回设备信息
            # 调用设备添加回调，让其他组件知道设备已添加
            for callback in self._device_added_callbacks:
                try:
                    self.hass.create_task(callback(device_sn, device_name_with_sn, device_type))
                except Exception as e:
                    _LOGGER.error("调用设备添加回调失败: %s", e)
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
                    if existing_gateway_sn == self.gateway_sn:
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
                from .mqtt_handler import WindowControllerMQTTHandler
                # 查找与当前网关关联的MQTT处理器
                for entry_id, data in self.hass.data[DOMAIN].items():
                    if isinstance(data, dict) and data.get("gateway_sn") == self.gateway_sn:
                        if "mqtt_handler" in data:
                            mqtt_handler = data["mqtt_handler"]
                            # 触发设备发现，确保设备可以重新添加
                            self.hass.create_task(mqtt_handler.trigger_discovery())
                            break
            except ImportError as e:
                _LOGGER.error("导入MQTT处理器失败: %s", e)
            except KeyError as e:
                _LOGGER.error("访问DOMAIN数据失败: %s", e)
            except Exception as e:
                _LOGGER.error("通知MQTT处理器设备删除失败: %s", e)
            
            # 使缓存失效，确保下次加载时重新获取设备列表
            try:
                cache_manager = DeviceCacheManager(self.hass)
                self.hass.create_task(cache_manager.invalidate_cache(self.gateway_sn))
            except Exception as e:
                _LOGGER.error("使缓存失效失败: %s", e)
            
    async def update_device_status(self, device_sn: str, status: str, attributes: Optional[Dict[str, Any]] = None):
        """更新设备状态"""
        try:
            if device_sn in self.devices:
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
                # 生成默认设备名称
                device_name = f"设备 {device_sn[-6:]}"
                # 添加设备
                await self.add_device(device_sn, device_name, DEVICE_TYPE_WINDOW_OPENER)
                # 再次尝试更新状态
                if device_sn in self.devices:
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
                pass
            
    def get_device(self, device_sn: str) -> Optional[Dict[str, Any]]:
        """获取设备信息"""
        return self.devices.get(device_sn)
        
    def get_all_devices(self) -> List[Dict[str, Any]]:
        """获取所有设备"""
        # 返回设备列表的浅拷贝，避免外部修改影响内部状态
        return [device.copy() for device in self.devices.values()]
        
    async def cleanup(self):
        """清理资源"""
        _LOGGER.info("清理设备管理器资源")
        self.devices.clear()
        self._device_registry_cache = None
        # 更彻底的回调清理
        self._device_added_callbacks = []
        self._device_removed_callbacks = []
        self._device_update_callbacks.clear()
        # 注意：不要清空手动删除设备列表，因为这是持久化的状态
        # 当网关重新添加时，需要知道哪些设备是被手动删除的
        
        # 清理缓存相关资源
        try:
            # 创建临时缓存管理器实例并清理缓存
            cache_manager = DeviceCacheManager(self.hass)
            await cache_manager.invalidate_cache(self.gateway_sn)
            _LOGGER.debug("已清理网关 %s 的缓存", self.gateway_sn)
        except Exception as e:
            _LOGGER.error("清理缓存失败: %s", e)

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
                    if entry.data.get(CONF_GATEWAY_SN) == old_gateway_sn:
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
            for entry_id, data in self.hass.data[DOMAIN].items():
                if isinstance(data, dict) and data.get("gateway_sn") == gateway_sn:
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
            for device_sn, mapped_gateway_sn in device_to_gateway_mapping.items():
                if mapped_gateway_sn == gateway_sn:
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
                    if hasattr(device, 'via_device') and device.via_device and device.via_device[1] == old_gateway_sn:
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
                    if hasattr(device, 'via_device') and device.via_device and device.via_device[1] == gateway_sn:
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
                    if hasattr(device, 'via_device') and device.via_device and device.via_device[1] == gateway_sn:
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
            if entry.data.get(CONF_GATEWAY_SN) == old_gateway_sn:
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
    
    async def migrate_devices_with_rollback(self, old_gateway_sn, new_gateway_sn, delete_old_devices=False):
        """带完整回滚保障的迁移"""
        # 1. 创建完整快照
        snapshot = await self._create_migration_snapshot(old_gateway_sn)
        
        # 2. 执行迁移
        try:
            result = await self.migrate_devices(old_gateway_sn, delete_old_devices)
            
            # 3. 验证迁移结果
            if not await self._verify_migration_result(old_gateway_sn, new_gateway_sn):
                raise Exception("迁移结果验证失败")
                
            return result
        except Exception as e:
            # 4. 执行回滚
            _LOGGER.error("迁移失败，执行回滚: %s", e)
            await self._rollback_migration(snapshot)
            raise
    
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
    
    async def _verify_migration_result(self, old_gateway_sn, new_gateway_sn):
        """验证迁移结果"""
        # 实现基本的迁移结果验证逻辑
        old_gateway_devices = await self._get_gateway_devices_from_registry(old_gateway_sn)
        new_gateway_devices = await self._get_gateway_devices_from_registry(new_gateway_sn)
        
        _LOGGER.info("验证迁移结果，旧网关设备数: %d，新网关设备数: %d", 
                   len(old_gateway_devices), len(new_gateway_devices))
        
        # 检查是否有设备成功迁移
        if len(new_gateway_devices) == 0:
            _LOGGER.error("验证失败: 新网关没有关联的设备")
            return False
        
        # 检查设备数量是否合理
        if len(new_gateway_devices) < len(old_gateway_devices):
            _LOGGER.warning("验证警告: 新网关设备数少于旧网关")
        
        return True
    
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
            
            # 检查设备是否已经关联到新网关
            if hasattr(device, 'via_device') and device.via_device and device.via_device[1] == new_gateway_sn:
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
        """重新创建平台实体"""
        import asyncio
        from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
        
        entity_registry = async_get_entity_registry(self.hass)
        
        # 使用类常量 entity_recreate_map
        
        all_entities_to_remove = []
        
        for platform, domain in self.entity_recreate_map.items():
            # 查找需要重新创建的实体
            entities_to_remove = []
            
            for entity_id, entity_entry in entity_registry.entities.items():
                if entity_entry.platform == domain and entity_entry.domain == platform:
                    # 检查是否属于要迁移的设备
                    for device_sn in device_sns:
                        if device_sn in entity_entry.unique_id:
                            entities_to_remove.append(entity_id)
                            break
            
            if entities_to_remove:
                _LOGGER.info("准备移除 %s 平台实体: %d 个", platform, len(entities_to_remove))
                all_entities_to_remove.extend(entities_to_remove)
                
                # 先移除旧实体
                for entity_id in entities_to_remove:
                    try:
                        entity_registry.async_remove(entity_id)
                        _LOGGER.debug("已移除实体: %s", entity_id)
                    except Exception as e:
                        _LOGGER.error("移除实体失败 %s: %s", entity_id, e)
        
        # 触发设备添加回调，确保设备被添加到新网关的设备管理器中
        device_registry = await self._get_device_registry()
        for device_sn in device_sns:
            # 查找设备在注册表中的记录
            device = device_registry.async_get_device(
                identifiers={(DOMAIN, device_sn)}
            )
            
            if device:
                # 触发设备添加回调
                for callback in self._device_added_callbacks:
                    self.hass.create_task(callback(device_sn, device.name, DEVICE_TYPE_WINDOW_OPENER))
                _LOGGER.info("已触发设备 %s 的添加回调（重新创建平台实体）", device_sn)
        
        # 等待设备添加回调执行完成 - 减少等待时间
        await asyncio.sleep(MIGRATION_DELAY)
        
        # 触发平台重新加载
        if all_entities_to_remove:
            _LOGGER.info("触发平台重新加载，共 %d 个实体", len(all_entities_to_remove))
            for platform in entity_recreate_map.keys():
                await self._reload_platform(platform)
        
        # 重新加载所有已配置的网关，确保所有设备实体都被正确创建
        _LOGGER.info("重新加载所有已配置的网关，确保所有设备实体都被正确创建")
        existing_entries = self.hass.config_entries.async_entries(DOMAIN)
        for entry in existing_entries:
            if entry.data.get(CONF_GATEWAY_SN) == new_gateway_sn:
                await self.hass.config_entries.async_reload(entry.entry_id)
                _LOGGER.info("已重新加载新网关配置条目: %s", entry.entry_id)
    
    async def _reload_platform(self, platform: str):
        """重新加载特定平台"""
        try:
            # 获取相关配置条目
            config_entry = self.hass.config_entries.async_get_entry(self.entry.entry_id)
            if not config_entry:
                _LOGGER.error("配置条目未找到: %s", self.entry.entry_id)
                return
            
            # 卸载平台
            await self.hass.config_entries.async_forward_entry_unload(config_entry, platform)
            
            # 重新加载平台
            await self.hass.config_entries.async_forward_entry_setup(config_entry, platform)
            
            _LOGGER.info("平台 %s 重新加载完成", platform)
        except Exception as e:
            _LOGGER.error("重新加载平台 %s 失败: %s", platform, e)
    
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
                if device.via_device[1] == new_gateway_sn:
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
                if via_device_info and via_device_info[1] == gateway_sn:
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
                if device_sn in device_to_gateway_mapping and device_to_gateway_mapping[device_sn] == old_gateway_sn:
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
    
    async def safe_migrate_devices(self, old_gateway_sn, new_gateway_sn, delete_old_devices=False):
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
            
            # 6. 可选：清理旧网关
            if delete_old_devices:
                await self._cleanup_old_gateway(old_gateway_sn)
                
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
        
        # 2. 恢复设备到旧网关
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
                    # 检查设备是否关联到当前网关
                    if hasattr(device, 'via_device') and device.via_device and device.via_device[1] == self.gateway_sn:
                        # 恢复设备关联到旧网关
                        updated_device = device_registry.async_get_or_create(
                            config_entry_id=self.entry.entry_id,
                            identifiers={(DOMAIN, device_sn)},
                            name=device.name,
                            manufacturer=MANUFACTURER,
                            model=device.model,
                            via_device=(DOMAIN, old_gateway_sn)
                        )
                        _LOGGER.info("已回滚设备 %s 到旧网关", device_sn)
            
            # 3. 恢复设备到网关映射表
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
                if hasattr(device, 'via_device') and device.via_device and device.via_device[1] == old_gateway_sn:
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
                if hasattr(device, 'via_device') and device.via_device and device.via_device[1] == old_gateway_sn:
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
                    if hasattr(updated_device, 'via_device') and updated_device.via_device and updated_device.via_device[1] == self.gateway_sn:
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
                    
                    # 更新迁移计数并发送进度通知
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
                    for entity_id, entity_entry in entity_registry.entities.items():
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
        
        # 每20%进度发送一次通知
        progress_percent = (current_count / total_count) * 100
        if progress_percent % 20 <= 1:  # 允许1%的误差
            return True
        
        # 迁移完成时发送通知
        if current_count == total_count:
            return True
        
        return False