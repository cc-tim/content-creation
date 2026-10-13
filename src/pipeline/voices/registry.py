from __future__ import annotations

import json
from pathlib import Path

from pipeline.voices.base import VoiceEngine, VoiceNotFound, VoiceProfile
from pipeline.voices.edge_engine import EdgeEngine
from pipeline.voices.fallback_engine import EngineHealth, FallbackEngine


class VoiceRegistry:
    """On-disk catalog of voice profiles keyed by id.

    One registry serves one TTS run: the engines it hands out share per-engine-type
    health, so an outage switches every voice of the run to its fallback or none of them.
    `auto_fallback` overrides PIPELINE_TTS_AUTO_FALLBACK (False: plain engines, no guard).
    """

    def __init__(self, voices_dir: Path, auto_fallback: bool | None = None):
        self._dir = Path(voices_dir)
        self._path = self._dir / "registry.json"
        self._profiles: dict[str, VoiceProfile] = {}
        self._auto_fallback = auto_fallback
        self._health: dict[str, EngineHealth] = {}
        self._load()

    # ---- loading / saving ----
    def _load(self) -> None:
        if not self._path.exists():
            return
        data = json.loads(self._path.read_text())
        for entry in data.get("voices", []):
            profile = VoiceProfile.from_dict(entry)
            self._profiles[profile.id] = profile

    def save(self) -> Path:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(
                {"voices": [p.to_dict() for p in self._profiles.values()]},
                indent=2,
                ensure_ascii=False,
            )
        )
        return self._path

    # ---- queries ----
    def list(self) -> list[VoiceProfile]:
        return list(self._profiles.values())

    def get(self, voice_id: str) -> VoiceProfile:
        if voice_id not in self._profiles:
            raise VoiceNotFound(f"voice '{voice_id}' not in registry")
        return self._profiles[voice_id]

    def default_for_locale(self, locale: str) -> tuple[VoiceEngine, VoiceProfile]:
        for profile in self._profiles.values():
            if profile.locale == locale and profile.id.endswith("default-f"):
                return self._engine_for(profile), profile
        for profile in self._profiles.values():
            if profile.locale == locale:
                return self._engine_for(profile), profile
        raise VoiceNotFound(f"no default voice for locale {locale}")

    def resolve(self, voice_id: str) -> tuple[VoiceEngine, VoiceProfile]:
        profile = self.get(voice_id)
        return self._engine_for(profile), profile

    # ---- mutation ----
    def add(self, entry: dict) -> VoiceProfile:
        profile = VoiceProfile.from_dict(entry)
        self._profiles[profile.id] = profile
        return profile

    def remove(self, voice_id: str) -> None:
        if voice_id not in self._profiles:
            raise VoiceNotFound(f"voice '{voice_id}' not in registry")
        del self._profiles[voice_id]

    def fallbacks_used(self) -> dict[str, str]:
        """Primary voice id -> fallback voice id, for each voice that switched this run."""
        used: dict[str, str] = {}
        for health in self._health.values():
            used.update(health.fallbacks)
        return used

    # ---- engine factory ----
    def _auto_fallback_enabled(self) -> bool:
        if self._auto_fallback is not None:
            return self._auto_fallback
        from pipeline.config import PipelineConfig

        return PipelineConfig().TTS_AUTO_FALLBACK

    def _engine_for(self, profile: VoiceProfile) -> VoiceEngine:
        engine = self._base_engine_for(profile)
        # Prerecorded profiles use params.fallback_voice_id for missing recordings instead;
        # the voices they fall back to come through here and are guarded themselves.
        if profile.engine == "prerecorded" or not self._auto_fallback_enabled():
            return engine
        # Every voice is guarded, with or without a fallback, so a success on any voice
        # of this engine type counts for the run.
        health = self._health.setdefault(profile.engine, EngineHealth(profile.engine))
        fallback_id = profile.params.get("fallback_voice_id")
        if not fallback_id:
            return FallbackEngine(engine, health)
        fallback_profile = self.get(fallback_id)
        return FallbackEngine(
            engine, health, self._base_engine_for(fallback_profile), fallback_profile
        )

    def _base_engine_for(self, profile: VoiceProfile) -> VoiceEngine:
        if profile.engine == "edge":
            return EdgeEngine()
        if profile.engine == "prerecorded":
            from pipeline.voices.prerecorded_engine import PrerecordedEngine

            return PrerecordedEngine(registry=self)
        if profile.engine == "fish_audio":
            from pipeline.config import PipelineConfig
            from pipeline.voices.fish_audio_engine import FishAudioEngine

            return FishAudioEngine(api_key=PipelineConfig().FISH_AUDIO_API_KEY)
        if profile.engine == "kokoro":
            from pipeline.config import PipelineConfig
            from pipeline.voices.kokoro_engine import KokoroEngine

            return KokoroEngine(model_dir=PipelineConfig().TTS_KOKORO_MODEL_DIR)
        # TODO: elevenlabs engine
        raise VoiceNotFound(f"unknown engine '{profile.engine}' for voice {profile.id}")
