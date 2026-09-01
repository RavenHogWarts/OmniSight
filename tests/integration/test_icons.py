"""图标解析与磁盘缓存（04 文档 §6、12 文档 M2 的"第二次请求命中磁盘缓存"判据）。

改的是现状的三个问题：

1. **首次请求在 Flask 请求线程里遍历注册表**，可能耗时数百毫秒到数秒，仪表盘首屏被图标
   拖慢。现在请求线程只做一次主键点查。
2. **结果不持久化**，每次重启都要重走一遍。现在落在 ``app_icon`` 表。
3. **失败被永久缓存为 ``b""``**，于是用户装好某个程序后图标永远不出现。现在失败可在
   7 天后重试。

用平台无关的假 ``IconSource`` 测这三件事——它们全部发生在服务层与存储层，与 Win32 无关。
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from omnisight.presentation.web import create_app
from omnisight.storage.repositories.apps import ICON_RETRY_DAYS, AppDirectory, icon_is_stale
from seeded import NOW

PNG = b"\x89PNG\r\n\x1a\nfake"


class FakeIconSource:
    """记录调用次数——"第二次请求不再调平台 API"就是靠它断言的。"""

    def __init__(self, png: bytes | None = PNG) -> None:
        self.png = png
        self.calls: list[str] = []

    def icon_png(self, identity, size: int) -> bytes | None:
        self.calls.append(identity.app_key)
        return self.png


class ExplodingIconSource:
    def icon_png(self, identity, size: int):
        raise OSError("模拟一次平台调用失败")


@pytest.fixture
def icon_client(api_context, seeded):
    """带假图标源的客户端。``adapters`` 是一个鸭子类型的持有者，给它一个属性就够了。"""
    source = FakeIconSource()

    class Adapters:
        icons = source

    api_context.services.context.adapters = Adapters()
    app = create_app(api_context)
    app.config.update(TESTING=True)
    client = app.test_client()
    client.environ_base["HTTP_X_OMNISIGHT_TOKEN"] = "test-token-value"
    return client, source


def test_first_request_resolves_and_second_hits_the_disk_cache(icon_client, seeded):
    client, source = icon_client
    first = client.get(f"/api/v1/apps/{seeded.code}/icon")
    assert first.status_code == 200
    assert first.data == PNG
    assert first.mimetype == "image/png"
    assert source.calls == ["code.exe"]

    second = client.get(f"/api/v1/apps/{seeded.code}/icon")
    assert second.data == PNG
    assert source.calls == ["code.exe"], "第二次请求又调了一次平台 API"


def test_the_cache_survives_a_restart(icon_client, seeded, api_context, database):
    """结果落在 ``app_icon`` 表里。重启后重来一遍等于每次开机都卡首屏。"""
    client, _source = icon_client
    client.get(f"/api/v1/apps/{seeded.code}/icon")

    # 换一个全新的服务层实例（相当于重启），但用同一个库。
    fresh = AppDirectory(database)
    entry = fresh.icon(seeded.code)
    assert entry is not None
    assert bytes(entry["png"]) == PNG
    assert entry["resolved_at"]
    assert entry["failed_at"] is None


def test_no_icon_is_204_and_is_remembered_as_a_failure(api_context, seeded):
    """204 而不是 404：应用存在，只是没图标。而"没图标"这个结论也要记下来。"""
    class Adapters:
        icons = FakeIconSource(png=None)

    api_context.services.context.adapters = Adapters()
    client = create_app(api_context).test_client()
    client.environ_base["HTTP_X_OMNISIGHT_TOKEN"] = "test-token-value"
    assert client.get(f"/api/v1/apps/{seeded.code}/icon").status_code == 204

    entry = api_context.services.context.app_repo.icon(seeded.code)
    assert entry["png"] is None
    assert entry["failed_at"], "失败必须记时间，否则无法实现 7 天后重试"


def test_a_platform_failure_does_not_500(api_context, seeded):
    """图标是装饰。为它让整个请求失败是不值当的。"""
    class Adapters:
        icons = ExplodingIconSource()

    api_context.services.context.adapters = Adapters()
    client = create_app(api_context).test_client()
    client.environ_base["HTTP_X_OMNISIGHT_TOKEN"] = "test-token-value"
    assert client.get(f"/api/v1/apps/{seeded.code}/icon").status_code == 204


def test_a_missing_icon_is_retried_after_the_retry_window(icon_client, seeded, api_context):
    """现状把失败永久缓存，于是装好程序后图标永远不出现（除非重启进程）。"""
    repo = api_context.services.context.app_repo
    repo.store_icon(seeded.code, None, size=32, source_path="", now=NOW)
    entry = repo.icon(seeded.code)
    assert icon_is_stale(entry, now=NOW) is False
    assert icon_is_stale(entry, now=NOW + timedelta(days=ICON_RETRY_DAYS - 1)) is False
    assert icon_is_stale(entry, now=NOW + timedelta(days=ICON_RETRY_DAYS)) is True


def test_a_successful_icon_is_never_re_resolved(seeded, api_context):
    repo = api_context.services.context.app_repo
    repo.store_icon(seeded.code, PNG, size=32, source_path="", now=NOW)
    entry = repo.icon(seeded.code)
    assert icon_is_stale(entry, now=NOW + timedelta(days=365)) is False


def test_clearing_the_cache_resets_every_icon_state(seeded, api_context):
    repo = api_context.services.context.app_repo
    repo.store_icon(seeded.code, PNG, size=32, source_path="", now=NOW)
    repo.store_icon(seeded.chrome, None, size=32, source_path="", now=NOW)
    assert repo.clear_icons() == 2
    assert repo.icon(seeded.code) is None
    assert {meta.icon_state for meta in repo.all_meta().values()} == {"unknown"}


def test_the_unknown_sentinel_never_gets_an_icon(icon_client):
    """``app_id = 0`` 不是应用。为它去解析图标是一次注定失败的注册表遍历。"""
    client, source = icon_client
    assert client.get("/api/v1/apps/0/icon").status_code == 404
    assert source.calls == []


@pytest.mark.windows_only
def test_the_real_windows_source_produces_a_transparent_png():
    """真机验证：现状把图标画到白色画刷上，深色主题下每个图标都带一个白框。"""
    import shutil

    from omnisight.adapters.ports import AppIdentity
    from omnisight.adapters.windows.icons import WindowsIconSource, available

    assert available()
    exe = shutil.which("notepad.exe") or r"C:\Windows\System32\notepad.exe"
    png = WindowsIconSource().icon_png(
        AppIdentity(
            app_key="notepad.exe", identity_kind="process", display_name="记事本",
            process_name="notepad.exe", exe_path=exe,
        ),
        32,
    )
    assert png and png.startswith(b"\x89PNG")

    from io import BytesIO

    from PIL import Image

    image = Image.open(BytesIO(png))
    assert image.mode == "RGBA"
    assert image.size == (32, 32)
    assert image.getchannel("A").getextrema()[0] == 0, "透明像素被填成了不透明"


@pytest.mark.windows_only
def test_the_real_source_returns_none_for_an_unknown_process():
    from omnisight.adapters.ports import AppIdentity
    from omnisight.adapters.windows.icons import WindowsIconSource

    identity = AppIdentity(
        app_key="definitely-not-installed-xyz.exe", identity_kind="process",
        display_name="x", process_name="definitely-not-installed-xyz.exe", exe_path="",
    )
    assert WindowsIconSource().icon_png(identity, 32) is None
