# OmniSight（全览）

[![Release](https://img.shields.io/github/v/release/RavenHogWarts/OmniSight?include_prereleases)](https://github.com/RavenHogWarts/OmniSight/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/RavenHogWarts/OmniSight/total)](https://github.com/RavenHogWarts/OmniSight/releases)
![Platform](https://img.shields.io/badge/platform-Windows%2010%201809%2B%20%7C%2011-0078D6?logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)
[![License](https://img.shields.io/github/license/RavenHogWarts/OmniSight)](LICENSE)
![Privacy](https://img.shields.io/badge/privacy-offline%20%C2%B7%20no%20telemetry-brightgreen)

**本地运行的「应用使用时长 + 键盘使用」统计工具。** 无账号、不联网、无遥测——数据只留在本机。

## 功能

| 面板 | 内容                                                                                  |
| ---- | ------------------------------------------------------------------------------------- |
| 总览 | 屏幕时间、按键总量、应用排行、24 小时趋势、自动生成的要点                             |
| 应用 | 应用列表与详情、会话时间线、别名 / 分类 / 合并 / 排除                                 |
| 键盘 | 全键盘热力图（次数 / 平均时长 / 最长时长）、24 小时与日历趋势、单键详情、人体工学分布 |
| 洞察 | 应用×键热力图、某个键主要被哪些应用使用、输入节奏与屏幕时间的对比                     |
| 设置 | 隐私开关、周期与时区、导入旧数据、导出 CSV/JSON、暂停记录                             |

程序常驻托盘、不会自己弹窗口；仪表盘是本机网页（`http://127.0.0.1:6100/`，只监听回环地址，访问需要托盘自动带上的一次性令牌）。

## 平台支持

|     | 平台                  | 状态                                                      |
| --- | --------------------- | --------------------------------------------------------- |
| ✅   | Windows 10 1809+ / 11 | **已交付**，全功能                                        |
| 🚧   | macOS 12+、Linux X11  | 规划中，尚未实现                                          |
| ⚠️   | Linux Wayland         | 规划中，且应用归因受 Wayland 协议限制不可用，只有键盘统计 |

架构上已把平台差异收敛成一层显式的端口/适配器契约，但**架构就绪不等于平台就绪**。

## 下载

到 [Releases](https://github.com/RavenHogWarts/OmniSight/releases/latest) 取，两件产物都不需要 Python：

| 产物                     | 适合                               | 数据位置                    |
| ------------------------ | ---------------------------------- | --------------------------- |
| `OmniSight-Setup.exe`    | 装进系统，要开始菜单项与标准卸载项 | `%LOCALAPPDATA%\OmniSight\` |
| `OmniSight-portable.zip` | 解压即用，随身带走或不想动系统     | 解压目录                    |

功能完全一样，差别只有安装位置。唯一例外是设置页的「登录时以管理员身份启动」——它一般只有安装版能开（理由见 [FAQ](docs/faq.md)）。裸 `OmniSight.exe` 不单独发布：它带不走许可正文与说明。

**下载后请核对校验值。** 本程序未做代码签名，Windows 会显示 SmartScreen 警告（点「更多信息 → 仍要运行」），部分杀软也可能因为「读键盘」这一行为报警——因此校验值是你确认拿到的确实是这份产物的唯一手段：

```powershell
Get-FileHash .\OmniSight-Setup.exe -Algorithm SHA256
```

与发布页同名的 `.sha256` 比对。每次发布的校验值、本机杀软扫描结论与按哈希查询 VirusTotal 的地址都记在 [docs/scan-record.md](docs/scan-record.md)；杀软误报的详细说明见 [FAQ](docs/faq.md)。

## 首次启动

安装版从「开始」菜单启动，便携版双击 `OmniSight.exe`。托盘菜单：

```
打开 OmniSight            默认项，双击图标即可
─────────────
暂停记录                  勾选态，暂停时图标变灰
以管理员身份重启          仅当需要统计管理员程序里的按键时才用
─────────────
开机自启                  勾选态
打开数据目录
打开日志目录
─────────────
关于与隐私说明
退出
```

首次打开仪表盘会显示一屏说明：**记录什么、不记录什么、数据在哪、如何暂停**。那屏内容是按你此刻的能力探测与配置**算出来**的，不是固定文案。之后可从托盘「关于与隐私说明」随时再看。

以管理员身份运行的程序（管理员模式的 VS Code、终端、任务管理器）里敲的键**统计不到**——Windows 不允许普通权限的程序收到发往更高权限程序的输入。症状是那个应用的按键数一直是 0，而屏幕时间照常记录。托盘的「以管理员身份重启」提权来补这个缺口，且**只对本次运行有效**。日常使用**不需要**管理员权限。

## 隐私

- 记录的是**键位编号**、次数与时长，**不记录字符内容**；窗口标题默认不记录
- 无账号、无遥测、无崩溃上报——**代码结构上就不存在出站网络调用**，可在源码里验证
- 三档随时可关：暂停记录、排除指定应用（采集层排除，不是界面隐藏）、关掉原始按键事件
- 卸载会问是否一并删除统计数据，**默认保留**

必须诚实的一条：开启原始事件记录时，键位序列在技术上可以被还原成输入过的文本。完整说明与关闭方法见 [隐私白皮书](docs/privacy.md)。

## 配置

`config.json` 只存「启动前就要知道」的项，其余设置存库、在设置页里改。完整示例见 [config.example.json](config.example.json)。

| 项                                               | 默认                   | 说明                                                                           |
| ------------------------------------------------ | ---------------------- | ------------------------------------------------------------------------------ |
| `server.port`                                    | `6100`                 | 被占用时**报错退出而不是静默换端口**                                           |
| `capture.store_raw_key_events`                   | `true`                 | 每次按键的精确时间与所属应用。关掉后热力图等照常，只失去组合键与毫秒级节奏分析 |
| `privacy.record_window_titles`                   | `false`                | 窗口标题（网页标题、文件名）                                                   |
| `capture.paused`                                 | `false`                | 暂停一切写入；与托盘那一项是同一个开关                                         |
| `ui.theme` / `ui.timezone` / `ui.week_starts_on` | `system` / 系统 / 周一 | 界面与日期切分口径                                                             |

配置写错不会被静默覆盖：程序报错退出并指出具体字段，你的文件保持原样。

## 数据与卸载

| 情况   | 位置                                                                                                           |
| ------ | -------------------------------------------------------------------------------------------------------------- |
| 安装版 | `%LOCALAPPDATA%\OmniSight\`：`config.json`、`data/`、`logs/`（程序在 `Program Files`，与数据分开）             |
| 便携版 | 程序同级目录，由解压后同级的 `portable.marker` 决定；删掉它就回到上面那个位置（已有的 `data/` 不会被自动搬走） |

托盘「打开数据目录」「打开日志目录」直接跳过去。`logs/` 下除运行日志外还有崩溃报告（`crash-<时间戳>.txt`）——只在本机保存，不含窗口标题、按键内容或局部变量，可以直接附在问题报告里。

**卸载**：安装版到「设置 → 应用」里卸载，过程会问要不要一并删除统计数据（默认保留）；便携版退出后取消托盘的「开机自启」再删目录。两种形态都不装服务、不装驱动、不改系统设置，除自启项外不留注册表项。逐步说明见 [FAQ](docs/faq.md)。

## 文档

| 文档                            | 面向                                                     |
| ------------------------------- | -------------------------------------------------------- |
| [隐私白皮书](docs/privacy.md)   | 记录什么、能推出什么、怎么关掉、怎么删掉                 |
| [常见问题](docs/faq.md)         | 杀软误报、权限、端口冲突、便携模式、旧数据导入、完全卸载 |
| [开发](docs/development.md)     | 从源码运行、构建、发版流程                               |
| [扫描留证](docs/scan-record.md) | 发布物的校验值、杀软扫描结论、VirusTotal 查询地址        |

## 鸣谢

OmniSight 的全部起点是下面这两个项目，它们的采集思路、数据口径与界面形态被直接继承下来：

| 项目                                               | 它带来的部分                                                       |
| -------------------------------------------------- | ------------------------------------------------------------------ |
| [TimeLens](https://github.com/sanfuhualv/TimeLens) | 应用使用时长：前台应用采样、会话切分、本地网页仪表盘这一形态       |
| [KeyTrace](https://github.com/sanfuhualv/KeyTrace) | 键盘使用统计：Raw Input 采集、按压时长、全键盘热力图与人体工学分布 |

两者均由 [@sanfuhualv](https://github.com/sanfuhualv) 以 MIT 许可发布。OmniSight 带有导入向导，可以把旧库的历史数据搬过来；有两处口径刻意改了（键盘的小时分布、周的起点），差异写在 [FAQ](docs/faq.md) 里。

## 许可

MIT（见 [LICENSE](LICENSE)）。随产物分发的第三方开源包及其许可见 `THIRD_PARTY_NOTICES.md` 与 `THIRD_PARTY_LICENSES.txt`（由 `tools/licenses.py` 生成）。
