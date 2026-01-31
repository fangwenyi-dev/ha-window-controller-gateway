# 慧尖开窗器网关

![版本](https://img.shields.io/badge/版本-1.1.1-blue.svg)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.0.0%2B-green.svg)
![许可证](https://img.shields.io/badge/许可证-MIT-yellow.svg)

Home Assistant 自定义集成，用于控制慧尖开窗器网关及设备。

## 功能特性

- ✅ 支持网关在线状态监控
- ✅ 支持网关配对功能
- ✅ 支持开窗器设备控制（开、关、停、A）
- ✅ 支持子设备删除功能
- ✅ 支持电池电压和窗户状态传感器
- ✅ 支持 MQTT 通信协议
- ✅ 支持设备自动发现和添加
- ✅ 支持子设备顺序命名（开窗器 01, 开窗器 02 等）

## 设备控制

- **开**：控制开窗器完全打开
- **关**：控制开窗器完全关闭
- **停**：停止开窗器当前动作
- **A**：执行自定义动作（对应 w_travel: 200）

## 传感器

- **电池电压**：显示开窗器电池电压
- **状态**：显示开窗器当前状态（开/关）

## MQTT 主题

- **发送命令**：`gateway/<sn>/req`
- **接收响应**：`gateway/rpt_rsp`

## 协议类型

- **001**：绑定网关
- **002**：网关状态上报
- **003**：绑定子设备
- **004**：设备控制
- **005**：设备状态上报

## 安装方法

### 方法 1：通过 HACS 安装（推荐）
1. 在 HACS 中添加自定义仓库
2. 搜索并安装 "慧尖开窗器网关"
3. 重启 Home Assistant

### 方法 2：手动安装
1. 下载本仓库的 ZIP 文件
2. 解压到 `custom_components` 目录
3. 重启 Home Assistant

## 配置方法

1. 在 Home Assistant 中进入 "配置" > "设备与服务" > "添加集成"
2. 搜索 "慧尖开窗器网关"
3. 输入网关序列号（SN）
4. 点击 "提交" 完成配置

## 故障排除

### 常见问题

1. **网关无法连接**
   - 检查 MQTT 服务是否正常
   - 检查网关网络连接
   - 检查网关序列号是否正确

2. **设备控制无响应**
   - 检查设备是否在线
   - 检查 MQTT 主题配置
   - 检查网关与设备的通信

3. **传感器数据不更新**
   - 检查设备是否正常上报状态
   - 检查电池电压是否充足
   - 检查 MQTT 通信是否正常

## 开发者信息

### 核心文件

- `__init__.py` - 集成初始化
- `config_flow.py` - 配置流程
- `const.py` - 常量定义
- `cover.py` - 开窗器控制实体
- `sensor.py` - 传感器实体
- `binary_sensor.py` - 二进制传感器实体
- `button.py` - 按钮实体
- `gateway.py` - 网关实体
- `device_manager.py` - 设备管理器
- `mqtt_handler.py` - MQTT 处理器
- `manifest.json` - 集成信息
- `services.yaml` - 服务定义
- `strings.json` - 字符串定义
- `translations/` - 翻译文件
- `logo.png` - 集成图标

## 贡献

欢迎贡献代码、报告问题或提出建议！

## 联系方式

- 开发者：慧尖
- 版本：1.1.1
- 适配 Home Assistant 版本：2024.0.0 及以上
