"""开窗器网关常量定义 - 完整最终版"""

# 集成域
DOMAIN = "window_controller_gateway"

# 配置流常量
CONF_GATEWAY_SN = "gateway_sn"
CONF_GATEWAY_NAME = "gateway_name"
CONF_DEVICE_SN = "device_sn"
CONF_DEVICE_NAME = "device_name"
DEFAULT_GATEWAY_NAME = "慧尖开窗器网关"



# 服务常量
SERVICE_START_PAIRING = "start_pairing"
SERVICE_REFRESH_DEVICES = "refresh_devices"

# 属性常量（包含所有可能的属性）
ATTR_DEVICE_SN = "device_sn"
ATTR_DEVICE_NAME = "device_name"
ATTR_DEVICE_TYPE = "device_type"
ATTR_POSITION = "position"
ATTR_CURRENT_POSITION = "current_position"
ATTR_TARGET_POSITION = "target_position"
ATTR_ANGLE = "angle"
ATTR_SPEED = "speed"
ATTR_FORCE = "force"
ATTR_SAFETY_LOCK = "safety_lock"
ATTR_CHILD_LOCK = "child_lock"
ATTR_BATTERY = "battery"
ATTR_BATTERY_LEVEL = "battery_level"
ATTR_BATTERY_STATE = "battery_state"
ATTR_SIGNAL_STRENGTH = "signal_strength"
ATTR_CONNECTION_STATUS = "connection_status"
ATTR_LAST_SEEN = "last_seen"
ATTR_FIRMWARE_VERSION = "firmware_version"
ATTR_HARDWARE_VERSION = "hardware_version"
ATTR_IP_ADDRESS = "ip_address"
ATTR_MAC_ADDRESS = "mac_address"
ATTR_RSSI = "rssi"
ATTR_LQI = "lqi"
ATTR_VOLTAGE = "voltage"
ATTR_TEMPERATURE = "temperature"
ATTR_HUMIDITY = "humidity"
ATTR_PRESSURE = "pressure"
ATTR_ILLUMINANCE = "illuminance"

# 设备类型常量
DEVICE_TYPE_GATEWAY = "gateway"
DEVICE_TYPE_WINDOW_OPENER = "window_opener"

# 状态常量
STATE_PAIRING = "pairing"
STATE_CONNECTED = "connected"
STATE_DISCONNECTED = "disconnected"
STATE_OPENING = "opening"
STATE_CLOSING = "closing"
STATE_STOPPED = "stopped"
STATE_OPEN = "open"
STATE_CLOSED = "closed"
STATE_UNKNOWN = "unknown"

# 事件常量
EVENT_DEVICE_DISCOVERED = "window_controller_device_discovered"
EVENT_DEVICE_UPDATED = "window_controller_device_updated"
EVENT_GATEWAY_CONNECTED = "window_controller_gateway_connected"
EVENT_GATEWAY_DISCONNECTED = "window_controller_gateway_disconnected"

# 配置选项常量
CONF_DISCOVERY_INTERVAL = "discovery_interval"
CONF_AUTO_DISCOVERY = "auto_discovery"
CONF_DEBUG_LOGGING = "debug_logging"

# 默认值
DEFAULT_DISCOVERY_INTERVAL = 300
DEFAULT_AUTO_DISCOVERY = True
DEFAULT_DEBUG_LOGGING = False

# 扫描间隔（秒）
SCAN_INTERVAL = 300

# 命令常量
COMMAND_OPEN = "open"
COMMAND_CLOSE = "close"
COMMAND_STOP = "stop"
COMMAND_SET_POSITION = "set_position"
COMMAND_A = "a"
COMMAND_PAIR = "pair"
COMMAND_DISCOVER = "discover"
COMMAND_STATUS = "status"
COMMAND_START_PAIRING = "start_pairing"

# 网关实体常量
ENTITY_GATEWAY_PREFIX = "gateway_"
ENTITY_PAIRING_BUTTON_SUFFIX = "_pair"
ENTITY_ONLINE_SENSOR_SUFFIX = "_online"

# 网关状态常量
GATEWAY_STATUS_ONLINE = "online"
GATEWAY_STATUS_OFFLINE = "offline"
GATEWAY_STATUS_PAIRING = "pairing"

# 配对状态常量
PAIRING_STATUS_ACTIVE = "active"
PAIRING_STATUS_INACTIVE = "inactive"

# 其他常量
MANUFACTURER = "慧尖"
MODEL = "慧尖开窗器网关"
VERSION = "1.0.7"
