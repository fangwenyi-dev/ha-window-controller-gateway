"""开窗器网关按钮平台"""
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .gateway import GatewayPairingButton
from .const import (
    DOMAIN,
    CONF_GATEWAY_SN,
    CONF_GATEWAY_NAME,
    DEFAULT_GATEWAY_NAME
)

_LOGGER = logging.getLogger(__name__)

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
    
    # 只添加配对按钮
    entities = []
    pairing_button = GatewayPairingButton(
        hass,
        device_manager,
        mqtt_handler,
        gateway_sn,
        gateway_name
    )
    entities.append(pairing_button)
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info("已添加 %d 个按钮实体", len(entities))
