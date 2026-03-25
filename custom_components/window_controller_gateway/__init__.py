"""开窗器网关集成"""
import logging
import os
import re
import asyncio
import json
import voluptuous as vol
from datetime import timedelta
from typing import Any, Dict, Optional, Tuple

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
    SERVICE_MIGRATE_DEVICES,
    SCAN_INTERVAL,
    DEVICE_TO_GATEWAY_MAPPING,
    DEVICE_TO_GATEWAY_MAPPING_FILE,
    GLOBAL_MANUALLY_REMOVED_DEVICES,
    RESTART_DELAY,
    GATEWAY_PAIRING_TIMEOUT,
    POSITION_MIN,
    POSITION_MAX
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.COVER, Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR]

DISCOVERY_PLATFORM = "window_controller_gateway"

PERSISTENT_DATA_FILE = "window_controller_gateway_data.json"

async def _load_persistent_data(hass: HomeAssistant) -> None:
    """加载持久化的设备映射和手动删除列表"""
    try:
        config_dir = hass.config.config_dir
        data_file = os.path.join(config_dir, PERSISTENT_DATA_FILE)
        
        if os.path.exists(data_file):
            def _read_file():
                with open(data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            
            data = await hass.async_add_executor_job(_read_file)
            
            if 'device_to_gateway_mapping' in data:
                mapping = data['device_to_gateway_mapping']
                hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING] = mapping
                _LOGGER.info("已加载设备到网关映射表，共 %d 个设备", len(mapping))
            
            if 'manually_removed_devices' in data:
                removed_set = set(data['manually_removed_devices'])
                hass.data[DOMAIN][GLOBAL_MANUALLY_REMOVED_DEVICES] = removed_set
                _LOGGER.info("已加载手动删除设备列表，共 %d 个设备", len(removed_set))
                
    except Exception as e:
        _LOGGER.info("加载持久化数据失败: %s", e)

async def _save_persistent_data(hass: HomeAssistant) -> None:
    """保存设备映射和手动删除列表到持久化存储"""
    try:
        config_dir = hass.config.config_dir
        data_file = os.path.join(config_dir, PERSISTENT_DATA_FILE)
        
        data = {
            'device_to_gateway_mapping': hass.data[DOMAIN].get(DEVICE_TO_GATEWAY_MAPPING, {}),
            'manually_removed_devices': list(hass.data[DOMAIN].get(GLOBAL_MANUALLY_REMOVED_DEVICES, set()))
        }
        
        def _write_file():
            with open(data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        
        await hass.async_add_executor_job(_write_file)
        
        _LOGGER.debug("已保存持久化数据")
        
    except Exception as e:
        _LOGGER.error("保存持久化数据失败: %s", e)

async def _cleanup_duplicate_entities(hass: HomeAssistant, entry: ConfigEntry):
    """清理重复实体
    
    清理可能存在的旧格式实体（包含entry_id的实体）
    
    Args:
        hass: Home Assistant实例
        entry: 配置条目
    """
    from homeassistant.helpers.entity_registry import async_get
    
    gateway_sn = entry.data[CONF_GATEWAY_SN]
    entry_id = str(entry.entry_id)
    
    entity_registry = async_get(hass)
    entities_to_remove = []
    
    for entity_id, entity_entry in entity_registry.entities.items():
        if entity_entry.platform == DOMAIN:
            if entity_entry.unique_id:
                if entry_id in entity_entry.unique_id:
                    _LOGGER.info("发现旧格式实体（包含entry_id），准备删除: %s (唯一ID: %s)", entity_id, entity_entry.unique_id)
                    entities_to_remove.append(entity_id)
    
    for entity_id in entities_to_remove:
        try:
            entity_registry.async_remove(entity_id)
            _LOGGER.info("已删除旧格式实体: %s", entity_id)
        except Exception as e:
            _LOGGER.error("删除旧格式实体失败 %s: %s", entity_id, e)
    
    if entities_to_remove:
        _LOGGER.info("共删除 %d 个旧格式实体", len(entities_to_remove))

async def async_setup(hass: HomeAssistant, config: Dict[str, Any]) -> bool:
    """设置集成 - Home Assistant调用此函数加载集成"""
    _LOGGER.info("=== 开窗器网关集成初始化 ===")
    hass.data.setdefault(DOMAIN, {})
    
    from .const import DEVICE_TO_GATEWAY_MAPPING, GLOBAL_MANUALLY_REMOVED_DEVICES
    hass.data[DOMAIN].setdefault(DEVICE_TO_GATEWAY_MAPPING, {})
    hass.data[DOMAIN].setdefault(GLOBAL_MANUALLY_REMOVED_DEVICES, set())
    
    await _load_persistent_data(hass)
    
    try:
        from .discovery import async_setup_discovery_platform
        await async_setup_discovery_platform(hass)
        _LOGGER.info("开窗器网关发现平台设置成功")
    except Exception as e:
        _LOGGER.error("设置开窗器网关发现平台失败: %s", e)
    
    try:
        from homeassistant.helpers import discovery
        _LOGGER.info("开窗器网关发现平台注册成功")
    except Exception as e:
        _LOGGER.error("注册开窗器网关发现平台失败: %s", e)
    
    from .utils import find_gateway_by_device_id, find_device_by_device_id

    async def handle_start_pairing(call: ServiceCall) -> None:
        """处理开始配对服务调用"""
        device_id = call.data.get("device_id")
        duration = call.data.get("duration", GATEWAY_PAIRING_TIMEOUT)

        if not device_id:
            _LOGGER.error("开始配对服务调用失败：未指定设备ID")
            return

        _LOGGER.info("收到开始配对请求，设备ID: %s，持续时间: %d秒", device_id, duration)
        
        gateway_data, gateway_sn = find_gateway_by_device_id(hass, device_id)
        if not gateway_data:
            _LOGGER.error("未找到设备ID %s 对应的网关", device_id)
            return

        try:
            await gateway_data["mqtt_handler"].start_pairing(duration)
            _LOGGER.info("已为网关 %s 发起配对", gateway_sn)
        except (ConnectionError, TimeoutError) as e:
            _LOGGER.error("网关 %s 连接或超时错误: %s", gateway_sn, e)
        except (KeyError, AttributeError) as e:
            _LOGGER.error("网关 %s MQTT处理器未找到或配置错误: %s", gateway_sn, e)
        except Exception as e:
            _LOGGER.error("网关 %s 执行配对命令失败: %s", gateway_sn, e)

    async def handle_refresh_devices(call: ServiceCall) -> None:
        """处理刷新设备服务调用 - 优化版，减少阻塞"""
        device_id = call.data.get("device_id")

        if not device_id:
            _LOGGER.error("刷新设备服务调用失败：未指定设备ID")
            return

        gateway_data, gateway_sn = find_gateway_by_device_id(hass, device_id)
        if not gateway_data:
            _LOGGER.error("未找到设备ID %s 对应的网关", device_id)
            return

        async def refresh_devices_async():
            try:
                await gateway_data["mqtt_handler"].trigger_discovery()
                _LOGGER.info("已触发网关 %s 的设备发现", gateway_sn)
            except (ConnectionError, TimeoutError) as e:
                _LOGGER.error("网关 %s 连接或超时错误: %s", gateway_sn, e)
            except (KeyError, AttributeError) as e:
                _LOGGER.error("网关 %s MQTT处理器未找到或配置错误: %s", gateway_sn, e)
            except Exception as e:
                _LOGGER.error("网关 %s 触发设备发现失败: %s", gateway_sn, e)
        
        hass.create_task(refresh_devices_async())
        _LOGGER.info("刷新设备服务调用已提交，设备ID: %s", device_id)

    async def handle_set_position(call: ServiceCall) -> None:
        """处理设置位置服务调用 - 优化版，减少阻塞"""
        device_id = call.data.get("device_id")
        position = call.data.get("position")

        if not device_id:
            _LOGGER.error("设置位置服务调用失败：未指定设备ID")
            return

        if position is None:
            _LOGGER.error("设置位置服务调用失败：未指定位置")
            return

        if not isinstance(position, int) or position < 0 or position > 100:
            _LOGGER.error("设置位置服务调用失败：位置必须是0-100之间的整数")
            return

        _LOGGER.info("收到设置位置请求，设备ID: %s，位置: %d", device_id, position)
        
        device, gateway_data, gateway_sn = find_device_by_device_id(hass, device_id)
        if not device or not gateway_data:
            _LOGGER.error("未找到设备ID %s 对应的设备", device_id)
            return

        mqtt_handler = gateway_data.get("mqtt_handler")
        if not mqtt_handler:
            _LOGGER.error("未找到MQTT处理器")
            return

        async def set_position_async():
            try:
                await mqtt_handler.send_command(
                    device["sn"], 
                    "set_position", 
                    {"position": position}
                )
                _LOGGER.info("已为设备 %s 设置位置: %d", device["sn"], position)
            except (ConnectionError, TimeoutError) as e:
                _LOGGER.error("设备 %s 连接或超时错误: %s", device["sn"], e)
            except (KeyError, AttributeError) as e:
                _LOGGER.error("设备 %s MQTT处理器配置错误: %s", device["sn"], e)
            except Exception as e:
                _LOGGER.error("设置设备位置失败: %s", e)
        
        hass.create_task(set_position_async())
        _LOGGER.info("设置位置服务调用已提交，设备ID: %s，位置: %d", device_id, position)

    async def handle_check_gateway_status(call: ServiceCall) -> None:
        """处理检查网关状态服务调用"""
        device_id = call.data.get("device_id")

        if not device_id:
            _LOGGER.error("检查网关状态服务调用失败：未指定设备ID")
            return

        _LOGGER.info("收到检查网关状态请求，设备ID: %s", device_id)
        
        gateway_data, gateway_sn = find_gateway_by_device_id(hass, device_id)
        if not gateway_data:
            _LOGGER.error("未找到设备ID %s 对应的网关", device_id)
            return

        try:
            is_connected = await gateway_data["mqtt_handler"].check_connection()
            gateway_info = gateway_data["device_manager"].get_gateway_info()
            _LOGGER.info("网关 %s 状态检查结果: 在线=%s, 信息=%s", 
                        gateway_info.get("name"), is_connected, gateway_info)
        except (ConnectionError, TimeoutError) as e:
            _LOGGER.error("网关 %s 连接或超时错误: %s", gateway_sn, e)
        except (KeyError, AttributeError) as e:
            _LOGGER.error("网关 %s 配置错误: %s", gateway_sn, e)
        except Exception as e:
            _LOGGER.error("检查网关状态失败: %s", e)

    async def handle_migrate_devices(call: ServiceCall) -> None:
        """完善的设备迁移服务"""
        old_gateway_sn = call.data.get("old_gateway_sn")
        new_gateway_sn = call.data.get("new_gateway_sn")
        remove_old_gateway = call.data.get("remove_old_gateway", False)

        if not isinstance(old_gateway_sn, str) or len(old_gateway_sn) < 10:
            _LOGGER.error("旧网关SN格式无效: %s", old_gateway_sn)
            return
        
        if not isinstance(new_gateway_sn, str) or len(new_gateway_sn) < 10:
            _LOGGER.error("新网关SN格式无效: %s", new_gateway_sn)
            return
        
        if not re.match(r'^[a-fA-F0-9]+$', old_gateway_sn):
            _LOGGER.error("旧网关SN必须只包含字母和数字: %s", old_gateway_sn)
            return
        
        if not re.match(r'^[a-fA-F0-9]+$', new_gateway_sn):
            _LOGGER.error("新网关SN必须只包含字母和数字: %s", new_gateway_sn)
            return
        
        if not isinstance(remove_old_gateway, bool):
            _LOGGER.error("remove_old_gateway参数必须是布尔值: %s", remove_old_gateway)
            return

        if old_gateway_sn == new_gateway_sn:
            _LOGGER.error("新旧网关不能相同: %s", old_gateway_sn)
            return

        _LOGGER.info("开始设备迁移，新网关: %s, 旧网关: %s", new_gateway_sn, old_gateway_sn)

        def find_gateway_entry(gateway_sn):
            for entry in hass.config_entries.async_entries(DOMAIN):
                if CONF_GATEWAY_SN in entry.data and entry.data[CONF_GATEWAY_SN] == gateway_sn:
                    return entry
            return None

        old_gateway_entry = find_gateway_entry(old_gateway_sn)
        new_gateway_entry = find_gateway_entry(new_gateway_sn)

        if not old_gateway_entry or not new_gateway_entry:
            _LOGGER.error("网关不存在，旧网关: %s, 新网关: %s", old_gateway_entry, new_gateway_entry)
            return

        _LOGGER.info("找到网关条目，旧网关: %s, 新网关: %s", old_gateway_entry.entry_id, new_gateway_entry.entry_id)

        old_manager = None
        new_manager = None

        if old_gateway_entry.entry_id in hass.data[DOMAIN]:
            old_manager = hass.data[DOMAIN][old_gateway_entry.entry_id].get("device_manager")

        if new_gateway_entry.entry_id in hass.data[DOMAIN]:
            new_manager = hass.data[DOMAIN][new_gateway_entry.entry_id].get("device_manager")

        if not old_manager or not new_manager:
            _LOGGER.error("设备管理器不存在")
            return

        try:
            hass.bus.async_fire(
                f"{DOMAIN}_migration_progress",
                {
                    "old_gateway_sn": old_gateway_sn,
                    "new_gateway_sn": new_gateway_sn,
                    "status": "started",
                    "progress": 0,
                    "message": "开始设备迁移"
                }
            )
            
            success, migrated_devices = await new_manager.safe_migrate_devices(
                old_gateway_sn,
                new_gateway_sn,
                delete_old_devices=True
            )

            if success:
                hass.bus.async_fire(
                    f"{DOMAIN}_migration_progress",
                    {
                        "old_gateway_sn": old_gateway_sn,
                        "new_gateway_sn": new_gateway_sn,
                        "status": "devices_migrated",
                        "progress": 50,
                        "message": "设备迁移完成，开始验证实体"
                    }
                )
                
                _LOGGER.info("设备迁移成功")

        except Exception as e:
            _LOGGER.error("设备迁移失败: %s", e)
            hass.bus.async_fire(
                f"{DOMAIN}_migration_progress",
                {
                    "old_gateway_sn": old_gateway_sn,
                    "new_gateway_sn": new_gateway_sn,
                    "status": "failed",
                    "progress": 0,
                    "message": f"设备迁移失败: {e}"
                }
            )

    async def handle_query_device_status(call: ServiceCall) -> None:
        """处理查询设备状态服务调用"""
        device_id = call.data.get("device_id")

        if not device_id:
            _LOGGER.error("查询设备状态服务调用失败：未指定设备ID")
            return

        _LOGGER.info("收到查询设备状态请求，设备ID: %s", device_id)
        
        device, gateway_data, gateway_sn = find_device_by_device_id(hass, device_id)
        if not device or not gateway_data:
            _LOGGER.error("未找到设备ID %s 对应的设备", device_id)
            return

        mqtt_handler = gateway_data.get("mqtt_handler")
        if not mqtt_handler:
            _LOGGER.error("未找到MQTT处理器")
            return

        async def query_status_async():
            try:
                await mqtt_handler.send_command(device["sn"], "status")
                _LOGGER.info("已发送设备 %s 状态查询命令", device["sn"])
            except Exception as e:
                _LOGGER.error("查询设备 %s 状态失败: %s", device["sn"], e)
        
        hass.create_task(query_status_async())
        _LOGGER.info("查询设备状态服务调用已提交，设备ID: %s", device_id)

    if not hass.services.has_service(DOMAIN, SERVICE_START_PAIRING):
        hass.services.async_register(
            DOMAIN, SERVICE_START_PAIRING, handle_start_pairing,
            schema=vol.Schema({
                vol.Required("device_id"): cv.string,
                vol.Optional("duration", default=GATEWAY_PAIRING_TIMEOUT): cv.positive_int
            })
        )
    
    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH_DEVICES):
        hass.services.async_register(
            DOMAIN, SERVICE_REFRESH_DEVICES, handle_refresh_devices,
            schema=vol.Schema({
                vol.Required("device_id"): cv.string
            })
        )
    
    if not hass.services.has_service(DOMAIN, "set_position"):
        hass.services.async_register(
            DOMAIN, "set_position", handle_set_position,
            schema=vol.Schema({
                vol.Required("device_id"): cv.string,
                vol.Required("position"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100))
            })
        )
    
    if not hass.services.has_service(DOMAIN, "check_gateway_status"):
        hass.services.async_register(
            DOMAIN, "check_gateway_status", handle_check_gateway_status,
            schema=vol.Schema({
                vol.Required("device_id"): cv.string
            })
        )
    
    if not hass.services.has_service(DOMAIN, SERVICE_MIGRATE_DEVICES):
        hass.services.async_register(
            DOMAIN, SERVICE_MIGRATE_DEVICES, handle_migrate_devices,
            schema=vol.Schema({
                vol.Required("old_gateway_sn"): cv.string,
                vol.Required("new_gateway_sn"): cv.string,
                vol.Optional("remove_old_gateway", default=False): cv.boolean
            })
        )

    if not hass.services.has_service(DOMAIN, "query_device_status"):
        hass.services.async_register(
            DOMAIN, "query_device_status", handle_query_device_status,
            schema=vol.Schema({
                vol.Required("device_id"): cv.string
            })
        )

    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """设置配置条目 - Home Assistant调用此函数加载配置条目"""
    _LOGGER.info("=== 开窗器网关配置条目加载 ===")
    
    gateway_sn = entry.data[CONF_GATEWAY_SN]
    gateway_name = entry.data.get(CONF_GATEWAY_NAME, DEFAULT_GATEWAY_NAME)
    
    _LOGGER.info("加载网关: %s (SN: %s)", gateway_name, gateway_sn)
    
    from .mqtt_handler import MqttHandler
    from .device_manager import DeviceManager
    from .gateway import Gateway
    
    device_manager = DeviceManager(hass, entry, gateway_sn, gateway_name)
    mqtt_handler = MqttHandler(hass, gateway_sn, device_manager)
    
    try:
        await mqtt_handler.init()
        _LOGGER.info("MQTT处理器初始化成功")
    except Exception as e:
        _LOGGER.error("MQTT处理器初始化失败: %s", e)
        raise ConfigEntryNotReady from e
    
    try:
        await device_manager.init()
        _LOGGER.info("设备管理器初始化成功")
    except Exception as e:
        _LOGGER.error("设备管理器初始化失败: %s", e)
    
    unsub_listeners = []
    
    unsub_listeners.append(entry.add_update_listener(_async_update_listener))
    
    async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
        """配置条目更新监听器"""
        _LOGGER.info("检测到配置条目更新: %s", entry.entry_id)
        
        new_gateway_name = entry.data.get(CONF_GATEWAY_NAME, DEFAULT_GATEWAY_NAME)
        
        if entry.data.get(CONF_GATEWAY_SN) != gateway_sn:
            _LOGGER.warning("网关SN不能更改，需要重新配置")
            return
        
        await device_manager.update_gateway_name(new_gateway_name)
        
        _LOGGER.info("配置条目更新完成")
    
    for platform in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, platform)
        )
    
    def cleanup(event):
        """清理函数 - 在配置条目卸载或HA关闭时调用"""
        _LOGGER.info("执行清理函数")
        
        for unsub in unsub_listeners:
            try:
                unsub()
            except Exception as e:
                _LOGGER.error("取消订阅失败: %s", e)
        
        try:
            mqtt_handler.cleanup()
        except Exception as e:
            _LOGGER.error("MQTT处理器清理失败: %s", e)
    
    unsub_listeners.append(hass.bus.async_listen(EVENT_HOMEASSISTANT_STOP, cleanup))
    
    options = entry.options
    discovery_interval = options.get("discovery_interval", SCAN_INTERVAL)
    auto_discovery = options.get("auto_discovery", True)
    debug_logging = options.get("debug_logging", False)
    
    if debug_logging:
        _LOGGER.setLevel(logging.DEBUG)
        _LOGGER.info("调试日志已启用")

    async def periodic_update(_now):
        """定期检查连接状态"""
        try:
            await mqtt_handler.check_connection()
        except Exception as e:
            _LOGGER.warning("定期连接检查时出错: %s", e)

    remove_interval = async_track_time_interval(hass, periodic_update, timedelta(seconds=discovery_interval))
    unsub_listeners.append(remove_interval)

    hass.data[DOMAIN][entry.entry_id] = {
        "gateway_sn": gateway_sn,
        "gateway_name": gateway_name,
        "device_manager": device_manager,
        "mqtt_handler": mqtt_handler,
        "unsub_listeners": unsub_listeners,
        "_setup_complete": True
    }

    _LOGGER.debug("正在设置前端平台组件...")
    
    await asyncio.sleep(RESTART_DELAY)
    
    try:
        await mqtt_handler.trigger_discovery()
    except Exception as e:
        _LOGGER.warning("初始设备发现失败（可忽略）: %s", e)
    
    try:
        await device_manager.async_start()
    except Exception as e:
        _LOGGER.warning("设备管理器启动失败（可忽略）: %s", e)
    
    _LOGGER.info("=== 开窗器网关配置条目加载完成 ===")
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载配置条目"""
    _LOGGER.info("=== 开窗器网关配置条目卸载 ===")
    
    gateway_data = hass.data[DOMAIN].get(entry.entry_id)
    
    if not gateway_data:
        _LOGGER.warning("未找到网关数据")
        return False
    
    unsub_listeners = gateway_data.get("unsub_listeners", [])
    
    for unsub in unsub_listeners:
        try:
            unsub()
        except Exception as e:
            _LOGGER.error("取消订阅失败: %s", e)
    
    mqtt_handler = gateway_data.get("mqtt_handler")
    if mqtt_handler:
        try:
            mqtt_handler.cleanup()
        except Exception as e:
            _LOGGER.error("MQTT处理器清理失败: %s", e)
    
    device_manager = gateway_data.get("device_manager")
    if device_manager:
        try:
            await device_manager.async_stop()
        except Exception as e:
            _LOGGER.error("设备管理器停止失败: %s", e)
    
    unload_tasks = []
    for platform in PLATFORMS:
        unload_tasks.append(hass.config_entries.async_forward_entry_unload(entry, platform))
    
    results = await asyncio.gather(*unload_tasks, return_exceptions=True)
    
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            _LOGGER.error("卸载平台 %s 失败: %s", PLATFORMS[i], result)
    
    hass.data[DOMAIN].pop(entry.entry_id, None)
    
    _LOGGER.info("=== 开窗器网关配置条目卸载完成 ===")
    
    return True

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """重新加载配置条目"""
    _LOGGER.info("=== 开窗器网关配置条目重载 ===")
    
    await async_unload_entry(hass, entry)
    
    await async_setup_entry(hass, entry)
    
    _LOGGER.info("=== 开窗器网关配置条目重载完成 ===")
