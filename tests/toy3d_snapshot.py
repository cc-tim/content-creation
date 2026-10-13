"""The frozen r7-3d snapshot driven by its own code (E11, EM ruling D1): the parity references,
the Layer B node goldens and the AO denoise noise's stream position all come from here.

The snapshot (spec §12) is immutable: every file is checked against its SHA256SUMS, whose own hash
is pinned below, before it is served. It runs on the pinned browser build with the same launch
flags as the engine. `three` comes from the vendored r170 (the same files the snapshot's lockfile
pins). Its scene.js is served with one line appended (`window.__snap = {...}`) so its scene graph
can be read; the file on disk is never touched.

    uv run python -m tests.toy3d_snapshot refs <out_dir>     # the 6 key frames + the design view
    uv run python -m tests.toy3d_snapshot nodes <out.json>   # Layer B: named nodes at the key times
    uv run python -m tests.toy3d_snapshot random             # the denoise noise's stream position
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SUMS_SHA256 = "d9c61f636be2ee9adc537f2367224ebdf18bc2898fcec595fa2ca79f32715d75"
RELATIVE = Path("output/projects/20260724-hybrid-ai-agent-controller/style-tryouts/r7-3d/frozen-v7-20261013")
ORIGIN = "http://snap.local"
KEY_TIMES = (0.6, 2.4, 3.3, 4.0, 5.3, 7.0)
DESIGN_VIEW = ("guo", 0.714)            # STILLS.guo: standing GuoGuo, 3/4, neutral


def snapshot_dir() -> Path | None:
    """TOY3D_SNAPSHOT, else the main checkout's copy (a worktree has no output/)."""
    env = os.environ.get("TOY3D_SNAPSHOT")
    candidates = [Path(env)] if env else [REPO / RELATIVE, REPO.parents[1] / RELATIVE]
    return next((c for c in candidates if (c / "SHA256SUMS").is_file()), None)


def verify(d: Path) -> dict[str, str]:
    """Every snapshot file against its SHA256SUMS, and SHA256SUMS against the pinned hash."""
    sums = (d / "SHA256SUMS").read_bytes()
    got = hashlib.sha256(sums).hexdigest()
    if got != SUMS_SHA256:
        raise RuntimeError(f"{d}/SHA256SUMS is {got}, not the frozen snapshot's {SUMS_SHA256}")
    table = {}
    for line in sums.decode().splitlines():
        digest, name = line.split(maxsplit=1)
        if hashlib.sha256((d / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"{d}/{name} does not match the snapshot's SHA256SUMS")
        table[name] = digest
    return table


EXPORT_JS = """
window.__snap = { scene, camera, tim, lion, guoSit, guoStand, chair, doorHinge, bulb, glow, rays, bulbLight,
  mGlass, bubble, bubPop, bang, puffs, TIM_FACE, LION_FACE };
"""

# Counts Math.random draws (the stage seeds it): `start` = draws before the GTAOPass constructor's
# first one, `noise` = draws before its SimplexNoise's first one.
COUNT_JS = """
(() => {
  let impl = Math.random, n = 0, start = null, noise = null;
  Object.defineProperty(Math, 'random', { configurable: true,
    get() { return function () {
      if (start === null || noise === null) {
        const st = new Error().stack;
        if (start === null && st.includes('GTAOPass')) start = n;
        if (noise === null && st.includes('SimplexNoise')) noise = n;
      }
      n++; return impl(); }; },
    set(f) { impl = f; } });
  window.__rand = () => ({ start, noise, total: n });
})();
"""

# Layer B: the snapshot's named nodes, keyed as toy3d's world.js keys its own (snapshot()).
NODES_JS = """
() => {
  const S = window.__snap, out = {};
  const put = (name, o) => { if (o.visible) out[name] = Array.from(o.matrixWorld.elements); };
  const rig = (name, a, kind) => {
    put(`${name}.root`, a.root); put(`${name}.head`, a.head); put(`${name}.hips`, a.hips); put(`${name}.neck`, a.neck);
    if (kind === 'tim') put(`${name}.torso`, a.torso);
    else { put(`${name}.body`, a.body); put(`${name}.tail`, a.tail); put(`${name}.ear_l`, a.ears[0]); put(`${name}.ear_r`, a.ears[1]); }
    ['l', 'r'].forEach((s, i) => { for (const j of ['j1', 'j2']) { put(`${name}.arm_${s}.${j}`, a.arms[i][j]); put(`${name}.leg_${s}.${j}`, a.legs[i][j]); } });
  };
  rig('tim', S.tim, 'tim');
  out['tim.face'] = 'tim_' + Object.entries(S.TIM_FACE).find(([, t]) => t === S.tim.face.material.map)[0];
  if (S.tim.drop.visible) put('tim.drop', S.tim.drop);
  rig('lioness', S.lion, 'lioness');
  out['lioness.face'] = 'lion_' + Object.entries(S.LION_FACE).find(([, t]) => t === S.lion.face.material.map)[0];
  out['lioness.finger'] = S.lion.arms[1].e.children[0].userData.finger.visible;
  const g = S.guoSit.root.visible ? S.guoSit : S.guoStand;
  put('guoguo.root', g.root); put('guoguo.body', g.body); put('guoguo.head', g.head);
  g.flippers.forEach((f, i) => put(`guoguo.flipper_${'lr'[i]}`, f));
  g.eyes.forEach((e, i) => { put(`guoguo.eye_${'lr'[i]}`, e.eye); put(`guoguo.pupil_${'lr'[i]}`, e.pupil); });
  out['guoguo.build'] = g.seated ? 'guoguo_seated' : 'guoguo_standing';
  out['guoguo.twist'] = g.twist.value;
  g.parts.forEach((part, i) => { out[`guoguo.push.${i}`] = part.userData.push.value.toArray(); });
  put('chair', S.chair); put('door', S.doorHinge); put('camera', S.camera);
  out['camera.fov'] = S.camera.fov;
  put('bulb', S.bulb);
  Object.assign(out, { 'bulb.emissive': S.mGlass.emissiveIntensity, 'bulb.opacity': S.mGlass.opacity,
    'bulb.color': S.mGlass.color.getHexString(), 'glow.opacity': S.glow.material.opacity,
    'glow.scale': S.glow.scale.x, 'rays.visible': S.rays.visible, 'light.intensity': S.bulbLight.intensity });
  if (S.rays.visible) out['rays.scale'] = S.rays.scale.x;
  if (S.bubble.visible) { put('bubble', S.bubble); put('bubble.pop', S.bubPop); put('bubble.bang', S.bang); }
  S.puffs.slice(0, 9).forEach((m, i) => { if (m.visible) { put(`dust.${i}`, m); out[`dust.${i}.opacity`] = m.material.opacity; } });
  S.puffs.slice(9).forEach((m, i) => { if (m.visible) { put(`smoke.${i}`, m); out[`smoke.${i}.opacity`] = m.material.opacity; } });
  return out;
}
"""


def _route(d: Path):
    from toy3d.runtime import WEB_ROOT

    three = WEB_ROOT / "vendor" / "three-0.170.0"

    def handler(route) -> None:
        rel = route.request.url.removeprefix(ORIGIN + "/").split("?")[0]
        if rel.startswith("node_modules/three/"):
            path = three / rel.removeprefix("node_modules/three/")
        else:
            path = d / rel
        if not path.is_file():
            route.fulfill(status=404, body="")
            return
        body = path.read_bytes()
        if rel == "scene.js":
            body += EXPORT_JS.encode()
        ctype = "text/javascript" if path.suffix in (".js", ".mjs") else (
            "text/html" if path.suffix == ".html" else "application/json")
        route.fulfill(status=200, body=body, content_type=ctype)
    return handler


@contextmanager
def open_snapshot(d: Path, width: int = 1920, height: int = 1080, *, count: bool = False) -> Iterator:
    """The snapshot's stage.html (look A) on the pinned browser, ready for `renderAt`."""
    from playwright.sync_api import sync_playwright

    from toy3d.runtime import BROWSER_VERSION, launch_args, require_build, wait_ready

    verify(d)
    with sync_playwright() as pw:
        exe = require_build(Path(pw.chromium.executable_path))
        browser = pw.chromium.launch(executable_path=str(exe), args=launch_args())
        try:
            assert browser.version == BROWSER_VERSION, browser.version
            page = browser.new_page(viewport={"width": width, "height": height})
            page.set_default_timeout(240_000)
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            if count:
                page.add_init_script(COUNT_JS)
            page.route(f"{ORIGIN}/**", _route(d))
            page.goto(f"{ORIGIN}/stage.html?look=A")
            wait_ready(page, errors, timeout=240.0)
            renderer = page.evaluate(
                "() => { const gl = document.querySelector('canvas').getContext('webgl2');"
                " const e = gl.getExtension('WEBGL_debug_renderer_info'); return gl.getParameter(e.UNMASKED_RENDERER_WEBGL); }")
            yield page, {"renderer": renderer, "build": browser.version}
        finally:
            browser.close()


def render(page, t: float, shot: str | None = None) -> bytes:
    url = page.evaluate("([t, s]) => window.renderAt(t, s)", [t, shot])
    return base64.b64decode(url.split(",", 1)[1])


def nodes(page, t: float, shot: str | None = None) -> dict:
    render(page, t, shot)
    return page.evaluate(NODES_JS)


def downscale(png: bytes) -> bytes:
    """P2-R7: references and goldens are 1920×1080 renders downscaled to 960×540 (LANCZOS)."""
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(png)).convert("RGB").resize((960, 540), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def ref_name(t: float, shot: str | None = None) -> str:
    return f"{shot}@{t:.3f}.png" if shot else f"worked@{t:.3f}.png"


def main(argv: list[str]) -> None:
    d = snapshot_dir()
    if d is None:
        sys.exit("no frozen snapshot: set TOY3D_SNAPSHOT to frozen-v7-20261013/")
    cmd = argv[0] if argv else ""
    if cmd == "random":
        with open_snapshot(d, count=True) as (page, _):
            print(json.dumps(page.evaluate("() => window.__rand()")))
    elif cmd == "refs":
        out = Path(argv[1])
        out.mkdir(parents=True, exist_ok=True)
        with open_snapshot(d) as (page, info):
            render(page, 0.0)                          # warm-up: shader compile
            for t in KEY_TIMES:
                (out / ref_name(t)).write_bytes(downscale(render(page, t)))
            shot, t = DESIGN_VIEW
            (out / ref_name(t, shot)).write_bytes(downscale(render(page, t, shot)))
            print(json.dumps(info))
    elif cmd == "nodes":
        with open_snapshot(d) as (page, _):
            got = {f"worked@{t}": nodes(page, t) for t in KEY_TIMES}
            shot, t = DESIGN_VIEW
            got[f"{shot}@{t}"] = nodes(page, t, shot)
        Path(argv[1]).write_text(json.dumps(got, indent=1, sort_keys=True) + "\n")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
