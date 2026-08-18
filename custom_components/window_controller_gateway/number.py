"""开窗器网关数值调节平台 - Number 实体（HA 界面滑动条）

通过 004 协议发送 rwp_winact_* 参数（0-100）控制命令，
并解析 005 上报的同名属性回显当前值。
当前支持：
- 速度（rwp_winact_speed）
- 力度（rwp_winact_strength）
"""
import logging

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.components.number import NumberEntity, NumberMode

from .base_entity import WindowControllerBaseEntity
from .const import (
    DOMAIN,
    CONF_GATEWAY_SN,
    DEVICE_TYPE_WINDOW_OPENER,
    MANUFACTURER,
    COMMAND_SET_SPEED,
    COMMAND_SET_STRENGTH,
    SPEED_MIN,
    SPEED_MAX,
    DEVICE_SETPOINTS,
)

_LOGGER = logging.getLogger(__name__)

from .utils import get_entity_registry


class WindowControllerRangeNumber(WindowControllerBaseEntity, NumberEntity):
    """开窗器数值调节滑动条基类（rwp_winact_*，0-100%）

    子类需定义：
    - _entity_suffix: unique_id 后缀（如 speed）
    - _entity_label: 实体名称（如 速度）
    - _entity_icon: 图标
    - _command: 发送命令（COMMAND_SET_SPEED / COMMAND_SET_STRENGTH）
    - _param_key: send_command 的参数字段（speed / strength）
    - _state_key: 设备属性中回显的键（winact_speed / winact_strength）
    """

    _entity_suffix = ""
    _entity_label = ""
    _entity_icon = ""
    _command = ""
    _param_key = ""
    _state_key = ""

    def __init__(
        self,
        hass: HomeAssistant,
        device_manager,
        mqtt_handler,
        gateway_sn: str,
        device_sn: str,
        device_name: str,
        entry_id: str = None
    ):
        """初始化滑动条实体"""
        super().__init__(
            hass=hass,
            device_manager=device_manager,
            mqtt_handler=mqtt_handler,
            gateway_sn=gateway_sn,
            device_sn=device_sn,
            device_name=device_name
        )

        self._attr_name = self._entity_label
        self._attr_unique_id = f"{gateway_sn}_{device_sn}_{self._entity_suffix}"
        self._attr_icon = self._entity_icon
        self._attr_native_min_value = float(SPEED_MIN)
        self._attr_native_max_value = float(SPEED_MAX)
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = "%"
        self._attr_mode = NumberMode.SLIDER
        self._attr_entity_category = EntityCategory.CONFIG
        # 始终可用，防止变灰（与按钮/Cover 行为一致）
        self._attr_available = True
        self.entry_id = entry_id

        # 初始化状态（若有已上报的值）
        self._update_state()

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

    def _read_setpoint(self):
        """读取设备参数设定值（上次用户设定的位置）"""
        setpoints = self.hass.data.get(DOMAIN, {}).get(DEVICE_SETPOINTS, {})
        return setpoints.get(self.device_sn, {}).get(self._param_key)

    def _update_state(self):
        """同步实体状态：显示上次设定的值（setpoint）

        注意：不读取 005 上报的运行时值——网关空闲时上报 0，
        若以运行时值回显，重新进入界面后滑块会跳回 0。
        """
        value = self._read_setpoint()
        if value is not None:
            try:
                value = int(value)
                self._attr_native_value = float(max(SPEED_MIN, min(SPEED_MAX, value)))
            except (ValueError, TypeError):
                _LOGGER.debug("设备 %s %s设定值无效: %r", self.device_sn, self._entity_label, value)

    async def async_update(self) -> None:
        """定期更新状态（HA 轮询）"""
        self._update_state()
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """滑动条拖动回调：发送 004 控制命令并本地记录设定值"""
        value_int = max(SPEED_MIN, min(SPEED_MAX, int(value)))
        try:
            success = await self._get_mqtt_handler().send_command(
                self.device_sn, self._command, {self._param_key: value_int}
            )
            if not success:
                _LOGGER.warning("设备 %s %s设置命令发送失败，不保存设定值", self.device_sn, self._entity_label)
                return
            # 本地记录设定值：重新进入界面/HA 重启后仍回显上次设定位置
            setpoints = self.hass.data.setdefault(DOMAIN, {}).setdefault(DEVICE_SETPOINTS, {})
            setpoints.setdefault(self.device_sn, {})[self._param_key] = value_int
            self._attr_native_value = float(value_int)
            self.async_write_ha_state()
            # 触发持久化保存（save_persistent_data 内部有防抖，连续拖动只落盘一次）
            from .persist import save_persistent_data
            self.hass.async_create_task(save_persistent_data(self.hass))
            _LOGGER.info("设备 %s %s设置为 %d%%", self.device_sn, self._entity_label, value_int)
        except Exception as e:
            _LOGGER.error("设置设备 %s %s失败: %s", self.device_sn, self._entity_label, e)


class WindowControllerSpeedNumber(WindowControllerRangeNumber):
    """开窗速度滑动条（rwp_winact_speed，0-100%）"""

    _entity_suffix = "speed"
    _entity_label = "速度"
    _entity_icon = "mdi:speedometer"
    _command = COMMAND_SET_SPEED
    _param_key = "speed"
    _state_key = "winact_speed"


class WindowControllerStrengthNumber(WindowControllerRangeNumber):
    """开窗力度滑动条（rwp_winact_strength，0-100%）"""

    _entity_suffix = "strength"
    _entity_label = "力度"
    _entity_icon = "mdi:arm-flex"
    _command = COMMAND_SET_STRENGTH
    _param_key = "strength"
    _state_key = "winact_strength"


# 所有数值调节实体类（新增 rwp_winact_* 参数时在此追加）
_NUMBER_ENTITY_CLASSES = (WindowControllerSpeedNumber, WindowControllerStrengthNumber)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置数值调节（Number）平台"""
    _LOGGER.info("设置数值调节平台: %s", entry.entry_id)

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

    # 设备SN -> {实体后缀: 实体实例}，用于移除时清理
    created_numbers = {}

    async def on_device_added(device_sn: str, device_name: str, device_type: str):
        """设备添加回调，自动创建滑动条实体"""
        if device_type == DEVICE_TYPE_WINDOW_OPENER:
            entity_registry = get_entity_registry(hass)
            entities_to_add = []
            created = {}
            for cls in _NUMBER_ENTITY_CLASSES:
                unique_id = f"{gateway_sn}_{device_sn}_{cls._entity_suffix}"
                if entity_registry.async_get_entity_id("number", DOMAIN, unique_id) is not None:
                    _LOGGER.debug("%s实体已存在，跳过创建: %s", cls._entity_label, device_sn)
                    continue
                number = cls(
                    hass, device_manager, mqtt_handler,
                    gateway_sn, device_sn, device_name, str(entry.entry_id)
                )
                entities_to_add.append(number)
                created[cls._entity_suffix] = number
                # 注册状态更新回调，005 上报时即时刷新
                mqtt_handler.add_status_callback(device_sn, number.async_update)
                _LOGGER.info("自动为设备 %s 添加%s滑动条", device_name, cls._entity_label)
            if entities_to_add:
                async_add_entities(entities_to_add)
            if created:
                created_numbers.setdefault(device_sn, {}).update(created)

    async def on_device_removed(device_sn: str, device_name: str, device_type: str):
        """设备移除回调，清理滑动条实体"""
        if device_type == DEVICE_TYPE_WINDOW_OPENER and device_sn in created_numbers:
            numbers = created_numbers.pop(device_sn)
            try:
                entity_registry = get_entity_registry(hass)
                for number in numbers.values():
                    mqtt_handler.remove_status_callback(device_sn, number.async_update)
                    if number.entity_id:
                        entity_registry.async_remove(number.entity_id)
                _LOGGER.info("已移除设备 %s 的滑动条实体", device_name)
            except Exception as e:
                _LOGGER.error("移除设备 %s 的滑动条实体失败: %s", device_name, e)

    device_manager.set_device_added_callback(on_device_added)
    device_manager.set_device_removed_callback(on_device_removed)

    # 启动循环无条件创建实体（与 button/sensor 一致）：
    # 注册表条目跨重启/重载持久保留，用注册表查重会导致重启后实体无平台实例。
    entities = []
    for device in device_manager.get_all_devices():
        if device.get("type") == DEVICE_TYPE_WINDOW_OPENER:
            device_sn = device["sn"]
            created_numbers[device_sn] = {}
            for cls in _NUMBER_ENTITY_CLASSES:
                number = cls(
                    hass, device_manager, mqtt_handler,
                    gateway_sn, device_sn, device["name"], str(entry.entry_id)
                )
                entities.append(number)
                created_numbers[device_sn][cls._entity_suffix] = number
                mqtt_handler.add_status_callback(device_sn, number.async_update)

    if entities:
        async_add_entities(entities)
        _LOGGER.info("已添加 %d 个滑动条实体", len(entities))
