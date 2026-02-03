"""开窗器网关集成"""
import logging
import os
import voluptuous as vol
from datetime import timedelta
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.const import Platform, EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    DOMAIN, 
    CONF_GATEWAY_SN, 
    CONF_GATEWAY_NAME,
    DEFAULT_GATEWAY_NAME,
    SERVICE_START_PAIRING, 
    SERVICE_REFRESH_DEVICES,
    SCAN_INTERVAL
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.COVER, Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR]

async def async_setup(hass: HomeAssistant, config: Dict[str, Any]) -> bool:
    """设置集成 - Home Assistant调用此函数加载集成"""
    _LOGGER.info("开窗器网关集成初始化")
    hass.data.setdefault(DOMAIN, {})
    
    # 图标配置通过icons.json和MDI图标实现，无需静态路径注册

    async def handle_start_pairing(call: ServiceCall) -> None:
        """处理开始配对服务调用"""
        device_id = call.data.get("device_id")
        duration = call.data.get("duration", 60)

        if not device_id:
            _LOGGER.error("开始配对服务调用失败：未指定设备ID")
            return

        _LOGGER.info("收到开始配对请求，设备ID: %s，持续时间: %d秒", device_id, duration)
        
        if DOMAIN not in hass.data or not hass.data[DOMAIN]:
            _LOGGER.error("服务调用失败：集成尚未完成初始化或没有已配置的网关。")
            return

        gateway_found = False
        for entry_id, data in hass.data[DOMAIN].items():
            if isinstance(data, dict) and data.get("gateway_sn", "") in device_id:
                gateway_found = True
                try:
                    await data["mqtt_handler"].start_pairing(duration)
                    _LOGGER.info("已为网关 %s 发起配对", data.get("gateway_sn"))
                except Exception as e:
                    _LOGGER.error("网关 %s 执行配对命令失败: %s", data.get("gateway_sn"), e)
                return

        if not gateway_found:
            _LOGGER.error("未找到设备ID %s 对应的网关", device_id)

    async def handle_refresh_devices(call: ServiceCall) -> None:
        """处理刷新设备服务调用"""
        device_id = call.data.get("device_id")

        if not device_id:
            _LOGGER.error("刷新设备服务调用失败：未指定设备ID")
            return

        if DOMAIN not in hass.data or not hass.data[DOMAIN]:
            _LOGGER.error("服务调用失败：集成尚未完成初始化。")
            return

        for entry_id, data in hass.data[DOMAIN].items():
            if isinstance(data, dict) and data.get("gateway_sn", "") in device_id:
                try:
                    await data["mqtt_handler"].trigger_discovery()
                    _LOGGER.info("已触发网关 %s 的设备发现", data.get("gateway_sn"))
                except Exception as e:
                    _LOGGER.error("网关 %s 触发设备发现失败: %s", data.get("gateway_sn"), e)
                return

        _LOGGER.error("未找到设备ID %s 对应的网关", device_id)

    async def handle_set_position(call: ServiceCall) -> None:
        """处理设置位置服务调用"""
        device_id = call.data.get("device_id")
        position = call.data.get("position")

        if not device_id:
            _LOGGER.error("设置位置服务调用失败：未指定设备ID")
            return

        if position is None:
            _LOGGER.error("设置位置服务调用失败：未指定位置")
            return

        # 加强位置参数验证
        if not isinstance(position, int) or position < 0 or position > 100:
            _LOGGER.error("设置位置服务调用失败：位置必须是0-100之间的整数")
            return

        _LOGGER.info("收到设置位置请求，设备ID: %s，位置: %d", device_id, position)
        
        if DOMAIN not in hass.data or not hass.data[DOMAIN]:
            _LOGGER.error("服务调用失败：集成尚未完成初始化或没有已配置的网关。")
            return

        # 查找对应的设备和网关
        for entry_id, data in hass.data[DOMAIN].items():
            device_manager = data.get("device_manager")
            mqtt_handler = data.get("mqtt_handler")
            
            if device_manager and mqtt_handler:
                # 检查设备是否属于此网关
                devices = device_manager.get_all_devices()
                for device in devices:
                    if device["sn"] in device_id:
                        try:
                            await mqtt_handler.send_command(
                                device["sn"], 
                                "set_position", 
                                {"position": position}
                            )
                            _LOGGER.info("已为设备 %s 设置位置: %d", device["sn"], position)
                            return
                        except Exception as e:
                            _LOGGER.error("设置设备位置失败: %s", e)
                        return

        _LOGGER.error("未找到设备ID %s 对应的设备", device_id)

    async def handle_check_gateway_status(call: ServiceCall) -> None:
        """处理检查网关状态服务调用"""
        device_id = call.data.get("device_id")

        if not device_id:
            _LOGGER.error("检查网关状态服务调用失败：未指定设备ID")
            return

        _LOGGER.info("收到检查网关状态请求，设备ID: %s", device_id)
        
        if DOMAIN not in hass.data or not hass.data[DOMAIN]:
            _LOGGER.error("服务调用失败：集成尚未完成初始化或没有已配置的网关。")
            return

        for entry_id, data in hass.data[DOMAIN].items():
            if isinstance(data, dict) and data.get("gateway_sn", "") in device_id:
                try:
                    is_connected = await data["mqtt_handler"].check_connection()
                    gateway_info = data["device_manager"].get_gateway_info()
                    _LOGGER.info("网关 %s 状态检查结果: 在线=%s, 信息=%s", 
                                gateway_info.get("name"), is_connected, gateway_info)
                    return
                except Exception as e:
                    _LOGGER.error("检查网关状态失败: %s", e)
                return

        _LOGGER.error("未找到设备ID %s 对应的网关", device_id)

    # 注册服务
    try:
        hass.services.async_register(
            DOMAIN,
            SERVICE_START_PAIRING,
            handle_start_pairing,
            schema=vol.Schema({
                vol.Required("device_id"): cv.string,
                vol.Optional("duration", default=60): cv.positive_int,
            })
        )

        hass.services.async_register(
            DOMAIN,
            SERVICE_REFRESH_DEVICES,
            handle_refresh_devices,
            schema=vol.Schema({
                vol.Required("device_id"): cv.string,
            })
        )

        hass.services.async_register(
            DOMAIN,
            "set_position",
            handle_set_position,
            schema=vol.Schema({
                vol.Required("device_id"): cv.string,
                vol.Required("position"): vol.All(cv.positive_int, vol.Range(min=0, max=100)),
            })
        )

        hass.services.async_register(
            DOMAIN,
            "check_gateway_status",
            handle_check_gateway_status,
            schema=vol.Schema({
                vol.Required("device_id"): cv.string,
            })
        )
        _LOGGER.info("开窗器网关服务注册成功")
    except vol.Invalid as e:
        _LOGGER.error("服务参数模式无效: %s", e)
        return False
    except Exception as e:
        _LOGGER.error("注册服务时发生意外错误: %s", e)
        return False

    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """设置配置条目"""
    _LOGGER.info("开始设置配置条目: %s", entry.entry_id)
    
    try:
        from .device_manager import WindowControllerDeviceManager
        from .mqtt_handler import WindowControllerMQTTHandler
    except ImportError as e:
        _LOGGER.critical("导入核心模块失败: %s", e)
        return False

    gateway_sn = entry.data[CONF_GATEWAY_SN]
    gateway_name = entry.data.get(CONF_GATEWAY_NAME, f"{DEFAULT_GATEWAY_NAME} {gateway_sn[-6:]}")
    
    device_manager = None
    mqtt_handler = None
    unsub_listeners = []

    try:
        # 创建设备管理器
        _LOGGER.debug("正在创建设备管理器...")
        device_manager = WindowControllerDeviceManager(hass, entry)
        await device_manager.setup()

        # 创建MQTT处理器
        _LOGGER.debug("正在创建MQTT处理器...")
        mqtt_handler = WindowControllerMQTTHandler(hass, gateway_sn, device_manager)
        await mqtt_handler.setup()

        # 注册网关设备
        _LOGGER.debug("正在注册网关设备实体...")
        await device_manager.register_gateway_device()

        # 获取配置选项
        options = entry.options
        discovery_interval = options.get("discovery_interval", SCAN_INTERVAL)
        auto_discovery = options.get("auto_discovery", True)
        debug_logging = options.get("debug_logging", False)
        
        # 如果启用了调试日志，设置日志级别
        if debug_logging:
            _LOGGER.setLevel(logging.DEBUG)
            _LOGGER.info("调试日志已启用")

        # 设置状态定期更新
        async def periodic_update(_now):
            """定期更新设备状态"""
            try:
                await mqtt_handler.check_connection()
                # 如果启用了自动发现，定期触发设备发现
                if auto_discovery:
                    await mqtt_handler.trigger_discovery()
            except Exception as e:
                _LOGGER.warning("定期连接检查时出错: %s", e)
                # 记录详细的异常信息，便于调试
                _LOGGER.debug("定期连接检查详细错误:", exc_info=True)

        remove_interval = async_track_time_interval(hass, periodic_update, timedelta(seconds=discovery_interval))
        unsub_listeners.append(remove_interval)

        # 存储运行数据
        hass.data[DOMAIN][entry.entry_id] = {
            "gateway_sn": gateway_sn,
            "gateway_name": gateway_name,
            "device_manager": device_manager,
            "mqtt_handler": mqtt_handler,
            "unsub_listeners": unsub_listeners
        }

        # 设置平台
        _LOGGER.debug("正在设置前端平台组件...")
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        # 监听HA停止事件
        async def async_shutdown(event):
            _LOGGER.info("Home Assistant停止，清理网关资源...")
            await async_unload_entry(hass, entry)

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_shutdown)

        _LOGGER.info("开窗器网关 [%s] 设置完成", gateway_name)
        return True

    except Exception as e:
        _LOGGER.error("设置网关 [%s] 过程中失败: %s", gateway_name, e, exc_info=True)
        
        # 清理已创建的资源
        if mqtt_handler:
            await mqtt_handler.cleanup()
        if device_manager and hasattr(device_manager, 'cleanup'):
            await device_manager.cleanup()
        for unsub in unsub_listeners:
            unsub()
            
        if "MQTT" in str(e):
            raise ConfigEntryNotReady(f"MQTT服务不可用: {e}") from e
            
        return False

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载配置条目"""
    entry_id = entry.entry_id
    _LOGGER.info("正在卸载配置条目: %s", entry_id)

    if DOMAIN not in hass.data or entry_id not in hass.data[DOMAIN]:
        _LOGGER.debug("要卸载的条目 %s 未在数据中找到", entry_id)
        return False

    data = hass.data[DOMAIN][entry_id]
    unload_successful = True

    # 停止所有定时任务和监听器
    for unsub in data.get("unsub_listeners", []):
        try:
            unsub()
        except Exception as e:
            _LOGGER.warning("取消监听器时出错: %s", e)
            unload_successful = False

    # 清理MQTT处理器
    try:
        if "mqtt_handler" in data and data["mqtt_handler"]:
            await data["mqtt_handler"].cleanup()
    except Exception as e:
        _LOGGER.error("清理MQTT处理器时出错: %s", e)
        unload_successful = False

    # 清理设备管理器
    try:
        if "device_manager" in data and data["device_manager"]:
            await data["device_manager"].cleanup()
    except Exception as e:
        _LOGGER.error("清理设备管理器时出错: %s", e)
        unload_successful = False

    # 卸载平台
    try:
        await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    except Exception as e:
        _LOGGER.error("卸载平台时出错: %s", e)
        unload_successful = False

    # 从内存中移除条目数据
    if unload_successful:
        hass.data[DOMAIN].pop(entry_id, None)
        _LOGGER.info("配置条目 %s 卸载成功", entry_id)
    else:
        _LOGGER.warning("配置条目 %s 卸载完成，但部分清理操作遇到问题", entry_id)

    return unload_successful

async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """更新配置选项"""
    _LOGGER.info("更新配置选项: %s", entry.entry_id)
    
    # 重新加载配置条目
    await hass.config_entries.async_reload(entry.entry_id)

async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """删除配置条目"""
    gateway_sn = entry.data.get(CONF_GATEWAY_SN, "unknown")
    _LOGGER.info("从配置中永久移除开窗器网关: %s", gateway_sn)