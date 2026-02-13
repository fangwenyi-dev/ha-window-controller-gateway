"""开窗器网关传感器平台"""
import logging
from typing import Optional

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo

from datetime import timedelta

from .const import (
    DOMAIN,
    CONF_GATEWAY_SN,
    CONF_GATEWAY_NAME,
    DEFAULT_GATEWAY_NAME
)
from .base_entity import WindowControllerBaseEntity
from .utils import get_device_gateway_mapping
from .const import SENSOR_SCAN_INTERVAL

# 传感器扫描间隔，设置为10秒以提高更新频率
SCAN_INTERVAL = timedelta(seconds=SENSOR_SCAN_INTERVAL)

_LOGGER = logging.getLogger(__name__)

from .utils import get_entity_registry

# 直接使用从utils导入的get_entity_registry函数，不再重复定义


class WindowControllerBatterySensor(WindowControllerBaseEntity, SensorEntity):
    """开窗器电池电压传感器"""
    
    def __init__(
        self,
        hass: HomeAssistant,
        device_manager,
        gateway_sn: str,
        device_sn: str,
        device_name: str,
        entry_id: str = None
    ):
        """初始化电池电压传感器"""
        # 调用基类初始化，mqtt_handler参数传入None
        super().__init__(
            hass=hass,
            device_manager=device_manager,
            mqtt_handler=None,
            gateway_sn=gateway_sn,
            device_sn=device_sn,
            device_name=device_name
        )
        
        self._attr_name = f"{device_name} 电池电压"
        # unique_id基于设备SN，确保同一设备只有一个实体
        self._attr_unique_id = f"{device_sn}_battery"
        self._attr_device_class = SensorDeviceClass.VOLTAGE
        self._attr_state_class = "measurement"
        self.last_update_time = None  # 最后更新时间
        self.entry_id = entry_id
        # 添加图标
        self._attr_icon = "mdi:battery"
        
        # 初始化状态
        self._update_state()
        
        # 注册状态更新回调
        # 注意：这里需要从hass.data中获取mqtt_handler
        # 由于初始化时可能还未设置，这里暂时不注册
        # 回调注册将在async_add_entities后通过其他方式处理
    
    @property
    def device_info(self) -> DeviceInfo:
        """返回设备信息"""
        from .const import MANUFACTURER
        # 使用基类方法获取当前关联的网关
        current_gateway_sn = self.get_current_gateway_sn()
        
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_sn)},
            name=self.device_name,
            manufacturer=MANUFACTURER,
            model="开窗器",
            via_device=(DOMAIN, current_gateway_sn)
        )
    
    def _update_state(self):
        """从设备管理器更新状态"""
        from datetime import datetime, timedelta
        
        device = self.device_manager.get_device(self.device_sn)
        if device:
            attributes = device.get("attributes", {})
            voltage = attributes.get("voltage")
            if voltage is not None:
                self._attr_native_value = voltage
                self.last_update_time = datetime.now()
                _LOGGER.debug("设备 %s 电池电压更新: %.1fV", self.device_sn, voltage)
        
        # 检查是否超过15分钟没有更新
        if self.last_update_time and (datetime.now() - self.last_update_time) > timedelta(minutes=15):
            self._attr_native_value = None
            _LOGGER.debug("设备 %s 电池电压数据超时", self.device_sn)
    
    @property
    def native_unit_of_measurement(self):
        """返回单位 - 确保即使状态为None时也返回正确的单位"""
        return "V"
    
    async def async_update(self):
        """更新实体状态"""
        self._update_state()


class WindowControllerStatusSensor(SensorEntity):
    """开窗器状态传感器"""
    
    def __init__(
        self,
        hass: HomeAssistant,
        device_manager,
        gateway_sn: str,
        device_sn: str,
        device_name: str,
        entry_id: str = None
    ):
        """初始化状态传感器"""
        self.hass = hass
        self.device_manager = device_manager
        self.gateway_sn = gateway_sn
        self.device_sn = device_sn
        self._device_name = device_name
        self.entry_id = entry_id
        self._attr_name = f"{device_name} 状态"
        # unique_id基于设备SN，确保同一设备只有一个实体
        self._attr_unique_id = f"{device_sn}_status"
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = ["closed", "open"]
        self.last_update_time = None  # 最后更新时间
        
        # 初始化状态
        self._update_state()
    
    @property
    def device_info(self) -> DeviceInfo:
        """返回设备信息"""
        from .const import MANUFACTURER, DEVICE_TO_GATEWAY_MAPPING
        # 动态获取设备当前关联的网关
        current_gateway_sn = self.gateway_sn
        if DEVICE_TO_GATEWAY_MAPPING in self.hass.data[DOMAIN]:
            device_to_gateway_mapping = self.hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING]
            if self.device_sn in device_to_gateway_mapping:
                current_gateway_sn = device_to_gateway_mapping[self.device_sn]
                _LOGGER.debug("设备 %s 当前关联到网关: %s", self.device_sn, current_gateway_sn)
        
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_sn)},
            name=self._device_name,
            manufacturer=MANUFACTURER,
            model="开窗器",
            via_device=(DOMAIN, current_gateway_sn)
        )
    
    def _update_state(self):
        """从设备管理器更新状态"""
        from datetime import datetime, timedelta
        
        device = self.device_manager.get_device(self.device_sn)
        if device:
            # 优先使用设备状态
            status = device.get("status")
            if status in ["closed", "open"]:
                self._attr_native_value = status
                self.last_update_time = datetime.now()
                _LOGGER.debug("设备 %s 状态更新为: %s", self.device_sn, status)
            else:
                # 如果没有状态，使用r_travel判断
                attributes = device.get("attributes", {})
                r_travel = attributes.get("r_travel")
                if r_travel is not None:
                    new_status = "closed" if r_travel == 0 else "open"
                    self._attr_native_value = new_status
                    self.last_update_time = datetime.now()
                    _LOGGER.debug("设备 %s 状态根据r_travel更新为: %s", self.device_sn, new_status)
        
        # 检查是否超过15分钟没有更新
        if self.last_update_time and (datetime.now() - self.last_update_time) > timedelta(minutes=15):
            self._attr_native_value = None
    
    async def async_update(self):
        """更新实体状态"""
        self._update_state()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置传感器实体"""
    _LOGGER.info("设置传感器平台")
    # 从设备管理器获取设备
    domain_data = hass.data[DOMAIN]
    entry_data = domain_data.get(entry.entry_id)
    
    if not entry_data:
        _LOGGER.error("配置条目数据未找到: %s", entry.entry_id)
        return
        
    device_manager = entry_data.get("device_manager")
    
    if not device_manager:
        _LOGGER.error("设备管理器未找到")
        return
    
    gateway_sn = entry.data[CONF_GATEWAY_SN]
    
    # 跟踪创建的传感器实体
    created_sensors = {}
    
    # 定义设备添加回调函数
    async def on_device_added(device_sn: str, device_name: str, device_type: str):
        """设备添加回调，自动创建传感器实体"""
        _LOGGER.info("收到设备添加回调: %s - %s", device_name, device_sn)
        
        # 检查实体是否已经存在于实体注册表中
        entity_registry = get_entity_registry(hass)
        
        # 存储要添加的实体
        entities_to_add = []
        sensors_to_track = {}
        
        # 检查并创建电池电压传感器
        battery_sensor_unique_id = f"{device_sn}_battery"
        existing_battery_entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, battery_sensor_unique_id)
        if not existing_battery_entity_id:
            battery_sensor = WindowControllerBatterySensor(
                hass,
                device_manager,
                gateway_sn,
                device_sn,
                device_name
            )
            entities_to_add.append(battery_sensor)
            sensors_to_track["battery"] = battery_sensor
            _LOGGER.debug("为设备 %s 添加电池传感器", device_name)
        else:
            _LOGGER.debug("设备 %s 的电池传感器已存在，跳过创建", device_name)
        
        # 检查并创建状态传感器
        status_sensor_unique_id = f"{device_sn}_status"
        existing_status_entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, status_sensor_unique_id)
        if not existing_status_entity_id:
            status_sensor = WindowControllerStatusSensor(
                hass,
                device_manager,
                gateway_sn,
                device_sn,
                device_name
            )
            entities_to_add.append(status_sensor)
            sensors_to_track["status"] = status_sensor
            _LOGGER.debug("为设备 %s 添加状态传感器", device_name)
        else:
            _LOGGER.debug("设备 %s 的状态传感器已存在，跳过创建", device_name)
        
        # 只有当有实体需要添加时才调用async_add_entities
        if entities_to_add:
            async_add_entities(entities_to_add)
            _LOGGER.info("为新设备 %s 添加了传感器实体", device_name)
            
            # 跟踪创建的传感器
            created_sensors[device_sn] = sensors_to_track
            
            # 注册状态更新回调
            # 注意：这里需要从hass.data中获取mqtt_handler
            domain_data = hass.data.get(DOMAIN, {})
            entry_data = domain_data.get(entry.entry_id)
            if entry_data:
                mqtt_handler = entry_data.get("mqtt_handler")
                if mqtt_handler:
                    # 为电池传感器注册回调
                    if "battery" in sensors_to_track:
                        mqtt_handler.add_status_callback(device_sn, sensors_to_track["battery"].async_update)
                    # 为状态传感器注册回调
                    if "status" in sensors_to_track:
                        mqtt_handler.add_status_callback(device_sn, sensors_to_track["status"].async_update)
                    _LOGGER.debug("为设备 %s 注册了状态更新回调", device_sn)

    # 定义设备移除回调函数
    async def on_device_removed(device_sn: str, device_name: str, device_type: str):
        """设备移除回调，清理相关传感器"""
        _LOGGER.info("收到设备移除回调: %s - %s", device_name, device_sn)
        if device_sn in created_sensors:
            # 获取传感器实体
            sensors = created_sensors[device_sn]
            # 从跟踪字典中删除
            del created_sensors[device_sn]
            _LOGGER.info("已清理设备 %s 的传感器实体跟踪", device_name)
            
            # 移除状态更新回调
            try:
                domain_data = hass.data.get(DOMAIN, {})
                entry_data = domain_data.get(entry.entry_id)
                if entry_data:
                    mqtt_handler = entry_data.get("mqtt_handler")
                    if mqtt_handler:
                        # 移除电池传感器回调
                        if "battery" in sensors:
                            battery_entity = sensors["battery"]
                            mqtt_handler.remove_status_callback(device_sn, battery_entity.async_update)
                        # 移除状态传感器回调
                        if "status" in sensors:
                            status_entity = sensors["status"]
                            mqtt_handler.remove_status_callback(device_sn, status_entity.async_update)
                        _LOGGER.debug("已移除设备 %s 的状态更新回调", device_sn)
            except Exception as e:
                _LOGGER.error("移除设备 %s 的状态更新回调失败: %s", device_name, e)
            
            # 尝试从实体注册表中删除实体
            try:
                entity_registry = get_entity_registry(hass)
                # 删除电池传感器
                if "battery" in sensors:
                    battery_entity = sensors["battery"]
                    if battery_entity.entity_id:
                        entity_registry.async_remove(battery_entity.entity_id)
                        _LOGGER.info("已从实体注册表中删除设备 %s 的电池传感器", device_name)
                # 删除状态传感器
                if "status" in sensors:
                    status_entity = sensors["status"]
                    if status_entity.entity_id:
                        entity_registry.async_remove(status_entity.entity_id)
                        _LOGGER.info("已从实体注册表中删除设备 %s 的状态传感器", device_name)
            except Exception as e:
                _LOGGER.error("从实体注册表中删除设备 %s 的传感器失败: %s", device_name, e)

    # 设置设备添加回调
    device_manager.set_device_added_callback(on_device_added)
    # 设置设备移除回调
    device_manager.set_device_removed_callback(on_device_removed)
    _LOGGER.info("已设置设备回调")
    
    # 为每个设备创建传感器
    entities = []
    devices = device_manager.get_all_devices()
    
    # 获取实体注册表，用于检查实体是否已存在
    entity_registry = get_entity_registry(hass)
    
    for device in devices:
        device_sn = device.get("sn")
        device_name = device.get("name")
        
        if device_sn and device_name:
            # 检查并创建电池电压传感器
            battery_sensor_unique_id = f"{device_sn}_battery"
            existing_battery_entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, battery_sensor_unique_id)
            if not existing_battery_entity_id:
                battery_sensor = WindowControllerBatterySensor(
                    hass,
                    device_manager,
                    gateway_sn,
                    device_sn,
                    device_name
                )
                entities.append(battery_sensor)
                # 跟踪创建的传感器
                if device_sn not in created_sensors:
                    created_sensors[device_sn] = {}
                created_sensors[device_sn]["battery"] = battery_sensor
                _LOGGER.debug("为设备 %s 添加电池传感器", device_name)
            else:
                _LOGGER.debug("设备 %s 的电池传感器已存在于实体注册表中，跳过创建", device_name)
            
            # 检查并创建状态传感器
            status_sensor_unique_id = f"{device_sn}_status"
            existing_status_entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, status_sensor_unique_id)
            if not existing_status_entity_id:
                status_sensor = WindowControllerStatusSensor(
                    hass,
                    device_manager,
                    gateway_sn,
                    device_sn,
                    device_name
                )
                entities.append(status_sensor)
                # 跟踪创建的传感器
                if device_sn not in created_sensors:
                    created_sensors[device_sn] = {}
                created_sensors[device_sn]["status"] = status_sensor
                _LOGGER.debug("为设备 %s 添加状态传感器", device_name)
            else:
                _LOGGER.debug("设备 %s 的状态传感器已存在于实体注册表中，跳过创建", device_name)
            
            if device_sn in created_sensors:
                _LOGGER.info("为设备 %s 添加传感器实体", device_name)
    
    if entities:
        async_add_entities(entities)
        _LOGGER.info("已添加 %d 个传感器实体", len(entities))
        
        # 为已添加的传感器注册状态更新回调
        domain_data = hass.data.get(DOMAIN, {})
        entry_data = domain_data.get(entry.entry_id)
        if entry_data:
            mqtt_handler = entry_data.get("mqtt_handler")
            if mqtt_handler:
                # 为每个已创建的传感器注册状态更新回调
                # 遍历已创建的传感器，为每个设备的传感器注册回调
                for device_sn, sensors in created_sensors.items():
                    if "battery" in sensors:
                        battery_sensor = sensors["battery"]
                        mqtt_handler.add_status_callback(device_sn, battery_sensor.async_update)
                        _LOGGER.debug("为设备 %s 的电池传感器注册了状态更新回调", device_sn)
                    if "status" in sensors:
                        status_sensor = sensors["status"]
                        mqtt_handler.add_status_callback(device_sn, status_sensor.async_update)
                        _LOGGER.debug("为设备 %s 的状态传感器注册了状态更新回调", device_sn)
    else:
        _LOGGER.info("当前没有设备，等待设备添加")
