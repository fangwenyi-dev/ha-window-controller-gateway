"""设备实体管理基类"""
from typing import Optional
from homeassistant.core import HomeAssistant

from .utils import get_device_gateway_mapping


class WindowControllerBaseEntity:
    """所有设备实体基类
    
    提供通用的设备实体管理功能，减少代码重复
    """
    
    def __init__(
        self,
        hass: HomeAssistant,
        device_manager,
        mqtt_handler,
        gateway_sn: str,
        device_sn: str,
        device_name: str
    ):
        """初始化设备实体基类
        
        Args:
            hass: Home Assistant 实例
            device_manager: 设备管理器实例
            mqtt_handler: MQTT处理器实例
            gateway_sn: 网关序列号
            device_sn: 设备序列号
            device_name: 设备名称
        """
        self.hass = hass
        self.device_manager = device_manager
        self.mqtt_handler = mqtt_handler
        self.gateway_sn = gateway_sn
        self.device_sn = device_sn
        self.device_name = device_name
    
    def get_current_gateway_sn(self) -> str:
        """统一获取设备当前关联的网关
        
        Returns:
            str: 设备当前关联的网关序列号
        """
        return get_device_gateway_mapping(self.hass, self.device_sn) or self.gateway_sn
    
    async def async_added_to_hass(self) -> None:
        """实体添加到Home Assistant时调用"""
        # 基类提供基本实现，子类可以重写
        import logging
        _LOGGER = logging.getLogger(__name__)
        _LOGGER.debug("实体已添加到Home Assistant: %s (%s)", self.device_name, self.device_sn)
    
    async def async_will_remove_from_hass(self) -> None:
        """实体从Home Assistant移除时调用"""
        # 基类提供基本实现，子类可以重写
        import logging
        _LOGGER = logging.getLogger(__name__)
        _LOGGER.debug("实体将从Home Assistant移除: %s (%s)", self.device_name, self.device_sn)
