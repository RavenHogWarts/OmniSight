# OmniSight（全览）

本地运行的**应用使用时长 + 键盘使用**统计工具。数据只留在本机：无账号、不联网、无遥测。

由两个独立项目合并而来——**TimeLens**（应用时长）与 **KeyTrace**（键盘统计）。合并的核心价值不是"少一个托盘图标"，而是**按键事件在采集时刻就能拿到当前前台应用**，从而让"某个应用的键盘热力图"从跨进程 HTTP + 区间求交 + 全表扫描变成一次预聚合表点查，并解锁一批原本不可能的反向分析。

> **当前版本 `0.1.0-alpha.1`（预发布）。** 采集、查询、界面、洞察、旧数据导入均已可用；
> 里程碑与逐条进度见 [dev/PROGRESS.md](dev/PROGRESS.md)。

## 功能

| 面板 | 内容 |
| --- | --- |
| 总览 | 屏幕时间、按键总量、应用排行、24 小时趋势、自动生成的要点 |
| 应用 | 应用列表与详情、会话时间线、别名/分类/合并/排除 |
| 键盘 | 全键盘热力图（次数 / 平均时长 / 最长时长）、24 小时与日历趋势、单键详情、人体工学分布 |
| 洞察 | 应用×键热力图、某个键主要被哪些应用使用、输入节奏与屏幕时间的对比 |
| 设置 | 隐私开关、周期与时区、导入旧数据、导出 CSV/JSON、暂停记录 |

## 平台支持

**当前版本只支持 Windows，macOS 与 Linux 在规划中、尚未实现。** 架构上把平台差异收敛为一层显式的端口/适配器契约，使其他平台可以在不改动核心层的前提下加入——但**架构就绪不等于平台就绪**，下表的"二级/三级"描述的是目标形态，不是现在的能力。

| 级别 | 平台 | 承诺 | 现状 |
| --- | --- | --- | --- |
| 一级 | Windows 10 1809+ / 11 | 全功能，CI 全量测试，性能基准在此度量 | **已交付** |
| 二级 | macOS 12+、Linux X11 | 全功能，已知差异逐条记录 | 未实现（M9 / M8） |
| 三级 | Linux Wayland | 仅键盘统计；应用归因受 Wayland 协议限制不可用 | 未实现（M8） |

## 下载与安装

程序不需要安装，也不需要 Python。**发布只提供一件产物：`OmniSight-portable.zip`**——单文件 EXE 本来就不需要安装步骤，"安装版 vs 便携版"那道选择题没有实质内容；而裸 EXE 带不走许可正文与说明（`LICENSE`、第三方清单、`README.txt` 都在压缩包里）。

解压到任意可写目录（桌面、文档、U 盘都行；别放 `Program Files` 那类需要管理员权限的位置），双击 `OmniSight.exe` 即可。

| 情况 | 数据位置 |
| --- | --- |
| 默认（解压后同级有 `portable.marker`） | 解压目录下的 `data/`、`logs/`、`config.json` |
| 删掉 `portable.marker` 后 | `%LOCALAPPDATA%\OmniSight\`（Windows 惯例位置） |

**下载后请核对校验值。** 本程序未做代码签名，Windows 会显示 SmartScreen 警告（点"更多信息 → 仍要运行"），部分杀软也可能因为"读键盘"这一行为报警——因此校验值是你确认拿到的确实是这份产物的唯一手段：

```powershell
Get-FileHash .\OmniSight-portable.zip -Algorithm SHA256
```

与发布页的 `OmniSight-portable.zip.sha256` 比对。每次发布的校验值、本机杀软扫描结论与按哈希查询 VirusTotal 的地址都记录在 [docs/scan-record.md](docs/scan-record.md)；杀软误报的详细说明与应对见 [docs/faq.md](docs/faq.md)。

## 首次启动

解压后双击 `OmniSight.exe`。程序常驻托盘，不会自己弹窗口。托盘菜单：

```
打开 OmniSight            默认项，双击图标即可
─────────────
暂停记录                  勾选态，暂停时图标变灰
─────────────
开机自启                  勾选态
打开数据目录
打开日志目录
─────────────
关于与隐私说明
退出
```

首次打开仪表盘时会显示一屏说明：**记录什么、不记录什么、数据在哪、如何暂停**。那屏内容是按你此刻的能力探测与配置**算出来**的，不是固定文案——开启了原始事件记录，它就会如实出现在"会记录"那一栏。之后可以从托盘「关于与隐私说明」或设置页随时再看。

仪表盘地址是 `http://127.0.0.1:6100/`，只监听回环地址。访问需要一次性令牌，由托盘那一项自动带上；手输地址会看到 401——它挡住的是任意网页对本机接口的读取（见 [docs/privacy.md](docs/privacy.md)）。

## 配置

`config.json` 只存"启动前就要知道"的项，其余设置存库、在设置页里改。完整示例见 [config.example.json](config.example.json)。

| 项 | 默认 | 说明 |
| --- | --- | --- |
| `server.port` | `6100` | 被占用时**报错退出而不是静默换端口** |
| `capture.store_raw_key_events` | `true` | 每次按键的精确时间与所属应用。关掉后热力图等全部功能照常，只失去组合键与毫秒级节奏分析 |
| `storage.raw_event_retention_days` | `90` | 原始事件保留天数（`0` = 永久）。**当前版本只记录这个值，按期清理排在 M7** |
| `privacy.record_window_titles` | `false` | 窗口标题（网页标题、文件名） |
| `capture.paused` | `false` | 暂停一切写入；与托盘那一项是同一个开关 |
| `ui.theme` / `ui.timezone` / `ui.week_starts_on` | `system` / 系统 / 周一 | 界面与日期切分口径 |

配置写错不会被静默覆盖：程序报错退出并指出具体字段，你的文件保持原样。

## 数据位置

| 情况 | 位置 |
| --- | --- |
| 默认（发布包解压后的样子） | 程序同级目录（`portable.marker` 存在时）：`config.json`、`data/`、`logs/` |
| 删掉 `portable.marker` | `%LOCALAPPDATA%\OmniSight\`（Windows 惯例位置，已有的 `data/` 不会自动搬走） |
| 升级沿用 | 程序同级已有 `data/omnisight.db` 时保持原位，绝不搬走 |

托盘「打开数据目录」「打开日志目录」直接跳过去。`logs/` 下除运行日志外还有崩溃报告（`crash-<时间戳>.txt`）——它只在本机保存，不含窗口标题、按键内容或局部变量，可以直接附在问题报告里。

## 完全卸载

1. 托盘 →「退出」
2. 关掉开机自启：托盘取消勾选「开机自启」，或删除注册表 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` 下的 `OmniSight` 值
3. 删除数据目录（上表位置）
4. 删除 `OmniSight.exe` 本身

程序不写系统目录、不装服务、不装驱动，除第 2 步那个自启项外不留任何注册表项。

## 从源码运行

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
.venv/Scripts/python tools/check_frontend.py         # 前端静态检查
.venv/Scripts/python tools/build.py        # 只构建 EXE（日常开发用这个）
.venv/Scripts/python tools/build.py --release   # 构建 + 组装发布物（便携 zip）
.venv/Scripts/python tools/smoke.py dist/OmniSight.exe   # 对产物冒烟
.venv/Scripts/python tools/scan_record.py  # 扫描留证（写 docs/scan-record.md）
```

`tools/build.py` **默认只出 EXE**——本地一天构建好几次，而组装（重新生成许可清单、写 `README.txt`、打 zip、算摘要）只有发布那一次用得上。`--release` 组装发布物，`--assemble-only` 用现有 EXE 重新组装。发布物只有 `OmniSight-portable.zip` 一件，`dist/OmniSight.exe` 是构建产物而不是发布物。配置了 `OMNISIGHT_SIGN_THUMBPRINT` 或 `OMNISIGHT_SIGN_PFX` 时，签名发生在算校验值与打包之前（未配置就是不签名，构建照常）。

## 文档

| 文档 | 面向 |
| --- | --- |
| [docs/privacy.md](docs/privacy.md) | 隐私白皮书：记录什么、能推出什么、怎么关掉、怎么删掉 |
| [docs/faq.md](docs/faq.md) | 杀软误报、Raw Input 权限、端口冲突、便携模式、旧数据导入 |
| [docs/scan-record.md](docs/scan-record.md) | 发布物的校验值、本机杀软扫描结论、VirusTotal 查询地址 |
| [dev/](dev/) | 完整设计文档集（13 份）；实现前应先通读 `01`~`03` |
| [dev/PROGRESS.md](dev/PROGRESS.md) | 实施进度真源：各里程碑判据核对与实现偏离 |

## 许可

MIT（见 [LICENSE](LICENSE)）。随产物分发的第三方开源包及其许可见 `THIRD_PARTY_NOTICES.md` 与 `THIRD_PARTY_LICENSES.txt`（由 `tools/licenses.py` 生成）。
