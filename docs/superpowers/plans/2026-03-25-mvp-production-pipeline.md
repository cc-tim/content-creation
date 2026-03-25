# MVP Production Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the minimum viable production pipeline so we can run `uv run pipeline produce --url "<youtube-url>" --locale zh-TW` end-to-end: acquire → analyze → scriptwrite → (human pause) → tts → compose → output a finished video.

**Architecture:** Linear stage pipeline. Each stage implements `PipelineStage.run(ctx) -> ctx`. PipelineContext dataclass carries mutable state. Serialized to `context.json` after each stage for resume. No database for MVP — file system + context only. Ad-hoc URL mode (bypass discovery).

**Tech Stack:** Python 3.12+, uv, Typer, pydantic-settings, yt-dlp, youtube-transcript-api, anthropic SDK, edge-tts, ffmpeg-python, pysrt, structlog, pytest, ruff

**Spec:** `docs/superpowers/specs/2026-03-23-content-porting-pipeline-design.md`

---

## File Structure

```
pyproject.toml                          # PEP 621 project definition
.env.example                            # Placeholder secrets
src/
  pipeline/
    __init__.py                         # Package init
    cli.py                              # Typer CLI with subcommands
    config.py                           # pydantic-settings config loading
    models.py                           # Shared Pydantic models (Locale enum, etc.)
    orchestrator.py                     # Stage chaining, resume, human gates
    stages/
      __init__.py
      base.py                           # PipelineStage ABC + PipelineContext dataclass
      acquire.py                        # yt-dlp download + transcript extraction
      analyze.py                        # Claude API story structure + knowledge graph
      scriptwrite.py                    # Claude API script adaptation
      tts.py                            # edge-tts narration generation
      compose.py                        # FFmpeg video composition
    utils/
      __init__.py
      ffmpeg.py                         # FFmpeg command builders
      srt.py                            # SRT parsing + generation
tests/
  __init__.py
  conftest.py                           # Shared fixtures, pytest markers
  unit/
    __init__.py
    test_config.py
    test_base.py
    test_orchestrator.py
    test_acquire.py
    test_analyze.py
    test_scriptwrite.py
    test_tts.py
    test_compose.py
    test_srt.py
    test_ffmpeg.py
  fixtures/
    sample.srt
    transcript.json                     # Sample youtube-transcript-api output
    claude_analysis_response.json       # Sample Claude analysis response
    claude_scriptwrite_response.json    # Sample Claude scriptwrite response
    sample_script.md                    # Script with markers for compose tests
```

---

## Task 1: Project Initialization

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `src/pipeline/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "content-pipeline"
version = "0.1.0"
description = "YouTube content porting pipeline"
requires-python = ">=3.12"
dependencies = [
    "typer>=0.15",
    "pydantic-settings>=2.7",
    "yt-dlp>=2025.3",
    "youtube-transcript-api>=1.0",
    "anthropic>=0.49",
    "edge-tts>=7.0",
    "ffmpeg-python>=0.2",
    "pysrt>=1.1",
    "structlog>=25.1",
]

[project.scripts]
pipeline = "pipeline.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/pipeline"]

[tool.uv]
dev-dependencies = [
    "pytest>=8.3",
    "pytest-asyncio>=0.25",
    "ruff>=0.11",
    "mypy>=1.15",
]

[tool.pytest.ini_options]
markers = [
    "slow: marks tests that load large models",
    "integration: marks tests requiring FFmpeg binary",
    "network: marks tests requiring network + API keys",
]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.12"
strict = true
```

- [ ] **Step 2: Create .env.example**

```env
# Required for Analyze + Scriptwrite stages
PIPELINE_ANTHROPIC_API_KEY=sk-ant-xxx

# Required for Discovery (not needed for MVP ad-hoc mode)
# PIPELINE_YOUTUBE_API_KEY=AIzaXxx

# Optional: premium TTS fallback
# PIPELINE_GOOGLE_CLOUD_TTS_KEY=xxx

# Output directory (default: ./output)
# PIPELINE_OUTPUT_DIR=./output
```

- [ ] **Step 3: Create package init**

```python
# src/pipeline/__init__.py
```

Empty file. Also create `src/pipeline/stages/__init__.py` and `src/pipeline/utils/__init__.py`.

- [ ] **Step 4: Run uv sync**

Run: `cd /home/tim-huang/content-creation && uv sync`
Expected: dependencies installed, `.venv/` created, `uv.lock` generated

- [ ] **Step 5: Verify import works**

Run: `uv run python -c "import pipeline; print('ok')"`
Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock .env.example src/
git commit -m "feat: initialize Python project with uv and dependencies"
```

---

## Task 2: PipelineContext + PipelineStage ABC

**Files:**
- Create: `src/pipeline/stages/base.py`
- Create: `src/pipeline/models.py`
- Create: `tests/unit/test_base.py`
- Create: `tests/__init__.py`, `tests/unit/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write test for PipelineContext serialization**

```python
# tests/unit/test_base.py
import json
from pathlib import Path

from pipeline.stages.base import PipelineContext


def test_context_round_trip_serialization(tmp_path: Path):
    ctx = PipelineContext(
        project_id=1,
        source_url="https://youtube.com/watch?v=abc",
        locale="zh-TW",
        work_dir=tmp_path / "project_1",
    )
    ctx.transcript_text = "Hello world"
    ctx.clip_timestamps = [(0.0, 30.0), (120.0, 135.0)]

    # Serialize
    data = ctx.to_dict()
    json_str = json.dumps(data)

    # Deserialize
    loaded = PipelineContext.from_dict(json.loads(json_str))
    assert loaded.project_id == 1
    assert loaded.source_url == "https://youtube.com/watch?v=abc"
    assert loaded.locale == "zh-TW"
    assert loaded.transcript_text == "Hello world"
    assert loaded.video_path is None
    # clip_timestamps should round-trip as tuples
    assert loaded.clip_timestamps == [(0.0, 30.0), (120.0, 135.0)]
    assert isinstance(loaded.clip_timestamps[0], tuple)


def test_context_save_and_load(tmp_path: Path):
    work_dir = tmp_path / "project_1"
    work_dir.mkdir()
    ctx = PipelineContext(
        project_id=1,
        source_url="https://youtube.com/watch?v=abc",
        locale="zh-TW",
        work_dir=work_dir,
    )
    ctx.save()
    loaded = PipelineContext.load(work_dir / "context.json")
    assert loaded.project_id == ctx.project_id
    assert loaded.work_dir == ctx.work_dir
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.stages.base'`

- [ ] **Step 3: Create models.py with Locale enum**

```python
# src/pipeline/models.py
from enum import StrEnum


class Locale(StrEnum):
    ZH_TW = "zh-TW"
    JA = "ja"
    ES_MX = "es-MX"
```

- [ ] **Step 4: Implement PipelineContext + PipelineStage**

```python
# src/pipeline/stages/base.py
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
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

    # Stage 3: Scriptwrite
    script_path: Path | None = None

    # Stage 4: TTS
    narration_path: Path | None = None
    subtitle_path: Path | None = None
    segment_timings: list[dict[str, Any]] | None = None

    # Stage 5: Compose
    final_video_path: Path | None = None

    # Stage 6: Publish
    youtube_video_id: str | None = None

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
            "work_dir", "video_path", "transcript_path",
            "script_path", "narration_path", "subtitle_path",
            "final_video_path",
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
```

- [ ] **Step 5: Create conftest.py and test __init__ files**

```python
# tests/conftest.py
from pathlib import Path
import pytest

from pipeline.stages.base import PipelineContext


@pytest.fixture
def sample_context(tmp_path: Path) -> PipelineContext:
    work_dir = tmp_path / "test_project"
    work_dir.mkdir()
    return PipelineContext(
        project_id=1,
        source_url="https://youtube.com/watch?v=test123",
        locale="zh-TW",
        work_dir=work_dir,
    )
```

Create empty `tests/__init__.py` and `tests/unit/__init__.py`.

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/unit/test_base.py -v`
Expected: 2 tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/pipeline/models.py src/pipeline/stages/base.py tests/
git commit -m "feat: add PipelineContext with serialization and PipelineStage ABC"
```

---

## Task 3: Config

**Files:**
- Create: `src/pipeline/config.py`
- Create: `tests/unit/test_config.py`

- [ ] **Step 1: Write test for config loading**

```python
# tests/unit/test_config.py
import os
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: FAIL — import error

- [ ] **Step 3: Implement config**

```python
# src/pipeline/config.py
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
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/config.py tests/unit/test_config.py
git commit -m "feat: add pydantic-settings config with env prefix PIPELINE_"
```

---

## Task 4: SRT Utilities

**Files:**
- Create: `src/pipeline/utils/srt.py`
- Create: `tests/unit/test_srt.py`
- Create: `tests/fixtures/sample.srt`

- [ ] **Step 1: Create sample SRT fixture**

```srt
1
00:00:01,000 --> 00:00:04,000
This is the first subtitle.

2
00:00:05,000 --> 00:00:08,500
This is the second subtitle.

3
00:00:10,000 --> 00:00:15,000
And this is the third one.
```

Save to `tests/fixtures/sample.srt`.

- [ ] **Step 2: Write tests**

```python
# tests/unit/test_srt.py
from pathlib import Path
from pipeline.utils.srt import parse_srt, write_srt, SrtEntry


def test_parse_srt():
    fixture = Path(__file__).parent.parent / "fixtures" / "sample.srt"
    entries = parse_srt(fixture)
    assert len(entries) == 3
    assert entries[0].text == "This is the first subtitle."
    assert entries[0].start_ms == 1000
    assert entries[0].end_ms == 4000


def test_write_srt(tmp_path: Path):
    entries = [
        SrtEntry(index=1, start_ms=0, end_ms=3000, text="你好世界"),
        SrtEntry(index=2, start_ms=3500, end_ms=7000, text="這是測試"),
    ]
    out = tmp_path / "output.srt"
    write_srt(entries, out)
    # Round-trip
    parsed = parse_srt(out)
    assert len(parsed) == 2
    assert parsed[0].text == "你好世界"
    assert parsed[1].start_ms == 3500
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_srt.py -v`
Expected: FAIL — import error

- [ ] **Step 4: Implement SRT utilities**

```python
# src/pipeline/utils/srt.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class SrtEntry:
    index: int
    start_ms: int
    end_ms: int
    text: str


def _ms_to_srt_time(ms: int) -> str:
    """Convert milliseconds to SRT timestamp: HH:MM:SS,mmm"""
    hours = ms // 3_600_000
    ms %= 3_600_000
    minutes = ms // 60_000
    ms %= 60_000
    seconds = ms // 1_000
    millis = ms % 1_000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _srt_time_to_ms(ts: str) -> int:
    """Parse SRT timestamp to milliseconds."""
    time_part, millis_str = ts.replace(",", ".").rsplit(".", 1)
    parts = time_part.split(":")
    hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])
    return hours * 3_600_000 + minutes * 60_000 + seconds * 1_000 + int(millis_str)


def parse_srt(path: Path) -> list[SrtEntry]:
    """Parse an SRT file into a list of entries."""
    text = path.read_text(encoding="utf-8")
    entries: list[SrtEntry] = []
    blocks = text.strip().split("\n\n")
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        index = int(lines[0])
        start_str, end_str = lines[1].split(" --> ")
        content = "\n".join(lines[2:])
        entries.append(SrtEntry(
            index=index,
            start_ms=_srt_time_to_ms(start_str.strip()),
            end_ms=_srt_time_to_ms(end_str.strip()),
            text=content,
        ))
    return entries


def write_srt(entries: list[SrtEntry], path: Path) -> None:
    """Write SRT entries to a file."""
    blocks: list[str] = []
    for entry in entries:
        blocks.append(
            f"{entry.index}\n"
            f"{_ms_to_srt_time(entry.start_ms)} --> {_ms_to_srt_time(entry.end_ms)}\n"
            f"{entry.text}"
        )
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/unit/test_srt.py -v`
Expected: 2 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/utils/srt.py tests/unit/test_srt.py tests/fixtures/sample.srt
git commit -m "feat: add SRT parsing and writing utilities"
```

---

## Task 5: FFmpeg Utilities

**Files:**
- Create: `src/pipeline/utils/ffmpeg.py`
- Create: `tests/unit/test_ffmpeg.py`

- [ ] **Step 1: Write tests for FFmpeg command builders**

```python
# tests/unit/test_ffmpeg.py
from pipeline.utils.ffmpeg import (
    build_extract_clip_cmd,
    build_burn_subtitles_cmd,
    build_concat_cmd,
    check_ffmpeg_available,
)


def test_extract_clip_cmd():
    cmd = build_extract_clip_cmd(
        input_path="video.mp4",
        output_path="clip.mp4",
        start_sec=83.0,
        end_sec=95.0,
    )
    assert "video.mp4" in cmd
    assert "clip.mp4" in cmd
    assert "-ss" in cmd
    assert "83.0" in cmd or "00:01:23" in cmd


def test_burn_subtitles_cmd():
    cmd = build_burn_subtitles_cmd(
        input_path="video.mp4",
        subtitle_path="subs.srt",
        output_path="output.mp4",
        font_name="Noto Sans CJK TC",
    )
    assert "subtitles=" in " ".join(cmd) or "subs.srt" in " ".join(cmd)
    assert "Noto Sans CJK TC" in " ".join(cmd)


def test_concat_cmd(tmp_path):
    filelist = tmp_path / "files.txt"
    cmd = build_concat_cmd(
        filelist_path=str(filelist),
        output_path="final.mp4",
    )
    assert "concat" in " ".join(cmd)
    assert "final.mp4" in cmd
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_ffmpeg.py -v`
Expected: FAIL — import error

- [ ] **Step 3: Implement FFmpeg command builders**

```python
# src/pipeline/utils/ffmpeg.py
from __future__ import annotations

import shutil
import subprocess


def check_ffmpeg_available() -> bool:
    """Check if ffmpeg is on PATH."""
    return shutil.which("ffmpeg") is not None


def build_extract_clip_cmd(
    input_path: str,
    output_path: str,
    start_sec: float,
    end_sec: float,
) -> list[str]:
    """Build ffmpeg command to extract a clip between start and end seconds."""
    duration = end_sec - start_sec
    return [
        "ffmpeg", "-y",
        "-ss", str(start_sec),
        "-i", input_path,
        "-t", str(duration),
        "-c", "copy",
        output_path,
    ]


def build_burn_subtitles_cmd(
    input_path: str,
    subtitle_path: str,
    output_path: str,
    font_name: str = "Noto Sans CJK TC",
    font_size: int = 24,
) -> list[str]:
    """Build ffmpeg command to burn subtitles into video."""
    style = f"FontName={font_name},FontSize={font_size}"
    # No quotes around style — subprocess.run passes args directly, not via shell
    subtitle_filter = f"subtitles={subtitle_path}:force_style={style}"
    return [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", subtitle_filter,
        "-c:a", "copy",
        output_path,
    ]


def build_concat_cmd(
    filelist_path: str,
    output_path: str,
) -> list[str]:
    """Build ffmpeg command to concatenate files listed in a text file."""
    return [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", filelist_path,
        "-c", "copy",
        output_path,
    ]


def run_ffmpeg(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess[str]:
    """Execute an ffmpeg command. Raises on failure."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_ffmpeg.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/utils/ffmpeg.py tests/unit/test_ffmpeg.py
git commit -m "feat: add FFmpeg command builder utilities"
```

---

## Task 6: Acquire Stage

**Files:**
- Create: `src/pipeline/stages/acquire.py`
- Create: `tests/unit/test_acquire.py`
- Create: `tests/fixtures/transcript.json`

- [ ] **Step 1: Create transcript fixture**

```json
[
  {"text": "On the night of March 15th,", "start": 0.0, "duration": 2.5},
  {"text": "Officer Johnson responded to a disturbance call", "start": 2.5, "duration": 3.0},
  {"text": "in downtown Austin, Texas.", "start": 5.5, "duration": 2.0}
]
```

Save to `tests/fixtures/transcript.json`.

- [ ] **Step 2: Write tests for acquire stage**

```python
# tests/unit/test_acquire.py
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from pipeline.stages.acquire import AcquireStage
from pipeline.stages.base import PipelineContext


@pytest.fixture
def transcript_fixture() -> list[dict]:
    path = Path(__file__).parent.parent / "fixtures" / "transcript.json"
    return json.loads(path.read_text())


@pytest.mark.asyncio
async def test_acquire_downloads_video_and_transcript(sample_context, transcript_fixture):
    stage = AcquireStage()
    assert stage.name == "acquire"

    with (
        patch("pipeline.stages.acquire.download_video") as mock_dl,
        patch("pipeline.stages.acquire.extract_transcript") as mock_tr,
    ):
        # Mock download: create a dummy video file
        def fake_download(url, output_dir, resolution):
            video_path = output_dir / "video.mp4"
            video_path.write_bytes(b"fake video")
            return video_path

        mock_dl.side_effect = fake_download
        mock_tr.return_value = (
            "On the night of March 15th, Officer Johnson responded...",
            transcript_fixture,
        )

        ctx = await stage.run(sample_context)

    assert ctx.video_path is not None
    assert ctx.video_path.exists()
    assert ctx.transcript_text is not None
    assert "March 15th" in ctx.transcript_text


@pytest.mark.asyncio
async def test_acquire_creates_source_directory(sample_context, transcript_fixture):
    stage = AcquireStage()
    with (
        patch("pipeline.stages.acquire.download_video") as mock_dl,
        patch("pipeline.stages.acquire.extract_transcript") as mock_tr,
    ):
        def fake_download(url, output_dir, resolution):
            video_path = output_dir / "video.mp4"
            video_path.write_bytes(b"fake")
            return video_path

        mock_dl.side_effect = fake_download
        mock_tr.return_value = ("transcript text", [])

        ctx = await stage.run(sample_context)

    source_dir = sample_context.work_dir / "source"
    assert source_dir.exists()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_acquire.py -v`
Expected: FAIL — import error

- [ ] **Step 4: Implement acquire stage**

```python
# src/pipeline/stages/acquire.py
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import structlog

from pipeline.stages.base import PipelineContext, PipelineStage

logger = structlog.get_logger()


def download_video(url: str, output_dir: Path, resolution: str = "720p") -> Path:
    """Download video via yt-dlp. Returns path to downloaded file."""
    output_template = str(output_dir / "video.%(ext)s")
    cmd = [
        "yt-dlp",
        "-f", f"bestvideo[height<={resolution[:-1]}]+bestaudio/best[height<={resolution[:-1]}]",
        "--merge-output-format", "mp4",
        "-o", output_template,
        url,
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)

    # Find the downloaded file
    for f in output_dir.iterdir():
        if f.suffix == ".mp4" and f.stem.startswith("video"):
            return f
    raise FileNotFoundError(f"No video file found in {output_dir}")


def extract_transcript(url: str) -> tuple[str, list[dict]]:
    """Extract transcript. Tries youtube-transcript-api first, falls back to yt-dlp subs."""
    video_id = _extract_video_id(url)
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        transcript_data = YouTubeTranscriptApi.get_transcript(video_id, languages=["en"])
        full_text = " ".join(entry["text"] for entry in transcript_data)
        return full_text, transcript_data
    except Exception as e:
        logger.warning("youtube-transcript-api failed, trying yt-dlp subs", error=str(e))
        return _extract_via_ytdlp(url)


def _extract_video_id(url: str) -> str:
    """Extract video ID from various YouTube URL formats."""
    if "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]
    if "v=" in url:
        return url.split("v=")[1].split("&")[0]
    raise ValueError(f"Cannot extract video ID from: {url}")


def _extract_via_ytdlp(url: str) -> tuple[str, list[dict]]:
    """Fallback: use yt-dlp to download auto-subs."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        cmd = [
            "yt-dlp",
            "--write-auto-sub", "--sub-lang", "en",
            "--skip-download",
            "-o", f"{tmpdir}/subs",
            url,
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)

        # Find and parse the subtitle file
        tmppath = Path(tmpdir)
        for f in tmppath.iterdir():
            if f.suffix in (".vtt", ".srt"):
                text = f.read_text(encoding="utf-8")
                return text, []

    raise RuntimeError("No transcript available via any method")


class AcquireStage(PipelineStage):
    @property
    def name(self) -> str:
        return "acquire"

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        logger.info("acquire.start", url=ctx.source_url)

        source_dir = ctx.work_dir / "source"
        source_dir.mkdir(parents=True, exist_ok=True)

        # Download video
        ctx.video_path = download_video(
            ctx.source_url, source_dir, resolution="720p"
        )
        logger.info("acquire.video_downloaded", path=str(ctx.video_path))

        # Extract transcript
        full_text, raw_data = extract_transcript(ctx.source_url)
        ctx.transcript_text = full_text

        # Save transcript as SRT for reference
        transcript_path = source_dir / "transcript.json"
        transcript_path.write_text(
            json.dumps(raw_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        ctx.transcript_path = transcript_path
        logger.info("acquire.transcript_extracted", chars=len(full_text))

        return ctx
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/unit/test_acquire.py -v`
Expected: 2 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/stages/acquire.py tests/unit/test_acquire.py tests/fixtures/transcript.json
git commit -m "feat: add acquire stage with yt-dlp download and transcript extraction"
```

---

## Task 7: Analyze Stage

**Files:**
- Create: `src/pipeline/stages/analyze.py`
- Create: `tests/unit/test_analyze.py`
- Create: `tests/fixtures/claude_analysis_response.json`

- [ ] **Step 1: Create Claude analysis response fixture**

```json
{
  "story_structure": {
    "hook": "Officer encounters suspect at 2AM traffic stop",
    "beats": [
      {"timestamp": "0:00-0:30", "beat": "hook", "description": "Bodycam activates, officer approaches vehicle"},
      {"timestamp": "0:30-2:00", "beat": "context", "description": "Dispatch call details, location established"},
      {"timestamp": "2:00-5:00", "beat": "rising_action", "description": "Driver becomes uncooperative"},
      {"timestamp": "5:00-7:00", "beat": "climax", "description": "Pursuit begins"},
      {"timestamp": "7:00-9:00", "beat": "aftermath", "description": "Suspect apprehended, charges filed"}
    ],
    "emotional_arc": "tension_build"
  },
  "knowledge_graph": {
    "entities": [
      {"name": "Officer Johnson", "role": "police_officer", "department": "Austin PD"},
      {"name": "Suspect", "role": "driver", "charges": ["evading arrest", "DUI"]}
    ],
    "location": {"city": "Austin", "state": "Texas", "setting": "highway"},
    "conflicts": ["authority_vs_resistance", "law_enforcement_procedure"],
    "context_needed_for_zh_tw": [
      "US traffic stop procedures differ from Taiwan",
      "DUI legal consequences in Texas",
      "Bodycam mandate policies in US police departments"
    ]
  },
  "clip_timestamps": [[0, 30], [120, 135], [300, 315], [420, 435]]
}
```

Save to `tests/fixtures/claude_analysis_response.json`.

- [ ] **Step 2: Write tests for analyze stage**

```python
# tests/unit/test_analyze.py
import json
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from pipeline.stages.analyze import AnalyzeStage, build_analysis_prompt
from pipeline.stages.base import PipelineContext


@pytest.fixture
def analysis_fixture() -> dict:
    path = Path(__file__).parent.parent / "fixtures" / "claude_analysis_response.json"
    return json.loads(path.read_text())


def test_build_analysis_prompt():
    prompt = build_analysis_prompt("This is a transcript about a traffic stop in Austin.")
    assert "transcript" in prompt.lower()
    assert "story_structure" in prompt or "story structure" in prompt.lower()
    assert "knowledge_graph" in prompt or "knowledge graph" in prompt.lower()


@pytest.mark.asyncio
async def test_analyze_extracts_structure(sample_context, analysis_fixture):
    sample_context.transcript_text = "Officer Johnson responded to a call..."
    stage = AnalyzeStage()
    assert stage.name == "analyze"

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(analysis_fixture))]

    with patch("pipeline.stages.analyze.get_anthropic_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_client_fn.return_value = mock_client

        ctx = await stage.run(sample_context)

    assert ctx.story_structure is not None
    assert "beats" in ctx.story_structure
    assert ctx.knowledge_graph is not None
    assert "entities" in ctx.knowledge_graph
    assert ctx.clip_timestamps is not None
    assert len(ctx.clip_timestamps) > 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_analyze.py -v`
Expected: FAIL — import error

- [ ] **Step 4: Implement analyze stage**

```python
# src/pipeline/stages/analyze.py
from __future__ import annotations

import json
from pathlib import Path

import structlog

from pipeline.config import PipelineConfig
from pipeline.stages.base import PipelineContext, PipelineStage

logger = structlog.get_logger()


def get_anthropic_client():
    """Create Anthropic client from config."""
    import anthropic
    config = PipelineConfig()
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def build_analysis_prompt(transcript: str) -> str:
    """Build the Claude prompt for story analysis."""
    return f"""Analyze this video transcript and extract two things:

1. **Story structure**: Identify the narrative beats with approximate timestamps.
   - hook: the most dramatic/attention-grabbing moment
   - context: setting, people, background
   - rising_action: escalation of events
   - climax: peak tension
   - aftermath: resolution, consequences

2. **Knowledge graph**: Extract entities, relationships, conflicts, and context that a non-US audience would need explained.

3. **Clip timestamps**: Suggest 4-8 short segments (5-15 seconds each) that would work as visual reference clips in a ported video. Focus on high-visual-impact moments.

Return ONLY valid JSON in this exact format:
{{
  "story_structure": {{
    "hook": "one-line description of the hook",
    "beats": [
      {{"timestamp": "M:SS-M:SS", "beat": "hook|context|rising_action|climax|aftermath", "description": "what happens"}}
    ],
    "emotional_arc": "tension_build|mystery_reveal|justice_served|survival|tragedy"
  }},
  "knowledge_graph": {{
    "entities": [{{"name": "...", "role": "...", "details": "..."}}],
    "location": {{"city": "...", "state": "...", "setting": "..."}},
    "conflicts": ["..."],
    "context_needed_for_target_audience": ["..."]
  }},
  "clip_timestamps": [[start_sec, end_sec], ...]
}}

TRANSCRIPT:
{transcript}"""


class AnalyzeStage(PipelineStage):
    @property
    def name(self) -> str:
        return "analyze"

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.transcript_text:
            raise ValueError("No transcript available — run acquire stage first")

        logger.info("analyze.start", transcript_len=len(ctx.transcript_text))

        client = get_anthropic_client()
        config = PipelineConfig()
        prompt = build_analysis_prompt(ctx.transcript_text)

        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        raw_text = response.content[0].text
        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1].rsplit("```", 1)[0]

        result = json.loads(raw_text)

        ctx.story_structure = result["story_structure"]
        ctx.knowledge_graph = result["knowledge_graph"]
        ctx.clip_timestamps = [tuple(ts) for ts in result["clip_timestamps"]]

        # Save analysis to work_dir
        analysis_dir = ctx.work_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        (analysis_dir / "structure.json").write_text(
            json.dumps(ctx.story_structure, indent=2, ensure_ascii=False)
        )
        (analysis_dir / "knowledge_graph.json").write_text(
            json.dumps(ctx.knowledge_graph, indent=2, ensure_ascii=False)
        )

        logger.info("analyze.complete", beats=len(ctx.story_structure.get("beats", [])))
        return ctx
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/unit/test_analyze.py -v`
Expected: 2 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/stages/analyze.py tests/unit/test_analyze.py tests/fixtures/claude_analysis_response.json
git commit -m "feat: add analyze stage with Claude API story structure extraction"
```

---

## Task 8: Scriptwrite Stage

**Files:**
- Create: `src/pipeline/stages/scriptwrite.py`
- Create: `tests/unit/test_scriptwrite.py`
- Create: `tests/fixtures/claude_scriptwrite_response.json`
- Create: `tests/fixtures/sample_script.md`

- [ ] **Step 1: Create scriptwrite response fixture**

```json
{
  "script": "[HOOK]\n[CLIP:00:05-00:20]\n在深夜兩點的德州奧斯汀，一名員警攔下了一輛行駛異常的車輛，接下來發生的事情，讓在場所有人都始料未及。\n\n[CONTEXT]\n[OVERLAY:map:Austin, Texas]\n這起事件發生在美國德州的首府奧斯汀。在美國，警察有權在路上攔檢可疑車輛，這跟台灣的臨檢制度有些不同。\n\n[OVERLAY:namecard:乘客甲, 32歲, 駕駛]\n當晚值班的乘森警官接到了一通報案電話，指出有一輛車在公路上蛇行。\n\n[RISING]\n[CLIP:02:00-02:15]\n當警官靠近車窗時，他立刻聞到了濃烈的酒味。\n\n[PAUSE:2s]\n在美國，酒駕（DUI）是非常嚴重的罪行。在德州，初犯就可能面臨最高180天的監禁和2000美元的罰款。\n\n[CLIMAX]\n[CLIP:05:00-05:15]\n駕駛突然發動車子，高速駛離現場。一場驚心動魄的追逐就此展開。\n\n[AFTERMATH]\n[CLIP:07:00-07:10]\n最終，嫌疑人在十分鐘後被成功攔截逮捕，被加控拒捕和危險駕駛等多項罪名。\n\n[ANALYSIS]\n[OVERLAY:text:此案件結果]\n這起案件凸顯了美國警察在處理酒駕案件時所面臨的風險。"
}
```

Save to `tests/fixtures/claude_scriptwrite_response.json`.

Also save the `script` field value as `tests/fixtures/sample_script.md` (for compose tests later).

- [ ] **Step 2: Write tests**

```python
# tests/unit/test_scriptwrite.py
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from pipeline.stages.scriptwrite import (
    ScriptwriteStage,
    build_scriptwrite_prompt,
    parse_script_markers,
)
from pipeline.stages.base import PipelineContext


@pytest.fixture
def scriptwrite_fixture() -> dict:
    path = Path(__file__).parent.parent / "fixtures" / "claude_scriptwrite_response.json"
    return json.loads(path.read_text())


def test_build_scriptwrite_prompt():
    prompt = build_scriptwrite_prompt(
        story_structure={"hook": "test", "beats": []},
        knowledge_graph={"entities": [], "conflicts": []},
        locale="zh-TW",
    )
    assert "zh-TW" in prompt or "Traditional Chinese" in prompt
    assert "NOT" in prompt or "not translation" in prompt.lower() or "原創" in prompt


def test_parse_script_markers():
    script = "[HOOK]\n[CLIP:01:23-01:35]\n一段文字\n[OVERLAY:map:Texas]\n更多文字"
    markers = parse_script_markers(script)
    sections = [m for m in markers if m["type"] == "section"]
    clips = [m for m in markers if m["type"] == "clip"]
    overlays = [m for m in markers if m["type"] == "overlay"]
    narration = [m for m in markers if m["type"] == "narration"]
    assert len(sections) == 1
    assert sections[0]["value"] == "HOOK"
    assert len(clips) == 1
    assert len(overlays) == 1
    assert len(narration) >= 1


@pytest.mark.asyncio
async def test_scriptwrite_produces_script(sample_context, scriptwrite_fixture):
    sample_context.story_structure = {"hook": "test", "beats": []}
    sample_context.knowledge_graph = {"entities": [], "conflicts": []}
    sample_context.clip_timestamps = [[5, 20], [120, 135]]

    stage = ScriptwriteStage()
    assert stage.name == "scriptwrite"

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=scriptwrite_fixture["script"])]

    with patch("pipeline.stages.scriptwrite.get_anthropic_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_client_fn.return_value = mock_client

        ctx = await stage.run(sample_context)

    assert ctx.script_path is not None
    assert ctx.script_path.exists()
    script_text = ctx.script_path.read_text()
    assert "[HOOK]" in script_text
    assert "[CLIP:" in script_text
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_scriptwrite.py -v`
Expected: FAIL — import error

- [ ] **Step 4: Implement scriptwrite stage**

```python
# src/pipeline/stages/scriptwrite.py
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import structlog

from pipeline.config import PipelineConfig
from pipeline.stages.analyze import get_anthropic_client
from pipeline.stages.base import PipelineContext, PipelineStage

logger = structlog.get_logger()

LOCALE_INSTRUCTIONS = {
    "zh-TW": (
        "Write in Traditional Chinese (zh-TW), Taiwan usage conventions. "
        "Explain US-specific context (legal system, geography, policing norms) "
        "that Taiwanese audiences need. Use conversational but authoritative tone."
    ),
    "ja": (
        "Write in Japanese. Use appropriate keigo level for documentary narration. "
        "Add cultural context bridging US and Japanese norms."
    ),
    "es-MX": (
        "Write in Latin American Spanish (Mexican variant). "
        "Explain US cultural context for Latin American audiences."
    ),
}


def build_scriptwrite_prompt(
    story_structure: dict[str, Any],
    knowledge_graph: dict[str, Any],
    locale: str,
) -> str:
    """Build the Claude prompt for script adaptation (NOT translation)."""
    locale_instruction = LOCALE_INSTRUCTIONS.get(locale, LOCALE_INSTRUCTIONS["zh-TW"])

    return f"""You are a scriptwriter for a YouTube channel. Write a NEW, ORIGINAL script
based on the story analysis below. This is NOT a translation — it is a cultural adaptation.
Restructure the narrative for maximum engagement with the target audience.

LOCALE: {locale}
LANGUAGE INSTRUCTION: {locale_instruction}

STORY STRUCTURE:
{json.dumps(story_structure, indent=2, ensure_ascii=False)}

KNOWLEDGE GRAPH:
{json.dumps(knowledge_graph, indent=2, ensure_ascii=False)}

VIDEO STRUCTURE (follow this):
- [HOOK] (0-30s): Start with the most dramatic moment out of context
- [CONTEXT] (30s-2min): Map, people, setting, background
- [RISING] (2-6min): Escalation of events
- [CLIMAX] (6-8min): Peak tension
- [AFTERMATH] (8-10min): Resolution, consequences
- [ANALYSIS] (10-12min): Commentary, broader implications

USE THESE MARKERS in your script:
- [CLIP:MM:SS-MM:SS] — reference a source video segment
- [OVERLAY:map:Location] — map overlay
- [OVERLAY:namecard:Name, Age, Role] — name card
- [OVERLAY:text:Important Info] — text card
- [OVERLAY:title:Title Text] — title card
- [PAUSE:Ns] — dramatic pause (N seconds)

Plain text = narration (will be sent to TTS).

Keep source clips SHORT (5-15 seconds each). Original narration must be 50-70%+ of the video.

Write ONLY the script with markers. No meta-commentary."""


def parse_script_markers(script: str) -> list[dict[str, Any]]:
    """Parse a script into a list of typed markers and narration blocks."""
    markers: list[dict[str, Any]] = []
    lines = script.split("\n")

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Section marker: [HOOK], [CONTEXT], etc.
        if re.match(r"^\[(HOOK|CONTEXT|RISING|CLIMAX|AFTERMATH|ANALYSIS)\]$", stripped):
            markers.append({"type": "section", "value": stripped[1:-1]})
        # Clip reference: [CLIP:MM:SS-MM:SS]
        elif re.match(r"^\[CLIP:\d{1,2}:\d{2}-\d{1,2}:\d{2}\]$", stripped):
            times = stripped[6:-1]
            start, end = times.split("-")
            markers.append({"type": "clip", "start": start, "end": end})
        # Overlay: [OVERLAY:type:content]
        elif stripped.startswith("[OVERLAY:"):
            inner = stripped[9:-1]
            overlay_type, content = inner.split(":", 1)
            markers.append({"type": "overlay", "overlay_type": overlay_type, "content": content})
        # Pause: [PAUSE:Ns]
        elif re.match(r"^\[PAUSE:\d+s\]$", stripped):
            seconds = int(stripped[7:-2])
            markers.append({"type": "pause", "seconds": seconds})
        else:
            # Narration text
            markers.append({"type": "narration", "text": stripped})

    return markers


class ScriptwriteStage(PipelineStage):
    @property
    def name(self) -> str:
        return "scriptwrite"

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.story_structure or not ctx.knowledge_graph:
            raise ValueError("No analysis available — run analyze stage first")

        logger.info("scriptwrite.start", locale=ctx.locale)

        client = get_anthropic_client()
        config = PipelineConfig()

        prompt = build_scriptwrite_prompt(
            ctx.story_structure, ctx.knowledge_graph, ctx.locale,
        )

        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )

        script_text = response.content[0].text

        # Save script
        script_dir = ctx.work_dir / "script"
        script_dir.mkdir(parents=True, exist_ok=True)
        script_path = script_dir / f"script_{ctx.locale}.md"
        script_path.write_text(script_text, encoding="utf-8")
        ctx.script_path = script_path

        logger.info("scriptwrite.complete", path=str(script_path), chars=len(script_text))
        return ctx
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/unit/test_scriptwrite.py -v`
Expected: 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/stages/scriptwrite.py tests/unit/test_scriptwrite.py tests/fixtures/claude_scriptwrite_response.json tests/fixtures/sample_script.md
git commit -m "feat: add scriptwrite stage with cultural adaptation prompts and marker parsing"
```

---

## Task 9: TTS Stage

**Files:**
- Create: `src/pipeline/stages/tts.py`
- Create: `tests/unit/test_tts.py`

- [ ] **Step 1: Write tests**

```python
# tests/unit/test_tts.py
import json
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from pipeline.stages.tts import TtsStage, extract_narration_segments
from pipeline.stages.base import PipelineContext


def test_extract_narration_segments():
    script = (
        "[HOOK]\n"
        "[CLIP:00:05-00:20]\n"
        "這是第一段旁白文字。\n"
        "\n"
        "[OVERLAY:map:Texas]\n"
        "這是第二段旁白文字。\n"
        "[PAUSE:2s]\n"
        "這是第三段。\n"
    )
    segments = extract_narration_segments(script)
    assert len(segments) == 3
    assert segments[0] == "這是第一段旁白文字。"
    assert segments[1] == "這是第二段旁白文字。"
    assert segments[2] == "這是第三段。"


@pytest.mark.asyncio
async def test_tts_generates_audio(sample_context, tmp_path):
    script_dir = sample_context.work_dir / "script"
    script_dir.mkdir(parents=True)
    script_path = script_dir / "script_zh-TW.md"
    script_path.write_text(
        "[HOOK]\n一段測試旁白。\n[CONTEXT]\n第二段旁白。\n",
        encoding="utf-8",
    )
    sample_context.script_path = script_path

    stage = TtsStage()
    assert stage.name == "tts"

    with patch("pipeline.stages.tts.generate_edge_tts") as mock_tts:
        # Mock TTS: create dummy audio files
        async def fake_tts(text, voice, output_path):
            output_path.write_bytes(b"fake audio")
            return {"duration_ms": 3000, "word_timings": []}

        mock_tts.side_effect = fake_tts

        ctx = await stage.run(sample_context)

    assert ctx.narration_path is not None
    assert ctx.narration_path.exists()
    assert ctx.subtitle_path is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_tts.py -v`
Expected: FAIL — import error

- [ ] **Step 3: Implement TTS stage**

```python
# src/pipeline/stages/tts.py
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import structlog

from pipeline.config import PipelineConfig
from pipeline.stages.base import PipelineContext, PipelineStage
from pipeline.utils.srt import SrtEntry, write_srt

logger = structlog.get_logger()


def extract_narration_segments(script: str) -> list[str]:
    """Extract plain narration text from a script with markers."""
    segments: list[str] = []
    marker_pattern = re.compile(
        r"^\[(HOOK|CONTEXT|RISING|CLIMAX|AFTERMATH|ANALYSIS|"
        r"CLIP:[^\]]+|OVERLAY:[^\]]+|PAUSE:\d+s)\]$"
    )

    for line in script.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if marker_pattern.match(stripped):
            continue
        segments.append(stripped)

    return segments


async def generate_edge_tts(text: str, voice: str, output_path: Path) -> dict[str, Any]:
    """Generate TTS audio using edge-tts. Returns timing metadata."""
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    submaker = edge_tts.SubMaker()

    with open(output_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.feed(chunk)

    return {
        "duration_ms": 0,  # edge-tts doesn't provide total duration directly
        "word_timings": [],  # simplified for MVP
    }


class TtsStage(PipelineStage):
    @property
    def name(self) -> str:
        return "tts"

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.script_path or not ctx.script_path.exists():
            raise ValueError("No script available — run scriptwrite stage first")

        logger.info("tts.start", locale=ctx.locale)

        config = PipelineConfig()
        voice = config.get_tts_voice(ctx.locale)
        script_text = ctx.script_path.read_text(encoding="utf-8")

        audio_dir = ctx.work_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        segments = extract_narration_segments(script_text)
        logger.info("tts.segments", count=len(segments))

        # Generate audio per segment
        segment_paths: list[Path] = []
        segment_timings: list[dict[str, Any]] = []
        cumulative_ms = 0

        for i, text in enumerate(segments):
            seg_path = audio_dir / f"segment_{i:03d}.mp3"
            timing = await generate_edge_tts(text, voice, seg_path)

            # Estimate duration from file size (~16kB/sec for edge-tts mp3)
            file_size = seg_path.stat().st_size
            est_duration_ms = max(int(file_size / 16 * 1000), 1000)

            segment_timings.append({
                "index": i,
                "text": text,
                "path": str(seg_path),
                "start_ms": cumulative_ms,
                "duration_ms": est_duration_ms,
            })
            segment_paths.append(seg_path)
            cumulative_ms += est_duration_ms

        # Concatenate all segments into one file
        narration_path = audio_dir / f"narration_{ctx.locale}.mp3"
        _concatenate_audio(segment_paths, narration_path)
        ctx.narration_path = narration_path

        # Generate SRT from segment timings
        srt_entries = [
            SrtEntry(
                index=t["index"] + 1,
                start_ms=t["start_ms"],
                end_ms=t["start_ms"] + t["duration_ms"],
                text=t["text"],
            )
            for t in segment_timings
        ]
        subtitle_path = audio_dir / f"subtitles_{ctx.locale}.srt"
        write_srt(srt_entries, subtitle_path)
        ctx.subtitle_path = subtitle_path

        ctx.segment_timings = segment_timings

        logger.info("tts.complete", segments=len(segments), path=str(narration_path))
        return ctx


def _concatenate_audio(paths: list[Path], output: Path) -> None:
    """Concatenate MP3 files by simple binary append (sufficient for MP3)."""
    with open(output, "wb") as out:
        for p in paths:
            out.write(p.read_bytes())
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_tts.py -v`
Expected: 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/stages/tts.py tests/unit/test_tts.py
git commit -m "feat: add TTS stage with edge-tts and SRT subtitle generation"
```

---

## Task 10: Compose Stage

**Files:**
- Create: `src/pipeline/stages/compose.py`
- Create: `tests/unit/test_compose.py`

- [ ] **Step 1: Write tests**

```python
# tests/unit/test_compose.py
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from pipeline.stages.compose import ComposeStage, build_composition_plan
from pipeline.stages.base import PipelineContext


def test_build_composition_plan():
    script = (
        "[HOOK]\n"
        "[CLIP:00:05-00:20]\n"
        "旁白文字\n"
        "[OVERLAY:map:Texas]\n"
        "更多旁白\n"
    )
    plan = build_composition_plan(script)
    assert any(step["type"] == "clip" for step in plan)
    assert any(step["type"] == "overlay" for step in plan)


@pytest.mark.asyncio
async def test_compose_builds_ffmpeg_commands(sample_context):
    # Set up all prerequisite paths
    source_dir = sample_context.work_dir / "source"
    source_dir.mkdir(parents=True)
    video_path = source_dir / "video.mp4"
    video_path.write_bytes(b"fake video")
    sample_context.video_path = video_path

    audio_dir = sample_context.work_dir / "audio"
    audio_dir.mkdir(parents=True)
    narration_path = audio_dir / "narration_zh-TW.mp3"
    narration_path.write_bytes(b"fake audio")
    sample_context.narration_path = narration_path

    subtitle_path = audio_dir / "subtitles_zh-TW.srt"
    subtitle_path.write_text("1\n00:00:00,000 --> 00:00:03,000\n測試\n")
    sample_context.subtitle_path = subtitle_path

    script_dir = sample_context.work_dir / "script"
    script_dir.mkdir(parents=True)
    script_path = script_dir / "script_zh-TW.md"
    script_path.write_text("[HOOK]\n[CLIP:00:05-00:20]\n旁白\n")
    sample_context.script_path = script_path

    sample_context.segment_timings = [
        {"index": 0, "text": "旁白", "start_ms": 0, "duration_ms": 3000}
    ]

    stage = ComposeStage()
    assert stage.name == "compose"

    with patch("pipeline.stages.compose.run_ffmpeg") as mock_ffmpeg:
        mock_ffmpeg.return_value = MagicMock(returncode=0)
        # Also need to create the expected output file
        with patch.object(stage, "_compose_video") as mock_compose:
            final_path = sample_context.work_dir / "compose" / "final_zh-TW.mp4"
            final_path.parent.mkdir(parents=True, exist_ok=True)
            final_path.write_bytes(b"fake final video")
            mock_compose.return_value = final_path

            ctx = await stage.run(sample_context)

    assert ctx.final_video_path is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_compose.py -v`
Expected: FAIL — import error

- [ ] **Step 3: Implement compose stage**

```python
# src/pipeline/stages/compose.py
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog

from pipeline.stages.base import PipelineContext, PipelineStage
from pipeline.stages.scriptwrite import parse_script_markers
from pipeline.utils.ffmpeg import (
    build_extract_clip_cmd,
    build_burn_subtitles_cmd,
    run_ffmpeg,
    check_ffmpeg_available,
)

logger = structlog.get_logger()


def build_composition_plan(script: str) -> list[dict[str, Any]]:
    """Parse script markers into a sequential composition plan."""
    markers = parse_script_markers(script)
    plan: list[dict[str, Any]] = []

    for marker in markers:
        if marker["type"] == "clip":
            plan.append({
                "type": "clip",
                "start": marker["start"],
                "end": marker["end"],
            })
        elif marker["type"] == "overlay":
            plan.append({
                "type": "overlay",
                "overlay_type": marker["overlay_type"],
                "content": marker["content"],
            })
        elif marker["type"] == "narration":
            plan.append({"type": "narration", "text": marker["text"]})
        elif marker["type"] == "pause":
            plan.append({"type": "pause", "seconds": marker["seconds"]})

    return plan


def _timestamp_to_seconds(ts: str) -> float:
    """Convert MM:SS to seconds."""
    parts = ts.split(":")
    return int(parts[0]) * 60 + int(parts[1])


class ComposeStage(PipelineStage):
    @property
    def name(self) -> str:
        return "compose"

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.narration_path or not ctx.subtitle_path or not ctx.video_path:
            raise ValueError("Missing narration, subtitles, or source video")
        if not ctx.script_path:
            raise ValueError("Missing script")

        if not check_ffmpeg_available():
            raise RuntimeError("ffmpeg not found on PATH — install with: sudo apt install ffmpeg")

        logger.info("compose.start")

        compose_dir = ctx.work_dir / "compose"
        compose_dir.mkdir(parents=True, exist_ok=True)

        final_path = await self._compose_video(ctx, compose_dir)
        ctx.final_video_path = final_path

        logger.info("compose.complete", path=str(final_path))
        return ctx

    async def _compose_video(self, ctx: PipelineContext, compose_dir: Path) -> Path:
        """MVP composition: narration audio + burned subtitles over source clips.

        Full composition (clips + overlays + narration interleaving) is complex.
        MVP approach: take the source video, replace audio with narration, burn subtitles.
        """
        assert ctx.video_path is not None
        assert ctx.narration_path is not None
        assert ctx.subtitle_path is not None

        # Step 1: Extract relevant clips from source video
        script_text = ctx.script_path.read_text(encoding="utf-8") if ctx.script_path else ""
        plan = build_composition_plan(script_text)

        clip_segments = [s for s in plan if s["type"] == "clip"]
        clip_paths: list[Path] = []

        for i, clip in enumerate(clip_segments):
            clip_path = compose_dir / f"clip_{i:03d}.mp4"
            start = _timestamp_to_seconds(clip["start"])
            end = _timestamp_to_seconds(clip["end"])
            cmd = build_extract_clip_cmd(
                str(ctx.video_path), str(clip_path), start, end
            )
            run_ffmpeg(cmd)
            clip_paths.append(clip_path)

        # Step 2: Concatenate clips (or use full source if no clips extracted)
        if clip_paths:
            filelist = compose_dir / "clips.txt"
            filelist.write_text(
                "\n".join(f"file '{p}'" for p in clip_paths),
                encoding="utf-8",
            )
            clips_video = compose_dir / "clips_concat.mp4"
            from pipeline.utils.ffmpeg import build_concat_cmd
            run_ffmpeg(build_concat_cmd(str(filelist), str(clips_video)))
            base_video = clips_video
        else:
            base_video = ctx.video_path

        # Step 3: Replace audio with narration
        narration_video = compose_dir / "with_narration.mp4"
        run_ffmpeg([
            "ffmpeg", "-y",
            "-i", str(base_video),
            "-i", str(ctx.narration_path),
            "-c:v", "copy",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            str(narration_video),
        ])

        # Step 4: Burn subtitles
        final_path = compose_dir / f"final_{ctx.locale}.mp4"
        cmd = build_burn_subtitles_cmd(
            str(narration_video),
            str(ctx.subtitle_path),
            str(final_path),
            font_name="Noto Sans CJK TC",
        )
        run_ffmpeg(cmd)

        return final_path
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_compose.py -v`
Expected: 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/stages/compose.py tests/unit/test_compose.py
git commit -m "feat: add compose stage with FFmpeg clip extraction and subtitle burning"
```

---

## Task 11: Orchestrator

**Files:**
- Create: `src/pipeline/orchestrator.py`
- Create: `tests/unit/test_orchestrator.py`

- [ ] **Step 1: Write tests**

```python
# tests/unit/test_orchestrator.py
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from pipeline.orchestrator import Orchestrator, StageResult
from pipeline.stages.base import PipelineContext, PipelineStage


class FakePassStage(PipelineStage):
    @property
    def name(self) -> str:
        return "fake_pass"

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        ctx.transcript_text = "processed"
        return ctx


class FakeFailStage(PipelineStage):
    @property
    def name(self) -> str:
        return "fake_fail"

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        raise RuntimeError("Stage exploded")


@pytest.mark.asyncio
async def test_orchestrator_runs_stages_in_order(sample_context):
    orch = Orchestrator(stages=[FakePassStage()])
    result = await orch.run(sample_context)
    assert result.success
    assert result.ctx.transcript_text == "processed"


@pytest.mark.asyncio
async def test_orchestrator_stops_on_failure(sample_context):
    orch = Orchestrator(stages=[FakeFailStage(), FakePassStage()])
    result = await orch.run(sample_context)
    assert not result.success
    assert result.failed_stage == "fake_fail"
    assert "exploded" in result.error


@pytest.mark.asyncio
async def test_orchestrator_saves_context_after_each_stage(sample_context):
    orch = Orchestrator(stages=[FakePassStage()])
    result = await orch.run(sample_context)
    context_file = sample_context.work_dir / "context.json"
    assert context_file.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_orchestrator.py -v`
Expected: FAIL — import error

- [ ] **Step 3: Implement orchestrator**

```python
# src/pipeline/orchestrator.py
from __future__ import annotations

from dataclasses import dataclass

import structlog

from pipeline.stages.base import PipelineContext, PipelineStage

logger = structlog.get_logger()


@dataclass
class StageResult:
    success: bool
    ctx: PipelineContext
    failed_stage: str = ""
    error: str = ""


class Orchestrator:
    """Chains pipeline stages, handles state persistence and resume."""

    def __init__(self, stages: list[PipelineStage]) -> None:
        self.stages = stages

    async def run(
        self,
        ctx: PipelineContext,
        start_from: str | None = None,
    ) -> StageResult:
        """Run all stages sequentially. Saves context after each stage."""
        skip = start_from is not None

        for stage in self.stages:
            if skip:
                if stage.name == start_from:
                    skip = False
                else:
                    logger.info("orchestrator.skip", stage=stage.name)
                    continue

            logger.info("orchestrator.stage.start", stage=stage.name)
            try:
                ctx = await stage.run(ctx)
                ctx.save()
                logger.info("orchestrator.stage.complete", stage=stage.name)
            except Exception as e:
                logger.error("orchestrator.stage.failed", stage=stage.name, error=str(e))
                return StageResult(
                    success=False,
                    ctx=ctx,
                    failed_stage=stage.name,
                    error=str(e),
                )

        return StageResult(success=True, ctx=ctx)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_orchestrator.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/orchestrator.py tests/unit/test_orchestrator.py
git commit -m "feat: add orchestrator with sequential stage execution and resume support"
```

---

## Task 12: CLI

**Files:**
- Create: `src/pipeline/cli.py`
- Create: `tests/unit/test_cli.py`

- [ ] **Step 1: Write test for CLI help output**

```python
# tests/unit/test_cli.py
from typer.testing import CliRunner

from pipeline.cli import app

runner = CliRunner()


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "produce" in result.output


def test_produce_help():
    result = runner.invoke(app, ["produce", "--help"])
    assert result.exit_code == 0
    assert "--url" in result.output
    assert "--locale" in result.output
    assert "--skip-review" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_cli.py -v`
Expected: FAIL — import error

- [ ] **Step 3: Implement CLI**

```python
# src/pipeline/cli.py
from __future__ import annotations

import asyncio
from pathlib import Path

import structlog
import typer

from pipeline.config import PipelineConfig
from pipeline.models import Locale
from pipeline.orchestrator import Orchestrator
from pipeline.stages.acquire import AcquireStage
from pipeline.stages.analyze import AnalyzeStage
from pipeline.stages.base import PipelineContext
from pipeline.stages.compose import ComposeStage
from pipeline.stages.scriptwrite import ScriptwriteStage
from pipeline.stages.tts import TtsStage

logger = structlog.get_logger()
app = typer.Typer(name="pipeline", help="YouTube content porting pipeline")


@app.command()
def produce(
    url: str = typer.Option(..., "--url", help="YouTube video URL"),
    locale: str = typer.Option("zh-TW", "--locale", help="Target locale (zh-TW, ja, es-MX)"),
    start_from: str | None = typer.Option(None, "--start-from", help="Resume from stage"),
    project_id: int = typer.Option(0, "--project-id", help="Project ID (0 = auto)"),
    skip_review: bool = typer.Option(False, "--skip-review", help="Skip human script review gate"),
) -> None:
    """Run the full production pipeline for a single video."""
    config = PipelineConfig()

    # Create project directory
    if project_id == 0:
        import time
        project_id = int(time.time())

    work_dir = config.OUTPUT_DIR / "projects" / str(project_id)
    work_dir.mkdir(parents=True, exist_ok=True)

    ctx = PipelineContext(
        project_id=project_id,
        source_url=url,
        locale=locale,
        work_dir=work_dir,
    )

    # Phase 1: acquire → analyze → scriptwrite
    pre_review_stages = [
        AcquireStage(),
        AnalyzeStage(),
        ScriptwriteStage(),
    ]

    # Phase 2: tts → compose (after human review)
    post_review_stages = [
        TtsStage(),
        ComposeStage(),
    ]

    # Run phase 1 (or resume from a specific stage)
    if start_from and start_from in ("tts", "compose"):
        # Resuming after review — load existing context
        ctx = PipelineContext.load(work_dir / "context.json")
        orch = Orchestrator(stages=post_review_stages)
        result = asyncio.run(orch.run(ctx, start_from=start_from))
    else:
        orch = Orchestrator(stages=pre_review_stages)
        result = asyncio.run(orch.run(ctx, start_from=start_from))

        if result.success and not skip_review:
            typer.echo(f"\n--- HUMAN REVIEW GATE ---")
            typer.echo(f"Script ready for review: {result.ctx.script_path}")
            typer.echo(f"Edit the script, then resume with:")
            typer.echo(f"  uv run pipeline produce --url \"{url}\" --locale {locale} "
                       f"--project-id {project_id} --start-from tts")
            return

        if result.success and skip_review:
            # Continue directly to phase 2
            orch = Orchestrator(stages=post_review_stages)
            result = asyncio.run(orch.run(result.ctx))

    if result.success:
        typer.echo(f"\nPipeline complete! Output: {result.ctx.final_video_path}")
    else:
        typer.echo(f"\nPipeline failed at stage '{result.failed_stage}': {result.error}")
        raise typer.Exit(code=1)


@app.command()
def acquire(
    url: str = typer.Option(..., "--url", help="YouTube video URL"),
) -> None:
    """Download video and extract transcript only."""
    config = PipelineConfig()
    import time
    project_id = int(time.time())
    work_dir = config.OUTPUT_DIR / "projects" / str(project_id)
    work_dir.mkdir(parents=True, exist_ok=True)

    ctx = PipelineContext(
        project_id=project_id,
        source_url=url,
        locale="zh-TW",
        work_dir=work_dir,
    )

    result = asyncio.run(Orchestrator(stages=[AcquireStage()]).run(ctx))
    if result.success:
        typer.echo(f"Acquired: {result.ctx.video_path}")
        typer.echo(f"Transcript: {result.ctx.transcript_path}")
    else:
        typer.echo(f"Failed: {result.error}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_cli.py -v`
Expected: 2 tests PASS

- [ ] **Step 5: Verify CLI works**

Run: `uv run pipeline --help`
Expected: Shows help with `produce` and `acquire` subcommands

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/cli.py tests/unit/test_cli.py
git commit -m "feat: add Typer CLI with produce and acquire subcommands"
```

---

## Task 13: Run All Tests + Lint

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All unit tests PASS (~15-18 tests)

- [ ] **Step 2: Run ruff lint**

Run: `uv run ruff check src/ tests/`
Expected: No errors (fix any that appear)

- [ ] **Step 3: Run ruff format**

Run: `uv run ruff format src/ tests/`
Expected: Files formatted

- [ ] **Step 4: Commit any lint fixes**

```bash
git add -u
git commit -m "style: apply ruff formatting and fix lint issues"
```

---

## Task 14: End-to-End Smoke Test (Manual)

This task requires API keys and network access. Run manually.

- [ ] **Step 1: Set up .env**

```bash
cp .env.example .env
# Edit .env and add your real PIPELINE_ANTHROPIC_API_KEY
```

- [ ] **Step 2: Verify system dependencies**

Run: `ffmpeg -version && fc-list | grep -i "noto.*cjk"`
Expected: FFmpeg version shown, Noto CJK fonts found. If not:
```bash
sudo apt install ffmpeg fonts-noto-cjk
```

- [ ] **Step 3: Run acquire only (test download + transcript)**

Run: `uv run pipeline acquire --url "https://www.youtube.com/watch?v=<short-test-video>"`
Expected: Video downloaded, transcript extracted, paths printed

- [ ] **Step 4: Run full pipeline on a short test video**

Run: `uv run pipeline produce --url "https://www.youtube.com/watch?v=<short-test-video>" --locale zh-TW`
Expected: Pipeline runs through acquire → analyze → scriptwrite → tts → compose. Final video at `output/projects/<id>/compose/final_zh-TW.mp4`

- [ ] **Step 5: Review outputs**

Check:
- `output/projects/<id>/analysis/structure.json` — story beats make sense?
- `output/projects/<id>/script/script_zh-TW.md` — script has markers, reads naturally in zh-TW?
- `output/projects/<id>/compose/final_zh-TW.mp4` — video plays, has audio, has subtitles?

- [ ] **Step 6: Commit and tag**

```bash
git add -A
git commit -m "feat: MVP production pipeline complete — acquire through compose"
git tag v0.1.0
```
