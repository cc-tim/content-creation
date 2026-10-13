from __future__ import annotations

import asyncio
from pathlib import Path

import edge_tts
import edge_tts.communicate
from edge_tts.constants import TRUSTED_CLIENT_TOKEN

from pipeline.voices.base import VoiceEngine, VoiceProfile

# Since Oct 2026 speech.platform.bing.com answers the synthesis WebSocket with 403
# (rany2/edge-tts#490); Edge 155 synthesizes through api.msedgeservices.com with the same
# token (upstream fix rany2/edge-tts#491, unreleased as of 7.2.8). Applied only while the
# installed edge_tts still points at the legacy host, so a fixed release takes over on its own.
_LEGACY_SYNTH_HOST = "speech.platform.bing.com"
_SYNTH_WSS_URL = (
    "wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1"
    f"?Ocp-Apim-Subscription-Key={TRUSTED_CLIENT_TOKEN}"
)


def _ensure_synth_endpoint() -> None:
    if _LEGACY_SYNTH_HOST in edge_tts.communicate.WSS_URL:
        edge_tts.communicate.WSS_URL = _SYNTH_WSS_URL


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
        _ensure_synth_endpoint()
        asyncio.run(self._run(text, voice, out_path))
        return out_path

    @staticmethod
    async def _run(text: str, voice: str, out_path: Path) -> None:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(out_path))
