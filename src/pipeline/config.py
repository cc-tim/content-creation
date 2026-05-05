from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class PipelineConfig(BaseSettings):
    model_config = {"env_prefix": "PIPELINE_", "env_file": ".env", "env_file_encoding": "utf-8"}

    # API keys
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""   # used only for OpenAI TTS; image gen uses gen-image.py
    YOUTUBE_API_KEY: str = ""
    GOOGLE_CLOUD_TTS_KEY: str = ""
    FISH_AUDIO_API_KEY: str = ""
    PEXELS_API_KEY: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PEXELS_API_KEY", "PIPELINE_PEXELS_API_KEY"),
    )
    PIXABAY_API_KEY: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PIXABAY_API_KEY", "PIPELINE_PIXABAY_API_KEY"),
    )

    # Paths
    OUTPUT_DIR: Path = Path("output")
    VOICES_DIR: Path = Path("voices")

    # Claude
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"

    # TTS
    TTS_PROVIDER: str = "edge-tts"  # edge-tts | google | openai
    TTS_VOICE_ZH_TW: str = "zh-TW-HsiaoChenNeural"
    TTS_VOICE_JA: str = "ja-JP-NanamiNeural"
    TTS_VOICE_ES_MX: str = "es-MX-DaliaNeural"

    # Video
    MAX_VIDEO_RESOLUTION: str = "720p"

    # Concurrency
    MAX_COMPOSE_WORKERS: int = Field(
        default=4,
        ge=1,
        le=32,
        description="Max parallel workers for scene composition (FFmpeg subprocesses)",
    )

    def get_tts_voice(self, locale: str) -> str:
        voices = {
            "zh-TW": self.TTS_VOICE_ZH_TW,
            "ja": self.TTS_VOICE_JA,
            "es-MX": self.TTS_VOICE_ES_MX,
        }
        return voices.get(locale, self.TTS_VOICE_ZH_TW)
