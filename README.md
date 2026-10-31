# SPSS 数据阅读器 (SAV Reader)

一个轻量、快速的 SPSS `.sav` 数据文件阅读器，采用 Canvas 虚拟滚动引擎，可流畅浏览百列万行数据。

## 功能特性

- 打开 `.sav` 文件（点击按钮或拖拽文件到窗口）
- **Canvas 虚拟滚动引擎** — 只渲染可视区域，5 万行以上数据秒开，滚动不卡顿
- 变量信息面板
  - 数据类型、变量标签、值标签
  - 测量级别、缺失值、唯一值分布
  - 描述统计（均值、中位数、标准差、Q1/Q3），后台预计算，点击即时显示
- 导出为 CSV（UTF-8 BOM，Excel 打开中文不乱码）
- 彩色分级日志 + 加载动画
- 全局异常捕获

## 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+O` | 打开文件 |
| `Ctrl+S` | 导出 CSV |

## 环境要求

- Python 3.9+
- Windows / macOS / Linux（GUI 基于 tkinter）

## 安装

```bash
pip install -r requirements.txt
```

## 运行

```bash
python app/main.py
```

Windows 下也可双击 `run.bat`。

## 打包为 EXE

```bash
pip install pyinstaller
pyinstaller SAV阅读器.spec
```

## 项目结构

```
.
├── app/
│   ├── main.py          # 主程序（GUI + 虚拟滚动引擎）
│   └── icon.ico
├── SAV阅读器.spec       # PyInstaller 打包配置
├── run.bat
├── 使用说明.txt
└── requirements.txt
```

## 说明

- 内部编码自动检测 UTF-8 / UTF-16
- 超大数据集默认只显示前若干行以保证流畅，导出 CSV 可获取完整数据

## 许可证

MIT License
