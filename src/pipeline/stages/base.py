from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class PipelineContext:
    """Mutable state carried between pipeline stages."""

    # Set at creation
    project_id: int
    source_url: str
    locale: str  # zh-TW, ja, es-MX
    work_dir: Path
    candidate_id: int | None = None  # FK to candidates table (set when coming from discovery)

    # Stage 1: Acquire
    video_path: Path | None = None
    transcript_path: Path | None = None
    transcript_text: str | None = None

    # Stage 2: Analyze
    story_structure: dict[str, Any] | None = None
    knowledge_graph: dict[str, Any] | None = None
    clip_timestamps: list[tuple[float, float]] | None = None
    knowledge_path: Path | None = None

    # Stage 3: Direct (storyboard generation)
    storyboard_path: Path | None = None
    script_path: Path | None = None

    # Stage 4: TTS
    narration_path: Path | None = None
    subtitle_path: Path | None = None
    segment_timings: list[dict[str, Any]] | None = None
    voice_id: str | None = None

    # Stage 5: Compose
    final_video_path: Path | None = None
    burn_subtitles: bool = True

    # Stage 6: Publish
    youtube_video_id: str | None = None

    # Locale framing (optional, set manually or by analyze stage)
    source_locale: str | None = None
    reference_storyboard_path: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dict. Converts Path to str."""
        data: dict[str, Any] = {}
        for k, v in asdict(self).items():
            if isinstance(v, Path):
                data[k] = str(v)
            else:
                data[k] = v
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PipelineContext:
        """Deserialize from dict. Converts path strings back to Path, lists back to tuples."""
        path_fields = {
            "work_dir",
            "video_path",
            "transcript_path",
            "script_path",
            "narration_path",
            "subtitle_path",
            "final_video_path",
            "knowledge_path",
            "storyboard_path",
            "reference_storyboard_path",
        }
        cleaned = {}
        for k, v in data.items():
            if k in path_fields and v is not None:
                cleaned[k] = Path(v)
            elif k == "clip_timestamps" and v is not None:
                cleaned[k] = [tuple(ts) for ts in v]
            else:
                cleaned[k] = v
        return cls(**cleaned)

    def save(self) -> Path:
        """Save context to work_dir/context.json."""
        path = self.work_dir / "context.json"
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False))
        return path

    @classmethod
    def load(cls, path: Path) -> PipelineContext:
        """Load context from a context.json file."""
        data = json.loads(path.read_text())
        return cls.from_dict(data)


class PipelineStage(ABC):
    """Base class for all pipeline stages."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stage name (e.g. 'acquire', 'analyze')."""

    @abstractmethod
    async def run(self, ctx: PipelineContext) -> PipelineContext:
        """Execute stage. Mutates and returns ctx."""
