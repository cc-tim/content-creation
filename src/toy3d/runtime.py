"""The toy3d browser runtime (E11): the pinned Chrome for Testing build on an allow-listed GPU
backend, serving `web/` to the page, and the page's API (`window.toy3d`) as a Python `Page`.

There is no fallback: a missing build, a different build, a software or Vulkan backend, a page that
fails to load or throws all raise `Toy3DRenderError` naming what to do.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import sys
import time
from collections.abc import Iterator
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
CALL_TIMEOUT_MS = 120_000                # one page call (init builds the whole world, shaders included)

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
    """`Page` over a Playwright page. Every failure, a JS throw included, is a Toy3DRenderError."""

    def __init__(self, page, errors: list[str], build: str):
        self._page = page
        self._errors = errors
        self._build = build      # the page's user agent is reduced (Chrome/151.0.0.0); the browser knows

    def _call(self, what: str, expr: str, arg: Any = None) -> Any:
        try:
            return self._page.evaluate(expr, arg)
        except PlaywrightError as exc:
            extra = f" (page errors: {'; '.join(self._errors)})" if self._errors else ""
            raise Toy3DRenderError(f"toy3d page: {what} failed: {_first_line(exc)}{extra}") from exc

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


@contextmanager
def open_page(width: int, height: int, mode: str = "render", *,
              init_script: str | None = None) -> Iterator[PlaywrightPage]:
    """The pinned browser with stage.html loaded at `width`×`height`, ready for `Page.init`.
    `init_script` runs in the page before stage.html does (tests)."""
    with sync_playwright() as pw:
        exe = require_build(Path(pw.chromium.executable_path))
        browser = pw.chromium.launch(executable_path=str(exe), args=launch_args())
        try:
            if browser.version != BROWSER_VERSION:
                raise Toy3DRenderError(
                    f"toy3d needs Chrome for Testing {BROWSER_VERSION} (playwright {PLAYWRIGHT_VERSION}), "
                    f"but {exe} is {browser.version}: run `{INSTALL_HINT}`")
            page = browser.new_page(viewport={"width": width, "height": height})
            page.set_default_timeout(CALL_TIMEOUT_MS)
            errors: list[str] = []
            page.on("pageerror", lambda exc: errors.append(f"page error: {_first_line(exc)}"))
            if init_script:
                page.add_init_script(init_script)
            page.route(f"{ORIGIN}/**", _serve(errors))
            page.goto(f"{ORIGIN}/stage.html")
            wait_ready(page, errors)
            yield PlaywrightPage(page, errors, browser.version)
        finally:
            browser.close()
