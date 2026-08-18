# 慧尖开窗器网关

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Validate](https://github.com/fangwenyi-dev/ha-window-controller-gateway/actions/workflows/validate.yaml/badge.svg)](https://github.com/fangwenyi-dev/ha-window-controller-gateway/actions/workflows/validate.yaml)

Home Assistant 自定义集成，通过 MQTT 协议控制慧尖开窗器网关及其子设备。

## 功能特性

- 网关在线状态实时监控（二进制传感器）
- 网关配对模式（按钮触发，60 秒超时自动恢复）
- 开窗器设备控制：开启、关闭、暂停、内倒（A 键）
- 开窗速度调节：Number 滑动条实体（`rwp_winact_speed`，0-100%）
- 开窗力度调节：Number 滑动条实体（`rwp_winact_strength`，0-100%）
- Cover 实体（`device_class=WINDOW`），兼容 LLM 语音控制语义
- 设备电池电压传感器（V）与窗户状态传感器（开/关）
- 设备自动发现与手动配对双模式
- 子设备单独删除按钮（发送解绑协议 003）
- 多网关管理，支持网关替换与设备迁移
- 设备重命名，自动同步按钮别名（语音控制精确匹配）
- 设备到网关映射持久化，重启不丢失
- 手动删除设备列表持久化，防止自动发现重复添加
- MQTT 线程安全调度，消息去重（5 秒窗口）
- 设备名称自动编号（开窗器 网关后4位-设备后4位 #01）
- 设备迁移快照与回滚机制

## 要求

- Home Assistant 2024.2 或更高版本
- 已安装并配置 MQTT 集成（如 Mosquitto broker）

## 安装方法

### 方法 1：通过 HACS 安装（推荐）

1. 打开 HACS
2. 点击右上角三个点 → **自定义仓库**
3. 输入：`https://github.com/fangwenyi-dev/ha-window-controller-gateway`
4. 选择类别：**集成**
5. 点击 **添加**
6. 搜索并安装 **慧尖开窗器网关**
7. 重启 Home Assistant

### 方法 2：手动安装

1. 下载本仓库的 ZIP 文件
2. 将 `custom_components/window_controller_gateway` 文件夹解压到 Home Assistant 的 `custom_components` 目录
3. 重启 Home Assistant

## 配置方法

### 第一步：配置 MQTT 代理

1. 在 Home Assistant 中安装 **Mosquitto broker** 插件
2. 创建 MQTT 账号（用户名 `admin`，密码 `admin`）
3. 在「设置 → 设备与服务 → MQTT」中确认连接正常

### 第二步：配置网关后台

1. 通过路由器查看网关 IP 地址，访问网关后台
2. 登录凭据：用户名 `admin`，密码 `12345678`
3. 在 YGsmartlife 界面中找到 **mqtt config**
4. 修改配置：
   - MQTT IP 地址 → Home Assistant 主机 IP（如 `192.168.1.91`）
   - enable → `enable`
   - username → `admin`
   - password → `admin`
5. 点击 **save&apply**，然后重启网关

### 第三步：添加集成

1. 在 Home Assistant 中进入「设置 → 设备与服务 → 添加集成」
2. 搜索 **慧尖开窗器网关**
3. 输入网关序列号（SN，至少 10 位字母数字）
4. 点击「提交」完成配置

> 也可通过自动发现添加：网关上电后发送 002 上报消息，HA 会弹出发现通知。

## 实体说明

### 网关设备

| 实体 | 平台 | 说明 |
|------|------|------|
| 在线 | `binary_sensor` | 网关 MQTT 连接状态（`connectivity` 类） |
| 配对 | `button` | 触发配对模式，60 秒后自动恢复 |

### 开窗器子设备

#### 通用实体（所有设备）

| 实体 | 平台 | 说明 |
|------|------|------|
| Cover | `cover` | 窗户 Cover 实体，支持 open/close/stop 语义 |
| 速度 | `number` | 开窗速度滑动条（`rwp_winact_speed`，0-100%，拖动即发送 004 命令） |
| 力度 | `number` | 开窗力度滑动条（`rwp_winact_strength`，0-100%，拖动即发送 004 命令） |
| 开启 | `button` | 发送打开命令（`w_travel=100`） |
| 暂停 | `button` | 发送停止命令（`w_travel=101`） |
| 关闭 | `button` | 发送关闭命令（`w_travel=0`） |
| 移除 {SN后4位} | `button` | 发送解绑命令并从系统中删除设备 |
| 电池电压 | `sensor` | 设备电池电压（V，诊断类） |
| 状态 | `sensor` | 窗户开/关状态（`enum` 类，诊断类） |

#### 风锁模式实体（仅 SN 前缀为 `5005` 的设备）

| 实体 | 平台 | 说明 |
|------|------|------|
| 内倒 | `button` | 发送内倒命令（`w_travel=200`） |
| 内倒模式 | `button` | 风锁模式设为内倒（`rwp_wind_lock_mode=0`） |
| 平开模式 | `button` | 风锁模式设为平开（`rwp_wind_lock_mode=1`） |

> **SN 前缀区分**：只有 SN 前四位为 `5005` 的 LoRa 子设备才支持内倒及风锁模式功能，会额外创建「内倒」「内倒模式」「平开模式」三个按钮。`5001`/`5002`/`5003` 等设备仅有开/关/停三个控制按钮。
>
> 「速度」「力度」滑动条**所有子设备均支持**（不区分 SN 前缀），与内倒/风锁模式按钮不同。
>
> 按钮实体设为 `EntityCategory.CONFIG`，Cover 实体设为 `CoverDeviceClass.WINDOW`。

## 服务

| 服务 | 说明 | 参数 |
|------|------|------|
| `start_pairing` | 启动网关配对模式 | `device_id`（必填），`duration`（可选，默认 60 秒） |
| `refresh_devices` | 触发网关重新发现设备 | `device_id`（必填） |
| `set_position` | 设置窗户位置 | `device_id`（必填），`position`（必填，0-100） |
| `check_gateway_status` | 检查网关在线状态 | `device_id`（必填） |
| `rename_device` | 重命名子设备 | `device_id`（必填），`name`（必填，1-50 字符） |
| `migrate_devices` | 批量迁移设备到新网关 | `old_gateway_sn`（必填），`new_gateway_sn`（必填），`remove_old_gateway`（可选） |
| `transfer_device` | 转移单个设备到另一网关 | `device_id`（必填），`new_gateway_sn`（必填） |

## MQTT 通信

### 主题

| 方向 | 主题 | 说明 |
|------|------|------|
| 发送命令 | `gateway/{gateway_sn}/req` | 下发控制/查询命令 |
| 接收响应 | `gateway/rpt_rsp` | 所有网关的响应与上报 |

### 协议格式

```json
{
  "head": "$SH",
  "ctype": "004",
  "id": 1,
  "data": { "sn": "设备SN", "attribute": "w_travel", "value": "100" },
  "sn": "网关SN"
}
```

### 协议类型

| ctype | 发起方 | 回复 ctype | 说明 |
|-------|--------|-----------|------|
| 001 | 网关主动发起 | 001 | 绑定网关，HA 响应一次 |
| 002 | 网关主动发起 | 002 | 网关状态上报 / 设备列表，HA 响应一次 |
| 003 | HA 主动发起 | 003 | 配对(bind=1) / 解绑(bind=0) 子设备，网关响应，不重发 |
| 004 | HA 主动发起 | 004 | 设备控制（开/关/停/内倒/风锁模式），网关响应，不重发 |
| 005 | 网关主动发起 | 005 | 设备状态上报，HA 响应一次 |
| 006 | HA 主动发起 | 006 | 网关响应，不重发 |
| 007 | HA 主动发起 | 007 | 网关响应，不重发 |

> **说明**：所有命令均不启用自动重发——MQTT QoS 1 保证消息送达 broker，网关在线即可收到；网关已执行但回复丢失时自动重发会造成重复配对/重复控制，命令均由用户主动触发，未生效时用户再次操作即可。

## 高级配置

在「设置 → 设备与服务 → 慧尖开窗器网关 → 配置」中可设置：

| 选项 | 默认值 | 范围 | 说明 |
|------|--------|------|------|
| 设备发现间隔 | 300 秒 | 60-3600 | 定期连接检查的间隔 |
| 自动发现设备 | 开启 | 开/关 | 是否启用设备自动发现 |
| 调试日志 | 关闭 | 开/关 | 启用 DEBUG 级别日志 |

### 内部机制

- **网关离线检测**：30 分钟（`GATEWAY_TIMEOUT_SECONDS=1800`）未收到网关上报消息则标记离线；从未收到上报时也标记离线
- **消息去重**：5 秒窗口内相同 `ctype + id + sn` 的消息自动跳过（网关周期上报 id=0 时不做去重）
- **线程安全调度**：MQTT 回调运行在 paho-mqtt 线程，通过 `_schedule_async_task` 自动检测上下文，事件循环内用 `async_create_task`，线程内用 `run_coroutine_threadsafe`
- **持久化存储**：`window_controller_gateway_data.json`，原子写入（tmp + os.replace），Lock 串行化 + 防抖
- **设备迁移**：快照 → 转移设备关联 → 更新映射表 → 验证 → 失败自动回滚
- **弱引用回调**：状态更新回调使用 `weakref` 存储，避免内存泄漏

## 调试

### 启用详细日志

在 `configuration.yaml` 中添加：

```yaml
logger:
  logs:
    custom_components.window_controller_gateway: debug
```

### 使用 MQTT 调试面板

1. 进入 Home Assistant 的 MQTT 调试面板
2. 订阅主题 `gateway/rpt_rsp` 查看设备响应
3. 发布消息到 `gateway/<网关SN>/req` 手动发送命令

### 常见问题

| 问题 | 可能原因 | 解决方案 |
|------|----------|----------|
| 网关始终显示离线 | MQTT 配置不正确或网关未上报 | 检查网关后台 MQTT 配置，确认 IP/用户名/密码正确 |
| 设备控制无响应 | 网关离线或设备 SN 不匹配 | 检查网关在线状态，确认设备 SN 与上报一致 |
| 设备重复添加 | 映射表未正确清理 | 使用删除按钮移除设备后重新配对 |
| 传感器无数据 | 设备未上报状态 | 触发 `refresh_devices` 服务刷新设备状态 |
| 配对后设备未出现 | 配对超时或设备已被其他网关绑定 | 检查日志中的错误码，确认设备未被其他网关占用 |

## 网关替换与设备迁移

### 网关替换（自动发现）

1. 新网关上电后，HA 弹出发现通知
2. 选择要替换的旧网关
3. 确认迁移，系统自动将旧网关设备转移到新网关
4. 可选：迁移后自动移除旧网关配置

### 设备迁移（服务调用）

```yaml
service: window_controller_gateway.migrate_devices
data:
  old_gateway_sn: "100121501186"
  new_gateway_sn: "100121501187"
  remove_old_gateway: false
```

### 单设备转移

```yaml
service: window_controller_gateway.transfer_device
data:
  device_id: "500534380259"
  new_gateway_sn: "100122501203"
```

## 版本历史

### v1.4.3
- 新增: 子设备「速度」Number 滑动条实体 — 通过 004 协议下发 `rwp_winact_speed`（0-100%，step 1），拖动滑块即时发送；解析 005 上报的同名属性回显当前速度
- 新增: 子设备「力度」Number 滑动条实体 — 通过 004 协议下发 `rwp_winact_strength`（0-100%，step 1），行为与「速度」一致；解析 005 上报的同名属性回显当前力度
- 新增: `set_speed` / `set_strength` 命令，与其他控制命令一致，网关离线也尝试发送、QoS1 送达 broker
- 修复: 速度/力度滑动条设定值未本地保存 — 拖动后重新进入设备界面/HA 重启会回退为 0。现改为显示「设定值」：设置成功即写入 `device_setpoints`（随 `window_controller_gateway_data.json` 持久化），重启后回显上次设定位置；005 的运行时上报（空闲时为 0）不再覆盖滑块位置

### v1.4.1
- 修复: 未配置网关的发现通知循环轰炸 — 同一网关在一次 HA 会话内只触发一次发现流程/通知（新增 `announced_gateways` 会话去重），网关周期心跳不再反复弹出"发现新网关"；删除网关后重置记录，可再次被发现
- 修复: `set_position` 服务 `position: true` 被 `vol.Coerce(int)` 静默转为位置 1 — schema 在 Coerce 前置拒绝布尔值
- 修复: 003 绑定/解绑命令方向记录（`_bind_ops`）无上限，网关不回复时持续增长 — 增加上限（`MAX_BIND_OPS=200`）并按序淘汰最旧记录
- 修复: `update_gateway_status` 空实现 — 现在真实记录网关状态，配对状态通过在线传感器的 `pairing_active` / `gateway_status` 属性可见
- 修复: `set_position` / `rename_device` 服务的 `device_id` 支持 HA 设备注册表 ID（UUID），与 `transfer_device` 行为一致
- 优化: 自动发现设备名补充 `#NN` 自动编号，与手动配对命名格式一致

### v1.3.7
- 功能调整: 设备迁移（migrate_devices 服务与替换网关自动迁移）暂禁用（服务注册与自动触发已注释，发现流程不再强制进入替换流程，可正常添加多网关）
- 修复: `set_position` 服务 schema 不再用 `positive_int`（位置 0 即完全关闭会被错误拒绝）
- 修复: `_handle_ctype_003` 增加命令 id 匹配判定（发送端记录 003 绑定/解绑方向，回复按 id 匹配）——彻底消除"解绑回复晚于本地删除"时设备被误添加的竞态窗口（固件回复不带 data.bind 时此前只能靠设备存在性推断）
- 修复: `_handle_ctype_003` 恢复 bind 字段/设备存在性判断——固件解绑回复同样携带 data.sn（真实日志确认），此前无 bind 判断时解绑回复被误判为绑定成功、把刚删除的设备重新添加（设备"复活"）
- 修复: 解绑命令（003 bind=0）payload 顶层补 `bind` 字段，与配对（顶层 bind=1）一致——固件按顶层 bind 识别绑定/解绑
- 修复: MQTT 重连任务去重（同一实例不再并发重连，cleanup 可取消）；`transfer_device` 保留实体自定义名称/别名；删除网关时清理子设备孤儿注册表条目
- 工程: CI 接入 Python 语法检查（compileall）+ JSON 校验 + 模拟测试（test_full_simulation.py），防止语法/格式错误进入 main
- 修复: P0 — `mqtt_handler.py` 006/007 缩进损坏（IndentationError）导致集成无法加载
- 修复: `check_connection` 不再向网关 req 主题发布空 payload；网关在线状态由收到上报/心跳维护，离线超时 30 分钟（网关约 5 分钟心跳一次）
- 修复: 迁移回滚只回滚快照中的设备，不再误伤新网关已有设备
- 修复: 迁移时误用 `async_update_device(config_entry_id=...)`（HA 无此参数）导致迁移静默失败，改用 `async_get_or_create`
- 修复: 5 处设备-网关映射修改未持久化导致重启后不一致，全部补齐保存
- 修复: 手动删除的设备重启后复活（加载时跳过手动删除列表）
- 修复: 按钮/删除按钮被 HA 自动禁用（disabled_by=integration）显示灰色，集成加载时自动恢复；配对/删除按钮显式 `_attr_available=True`
- 修复: 添加网关连接测试失败不再阻塞（新增"仍然添加"确认步骤），MQTT 集成未启用仍硬性报错
- 修复: 取消全部命令重发机制（003/004/006/007）— MQTT QoS 1 保证送达，网关已执行但回复丢失时自动重发会造成重复配对/重复控制
- 修复: 控制命令（开/关/停/内倒/风锁模式/设置位置）不再要求设备已在设备管理器中登记，任何时候都可发送（MQTT QoS 1 保证送达，网关在线与否均尝试发送）
- 修复: 删除按钮不再被网关在线状态阻断（MQTT 解绑尽力而为，本地删除必执行）；控制命令不再要求设备已登记（任何时候可控制）
- 修复: `transfer_device` 转移设备后删除旧前缀实体，避免同一设备两套实体；迁移不再强制要求新网关在线（本地操作）
- 修复: 迁移任务清除 migration_info 与 reload 竞态；`set_position` 排除 bool 参数；003 配对只信任 data.sn（不误把网关当子设备）；config_flow unique_id 统一小写并兼容历史大小写
- 修复: MQTT 去重对 id=0 的网关周期上报不再误杀状态更新
- 修复: 迁移后旧前缀实体与新前缀实体并存（同一设备出现两套按钮/Cover/传感器），迁移时删除旧前缀实体（含删除按钮）
- 安全: `add_device` 增加设备数量上限（MAX_DEVICES_PER_GATEWAY=32），防伪造消息无限注入
- 安全: 替换/迁移/发现流程网关 SN 校验字符集（≥10 位字母数字），防畸形 SN 生成非法 MQTT 主题
- 安全: 持久化保存前对数据快照，防并发修改异常
- 优化: 清理约 700 行死代码与 5 个未用常量；设备状态词汇统一为 `DEVICE_STATUS_*` 常量
- 优化: 实体启动循环恢复无条件创建（注册表查重会导致重启后实体无实例），回调路径保留查重与 `created_*` 合并

### v1.3.6
- 修复: P0 — `_handle_ctype_003` 读取网关回复的 bind 字段导致配对成功后设备不添加，回退为收到 errcode=0 直接添加设备
- 修复: P0 — `_handle_ctype_002` 收到空 data 时 status 默认 "unknown" 覆盖网关在线状态，改为不更新
- 修复: P0 — 网关断电后 HA 仍显示在线（虚假在线），解耦 MQTT broker 可达性与网关设备在线状态
- 新增: 003/004/006/007 命令重发机制 — 网关 5 秒未回复自动重发 1 次，收到回复取消定时器
- 新增: 解绑命令也加入重发机制，解绑回复走 003，通过 command_id 精确匹配回复
- 修复: 删除不存在的 008/009/010 协议处理器
- 修复: 006/007 由网关主动上报改为 HA 主动发起，回复后取消重发定时器，不再发送 ack
- 优化: 移除 HA 主动发送 001/002/005 的无效代码（这些是网关主动发起，HA 发了网关不响应）
- 优化: 协议响应规范化 — 001/002/005 由 HA 回复一次确认，003/004/006/007 网关回复后 HA 不再回复

### v1.3.5
- 修复: P1 — Cover `is_closed` / `current_cover_position` 返回实际状态导致 HA 自动灰掉按钮，恢复为返回 `None` 保证所有按钮始终可点击
- 修复: P1 — `_handle_ctype_005` 无 status 字段时用 `"unknown"` 覆盖设备已有状态，改为 `data.get("status")` 不设默认值
- 修复: P1 — `current_cover_position` 未裁剪 `r_travel` 到 0-100 范围
- 修复: P1 — `handle_transfer_device` 用 `in` 模糊匹配 SN，改为精确匹配
- 修复: P2 — `rename_device` 未同步更新风锁按钮别名
- 修复: P2 — 传感器超时阈值硬编码，改用 `SENSOR_TIMEOUT_MINUTES` 常量
- 新增: `extra_state_attributes` 暴露设备实际位置和状态，供用户查看但不影响按钮可用性
- 新增: SN 前缀 `5005` 条件化创建内倒/平开模式按钮

### v1.3.4
- 修复: P0 — `_update_device_attributes` 仅收到电池数据时误判设备状态为 "open"
- 修复: P0 — 迁移无限循环，调度后立即清除 `migration_info` 防止重载时重复触发
- 修复: P0 — 选项更新监听器未注册，配置选项变更无法即时生效
- 修复: P1 — MQTT 线程安全，`_schedule_async_task` 自动检测事件循环上下文，线程内回退 `run_coroutine_threadsafe`
- 修复: P1 — 配对超时句柄统一管理，服务调用与按钮按下共享同一超时
- 修复: P1 — 后台任务取消未 await，cleanup 中 cancel + await 所有后台任务
- 修复: P1 — 迁移中字典遍历时修改导致 `RuntimeError`，使用 `list()` 创建副本
- 修复: P2 — 网关名称后缀统一为 `[-4:]`
- 修复: P2 — 迁移设备结构统一为 `status/attributes`，与其他代码路径一致
- 修复: P2 — 死代码移除（不存在的 `homeassistant/reload_entities` 事件）
- 优化: `check_connection` 恢复为 publish 成功即标记在线，网关离线检测由超时机制负责
- 优化: 配置流程连接测试恢复 `MockDeviceManager` + `_test_gateway_connectivity` 逻辑
- 优化: `device_manager.update_device_status` 支持 `status=None` 仅更新属性
- 优化: 持久化写入改为 Lock 串行化 + 防抖标志，避免竞态丢数据
- 优化: 版本号同步至 1.3.4，最低 HA 版本修正为 2024.2
- 优化: README 根据当前代码全面重写

### v1.3.3
- 新增: Cover 实体添加 `device_class=WINDOW`，大模型 LLM 指令匹配更精准
- 优化: `const.py` 全面重构，移除 12 个类包装和 141 行重复导出
- 优化: 清理 7 处冗余内联导入，提升运行时性能
- 优化: `async_setup_entry` 拆分出 3 个模块级函数，提升代码可维护性
- 优化: 补充 6 处类型注解，添加 `timedelta` 类型安全守卫

### v1.3.2
- 优化: `mqtt_handler.py` 清理 8 处冗余内联导入
- 优化: 提取 `_get_mqtt_handler()` 到基类，消除 cover/button 中重复逻辑
- 优化: `device_manager.py` 简化网关 SN 匹配（精确匹配替代模糊匹配）
- 优化: `config_flow.py` MockDeviceManager 移至模块级别，context 键使用 `.get()` 安全访问
- 优化: 清理过时注释和死代码

### v1.3.1
- 新增: 所有实体启用 `_attr_has_entity_name = True`，实体名称自动包含设备名
- 优化: 按钮名称自动跟随设备名，LLM 语音控制可直接按窗户类型匹配
- 修复: `services.yaml` 添加 `migrate_devices` 服务定义
- 修复: `strings.json`/`zh-CN.json` 补充服务翻译
- 修复: 持久化数据写入改为原子写入（tmp + os.replace）

### v1.3.0
- 新增: Cover 实体，LLM 语音控制可直接使用 open_cover/close_cover/stop_cover
- 优化: 精简代码，移除 DeviceCacheManager 等约 700 行死代码

### v1.2.8
- 优化: 取消定时设备发现功能，减少 MQTT 负载
- 优化: 网关离线判断逻辑保持 30 分钟无上报则离线

### v1.2.7
- 修复: 添加 MQTT 消息去重机制，防止网关状态上报时重复响应

### v1.2.6
- 修复: 子设备控制按钮（开关停A）显示在设备详情页

### v1.2.5
- 修复: 网关和子设备控制实体始终可用，不受网关离线影响
- 优化: 网关超时时间从 20 分钟调整为 30 分钟

### v1.2.4
- 修复: 调整 unique_id 格式，确保实体正常显示
- 修复: 修复设备加载逻辑，支持多网关设备映射

### v1.2.2
- 修复: 传感器实体重启后未正确添加的问题
- 修复: 按钮 unique_id 冲突问题
- 优化: 设备映射逻辑，确保设备正确绑定到对应网关

### v1.2.0
- 修复: MQTT 回调线程安全问题
- 修复: HA 启动阻塞问题，使用 `eager_start`
- 优化: 控制命令无论网关在线与否都可发送

### v1.1.9
- 新增: 设备到网关映射表持久化
- 新增: 手动删除设备列表持久化
- 新增: `status` 命令支持
- 优化: 极速状态查询，自适应查询间隔和批处理

### v1.1.8
- 修复: 手动删除的子设备不会通过周期上报自动重新添加
- 新增: 允许通过手动配对重新添加已删除的子设备

### v1.1.5
- 新增: 网关在线状态传感器
- 新增: 电池电压和窗户状态传感器

### v1.1.3
- 新增: 手动删除设备功能

### v1.1.1
- 新增: 设备名称自动编号功能

### v1.1.0
- 集成重构，使用 Config Flow 配置
- 支持 MQTT 自动发现

### v1.0.4
- 初始版本发布

## License

MIT License
