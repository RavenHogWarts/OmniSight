# 发布物扫描记录

本文件由 `tools/scan_record.py` 生成，请勿手改——每次发布重新生成一份。
它只回答一个问题：**这份产物在发出去之前被扫过没有，结果是什么。**

OmniSight 全局读取键盘输入，杀软把它标为可疑是合理的启发式判断——为什么会这样、
以及怎么处理，见 [faq.md 的杀软一节](faq.md)。这份记录不试图说服你它无害，
只提供可核对的事实。

- 程序版本：`0.1.0-alpha.1`
- 记录时间：2026-09-03T00:14:34+08:00
- 生成环境：Python 3.12.13 / win32

## 产物与校验值

**发布两件产物**：便携 zip 与安装包（分工是安装位置，见 [README](../README.md)）。
下表同时列出它们内含的可执行文件，因为杀软报的是它，而你核对下载用的是发布物的校验值。

| 文件 | 角色 | 大小 | SHA-256 |
| --- | --- | --- | --- |
| `OmniSight.exe` | 两件发布物内含的可执行文件 | 21.3 MB | `91eb1fc2eadd4998d9db33c468ec58b731c97932e92f19c6aedfe8a684169877` |
| `OmniSight-portable.zip` | 发布物 | 21.0 MB | `855a6ee08599af5e3e4203cf47dad1aaf763931694d8abdb7e3ffdb52c348301` |
| `OmniSight-Setup.exe` | 发布物 | 22.9 MB | `b980d068e994b5d91afd045ce57513f2d8798789298aef40808ef790aa9aceb2` |

下载后自己算一遍，与上表比对：

```powershell
Get-FileHash .\OmniSight-portable.zip -Algorithm SHA256
Get-FileHash .\OmniSight-Setup.exe -Algorithm SHA256
```

## 本机杀软扫描

引擎：Windows Defender（引擎平台版本 4.18.26080.3-0）

| 文件 | 结果 | 说明 |
| --- | --- | --- |
| `OmniSight.exe` | 未执行（引擎不可用） | [Failed][0x80004005] 未指定的错误 |
| `OmniSight-portable.zip` | 未执行（引擎不可用） | [Failed][0x80004005] 未指定的错误 |
| `OmniSight-Setup.exe` | 未执行（引擎不可用） | [Failed][0x80004005] 未指定的错误 |

复现命令（`<MpCmdRun>` 在 `%ProgramData%\Microsoft\Windows Defender\Platform\<版本>\` 下）：

```powershell
& "<MpCmdRun>" -Scan -ScanType 3 -File .\OmniSight.exe -DisableRemediation
```

`-DisableRemediation` 是刻意的：取证时不希望杀软顺手把产物隔离掉。

**"未报警"的含义有限**：它是这一个引擎、这一份特征库、这一次扫描的结论，不是
"本程序无害"的证明。真正能支撑后者的是源码公开与下面第三条路径。

## VirusTotal

状态：**未提交**（提交是人工步骤，见下）

按 SHA-256 查询（**查询不上传文件**，用的是上表里本地算出的哈希）：

- `OmniSight.exe` → <https://www.virustotal.com/gui/file/91eb1fc2eadd4998d9db33c468ec58b731c97932e92f19c6aedfe8a684169877>
- `OmniSight-portable.zip` → <https://www.virustotal.com/gui/file/855a6ee08599af5e3e4203cf47dad1aaf763931694d8abdb7e3ffdb52c348301>
- `OmniSight-Setup.exe` → <https://www.virustotal.com/gui/file/b980d068e994b5d91afd045ce57513f2d8798789298aef40808ef790aa9aceb2>

提交样本是人工步骤：上传到 VirusTotal 等于公开发布这个文件，此后任何人都能按
哈希取走样本，因此这个决定由维护者本人做，构建脚本不代劳。首次发布时上面的
链接可能显示"未收录"——那说明还没有人提交过这个哈希，**不代表扫描通过**。

## 你可以自己验证的三条路径

1. **核对校验值**——确认下载到的字节与本记录一致（上面那条 `Get-FileHash`）。
2. **按哈希查 VirusTotal**——不需要上传，也不需要相信本文件里的任何结论。
3. **从源码构建**——`python tools/build.py`。注意 PyInstaller 的输出**不是逐字节
   可复现**的（构建时间戳、临时路径、依赖轮子差异都会进产物），所以你自己构建出的
   EXE 哈希**不会**等于发布版的哈希。这不是被篡改的迹象；逐字节比对只在同一次
   构建的产物之间成立。

未签名产物的说明、以及为什么暂不购买代码签名证书，见 [faq.md](faq.md)；
程序记录什么、不记录什么见 [privacy.md](privacy.md)。
