"""The toy3d cast model sheet (E11 S12-12): the cast in three views, the snapshot's stills. Standing
GuoGuo 3/4 (his design view), and the two-shot and close-up of the worked scene at its still time.
For review and for the Layer C goldens."""
from __future__ import annotations

from toon.scene import ToonScene

SHEET_T = 4.6           # scene.js STILL_T: Tim shocked, the lioness pointing, the bubble up
DESIGN_T = 0.714        # scene.js STILLS.guo: the design views' time


def with_camera(scene: ToonScene, preset: str) -> ToonScene:
    """`scene` seen from another camera preset (its first shot's), the acting unchanged."""
    first = scene.shots[0].model_copy(update={"camera": preset})
    return scene.model_copy(update={"shots": [first, *scene.shots[1:]]})


def sheet_views(worked: ToonScene, design: ToonScene) -> list[tuple[str, ToonScene, float]]:
    """(name, scene, time) per view: `design` is the standing-GuoGuo scene (its own camera)."""
    return [("guo_34", design, DESIGN_T),
            ("twoshot", with_camera(worked, "twoshot"), SHEET_T),
            ("closeup", with_camera(worked, "closeup"), SHEET_T)]
