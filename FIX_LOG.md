# 13 个代码质量问题修复变更日志
# 回滚指南：根据时间戳可逐一回退每个修复

## Fix 1 - sensor.py - 传感器状态更新未推送至前端
- **文件**: sensor.py 第 104 行、第 175 行
- **问题**: BatterySensor 和 StatusSensor 的 async_update() 更新内部状态后未调用 async_write_ha_state()
- **修复**: 在 async_update() 末尾添加 self.async_write_ha_state()
- **回滚**: 删除添加的 async_write_ha_state() 调用

## Fix 2 - mqtt_handler.py - MQTT 订阅泄漏
- **文件**: mqtt_handler.py 第 264 行、cleanup() 方法
- **问题**: async_subscribe 返回值未保存，cleanup() 无法取消订阅
- **修复**: 添加 self._unsub_rsp 属性并保存订阅返回值，cleanup() 中调用取消
- **回滚**: 删除 self._unsub_rsp 相关代码，恢复 cleanup() 中订阅移除逻辑

## Fix 3 - mqtt_handler.py - 线程安全问题
- **文件**: mqtt_handler.py 第 6 行、第 152-164 行
- **问题**: _processed_messages 字典在 MQTT 同步回调线程中无保护
- **修复**: 添加 import threading + self._msg_lock，使用 with self._msg_lock 保护
- **回滚**: 删除 threading import、_msg_lock 及所有加锁代码

## Fix 4 - config_flow.py - 多网关时替换选择不当
- **文件**: config_flow.py 第 162-175 行
- **问题**: existing_entries[0] 直接取第一个网关，没有让用户选择
- **修复**: 多网关(>1)时改走 async_step_replace 让用户选择
- **回滚**: 恢复 existing_entries[0] 的简单取值方式

## Fix 5 - __init__.py - 卸载时丢失持久化数据
- **文件**: __init__.py 第 713-714 行 async_unload_entry
- **问题**: 
  - 卸载配置条目时未先保存持久化数据
  - 调用 _save_persistent_data 时缺少 await 导致协程未被执行（预存 bug）
- **修复**: 
  - 在清理资源前调用 await save_persistent_data(hass)
  - async_unload_entry / async_remove_entry / async_setup 中修复函数名（去除下划线前缀）并添加 await
- **回滚**: 删除 async_unload_entry 中的 save_persistent_data 调用

## Fix 6 - __init__.py - 停止事件监听器泄漏
- **文件**: __init__.py 第 666 行、第 717-722 行
- **问题**: async_listen_once 返回值未保存，中途卸载后 HA 停机会重复卸载
- **修复**: 保存 _stop_unsub，在 async_unload_entry 中主动取消监听
- **回滚**: 删除 _stop_unsub 存储和取消逻辑

## Fix 7 - cover.py - 迁移时 Cover 实体未被清理
- **文件**: device_manager.py 第 35 行
- **问题**: entity_recreate_platforms 缺少 "cover"，迁移时 Cover 实体残留
- **修复**: 添加 "cover" 到 entity_recreate_platforms 列表
- **回滚**: 从列表中移除 "cover"

## Fix 8 - device_manager.py - create_task 泛滥
- **文件**: device_manager.py 多处
- **问题**: setup() 和 add_device() 中大量 scattered asyncio.create_task 无控制
- **修复**: 
  - 添加 _background_tasks 列表追踪后台任务
  - 添加 _notify_device_added_callbacks 批量并发执行回调
  - 添加 _spawn_background_task 受控创建后台任务
  - cleanup() 中取消所有后台任务
- **回滚**: 恢复原有的 for + create_task 模式，删除 _background_tasks/_spawn_background_task/_notify_device_added_callbacks

## Fix 9 - gateway.py - 配对按钮绕过命令管理器
- **文件**: gateway.py 第 148-155 行
- **问题**: GatewayPairingButton 直接使用 mqtt.async_publish，绕过 send_command
- **修复**: 使用 mqtt_handler.send_command("", "start_pairing") 统一命令管理
- **回滚**: 恢复原有的内联 MQTT 发布代码

## Fix 10 - device_manager.py - 未使用的方法
- **文件**: device_manager.py 第 1171 行、第 1203 行
- **问题**: migrate_devices_with_rollback 和 _verify_migration_result 已定义但未被调用
- **修复**: 添加 # TODO: 未使用的方法 注释标记
- **回滚**: 删除 TODO 注释

## Fix 11 - 循环导入优化（创建 persist.py）
- **文件**: 新建 persist.py，修改 __init__.py 和 device_manager.py
- **问题**: device_manager.py 使用 from . import _save_persistent_data 动态导入
- **修复**: 创建 persist.py 独立模块保存持久化函数，__init__.py 和 device_manager.py 静态导入
- **回滚**: 删除 persist.py，恢复 __init__.py 中内联函数，恢复 device_manager.py 动态导入

## Fix 12 - utils.py - SN 匹配改为精确匹配
- **文件**: utils.py 第 110 行、第 117-118 行、第 143 行
- **问题**: 使用 in 子串匹配可能误匹配类似 SN
- **修复**: 用 device_id.split("_") 后精确匹配 SN 段
- **回滚**: 恢复 in 子串匹配方式

## Fix 13 - sensor.py - 迁移回调处理（已有 _recreate 逻辑）
- **说明**: 此问题已在现有 _recreate_platform_entities + _reload_platform 流程中被隐式修复
- **无需额外代码修改**