from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pipeline.utils.audio import normalize_to_wav


def _make_test_audio(path: Path, *, duration: float, frequency: int) -> Path:
    """Create a small sine-wave audio file (any container ffmpeg supports)."""
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration={duration}",
         "-c:a", "libmp3lame", str(path)],
        check=True,
    )
    return path


def test_normalize_to_wav_emits_48k_stereo_wav(tmp_path: Path):
    src = _make_test_audio(tmp_path / "src.mp3", duration=1.0, frequency=440)
    dst = tmp_path / "out.wav"
    normalize_to_wav(src, dst)

    assert dst.exists() and dst.stat().st_size > 0
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=codec_name,sample_rate,channels",
         "-of", "default=noprint_wrappers=1", str(dst)],
        capture_output=True, text=True, check=True,
    )
    assert "codec_name=pcm_s16le" in probe.stdout
    assert "sample_rate=48000" in probe.stdout
    assert "channels=2" in probe.stdout


def test_normalize_to_wav_creates_parent_dir(tmp_path: Path):
    src = _make_test_audio(tmp_path / "src.mp3", duration=0.5, frequency=440)
    dst = tmp_path / "deep" / "nested" / "out.wav"
    normalize_to_wav(src, dst)
    assert dst.exists()


def test_normalize_to_wav_raises_on_missing_source(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        normalize_to_wav(tmp_path / "missing.mp3", tmp_path / "out.wav")


def test_normalize_to_wav_handles_webm_input(tmp_path: Path):
    """Browser recorders produce opus-in-webm; verify we can normalize that."""
    src = tmp_path / "src.webm"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1.0",
         "-c:a", "libopus", str(src)],
        check=True,
    )
    dst = tmp_path / "out.wav"
    normalize_to_wav(src, dst)
    assert dst.exists() and dst.stat().st_size > 0
