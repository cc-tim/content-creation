from __future__ import annotations

import json

from typer.testing import CliRunner

from pipeline.cli_voice import voice_app


def _init_voices(tmp_path):
    voices = tmp_path / "voices"
    voices.mkdir()
    (voices / "registry.json").write_text(
        json.dumps(
            {
                "voices": [
                    {
                        "id": "zh-TW-default-f",
                        "engine": "edge",
                        "locale": "zh-TW",
                        "params": {"voice": "zh-TW-HsiaoChenNeural"},
                        "display_name": "HsiaoChen",
                    }
                ]
            }
        )
    )
    return voices


def test_voice_list_shows_registry(tmp_path, monkeypatch):
    _init_voices(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(voice_app, ["list"])
    assert result.exit_code == 0
    assert "zh-TW-default-f" in result.stdout
    assert "HsiaoChen" in result.stdout


def test_voice_add_persists_entry(tmp_path, monkeypatch):
    voices = _init_voices(tmp_path)
    monkeypatch.chdir(tmp_path)
    ref = voices / "cloned" / "tim.wav"
    ref.parent.mkdir(parents=True)
    ref.write_bytes(b"RIFF-stub")

    result = CliRunner().invoke(
        voice_app,
        [
            "add",
            "--id",
            "tim-zhtw",
            "--engine",
            "edge",
            "--locale",
            "zh-TW",
            "--reference",
            str(ref),
            "--reference-text",
            "大家好",
            "--display-name",
            "Tim",
        ],
    )
    assert result.exit_code == 0, result.stdout

    data = json.loads((voices / "registry.json").read_text())
    ids = [v["id"] for v in data["voices"]]
    assert "tim-zhtw" in ids


def test_voice_remove_deletes_entry(tmp_path, monkeypatch):
    voices = _init_voices(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(voice_app, ["remove", "zh-TW-default-f"])
    assert result.exit_code == 0, result.stdout
    data = json.loads((voices / "registry.json").read_text())
    assert data["voices"] == []


def test_voice_add_prerecorded(tmp_path, monkeypatch):
    voices = _init_voices(tmp_path)
    monkeypatch.chdir(tmp_path)
    rec_dir = tmp_path / "rec"
    result = CliRunner().invoke(
        voice_app,
        [
            "add",
            "--id",
            "tim-zhtw",
            "--engine",
            "prerecorded",
            "--locale",
            "zh-TW",
            "--recording-dir",
            str(rec_dir),
            "--fallback-voice",
            "zh-TW-default-f",
            "--display-name",
            "Tim (zh-TW)",
        ],
    )
    assert result.exit_code == 0, result.stdout

    data = json.loads((voices / "registry.json").read_text())
    profile = next(v for v in data["voices"] if v["id"] == "tim-zhtw")
    assert profile["engine"] == "prerecorded"
    assert profile["params"]["recording_dir"] == str(rec_dir)
    assert profile["params"]["fallback_voice_id"] == "zh-TW-default-f"


def test_voice_test_plays_the_requested_voice_or_fails(tmp_path, monkeypatch):
    """`voice test` is for hearing this voice: never substitute its fallback."""
    from pipeline.voices.base import VoiceEngineUnavailable
    from pipeline.voices.edge_engine import EdgeEngine
    from pipeline.voices.kokoro_engine import KokoroEngine

    voices = tmp_path / "voices"
    voices.mkdir()
    (voices / "registry.json").write_text(json.dumps({"voices": [
        {"id": "zh-TW-default-f", "engine": "edge", "locale": "zh-TW",
         "params": {"voice": "zh-TW-HsiaoChenNeural", "fallback_voice_id": "zh-TW-kokoro-f"}},
        {"id": "zh-TW-kokoro-f", "engine": "kokoro", "locale": "zh-TW", "params": {"sid": 3}},
    ]}))
    monkeypatch.setenv("PIPELINE_VOICES_DIR", str(voices))
    kokoro_calls: list[str] = []

    def edge(self, text, out_path, profile, scene_id=None):
        raise VoiceEngineUnavailable("edge refused synthesis (HTTP 403)")

    def kokoro(self, text, out_path, profile, scene_id=None):
        kokoro_calls.append(text)
        out_path.write_text("kokoro")
        return out_path

    monkeypatch.setattr(EdgeEngine, "synthesize", edge)
    monkeypatch.setattr(KokoroEngine, "synthesize", kokoro)

    result = CliRunner().invoke(
        voice_app, ["test", "zh-TW-default-f", "--out", str(tmp_path / "t.mp3")]
    )

    assert result.exit_code != 0
    assert isinstance(result.exception, VoiceEngineUnavailable)
    assert kokoro_calls == []
