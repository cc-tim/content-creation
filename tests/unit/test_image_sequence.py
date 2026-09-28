"""image_sequence: one image failing to generate refuses the scene, never a black sub-clip.

Spec: docs/superpowers/specs/2026-09-29-e5-loud-failure-sweep-design.md §5.4
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from pipeline.composer import image_sequence
from pipeline.errors import SceneRenderError
from pipeline.providers.base import ProviderError, ProviderResult

VISUAL = {
    "type": "image_sequence",
    "images": [{"prompt": "a calm kitchen at dawn"}, {"prompt": "a stormy sea at night"}],
}


@pytest.fixture
def fake_media(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Fake provider, Ken Burns and ffmpeg. Prompts containing a word in state["fail"]
    raise ProviderError; the rest write a bright PNG to the prompt-hash cache path."""
    state: dict = {"fail": {"stormy"}, "prompts": [], "ffmpeg": []}

    def fake_try_chain(providers, *, prompt, out_path, size, reference_image=None):
        state["prompts"].append(prompt)
        if any(word in prompt for word in state["fail"]):
            raise ProviderError("all image providers failed; last error: fal 503 upstream")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (64, 36), (240, 240, 230)).save(out_path)
        return ProviderResult(path=out_path, provider="fake")

    def fake_image_to_video(png, out, duration, width, height, **kwargs):
        out.write_bytes(b"clip")
        return out

    def fake_run_ffmpeg(cmd, timeout=600):
        state["ffmpeg"].append([str(c) for c in cmd])
        Path(cmd[-1]).write_bytes(b"mp4")

    monkeypatch.setattr(image_sequence, "try_chain", fake_try_chain)
    monkeypatch.setattr(image_sequence, "image_to_video", fake_image_to_video)
    monkeypatch.setattr(image_sequence, "run_ffmpeg", fake_run_ffmpeg)
    return state


def test_failed_image_raises_scene_render_error_not_black(tmp_path, fake_media):
    with pytest.raises(SceneRenderError) as ei:
        image_sequence.render_image_sequence(VISUAL, 6.0, 1280, 720, tmp_path, "s3")

    err = ei.value
    assert err.scene == "s3"
    assert "image_sequence image 1 failed to generate" in err.reason
    assert "fal 503 upstream" in err.reason
    assert "pipeline doctor" in err.suggested_fix and "--scene s3" in err.suggested_fix
    assert not any("color=c=black" in " ".join(cmd) for cmd in fake_media["ffmpeg"])
    assert not (tmp_path / "s3_seq1_visual.mp4").exists()
    assert not (tmp_path / "s3_visual.mp4").exists()


def test_failed_image_suggested_fix_uses_real_project_id(tmp_path, fake_media):
    """RF10: render_image_sequence is always called with work_dir == <project>/compose/scenes
    (base.py's render_scene passes its own work_dir straight through, and compose.py's
    _render_one_scene calls render_scene(..., scenes_dir, ...) where scenes_dir is
    ctx.work_dir / "compose" / "scenes"). So work_dir.parents[1].name is the real project id
    — matching how _scene_fixes derives it from ctx.work_dir.name — and the suggested_fix must
    use it instead of the literal placeholder '<project-id>'."""
    project_dir = tmp_path / "1777777777_B"
    work_dir = project_dir / "compose" / "scenes"
    work_dir.mkdir(parents=True)

    with pytest.raises(SceneRenderError) as ei:
        image_sequence.render_image_sequence(VISUAL, 6.0, 1280, 720, work_dir, "s3")

    assert "<project-id>" not in ei.value.suggested_fix
    assert (
        f"uv run pipeline compose rescene --project-id {project_dir.name} --scene s3"
        in ei.value.suggested_fix
    )


def test_rerun_after_failed_image_regenerates_only_that_image(tmp_path, fake_media):
    """Review Focus RF4: the images that succeeded stay cached by prompt hash, so the
    retry the suggested_fix recommends asks the provider for the failed image only."""
    with pytest.raises(SceneRenderError):
        image_sequence.render_image_sequence(VISUAL, 6.0, 1280, 720, tmp_path, "s3")

    fake_media["fail"] = set()  # the provider recovered
    fake_media["prompts"].clear()
    out = image_sequence.render_image_sequence(VISUAL, 6.0, 1280, 720, tmp_path, "s3")

    assert out == tmp_path / "s3_visual.mp4"
    assert fake_media["prompts"] == ["a stormy sea at night"]
