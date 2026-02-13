"""开窗器网关实体"""
import logging
import asyncio
from typing import Optional

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass
)
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    CONF_GATEWAY_SN,
    CONF_GATEWAY_NAME,
    DEFAULT_GATEWAY_NAME,
    ENTITY_GATEWAY_PREFIX,
    ENTITY_ONLINE_SENSOR_SUFFIX,
    ENTITY_PAIRING_BUTTON_SUFFIX,
    MANUFACTURER,
    MODEL,
    GATEWAY_READY_DELAY
)

_LOGGER = logging.getLogger(__name__)



class GatewayOnlineSensor(BinarySensorEntity):
    """网关在线状态传感器"""
    
    def __init__(
        self,
        hass: HomeAssistant,
        device_manager,
        mqtt_handler,
        gateway_sn: str,
        gateway_name: str,
        entry_id: str = None
    ):
        """初始化网关在线状态传感器"""
        self.hass = hass
        self.device_manager = device_manager
        self.mqtt_handler = mqtt_handler
        self.gateway_sn = gateway_sn
        self.gateway_name = gateway_name
        self.entry_id = entry_id
        self._attr_name = f"{gateway_name} 在线"
        # unique_id基于网关SN，确保同一网关只有一个在线状态传感器
        self._attr_unique_id = f"{gateway_sn}_online"
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        self._attr_is_on = False
        # 添加图标
        self._attr_icon = "mdi:access-point"
        
        # 添加状态更新回调
        self.mqtt_handler.add_status_callback(self._on_status_change)
        
        # 初始状态更新
        self._update_state()
    
    @property
    def device_info(self) -> DeviceInfo:
        """返回设备信息"""
        return DeviceInfo(
            identifiers={(DOMAIN, self.gateway_sn)},
            name=self.gateway_name,
            manufacturer=MANUFACTURER,
            model=MODEL,
            serial_number=self.gateway_sn
        )
    
    def _update_state(self):
        """更新状态"""
        # 从MQTT处理器获取连接状态
        self._attr_is_on = self.mqtt_handler.connected
        _LOGGER.debug("网关 %s 在线状态更新为: %s", self.gateway_sn, self._attr_is_on)
    
    def _on_status_change(self):
        """当MQTT状态改变时调用"""
        self._update_state()
        # 通知Home Assistant状态已更新
        # 使用schedule_update_ha_state确保在事件循环线程中执行
        try:
            if self.hass is not None:
                self.schedule_update_ha_state()
            else:
                _LOGGER.warning("无法更新网关状态：hass为None")
        except Exception as e:
            _LOGGER.error("更新网关状态失败: %s", e)
    
    async def async_update(self):
        """更新实体状态"""
        self._update_state()
    
    async def async_will_remove_from_hass(self):
        """当实体从HA中移除时调用"""
        # 移除状态更新回调
        self.mqtt_handler.remove_status_callback(self._on_status_change)

class GatewayPairingButton(ButtonEntity):
    """网关配对按键"""
    
    def __init__(
        self,
        hass: HomeAssistant,
        device_manager,
        mqtt_handler,
        gateway_sn: str,
        gateway_name: str,
        entry_id: str = None
    ):
        """初始化网关配对按键"""
        self.hass = hass
        self.device_manager = device_manager
        self.mqtt_handler = mqtt_handler
        self.gateway_sn = gateway_sn
        self.gateway_name = gateway_name
        self.entry_id = entry_id
        self._attr_name = f"{gateway_name} 配对"
        # unique_id基于网关SN，确保同一网关只有一个配对按钮
        self._attr_unique_id = f"{gateway_sn}_pairing"
        # 添加图标
        self._attr_icon = "mdi:plus-circle"
    
    @property
    def device_info(self) -> DeviceInfo:
        """返回设备信息 - 与网关关联"""
        return DeviceInfo(
            identifiers={(DOMAIN, self.gateway_sn)},
            name=self.gateway_name,
            manufacturer=MANUFACTURER,
            model=MODEL
        )
    
    async def async_press(self) -> None:
        """按下按键，触发配对模式"""
        try:
            # 调用MQTT处理器的开始配对方法
            await self.mqtt_handler.start_pairing()
            _LOGGER.info("已触发网关 %s 的配对模式", self.gateway_sn)
        except Exception as e:
            _LOGGER.error("触发网关配对模式失败: %s", e)

class GatewayDeviceRemoveButton(ButtonEntity):
    """网关设备删除按键"""
    
    def __init__(
        self,
        hass: HomeAssistant,
        device_manager,
        mqtt_handler,
        gateway_sn: str,
        gateway_name: str,
        device_sn: str,
        device_name: str,
        entry_id: str = None
    ):
        """初始化网关设备删除按键"""
        self.hass = hass
        self.device_manager = device_manager
        self.mqtt_handler = mqtt_handler
        self.gateway_sn = gateway_sn
        self.gateway_name = gateway_name
        self.device_sn = device_sn
        self.device_name = device_name
        self.entry_id = entry_id
        self._attr_name = f"开窗器 {device_sn[-4:]} 删除"
        # unique_id基于网关SN和设备SN，确保同一网关的同一设备只有一个删除按钮
        self._attr_unique_id = f"{gateway_sn}_remove_{device_sn}"
        # 添加图标
        self._attr_icon = "mdi:delete"
    
    @property
    def device_info(self) -> DeviceInfo:
        """返回设备信息 - 与网关关联，显示在网关控制栏中"""
        return DeviceInfo(
            identifiers={(DOMAIN, self.gateway_sn)},
            name=self.gateway_name,
            manufacturer=MANUFACTURER,
            model=MODEL
        )
    
    async def async_press(self) -> None:
        """按下按键，删除设备"""
        try:
            # 调用MQTT处理器的解绑设备方法
            await self.mqtt_handler.unbind_device(self.device_sn)
            _LOGGER.info("已发送解绑命令，设备SN: %s", self.device_sn)
            
            # 等待1秒，确保网关有足够时间处理解绑命令
            await asyncio.sleep(GATEWAY_READY_DELAY)
            
            # 从设备管理器中删除设备
            await self.device_manager.remove_device(self.device_sn)
            _LOGGER.info("已从系统中删除设备: %s", self.device_sn)
            
            # 从实体注册表中删除自身（删除按钮）
            from homeassistant.helpers.entity_registry import async_get
            entity_registry = async_get(self.hass)
            
            # 方法1：使用精确的唯一ID查找
            entity_id = entity_registry.async_get_entity_id("button", DOMAIN, self._attr_unique_id)
            if entity_id:
                entity_registry.async_remove(entity_id)
                _LOGGER.info("已从实体注册表中删除删除按钮: %s", entity_id)
            else:
                # 方法2：使用不区分大小写的部分匹配
                import re
                found = False
                
                # 遍历所有实体，查找匹配的按钮
                for entity in entity_registry.entities.values():
                    if entity.domain == "button" and entity.platform == DOMAIN:
                        # 检查实体是否包含网关SN和设备SN（不区分大小写）
                        unique_id_lower = entity.unique_id.lower()
                        gateway_sn_lower = self.gateway_sn.lower()
                        device_sn_lower = self.device_sn.lower()
                        
                        if gateway_sn_lower in unique_id_lower and device_sn_lower in unique_id_lower:
                            entity_registry.async_remove(entity.entity_id)
                            _LOGGER.info("已通过不区分大小写的部分匹配从实体注册表中删除删除按钮: %s (唯一ID: %s)", entity.entity_id, entity.unique_id)
                            found = True
                            break
                
                # 方法3：如果仍未找到，尝试使用更宽松的匹配
                if not found:
                    for entity in entity_registry.entities.values():
                        if entity.domain == "button" and entity.platform == DOMAIN:
                            # 检查实体ID是否包含设备SN的一部分
                            if self.device_sn[-4:] in entity.unique_id:
                                entity_registry.async_remove(entity.entity_id)
                                _LOGGER.info("已通过设备SN后4位匹配从实体注册表中删除删除按钮: %s (唯一ID: %s)", entity.entity_id, entity.unique_id)
                                found = True
                                break
                
                if not found:
                    # 实体未找到是正常情况，因为它可能已经被删除或不存在
                    # 将警告日志改为调试日志，避免在正常操作中产生错误信息
                    _LOGGER.debug("删除按钮实体未找到，可能已经被删除: %s", self._attr_unique_id)
                    # 记录所有相关实体，以便调试
                    related_entities = []
                    for entity in entity_registry.entities.values():
                        if entity.domain == 'button' and entity.platform == DOMAIN:
                            related_entities.append((entity.entity_id, entity.unique_id))
                    if related_entities:
                        _LOGGER.debug("注册表中相关的按钮实体: %s", related_entities)
        except Exception as e:
            _LOGGER.error("触发设备解绑模式失败: %s", e)

class GatewayReplaceButton(ButtonEntity):
    """网关替换按键"""
    
    def __init__(
        self,
        hass: HomeAssistant,
        device_manager,
        mqtt_handler,
        gateway_sn: str,
        gateway_name: str,
        entry_id: str = None
    ):
        """初始化网关替换按键"""
        self.hass = hass
        self.device_manager = device_manager
        self.mqtt_handler = mqtt_handler
        self.gateway_sn = gateway_sn
        self.gateway_name = gateway_name
        self.entry_id = entry_id
        self._attr_name = f"{gateway_name} 替换旧网关"
        # unique_id基于网关SN，确保同一网关只有一个替换按钮
        self._attr_unique_id = f"{gateway_sn}_replace"
        # 添加图标
        self._attr_icon = "mdi:gateway-transfer"
        # 添加设备ID属性，用于服务调用
        self.device_id = gateway_sn
        # 添加防重复点击标志
        self._is_processing = False
    
    @property
    def device_info(self) -> DeviceInfo:
        """返回设备信息 - 与网关关联"""
        return DeviceInfo(
            identifiers={(DOMAIN, self.gateway_sn)},
            name=self.gateway_name,
            manufacturer=MANUFACTURER,
            model=MODEL
        )
    
    async def async_press(self) -> None:
        """按下按键，触发网关替换模式"""
        # 防重复点击检查
        if self._is_processing:
            _LOGGER.debug("网关替换操作正在处理中，忽略重复点击")
            return
        
        try:
            # 设置处理中标志
            self._is_processing = True
            
            # 检查是否已经存在一个网关替换配置流
            existing_flow = None
            for flow in self.hass.config_entries.flow.async_progress():
                if flow["handler"] == DOMAIN and flow.get("context", {}).get("source") == "replace_gateway":
                    existing_flow = flow
                    break
            
            if existing_flow:
                # 已经存在一个替换配置流，使用它
                _LOGGER.info("已存在网关替换配置流，使用现有流")
                return
            
            # 启动网关替换配置流
            await self.hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": "replace_gateway"},
                data={
                    "gateway_sn": self.gateway_sn,
                    "device_id": self.device_id
                }
            )
            
            _LOGGER.info("已启动网关替换配置流，设备ID: %s", self.device_id)
            
        except Exception as e:
            _LOGGER.error("触发网关替换模式失败: %s", e)
            # 发送错误通知
            await self.hass.services.async_call(
                "notify",
                "persistent_notification",
                {
                    "title": "网关替换操作失败",
                    "message": f"触发网关替换操作时出错: {e}\n\n请手动进入开发者工具 → 服务，选择 'window_controller_gateway.migrate_devices' 服务并填写服务数据。"
                },
                blocking=False
            )
        finally:
            # 无论成功失败，都设置处理完成标志
            self._is_processing = False