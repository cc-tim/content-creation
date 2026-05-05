from __future__ import annotations

import json

import pytest

from pipeline.voices.base import VoiceEngine, VoiceNotFound, VoiceProfile
from pipeline.voices.edge_engine import EdgeEngine
from pipeline.voices.registry import VoiceRegistry


def test_voice_profile_from_dict_minimum():
    profile = VoiceProfile.from_dict(
        {
            "id": "zh-TW-default-f",
            "engine": "edge",
            "locale": "zh-TW",
            "params": {"voice": "zh-TW-HsiaoChenNeural"},
        }
    )
    assert profile.id == "zh-TW-default-f"
    assert profile.engine == "edge"
    assert profile.locale == "zh-TW"
    assert profile.params == {"voice": "zh-TW-HsiaoChenNeural"}
    assert profile.reference_path is None


def test_voice_profile_with_reference(tmp_path):
    ref = tmp_path / "sample.wav"
    ref.write_bytes(b"RIFFWAVE-stub")
    profile = VoiceProfile.from_dict(
        {
            "id": "tim-zhtw",
            "engine": "edge",
            "locale": "zh-TW",
            "reference": str(ref),
            "reference_text": "大家好",
            "params": {},
        }
    )
    assert profile.reference_path == ref
    assert profile.reference_text == "大家好"


def test_voice_engine_is_abstract():
    with pytest.raises(TypeError):
        VoiceEngine()  # type: ignore[abstract]


# ---- VoiceRegistry tests ----


def _seed_registry(tmp_path) -> VoiceRegistry:
    voices_dir = tmp_path / "voices"
    voices_dir.mkdir()
    (voices_dir / "registry.json").write_text(
        json.dumps(
            {
                "voices": [
                    {
                        "id": "zh-TW-default-f",
                        "engine": "edge",
                        "locale": "zh-TW",
                        "params": {"voice": "zh-TW-HsiaoChenNeural"},
                        "display_name": "HsiaoChen (default)",
                    }
                ]
            }
        )
    )
    return VoiceRegistry(voices_dir)


def test_registry_lists_built_in_voice(tmp_path):
    registry = _seed_registry(tmp_path)
    profiles = registry.list()
    assert [p.id for p in profiles] == ["zh-TW-default-f"]


def test_registry_resolve_returns_engine_and_profile(tmp_path):
    registry = _seed_registry(tmp_path)
    engine, profile = registry.resolve("zh-TW-default-f")
    assert isinstance(engine, EdgeEngine)
    assert profile.locale == "zh-TW"


def test_registry_resolve_missing_raises(tmp_path):
    registry = _seed_registry(tmp_path)
    try:
        registry.resolve("nonexistent")
    except VoiceNotFound:
        return
    raise AssertionError("expected VoiceNotFound")


def test_registry_default_by_locale(tmp_path):
    registry = _seed_registry(tmp_path)
    engine, profile = registry.default_for_locale("zh-TW")
    assert profile.id == "zh-TW-default-f"


def test_registry_add_and_save(tmp_path):
    registry = _seed_registry(tmp_path)
    added = registry.add(
        {
            "id": "tim-zhtw",
            "engine": "edge",
            "locale": "zh-TW",
            "params": {},
            "reference": str(tmp_path / "voices" / "cloned" / "tim.wav"),
            "reference_text": "測試",
            "display_name": "Tim (clone)",
        }
    )
    assert added.id == "tim-zhtw"
    registry.save()

    # Re-load from disk to prove it persisted.
    reloaded = VoiceRegistry(tmp_path / "voices")
    assert any(p.id == "tim-zhtw" for p in reloaded.list())


def test_edge_engine_accepts_optional_scene_id(tmp_path, monkeypatch):
    """EdgeEngine ignores scene_id but must not reject it."""

    async def fake_run(cls, text, voice, out_path):
        out_path.write_bytes(b"fake-mp3")

    monkeypatch.setattr(EdgeEngine, "_run", classmethod(fake_run))

    profile = VoiceProfile(
        id="t",
        engine="edge",
        locale="zh-TW",
        params={"voice": "zh-TW-HsiaoChenNeural"},
    )
    out = tmp_path / "a.mp3"
    # Must not raise:
    EdgeEngine().synthesize("你好", out, profile, scene_id="scene_001")
    assert out.exists()


def test_registry_resolves_prerecorded_engine(tmp_path):
    from pipeline.voices.prerecorded_engine import PrerecordedEngine
    from pipeline.voices.registry import VoiceRegistry

    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        '{"voices": [{"id": "tim-zhtw", "engine": "prerecorded", '
        '"locale": "zh-TW", "params": {"recording_dir": "r"}}, '
        '{"id": "zh-TW-default-f", "engine": "edge", "locale": "zh-TW", '
        '"params": {"voice": "zh-TW-HsiaoChenNeural"}}]}',
        encoding="utf-8",
    )
    registry = VoiceRegistry(tmp_path)
    engine, profile = registry.resolve("tim-zhtw")
    assert isinstance(engine, PrerecordedEngine)
    assert profile.id == "tim-zhtw"


def test_registry_rejects_cosyvoice_engine(tmp_path):
    from pipeline.voices.base import VoiceNotFound
    from pipeline.voices.registry import VoiceRegistry

    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        '{"voices": [{"id": "gone", "engine": "cosyvoice", '
        '"locale": "zh-TW", "params": {}}]}',
        encoding="utf-8",
    )
    registry = VoiceRegistry(tmp_path)
    with pytest.raises(VoiceNotFound, match="unknown engine 'cosyvoice'"):
        registry.resolve("gone")
