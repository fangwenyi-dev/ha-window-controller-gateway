"""开窗器网关实体"""
import logging
from typing import Optional

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass
)
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    CONF_GATEWAY_SN,
    CONF_GATEWAY_NAME,
    DEFAULT_GATEWAY_NAME,
    ENTITY_GATEWAY_PREFIX,
    ENTITY_ONLINE_SENSOR_SUFFIX,
    ENTITY_PAIRING_BUTTON_SUFFIX,
    MANUFACTURER,
    MODEL
)

_LOGGER = logging.getLogger(__name__)



class GatewayOnlineSensor(BinarySensorEntity):
    """网关在线状态传感器"""
    
    def __init__(
        self,
        hass: HomeAssistant,
        device_manager,
        mqtt_handler,
        gateway_sn: str,
        gateway_name: str
    ):
        """初始化网关在线状态传感器"""
        self.hass = hass
        self.device_manager = device_manager
        self.mqtt_handler = mqtt_handler
        self.gateway_sn = gateway_sn
        self.gateway_name = gateway_name
        self._attr_name = f"{gateway_name} 在线"
        self._attr_unique_id = f"{ENTITY_GATEWAY_PREFIX}{gateway_sn}{ENTITY_ONLINE_SENSOR_SUFFIX}"
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        self._attr_is_on = False
        
        # 添加状态更新回调
        self.mqtt_handler.add_status_callback(self._on_status_change)
        
        # 初始状态更新
        self._update_state()
    
    @property
    def device_info(self) -> DeviceInfo:
        """返回设备信息"""
        return DeviceInfo(
            identifiers={(DOMAIN, self.gateway_sn)},
            name=self.gateway_name,
            manufacturer=MANUFACTURER,
            model=MODEL
        )
    
    def _update_state(self):
        """更新状态"""
        # 从MQTT处理器获取连接状态
        self._attr_is_on = self.mqtt_handler.connected
        _LOGGER.debug("网关 %s 在线状态更新为: %s", self.gateway_sn, self._attr_is_on)
    
    def _on_status_change(self):
        """当MQTT状态改变时调用"""
        self._update_state()
        # 通知Home Assistant状态已更新
        # 使用schedule_update_ha_state确保在事件循环线程中执行
        self.schedule_update_ha_state()
    
    async def async_update(self):
        """更新实体状态"""
        self._update_state()
    
    async def async_will_remove_from_hass(self):
        """当实体从HA中移除时调用"""
        # 移除状态更新回调
        self.mqtt_handler.remove_status_callback(self._on_status_change)

class GatewayPairingButton(ButtonEntity):
    """网关配对按键"""
    
    def __init__(
        self,
        hass: HomeAssistant,
        device_manager,
        mqtt_handler,
        gateway_sn: str,
        gateway_name: str
    ):
        """初始化网关配对按键"""
        self.hass = hass
        self.device_manager = device_manager
        self.mqtt_handler = mqtt_handler
        self.gateway_sn = gateway_sn
        self.gateway_name = gateway_name
        self._attr_name = f"{gateway_name} 配对"
        self._attr_unique_id = f"{ENTITY_GATEWAY_PREFIX}{gateway_sn}{ENTITY_PAIRING_BUTTON_SUFFIX}"
    
    @property
    def device_info(self) -> DeviceInfo:
        """返回设备信息"""
        return DeviceInfo(
            identifiers={(DOMAIN, self.gateway_sn)},
            name=self.gateway_name,
            manufacturer=MANUFACTURER,
            model=MODEL
        )
    
    async def async_press(self) -> None:
        """按下按键，触发配对模式"""
        try:
            # 调用MQTT处理器的开始配对方法
            await self.mqtt_handler.start_pairing()
            _LOGGER.info("已触发网关 %s 的配对模式", self.gateway_sn)
        except Exception as e:
            _LOGGER.error("触发网关配对模式失败: %s", e)
