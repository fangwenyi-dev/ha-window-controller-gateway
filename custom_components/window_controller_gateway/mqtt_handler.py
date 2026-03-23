"""MQTT处理器 - 使用HA内置MQTT，符合新的主题规程"""
import logging
import json
import asyncio
import random
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
    ATTRIBUTE_W_TRAVEL
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
        from .const import DEFAULT_COMMAND_ID, TOPIC_GATEWAY_REQ_FORMAT, TOPIC_GATEWAY_RSP
        self.command_id = DEFAULT_COMMAND_ID  # 命令ID初始值
        self._check_task = None  # 后台任务引用
        
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
        
        在MQTT回调线程中正确调度协程到HA主事件循环执行
        """
        try:
            loop = self.hass.loop
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(coro, loop)
            else:
                _LOGGER.warning("事件循环未运行，跳过任务调度")
        except RuntimeError as e:
            _LOGGER.error("调度异步任务失败: %s", e)
    
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
                    from .const import GATEWAY_TIMEOUT_SECONDS
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
                    
                    # 清理过期的消息记录
                    self._processed_messages = {
                        k: v for k, v in self._processed_messages.items()
                        if current_time - v < self._message_dedup_duration
                    }
                    
                    # 如果消息已处理过，跳过
                    if msg_key in self._processed_messages:
                        _LOGGER.debug("跳过重复消息: %s", msg_key)
                        return
                    
                    # 记录新消息
                    self._processed_messages[msg_key] = current_time
                    
                    # 如果是来自未配置网关的消息，触发网关发现
                    if response_sn != self.gateway_sn:
                        try:
                            from .discovery import async_discover_gateway
                            gateway_name = f"网关 {response_sn[-6:]}"
                            
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
                            ctype_handlers[ctype](payload, ctype, data)
                        )
                    else:
                        _LOGGER.warning("未知的消息类型: %s", ctype)
                    
                    return
                
                # 处理原有格式的响应（向后兼容）
                gateway_sn = payload.get("gateway_sn")
                if not gateway_sn or gateway_sn != self.gateway_sn:
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
            await mqtt.async_subscribe(self.hass, self.TOPIC_GATEWAY_RSP, handle_gateway_response, 1)
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
                if self._check_task and self._check_task.done():
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
            
            # 添加额外参数
            if params:
                try:
                    payload["data"].update(params)
                except Exception as e:
                    _LOGGER.error("更新额外参数失败: %s", e)
                    return False
            
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
                _LOGGER.info("发送协议命令 %s (类型: %s) 到设备 %s, 参数: %s", command, ctype, device_sn, payload["data"])
                return True
            except Exception as e:
                _LOGGER.error("发送MQTT消息失败: %s", e)
                return False
        
        except Exception as e:
            _LOGGER.error("发送命令时出错: %s", e)
            return False
    
    async def unbind_device(self, device_sn: str):
        """解绑设备 - 使用协议类型003，bind=0"""
        payload = {
            "head": PROTOCOL_HEAD,
            "ctype": "003",
            "id": self.command_id,
            "data": {
                "bind": 0,  # 解绑
                "devtype": DEVICE_TYPE_CURTAIN_CTR,
                "sn": device_sn
            },
            "sn": self.gateway_sn,
            "bind": 0  # 0代表解绑
        }
        
        _LOGGER.info("解绑设备: %s", device_sn)
        
        try:
            await mqtt.async_publish(
                self.hass,
                self.TOPIC_GATEWAY_REQ,
                json.dumps(payload),
                1,
                False
            )
            _LOGGER.info("解绑命令已发送: %s", device_sn)
            return True
        except Exception as e:
            _LOGGER.error("发送解绑命令失败: %s", e)
            return False
    
    async def unbind_device_legacy(self, device_sn: str):
        """解绑设备（兼容旧格式）"""
        payload = {
            "type": "unbind_device",
            "gateway_sn": self.gateway_sn,
            "device_sn": device_sn
        }
        
        _LOGGER.info("解绑设备(旧格式): %s", device_sn)
        
        try:
            await mqtt.async_publish(
                self.hass,
                self.TOPIC_GATEWAY_REQ,
                json.dumps(payload),
                1,
                False
            )
            return True
        except Exception as e:
            _LOGGER.error("发送解绑命令失败: %s", e)
            return False
    
    def _notify_status_change(self):
        """通知状态变化，触发所有注册的回调"""
        for device_sn, callbacks in self._status_callbacks.items():
            for callback in callbacks:
                try:
                    callback()
                except Exception as e:
                    _LOGGER.error("执行状态回调失败: %s", e)
    
    def _notify_device_status_change(self, device_sn):
        """通知特定设备状态变化"""
        if device_sn in self._status_callbacks:
            for callback in self._status_callbacks[device_sn]:
                try:
                    callback()
                except Exception as e:
                    _LOGGER.error("执行设备状态回调失败: %s", e)
    
    def register_status_callback(self, device_sn: str, callback: Callable):
        """注册设备状态变化回调"""
        if device_sn not in self._status_callbacks:
            self._status_callbacks[device_sn] = []
        self._status_callbacks[device_sn].append(callback)
    
    def unregister_status_callback(self, device_sn: str, callback: Callable):
        """注销设备状态变化回调"""
        if device_sn in self._status_callbacks:
            try:
                self._status_callbacks[device_sn].remove(callback)
            except ValueError:
                pass
    
    async def _handle_ctype_001(self, payload, ctype, data):
        """处理协议类型001：绑定网关响应"""
        errcode = data.get("errcode", -1)
        if errcode == 0:
            _LOGGER.info("网关绑定成功")
        else:
            _LOGGER.warning("网关绑定失败，错误码: %d", errcode)
    
    async def _handle_ctype_002(self, payload, ctype, data):
        """处理协议类型002：设备发现/状态上报"""
        devices = data.get("devices", [])
        
        for device_info in devices:
            device_sn = device_info.get("sn")
            if not device_sn:
                continue
            
            # 获取设备类型
            devtype = device_info.get("devtype", 0)
            
            # 根据设备类型确定设备名称
            if devtype == 20482:
                device_name = f"窗户 {device_sn[-4:]}"
            elif devtype == 20485:
                device_name = f"传感器 {device_sn[-4:]}"
            else:
                device_name = f"设备 {device_sn[-4:]}"
            
            # 提取设备属性
            attributes = {}
            
            # 电池电压
            if "battery" in device_info:
                battery = device_info["battery"]
                voltage = float(battery) / 10
                attributes["voltage"] = voltage
            
            # 窗户行程（用于判断开关状态）
            if "r_travel" in device_info:
                r_travel = device_info["r_travel"]
                attributes["r_travel"] = r_travel
            
            # 最后通信时间
            if "last" in device_info:
                attributes["last_seen"] = device_info["last"]
            
            # 版本号
            if "version" in device_info:
                attributes["version"] = device_info["version"]
            
            # roll值（可能是位置）
            if "roll" in device_info:
                attributes["roll"] = device_info["roll"]
            
            # 根据 r_travel 确定状态
            r_travel = device_info.get("r_travel", 0)
            if r_travel == 0:
                status = "closed"
            else:
                status = "open"
            
            _LOGGER.debug("处理设备状态: %s, 名称: %s, 状态: %s, 类型: %d", 
                         device_sn, device_name, status, devtype)
            
            # 更新设备状态
            await self.device_manager.update_device_status(device_sn, status, attributes)
    
    async def _handle_ctype_003(self, payload, ctype, data):
        """处理协议类型003：绑定子设备响应"""
        errcode = data.get("errcode", -1)
        device_sn = data.get("sn")
        
        if errcode == 0:
            if device_sn:
                _LOGGER.info("设备绑定成功: %s", device_sn)
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
            # 错误码7可能表示通讯距离不够，不记录为错误
            if errcode == 7:
                _LOGGER.debug("设备控制失败，错误码: %d, SN: %s (可能是通讯距离不够)", errcode, device_sn)
            else:
                # 其他错误码记录为警告
                _LOGGER.warning("设备控制失败，错误码: %d, SN: %s", errcode, device_sn)       
            # 尝试重新发送命令，可能是临时错误 
            if device_sn:
                _LOGGER.debug("尝试重新发送命令到设备: %s", device_sn)

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
                # 统一存储为 voltage，与网关上 报保持一致
                battery = data["battery"]      
                # 转换为浮点数并除以10（如105 → 10.5V）
                voltage = float(battery) / 10  
                attributes["voltage"] = voltage
                _LOGGER.debug("设备 %s 电池电压: %.1fV", device_sn, voltage)
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
                        voltage = float(value) / 10
                        attributes["voltage"] = voltage
                    elif attribute == "r_travel":
                        # 处理窗户状态，0表示关闭，其他表示打开
                        travel_value = int(value)
                        attributes["r_travel"] = travel_value
                        # 根据r_travel设置状态 
                        if travel_value == 0:  
                            status = "closed"  
                        else:
                            status = "open"    

            # 更新设备状态
            await self.device_manager.update_device_status(device_sn, status, attributes)     
            # 通知设备状态变化，触发传感器实体 更新
            self._notify_device_status_change(device_sn)
            _LOGGER.debug("设备上报处理完成: %s", device_sn)

    async def _handle_ctype_006(self, payload, ctype, data):
        """处理协议类型006：批量设备状态上报"""
        # 这里可以添加批量设备状态上报的处理逻 辑
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
        # MQTT订阅会在HA重启时自动清理，无需手 动处理
        return True
