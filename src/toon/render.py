"""Draw frames from FrameState and stream them to ffmpeg (parallel, cached, atomic)."""
from __future__ import annotations

import hashlib
import math
import multiprocessing
import os
import subprocess
import tempfile
from collections.abc import Iterable, Iterator
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

import toon
from toon import ENGINE_VERSION
from toon.bank import Bank, bank_files, load_bank
from toon.cairo_compat import cairo
from toon.engine.camera import orbit
from toon.engine.look import Look
from toon.engine.mathx import V, e_out
from toon.engine.order import character_parts, run
from toon.engine.paper import composite
from toon.engine.pen import Pen
from toon.kit.graphics import (
    GLOW_COLORS,
    anger_mark,
    bubble,
    check_pill,
    glow,
    popped,
    speed_lines,
    x_card,
)
from toon.kit.props import idea_bulb, plate, plate_stack
from toon.kit.sets import build_set
from toon.scene import ToonScene
from toon.timeline import HIP_REF, FrameState, state_at


class ToonRenderError(RuntimeError):
    pass


def _look(bank: Bank, character: str) -> Look:
    ch = bank.characters[character]
    return Look(face=dict(ch.face), hair=dict(ch.hair), body=dict(ch.body))


def draw_frame(ctx, scene: ToonScene, bank: Bank, fs: FrameState, t_draw: float,
               width: int, height: int, boil: int) -> None:
    px = height / 1080
    cam = orbit(fs.cam.az, fs.cam.el, fs.cam.dist, V(*fs.cam.target), fs.cam.focal, width, height)
    zoom = cam.scale(V(0, 2.5, 0.5)) / (100.0 * px)
    mode = scene.boil or bank.style.boil.mode
    shimmer = bank.style.boil.shimmer
    pen = Pen(ctx, boil, zoom=zoom, px=px, mode=mode, shimmer=shimmer)
    gp = Pen(ctx, boil, zoom=zoom, px=px, ghost=True, mode=mode, shimmer=shimmer)
    layers = build_set(bank.sets[fs.set_id].kind, pen, gp, cam, t_draw, door=fs.door)
    for fn in layers.back:
        fn()
    for g in fs.graphics:  # behind the characters
        if g.show.speed_lines:
            c = fs.chars[g.show.speed_lines]
            speed_lines(pen, cam.p(c.root + V(0, 2.1, 0)), 0.16 * height, grow=e_out(g.k))
    for f in fs.fx:
        at = V(*f.glow.at)
        glow(ctx, cam.p(at), f.glow.radius * cam.scale(at), GLOW_COLORS[f.glow.color], f.glow.alpha)

    def held_by(who):
        held = [p for p in fs.props.values() if p.held_by == who and p.kind == "plate"]

        def extra(rg):
            mid = (rg["arms"]["l"][2] + rg["arms"]["r"][2]) / 2
            return [(cam.depth(mid) - 0.05,
                     lambda p=p: plate(pen, cam, mid + V(*p.anchor), "held", tilt=0.75)) for p in held]
        return extra

    lows, highs, rigs = [], [], {}
    for who, c in fs.chars.items():
        parts, rg = character_parts(pen, cam, _look(bank, c.character), c.pose, c.root, c.yaw, t_draw,
                                    HIP_REF[c.hip_ref], extra=held_by(who))
        rigs[who] = rg
        if c.layer == "low":
            lows += parts.low + parts.high
        else:
            lows += parts.low
            highs += parts.high
    run(lows + layers.low)
    for fn in layers.mid:
        fn()
    for p in fs.props.values():
        if p.layer == "mid" and p.kind == "plate_stack":
            plate_stack(pen, cam, p.count)
    run(highs + layers.high)
    for p in fs.props.values():
        if p.layer == "top" and p.on in rigs:
            idea_bulb(pen, cam, rigs[p.on]["head"] + V(*p.anchor), p.b, p.mode, p.smoke)
    for g in fs.graphics:  # over everything
        s = g.show
        if s.bubble is not None:
            hp = cam.p(rigs[s.from_]["head"])
            tail = (hp[0] + 60 * px, hp[1] - 110 * px)
            box = (hp[0] + 80 * px, hp[1] - 330 * px, 330 * px, 170 * px)
            popped(ctx, tail, g.k, lambda box=box, tail=tail, s=s: bubble(pen, box, tail, s.bubble))
        elif s.anger is not None:
            head = rigs[s.anger]["head"]
            hp, sc = cam.p(head), cam.scale(head)
            anger_mark(pen, (hp[0] - 0.6 * sc, hp[1] - 0.75 * sc), 0.3 * sc)
        elif s.x_card is not None or s.check_pill is not None:
            x, y = s.at[0] * width, s.at[1] * height
            size_px = 140 * px
            draw = (lambda x=x, y=y, s=s: x_card(pen, x, y, s.x_card)) if s.x_card else \
                   (lambda x=x, y=y, s=s: check_pill(pen, x, y, s.check_pill))
            popped(ctx, (x + size_px / 2, y + size_px / 2), g.k, draw)


def frame(scene: ToonScene, bank: Bank, t: float, width: int = 1920, height: int = 1080) -> np.ndarray:
    dfps = bank.style.drawing_fps
    td = math.floor(t * dfps + 1e-9) / dfps          # drawings on twos; camera on ones
    fs = state_at(scene, bank, td, t)
    td = max(td, scene.shots[fs.shot].at)
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    draw_frame(cairo.Context(surf), scene, bank, fs, td, width, height, boil=int(t * dfps + 1e-9))
    return composite(surf, width, height, bank.style.grain)


_WORKER: dict = {}


def _init_worker(scene_json: str, bank_root: str, width: int, height: int) -> None:
    _WORKER.update(scene=ToonScene.model_validate_json(scene_json), bank=load_bank(Path(bank_root)),
                   width=width, height=height)


def _render_one(t: float) -> bytes:
    return frame(_WORKER["scene"], _WORKER["bank"], t, _WORKER["width"], _WORKER["height"]).tobytes()


def render_frames(scene: ToonScene, bank: Bank, times: Iterable[float], width: int, height: int,
                  workers: int | None = None) -> Iterator[bytes]:
    times = list(times)
    if workers == 1 or len(times) < 2:
        for t in times:
            yield frame(scene, bank, t, width, height).tobytes()
        return
    ctx = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=workers or os.cpu_count() or 2, mp_context=ctx,
                             initializer=_init_worker,
                             initargs=(scene.model_dump_json(by_alias=True), str(bank.root), width, height)) as ex:
        yield from ex.map(_render_one, times, chunksize=4)


# Every engine/kit/scene source is part of the cache key, so a drawing change re-renders even
# without a manual ENGINE_VERSION bump (compose rescene relies on this cache).
ENGINE_ROOT = Path(toon.__file__).parent


def cache_key(scene: ToonScene, bank: Bank, duration: float, width: int, height: int) -> str:
    h = hashlib.sha256(scene.model_dump_json(by_alias=True).encode())
    for f in bank_files(bank.root):
        h.update(str(f.relative_to(bank.root)).encode())
        h.update(f.read_bytes())
    for f in sorted(ENGINE_ROOT.rglob("*.py")):
        h.update(str(f.relative_to(ENGINE_ROOT)).encode())
        h.update(f.read_bytes())
    h.update(f"{ENGINE_VERSION}|{duration:.4f}|{width}x{height}|{bank.style.fps}".encode())
    return h.hexdigest()[:16]


def _tail(f, n: int = 2000) -> str:
    """The last `n` bytes of a binary file object, decoded leniently (for ffmpeg stderr)."""
    f.seek(0, os.SEEK_END)
    size = f.tell()
    f.seek(max(0, size - n))
    return f.read().decode("utf-8", errors="replace").strip()


def render_clip(scene: ToonScene, bank: Bank, out_path: Path, duration: float,
                width: int = 1920, height: int = 1080, workers: int | None = None) -> Path:
    out_path = Path(out_path)
    key = cache_key(scene, bank, duration, width, height)
    stamp = out_path.with_suffix(".key")
    if out_path.exists() and stamp.exists() and stamp.read_text() == key:
        return out_path
    # Drop the stamp first: a crash between replacing the clip and writing the new stamp must
    # never pair an old key with a new file.
    stamp.unlink(missing_ok=True)
    fps = bank.style.fps
    n = round(duration * fps)
    tmp = out_path.with_suffix(".part.mp4")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # ffmpeg's stderr goes to a spooled tempfile, not a pipe: the parent is busy writing frames to
    # stdin, and a PIPE's small OS buffer would deadlock against ffmpeg blocking on a full stderr
    # pipe while nobody is draining it.
    with tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{width}x{height}",
             "-r", str(fps), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
             "-preset", "medium", str(tmp)], stdin=subprocess.PIPE, stderr=err)
        try:
            for data in render_frames(scene, bank, [i / fps for i in range(n)], width, height, workers):
                proc.stdin.write(data)
            proc.stdin.close()
            if proc.wait() != 0:
                raise ToonRenderError(f"ffmpeg exited {proc.returncode} while encoding {out_path.name}: "
                                      f"{_tail(err)}")
        except Exception as exc:
            if proc.stdin is not None and not proc.stdin.closed:
                proc.stdin.close()
            proc.kill()
            proc.wait()  # reap: kill() alone leaves a zombie until the child is waited on
            tmp.unlink(missing_ok=True)
            if isinstance(exc, ToonRenderError):
                raise
            raise ToonRenderError(f"rendering {scene.id} failed: {exc} (ffmpeg stderr: {_tail(err)})") from exc
    tmp.replace(out_path)
    stamp.write_text(key)
    return out_path
