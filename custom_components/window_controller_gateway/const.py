"""开窗器网关常量定义"""
from typing import Final

# ==================== 集成域 ====================
DOMAIN: Final = "window_controller_gateway"

# ==================== 配置相关 ====================
CONF_GATEWAY_SN: Final = "gateway_sn"
CONF_GATEWAY_NAME: Final = "gateway_name"
CONF_DEVICE_SN: Final = "device_sn"
CONF_DEVICE_NAME: Final = "device_name"
DEFAULT_GATEWAY_NAME: Final = "慧尖网关"
CONF_DISCOVERY_INTERVAL: Final = "discovery_interval"
CONF_AUTO_DISCOVERY: Final = "auto_discovery"
CONF_DEBUG_LOGGING: Final = "debug_logging"
DEFAULT_DISCOVERY_INTERVAL: Final = 300
DEFAULT_AUTO_DISCOVERY: Final = True
DEFAULT_DEBUG_LOGGING: Final = False

# ==================== 服务相关 ====================
SERVICE_START_PAIRING: Final = "start_pairing"
SERVICE_REFRESH_DEVICES: Final = "refresh_devices"
SERVICE_MIGRATE_DEVICES: Final = "migrate_devices"
SERVICE_RENAME_DEVICE: Final = "rename_device"
SERVICE_TRANSFER_DEVICE: Final = "transfer_device"

# ==================== 属性相关 ====================
ATTR_DEVICE_SN: Final = "device_sn"
ATTR_DEVICE_NAME: Final = "device_name"
ATTR_NEW_NAME: Final = "name"
ATTR_DEVICE_TYPE: Final = "device_type"
ATTR_POSITION: Final = "position"
ATTR_CURRENT_POSITION: Final = "current_position"
ATTR_TARGET_POSITION: Final = "target_position"
ATTR_BATTERY: Final = "battery"
ATTR_VOLTAGE: Final = "voltage"
POSITION_MIN: Final = 0
POSITION_MAX: Final = 100
SENSOR_TIMEOUT_MINUTES: Final = 15

# ==================== 设备相关 ====================
DEVICE_TYPE_WINDOW_OPENER: Final = "window_opener"
DEVICE_TYPE_GATEWAY: Final = "gateway"
MAX_DEVICES_PER_GATEWAY: Final = 32
DEVICE_TO_GATEWAY_MAPPING: Final = "device_to_gateway_mapping"
DEVICE_TO_GATEWAY_MAPPING_FILE: Final = "device_gateway_mapping.json"
GLOBAL_MANUALLY_REMOVED_DEVICES: Final = "global_manually_removed_devices"

# ==================== MQTT 相关 ====================
DEFAULT_COMMAND_ID: Final = 1
MAX_COMMAND_ID: Final = 999999
GATEWAY_TIMEOUT_SECONDS: Final = 1800
TOPIC_GATEWAY_REQ_FORMAT: Final = "gateway/{gateway_sn}/req"
TOPIC_GATEWAY_RSP: Final = "gateway/rpt_rsp"
MQTT_MAX_RETRIES: Final = 5
MQTT_MIN_JITTER: Final = 0.5
MQTT_MAX_JITTER: Final = 1.5
MQTT_RETRY_DELAY_MAX: Final = 60
MQTT_BATCH_SIZE: Final = 20
PROTOCOL_HEAD: Final = "$SH"
DEVICE_TYPE_CURTAIN_CTR: Final = "curtain_ctr"
PAIRING_SN_PLACEHOLDER: Final = "FFFFFFFFFFFF"
COMMAND_VALUE_OPEN: Final = "100"
COMMAND_VALUE_CLOSE: Final = "0"
COMMAND_VALUE_STOP: Final = "101"
COMMAND_VALUE_TOGGLE: Final = "200"
ATTRIBUTE_W_TRAVEL: Final = "w_travel"
ATTRIBUTE_WIND_LOCK_MODE: Final = "rwp_wind_lock_mode"
COMMAND_VALUE_WIND_LOCK_TILT: Final = "0"   # 内倒模式
COMMAND_VALUE_WIND_LOCK_FLAT: Final = "1"    # 平开模式

# ==================== 状态相关 ====================
STATE_PAIRING: Final = "pairing"
STATE_CONNECTED: Final = "connected"
STATE_DISCONNECTED: Final = "disconnected"
STATE_OPENING: Final = "opening"
STATE_CLOSING: Final = "closing"
STATE_STOPPED: Final = "stopped"
STATE_OPEN: Final = "open"
STATE_CLOSED: Final = "closed"
STATE_UNKNOWN: Final = "unknown"
GATEWAY_STATUS_ONLINE: Final = "online"
GATEWAY_STATUS_OFFLINE: Final = "offline"
GATEWAY_STATUS_PAIRING: Final = "pairing"
PAIRING_STATUS_ACTIVE: Final = "active"
PAIRING_STATUS_INACTIVE: Final = "inactive"

# ==================== 错误代码相关 ====================
ERROR_CODE_SUCCESS: Final = 0
ERROR_CODE_BIND_EXISTS: Final = 7

# ==================== 事件相关 ====================
EVENT_DEVICE_DISCOVERED: Final = "window_controller_device_discovered"
EVENT_DEVICE_UPDATED: Final = "window_controller_device_updated"
EVENT_GATEWAY_CONNECTED: Final = "window_controller_gateway_connected"
EVENT_GATEWAY_DISCONNECTED: Final = "window_controller_gateway_disconnected"

# ==================== 命令相关 ====================
COMMAND_OPEN: Final = "open"
COMMAND_CLOSE: Final = "close"
COMMAND_STOP: Final = "stop"
COMMAND_SET_POSITION: Final = "set_position"
COMMAND_A: Final = "a"
COMMAND_PAIR: Final = "pair"
COMMAND_DISCOVER: Final = "discover"
COMMAND_STATUS: Final = "status"
COMMAND_START_PAIRING: Final = "start_pairing"
COMMAND_WIND_LOCK_TILT: Final = "wind_lock_tilt"   # 内倒模式
COMMAND_WIND_LOCK_FLAT: Final = "wind_lock_flat"    # 平开模式

# ==================== 实体相关 ====================
ENTITY_GATEWAY_PREFIX: Final = "gateway_"
ENTITY_PAIRING_BUTTON_SUFFIX: Final = "_pair"
ENTITY_ONLINE_SENSOR_SUFFIX: Final = "_online"

# ==================== 时间相关（秒） ====================
SCAN_INTERVAL: Final = 300
SENSOR_SCAN_INTERVAL: Final = 10
DEVICE_REGISTRATION_DELAY: Final = 0.5
GATEWAY_READY_DELAY: Final = 1
DEVICE_SETUP_DELAY: Final = 2
GATEWAY_CHECK_INTERVAL: Final = 30
INITIAL_RETRY_DELAY: Final = 5
RESTART_DELAY: Final = 1
GATEWAY_PAIRING_TIMEOUT: Final = 60

# ==================== 设备SN前缀 ====================
DEVICE_SN_PREFIX_WIND_LOCK: Final = "5005"  # 支持内倒/平开模式的LoRa子设备SN前四位

# ==================== 其他 ====================
MANUFACTURER: Final = "慧尖"
MODEL: Final = "慧尖开窗器网关"
VERSION: Final = "1.3.5"
ICON_GATEWAY: Final = "mdi:gateway"
ICON_WINDOW_OPENER: Final = "mdi:window-closed"


def supports_wind_lock_mode(device_sn: str) -> bool:
    """判断设备是否支持内倒/平开模式

    只有SN前四位为5005的LoRa子设备才支持内倒功能，
    5001/5002/5003等设备不支持内倒功能，不创建相关按钮。

    Args:
        device_sn: 设备序列号

    Returns:
        bool: True表示支持内倒/平开模式
    """
    return device_sn[:4] == DEVICE_SN_PREFIX_WIND_LOCK


def get_device_display_name(gateway_sn: str, device_sn: str, device_number: int = None) -> str:
    """统一设备显示名称"""
    short_gw = gateway_sn[-4:]
    short_dev = device_sn[-4:]
    if device_number is not None:
        return f"开窗器 {short_gw}-{short_dev} (#{device_number:02d})"
    return f"开窗器 {short_gw}-{short_dev}"