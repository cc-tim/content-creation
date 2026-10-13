from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from pipeline.voices.base import VoiceProfile
from pipeline.voices.kokoro_engine import KokoroEngine

_SR = 24000


@dataclass
class _FakeAudio:
    samples: list[float]
    sample_rate: int = _SR


@dataclass
class _FakeTts:
    samples: list[float]
    calls: list[tuple[str, int, float]] = field(default_factory=list)

    def generate(self, text: str, sid: int = 0, speed: float = 1.0) -> _FakeAudio:
        self.calls.append((text, sid, speed))
        return _FakeAudio(self.samples)


def _tone(seconds: float) -> list[float]:
    return [0.3 * math.sin(2 * math.pi * 220 * i / _SR) for i in range(int(seconds * _SR))]


def _profile(**params) -> VoiceProfile:
    return VoiceProfile(id="zh-TW-kokoro-f", engine="kokoro", locale="zh-TW", params=params)


def _duration_sec(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def test_kokoro_engine_writes_mp3_of_the_generated_speech(tmp_path):
    fake = _FakeTts(_tone(0.5))
    engine = KokoroEngine(model_dir=tmp_path, tts_factory=lambda _dir: fake)
    out = tmp_path / "audio" / "segment_000.mp3"

    result = engine.synthesize("你好，世界。", out, _profile(sid=3), scene_id="s1")

    assert result == out
    assert fake.calls == [("你好，世界。", 3, 1.0)]
    assert _duration_sec(out) == pytest.approx(0.5, abs=0.08)


def test_kokoro_engine_passes_profile_speed(tmp_path):
    fake = _FakeTts(_tone(0.2))
    engine = KokoroEngine(model_dir=tmp_path, tts_factory=lambda _dir: fake)

    engine.synthesize("你好。", tmp_path / "a.mp3", _profile(sid=59, speed=0.9))

    assert fake.calls == [("你好。", 59, 0.9)]


def test_kokoro_engine_requires_sid(tmp_path):
    engine = KokoroEngine(model_dir=tmp_path, tts_factory=lambda _dir: _FakeTts(_tone(0.1)))
    with pytest.raises(ValueError, match="params.sid"):
        engine.synthesize("你好。", tmp_path / "a.mp3", _profile())


def test_kokoro_engine_refuses_empty_audio(tmp_path):
    engine = KokoroEngine(model_dir=tmp_path, tts_factory=lambda _dir: _FakeTts([]))
    out = tmp_path / "a.mp3"
    with pytest.raises(RuntimeError, match="no audio"):
        engine.synthesize("你好。", out, _profile(sid=3))
    assert not out.exists()


def test_kokoro_engine_loads_the_model_once_per_engine(tmp_path):
    loads: list[Path] = []
    fake = _FakeTts(_tone(0.1))

    def factory(model_dir: Path) -> _FakeTts:
        loads.append(model_dir)
        return fake

    engine = KokoroEngine(model_dir=tmp_path, tts_factory=factory)
    engine.synthesize("一。", tmp_path / "a.mp3", _profile(sid=3))
    engine.synthesize("二。", tmp_path / "b.mp3", _profile(sid=3))

    assert loads == [tmp_path]


def test_kokoro_engine_missing_model_says_how_to_install(tmp_path):
    engine = KokoroEngine(model_dir=tmp_path / "not-downloaded")
    with pytest.raises(FileNotFoundError, match="install_kokoro_tts.sh"):
        engine.synthesize("你好。", tmp_path / "a.mp3", _profile(sid=3))


def test_kokoro_engine_reads_traditional_text_as_simplified(tmp_path):
    """The bundle's zh lexicon has Simplified words only: 銀行 alone was read yín-xíng."""
    fake = _FakeTts(_tone(0.2))
    engine = KokoroEngine(model_dir=tmp_path, tts_factory=lambda _dir: fake)

    engine.synthesize("他去銀行領錢，長大後還會來。", tmp_path / "a.mp3", _profile(sid=3))

    assert fake.calls[0][0] == "他去银行领钱，长大后还会来。"


def test_kokoro_engine_keeps_taiwan_vocabulary(tmp_path):
    """Character variants only (tw2s): no 影片→视频 style word swaps change what is said."""
    fake = _FakeTts(_tone(0.2))
    engine = KokoroEngine(model_dir=tmp_path, tts_factory=lambda _dir: fake)

    engine.synthesize("打開軟體看影片。", tmp_path / "a.mp3", _profile(sid=3))

    assert fake.calls[0][0] == "打开软体看影片。"


def test_kokoro_engine_voices_the_zero_numeral(tmp_path):
    """〇 is not in the lexicon and was dropped silently (二〇二四 → 二二四)."""
    fake = _FakeTts(_tone(0.2))
    engine = KokoroEngine(model_dir=tmp_path, tts_factory=lambda _dir: fake)

    engine.synthesize("二〇二四年", tmp_path / "a.mp3", _profile(sid=3))

    assert fake.calls[0][0] == "二零二四年"


def _integrated_lufs(path: Path) -> float:
    import re

    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
        capture_output=True, text=True, check=True,
    )
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", out.stderr)[-1])


@pytest.mark.parametrize("seconds", [1.5, 6.0])
def test_kokoro_engine_output_matches_edge_loudness(tmp_path, seconds):
    """Kokoro came out ~6 LU under edge (-19 LUFS), below the music bed's sidechain threshold."""
    quiet = [0.1 * x for x in _tone(seconds)]  # ~-30 LUFS
    engine = KokoroEngine(model_dir=tmp_path, tts_factory=lambda _dir: _FakeTts(quiet))
    out = tmp_path / "a.mp3"

    engine.synthesize("你好。", out, _profile(sid=3))

    assert _integrated_lufs(out) == pytest.approx(-19.0, abs=1.5)
