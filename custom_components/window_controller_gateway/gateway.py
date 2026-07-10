"""开窗器网关实体"""
import logging
import asyncio

from homeassistant.core import HomeAssistant
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass
)
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .const import (
    DOMAIN,
    CONF_GATEWAY_SN,
    CONF_GATEWAY_NAME,
    DEFAULT_GATEWAY_NAME,
    ENTITY_ONLINE_SENSOR_SUFFIX,
    ENTITY_PAIRING_BUTTON_SUFFIX,
    MANUFACTURER,
    MODEL,
    GATEWAY_READY_DELAY,
    MAX_COMMAND_ID,
    GATEWAY_PAIRING_TIMEOUT,
    PAIRING_SN_PLACEHOLDER,
    DEVICE_TYPE_CURTAIN_CTR,
    PROTOCOL_HEAD
)

_LOGGER = logging.getLogger(__name__)



class GatewayOnlineSensor(BinarySensorEntity):
    """网关在线状态传感器"""
    
    _attr_has_entity_name = True
    
    def __init__(
        self,
        hass: HomeAssistant,
        device_manager,
        mqtt_handler,
        gateway_sn: str,
        gateway_name: str,
        entry_id: str = None
    ):
        """初始化网关在线状态传感器"""
        self.hass = hass
        self.device_manager = device_manager
        self.mqtt_handler = mqtt_handler
        self.gateway_sn = gateway_sn
        self.gateway_name = gateway_name
        self.entry_id = entry_id
        self._attr_name = "在线"
        # unique_id基于网关SN，确保同一网关只有一个在线状态传感器
        self._attr_unique_id = f"{gateway_sn}_online"
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        self._attr_is_on = False
        # 添加图标
        self._attr_icon = "mdi:access-point"
        
        # 添加状态更新回调
        try:
            self.mqtt_handler.add_status_callback(self._on_status_change)
        except Exception as e:
            _LOGGER.error("添加网关在线状态回调失败: %s", e)
        
        # 初始状态更新
        self._update_state()
    
    @property
    def device_info(self) -> DeviceInfo:
        """返回设备信息"""
        return DeviceInfo(
            identifiers={(DOMAIN, self.gateway_sn)},
            name=self.gateway_name,
            manufacturer=MANUFACTURER,
            model=MODEL,
            serial_number=self.gateway_sn
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
        try:
            if self.hass is not None:
                self.schedule_update_ha_state()
            else:
                _LOGGER.warning("无法更新网关状态：hass为None")
        except Exception as e:
            _LOGGER.error("更新网关状态失败: %s", e)
    
    async def async_update(self) -> None:
        """更新实体状态"""
        self._update_state()

    async def async_will_remove_from_hass(self) -> None:
        """当实体从HA中移除时调用"""
        # 移除状态更新回调
        self.mqtt_handler.remove_status_callback(self._on_status_change)

class GatewayPairingButton(ButtonEntity):
    """网关配对按键"""
    
    _attr_has_entity_name = True
    
    def __init__(
        self,
        hass: HomeAssistant,
        device_manager,
        mqtt_handler,
        gateway_sn: str,
        gateway_name: str,
        entry_id: str = None
    ):
        """初始化网关配对按键"""
        self.hass = hass
        self.device_manager = device_manager
        self.mqtt_handler = mqtt_handler
        self.gateway_sn = gateway_sn
        self.gateway_name = gateway_name
        self.entry_id = entry_id
        self._attr_name = "配对"
        # unique_id基于网关SN，确保同一网关只有一个配对按钮
        self._attr_unique_id = f"{gateway_sn}_pairing"
        # 添加图标
        self._attr_icon = "mdi:plus-circle"
    
    @property
    def device_info(self) -> DeviceInfo:
        """返回设备信息 - 与网关关联"""
        return DeviceInfo(
            identifiers={(DOMAIN, self.gateway_sn)},
            name=self.gateway_name,
            manufacturer=MANUFACTURER,
            model=MODEL
        )
    
    async def async_press(self) -> None:
        """按下按键，触发配对模式"""
        try:
            # P1 修复：使用 mqtt_handler.pairing_timeout_handle 统一管理配对超时，
            # 与 __init__.py 的 handle_start_pairing 服务共享同一个句柄。
            if self.mqtt_handler.pairing_timeout_handle:
                self.mqtt_handler.pairing_timeout_handle.cancel()
                self.mqtt_handler.pairing_timeout_handle = None

            # 使用命令管理器发送，统一处理命令ID、连接检查等
            success = await self.mqtt_handler.send_command(self.gateway_sn, "start_pairing")
            if not success:
                _LOGGER.error("发送配对命令失败")
                return
            
            # 更新配对状态
            self.mqtt_handler.pairing_active = True
            self.mqtt_handler._notify_status_change()
            
            # 更新网关状态
            self.hass.async_create_task(
                self.device_manager.update_gateway_status("pairing")
            )
            
            _LOGGER.info("配对命令已发送，持续时间: %d秒", GATEWAY_PAIRING_TIMEOUT)
            _LOGGER.info("已触发网关 %s 的配对模式", self.gateway_sn)
            
            # 设置定时器，在配对超时后恢复状态
            def pairing_timeout():
                self.mqtt_handler.pairing_timeout_handle = None
                self.mqtt_handler.pairing_active = False
                self.mqtt_handler._notify_status_change()
                self.hass.async_create_task(
                    self.device_manager.update_gateway_status("online" if self.mqtt_handler.connected else "offline")
                )
                _LOGGER.info("配对模式已超时，恢复正常状态")
            
            # 延迟执行超时回调
            self.mqtt_handler.pairing_timeout_handle = self.hass.loop.call_later(GATEWAY_PAIRING_TIMEOUT, pairing_timeout)
        except Exception as e:
            _LOGGER.error("触发网关配对模式失败: %s", e)

class GatewayDeviceRemoveButton(ButtonEntity):
    """网关设备删除按键"""
    
    _attr_has_entity_name = True
    
    def __init__(
        self,
        hass: HomeAssistant,
        device_manager,
        mqtt_handler,
        gateway_sn: str,
        gateway_name: str,
        device_sn: str,
        device_name: str,
        entry_id: str = None
    ):
        """初始化网关设备删除按键"""
        self.hass = hass
        self.device_manager = device_manager
        self.mqtt_handler = mqtt_handler
        self.gateway_sn = gateway_sn
        self.gateway_name = gateway_name
        self.device_sn = device_sn
        self.device_name = device_name
        self.entry_id = entry_id
        self._attr_name = f"移除 {device_sn[-4:]}"
        # unique_id基于网关SN和设备SN，确保同一网关的同一设备只有一个删除按钮
        self._attr_unique_id = f"{gateway_sn}_remove_{device_sn}"
        # 添加图标
        self._attr_icon = "mdi:delete"
        # 设为配置类，使按钮出现在配置区域
        self._attr_entity_category = EntityCategory.CONFIG
    
    @property
    def device_info(self) -> DeviceInfo:
        """返回设备信息 - 与网关关联，显示在网关控制栏中"""
        return DeviceInfo(
            identifiers={(DOMAIN, self.gateway_sn)},
            name=self.gateway_name,
            manufacturer=MANUFACTURER,
            model=MODEL
        )
    
    async def async_press(self) -> None:
        """按下按键，删除设备"""
        try:
            # 调用MQTT处理器的解绑设备方法
            await self.mqtt_handler.unbind_device(self.device_sn)
            _LOGGER.info("已发送解绑命令，设备SN: %s", self.device_sn)
            
            # 等待1秒，确保网关有足够时间处理解绑命令
            await asyncio.sleep(GATEWAY_READY_DELAY)
            
            # 从设备管理器中删除设备
            await self.device_manager.remove_device(self.device_sn)
            _LOGGER.info("已从系统中删除设备: %s", self.device_sn)
            
            # 从实体注册表中删除自身（删除按钮）
            from homeassistant.helpers.entity_registry import async_get
            entity_registry = async_get(self.hass)
            
            entity_id = entity_registry.async_get_entity_id("button", DOMAIN, self._attr_unique_id)
            if entity_id:
                entity_registry.async_remove(entity_id)
                _LOGGER.info("已从实体注册表中删除删除按钮: %s", entity_id)
            else:
                _LOGGER.debug("删除按钮实体未找到，可能已经被删除: %s", self._attr_unique_id)
        except Exception as e:
            _LOGGER.error("触发设备解绑模式失败: %s", e)