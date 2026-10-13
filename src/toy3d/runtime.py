"""The toy3d browser runtime (E11): the pinned Chrome for Testing build on an allow-listed GPU
backend, serving `web/` to the page, and the page's API (`window.toy3d`) as a Python `Page`.

There is no fallback: a missing build, a different build, a software or Vulkan backend, a page that
fails to load or throws all raise `Toy3DRenderError` naming what to do.
"""
from __future__ import annotations

import base64
import contextlib
import itertools
import json
import mimetypes
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

PLAYWRIGHT_VERSION = "1.62.0"
BROWSER_VERSION = "151.0.7922.34"        # chromium-1234: Chrome for Testing as playwright 1.62.0 pins it
INSTALL_HINT = "uv run playwright install chromium"
WEB_ROOT = Path(__file__).parent / "web"
ORIGIN = "http://toy3d.local"
READY_TIMEOUT = 60.0                     # seconds for stage.html and the engine modules to load
CALL_TIMEOUT = 120.0                     # seconds for one page call (init builds the world, shaders included);
                                         # past it a watchdog stops the browser: evaluate has no timeout

# The GPU backends toy3d renders on: the Mac's Metal, the hub's NVIDIA through OpenGL ES (EGL).
# Software (SwiftShader, llvmpipe) and Vulkan are refused: they draw differently, or not at all.
_ALLOWED = {"darwin": re.compile(r"ANGLE Metal Renderer"), "linux": re.compile(r"OpenGL ES")}
_REFUSED = re.compile(r"Vulkan|SwiftShader|llvmpipe", re.IGNORECASE)
_ANGLE = {"darwin": "metal", "linux": "gl-egl"}
PLATFORM = sys.platform
_PREFIX = re.compile(r"^(?:\w+\.\w+: )?(?:\w*Error: )?")


class Toy3DRenderError(RuntimeError):
    pass


class Page(Protocol):
    """The page API: build the world from the bank once, then pose it per frame spec."""

    def init(self, bank: dict[str, Any], width: int, height: int, mode: str) -> None: ...

    def info(self) -> dict[str, Any]: ...

    def apply_state(self, spec: dict[str, Any]) -> dict[str, Any]: ...

    def render_state(self, spec: dict[str, Any]) -> bytes: ...


def launch_args(platform: str | None = None) -> list[str]:
    return [f"--use-angle={_ANGLE.get(platform or PLATFORM, 'default')}", "--ignore-gpu-blocklist"]


def check_renderer(renderer: str, platform: str | None = None) -> str:
    """The WebGL renderer string, if toy3d renders on it here; else a loud refusal."""
    platform = platform or PLATFORM
    allowed = _ALLOWED.get(platform)
    if allowed is None or not allowed.search(renderer) or _REFUSED.search(renderer):
        need = {"darwin": "ANGLE Metal", "linux": "an OpenGL ES GPU (ANGLE gl-egl)"}.get(
            platform, "macOS (Metal) or Linux (OpenGL ES) only")
        raise Toy3DRenderError(
            f"toy3d renders on {need}, but this browser's WebGL renderer is {renderer!r} "
            f"(software and Vulkan backends draw differently); check the GPU driver, then "
            f"`uv run pipeline doctor`")
    return renderer


def cache_dir() -> Path:
    env = os.environ.get("TOY3D_CACHE_DIR")
    return Path(env) if env else Path.home() / ".cache" / "content-creation" / "toy3d"


def renderer_record_path() -> Path:
    """This machine's last seen browser build and renderer string, rewritten at every launch: the
    clip cache key reads it, so a cache hit never launches a browser."""
    return cache_dir() / "renderer.json"


def read_renderer_record() -> dict[str, str]:
    try:
        record = json.loads(renderer_record_path().read_text())
    except (OSError, ValueError):
        return {}
    return record if isinstance(record, dict) else {}


def write_renderer_record(info: dict[str, Any]) -> None:
    path = renderer_record_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_text(json.dumps({"build": info["build"], "renderer": info["renderer"]}))
    tmp.replace(path)


def bank_payload(bank) -> dict[str, Any]:
    """The bank as the page reads it: JSON, without the machine-specific root."""
    return bank.model_dump(mode="json", exclude={"root"})


def _first_line(exc: BaseException) -> str:
    """A page error's own words: its first line without Playwright's `Page.evaluate: Error: `."""
    text = getattr(exc, "message", None) or str(exc)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return _PREFIX.sub("", lines[0]).strip() if lines else type(exc).__name__


class PlaywrightPage:
    """`Page` over a Playwright page. Every failure is a Toy3DRenderError: a JS throw, a page or
    console error the page logged (three reports a broken shader on the console and draws on
    without it), and a call that outlives CALL_TIMEOUT (`kill` stops the browser)."""

    def __init__(self, page, errors: list[str], build: str, kill: Callable[[], None] | None = None,
                 tag: str = ""):
        self._page = page
        self._errors = errors
        self._build = build      # the page's user agent is reduced (Chrome/151.0.0.0); the browser knows
        self._kill = kill
        self._timed_out = threading.Event()
        self.tag = tag           # on the browser's command line: --toy3d-page=<tag>

    def _logged(self, what: str) -> None:
        if self._errors:
            raise Toy3DRenderError(f"toy3d page: {what}: the page logged {'; '.join(self._errors)}")

    def _expire(self) -> None:
        self._timed_out.set()
        if self._kill is not None:
            self._kill()

    def _call(self, what: str, expr: str, arg: Any = None) -> Any:
        self._logged(f"before {what}")
        watchdog = threading.Timer(CALL_TIMEOUT, self._expire)
        watchdog.daemon = True
        watchdog.start()
        try:
            out = self._page.evaluate(expr, arg)
        except Exception as exc:
            if self._timed_out.is_set():
                raise Toy3DRenderError(f"toy3d page: {what} timed out after {CALL_TIMEOUT:g} s "
                                       f"(the browser was stopped)") from exc
            if not isinstance(exc, PlaywrightError):
                raise
            extra = f" (page errors: {'; '.join(self._errors)})" if self._errors else ""
            raise Toy3DRenderError(f"toy3d page: {what} failed: {_first_line(exc)}{extra}") from exc
        finally:
            watchdog.cancel()
        self._logged(f"after {what}")
        return out

    def init(self, bank: dict[str, Any], width: int, height: int, mode: str) -> None:
        self._call("init", "([b, o]) => window.toy3d.init(b, o)",
                   [bank, {"width": width, "height": height, "mode": mode}])

    def info(self) -> dict[str, Any]:
        return {**self._call("info", "() => window.toy3d.info()"), "build": self._build}

    def evaluate(self, expr: str, arg: Any = None) -> Any:
        """Any page expression, failing like every call (for tests and doctor)."""
        return self._call("evaluate", expr, arg)

    def apply_state(self, spec: dict[str, Any]) -> dict[str, Any]:
        return self._call("applyState", "(s) => window.toy3d.applyState(s)", spec)

    def render_state(self, spec: dict[str, Any]) -> bytes:
        url = self._call("renderState", "(s) => window.toy3d.renderState(s)", spec)
        prefix = "data:image/png;base64,"
        if not isinstance(url, str) or not url.startswith(prefix):
            raise Toy3DRenderError(f"toy3d page: renderState returned {str(url)[:40]!r}, not a PNG data URL")
        return base64.b64decode(url[len(prefix):])


def wait_ready(page, errors: list[str], timeout: float = READY_TIMEOUT) -> None:
    """Wait for stage.html to set `window.ready`; a load error (a 404, a module that throws) is
    reported as soon as it happens, never after the timeout."""
    deadline = time.monotonic() + timeout
    while True:
        if errors:
            raise Toy3DRenderError(f"toy3d page failed to load: {'; '.join(errors)}")
        if page.evaluate("() => window.ready === true"):
            return
        if time.monotonic() >= deadline:
            raise Toy3DRenderError(f"toy3d page not ready after {timeout:.0f}s (no page error reported)")
        page.wait_for_timeout(50)


def _serve(errors: list[str]):
    root = WEB_ROOT.resolve()

    def handler(route) -> None:
        url = route.request.url
        rel = url.removeprefix(ORIGIN + "/").split("?")[0]
        path = (root / rel).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            errors.append(f"404 {url}")
            route.fulfill(status=404, body="")
            return
        ctype = "text/javascript" if path.suffix in (".js", ".mjs") else (
            mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        route.fulfill(status=200, body=path.read_bytes(), content_type=ctype)
    return handler


def require_build(executable: Path) -> Path:
    if not executable.exists():
        raise Toy3DRenderError(
            f"toy3d needs the pinned browser build (Chrome for Testing {BROWSER_VERSION}, "
            f"playwright {PLAYWRIGHT_VERSION}), missing at {executable}: run `{INSTALL_HINT}`")
    return executable


def _kill_tree(pid: int) -> None:
    """SIGKILL a process and every descendant (the Playwright driver and the browser it launched)."""
    out = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True)
    for child in out.stdout.split():
        _kill_tree(int(child))
    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, signal.SIGKILL)


def _driver_pid(pw) -> int | None:
    """The Playwright driver's pid (a private attribute of the pinned playwright; None if absent)."""
    proc = getattr(getattr(getattr(getattr(pw, "_impl_obj", None), "_connection", None), "_transport", None),
                   "_proc", None)
    return getattr(proc, "pid", None)


_PAGES = itertools.count(1)


@contextmanager
def open_page(width: int, height: int, mode: str = "render", *,
              init_script: str | None = None) -> Iterator[PlaywrightPage]:
    """The pinned browser with stage.html loaded at `width`×`height`, ready for `Page.init`.
    `init_script` runs in the page before stage.html does (tests)."""
    tag = f"{os.getpid()}-{next(_PAGES)}"
    stopped = threading.Event()
    cm = sync_playwright()
    pw = cm.__enter__()
    driver = _driver_pid(pw)

    def kill() -> None:
        stopped.set()
        if driver is not None:
            _kill_tree(driver)

    try:
        exe = require_build(Path(pw.chromium.executable_path))
        browser = pw.chromium.launch(executable_path=str(exe), args=[*launch_args(), f"--toy3d-page={tag}"])
        try:
            if browser.version != BROWSER_VERSION:
                raise Toy3DRenderError(
                    f"toy3d needs Chrome for Testing {BROWSER_VERSION} (playwright {PLAYWRIGHT_VERSION}), "
                    f"but {exe} is {browser.version}: run `{INSTALL_HINT}`")
            page = browser.new_page(viewport={"width": width, "height": height})
            page.set_default_timeout(CALL_TIMEOUT * 1000)
            errors: list[str] = []
            page.on("pageerror", lambda exc: errors.append(f"page error: {_first_line(exc)}"))
            page.on("console", lambda msg: errors.append(f"console error: {msg.text}") if msg.type == "error" else None)
            if init_script:
                page.add_init_script(init_script)
            page.route(f"{ORIGIN}/**", _serve(errors))
            page.goto(f"{ORIGIN}/stage.html")
            wait_ready(page, errors)
            yield PlaywrightPage(page, errors, browser.version, kill=kill, tag=tag)
        finally:
            if not stopped.is_set():
                browser.close()
    finally:
        try:
            cm.__exit__(None, None, None)
        except Exception:
            if not stopped.is_set():  # after the watchdog the driver is gone: nothing to close
                raise


def start(page: Page, bank, width: int, height: int, mode: str = "render") -> dict[str, Any]:
    """Every caller's way in (clips, stills, doctor): build the world from the bank and, to render,
    refuse a disallowed GPU backend and record this machine's renderer (the clip cache key's)."""
    page.init(bank_payload(bank), width, height, mode)
    info = page.info()
    if mode == "render":
        check_renderer(info["renderer"])
        write_renderer_record(info)
    return info
