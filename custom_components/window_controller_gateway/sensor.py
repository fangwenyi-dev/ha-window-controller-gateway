"""开窗器网关传感器平台"""
import asyncio
import logging

from typing import Optional

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from datetime import datetime, timedelta

from .const import (
    DOMAIN,
    CONF_GATEWAY_SN,
    CONF_GATEWAY_NAME,
    DEFAULT_GATEWAY_NAME,
    MANUFACTURER
)
from .base_entity import WindowControllerBaseEntity

_LOGGER = logging.getLogger(__name__)

from .utils import get_entity_registry


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
        
        self._attr_name = "电池电压"
        # unique_id 基于设备SN，与v1.1.8保持一致
        self._attr_unique_id = f"{gateway_sn}_{device_sn}_battery"
        self._attr_device_class = SensorDeviceClass.VOLTAGE
        self._attr_state_class = "measurement"
        self.last_update_time = None  # 最后更新时间
        self.entry_id = entry_id
        # 添加图标
        self._attr_icon = "mdi:battery"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        
        # 初始化状态
        self._update_state()
        
        # 注册状态更新回调
        # 注意：这里需要从hass.data中获取mqtt_handler
        # 由于初始化时可能还未设置，这里暂时不注册
        # 回调注册将在async_add_entities后通过其他方式处理
    
    @property
    def device_info(self) -> DeviceInfo:
        """返回设备信息"""
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_sn)},
            name=self.device_name,
            manufacturer=MANUFACTURER,
            model="开窗器"
        )
    
    def _update_state(self):
        """从设备管理器更新状态"""
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
    
    async def async_update(self) -> None:
        """更新实体状态"""
        self._update_state()
        self.async_write_ha_state()


class WindowControllerStatusSensor(SensorEntity):
    """开窗器状态传感器"""
    
    _attr_has_entity_name = True
    
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
        self._attr_name = "状态"
        # unique_id 基于设备SN，与v1.1.8保持一致
        self._attr_unique_id = f"{gateway_sn}_{device_sn}_status"
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = ["closed", "open"]
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self.last_update_time = None  # 最后更新时间
        
        # 初始化状态
        self._update_state()
    
    @property
    def device_info(self) -> DeviceInfo:
        """返回设备信息"""
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_sn)},
            name=self._device_name,
            manufacturer=MANUFACTURER,
            model="开窗器"
        )
    
    def _update_state(self):
        """从设备管理器更新状态"""
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

    async def async_update(self) -> None:
        """更新实体状态"""
        self._update_state()
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置传感器实体"""
    _LOGGER.info("设置传感器平台: %s, entry_id: %s", entry.entry_id, entry.entry_id)
    # 从设备管理器获取设备
    domain_data = hass.data[DOMAIN]
    entry_data = domain_data.get(entry.entry_id)
    
    _LOGGER.info("传感器平台: 获取到 domain_data, keys: %s", list(domain_data.keys()))
    
    if not entry_data:
        _LOGGER.error("配置条目数据未找到: %s, domain_data keys: %s", entry.entry_id, list(domain_data.keys()))
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
        
        # 检查实体是否已存在（避免重复创建）
        entity_registry = get_entity_registry(hass)
        
        battery_unique_id = f"{gateway_sn}_{device_sn}_battery"
        status_unique_id = f"{gateway_sn}_{device_sn}_status"
        
        battery_exists = entity_registry.async_get_entity_id("sensor", DOMAIN, battery_unique_id) is not None
        status_exists = entity_registry.async_get_entity_id("sensor", DOMAIN, status_unique_id) is not None
        
        if battery_exists and status_exists:
            _LOGGER.info("传感器实体已存在，跳过创建: %s", device_sn)
            return
        
        entities_to_add = []
        sensors_to_track = {}
        
        # 检查并创建电池电压传感器
        if not battery_exists:
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
        
        # 检查并创建状态传感器
        if not status_exists:
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
        
        # 调用async_add_entities添加实体
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
    
    # 为每个设备创建传感器（直接创建所有传感器，不检查实体是否存在）
    entities = []
    
    try:
        devices = device_manager.get_all_devices()
        _LOGGER.info("传感器平台: 获取到 %d 个设备", len(devices))
        
        for device in devices:
            device_sn = device.get("sn")
            device_name = device.get("name")
            
            if device_sn and device_name:
                battery_sensor = WindowControllerBatterySensor(
                    hass,
                    device_manager,
                    gateway_sn,
                    device_sn,
                    device_name
                )
                entities.append(battery_sensor)
                if device_sn not in created_sensors:
                    created_sensors[device_sn] = {}
                created_sensors[device_sn]["battery"] = battery_sensor
                
                status_sensor = WindowControllerStatusSensor(
                    hass,
                    device_manager,
                    gateway_sn,
                    device_sn,
                    device_name
                )
                entities.append(status_sensor)
                if device_sn not in created_sensors:
                    created_sensors[device_sn] = {}
                created_sensors[device_sn]["status"] = status_sensor
                
    except Exception as e:
        _LOGGER.error("传感器平台: 创建传感器实体时发生错误: %s", e, exc_info=True)
    
    _LOGGER.info("传感器平台: 检查 entities 数量: %d", len(entities))
    _LOGGER.info("传感器平台: entities bool: %s", bool(entities))
    
    if entities:
        _LOGGER.info("传感器平台: 进入 if entities 块, 数量=%d", len(entities))
        
        # 直接调用 async_add_entities（与 button.py 保持一致）
        async_add_entities(entities)
        _LOGGER.info("传感器平台: async_add_entities 调用完成")
        _LOGGER.info("已添加 %d 个传感器实体", len(entities))
        
        # 注册回调
        try:
            domain_data = hass.data.get(DOMAIN, {})
            entry_data = domain_data.get(entry.entry_id)
            if entry_data:
                mqtt_handler = entry_data.get("mqtt_handler")
                if mqtt_handler:
                    for device_sn, sensors in created_sensors.items():
                        if "battery" in sensors:
                            battery_sensor = sensors["battery"]
                            mqtt_handler.add_status_callback(device_sn, battery_sensor.async_update)
                        if "status" in sensors:
                            status_sensor = sensors["status"]
                            mqtt_handler.add_status_callback(device_sn, status_sensor.async_update)
                    _LOGGER.info("传感器回调注册完成")
        except Exception as e:
            _LOGGER.error("传感器平台: 注册回调失败: %s", e, exc_info=True)
    else:
        _LOGGER.info("当前没有设备，等待设备添加")
