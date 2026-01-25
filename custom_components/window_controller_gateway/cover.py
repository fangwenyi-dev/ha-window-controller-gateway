"""开窗器网关组件"""
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
    COMMAND_A,
    DEVICE_TYPE_WINDOW_OPENER
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置开窗器实体"""
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
    
    # 跟踪创建的开窗器实体
    created_covers = {}
    
    # 定义设备添加回调函数
    async def on_device_added(device_sn: str, device_name: str, device_type: str):
        """设备添加回调，自动创建实体"""
        if device_type == DEVICE_TYPE_WINDOW_OPENER:
            entity = WindowControllerCover(
                hass,
                device_manager,
                mqtt_handler,
                gateway_sn,
                device_sn,
                device_name,
                device_type
            )
            async_add_entities([entity])
            # 跟踪创建的实体
            created_covers[device_sn] = entity
            _LOGGER.info("自动创建开窗器实体: %s (%s)", device_name, device_sn)
    
    # 定义设备移除回调函数
    async def on_device_removed(device_sn: str, device_name: str, device_type: str):
        """设备移除回调，清理相关实体"""
        if device_type == DEVICE_TYPE_WINDOW_OPENER:
            if device_sn in created_covers:
                # 获取开窗器实体
                cover_entity = created_covers[device_sn]
                # 从Home Assistant中移除实体
                try:
                    await cover_entity.async_remove()
                    _LOGGER.info("已从Home Assistant中移除开窗器实体: %s", device_name)
                except Exception as e:
                    _LOGGER.error("移除开窗器实体失败: %s", e)
                # 从跟踪字典中删除
                del created_covers[device_sn]
                _LOGGER.info("已清理设备 %s 的开窗器实体", device_name)
    
    # 设置设备添加回调
    device_manager.set_device_added_callback(on_device_added)
    # 设置设备移除回调
    device_manager.set_device_removed_callback(on_device_removed)
    
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
            # 跟踪创建的实体
            created_covers[device["sn"]] = entity
            _LOGGER.info("创建开窗器实体: %s (%s)", device["name"], device["sn"])
            
    if entities:
        async_add_entities(entities)
        _LOGGER.info("已添加 %d 个开窗器实体", len(entities))

class WindowControllerCover(CoverEntity):
    """开窗器实体"""
    
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
        """初始化开窗器实体"""
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
        
        # 更新初始状态
        self._update_state_from_device()
        
    def _get_device_class(self, device_type: str) -> CoverDeviceClass:
        """根据设备类型获取设备类别"""
        device_class_map = {
            "window_controller": CoverDeviceClass.WINDOW,
            "curtain": CoverDeviceClass.WINDOW,
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
            # 优先使用r_travel作为位置
            position = attributes.get("r_travel")
            # 如果没有r_travel，使用传统的position
            if position is None:
                position = attributes.get(CONST_ATTR_POSITION)
            
            if position is not None:
                self._attr_current_cover_position = position
                self._attr_is_closed = position == 0
    
    @property
    def extra_state_attributes(self):
        """返回额外的状态属性"""
        device = self.device_manager.get_device(self.device_sn)
        if device:
            attributes = device.get("attributes", {})
            extra_attrs = {}
            
            # 添加电池电压
            voltage = attributes.get("voltage")
            if voltage is not None:
                extra_attrs["battery_voltage"] = f"{voltage}v"
            
            return extra_attrs
        return {}
                
    @property
    def device_info(self) -> DeviceInfo:
        """返回设备信息"""
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_sn)},
            name=self._attr_name,
            manufacturer=MANUFACTURER,
            model=self.device_type.capitalize(),
            serial_number=self.device_sn,
            via_device=(DOMAIN, self.gateway_sn)
        )
        
    async def async_open_cover(self, **kwargs):
        """打开开窗器"""
        try:
            await self.mqtt_handler.send_command(self.device_sn, COMMAND_OPEN)
            # 移除状态标志设置，让实际状态通过 async_update 获取
            # 这样用户可以连续点击开按钮
            self.async_write_ha_state()
            _LOGGER.info("发送打开命令到设备: %s", self.device_sn)
        except Exception as e:
            _LOGGER.error("发送打开命令失败: %s", e)
        
    async def async_close_cover(self, **kwargs):
        """关闭开窗器"""
        try:
            await self.mqtt_handler.send_command(self.device_sn, COMMAND_CLOSE)
            # 移除状态标志设置，让实际状态通过 async_update 获取
            # 这样用户可以连续点击关按钮
            self.async_write_ha_state()
            _LOGGER.info("发送关闭命令到设备: %s", self.device_sn)
        except Exception as e:
            _LOGGER.error("发送关闭命令失败: %s", e)
        
    async def async_stop_cover(self, **kwargs):
        """停止开窗器"""
        try:
            await self.mqtt_handler.send_command(self.device_sn, COMMAND_STOP)
            # 移除状态标志设置，让实际状态通过 async_update 获取
            self.async_write_ha_state()
            _LOGGER.info("发送停止命令到设备: %s", self.device_sn)
        except Exception as e:
            _LOGGER.error("发送停止命令失败: %s", e)
        
    async def async_set_cover_position(self, **kwargs):
        """设置开窗器位置"""
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