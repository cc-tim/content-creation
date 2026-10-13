"""`toon` visual type: render an own-show scene as the scene's clip, on the engine its file
names: the 2.5D doodle engine (src/toon) or the 3D toy engine (src/toy3d, E11).

Every failure is a SceneRenderError carrying the engine's fix; compose would otherwise only wrap
it generically as `visual (toon) failed`. A toy3d scene never falls back to the 2.5D engine.
"""
from __future__ import annotations

from pathlib import Path

import structlog

from pipeline.errors import SceneRenderError

logger = structlog.get_logger()
_FIX = "Run `uv run pipeline toon validate <scene>` and fix the scene file or bank."
_FIX_TOY3D = ("Run `uv run pipeline doctor` (its toy3d check: the pinned browser on a GPU backend), "
              "then `uv run pipeline toon validate <scene>`.")


def render_toon_scene(scene: dict, duration_sec: float, width: int, height: int,
                      work_dir: Path, scene_id: str, storyboard_file: Path | None = None) -> Path:
    if width * 9 != height * 16:
        raise SceneRenderError(scene=scene_id, reason=f"toon renders 16:9 only in v0 (got {width}x{height})",
                               suggested_fix="Use 16:9 for toon scenes.")
    engine = None  # known once the scene loads: a render failure gets that engine's fix
    try:
        from toon import render
        from toon.scene import (
            catalog_for,
            drift_warnings,
            load_scene,
            scene_data_from_visual,
            scene_warnings,
            source_name,
        )

        origin = f"{source_name(storyboard_file) if storyboard_file else 'storyboard'} scene {scene_id}"
        data = scene_data_from_visual(scene.get("visual", {}), origin)
        catalog = catalog_for(data)  # the scene's engine; an unbuilt one fails, never falls back
        toon_scene = load_scene(data, catalog, narration=scene.get("narration"), duration=duration_sec)
        for w in scene_warnings(toon_scene, duration_sec):
            logger.warning("toon.scene.cut", scene_id=scene_id, detail=w)
        for w in drift_warnings(toon_scene, duration_sec):
            logger.warning("toon.scene.drift", scene_id=scene_id, detail=w)
        out = Path(work_dir) / f"toon_{scene_id}.mp4"
        engine = toon_scene.engine
        if engine == "toy3d":
            from toy3d import render as toy3d_render
            from toy3d.bank import load_bank as load_toy3d_bank

            return toy3d_render.render_clip(toon_scene, load_toy3d_bank(), out, duration_sec, width, height)
        if engine != "toon2d":
            raise SceneRenderError(scene=scene_id, reason=f"toon: no renderer for engine {engine!r}",
                                   suggested_fix=_FIX)
        return render.render_clip(toon_scene, catalog, out, duration_sec, width, height)
    except SceneRenderError:
        raise
    except Exception as exc:  # BankError, SceneError, ToonRenderError, Toy3DRenderError, cairo load (OSError) …
        fix = _FIX_TOY3D if engine == "toy3d" else _FIX
        raise SceneRenderError(scene=scene_id, reason=f"toon: {exc}", suggested_fix=fix) from exc
