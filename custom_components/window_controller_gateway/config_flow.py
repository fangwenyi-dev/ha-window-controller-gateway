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
    DEFAULT_GATEWAY_NAME,
    DEVICE_SETUP_DELAY
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

        # 从上下文中获取网关SN和名称（如果是从发现流程进入）
        gateway_sn_from_context = self.context.get("gateway_sn")
        gateway_name_from_context = self.context.get("gateway_name")

        if user_input is not None:
            gateway_sn = user_input[CONF_GATEWAY_SN].strip()
            gateway_name = user_input.get(CONF_GATEWAY_NAME, "").strip() or f"{DEFAULT_GATEWAY_NAME} {gateway_sn[-4:]}"

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
        default_sn = gateway_sn_from_context or (user_input.get(CONF_GATEWAY_SN, "") if user_input else "")
        if default_sn:
            default_name = gateway_name_from_context or (user_input.get(CONF_GATEWAY_NAME, f"{DEFAULT_GATEWAY_NAME} {default_sn[-4:]}") if user_input else f"{DEFAULT_GATEWAY_NAME} {default_sn[-4:]}")
        else:
            default_name = gateway_name_from_context or (user_input.get(CONF_GATEWAY_NAME, DEFAULT_GATEWAY_NAME) if user_input else DEFAULT_GATEWAY_NAME)
        
        data_schema = vol.Schema({
            vol.Required(
                CONF_GATEWAY_SN,
                default=default_sn
            ): str,
            vol.Optional(
                CONF_GATEWAY_NAME,
                description={"suggested_value": default_name},
                default=default_name
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

    async def async_step_replace_gateway(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle gateway replacement flow initialization"""
        # 从上下文中获取数据
        # 优先从context中直接获取，如果没有则从context["data"]中获取
        data = self.context.get("data", {})
        self.gateway_sn = self.context.get("gateway_sn") or data.get("gateway_sn")
        self.device_id = self.context.get("device_id") or data.get("device_id")

        # 直接进入替换步骤
        return await self.async_step_replace()

    async def async_step_discovery(self, discovery_info: Dict[str, Any]) -> FlowResult:
        """Handle discovery step"""
        _LOGGER.info("处理网关发现: %s", discovery_info)
        
        gateway_sn = discovery_info.get("gateway_sn")
        gateway_name = discovery_info.get("gateway_name", f"慧尖网关 {gateway_sn[-4:]}")
        replace_mode = discovery_info.get("replace_mode", False)
        current_gateway_sn = discovery_info.get("current_gateway_sn")
        
        # 检查是否已配置
        await self.async_set_unique_id(gateway_sn)
        self._abort_if_unique_id_configured()
        
        # 检查是否已存在配置的网关
        existing_entries = self.hass.config_entries.async_entries(DOMAIN)
        
        if replace_mode or existing_entries:
            # 替换模式或已存在配置的网关，进入替换流程
            _LOGGER.info("检测到替换模式或已配置的网关，进入替换流程")
            
            # 获取第一个已配置的网关信息或使用current_gateway_sn
            existing_gateway_sn = current_gateway_sn
            if not existing_gateway_sn and existing_entries:
                existing_entry = existing_entries[0]
                existing_gateway_sn = existing_entry.data.get(CONF_GATEWAY_SN)
            
            # 设置上下文信息
            # device_id应该是旧网关的SN（已配置的网关）
            # old_gateway_sn是旧网关的SN（已配置的网关）
            self.context.update({
                "gateway_sn": gateway_sn,  # 新网关的SN
                "gateway_name": gateway_name,
                "device_id": existing_gateway_sn,  # 旧网关的SN
                "old_gateway_sn": existing_gateway_sn,  # 旧网关的SN
                "new_gateway_sn": gateway_sn,  # 新网关的SN
                "title_placeholders": {
                    "name": gateway_name
                },
                "suggested_display_name": gateway_name,
                "source": "discovery",
                "replace_mode": replace_mode
            })
            
            # 进入替换流程
            return await self.async_step_confirm_migration()
        else:
            # 没有已配置的网关，进入添加流程
            _LOGGER.info("没有已配置的网关，进入添加流程")
            
            # 设置上下文信息，确保Home Assistant能够显示带有"忽略"按钮的发现卡片
            self.context.update({
                "gateway_sn": gateway_sn,
                "gateway_name": gateway_name,
                "title_placeholders": {
                    "name": gateway_name
                },
                "suggested_display_name": gateway_name,
                "source": "discovery"
            })
            
            # 对于发现的设备，Home Assistant会自动显示"忽略"按钮
            # 我们只需要确保流程能够正确处理
            return await self.async_step_user()
    
    async def async_step_ignore(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle ignore step"""
        _LOGGER.info("忽略网关: %s", self.context.get("gateway_sn"))
        
        # 调用忽略网关的方法
        gateway_sn = self.context.get("gateway_sn")
        if gateway_sn:
            from .discovery import async_ignore_gateway
            await async_ignore_gateway(self.hass, gateway_sn)
        
        # 中止流程
        return self.async_abort(reason="ignored")

    async def async_step_confirm_migration(self, user_input=None):
        """确认迁移"""
        if user_input is not None:
            if user_input.get("confirm"):
                # 保存迁移信息到数据中，以便在配置条目设置完成后使用
                migration_info = {
                    "old_gateway_sn": self.context["old_gateway_sn"],
                    "remove_old_gateway": user_input.get("remove_old", False)
                }
                
                _LOGGER.info("保存迁移信息到数据: %s", migration_info)
                
                # 检查是否已经存在具有相同SN的网关配置条目
                new_gateway_sn = self.context["new_gateway_sn"]
                existing_entries = self.hass.config_entries.async_entries(DOMAIN)
                existing_entry = None
                
                for entry in existing_entries:
                    if entry.data.get(CONF_GATEWAY_SN) == new_gateway_sn:
                        existing_entry = entry
                        break
                
                if existing_entry:
                    # 如果存在，更新该条目
                    _LOGGER.info("更新现有网关配置条目: %s", existing_entry.entry_id)
                    self.hass.config_entries.async_update_entry(
                        existing_entry,
                        data={
                            **existing_entry.data,
                            "migration_info": migration_info  # 将迁移信息保存到 data 中
                        }
                    )
                    # 重新加载配置条目
                    await self.hass.config_entries.async_reload(existing_entry.entry_id)
                    return self.async_abort(reason="updated_existing_gateway")
                else:
                    # 如果不存在，创建新条目
                    _LOGGER.info("创建新网关配置条目: %s", new_gateway_sn)
                    return self.async_create_entry(
                        title=self.context.get("gateway_name", f"慧尖网关 {new_gateway_sn[-4:]}"),
                        data={
                            CONF_GATEWAY_SN: new_gateway_sn,
                            CONF_GATEWAY_NAME: self.context.get("gateway_name", f"慧尖网关 {new_gateway_sn[-4:]}"),
                            "migration_info": migration_info  # 将迁移信息保存到 data 中
                        }
                    )
        
        # 显示确认表单
        return self.async_show_form(
            step_id="confirm_migration",
            data_schema=vol.Schema({
                vol.Required("confirm", default=False): bool,
                vol.Optional("remove_old", default=False): bool,
            }),
            description_placeholders={
                "old_gateway": self.context.get("old_gateway_name", self.context["old_gateway_sn"]),
                "new_gateway": self.context.get("new_gateway_name", self.context["new_gateway_sn"]),
                "device_count": self.context.get("device_count", "未知")
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
                
                def get_device(self, device_sn):
                    # 模拟获取设备，返回None
                    return None
                
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
            await asyncio.sleep(DEVICE_SETUP_DELAY)

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

    async def async_step_replace(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle gateway replacement step"""
        errors = {}
        
        # 从context中获取网关信息
        gateway_sn = self.context.get("gateway_sn")
        gateway_name = self.context.get("gateway_name", f"慧尖网关 {gateway_sn[-4:]}" if gateway_sn else "慧尖网关")
        device_id = self.context.get("device_id")
        old_gateway_sn_from_context = self.context.get("old_gateway_sn")
        replace_mode = self.context.get("replace_mode", False)

        # 获取所有已配置的网关
        existing_entries = self.hass.config_entries.async_entries(DOMAIN)
        gateway_options = {
            entry.data[CONF_GATEWAY_SN]: entry.data.get(CONF_GATEWAY_NAME, f"慧尖网关 {entry.data[CONF_GATEWAY_SN][-4:]}")
            for entry in existing_entries
        }

        # 如果只有1个网关，自动选中
        if len(gateway_options) == 1 and not old_gateway_sn_from_context:
            old_gateway_sn_from_context = list(gateway_options.keys())[0]
            _LOGGER.info("自动选中唯一网关: %s", old_gateway_sn_from_context)

        if user_input is not None:
            old_gateway_sn = user_input.get("old_gateway_sn")
            
            # 在替换模式下，新网关SN总是从上下文获取，不允许修改
            if replace_mode:
                new_gateway_sn = gateway_sn
            else:
                new_gateway_sn = user_input.get("new_gateway_sn", gateway_sn)  # 使用默认值（当前发现的网关）

            if not old_gateway_sn or len(old_gateway_sn) < 10:
                errors["old_gateway_sn"] = "invalid_sn_format"
            elif not replace_mode and (not new_gateway_sn or len(new_gateway_sn) < 10):
                errors["new_gateway_sn"] = "invalid_sn_format"
            else:
                # 保存到上下文
                self.context["old_gateway_sn"] = old_gateway_sn
                self.context["new_gateway_sn"] = new_gateway_sn
                self.context["old_gateway_name"] = gateway_options.get(old_gateway_sn, f"慧尖网关 {old_gateway_sn[-4:]}")
                self.context["new_gateway_name"] = gateway_name
                
                # 进入确认迁移步骤
                return await self.async_step_confirm_migration()

        # 构建数据模式，确保替换时必须输入旧网关和新网关SN
        data_schema = vol.Schema({})
        
        # 添加旧网关SN字段，使用下拉选择器
        if gateway_options:
            data_schema = data_schema.extend({
                vol.Required(
                    "old_gateway_sn",
                    default=user_input.get("old_gateway_sn", old_gateway_sn_from_context or list(gateway_options.keys())[0]) if user_input else old_gateway_sn_from_context or list(gateway_options.keys())[0]
                ): vol.In(gateway_options),
            })
        else:
            data_schema = data_schema.extend({
                vol.Required(
                    "old_gateway_sn",
                    default=user_input.get("old_gateway_sn", old_gateway_sn_from_context or "") if user_input else old_gateway_sn_from_context or ""
                ): str,
            })
        
        # 如果不是替换模式，允许用户输入新网关SN
        if not replace_mode:
            data_schema = data_schema.extend({
                vol.Required(
                    "new_gateway_sn",
                    default=user_input.get("new_gateway_sn", gateway_sn) if user_input else gateway_sn
                ): str,
            })

        return self.async_show_form(
            step_id="replace",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "gateway_name": gateway_name,
                "new_gateway_sn": gateway_sn
            }
        )

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

