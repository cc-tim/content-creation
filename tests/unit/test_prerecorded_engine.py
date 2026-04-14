from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pipeline.voices.base import VoiceProfile
from pipeline.voices.prerecorded_engine import PrerecordedEngine


def _mk_profile(tmp_path: Path, fallback: str | None = "zh-TW-default-f") -> VoiceProfile:
    rec_dir = tmp_path / "rec"
    rec_dir.mkdir()
    params = {"recording_dir": str(rec_dir)}
    if fallback is not None:
        params["fallback_voice_id"] = fallback
    return VoiceProfile(
        id="tim-zhtw",
        engine="prerecorded",
        locale="zh-TW",
        params=params,
    )


class _FakeFallbackEngine:
    @property
    def name(self) -> str:
        return "edge"

    def synthesize(self, text, out_path, profile, scene_id=None):
        Path(out_path).write_bytes(b"fallback-mp3")
        self.last = (text, out_path, profile.id, scene_id)
        return out_path


class _FakeRegistry:
    def __init__(self, fallback_profile: VoiceProfile):
        self._fallback_profile = fallback_profile
        self._fallback_engine = _FakeFallbackEngine()

    def resolve(self, voice_id):
        return self._fallback_engine, self._fallback_profile

    def default_for_locale(self, locale):
        return self._fallback_engine, self._fallback_profile


def _fallback_profile():
    return VoiceProfile(
        id="zh-TW-default-f",
        engine="edge",
        locale="zh-TW",
        params={"voice": "zh-TW-HsiaoChenNeural"},
    )


def test_requires_scene_id(tmp_path):
    engine = PrerecordedEngine(registry=_FakeRegistry(_fallback_profile()))
    with pytest.raises(ValueError, match="scene_id"):
        engine.synthesize("你好", tmp_path / "out.mp3", _mk_profile(tmp_path), scene_id=None)


def test_missing_recording_delegates_to_fallback(tmp_path):
    reg = _FakeRegistry(_fallback_profile())
    engine = PrerecordedEngine(registry=reg)
    out = tmp_path / "out.mp3"
    engine.synthesize("你好", out, _mk_profile(tmp_path), scene_id="scene_001")
    assert out.read_bytes() == b"fallback-mp3"
    assert reg._fallback_engine.last[3] == "scene_001"


def test_missing_fallback_voice_id_uses_default_for_locale(tmp_path):
    fb_prof = _fallback_profile()
    reg = _FakeRegistry(fb_prof)
    called = {}
    orig = reg.default_for_locale

    def spy(locale):
        called["locale"] = locale
        return orig(locale)

    reg.default_for_locale = spy

    engine = PrerecordedEngine(registry=reg)
    out = tmp_path / "out.mp3"
    engine.synthesize(
        "你好", out, _mk_profile(tmp_path, fallback=None), scene_id="scene_001"
    )
    assert called["locale"] == "zh-TW"


def test_found_recording_transcodes_and_writes_snapshot(tmp_path, monkeypatch):
    profile = _mk_profile(tmp_path)
    rec_dir = Path(profile.params["recording_dir"])
    (rec_dir / "scene_001.wav").write_bytes(b"RIFF-stub")

    fake_transcode = MagicMock()
    monkeypatch.setattr(
        "pipeline.voices.prerecorded_engine._transcode_to_mp3",
        fake_transcode,
    )

    engine = PrerecordedEngine(registry=_FakeRegistry(_fallback_profile()))
    out = tmp_path / "out.mp3"
    engine.synthesize("你好", out, profile, scene_id="scene_001")

    fake_transcode.assert_called_once()
    src_arg, dst_arg = fake_transcode.call_args[0]
    assert src_arg == rec_dir / "scene_001.wav"
    assert dst_arg == out
    assert (rec_dir / "scene_001.txt").read_text(encoding="utf-8").strip() == "你好"


def test_found_recording_with_matching_snapshot_no_warning(tmp_path, monkeypatch, caplog):
    import logging

    profile = _mk_profile(tmp_path)
    rec_dir = Path(profile.params["recording_dir"])
    (rec_dir / "scene_001.wav").write_bytes(b"RIFF-stub")
    (rec_dir / "scene_001.txt").write_text("你好\n", encoding="utf-8")

    monkeypatch.setattr(
        "pipeline.voices.prerecorded_engine._transcode_to_mp3",
        lambda src, dst: dst.write_bytes(b"mp3"),
    )

    caplog.set_level(logging.WARNING)
    engine = PrerecordedEngine(registry=_FakeRegistry(_fallback_profile()))
    engine.synthesize("你好", tmp_path / "out.mp3", profile, scene_id="scene_001")
    assert "stale_recording" not in caplog.text


def test_found_recording_with_drifted_snapshot_emits_warning(
    tmp_path, monkeypatch, caplog
):
    import logging

    profile = _mk_profile(tmp_path)
    rec_dir = Path(profile.params["recording_dir"])
    (rec_dir / "scene_001.wav").write_bytes(b"RIFF-stub")
    (rec_dir / "scene_001.txt").write_text("原始文字", encoding="utf-8")

    monkeypatch.setattr(
        "pipeline.voices.prerecorded_engine._transcode_to_mp3",
        lambda src, dst: dst.write_bytes(b"mp3"),
    )

    caplog.set_level(logging.WARNING)
    engine = PrerecordedEngine(registry=_FakeRegistry(_fallback_profile()))
    engine.synthesize("新文字", tmp_path / "out.mp3", profile, scene_id="scene_001")
    assert "stale_recording" in caplog.text


def test_missing_recording_dir_param_raises(tmp_path):
    profile = VoiceProfile(
        id="tim-zhtw",
        engine="prerecorded",
        locale="zh-TW",
        params={},  # missing recording_dir
    )
    engine = PrerecordedEngine(registry=_FakeRegistry(_fallback_profile()))
    with pytest.raises(ValueError, match="recording_dir"):
        engine.synthesize("你好", tmp_path / "out.mp3", profile, scene_id="scene_001")
