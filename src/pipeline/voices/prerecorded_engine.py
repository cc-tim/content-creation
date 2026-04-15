from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from pipeline.voices.base import VoiceEngine, VoiceProfile

if TYPE_CHECKING:
    from pipeline.voices.registry import VoiceRegistry

logger = logging.getLogger(__name__)

_SUPPORTED_EXTS = (".wav", ".mp3", ".m4a")


def _transcode_to_mp3(src: Path, dst: Path) -> None:
    """Transcode any ffmpeg-readable audio to MP3 at dst."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-c:a",
            "libmp3lame",
            "-q:a",
            "2",
            str(dst),
        ],
        check=True,
        capture_output=True,
    )


def _find_recording(recording_dir: Path, scene_id: str) -> Path | None:
    for ext in _SUPPORTED_EXTS:
        candidate = recording_dir / f"{scene_id}{ext}"
        if candidate.exists():
            return candidate
    return None


class PrerecordedEngine(VoiceEngine):
    """Looks up scene-keyed recordings; falls back to another voice on miss."""

    def __init__(self, registry: VoiceRegistry):
        self._registry = registry

    @property
    def name(self) -> str:
        return "prerecorded"

    def synthesize(
        self,
        text: str,
        out_path: Path,
        profile: VoiceProfile,
        scene_id: str | None = None,
    ) -> Path:
        if scene_id is None:
            raise ValueError("PrerecordedEngine requires scene_id; invoke via TtsStage")

        recording_dir_str = profile.params.get("recording_dir")
        if not recording_dir_str:
            raise ValueError(f"prerecorded profile {profile.id} missing params.recording_dir")
        recording_dir = Path(recording_dir_str)

        src = _find_recording(recording_dir, scene_id)

        if src is not None:
            self._handle_snapshot(recording_dir, scene_id, text)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            _transcode_to_mp3(src, out_path)
            logger.info(
                "prerecorded.used",
                extra={"scene_id": scene_id, "src": str(src)},
            )
            return out_path

        fallback_engine, fallback_profile = self._resolve_fallback(profile)
        logger.info(
            "prerecorded.fallback",
            extra={
                "scene_id": scene_id,
                "fallback_voice_id": fallback_profile.id,
            },
        )
        return fallback_engine.synthesize(text, out_path, fallback_profile, scene_id=scene_id)

    def _handle_snapshot(self, recording_dir: Path, scene_id: str, live_text: str) -> None:
        snapshot_path = recording_dir / f"{scene_id}.txt"
        if not snapshot_path.exists():
            snapshot_path.write_text(live_text, encoding="utf-8")
            return
        recorded = snapshot_path.read_text(encoding="utf-8").strip()
        if recorded != live_text.strip():
            logger.warning(
                "prerecorded.stale_recording",
                extra={
                    "scene_id": scene_id,
                    "recorded_text": recorded,
                    "live_text": live_text,
                },
            )

    def _resolve_fallback(self, profile: VoiceProfile) -> tuple[VoiceEngine, VoiceProfile]:
        fallback_id = profile.params.get("fallback_voice_id")
        if fallback_id:
            return self._registry.resolve(fallback_id)
        return self._registry.default_for_locale(profile.locale)
