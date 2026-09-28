"""`toon` visual type: render an own-show 2.5D scene (src/toon) as the scene's clip.

Every failure is a SceneRenderError carrying the toon-specific fix (`pipeline toon
validate`); compose would otherwise only wrap it generically as `visual (toon) failed`.
"""
from __future__ import annotations

from pathlib import Path

import structlog

from pipeline.errors import SceneRenderError

logger = structlog.get_logger()
_FIX = "Run `uv run pipeline toon validate <scene>` and fix the scene file or bank."


def render_toon_scene(scene: dict, duration_sec: float, width: int, height: int,
                      work_dir: Path, scene_id: str) -> Path:
    if width * 9 != height * 16:
        raise SceneRenderError(scene=scene_id, reason=f"toon renders 16:9 only in v0 (got {width}x{height})",
                               suggested_fix="Use 16:9 for toon scenes.")
    try:
        from toon import render
        from toon.bank import load_bank
        from toon.scene import load_scene, scene_data_from_visual, scene_warnings

        bank = load_bank()
        data = scene_data_from_visual(scene.get("visual", {}))
        toon_scene = load_scene(data, bank, narration=scene.get("narration"), duration=duration_sec)
        for w in scene_warnings(toon_scene, duration_sec):
            logger.warning("toon.scene.cut", scene_id=scene_id, detail=w)
        out = Path(work_dir) / f"toon_{scene_id}.mp4"
        return render.render_clip(toon_scene, bank, out, duration_sec, width, height)
    except SceneRenderError:
        raise
    except Exception as exc:  # BankError, SceneError, ToonRenderError, cairo load (OSError) …
        raise SceneRenderError(scene=scene_id, reason=f"toon: {exc}", suggested_fix=_FIX) from exc
