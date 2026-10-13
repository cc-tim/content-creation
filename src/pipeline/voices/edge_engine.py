from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from pathlib import Path

import aiohttp
import edge_tts
import edge_tts.communicate
import edge_tts.constants
import structlog
from edge_tts.constants import TRUSTED_CLIENT_TOKEN

from pipeline.voices.base import VoiceEngine, VoiceEngineUnavailable, VoiceProfile

logger = structlog.get_logger()

# Since Oct 2026 speech.platform.bing.com answers the synthesis WebSocket with 403
# (rany2/edge-tts#490); Edge 155 synthesizes through api.msedgeservices.com with the same
# token (upstream fix rany2/edge-tts#491, unreleased as of 7.2.8). Applied only while the
# installed edge_tts still points at the legacy host, so a fixed release takes over on its own.
_LEGACY_SYNTH_HOST = "speech.platform.bing.com"
_SYNTH_WSS_URL = (
    "wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1"
    f"?Ocp-Apim-Subscription-Key={TRUSTED_CLIENT_TOKEN}"
)
# That endpoint throttles: ~1 in 5 back-to-back requests gets a 429 (no Retry-After) and
# the next one usually succeeds. 401/403 are not retried: the endpoint refuses us.
_REFUSED_STATUSES = frozenset({401, 403})
_RETRY_EXCEPTIONS = (
    aiohttp.ClientConnectorError,
    aiohttp.ServerDisconnectedError,
    asyncio.TimeoutError,
)
_RETRY_DELAYS_SEC = (1.0, 2.0, 4.0, 8.0, 16.0)


def _is_retryable_status(status: int) -> bool:
    return status == 429 or 500 <= status < 600


def _ensure_synth_endpoint() -> bool:
    """Point edge_tts at the working endpoint; True while this module's override is in use."""
    if _LEGACY_SYNTH_HOST in edge_tts.communicate.WSS_URL:
        edge_tts.communicate.WSS_URL = _SYNTH_WSS_URL
    # edge_tts.constants keeps the release's own URL, so a fixed release reads False here.
    return (
        edge_tts.communicate.WSS_URL == _SYNTH_WSS_URL
        and _LEGACY_SYNTH_HOST in edge_tts.constants.WSS_URL
    )


class EdgeEngine(VoiceEngine):
    def __init__(self, sleep: Callable[[float], None] = time.sleep) -> None:
        self._sleep = sleep
        self._endpoint_logged = False

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
        overridden = _ensure_synth_endpoint()
        if not self._endpoint_logged:
            # Without the query string: it carries the client token.
            endpoint = edge_tts.communicate.WSS_URL.split("?", 1)[0]
            logger.info("tts.edge.endpoint", endpoint=endpoint, overridden=overridden)
            self._endpoint_logged = True
        attempts = len(_RETRY_DELAYS_SEC) + 1
        for attempt, delay in enumerate((*_RETRY_DELAYS_SEC, None), start=1):
            try:
                asyncio.run(self._run(text, voice, out_path))
                return out_path
            except aiohttp.WSServerHandshakeError as exc:
                if exc.status in _REFUSED_STATUSES:
                    raise VoiceEngineUnavailable(
                        f"edge refused synthesis for {voice} (HTTP {exc.status})"
                    ) from exc
                if not _is_retryable_status(exc.status):
                    raise
                error: Exception = exc
            except _RETRY_EXCEPTIONS as exc:
                error = exc
            if delay is None:
                raise VoiceEngineUnavailable(
                    f"edge unreachable for {voice} after {attempts} attempts: {error!r}"
                ) from error
            logger.warning(
                "tts.edge.retry", voice=voice, error=repr(error),
                attempt=attempt, delay_sec=delay,
            )
            self._sleep(delay)
        raise AssertionError("unreachable")

    @staticmethod
    async def _run(text: str, voice: str, out_path: Path) -> None:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(out_path))
