"""开窗器网关Cover平台 - 供LLM等使用Cover语义控制开窗器"""
import logging
from typing import Optional

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.components.cover import (
    CoverEntity,
    CoverEntityFeature,
    CoverDeviceClass,
)
from datetime import datetime, timedelta

from .base_entity import WindowControllerBaseEntity
from .const import (
    DOMAIN,
    CONF_GATEWAY_SN,
    CONF_GATEWAY_NAME,
    DEFAULT_GATEWAY_NAME,
    DEVICE_TYPE_WINDOW_OPENER,
    MANUFACTURER,
    COMMAND_OPEN,
    COMMAND_CLOSE,
    COMMAND_STOP,
)

_LOGGER = logging.getLogger(__name__)


from .utils import get_entity_registry


class WindowControllerCover(WindowControllerBaseEntity, CoverEntity):
    """开窗器Cover实体 - 供LLM等使用Cover语义控制"""

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
        """初始化开窗器Cover实体"""
        super().__init__(
            hass=hass,
            device_manager=device_manager,
            mqtt_handler=mqtt_handler,
            gateway_sn=gateway_sn,
            device_sn=device_sn,
            device_name=device_name
        )

        self._attr_unique_id = f"{gateway_sn}_{device_sn}_cover"
        self._attr_device_class = CoverDeviceClass.WINDOW
        self._attr_name = "开窗器"
        self.entry_id = entry_id
        self._attr_supported_features = (
            CoverEntityFeature.OPEN |
            CoverEntityFeature.CLOSE |
            CoverEntityFeature.STOP
        )
        # 始终可用，防止变灰
        self._attr_available = True
        self._last_state_update = None

    @property
    def device_info(self) -> DeviceInfo:
        """返回设备信息"""
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_sn)},
            name=self.device_name,
            manufacturer=MANUFACTURER,
            model="开窗器",
            serial_number=self.device_sn,
            sw_version="1.0"
        )

    @property
    def is_closed(self):
        """始终返回None，HA不知道开闭状态，所以所有按钮都可点击"""
        return None

    @property
    def is_closing(self):
        """始终返回False，确保关闭按钮不会变灰"""
        return False

    @property
    def is_opening(self):
        """始终返回False，确保打开按钮不会变灰"""
        return False

    @property
    def current_cover_position(self):
        """始终返回None，HA不知道位置，所以所有按钮都可点击

        注意：如果返回 0，HA 会自动灰掉关闭按钮；
        如果返回 100，HA 会自动灰掉打开按钮。
        因此必须返回 None 来保证所有按钮始终可用。
        位置信息通过 extra_state_attributes 供用户查看。
        """
        return None

    @property
    def extra_state_attributes(self):
        """返回额外状态属性，供用户查看设备实际位置和状态"""
        attrs = {}
        device = self.device_manager.get_device(self.device_sn)
        if device:
            status = device.get("status")
            if status:
                attrs["device_status"] = status
            attributes = device.get("attributes", {})
            r_travel = attributes.get("r_travel")
            if r_travel is not None:
                try:
                    attrs["position"] = max(0, min(100, int(r_travel)))
                except (ValueError, TypeError):
                    pass
        return attrs

    async def async_update(self) -> None:
        """定期更新状态，防止实体被HA标记为unavailable"""
        self._attr_available = True
        self.async_write_ha_state()

    async def async_open_cover(self, **kwargs) -> None:
        """打开开窗器"""
        try:
            await self._get_mqtt_handler().send_command(self.device_sn, COMMAND_OPEN)
            _LOGGER.info("Cover打开: %s", self.device_sn)
        except Exception as e:
            _LOGGER.error("Cover打开失败 %s: %s", self.device_sn, e)

    async def async_close_cover(self, **kwargs) -> None:
        """关闭开窗器"""
        try:
            await self._get_mqtt_handler().send_command(self.device_sn, COMMAND_CLOSE)
            _LOGGER.info("Cover关闭: %s", self.device_sn)
        except Exception as e:
            _LOGGER.error("Cover关闭失败 %s: %s", self.device_sn, e)

    async def async_stop_cover(self, **kwargs) -> None:
        """停止开窗器"""
        try:
            await self._get_mqtt_handler().send_command(self.device_sn, COMMAND_STOP)
            _LOGGER.info("Cover停止: %s", self.device_sn)
        except Exception as e:
            _LOGGER.error("Cover停止失败 %s: %s", self.device_sn, e)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置Cover实体"""
    _LOGGER.info("设置Cover平台: %s", entry.entry_id)

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

    created_covers = {}

    async def on_device_added(device_sn: str, device_name: str, device_type: str):
        """设备添加回调，自动创建Cover实体"""
        if device_type == DEVICE_TYPE_WINDOW_OPENER:
            entity_registry = get_entity_registry(hass)

            cover_unique_id = f"{gateway_sn}_{device_sn}_cover"
            cover_exists = entity_registry.async_get_entity_id("cover", DOMAIN, cover_unique_id) is not None

            if cover_exists:
                _LOGGER.debug("Cover实体已存在，跳过创建: %s", device_sn)
                return

            cover = WindowControllerCover(
                hass,
                device_manager,
                mqtt_handler,
                gateway_sn,
                device_sn,
                device_name,
                str(entry.entry_id)
            )
            async_add_entities([cover])
            created_covers[device_sn] = cover
            _LOGGER.info("自动为设备 %s 添加Cover实体", device_name)

    async def on_device_removed(device_sn: str, device_name: str, device_type: str):
        """设备移除回调，清理相关Cover实体"""
        if device_type == DEVICE_TYPE_WINDOW_OPENER:
            if device_sn in created_covers:
                cover = created_covers[device_sn]
                del created_covers[device_sn]

                try:
                    entity_registry = get_entity_registry(hass)
                    if cover.entity_id:
                        entity_registry.async_remove(cover.entity_id)
                        _LOGGER.info("已移除设备 %s 的Cover实体", device_name)
                except Exception as e:
                    _LOGGER.error("移除Cover实体失败 %s: %s", device_name, e)

    device_manager.set_device_added_callback(on_device_added)
    device_manager.set_device_removed_callback(on_device_removed)

    entities = []
    devices = device_manager.get_all_devices()
    for device in devices:
        if device.get("type") == DEVICE_TYPE_WINDOW_OPENER:
            device_sn = device["sn"]
            device_name = device["name"]

            # 启动循环无条件创建 Cover：
            # 注册表条目跨重启/重载持久保留，用注册表查重会导致重启后
            # 实体只有注册表条目、没有平台实例（不可用）。
            # 重复添加由 HA 按 unique_id 自动去重（替换更新）。
            cover = WindowControllerCover(
                hass,
                device_manager,
                mqtt_handler,
                gateway_sn,
                device_sn,
                device_name,
                str(entry.entry_id)
            )
            entities.append(cover)
            created_covers[device_sn] = cover

    if entities:
        async_add_entities(entities)
        _LOGGER.info("已添加 %d 个Cover实体", len(entities))
