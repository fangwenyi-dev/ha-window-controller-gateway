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
from .utils import get_device_gateway_mapping

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
    
    # 不再创建 Cover 实体，只使用 button.py 中创建的独立按钮
    # 这样就不会显示多余的"内开内倒"控制区域
    _LOGGER.info("Cover 实体已禁用，只使用独立按钮控制")
    return True

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
        # 添加图标
        self._attr_icon = "mdi:window-open"
        
        # 设置支持的功能
        self._attr_supported_features = (
            CoverEntityFeature.OPEN |
            CoverEntityFeature.CLOSE |
            CoverEntityFeature.STOP
        )
        
        # 初始化状态
        self._attr_is_closed = None
        self._attr_current_cover_position = None
        
        # 更新初始状态
        self._update_state_from_device()
    
    def can_open(self) -> bool:
        """覆盖默认行为，始终允许打开操作"""
        return True
    
    def can_close(self) -> bool:
        """覆盖默认行为，始终允许关闭操作"""
        return True
    
    def can_stop(self) -> bool:
        """覆盖默认行为，始终允许停止操作"""
        return True
    
    async def async_can_open(self) -> bool:
        """覆盖默认行为，始终允许打开操作"""
        return True
    
    async def async_can_close(self) -> bool:
        """覆盖默认行为，始终允许关闭操作"""
        return True
    
    async def async_can_stop(self) -> bool:
        """覆盖默认行为，始终允许停止操作"""
        return True
        
    def _get_device_class(self, device_type: str) -> CoverDeviceClass:
        """根据设备类型获取设备类别"""
        device_class_map = {
            "window_controller": CoverDeviceClass.SHUTTER,
            "curtain": CoverDeviceClass.SHUTTER,
            "shutter": CoverDeviceClass.SHUTTER,
            "blind": CoverDeviceClass.BLIND,
            "awning": CoverDeviceClass.AWNING
        }
        return device_class_map.get(device_type, CoverDeviceClass.SHUTTER)
        
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
                # 不再设置_attr_is_closed，让is_closed属性动态计算
    
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
            
            # 添加实际窗户状态
            position = attributes.get("r_travel")
            if position is not None:
                extra_attrs["actual_state"] = "closed" if position == 0 else "open"
            
            return extra_attrs
        return {}
                
    @property
    def is_closed(self) -> Optional[bool]:
        """根据位置判断是否关闭"""
        if self._attr_current_cover_position is not None:
            return self._attr_current_cover_position == 0
        return None  # 让HA使用默认行为
        
    @property
    def device_info(self) -> DeviceInfo:
        """返回设备信息"""
        # 动态获取设备当前关联的网关
        current_gateway_sn = get_device_gateway_mapping(self.hass, self.device_sn) or self.gateway_sn
        
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_sn)},
            name=self._attr_name,
            manufacturer=MANUFACTURER,
            model=self.device_type.capitalize(),
            serial_number=self.device_sn,
            via_device=(DOMAIN, current_gateway_sn)
        )
        
    async def _send_command_to_device(self, command: str, params: Optional[Dict[str, Any]] = None) -> bool:
        """发送命令到设备，处理网关切换逻辑
        
        Args:
            command: 命令类型
            params: 命令参数
        
        Returns:
            bool: 命令发送是否成功
        """
        try:
            # 动态获取设备当前关联的网关
            from .const import DEVICE_TO_GATEWAY_MAPPING
            current_gateway_sn = self.gateway_sn
            if DEVICE_TO_GATEWAY_MAPPING in self.hass.data[DOMAIN]:
                device_to_gateway_mapping = self.hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING]
                if self.device_sn in device_to_gateway_mapping:
                    current_gateway_sn = device_to_gateway_mapping[self.device_sn]
                    _LOGGER.debug("设备 %s 当前关联到网关: %s", self.device_sn, current_gateway_sn)
            
            # 如果设备关联的网关与当前网关不同，需要找到正确的mqtt_handler
            if current_gateway_sn != self.gateway_sn:
                # 查找与设备关联的网关的mqtt_handler
                for entry_id, data in self.hass.data[DOMAIN].items():
                    if isinstance(data, dict) and data.get("gateway_sn") == current_gateway_sn:
                        if "mqtt_handler" in data:
                            mqtt_handler = data["mqtt_handler"]
                            await mqtt_handler.send_command(self.device_sn, command, params)
                            self.async_write_ha_state()
                            _LOGGER.info("发送%s命令到设备 %s（通过网关 %s）", command, self.device_sn, current_gateway_sn)
                            return True
                _LOGGER.error("未找到设备 %s 关联的网关 %s 的MQTT处理器", self.device_sn, current_gateway_sn)
            else:
                # 使用当前mqtt_handler发送命令
                await self.mqtt_handler.send_command(self.device_sn, command, params)
                self.async_write_ha_state()
                _LOGGER.info("发送%s命令到设备: %s", command, self.device_sn)
                return True
        except Exception as e:
            _LOGGER.error("发送%s命令失败: %s", command, e)
        return False
    
    async def async_open_cover(self, **kwargs):
        """打开开窗器"""
        await self._send_command_to_device(COMMAND_OPEN)
    
    async def async_close_cover(self, **kwargs):
        """关闭开窗器"""
        await self._send_command_to_device(COMMAND_CLOSE)
    
    async def async_stop_cover(self, **kwargs):
        """停止开窗器"""
        await self._send_command_to_device(COMMAND_STOP)
    
    async def async_set_cover_position(self, **kwargs):
        """设置开窗器位置"""
        position = kwargs.get(ATTR_POSITION)
        if position is not None:
            await self._send_command_to_device(
                COMMAND_SET_POSITION,
                {"position": position}
            )
    

            
    async def async_update(self):
        """更新实体状态"""
        self._update_state_from_device()