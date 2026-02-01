"""设备管理器 - 修正版"""
import logging
from typing import Dict, Any, List, Optional
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
    MODEL
)

_LOGGER = logging.getLogger(__name__)

class WindowControllerDeviceManager:
    """设备管理器类"""
    
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """初始化设备管理器"""
        self.hass = hass
        self.entry = entry
        self.gateway_sn = entry.data[CONF_GATEWAY_SN]
        self.gateway_name = entry.data.get(CONF_GATEWAY_NAME, f"开窗器网关 {self.gateway_sn[-6:]}")
        self.devices = {}
        self.gateway_device_id = None
        self._device_added_callbacks = []
        self._device_removed_callbacks = []
        self._device_registry_cache = None
        
    async def _get_device_registry(self):
        """获取设备注册表（带缓存）"""
        if not self._device_registry_cache:
            from homeassistant.helpers.device_registry import async_get
            self._device_registry_cache = async_get(self.hass)
        return self._device_registry_cache

    async def setup(self):
        """设置设备管理器"""
        _LOGGER.info("设备管理器初始化: %s", self.gateway_sn)
        
        # 从Home Assistant设备注册表中加载已存在的设备
        try:
            device_registry = await self._get_device_registry()
            # 获取所有属于此集成的设备
            for device in device_registry.devices.values():
                # 检查设备是否属于当前配置条目
                if self.entry.entry_id in device.config_entries:
                    # 检查设备是否是子设备（不是网关本身）
                    for identifier in device.identifiers:
                        if identifier[0] == DOMAIN:
                            device_sn = identifier[1]
                            # 跳过网关本身
                            if device_sn != self.gateway_sn:
                                # 创建设备信息
                                device_info = {
                                    "sn": device_sn,
                                    "name": device.name,
                                    "type": DEVICE_TYPE_WINDOW_OPENER,
                                    "status": "connected",
                                    "attributes": {}
                                }
                                # 添加到设备列表
                                self.devices[device_sn] = device_info
                                _LOGGER.info("从设备注册表加载设备: %s (%s)", device.name, device_sn)
        except Exception as e:
            _LOGGER.error("从设备注册表加载设备失败: %s", e)
            
        return True
        
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
        
    def set_device_added_callback(self, callback):
        """添加设备添加回调"""
        if callback not in self._device_added_callbacks:
            self._device_added_callbacks.append(callback)
            _LOGGER.debug("设备添加回调已添加")
    
    def set_device_removed_callback(self, callback):
        """添加设备移除回调"""
        if callback not in self._device_removed_callbacks:
            self._device_removed_callbacks.append(callback)
            _LOGGER.debug("设备移除回调已添加")
    
    async def add_device(self, device_sn: str, device_name: str, device_type: str = None):
        """添加设备 - 只支持开窗器类型"""
        # 强制设备类型为开窗器，忽略传入的其他类型
        device_type = DEVICE_TYPE_WINDOW_OPENER
            
        device_existed = device_sn in self.devices
        if device_existed:
            _LOGGER.debug("设备已存在: %s", device_sn)
            # 更新设备类型为开窗器
            self.devices[device_sn]["type"] = device_type
            # 即使设备已存在，也要调用回调，确保实体被重新创建
            for callback in self._device_added_callbacks:
                self.hass.create_task(callback(device_sn, device_name, device_type))
            _LOGGER.info("设备已存在，重新触发回调: %s", device_sn)
            return self.devices[device_sn]
            
        device_info = {
            "sn": device_sn,
            "name": device_name,
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
                _LOGGER.warning("配置条目不存在，跳过创建设备注册: %s", self.entry.entry_id)
                # 即使配置条目不存在，也要返回设备信息，这样设备仍会被添加到内存中
                # 但不会创建Home Assistant设备注册
                # 调用设备添加回调，让其他组件知道设备已添加
                for callback in self._device_added_callbacks:
                    self.hass.create_task(callback(device_sn, device_name, device_type))
                _LOGGER.info("开窗器设备添加成功 (内存中): %s (%s)", device_name, device_sn)
                return device_sn
            
            device = device_registry.async_get_or_create(
                config_entry_id=self.entry.entry_id,
                identifiers={(DOMAIN, device_sn)},
                name=device_name,
                manufacturer=MANUFACTURER,
                model=self._get_device_model(device_type),
                via_device=(DOMAIN, self.gateway_sn)
            )
        except Exception as e:
            _LOGGER.error("创建设备注册失败: %s", e)
            # 即使创建设备注册失败，也要返回设备信息
            # 调用设备添加回调，让其他组件知道设备已添加
            for callback in self._device_added_callbacks:
                self.hass.create_task(callback(device_sn, device_name, device_type))
            _LOGGER.info("开窗器设备添加成功 (内存中): %s (%s)", device_name, device_sn)
            return device_sn
        
        if device:
            _LOGGER.info("开窗器设备添加成功: %s (%s)", device_name, device_sn)
            
            # 调用所有设备添加回调，通知需要添加新实体
            for callback in self._device_added_callbacks:
                self.hass.create_task(callback(device_sn, device_name, device_type))
            _LOGGER.debug("已通知所有设备添加回调: %s", device_name)
            
            return device.id
        else:
            _LOGGER.error("创建设备失败，device 为 None: %s", device_sn)
            # 即使创建设备失败，也要返回设备信息
            # 调用设备添加回调，让其他组件知道设备已添加
            for callback in self._device_added_callbacks:
                self.hass.create_task(callback(device_sn, device_name, device_type))
            _LOGGER.info("开窗器设备添加成功 (内存中): %s (%s)", device_name, device_sn)
            return device_sn
    
    def _get_device_model(self, device_type: str) -> str:
        """根据设备类型获取模型名称"""
        # 只支持开窗器设备
        return "开窗器"
        
    async def remove_device(self, device_sn: str):
        """移除设备"""
        if device_sn in self.devices:
            # 获取设备信息
            device_info = self.devices[device_sn]
            device_name = device_info.get("name")
            device_type = device_info.get("type")
            
            # 从内存中删除设备
            del self.devices[device_sn]
            _LOGGER.info("设备移除: %s", device_sn)
            
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
                    _LOGGER.warning("设备在注册表中未找到: %s", device_sn)
            except Exception as e:
                _LOGGER.error("从设备注册表中删除设备失败: %s", e)
            
            # 调用设备移除回调
            if hasattr(self, '_device_removed_callbacks'):
                _LOGGER.info("正在通知设备移除回调，设备: %s", device_sn)
                for callback in self._device_removed_callbacks:
                    try:
                        await callback(device_sn, device_name, device_type)
                        _LOGGER.info("设备移除回调执行成功")
                    except Exception as e:
                        _LOGGER.error("执行设备移除回调失败: %s", e)
            else:
                _LOGGER.warning("设备移除回调未设置")
            
            _LOGGER.info("设备移除流程完成: %s", device_sn)
            
    async def update_device_status(self, device_sn: str, status: str, attributes: Optional[Dict[str, Any]] = None):
        """更新设备状态"""
        if device_sn in self.devices:
            self.devices[device_sn]["status"] = status
            if attributes:
                # 直接更新属性，后收到的上报会覆盖先前的值
                # 这样确保使用最后上报的r_travel值代表窗户当前状态
                self.devices[device_sn]["attributes"].update(attributes)
                # 特别记录r_travel的更新
                if "r_travel" in attributes:
                    _LOGGER.debug("设备 %s 位置更新: %d", device_sn, attributes["r_travel"])
                # 特别记录voltage的更新
                if "voltage" in attributes:
                    _LOGGER.debug("设备 %s 电压更新: %.1fV", device_sn, attributes["voltage"])
            _LOGGER.debug("设备状态更新: %s -> %s", device_sn, status)
            
    def get_device(self, device_sn: str) -> Optional[Dict[str, Any]]:
        """获取设备信息"""
        return self.devices.get(device_sn)
        
    def get_all_devices(self) -> List[Dict[str, Any]]:
        """获取所有设备"""
        return list(self.devices.values())
        
    async def cleanup(self):
        """清理资源"""
        _LOGGER.info("清理设备管理器资源")
        self.devices.clear()
        self._device_registry_cache = None