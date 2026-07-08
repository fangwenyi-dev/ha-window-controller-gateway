"""持久化数据管理 - 避免 __init__.py 与 device_manager.py 之间的循环导入"""
import logging
import os
import json
import asyncio
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    DEVICE_TO_GATEWAY_MAPPING,
    GLOBAL_MANUALLY_REMOVED_DEVICES,
)

_LOGGER = logging.getLogger(__name__)

PERSISTENT_DATA_FILE = "window_controller_gateway_data.json"
SCHEMA_VERSION = 1

# 串行化写入锁 + 防抖标志
_save_lock = asyncio.Lock()
_save_pending = False


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

            version = data.get("schema_version", 0)
            if version > SCHEMA_VERSION:
                _LOGGER.warning(
                    "持久化数据版本(%d)高于当前支持版本(%d)，可能不兼容",
                    version, SCHEMA_VERSION
                )

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
    """保存设备映射和手动删除列表到持久化存储

    使用 asyncio.Lock 串行化写入，确保不会有两个协程同时写同一个 .tmp 文件。
    通过 _save_pending 标志实现防抖：当写入期间有新的保存请求到来时，
    当前写入完成后会再执行一次写入（读取最新数据），确保数据不会丢失。
    后续的保存请求只需设置标志即可返回，无需重复写入。
    """
    global _save_pending

    # 如果已有保存任务在执行或等待，只需标记还需要再保存一次
    # 正在执行的任务会在完成后检查此标志并自动补写最新数据
    if _save_pending:
        _save_pending = True
        return

    _save_pending = True
    async with _save_lock:
        while _save_pending:
            _save_pending = False
            await _do_save(hass)


async def _do_save(hass: HomeAssistant) -> None:
    """执行实际的文件写入操作"""
    try:
        config_dir = hass.config.config_dir
        data_file = os.path.join(config_dir, PERSISTENT_DATA_FILE)

        data = {
            'schema_version': SCHEMA_VERSION,
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
