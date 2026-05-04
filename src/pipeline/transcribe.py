"""OpenAI Whisper API wrapper for browser-recorded narration audio.

Used by the dashboard's narration-source modal: after a user records via the
browser MediaRecorder API and uploads the WAV, the dashboard calls Whisper to
produce a transcript and shows a diff against the storyboard's existing
narration text. The user accepts or rejects the transcript before any
storyboard mutation lands.

Single function only. No SDK dep — direct httpx POST to the multipart endpoint.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import structlog

logger = structlog.get_logger()

_ENDPOINT = "https://api.openai.com/v1/audio/transcriptions"
_MODEL = "whisper-1"


def transcribe_audio(audio_path: Path, *, language: str, api_key: str, timeout: float = 60.0) -> str:
    """Transcribe a local audio file using OpenAI Whisper API.

    `language` is an ISO 639-1 code (e.g. "zh", "ja", "es"). Whisper accepts
    the locale-style "zh-TW" and similar but the simpler form is recommended.

    Returns the transcript text. Raises:
      - FileNotFoundError if audio_path doesn't exist.
      - ValueError if api_key is empty.
      - Whatever httpx.HTTPStatusError chain `raise_for_status` raises on
        non-2xx responses.
    """
    if not api_key:
        raise ValueError("OPENAI_API_KEY is empty; cannot call Whisper")
    if not audio_path.exists():
        raise FileNotFoundError(f"audio file not found: {audio_path}")

    logger.info("transcribe.start", path=str(audio_path), language=language)
    with audio_path.open("rb") as fh:
        response = httpx.post(
            _ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}"},
            data={"model": _MODEL, "language": language},
            files={"file": (audio_path.name, fh, "audio/wav")},
            timeout=timeout,
        )
    response.raise_for_status()
    text = str(response.json().get("text", ""))
    logger.info("transcribe.complete", chars=len(text))
    return text
