"""开窗器网关常量定义 - 完整最终版"""

# 集成域
DOMAIN = "window_controller_gateway"


class ConfigConstants:
    """配置相关常量"""
    # 配置流常量
    CONF_GATEWAY_SN = "gateway_sn"
    CONF_GATEWAY_NAME = "gateway_name"
    CONF_DEVICE_SN = "device_sn"
    CONF_DEVICE_NAME = "device_name"
    DEFAULT_GATEWAY_NAME = "慧尖网关"
    
    # 配置选项常量
    CONF_DISCOVERY_INTERVAL = "discovery_interval"
    CONF_AUTO_DISCOVERY = "auto_discovery"
    CONF_DEBUG_LOGGING = "debug_logging"
    
    # 默认值
    DEFAULT_DISCOVERY_INTERVAL = 300
    DEFAULT_AUTO_DISCOVERY = True
    DEFAULT_DEBUG_LOGGING = False


class ServiceConstants:
    """服务相关常量"""
    SERVICE_START_PAIRING = "start_pairing"
    SERVICE_REFRESH_DEVICES = "refresh_devices"
    SERVICE_MIGRATE_DEVICES = "migrate_devices"


class AttributeConstants:
    """属性相关常量"""
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


class DeviceConstants:
    """设备相关常量"""
    # 设备类型常量
    DEVICE_TYPE_WINDOW_OPENER = "window_opener"
    DEVICE_TYPE_GATEWAY = "gateway"
    
    # 网关配置常量
    MAX_DEVICES_PER_GATEWAY = 32  # 每个网关最多支持32个设备
    
    # 设备到网关映射表常量
    DEVICE_TO_GATEWAY_MAPPING = "device_to_gateway_mapping"
    
    # 全局手动删除设备列表常量
    GLOBAL_MANUALLY_REMOVED_DEVICES = "global_manually_removed_devices"


class MqttConstants:
    """MQTT相关常量"""
    DEFAULT_COMMAND_ID = 1  # 命令ID初始值
    GATEWAY_TIMEOUT_SECONDS = 1200  # 网关超时时间（20分钟）
    TOPIC_GATEWAY_REQ_FORMAT = "gateway/{gateway_sn}/req"  # 发送命令到网关的主题格式
    TOPIC_GATEWAY_RSP = "gateway/rpt_rsp"  # 接收网关数据和响应的主题


class StatusConstants:
    """状态相关常量"""
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
    
    # 网关状态常量
    GATEWAY_STATUS_ONLINE = "online"
    GATEWAY_STATUS_OFFLINE = "offline"
    GATEWAY_STATUS_PAIRING = "pairing"
    
    # 配对状态常量
    PAIRING_STATUS_ACTIVE = "active"
    PAIRING_STATUS_INACTIVE = "inactive"


class ErrorConstants:
    """错误代码相关常量"""
    ERROR_CODE_SUCCESS = 0
    ERROR_CODE_BIND_EXISTS = 7


class EventConstants:
    """事件相关常量"""
    EVENT_DEVICE_DISCOVERED = "window_controller_device_discovered"
    EVENT_DEVICE_UPDATED = "window_controller_device_updated"
    EVENT_GATEWAY_CONNECTED = "window_controller_gateway_connected"
    EVENT_GATEWAY_DISCONNECTED = "window_controller_gateway_disconnected"


class CommandConstants:
    """命令相关常量"""
    COMMAND_OPEN = "open"
    COMMAND_CLOSE = "close"
    COMMAND_STOP = "stop"
    COMMAND_SET_POSITION = "set_position"
    COMMAND_A = "a"
    COMMAND_PAIR = "pair"
    COMMAND_DISCOVER = "discover"
    COMMAND_STATUS = "status"
    COMMAND_START_PAIRING = "start_pairing"


class EntityConstants:
    """实体相关常量"""
    # 网关实体常量
    ENTITY_GATEWAY_PREFIX = "gateway_"
    ENTITY_PAIRING_BUTTON_SUFFIX = "_pair"
    ENTITY_ONLINE_SENSOR_SUFFIX = "_online"
    
    # 平台常量
    PLATFORMS = [
        "binary_sensor",
        "button",
        "cover",
        "sensor"
    ]


class TimeConstants:
    """时间相关常量"""
    # 扫描间隔（秒）
    SCAN_INTERVAL = 300
    SENSOR_SCAN_INTERVAL = 10  # 传感器扫描间隔，提高更新频率
    
    # 延迟常量（秒）
    DEVICE_REGISTRATION_DELAY = 0.5  # 设备注册延迟，让主流程先完成
    GATEWAY_READY_DELAY = 1  # 网关就绪延迟
    DEVICE_SETUP_DELAY = 2  # 设备设置延迟
    GATEWAY_CHECK_INTERVAL = 30  # 网关检查间隔
    INITIAL_RETRY_DELAY = 5  # 初始重试延迟
    MIGRATION_DELAY = 1  # 迁移延迟
    RESTART_DELAY = 5  # 重启延迟


class OtherConstants:
    """其他常量"""
    # 其他常量
    MANUFACTURER = "慧尖"
    MODEL = "慧尖开窗器网关"
    VERSION = "1.1.7"
    
    # 图标常量
    ICON_GATEWAY = "mdi:gateway"
    ICON_WINDOW_OPENER = "mdi:window-closed"


# 为了保持向后兼容性，导出常用常量
# 配置流常量
CONF_GATEWAY_SN = ConfigConstants.CONF_GATEWAY_SN
CONF_GATEWAY_NAME = ConfigConstants.CONF_GATEWAY_NAME
CONF_DEVICE_SN = ConfigConstants.CONF_DEVICE_SN
CONF_DEVICE_NAME = ConfigConstants.CONF_DEVICE_NAME
DEFAULT_GATEWAY_NAME = ConfigConstants.DEFAULT_GATEWAY_NAME

# 服务常量
SERVICE_START_PAIRING = ServiceConstants.SERVICE_START_PAIRING
SERVICE_REFRESH_DEVICES = ServiceConstants.SERVICE_REFRESH_DEVICES
SERVICE_MIGRATE_DEVICES = ServiceConstants.SERVICE_MIGRATE_DEVICES

# 属性常量
ATTR_DEVICE_SN = AttributeConstants.ATTR_DEVICE_SN
ATTR_DEVICE_NAME = AttributeConstants.ATTR_DEVICE_NAME
ATTR_DEVICE_TYPE = AttributeConstants.ATTR_DEVICE_TYPE
ATTR_POSITION = AttributeConstants.ATTR_POSITION
ATTR_CURRENT_POSITION = AttributeConstants.ATTR_CURRENT_POSITION
ATTR_TARGET_POSITION = AttributeConstants.ATTR_TARGET_POSITION
ATTR_ANGLE = AttributeConstants.ATTR_ANGLE
ATTR_SPEED = AttributeConstants.ATTR_SPEED
ATTR_FORCE = AttributeConstants.ATTR_FORCE
ATTR_SAFETY_LOCK = AttributeConstants.ATTR_SAFETY_LOCK
ATTR_CHILD_LOCK = AttributeConstants.ATTR_CHILD_LOCK
ATTR_BATTERY = AttributeConstants.ATTR_BATTERY
ATTR_BATTERY_LEVEL = AttributeConstants.ATTR_BATTERY_LEVEL
ATTR_BATTERY_STATE = AttributeConstants.ATTR_BATTERY_STATE
ATTR_SIGNAL_STRENGTH = AttributeConstants.ATTR_SIGNAL_STRENGTH
ATTR_CONNECTION_STATUS = AttributeConstants.ATTR_CONNECTION_STATUS
ATTR_LAST_SEEN = AttributeConstants.ATTR_LAST_SEEN
ATTR_FIRMWARE_VERSION = AttributeConstants.ATTR_FIRMWARE_VERSION
ATTR_HARDWARE_VERSION = AttributeConstants.ATTR_HARDWARE_VERSION
ATTR_IP_ADDRESS = AttributeConstants.ATTR_IP_ADDRESS
ATTR_MAC_ADDRESS = AttributeConstants.ATTR_MAC_ADDRESS
ATTR_RSSI = AttributeConstants.ATTR_RSSI
ATTR_LQI = AttributeConstants.ATTR_LQI
ATTR_VOLTAGE = AttributeConstants.ATTR_VOLTAGE
ATTR_TEMPERATURE = AttributeConstants.ATTR_TEMPERATURE
ATTR_HUMIDITY = AttributeConstants.ATTR_HUMIDITY
ATTR_PRESSURE = AttributeConstants.ATTR_PRESSURE
ATTR_ILLUMINANCE = AttributeConstants.ATTR_ILLUMINANCE

# 设备类型常量
DEVICE_TYPE_WINDOW_OPENER = DeviceConstants.DEVICE_TYPE_WINDOW_OPENER
DEVICE_TYPE_GATEWAY = DeviceConstants.DEVICE_TYPE_GATEWAY

# 网关配置常量
MAX_DEVICES_PER_GATEWAY = DeviceConstants.MAX_DEVICES_PER_GATEWAY

# MQTT配置常量
DEFAULT_COMMAND_ID = MqttConstants.DEFAULT_COMMAND_ID
GATEWAY_TIMEOUT_SECONDS = MqttConstants.GATEWAY_TIMEOUT_SECONDS
TOPIC_GATEWAY_REQ_FORMAT = MqttConstants.TOPIC_GATEWAY_REQ_FORMAT
TOPIC_GATEWAY_RSP = MqttConstants.TOPIC_GATEWAY_RSP

# 状态常量
GATEWAY_STATUS_ONLINE = StatusConstants.GATEWAY_STATUS_ONLINE
GATEWAY_STATUS_OFFLINE = StatusConstants.GATEWAY_STATUS_OFFLINE
GATEWAY_STATUS_PAIRING = StatusConstants.GATEWAY_STATUS_PAIRING

# 错误代码常量
ERROR_CODE_SUCCESS = ErrorConstants.ERROR_CODE_SUCCESS
ERROR_CODE_BIND_EXISTS = ErrorConstants.ERROR_CODE_BIND_EXISTS

# 状态常量
STATE_PAIRING = StatusConstants.STATE_PAIRING
STATE_CONNECTED = StatusConstants.STATE_CONNECTED
STATE_DISCONNECTED = StatusConstants.STATE_DISCONNECTED
STATE_OPENING = StatusConstants.STATE_OPENING
STATE_CLOSING = StatusConstants.STATE_CLOSING
STATE_STOPPED = StatusConstants.STATE_STOPPED
STATE_OPEN = StatusConstants.STATE_OPEN
STATE_CLOSED = StatusConstants.STATE_CLOSED
STATE_UNKNOWN = StatusConstants.STATE_UNKNOWN

# 事件常量
EVENT_DEVICE_DISCOVERED = EventConstants.EVENT_DEVICE_DISCOVERED
EVENT_DEVICE_UPDATED = EventConstants.EVENT_DEVICE_UPDATED
EVENT_GATEWAY_CONNECTED = EventConstants.EVENT_GATEWAY_CONNECTED
EVENT_GATEWAY_DISCONNECTED = EventConstants.EVENT_GATEWAY_DISCONNECTED

# 配置选项常量
CONF_DISCOVERY_INTERVAL = ConfigConstants.CONF_DISCOVERY_INTERVAL
CONF_AUTO_DISCOVERY = ConfigConstants.CONF_AUTO_DISCOVERY
CONF_DEBUG_LOGGING = ConfigConstants.CONF_DEBUG_LOGGING

# 默认值
DEFAULT_DISCOVERY_INTERVAL = ConfigConstants.DEFAULT_DISCOVERY_INTERVAL
DEFAULT_AUTO_DISCOVERY = ConfigConstants.DEFAULT_AUTO_DISCOVERY
DEFAULT_DEBUG_LOGGING = ConfigConstants.DEFAULT_DEBUG_LOGGING

# 扫描间隔（秒）
SCAN_INTERVAL = TimeConstants.SCAN_INTERVAL
SENSOR_SCAN_INTERVAL = TimeConstants.SENSOR_SCAN_INTERVAL

# 延迟常量（秒）
DEVICE_REGISTRATION_DELAY = TimeConstants.DEVICE_REGISTRATION_DELAY
GATEWAY_READY_DELAY = TimeConstants.GATEWAY_READY_DELAY
DEVICE_SETUP_DELAY = TimeConstants.DEVICE_SETUP_DELAY
GATEWAY_CHECK_INTERVAL = TimeConstants.GATEWAY_CHECK_INTERVAL
INITIAL_RETRY_DELAY = TimeConstants.INITIAL_RETRY_DELAY
MIGRATION_DELAY = TimeConstants.MIGRATION_DELAY
RESTART_DELAY = TimeConstants.RESTART_DELAY

# 命令常量
COMMAND_OPEN = CommandConstants.COMMAND_OPEN
COMMAND_CLOSE = CommandConstants.COMMAND_CLOSE
COMMAND_STOP = CommandConstants.COMMAND_STOP
COMMAND_SET_POSITION = CommandConstants.COMMAND_SET_POSITION
COMMAND_A = CommandConstants.COMMAND_A
COMMAND_PAIR = CommandConstants.COMMAND_PAIR
COMMAND_DISCOVER = CommandConstants.COMMAND_DISCOVER
COMMAND_STATUS = CommandConstants.COMMAND_STATUS
COMMAND_START_PAIRING = CommandConstants.COMMAND_START_PAIRING

# 网关实体常量
ENTITY_GATEWAY_PREFIX = EntityConstants.ENTITY_GATEWAY_PREFIX
ENTITY_PAIRING_BUTTON_SUFFIX = EntityConstants.ENTITY_PAIRING_BUTTON_SUFFIX
ENTITY_ONLINE_SENSOR_SUFFIX = EntityConstants.ENTITY_ONLINE_SENSOR_SUFFIX

# 设备到网关映射表常量
DEVICE_TO_GATEWAY_MAPPING = DeviceConstants.DEVICE_TO_GATEWAY_MAPPING

# 全局手动删除设备列表常量
GLOBAL_MANUALLY_REMOVED_DEVICES = DeviceConstants.GLOBAL_MANUALLY_REMOVED_DEVICES

# 配对状态常量
PAIRING_STATUS_ACTIVE = StatusConstants.PAIRING_STATUS_ACTIVE
PAIRING_STATUS_INACTIVE = StatusConstants.PAIRING_STATUS_INACTIVE

# 其他常量
MANUFACTURER = OtherConstants.MANUFACTURER
MODEL = OtherConstants.MODEL
VERSION = OtherConstants.VERSION

# 平台常量
PLATFORMS = EntityConstants.PLATFORMS

# 图标常量
ICON_GATEWAY = OtherConstants.ICON_GATEWAY
ICON_WINDOW_OPENER = OtherConstants.ICON_WINDOW_OPENER
