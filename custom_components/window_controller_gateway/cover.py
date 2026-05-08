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
)

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


def _get_entity_registry(hass):
    """获取实体注册表（带缓存）"""
    return get_entity_registry(hass)


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

        self._attr_name = device_name
        self._attr_unique_id = f"{gateway_sn}_{device_sn}_cover"
        self.entry_id = entry_id
        self._attr_supported_features = (
            CoverEntityFeature.OPEN |
            CoverEntityFeature.CLOSE |
            CoverEntityFeature.STOP
        )

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

    def _update_state(self):
        """从设备管理器更新状态"""
        from datetime import datetime, timedelta

        device = self.device_manager.get_device(self.device_sn)
        if device:
            status = device.get("status")
            attributes = device.get("attributes", {})
            r_travel = attributes.get("r_travel")

            if status == "closed" or r_travel == 0:
                self._attr_is_closed = True
                self._attr_current_cover_position = 0
            elif status == "open" or (r_travel is not None and r_travel > 0):
                self._attr_is_closed = False
                self._attr_current_cover_position = 100
            else:
                self._attr_is_closed = None
                self._attr_current_cover_position = None

    async def async_open_cover(self, **kwargs):
        """打开开窗器"""
        try:
            current_gateway_sn = self.get_current_gateway_sn()
            if current_gateway_sn != self.gateway_sn:
                for entry_id, data in self.hass.data[DOMAIN].items():
                    if isinstance(data, dict) and data.get("gateway_sn") == current_gateway_sn:
                        if "mqtt_handler" in data:
                            await data["mqtt_handler"].send_command(self.device_sn, COMMAND_OPEN)
                            return
                _LOGGER.error("未找到设备 %s 关联的网关 %s 的MQTT处理器", self.device_sn, current_gateway_sn)
            else:
                await self.mqtt_handler.send_command(self.device_sn, COMMAND_OPEN)
                _LOGGER.info("Cover打开: %s", self.device_sn)
        except Exception as e:
            _LOGGER.error("Cover打开失败 %s: %s", self.device_sn, e)

    async def async_close_cover(self, **kwargs):
        """关闭开窗器"""
        try:
            current_gateway_sn = self.get_current_gateway_sn()
            if current_gateway_sn != self.gateway_sn:
                for entry_id, data in self.hass.data[DOMAIN].items():
                    if isinstance(data, dict) and data.get("gateway_sn") == current_gateway_sn:
                        if "mqtt_handler" in data:
                            await data["mqtt_handler"].send_command(self.device_sn, COMMAND_CLOSE)
                            return
                _LOGGER.error("未找到设备 %s 关联的网关 %s 的MQTT处理器", self.device_sn, current_gateway_sn)
            else:
                await self.mqtt_handler.send_command(self.device_sn, COMMAND_CLOSE)
                _LOGGER.info("Cover关闭: %s", self.device_sn)
        except Exception as e:
            _LOGGER.error("Cover关闭失败 %s: %s", self.device_sn, e)

    async def async_stop_cover(self, **kwargs):
        """停止开窗器"""
        try:
            current_gateway_sn = self.get_current_gateway_sn()
            if current_gateway_sn != self.gateway_sn:
                for entry_id, data in self.hass.data[DOMAIN].items():
                    if isinstance(data, dict) and data.get("gateway_sn") == current_gateway_sn:
                        if "mqtt_handler" in data:
                            await data["mqtt_handler"].send_command(self.device_sn, COMMAND_STOP)
                            return
                _LOGGER.error("未找到设备 %s 关联的网关 %s 的MQTT处理器", self.device_sn, current_gateway_sn)
            else:
                await self.mqtt_handler.send_command(self.device_sn, COMMAND_STOP)
                _LOGGER.info("Cover停止: %s", self.device_sn)
        except Exception as e:
            _LOGGER.error("Cover停止失败 %s: %s", self.device_sn, e)

    async def async_update(self):
        """更新实体状态"""
        self._update_state()


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
            entity_registry = _get_entity_registry(hass)

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
            mqtt_handler.add_status_callback(device_sn, cover.async_update)
            _LOGGER.info("自动为设备 %s 添加Cover实体", device_name)

    async def on_device_removed(device_sn: str, device_name: str, device_type: str):
        """设备移除回调，清理相关Cover实体"""
        if device_type == DEVICE_TYPE_WINDOW_OPENER:
            if device_sn in created_covers:
                cover = created_covers[device_sn]
                del created_covers[device_sn]
                mqtt_handler.remove_status_callback(device_sn, cover.async_update)

                try:
                    entity_registry = _get_entity_registry(hass)
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

        for device_sn, cover in created_covers.items():
            mqtt_handler.add_status_callback(device_sn, cover.async_update)
        _LOGGER.info("Cover回调注册完成")
