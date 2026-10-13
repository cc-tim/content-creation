from __future__ import annotations

import json
from pathlib import Path

import pytest
from structlog.testing import capture_logs

from pipeline.voices.base import VoiceEngine, VoiceEngineUnavailable, VoiceNotFound, VoiceProfile
from pipeline.voices.edge_engine import EdgeEngine
from pipeline.voices.fallback_engine import FallbackEngine
from pipeline.voices.kokoro_engine import KokoroEngine
from pipeline.voices.prerecorded_engine import PrerecordedEngine
from pipeline.voices.registry import VoiceRegistry


class _ScriptedEngine(VoiceEngine):
    """Writes its tag to out_path, or raises the next scripted error."""

    def __init__(self, tag: str, errors: list[Exception | None] | None = None) -> None:
        self.tag = tag
        self.errors = list(errors or [])
        self.calls: list[str] = []

    @property
    def name(self) -> str:
        return self.tag

    def synthesize(self, text, out_path, profile, scene_id=None):
        self.calls.append(text)
        err = self.errors.pop(0) if self.errors else None
        if err is not None:
            raise err
        out_path.write_text(self.tag)
        return out_path


_PRIMARY = VoiceProfile(id="zh-TW-default-f", engine="edge", locale="zh-TW",
                        params={"voice": "zh-TW-HsiaoChenNeural"})
_FALLBACK = VoiceProfile(id="zh-TW-kokoro-f", engine="kokoro", locale="zh-TW",
                         params={"sid": 3})


def _engine(primary: _ScriptedEngine, fallback: _ScriptedEngine) -> FallbackEngine:
    return FallbackEngine(primary=primary, fallback=fallback, fallback_profile=_FALLBACK)


def test_fallback_engine_uses_primary_while_it_works(tmp_path):
    primary, fallback = _ScriptedEngine("edge"), _ScriptedEngine("kokoro")
    with capture_logs() as logs:
        out = _engine(primary, fallback).synthesize("一。", tmp_path / "a.mp3", _PRIMARY)
    assert out.read_text() == "edge"
    assert fallback.calls == []
    assert [e for e in logs if e["log_level"] == "error"] == []


def test_fallback_engine_engages_loudly_when_primary_fails_first(tmp_path):
    primary = _ScriptedEngine("edge", [VoiceEngineUnavailable("edge refused synthesis (HTTP 403)")])
    fallback = _ScriptedEngine("kokoro")
    with capture_logs() as logs:
        out = _engine(primary, fallback).synthesize(
            "一。", tmp_path / "a.mp3", _PRIMARY, scene_id="s1"
        )
    assert out.read_text() == "kokoro"
    engaged = [e for e in logs if e["event"] == "tts.fallback.engaged"]
    assert len(engaged) == 1
    assert engaged[0]["log_level"] == "error"
    assert engaged[0]["primary_voice"] == "zh-TW-default-f"
    assert engaged[0]["fallback_voice"] == "zh-TW-kokoro-f"
    assert "403" in engaged[0]["error"]


def test_fallback_engine_stays_on_fallback_for_the_rest_of_the_pass(tmp_path):
    primary = _ScriptedEngine("edge", [VoiceEngineUnavailable("403")])
    fallback = _ScriptedEngine("kokoro")
    engine = _engine(primary, fallback)
    engine.synthesize("一。", tmp_path / "a.mp3", _PRIMARY)
    out = engine.synthesize("二。", tmp_path / "b.mp3", _PRIMARY)
    assert out.read_text() == "kokoro"
    assert primary.calls == ["一。"]
    assert fallback.calls == ["一。", "二。"]


def test_fallback_engine_refuses_to_mix_voices_mid_pass(tmp_path):
    primary = _ScriptedEngine("edge", [None, VoiceEngineUnavailable("503")])
    fallback = _ScriptedEngine("kokoro")
    engine = _engine(primary, fallback)
    engine.synthesize("一。", tmp_path / "a.mp3", _PRIMARY)
    with pytest.raises(RuntimeError, match="mix") as excinfo:
        engine.synthesize("二。", tmp_path / "b.mp3", _PRIMARY, scene_id="s2")
    assert "--voice zh-TW-kokoro-f" in str(excinfo.value)
    assert fallback.calls == []


def test_fallback_engine_reports_both_failures(tmp_path):
    primary = _ScriptedEngine("edge", [VoiceEngineUnavailable("403 from bing")])
    fallback = _ScriptedEngine("kokoro", [FileNotFoundError("Kokoro model not found")])
    with pytest.raises(RuntimeError) as excinfo:
        _engine(primary, fallback).synthesize("一。", tmp_path / "a.mp3", _PRIMARY)
    assert "403 from bing" in str(excinfo.value)
    assert "Kokoro model not found" in str(excinfo.value)


@pytest.mark.parametrize(
    "error",
    [ValueError("edge voice profile x is missing params.voice"), RuntimeError("No audio")],
    ids=["config-bug", "text-specific"],
)
def test_fallback_engine_lets_unclassified_failures_propagate(tmp_path, error):
    """Only VoiceEngineUnavailable means the service is down; anything else is a real bug."""
    primary = _ScriptedEngine("edge", [error])
    fallback = _ScriptedEngine("kokoro")
    with capture_logs() as logs, pytest.raises(type(error)):
        _engine(primary, fallback).synthesize("一。", tmp_path / "a.mp3", _PRIMARY)
    assert fallback.calls == []
    assert [e for e in logs if e["event"] == "tts.fallback.engaged"] == []


# ---- registry wiring ----


def _registry(tmp_path: Path, voices: list[dict]) -> VoiceRegistry:
    (tmp_path / "registry.json").write_text(json.dumps({"voices": voices}), encoding="utf-8")
    return VoiceRegistry(tmp_path)


_EDGE_WITH_FALLBACK = {
    "id": "zh-TW-default-f", "engine": "edge", "locale": "zh-TW",
    "params": {"voice": "zh-TW-HsiaoChenNeural", "fallback_voice_id": "zh-TW-kokoro-f"},
}
_KOKORO = {"id": "zh-TW-kokoro-f", "engine": "kokoro", "locale": "zh-TW", "params": {"sid": 3}}


def test_registry_wraps_a_voice_that_names_a_fallback(tmp_path):
    engine, profile = _registry(tmp_path, [_EDGE_WITH_FALLBACK, _KOKORO]).resolve(
        "zh-TW-default-f"
    )
    assert isinstance(engine, FallbackEngine)
    assert isinstance(engine.primary, EdgeEngine)
    assert isinstance(engine.fallback, KokoroEngine)
    assert engine.fallback_profile.id == "zh-TW-kokoro-f"
    assert profile.id == "zh-TW-default-f"


def test_registry_default_voice_gets_the_fallback_too(tmp_path):
    engine, _ = _registry(tmp_path, [_EDGE_WITH_FALLBACK, _KOKORO]).default_for_locale("zh-TW")
    assert isinstance(engine, FallbackEngine)


def test_registry_auto_fallback_can_be_switched_off(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPELINE_TTS_AUTO_FALLBACK", "false")
    engine, _ = _registry(tmp_path, [_EDGE_WITH_FALLBACK, _KOKORO]).resolve("zh-TW-default-f")
    assert isinstance(engine, EdgeEngine)


def test_registry_unknown_fallback_voice_fails_at_resolve(tmp_path):
    with pytest.raises(VoiceNotFound, match="zh-TW-kokoro-f"):
        _registry(tmp_path, [_EDGE_WITH_FALLBACK]).resolve("zh-TW-default-f")


def test_registry_leaves_prerecorded_fallback_to_the_prerecorded_engine(tmp_path):
    prerecorded = {
        "id": "tim-zhtw", "engine": "prerecorded", "locale": "zh-TW",
        "params": {"recording_dir": "r", "fallback_voice_id": "zh-TW-kokoro-f"},
    }
    engine, _ = _registry(tmp_path, [prerecorded, _KOKORO]).resolve("tim-zhtw")
    assert isinstance(engine, PrerecordedEngine)


# ---- shipped registry ----

_REPO_VOICES = Path(__file__).resolve().parents[2] / "voices"


@pytest.mark.parametrize(
    ("voice_id", "fallback_id"),
    [
        ("zh-TW-default-f", "zh-TW-kokoro-f"),
        ("zh-TW-default-f2", "zh-TW-kokoro-f"),
        ("zh-TW-default-m", "zh-TW-kokoro-m"),
    ],
)
def test_shipped_zh_tw_edge_voices_fall_back_to_local_kokoro(voice_id, fallback_id):
    engine, _ = VoiceRegistry(_REPO_VOICES).resolve(voice_id)
    assert isinstance(engine, FallbackEngine)
    assert isinstance(engine.fallback, KokoroEngine)
    assert engine.fallback_profile.id == fallback_id
