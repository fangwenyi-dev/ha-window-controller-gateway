"""持久化数据管理 - 避免 __init__.py 与 device_manager.py 之间的循环导入"""
import logging
import os
import json
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    DEVICE_TO_GATEWAY_MAPPING,
    GLOBAL_MANUALLY_REMOVED_DEVICES,
)

_LOGGER = logging.getLogger(__name__)

PERSISTENT_DATA_FILE = "window_controller_gateway_data.json"

async def load_persistent_data(hass: HomeAssistant) -> None:
    """加载持久化的设备映射和手动删除列表"""
    try:
        config_dir = hass.config.config_dir
        data_file = os.path.join(config_dir, PERSISTENT_DATA_FILE)

        if os.path.exists(data_file):
            def _read_file():
                with open(data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)

            data = await hass.async_add_executor_job(_read_file)

            if 'device_to_gateway_mapping' in data:
                mapping = data['device_to_gateway_mapping']
                hass.data[DOMAIN][DEVICE_TO_GATEWAY_MAPPING] = mapping
                _LOGGER.info("已加载设备到网关映射表，共 %d 个设备", len(mapping))

            if 'manually_removed_devices' in data:
                removed_set = set(data['manually_removed_devices'])
                hass.data[DOMAIN][GLOBAL_MANUALLY_REMOVED_DEVICES] = removed_set
                _LOGGER.info("已加载手动删除设备列表，共 %d 个设备", len(removed_set))

    except Exception as e:
        _LOGGER.info("加载持久化数据失败: %s", e)

async def save_persistent_data(hass: HomeAssistant) -> None:
    """保存设备映射和手动删除列表到持久化存储"""
    try:
        config_dir = hass.config.config_dir
        data_file = os.path.join(config_dir, PERSISTENT_DATA_FILE)

        data = {
            'device_to_gateway_mapping': hass.data[DOMAIN].get(DEVICE_TO_GATEWAY_MAPPING, {}),
            'manually_removed_devices': list(hass.data[DOMAIN].get(GLOBAL_MANUALLY_REMOVED_DEVICES, set()))
        }

        def _write_file():
            tmp_file = data_file + ".tmp"
            try:
                with open(tmp_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                os.replace(tmp_file, data_file)
            except OSError:
                with open(data_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

        await hass.async_add_executor_job(_write_file)

        _LOGGER.debug("已保存持久化数据")

    except Exception as e:
        _LOGGER.error("保存持久化数据失败: %s", e)