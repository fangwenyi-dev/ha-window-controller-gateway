"""工具模块 - 存放通用辅助函数"""
import logging
from typing import Dict, Any, Optional, Tuple
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class EntityRegistryCacheManager:
    """实体注册表缓存管理器"""
    
    # 类属性，存储单例实例
    _instance = None
    
    def __init__(self):
        """初始化"""
        if not hasattr(self, '_cache'):
            self._cache = {}
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super(EntityRegistryCacheManager, cls).__new__(cls)
        return cls._instance
    
    def get_entity_registry(self, hass: HomeAssistant):
        """获取实体注册表（带缓存）
        
        Args:
            hass: Home Assistant实例
        
        Returns:
            EntityRegistry: 实体注册表
        """
        if hass not in self._cache:
            from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
            self._cache[hass] = async_get_entity_registry(hass)
        return self._cache[hass]
    
    def clear_cache(self, hass: HomeAssistant = None):
        """清理缓存
        
        Args:
            hass: Home Assistant实例，如果为None则清理所有缓存
        """
        if hass is None:
            self._cache.clear()
            _LOGGER.debug("所有实体注册表缓存已清理")
        elif hass in self._cache:
            del self._cache[hass]
            _LOGGER.debug("实体注册表缓存已清理")
    
    def has_cache(self, hass: HomeAssistant) -> bool:
        """检查是否有缓存
        
        Args:
            hass: Home Assistant实例
        
        Returns:
            bool: 是否有缓存
        """
        return hass in self._cache


# 创建全局实例
entity_registry_cache_manager = EntityRegistryCacheManager()


def get_entity_registry(hass: HomeAssistant):
    """获取实体注册表（带缓存）
    
    Args:
        hass: Home Assistant实例
    
    Returns:
        EntityRegistry: 实体注册表
    """
    return entity_registry_cache_manager.get_entity_registry(hass)


def clear_entity_registry_cache(hass: HomeAssistant = None):
    """清理实体注册表缓存
    
    Args:
        hass: Home Assistant实例，如果为None则清理所有缓存
    """
    entity_registry_cache_manager.clear_cache(hass)

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
            if gateway_sn in device_id:
                return data, gateway_sn
            
            # 检查是否包含设备SN
            device_manager = data.get("device_manager")
            if device_manager:
                devices = device_manager.get_all_devices()
                for device in devices:
                    if device.get("sn") in device_id:
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
                for device in devices:
                    if device.get("sn") in device_id:
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