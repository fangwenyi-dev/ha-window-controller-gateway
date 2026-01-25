"""MQTT处理器 - 使用HA内置MQTT，符合新的主题规程"""
import logging
import json
import asyncio
import random
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
        self.last_gateway_report_time = None  # 最后收到网关002上报的时间
        self.command_id = 1  # 命令ID初始值
        
        # MQTT主题定义 - 根据协议要求简化为两个主题
        self.TOPIC_GATEWAY_REQ = f"gateway/{gateway_sn}/req"  # 发送命令到网关
        self.TOPIC_GATEWAY_RSP = "gateway/rpt_rsp"  # 接收网关数据和响应，同时用于发送响应
        
        # 状态更新回调 - 使用字典按设备SN组织回调
        self._status_callbacks = {}
    
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
        self.hass.loop.create_task(self._check_gateway_timeout())
        
        return True
    
    async def _check_gateway_timeout(self):
        """检查网关是否超时未上报"""
        while True:
            await asyncio.sleep(30)  # 每30秒检查一次
            try:
                # 检查是否超过20分钟没有收到上报
                if self.last_gateway_report_time:
                    time_diff = datetime.now() - self.last_gateway_report_time
                    if time_diff.total_seconds() > 1200:  # 20分钟 = 1200秒
                        if self.connected:
                            self.connected = False
                            self._notify_status_change()
                            _LOGGER.warning("网关 %s 超过20分钟未上报，标记为离线", self.gateway_sn)
                            self.hass.create_task(
                                self.device_manager.update_gateway_status("offline")
                            )
            except Exception as e:
                _LOGGER.error("检查网关超时出错: %s", e)
    
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
                    if not response_sn or response_sn != self.gateway_sn:
                        return
                    
                    # 更新最后上报时间 - 只要收到网关消息就认为在线
                    self.last_gateway_report_time = datetime.now()
                    
                    # 处理协议类型001：绑定网关
                    if ctype == "001":
                        # 检查是否包含设备信息（vesion, model等字段）
                        if "vesion" in data or "model" in data or "userid" in data:
                            # 这是设备信息上报，需要回复001
                            _LOGGER.debug("收到网关设备信息: %s, 版本: %s", 
                                         self.gateway_sn, data.get("vesion"))
                            
                            # 构建响应消息 - 按照协议要求回复001
                            response_payload = {
                                "head": "$SH",
                                "ctype": "001",
                                "id": payload.get("id", 0),
                                "sn": self.gateway_sn,
                                "data": {
                                    "errcode": 0,
                                    "uuid": "4bc297c6-308d-4397-b1d6-2ef6ccc329d3"
                                }
                            }
                            
                            # 发送响应到网关 - 按照协议要求发送到gateway/<sn>/req主题
                            self.hass.create_task(
                                mqtt.async_publish(
                                    self.hass,
                                    self.TOPIC_GATEWAY_REQ,
                                    json.dumps(response_payload),
                                    1,
                                    False
                                )
                            )
                            _LOGGER.info("发送网关设备信息响应成功到主题: %s", self.TOPIC_GATEWAY_REQ)
                            
                            # 更新网关状态为在线
                            self.hass.create_task(
                                self.device_manager.update_gateway_status("online")
                            )
                            self.connected = True
                            self._notify_status_change()
                        elif "errcode" not in data:
                            # 网关主动发起绑定请求，需要发送响应
                            _LOGGER.info("收到网关绑定请求: %s", self.gateway_sn)
                            
                            # 构建响应消息 - 按照协议要求回复001
                            response_payload = {
                                "head": "$SH",
                                "ctype": "001",
                                "id": payload.get("id", 0),
                                "sn": self.gateway_sn,
                                "data": {
                                    "errcode": 0,
                                    "uuid": "4bc297c6-308d-4397-b1d6-2ef6ccc329d3"
                                }
                            }
                            
                            # 发送响应到网关 - 按照协议要求发送到gateway/<sn>/req主题
                            self.hass.create_task(
                                mqtt.async_publish(
                                    self.hass,
                                    self.TOPIC_GATEWAY_REQ,
                                    json.dumps(response_payload),
                                    1,
                                    False
                                )
                            )
                            _LOGGER.info("发送网关绑定响应成功到主题: %s", self.TOPIC_GATEWAY_REQ)
                            
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
                        self.connected = True  # 收到上报就认为在线
                        self._notify_status_change()
                        
                        # 处理设备列表信息
                        if "devices" in data:
                            devices = data["devices"]
                            for device_info in devices:
                                device_sn = device_info.get("sn")
                                if device_sn:
                                    # 提取设备属性
                                    attributes = {}
                                    
                                    # 处理电池电压
                                    if "battery" in device_info:
                                        battery = device_info["battery"]
                                        # 转换为浮点数并除以10（如105 → 10.5V）
                                        voltage = float(battery) / 10
                                        attributes["voltage"] = voltage
                                        _LOGGER.debug("设备 %s 电池电压: %.1fV", device_sn, voltage)
                                    
                                    # 处理位置状态
                                    if "r_travel" in device_info:
                                        r_travel = device_info["r_travel"]
                                        attributes["r_travel"] = r_travel
                                        _LOGGER.debug("设备 %s 位置状态: %d", device_sn, r_travel)
                                    
                                    # 更新设备状态
                                    if attributes:
                                        # 确定设备状态
                                        device_status = "closed" if attributes.get("r_travel") == 0 else "open"
                                        self.hass.create_task(
                                            self.device_manager.update_device_status(device_sn, device_status, attributes)
                                        )
                                        # 通知设备状态变化，触发传感器实体更新
                                        self._notify_device_status_change(device_sn)
                        
                        # 构建002响应
                        response_payload = {
                            "head": "$SH",
                            "ctype": "002",
                            "id": payload.get("id", 0),
                            "sn": self.gateway_sn,
                            "data": {
                                "errcode": 0
                            }
                        }
                        
                        # 发送响应到网关 - 按照协议要求发送到gateway/<sn>/req主题
                        self.hass.create_task(
                            mqtt.async_publish(
                                self.hass,
                                self.TOPIC_GATEWAY_REQ,
                                json.dumps(response_payload),
                                1,
                                False
                            )
                        )
                        _LOGGER.info("发送网关状态上报响应成功到主题: %s", self.TOPIC_GATEWAY_REQ)
                    
                    # 处理协议类型003：绑定子设备
                    elif ctype == "003":
                        errcode = data.get("errcode", -1)
                        device_sn = data.get("sn")
                        
                        if errcode == 0 and device_sn:
                            # 绑定成功，添加设备
                            # 计算设备序号，从01开始
                            device_count = len(self.device_manager.get_all_devices())
                            device_number = device_count + 1
                            device_name = f"开窗器 {device_number:02d}"
                            self.hass.create_task(
                                self.device_manager.add_device(device_sn, device_name, DEVICE_TYPE_WINDOW_OPENER)
                            )
                            _LOGGER.info("设备绑定成功: %s, 名称: %s", device_sn, device_name)
                        else:
                            _LOGGER.error("设备绑定失败，错误码: %d, SN: %s", errcode, device_sn)
                    
                    # 处理协议类型004：设备控制响应
                    elif ctype == "004":
                        errcode = data.get("errcode", -1)
                        device_sn = data.get("sn")
                        if errcode == 0:
                            if device_sn:
                                _LOGGER.debug("设备控制成功: %s", device_sn)
                            else:
                                _LOGGER.debug("设备控制成功，但未返回设备SN")
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
                                # 统一存储为 voltage，与网关上报保持一致
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
                            self.hass.create_task(
                                self.device_manager.update_device_status(device_sn, status, attributes)
                            )
                            # 通知设备状态变化，触发传感器实体更新
                            self._notify_device_status_change(device_sn)
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
                _LOGGER.error("处理网关消息时出错: %s", e)
        
        await mqtt.async_subscribe(self.hass, self.TOPIC_GATEWAY_RSP, handle_gateway_response, 1)
        _LOGGER.debug("订阅网关消息主题: %s", self.TOPIC_GATEWAY_RSP)
    
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
            "id": self.command_id,  # 使用自增ID
            "data": {
            }
        }
        # 递增ID，确保不超过26位
        self.command_id += 1
        if self.command_id > 99999999999999999999999999:  # 26位最大值
            self.command_id = 1
        # 添加sn字段到payload的末尾
        payload["sn"] = self.gateway_sn
        
        # 添加额外参数
        if params:
            payload["data"].update(params)
        
        # 根据命令类型添加特定参数
        if command == "start_pairing":
            # 清空data并设置正确的配对参数
            payload["data"] = {
                "bind": 1,  # 新增字段
                "devtype": "curtain_ctr",  # 配对命令需要devtype为curtain_ctr
                "sn": "FFFFFFFFFFFF"  # 配对模式下使用固定SN
            }
            # 在顶层也添加bind字段
            payload["bind"] = 1
        elif command in ["open", "close", "stop", "a"]:
            # 控制命令需要包含子设备SN
            payload["data"]["sn"] = device_sn
            payload["data"]["attribute"] = "w_travel"
            if command == "open":
                payload["data"]["value"] = "100"
            elif command == "close":
                payload["data"]["value"] = "0"
            elif command == "stop":
                payload["data"]["value"] = "101"
            elif command == "a":
                payload["data"]["value"] = "200"
        elif command == "set_position":
            # 设置位置命令
            payload["data"]["sn"] = device_sn
            payload["data"]["attribute"] = "w_travel"
            position = params.get("position", 0)
            payload["data"]["value"] = str(position)
        
        await mqtt.async_publish(
            self.hass,
            self.TOPIC_GATEWAY_REQ,
            json.dumps(payload),
            1,
            False
        )
        _LOGGER.info("发送协议命令: %s (类型: %s) 到设备: %s, 参数: %s", command, ctype, device_sn, payload["data"])
    
    def add_status_callback(self, *args):
        """添加状态更新回调
        
        支持两种调用方式：
        1. add_status_callback(device_sn, callback) - 为特定设备添加回调
        2. add_status_callback(callback) - 为网关添加回调
        """
        if len(args) == 2:
            # 为特定设备添加回调
            device_sn, callback = args
            if device_sn not in self._status_callbacks:
                self._status_callbacks[device_sn] = []
            if callback not in self._status_callbacks[device_sn]:
                self._status_callbacks[device_sn].append(callback)
                _LOGGER.debug("为设备 %s 添加状态更新回调", device_sn)
        elif len(args) == 1:
            # 为网关添加回调（向后兼容）
            callback = args[0]
            # 使用特殊键 "gateway" 存储网关回调
            if "gateway" not in self._status_callbacks:
                self._status_callbacks["gateway"] = []
            if callback not in self._status_callbacks["gateway"]:
                self._status_callbacks["gateway"].append(callback)
                _LOGGER.debug("为网关添加状态更新回调")
    
    def remove_status_callback(self, *args):
        """移除状态更新回调
        
        支持两种调用方式：
        1. remove_status_callback(device_sn, callback) - 移除特定设备的回调
        2. remove_status_callback(callback) - 移除网关的回调
        """
        if len(args) == 2:
            # 移除特定设备的回调
            device_sn, callback = args
            if device_sn in self._status_callbacks:
                if callback in self._status_callbacks[device_sn]:
                    self._status_callbacks[device_sn].remove(callback)
                    _LOGGER.debug("从设备 %s 移除状态更新回调", device_sn)
        elif len(args) == 1:
            # 移除网关的回调（向后兼容）
            callback = args[0]
            if "gateway" in self._status_callbacks:
                if callback in self._status_callbacks["gateway"]:
                    self._status_callbacks["gateway"].remove(callback)
                    _LOGGER.debug("从网关移除状态更新回调")
    
    def _notify_status_change(self):
        """通知状态变化 - 确保在事件循环线程中执行回调"""
        # 此方法现在用于网关状态变化通知
        # 设备状态变化通知使用 _notify_device_status_change
        
        # 通知网关状态回调
        gateway_callbacks = self._status_callbacks.get("gateway", [])
        for callback in gateway_callbacks:
            try:
                # 使用hass.add_job确保在事件循环线程中执行回调
                self.hass.add_job(callback)
            except Exception as e:
                _LOGGER.error("调用网关状态回调失败: %s", e)
    
    def _notify_device_status_change(self, device_sn):
        """通知设备状态变化 - 确保在事件循环线程中执行回调"""
        if device_sn in self._status_callbacks:
            for callback in self._status_callbacks[device_sn]:
                try:
                    # 使用hass.add_job确保在事件循环线程中执行回调
                    self.hass.add_job(callback)
                    _LOGGER.debug("通知设备 %s 状态更新回调", device_sn)
                except Exception as e:
                    _LOGGER.error("调用设备状态回调失败: %s", e)
    
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
            "start_pairing"
            # 配对命令不需要duration参数
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
    
    async def unbind_device(self, device_sn: str):
        """解绑设备 - 使用协议类型003，bind=0"""
        # 构建符合协议要求的解绑命令
        payload = {
            "head": "$SH",
            "ctype": "003",
            "id": self.command_id,
            "data": {
                "bind": 1,
                "devtype": "curtain_ctr",
                "sn": device_sn
            },
            "sn": self.gateway_sn,
            "bind": 0  # 0代表解绑
        }
        # 递增ID
        self.command_id += 1
        if self.command_id > 99999999999999999999999999:
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
    
    async def cleanup(self):
        """清理MQTT资源"""
        _LOGGER.info("清理MQTT资源")
        # MQTT订阅会在HA重启时自动清理，无需手动处理
        return True
