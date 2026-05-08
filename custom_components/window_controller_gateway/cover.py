"""开窗器网关组件"""
import logging

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    CONF_GATEWAY_SN,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置开窗器实体"""
    _LOGGER.info("设置Cover平台: %s", entry.entry_id)
    
    # 不再创建 Cover 实体，只使用 button.py 中创建的独立按钮
    _LOGGER.info("Cover 实体已禁用，只使用独立按钮控制")