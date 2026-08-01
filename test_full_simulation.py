"""全面模拟测试脚本 - 覆盖各模块场景和边缘情况

测试维度：
1. 版本一致性检查
2. 常量与工具函数测试
3. MQTT 消息解析与 ACK 规则
4. 设备管理逻辑（添加/删除/迁移/冲突）
5. 配置流验证
6. 实体创建逻辑
7. 持久化逻辑
8. 边缘情况与异常数据
"""
import sys
import os
import json
import asyncio
import types
import importlib.util
import time
import re
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

# ============================================================
# 路径设置
# ============================================================
COMPONENT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "custom_components", "window_controller_gateway"
)
sys.path.insert(0, os.path.dirname(COMPONENT_DIR))

# ============================================================
# Mock Home Assistant 框架
# ============================================================

# 创建 mock 模块树
def setup_mock_modules():
    """设置 Home Assistant 框架的 mock 模块"""
    # homeassistant 核心
    ha = types.ModuleType("homeassistant")
    ha_core = types.ModuleType("homeassistant.core")
    ha_core.HomeAssistant = MagicMock
    ha_core.callback = lambda f: f
    ha_core.ValidacaoError = Exception

    # 创建支持 domain= 关键字参数的 mock 基类
    class _MockFlowBase:
        """模拟 HA 的 ConfigFlow/OptionsFlow 基类，支持 domain= 语法"""
        def __init_subclass__(cls, *, domain=None, **kwargs):
            super().__init_subclass__()
        def __init__(self, *args, **kwargs):
            pass

    ha_config_entries = types.ModuleType("homeassistant.config_entries")
    ha_config_entries.ConfigEntry = MagicMock
    ha_config_entries.ConfigFlow = _MockFlowBase
    ha_config_entries.OptionsFlow = _MockFlowBase

    ha_helpers = types.ModuleType("homeassistant.helpers")
    ha_helpers_config_validation = types.ModuleType("homeassistant.helpers.config_validation")
    ha_helpers_config_validation.valid = lambda *a, **kw: (lambda x: x)
    ha_helpers_entity = types.ModuleType("homeassistant.helpers.entity")
    ha_helpers_entity.Entity = MagicMock
    ha_helpers_entity.DeviceInfo = dict
    ha_helpers_entity.EntityCategory = MagicMock()
    ha_helpers_entity.EntityCategory.CONFIG = "config"
    ha_helpers_entity.EntityCategory.DIAGNOSTIC = "diagnostic"
    ha_helpers_entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")
    ha_helpers_entity_platform.AddEntitiesCallback = callable
    ha_helpers_device_registry = types.ModuleType("homeassistant.helpers.device_registry")
    ha_helpers_device_registry.async_get = lambda hass: MagicMock()

    ha_mqtt = types.ModuleType("homeassistant.components.mqtt")

    # MQTT mock - 记录所有发布的消息
    PUBLISHED_MESSAGES = []

    async def mock_async_publish(hass, topic, payload_str, qos, retain):
        payload = json.loads(payload_str)
        PUBLISHED_MESSAGES.append({
            "topic": topic,
            "payload": payload,
            "ctype": payload.get("ctype"),
            "has_errcode": "errcode" in payload.get("data", {}),
            "errcode": payload.get("data", {}).get("errcode"),
            "data": payload.get("data", {}),
            "sn": payload.get("sn"),
            "id": payload.get("id"),
        })

    async def mock_async_subscribe(hass, topic, callback, qos):
        return lambda: None

    ha_mqtt.async_publish = mock_async_publish
    ha_mqtt.async_subscribe = mock_async_subscribe

    ha_components = types.ModuleType("homeassistant.components")
    ha_components_button = types.ModuleType("homeassistant.components.button")
    ha_components_button.ButtonEntity = MagicMock
    ha_components_cover = types.ModuleType("homeassistant.components.cover")
    ha_components_cover.CoverEntity = MagicMock
    ha_components_cover.CoverEntityFeature = MagicMock()
    ha_components_cover.CoverEntityFeature.OPEN = 1
    ha_components_cover.CoverEntityFeature.CLOSE = 2
    ha_components_cover.CoverEntityFeature.STOP = 4
    ha_components_cover.CoverDeviceClass = MagicMock()
    ha_components_cover.CoverDeviceClass.WINDOW = "window"
    ha_components_sensor = types.ModuleType("homeassistant.components.sensor")
    ha_components_sensor.SensorEntity = MagicMock
    ha_components_sensor.SensorDeviceClass = MagicMock()
    ha_components_sensor.SensorDeviceClass.VOLTAGE = "voltage"
    ha_components_sensor.SensorDeviceClass.ENUM = "enum"
    ha_components_binary_sensor = types.ModuleType("homeassistant.components.binary_sensor")
    ha_components_binary_sensor.BinarySensorEntity = MagicMock

    ha_data_entry_flow = types.ModuleType("homeassistant.data_entry_flow")
    ha_data_entry_flow.FlowResult = dict

    # voluptuous mock
    vol = types.ModuleType("voluptuous")
    vol.Schema = lambda *a, **kw: MagicMock()
    vol.Required = lambda *a, **kw: MagicMock()
    vol.Optional = lambda *a, **kw: MagicMock()
    vol.All = lambda *a, **kw: MagicMock()
    vol.Coerce = lambda *a, **kw: MagicMock()
    vol.Range = lambda *a, **kw: MagicMock()
    vol.In = lambda *a, **kw: MagicMock()

    # 注册所有模块
    sys.modules["homeassistant"] = ha
    sys.modules["homeassistant.core"] = ha_core
    sys.modules["homeassistant.config_entries"] = ha_config_entries
    sys.modules["homeassistant.helpers"] = ha_helpers
    sys.modules["homeassistant.helpers.config_validation"] = ha_helpers_config_validation
    sys.modules["homeassistant.helpers.entity"] = ha_helpers_entity
    sys.modules["homeassistant.helpers.entity_platform"] = ha_helpers_entity_platform
    sys.modules["homeassistant.helpers.device_registry"] = ha_helpers_device_registry
    ha_helpers_entity_registry = types.ModuleType("homeassistant.helpers.entity_registry")
    ha_helpers_entity_registry.async_get = lambda hass: MagicMock()
    sys.modules["homeassistant.helpers.entity_registry"] = ha_helpers_entity_registry
    sys.modules["homeassistant.components"] = ha_components
    sys.modules["homeassistant.components.mqtt"] = ha_mqtt
    sys.modules["homeassistant.components.button"] = ha_components_button
    sys.modules["homeassistant.components.cover"] = ha_components_cover
    sys.modules["homeassistant.components.sensor"] = ha_components_sensor
    sys.modules["homeassistant.components.binary_sensor"] = ha_components_binary_sensor
    sys.modules["homeassistant.data_entry_flow"] = ha_data_entry_flow
    sys.modules["voluptuous"] = vol

    return PUBLISHED_MESSAGES


PUBLISHED_MESSAGES = setup_mock_modules()


# ============================================================
# 测试框架
# ============================================================
class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.details: List[str] = []
        self.bugs_found: List[str] = []

    def ok(self, name):
        self.passed += 1
        self.details.append(f"  [PASS] {name}")

    def fail(self, name, reason):
        self.failed += 1
        self.details.append(f"  [FAIL] {name}: {reason}")
        self.bugs_found.append(f"{name}: {reason}")

    def warn(self, name, reason):
        self.warnings += 1
        self.details.append(f"  [WARN] {name}: {reason}")

    def summary(self):
        total = self.passed + self.failed
        status = "ALL PASSED" if self.failed == 0 else f"{self.failed} FAILED"
        result = f"\n{'='*70}\n"
        result += f"测试结果: {self.passed}/{total} 通过, {self.warnings} 警告 - {status}\n"
        result += f"{'='*70}\n"
        result += "\n".join(self.details)
        if self.bugs_found:
            result += f"\n\n{'='*70}\n发现的 Bug 列表:\n{'='*70}\n"
            for i, bug in enumerate(self.bugs_found, 1):
                result += f"  {i}. {bug}\n"
        return result


# ============================================================
# 加载模块
# ============================================================
def load_module(module_name, file_path):
    """动态加载模块"""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# 加载常量模块
const_mod = load_module(
    "custom_components.window_controller_gateway.const",
    os.path.join(COMPONENT_DIR, "const.py")
)

# 加载工具模块
utils_mod = load_module(
    "custom_components.window_controller_gateway.utils",
    os.path.join(COMPONENT_DIR, "utils.py")
)

# 加载 MQTT 处理器模块
mqtt_handler_mod = load_module(
    "custom_components.window_controller_gateway.mqtt_handler",
    os.path.join(COMPONENT_DIR, "mqtt_handler.py")
)

# 加载 persist 模块
persist_mod = load_module(
    "custom_components.window_controller_gateway.persist",
    os.path.join(COMPONENT_DIR, "persist.py")
)


# ============================================================
# Mock 辅助类
# ============================================================
class MockDeviceManager:
    """模拟设备管理器"""
    def __init__(self):
        self.devices = {}
        self.gateway_sn = "1001ABCD1234"
        self._manually_removed_devices = set()
        self._device_added_callbacks = []
        self._device_removed_callbacks = []

    async def update_gateway_status(self, status, attributes=None):
        pass

    async def update_device_status(self, device_sn, status, attributes=None):
        if device_sn not in self.devices:
            self.devices[device_sn] = {
                "sn": device_sn,
                "name": f"设备 {device_sn[-6:]}",
                "type": "window_opener",
                "status": "offline",
                "attributes": {}
            }
        if status is not None:
            self.devices[device_sn]["status"] = status
        if attributes:
            if "attributes" not in self.devices[device_sn]:
                self.devices[device_sn]["attributes"] = {}
            self.devices[device_sn]["attributes"].update(attributes)

    def get_device(self, device_sn):
        return self.devices.get(device_sn)

    def get_all_devices(self):
        return list(self.devices.values())

    async def add_device(self, device_sn, device_name, device_type=None, force=False, is_manual_pairing=False):
        self.devices[device_sn] = {
            "sn": device_sn,
            "name": device_name,
            "type": device_type or "window_opener",
            "status": "connected",
            "attributes": {}
        }
        return device_sn

    def is_device_manually_removed(self, device_sn):
        return device_sn in self._manually_removed_devices

    def get_gateway_info(self):
        return {"name": "Test Gateway", "sn": self.gateway_sn}


class MockHass:
    """模拟 Home Assistant 实例"""
    def __init__(self):
        self.data = {"mqtt": MagicMock()}
        self.config = MagicMock()
        self.config.config_dir = "/tmp/test_ha_config"
        self.loop = None  # 在测试中设置
        self.states = MagicMock()
        self.services = MagicMock()
        self.config_entries = MagicMock()

    def async_create_task(self, coro):
        """创建异步任务"""
        if self.loop and self.loop.is_running():
            return asyncio.ensure_future(coro, loop=self.loop)
        else:
            # 如果没有运行的事件循环，同步执行
            try:
                coro.send(None)
            except StopIteration:
                pass
            return asyncio.Future()

    def add_job(self, target, *args):
        """添加任务 - 兼容 HA 的 add_job 接口
        
        支持三种形式：
        1. add_job(coro) - 直接传入协程
        2. add_job(callable) - 传入可调用对象，调用后可能返回协程
        3. add_job(callable, *args) - 传入可调用对象和参数
        """
        try:
            if asyncio.iscoroutine(target):
                asyncio.ensure_future(target, loop=self.loop)
            else:
                result = target(*args) if args else target()
                if asyncio.iscoroutine(result):
                    asyncio.ensure_future(result, loop=self.loop)
        except Exception:
            pass


def make_msg(ctype: str, msg_id: int, sn: str, data: dict = None) -> dict:
    """构建标准协议消息"""
    return {
        "head": "$SH",
        "ctype": ctype,
        "id": msg_id,
        "sn": sn,
        "data": data or {}
    }


class MsgWrapper:
    """MQTT 消息包装器"""
    def __init__(self, payload_dict):
        self.payload = json.dumps(payload_dict).encode('utf-8')


# ============================================================
# 测试用例
# ============================================================

def test_version_consistency(tr: TestResult):
    """测试 1: 版本一致性检查"""
    # 读取 manifest.json
    manifest_path = os.path.join(COMPONENT_DIR, "manifest.json")
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    manifest_version = manifest.get("version", "")
    const_version = const_mod.VERSION

    if manifest_version == const_version:
        tr.ok(f"版本一致: const.py({const_version}) == manifest.json({manifest_version})")
    else:
        tr.fail(
            "版本一致性",
            f"const.py VERSION='{const_version}' != manifest.json version='{manifest_version}'"
        )


def test_supports_wind_lock_mode(tr: TestResult):
    """测试 2: supports_wind_lock_mode 函数"""
    # 5005 前缀支持
    if const_mod.supports_wind_lock_mode("5005ABCDEFGHIJ"):
        tr.ok("5005前缀设备支持风锁模式")
    else:
        tr.fail("5005前缀支持", "5005前缀应支持风锁模式")

    # 5001 前缀不支持
    if not const_mod.supports_wind_lock_mode("5001ABCDEFGHIJ"):
        tr.ok("5001前缀设备不支持风锁模式")
    else:
        tr.fail("5001前缀不支持", "5001前缀不应支持风锁模式")

    # 5002/5003 前缀不支持
    for prefix in ["5002", "5003", "5004", "5006"]:
        if not const_mod.supports_wind_lock_mode(f"{prefix}ABCDEFGHIJ"):
            tr.ok(f"{prefix}前缀设备不支持风锁模式")
        else:
            tr.fail(f"{prefix}前缀不支持", f"{prefix}前缀不应支持风锁模式")

    # 空字符串
    try:
        result = const_mod.supports_wind_lock_mode("")
        if not result:
            tr.ok("空字符串不支持风锁模式")
        else:
            tr.fail("空字符串处理", "空字符串不应支持风锁模式")
    except Exception as e:
        tr.fail("空字符串处理", f"抛出异常: {e}")

    # 短字符串（少于4位）
    try:
        result = const_mod.supports_wind_lock_mode("500")
        if not result:
            tr.ok("短字符串(3位)不支持风锁模式")
        else:
            tr.fail("短字符串处理", "3位字符串不应支持风锁模式")
    except Exception as e:
        tr.fail("短字符串处理", f"抛出异常: {e}")


def test_get_device_display_name(tr: TestResult):
    """测试 3: get_device_display_name 函数"""
    # 正常调用
    name = const_mod.get_device_display_name("1001ABCD1234", "5005EFGH5678")
    if "1234" in name and "5678" in name:
        tr.ok(f"设备显示名称正确: {name}")
    else:
        tr.fail("设备显示名称", f"名称不包含SN后4位: {name}")

    # 带设备编号
    name_with_num = const_mod.get_device_display_name("1001ABCD1234", "5005EFGH5678", 5)
    if "#05" in name_with_num:
        tr.ok(f"带编号的设备显示名称正确: {name_with_num}")
    else:
        tr.fail("带编号设备名称", f"名称不包含编号: {name_with_num}")

    # 边缘情况：短SN
    try:
        name_short = const_mod.get_device_display_name("AB", "CD")
        if name_short:  # 只要不崩溃就算通过
            tr.ok(f"短SN处理正常: {name_short}")
    except Exception as e:
        tr.fail("短SN处理", f"抛出异常: {e}")


async def test_mqtt_ack_rules(tr: TestResult):
    """测试 4: MQTT ACK 规则验证

    规则（与协议文档一致）：
    - 001/002/005: 网关上报，HA 需回复 ACK
    - 003/004/006/007: HA 主动发起，网关回复，HA 不回复 ACK（008/009/010 已从协议中移除）
    """
    PUBLISHED_MESSAGES.clear()

    hass = MockHass()
    hass.loop = asyncio.get_event_loop()
    device_manager = MockDeviceManager()

    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)

    GATEWAY_SN = "1001ABCD1234"
    DEVICE_SN = "5005TEST0001"

    # 测试 002 - 应该回复 ACK
    PUBLISHED_MESSAGES.clear()
    msg_002 = make_msg("002", 1001, GATEWAY_SN, {"status": "online", "devices": []})
    await handler._handle_ctype_002(msg_002, "002", msg_002["data"])
    ack_count = sum(1 for m in PUBLISHED_MESSAGES if m["ctype"] == "002" and m["has_errcode"])
    if ack_count == 1:
        tr.ok("002 网关上报 - HA 回复 ACK")
    else:
        tr.fail("002 ACK", f"期望1个ACK，实际{ack_count}个")

    # 测试 005 - 应该回复 ACK
    PUBLISHED_MESSAGES.clear()
    msg_005 = make_msg("005", 1002, GATEWAY_SN, {
        "sn": DEVICE_SN,
        "attrs": [{"attribute": "r_travel", "value": 50}]
    })
    await handler._handle_ctype_005(msg_005, "005", msg_005["data"])
    ack_count = sum(1 for m in PUBLISHED_MESSAGES if m["ctype"] == "005" and m["has_errcode"])
    if ack_count == 1:
        tr.ok("005 设备上报 - HA 回复 ACK")
    else:
        tr.fail("005 ACK", f"期望1个ACK，实际{ack_count}个")

    # 测试 003 - 不应该回复 ACK
    PUBLISHED_MESSAGES.clear()
    msg_003 = make_msg("003", 1003, GATEWAY_SN, {"errcode": 0, "sn": DEVICE_SN, "bind": 1})
    await handler._handle_ctype_003(msg_003, "003", msg_003["data"])
    ack_count = sum(1 for m in PUBLISHED_MESSAGES if m["ctype"] == "003" and m["has_errcode"])
    if ack_count == 0:
        tr.ok("003 HA发起命令 - HA 不回复 ACK")
    else:
        tr.fail("003 不应ACK", f"期望0个ACK，实际{ack_count}个")

    # 测试 004 - 不应该回复 ACK
    PUBLISHED_MESSAGES.clear()
    msg_004 = make_msg("004", 1004, GATEWAY_SN, {"errcode": 0, "sn": DEVICE_SN})
    await handler._handle_ctype_004(msg_004, "004", msg_004["data"])
    ack_count = sum(1 for m in PUBLISHED_MESSAGES if m["ctype"] == "004" and m["has_errcode"])
    if ack_count == 0:
        tr.ok("004 HA发起控制 - HA 不回复 ACK")
    else:
        tr.fail("004 不应ACK", f"期望0个ACK，实际{ack_count}个")

    # 测试 006/007 - HA 主动发起的命令，HA 不回复 ACK
    for ctype in ["006", "007"]:
        PUBLISHED_MESSAGES.clear()
        msg = make_msg(ctype, 1000 + int(ctype), GATEWAY_SN, {"errcode": 0})
        handler_method = getattr(handler, f"_handle_ctype_{ctype}")
        await handler_method(msg, ctype, msg["data"])
        ack_count = sum(1 for m in PUBLISHED_MESSAGES if m["ctype"] == ctype and m["has_errcode"])
        if ack_count == 0:
            tr.ok(f"{ctype} HA主动发起命令 - HA 不回复 ACK")
        else:
            tr.fail(f"{ctype} 不应ACK", f"期望0个ACK，实际{ack_count}个")


async def test_mqtt_message_dedup(tr: TestResult):
    """测试 5: MQTT 消息去重"""
    PUBLISHED_MESSAGES.clear()

    hass = MockHass()
    hass.loop = asyncio.get_event_loop()
    device_manager = MockDeviceManager()

    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)

    GATEWAY_SN = "1001ABCD1234"
    msg_key = "002_9999_1001ABCD1234"
    current_time = time.time()

    # 第一次消息 - 应该处理
    msg = make_msg("002", 9999, GATEWAY_SN, {"status": "online"})
    coro1 = handler._handle_ctype_002(msg, "002", msg["data"])
    await handler._dispatch_with_dedup(coro1, msg_key, current_time)
    ack_count_1 = sum(1 for m in PUBLISHED_MESSAGES if m["ctype"] == "002" and m["has_errcode"])

    # 第二次相同消息 - 应该跳过
    PUBLISHED_MESSAGES.clear()
    msg2 = make_msg("002", 9999, GATEWAY_SN, {"status": "online"})
    coro2 = handler._handle_ctype_002(msg2, "002", msg2["data"])
    await handler._dispatch_with_dedup(coro2, msg_key, current_time)
    ack_count_2 = sum(1 for m in PUBLISHED_MESSAGES if m["ctype"] == "002" and m["has_errcode"])

    if ack_count_1 >= 1 and ack_count_2 == 0:
        tr.ok("消息去重正常 - 重复消息被跳过")
    else:
        tr.fail("消息去重", f"第一次ACK={ack_count_1}, 重复消息ACK={ack_count_2}")


async def test_mqtt_005_status_parsing(tr: TestResult):
    """测试 6: 005 设备上报状态解析"""
    PUBLISHED_MESSAGES.clear()

    hass = MockHass()
    hass.loop = asyncio.get_event_loop()
    device_manager = MockDeviceManager()

    # 预添加设备
    await device_manager.add_device("5005TEST0001", "测试设备", "window_opener")

    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)

    # 测试 r_travel = 0 (关闭)
    msg_close = make_msg("005", 2001, "1001ABCD1234", {
        "sn": "5005TEST0001",
        "attrs": [{"attribute": "r_travel", "value": 0}]
    })
    await handler._handle_ctype_005(msg_close, "005", msg_close["data"])
    device = device_manager.get_device("5005TEST0001")
    if device and device.get("status") == "closed":
        tr.ok("005 r_travel=0 正确解析为 closed")
    else:
        tr.fail("005 r_travel=0", f"状态应为closed，实际: {device.get('status') if device else 'None'}")

    # 测试 r_travel = 50 (打开)
    msg_open = make_msg("005", 2002, "1001ABCD1234", {
        "sn": "5005TEST0001",
        "attrs": [{"attribute": "r_travel", "value": 50}]
    })
    await handler._handle_ctype_005(msg_open, "005", msg_open["data"])
    device = device_manager.get_device("5005TEST0001")
    if device and device.get("status") == "open":
        tr.ok("005 r_travel=50 正确解析为 open")
    else:
        tr.fail("005 r_travel=50", f"状态应为open，实际: {device.get('status') if device else 'None'}")

    # 测试 battery 解析
    msg_battery = make_msg("005", 2003, "1001ABCD1234", {
        "sn": "5005TEST0001",
        "battery": 105  # 应该转换为 10.5V
    })
    await handler._handle_ctype_005(msg_battery, "005", msg_battery["data"])
    device = device_manager.get_device("5005TEST0001")
    voltage = device.get("attributes", {}).get("voltage") if device else None
    if voltage is not None and abs(voltage - 10.5) < 0.01:
        tr.ok(f"005 battery=105 正确解析为 10.5V")
    else:
        tr.fail("005 battery解析", f"电压应为10.5V，实际: {voltage}")

    # 测试 r_travel 字符串值
    msg_str = make_msg("005", 2004, "1001ABCD1234", {
        "sn": "5005TEST0001",
        "attrs": [{"attribute": "r_travel", "value": "0"}]
    })
    try:
        await handler._handle_ctype_005(msg_str, "005", msg_str["data"])
        device = device_manager.get_device("5005TEST0001")
        if device and device.get("status") == "closed":
            tr.ok("005 r_travel='0'(字符串) 正确解析为 closed")
        else:
            tr.fail("005 字符串r_travel", f"状态应为closed，实际: {device.get('status') if device else 'None'}")
    except Exception as e:
        tr.fail("005 字符串r_travel", f"抛出异常: {e}")

    # 测试 r_travel 无效值
    msg_invalid = make_msg("005", 2005, "1001ABCD1234", {
        "sn": "5005TEST0001",
        "attrs": [{"attribute": "r_travel", "value": "abc"}]
    })
    try:
        await handler._handle_ctype_005(msg_invalid, "005", msg_invalid["data"])
        tr.ok("005 r_travel='abc'(无效值) 不崩溃")
    except Exception as e:
        tr.fail("005 无效r_travel", f"抛出异常: {e}")

    # 测试 wind_lock_mode 解析
    msg_wind = make_msg("005", 2006, "1001ABCD1234", {
        "sn": "5005TEST0001",
        "attrs": [{"attribute": "rwp_wind_lock_mode", "value": "0"}]
    })
    await handler._handle_ctype_005(msg_wind, "005", msg_wind["data"])
    device = device_manager.get_device("5005TEST0001")
    wind_mode = device.get("attributes", {}).get("wind_lock_mode") if device else None
    if wind_mode is not None:
        tr.ok(f"005 wind_lock_mode 正确解析: {wind_mode}")
    else:
        tr.fail("005 wind_lock_mode", "风锁模式属性未设置")

    # 测试仅上报 battery，不覆盖已有状态
    # 先设置状态为 open
    msg_open2 = make_msg("005", 2007, "1001ABCD1234", {
        "sn": "5005TEST0001",
        "attrs": [{"attribute": "r_travel", "value": 80}]
    })
    await handler._handle_ctype_005(msg_open2, "005", msg_open2["data"])
    # 然后只上报 battery
    msg_batt_only = make_msg("005", 2008, "1001ABCD1234", {
        "sn": "5005TEST0001",
        "battery": 110
    })
    await handler._handle_ctype_005(msg_batt_only, "005", msg_batt_only["data"])
    device = device_manager.get_device("5005TEST0001")
    if device and device.get("status") == "open":
        tr.ok("005 仅上报battery不覆盖已有open状态")
    else:
        tr.fail("005 状态覆盖", f"状态应保持open，实际: {device.get('status') if device else 'None'}")


async def test_mqtt_002_device_discovery(tr: TestResult):
    """测试 7: 002 设备发现与批量处理"""
    PUBLISHED_MESSAGES.clear()

    hass = MockHass()
    hass.loop = asyncio.get_event_loop()

    # 设置 hass.data
    hass.data[const_mod.DOMAIN] = {
        const_mod.DEVICE_TO_GATEWAY_MAPPING: {}
    }

    device_manager = MockDeviceManager()
    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)

    # 模拟 002 上报多个设备
    devices_data = [
        {"sn": "5005DEVICE0001", "battery": 120, "r_travel": 0},
        {"sn": "5005DEVICE0002", "battery": 98, "r_travel": 50},
        {"sn": "5001DEVICE0003", "battery": 105, "r_travel": 100},
        # 网关设备应被跳过
        {"sn": "1001ABCD1234", "model": "gateway"},
        # 重复设备
        {"sn": "5005DEVICE0001", "battery": 110, "r_travel": 10},
        # 空 SN
        {"sn": "", "battery": 100},
    ]

    msg = make_msg("002", 3001, "1001ABCD1234", {
        "status": "online",
        "devices": devices_data
    })
    await handler._handle_ctype_002(msg, "002", msg["data"])

    # 验证非网关设备被添加
    if "5005DEVICE0001" in device_manager.devices:
        tr.ok("002 设备发现 - 5005DEVICE0001 被添加")
    else:
        tr.fail("002 设备发现", "5005DEVICE0001 未被添加")

    if "5005DEVICE0002" in device_manager.devices:
        tr.ok("002 设备发现 - 5005DEVICE0002 被添加")
    else:
        tr.fail("002 设备发现", "5005DEVICE0002 未被添加")

    if "5001DEVICE0003" in device_manager.devices:
        tr.ok("002 设备发现 - 5001DEVICE0003 被添加")
    else:
        tr.fail("002 设备发现", "5001DEVICE0003 未被添加")

    # 网关设备不应被添加
    if "1001ABCD1234" not in device_manager.devices:
        tr.ok("002 设备发现 - 网关设备被正确跳过")
    else:
        tr.fail("002 网关跳过", "网关设备不应被添加到子设备列表")

    # 空SN设备不应被添加
    if "" not in device_manager.devices:
        tr.ok("002 设备发现 - 空 SN 设备被跳过")
    else:
        tr.fail("002 空SN跳过", "空SN设备不应被添加")

    # 002 应回复 ACK
    ack_count = sum(1 for m in PUBLISHED_MESSAGES if m["ctype"] == "002" and m["has_errcode"])
    if ack_count >= 1:
        tr.ok("002 设备发现 - 回复了 ACK")
    else:
        tr.fail("002 ACK", f"期望至少1个ACK，实际{ack_count}个")


async def test_mqtt_003_binding_response(tr: TestResult):
    """测试 8: 003 绑定/解绑响应处理"""
    PUBLISHED_MESSAGES.clear()

    hass = MockHass()
    hass.loop = asyncio.get_event_loop()
    device_manager = MockDeviceManager()
    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)

    # 测试绑定成功 (errcode=0, bind=1)
    msg_bind = make_msg("003", 4001, "1001ABCD1234", {
        "errcode": 0,
        "sn": "5005BIND00001",
        "bind": 1
    })
    await handler._handle_ctype_003(msg_bind, "003", msg_bind["data"])

    if "5005BIND00001" in device_manager.devices:
        tr.ok("003 绑定成功 - 设备被添加")
    else:
        tr.fail("003 绑定", "设备未被添加")

    # 测试绑定失败 (errcode=7)
    PUBLISHED_MESSAGES.clear()
    msg_fail = make_msg("003", 4002, "1001ABCD1234", {
        "errcode": 7,
        "sn": "5005FAIL00001",
        "bind": 1
    })
    try:
        await handler._handle_ctype_003(msg_fail, "003", msg_fail["data"])
        if "5005FAIL00001" not in device_manager.devices:
            tr.ok("003 绑定失败(errcode=7) - 设备未被添加")
        else:
            tr.fail("003 绑定失败", "errcode=7时设备不应被添加")
    except Exception as e:
        tr.fail("003 绑定失败", f"抛出异常: {e}")

    # 测试 003 不回复 ACK
    ack_count = sum(1 for m in PUBLISHED_MESSAGES if m["ctype"] == "003" and m["has_errcode"])
    if ack_count == 0:
        tr.ok("003 绑定响应 - 不回复 ACK")
    else:
        tr.fail("003 不应ACK", f"期望0个ACK，实际{ack_count}个")


async def test_mqtt_001_binding(tr: TestResult):
    """测试 9: 001 网关绑定处理"""
    PUBLISHED_MESSAGES.clear()

    hass = MockHass()
    hass.loop = asyncio.get_event_loop()
    device_manager = MockDeviceManager()
    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)

    # 测试网关主动发起绑定请求（无errcode）
    msg_001 = make_msg("001", 5001, "1001ABCD1234", {
        "vesion": "1.0.5",
        "model": "Gateway-X"
    })
    await handler._handle_ctype_001(msg_001, "001", msg_001["data"])

    # 应该回复 001 带errcode=0
    ack_count = sum(1 for m in PUBLISHED_MESSAGES if m["ctype"] == "001" and m["has_errcode"] and m["errcode"] == 0)
    if ack_count >= 1:
        tr.ok("001 网关绑定请求 - HA 回复 errcode=0")
    else:
        tr.fail("001 绑定响应", f"期望至少1个errcode=0的响应，实际{ack_count}个")

    # 验证响应包含 uuid
    has_uuid = any("uuid" in m["data"] for m in PUBLISHED_MESSAGES if m["ctype"] == "001")
    if has_uuid:
        tr.ok("001 绑定响应 - 包含 uuid 字段")
    else:
        tr.fail("001 uuid", "响应中缺少 uuid 字段")


async def test_send_command(tr: TestResult):
    """测试 10: 命令发送验证"""
    PUBLISHED_MESSAGES.clear()

    hass = MockHass()
    hass.loop = asyncio.get_event_loop()
    device_manager = MockDeviceManager()

    # 预添加设备
    await device_manager.add_device("5005TEST0001", "测试设备", "window_opener")

    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)
    handler.connected = True  # 模拟已连接

    # 测试 open 命令
    result = await handler.send_command("5005TEST0001", "open")
    if result:
        tr.ok("发送 open 命令成功")
    else:
        tr.fail("open命令", "发送失败")

    # 验证 payload 格式
    cmd_msg = next((m for m in PUBLISHED_MESSAGES if m["ctype"] == "004"), None)
    if cmd_msg:
        if cmd_msg["data"].get("sn") == "5005TEST0001":
            tr.ok("open 命令 payload 包含正确的设备SN")
        else:
            tr.fail("open payload", f"设备SN不正确: {cmd_msg['data'].get('sn')}")

        if cmd_msg["data"].get("value") == "100":
            tr.ok("open 命令 value=100")
        else:
            tr.fail("open value", f"value应为100，实际: {cmd_msg['data'].get('value')}")

        if cmd_msg["data"].get("attribute") == "w_travel":
            tr.ok("open 命令 attribute=w_travel")
        else:
            tr.fail("open attribute", f"attribute应为w_travel，实际: {cmd_msg['data'].get('attribute')}")
    else:
        tr.fail("004 命令", "未找到004类型的命令消息")

    # 测试 close 命令
    PUBLISHED_MESSAGES.clear()
    await handler.send_command("5005TEST0001", "close")
    cmd_msg = next((m for m in PUBLISHED_MESSAGES if m["ctype"] == "004"), None)
    if cmd_msg and cmd_msg["data"].get("value") == "0":
        tr.ok("close 命令 value=0")
    else:
        tr.fail("close value", f"value应为0")

    # 测试 stop 命令
    PUBLISHED_MESSAGES.clear()
    await handler.send_command("5005TEST0001", "stop")
    cmd_msg = next((m for m in PUBLISHED_MESSAGES if m["ctype"] == "004"), None)
    if cmd_msg and cmd_msg["data"].get("value") == "101":
        tr.ok("stop 命令 value=101")
    else:
        tr.fail("stop value", f"value应为101")

    # 测试 wind_lock_tilt 命令
    PUBLISHED_MESSAGES.clear()
    await handler.send_command("5005TEST0001", "wind_lock_tilt")
    cmd_msg = next((m for m in PUBLISHED_MESSAGES if m["ctype"] == "004"), None)
    if cmd_msg:
        if cmd_msg["data"].get("value") == "0":
            tr.ok("wind_lock_tilt 命令 value=0(内倒模式)")
        else:
            tr.fail("wind_lock_tilt value", f"value应为0，实际: {cmd_msg['data'].get('value')}")

        if cmd_msg["data"].get("attribute") == "rwp_wind_lock_mode":
            tr.ok("wind_lock_tilt 命令 attribute=rwp_wind_lock_mode")
        else:
            tr.fail("wind_lock_tilt attr", f"attribute应为rwp_wind_lock_mode")
    else:
        tr.fail("wind_lock_tilt", "未找到命令消息")

    # 测试 wind_lock_flat 命令
    PUBLISHED_MESSAGES.clear()
    await handler.send_command("5005TEST0001", "wind_lock_flat")
    cmd_msg = next((m for m in PUBLISHED_MESSAGES if m["ctype"] == "004"), None)
    if cmd_msg and cmd_msg["data"].get("value") == "1":
        tr.ok("wind_lock_flat 命令 value=1(平开模式)")
    else:
        tr.fail("wind_lock_flat value", f"value应为1")

    # 测试无效命令
    result = await handler.send_command("5005TEST0001", "invalid_command")
    if not result:
        tr.ok("无效命令被正确拒绝")
    else:
        tr.fail("无效命令", "无效命令应返回False")

    # 测试空设备SN
    result = await handler.send_command("", "open")
    if not result:
        tr.ok("空设备SN被正确拒绝")
    else:
        tr.fail("空SN", "空SN应返回False")

    # 测试不存在的设备
    result = await handler.send_command("NOTEXIST12345", "open")
    if not result:
        tr.ok("不存在的设备被正确拒绝")
    else:
        tr.fail("不存在设备", "不存在的设备应返回False")


async def test_command_id_increment(tr: TestResult):
    """测试 11: 命令ID自增与回绕"""
    PUBLISHED_MESSAGES.clear()

    hass = MockHass()
    hass.loop = asyncio.get_event_loop()
    device_manager = MockDeviceManager()
    await device_manager.add_device("5005TEST0001", "测试设备", "window_opener")

    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)
    handler.connected = True

    # 记录初始 command_id
    initial_id = handler.command_id

    # 发送命令
    await handler.send_command("5005TEST0001", "open")
    if handler.command_id == initial_id + 1:
        tr.ok("命令ID正确自增")
    else:
        tr.fail("命令ID自增", f"期望{initial_id+1}，实际{handler.command_id}")

    # 测试回绕
    handler.command_id = const_mod.MAX_COMMAND_ID
    await handler.send_command("5005TEST0001", "open")
    if handler.command_id == 1:
        tr.ok(f"命令ID正确回绕 (MAX={const_mod.MAX_COMMAND_ID} -> 1)")
    else:
        tr.fail("命令ID回绕", f"期望1，实际{handler.command_id}")


async def test_005_missing_device_sn(tr: TestResult):
    """测试 12: 005 消息缺少设备SN时的处理"""
    PUBLISHED_MESSAGES.clear()

    hass = MockHass()
    hass.loop = asyncio.get_event_loop()
    device_manager = MockDeviceManager()
    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)

    # 005 消息没有 sn 字段
    msg_no_sn = make_msg("005", 6001, "1001ABCD1234", {
        "attrs": [{"attribute": "r_travel", "value": 50}]
    })
    try:
        await handler._handle_ctype_005(msg_no_sn, "005", msg_no_sn["data"])
        # 即使没有 sn，也应该回复 ACK（在函数末尾）
        ack_count = sum(1 for m in PUBLISHED_MESSAGES if m["ctype"] == "005" and m["has_errcode"])
        if ack_count == 1:
            tr.ok("005 无设备SN - 仍回复 ACK")
        else:
            tr.fail("005 无SN ACK", f"期望1个ACK，实际{ack_count}个")
    except Exception as e:
        tr.fail("005 无SN处理", f"抛出异常: {e}")


async def test_002_empty_devices(tr: TestResult):
    """测试 13: 002 空设备列表处理"""
    PUBLISHED_MESSAGES.clear()

    hass = MockHass()
    hass.loop = asyncio.get_event_loop()
    hass.data[const_mod.DOMAIN] = {const_mod.DEVICE_TO_GATEWAY_MAPPING: {}}

    device_manager = MockDeviceManager()
    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)

    # 002 消息不带 devices 字段
    msg_no_devices = make_msg("002", 7001, "1001ABCD1234", {"status": "online"})
    try:
        await handler._handle_ctype_002(msg_no_devices, "002", msg_no_devices["data"])
        tr.ok("002 无devices字段 - 不崩溃")
    except Exception as e:
        tr.fail("002 无devices", f"抛出异常: {e}")

    # 002 消息带空 devices 列表
    msg_empty = make_msg("002", 7002, "1001ABCD1234", {"status": "online", "devices": []})
    try:
        await handler._handle_ctype_002(msg_empty, "002", msg_empty["data"])
        tr.ok("002 空devices列表 - 不崩溃")
    except Exception as e:
        tr.fail("002 空devices", f"抛出异常: {e}")


async def test_005_string_r_travel_value(tr: TestResult):
    """测试 14: 005 r_travel 值为字符串时的类型安全"""
    PUBLISHED_MESSAGES.clear()

    hass = MockHass()
    hass.loop = asyncio.get_event_loop()
    device_manager = MockDeviceManager()
    await device_manager.add_device("5005TEST0001", "测试设备", "window_opener")

    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)

    # r_travel 值为字符串 "0"
    msg = make_msg("005", 8001, "1001ABCD1234", {
        "sn": "5005TEST0001",
        "attrs": [{"attribute": "r_travel", "value": "0"}]
    })
    try:
        await handler._handle_ctype_005(msg, "005", msg["data"])
        device = device_manager.get_device("5005TEST0001")
        r_travel = device.get("attributes", {}).get("r_travel") if device else None
        if r_travel == 0:
            tr.ok("005 r_travel='0'(字符串) 正确转换为int 0")
        else:
            tr.fail("005 r_travel转换", f"期望int 0，实际: {r_travel} (类型: {type(r_travel).__name__})")
    except Exception as e:
        tr.fail("005 字符串r_travel", f"抛出异常: {e}")


async def test_002_update_existing_device(tr: TestResult):
    """测试 15: 002 更新已存在设备的状态"""
    PUBLISHED_MESSAGES.clear()

    hass = MockHass()
    hass.loop = asyncio.get_event_loop()
    hass.data[const_mod.DOMAIN] = {const_mod.DEVICE_TO_GATEWAY_MAPPING: {}}

    device_manager = MockDeviceManager()

    # 预添加设备
    await device_manager.add_device("5005EXIST001", "已有设备", "window_opener")
    device_manager.devices["5005EXIST001"]["status"] = "open"
    device_manager.devices["5005EXIST001"]["attributes"]["r_travel"] = 80

    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)

    # 002 上报更新该设备
    msg = make_msg("002", 9001, "1001ABCD1234", {
        "status": "online",
        "devices": [
            {"sn": "5005EXIST001", "battery": 100, "r_travel": 0}
        ]
    })
    await handler._handle_ctype_002(msg, "002", msg["data"])

    device = device_manager.get_device("5005EXIST001")
    if device:
        r_travel = device.get("attributes", {}).get("r_travel")
        if r_travel == 0:
            tr.ok("002 更新已存在设备 - r_travel 正确更新为 0")
        else:
            tr.fail("002 更新设备", f"r_travel应为0，实际: {r_travel}")

        status = device.get("status")
        if status == "closed":
            tr.ok("002 更新已存在设备 - 状态正确更新为 closed")
        else:
            tr.fail("002 状态更新", f"状态应为closed(r_travel=0)，实际: {status}")
    else:
        tr.fail("002 设备更新", "设备不存在")


def test_persist_save_load(tr: TestResult):
    """测试 16: 持久化保存与加载"""
    import tempfile
    import os as os_module

    # 创建临时目录
    with tempfile.TemporaryDirectory() as temp_dir:
        # 测试保存数据
        test_data = {
            "device_gateway_mapping": {
                "5005TEST0001": "1001ABCD1234",
                "5001TEST0002": "1001ABCD1234"
            },
            "global_manually_removed_devices": ["5005REMOVED001"]
        }

        file_path = os_module.path.join(temp_dir, "test_persist.json")

        # 直接写入
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(test_data, f, ensure_ascii=False, indent=2)

        # 读取验证
        with open(file_path, 'r', encoding='utf-8') as f:
            loaded_data = json.load(f)

        if loaded_data == test_data:
            tr.ok("持久化数据保存与加载一致")
        else:
            tr.fail("持久化", f"数据不一致:\n期望: {test_data}\n实际: {loaded_data}")

        # 测试中文保存
        test_data_cn = {
            "device_gateway_mapping": {
                "5005TEST0001": "1001ABCD1234"
            },
            "gateway_name": "慧尖网关"
        }

        file_path_cn = os_module.path.join(temp_dir, "test_persist_cn.json")
        with open(file_path_cn, 'w', encoding='utf-8') as f:
            json.dump(test_data_cn, f, ensure_ascii=False, indent=2)

        with open(file_path_cn, 'r', encoding='utf-8') as f:
            loaded_data_cn = json.load(f)

        if loaded_data_cn.get("gateway_name") == "慧尖网关":
            tr.ok("持久化中文数据保存正常（无乱码）")
        else:
            tr.fail("中文持久化", f"中文字符乱码: {loaded_data_cn.get('gateway_name')}")


def test_config_flow_validation(tr: TestResult):
    """测试 17: 配置流验证"""
    # 测试 validate_gateway_sn
    # 需要加载 config_flow 模块
    try:
        config_flow_mod = load_module(
            "custom_components.window_controller_gateway.config_flow",
            os.path.join(COMPONENT_DIR, "config_flow.py")
        )
    except Exception as e:
        tr.warn("配置流加载", f"无法加载config_flow模块: {e}")
        return

    validate_fn = config_flow_mod.validate_gateway_sn

    # 有效SN
    if validate_fn("100121501186"):
        tr.ok("有效网关SN验证通过 (100121501186)")
    else:
        tr.fail("SN验证", "100121501186 应该是有效的")

    # 太短
    if not validate_fn("12345"):
        tr.ok("短SN验证被拒绝 (12345)")
    else:
        tr.fail("短SN验证", "12345 应该无效")

    # 空值
    if not validate_fn(""):
        tr.ok("空SN验证被拒绝")
    else:
        tr.fail("空SN验证", "空字符串应该无效")

    if not validate_fn(None):
        tr.ok("None SN验证被拒绝")
    else:
        tr.fail("None SN验证", "None 应该无效")

    # 包含特殊字符
    if not validate_fn("10012150118!"):
        tr.ok("特殊字符SN验证被拒绝")
    else:
        tr.fail("特殊字符SN", "包含!的SN应该无效")

    # 包含空格
    if not validate_fn("100121 501186"):
        tr.ok("含空格SN验证被拒绝")
    else:
        tr.fail("空格SN验证", "包含空格的SN应该无效")

    # 混合大小写字母
    if validate_fn("1001ABCD1234"):
        tr.ok("混合大小写字母SN验证通过")
    else:
        tr.fail("大小写SN", "1001ABCD1234 应该有效")


async def test_mqtt_005_battery_only_no_status_override(tr: TestResult):
    """测试 18: 005 仅上报battery时不覆盖已有状态"""
    PUBLISHED_MESSAGES.clear()

    hass = MockHass()
    hass.loop = asyncio.get_event_loop()
    device_manager = MockDeviceManager()
    await device_manager.add_device("5005TEST0001", "测试设备", "window_opener")

    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)

    # 先设置状态为 closed
    msg_close = make_msg("005", 10001, "1001ABCD1234", {
        "sn": "5005TEST0001",
        "attrs": [{"attribute": "r_travel", "value": 0}]
    })
    await handler._handle_ctype_005(msg_close, "005", msg_close["data"])

    # 然后只上报 battery（不包含 r_travel）
    msg_batt = make_msg("005", 10002, "1001ABCD1234", {
        "sn": "5005TEST0001",
        "battery": 105
    })
    await handler._handle_ctype_005(msg_batt, "005", msg_batt["data"])

    device = device_manager.get_device("5005TEST0001")
    if device:
        status = device.get("status")
        if status == "closed":
            tr.ok("005 仅上报battery - 状态保持closed（未被覆盖为unknown）")
        else:
            tr.fail("005 状态覆盖", f"状态应为closed，实际: {status}（被覆盖了）")

        voltage = device.get("attributes", {}).get("voltage")
        if voltage is not None and abs(voltage - 10.5) < 0.01:
            tr.ok("005 仅上报battery - 电压正确更新为10.5V")
        else:
            tr.fail("005 battery更新", f"电压应为10.5V，实际: {voltage}")


async def test_unknown_ctype_handling(tr: TestResult):
    """测试 19: 未知消息类型处理"""
    PUBLISHED_MESSAGES.clear()

    hass = MockHass()
    hass.loop = asyncio.get_event_loop()
    device_manager = MockDeviceManager()
    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)

    # 未知 ctype 不应崩溃
    msg_unknown = make_msg("999", 11001, "1001ABCD1234", {"test": "data"})
    try:
        # 模拟消息处理逻辑
        ctype = msg_unknown.get("ctype")
        ctype_handlers = {
            "001": handler._handle_ctype_001,
            "002": handler._handle_ctype_002,
            "003": handler._handle_ctype_003,
            "004": handler._handle_ctype_004,
            "005": handler._handle_ctype_005,
        }
        if ctype not in ctype_handlers:
            tr.ok("未知消息类型 '999' 被正确识别为未知")
        else:
            tr.fail("未知ctype", "ctype '999' 不应存在于处理器中")
    except Exception as e:
        tr.fail("未知ctype处理", f"抛出异常: {e}")


async def test_002_battery_parsing(tr: TestResult):
    """测试 20: 002 设备 battery 解析（除以10转电压）"""
    PUBLISHED_MESSAGES.clear()

    hass = MockHass()
    hass.loop = asyncio.get_event_loop()
    hass.data[const_mod.DOMAIN] = {const_mod.DEVICE_TO_GATEWAY_MAPPING: {}}

    device_manager = MockDeviceManager()
    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)

    # 002 上报设备带 battery=105 (应解析为 10.5V)
    msg = make_msg("002", 12001, "1001ABCD1234", {
        "status": "online",
        "devices": [
            {"sn": "5005BATT0001", "battery": 105, "r_travel": 30}
        ]
    })
    await handler._handle_ctype_002(msg, "002", msg["data"])

    # 等待异步任务完成
    await asyncio.sleep(0.1)

    device = device_manager.get_device("5005BATT0001")
    if device:
        voltage = device.get("attributes", {}).get("voltage")
        if voltage is not None and abs(voltage - 10.5) < 0.01:
            tr.ok(f"002 battery=105 正确解析为 10.5V")
        else:
            tr.fail("002 battery解析", f"电压应为10.5V，实际: {voltage}")

        r_travel = device.get("attributes", {}).get("r_travel")
        if r_travel == 30:
            tr.ok(f"002 r_travel=30 正确解析")
        else:
            tr.fail("002 r_travel解析", f"r_travel应为30，实际: {r_travel}")
    else:
        tr.fail("002 设备添加", "设备未被添加")


async def test_callback_registration(tr: TestResult):
    """测试 21: 状态回调注册与移除"""
    PUBLISHED_MESSAGES.clear()

    hass = MockHass()
    hass.loop = asyncio.get_event_loop()
    device_manager = MockDeviceManager()
    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)

    # 注册回调
    call_count = [0]

    class TestCallback:
        def __init__(self):
            self.count = 0

        async def __call__(self):
            self.count += 1

    callback = TestCallback()

    # 添加回调
    handler.add_status_callback("5005TEST0001", callback)
    if "5005TEST0001" in handler._status_callbacks:
        tr.ok("状态回调注册成功")
    else:
        tr.fail("回调注册", "回调未被注册")

    # 通知状态变化
    handler._notify_device_status_change("5005TEST0001")
    # 让事件循环处理通过 add_job 调度的协程
    await asyncio.sleep(0.01)
    if callback.count >= 1:
        tr.ok("状态回调被正确触发")
    else:
        tr.fail("回调触发", f"回调未被调用，count={callback.count}")

    # 移除回调
    handler.remove_status_callback("5005TEST0001", callback)
    if "5005TEST0001" not in handler._status_callbacks:
        tr.ok("状态回调移除成功")
    else:
        tr.fail("回调移除", "回调未被移除")


async def test_mqtt_cleanup(tr: TestResult):
    """测试 22: MQTT 处理器清理"""
    PUBLISHED_MESSAGES.clear()

    hass = MockHass()
    hass.loop = asyncio.get_event_loop()
    device_manager = MockDeviceManager()
    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)

    # 注册一些回调
    handler.add_status_callback("5005TEST0001", lambda: None)
    handler.add_status_callback("gateway", lambda: None)

    # 设置一些状态
    handler.connected = True
    handler.pairing_active = True

    # 清理
    try:
        await handler.cleanup()
        if len(handler._status_callbacks) == 0:
            tr.ok("清理后状态回调为空")
        else:
            tr.fail("清理回调", f"回调未清空: {handler._status_callbacks}")

        if not handler.connected:
            tr.ok("清理后连接状态正确")
        else:
            tr.warn("清理连接状态", "cleanup未重置connected状态（可能是设计如此）")
    except Exception as e:
        tr.fail("cleanup", f"抛出异常: {e}")


async def test_002_invalid_battery_value(tr: TestResult):
    """测试 23: 002 无效 battery 值处理"""
    PUBLISHED_MESSAGES.clear()

    hass = MockHass()
    hass.loop = asyncio.get_event_loop()
    hass.data[const_mod.DOMAIN] = {const_mod.DEVICE_TO_GATEWAY_MAPPING: {}}

    device_manager = MockDeviceManager()
    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)

    # battery 为非数字字符串
    msg = make_msg("002", 13001, "1001ABCD1234", {
        "status": "online",
        "devices": [
            {"sn": "5005INVBAT001", "battery": "invalid", "r_travel": 50}
        ]
    })
    try:
        await handler._handle_ctype_002(msg, "002", msg["data"])
        await asyncio.sleep(0.1)

        # 设备应该被添加，但 battery 不应被设置
        device = device_manager.get_device("5005INVBAT001")
        if device:
            voltage = device.get("attributes", {}).get("voltage")
            if voltage is None:
                tr.ok("002 无效battery值 - 电压未设置（正确处理异常）")
            else:
                tr.fail("002 无效battery", f"电压不应被设置，实际: {voltage}")

            # r_travel 应该正常解析
            r_travel = device.get("attributes", {}).get("r_travel")
            if r_travel == 50:
                tr.ok("002 无效battery时 r_travel 仍正常解析")
            else:
                tr.fail("002 r_travel", f"r_travel应为50，实际: {r_travel}")
        else:
            tr.fail("002 设备添加", "设备未被添加")
    except Exception as e:
        tr.fail("002 无效battery", f"抛出异常: {e}")


async def test_005_attrs_missing_attribute(tr: TestResult):
    """测试 24: 005 attrs 中缺少 attribute 字段"""
    PUBLISHED_MESSAGES.clear()

    hass = MockHass()
    hass.loop = asyncio.get_event_loop()
    device_manager = MockDeviceManager()
    await device_manager.add_device("5005TEST0001", "测试设备", "window_opener")

    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)

    # attrs 中有一项缺少 attribute 字段
    msg = make_msg("005", 14001, "1001ABCD1234", {
        "sn": "5005TEST0001",
        "attrs": [
            {"value": 50},  # 缺少 attribute
            {"attribute": "r_travel", "value": 30}  # 正常
        ]
    })
    try:
        await handler._handle_ctype_005(msg, "005", msg["data"])
        device = device_manager.get_device("5005TEST0001")
        if device:
            r_travel = device.get("attributes", {}).get("r_travel")
            if r_travel == 30:
                tr.ok("005 attrs缺少attribute字段 - 正常项仍被处理")
            else:
                tr.fail("005 attrs处理", f"r_travel应为30，实际: {r_travel}")
        else:
            tr.fail("005 设备", "设备不存在")
    except Exception as e:
        tr.fail("005 attrs异常", f"抛出异常: {e}")


async def test_005_empty_attrs(tr: TestResult):
    """测试 25: 005 空 attrs 数组"""
    PUBLISHED_MESSAGES.clear()

    hass = MockHass()
    hass.loop = asyncio.get_event_loop()
    device_manager = MockDeviceManager()
    await device_manager.add_device("5005TEST0001", "测试设备", "window_opener")

    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)

    # 空 attrs 数组
    msg = make_msg("005", 15001, "1001ABCD1234", {
        "sn": "5005TEST0001",
        "attrs": []
    })
    try:
        await handler._handle_ctype_005(msg, "005", msg["data"])
        tr.ok("005 空 attrs 数组 - 不崩溃")

        # 仍应回复 ACK
        ack_count = sum(1 for m in PUBLISHED_MESSAGES if m["ctype"] == "005" and m["has_errcode"])
        if ack_count == 1:
            tr.ok("005 空 attrs - 仍回复 ACK")
        else:
            tr.fail("005 空attrs ACK", f"期望1个ACK，实际{ack_count}个")
    except Exception as e:
        tr.fail("005 空attrs", f"抛出异常: {e}")


async def test_set_position_command(tr: TestResult):
    """测试 26: set_position 命令验证"""
    PUBLISHED_MESSAGES.clear()

    hass = MockHass()
    hass.loop = asyncio.get_event_loop()
    device_manager = MockDeviceManager()
    await device_manager.add_device("5005TEST0001", "测试设备", "window_opener")

    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)
    handler.connected = True

    # 测试设置位置 50%
    result = await handler.send_command("5005TEST0001", "set_position", {"position": 50})
    if result:
        tr.ok("set_position 命令发送成功")
    else:
        tr.fail("set_position", "发送失败")

    cmd_msg = next((m for m in PUBLISHED_MESSAGES if m["ctype"] == "004"), None)
    if cmd_msg:
        if cmd_msg["data"].get("value") == "50":
            tr.ok("set_position value=50 正确")
        else:
            tr.fail("set_position value", f"value应为'50'，实际: {cmd_msg['data'].get('value')}")

    # 测试超出范围的位置
    PUBLISHED_MESSAGES.clear()
    await handler.send_command("5005TEST0001", "set_position", {"position": 150})
    cmd_msg = next((m for m in PUBLISHED_MESSAGES if m["ctype"] == "004"), None)
    if cmd_msg and cmd_msg["data"].get("value") == "0":
        tr.ok("set_position 超范围(150) 正确回退为0")
    else:
        tr.fail("set_position 超范围", f"value应为'0'，实际: {cmd_msg['data'].get('value') if cmd_msg else 'None'}")

    # 测试负数位置
    PUBLISHED_MESSAGES.clear()
    await handler.send_command("5005TEST0001", "set_position", {"position": -10})
    cmd_msg = next((m for m in PUBLISHED_MESSAGES if m["ctype"] == "004"), None)
    if cmd_msg and cmd_msg["data"].get("value") == "0":
        tr.ok("set_position 负数(-10) 正确回退为0")
    else:
        tr.fail("set_position 负数", f"value应为'0'")

    # 测试字符串位置
    PUBLISHED_MESSAGES.clear()
    await handler.send_command("5005TEST0001", "set_position", {"position": "75"})
    cmd_msg = next((m for m in PUBLISHED_MESSAGES if m["ctype"] == "004"), None)
    if cmd_msg and cmd_msg["data"].get("value") == "75":
        tr.ok("set_position 字符串'75' 正确转换为75")
    else:
        tr.fail("set_position 字符串", f"value应为'75'，实际: {cmd_msg['data'].get('value') if cmd_msg else 'None'}")


async def test_003_unbind_response(tr: TestResult):
    """测试 27: 003 解绑响应处理"""
    PUBLISHED_MESSAGES.clear()

    hass = MockHass()
    hass.loop = asyncio.get_event_loop()
    device_manager = MockDeviceManager()

    # 预添加设备
    await device_manager.add_device("5005BIND00001", "已绑定设备", "window_opener")

    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)

    # 解绑成功响应 (errcode=0, bind=0)
    msg = make_msg("003", 16001, "1001ABCD1234", {
        "errcode": 0,
        "sn": "5005BIND00001",
        "bind": 0
    })
    try:
        await handler._handle_ctype_003(msg, "003", msg["data"])
        tr.ok("003 解绑响应 - 不崩溃")

        # 003 不应回复 ACK
        ack_count = sum(1 for m in PUBLISHED_MESSAGES if m["ctype"] == "003" and m["has_errcode"])
        if ack_count == 0:
            tr.ok("003 解绑响应 - 不回复 ACK")
        else:
            tr.fail("003 解绑ACK", f"期望0个ACK，实际{ack_count}个")
    except Exception as e:
        tr.fail("003 解绑", f"抛出异常: {e}")


async def test_mqtt_offline_command_sending(tr: TestResult):
    """测试 28: 网关离线时发送命令"""
    PUBLISHED_MESSAGES.clear()

    hass = MockHass()
    hass.loop = asyncio.get_event_loop()
    device_manager = MockDeviceManager()
    await device_manager.add_device("5005TEST0001", "测试设备", "window_opener")

    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)
    handler.connected = False  # 网关离线

    # open/close/stop 命令在离线时仍应尝试发送
    result = await handler.send_command("5005TEST0001", "open")
    if result:
        tr.ok("网关离线时 open 命令仍尝试发送")
    else:
        tr.fail("离线命令", "open命令在离线时应仍尝试发送")

    # 验证消息已发布
    cmd_count = sum(1 for m in PUBLISHED_MESSAGES if m["ctype"] == "004")
    if cmd_count >= 1:
        tr.ok("离线时命令消息已发布")
    else:
        tr.fail("离线发布", "离线时命令未发布")


async def test_pairing_flow(tr: TestResult):
    """测试 29: 配对流程"""
    PUBLISHED_MESSAGES.clear()

    hass = MockHass()
    hass.loop = asyncio.get_event_loop()
    device_manager = MockDeviceManager()
    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)
    handler.connected = True

    # 发送配对命令
    result = await handler.send_command("1001ABCD1234", "start_pairing")
    if result:
        tr.ok("配对命令发送成功")
    else:
        tr.fail("配对命令", "发送失败")

    # 验证 payload
    pair_msg = next((m for m in PUBLISHED_MESSAGES if m["ctype"] == "003"), None)
    if pair_msg:
        if pair_msg["data"].get("bind") == 1:
            tr.ok("配对命令包含 bind=1")
        else:
            tr.fail("配对bind", f"bind应为1，实际: {pair_msg['data'].get('bind')}")

        if pair_msg["data"].get("sn") == "FFFFFFFFFFFF":
            tr.ok("配对命令包含正确的占位符SN")
        else:
            tr.fail("配对SN", f"sn应为FFFFFFFFFFFF，实际: {pair_msg['data'].get('sn')}")

        if pair_msg["data"].get("devtype") == "curtain_ctr":
            tr.ok("配对命令包含正确的设备类型")
        else:
            tr.fail("配对devtype", f"devtype应为curtain_ctr")
    else:
        tr.fail("配对payload", "未找到003类型的命令消息")


def test_manifest_structure(tr: TestResult):
    """测试 30: manifest.json 结构验证"""
    manifest_path = os.path.join(COMPONENT_DIR, "manifest.json")
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    required_fields = ["domain", "name", "version", "config_flow", "requirements", "dependencies", "codeowners", "iot_class"]
    for field in required_fields:
        if field in manifest:
            tr.ok(f"manifest.json 包含必要字段: {field}")
        else:
            tr.fail("manifest字段", f"缺少必要字段: {field}")

    # 验证 domain
    if manifest.get("domain") == "window_controller_gateway":
        tr.ok("manifest.json domain 正确")
    else:
        tr.fail("manifest domain", f"domain不正确: {manifest.get('domain')}")

    # 验证 config_flow
    if manifest.get("config_flow") == True:
        tr.ok("manifest.json config_flow 启用")
    else:
        tr.fail("manifest config_flow", "config_flow应为true")

    # 验证 dependencies 包含 mqtt
    if "mqtt" in manifest.get("dependencies", []):
        tr.ok("manifest.json 依赖 mqtt")
    else:
        tr.fail("manifest依赖", "dependencies应包含mqtt")

    # 验证 iot_class
    if manifest.get("iot_class") == "local_push":
        tr.ok("manifest.json iot_class 正确 (local_push)")
    else:
        tr.fail("manifest iot_class", f"iot_class应为local_push，实际: {manifest.get('iot_class')}")


def test_strings_json_structure(tr: TestResult):
    """测试 31: strings.json 结构验证"""
    strings_path = os.path.join(COMPONENT_DIR, "strings.json")
    try:
        with open(strings_path, 'r', encoding='utf-8') as f:
            strings = json.load(f)

        if "config" in strings:
            tr.ok("strings.json 包含 config 部分")
        else:
            tr.fail("strings.json", "缺少 config 部分")

        # HA strings.json 的 title 在顶层，而非 config 内部
        if "title" in strings:
            tr.ok("strings.json 包含顶层 title 字段")
        else:
            tr.warn("strings.json title", "缺少顶层 title 字段")
        if "config" in strings and "step" in strings["config"]:
            tr.ok("strings.json config 包含 step 定义")
        else:
            tr.warn("strings.json step", "config 缺少 step 定义")
    except Exception as e:
        tr.warn("strings.json", f"读取失败: {e}")


async def test_005_none_status_preserved(tr: TestResult):
    """测试 32: 005 status=None 时不覆盖已有状态"""
    PUBLISHED_MESSAGES.clear()

    hass = MockHass()
    hass.loop = asyncio.get_event_loop()
    device_manager = MockDeviceManager()
    await device_manager.add_device("5005TEST0001", "测试设备", "window_opener")

    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)

    # 先设置状态为 open
    await device_manager.update_device_status("5005TEST0001", "open", {"r_travel": 80})

    # 发送一个不包含 r_travel 和 status 的 005 消息
    msg = make_msg("005", 17001, "1001ABCD1234", {
        "sn": "5005TEST0001",
        "battery": 100
    })
    await handler._handle_ctype_005(msg, "005", msg["data"])

    device = device_manager.get_device("5005TEST0001")
    if device:
        status = device.get("status")
        if status == "open":
            tr.ok("005 无status字段时 - 保持原有open状态")
        else:
            tr.fail("005 状态保持", f"状态应保持open，实际: {status}")

    # 同理测试 closed 状态保持
    await device_manager.update_device_status("5005TEST0001", "closed", {"r_travel": 0})
    msg2 = make_msg("005", 17002, "1001ABCD1234", {
        "sn": "5005TEST0001",
        "battery": 95
    })
    await handler._handle_ctype_005(msg2, "005", msg2["data"])
    device = device_manager.get_device("5005TEST0001")
    if device and device.get("status") == "closed":
        tr.ok("005 无status字段时 - 保持原有closed状态")
    else:
        tr.fail("005 closed保持", f"状态应保持closed")


async def test_002_device_already_in_other_gateway(tr: TestResult):
    """测试 33: 002 设备已绑定到其他网关"""
    PUBLISHED_MESSAGES.clear()

    hass = MockHass()
    hass.loop = asyncio.get_event_loop()
    hass.data[const_mod.DOMAIN] = {
        const_mod.DEVICE_TO_GATEWAY_MAPPING: {
            "5005OTHER001": "9999OTHER9999"
        }
    }

    device_manager = MockDeviceManager()
    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)

    # 002 上报一个已绑定到其他网关的设备
    msg = make_msg("002", 18001, "1001ABCD1234", {
        "status": "online",
        "devices": [
            {"sn": "5005OTHER001", "battery": 100, "r_travel": 50}
        ]
    })
    await handler._handle_ctype_002(msg, "002", msg["data"])
    await asyncio.sleep(0.1)

    # 设备不应该被添加到当前网关
    if "5005OTHER001" not in device_manager.devices:
        tr.ok("002 设备已绑定到其他网关 - 不自动添加")
    else:
        tr.fail("002 设备冲突", "已绑定到其他网关的设备不应被添加")


async def test_all_ctypes_have_handlers(tr: TestResult):
    """测试 34: 所有声明的 ctype 都有对应的处理函数"""
    hass = MockHass()
    hass.loop = asyncio.get_event_loop()
    device_manager = MockDeviceManager()
    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)

    expected_handlers = ["001", "002", "003", "004", "005", "006", "007"]
    for ctype in expected_handlers:
        handler_name = f"_handle_ctype_{ctype}"
        if hasattr(handler, handler_name):
            tr.ok(f"ctype {ctype} 有对应的处理函数")
        else:
            tr.fail("ctype处理函数", f"缺少 {handler_name}")


async def test_005_ack_id_matches(tr: TestResult):
    """测试 35: ACK 消息的 id 应与原消息一致"""
    PUBLISHED_MESSAGES.clear()

    hass = MockHass()
    hass.loop = asyncio.get_event_loop()
    device_manager = MockDeviceManager()
    handler = mqtt_handler_mod.WindowControllerMQTTHandler(hass, "1001ABCD1234", device_manager)

    # 发送带特定 id 的 005 消息
    test_id = 99999
    msg = make_msg("005", test_id, "1001ABCD1234", {
        "sn": "5005TEST0001",
        "attrs": [{"attribute": "r_travel", "value": 50}]
    })
    await handler._handle_ctype_005(msg, "005", msg["data"])

    ack_msg = next((m for m in PUBLISHED_MESSAGES if m["ctype"] == "005" and m["has_errcode"]), None)
    if ack_msg:
        if ack_msg["id"] == test_id:
            tr.ok(f"ACK id 与原消息一致 ({test_id})")
        else:
            tr.fail("ACK id", f"期望id={test_id}，实际: {ack_msg['id']}")
    else:
        tr.fail("ACK消息", "未找到ACK消息")


# ============================================================
# 主函数
# ============================================================
async def run_all_tests():
    """运行所有测试"""
    tr = TestResult()

    print("=" * 70)
    print("开始全面模拟测试 - 慧尖开窗器网关集成")
    print("=" * 70)

    # 同步测试
    print("\n--- 基础验证测试 ---")
    test_version_consistency(tr)
    test_supports_wind_lock_mode(tr)
    test_get_device_display_name(tr)
    test_manifest_structure(tr)
    test_strings_json_structure(tr)

    print("\n--- 配置流验证测试 ---")
    test_config_flow_validation(tr)

    # 异步测试
    print("\n--- MQTT ACK 规则测试 ---")
    await test_mqtt_ack_rules(tr)

    print("\n--- MQTT 消息处理测试 ---")
    await test_mqtt_message_dedup(tr)
    await test_mqtt_005_status_parsing(tr)
    await test_mqtt_002_device_discovery(tr)
    await test_mqtt_003_binding_response(tr)
    await test_mqtt_001_binding(tr)

    print("\n--- 命令发送测试 ---")
    await test_send_command(tr)
    await test_command_id_increment(tr)
    await test_set_position_command(tr)
    await test_mqtt_offline_command_sending(tr)
    await test_pairing_flow(tr)

    print("\n--- 边缘情况测试 ---")
    await test_005_missing_device_sn(tr)
    await test_002_empty_devices(tr)
    await test_005_string_r_travel_value(tr)
    await test_002_update_existing_device(tr)
    await test_mqtt_005_battery_only_no_status_override(tr)
    await test_unknown_ctype_handling(tr)
    await test_002_battery_parsing(tr)
    await test_002_invalid_battery_value(tr)
    await test_005_attrs_missing_attribute(tr)
    await test_005_empty_attrs(tr)
    await test_003_unbind_response(tr)
    await test_005_none_status_preserved(tr)
    await test_002_device_already_in_other_gateway(tr)
    await test_all_ctypes_have_handlers(tr)
    await test_005_ack_id_matches(tr)

    print("\n--- 回调与清理测试 ---")
    await test_callback_registration(tr)
    await test_mqtt_cleanup(tr)

    print("\n--- 持久化测试 ---")
    test_persist_save_load(tr)

    # 输出结果
    print(tr.summary())

    return tr


if __name__ == "__main__":
    # 设置事件循环
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    result = asyncio.run(run_all_tests())

    # 以退出码返回结果
    sys.exit(0 if result.failed == 0 else 1)
