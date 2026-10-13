from __future__ import annotations

import subprocess
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from pipeline.voices.base import VoiceEngine, VoiceProfile

_INSTALL_HINT = "run scripts/install_kokoro_tts.sh (downloads ~350 MB, one time per machine)"


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


def _default_tts_factory(model_dir: Path) -> Any:
    if not (model_dir / "model.onnx").exists():
        raise FileNotFoundError(f"Kokoro model not found in {model_dir}; {_INSTALL_HINT}")
    return _load_sherpa_kokoro(model_dir)


def _write_mp3(samples: Any, sample_rate: int, out_path: Path) -> None:
    """Encode mono float samples as a header-free CBR MP3, like edge-tts writes.

    TtsStage joins segment MP3s by byte concatenation, so no Xing/ID3 frames.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.asarray(samples, dtype="<f4").tobytes()
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "f32le", "-ar", str(sample_rate), "-ac", "1", "-i", "pipe:0",
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
        audio = self._tts.generate(text, sid=int(sid), speed=speed)
        if len(audio.samples) == 0:
            raise RuntimeError(f"kokoro returned no audio for {profile.id}: {text[:40]!r}")

        _write_mp3(audio.samples, audio.sample_rate, out_path)
        return out_path
