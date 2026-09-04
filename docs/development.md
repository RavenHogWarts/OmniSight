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

### 前端（TypeScript + React + Vite）

前端源码全部在 [`frontend/`](../frontend/) 下：`src/` 是 47 个 `.ts` / `.tsx`，
`styles/` 是 30 个 `.css`。两者一起经 Vite 编译进
`src/omnisight/presentation/static/dist`，**产物提交进版本库**——`pip install` 路径上
没有 Node，wheel 必须自带打包好的前端（`dev/15-frontend-stack-migration.md` §3.2）。

`presentation/static/` 下**没有手写的浏览器代码**，只有三样不该进构建图的东西：产物
（`dist/`）、产物缺失时的兜底样式（`css/shell.css`）、以及浏览器在 JS 之前就索要的
`assets/favicon.svg`。

**样式表也从 `main.tsx` import 进构建图。** 加一个组件样式：在 `frontend/styles/` 下
建文件，再往 `styles/app.css` 加一条 `@import`——级联顺序只有那一处真源。忘了加
`@import` 的症状是"这个组件长得不对"，`test_frontend_contract.py` 里有一条反向断言盯着
（每个样式文件都必须被汇总进来）。

**主题不由前端防闪白。** `<html data-theme>` 由服务端按 `ui.theme` 渲染
（`web.py:index`）；`core/theme.ts` 只管切换与本地偏好的回读，它跑在首次绘制之后。改这
一块时注意 `lifecycle.py:on_config_change` 那条链——设置服务写的是另一个配置对象，断了
的症状是"切成深色、刷新又变回跟随系统"。

```bash
pnpm install                 # 装依赖（运行时 3 个 + 开发期若干）
pnpm build                   # 构建产物（改完前端必跑，产物要跟着提交）
pnpm dev                     # = vite build --watch，改完刷新页面即可
pnpm typecheck               # tsc --noEmit
pnpm test                    # tests/frontend 的纯函数用例（node --test）
```

**没有 HMR，但有"改完自己刷新"。** CSP 是 `script-src 'self'`（`dev/08-privacy-and-security.md`
§3），而 HMR 要连 dev server 的 websocket 并注入内联脚本，两条都撞——保留 CSP 的单一真相比
省一次刷新重要。替代形状是 `tools/devserver.py --watch`：它在**自己进程里**起 vite watch，
再给页面注入一段同源轮询（`tools/_devlive.py`），产物 `manifest.json` 的内容哈希一变就
`location.reload()`。于是一条命令、一个终端，改完 `frontend/` 页面自己刷新。判据是内容哈希
而不是 mtime，所以"存了但什么都没改"不会白刷一次。已经在别处开着 `pnpm dev` 的话，用
`--live-reload` 只要自动刷新那一半。

**改完前端必须重新构建并提交产物。** 忘了的症状是"页面加载的仍然是旧代码，而测试
全绿"——`tools/check_bundle.py --check` 就是为这件事存在的（它重新构建一次并逐字节
比对）。**没有任何流水线在跑它**：这个仓库没有常驻 CI，发版流水线也不跑测试与静态检查
（`dev/10-packaging-and-ops.md` §11.1），所以它属于下面「常用命令」里那批**你自己要记得跑**
的检查。缓解是发版时 `build.py --release` 会现场重新构建前端，因此发出去的 EXE 不会带
过期产物——过期只会留在版本库里。

产物在 `git diff` 里显示为"binary files differ"（`.gitattributes` 给它加了
`linguist-generated -diff`，GitHub 也会在 PR 里默认折叠），**只有 `manifest.json` 例外**
——它的 diff 是唯一有信息量的那一份。因此**合并冲突会是二进制冲突**，而解法本来就不是
文本合并：`pnpm build` 重新构建，产物由源码唯一决定。

```bash
.venv/Scripts/python tools/check_bundle.py --exists   # 产物齐全吗（纯 Python）
.venv/Scripts/python tools/check_bundle.py --check    # 与源码一致吗（需 Node）
.venv/Scripts/python tools/fix_imports.py             # 补齐相对导入的扩展名
```

**相对导入要写真实扩展名**（`./core/store.ts`，不是 `./core/store`）。理由是
`tests/frontend/*.test.ts` 用 `node --test --experimental-strip-types` 直接跑源码，而
Node 的 ESM 只认磁盘上的真路径。`tools/check_frontend.py` 会拦，`tools/fix_imports.py`
能一把补齐。

**没装 Node 也能开发后端**：`tools/check_types.py` 与相关测试都会跳过而不是失败，
`tools/build.py` 会用版本库里已提交的产物打包（并说明它没有重新构建）。

### 图标

图标来自 `lucide-react`，经 [`components/Icon.tsx`](../frontend/src/components/Icon.tsx)
的一张映射表按语义命名（`theme` -> `Contrast`、`insights` -> `ChartColumn`）。加一个图标：
在那张表里加一行 import 与一个键。

笔重与尺寸仍然由 `frontend/styles/base.css` 的 `.icon` 控制（24×24 视框、
`currentColor`、1.5 笔重）
——CSS 声明的优先级高于 SVG 表现属性，所以 lucide 自带的 `stroke-width="2"` 压不过它。

唯一一处内联图标几何在 `templates/dashboard.html` 的 `<noscript>` 里：那一块只在 JS
被禁时渲染，React 到不了。它的笔画规格由 `css/shell.css` 兜住那一种情况——产物缺失时
样式表也缺，而那正是它要覆盖的场景。

## 常用命令

```bash
.venv/Scripts/python -m omnisight                            # 运行（Windows）
.venv/Scripts/python -m pytest                               # 测试
.venv/Scripts/python -m ruff check .                         # 静态检查
.venv/Scripts/python tools/check_platform_leaks.py           # 平台泄漏检查
.venv/Scripts/python tools/check_frontend.py                 # 前端静态检查（结构与禁令）
.venv/Scripts/python tools/check_types.py                    # 前端类型检查（需 Node，缺则跳过）
.venv/Scripts/python tools/check_bundle.py --check            # 前端产物与源码一致吗（需 Node）
.venv/Scripts/python tools/devserver.py --open               # 只跑仪表盘（合成数据，不采集不起托盘）
.venv/Scripts/python tools/devserver.py --watch --open       # 同上 + vite watch + 页面自动刷新
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

0. **本地跑一遍流水线不跑的那几道**——也就是几乎全部：`ruff check .`、`pytest`、
   `check_platform_leaks.py`、`check_frontend.py`、`check_types.py`、
   `check_bundle.py --exists --check`、以及构建后 `smoke.py dist/OmniSight.exe`；
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

`.github/workflows/release.yml` 是**唯一**的流水线，只由 tag 触发，push 与 pull_request 上
没有任何 job；它也**不跑测试与静态检查**，只做核对 tag、构建、生成说明、建 Release 四件事。
唯一的例外是 `npm_licenses.py --check`——许可清单是提交进版本库的快照，过期就等于发出去的
THIRD_PARTY_NOTICES.md 少列依赖，那是分发义务而不是测试。这个取舍与它的代价（哪几道门禁
因此只在本地）记在 `dev/10-packaging-and-ops.md` §11.1 那张表。

## 设计文档

`dev/` 是完整的设计文档集（13 份），实现前应先通读 `01`~`03`；`dev/PROGRESS.md` 是实施
进度的真源：各里程碑判据核对与每一条实现偏离。两者都只在工作区里，不随仓库分发。
