# ADB Studio

ADB Studio 是一个基于 Python 和 Tkinter 的 Windows 图形化 ADB 工具，用于简化 Android 设备的常用操作。

## 主要功能

- 检测并选择已连接的 Android 设备
- 安装 `apk` 目录中的 APK 文件
- 卸载指定应用
- 向设备推送本地文件
- 从设备拉取文件到 `ReadByPhone` 目录
- 重启 ADB 服务并查看运行日志

## 环境要求

- Windows
- Python 2 或 Python 3，并支持 Tkinter
- Android SDK Platform Tools，确保 `adb` 命令已加入系统 `PATH`
- Android 设备已开启 USB 调试并授权当前电脑

## 快速开始

1. 克隆或下载本项目。
2. 将需要安装的 `.apk` 文件放入项目根目录下的 `apk` 文件夹。
3. 使用 USB 连接 Android 设备，并确认设备已授权 USB 调试。
4. 双击 `start.bat` 启动工具。
5. 在界面中选择设备和所需功能进行操作。

## APK 文件说明

`.apk` 和 `.xapk` 文件已通过 `.gitignore` 排除，不会提交到 Git 仓库。请自行将安装包放入本地 `apk` 文件夹。

当前工具的安装功能只识别 `.apk` 文件，不支持直接安装 `.xapk` 文件。
