"""E11 S12-8, S12-9, S12-13: the toy3d runtime refuses anything but the pinned browser build on an
allow-listed GPU backend, and every page failure reaches `Toy3DRenderError` (no hang, no fallback)."""
import base64
from contextlib import contextmanager

import pytest
from playwright.sync_api import Error as PlaywrightError

METAL = "ANGLE (Apple, ANGLE Metal Renderer: Apple M3 Pro, Unspecified Version)"
HUB_GLES = "ANGLE (NVIDIA Corporation, NVIDIA GeForce GTX 1050/PCIe/SSE2, OpenGL ES 3.2)"
SWIFTSHADER = "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)"
NVIDIA_VULKAN = "ANGLE (NVIDIA, Vulkan 1.4.312 (NVIDIA NVIDIA GeForce GTX 1050 (0x00001C81)), NVIDIA)"
LLVMPIPE = "ANGLE (Mesa, llvmpipe (LLVM 17.0.6, 256 bits), OpenGL ES 3.2)"


@pytest.mark.parametrize(("platform", "renderer"), [("darwin", METAL), ("linux", HUB_GLES)])
def test_backend_allow_list_passes_the_two_machines(platform, renderer):
    from toy3d.runtime import check_renderer

    assert check_renderer(renderer, platform) == renderer


@pytest.mark.parametrize(("platform", "renderer"), [
    ("darwin", SWIFTSHADER), ("darwin", "Apple M3 Pro"), ("darwin", ""),
    ("linux", SWIFTSHADER), ("linux", NVIDIA_VULKAN), ("linux", LLVMPIPE), ("linux", "NVIDIA GeForce GTX 1050"),
    ("win32", METAL)])
def test_backend_allow_list_refuses_swiftshader_vulkan_and_unknown(platform, renderer):
    from toy3d.runtime import Toy3DRenderError, check_renderer

    with pytest.raises(Toy3DRenderError) as e:
        check_renderer(renderer, platform)
    assert repr(renderer) in str(e.value)
    assert "toy3d renders on" in str(e.value)        # says what it needs, never falls back


def test_each_platform_launches_its_angle_backend():
    from toy3d.runtime import launch_args

    assert launch_args("darwin") == ["--use-angle=metal", "--ignore-gpu-blocklist"]
    assert launch_args("linux") == ["--use-angle=gl-egl", "--ignore-gpu-blocklist"]


class _NoLaunch:
    def __init__(self, executable, version="151.0.7922.34"):
        self.executable_path = str(executable)
        self.version = version
        self.launched = []

    def launch(self, **kw):
        self.launched.append(kw)
        return _FakeBrowser(self.version)


class _FakeBrowser:
    def __init__(self, version):
        self.version = version
        self.closed = False

    def new_page(self, **kw):
        raise AssertionError("a refused build must not get a page")

    def close(self):
        self.closed = True


def _fake_playwright(monkeypatch, chromium):
    from toy3d import runtime

    @contextmanager
    def fake():
        class P:
            pass
        p = P()
        p.chromium = chromium
        yield p
    monkeypatch.setattr(runtime, "sync_playwright", fake)


def test_missing_build_names_the_install_command(tmp_path, monkeypatch):
    from toy3d import runtime

    chromium = _NoLaunch(tmp_path / "chromium-1234" / "chrome")    # playwright's cache wiped
    _fake_playwright(monkeypatch, chromium)
    with pytest.raises(runtime.Toy3DRenderError) as e, runtime.open_page(64, 36, "render"):
        pass
    msg = str(e.value)
    assert "uv run playwright install chromium" in msg
    assert runtime.BROWSER_VERSION in msg and str(tmp_path / "chromium-1234" / "chrome") in msg
    assert chromium.launched == []                                   # no system-Chrome fallback


def test_a_different_browser_build_is_refused(tmp_path, monkeypatch):
    from toy3d import runtime

    exe = tmp_path / "chrome"
    exe.write_text("")
    chromium = _NoLaunch(exe, version="150.0.7871.0")
    _fake_playwright(monkeypatch, chromium)
    with pytest.raises(runtime.Toy3DRenderError) as e, runtime.open_page(64, 36, "render"):
        pass
    assert "150.0.7871.0" in str(e.value) and runtime.BROWSER_VERSION in str(e.value)
    assert chromium.launched and chromium.launched[0]["executable_path"] == str(exe)


class _StubPage:
    """A Playwright page that answers `evaluate` from a script."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.waits = 0

    def evaluate(self, expr, arg=None):
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(a, Exception):
            raise a
        return a(arg) if callable(a) else a

    def wait_for_timeout(self, ms):
        self.waits += 1


def test_page_error_reaches_the_render_error():
    from toy3d.runtime import PlaywrightPage, Toy3DRenderError

    stub = _StubPage([PlaywrightError(
        "Page.evaluate: Error: toy3d init: palette.fur.base: not a colour 'nope'\n    at init (engine/core.js:12:9)")])
    with pytest.raises(Toy3DRenderError) as e:
        PlaywrightPage(stub, []).init({"style": {}}, 64, 36, "render")
    assert str(e.value) == "toy3d page: init failed: toy3d init: palette.fur.base: not a colour 'nope'"


def test_a_page_that_fails_to_load_is_reported_at_once_not_after_the_timeout():
    from toy3d.runtime import Toy3DRenderError, wait_ready

    errors = []
    stub = _StubPage([False])
    original = stub.wait_for_timeout

    def tick(ms):
        original(ms)
        if stub.waits == 2:
            errors.append("404 http://toy3d.local/engine/world.js")
        if stub.waits > 5:
            raise AssertionError("still waiting after the page reported an error")
    stub.wait_for_timeout = tick
    with pytest.raises(Toy3DRenderError) as e:
        wait_ready(stub, errors, timeout=600.0)
    assert "engine/world.js" in str(e.value)
    assert stub.waits == 2


def test_a_page_that_never_gets_ready_times_out_loudly():
    from toy3d.runtime import Toy3DRenderError, wait_ready

    with pytest.raises(Toy3DRenderError, match="not ready"):
        wait_ready(_StubPage([False]), [], timeout=0.0)


def test_render_state_decodes_the_png_data_url():
    from toy3d.runtime import PlaywrightPage, Toy3DRenderError

    png = b"\x89PNG\r\n\x1a\nfake"
    url = "data:image/png;base64," + base64.b64encode(png).decode()
    assert PlaywrightPage(_StubPage([url]), []).render_state({"frame": 0}) == png
    with pytest.raises(Toy3DRenderError, match="not a PNG data URL"):
        PlaywrightPage(_StubPage(["data:image/jpeg;base64,AAAA"]), []).render_state({"frame": 0})


def test_info_names_the_browser_build_the_page_cannot_see():
    """The page's user agent is reduced (Chrome/151.0.0.0); the build comes from the browser."""
    from toy3d.runtime import PlaywrightPage

    page = PlaywrightPage(_StubPage([{"renderer": "ANGLE Metal Renderer", "mode": "render"}]), [], build="151.0.7922.34")
    assert page.info() == {"renderer": "ANGLE Metal Renderer", "mode": "render", "build": "151.0.7922.34"}


def test_evaluate_reports_page_errors_like_every_call():
    from toy3d.runtime import PlaywrightPage, Toy3DRenderError

    assert PlaywrightPage(_StubPage([7]), [], build="x").evaluate("() => 7") == 7
    with pytest.raises(Toy3DRenderError, match="evaluate failed: boom"):
        PlaywrightPage(_StubPage([PlaywrightError("Page.evaluate: Error: boom")]), [], build="x").evaluate("() => 1")
