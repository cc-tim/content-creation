from __future__ import annotations

import asyncio
from pathlib import Path

import edge_tts

from pipeline.voices.base import VoiceEngine, VoiceProfile


class EdgeEngine(VoiceEngine):
    @property
    def name(self) -> str:
        return "edge"

    def synthesize(
        self,
        text: str,
        out_path: Path,
        profile: VoiceProfile,
        scene_id: str | None = None,
    ) -> Path:
        _ = scene_id  # unused: edge voices are scene-agnostic
        voice = profile.params.get("voice")
        if not voice:
            raise ValueError(f"edge voice profile {profile.id} is missing params.voice")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        asyncio.run(self._run(text, voice, out_path))
        return out_path

    @staticmethod
    async def _run(text: str, voice: str, out_path: Path) -> None:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(out_path))
