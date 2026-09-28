import importlib.util
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from toon.bank import load_bank
from toon.render import frame
from toon.scene import load_scene, read_scene

TRYOUT = Path.home() / "content-creation/output/own-show/scenes/001-lioness-dishes/scene_lioness.py"
EVIDENCE = Path("tmp/toon-v0/scene001")
KEY_TIMES = (1.5, 4.0, 4.7, 8.0, 10.45, 12.2)


@pytest.mark.integration
@pytest.mark.skipif(not TRYOUT.exists(), reason="tryout scene not on this machine")
def test_scene_001_matches_tryout_v2():
    import sys

    from toon.cairo_compat import cairo

    sys.modules.setdefault("cairo", cairo)  # the tryout imports pycairo; cairocffi is byte-identical
    spec = importlib.util.spec_from_file_location("scene_lioness", TRYOUT)
    tryout = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tryout)
    bank = load_bank()
    # The tryout is full boil; soft shimmer is now the bank default, so pin this comparison to
    # full explicitly.
    scene = load_scene(read_scene("001-lioness-dishes"), bank).model_copy(update={"boil": "full"})
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    worst = 0.0
    for t in KEY_TIMES:
        new = frame(scene, bank, t)[..., [2, 1, 0]]
        old = tryout.frame(t, "bulb")[..., [2, 1, 0]]
        side = np.concatenate([old, new], axis=1)
        Image.fromarray(side).save(EVIDENCE / f"side_{t:05.2f}.png")
        worst = max(worst, float(np.abs(new.astype(np.int16) - old.astype(np.int16)).mean()))
    assert worst <= 4.0, f"worst key-frame mean abs diff {worst:.2f} > 4.0; see {EVIDENCE}"
