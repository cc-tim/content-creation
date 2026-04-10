from __future__ import annotations

import json
from pathlib import Path

from pipeline.voices.base import VoiceEngine, VoiceNotFound, VoiceProfile
from pipeline.voices.edge_engine import EdgeEngine


class VoiceRegistry:
    """On-disk catalog of voice profiles keyed by id."""

    def __init__(self, voices_dir: Path):
        self._dir = Path(voices_dir)
        self._path = self._dir / "registry.json"
        self._profiles: dict[str, VoiceProfile] = {}
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

    # ---- engine factory ----
    @staticmethod
    def _engine_for(profile: VoiceProfile) -> VoiceEngine:
        if profile.engine == "edge":
            return EdgeEngine()
        if profile.engine == "cosyvoice":
            from pipeline.voices.cosy_engine import CosyVoiceEngine

            return CosyVoiceEngine()
        raise VoiceNotFound(f"unknown engine '{profile.engine}' for voice {profile.id}")
