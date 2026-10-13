from __future__ import annotations

import subprocess
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from pipeline.voices.base import VoiceEngine, VoiceProfile

_INSTALL_HINT = "run scripts/install_kokoro_tts.sh (downloads ~350 MB, one time per machine)"

# Characters the zh frontend drops but that have a plain reading.
_READING_FIXES = str.maketrans({"〇": "零"})


@lru_cache(maxsize=1)
def _taiwan_to_simplified() -> Any:
    from opencc import OpenCC

    return OpenCC("tw2s")


def _prepare_text(text: str) -> str:
    """Text as the Kokoro zh frontend reads it right.

    Its lexicon has Simplified multi-character words only, so Traditional text falls back
    to per-character readings (銀行 → yín xíng). tw2s converts character variants only, so
    Taiwan vocabulary (影片, 軟體) is still what gets said. Subtitles keep the original text.
    """
    return _taiwan_to_simplified().convert(text.translate(_READING_FIXES))


@lru_cache(maxsize=2)
def _load_sherpa_kokoro(model_dir: Path) -> Any:
    """Build a sherpa-onnx OfflineTts for the kokoro-multi-lang-v1_1 bundle (zh + en)."""
    import sherpa_onnx

    m = model_dir
    config = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
                model=str(m / "model.onnx"),
                voices=str(m / "voices.bin"),
                tokens=str(m / "tokens.txt"),
                data_dir=str(m / "espeak-ng-data"),
                dict_dir=str(m / "dict"),
                lexicon=f"{m / 'lexicon-us-en.txt'},{m / 'lexicon-zh.txt'}",
            ),
            num_threads=4,
            provider="cpu",
        ),
        # Spoken forms for dates, phone numbers and digits ("2024年", "5個").
        rule_fsts=f"{m / 'date-zh.fst'},{m / 'phone-zh.fst'},{m / 'number-zh.fst'}",
        max_num_sentences=1,
    )
    return sherpa_onnx.OfflineTts(config)


# Everything _load_sherpa_kokoro points sherpa-onnx at. sherpa exits the whole process
# (exit 255 from C++) on a missing or empty file, so check them in Python first.
_BUNDLE_FILES = (
    "model.onnx", "voices.bin", "tokens.txt", "lexicon-us-en.txt", "lexicon-zh.txt",
    "date-zh.fst", "phone-zh.fst", "number-zh.fst",
)
_BUNDLE_DIRS = ("dict", "espeak-ng-data")


def _default_tts_factory(model_dir: Path) -> Any:
    missing = [
        *(f for f in _BUNDLE_FILES if not (model_dir / f).is_file()
          or (model_dir / f).stat().st_size == 0),
        *(d for d in _BUNDLE_DIRS if not (model_dir / d).is_dir()),
    ]
    if missing:
        raise FileNotFoundError(
            f"Kokoro bundle in {model_dir} is incomplete, missing: {', '.join(missing)}; "
            f"{_INSTALL_HINT}"
        )
    return _load_sherpa_kokoro(model_dir)


# Edge's default voice (HsiaoChen) measures -19 LUFS; Kokoro comes out 4-8 LU quieter.
_TARGET_LUFS = -19.0


def _write_mp3(samples: Any, sample_rate: int, out_path: Path) -> None:
    """Encode mono float samples as a header-free CBR MP3 at edge-tts loudness.

    TtsStage joins segment MP3s by byte concatenation, so no Xing/ID3 frames. Single-pass
    loudnorm (as utils/audio.py uses for narration) lands within ~1 LU of the target.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.asarray(samples, dtype="<f4").tobytes()
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "f32le", "-ar", str(sample_rate), "-ac", "1", "-i", "pipe:0",
            "-af", f"loudnorm=I={_TARGET_LUFS}:TP=-1.5:LRA=11", "-ar", str(sample_rate),
            "-c:a", "libmp3lame", "-b:a", "96k",
            "-write_xing", "0", "-id3v2_version", "0", "-write_id3v1", "0",
            str(out_path),
        ],
        input=pcm,
        check=True,
        capture_output=True,
    )


class KokoroEngine(VoiceEngine):
    """Local Kokoro-82M v1.1-zh (Apache-2.0) through sherpa-onnx: CPU, offline, no API.

    Mandarin speakers with a mainland accent; English words go through its en lexicon.
    `params.sid` picks the speaker (3 = zf_001, 59 = zm_010).
    """

    def __init__(
        self,
        model_dir: Path,
        tts_factory: Callable[[Path], Any] | None = None,
    ) -> None:
        self._model_dir = Path(model_dir).expanduser()
        self._tts_factory = tts_factory or _default_tts_factory
        self._tts: Any = None

    @property
    def name(self) -> str:
        return "kokoro"

    def synthesize(
        self,
        text: str,
        out_path: Path,
        profile: VoiceProfile,
        scene_id: str | None = None,
    ) -> Path:
        _ = scene_id  # unused: kokoro voices are scene-agnostic
        sid = profile.params.get("sid")
        if sid is None:
            raise ValueError(f"kokoro voice profile {profile.id} is missing params.sid")
        speed = float(profile.params.get("speed", 1.0))

        if self._tts is None:
            self._tts = self._tts_factory(self._model_dir)
        audio = self._tts.generate(_prepare_text(text), sid=int(sid), speed=speed)
        if len(audio.samples) == 0:
            raise RuntimeError(f"kokoro returned no audio for {profile.id}: {text[:40]!r}")

        _write_mp3(audio.samples, audio.sample_rate, out_path)
        return out_path
