# macOS 打包与虚拟机测试指引

> 面向的场景：手上只有 Windows 真机 + 一台 macOS 虚拟机。包由 CI 构建，
> 虚拟机只负责**实际运行验证**。当前 macOS 处于 M9 中期（B1–B3、C1–C2 已落地，
> B4–B7 的采集适配器未实现），见 `dev/PROGRESS.md` 的 M9 节——本文同时写清
> "现在能测到什么、测不到什么"。

## 路线 A（推荐）：下载 CI 构建的包

仓库有两条流水线，分工见 `release.yml` 与 `build.yml` 的头注释：

1. 开一个 PR（或对任意分支手动跑 **Actions → Build → Run workflow**）；
2. 等 `windows` 与 `macos` 两个 job 变绿；
3. 在运行页底部 **Artifacts** 下载：
   - `OmniSight-macos` —— `OmniSight-macos.tar.gz`（内含 `OmniSight.app`）+ `.sha256`；
   - `OmniSight-windows` —— 便携 zip + `.sha256`；
4. 在虚拟机里：

```sh
cd ~/Downloads
shasum -a 256 OmniSight-macos.tar.gz   # 与 .sha256 的内容比对
tar xzf OmniSight-macos.tar.gz
open OmniSight.app                      # 或拖进「应用程序」后再打开
```

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
