r"""开发期的"改完自己刷新"：一个 vite watch 子进程 + 一段注入页面的轮询脚本。

**为什么不是 Vite 的 dev server 与 HMR**：CSP 是 ``script-src 'self'``（08 文档 §3），
而 HMR 要连另一个源的 websocket 并注入内联脚本，两条都撞。放宽 CSP 换一次省下的刷新
不值——那条头是生产与开发共用的单一真相（15 文档 §3.3）。所以这里是最笨、也最不侵入
生产代码的形状：Flask 照旧托 ``static/dist``，vite 照旧 ``build --watch`` 往那里写，
页面自己看一眼产物变没变，变了就 ``location.reload()``。

三个细节值得写下来，它们各自对应一种坏法：

1. **判据是 ``manifest.json`` 的内容哈希，不是 mtime。** vite 每次重建都重写全部产物，
   mtime 必然变；而产物文件名本身就是内容哈希，所以内容没变时清单逐字节相同。用 mtime
   会让"保存了但什么都没改"（只动了注释、编辑器多存一次）也刷新一遍，而刷新会丢掉当前
   视图与滚动位置——那正是自动刷新本来要省下的事。
2. **清单变了不等于产物齐了。** 一次重建里清单与各个 chunk 的落盘顺序没有保证：先看到
   新清单、再去请求还没写完的 chunk，结果是白屏。所以 :func:`bundle_stamp` 只在清单引用
   的每个文件都在盘上时才算 ready，其余时候如实上报"没准备好"，由客户端继续等。
3. **短轮询，不是长轮询也不是 SSE。** 长轮询会在关页面时留下一条被中断的请求，而
   ``tools/page.mjs`` 的 ``requestfailed`` 清单会把它记成失败——一个每次都在的假警报比
   没有清单更糟（``devserver.py`` 关掉 SSE 是同一个理由）。短轮询每次都完成，一秒一次、
   一次两百字节，在本机上不算开销。
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import quote

from flask import Flask, Response, request

#: 轮询间隔（毫秒）：小到"感觉是即时的"，大到不在网络面板里刷屏。
POLL_INTERVAL_MS = 1000

#: 都挂在 ``/__dev/`` 下，一眼看得出不属于生产的接口面。
STAMP_ROUTE = "/__dev/bundle-stamp"
SCRIPT_ROUTE = "/__dev/live.js"

def bundle_stamp(dist: Path) -> tuple[str, bool]:
    """返回 ``(戳, 产物是否齐全)``。

    戳是 ``manifest.json`` 的内容哈希——见模块文档第 1 条。第二个值为假时客户端必须
    继续等：那说明这一轮重建还在落盘（第 2 条）。
    """
    try:
        raw = (dist / "manifest.json").read_bytes()
    except OSError:
        # 还没构建过（新检出且没跑 pnpm build）。给一个稳定的戳，第一次构建完成时它会
        # 变成真的哈希，页面于是从"产物缺失"那张卡自己刷成仪表盘。
        return "no-manifest", False
    stamp = hashlib.sha1(raw, usedforsecurity=False).hexdigest()[:12]
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError:
        return stamp, False  # 正被写到一半
    if not isinstance(entries, dict):  # pragma: no cover - 清单结构变了才会走到
        return stamp, False
    for entry in entries.values():
        if not isinstance(entry, dict):
            continue
        for name in (entry.get("file"), *(entry.get("css") or ())):
            if isinstance(name, str) and not (dist / name).exists():
                return stamp, False
    return stamp, True


def install(app: Flask, *, token: str) -> None:
    """挂上两个 ``/__dev/`` 路由，并把那段脚本注入页面外壳。

    **令牌走查询串**：``<script src>`` 发不出自定义头（favicon 免令牌是同一个坑，见
    ``web.py:favicon``），而 ``security.py:_require_token`` 本来就同时认 ``?token=``，
    于是这里不必碰 ``PUBLIC_ENDPOINTS``——生产的免令牌清单一字未动。

    注入而不是改模板：``templates/dashboard.html`` 是生产的页面外壳，开发期的东西不该
    出现在它里面（哪怕包在 ``{% if %}`` 里——那会多一个只有开发服务器才会走的分支）。
    """
    dist = Path(app.static_folder or ".") / "dist"
    tag = f'<script src="{SCRIPT_ROUTE}?token={quote(token)}"></script>'

    @app.get(STAMP_ROUTE)
    def _dev_bundle_stamp():
        stamp, ready = bundle_stamp(dist)
        return {"stamp": stamp, "ready": ready}

    @app.get(SCRIPT_ROUTE)
    def _dev_live_script():
        stamp, _ = bundle_stamp(dist)
        script = (
            _SCRIPT.replace("__STAMP__", stamp)
            .replace("__URL__", f"{STAMP_ROUTE}?token={quote(token)}")
            .replace("__INTERVAL__", str(POLL_INTERVAL_MS))
        )
        return Response(script, mimetype="text/javascript")

    @app.after_request
    def _inject_live_script(response):
        # 三个页面外壳都要注入（18 文档 批 1）：改设置页的样式时也该自动刷新，否则那一页
        # 会安静地停在上一次构建上，而"改了没生效"是这条工具存在的全部理由。
        if request.path not in ("/", "/settings", "/about") or response.mimetype != "text/html":
            return response
        html = response.get_data(as_text=True)
        if "</body>" not in html:  # pragma: no cover - 模板结构变了才会走到
            return response
        # 用 set_data 而不是拼字节：它顺手改掉 Content-Length，不改就是一个截断的页面。
        response.set_data(html.replace("</body>", f"{tag}</body>", 1))
        return response


#: 注入的脚本。**普通脚本而不是模块**：``dist`` 整个缺失时模块图是坏的，而这段恰恰要在
#: 那时候也能跑（它就是把页面从"产物缺失"救回来的东西）。语法刻意保守——它不过 esbuild，
#: 就是原样发出去的字符串，浏览器基线是 Safari 15.4（07 文档 §2）。
_SCRIPT = """\
// 由 tools/_devlive.py 注入，只存在于开发服务器；生产页面里没有这段。
(function () {
  var stamp = "__STAMP__";
  var url = "__URL__";
  var backoff = 0;

  function poll() {
    fetch(url, { cache: "no-store" })
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(function (data) {
        backoff = 0;
        // ready 为假：这一轮重建还没落全盘，继续等，别刷成白屏。
        if (data.ready && data.stamp !== stamp) {
          console.info("[devserver] 前端产物已更新，正在刷新页面");
          window.location.reload();
          return;
        }
        window.setTimeout(poll, __INTERVAL__);
      })
      .catch(function () {
        // 开发服务器重启中会连不上：退避到 5 秒，回来后照常比对。
        backoff = Math.min(backoff + 1, 5);
        window.setTimeout(poll, backoff * 1000);
      });
  }

  window.setTimeout(poll, __INTERVAL__);
})();
"""


def start_vite_watch(root: Path, *, quiet: bool = False) -> subprocess.Popen[str]:
    """在本进程下起 ``vite build --watch``，输出加 ``[vite]`` 前缀转发出来。

    **直接 spawn node，不走 ``pnpm dev``**：Windows 上 pnpm 是个 ``.CMD`` 包装，
    ``terminate()`` 打在包装上不会带走它底下的 node，于是退出后留一个还在往 ``dist`` 里
    写的孤儿——下次启动就撞上"产物一直在变、页面反复自己刷新"。spawn 到 node 本身则一刀
    两断（esbuild 的服务进程靠 stdin 关闭自行退出，不需要额外收拾）。
    """
    node = shutil.which("node")
    if node is None:
        raise SystemExit("--watch 需要 Node：`node` 不在 PATH 上。去掉 --watch，或装 Node 22+。")
    cli = root / "node_modules" / "vite" / "bin" / "vite.js"
    if not cli.exists():
        raise SystemExit(f"找不到 {cli}，先跑一次 `pnpm install`。")
    process = subprocess.Popen(
        [node, str(cli), "build", "--watch"],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    threading.Thread(
        target=_forward_output, args=(process, quiet), name="vite-output", daemon=True
    ).start()
    _tie_lifetime_to_parent(process, quiet=quiet)
    return process


#: Job 句柄要活到本进程结束：**它一关，job 里的进程立刻被杀**，所以不能是局部变量。
_JOB_HANDLE: int | None = None

_JOB_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_EXTENDED_LIMIT_INFORMATION = 9


# JOBOBJECT_EXTENDED_LIMIT_INFORMATION（winnt.h）。字段一个都不能少也不能换顺序：
# SetInformationJobObject 按大小与偏移读它，错一个字节就是静默失效或 ERROR_INVALID_PARAMETER。
# 这里只用 LimitFlags 一个字段，其余留零。
class _JobObjectBasicLimit(ctypes.Structure):
    _fields_ = (
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    )


class _IoCounters(ctypes.Structure):
    _fields_ = tuple(
        (name, ctypes.c_uint64)
        for name in (
            "ReadOperationCount",
            "WriteOperationCount",
            "OtherOperationCount",
            "ReadTransferCount",
            "WriteTransferCount",
            "OtherTransferCount",
        )
    )


class _JobObjectExtendedLimit(ctypes.Structure):
    _fields_ = (
        ("BasicLimitInformation", _JobObjectBasicLimit),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    )


def _tie_lifetime_to_parent(process: subprocess.Popen[str], *, quiet: bool) -> None:
    """把子进程绑进一个 Windows Job Object，本进程一死它跟着死。

    **为什么 ``finally`` 里的 :func:`stop_vite_watch` 不够**：那条路只在正常退出时走到。
    Ctrl+C 会走，而关掉终端窗口、任务管理器结束进程、``taskkill /F`` 都不会——那时留下的
    是一个还在往 ``dist`` 里写的 vite。它的后果不止"多一个进程"：下次启动的 watch 会与它
    交错写同一批文件，症状是页面反复自己刷新、产物时好时坏，而两个 watch 谁都不在前台，
    没人会想到去看进程列表。``KILL_ON_JOB_CLOSE`` 让操作系统替我们兜住这一条。

    失败只警告不抛：拿不到 job 也照样能开发，只是退出时要靠上面那条正常路径。
    非 Windows 上直接跳过——这个工具目前只在 Windows 上跑（13 文档 §4.1）。
    """
    global _JOB_HANDLE
    if sys.platform != "win32" or _JOB_HANDLE is not None:
        return
    sink = sys.stderr if quiet else sys.stdout
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        # 显式声明 restype/argtypes：HANDLE 在 64 位上超过 2^31，按默认的 int 会被截断。
        kernel32.CreateJobObjectW.restype = ctypes.c_void_p
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        kernel32.SetInformationJobObject.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32
        ]
        kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW 失败")
        limits = _JobObjectExtendedLimit()
        limits.BasicLimitInformation.LimitFlags = _JOB_LIMIT_KILL_ON_JOB_CLOSE
        assigned = kernel32.SetInformationJobObject(
            job, _JOB_EXTENDED_LIMIT_INFORMATION, ctypes.byref(limits), ctypes.sizeof(limits)
        ) and kernel32.AssignProcessToJobObject(job, int(process._handle))
        if not assigned:
            error = ctypes.get_last_error()
            kernel32.CloseHandle(job)
            raise OSError(error, "AssignProcessToJobObject 失败")
        _JOB_HANDLE = job
    except (OSError, AttributeError) as error:  # pragma: no cover - 取决于系统
        print(f"[vite] 无法绑定进程生命周期（{error}）：异常退出时可能留下孤儿进程", file=sink)


def _forward_output(process: subprocess.Popen[str], quiet: bool) -> None:
    """把 vite 的输出转发出来——构建报错就在这些行里，吞掉它等于调试时瞎着一只眼。"""
    stream = process.stdout
    if stream is None:  # pragma: no cover - 上面固定给了 PIPE
        return
    # quiet 模式下 stdout 只许有那一行 URL（tools/page.py 读它），所以改走 stderr。
    sink = sys.stderr if quiet else sys.stdout
    for line in stream:
        text = line.rstrip()
        if text:
            print(f"[vite] {text}", file=sink, flush=True)
    code = process.wait()
    if code:
        print(f"[vite] 退出，返回码 {code}——前端不再自动重建", file=sink, flush=True)


def stop_vite_watch(process: subprocess.Popen[str] | None) -> None:
    """跟着开发服务器一起停。留着不管的后果见 :func:`start_vite_watch` 的文档。"""
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:  # pragma: no cover
        process.kill()


__all__ = ["bundle_stamp", "install", "start_vite_watch", "stop_vite_watch"]



