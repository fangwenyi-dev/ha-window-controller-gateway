"""开窗器网关按钮平台"""
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.components.button import ButtonEntity

from .gateway import GatewayPairingButton, GatewayDeviceRemoveButton
from .const import (
    DOMAIN,
    CONF_GATEWAY_SN,
    CONF_GATEWAY_NAME,
    DEFAULT_GATEWAY_NAME,
    DEVICE_TYPE_WINDOW_OPENER,
    MANUFACTURER,
    COMMAND_A,
    COMMAND_OPEN,
    COMMAND_CLOSE,
    COMMAND_STOP,
    ENTITY_GATEWAY_PREFIX
)

_LOGGER = logging.getLogger(__name__)

class WindowControllerAButton(ButtonEntity):
    """开窗器A按钮实体"""
    
    def __init__(
        self,
        hass: HomeAssistant,
        device_manager,
        mqtt_handler,
        gateway_sn: str,
        device_sn: str,
        device_name: str
    ):
        """初始化开窗器A按钮"""
        self.hass = hass
        self.device_manager = device_manager
        self.mqtt_handler = mqtt_handler
        self.gateway_sn = gateway_sn
        self.device_sn = device_sn
        self.device_name = device_name
        self._attr_name = "A"
        self._attr_unique_id = f"{gateway_sn}_{device_sn}_a"
        # 添加图标
        self._attr_icon = "mdi:alpha-a"
    
    @property
    def device_info(self) -> DeviceInfo:
        """返回设备信息"""
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_sn)},
            name=self.device_name,
            manufacturer=MANUFACTURER,
            model="开窗器",
            via_device=(DOMAIN, self.gateway_sn)
        )
    
    async def async_press(self) -> None:
        """按下按键，执行A命令"""
        try:
            # 调用MQTT处理器发送A命令
            await self.mqtt_handler.send_command(self.device_sn, COMMAND_A)
            _LOGGER.info("已触发设备 %s 的A命令", self.device_sn)
        except Exception as e:
            _LOGGER.error("触发设备A命令失败: %s", e)

class WindowControllerOpenButton(ButtonEntity):
    """开窗器打开按钮实体"""
    
    def __init__(
        self,
        hass: HomeAssistant,
        device_manager,
        mqtt_handler,
        gateway_sn: str,
        device_sn: str,
        device_name: str
    ):
        """初始化开窗器打开按钮"""
        self.hass = hass
        self.device_manager = device_manager
        self.mqtt_handler = mqtt_handler
        self.gateway_sn = gateway_sn
        self.device_sn = device_sn
        self.device_name = device_name
        self._attr_name = "开启"
        self._attr_unique_id = f"{gateway_sn}_{device_sn}_open"
        # 添加图标
        self._attr_icon = "mdi:window-open"
    
    @property
    def device_info(self) -> DeviceInfo:
        """返回设备信息"""
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_sn)},
            name=self.device_name,
            manufacturer=MANUFACTURER,
            model="开窗器",
            via_device=(DOMAIN, self.gateway_sn)
        )
    
    async def async_press(self) -> None:
        """按下按键，执行打开命令"""
        try:
            # 调用MQTT处理器发送打开命令
            await self.mqtt_handler.send_command(self.device_sn, COMMAND_OPEN)
            _LOGGER.info("已触发设备 %s 的打开命令", self.device_sn)
        except Exception as e:
            _LOGGER.error("触发设备打开命令失败: %s", e)

class WindowControllerCloseButton(ButtonEntity):
    """开窗器关闭按钮实体"""
    
    def __init__(
        self,
        hass: HomeAssistant,
        device_manager,
        mqtt_handler,
        gateway_sn: str,
        device_sn: str,
        device_name: str
    ):
        """初始化开窗器关闭按钮"""
        self.hass = hass
        self.device_manager = device_manager
        self.mqtt_handler = mqtt_handler
        self.gateway_sn = gateway_sn
        self.device_sn = device_sn
        self.device_name = device_name
        self._attr_name = "关闭"
        self._attr_unique_id = f"{gateway_sn}_{device_sn}_close"
        # 添加图标
        self._attr_icon = "mdi:window-closed"
    
    @property
    def device_info(self) -> DeviceInfo:
        """返回设备信息"""
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_sn)},
            name=self.device_name,
            manufacturer=MANUFACTURER,
            model="开窗器",
            via_device=(DOMAIN, self.gateway_sn)
        )
    
    async def async_press(self) -> None:
        """按下按键，执行关闭命令"""
        try:
            # 调用MQTT处理器发送关闭命令
            await self.mqtt_handler.send_command(self.device_sn, COMMAND_CLOSE)
            _LOGGER.info("已触发设备 %s 的关闭命令", self.device_sn)
        except Exception as e:
            _LOGGER.error("触发设备关闭命令失败: %s", e)

class WindowControllerStopButton(ButtonEntity):
    """开窗器停止按钮实体"""
    
    def __init__(
        self,
        hass: HomeAssistant,
        device_manager,
        mqtt_handler,
        gateway_sn: str,
        device_sn: str,
        device_name: str
    ):
        """初始化开窗器停止按钮"""
        self.hass = hass
        self.device_manager = device_manager
        self.mqtt_handler = mqtt_handler
        self.gateway_sn = gateway_sn
        self.device_sn = device_sn
        self.device_name = device_name
        self._attr_name = "暂停"
        self._attr_unique_id = f"{gateway_sn}_{device_sn}_stop"
        # 添加图标
        self._attr_icon = "mdi:pause"
    
    @property
    def device_info(self) -> DeviceInfo:
        """返回设备信息"""
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_sn)},
            name=self.device_name,
            manufacturer=MANUFACTURER,
            model="开窗器",
            via_device=(DOMAIN, self.gateway_sn)
        )
    
    async def async_press(self) -> None:
        """按下按键，执行停止命令"""
        try:
            # 调用MQTT处理器发送停止命令
            await self.mqtt_handler.send_command(self.device_sn, COMMAND_STOP)
            _LOGGER.info("已触发设备 %s 的停止命令", self.device_sn)
        except Exception as e:
            _LOGGER.error("触发设备停止命令失败: %s", e)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置按钮平台"""
    _LOGGER.debug("设置按钮平台")
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
    
    gateway_sn = entry.data[CONF_GATEWAY_SN]
    gateway_name = entry.data.get(CONF_GATEWAY_NAME, f"{DEFAULT_GATEWAY_NAME} {gateway_sn[-6:]}")
    
    # 存储已创建的删除按钮，用于后续清理
    # 始终使用空字典，避免组件重载时重复创建已存在的实体
    created_remove_buttons = {}
    
    # 添加按钮实体
    entities = []
    
    # 添加配对按钮
    pairing_button = GatewayPairingButton(
        hass,
        device_manager,
        mqtt_handler,
        gateway_sn,
        gateway_name
    )
    entities.append(pairing_button)
    
    # 为每个开窗器设备添加删除按钮（显示在网关控制栏）
    devices = device_manager.get_all_devices()
    
    # 获取实体注册表，用于检查实体是否已存在
    from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
    entity_registry = async_get_entity_registry(hass)
    
    for device in devices:
        if device["type"] == DEVICE_TYPE_WINDOW_OPENER:
            device_sn = device["sn"]
            device_name = device["name"]
            
            # 生成删除按钮的唯一ID
            remove_button_unique_id = f"{ENTITY_GATEWAY_PREFIX}{gateway_sn}_remove_{device_sn}"
            
            # 检查实体是否已经存在于实体注册表中
            existing_entity = entity_registry.async_get(remove_button_unique_id)
            
            # 只有当实体不存在时才创建
            if not existing_entity:
                # 添加删除按钮（显示在网关控制栏）
                remove_button = GatewayDeviceRemoveButton(
                    hass,
                    device_manager,
                    mqtt_handler,
                    gateway_sn,
                    gateway_name,
                    device_sn,
                    device_name
                )
                entities.append(remove_button)
                created_remove_buttons[device_sn] = remove_button
                _LOGGER.debug("为设备 %s 添加删除按钮", device_name)
            else:
                _LOGGER.debug("设备 %s 的删除按钮已存在于实体注册表中，跳过创建", device_name)
            # 添加打开按钮（显示在设备控制栏）
            open_button = WindowControllerOpenButton(
                hass,
                device_manager,
                mqtt_handler,
                gateway_sn,
                device_sn,
                device_name
            )
            entities.append(open_button)
            _LOGGER.debug("为设备 %s 添加打开按钮", device_name)
            
            # 添加停止按钮（显示在设备控制栏）
            stop_button = WindowControllerStopButton(
                hass,
                device_manager,
                mqtt_handler,
                gateway_sn,
                device_sn,
                device_name
            )
            entities.append(stop_button)
            _LOGGER.debug("为设备 %s 添加停止按钮", device_name)
            
            # 添加关闭按钮（显示在设备控制栏）
            close_button = WindowControllerCloseButton(
                hass,
                device_manager,
                mqtt_handler,
                gateway_sn,
                device_sn,
                device_name
            )
            entities.append(close_button)
            _LOGGER.debug("为设备 %s 添加关闭按钮", device_name)
            
            # 添加A按钮（显示在设备控制栏）
            a_button = WindowControllerAButton(
                hass,
                device_manager,
                mqtt_handler,
                gateway_sn,
                device_sn,
                device_name
            )
            entities.append(a_button)
            _LOGGER.debug("为设备 %s 添加A按钮", device_name)
    
    # 定义设备添加回调函数
    async def on_device_added(device_sn: str, device_name: str, device_type: str):
        """设备添加回调，自动创建按钮"""
        if device_type == DEVICE_TYPE_WINDOW_OPENER:
            # 生成删除按钮的唯一ID
            remove_button_unique_id = f"{ENTITY_GATEWAY_PREFIX}{gateway_sn}_remove_{device_sn}"
            
            # 检查实体是否已经存在于实体注册表中
            from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
            entity_registry = async_get_entity_registry(hass)
            existing_entity = entity_registry.async_get(remove_button_unique_id)
            
            # 只有当实体不存在时才创建
            if not existing_entity:
                # 添加删除按钮（显示在网关控制栏）
                remove_button = GatewayDeviceRemoveButton(
                    hass,
                    device_manager,
                    mqtt_handler,
                    gateway_sn,
                    gateway_name,
                    device_sn,
                    device_name
                )
                # 添加打开按钮（显示在设备控制栏）
                open_button = WindowControllerOpenButton(
                    hass,
                    device_manager,
                    mqtt_handler,
                    gateway_sn,
                    device_sn,
                    device_name
                )
                
                # 添加停止按钮（显示在设备控制栏）
                stop_button = WindowControllerStopButton(
                    hass,
                    device_manager,
                    mqtt_handler,
                    gateway_sn,
                    device_sn,
                    device_name
                )
                
                # 添加关闭按钮（显示在设备控制栏）
                close_button = WindowControllerCloseButton(
                    hass,
                    device_manager,
                    mqtt_handler,
                    gateway_sn,
                    device_sn,
                    device_name
                )
                
                # 添加A按钮（显示在设备控制栏）
                a_button = WindowControllerAButton(
                    hass,
                    device_manager,
                    mqtt_handler,
                    gateway_sn,
                    device_sn,
                    device_name
                )
                
                async_add_entities([remove_button, open_button, stop_button, close_button, a_button])
                created_remove_buttons[device_sn] = remove_button
                # 更新entry_data中的删除按钮跟踪信息
                entry_data["created_remove_buttons"] = created_remove_buttons
                _LOGGER.info("自动为设备 %s 添加删除按钮、打开按钮、停止按钮、关闭按钮和A按钮", device_name)
            else:
                # 添加打开按钮（显示在设备控制栏）
                open_button = WindowControllerOpenButton(
                    hass,
                    device_manager,
                    mqtt_handler,
                    gateway_sn,
                    device_sn,
                    device_name
                )
                
                # 添加停止按钮（显示在设备控制栏）
                stop_button = WindowControllerStopButton(
                    hass,
                    device_manager,
                    mqtt_handler,
                    gateway_sn,
                    device_sn,
                    device_name
                )
                
                # 添加关闭按钮（显示在设备控制栏）
                close_button = WindowControllerCloseButton(
                    hass,
                    device_manager,
                    mqtt_handler,
                    gateway_sn,
                    device_sn,
                    device_name
                )
                
                # 添加A按钮（显示在设备控制栏）
                a_button = WindowControllerAButton(
                    hass,
                    device_manager,
                    mqtt_handler,
                    gateway_sn,
                    device_sn,
                    device_name
                )
                
                async_add_entities([open_button, stop_button, close_button, a_button])
                _LOGGER.info("设备 %s 的删除按钮已存在，只添加打开按钮、停止按钮、关闭按钮和A按钮", device_name)
    
    # 定义设备移除回调函数
    async def on_device_removed(device_sn: str, device_name: str, device_type: str):
        """设备移除回调，清理相关按钮"""
        if device_type == DEVICE_TYPE_WINDOW_OPENER:
            # 从存储中移除删除按钮引用
            if device_sn in created_remove_buttons:
                # 获取删除按钮实体
                remove_button = created_remove_buttons[device_sn]
                # 从跟踪字典中删除
                del created_remove_buttons[device_sn]
                # 更新entry_data中的删除按钮跟踪信息
                entry_data["created_remove_buttons"] = created_remove_buttons
                _LOGGER.info("已清理设备 %s 的删除按钮引用", device_name)
                
                # 尝试从实体注册表中删除按钮实体
                try:
                    from homeassistant.helpers.entity_registry import async_get
                    entity_registry = async_get(hass)
                    # 删除删除按钮
                    if remove_button.entity_id:
                        entity_registry.async_remove(remove_button.entity_id)
                        _LOGGER.info("已从实体注册表中删除设备 %s 的删除按钮", device_name)
                    
                    # 生成并删除其他按钮实体ID
                    button_types = ["open", "stop", "close", "a"]
                    for button_type in button_types:
                        button_unique_id = f"{gateway_sn}_{device_sn}_{button_type}"
                        # 查找并删除实体
                        entity_entry = entity_registry.async_get_entity_id("button", DOMAIN, button_unique_id)
                        if entity_entry:
                            entity_registry.async_remove(entity_entry)
                            _LOGGER.info("已从实体注册表中删除设备 %s 的%s按钮", device_name, button_type)
                except Exception as e:
                    _LOGGER.error("从实体注册表中删除设备 %s 的按钮失败: %s", device_name, e)
    
    # 设置设备添加回调
    device_manager.set_device_added_callback(on_device_added)
    # 设置设备移除回调
    device_manager.set_device_removed_callback(on_device_removed)
    _LOGGER.info("已设置设备回调")
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info("已添加 %d 个按钮实体", len(entities))
    
    # 存储删除按钮跟踪信息到entry_data，以便在卸载时清理
    entry_data["created_remove_buttons"] = created_remove_buttons
