from __future__ import annotations

import logging
from pathlib import Path

from pipeline.voices.base import VoiceEngine, VoiceProfile

logger = logging.getLogger(__name__)

_MODEL = None  # module-level cache to avoid reloading between scenes


def _load_model():
    """Lazy import + load CosyVoice2. Heavy — cached after first call."""
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    try:
        from cosyvoice.cli.cosyvoice import CosyVoice2  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "CosyVoice2 is not installed. Run scripts/install_cosyvoice.sh first."
        ) from exc
    logger.info("loading CosyVoice2 model (one-time, ~seconds)")
    _MODEL = CosyVoice2("pretrained_models/CosyVoice2-0.5B", load_jit=False)
    return _MODEL


def _load_audio(path: Path):
    """Load a WAV file as a tensor. Lazy-imports torchaudio."""
    import torchaudio  # lazy

    return torchaudio.load(str(path))


def _save_tensor(tensor, out_path: Path, sample_rate: int = 24000) -> None:
    import torchaudio  # lazy

    torchaudio.save(str(out_path), tensor, sample_rate)


class CosyVoiceEngine(VoiceEngine):
    @property
    def name(self) -> str:
        return "cosyvoice"

    def synthesize(self, text: str, out_path: Path, profile: VoiceProfile) -> Path:
        if profile.reference_path is None:
            raise ValueError(
                f"cosyvoice profile {profile.id} requires a reference audio file"
            )
        if not profile.reference_path.exists():
            raise FileNotFoundError(
                f"reference audio not found for {profile.id}: {profile.reference_path}"
            )

        model = _load_model()
        prompt_audio, _sr = _load_audio(profile.reference_path)

        result_tensor = None
        for chunk in model.inference_zero_shot(
            text,
            profile.reference_text or "",
            prompt_audio,
            stream=False,
        ):
            piece = chunk["tts_speech"]
            result_tensor = piece if result_tensor is None else _concat(result_tensor, piece)

        if result_tensor is None:
            raise RuntimeError("CosyVoice2 produced no audio output")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        _save_tensor(result_tensor, out_path)
        return out_path


def _concat(a, b):
    import torch  # lazy

    return torch.cat([a, b], dim=-1)
