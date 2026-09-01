# OmniSight（全览）

本地运行的**应用使用时长 + 键盘使用**统计工具。数据只留在本机：无账号、不联网、无遥测。

由两个独立项目合并而来——**TimeLens**（应用时长）与 **KeyTrace**（键盘统计）。合并的核心价值不是"少一个托盘图标"，而是**按键事件在采集时刻就能拿到当前前台应用**，从而让"某个应用的键盘热力图"从跨进程 HTTP + 区间求交 + 全表扫描变成一次预聚合表点查，并解锁一批原本不可能的反向分析。

> **当前状态：M0（地基）已完成，尚不产生任何统计数据，也不记录任何按键。**
> 采集功能在 M1 加入。里程碑与进度见 [dev/PROGRESS.md](dev/PROGRESS.md)。

## 平台支持

首期只交付 Windows。架构上把平台差异收敛为一层显式的端口/适配器契约，使其他平台可以在不改动核心层的前提下加入——但**架构就绪不等于平台就绪**。

| 级别 | 平台 | 承诺 |
| --- | --- | --- |
| 一级 | Windows 10 1809+ / 11 | 全功能，CI 全量测试，性能基准在此度量 |
| 二级 | macOS 12+、Linux X11 | 全功能（M9 / M8 实现），已知差异逐条记录 |
| 三级 | Linux Wayland | 仅键盘统计；应用归因受 Wayland 协议限制不可用 |

## 开发环境

项目使用**项目级 Python 3.12 与仓库内 `.venv`**，不依赖全局解释器。

```bash
uv python install 3.12
uv venv --python 3.12 .venv
uv pip install -r requirements-dev.txt -r requirements-optional.txt
```

```bash
.venv/Scripts/python -m omnisight          # 运行（Windows）
.venv/Scripts/python -m pytest -q          # 测试
.venv/Scripts/python -m ruff check .       # 静态检查
.venv/Scripts/python tools/check_platform_leaks.py   # 平台泄漏检查
.venv/Scripts/python tools/build.py        # 打包
.venv/Scripts/python tools/smoke.py dist/OmniSight.exe   # 对产物冒烟
```

## 数据位置

| 情况 | 位置 |
| --- | --- |
| 默认 | `%LOCALAPPDATA%\OmniSight\`（配置、`data/`、`logs/`） |
| 便携模式 | 程序同级目录（存在 `portable.marker` 时） |
| 升级沿用 | 程序同级已有 `data/omnisight.db` 时保持原位，绝不搬走 |

启动后仪表盘地址为 `http://127.0.0.1:6100/`，只监听回环地址。访问需要一次性令牌，由托盘"打开 OmniSight"带上。

## 完全卸载

1. 关闭程序（托盘 → 退出）
2. 关闭开机自启（托盘取消勾选，或删除注册表 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` 下的 `OmniSight` 值）
3. 删除数据目录（上表中的位置）与程序本身

## 设计文档

完整设计文档集在 [dev/](dev/)，实现前应先通读 `01`~`03`。

## 许可

MIT
