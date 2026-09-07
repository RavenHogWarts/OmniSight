# macOS 打包与虚拟机测试指引

> 面向的场景：手上只有 Windows 真机 + 一台 macOS 虚拟机。包由 CI 构建，
> 虚拟机只负责**实际运行验证**。当前 macOS 处于 M9 中期（B1–B3、C1–C2 已落地，
> B4–B7 的采集适配器未实现），见 `dev/PROGRESS.md` 的 M9 节——本文同时写清
> "现在能测到什么、测不到什么"。

## 架构说明（选哪个产物）

mac 的 CI 产物分两种架构，名字带后缀：

- `OmniSight-macos-x64` —— Intel。Windows 宿主上的 macOS 虚拟机是 x86_64，**选这个**；
- `OmniSight-macos-arm64` —— Apple Silicon（M 系列真机 / ARM 虚拟机）。

不确定自己的机器是什么架构时：

```sh
uname -m    # x86_64 = Intel（或 Rosetta 下的终端）；arm64 = Apple Silicon
```

选错架构的症状就是那张"你无法打开应用程序'OmniSight'，因为这台 Mac 不支持此
应用程序"的弹窗（图标带禁止符号）。universal2（双架构合一）是更好的长期形态，
但被 Pillow 等 binary 依赖的 wheel 选择问题挡着——记账在 `dev/PROGRESS.md` 的
M9 节，解决后可以合并回一个产物。

## 路线 A（推荐）：下载 CI 构建的包

1. 开一个 PR，或对任意分支手动跑 **Actions → Build → Run workflow**——手动运行时
   可以只勾要构建的目标（比如只勾"构建 macOS x64"，省下另外两条 runner 时间）；
2. 等对应 job 变绿；
3. 在运行页底部 **Artifacts** 按架构下载 `OmniSight-macos-x64`（或 `-arm64`）；
4. 下载得到的是 GitHub 的 artifact 包装 zip（平台行为，去不掉），**里面是
   `OmniSight-macos-<架构>.tar.gz` 与它的 `.sha256`**：

```sh
cd ~/Downloads
unzip OmniSight-macos-x64.zip
tar xzf OmniSight-macos-x64.tar.gz
open OmniSight.app                      # 或拖进「应用程序」后再打开
```

产物只保留 **24 小时**（它是待验证件，不是存档），过期就重新跑一次流水线。
CI 产物只带链接器的 **ad-hoc 签名**（自签名私钥不进 CI），因此每次下载的包
都要重新给一次「输入监控」授权。嫌烦就走下面的"固定签名身份"，或改用路线 B。

## 路线 B：在虚拟机里从源码构建

```sh
git clone https://github.com/RavenHogwarts/OmniSight.git
cd OmniSight
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt -r requirements-optional.txt
python tools/build.py          # 产物在 dist/OmniSight.app
```

不需要 Node：没装 pnpm 时 `build.py` 用版本库里已提交的前端产物。
想先不打包直接跑源码（迭代最快）：

```sh
PYTHONPATH=src python main.py
```

### 固定一个自签名身份（建议做一次）

TCC 的「输入监控」授权绑定 bundle id + 代码签名的 designated requirement；
ad-hoc 签名每次构建都变，等于每个版本都要重新授权。固定身份后授权跨构建存活：

1. 钥匙串访问 → 证书助理 → 创建证书：类型选**代码签名**，命名如 `omnisight-dev`；
2. 之后每次构建后签一次（或组装时用环境变量）：

```sh
codesign --sign omnisight-dev --deep --force --options runtime dist/OmniSight.app
# 或：OMNISIGHT_CODESIGN_IDENTITY=omnisight-dev python tools/build.py --release
```

3. 私钥**不要**丢：换身份 = 全部用户重新授权（19 文档 R22）。

## 当前能测什么、测不到什么

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| 启动 / 菜单栏托盘 / Web 仪表盘 | ✅ | 全功能；仪表盘地址由托盘带令牌打开 |
| 键盘统计 | ⚠️ 走 pynput 兜底 | 需要「输入监控」授权（见下）；左右修饰键合并、无按压时长、`key_position_stable=false` |
| Mac 键位 / 布局 | ✅ | `mac_ansi` / `mac_iso` 族与 ⌘⌥⇧ 标签已就位 |
| 应用时长 / 前台识别 | ❌ | B4 未实现——总览与应用页会是空的，属预期 |
| event tap 键盘后端 | ❌ | B6 未实现 |
| 图标 / 自启 / 空闲判定 | ❌ | B4/B7 未实现 |

**给「输入监控」授权**：系统设置 → 隐私与安全性 → 输入监控。源码直跑时授权归因到
**终端**（Terminal/iTerm），打包后归因到 **OmniSight.app**——是两个不同的条目。
虚拟机里这套与真机一致。

## 进入网页控制台

程序是**菜单栏常驻**应用，没有主窗口（Dock 图标点了不出窗口是正常的）。两个入口：

- **正常入口**：屏幕顶部菜单栏右侧的 OmniSight 图标（蓝色"眼睛"）→「打开 OmniSight」，
  浏览器会自动打开带令牌的仪表盘；
- **手动入口**（菜单栏找不到图标 / 远程排查时）：

```sh
cat ~/Library/Application\ Support/Omnisight/runtime.json
# {"port": 6100, "token": "……"}
open "http://127.0.0.1:6100/?token=<上面读到的 token>"
```

`runtime.json` 只在程序运行期间存在（干净退出即删除）——它不在，多半是程序没起来。
确认进程：`pgrep -fl OmniSight`。菜单栏图标被挤掉时，按住 ⌘ 拖动可以把它挪回可见
区域；macOS 也可能在"控制中心"设置里隐藏了它。

## 出问题时看哪里

- 数据与日志：`~/Library/Application Support/OmniSight/`（`logs/omnisight.log`、
  崩溃报告；启动失败且无窗口时看数据目录下的 `STARTUP_ERROR.txt`）；
- `/api/v1/status` 返回的 `capabilities` 与 `degraded` 是判断"哪些能力在跑、
  为什么没在跑"的第一入口（带令牌访问，地址从托盘拿）；
- 构建本身的失败：Actions 页的 job 日志（路线 A）或终端输出（路线 B）。

## 给开发侧的反馈清单

在虚拟机上测完一轮后，最有价值的反馈依次是：

1. 构建能不能过、产物能不能起（路线 A 的两个 job 绿不绿）；
2. 托盘是否出现、菜单是否可用、仪表盘是否完整（含键盘页的 Mac 布局图）；
3. pynput 路径的键盘计数是否工作（授权前后各看一次）；
4. 任何 `degraded` 说明里没见过的降级码。

拿到这些之后，B4–B7（前台识别、TCC 探测、event tap、装配）就可以按
`dev/20-macos-execution.md` 的施工图在真机上迭代了。
