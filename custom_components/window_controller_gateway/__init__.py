"""开窗器网关集成"""
import logging
import os
import re
import asyncio
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
    RESTART_DELAY
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.COVER, Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR]

# 发现平台名称
DISCOVERY_PLATFORM = "window_controller_gateway"

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
    
    # 查找所有可能的重复实体
    for entity_id, entity_entry in entity_registry.entities.items():
        if entity_entry.platform == DOMAIN:
            # 检查实体是否属于当前网关
            if entity_entry.unique_id:
                # 如果实体ID包含entry_id，则是旧格式实体（需要删除）
                # 新格式不包含entry_id，只基于设备SN或网关SN
                if entry_id in entity_entry.unique_id:
                    _LOGGER.info("发现旧格式实体（包含entry_id），准备删除: %s (唯一ID: %s)", entity_id, entity_entry.unique_id)
                    entities_to_remove.append(entity_id)
    
    # 删除重复实体
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
    _LOGGER.info("开窗器网关集成初始化")
    hass.data.setdefault(DOMAIN, {})
    
    # 设置发现平台
    try:
        from .discovery import async_setup_discovery_platform
        await async_setup_discovery_platform(hass)
        _LOGGER.info("开窗器网关发现平台设置成功")
    except Exception as e:
        _LOGGER.error("设置开窗器网关发现平台失败: %s", e)
    
    # 注册发现平台处理函数
    try:
        from homeassistant.helpers import discovery
        
        # 确保集成能够处理发现流程
        _LOGGER.info("开窗器网关发现平台注册成功")
    except Exception as e:
        _LOGGER.error("注册开窗器网关发现平台失败: %s", e)
    
    # 导入辅助函数
    from .utils import find_gateway_by_device_id, find_device_by_device_id

    async def handle_start_pairing(call: ServiceCall) -> None:
        """处理开始配对服务调用"""
        device_id = call.data.get("device_id")
        duration = call.data.get("duration", 60)

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

        # 使用异步任务执行，减少阻塞
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
        
        # 创建异步任务，立即返回
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

        # 加强位置参数验证
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

        # 使用异步任务执行，减少阻塞
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
        
        # 创建异步任务，立即返回
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
        old_gateway_sn = call.data.get("old_gateway_sn")  # 旧网关SN
        new_gateway_sn = call.data.get("new_gateway_sn")  # 新网关SN
        remove_old_gateway = call.data.get("remove_old_gateway", False)  # 是否移除旧网关

        # 添加更严格的参数验证
        if not isinstance(old_gateway_sn, str) or len(old_gateway_sn) < 10:
            _LOGGER.error("旧网关SN格式无效: %s", old_gateway_sn)
            return
        
        if not isinstance(new_gateway_sn, str) or len(new_gateway_sn) < 10:
            _LOGGER.error("新网关SN格式无效: %s", new_gateway_sn)
            return
        
        # 修改验证逻辑：允许字母和数字（十六进制格式）
        if not re.match(r'^[a-fA-F0-9]+$', old_gateway_sn):
            _LOGGER.error("旧网关SN必须只包含字母和数字: %s", old_gateway_sn)
            return
        
        if not re.match(r'^[a-fA-F0-9]+$', new_gateway_sn):
            _LOGGER.error("新网关SN必须只包含字母和数字: %s", new_gateway_sn)
            return
        
        if not isinstance(remove_old_gateway, bool):
            _LOGGER.error("remove_old_gateway参数必须是布尔值: %s", remove_old_gateway)
            return

        # 检查新旧网关是否相同
        if old_gateway_sn == new_gateway_sn:
            _LOGGER.error("新旧网关不能相同: %s", old_gateway_sn)
            return

        _LOGGER.info("开始设备迁移，新网关: %s, 旧网关: %s", new_gateway_sn, old_gateway_sn)

        # 1. 验证网关存在
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

        # 2. 获取设备管理器
        old_manager = None
        new_manager = None

        if old_gateway_entry.entry_id in hass.data[DOMAIN]:
            old_manager = hass.data[DOMAIN][old_gateway_entry.entry_id].get("device_manager")

        if new_gateway_entry.entry_id in hass.data[DOMAIN]:
            new_manager = hass.data[DOMAIN][new_gateway_entry.entry_id].get("device_manager")

        if not old_manager or not new_manager:
            _LOGGER.error("设备管理器不存在")
            return

        # 3. 执行迁移
        try:
            # 发送迁移开始事件
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
            
            # 使用安全迁移方法，支持旧网关不在线的情况
            success, migrated_devices = await new_manager.safe_migrate_devices(
                old_gateway_sn,
                new_gateway_sn,
                delete_old_devices=True  # 从旧网关删除设备
            )

            if success:
                # 发送迁移完成事件
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
                
                # # 4. 验证实体迁移（改为可选，不阻塞主流程）
                # try:
                #     migration_verified = await new_manager._verify_entity_migration(
                #         old_gateway_sn,
                #         new_gateway_sn
                #     )
                #     if migration_verified:
                #         _LOGGER.info("实体迁移验证成功")
                #         # 发送验证成功事件
                #         hass.bus.async_fire(
                #             f"{DOMAIN}_migration_progress",
                #             {
                #                 "old_gateway_sn": old_gateway_sn,
                #                 "new_gateway_sn": new_gateway_sn,
                #                 "status": "verified",
                #                 "progress": 75,
                #                 "message": "实体迁移验证成功"
                #             }
                #         )
                #     else:
                #         _LOGGER.warning("实体迁移验证失败，但设备已迁移")
                #         # 发送验证失败事件
                #         hass.bus.async_fire(
                #             f"{DOMAIN}_migration_progress",
                #             {
                #                 "old_gateway_sn": old_gateway_sn,
                #                 "new_gateway_sn": new_gateway_sn,
                #                 "status": "verification_failed",
                #                 "progress": 75,
                #                 "message": "实体迁移验证失败，但设备已迁移"
                #             }
                #         )
                # except Exception as verify_error:
                #     _LOGGER.error("验证实体迁移失败，但不影响迁移结果: %s", verify_error)
                #     # 发送验证错误事件
                #     hass.bus.async_fire(
                #         f"{DOMAIN}_migration_progress",
                #         {
                #             "old_gateway_sn": old_gateway_sn,
                #             "new_gateway_sn": new_gateway_sn,
                #             "status": "verification_error",
                #             "progress": 75,
                #             "message": f"验证实体迁移失败: {verify_error}"
                #         }
                #     )
                
                # 直接发送迁移成功事件
                hass.bus.async_fire(
                    f"{DOMAIN}_migration_progress",
                    {
                        "old_gateway_sn": old_gateway_sn,
                        "new_gateway_sn": new_gateway_sn,
                        "status": "verified",
                        "progress": 75,
                        "message": "设备迁移完成"
                    }
                )
                
                # 5. 不再重新加载平台，而是发送事件让前端刷新
                try:
                    _LOGGER.info("发送迁移完成事件，通知前端刷新")
                    
                    # 发送事件通知前端刷新
                    hass.bus.async_fire(
                        f"{DOMAIN}_devices_migrated",
                        {
                            "old_gateway_sn": old_gateway_sn,
                            "new_gateway_sn": new_gateway_sn,
                            "success": True,
                            "device_count": len(migrated_devices) if 'migrated_devices' in locals() else 0
                        }
                    )
                    
                    # 同时发送一个通用的Home Assistant事件，触发UI刷新
                    hass.bus.async_fire(
                        "homeassistant/reload_entities",
                        {
                            "domain": DOMAIN,
                            "entry_id": new_gateway_entry.entry_id
                        }
                    )
                    
                    _LOGGER.info("已通知前端刷新，用户可能需要手动刷新页面或等待自动更新")
                    
                except Exception as reload_error:
                    _LOGGER.error("发送刷新事件失败: %s", reload_error)

                # 6. 可选：卸载旧网关
                if remove_old_gateway:
                    try:
                        _LOGGER.info("移除旧网关: %s", old_gateway_entry.entry_id)
                        # 发送移除旧网关事件
                        hass.bus.async_fire(
                            f"{DOMAIN}_migration_progress",
                            {
                                "old_gateway_sn": old_gateway_sn,
                                "new_gateway_sn": new_gateway_sn,
                                "status": "removing_old_gateway",
                                "progress": 95,
                                "message": "正在移除旧网关"
                            }
                        )
                        
                        await hass.config_entries.async_remove(old_gateway_entry.entry_id)
                        _LOGGER.info("旧网关移除成功")
                    except Exception as remove_error:
                        _LOGGER.error("移除旧网关失败: %s", remove_error)
                
                # 发送迁移完成事件
                hass.bus.async_fire(
                    f"{DOMAIN}_migration_progress",
                    {
                        "old_gateway_sn": old_gateway_sn,
                        "new_gateway_sn": new_gateway_sn,
                        "status": "completed",
                        "progress": 100,
                        "message": "迁移完成"
                    }
                )
                
                # 重新加载新网关的平台，确保实体正确显示
                try:
                    _LOGGER.info("重新加载新网关 %s 的平台", new_gateway_sn)
                    await hass.config_entries.async_reload(new_gateway_entry.entry_id)
                    _LOGGER.info("新网关平台重新加载完成")
                except Exception as reload_error:
                    _LOGGER.error("重新加载新网关平台失败: %s", reload_error)
                        
        except Exception as e:
            _LOGGER.error("迁移失败: %s", e)
            import traceback
            _LOGGER.error("详细错误信息: %s", traceback.format_exc())
            # 发送错误通知
            hass.bus.async_fire(
                f"{DOMAIN}_migration_failed",
                {
                    "old_gateway_sn": old_gateway_sn,
                    "new_gateway_sn": new_gateway_sn,
                    "error": str(e)
                }
            )
            # 发送迁移失败事件
            hass.bus.async_fire(
                f"{DOMAIN}_migration_progress",
                {
                    "old_gateway_sn": old_gateway_sn,
                    "new_gateway_sn": new_gateway_sn,
                    "status": "failed",
                    "progress": 0,
                    "message": f"迁移失败: {str(e)}"
                }
            )

    async def _safe_reload_platforms(hass: HomeAssistant, config_entry):
        """安全地重新加载平台"""
        if not isinstance(config_entry, ConfigEntry):
            _LOGGER.error("config_entry 不是 ConfigEntry 类型")
            return
        
        # 使用本地定义的PLATFORMS变量（使用Home Assistant的Platform枚举）
        for platform in PLATFORMS:
            try:
                _LOGGER.debug("重新加载平台: %s", platform)
                
                # 检查方法是否存在
                if hasattr(hass.config_entries, 'async_forward_entry_unload'):
                    try:
                        await hass.config_entries.async_forward_entry_unload(config_entry, platform)
                        _LOGGER.debug("平台 %s 卸载成功", platform)
                    except Exception as unload_error:
                        _LOGGER.warning("卸载平台 %s 失败: %s", platform, unload_error)
                
                if hasattr(hass.config_entries, 'async_forward_entry_setup'):
                    try:
                        await hass.config_entries.async_forward_entry_setup(config_entry, platform)
                        _LOGGER.debug("平台 %s 重新加载成功", platform)
                    except AttributeError as e:
                        _LOGGER.error("async_forward_entry_setup 调用失败: %s", e)
                        # 尝试使用备用方法
                        await _alternative_setup_platform(hass, config_entry, platform)
                else:
                    # 如果没有async_forward_entry_setup方法，使用备用方法
                    await _alternative_setup_platform(hass, config_entry, platform)
                    
            except Exception as e:
                _LOGGER.error("重新加载平台 %s 时发生错误: %s", platform, e)

    async def _alternative_setup_platform(hass: HomeAssistant, config_entry, platform):
        """备用平台设置方法"""
        try:
            # 手动触发平台设置
            from . import cover, button, sensor, binary_sensor
            
            setup_functions = {
                "cover": cover.async_setup_entry,
                "button": button.async_setup_entry,
                "sensor": sensor.async_setup_entry,
                "binary_sensor": binary_sensor.async_setup_entry
            }
            
            if platform in setup_functions:
                async_add_entities = lambda entities: None  # 占位符
                await setup_functions[platform](hass, config_entry, async_add_entities)
                _LOGGER.info("平台 %s 设置成功（备用方法）", platform)
                
        except Exception as e:
            _LOGGER.error("备用平台设置方法失败: %s", e)

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

        hass.services.async_register(
            DOMAIN,
            SERVICE_MIGRATE_DEVICES,
            handle_migrate_devices,
            schema=vol.Schema({
                vol.Required("old_gateway_sn"): cv.string,
                vol.Required("new_gateway_sn"): cv.string,
                vol.Optional("remove_old_gateway", default=False): cv.boolean,
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
    gateway_name = entry.data.get(CONF_GATEWAY_NAME, f"{DEFAULT_GATEWAY_NAME} {gateway_sn[-4:]}")
    
    device_manager = None
    mqtt_handler = None
    unsub_listeners = []

    try:
        # 创建设备管理器
        _LOGGER.debug("正在创建设备管理器...")
        device_manager = WindowControllerDeviceManager(hass, entry)

        # 快速注册网关设备（立即返回，给用户即时反馈）
        _LOGGER.debug("正在注册网关设备实体...")
        await device_manager.register_gateway_device()

        # 创建MQTT处理器（快速初始化，不等待连接）
        _LOGGER.debug("正在创建MQTT处理器...")
        mqtt_handler = WindowControllerMQTTHandler(hass, gateway_sn, device_manager)
        await mqtt_handler.setup()

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

        # 设置平台（快速返回，不等待实体创建完成）
        _LOGGER.debug("正在设置前端平台组件...")
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        # 清理重复实体（在设置完成后执行）
        await _cleanup_duplicate_entities(hass, entry)

        # 监听HA停止事件
        async def async_shutdown(event):
            _LOGGER.info("Home Assistant停止，清理网关资源...")
            await async_unload_entry(hass, entry)

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_shutdown)

        # 创建后台任务，延迟加载设备和触发发现
        async def background_initialization():
            """后台初始化任务，不阻塞主流程"""
            try:
                # 延迟加载已存在的设备（此时网关已注册，子设备可以正确关联）
                _LOGGER.debug("后台任务：正在加载已存在的设备...")
                await device_manager.setup()

                # 使用快速设备发现，提升设备显示速度
                _LOGGER.debug("后台任务：正在触发快速设备发现...")
                await mqtt_handler.fast_discovery()

                # 等待设备发现完成，确保设备关联正确
                _LOGGER.debug("后台任务：等待设备发现完成...")
                await asyncio.sleep(RESTART_DELAY)

                _LOGGER.debug("后台任务：初始化完成")
            except Exception as e:
                _LOGGER.warning("后台初始化任务出错: %s", e)

        # 创建后台任务，不等待完成
        hass.create_task(background_initialization(), name=f"{DOMAIN}_background_init_{entry.entry_id}")

        # 检查是否需要执行设备迁移（替换网关流程）
        # 从数据中获取迁移信息
        _LOGGER.info("检查是否需要执行设备迁移，entry.data: %s", entry.data)
        migration_info = entry.data.get("migration_info")
        _LOGGER.info("迁移信息: %s", migration_info)
        if migration_info:
            old_gateway_sn = migration_info.get("old_gateway_sn")
            remove_old_gateway = migration_info.get("remove_old_gateway", False)
            _LOGGER.info("准备迁移设备，旧网关: %s, 新网关: %s, 是否移除旧网关: %s", old_gateway_sn, gateway_sn, remove_old_gateway)
            if old_gateway_sn and old_gateway_sn != gateway_sn:
                    # 创建后台任务执行迁移
                async def migrate_devices_async():
                    """异步执行设备迁移"""
                    try:
                        _LOGGER.info("开始异步设备迁移，旧网关: %s, 新网关: %s", old_gateway_sn, gateway_sn)
                        
                        # 等待一段时间，确保新网关完全初始化
                        _LOGGER.info("等待5秒，确保新网关完全初始化和设备发现完成...")
                        await asyncio.sleep(RESTART_DELAY)
                        
                        # 调用迁移服务
                        _LOGGER.info("调用迁移服务...")
                        await hass.services.async_call(
                            DOMAIN,
                            "migrate_devices",
                            {
                                "old_gateway_sn": old_gateway_sn,
                                "new_gateway_sn": gateway_sn,
                                "remove_old_gateway": remove_old_gateway
                            },
                            blocking=True
                        )
                        
                        _LOGGER.info("设备迁移任务已提交并完成")
                    except Exception as e:
                        _LOGGER.error("异步执行设备迁移失败: %s", e, exc_info=True)
                
                # 创建迁移任务，不等待完成
                _LOGGER.info("创建迁移后台任务...")
                hass.create_task(migrate_devices_async(), name=f"{DOMAIN}_migrate_{entry.entry_id}")

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

    # 1. 先停止所有定时任务和监听器
    for unsub in data.get("unsub_listeners", []):
        try:
            unsub()
        except Exception as e:
            _LOGGER.warning("取消监听器时出错: %s", e)
            unload_successful = False

    # 2. 停止后台检查任务
    if "mqtt_handler" in data and data["mqtt_handler"]:
        if hasattr(data["mqtt_handler"], '_check_task') and data["mqtt_handler"]._check_task:
            try:
                data["mqtt_handler"]._check_task.cancel()
                _LOGGER.info("已停止MQTT后台检查任务")
            except Exception as e:
                _LOGGER.warning("停止MQTT后台检查任务时出错: %s", e)
                unload_successful = False

    # 3. 卸载平台实体
    try:
        await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        _LOGGER.info("平台实体卸载完成")
    except Exception as e:
        _LOGGER.error("卸载平台时出错: %s", e)
        unload_successful = False

    # 4. 清理MQTT处理器
    try:
        if "mqtt_handler" in data and data["mqtt_handler"]:
            await data["mqtt_handler"].cleanup()
            _LOGGER.info("MQTT处理器清理完成")
    except Exception as e:
        _LOGGER.error("清理MQTT处理器时出错: %s", e)
        unload_successful = False

    # 5. 清理设备管理器
    try:
        if "device_manager" in data and data["device_manager"]:
            await data["device_manager"].cleanup()
            _LOGGER.info("设备管理器清理完成")
    except Exception as e:
        _LOGGER.error("清理设备管理器时出错: %s", e)
        unload_successful = False

    # 6. 最后移除数据
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
    
    # 保留设备到网关映射表，以便重新添加网关时快速恢复设备
    # 不删除映射表，只是标记设备为未关联状态
    if DOMAIN in hass.data and DEVICE_TO_GATEWAY_MAPPING in hass.data[DOMAIN]:
        device_to_gateway_mapping = hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING]
        devices_to_remove = []
        
        # 找出所有映射到该网关的设备
        for device_sn, mapped_gateway_sn in device_to_gateway_mapping.items():
            if mapped_gateway_sn == gateway_sn:
                devices_to_remove.append(device_sn)
        
        # 不从映射表中移除这些设备，而是保留映射关系
        # 这样重新添加网关时可以快速恢复设备
        _LOGGER.info("保留 %d 个设备的映射关系，以便快速恢复", len(devices_to_remove))