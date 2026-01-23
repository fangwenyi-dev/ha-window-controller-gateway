"""开窗器网关窗帘组件"""
import logging
from typing import Optional, Dict, Any

from homeassistant.components.cover import (
    CoverEntity,
    CoverDeviceClass,
    CoverEntityFeature,
    ATTR_POSITION,
    ATTR_CURRENT_POSITION
)
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    CONF_GATEWAY_SN,
    ATTR_DEVICE_SN,
    ATTR_DEVICE_NAME,
    ATTR_POSITION as CONST_ATTR_POSITION,
    MANUFACTURER,
    COMMAND_OPEN,
    COMMAND_CLOSE,
    COMMAND_STOP,
    COMMAND_SET_POSITION,
    DEVICE_TYPE_WINDOW_OPENER
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置窗帘实体"""
    gateway_sn = entry.data[CONF_GATEWAY_SN]
    
    # 从设备管理器获取设备
    domain_data = hass.data[DOMAIN]
    entry_data = domain_data.get(entry.entry_id)
    
    if not entry_data:
        _LOGGER.error("配置条目数据未找到: %s", entry.entry_id)
        return
        
    device_manager = entry_data.get("device_manager")
    mqtt_handler = entry_data.get("mqtt_handler")
    
    if not device_manager or not mqtt_handler:
        _LOGGER.error("设备管理器或MQTT处理器未找到")
        return
        
    # 创建设备实体
    devices = device_manager.get_all_devices()
    entities = []
    
    for device in devices:
        if device["type"] == DEVICE_TYPE_WINDOW_OPENER:
            entity = WindowControllerCover(
                hass,
                device_manager,
                mqtt_handler,
                gateway_sn,
                device["sn"],
                device["name"],
                device["type"]
            )
            entities.append(entity)
            _LOGGER.info("创建窗帘实体: %s (%s)", device["name"], device["sn"])
            
    if entities:
        async_add_entities(entities)
        _LOGGER.info("已添加 %d 个窗帘实体", len(entities))

class WindowControllerCover(CoverEntity):
    """开窗器网关窗帘实体"""
    
    def __init__(
        self,
        hass: HomeAssistant,
        device_manager,
        mqtt_handler,
        gateway_sn: str,
        device_sn: str,
        device_name: str,
        device_type: str
    ):
        """初始化窗帘实体"""
        self.hass = hass
        self.device_manager = device_manager
        self.mqtt_handler = mqtt_handler
        self.gateway_sn = gateway_sn
        self.device_sn = device_sn
        self._attr_name = device_name
        self.device_type = device_type
        self._attr_unique_id = f"{gateway_sn}_{device_sn}"
        self._attr_device_class = self._get_device_class(device_type)
        
        # 设置支持的功能
        self._attr_supported_features = (
            CoverEntityFeature.OPEN |
            CoverEntityFeature.CLOSE |
            CoverEntityFeature.STOP |
            CoverEntityFeature.SET_POSITION
        )
        
        # 初始化状态
        self._attr_is_closed = None
        self._attr_current_cover_position = None
        self._attr_is_opening = False
        self._attr_is_closing = False
        
        # 更新初始状态
        self._update_state_from_device()
        
    def _get_device_class(self, device_type: str) -> CoverDeviceClass:
        """根据设备类型获取设备类别"""
        device_class_map = {
            "window_controller": CoverDeviceClass.WINDOW,
            "curtain": CoverDeviceClass.CURTAIN,
            "shutter": CoverDeviceClass.SHUTTER,
            "blind": CoverDeviceClass.BLIND,
            "awning": CoverDeviceClass.AWNING
        }
        return device_class_map.get(device_type, CoverDeviceClass.WINDOW)
        
    def _update_state_from_device(self):
        """从设备管理器更新状态"""
        device = self.device_manager.get_device(self.device_sn)
        if device:
            attributes = device.get("attributes", {})
            position = attributes.get(CONST_ATTR_POSITION)
            
            if position is not None:
                self._attr_current_cover_position = position
                self._attr_is_closed = position == 0
                
    @property
    def device_info(self) -> DeviceInfo:
        """返回设备信息"""
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_sn)},
            name=self._attr_name,
            manufacturer=MANUFACTURER,
            model=self.device_type.capitalize(),
            via_device=(DOMAIN, self.gateway_sn)
        )
        
    async def async_open_cover(self, **kwargs):
        """打开窗帘"""
        try:
            await self.mqtt_handler.send_command(self.device_sn, COMMAND_OPEN)
            self._attr_is_opening = True
            self._attr_is_closing = False
            self.async_write_ha_state()
            _LOGGER.info("发送打开命令到设备: %s", self.device_sn)
        except Exception as e:
            _LOGGER.error("发送打开命令失败: %s", e)
        
    async def async_close_cover(self, **kwargs):
        """关闭窗帘"""
        try:
            await self.mqtt_handler.send_command(self.device_sn, COMMAND_CLOSE)
            self._attr_is_opening = False
            self._attr_is_closing = True
            self.async_write_ha_state()
            _LOGGER.info("发送关闭命令到设备: %s", self.device_sn)
        except Exception as e:
            _LOGGER.error("发送关闭命令失败: %s", e)
        
    async def async_stop_cover(self, **kwargs):
        """停止窗帘"""
        try:
            await self.mqtt_handler.send_command(self.device_sn, COMMAND_STOP)
            self._attr_is_opening = False
            self._attr_is_closing = False
            self.async_write_ha_state()
            _LOGGER.info("发送停止命令到设备: %s", self.device_sn)
        except Exception as e:
            _LOGGER.error("发送停止命令失败: %s", e)
        
    async def async_set_cover_position(self, **kwargs):
        """设置窗帘位置"""
        position = kwargs.get(ATTR_POSITION)
        if position is not None:
            try:
                await self.mqtt_handler.send_command(
                    self.device_sn,
                    COMMAND_SET_POSITION,
                    {"position": position}
                )
                self._attr_current_cover_position = position
                self._attr_is_closed = position == 0
                self.async_write_ha_state()
                _LOGGER.info("发送设置位置命令到设备 %s: %d", self.device_sn, position)
            except Exception as e:
                _LOGGER.error("发送设置位置命令失败: %s", e)
            
    async def async_update(self):
        """更新实体状态"""
        self._update_state_from_device()