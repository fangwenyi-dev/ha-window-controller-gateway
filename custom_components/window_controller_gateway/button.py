"""开窗器网关按钮平台"""
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.components.button import ButtonEntity

from .gateway import GatewayPairingButton, GatewayDeviceRemoveButton
from .base_entity import WindowControllerBaseEntity
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
    COMMAND_WIND_LOCK_TILT,
    COMMAND_WIND_LOCK_FLAT,
)

_LOGGER = logging.getLogger(__name__)


from .utils import get_entity_registry


def _create_device_buttons(hass, device_manager, mqtt_handler, gateway_sn, device_sn, device_name, entry_id):
    """为设备创建所有按钮实体
    
    Args:
        hass: Home Assistant实例
        device_manager: 设备管理器
        mqtt_handler: MQTT处理器
        gateway_sn: 网关SN
        device_sn: 设备SN
        device_name: 设备名称
        entry_id: 配置条目ID
    
    Returns:
        list: 要添加的按钮实体列表
    """
    entities_to_add = []
    
    # 按钮配置 - 使用序号前缀控制排列顺序（从上到下）
    button_configs = [
        ("open", "① 开启", "mdi:window-open", COMMAND_OPEN),
        ("stop", "② 暂停", "mdi:pause", COMMAND_STOP),
        ("close", "③ 关闭", "mdi:window-closed", COMMAND_CLOSE),
        ("a", "④ 内倒", "mdi:rotate-3d-variant", COMMAND_A)
    ]
    
    # 直接创建所有按钮，不检查实体是否存在
    # 与配对按钮逻辑一致，确保按钮始终可用
    # HA 会自动处理重复实体（使用相同的 unique_id）
    for button_type, button_name, icon, command in button_configs:
        button = BaseWindowControllerButton(
            hass,
            device_manager,
            mqtt_handler,
            gateway_sn,
            device_sn,
            device_name,
            button_name,
            button_type,
            command,
            icon,
            entry_id
        )
        entities_to_add.append(button)
        _LOGGER.debug("为设备 %s 添加%s按钮", device_name, button_name)
    
    return entities_to_add


class BaseWindowControllerButton(WindowControllerBaseEntity, ButtonEntity):
    """开窗器基础按钮实体"""
    
    def __init__(
        self,
        hass: HomeAssistant,
        device_manager,
        mqtt_handler,
        gateway_sn: str,
        device_sn: str,
        device_name: str,
        button_name: str,
        button_type: str,
        command: str,
        icon: str,
        entry_id: str = None
    ):
        """初始化开窗器基础按钮"""
        # 调用基类初始化
        super().__init__(
            hass=hass,
            device_manager=device_manager,
            mqtt_handler=mqtt_handler,
            gateway_sn=gateway_sn,
            device_sn=device_sn,
            device_name=device_name
        )
        
        self._attr_name = button_name
        # unique_id基于网关SN和设备SN，确保不同网关的同一设备有不同的实体
        self._attr_unique_id = f"{gateway_sn}_{device_sn}_{button_type}"
        self._attr_icon = icon
        self.command = command
        self.entry_id = entry_id
        # 确保按钮始终可用，不会变成灰色
        self._attr_available = True
        # 不设置 entity_category，使按钮出现在控制区域
        # HA 会按平台类型分卡片：Cover 一张卡片，Button 一张卡片
    
    @property
    def device_info(self) -> DeviceInfo:
        """返回设备信息"""
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_sn)},
            name=self.device_name,
            manufacturer=MANUFACTURER,
            model="开窗器",
            serial_number=self.device_sn
        )
    
    async def async_press(self) -> None:
        """按下按键，执行命令"""
        try:
            await self._get_mqtt_handler().send_command(self.device_sn, self.command)
            _LOGGER.info("已触发设备 %s 的%s命令", self.device_sn, self._attr_name)
        except Exception as e:
            _LOGGER.error("触发设备%s命令失败: %s", self._attr_name, e)


class WindLockModeButton(WindowControllerBaseEntity, ButtonEntity):
    """风锁模式按钮实体 - 内倒模式/平开模式

    设为 CONFIG 类别，使按钮出现在配置区域，
    与控制区的 Cover 和基础控制按钮分离。
    """

    def __init__(
        self,
        hass: HomeAssistant,
        device_manager,
        mqtt_handler,
        gateway_sn: str,
        device_sn: str,
        device_name: str,
        button_name: str,
        button_type: str,
        command: str,
        icon: str,
        entry_id: str = None
    ):
        """初始化风锁模式按钮"""
        super().__init__(
            hass=hass,
            device_manager=device_manager,
            mqtt_handler=mqtt_handler,
            gateway_sn=gateway_sn,
            device_sn=device_sn,
            device_name=device_name
        )

        self._attr_name = button_name
        self._attr_unique_id = f"{gateway_sn}_{device_sn}_{button_type}"
        self._attr_icon = icon
        self.command = command
        self.entry_id = entry_id
        self._attr_available = True
        # 设为配置类，使按钮出现在配置区域
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def device_info(self) -> DeviceInfo:
        """返回设备信息"""
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_sn)},
            name=self.device_name,
            manufacturer=MANUFACTURER,
            model="开窗器",
            serial_number=self.device_sn
        )

    async def async_press(self) -> None:
        """按下按键，发送风锁模式命令"""
        try:
            await self._get_mqtt_handler().send_command(self.device_sn, self.command)
            _LOGGER.info("已触发设备 %s 的%s", self.device_sn, self._attr_name)
        except Exception as e:
            _LOGGER.error("触发设备%s失败: %s", self._attr_name, e)


def _create_wind_lock_buttons(hass, device_manager, mqtt_handler, gateway_sn, device_sn, device_name, entry_id):
    """为设备创建风锁模式按钮（内倒模式、平开模式）

    Args:
        hass: Home Assistant实例
        device_manager: 设备管理器
        mqtt_handler: MQTT处理器
        gateway_sn: 网关SN
        device_sn: 设备SN
        device_name: 设备名称
        entry_id: 配置条目ID

    Returns:
        list: 风锁模式按钮实体列表
    """
    button_configs = [
        ("wind_lock_flat", "⑤ 平开模式", "mdi:window-open", COMMAND_WIND_LOCK_FLAT),
        ("wind_lock_tilt", "⑥ 内倒模式", "mdi:window-open-variant", COMMAND_WIND_LOCK_TILT),
    ]

    entities = []
    for button_type, button_name, icon, command in button_configs:
        button = WindLockModeButton(
            hass,
            device_manager,
            mqtt_handler,
            gateway_sn,
            device_sn,
            device_name,
            button_name,
            button_type,
            command,
            icon,
            entry_id
        )
        entities.append(button)
        _LOGGER.debug("为设备 %s 添加%s按钮", device_name, button_name)

    return entities


def _fix_entity_categories(hass, gateway_sn, device_sn):
    """强制更新实体注册表中的 entity_category
    
    HA 实体注册表会缓存 entity_category，代码中修改 _attr_entity_category 
    不会自动更新已有实体。需要显式调用 async_update_entity 来修正。
    """
    from homeassistant.helpers.entity_registry import async_get
    entity_registry = async_get(hass)
    
    # 控制区按钮（无 entity_category）
    control_button_types = ["open", "stop", "close", "a"]
    # 配置区按钮（CONFIG）
    config_button_types = ["wind_lock_tilt", "wind_lock_flat"]
    
    for button_type in control_button_types:
        unique_id = f"{gateway_sn}_{device_sn}_{button_type}"
        entity_id = entity_registry.async_get_entity_id("button", DOMAIN, unique_id)
        if entity_id:
            entity_entry = entity_registry.entities.get(entity_id)
            if entity_entry and entity_entry.entity_category is not None:
                entity_registry.async_update_entity(entity_id, entity_category=None)
                _LOGGER.info("修正控制按钮 entity_category → None: %s", entity_id)
    
    for button_type in config_button_types:
        unique_id = f"{gateway_sn}_{device_sn}_{button_type}"
        entity_id = entity_registry.async_get_entity_id("button", DOMAIN, unique_id)
        if entity_id:
            entity_entry = entity_registry.entities.get(entity_id)
            if entity_entry and entity_entry.entity_category != EntityCategory.CONFIG:
                entity_registry.async_update_entity(entity_id, entity_category=EntityCategory.CONFIG)
                _LOGGER.info("修正配置按钮 entity_category → CONFIG: %s", entity_id)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置按钮平台"""
    _LOGGER.info("设置按钮平台: %s, entry_id: %s", entry.entry_id, entry.entry_id)
    # 从设备管理器获取设备
    domain_data = hass.data[DOMAIN]
    entry_data = domain_data.get(entry.entry_id)
    
    _LOGGER.info("按钮平台: 获取到 domain_data, keys: %s", list(domain_data.keys()))
    
    if not entry_data:
        _LOGGER.error("配置条目数据未找到: %s, domain_data keys: %s", entry.entry_id, list(domain_data.keys()))
        return
        
    device_manager = entry_data.get("device_manager")
    mqtt_handler = entry_data.get("mqtt_handler")
    
    if not device_manager or not mqtt_handler:
        _LOGGER.error("设备管理器或MQTT处理器未找到, device_manager: %s, mqtt_handler: %s", device_manager, mqtt_handler)
        return
    
    gateway_sn = entry.data[CONF_GATEWAY_SN]
    gateway_name = entry.data.get(CONF_GATEWAY_NAME, f"{DEFAULT_GATEWAY_NAME} {gateway_sn[-4:]}")
    
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
        gateway_name,
        str(entry.entry_id)
    )
    entities.append(pairing_button)
    
    # 添加网关替换按钮 - 暂时注释，保留功能但不显示
    # replace_button = GatewayReplaceButton(
    #     hass,
    #     device_manager,
    #     mqtt_handler,
    #     gateway_sn,
    #     gateway_name,
    #     str(entry.entry_id)
    # )
    # entities.append(replace_button)
    
    # 为每个开窗器设备添加删除按钮（显示在网关控制栏）
    devices = device_manager.get_all_devices()
    _LOGGER.info("按钮平台: 获取到 %d 个设备: %s", len(devices), [d.get("sn") for d in devices])
    for device in devices:
        _LOGGER.debug("处理设备: %s, 类型: %s", device.get("sn"), device.get("type"))
        if device["type"] == DEVICE_TYPE_WINDOW_OPENER:
            device_sn = device["sn"]
            device_name = device["name"]
            
            # 强制修正已有实体的 entity_category（解决注册表缓存旧值的问题）
            _fix_entity_categories(hass, gateway_sn, device_sn)
            
            # 生成删除按钮的唯一ID
            remove_button_unique_id = f"{gateway_sn}_remove_{device_sn}"
            
            # 直接添加删除按钮，不检查实体是否存在
            # HA 会自动处理重复实体，确保按钮始终可用
            remove_button = GatewayDeviceRemoveButton(
                hass,
                device_manager,
                mqtt_handler,
                gateway_sn,
                gateway_name,
                device_sn,
                device_name,
                str(entry.entry_id)
            )
            entities.append(remove_button)
            created_remove_buttons[device_sn] = remove_button
            _LOGGER.debug("为设备 %s 添加删除按钮", device_name)
            
            device_buttons = _create_device_buttons(hass, device_manager, mqtt_handler, gateway_sn, device_sn, device_name, str(entry.entry_id))
            _LOGGER.debug("设备 %s 创建了 %d 个按钮", device_sn, len(device_buttons))
            entities.extend(device_buttons)
            
            # 创建风锁模式按钮（内倒模式、平开模式）- 不设置 entity_category，独立显示
            wind_lock_buttons = _create_wind_lock_buttons(hass, device_manager, mqtt_handler, gateway_sn, device_sn, device_name, str(entry.entry_id))
            entities.extend(wind_lock_buttons)
    
    # 定义设备添加回调函数
    async def on_device_added(device_sn: str, device_name: str, device_type: str):
        """设备添加回调，自动创建按钮"""
        if device_type == DEVICE_TYPE_WINDOW_OPENER:
            entity_registry = get_entity_registry(hass)
            entities_to_add = []
            
            # 强制修正已有实体的 entity_category
            _fix_entity_categories(hass, gateway_sn, device_sn)
            
            # 检查删除按钮是否已存在
            remove_unique_id = f"{gateway_sn}_remove_{device_sn}"
            if not entity_registry.async_get_entity_id("button", DOMAIN, remove_unique_id):
                remove_button = GatewayDeviceRemoveButton(
                    hass,
                    device_manager,
                    mqtt_handler,
                    gateway_sn,
                    gateway_name,
                    device_sn,
                    device_name,
                    str(entry.entry_id)
                )
                entities_to_add.append(remove_button)
                created_remove_buttons[device_sn] = remove_button
                entry_data["created_remove_buttons"] = created_remove_buttons
                _LOGGER.debug("为设备 %s 添加删除按钮", device_name)
            
            # 检查设备按钮是否已存在（用 open 按钮作代表检查）
            open_unique_id = f"{gateway_sn}_{device_sn}_open"
            if not entity_registry.async_get_entity_id("button", DOMAIN, open_unique_id):
                # 为设备创建所有按钮
                device_buttons = _create_device_buttons(hass, device_manager, mqtt_handler, gateway_sn, device_sn, device_name, str(entry.entry_id))
                entities_to_add.extend(device_buttons)
            
            # 检查风锁模式按钮是否已存在
            wind_lock_tilt_unique_id = f"{gateway_sn}_{device_sn}_wind_lock_tilt"
            if not entity_registry.async_get_entity_id("button", DOMAIN, wind_lock_tilt_unique_id):
                wind_lock_buttons = _create_wind_lock_buttons(hass, device_manager, mqtt_handler, gateway_sn, device_sn, device_name, str(entry.entry_id))
                entities_to_add.extend(wind_lock_buttons)
            
            # 只有当有实体需要添加时才调用async_add_entities
            if entities_to_add:
                async_add_entities(entities_to_add)
                _LOGGER.info("自动为设备 %s 添加按钮实体", device_name)
    
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
                    button_types = ["open", "stop", "close", "a", "wind_lock_tilt", "wind_lock_flat"]
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
