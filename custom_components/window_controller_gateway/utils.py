"""工具模块 - 存放通用辅助函数"""
import logging
from typing import Dict, Any, Optional, Tuple
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def get_entity_registry(hass: HomeAssistant):
    """获取实体注册表

    Args:
        hass: Home Assistant实例

    Returns:
        EntityRegistry: 实体注册表
    """
    from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
    return async_get_entity_registry(hass)


def clear_entity_registry_cache(hass=None):
    """清理实体注册表缓存（兼容接口，实际不再需要缓存管理）"""
    pass

def find_gateway_by_device_id(hass: Any, device_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """根据设备ID查找对应的网关
    
    Args:
        hass: Home Assistant实例
        device_id: 设备ID，包含网关SN或设备SN
        
    Returns:
        Tuple[Optional[Dict[str, Any]], Optional[str]]: (网关数据, 网关SN) 如果找到，否则 (None, None)
    """
    if DOMAIN not in hass.data or not hass.data[DOMAIN]:
        _LOGGER.error("服务调用失败：集成尚未完成初始化或没有已配置的网关。")
        return None, None

    for entry_id, data in hass.data[DOMAIN].items():
        if isinstance(data, dict):
            gateway_sn = data.get("gateway_sn", "")
            if gateway_sn and gateway_sn in device_id.split("_"):
                return data, gateway_sn
            
            # 检查是否包含设备SN
            device_manager = data.get("device_manager")
            if device_manager:
                devices = device_manager.get_all_devices()
                id_parts = device_id.split("_")
                for device in devices:
                    device_sn = device.get("sn", "")
                    if device_sn in id_parts:
                        return data, gateway_sn
    
    return None, None


def find_device_by_device_id(hass: Any, device_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[str]]:
    """根据设备ID查找对应的设备和网关
    
    Args:
        hass: Home Assistant实例
        device_id: 设备ID，包含设备SN
        
    Returns:
        Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[str]]: (设备数据, 网关数据, 网关SN) 如果找到，否则 (None, None, None)
    """
    if DOMAIN not in hass.data or not hass.data[DOMAIN]:
        _LOGGER.error("服务调用失败：集成尚未完成初始化或没有已配置的网关。")
        return None, None, None

    for entry_id, data in hass.data[DOMAIN].items():
        if isinstance(data, dict):
            device_manager = data.get("device_manager")
            if device_manager:
                devices = device_manager.get_all_devices()
                id_parts = device_id.split("_")
                for device in devices:
                    device_sn = device.get("sn", "")
                    if device_sn in id_parts:
                        return device, data, data.get("gateway_sn", "")

    return None, None, None


def get_device_gateway_mapping(hass: HomeAssistant, device_sn: str) -> Optional[str]:
    """获取设备关联的网关SN
    
    Args:
        hass: Home Assistant实例
        device_sn: 设备SN
    
    Returns:
        Optional[str]: 网关SN，如果未找到返回None
    """
    try:
        from .const import DEVICE_TO_GATEWAY_MAPPING
        if DOMAIN in hass.data and DEVICE_TO_GATEWAY_MAPPING in hass.data[DOMAIN]:
            device_to_gateway_mapping = hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING]
            if device_sn in device_to_gateway_mapping:
                return device_to_gateway_mapping[device_sn]
    except Exception as e:
        _LOGGER.error("获取设备网关映射失败: %s", e)
    return None