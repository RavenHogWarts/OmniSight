# 第三方声明

OmniSight 自身以 MIT 许可发布。发布物里静态包含了下列开源 Python 包；
它们各自的完整许可正文见同目录的 `THIRD_PARTY_LICENSES.txt`。

本文件由 `tools/licenses.py` 生成，请勿手改——依赖变化后重新生成。
清单只包含**随产物分发的**依赖（`requirements.txt` +
`requirements-optional.txt` 的传递闭包，按当前平台的环境标记求值）；
开发期依赖（pytest / ruff / PyInstaller 等）不在其中。

| 包 | 版本 | 许可 | 项目地址 |
| --- | --- | --- | --- |
| blinker | 1.9.0 | MIT License | <https://github.com/pallets-eco/blinker/> |
| bottle | 0.13.4 | MIT | <http://bottlepy.org/> |
| cffi | 2.1.1 | MIT-0 | <https://github.com/python-cffi/cffi> |
| click | 8.5.0 | BSD-3-Clause | <https://github.com/pallets/click/> |
| clr_loader | 0.3.1 | 未声明 | <https://github.com/pythonnet/clr-loader> |
| Flask | 3.1.1 | BSD-3-Clause | <https://github.com/pallets/flask/> |
| itsdangerous | 2.2.0 | BSD License | <https://github.com/pallets/itsdangerous/> |
| Jinja2 | 3.1.6 | BSD License | <https://github.com/pallets/jinja/> |
| MarkupSafe | 3.0.3 | BSD-3-Clause | <https://github.com/pallets/markupsafe/> |
| pillow | 11.3.0 | MIT-CMU | <https://python-pillow.github.io> |
| proxy_tools | 0.1.0 | MIT | <http://github.com/jtushman/proxy_tools> |
| psutil | 7.1.0 | BSD-3-Clause | <https://github.com/giampaolo/psutil> |
| pycparser | 3.0 | BSD-3-Clause | <https://github.com/eliben/pycparser> |
| pynput | 1.8.2 | LGPLv3 | <https://github.com/moses-palmer/pynput> |
| pystray | 0.19.5 | LGPLv3 | <https://github.com/moses-palmer/pystray> |
| pythonnet | 3.1.0 | MIT | <https://pythonnet.github.io/> |
| pywebview | 5.4 | BSD License | <https://pywebview.flowrl.com/> |
| pywin32 | 311 | PSF | <https://github.com/mhammond/pywin32> |
| six | 1.17.0 | MIT | <https://github.com/benjaminp/six> |
| typing_extensions | 4.16.0 | PSF-2.0 | <https://github.com/python/typing_extensions> |
| tzdata | 2026.3 | Apache-2.0 | <https://github.com/python/tzdata> |
| Werkzeug | 3.1.8 | BSD-3-Clause | <https://github.com/pallets/werkzeug/> |

共 22 个包。

下列 2 个包以 **LGPL** 系许可发布（pynput、pystray）。
LGPL 要求用户能够替换这些库；OmniSight 自身以 MIT 开源且构建脚本完整公开
（`tools/build.py`），因此这一义务的行使方式是：检出源码、修改或替换对应库、
重新构建。GPL/AGPL 系许可的依赖会被构建直接拒绝，与此不同。

另有 1 个包的元数据没声明 LGPL，但其 wheel 里随附了 LGPL 许可正文：

- **pywin32**（元数据写 PSF）：`adodbapi/license.txt`

这些组件是否真的进了 EXE 取决于 PyInstaller 的模块收集，但本清单按**包**
粒度声明，因此同一条 LGPL 义务照样列在这里。

有 1 个包的元数据未声明许可标识（clr_loader）。对应的许可正文随 wheel 分发，
见 `THIRD_PARTY_LICENSES.txt` 里那一节——缺标识不等于缺许可。

## 随产物分发的 npm 包

前端由 TypeScript + React 写成，经 Vite 打包进
`src/omnisight/presentation/static/dist`（15 文档方案 A）。下列包的代码**打进了那份
产物**，因此随发布物分发；完整许可正文见 `THIRD_PARTY_LICENSES.txt`。

| 包 | 版本 | 许可 | 项目地址 |
| --- | --- | --- | --- |
| lucide-react | 1.40.0 | ISC | <https://lucide.dev> |
| react | 19.2.8 | MIT | <https://react.dev/> |
| react-dom | 19.2.8 | MIT | <https://react.dev/> |
| scheduler | 0.27.0 | MIT | <https://react.dev/> |

共 4 个包，是 `package.json` 的 `dependencies` 传递闭包。
开发期依赖（vite、typescript、@types/*、playwright-core）不进产物，
因此不在其中。
