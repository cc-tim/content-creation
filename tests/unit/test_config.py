from pipeline.config import PipelineConfig


def test_config_defaults():
    config = PipelineConfig(ANTHROPIC_API_KEY="test-key")
    assert config.OUTPUT_DIR.name == "output"
    assert config.TTS_PROVIDER == "edge-tts"
    assert config.CLAUDE_MODEL == "claude-sonnet-4-20250514"
    assert config.MAX_VIDEO_RESOLUTION == "720p"


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("PIPELINE_ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("PIPELINE_TTS_PROVIDER", "google")
    config = PipelineConfig()
    assert config.ANTHROPIC_API_KEY == "sk-test"
    assert config.TTS_PROVIDER == "google"
