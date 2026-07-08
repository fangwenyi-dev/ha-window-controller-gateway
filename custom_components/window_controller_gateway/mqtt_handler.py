"""MQTT处理器 - 使用HA内置MQTT，符合新的主题规程"""
import logging
import json
import asyncio
import random
import uuid
import weakref
import time
from datetime import datetime
from typing import Dict, Any, Optional, Callable, Union

from homeassistant.core import HomeAssistant
from homeassistant.components import mqtt

from .const import (
    DOMAIN,
    ATTR_DEVICE_SN,
    ATTR_DEVICE_NAME,
    ATTR_POSITION,
    ATTR_BATTERY,
    DEVICE_TYPE_WINDOW_OPENER,
    GATEWAY_CHECK_INTERVAL,
    GATEWAY_TIMEOUT_SECONDS,
    INITIAL_RETRY_DELAY,
    MQTT_MAX_RETRIES,
    MQTT_MIN_JITTER,
    MQTT_MAX_JITTER,
    MQTT_RETRY_DELAY_MAX,
    MQTT_BATCH_SIZE,
    MAX_COMMAND_ID,
    PROTOCOL_HEAD,
    DEVICE_TYPE_CURTAIN_CTR,
    PAIRING_SN_PLACEHOLDER,
    COMMAND_VALUE_OPEN,
    COMMAND_VALUE_CLOSE,
    COMMAND_VALUE_STOP,
    COMMAND_VALUE_TOGGLE,
    ATTRIBUTE_W_TRAVEL,
    DEFAULT_COMMAND_ID,
    TOPIC_GATEWAY_REQ_FORMAT,
    TOPIC_GATEWAY_RSP,
    DEVICE_TO_GATEWAY_MAPPING,
    get_device_display_name,
)

_LOGGER = logging.getLogger(__name__)

class WindowControllerMQTTHandler:
    """MQTT处理器类 - 使用HA内置MQTT"""
    
    def __init__(self, hass: HomeAssistant, gateway_sn: str, device_manager):
        """初始化MQTT处理器"""
        self.hass = hass
        self.gateway_sn = gateway_sn
        self.device_manager = device_manager
        self.connected = False
        self.pairing_active = False
        self.last_gateway_report_time = None  # 最后收到网关002上报的时间
        self.command_id = DEFAULT_COMMAND_ID  # 命令ID初始值
        self._check_task = None  # 后台任务引用
        self._unsub_rsp = None  # MQTT 订阅取消函数
        self._msg_lock = asyncio.Lock()  # 异步消息去重锁
        self.instance_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, hass.config.config_dir))
        # P1 修复：将配对超时句柄统一存储在 mqtt_handler 上，
        # 使服务调用和按钮按下共享同一个超时管理，避免重复超时回调。
        self.pairing_timeout_handle = None
        
        # MQTT主题定义 - 根据协议要求简化为两个主题
        self.TOPIC_GATEWAY_REQ = TOPIC_GATEWAY_REQ_FORMAT.format(gateway_sn=gateway_sn)  # 发送命令到网关
        self.TOPIC_GATEWAY_RSP = TOPIC_GATEWAY_RSP  # 接收网关数据和响应，同时用于发送响应
        
        # 状态更新回调 - 使用字典按设备SN组织回调
        self._status_callbacks = {}
        
        # 消息去重 - 记录最近处理的消息ID，避免重复处理
        self._processed_messages = {}  # {message_id: timestamp}
        self._message_dedup_duration = 5  # 5秒内相同ID的消息认为是重复
    
    def _schedule_async_task(self, coro):
        """安全地将异步任务调度到主事件循环

        在MQTT回调中正确调度协程到HA主事件循环执行。
        使用 hass.async_create_task 调度，HA 会自动记录未捕获的异常，
        避免异常被静默吞没。如果事件循环未运行，则关闭协程并跳过。
        """
        try:
            loop = self.hass.loop
            if loop.is_running():
                # 优先使用 hass.async_create_task，它会自动记录任务中的未捕获异常
                self.hass.async_create_task(coro)
            else:
                _LOGGER.warning("事件循环未运行，跳过任务调度")
                coro.close()
        except RuntimeError as e:
            _LOGGER.error("调度异步任务失败: %s", e)
            coro.close()
    
    async def setup(self):
        """设置MQTT处理器"""
        _LOGGER.info("MQTT处理器初始化: %s", self.gateway_sn)
        
        # 检查MQTT集成是否可用
        if not self.hass.data.get("mqtt"):
            _LOGGER.error("MQTT集成未启用，请先在Home Assistant中启用MQTT集成")
            return False
            
        # 订阅主题
        await self._subscribe_topics()
        
        # 启动定时检查任务，每30秒检查一次是否超时
        self._check_task = self.hass.loop.create_task(self._check_gateway_timeout())
        
        return True
    
    async def _check_gateway_timeout(self):
        """检查网关是否超时未上报"""
        try:
            while True:
                await asyncio.sleep(GATEWAY_CHECK_INTERVAL)  # 每30秒检查一次
                try:
                    # 检查是否超过超时时间没有收到上报
                    if self.last_gateway_report_time:
                        time_diff = datetime.now() - self.last_gateway_report_time
                        if time_diff.total_seconds() > GATEWAY_TIMEOUT_SECONDS:  # 网关超时时间
                            if self.connected:
                                self.connected = False
                                self._notify_status_change()
                                _LOGGER.warning("网关 %s 超过%s秒未上报，标记为离线", self.gateway_sn, GATEWAY_TIMEOUT_SECONDS)
                                self._schedule_async_task(
                                    self.device_manager.update_gateway_status("offline")
                                )
                except Exception as e:
                    _LOGGER.error("检查网关超时出错: %s", e)
        except asyncio.CancelledError:
            _LOGGER.info("网关超时检查任务已取消")
            return
        except Exception as e:
            _LOGGER.error("网关超时检查任务异常: %s", e)
    
    async def _subscribe_topics(self):
        """订阅MQTT主题 - 根据协议要求简化为只订阅网关响应主题"""
        # 取消旧订阅（防止重连时累积重复订阅）
        if self._unsub_rsp:
            try:
                self._unsub_rsp()
            except Exception as e:
                _LOGGER.debug("取消旧MQTT订阅时出错: %s", e)
            self._unsub_rsp = None
        
        # 订阅网关响应和数据主题
        def handle_gateway_response(msg):
            """处理网关响应和数据消息"""
            try:
                payload = json.loads(msg.payload)
                _LOGGER.debug("收到网关消息: %s", payload)
                
                # 检查是否是标准协议格式（带head和ctype字段）
                if "head" in payload and "ctype" in payload:
                    # 标准协议格式处理
                    ctype = payload.get("ctype")
                    data = payload.get("data", {})
                    
                    # 检查响应是否来自此网关
                    response_sn = payload.get("sn")
                    if not response_sn:
                        return
                    
                    # 消息去重检查 - 使用 ctype + id + sn 作为唯一标识
                    msg_key = f"{ctype}_{payload.get('id', 0)}_{response_sn}"
                    current_time = time.time()
                    
                    # 如果是来自未配置网关的消息，触发网关发现
                    if response_sn.lower() != self.gateway_sn.lower():
                        try:
                            from .discovery import async_discover_gateway
                            gateway_name = f"网关 {response_sn[-4:]}"
                            
                            # 检查是否处于替换模式
                            replace_mode = False
                            for flow in self.hass.config_entries.flow.async_progress():
                                if flow["handler"] == DOMAIN and flow.get("context", {}).get("source") == "replace_gateway":
                                    replace_mode = True
                                    break
                            
                            # 触发网关发现，传入替换模式标志
                            self._schedule_async_task(
                                async_discover_gateway(self.hass, response_sn, gateway_name, replace_mode, self.gateway_sn)
                            )
                        except Exception as e:
                            _LOGGER.error("触发未配置网关发现失败: %s", e)
                        return
                    
                    # 更新最后上报时间 - 只要收到网关消息就认为在线
                    self.last_gateway_report_time = datetime.now()
                    
                    # 只要收到网关消息就认为在线，更新connected状态
                    if not self.connected:
                        self.connected = True
                        self._notify_status_change()
                        _LOGGER.info("网关 %s 收到消息，标记为在线", self.gateway_sn)
                    
                    # 根据不同的消息类型调用相应的处理函数
                    ctype_handlers = {
                        "001": self._handle_ctype_001,
                        "002": self._handle_ctype_002,
                        "003": self._handle_ctype_003,
                        "004": self._handle_ctype_004,
                        "005": self._handle_ctype_005,
                        "006": self._handle_ctype_006,
                        "007": self._handle_ctype_007,
                        "008": self._handle_ctype_008,
                        "009": self._handle_ctype_009,
                        "010": self._handle_ctype_010
                    }
                    
                    if ctype in ctype_handlers:
                        self._schedule_async_task(
                            self._dispatch_with_dedup(
                                ctype_handlers[ctype](payload, ctype, data),
                                msg_key,
                                current_time
                            )
                        )
                    else:
                        _LOGGER.warning("未知的消息类型: %s", ctype)
                    
                    return
                
                # 处理原有格式的响应（向后兼容）
                gateway_sn = payload.get("gateway_sn")
                if not gateway_sn or gateway_sn.lower() != self.gateway_sn.lower():
                    return
                
                response_type = payload.get("type")
                
                if response_type == "device_discovery":
                    devices = payload.get("devices", [])
                    for device_info in devices:
                        device_sn = device_info.get(ATTR_DEVICE_SN)
                        device_name = device_info.get(ATTR_DEVICE_NAME, f"设备 {device_sn[-6:]}")
                        device_type = device_info.get("device_type", DEVICE_TYPE_WINDOW_OPENER)
                        
                        self._schedule_async_task(
                            self.device_manager.add_device(device_sn, device_name, device_type)
                        )
                        
                elif response_type == "device_status":
                    device_sn = payload.get(ATTR_DEVICE_SN)
                    if not device_sn:
                        return
                    
                    status = payload.get("status", "unknown")
                    attributes = {}
                    
                    if ATTR_POSITION in payload:
                        attributes[ATTR_POSITION] = payload[ATTR_POSITION]
                    if ATTR_BATTERY in payload:
                        attributes[ATTR_BATTERY] = payload[ATTR_BATTERY]
                    
                    self._schedule_async_task(
                        self.device_manager.update_device_status(device_sn, status, attributes)
                    )
                    
            except json.JSONDecodeError:
                _LOGGER.error("MQTT消息解析失败: %s", msg.payload)
            except KeyError as e:
                _LOGGER.error("MQTT消息缺少必要字段: %s", e)
            except ValueError as e:
                _LOGGER.error("MQTT消息数据格式错误: %s", e)
            except Exception as e:
                _LOGGER.error("处理网关消息时出错: %s", e)
        
        try:
            # 订阅网关响应主题
            self._unsub_rsp = await mqtt.async_subscribe(self.hass, self.TOPIC_GATEWAY_RSP, handle_gateway_response, 1)
            _LOGGER.debug("订阅网关消息主题: %s", self.TOPIC_GATEWAY_RSP)
        except ConnectionError as e:
            _LOGGER.error("MQTT连接失败: %s", e)
        except TimeoutError as e:
            _LOGGER.error("MQTT订阅超时: %s", e)
        except Exception as e:
            _LOGGER.error("订阅MQTT主题失败: %s", e)
            # 触发重连逻辑
            self._schedule_async_task(
                self._reconnect_mqtt()
            )
    
    async def _reconnect_mqtt(self):
        """MQTT重连逻辑 - 自适应重试策略，结合抖动和随机化"""
        retry_count = 0
        max_retries = MQTT_MAX_RETRIES
        base_delay = INITIAL_RETRY_DELAY
        min_jitter = MQTT_MIN_JITTER
        max_jitter = MQTT_MAX_JITTER
        
        while retry_count < max_retries:
            try:
                _LOGGER.debug("尝试重新连接MQTT... (重试 %d/%d)", retry_count + 1, max_retries)
                
                # 重新订阅主题
                await self._subscribe_topics()
                
                # 重新启动网关超时检查任务
                if self._check_task:
                    if not self._check_task.done():
                        self._check_task.cancel()
                        try:
                            await self._check_task
                        except (asyncio.CancelledError, Exception):
                            pass
                self._check_task = self.hass.loop.create_task(self._check_gateway_timeout())
                
                _LOGGER.debug("MQTT重新连接成功")
                return
            except Exception as e:
                retry_count += 1
                _LOGGER.debug("MQTT重连失败: %s", e)
                
                if retry_count < max_retries:
                    # 实现自适应重试策略
                    # 1. 基础指数退避
                    delay = base_delay * (2 ** (retry_count - 1))
                    # 2. 添加抖动（随机化）
                    jitter = random.uniform(min_jitter, max_jitter)
                    jittered_delay = delay * jitter
                    # 3. 确保延迟在合理范围内
                    jittered_delay = max(1, min(jittered_delay, MQTT_RETRY_DELAY_MAX))
                    
                    _LOGGER.debug("%.1f秒后重试... (基础延迟: %.1f秒, 抖动系数: %.2f)", jittered_delay, delay, jitter)
                    await asyncio.sleep(jittered_delay)
                else:
                    _LOGGER.debug("MQTT重连失败，已达到最大重试次数")
                    # 标记为离线
                    if self.connected:
                        self.connected = False
                        self._notify_status_change()
                        self._schedule_async_task(
                            self.device_manager.update_gateway_status("offline")
                        )
                    return
    
    async def send_command(self, device_sn: str, command: str, params: Optional[Dict[str, Any]] = None) -> bool:
        """发送命令到设备
        
        Args:
            device_sn: 设备SN
            command: 命令类型
            params: 额外参数
            
        Returns:
            bool: 发送是否成功
        """
        try:
            # 验证参数
            if not device_sn:
                _LOGGER.error("设备SN不能为空")
                return False
            
            if not command:
                _LOGGER.error("命令类型不能为空")
                return False
            
            # 验证命令类型
            valid_commands = ["bind_gateway", "start_pairing", "discover", "open", "close", "stop", "a", "set_position", "status"]
            if command not in valid_commands:
                _LOGGER.error("未知命令类型: %s", command)
                return False
            
            # 检查设备是否存在
            if command not in ["bind_gateway", "start_pairing", "discover"]:
                device = self.device_manager.get_device(device_sn)
                if not device:
                    _LOGGER.error("设备不存在，无法发送命令: %s", device_sn)
                    return False
            
            is_offline_allowed_command = command in ["open", "close", "stop", "a", "set_position", "start_pairing"]
            
            if is_offline_allowed_command:
                _LOGGER.info("命令 %s 无论网关在线与否都尝试发送", command)
            else:
                if not self.connected:
                    _LOGGER.debug("MQTT连接未建立，尝试重连...")
                    try:
                        await self._reconnect_mqtt()
                        if not self.connected:
                            _LOGGER.debug("MQTT重连失败，无法发送命令")
                            return False
                    except Exception as reconnect_error:
                        _LOGGER.debug("MQTT重连失败: %s", reconnect_error)
                        return False
            
            # 根据协议文档，使用标准的协议格式
            command_map = {
                "bind_gateway": "001",  # 001: 绑定网关
                "start_pairing": "003",  # 003: 绑定子设备
                "discover": "002",  # 002: 网关状态上报/设备发现
                "open": "004",  # 004: 设备控制
                "close": "004",  # 004: 设备控制
                "stop": "004",  # 004: 设备控制
                "a": "004",  # 004: 设备控制
                "set_position": "004"  # 004: 设备控制
            }
            
            ctype = command_map.get(command, "004")
            
            # 构建协议格式的payload
            payload = {
                "head": PROTOCOL_HEAD,
                "ctype": ctype,
                "id": self.command_id,  # 使用自增ID
                "data": {
                }
            }
            
            # 添加sn字段到payload的末尾
            payload["sn"] = self.gateway_sn
            
            # 确保params不为None，避免后续访问 .get() 时崩溃
            if params is None:
                params = {}

            # 添加额外参数
            try:
                payload["data"].update(params)
            except Exception as e:
                _LOGGER.error("更新额外参数失败: %s", e)
            
            # 根据命令类型添加特定参数
            if command == "start_pairing":
                # 清空data并设置正确的配对参数
                payload["data"] = {
                    "bind": 1,  # 新增字段
                    "devtype": DEVICE_TYPE_CURTAIN_CTR,
                    "sn": PAIRING_SN_PLACEHOLDER
                }
                # 在顶层也添加bind字段
                payload["bind"] = 1
            elif command in ["open", "close", "stop", "a"]:
                # 控制命令需要包含子设备SN
                payload["data"]["sn"] = device_sn
                payload["data"]["attribute"] = ATTRIBUTE_W_TRAVEL
                if command == "open":
                    payload["data"]["value"] = COMMAND_VALUE_OPEN
                elif command == "close":
                    payload["data"]["value"] = COMMAND_VALUE_CLOSE
                elif command == "stop":
                    payload["data"]["value"] = COMMAND_VALUE_STOP
                elif command == "a":
                    payload["data"]["value"] = COMMAND_VALUE_TOGGLE
            elif command == "set_position":
                # 设置位置命令
                payload["data"]["sn"] = device_sn
                payload["data"]["attribute"] = ATTRIBUTE_W_TRAVEL
                position = params.get("position", 0)
                # 验证位置参数
                try:
                    position = int(position)
                    if position < 0 or position > 100:
                        _LOGGER.warning("位置参数超出范围(0-100)，使用默认值0: %s", position)
                        position = 0
                except (ValueError, TypeError):
                    _LOGGER.warning("位置参数无效，使用默认值0: %s", position)
                    position = 0
                payload["data"]["value"] = str(position)
            elif command == "status":
                # 状态查询命令 - 必须包含设备SN，网关才能知道查询哪个设备
                payload["data"]["sn"] = device_sn
            
            # 打印详细的命令信息
            _LOGGER.debug("发送命令到网关: %s, 命令: %s, 设备SN: %s, 载荷: %s", 
                          self.TOPIC_GATEWAY_REQ, command, device_sn, payload)
            
            # 递增ID，保持在合理范围内
            self.command_id += 1
            if self.command_id > MAX_COMMAND_ID:
                self.command_id = 1
            
            try:
                await mqtt.async_publish(
                    self.hass,
                    self.TOPIC_GATEWAY_REQ,
                    json.dumps(payload),
                    1,
                    False
                )
                _LOGGER.info("发送协议命令: %s (类型: %s) 到设备: %s, 参数: %s", command, ctype, device_sn, payload["data"])
                return True
            except Exception as publish_error:
                _LOGGER.error("MQTT消息发布失败: %s\n命令: %s\n设备: %s\n主题: %s\n载荷: %s", 
                             publish_error, command, device_sn, self.TOPIC_GATEWAY_REQ, payload)
                # 标记连接为断开
                self.connected = False
                self._notify_status_change()
                return False
        except Exception as e:
            _LOGGER.error("发送MQTT命令失败: %s\n命令: %s\n设备: %s", e, command, device_sn)
            return False
    

    
    def add_status_callback(self, *args: Union[str, Callable[[Union[str, Dict[str, Any]], Any], None]]):
        """添加状态更新回调
        
        支持两种调用方式：
        1. add_status_callback(device_sn, callback) - 为特定设备添加回调
        2. add_status_callback(callback) - 为网关添加回调
        
        Args:
            *args: 可变参数，
                - 方式1: (device_sn: str, callback: Callable)
                - 方式2: (callback: Callable)
        """
        def _get_weak_ref(callback):
            """获取回调的弱引用"""
            if hasattr(callback, '__self__') and hasattr(callback, '__func__'):
                # 实例方法
                return weakref.WeakMethod(callback)
            else:
                # 普通函数
                return weakref.ref(callback)
        
        if len(args) == 2:
            # 为特定设备添加回调
            device_sn, callback = args
            if device_sn not in self._status_callbacks:
                self._status_callbacks[device_sn] = []
            
            # 使用弱引用存储回调，避免内存泄漏
            weak_callback = _get_weak_ref(callback)
            # 检查是否已经存在相同的回调
            callback_exists = False
            for ref in self._status_callbacks[device_sn]:
                if ref() == callback:
                    callback_exists = True
                    break
            
            if not callback_exists:
                self._status_callbacks[device_sn].append(weak_callback)
                _LOGGER.debug("为设备 %s 添加状态更新回调", device_sn)
        elif len(args) == 1:
            # 为网关添加回调（向后兼容）
            callback = args[0]
            # 使用特殊键 "gateway" 存储网关回调
            if "gateway" not in self._status_callbacks:
                self._status_callbacks["gateway"] = []
            
            # 使用弱引用存储回调，避免内存泄漏
            weak_callback = _get_weak_ref(callback)
            # 检查是否已经存在相同的回调
            callback_exists = False
            for ref in self._status_callbacks["gateway"]:
                if ref() == callback:
                    callback_exists = True
                    break
            
            if not callback_exists:
                self._status_callbacks["gateway"].append(weak_callback)
                _LOGGER.debug("为网关添加状态更新回调")

    def remove_status_callback(self, *args: Union[str, Callable[[Union[str, Dict[str, Any]], Any], None]]):
        """移除状态更新回调
        
        支持两种调用方式：
        1. remove_status_callback(device_sn, callback) - 移除特定设备的回调
        2. remove_status_callback(callback) - 移除网关的回调
        
        Args:
            *args: 可变参数，
                - 方式1: (device_sn: str, callback: Callable)
                - 方式2: (callback: Callable)
        """
        if len(args) == 2:
            # 移除特定设备的回调
            device_sn, callback = args
            if device_sn in self._status_callbacks:
                # 找到并移除对应的弱引用
                refs_to_remove = []
                for ref in self._status_callbacks[device_sn]:
                    if ref() == callback:
                        refs_to_remove.append(ref)
                
                for ref in refs_to_remove:
                    self._status_callbacks[device_sn].remove(ref)
                    _LOGGER.debug("从设备 %s 移除状态更新回调", device_sn)
                
                # 清理无效的弱引用
                valid_refs = []
                for ref in self._status_callbacks[device_sn]:
                    if ref() is not None:
                        valid_refs.append(ref)
                
                if valid_refs:
                    self._status_callbacks[device_sn] = valid_refs
                else:
                    # 如果设备没有回调了，清理设备条目
                    del self._status_callbacks[device_sn]
                    _LOGGER.debug("清理设备 %s 的回调条目", device_sn)
        elif len(args) == 1:
            # 移除网关的回调（向后兼容）
            callback = args[0]
            if "gateway" in self._status_callbacks:
                # 找到并移除对应的弱引用
                refs_to_remove = []
                for ref in self._status_callbacks["gateway"]:
                    if ref() == callback:
                        refs_to_remove.append(ref)
                
                for ref in refs_to_remove:
                    self._status_callbacks["gateway"].remove(ref)
                    _LOGGER.debug("从网关移除状态更新回调")
                
                # 清理无效的弱引用
                valid_refs = []
                for ref in self._status_callbacks["gateway"]:
                    if ref() is not None:
                        valid_refs.append(ref)
                
                if valid_refs:
                    self._status_callbacks["gateway"] = valid_refs
                else:
                    # 如果网关没有回调了，清理网关条目
                    del self._status_callbacks["gateway"]
                    _LOGGER.debug("清理网关的回调条目")
    
    def _notify_status_change(self):
        """通知状态变化 - 确保在事件循环线程中执行回调"""
        # 此方法现在用于网关状态变化通知
        # 设备状态变化通知使用 _notify_device_status_change
        
        # 通知网关状态回调
        if "gateway" in self._status_callbacks:
            gateway_callbacks = self._status_callbacks["gateway"]
            valid_callbacks = []
            
            for ref in gateway_callbacks:
                callback = ref()
                if callback is not None:
                    valid_callbacks.append(callback)
                
            # 清理无效的弱引用
            self._status_callbacks["gateway"] = [ref for ref in gateway_callbacks if ref() is not None]
            
            for callback in valid_callbacks:
                try:
                    # 使用hass.add_job确保在事件循环线程中执行回调
                    self.hass.add_job(callback)
                except Exception as e:
                    _LOGGER.error("调用网关状态回调失败: %s", e)
    
    def _notify_device_status_change(self, device_sn):
        """通知设备状态变化 - 确保在事件循环线程中执行回调"""
        if device_sn in self._status_callbacks:
            device_callbacks = self._status_callbacks[device_sn]
            valid_callbacks = []
            
            for ref in device_callbacks:
                callback = ref()
                if callback is not None:
                    valid_callbacks.append(callback)
            
            # 清理无效的弱引用
            self._status_callbacks[device_sn] = [ref for ref in device_callbacks if ref() is not None]
            
            for callback in valid_callbacks:
                try:
                    # 使用hass.add_job确保在事件循环线程中执行回调
                    self.hass.add_job(callback)
                    _LOGGER.debug("通知设备 %s 状态更新回调", device_sn)
                except Exception as e:
                    _LOGGER.error("调用设备状态回调失败: %s", e)
            
            # 如果设备没有回调了，清理设备条目
            if not self._status_callbacks[device_sn]:
                del self._status_callbacks[device_sn]
                _LOGGER.debug("清理设备 %s 的回调条目", device_sn)
    
    async def check_connection(self):
        """检查MQTT连接状态

        发送标准 $SH 协议的 002 发现命令，既能验证 MQTT broker 连通性，
        又能触发网关上报状态，保持网关活跃。
        网关的 connected 状态由 handle_gateway_response 收到网关消息时设为 True，
        由 _check_gateway_timeout 超时后设为 False。
        """
        try:
            # 使用标准 $SH 协议格式发送发现命令
            payload = {
                "head": PROTOCOL_HEAD,
                "ctype": "002",
                "id": self.command_id,
                "data": {},
                "sn": self.gateway_sn
            }

            # 递增命令ID
            self.command_id += 1
            if self.command_id > MAX_COMMAND_ID:
                self.command_id = 1

            await mqtt.async_publish(
                self.hass,
                self.TOPIC_GATEWAY_REQ,
                json.dumps(payload),
                1,
                False
            )
            _LOGGER.debug("MQTT broker 连通性检查通过（网关 %s）", self.gateway_sn)
        except Exception as e:
            _LOGGER.error("MQTT连接检查失败: %s", e)

            # 只有在 publish 失败时才标记离线（说明 MQTT broker 不可达）
            if self.connected:
                self.connected = False
                self._notify_status_change()

                self._schedule_async_task(
                    self.device_manager.update_gateway_status("offline")
                )

        return self.connected
    
    async def unbind_device(self, device_sn: str):
        """解绑设备 - 使用协议类型003，bind=0"""
        # 构建符合协议要求的解绑命令
        payload = {
            "head": PROTOCOL_HEAD,
            "ctype": "003",
            "id": self.command_id,
            "data": {
                "bind": 0,
                "devtype": DEVICE_TYPE_CURTAIN_CTR,
                "sn": device_sn
            },
            "sn": self.gateway_sn,
            "bind": 0  # 0代表解绑
        }
        # 递增ID
        self.command_id += 1
        if self.command_id > MAX_COMMAND_ID:
            self.command_id = 1
        
        # 发送MQTT消息
        try:
            await mqtt.async_publish(
                self.hass,
                self.TOPIC_GATEWAY_REQ,
                json.dumps(payload),
                1,
                False
            )
            _LOGGER.info("解绑命令已发送，设备SN: %s", device_sn)
            _LOGGER.debug("解绑命令payload: %s", payload)
        except Exception as e:
            _LOGGER.error("发送解绑命令失败: %s", e)
            raise
    
    async def trigger_discovery(self):
        """触发设备发现 - 使用协议类型002"""
        # 使用send_command方法发送符合协议要求的设备发现命令
        await self.send_command(
            self.gateway_sn,  # 使用网关SN作为设备SN
            "discover"
        )
        _LOGGER.info("设备发现命令已发送")
    
    async def fast_discovery(self):
        """快速设备发现 - 优化版，添加设备状态预查询逻辑"""
        start_time = time.time()
        
        # 1. 立即发送发现命令
        await self.send_command(self.gateway_sn, "discover")
        _LOGGER.debug("快速发现: 已发送发现命令")
        
        # 2. 并行处理后续流程
        tasks = []
        
        # 任务1: 更新网关状态
        tasks.append(self.device_manager.update_gateway_status("online"))
        _LOGGER.debug("快速发现: 添加网关状态更新任务")
        
        # 任务2: 批量查询所有已知设备状态（预查询）
        device_sns = list(self.device_manager.devices.keys())
        if device_sns:
            # 分批查询设备状态，避免一次性发送过多命令
            batch_size = MQTT_BATCH_SIZE
            for i in range(0, len(device_sns), batch_size):
                batch_devices = device_sns[i:i+batch_size]
                for device_sn in batch_devices:
                    tasks.append(self.send_command(device_sn, "status"))
                    _LOGGER.debug("快速发现: 添加设备状态预查询任务: %s", device_sn)
                _LOGGER.debug("快速发现: 批次 %d 预查询 %d 个设备", i//batch_size + 1, len(batch_devices))
        
        # 并行执行所有任务
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            # 统计成功和失败的任务
            success_count = sum(1 for r in results if not isinstance(r, Exception))
            _LOGGER.debug("快速发现: 并行任务完成，成功: %d，总数: %d", success_count, len(tasks))
        
        elapsed_time = time.time() - start_time
        _LOGGER.info("快速设备发现完成，耗时: %.2f秒，预查询设备数: %d", elapsed_time, len(device_sns))
    
    async def cleanup(self):
        """清理MQTT资源"""
        _LOGGER.info("清理MQTT资源")
        # 取消配对超时句柄
        if self.pairing_timeout_handle:
            try:
                self.pairing_timeout_handle.cancel()
            except Exception as e:
                _LOGGER.debug("取消配对超时句柄异常: %s", e)
            self.pairing_timeout_handle = None
        
        # 取消后台任务
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                _LOGGER.debug("MQTT检查任务已取消")
            except Exception as e:
                _LOGGER.debug("MQTT检查任务异常: %s", e)
            self._check_task = None
        
        # 取消 MQTT 订阅
        if self._unsub_rsp:
            try:
                self._unsub_rsp()
            except Exception as e:
                _LOGGER.debug("取消MQTT订阅异常: %s", e)
            self._unsub_rsp = None
        
        # 清理所有回调引用，避免内存泄漏
        self._status_callbacks.clear()
        _LOGGER.debug("所有状态更新回调已清理")

    async def _batch_process_tasks(self, tasks, task_type="处理"):
        """批处理异步任务
        
        Args:
            tasks: 要执行的异步任务列表
            task_type: 任务类型描述，用于日志
        """
        if not tasks:
            return
        
        batch_size = 10
        total_success = 0
        for i in range(0, len(tasks), batch_size):
            batch_tasks = tasks[i:i+batch_size]
            results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            success_count = sum(1 for r in results if not isinstance(r, Exception))
            total_success += success_count
            _LOGGER.info("批量%s完成，批次: %d，成功: %d，总数: %d", 
                       task_type, i//batch_size + 1, success_count, len(batch_tasks))
        _LOGGER.info("所有批次%s完成，总成功: %d，总总数: %d", task_type, total_success, len(tasks))
    
    async def _dispatch_with_dedup(self, handler_coro, msg_key: str, current_time: float):
        """带去重检查的异步任务分发"""
        async with self._msg_lock:
            self._processed_messages = {
                k: v for k, v in self._processed_messages.items()
                if current_time - v < self._message_dedup_duration
            }
            if msg_key in self._processed_messages:
                _LOGGER.debug("跳过重复消息: %s", msg_key)
                handler_coro.close()
                return
            self._processed_messages[msg_key] = current_time
        await handler_coro

    async def _handle_ctype_001(self, payload, ctype, data):
        """处理协议类型001：绑定网关"""
        # 检查是否包含设备信息（vesion, model等字段）或网关主动发起绑定请求
        # 两种情况都需要回复相同的 001 响应
        if "errcode" not in data:
            _LOGGER.debug("收到网关绑定请求/设备信息: %s, 版本: %s",
                         self.gateway_sn, data.get("vesion"))

            # 构建响应消息 - 按照协议要求回复001
            response_payload = {
                "head": PROTOCOL_HEAD,
                "ctype": "001",
                "id": payload.get("id", 0),
                "sn": self.gateway_sn,
                "data": {
                    "errcode": 0,
                    "uuid": self.instance_uuid
                }
            }

            # 发送响应到网关
            await mqtt.async_publish(
                self.hass,
                self.TOPIC_GATEWAY_REQ,
                json.dumps(response_payload),
                1,
                False
            )
            _LOGGER.info("发送网关绑定响应成功到主题: %s", self.TOPIC_GATEWAY_REQ)

            # 更新网关状态
            await self.device_manager.update_gateway_status("online")
        else:
            # 处理网关响应（可能来自其他系统）
            errcode = data.get("errcode", -1)
            if errcode == 0:
                _LOGGER.info("网关绑定成功: %s", self.gateway_sn)
                await self.device_manager.update_gateway_status("online")
            else:
                _LOGGER.error("网关绑定失败，错误码: %d", errcode)

    async def _handle_ctype_002(self, payload, ctype, data):
        """处理协议类型002：网关状态上报 - 优化版"""
        try:
            status = data.get("status", "unknown")
            _LOGGER.debug("网关状态上报: %s", status)
            await self.device_manager.update_gateway_status(status)
            # connected 状态已由 handle_gateway_response 在消息分发前设置，此处无需重复
            
            # 002 上报时不再重复触发 async_discover_gateway，
            # 网关已在配置流程中注册，重复发现只会浪费资源。
            # 发现流程由 _subscribe_topics 中收到未配置网关消息时触发。
            
            # 批量处理设备列表
            if "devices" in data:
                devices = data["devices"]
                
                # 使用集合记录已处理的设备，避免重复处理
                processed_sns = set()
                
                # 批量添加和更新任务
                add_tasks = []
                update_tasks = []
                
                for device_info in devices:
                    try:
                        device_sn = device_info.get("sn")
                        if not device_sn:
                            continue
                        
                        # 跳过已处理的设备
                        if device_sn in processed_sns:
                            continue
                        processed_sns.add(device_sn)
                        
                        # 检查是否网关设备
                        if device_sn.startswith("1001"):
                            continue
                        
                        # 保留原有检查逻辑作为备份
                        device_model = device_info.get("model", "").lower()
                        device_vesion = device_info.get("vesion", "").lower()
                        if "gateway" in device_model or "网关" in device_model:
                            continue
                        elif "gateway" in device_vesion or "网关" in device_vesion:
                            continue
                        
                        # 检查设备是否已存在
                        existing_device = self.device_manager.get_device(device_sn)
                        if existing_device:
                            # 只更新状态，不重复添加
                            update_tasks.append(self._update_device_attributes(device_sn, device_info))
                        else:
                            # 检查设备是否已添加到其他网关中
                            if DEVICE_TO_GATEWAY_MAPPING in self.hass.data[DOMAIN]:
                                device_to_gateway_mapping = self.hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING]
                                if device_sn in device_to_gateway_mapping:
                                    existing_gateway_sn = device_to_gateway_mapping[device_sn]
                                    if existing_gateway_sn.lower() != self.gateway_sn.lower():
                                        _LOGGER.info("设备 %s 已添加到网关 %s，不自动添加到当前网关 %s", 
                                                    device_sn, existing_gateway_sn, self.gateway_sn)
                                        continue
                            
                            # 快速添加设备任务
                            add_tasks.append(self._quick_add_device(device_sn, device_info))
                            
                    except Exception as e:
                        _LOGGER.error("处理设备信息异常: %s", e, exc_info=True)
                
                # 分批执行添加任务，每批10个设备
                if add_tasks:
                    await self._batch_process_tasks(add_tasks, "添加设备")
                
                # 分批执行更新任务，每批10个设备
                if update_tasks:
                    await self._batch_process_tasks(update_tasks, "更新设备状态")
        except KeyError as e:
            _LOGGER.error("缺少必要字段: %s, payload: %s", e, payload)
        except ValueError as e:
            _LOGGER.error("数据格式错误: %s, data: %s", e, data)
        except Exception as e:
            _LOGGER.error("处理002消息异常: %s", e, exc_info=True)
        
        # 构建002响应
        response_payload = {
            "head": PROTOCOL_HEAD,
            "ctype": "002",
            "id": payload.get("id", 0),
            "sn": self.gateway_sn,
            "data": {
                "errcode": 0
            }
        }
        
        # 发送响应到网关 - 按照协议要求发送到gateway/<sn>/req主题
        await mqtt.async_publish(
            self.hass,
            self.TOPIC_GATEWAY_REQ,
            json.dumps(response_payload),
            1,
            False
        )
        _LOGGER.info("发送网关状态上报响应成功到主题: %s", self.TOPIC_GATEWAY_REQ)

    async def _quick_add_device(self, device_sn, device_info):
        """快速添加设备 - 自动发现"""
        device_name = get_device_display_name(self.gateway_sn, device_sn)
        
        # 直接调用设备管理器的添加方法（自动发现，不使用手动配对标记）
        await self.device_manager.add_device(device_sn, device_name, DEVICE_TYPE_WINDOW_OPENER)
        
        # 立即更新设备状态
        await self._update_device_attributes(device_sn, device_info)

    async def _update_device_attributes(self, device_sn, device_info):
        """更新设备属性"""
        attributes = {}
        
        # 提取设备属性
        if "battery" in device_info:
            try:
                voltage = float(device_info["battery"]) / 10
                attributes["voltage"] = voltage
                _LOGGER.debug("设备 %s 电池电压: %.1fV", device_sn, voltage)
            except ValueError as e:
                _LOGGER.error("电池电压数据格式错误: %s, 值: %s", e, device_info["battery"])
        
        if "r_travel" in device_info:
            try:
                r_travel = int(device_info["r_travel"])
                attributes["r_travel"] = r_travel
                _LOGGER.debug("设备 %s 位置状态: %d", device_sn, r_travel)
            except ValueError as e:
                _LOGGER.error("位置状态数据格式错误: %s, 值: %s", e, device_info["r_travel"])
        
        if attributes:
            # 只有当 r_travel 实际存在于上报数据中时才推导设备状态，
            # 避免仅有 battery/voltage 上报时将 None != 0 误判为 "open"
            if "r_travel" in attributes:
                device_status = "closed" if attributes["r_travel"] == 0 else "open"
                await self.device_manager.update_device_status(device_sn, device_status, attributes)
            else:
                # 没有 r_travel 时只更新属性，不覆盖设备的状态字段
                await self.device_manager.update_device_status(device_sn, None, attributes)
            self._notify_device_status_change(device_sn)

    async def _handle_ctype_003(self, payload, ctype, data):
        """处理协议类型003：绑定子设备"""
        errcode = data.get("errcode", -1)
        device_sn = data.get("sn") or payload.get("sn")
        
        if errcode == 0 and device_sn:
            # 绑定成功，添加设备
            # 计算设备序号，从01开始
            device_count = len(self.device_manager.get_all_devices())
            device_number = device_count + 1
            device_name = get_device_display_name(self.gateway_sn, device_sn, device_number)
            # 手动配对时使用 is_manual_pairing=True，跳过手动删除列表检查
            await self.device_manager.add_device(device_sn, device_name, DEVICE_TYPE_WINDOW_OPENER, is_manual_pairing=True)
            # 配对成功后立即退出配对模式，UI 可以立刻从"配对中"恢复
            # 同时取消配对超时定时器，避免超时回调冗余触发
            if self.pairing_timeout_handle:
                self.pairing_timeout_handle.cancel()
                self.pairing_timeout_handle = None
            self.pairing_active = False
            self._notify_status_change()
            _LOGGER.info("设备绑定成功: %s, 名称: %s", device_sn, device_name)
        elif errcode == 0 and not device_sn:
            _LOGGER.warning("设备绑定成功但未返回设备SN，无法添加设备: %s", payload)
        else:
            # 错误码7可能表示通讯距离不够，不记录为错误
            if errcode == 7:
                _LOGGER.debug("设备绑定失败，错误码: %d, SN: %s (可能是通讯距离不够)", errcode, device_sn)
            else:
                # 其他错误码记录为警告
                _LOGGER.warning("设备绑定失败，错误码: %d, SN: %s", errcode, device_sn)

    async def _handle_ctype_004(self, payload, ctype, data):
        """处理协议类型004：设备控制响应"""
        errcode = data.get("errcode", -1)
        device_sn = data.get("sn")
        if errcode == 0:
            if device_sn:
                _LOGGER.debug("设备控制成功: %s", device_sn)
            else:
                _LOGGER.debug("设备控制成功，但未返回设备SN")
        else:
            if errcode == 7:
                _LOGGER.debug("设备控制失败，错误码: %d, SN: %s (可能是通讯距离不够)", errcode, device_sn)
            else:
                _LOGGER.warning("设备控制失败，错误码: %d, SN: %s", errcode, device_sn)

    async def _handle_ctype_005(self, payload, ctype, data):
        """处理协议类型005：设备上报"""
        device_sn = data.get("sn")
        if device_sn:
            # 解析设备上报的状态
            status = data.get("status", "unknown")
            attributes = {}
            
            # 提取上报的属性
            if "position" in data:
                attributes[ATTR_POSITION] = data["position"]
            if "battery" in data:
                # 统一存储为 voltage，与网关上报保持一致
                battery = data["battery"]
                try:
                    # 转换为浮点数并除以10（如105 → 10.5V）
                    voltage = float(battery) / 10
                    attributes["voltage"] = voltage
                    _LOGGER.debug("设备 %s 电池电压: %.1fV", device_sn, voltage)
                except (ValueError, TypeError) as e:
                    _LOGGER.error("设备 %s 电池电压数据格式错误: %s, 值: %s", device_sn, e, battery)
            if "state" in data:
                attributes["state"] = data["state"]
            
            # 处理attrs数组
            if "attrs" in data:
                attrs = data["attrs"]
                for attr in attrs:
                    attribute = attr.get("attribute")
                    value = attr.get("value")
                    
                    if attribute == "voltage":
                        # 转换电压值，105表示10.5v
                        try:
                            voltage = float(value) / 10
                            attributes["voltage"] = voltage
                        except (ValueError, TypeError) as e:
                            _LOGGER.error("设备 %s 电压属性格式错误: %s, 值: %s", device_sn, e, value)
                    elif attribute == "r_travel":
                        # 处理窗户状态，0表示关闭，其他表示打开
                        try:
                            travel_value = int(value)
                            attributes["r_travel"] = travel_value
                            # 根据r_travel设置状态
                            if travel_value == 0:
                                status = "closed"
                            else:
                                status = "open"
                        except (ValueError, TypeError) as e:
                            _LOGGER.error("设备 %s 位置状态格式错误: %s, 值: %s", device_sn, e, value)
            
            # 更新设备状态
            await self.device_manager.update_device_status(device_sn, status, attributes)
            # 通知设备状态变化，触发传感器实体更新
            self._notify_device_status_change(device_sn)
            _LOGGER.debug("设备上报处理完成: %s", device_sn)

    async def _handle_ctype_006(self, payload, ctype, data):
        """处理协议类型006：批量设备状态上报"""
        # 这里可以添加批量设备状态上报的处理逻辑
        _LOGGER.debug("批量设备状态上报: %s", data)

    async def _handle_ctype_007(self, payload, ctype, data):
        """处理协议类型007：设备事件上报"""
        # 这里可以添加设备事件上报的处理逻辑
        _LOGGER.debug("设备事件上报: %s", data)

    async def _handle_ctype_008(self, payload, ctype, data):
        """处理协议类型008：网关配置更新"""
        # 这里可以添加网关配置更新的处理逻辑
        _LOGGER.debug("网关配置更新: %s", data)

    async def _handle_ctype_009(self, payload, ctype, data):
        """处理协议类型009：设备配置更新"""
        # 这里可以添加设备配置更新的处理逻辑
        _LOGGER.debug("设备配置更新: %s", data)

    async def _handle_ctype_010(self, payload, ctype, data):
        """处理协议类型010：系统消息"""
        # 这里可以添加系统消息的处理逻辑
        _LOGGER.debug("系统消息: %s", data)
        # MQTT订阅会在HA重启时自动清理，无需手动处理
        return True
