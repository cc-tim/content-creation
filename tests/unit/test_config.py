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


def test_pexels_key_from_unprefixed_env(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "fake-pexels-key")
    monkeypatch.delenv("PIPELINE_PEXELS_API_KEY", raising=False)
    cfg = PipelineConfig()
    assert cfg.PEXELS_API_KEY == "fake-pexels-key"


def test_pixabay_key_from_unprefixed_env(monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "fake-pixabay-key")
    monkeypatch.delenv("PIPELINE_PIXABAY_API_KEY", raising=False)
    cfg = PipelineConfig()
    assert cfg.PIXABAY_API_KEY == "fake-pixabay-key"
