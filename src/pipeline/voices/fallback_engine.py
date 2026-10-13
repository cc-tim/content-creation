from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from pipeline.voices.base import VoiceEngine, VoiceEngineUnavailable, VoiceProfile

logger = structlog.get_logger()


# Written next to the narration it describes, in the same step that commits that audio,
# so the record can't be lost the way an unsaved context.json can.
FALLBACK_MARKER = "tts_fallback.json"


def write_fallback_marker(audio_dir: Path, fallbacks: dict[str, str]) -> None:
    """Record the voices that narrated as fallbacks; remove the marker when there were none."""
    marker = audio_dir / FALLBACK_MARKER
    if fallbacks:
        marker.write_text(json.dumps({"fallback_voices": fallbacks}, indent=2), encoding="utf-8")
    else:
        marker.unlink(missing_ok=True)


def read_fallback_marker(audio_dir: Path) -> dict[str, str]:
    marker = audio_dir / FALLBACK_MARKER
    if not marker.exists():
        return {}
    return dict(json.loads(marker.read_text(encoding="utf-8")).get("fallback_voices") or {})


@dataclass
class EngineHealth:
    """One engine type's state for one run, shared by every wrapper a VoiceRegistry builds.

    `succeeded`: some voice of this engine already produced audio, so switching voices now
    would mix two narrators. `down_reason`: the engine was unavailable before any success,
    so every voice with a fallback uses it for the rest of the run.
    """

    engine: str
    succeeded: bool = False
    down_reason: str | None = None
    fallbacks: dict[str, str] = field(default_factory=dict)  # primary voice -> fallback voice


class FallbackEngine(VoiceEngine):
    """Guards one registry voice with run-scoped health and an optional fallback voice.

    Only VoiceEngineUnavailable (the service is down) switches voices; any other failure
    propagates. If the engine is unavailable before any voice of its type has produced
    audio in this run, every guarded voice with a fallback switches to it for the rest of
    the run, and the switch is logged as an error. If it already produced audio, the
    failure raises instead: one narration must never mix two voices.
    """

    def __init__(
        self,
        primary: VoiceEngine,
        health: EngineHealth,
        fallback: VoiceEngine | None = None,
        fallback_profile: VoiceProfile | None = None,
    ) -> None:
        self.primary = primary
        self.health = health
        self.fallback = fallback
        self.fallback_profile = fallback_profile

    @property
    def name(self) -> str:
        if self.health.down_reason is not None and self.fallback is not None:
            return self.fallback.name
        return self.primary.name

    def synthesize(
        self,
        text: str,
        out_path: Path,
        profile: VoiceProfile,
        scene_id: str | None = None,
    ) -> Path:
        if self.health.down_reason is not None and self.fallback is not None:
            return self._synthesize_fallback(text, out_path, profile, scene_id)
        try:
            result = self.primary.synthesize(text, out_path, profile, scene_id=scene_id)
        except VoiceEngineUnavailable as exc:
            if self.fallback is None or self.fallback_profile is None:
                raise VoiceEngineUnavailable(
                    f"{exc} at scene {scene_id}; voice {profile.id} has no fallback voice. "
                    f"Re-run TTS once {self.health.engine} is back."
                ) from exc
            if self.health.succeeded:
                raise RuntimeError(
                    f"TTS voice {profile.id} became unavailable mid-run at scene {scene_id}: "
                    f"{exc}. Earlier scenes already used {self.health.engine} voices, so "
                    f"falling back would mix two voices in one narration. Re-run TTS, or "
                    f"narrate the whole run with --voice {self.fallback_profile.id}."
                ) from exc
            self.health.down_reason = str(exc)
            return self._synthesize_fallback(text, out_path, profile, scene_id)
        if self.health.down_reason is None:
            self.health.succeeded = True
        return result

    def _synthesize_fallback(
        self,
        text: str,
        out_path: Path,
        profile: VoiceProfile,
        scene_id: str | None,
    ) -> Path:
        assert self.fallback is not None and self.fallback_profile is not None
        if profile.id not in self.health.fallbacks:
            logger.error(
                "tts.fallback.engaged",
                primary_voice=profile.id,
                fallback_voice=self.fallback_profile.id,
                scene_id=scene_id,
                error=self.health.down_reason,
                note="PRIMARY TTS VOICE UNAVAILABLE: the rest of this run is narrated by "
                "the fallback voice. Listen before publishing.",
            )
            self.health.fallbacks[profile.id] = self.fallback_profile.id
        try:
            return self.fallback.synthesize(
                text, out_path, self.fallback_profile, scene_id=scene_id
            )
        except Exception as fallback_error:
            raise RuntimeError(
                f"TTS voice {profile.id} is unavailable ({self.health.down_reason}) and "
                f"fallback voice {self.fallback_profile.id} failed too ({fallback_error})."
            ) from fallback_error
