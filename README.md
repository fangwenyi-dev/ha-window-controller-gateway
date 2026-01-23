# 慧尖开窗器网关 Home Assistant 集成

[![GitHub Release][releases-shield]][releases][![GitHub 发布][releases-shield][发布-盾牌][发布-盾牌]][releases发布][发布]
[![GitHub ActivityGitHub 活动][commits-shield][提交-盾牌]][commits][提交][![GitHub 活动][commits-shield]][commits][![GitHub 活动GitHub 活动][commits-shield][提交-盾牌]][commits][提交][![GitHub 活动][commits-shield]][commits]
[![License][license-shield]][license][![许可证][许可证盾牌]][许可证]

[commits-shield提交 shield提交 shield]: https://img.shields.io/github/commit-activity/y/yourusername/ha-window-controller-gateway.svg[提交次数盾牌]: https://img.shields.io/github/commit-activity/y/yourusername/ha-window-controller-gateway.svg
[commits提交]: https://github.com/yourusername/ha-window-controller-gateway/commits/main
[license-shield许可证盾牌]: https://img.shields.io/github/license/yourusername/ha-window-controller-gateway.svg
[license许可证]: https://github.com/yourusername/ha-window-controller-gateway/blob/main/LICENSE[许可证]: https://github.com/yourusername/ha-window-controller-gateway/blob/main/LICENSE
[releases-shield发布 shield][发布 shield][发布 shield][发布 shield]: https://img.shields.io/github/release/yourusername/ha-window-controller-gateway.svg[发布 shield]: https://img.shields.io/github/release/yourusername/ha-window-controller-gateway.svg
[releases]: https://github.com/yourusername/ha-window-controller-gateway/releases[发布]: https://github.com/yourusername/ha-window-controller-gateway/releases[发布]: https://github.com/yourusername/ha-window-controller-gateway/releases[发布]: https://github.com/yourusername/ha-window-controller-gateway/releases

慧尖开窗器网关的Home Assistant集成。

## 功能特性

- 网关在线状态监测
- 网关配对功能
- 开窗器设备自动发现
- 开窗器控制
- 设备状态自动更新

## 安装

### HACS（推荐）

1. 打开HACS
2. 点击"集成"
3. 点击右上角的三个点，选择"自定义仓库"
4. 添加仓库URL：`https://github.com/yourusername/ha-window-controller-gateway`
5. 类别选择：`Integration`
6. 点击"添加"
7. 搜索"慧尖开窗器网关"并安装

### 手动安装

1. 下载最新版本的[发布包](https://github.com/fangwenyi-dev/ha-window-controller-gateway/releases)
2. 将 `custom_components/window_controller_gateway` 目录复制到Home Assistant的 `config/custom_components/` 目录
3. 重启Home Assistant
4. 在集成中添加"慧尖开窗器网关"

## 配置

1. 确保您的Home Assistant已配置MQTT
2. 在集成页面点击"添加集成"
3. 搜索"慧尖开窗器网关"
4. 输入网关序列号
5. 点击"提交"
6. 点击配对按钮开始配对设备
7. 设备将自动添加到Home Assistant

## 支持的协议

- 协议类型001：网关绑定
- 协议类型002：状态上报
- 协议类型003：子设备绑定
- 协议类型004：设备控制
- 协议类型005：设备上报

## 许可证

MIT LicenseMIT 许可证MIT 许可证MIT 许可证MIT 许可证MIT 许可证MIT 许可证MIT 许可证
