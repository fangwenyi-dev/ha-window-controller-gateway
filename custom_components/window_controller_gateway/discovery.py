"""Window Controller Gateway Discovery Platform"""
import logging
from typing import Any, Dict, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, CONF_GATEWAY_SN, CONF_GATEWAY_NAME

_LOGGER = logging.getLogger(__name__)

async def async_setup_discovery_platform(hass: HomeAssistant):
    """设置发现平台"""
    _LOGGER.info("设置开窗器网关发现平台")
    
    # 注册发现平台
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["discovery"] = {
        "ignored_gateways": set()
    }
    
    return True

async def async_discover_gateway(hass: HomeAssistant, gateway_sn: str, gateway_name: str, replace_mode: bool = False, current_gateway_sn: str = None):
    """发现网关设备
    
    Args:
        hass: Home Assistant实例
        gateway_sn: 网关SN
        gateway_name: 网关名称
        replace_mode: 是否为替换模式
        current_gateway_sn: 当前网关SN（替换模式下使用）
    """
    _LOGGER.info(f"发现新网关: {gateway_name} (SN: {gateway_sn}), 替换模式: {replace_mode}")
    
    # 检查网关是否已被忽略
    if DOMAIN in hass.data and "discovery" in hass.data[DOMAIN]:
        if gateway_sn in hass.data[DOMAIN]["discovery"]["ignored_gateways"]:
            _LOGGER.debug(f"网关 {gateway_sn} 已被忽略，跳过发现")
            return
    
    # 检查网关是否已配置
    device_registry = dr.async_get(hass)
    existing_device = device_registry.async_get_device(
        identifiers={(DOMAIN, gateway_sn)}
    )
    
    if existing_device:
        _LOGGER.debug(f"网关 {gateway_sn} 已存在，跳过发现")
        return
    
    # 使用基本发现流程
    from homeassistant.config_entries import SOURCE_DISCOVERY
    
    # 创建发现流程
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": SOURCE_DISCOVERY,
            "show_ignore": True,  # 显示"忽略"按钮
            "replace_mode": replace_mode,  # 替换模式
            "current_gateway_sn": current_gateway_sn  # 当前网关SN（替换模式下使用）
        },
        data={
            "gateway_sn": gateway_sn,
            "gateway_name": gateway_name,
            "discovered": True,
            "replace_mode": replace_mode,
            "current_gateway_sn": current_gateway_sn
        }
    )
    
    _LOGGER.info("已使用标准发现流程发现网关: %s", gateway_name)

async def async_ignore_gateway(hass: HomeAssistant, gateway_sn: str):
    """忽略网关设备"""
    _LOGGER.info(f"忽略网关: {gateway_sn}")
    
    # 将网关添加到忽略列表
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    
    if "discovery" not in hass.data[DOMAIN]:
        hass.data[DOMAIN]["discovery"] = {
            "ignored_gateways": set()
        }
    
    hass.data[DOMAIN]["discovery"]["ignored_gateways"].add(gateway_sn)
    
    # 从实体注册表中删除相关实体
    entity_registry = er.async_get(hass)
    for entity in list(entity_registry.entities.values()):
        if entity.platform == DOMAIN and gateway_sn in entity.unique_id:
            entity_registry.async_remove(entity.entity_id)
            _LOGGER.debug(f"删除网关 {gateway_sn} 的实体: {entity.entity_id}")

async def async_unignore_gateway(hass: HomeAssistant, gateway_sn: str):
    """取消忽略网关设备"""
    _LOGGER.info(f"取消忽略网关: {gateway_sn}")
    
    # 从忽略列表中移除网关
    if DOMAIN in hass.data and "discovery" in hass.data[DOMAIN]:
        if gateway_sn in hass.data[DOMAIN]["discovery"]["ignored_gateways"]:
            hass.data[DOMAIN]["discovery"]["ignored_gateways"].remove(gateway_sn)
            _LOGGER.debug(f"网关 {gateway_sn} 已从忽略列表中移除")