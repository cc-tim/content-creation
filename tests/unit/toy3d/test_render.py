"""E11 S12-8, S12-13, S12-14 (unit half): the toy3d clip runner, with a fake page. Frames stream to
ffmpeg as PNGs; a uniform frame or a dying encode leaves nothing behind; the cache key covers every
input, and a hit launches no browser."""
import io
import json
import shutil
import stat
import subprocess
from contextlib import contextmanager
from pathlib import Path

import pytest
from PIL import Image

REPO = Path(__file__).resolve().parents[3]
WORKED = REPO / "assets" / "toy3d" / "scenes" / "001-beat2-break-in.yaml"
METAL = "ANGLE (Apple, ANGLE Metal Renderer: Apple M3 Pro, Unspecified Version)"
HUB_GLES = "ANGLE (NVIDIA Corporation, NVIDIA GeForce GTX 1050/PCIe/SSE2, OpenGL ES 3.2)"
W, H = 64, 36


@pytest.fixture(autouse=True)
def _on_the_mac(monkeypatch):
    """The fake page reports the Mac's Metal renderer; the allow-list judges it as the Mac would."""
    from toy3d import runtime

    monkeypatch.setattr(runtime, "PLATFORM", "darwin")


@pytest.fixture(scope="module")
def bank():
    from toy3d.bank import load_bank

    return load_bank()


@pytest.fixture(scope="module")
def scene(bank):
    from toon.scene import load_scene, read_scene

    return load_scene(read_scene(WORKED), bank.catalog)


def _spec(scene, bank, t):
    return {"t": t}


class FakePage:
    def __init__(self, renderer=METAL, uniform_at=None, fail_at=None, init_error=None, empty_at=None):
        self.renderer, self.uniform_at, self.fail_at, self.init_error = renderer, uniform_at, fail_at, init_error
        self.empty_at = empty_at
        self.specs = []
        self.inited = None

    def init(self, bank, width, height, mode):
        if self.init_error:
            raise self.init_error
        self.inited = (width, height, mode)
        assert "root" not in bank and bank["style"]["fps"] == 30

    def info(self):
        from toy3d.runtime import BROWSER_VERSION

        return {"renderer": self.renderer, "build": BROWSER_VERSION}

    def apply_state(self, spec):
        return {}

    def render_state(self, spec):
        i = len(self.specs)
        self.specs.append(spec)
        if i == self.fail_at:
            raise RuntimeError("Target page, context or browser has been closed")
        w, h = self.inited[:2]
        img = Image.new("RGB", (w, h), (40, 40, 40))
        if i == self.empty_at:              # the background and a vignette: a world that drew nothing
            import numpy as np

            y, x = np.mgrid[0:h, 0:w]
            r = np.hypot((x - w / 2) / w, (y - h / 2) / h)
            img = Image.fromarray(np.dstack([(230 - 60 * r).astype(np.uint8)] * 3))
        elif i != self.uniform_at:          # something drawn: a mark inside the frame, moving per frame
            img.putpixel((2 + i % (w - 4), h // 2), (250, 10, 10))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()


class Factory:
    def __init__(self, page_kw=None):
        self.page_kw = page_kw or {}
        self.launches = 0
        self.pages = []

    @contextmanager
    def __call__(self, width, height, mode):
        self.launches += 1
        page = FakePage(**self.page_kw)
        self.pages.append(page)
        yield page


def _render(scene, bank, out, duration=0.5, factory=None, **kw):
    from toy3d.render import render_clip

    return render_clip(scene, bank, out, duration, W, H, page_factory=factory or Factory(), resolve=_spec, **kw)


def _frames(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                          "-show_entries", "stream=nb_read_frames,width,height,r_frame_rate", "-of", "json",
                          str(path)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)["streams"][0]


def _leftovers(out):
    return sorted(p.name for p in out.parent.iterdir())


@pytest.mark.parametrize(("duration", "n"), [(0.5, 15), (0.37, 11)])
def test_clip_has_round_duration_times_fps_frames(scene, bank, tmp_path, duration, n):
    factory = Factory()
    out = _render(scene, bank, tmp_path / "s.mp4", duration, factory)
    s = _frames(out)
    assert int(s["nb_read_frames"]) == n and (s["width"], s["height"]) == (W, H) and s["r_frame_rate"] == "30/1"
    assert factory.pages[0].inited == (W, H, "render")
    assert [sp["t"] for sp in factory.pages[0].specs] == [i / 30 for i in range(n)]
    assert _leftovers(out) == ["s.key", "s.mp4"]


def test_uniform_frame_fails_loud(scene, bank, tmp_path):
    from toy3d.runtime import Toy3DRenderError

    out = tmp_path / "s.mp4"
    with pytest.raises(Toy3DRenderError) as e:
        _render(scene, bank, out, 0.5, Factory({"uniform_at": 3}))
    assert "frame 3" in str(e.value) and "uniform" in str(e.value)
    assert _leftovers(out) == []                                    # nothing encoded, no stamp


def test_a_dying_page_leaves_no_file_and_no_stamp(scene, bank, tmp_path):
    from toy3d.runtime import Toy3DRenderError

    out = tmp_path / "s.mp4"
    _render(scene, bank, out, 0.2)
    (tmp_path / "s.key").write_text("stale")                         # an older render's stamp
    with pytest.raises(Toy3DRenderError, match="has been closed"):
        _render(scene, bank, out, 0.5, Factory({"fail_at": 5}))
    assert not (tmp_path / "s.key").exists() and not (tmp_path / "s.part.mp4").exists()


def test_a_dying_encode_leaves_no_file_and_no_stamp(scene, bank, tmp_path, monkeypatch):
    from toy3d import render
    from toy3d.runtime import Toy3DRenderError

    dies = tmp_path / "bin" / "ffmpeg"
    dies.parent.mkdir()
    # Like a real ffmpeg killed mid-encode: a half-written output file, then a non-zero exit.
    dies.write_text("#!/bin/sh\nfor a; do last=$a; done\nhead -c 64 > \"$last\"\n"
                    "echo 'muxer died' >&2\nexit 1\n")
    dies.chmod(dies.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(render, "FFMPEG", str(dies))
    out = tmp_path / "out" / "s.mp4"
    with pytest.raises(Toy3DRenderError, match="ffmpeg"):
        _render(scene, bank, out, 0.5)
    assert _leftovers(out) == []


def test_page_init_error_reaches_the_caller_and_leaves_nothing(scene, bank, tmp_path):
    from toy3d.runtime import Toy3DRenderError

    out = tmp_path / "s.mp4"
    err = Toy3DRenderError("toy3d page: init failed: palette.fur.base: not a colour 'nope'")
    with pytest.raises(Toy3DRenderError, match="palette.fur.base"):
        _render(scene, bank, out, 0.5, Factory({"init_error": err}))
    assert _leftovers(out) == []


def test_a_disallowed_backend_renders_nothing(scene, bank, tmp_path):
    from toy3d.runtime import Toy3DRenderError

    out = tmp_path / "s.mp4"
    factory = Factory({"renderer": "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device), SwiftShader driver)"})
    with pytest.raises(Toy3DRenderError, match="SwiftShader"):
        _render(scene, bank, out, 0.5, factory)
    assert factory.pages[0].specs == [] and _leftovers(out) == []


def test_cache_hit_launches_no_browser(scene, bank, tmp_path):
    factory = Factory()
    out = _render(scene, bank, tmp_path / "s.mp4", 0.5, factory)
    first = out.stat().st_mtime_ns
    assert _render(scene, bank, out, 0.5, factory) == out
    assert factory.launches == 1 and out.stat().st_mtime_ns == first


def test_a_different_machine_renderer_misses_the_cache(scene, bank, tmp_path, monkeypatch):
    """Review Focus 5: a clip rendered on the Mac (Metal) is never served as cached on the hub."""
    from toy3d import runtime
    from toy3d.runtime import renderer_record_path

    out = _render(scene, bank, tmp_path / "s.mp4", 0.5)
    record = json.loads(renderer_record_path().read_text())
    assert record["renderer"] == METAL
    monkeypatch.setattr(runtime, "PLATFORM", "linux")                                    # on the hub
    renderer_record_path().write_text(json.dumps({**record, "renderer": HUB_GLES}))   # its record
    hub = Factory({"renderer": HUB_GLES})
    _render(scene, bank, out, 0.5, hub)
    assert hub.launches == 1
    assert json.loads(renderer_record_path().read_text())["renderer"] == HUB_GLES


def test_cache_key_covers_every_input(scene, bank, tmp_path, monkeypatch):
    from toy3d import render, runtime
    from toy3d.render import cache_key

    def key(**kw):
        args = {"scene": scene, "bank": bank, "duration": 8.0, "width": W, "height": H, "renderer": METAL}
        build = kw.pop("build", runtime.BROWSER_VERSION)
        args.update(kw)
        return cache_key(args.pop("scene"), args.pop("bank"), args.pop("duration"), args.pop("width"),
                         args.pop("height"), args.pop("renderer"), build=build)

    base = key()
    assert key() == base
    style = bank.style
    variants = {
        "scene": key(scene=scene.model_copy(update={"id": "001-other"})),
        "bank": key(bank=bank.model_copy(update={"style": style.model_copy(update={"background": "#000000"})})),
        "fps": key(bank=bank.model_copy(update={"style": style.model_copy(update={"fps": 24})})),
        "build": key(build="150.0.7871.0"),
        "renderer": key(renderer=HUB_GLES),
        "size": key(width=W, height=H + 2),
        "duration": key(duration=8.1),
    }
    web = tmp_path / "web"
    shutil.copytree(runtime.WEB_ROOT, web)
    monkeypatch.setattr(runtime, "WEB_ROOT", web)
    assert key() == base
    page_js = web / "engine" / "page.js"
    page_js.write_text(page_js.read_text() + "\n// changed\n")
    variants["engine js"] = key()
    sums = web / "vendor" / "three-0.170.0" / "SHA256SUMS"
    sums.write_text(sums.read_text() + "\n")
    variants["three sums"] = key()
    py = tmp_path / "acting.py"
    py.write_text("A = 1\n")
    monkeypatch.setattr(render, "acting_sources", lambda: [py])
    k1 = key()
    py.write_text("A = 2\n")
    variants["python acting"] = key()
    assert variants["python acting"] != k1
    assert len(set(variants.values()) | {base}) == len(variants) + 1, variants


def test_the_bank_root_is_not_in_the_key(scene, bank):
    """Two checkouts of one bank render the same clip: the key reads the bank's content, not its path."""
    from toy3d.render import cache_key

    moved = bank.model_copy(update={"root": Path("/elsewhere/assets/toy3d/bank")})
    assert cache_key(scene, bank, 8.0, W, H, METAL) == cache_key(scene, moved, 8.0, W, H, METAL)


def test_acting_sources_cover_toy3d_and_the_toon_modules_it_imports():
    import toon
    import toy3d
    from toy3d.render import acting_sources

    src = {p.resolve() for p in acting_sources()}
    toy3d_dir, toon_dir = Path(toy3d.__file__).parent, Path(toon.__file__).parent
    for name in ("bank.py", "render.py", "runtime.py", "__init__.py"):
        assert toy3d_dir / name in src
    for name in ("scene.py", "catalog.py", "__init__.py"):
        assert toon_dir / name in src
    assert toon_dir / "render.py" not in src                          # the 2.5D drawing never re-keys a toy3d clip


def test_import_closure_follows_submodule_imports(tmp_path):
    import toon
    from toy3d.render import import_closure

    f = tmp_path / "m.py"
    f.write_text("from toon.engine import mathx\n")
    toon_dir = Path(toon.__file__).parent
    assert set(import_closure([f])) >= {f, toon_dir / "__init__.py", toon_dir / "engine" / "__init__.py",
                                         toon_dir / "engine" / "mathx.py"}


def test_the_key_follows_the_python_that_shapes_each_frame(scene, bank, monkeypatch):
    """A3 I1: an ease or an acting formula changes frames, so it changes the key (the key hashes
    every frame's resolved spec, besides the sources)."""
    from toy3d import acting
    from toy3d.render import cache_key

    base = cache_key(scene, bank, 2.0, W, H, METAL)
    from toon.engine.mathx import EASES

    monkeypatch.setitem(EASES, "inout", lambda x: x)
    eased = cache_key(scene, bank, 2.0, W, H, METAL)
    monkeypatch.undo()
    monkeypatch.setattr(acting, "FLAP_RAMP", 0.1)
    flapped = cache_key(scene, bank, 4.0, W, H, METAL)
    monkeypatch.undo()
    assert eased != base and flapped != cache_key(scene, bank, 4.0, W, H, METAL)


def test_the_key_covers_the_vendored_files_not_just_their_sums(scene, bank, tmp_path, monkeypatch):
    # Phase 2 review M4: a locally patched three.js re-keys even if SHA256SUMS wasn't updated.
    from toy3d import runtime
    from toy3d.render import cache_key

    web = tmp_path / "web"
    shutil.copytree(runtime.WEB_ROOT, web)
    monkeypatch.setattr(runtime, "WEB_ROOT", web)
    before = cache_key(scene, bank, 1.0, W, H, METAL)
    f = web / "vendor" / "three-0.170.0" / "examples" / "jsm" / "postprocessing" / "OutputPass.js"
    f.write_text(f.read_text() + "\n// patched\n")
    assert cache_key(scene, bank, 1.0, W, H, METAL) != before


def test_toy3d_no_longer_depends_on_the_2d_bank():
    # A3 m2: toy3d's acting reads the engine-neutral timeline, so 2.5D bank edits never re-key it.
    import toon
    from toy3d.render import acting_sources

    src = {p.resolve() for p in acting_sources()}
    toon_dir = Path(toon.__file__).parent
    assert toon_dir / "beats.py" in src
    assert not {toon_dir / "bank.py", toon_dir / "timeline.py", toon_dir / "engine" / "rig.py"} & src



def test_a_background_only_frame_fails_loud(scene, bank, tmp_path):
    """Phase 2 review M2: a frame with nothing drawn but the background and its vignette isn't
    uniform, but it isn't a frame either."""
    from toy3d.runtime import Toy3DRenderError

    out = tmp_path / "s.mp4"
    with pytest.raises(Toy3DRenderError, match="frame 4 .*nothing but the background"):
        _render(scene, bank, out, 0.5, Factory({"empty_at": 4}))
    assert _leftovers(out) == []


def test_a_render_never_touches_another_renders_partial_file(scene, bank, tmp_path):
    """Phase 2 review M3: two renders of one clip at once must not share a temp file."""
    other = tmp_path / "s.part.mp4"
    other.write_bytes(b"another render's frames")
    _render(scene, bank, tmp_path / "s.mp4", 0.2)
    assert other.read_bytes() == b"another render's frames"
