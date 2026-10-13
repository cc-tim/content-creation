from __future__ import annotations

from pathlib import Path

import structlog

from pipeline.voices.base import VoiceEngine, VoiceProfile

logger = structlog.get_logger()


class FallbackEngine(VoiceEngine):
    """Primary engine with a whole-pass fallback voice for when the primary is down.

    One instance serves one TTS pass. If the primary fails before it has produced any
    audio, the pass switches to the fallback voice for good and logs an error. If the
    primary fails after it already produced audio, it raises instead: one narration
    must never mix two voices.
    """

    def __init__(
        self,
        primary: VoiceEngine,
        fallback: VoiceEngine,
        fallback_profile: VoiceProfile,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.fallback_profile = fallback_profile
        self._primary_succeeded = False
        self._engaged = False

    @property
    def name(self) -> str:
        return self.primary.name

    def synthesize(
        self,
        text: str,
        out_path: Path,
        profile: VoiceProfile,
        scene_id: str | None = None,
    ) -> Path:
        if self._engaged:
            return self.fallback.synthesize(
                text, out_path, self.fallback_profile, scene_id=scene_id
            )
        try:
            result = self.primary.synthesize(text, out_path, profile, scene_id=scene_id)
        except Exception as exc:
            if self._primary_succeeded:
                raise RuntimeError(
                    f"TTS voice {profile.id} failed mid-pass at scene {scene_id}: {exc}. "
                    f"Earlier scenes already used it, so falling back would mix two voices "
                    f"in one narration. Re-run TTS, or run the whole pass on the fallback "
                    f"with --voice {self.fallback_profile.id}."
                ) from exc
            return self._engage(text, out_path, profile, scene_id, exc)
        self._primary_succeeded = True
        return result

    def _engage(
        self,
        text: str,
        out_path: Path,
        profile: VoiceProfile,
        scene_id: str | None,
        primary_error: Exception,
    ) -> Path:
        logger.error(
            "tts.fallback.engaged",
            primary_voice=profile.id,
            fallback_voice=self.fallback_profile.id,
            scene_id=scene_id,
            error=str(primary_error),
            note="PRIMARY TTS VOICE FAILED: this whole pass is narrated by the fallback "
            "voice. Listen before publishing.",
        )
        self._engaged = True
        try:
            return self.fallback.synthesize(
                text, out_path, self.fallback_profile, scene_id=scene_id
            )
        except Exception as fallback_error:
            raise RuntimeError(
                f"TTS voice {profile.id} failed ({primary_error}) and fallback voice "
                f"{self.fallback_profile.id} failed too ({fallback_error})."
            ) from fallback_error
