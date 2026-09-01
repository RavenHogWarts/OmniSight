"""对打包产物的冒烟测试（11 文档 §5）。

它防的是两类单元测试完全测不到、却最可能发生的发布事故：

* **打包漏了 ``--add-data``** —— 首页 200 但模板缺失，或静态资源 404。
* **打包后写到了 ``_MEIPASS`` 临时目录** —— 数据"每次重启都清零"，用户报的是
  "统计不准"，而真正原因在打包参数里。

用法::

    python tools/smoke.py dist/OmniSight.exe [--keep]
"""

from __future__ import annotations

import contextlib
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]
STARTUP_TIMEOUT = 30.0
TOKEN_HEADER = "X-OmniSight-Token"

#: 页面外壳必须带的挂载点。模板改了 id 而 JS 没跟着改，症状是整页空白且控制台安静
#: （getElementById 返回 null 不报错），因此这条要在产物上验一次。
SHELL_MARKERS = (
    b'id="view-root"',
    b'id="periodbar"',
    b'id="banners"',
    b'id="toasts"',
    b'id="tab-overview"',
    b'/static/css/app.css',
    b'/static/js/main.js',
    b'/static/js/theme.js',
)

#: 各层抽一个：入口、样式汇总、核心层、领域层、图表层、组件层、视图层、图标。
SHELL_ASSETS = (
    "/static/css/app.css",
    "/static/css/tokens.css",
    "/static/css/components/key-cap.css",
    "/static/js/main.js",
    "/static/js/theme.js",
    "/static/js/core/store.js",
    "/static/js/domain/keyboard-layout.js",
    "/static/js/charts/canvas.js",
    "/static/js/components/keyboard-view.js",
    "/static/js/views/overview.js",
    "/favicon.svg",
)


def _check_shell(body: bytes) -> list[str]:
    """外壳自检：挂载点齐全，且**不含任何统计数据**（06 文档 §14 的模板零数据）。"""
    problems = [f"首页缺少 {marker.decode()}" for marker in SHELL_MARKERS if marker not in body]
    for leak in (b"press_count", b"total_seconds", b"capabilities"):
        if leak in body:
            problems.append(f"首页注入了数据（{leak.decode()}），模板应当零数据")
    return problems


#: 每个端点配一个校验函数：只断言 200 等于放过"返回了 200 但内容是空壳"这类打包事故。
#: M2 起遍历真实接口（M1 的 ``/_debug/attribution`` 已删除）。挑的这几个各有理由：
#: ``overview`` 一次请求横跨三个服务，``keyboard/layout`` 证明布局数据被收进了产物，
#: ``maintenance/integrity`` 是聚合自检的常驻出口。
CHECKED_ENDPOINTS = (
    "/api/v1/status",
    "/api/v1/maintenance/integrity",
    "/api/v1/overview?range=day",
    "/api/v1/keyboard/layout",
    "/api/v1/keyboard/heatmap?range=day",
    "/api/v1/insights/app-keyboard?range=day",
    "/api/v1/settings",
)


def _get(url: str, token: str | None = None, timeout: float = 5.0):
    request = urllib.request.Request(url)
    if token:
        request.add_header(TOKEN_HEADER, token)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read()


def _wait_for_runtime(data_dir: Path, process: subprocess.Popen) -> dict:
    """等 ``runtime.json`` 出现——它同时告诉我们端口与令牌。

    同时盯着进程是否已经退出。少了这一步，"启动即崩"会表现为干等 30 秒后超时，
    而真正有用的信息（退出码、STARTUP_ERROR.txt）反而不会被报出来——这正是本工具
    第一次跑真实产物时踩到的情况。
    """
    deadline = time.monotonic() + STARTUP_TIMEOUT
    runtime_file = data_dir / "runtime.json"
    while time.monotonic() < deadline:
        if runtime_file.exists():
            try:
                return json.loads(runtime_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass  # 正在写，下一轮再读
        code = process.poll()
        if code is not None:
            raise RuntimeError(f"进程已退出（退出码 {code}）{_startup_error_hint(data_dir.parent)}")
        time.sleep(0.25)
    raise TimeoutError(f"{STARTUP_TIMEOUT:.0f} 秒内未出现 {runtime_file}")


def _startup_error_hint(directory: Path) -> str:
    """把 STARTUP_ERROR.txt 的内容带进报错——它是无控制台产物唯一的错误出口。"""
    path = directory / "STARTUP_ERROR.txt"
    if not path.exists():
        return "；未找到 STARTUP_ERROR.txt"
    body = path.read_text(encoding="utf-8").strip()
    return f"；STARTUP_ERROR.txt 内容：\n{body}"


def _check_payload(endpoint: str, data: dict) -> list[str]:
    """逐端点的内容校验。

    ``/api/v1/status`` 里的 ``capture`` 段是**打包产物唯一**能证明 M1 采集真的起来了的
    地方：Raw Input 要注册窗口类、pynput 兜底要能被 PyInstaller 收进去，这两件事在
    开发模式下都正常，冻结后却可能双双失败——而症状只是"图表永远是 0"。
    """
    problems: list[str] = []
    if endpoint == "/api/v1/status":
        if data.get("degraded") is None:
            problems.append(f"{endpoint} 缺少 degraded 字段")
        capture = data.get("capture") or {}
        if not capture.get("keyboard", {}).get("running"):
            problems.append("打包产物里键盘采集没起来（后端注册失败或依赖未收进产物）")
        if not capture.get("foreground", {}).get("running"):
            problems.append("打包产物里前台监控没起来")
        if data.get("capabilities", {}).get("keyboard_backend") == "none":
            problems.append("有效能力里键盘后端是 none——采集实际未生效")
    elif endpoint == "/api/v1/maintenance/integrity":
        if not data.get("match"):
            problems.append(f"聚合自检不一致：{data.get('aggregates')}")
        if len(data.get("aggregates") or {}) < 8:
            problems.append("自检覆盖的聚合表少于 8 张——新表漏进了核对清单？")
    elif endpoint.startswith("/api/v1/overview"):
        for section in ("screen_time", "keyboard", "top_apps", "trend", "highlights"):
            if section not in data:
                problems.append(f"概览缺少 {section} 段")
        if len(data.get("trend", {}).get("buckets") or []) != 24:
            problems.append("概览的日趋势不是 24 个桶")
    elif endpoint == "/api/v1/keyboard/layout":
        rows = data.get("rows") or []
        if len(rows) != 6:
            problems.append("键盘布局不是 6 行（布局数据没被收进产物？）")
        if sum(1 for row in rows for slot in row if slot.get("id") != "gap") != 104:
            problems.append("ANSI104 布局的键数不对")
    elif endpoint.startswith("/api/v1/keyboard/heatmap"):
        if len(data.get("keys") or []) != 104:
            problems.append("热力图没有覆盖全部键位")
    elif endpoint.startswith("/api/v1/insights/app-keyboard"):
        if "unattributed_presses" not in data:
            problems.append("洞察接口缺少 unattributed_presses（总量守恒无法验证）")
    elif endpoint == "/api/v1/settings":
        if "privacy.record_window_titles" not in (data.get("settings") or {}):
            problems.append("设置接口缺少隐私开关")
    return problems


def run(executable: Path, *, keep: bool = False) -> int:
    if not executable.exists():
        print(f"找不到产物：{executable}", file=sys.stderr)
        return 2

    # 便携模式：产物同级放 portable.marker，数据落在 dist/data，便于检查与清理。
    # 构建脚本本来就会写这个文件，因此只清理"我们自己创建的"那一份。
    marker = executable.parent / "portable.marker"
    marker_was_ours = not marker.exists()
    marker.touch()
    data_dir = executable.parent / "data"

    process = subprocess.Popen([str(executable)], cwd=executable.parent)
    failures: list[str] = []
    try:
        runtime = _wait_for_runtime(data_dir, process)
        base = f"http://127.0.0.1:{runtime['port']}/"
        token = runtime["token"]

        status_code, body = _get(urljoin(base, "/"), token)
        if status_code != 200 or b"OmniSight" not in body:
            failures.append("首页未正常返回（可能漏了 --add-data 的模板）")
        failures.extend(_check_shell(body))
        # M3 起前端是 39 个 ES 模块 + 26 个样式文件。逐个校验太慢，抽查入口与
        # 每一层各一个：`--add-data` 收的是整棵目录树，漏就是整层都漏。
        for asset in SHELL_ASSETS:
            code, _ = _get(urljoin(base, asset))
            if code != 200:
                failures.append(f"静态资源 404：{asset}（--add-data 未收进 static/）")

        for endpoint in CHECKED_ENDPOINTS:
            code, payload = _get(urljoin(base, endpoint), token)
            if code != 200:
                failures.append(f"{endpoint} 返回 {code}")
                continue
            failures.extend(_check_payload(endpoint, json.loads(payload)))

        failures.extend(_check_stream(base, token))

        # 无令牌必须被拒——这条防的是"某次重构把令牌校验绕过了"。
        try:
            _get(urljoin(base, "/api/v1/status"))
            failures.append("无令牌也能读取 /api/v1/status")
        except urllib.error.HTTPError as exc:
            if exc.code != 401:
                failures.append(f"无令牌访问应返回 401，实际 {exc.code}")

        database = data_dir / "omnisight.db"
        if not database.exists():
            failures.append(f"数据库未创建在 {database}（可能写进了 _MEIPASS 临时目录）")
    except Exception as exc:
        failures.append(f"冒烟过程异常：{exc}")
    finally:
        failures.extend(_terminate_tree(process))
        if not keep:
            if marker_was_ours:
                marker.unlink(missing_ok=True)
            _cleanup(executable.parent)

    if failures:
        print("冒烟测试失败：", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print("冒烟测试通过")
    return 0


def _check_stream(base: str, token: str) -> list[str]:
    """SSE 在冻结产物里是否真的能推。

    只读第一行就断开：那一行是连接确认（``: connected``），拿到它就说明响应头、
    ``text/event-stream`` 与生成器都活着。**不能整段读**——这是一条永不结束的流。
    """
    request = urllib.request.Request(urljoin(base, "/api/v1/stream"))
    request.add_header(TOKEN_HEADER, token)
    try:
        with urllib.request.urlopen(request, timeout=5.0) as response:
            content_type = response.headers.get("Content-Type", "")
            first = response.readline()
    except Exception as exc:
        return [f"SSE 端点不可用：{exc}"]
    problems: list[str] = []
    if "text/event-stream" not in content_type:
        problems.append(f"SSE 的 Content-Type 是 {content_type!r}")
    if not first.startswith(b":"):
        problems.append(f"SSE 首帧不是连接确认：{first!r}")
    return problems


def _terminate_tree(process: subprocess.Popen) -> list[str]:
    """结束整棵进程树，并确认真的没有残留。

    PyInstaller 的 onefile 产物是一个**引导器**：它解压后再启动真正的应用进程。
    只 ``terminate()`` 直接子进程会让引导器退出、应用继续运行——表现为"退出了但
    数据库还被占着"，而且单实例互斥锁仍被持有，下一次启动会被自己挡住。
    第一次跑本工具时就是这样留下了四个孤儿进程。
    """
    import psutil

    failures: list[str] = []
    try:
        root = psutil.Process(process.pid)
    except psutil.NoSuchProcess:
        return failures

    family = [*root.children(recursive=True), root]
    for victim in family:
        try:
            victim.terminate()
        except psutil.NoSuchProcess:
            continue
    _, alive = psutil.wait_procs(family, timeout=10)
    if alive:
        failures.append(f"发送终止信号后 10 秒内仍有 {len(alive)} 个进程存活")
        for victim in alive:
            with contextlib.suppress(psutil.NoSuchProcess):
                victim.kill()
        psutil.wait_procs(alive, timeout=5)
    return failures


def _cleanup(directory: Path, attempts: int = 5) -> None:
    """清掉冒烟过程产生的运行数据。

    CI 会把 ``dist/`` 整个上传为发布物，留着这些文件等于把一份测试数据库发出去。

    需要重试：刚被终止的进程在 Windows 上会短暂保留 WAL/日志的文件句柄，
    第一次删除通常失败。
    """
    for attempt in range(attempts):
        shutil.rmtree(directory / "data", ignore_errors=True)
        shutil.rmtree(directory / "logs", ignore_errors=True)
        for name in ("config.json", "STARTUP_ERROR.txt"):
            with contextlib.suppress(OSError):
                (directory / name).unlink(missing_ok=True)
        if not (directory / "data").exists() and not (directory / "logs").exists():
            return
        time.sleep(0.5 * (attempt + 1))
    print("提示：冒烟数据未能完全清理，请手动删除 dist/data 与 dist/logs")


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    positional = [arg for arg in argv if not arg.startswith("--")]
    target = Path(positional[0]) if positional else ROOT / "dist" / "OmniSight.exe"
    return run(target, keep="--keep" in argv)


if __name__ == "__main__":
    sys.exit(main())
