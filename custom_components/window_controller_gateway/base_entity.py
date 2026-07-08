"""设备实体管理基类"""
import logging
from typing import Optional
from homeassistant.core import HomeAssistant

from .utils import get_device_gateway_mapping
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class WindowControllerBaseEntity:
    """所有设备实体基类
    
    提供通用的设备实体管理功能，减少代码重复
    """
    
    _attr_has_entity_name = True
    
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
        self._mqtt_handler_cache = {}
    
    def get_current_gateway_sn(self) -> str:
        """统一获取设备当前关联的网关
        
        Returns:
            str: 设备当前关联的网关序列号
        """
        return get_device_gateway_mapping(self.hass, self.device_sn) or self.gateway_sn
    
    def _get_mqtt_handler(self):
        """获取设备当前关联的正确MQTT处理器
        
        设备迁移后，设备关联的网关可能发生变化，
        此方法根据设备当前关联的网关SN查找正确的MQTT处理器。
        
        Returns:
            MQTT处理器实例
        """
        current_gateway_sn = self.get_current_gateway_sn()
        if current_gateway_sn.lower() != self.gateway_sn.lower():
            if current_gateway_sn in self._mqtt_handler_cache:
                return self._mqtt_handler_cache[current_gateway_sn]
            for entry_id, data in self.hass.data[DOMAIN].items():
                if isinstance(data, dict) and data.get("gateway_sn", "").lower() == current_gateway_sn.lower():
                    if "mqtt_handler" in data:
                        self._mqtt_handler_cache[current_gateway_sn] = data["mqtt_handler"]
                        return data["mqtt_handler"]
            _LOGGER.error("未找到设备 %s 关联的网关 %s 的MQTT处理器",
                         self.device_sn, current_gateway_sn)
            return self.mqtt_handler
        return self.mqtt_handler
    
    async def async_added_to_hass(self) -> None:
        """实体添加到Home Assistant时调用"""
        # 基类提供基本实现，子类可以重写
        _LOGGER.debug("实体已添加到Home Assistant: %s (%s)", self.device_name, self.device_sn)
    
    async def async_will_remove_from_hass(self) -> None:
        """实体从Home Assistant移除时调用"""
        # 基类提供基本实现，子类可以重写
        _LOGGER.debug("实体将从Home Assistant移除: %s (%s)", self.device_name, self.device_sn)
