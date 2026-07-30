"""开窗器网关集成"""
import logging
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
    SERVICE_RENAME_DEVICE,
    SERVICE_TRANSFER_DEVICE,
    ATTR_NEW_NAME,
    SCAN_INTERVAL,
    DEVICE_TO_GATEWAY_MAPPING,
    DEVICE_TO_GATEWAY_MAPPING_FILE,
    GLOBAL_MANUALLY_REMOVED_DEVICES,
    RESTART_DELAY,
    GATEWAY_PAIRING_TIMEOUT,
    POSITION_MIN,
    POSITION_MAX,
    COMMAND_SET_POSITION
)
from .persist import load_persistent_data, save_persistent_data

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR, Platform.COVER]

# 发现平台名称
DISCOVERY_PLATFORM = "window_controller_gateway"

async def async_setup(hass: HomeAssistant, config: Dict[str, Any]) -> bool:
    """设置集成 - Home Assistant调用此函数加载集成"""
    _LOGGER.info("=== 开窗器网关集成初始化 ===")
    hass.data.setdefault(DOMAIN, {})
    
    # 初始化全局设备到网关映射表
    hass.data[DOMAIN].setdefault(DEVICE_TO_GATEWAY_MAPPING, {})
    hass.data[DOMAIN].setdefault(GLOBAL_MANUALLY_REMOVED_DEVICES, set())
    
    # 加载持久化数据
    await load_persistent_data(hass)
    
    # 设置发现平台
    try:
        from .discovery import async_setup_discovery_platform
        await async_setup_discovery_platform(hass)
        _LOGGER.info("开窗器网关发现平台设置成功")
    except Exception as e:
        _LOGGER.error("设置开窗器网关发现平台失败: %s", e)
    
    # 导入辅助函数
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

        mqtt_handler = gateway_data.get("mqtt_handler")
        if not mqtt_handler:
            _LOGGER.error("未找到MQTT处理器")
            return

        try:
            # P1 修复：使用 mqtt_handler.pairing_timeout_handle 统一管理配对超时，
            # 确保服务调用和按钮按下共享同一个超时句柄，避免重复超时回调。
            if mqtt_handler.pairing_timeout_handle:
                mqtt_handler.pairing_timeout_handle.cancel()
                mqtt_handler.pairing_timeout_handle = None

            success = await mqtt_handler.send_command(mqtt_handler.gateway_sn, "start_pairing")
            if not success:
                _LOGGER.error("发送配对命令失败")
                return

            mqtt_handler.pairing_active = True
            mqtt_handler._notify_status_change()

            hass.async_create_task(
                gateway_data["device_manager"].update_gateway_status("pairing")
            )

            _LOGGER.info("已为网关 %s 发起配对，持续时间: %d秒", gateway_sn, duration)

            def pairing_timeout():
                mqtt_handler.pairing_timeout_handle = None
                mqtt_handler.pairing_active = False
                mqtt_handler._notify_status_change()
                hass.async_create_task(
                    gateway_data["device_manager"].update_gateway_status(
                        "online" if mqtt_handler.connected else "offline"
                    )
                )
                _LOGGER.info("配对模式已超时，恢复正常状态")

            mqtt_handler.pairing_timeout_handle = hass.loop.call_later(duration, pairing_timeout)
        except (ConnectionError, TimeoutError) as e:
            _LOGGER.error("网关 %s 连接或超时错误: %s", gateway_sn, e)
        except (KeyError, AttributeError) as e:
            _LOGGER.error("网关 %s MQTT处理器未找到或配置错误: %s", gateway_sn, e)
        except Exception as e:
            _LOGGER.error("网关 %s 执行配对命令失败: %s", gateway_sn, e)

    async def handle_rename_device(call: ServiceCall) -> None:
        """处理重命名设备服务调用"""
        device_id = call.data.get("device_id")
        new_name = call.data.get(ATTR_NEW_NAME)

        if not device_id or not new_name:
            _LOGGER.error("重命名设备服务调用失败：参数不完整")
            return

        # P0 修复：使用 find_device_by_device_id 解析出设备 SN，
        # 而非直接把 device_id（可能是 HA 设备 ID）传给 rename_device。
        device, gateway_data, gateway_sn = find_device_by_device_id(hass, device_id)
        if not device or not gateway_data:
            _LOGGER.error("未找到设备ID %s 对应的设备", device_id)
            return

        device_manager = gateway_data.get("device_manager")
        if not device_manager:
            _LOGGER.error("未找到设备管理器")
            return

        try:
            device_sn = device["sn"]
            success = await device_manager.rename_device(device_sn, new_name)
            if success:
                _LOGGER.info("设备 %s 已重命名为 %s", device_sn, new_name)
        except Exception as e:
            _LOGGER.error("设备 %s 重命名失败: %s", device_id, e)

    async def handle_refresh_devices(call: ServiceCall) -> None:
        """处理刷新设备服务调用

        协议说明：002 是网关主动发起的上报，HA 无法主动触发设备发现。
        设备列表更新完全依赖网关主动发送 002 消息，HA 被动接收。
        """
        device_id = call.data.get("device_id")

        if not device_id:
            _LOGGER.error("刷新设备服务调用失败：未指定设备ID")
            return

        gateway_data, gateway_sn = find_gateway_by_device_id(hass, device_id)
        if not gateway_data:
            _LOGGER.error("未找到设备ID %s 对应的网关", device_id)
            return

        # 协议说明：002 是网关主动发起，HA 无法主动触发设备发现
        # 设备列表更新依赖网关定期主动上报 002 消息
        _LOGGER.info(
            "网关 %s 的设备列表更新依赖网关主动上报（002），HA 无法主动触发。"
            "请等待网关下一次自动上报，或重启网关触发上报。",
            gateway_sn
        )

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
        hass.async_create_task(set_position_async())
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
        
        # 验证SN格式：与 config_flow.py 的 validate_gateway_sn 保持一致，允许所有字母和数字
        if not re.match(r'^[a-zA-Z0-9]+$', old_gateway_sn):
            _LOGGER.error("旧网关SN格式无效，只允许字母和数字: %s", old_gateway_sn)
            return
        
        if not re.match(r'^[a-zA-Z0-9]+$', new_gateway_sn):
            _LOGGER.error("新网关SN格式无效，只允许字母和数字: %s", new_gateway_sn)
            return
        
        if not isinstance(remove_old_gateway, bool):
            _LOGGER.error("remove_old_gateway参数必须是布尔值: %s", remove_old_gateway)
            return

        # 检查新旧网关是否相同
        if old_gateway_sn.lower() == new_gateway_sn.lower():
            _LOGGER.error("新旧网关不能相同: %s", old_gateway_sn)
            return

        _LOGGER.info("开始设备迁移，新网关: %s, 旧网关: %s", new_gateway_sn, old_gateway_sn)

        # 1. 验证网关存在
        def find_gateway_entry(gateway_sn):
            for entry in hass.config_entries.async_entries(DOMAIN):
                if CONF_GATEWAY_SN in entry.data and entry.data[CONF_GATEWAY_SN].lower() == gateway_sn.lower():
                    return entry
            return None

        old_gateway_entry = find_gateway_entry(old_gateway_sn)
        new_gateway_entry = find_gateway_entry(new_gateway_sn)

        if not old_gateway_entry or not new_gateway_entry:
            _LOGGER.error("网关不存在，旧网关SN: %s, 新网关SN: %s", old_gateway_sn, new_gateway_sn)
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
                new_gateway_sn
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
                            "device_count": len(migrated_devices)
                        }
                    )
                    
                    # P1 修复：移除不存在的 homeassistant/reload_entities 事件（死代码），
                    # 该事件并非 HA 标准事件，不会触发任何 UI 刷新。
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
                        
                        # 先清理旧网关的设备注册，再删除配置条目
                        await old_manager._cleanup_old_gateway(old_gateway_sn)
                        await hass.config_entries.async_remove(old_gateway_entry.entry_id)
                        _LOGGER.info("旧网关移除成功")
                    except Exception as remove_error:
                        _LOGGER.error("移除旧网关失败: %s", remove_error)
                else:
                    # 保留旧网关时，重载其平台以清理已迁移设备的旧实体
                    try:
                        _LOGGER.info("重载旧网关 %s 的平台，清理已迁移设备实体", old_gateway_sn)
                        await hass.config_entries.async_reload(old_gateway_entry.entry_id)
                    except Exception as reload_error:
                        _LOGGER.warning("重载旧网关平台失败: %s", reload_error)
                
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

    async def handle_transfer_device(call: ServiceCall) -> None:
        """处理转移设备服务调用"""
        device_id = call.data.get("device_id")
        new_gateway_sn = call.data.get("new_gateway_sn")

        if not device_id or not new_gateway_sn:
            _LOGGER.error("转移设备服务调用失败：参数不完整")
            return

        _LOGGER.info("收到转移设备请求，设备ID: %s，目标网关: %s", device_id, new_gateway_sn)

        # 解析设备SN（支持直接传入设备SN或HA设备ID）
        device_sn = None

        # 方法1：直接检查 device_id 是否是映射表中的设备SN
        if DOMAIN in hass.data and DEVICE_TO_GATEWAY_MAPPING in hass.data[DOMAIN]:
            mapping = hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING]
            if device_id in mapping:
                device_sn = device_id

        # 方法2：通过设备注册表查找（device_id 可能是 HA 设备注册表 ID）
        if not device_sn:
            try:
                from homeassistant.helpers.device_registry import async_get as async_get_device_registry
                dr = async_get_device_registry(hass)
                device_entry = dr.async_get(device_id)
                if device_entry:
                    for identifier in device_entry.identifiers:
                        if identifier[0] == DOMAIN:
                            device_sn = identifier[1]
                            break
            except Exception:
                pass

        # 方法3：在所有设备管理器的设备列表中查找
        if not device_sn:
            for entry_id, data in hass.data[DOMAIN].items():
                if isinstance(data, dict):
                    dm = data.get("device_manager")
                    if dm:
                        for device in dm.get_all_devices():
                            device_sn_candidate = device.get("sn", "")
                            # 使用精确匹配：device_id 等于 SN，或 SN 是 device_id 按 _ 分割后的某一段
                            if device_id == device_sn_candidate or device_sn_candidate in device_id.split("_"):
                                device_sn = device_sn_candidate
                                break
                        if device_sn:
                            break

        if not device_sn:
            _LOGGER.error("未找到设备ID %s 对应的设备SN", device_id)
            return

        # 查找任意一个设备管理器实例来执行转移
        device_manager = None
        for entry_id, data in hass.data[DOMAIN].items():
            if isinstance(data, dict) and data.get("device_manager"):
                device_manager = data["device_manager"]
                break

        if not device_manager:
            _LOGGER.error("未找到可用的设备管理器")
            return

        # 执行转移
        try:
            success = await device_manager.transfer_device(device_sn, new_gateway_sn)
            if success:
                _LOGGER.info("设备 %s 已成功转移到网关 %s", device_sn, new_gateway_sn)
            else:
                _LOGGER.error("设备 %s 转移失败", device_sn)
        except Exception as e:
            _LOGGER.error("转移设备失败: %s", e)

    # 注册服务
    try:
        hass.services.async_register(
            DOMAIN,
            SERVICE_START_PAIRING,
            handle_start_pairing,
            schema=vol.Schema({
                vol.Required("device_id"): cv.string,
                vol.Optional("duration", default=GATEWAY_PAIRING_TIMEOUT): cv.positive_int,
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
            COMMAND_SET_POSITION,
            handle_set_position,
            schema=vol.Schema({
                vol.Required("device_id"): cv.string,
                vol.Required("position"): vol.All(cv.positive_int, vol.Range(min=POSITION_MIN, max=POSITION_MAX)),
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

        hass.services.async_register(
            DOMAIN,
            SERVICE_RENAME_DEVICE,
            handle_rename_device,
            schema=vol.Schema({
                vol.Required("device_id"): cv.string,
                vol.Required(ATTR_NEW_NAME): cv.string,
            })
        )

        hass.services.async_register(
            DOMAIN,
            SERVICE_TRANSFER_DEVICE,
            handle_transfer_device,
            schema=vol.Schema({
                vol.Required("device_id"): cv.string,
                vol.Required("new_gateway_sn"): cv.string,
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
    gateway_sn = entry.data[CONF_GATEWAY_SN]
    _LOGGER.info("=== 开始设置配置条目: %s, gateway: %s ===", entry.entry_id, gateway_sn)
    
    # 检查持久化数据是否已加载
    if DEVICE_TO_GATEWAY_MAPPING in hass.data[DOMAIN]:
        mapping = hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING]
        _LOGGER.info("持久化映射表已加载: %s", mapping)
    else:
        _LOGGER.error("持久化映射表未加载！")
    
    try:
        from .device_manager import WindowControllerDeviceManager
        from .mqtt_handler import WindowControllerMQTTHandler
    except ImportError as e:
        _LOGGER.critical("导入核心模块失败: %s", e)
        return False

    gateway_name = entry.data.get(CONF_GATEWAY_NAME, f"{DEFAULT_GATEWAY_NAME} {gateway_sn[-4:]}")
    
    device_manager = None
    mqtt_handler = None
    unsub_listeners = []

    try:
        # 先存储一个占位数据，确保平台设置时能够访问到基础数据
        hass.data[DOMAIN].setdefault(entry.entry_id, {})
        hass.data[DOMAIN][entry.entry_id]["gateway_sn"] = gateway_sn
        hass.data[DOMAIN][entry.entry_id]["gateway_name"] = gateway_name
        hass.data[DOMAIN][entry.entry_id]["_setup_in_progress"] = True

        # 创建设备管理器
        _LOGGER.debug("正在创建设备管理器...")
        device_manager = WindowControllerDeviceManager(hass, entry)

        # 快速注册网关设备（立即返回，给用户即时反馈）
        _LOGGER.debug("正在注册网关设备实体...")
        await device_manager.register_gateway_device()

        # 创建MQTT处理器（快速初始化，不等待连接）
        _LOGGER.debug("正在创建MQTT处理器...")
        mqtt_handler = WindowControllerMQTTHandler(hass, gateway_sn, device_manager)
        mqtt_setup_ok = await mqtt_handler.setup()
        if not mqtt_setup_ok:
            _LOGGER.error("MQTT处理器初始化失败，MQTT集成可能未启用")
            raise ConfigEntryNotReady("MQTT集成未启用，请先在Home Assistant中启用MQTT集成")
        
        # 预先将 device_manager 和 mqtt_handler 存储到 entry_data
        # 确保在设备加载回调触发时，平台可以访问到这些对象
        hass.data[DOMAIN][entry.entry_id]["device_manager"] = device_manager
        hass.data[DOMAIN][entry.entry_id]["mqtt_handler"] = mqtt_handler
        hass.data[DOMAIN][entry.entry_id]["gateway_sn"] = gateway_sn
        hass.data[DOMAIN][entry.entry_id]["gateway_name"] = gateway_name

        # 立即加载设备（在平台设置之前）
        _LOGGER.info("正在加载已存在的设备: %s, entry_id: %s", gateway_sn, entry.entry_id)
        try:
            await device_manager.setup()
        except Exception as e:
            _LOGGER.error("加载设备失败: %s", e)
            import traceback
            _LOGGER.error("堆栈跟踪: %s", traceback.format_exc())
        
        # 检查设备加载结果
        devices = device_manager.get_all_devices()
        _LOGGER.info("设备加载完成，共 %d 个设备: %s", len(devices), [d.get("sn") for d in devices])

        # 获取配置选项
        options = entry.options
        discovery_interval = options.get("discovery_interval", SCAN_INTERVAL)
        auto_discovery = options.get("auto_discovery", True)
        debug_logging = options.get("debug_logging", False)
        
        # P1 修复：启用/禁用调试日志时显式设置日志级别，避免关闭后仍为 DEBUG
        if debug_logging:
            _LOGGER.setLevel(logging.DEBUG)
            _LOGGER.info("调试日志已启用")
        else:
            _LOGGER.setLevel(logging.INFO)

        # 设置状态定期更新（取消定时设备发现，只保留连接检查）
        async def periodic_update(_now):
            """定期检查连接状态"""
            try:
                await mqtt_handler.check_connection()
            except Exception as e:
                _LOGGER.warning("定期连接检查时出错: %s", e)

        seconds = discovery_interval.total_seconds() if isinstance(discovery_interval, timedelta) else discovery_interval
        remove_interval = async_track_time_interval(hass, periodic_update, timedelta(seconds=seconds))
        unsub_listeners.append(remove_interval)

        # 更新完整运行数据
        entry_data = {
            "gateway_sn": gateway_sn,
            "gateway_name": gateway_name,
            "device_manager": device_manager,
            "mqtt_handler": mqtt_handler,
            "unsub_listeners": unsub_listeners,
            "_setup_complete": True
        }
        # 合并已有数据（保留平台可能附加的键，如 created_remove_buttons）
        previous = hass.data[DOMAIN].get(entry.entry_id, {})
        previous.update(entry_data)
        hass.data[DOMAIN][entry.entry_id] = previous

        # 设置平台（快速返回，不等待实体创建完成）
        _LOGGER.debug("正在设置前端平台组件...")
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        # 监听HA停止事件
        hass.data[DOMAIN][entry.entry_id]["_stop_unsub"] = hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _make_shutdown_handler(hass, entry))

        # P0 修复 Bug #1：注册选项更新监听器，使配置选项变更即时生效
        entry.async_on_unload(entry.add_update_listener(async_update_options))

        # 创建后台任务，延迟触发发现
        hass.async_create_task(_background_initialization(mqtt_handler), eager_start=True)

        # 检查是否需要执行设备迁移（替换网关流程）
        _LOGGER.info("检查是否需要执行设备迁移，entry.data: %s", entry.data)
        migration_info = entry.data.get("migration_info")
        _LOGGER.info("迁移信息: %s", migration_info)
        if migration_info:
            old_gateway_sn = migration_info.get("old_gateway_sn")
            remove_old_gateway = migration_info.get("remove_old_gateway", False)
            _LOGGER.info("准备迁移设备，旧网关: %s, 新网关: %s, 是否移除旧网关: %s", old_gateway_sn, gateway_sn, remove_old_gateway)
            if old_gateway_sn and old_gateway_sn.lower() != gateway_sn.lower():
                hass.async_create_task(_migrate_devices_async(hass, old_gateway_sn, gateway_sn, remove_old_gateway), name=f"{DOMAIN}_migrate_{entry.entry_id}")
                # P0 修复 Bug #2：迁移任务调度后立即清除 migration_info，
                # 防止迁移完成后的 async_reload 再次触发迁移，形成无限循环
                new_data = {k: v for k, v in entry.data.items() if k != "migration_info"}
                hass.config_entries.async_update_entry(entry, data=new_data)
                _LOGGER.info("已清除 migration_info，防止重载时无限循环")

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
        _LOGGER.debug("要卸载的条目 %s 未在数据中找到（可能已被清理），视为卸载成功", entry_id)
        return True

    data = hass.data[DOMAIN][entry_id]
    unload_successful = True

    # 0. 保存持久化数据（在清理之前）
    await save_persistent_data(hass)

    # 1. 取消停止事件监听器
    stop_unsub = data.get("_stop_unsub")
    if stop_unsub:
        try:
            stop_unsub()
        except Exception as e:
            _LOGGER.debug("取消停止监听器时出错: %s", e)

    # 2. 先停止所有定时任务和监听器
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
                try:
                    await data["mqtt_handler"]._check_task
                except asyncio.CancelledError:
                    _LOGGER.debug("MQTT检查任务已取消")
                except Exception as e:
                    _LOGGER.debug("MQTT检查任务异常: %s", e)
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
    
    # 保存当前的持久化数据
    await save_persistent_data(hass)
    
    # 清理设备到网关映射表中属于该网关的映射关系
    # 否则这些设备会被永久锁死在已删除的网关上，无法被新网关发现和添加
    if DOMAIN in hass.data and DEVICE_TO_GATEWAY_MAPPING in hass.data[DOMAIN]:
        device_to_gateway_mapping = hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING]
        devices_to_remove = []
        
        # 找出所有映射到该网关的设备（大小写不敏感）
        for device_sn, mapped_gateway_sn in list(device_to_gateway_mapping.items()):
            if mapped_gateway_sn.lower() == gateway_sn.lower():
                devices_to_remove.append(device_sn)
                del device_to_gateway_mapping[device_sn]
        
        _LOGGER.info("已清理 %d 个设备的网关映射关系（网关 %s 已删除）", len(devices_to_remove), gateway_sn)
        
        # 保存更新后的持久化数据
        await save_persistent_data(hass)


async def _background_initialization(mqtt_handler):
    """后台初始化任务，不阻塞主流程"""
    try:
        await asyncio.sleep(0.5)
        _LOGGER.debug("后台任务：正在触发快速设备发现...")
        await mqtt_handler.fast_discovery()
        _LOGGER.debug("后台任务：初始化完成")
    except Exception as e:
        _LOGGER.warning("后台初始化任务出错: %s", e)


async def _migrate_devices_async(hass, old_gateway_sn, gateway_sn, remove_old_gateway):
    """异步执行设备迁移"""
    try:
        _LOGGER.info("开始异步设备迁移，旧网关: %s, 新网关: %s", old_gateway_sn, gateway_sn)
        await asyncio.sleep(RESTART_DELAY)
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


def _make_shutdown_handler(hass, entry):
    """创建HA停止时的清理回调"""
    async def async_shutdown(event):
        _LOGGER.info("Home Assistant停止，保存持久化数据...")
        await save_persistent_data(hass)
        _LOGGER.info("Home Assistant停止，清理网关资源...")
        await async_unload_entry(hass, entry)
    return async_shutdown