# 开发

面向要从源码跑、构建或发版的人。产品说明在 [README](../README.md)。

> 下文引用的 `dev/` 是完整的设计文档集（13 份 + 进度真源）。**它不进版本库**
> （`.gitignore` 里的 `dev`），所以这里只给编号不给链接——在检出的工作区里能打开，
> 在 GitHub 上看不到。

## 环境

项目使用**项目级 Python 3.12 与仓库内 `.venv`**，不依赖全局解释器。

```bash
uv python install 3.12
uv venv --python 3.12 .venv
uv pip install -r requirements-dev.txt -r requirements-optional.txt
```

### 前端类型检查（可选）

前端仍是**零构建**的原生 ESM：`static/js` 下的 `.js` 就是浏览器加载的那份文件，
没有任何编译步骤。但类型是有的——JSDoc 加上 `static/js/types/api.d.ts`，由 tsc 以
`noEmit` 模式检查（`dev/07-frontend-architecture.md` §2.1）。

它拦的是这一类：后端把 `/usage/period` 的某个字段改了名，前端只是静默显示空值，而
"这段时间没有记录"恰好也是合法状态。`tools/check_frontend.py` 查不到（它只做导入解析
与文本模式），`tests/frontend/dom-shim.js` 也测不到（它断言渲染结构）。

装了 Node 的话：

```bash
pnpm install                                   # 只装 typescript 一个开发依赖
pnpm typecheck                                 # 等价于下面那条
.venv/Scripts/python tools/check_types.py      # pytest 与发布流水线走这条
```

**没装 Node 也能开发**：`tools/check_types.py` 与相关测试都会跳过而不是失败，与
`tests/frontend/` 的 Node 测试同一条原则。产物里没有任何 npm 包。

### 图标（生成物）

`templates/_icon_sprite.html` 是**生成的**，不要手改。真源是 `tools/icons.py` 的
`ICON_SOURCES`——一张"我们的 id → lucide 图标名"映射表；几何从开发期依赖
`lucide-static` 里读，剥掉它自带的 `stroke-width` 等表现属性（笔重由 `base.css` 的
`.icon` 统一控制，规格是 1.5）。

加或换一个图标：

```bash
# 1. 改 tools/icons.py 的 ICON_SOURCES（加一行 "我们的 id": "lucide 名"）
# 2. 改 static/js/components/icon.js 的 ICON_NAMES（加同一个 id）
.venv/Scripts/python tools/icons.py            # 3. 重新生成精灵表
```

`tests/unit/test_icon_sprite.py` 盯着三处一致（映射表 / 生成物 / `ICON_NAMES`），
另外查视框、表现属性、以及"引用到的 `#i-x` 都存在"——引用一个不存在的 id 时浏览器
**不报错**，只是那个位置什么都不画。

**运行时仍然零依赖**：`lucide-static` 是 devDependency，生成结果是内联的 `<symbol>`
精灵表并提交进版本库，因此没装 Node 的机器照样能跑，产物里也没有 npm 包。

### 前端调试与页面读取

零构建的代价之一是**没有 dev server**：改一个 `.js` 要看到效果，得先有一个在跑的
OmniSight。而 `python -m omnisight` 会起托盘、会真采集、会写 `%LOCALAPPDATA%`——调版面
不需要这三样，还各带一个副作用（要管理员权限、页面数字每秒都在动因此两张截图不可比、
切设置会改到真实配置）。

三条路补这个洞：

| 工具                           | 干什么                                                       |
| ------------------------------ | ------------------------------------------------------------ |
| `tools/devserver.py`           | 只把仪表盘跑起来：合成数据、不采集、不起托盘、静态资源不缓存 |
| `tools/page.py`                | **批量**读它：截图 + 可量化的版面报告（需要时自己起服务器）  |
| `.mcp.json` 的 chrome-devtools | **交互**读它：一问一答地查一个具体现象（见下文）             |

第一条是另外两条的地基——不管用哪种方式读页面，先得有一个页面在跑。

#### 前置

`devserver.py` 只要 Python，没有别的前置。`page.py` 另外要：

```bash
pnpm install     # 装 playwright-core：1 个包、0 个传递依赖，**不下载浏览器**
```

它驱动的是**机器上已装的 Edge**（`channel: 'msedge'`）。因此没装 Node 的机器仍然能用
`devserver.py` 自己开浏览器调试，只是 `page.py` 不可用——与 `check_types.py` 同一条原则。
`playwright-core` 是 devDependency，**产物里依然没有 npm 包**。

> `dev/PROGRESS.md:1444` 曾以「Node 依赖树 + 数百 MB 浏览器下载」否掉 Playwright，
> `dev/15-frontend-stack-migration.md` §5 要求「Node 依赖树进仓库后重新评估」。这就是那次
> 评估的结果：两条反对理由在 `playwright-core` + 系统 Edge 这个组合下都不成立。

#### 起服务器

```bash
.venv/Scripts/python tools/devserver.py                 # 打印带令牌的 URL
.venv/Scripts/python tools/devserver.py --open          # 顺带用默认浏览器打开
.venv/Scripts/python tools/devserver.py --days 400 --fresh   # 重播一年数据
```

默认监听 `127.0.0.1:6180`（刻意避开生产的 `6100`，两边可以同时开着），数据落在仓库内
`.dev/`（已在 `.gitignore` 里）。首次启动会用 `tools/seed.py` 播 45 天合成数据，约几秒；
之后直接复用那个库，`--fresh` 才重播。

几条刻意的行为，看到时不必怀疑是 bug：

- **令牌是固定的** `omnisight-dev-token`——URL 要能被贴进浏览器、被脚本拼出来。令牌校验
  本身没关，Host 校验也没动（08 文档 §3 的威胁模型防的是任意网页，不是本机进程）。
- **静态资源一律 `no-store`**。ES 模块的浏览器缓存比 HTTP 缓存黏，改完刷新看到旧代码是
  这套架构最常见的一次「我明明改了」。
- **SSE 关掉**，前端走 30 秒轮询。没有采集就没有事件可推，开着只会让页面敲一个必然 404
  的端点，而那条 404 会变成 `page.py` 报告里每次都在的假警报。
- **首启说明自动确认掉**，否则每张截图拍到的都是那张铺满全屏的模态。要看它本身用
  `--onboarding`。
- **采集状态是假的「正常」**。真实值是「没在跑」，那会让状态点永久停在最差的一档；
  想看真实异常态用 `--capture-down`。

#### 读页面

```bash
.venv/Scripts/python tools/page.py                                  # 总览 @1440 浅色
.venv/Scripts/python tools/page.py --view keyboard --width 1024 --theme dark
.venv/Scripts/python tools/page.py --all                            # 四视图 × 四宽度 × 深浅 = 32 张
.venv/Scripts/python tools/page.py --view overview --forced-colors --reduced-motion
.venv/Scripts/python tools/page.py --view apps --settings            # 打开设置抽屉再截
```

服务器已经在跑就直接用，没在跑就起一个临时的、退出时收掉（`--keep` 留着它，接着看好几轮
时用这个）。截图与报告落在 `.dev/shots/`。

stdout 上每次捕获一行结论，只讲能拿去改代码的：

```
── keyboard @ 1024px dark (page=system, dark=true)  →  .dev/shots/keyboard-1024-dark.png
   无异常（5 张卡、1613 个可见元素）
── overview @ 1920px light (page=system, dark=false)  →  .dev/shots/overview-1920-light.png
   ! 超宽屏仍是单列（14 §4.1 要求 ≥1790px 分主列 + 副列）
   ! 主列 1392px 超过 1240px
```

`.dev/shots/report.json` 是完整的那一份，每次捕获一条记录：

| 字段                                             | 内容                                                                                          |
| ------------------------------------------------ | --------------------------------------------------------------------------------------------- |
| `outline`                                        | **版面骨架**：顶栏 / 周期栏 / 每张卡的选择器 + 位置 + 尺寸 + 标题。调布局时真正要看的那份结构 |
| `tinyText`                                       | 计算字号小于 11px 的可见文字（14 §2.5 P1-2 的判据）                                           |
| `clipped`                                        | `scrollWidth > clientWidth` 的元素；`ellipsis` 区分「刻意省略号」与「直接切字」               |
| `offscreen`                                      | 右边缘越过视口的元素                                                                          |
| `horizontalOverflow` / `layoutMax` / `ultrawide` | 横向溢出、`--layout-max` 令牌实测值、≥1790px 档的双列判据                                     |
| `console` / `failedRequests`                     | 控制台 error/warning、pageerror、4xx 与网络失败                                               |
| `banners` / `emptyStates`                        | 降级横幅与空态——降级预设下用它确认「该出现的提示出现了」                                      |

判据**读令牌而不写死数字**（`--layout-max` 从页面的 computed style 里取），因此 14 文档
§4.1 的三档宽度分级实现到哪一步，报告会如实反映，不会因为常量过期而误报。

#### 交互式调试：chrome-devtools MCP

上面那条是**批量**路径：一条命令扫完 32 种组合，产出可 diff 的 `report.json`，适合"改完
回归一遍"与将来进 CI。它答不了的是"这个元素为什么跳一下"——那需要在页面还活着的时候
连着问好几轮。

`.mcp.json` 里配好了 Google 官方的 [chrome-devtools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp)，
补的就是这一半。它进仓库（而不是各人机器上的全局配置），所以团队里每个人拿到的是同一份：

```json
{ "command": "npx", "args": ["-y", "chrome-devtools-mcp@1.8.0", "--isolated", "--viewport=1440x900"] }
```

三个选择的理由（JSON 放不下注释，写在这里）：

- **版本钉死** `1.8.0`，与 `lucide-static` / `typescript` / `playwright-core` 一样。`@latest`
  会让"昨天好的今天坏了"变成一种日常。
- **`--isolated`**：用临时的 user-data-dir，关掉即清。它不碰你真实的 Chrome 配置——没有
  你的 cookie、历史与登录态。对一个把隐私写进设计文档的项目，这条不是可选项。顺带解决
  "新开的 Chrome 被已在运行的实例接管"那个老问题。
- **`--viewport=1440x900`**：与 `page.mjs` 的默认宽度对齐。两条路从同一个几何出发，看到
  的差异才是真差异。

用它的时候**仍然要先起开发服务器**——MCP 只负责驱动浏览器，页面得有人提供：

```bash
.venv/Scripts/python tools/devserver.py        # 前台跑到 Ctrl+C，另开一个终端做别的
# 然后让 agent 打开 http://127.0.0.1:6180/?token=omnisight-dev-token
```

两条路的分工：

|      | 批量（`page.py`）                               | 交互（MCP）                                                                                           |
| ---- | ----------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| 适合 | 回归、扫宽度/主题、进 CI                        | 追一个具体现象、看网络瀑布、性能 trace                                                                |
| 产出 | 截图 + `report.json`（可 diff、可提交进 issue） | 一问一答，不留痕                                                                                      |
| 判据 | 写在 `page.mjs` 里，版本化、会一直跑            | 每次现场用 `evaluate_script` 现推                                                                     |
| 前置 | `pnpm install`（1 个包，不下载浏览器）          | `npx` 首次现拉 MCP 包；浏览器默认用系统已装的 stable Chrome（`--channel` / `--executable-path` 可改） |

`--browser-url=http://127.0.0.1:9222` 可以让它接到一个已经在跑的、开了远程调试端口的
浏览器上（VS Code 的集成浏览器若暴露了调试端口，走的就是这条）。默认不开：让它自己起一个
干净实例，行为更可预期。

#### 调降级态

06 文档 §4.2 的三级降级表达在本机只看得到 tier 1 那一档，而降级态最容易画错、也最少被
看见。`--preset` 伪造能力集（服务器启动时装配，改它要重启）：

```bash
.venv/Scripts/python tools/devserver.py --preset linux-wayland --open
.venv/Scripts/python tools/page.py --preset no-keyboard --view keyboard   # 顺带起服务器
```

| 预设                                                       | 调出来的东西                                                   |
| ---------------------------------------------------------- | -------------------------------------------------------------- |
| `full`（默认）                                             | Windows 一级平台，全能力                                       |
| `macos`                                                    | 二级平台：无按键时长、缺输入监控授权、带 `setup_hint`          |
| `linux-wayland`                                            | 三级平台：**应用归因不可用**——合并的核心价值缺席时页面长什么样 |
| `no-keyboard` / `no-foreground` / `no-icons` / `no-titles` | 单点能力缺失，比整平台降级更常见也更容易漏                     |

#### 它替下了 14 §8.3 里的哪几条

14 文档 §8.3 是「只能用眼睛确认的」清单。其中这几条现在是机器验的——`--all` 一次跑完：

- 键盘 1024 / 1280 / 1440 / 1920 四档：键面数值 ≥11px 或不印；不横向溢出
- 深浅两色逐屏看一遍（`--theme light --theme dark`）
- 2560 宽窗口：副列铺开，主列不超过 1240px（`--width 2560`）
- 强制颜色模式（`--forced-colors`）、`prefers-reduced-motion`（`--reduced-motion`）
- 类别构成条装不下的段有没有被裁字（`clipped` 里 `ellipsis: false` 的那些）

剩下的仍然要眼睛：键帽的按压动画像不像按了一个键、未按过的键与按过的键一眼能否分开、
色阶在深浅两套下有没有残留。**截图解决不了「像不像」，但它把「有没有」交给了机器。**

## 常用命令

```bash
.venv/Scripts/python -m omnisight                            # 运行（Windows）
.venv/Scripts/python -m pytest                               # 测试
.venv/Scripts/python -m ruff check .                         # 静态检查
.venv/Scripts/python tools/check_platform_leaks.py           # 平台泄漏检查
.venv/Scripts/python tools/check_frontend.py                 # 前端静态检查（结构与禁令）
.venv/Scripts/python tools/check_types.py                    # 前端类型检查（需 Node，缺则跳过）
.venv/Scripts/python tools/icons.py                          # 重新生成图标精灵表（需 lucide-static）
.venv/Scripts/python tools/devserver.py --open               # 只跑仪表盘（合成数据，不采集不起托盘）
.venv/Scripts/python tools/page.py --all                     # 无头浏览器读页面：截图 + 版面报告
.venv/Scripts/python tools/licenses.py                       # 重新生成第三方许可清单
.venv/Scripts/python tools/build.py                          # 只构建 EXE（日常开发用这个）
.venv/Scripts/python tools/build.py --release                # 构建 + 组装两件发布物
.venv/Scripts/python tools/smoke.py dist/OmniSight.exe       # 对产物冒烟
.venv/Scripts/python tools/release_prepare.py --dry-run      # 按提交记录建议下一个版本号
.venv/Scripts/python tools/release_notes.py --no-artifacts   # 预览发版说明
.venv/Scripts/python tools/scan_record.py                    # 扫描留证（写 docs/scan-record.md）
```

## 架构

平台差异全部收敛在 `adapters/` 的端口/适配器契约后面：`core/` `capture/` `storage/`
`services/` `presentation/` 五层**不得出现任何 `sys.platform` 判断**，由
`tools/check_platform_leaks.py` 机械化拦住。这条从第一天就打开——它便宜，而事后从散落的
分支里往外提取抽象非常痛苦。详见 `dev/02-architecture.md`。

同一条约束的另一半在测试里：**除端到端与手工层外，全部测试必须能在三个平台上通过**。需要
真实 Windows API 的用例用 `@pytest.mark.windows_only` 标记，数量应保持极少——标记数量增长
就说明平台依赖正在向上层泄漏（`dev/11-testing.md` §1）。

## 构建

`tools/build.py` **默认只出 EXE**：本地一天构建好几次，而组装（重新生成许可清单、写
`README.txt`、编译安装包、打 zip、算摘要）只有发布那一次用得上。

| 参数              | 作用                                  |
| ----------------- | ------------------------------------- |
| （无）            | 只出 `dist/OmniSight.exe`             |
| `--release`       | 组装两件发布物：便携 zip + 安装包     |
| `--assemble-only` | 用现有 EXE 重新组装，不跑 PyInstaller |
| `--no-installer`  | 跳过安装包（没装 Inno Setup 时用它）  |

安装包要 Inno Setup 的 `ISCC.exe`：自动找不到时用 `OMNISIGHT_ISCC` 指向它。向导的中文消息
文件随仓库分发（`installer/Languages/`），不指向构建机上 Inno 的安装目录——否则"向导是什么
语言"取决于谁在构建。

配置了 `OMNISIGHT_SIGN_THUMBPRINT` 或 `OMNISIGHT_SIGN_PFX` 时会签名，且**签名发生在算校验值
与打包之前**（未配置就是不签名，构建照常）。证书口令只从环境变量读，不进命令行、不进日志。

`dist/OmniSight.exe` 是构建产物而**不是**发布物：它带不走 `LICENSE`、第三方许可清单与
`README.txt`，而那几份是分发义务。

## 发版

**触发条件是手工打 tag**，格式 `v<版本号>`：`v0.1.0-alpha.1`、`v0.1.0-beta.1`、`v0.1.0`。

带预发布标记的 tag 发成 GitHub 的 pre-release，`v0.1.0` 这样的发成正式版——判定用的就是 EXE
属性页上那个「（预发布）」标记同一个函数。**tag 与代码里的 `__version__` 对不上时流水线在构建
之前就失败**：发布页写 0.2.0、而它发出去的文件属性页写 0.1.0-alpha.1，是最难被用户理解的
一种不一致。

变更日志取自 git 提交记录（不维护 `CHANGELOG.md`），按 Conventional Commits 的前缀分节；
**基线是同类的上一个 tag**——预发布跟上一个预发布比，正式版跟上一个正式版比。否则 `v0.1.0`
会拿 `v0.1.0-rc.1` 当基线，说明里只剩 rc 之后那几条提交，而这个正式版真正交付的东西全在
它前面。

步骤：

0. **本地跑一遍流水线不跑的那几道**：`pytest`、`check_platform_leaks.py`、以及构建后
   `smoke.py dist/OmniSight.exe`；
1. `python tools/release_prepare.py`——按提交记录算出下一个版本号（`feat:` → minor、
   `fix:` → patch、`feat!:` 在 0.x 期间仍走 minor；当前是预发布时默认只递增序号），把
   `src/omnisight/__init__.py` 与 `pyproject.toml` 两处字面量一起改掉，再打印该跑的命令。
   它**不提交、不打 tag、不推送**；
2. `python tools/release_notes.py --no-artifacts` 预览发版说明；
3. 提交 → `git tag v0.1.0-alpha.1` → `git push origin v0.1.0-alpha.1`；
4. 等流水线绿，看一眼 Release 页面（徽章、两件产物 + 两个 `.sha256`、正文）；
5. **对发出去的字节冒烟 + 留证**：下载那两件产物，把 zip 里的 EXE 解到同一个目录，
   `python tools/smoke.py <那个目录>\OmniSight.exe`，再
   `python tools/scan_record.py --dist <那个目录>`，提交 `docs/scan-record.md`。

第 5 步的顺序与直觉相反（先发布再留证），因为**发出去的字节是 runner 构建的**，而 PyInstaller
的产物不是逐字节可复现的：本地那份的摘要与发布页上的对不上。留证要对着用户真正下载到的
文件做。

`.github/workflows/release.yml` 只由 tag 触发，push 与 pull_request 上没有任何 job。这个
取舍与它的代价（哪几道门禁因此只在本地）记在
`dev/10-packaging-and-ops.md` §11。

## 设计文档

`dev/` 是完整的设计文档集（13 份），实现前应先通读 `01`~`03`；`dev/PROGRESS.md` 是实施
进度的真源：各里程碑判据核对与每一条实现偏离。两者都只在工作区里，不随仓库分发。
