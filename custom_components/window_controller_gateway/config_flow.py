"""Window Controller Gateway Configuration Flow"""
import voluptuous as vol
import re
import logging
import asyncio
from typing import Any, Dict, Optional

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv
from homeassistant.components import mqtt

from .const import (
    DOMAIN, 
    CONF_GATEWAY_SN, 
    CONF_GATEWAY_NAME, 
    DEFAULT_GATEWAY_NAME
)
from .mqtt_handler import WindowControllerMQTTHandler

_LOGGER = logging.getLogger(__name__)

def validate_gateway_sn(sn: str) -> bool:
    """Validate gateway serial number format"""
    if not sn or len(sn) < 10:
        return False
    return bool(re.match(r'^[a-zA-Z0-9]+$', sn))

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configuration flow handler class"""
    VERSION = 1

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle user step"""
        errors = {}

        if user_input is not None:
            gateway_sn = user_input[CONF_GATEWAY_SN].strip()
            gateway_name = user_input.get(CONF_GATEWAY_NAME, "").strip() or DEFAULT_GATEWAY_NAME

            # Validate gateway SN
            if not validate_gateway_sn(gateway_sn):
                errors[CONF_GATEWAY_SN] = "invalid_sn_format"
            else:
                # Check if already configured
                await self.async_set_unique_id(gateway_sn)
                self._abort_if_unique_id_configured()

                # Test gateway connectivity
                try:
                    connected = await self._test_gateway_connectivity(gateway_sn)
                    if not connected:
                        errors["base"] = "cannot_connect"
                except Exception:
                    errors["base"] = "cannot_connect"

                if not errors:
                    # Create config entry
                    return self.async_create_entry(
                        title=gateway_name,
                        data={
                            CONF_GATEWAY_SN: gateway_sn,
                            CONF_GATEWAY_NAME: gateway_name
                        }
                    )

        # Configuration form
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

    async def _test_gateway_connectivity(self, gateway_sn: str) -> bool:
        """Test gateway connectivity"""
        _LOGGER.info("Testing gateway connectivity for SN: %s", gateway_sn)

        try:
            # Check if MQTT integration is available
            if not self.hass.data.get("mqtt"):
                _LOGGER.error("MQTT integration not available")
                return False

            # Create a temporary MQTT handler for testing
            # We'll use a minimal device manager mock since we just need to test connectivity
            class MockDeviceManager:
                async def update_gateway_status(self, status):
                    pass
                
                async def update_device_status(self, device_sn, status, attributes=None):
                    pass
                
                def get_gateway_info(self):
                    return {"name": "Test Gateway"}
                
                def get_all_devices(self):
                    return []
                
                async def add_device(self, device_sn, device_name, device_type=None):
                    # 模拟添加设备
                    _LOGGER.debug("模拟添加设备: %s, 名称: %s", device_sn, device_name)
                    return device_sn

            mock_device_manager = MockDeviceManager()
            mqtt_handler = WindowControllerMQTTHandler(self.hass, gateway_sn, mock_device_manager)

            # Setup MQTT handler
            if not await mqtt_handler.setup():
                _LOGGER.error("Failed to setup MQTT handler")
                return False

            # Test connection
            connected = await mqtt_handler.check_connection()

            # Give the gateway a moment to respond
            await asyncio.sleep(2)

            # Cleanup
            await mqtt_handler.cleanup()

            if connected:
                _LOGGER.info("Gateway connectivity test passed")
            else:
                _LOGGER.warning("Gateway connectivity test failed")

            return connected

        except Exception as e:
            _LOGGER.error("Error testing gateway connectivity: %s", e)
            return False

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Create options flow"""
        return OptionsFlow(config_entry)

class OptionsFlow(config_entries.OptionsFlow):
    """Options flow handler class"""
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow"""
        self._config_entry = config_entry

    async def async_step_init(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Manage options"""
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