"""配置流程开窗器网关"""
import voluptuous as vol
import re
import logging
from typing import Any, Dict, Optional

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN, 
    CONF_GATEWAY_SN, 
    CONF_GATEWAY_NAME, 
    DEFAULT_GATEWAY_NAME
)

_LOGGER = logging.getLogger(__name__)

def validate_gateway_sn(sn: str) -> bool:
    """验证网关序列号格式"""
    if not sn or len(sn) < 10:
        return False
    return bool(re.match(r'^[a-zA-Z0-9]+$', sn))

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """配置流程处理类"""
    VERSION = 1

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """处理用户步骤"""
        errors = {}

        if user_input is not None:
            gateway_sn = user_input[CONF_GATEWAY_SN].strip()
            gateway_name = user_input.get(CONF_GATEWAY_NAME, "").strip() or DEFAULT_GATEWAY_NAME

            # 验证网关SN
            if not validate_gateway_sn(gateway_sn):
                errors[CONF_GATEWAY_SN] = "invalid_sn_format"
            else:
                # 检查是否已配置
                await self.async_set_unique_id(gateway_sn)
                self._abort_if_unique_id_configured()

                # 创建配置条目
                return self.async_create_entry(
                    title=gateway_name,
                    data={
                        CONF_GATEWAY_SN: gateway_sn,
                        CONF_GATEWAY_NAME: gateway_name
                    }
                )

        # 配置表单
        data_schema = vol.Schema({
            vol.Required(
                CONF_GATEWAY_SN,
                default=user_input.get(CONF_GATEWAY_SN, "") if user_input else ""
            ): str,
            vol.Optional(
                CONF_GATEWAY_NAME,
                description={"suggested_value": DEFAULT_GATEWAY_NAME},
                default=user_input.get(CONF_GATEWAY_NAME, DEFAULT_GATEWAY_NAME) if user_input else DEFAULT_GATEWAY_NAME
            ): str,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "example_sn": "100121501186",
                "min_length": "10"
            }
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """创建选项流程"""
        return OptionsFlow(config_entry)

class OptionsFlow(config_entries.OptionsFlow):
    """选项流程处理类"""
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """初始化选项流程"""
        self._config_entry = config_entry

    async def async_step_init(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """管理选项"""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    "discovery_interval",
                    default=self._config_entry.options.get("discovery_interval", 300)
                ): vol.All(vol.Coerce(int), vol.Range(min=60, max=3600)),
                vol.Optional(
                    "auto_discovery",
                    default=self._config_entry.options.get("auto_discovery", True)
                ): bool,
                vol.Optional(
                    "debug_logging",
                    default=self._config_entry.options.get("debug_logging", False)
                ): bool,
            })
        )