from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from pipeline.voices.base import VoiceProfile
from pipeline.voices.edge_engine import EdgeEngine


def test_edge_engine_invokes_edge_tts(tmp_path):
    profile = VoiceProfile(
        id="zh-TW-default-f",
        engine="edge",
        locale="zh-TW",
        params={"voice": "zh-TW-HsiaoChenNeural"},
    )
    out = tmp_path / "narration.mp3"

    async def fake_save(self, path):
        Path(path).write_bytes(b"FAKE-MP3")

    with patch("pipeline.voices.edge_engine.edge_tts.Communicate") as fake_class:
        instance = fake_class.return_value
        instance.save = fake_save.__get__(instance, type(instance))
        result = EdgeEngine().synthesize("你好", out, profile)

    assert result == out
    assert out.read_bytes() == b"FAKE-MP3"
    fake_class.assert_called_once()
    # First positional arg is the text, second is the voice.
    args, kwargs = fake_class.call_args
    assert args[0] == "你好"
    assert args[1] == "zh-TW-HsiaoChenNeural"


_LEGACY_WSS_URL = (
    "wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1"
    "?TrustedClientToken=6A5AA1D4EAFF4E9FB37E23D68491D6F4"
)


def _synthesize_with_fake_communicate(tmp_path):
    profile = VoiceProfile(
        id="zh-TW-default-f",
        engine="edge",
        locale="zh-TW",
        params={"voice": "zh-TW-HsiaoChenNeural"},
    )

    async def fake_save(self, path):
        Path(path).write_bytes(b"FAKE-MP3")

    with patch("pipeline.voices.edge_engine.edge_tts.Communicate") as fake_class:
        instance = fake_class.return_value
        instance.save = fake_save.__get__(instance, type(instance))
        EdgeEngine().synthesize("你好", tmp_path / "n.mp3", profile)


def test_edge_engine_moves_synthesis_off_the_legacy_bing_host(tmp_path, monkeypatch):
    """speech.platform.bing.com answers synthesis with 403 since Oct 2026 (rany2/edge-tts#490)."""
    import edge_tts.communicate

    monkeypatch.setattr(edge_tts.communicate, "WSS_URL", _LEGACY_WSS_URL)

    _synthesize_with_fake_communicate(tmp_path)

    url = edge_tts.communicate.WSS_URL
    assert url.startswith("wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1?")
    assert "Ocp-Apim-Subscription-Key=6A5AA1D4EAFF4E9FB37E23D68491D6F4" in url


def test_edge_engine_leaves_a_fixed_upstream_endpoint_alone(tmp_path, monkeypatch):
    """Once an edge-tts release ships its own endpoint, the override must step aside."""
    import edge_tts.communicate

    upstream = "wss://speech.example.invalid/v2?Ocp-Apim-Subscription-Key=abc"
    monkeypatch.setattr(edge_tts.communicate, "WSS_URL", upstream)

    _synthesize_with_fake_communicate(tmp_path)

    url = edge_tts.communicate.WSS_URL
    assert url == upstream


def _handshake_error(status: int):
    import aiohttp
    from multidict import CIMultiDict, CIMultiDictProxy
    from yarl import URL

    url = URL("wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1")
    info = aiohttp.RequestInfo(
        url=url, method="GET", headers=CIMultiDictProxy(CIMultiDict()), real_url=url
    )
    return aiohttp.WSServerHandshakeError(
        request_info=info, history=(), status=status, message="Invalid response status"
    )


def _scripted_run(monkeypatch, outcomes):
    """Patch EdgeEngine._run: each call pops an exception to raise, or None to succeed."""
    calls = []

    async def fake_run(text, voice, out_path):
        calls.append(text)
        err = outcomes.pop(0)
        if err is not None:
            raise err
        Path(out_path).write_bytes(b"FAKE-MP3")

    monkeypatch.setattr(EdgeEngine, "_run", staticmethod(fake_run))
    return calls


_HSIAOCHEN = VoiceProfile(
    id="zh-TW-default-f", engine="edge", locale="zh-TW",
    params={"voice": "zh-TW-HsiaoChenNeural"},
)


def test_edge_engine_retries_rate_limited_handshakes(tmp_path, monkeypatch):
    """api.msedgeservices.com answers ~1 in 5 back-to-back requests with 429."""
    calls = _scripted_run(monkeypatch, [_handshake_error(429), _handshake_error(503), None])
    sleeps: list[float] = []

    out = EdgeEngine(sleep=sleeps.append).synthesize("你好", tmp_path / "n.mp3", _HSIAOCHEN)

    assert out.read_bytes() == b"FAKE-MP3"
    assert len(calls) == 3
    assert sleeps == [1.0, 2.0]


@pytest.mark.parametrize("status", [401, 403])
def test_edge_engine_reports_a_refused_request_as_unavailable_at_once(
    tmp_path, monkeypatch, status
):
    """401/403 is the endpoint refusing us: no retry, and a fallback voice may take over."""
    import aiohttp

    from pipeline.voices.base import VoiceEngineUnavailable

    calls = _scripted_run(monkeypatch, [_handshake_error(status), None])
    sleeps: list[float] = []

    with pytest.raises(VoiceEngineUnavailable) as excinfo:
        EdgeEngine(sleep=sleeps.append).synthesize("你好", tmp_path / "n.mp3", _HSIAOCHEN)

    assert isinstance(excinfo.value.__cause__, aiohttp.WSServerHandshakeError)
    assert len(calls) == 1
    assert sleeps == []


def _connector_error():
    from types import SimpleNamespace

    import aiohttp

    key = SimpleNamespace(host="api.msedgeservices.com", port=443, ssl=True)
    return aiohttp.ClientConnectorError(key, OSError(8, "nodename nor servname provided"))


def _server_disconnected():
    import aiohttp

    return aiohttp.ServerDisconnectedError()


@pytest.mark.parametrize(
    "make_error",
    [
        lambda: _handshake_error(500),
        lambda: _handshake_error(502),
        _connector_error,
        _server_disconnected,
        lambda: TimeoutError(),
    ],
    ids=["500", "502", "connector", "disconnected", "timeout"],
)
def test_edge_engine_retries_transient_failures(tmp_path, monkeypatch, make_error):
    calls = _scripted_run(monkeypatch, [make_error(), None])
    sleeps: list[float] = []

    out = EdgeEngine(sleep=sleeps.append).synthesize("你好", tmp_path / "n.mp3", _HSIAOCHEN)

    assert out.read_bytes() == b"FAKE-MP3"
    assert len(calls) == 2
    assert sleeps == [1.0]


@pytest.mark.parametrize(
    "make_error",
    [lambda: _handshake_error(429), _connector_error],
    ids=["429", "connector"],
)
def test_edge_engine_reports_unavailable_after_its_retry_budget(
    tmp_path, monkeypatch, make_error
):
    from pipeline.voices.base import VoiceEngineUnavailable

    calls = _scripted_run(monkeypatch, [make_error() for _ in range(10)])
    sleeps: list[float] = []

    with pytest.raises(VoiceEngineUnavailable, match="6 attempts"):
        EdgeEngine(sleep=sleeps.append).synthesize("你好", tmp_path / "n.mp3", _HSIAOCHEN)

    assert len(calls) == 6
    assert sleeps == [1.0, 2.0, 4.0, 8.0, 16.0]


@pytest.mark.parametrize(
    "make_error",
    [
        lambda: __import__("edge_tts.exceptions").exceptions.NoAudioReceived("No audio"),
        lambda: _handshake_error(404),
    ],
    ids=["no-audio", "404"],
)
def test_edge_engine_lets_other_failures_propagate_unretried(tmp_path, monkeypatch, make_error):
    """NoAudioReceived is about this text; a 404 is not a classified outage."""
    from pipeline.voices.base import VoiceEngineUnavailable

    err = make_error()
    calls = _scripted_run(monkeypatch, [err, None])
    sleeps: list[float] = []

    with pytest.raises(type(err)) as excinfo:
        EdgeEngine(sleep=sleeps.append).synthesize("你好", tmp_path / "n.mp3", _HSIAOCHEN)

    assert not isinstance(excinfo.value, VoiceEngineUnavailable)
    assert len(calls) == 1
    assert sleeps == []


def test_edge_engine_logs_the_synthesis_endpoint_once_per_engine(tmp_path, monkeypatch):
    import edge_tts.communicate
    from structlog.testing import capture_logs

    monkeypatch.setattr(edge_tts.communicate, "WSS_URL", _LEGACY_WSS_URL)
    _scripted_run(monkeypatch, [None, None])
    engine = EdgeEngine()

    with capture_logs() as logs:
        engine.synthesize("一", tmp_path / "a.mp3", _HSIAOCHEN)
        engine.synthesize("二", tmp_path / "b.mp3", _HSIAOCHEN)

    events = [e for e in logs if e["event"] == "tts.edge.endpoint"]
    assert events == [
        {
            "event": "tts.edge.endpoint",
            "log_level": "info",
            "endpoint": "wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1",
            "overridden": True,
        }
    ]


def test_edge_engine_logs_an_upstream_endpoint_as_not_overridden(tmp_path, monkeypatch):
    import edge_tts.communicate
    from structlog.testing import capture_logs

    monkeypatch.setattr(
        edge_tts.communicate, "WSS_URL", "wss://speech.example.invalid/v2?Ocp-Apim-Subscription-Key=abc"
    )
    _scripted_run(monkeypatch, [None])

    with capture_logs() as logs:
        EdgeEngine().synthesize("一", tmp_path / "a.mp3", _HSIAOCHEN)

    events = [e for e in logs if e["event"] == "tts.edge.endpoint"]
    assert [(e["endpoint"], e["overridden"]) for e in events] == [
        ("wss://speech.example.invalid/v2", False)
    ]


def test_edge_engine_reports_the_override_for_every_engine_in_the_process(tmp_path, monkeypatch):
    """The first engine patches the module URL; later engines still run on that override."""
    import edge_tts.communicate
    from structlog.testing import capture_logs

    monkeypatch.setattr(edge_tts.communicate, "WSS_URL", _LEGACY_WSS_URL)
    _scripted_run(monkeypatch, [None, None])

    with capture_logs() as logs:
        EdgeEngine().synthesize("一", tmp_path / "a.mp3", _HSIAOCHEN)
        EdgeEngine().synthesize("二", tmp_path / "b.mp3", _HSIAOCHEN)

    assert [e["overridden"] for e in logs if e["event"] == "tts.edge.endpoint"] == [True, True]
