from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pipeline.stages.tts import _synthesize_pass
from pipeline.storyboard import NarrationSource, Scene, Storyboard


class _RecordingEngine:
    """Test double: records each call and writes a tiny placeholder mp3."""
    def __init__(self, name: str):
        self._name = name
        self.calls: list[tuple[str, str | None, str]] = []  # (text, scene_id, profile_id)

    @property
    def name(self) -> str:
        return self._name

    def synthesize(self, text: str, out_path: Path, profile: Any, scene_id: str | None = None) -> Path:
        self.calls.append((text, scene_id, profile.id))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # Write a 0.1s silent mp3 placeholder so duration probing returns >0
        import subprocess
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
             "-t", "0.1", "-c:a", "libmp3lame", str(out_path)],
            check=True,
        )
        return out_path


class _StubProfile:
    def __init__(self, id_: str):
        self.id = id_


class _StubRegistry:
    """Minimal registry stub. Resolves voice_ids → (engine, profile) tuples."""
    def __init__(self, mapping: dict[str, tuple[Any, Any]]):
        self._m = mapping

    def resolve(self, voice_id: str) -> tuple[Any, Any]:
        if voice_id not in self._m:
            from pipeline.voices.base import VoiceNotFound
            raise VoiceNotFound(voice_id)
        return self._m[voice_id]


def _make_storyboard(scenes_with_sources: list[tuple[str, NarrationSource | None]]) -> Storyboard:
    return Storyboard(scenes=[
        Scene(id=sid, section="content", narration=f"text-{sid}",
              narration_est_sec=1.0, narration_source=ns)
        for sid, ns in scenes_with_sources
    ])


def test_synthesize_pass_uses_default_when_no_narration_source(tmp_path: Path):
    """Backwards compat: scenes without narration_source use the passed-in default."""
    default_engine = _RecordingEngine("default")
    default_profile = _StubProfile("default-voice")
    sb = _make_storyboard([("s1", None), ("s2", None)])

    asyncio.run(_synthesize_pass(
        segments=["text-s1", "text-s2"],
        scene_ids=["s1", "s2"],
        scene_pauses_ms=[0, 0],
        audio_dir=tmp_path,
        locale_tag="zh-TW",
        engine=default_engine,
        profile=default_profile,
        seg_prefix="segment",
        registry=_StubRegistry({}),
        storyboard=sb,
    ))

    assert len(default_engine.calls) == 2
    assert all(c[2] == "default-voice" for c in default_engine.calls)


def test_synthesize_pass_dispatches_to_per_scene_edge_engine(tmp_path: Path):
    """A scene with narration_source.engine='edge' resolves through registry."""
    default_engine = _RecordingEngine("default")
    default_profile = _StubProfile("default-voice")
    custom_engine = _RecordingEngine("custom")
    custom_profile = _StubProfile("custom-voice")

    sb = _make_storyboard([
        ("s1", None),
        ("s2", NarrationSource(engine="edge", voice="custom-voice")),
    ])

    asyncio.run(_synthesize_pass(
        segments=["text-s1", "text-s2"],
        scene_ids=["s1", "s2"],
        scene_pauses_ms=[0, 0],
        audio_dir=tmp_path,
        locale_tag="zh-TW",
        engine=default_engine,
        profile=default_profile,
        seg_prefix="segment",
        registry=_StubRegistry({"custom-voice": (custom_engine, custom_profile)}),
        storyboard=sb,
    ))

    # s1 → default; s2 → custom
    assert len(default_engine.calls) == 1
    assert default_engine.calls[0][1] == "s1"
    assert len(custom_engine.calls) == 1
    assert custom_engine.calls[0][1] == "s2"
    assert custom_engine.calls[0][2] == "custom-voice"


def test_synthesize_pass_prerecorded_file_transcodes_directly(tmp_path: Path):
    """engine='prerecorded' + file=... bypasses VoiceEngine and transcodes the file."""
    import subprocess

    default_engine = _RecordingEngine("default")
    default_profile = _StubProfile("default-voice")

    # Create a real WAV input so ffmpeg can transcode it.
    overrides = tmp_path / "narration_overrides"
    overrides.mkdir()
    src_wav = overrides / "s2.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
         "-c:a", "pcm_s16le", str(src_wav)],
        check=True,
    )

    sb = _make_storyboard([
        ("s1", None),
        ("s2", NarrationSource(engine="prerecorded",
                               file="narration_overrides/s2.wav")),
    ])

    asyncio.run(_synthesize_pass(
        segments=["text-s1", "text-s2"],
        scene_ids=["s1", "s2"],
        scene_pauses_ms=[0, 0],
        audio_dir=tmp_path,
        locale_tag="zh-TW",
        engine=default_engine,
        profile=default_profile,
        seg_prefix="segment",
        registry=_StubRegistry({}),
        storyboard=sb,
        project_root=tmp_path,
    ))

    # s1 used the default engine; s2 went through direct transcode (no engine call).
    assert len(default_engine.calls) == 1
    # The s2 segment file must exist and be a valid mp3 (we transcode wav→mp3).
    assert (tmp_path / "segment_001.mp3").exists()
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=codec_name",
         "-of", "default=noprint_wrappers=1:nokey=1", str(tmp_path / "segment_001.mp3")],
        capture_output=True, text=True, check=True,
    )
    assert probe.stdout.strip() == "mp3"


def test_synthesize_pass_falls_back_when_voice_not_in_registry(tmp_path: Path):
    """If the per-scene voice isn't in the registry, fall back to default and warn."""
    default_engine = _RecordingEngine("default")
    default_profile = _StubProfile("default-voice")

    sb = _make_storyboard([
        ("s1", NarrationSource(engine="edge", voice="missing-voice")),
    ])

    asyncio.run(_synthesize_pass(
        segments=["text-s1"],
        scene_ids=["s1"],
        scene_pauses_ms=[0],
        audio_dir=tmp_path,
        locale_tag="zh-TW",
        engine=default_engine,
        profile=default_profile,
        seg_prefix="segment",
        registry=_StubRegistry({}),  # empty: missing-voice will not resolve
        storyboard=sb,
    ))

    # Falls back to the default engine.
    assert len(default_engine.calls) == 1
    assert default_engine.calls[0][2] == "default-voice"
