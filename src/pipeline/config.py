from pathlib import Path
from pydantic_settings import BaseSettings


class PipelineConfig(BaseSettings):
    model_config = {"env_prefix": "PIPELINE_"}

    # API keys
    ANTHROPIC_API_KEY: str = ""
    YOUTUBE_API_KEY: str = ""
    GOOGLE_CLOUD_TTS_KEY: str = ""

    # Paths
    OUTPUT_DIR: Path = Path("output")

    # Claude
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"

    # TTS
    TTS_PROVIDER: str = "edge-tts"  # edge-tts | google | openai
    TTS_VOICE_ZH_TW: str = "zh-TW-HsiaoChenNeural"
    TTS_VOICE_JA: str = "ja-JP-NanamiNeural"
    TTS_VOICE_ES_MX: str = "es-MX-DaliaNeural"

    # Video
    MAX_VIDEO_RESOLUTION: str = "720p"

    def get_tts_voice(self, locale: str) -> str:
        voices = {
            "zh-TW": self.TTS_VOICE_ZH_TW,
            "ja": self.TTS_VOICE_JA,
            "es-MX": self.TTS_VOICE_ES_MX,
        }
        return voices.get(locale, self.TTS_VOICE_ZH_TW)
