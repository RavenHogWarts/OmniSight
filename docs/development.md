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

## 常用命令

```bash
.venv/Scripts/python -m omnisight                            # 运行（Windows）
.venv/Scripts/python -m pytest                               # 测试
.venv/Scripts/python -m ruff check .                         # 静态检查
.venv/Scripts/python tools/check_platform_leaks.py           # 平台泄漏检查
.venv/Scripts/python tools/check_frontend.py                 # 前端静态检查
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

| 参数 | 作用 |
| --- | --- |
| （无） | 只出 `dist/OmniSight.exe` |
| `--release` | 组装两件发布物：便携 zip + 安装包 |
| `--assemble-only` | 用现有 EXE 重新组装，不跑 PyInstaller |
| `--no-installer` | 跳过安装包（没装 Inno Setup 时用它） |

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
