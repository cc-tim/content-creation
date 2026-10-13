"""Render a toy3d scene to a clip (E11): Python resolves each frame's acting (`toy3d.acting`), the
page draws it, PNG frames stream to ffmpeg. Cached on a key over every input, atomic on disk.
"""
from __future__ import annotations

import ast
import contextlib
import hashlib
import io
import os
import subprocess
import tempfile
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

from PIL import Image

import toon
import toy3d
from toon.scene import ToonScene
from toy3d import acting, runtime
from toy3d.bank import Toy3DBank
from toy3d.runtime import BROWSER_VERSION, Page, Toy3DRenderError

FFMPEG = "ffmpeg"
PageFactory = Callable[[int, int, str], AbstractContextManager[Page]]
Resolve = Callable[[ToonScene, Toy3DBank, float], dict[str, Any]]


def _module_file(name: str) -> Path | None:
    """The source file of a `toon` / `toy3d` module (a package's `__init__.py`), else None."""
    top, *rest = name.split(".")
    roots = {"toon": Path(toon.__file__).parent, "toy3d": Path(toy3d.__file__).parent}
    if top not in roots:
        return None
    base = roots[top].joinpath(*rest)
    for f in (base.with_suffix(".py"), base / "__init__.py"):
        if f.is_file():
            return f
    return None


def import_closure(files: list[Path]) -> list[Path]:
    """`files` plus, transitively, every `toon` / `toy3d` module they import (with each enclosing
    package's `__init__`, which runs on import)."""
    pending = list(files)
    seen: set[Path] = set()
    while pending:
        f = pending.pop()
        if f in seen:
            continue
        seen.add(f)
        names: set[str] = set()
        for node in ast.walk(ast.parse(f.read_text())):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names.add(node.module)
                names.update(f"{node.module}.{a.name}" for a in node.names)
        for name in names:
            parts = name.split(".")
            for i in range(1, len(parts) + 1):            # each enclosing package runs on import
                dep = _module_file(".".join(parts[:i]))
                if dep is not None and dep not in seen:
                    pending.append(dep)
    return sorted(seen)


def acting_sources() -> list[Path]:
    """Every Python source a toy3d frame depends on: the toy3d package and the `toon` modules it
    imports. Not the 2.5D drawing code."""
    return import_closure(sorted(Path(toy3d.__file__).parent.rglob("*.py")))


def _web_sources() -> list[Path]:
    """The page: stage.html, the engine modules and the vendored three.js (by its SHA256SUMS)."""
    web = runtime.WEB_ROOT
    return [web / "stage.html", *sorted((web / "engine").rglob("*.js")),
            web / "vendor" / "three-0.170.0" / "SHA256SUMS"]


def cache_key(scene: ToonScene, bank: Toy3DBank, duration: float, width: int, height: int,
              renderer: str, *, build: str = BROWSER_VERSION) -> str:
    h = hashlib.sha256(scene.model_dump_json(by_alias=True).encode())
    h.update(bank.model_dump_json(exclude={"root"}).encode())
    for f in _web_sources():
        h.update(f.relative_to(runtime.WEB_ROOT).as_posix().encode())
        h.update(f.read_bytes())
    for f in acting_sources():
        h.update(f.name.encode())
        h.update(f.read_bytes())
    h.update(f"{build}|{renderer}|{duration:.4f}|{width}x{height}|{bank.style.fps}".encode())
    return h.hexdigest()[:16]


def _record_key(scene, bank, duration, width, height) -> str | None:
    """The key from this machine's renderer record, if it is for the pinned build."""
    record = runtime.read_renderer_record()
    if record.get("build") != BROWSER_VERSION or not record.get("renderer"):
        return None
    return cache_key(scene, bank, duration, width, height, record["renderer"])


def check_frame(png: bytes, i: int, t: float, width: int, height: int) -> None:
    """A readable PNG of the asked size that isn't one colour, or a loud Toy3DRenderError."""
    try:
        img = Image.open(io.BytesIO(png))
        img.load()
    except Exception as exc:
        raise Toy3DRenderError(f"frame {i} (t={t:.3f}s) is not a readable PNG: {exc}") from exc
    if img.size != (width, height):
        raise Toy3DRenderError(f"frame {i} (t={t:.3f}s) is {img.size[0]}x{img.size[1]}, not {width}x{height}")
    extrema: Any = img.getextrema()
    bands = extrema if isinstance(extrema[0], tuple) else (extrema,)
    if all(lo == hi for lo, hi in bands):
        raise Toy3DRenderError(f"frame {i} (t={t:.3f}s) is a uniform colour {extrema}: the page drew nothing "
                               f"(a lost WebGL context or an empty world)")


def _tail(f, n: int = 2000) -> str:
    """The last `n` bytes of a binary file object, decoded leniently (for ffmpeg stderr)."""
    f.seek(0, os.SEEK_END)
    size = f.tell()
    f.seek(max(0, size - n))
    return f.read().decode("utf-8", errors="replace").strip()


def _frames(page: Page, scene, bank, resolve: Resolve, n: int, fps: int, width: int,
            height: int) -> Iterator[bytes]:
    for i in range(n):
        t = i / fps
        png = page.render_state(resolve(scene, bank, t))
        check_frame(png, i, t, width, height)
        yield png


def render_clip(scene: ToonScene, bank: Toy3DBank, out_path: Path, duration: float,
                width: int = 1920, height: int = 1080, *, page_factory: PageFactory | None = None,
                resolve: Resolve | None = None) -> Path:
    out_path = Path(out_path)
    stamp = out_path.with_suffix(".key")

    def cached(key: str | None) -> bool:
        return key is not None and out_path.exists() and stamp.exists() and stamp.read_text() == key

    if cached(_record_key(scene, bank, duration, width, height)):
        return out_path
    if resolve is None:
        resolve = acting.resolve
    factory = page_factory or runtime.open_page
    fps = bank.style.fps
    n = round(duration * fps)
    tmp = out_path.with_suffix(".part.mp4")
    with factory(width, height, "render") as page:
        page.init(runtime.bank_payload(bank), width, height, "render")
        info = page.info()
        runtime.check_renderer(info["renderer"])
        runtime.write_renderer_record(info)
        key = cache_key(scene, bank, duration, width, height, info["renderer"], build=info["build"])
        if cached(key):
            return out_path
        # Drop the stamp first: a crash between replacing the clip and writing the new stamp must
        # never pair an old key with a new file.
        stamp.unlink(missing_ok=True)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # ffmpeg's stderr goes to a tempfile, not a pipe, so a full stderr can't deadlock the writes.
        with tempfile.TemporaryFile() as err:
            proc = subprocess.Popen(
                [FFMPEG, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "png",
                 "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium",
                 "-f", "mp4", str(tmp)], stdin=subprocess.PIPE, stderr=err)
            assert proc.stdin is not None
            try:
                for png in _frames(page, scene, bank, resolve, n, fps, width, height):
                    proc.stdin.write(png)
                proc.stdin.close()
                if proc.wait() != 0:
                    raise Toy3DRenderError(f"ffmpeg exited {proc.returncode} while encoding {out_path.name}: "
                                           f"{_tail(err)}")
            except BaseException as exc:
                if not proc.stdin.closed:
                    with contextlib.suppress(BrokenPipeError):
                        proc.stdin.close()
                proc.kill()
                proc.wait()  # reap: kill() alone leaves a zombie until the child is waited on
                tmp.unlink(missing_ok=True)
                if isinstance(exc, Toy3DRenderError) or not isinstance(exc, Exception):
                    raise
                where = "ffmpeg" if isinstance(exc, BrokenPipeError) else "rendering"
                raise Toy3DRenderError(f"{where} failed on {scene.id}: {exc} "
                                       f"(ffmpeg stderr: {_tail(err)})") from exc
    tmp.replace(out_path)
    stamp.write_text(key)
    return out_path
