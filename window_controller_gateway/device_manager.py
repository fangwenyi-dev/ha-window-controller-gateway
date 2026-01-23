"""设备管理器 - 修正版"""
import logging
from typing import Dict, Any, List, Optional
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import async_get as async_get_device_registry

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
        
    async def setup(self):
        """设置设备管理器"""
        _LOGGER.info("设备管理器初始化: %s", self.gateway_sn)
        return True
        
    async def register_gateway_device(self):
        """注册网关设备"""
        device_registry = async_get_device_registry(self.hass)
        
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
        
    async def add_device(self, device_sn: str, device_name: str, device_type: str = None):
        """添加设备 - 只支持开窗器类型"""
        # 强制设备类型为开窗器，忽略传入的其他类型
        device_type = DEVICE_TYPE_WINDOW_OPENER
            
        if device_sn in self.devices:
            _LOGGER.debug("设备已存在: %s", device_sn)
            # 更新设备类型为开窗器
            self.devices[device_sn]["type"] = device_type
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
        device_registry = async_get_device_registry(self.hass)
        device = device_registry.async_get_or_create(
            config_entry_id=self.entry.entry_id,
            identifiers={(DOMAIN, device_sn)},
            name=device_name,
            manufacturer=MANUFACTURER,
            model=self._get_device_model(device_type),
            via_device=(DOMAIN, self.gateway_sn)
        )
        
        _LOGGER.info("开窗器设备添加成功: %s (%s)", device_name, device_sn)
        return device.id
    
    def _get_device_model(self, device_type: str) -> str:
        """根据设备类型获取模型名称"""
        # 只支持开窗器设备
        return "开窗器"
        
    async def remove_device(self, device_sn: str):
        """移除设备"""
        if device_sn in self.devices:
            del self.devices[device_sn]
            _LOGGER.info("设备移除: %s", device_sn)
            
    async def update_device_status(self, device_sn: str, status: str, attributes: Optional[Dict[str, Any]] = None):
        """更新设备状态"""
        if device_sn in self.devices:
            self.devices[device_sn]["status"] = status
            if attributes:
                self.devices[device_sn]["attributes"].update(attributes)
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