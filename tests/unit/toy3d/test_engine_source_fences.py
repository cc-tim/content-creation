"""E11 S12-7 and S12-10 (static halves): the vendored three.js is the pinned r170, the engine JS is
deterministic and wordless, and it holds no look constants (the look is bank data)."""
import hashlib
import re
from pathlib import Path

import toy3d

WEB = Path(toy3d.__file__).parent / "web"
VENDOR = WEB / "vendor" / "three-0.170.0"
SNAPSHOT_STAGE_SEED = "let a = 20261013;"   # stage.html in the frozen snapshot


def _engine_js():
    files = sorted((WEB / "engine").glob("*.js"))
    assert files, "no engine modules"
    return {f.name: f.read_text() for f in files}


def test_vendored_three_matches_its_sums():
    sums = {}
    for line in (VENDOR / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        sums[name] = digest
    on_disk = {str(p.relative_to(VENDOR)) for p in VENDOR.rglob("*") if p.is_file()} - {"SHA256SUMS"}
    assert set(sums) == on_disk
    for name, digest in sums.items():
        assert hashlib.sha256((VENDOR / name).read_bytes()).hexdigest() == digest, name
    assert "const REVISION = '170';" in (VENDOR / "build" / "three.module.js").read_text()
    assert (VENDOR / "LICENSE").read_text().startswith("The MIT License")


def test_stage_seeds_math_random_like_the_snapshot():
    stage = (WEB / "stage.html").read_text()
    assert SNAPSHOT_STAGE_SEED in stage and "Math.random = function" in stage
    assert "./vendor/three-0.170.0/build/three.module.js" in stage


_UNSEEDED = [r"Math\.random\s*\(", r"\bDate\b", r"performance\.now", r"requestAnimationFrame",
             r"\bfillText\b", r"\bstrokeText\b"]


def test_engine_js_has_no_unseeded_time_or_text():
    # Determinism (no wall clock, no unseeded randomness) and wordless (no drawn text).
    for name, src in _engine_js().items():
        for pattern in _UNSEEDED:
            assert not re.search(pattern, src), f"{name}: {pattern}"


_LOOK = [r"""['"`]#[0-9a-fA-F]{3,8}['"`]""", r"\brgba?\(\s*[0-9]",
         r"\b(?:toneMappingExposure|environmentIntensity|blendIntensity|intensity|strength|threshold|"
         r"roughness|clearcoat|sheen|metalness|opacity|emissiveIntensity)\s*[:=]\s*-?[0-9.]+"]


def test_no_look_constants_in_engine_js():
    # S12-7: palettes, materials, lights and post live in the bank; the engine reads them.
    for name, src in _engine_js().items():
        for pattern in _LOOK:
            hits = re.findall(pattern, src)
            assert not hits, f"{name}: look constant(s) {hits[:5]}"
