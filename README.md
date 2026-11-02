# DesktopSeeker 桌面搜索器

一个 Windows 桌面图标定位小工具：**悬浮搜索框 + 悬浮球定位**。

桌面图标多到找不到？输入文件名或程序名，悬浮球会飞到该图标旁并高亮标记，一眼就能看到它在哪——不移动、不整理、不改动你的桌面。

![Python](https://img.shields.io/badge/Python-3.10+-blue) ![PySide6](https://img.shields.io/badge/GUI-PySide6-green) ![License](https://img.shields.io/badge/License-GPL--3.0-orange)

## 功能特性

- **悬浮搜索框**：全局热键 `Ctrl+Alt+F` 呼出，输入即搜，实时过滤上百个桌面图标无压力
- **悬浮球定位**：回车后悬浮球沿飞行动画移动到目标图标旁，同时高亮标记图标位置（高亮层鼠标穿透，不影响操作）
- **手动确认定位**：搜索结果列表中手动选择、回车定位，不会误触
- **可拖动、位置记忆**：搜索框和悬浮球都可拖动，重启后保持位置（多屏下自动约束在屏幕内）
- **启动后自动收起**：定位的程序启动后，定位提示自动收起为悬浮球（可在托盘/右键菜单关闭此开关）
- **单实例锁**：重复启动自动唤起已运行的实例，不会开出多个
- **DPI 感知**：正确支持高 DPI / 多显示器 / 缩放环境（200% 缩放实测）
- **系统托盘**：退出、开关"定位前先显示桌面"等

## 演示

演示视频见 [demo/桌面搜索器_演示.mp4](demo/桌面搜索器_演示.mp4)。

## 使用方法

| 操作 | 方式 |
|---|---|
| 呼出搜索框 | 单击悬浮球，或按 `Ctrl + Alt + F` |
| 搜索 | 输入图标名称（支持部分匹配） |
| 定位 | `↑`/`↓` 选择结果后 `回车`，悬浮球飞过去高亮 |
| 关闭搜索框 | `Esc` 或右上角 `✕` |
| 退出程序 | 托盘图标右键 → 退出 |

## 从源码运行

依赖：Python 3.10+（Windows）

```bat
pip install PySide6 pywin32
run.bat
```

## 打包为独立 exe

```bat
build.bat
```

脚本会自动创建干净的打包虚拟环境（PySide6-Essentials + PyInstaller），按 `DesktopSeeker.spec` 精简裁剪未使用的 Qt 组件（Qml/Quick/OpenGL/Pdf 等约 54 MB），产出约 **26 MB** 的单文件 exe 并压缩为 zip。

## 技术原理

- **读取桌面图标**：桌面本质上是一个 Explorer 进程内的 `SysListView32` 列表控件。通过 `FindWindowEx` 定位 `Progman → SHELLDLL_DefView → SysListView32`，再用 `LLVM_*` 消息跨进程读取每项文本与坐标（`SendMessageTimeoutW` 带超时防卡死）
- **坐标换算**：进程声明 Per-Monitor DPI 感知，Explorer 返回物理像素，再换算为 Qt 逻辑坐标，保证高 DPI / 多屏下定位准确
- **快捷方式解析**：`win32com` 解析 `.lnk` 目标，可定位到快捷方式指向的程序
- **进程监听**：`EnumProcesses` + `QueryFullProcessImageNameW` 轮询被定位程序是否启动
- **单实例**：`QLockFile`（固定于 `%LOCALAPPDATA%`，规避 PyInstaller 单文件模式改写 TEMP 的问题）+ `QLocalServer/QLocalSocket` 唤醒已有实例

## 项目结构

```
DesktopSeeker/
├── main.py           # 入口：全局热键、托盘、单实例、定位流程
├── desktop_api.py    # Win32 层：桌面图标读取、快捷方式解析、进程枚举
├── ui_search.py      # 悬浮搜索框：拖动、位置记忆、结果列表
├── ui_ball.py        # 悬浮球：飞行动画、高亮层、右键菜单
├── ui_common.py      # 公共：矢量图标、DPI 换算
├── DesktopSeeker.spec# PyInstaller 精简打包配置
├── build.bat         # 一键构建 exe + zip
├── run.bat           # 一键从源码运行
└── demo/             # 演示视频
```

## 许可证

本项目基于 [GPL-3.0](LICENSE) 协议开源。
