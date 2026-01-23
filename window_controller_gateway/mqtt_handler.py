"""MQTT处理器 - 使用HA内置MQTT，符合新的主题规程"""
import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional

from homeassistant.core import HomeAssistant
from homeassistant.components import mqtt

from .const import (
    ATTR_DEVICE_SN,
    ATTR_DEVICE_NAME,
    ATTR_POSITION,
    ATTR_BATTERY,
    DEVICE_TYPE_WINDOW_OPENER
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
        
        # MQTT主题定义
        self.TOPIC_PLATFORM_REQ = "gateway/req"  # 订阅平台消息
        self.TOPIC_GATEWAY_REQ = f"gateway/{gateway_sn}/req"  # 发送命令到网关
        self.TOPIC_GATEWAY_RSP = "gateway/rpt_rsp"  # 接收网关响应和数据
        
        # 状态更新回调
        self._status_callbacks = []
    
    async def setup(self):
        """设置MQTT处理器"""
        _LOGGER.info("MQTT处理器初始化: %s", self.gateway_sn)
        
        # 检查MQTT集成是否可用
        if not self.hass.data.get("mqtt"):
            _LOGGER.error("MQTT集成未启用，请先在Home Assistant中启用MQTT集成")
            return False
            
        # 订阅主题
        await self._subscribe_topics()
        
        return True
    
    async def _subscribe_topics(self):
        """订阅MQTT主题"""
        # 订阅平台消息主题
        def handle_platform_message(msg):
            """处理平台消息"""
            try:
                payload = json.loads(msg.payload)
                _LOGGER.debug("收到平台消息: %s", payload)
                
                # 提取消息类型
                msg_type = payload.get("type")
                
                if msg_type == "device_discovery":
                    # 处理设备发现消息
                    devices = payload.get("devices", [])
                    for device_info in devices:
                        device_sn = device_info.get(ATTR_DEVICE_SN)
                        device_name = device_info.get(ATTR_DEVICE_NAME, f"设备 {device_sn[-6:]}")
                        device_type = device_info.get("device_type", DEVICE_TYPE_WINDOW_OPENER)
                        
                        # 异步添加设备
                        self.hass.create_task(
                            self.device_manager.add_device(device_sn, device_name, device_type)
                        )
                        
                elif msg_type == "status":
                    # 处理状态更新消息
                    device_sn = payload.get(ATTR_DEVICE_SN)
                    if not device_sn:
                        return
                    
                    status = payload.get("status", "unknown")
                    attributes = {}
                    
                    # 提取属性
                    if ATTR_POSITION in payload:
                        attributes[ATTR_POSITION] = payload[ATTR_POSITION]
                    if ATTR_BATTERY in payload:
                        attributes[ATTR_BATTERY] = payload[ATTR_BATTERY]
                    
                    # 更新设备状态
                    self.hass.create_task(
                        self.device_manager.update_device_status(device_sn, status, attributes)
                    )
                    
                elif msg_type == "response":
                    # 处理命令响应消息
                    _LOGGER.debug("收到命令响应: %s", payload)
                    
            except Exception as e:
                _LOGGER.error("处理平台消息时出错: %s", e)
        
        await mqtt.async_subscribe(self.hass, self.TOPIC_PLATFORM_REQ, handle_platform_message, 1)
        _LOGGER.debug("订阅平台消息主题: %s", self.TOPIC_PLATFORM_REQ)
        
        # 订阅网关响应主题
        def handle_gateway_response(msg):
            """处理网关响应消息"""
            try:
                payload = json.loads(msg.payload)
                _LOGGER.debug("收到网关响应: %s", payload)
                
                # 检查是否是标准协议格式（带head和ctype字段）
                if "head" in payload and "ctype" in payload:
                    # 标准协议格式处理
                    ctype = payload.get("ctype")
                    data = payload.get("data", {})
                    
                    # 检查响应是否来自此网关
                    response_sn = payload.get("sn")
                    if not response_sn or response_sn != self.gateway_sn:
                        return
                    
                    # 处理协议类型001：绑定网关
                    if ctype == "001":
                        # 检查是否包含设备信息（vesion, model等字段）
                        if "vesion" in data or "model" in data or "userid" in data:
                            # 这是设备信息上报，不是绑定请求，只更新状态
                            _LOGGER.debug("收到网关设备信息: %s, 版本: %s", 
                                         self.gateway_sn, data.get("vesion"))
                            # 更新网关状态为在线
                            self.hass.create_task(
                                self.device_manager.update_gateway_status("online")
                            )
                            self.connected = True
                            self._notify_status_change()
                        elif "errcode" not in data:
                            # 网关主动发起绑定请求，需要发送响应
                            _LOGGER.info("收到网关绑定请求: %s", self.gateway_sn)
                            
                            # 构建响应消息
                            response_payload = {
                                "head": "$SH",
                                "ctype": "001",
                                "id": payload.get("id", 0),
                                "sn": self.gateway_sn,
                                "data": {
                                    "errcode": 0,
                                    "devtype": "gateway",
                                    "sn": self.gateway_sn
                                }
                            }
                            
                            # 发送响应到网关 - 使用create_task替代async_create_task，避免线程安全问题
                            self.hass.create_task(
                                mqtt.async_publish(
                                    self.hass,
                                    self.TOPIC_GATEWAY_RSP,
                                    json.dumps(response_payload),
                                    1,
                                    False
                                )
                            )
                            _LOGGER.info("发送网关绑定响应成功: %s", self.gateway_sn)
                            
                            # 更新网关状态
                            self.hass.create_task(
                                self.device_manager.update_gateway_status("online")
                            )
                            self.connected = True
                            self._notify_status_change()
                        else:
                            # 处理网关响应（可能来自其他系统）
                            errcode = data.get("errcode", -1)
                            if errcode == 0:
                                _LOGGER.info("网关绑定成功: %s", self.gateway_sn)
                                self.hass.create_task(
                                    self.device_manager.update_gateway_status("online")
                                )
                                self.connected = True
                                self._notify_status_change()
                            else:
                                _LOGGER.error("网关绑定失败，错误码: %d", errcode)
                                self.connected = False
                                self._notify_status_change()
                    
                    # 处理协议类型002：网关状态上报
                    elif ctype == "002":
                        status = data.get("status", "unknown")
                        _LOGGER.debug("网关状态上报: %s", status)
                        # 使用async_create_task包装异步操作
                        self.hass.create_task(
                            self.device_manager.update_gateway_status(status)
                        )
                        self.connected = status == "online"
                        self._notify_status_change()
                    
                    # 处理协议类型003：绑定子设备
                    elif ctype == "003":
                        errcode = data.get("errcode", -1)
                        device_sn = data.get("sn")
                        
                        if errcode == 0 and device_sn:
                            # 绑定成功，添加设备
                            device_name = f"开窗器 {device_sn[-3:]}"
                            self.hass.create_task(
                                self.device_manager.add_device(device_sn, device_name, DEVICE_TYPE_WINDOW_OPENER)
                            )
                            _LOGGER.info("设备绑定成功: %s", device_sn)
                        else:
                            _LOGGER.error("设备绑定失败，错误码: %d, SN: %s", errcode, device_sn)
                    
                    # 处理协议类型004：设备控制响应
                    elif ctype == "004":
                        errcode = data.get("errcode", -1)
                        device_sn = data.get("sn")
                        if errcode == 0 and device_sn:
                            _LOGGER.debug("设备控制成功: %s", device_sn)
                        else:
                            _LOGGER.error("设备控制失败，错误码: %d, SN: %s", errcode, device_sn)
                    
                    # 处理协议类型005：设备上报
                    elif ctype == "005":
                        device_sn = data.get("sn")
                        if device_sn:
                            # 解析设备上报的状态
                            status = data.get("status", "unknown")
                            attributes = {}
                            
                            # 提取上报的属性
                            if "position" in data:
                                attributes[ATTR_POSITION] = data["position"]
                            if "battery" in data:
                                attributes[ATTR_BATTERY] = data["battery"]
                            if "state" in data:
                                attributes["state"] = data["state"]
                            
                            # 更新设备状态
                            self.hass.create_task(
                                self.device_manager.update_device_status(device_sn, status, attributes)
                            )
                            _LOGGER.debug("设备上报处理完成: %s", device_sn)
                    
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
                        
                        self.hass.create_task(
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
                    
                    self.hass.create_task(
                        self.device_manager.update_device_status(device_sn, status, attributes)
                    )
                    
            except Exception as e:
                _LOGGER.error("处理网关响应时出错: %s", e)
        
        await mqtt.async_subscribe(self.hass, self.TOPIC_GATEWAY_RSP, handle_gateway_response, 1)
        _LOGGER.debug("订阅网关响应主题: %s", self.TOPIC_GATEWAY_RSP)
    
    async def send_command(self, device_sn: str, command: str, params: Optional[Dict[str, Any]] = None):
        """发送命令到设备"""
        # 根据协议文档，使用标准的协议格式
        command_map = {
            "bind_gateway": "001",  # 001: 绑定网关
            "start_pairing": "003",  # 003: 绑定子设备
            "discover": "002",  # 002: 网关状态上报/设备发现
            "open": "004",  # 004: 设备控制
            "close": "004",  # 004: 设备控制
            "stop": "004",  # 004: 设备控制
            "set_position": "004"  # 004: 设备控制
        }
        
        ctype = command_map.get(command, "004")
        
        # 构建协议格式的payload
        payload = {
            "head": "$SH",
            "ctype": ctype,
            "id": int(datetime.now().timestamp() * 1000),  # 使用时间戳作为ID
            "sn": self.gateway_sn,
            "data": {
                "devtype": "window_opener"
                # 配对模式下不包含子设备SN，因为此时还没有具体的子设备
            }
        }
        
        # 添加额外参数
        if params:
            payload["data"].update(params)
        
        # 根据命令类型添加特定参数
        if command == "start_pairing":
            payload["data"]["bind"] = 1  # 1表示绑定
            # 配对模式下不包含子设备SN
        elif command in ["open", "close", "stop", "set_position"]:
            # 控制命令需要包含子设备SN
            payload["data"]["sn"] = device_sn
            payload["data"]["action"] = command  # 设备控制动作
        elif command != "start_pairing":
            # 其他命令需要包含子设备SN
            payload["data"]["sn"] = device_sn
        
        await mqtt.async_publish(
            self.hass,
            self.TOPIC_GATEWAY_REQ,
            json.dumps(payload),
            1,
            False
        )
        _LOGGER.info("发送协议命令: %s (类型: %s) 到设备: %s, 参数: %s", command, ctype, device_sn, payload["data"])
    
    def add_status_callback(self, callback):
        """添加状态更新回调"""
        if callback not in self._status_callbacks:
            self._status_callbacks.append(callback)
    
    def remove_status_callback(self, callback):
        """移除状态更新回调"""
        if callback in self._status_callbacks:
            self._status_callbacks.remove(callback)
    
    def _notify_status_change(self):
        """通知状态变化 - 确保在事件循环线程中执行回调"""
        for callback in self._status_callbacks:
            try:
                # 使用hass.add_job确保在事件循环线程中执行回调
                self.hass.add_job(callback)
            except Exception as e:
                _LOGGER.error("调用状态回调失败: %s", e)
    
    async def check_connection(self):
        """检查MQTT连接状态"""
        try:
            # 发送一个心跳消息检查连接
            payload = {
                "gateway_sn": self.gateway_sn,
                "type": "heartbeat",
                "timestamp": datetime.now().isoformat()
            }
            
            await mqtt.async_publish(
                self.hass,
                self.TOPIC_GATEWAY_REQ,
                json.dumps(payload),
                1,
                False
            )
            
            # 只有当连接状态改变时才通知
            if not self.connected:
                self.connected = True
                _LOGGER.debug("MQTT连接状态正常")
                self._notify_status_change()
                
                # 更新网关状态
                self.hass.create_task(
                    self.device_manager.update_gateway_status("online")
                )
        except Exception as e:
            _LOGGER.error("MQTT连接检查失败: %s", e)
            
            # 只有当连接状态改变时才通知
            if self.connected:
                self.connected = False
                self._notify_status_change()
                
                # 更新网关状态
                self.hass.create_task(
                    self.device_manager.update_gateway_status("offline")
                )
        
        return self.connected
    
    async def start_pairing(self, duration: int = 60):
        """开始配对 - 使用协议类型003"""
        # 使用send_command方法发送符合协议要求的配对命令
        await self.send_command(
            self.gateway_sn,  # 使用网关SN作为设备SN
            "start_pairing",
            {"duration": duration}  # 添加持续时间参数
        )
        
        # 更新配对状态
        self.pairing_active = True
        self._notify_status_change()
        
        # 更新网关状态
        self.hass.create_task(
            self.device_manager.update_gateway_status("pairing")
        )
        
        _LOGGER.info("配对命令已发送，持续时间: %d秒", duration)
        
        # 设置定时器，在配对超时后恢复状态
        async def pairing_timeout():
            self.pairing_active = False
            self._notify_status_change()
            self.hass.create_task(
                self.device_manager.update_gateway_status("online" if self.connected else "offline")
            )
            _LOGGER.info("配对模式已超时，恢复正常状态")
        
        # 延迟执行超时回调
        self.hass.loop.call_later(duration, lambda: self.hass.create_task(pairing_timeout()))
    
    async def trigger_discovery(self):
        """触发设备发现 - 使用协议类型002"""
        # 使用send_command方法发送符合协议要求的设备发现命令
        await self.send_command(
            self.gateway_sn,  # 使用网关SN作为设备SN
            "discover"
        )
        _LOGGER.info("设备发现命令已发送")
    
    async def cleanup(self):
        """清理MQTT资源"""
        _LOGGER.info("清理MQTT资源")
        # MQTT订阅会在HA重启时自动清理，无需手动处理
        return True
