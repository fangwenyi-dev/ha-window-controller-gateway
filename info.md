# 慧尖开窗器网关

这是一个用于慧尖开窗器网关的Home Assistant集成，支持通过MQTT控制和监控智能开窗器设备。

## 功能特点

- ✅ **网关支持**：支持慧尖开窗器网关设备
- ✅ **MQTT通信**：基于MQTT协议，稳定可靠
- ✅ **自动发现**：自动发现并添加开窗器设备
- ✅ **实时监控**：实时监控网关和设备状态
- ✅ **网关实体**：
  - 在线状态传感器
  - 配对按钮
- ✅ **开窗器控制**：
  - 开合控制
  - 位置调节
  - 状态反馈
- ✅ **中文界面**：完全中文支持

## 安装方法

### 通过HACS（推荐）

1. 确保已安装HACS
2. 在HACS中添加自定义仓库：
   - URL: `https://github.com/fangwenyi-dev/ha-window-controller-gateway`
   - 类别: `Integration`
3. 搜索并安装"慧尖开窗器网关"
4. 重启Home Assistant
5. 在"设备与服务"中添加集成

### 手动安装

1. 下载最新版本
2. 将`custom_components/window_controller_gateway/`目录复制到Home Assistant的`config/custom_components/`目录
3. 重启Home Assistant
4. 在"设备与服务"中添加集成

## 配置方法

1. 在"设备与服务"中点击"添加集成"
2. 搜索"慧尖开窗器网关"
3. 输入网关序列号和名称
4. 完成配置

## MQTT主题

- **网关请求**：`gateway/req`
- **设备请求**：`gateway/<sn>/req`
- **网关响应**：`gateway/rpt_rsp`

## 协议支持

- ✅ 001：绑定网关
- ✅ 002：状态上报
- ✅ 003：绑定子设备
- ✅ 004：设备控制
- ✅ 005：设备上报

## 技术支持

- 问题反馈：https://github.com/fangwenyi-dev/ha-window-controller-gateway/issues
- 协议文档：智能家居通讯协议.pdf

## 版本要求

- Home Assistant：2024.11.0或更高版本
- Python：3.12或更高版本

## 变更日志

### v1.0.0
- 初始版本发布
- 支持网关实体
- 支持开窗器控制
- 支持MQTT通信
- 支持设备自动发现
