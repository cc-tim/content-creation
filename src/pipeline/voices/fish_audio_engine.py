from __future__ import annotations

from pathlib import Path

import httpx

from pipeline.voices.base import VoiceEngine, VoiceProfile


class FishAudioEngine(VoiceEngine):
    _BASE_URL = "https://api.fish.audio/v1/tts"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "fish_audio"

    def synthesize(
        self,
        text: str,
        out_path: Path,
        profile: VoiceProfile,
        scene_id: str | None = None,
    ) -> Path:
        reference_id = profile.params.get("reference_id")
        if not reference_id:
            raise ValueError(
                f"fish_audio profile {profile.id!r} is missing params.reference_id"
            )

        response = httpx.post(
            self._BASE_URL,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"text": text, "reference_id": reference_id, "format": "mp3"},
            timeout=120,
        )
        response.raise_for_status()

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(response.content)
        return out_path
