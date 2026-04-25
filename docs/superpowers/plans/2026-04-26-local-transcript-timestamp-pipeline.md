# Local Transcript + Timestamp-Aware Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--transcript` / `--video` flags to `pipeline produce` so local files skip re-fetching, and feed structured timestamps into ANALYZE so `clip` scene `start_sec`/`end_sec` values in the storyboard are accurate.

**Architecture:** A new `parse_transcript_file()` in `acquire.py` converts `.csv` / `.txt` transcripts into the pipeline's `{text, start, duration}` format. `AcquireStage` accepts optional local file paths and skips fetch/download when provided. `AnalyzeStage` loads the saved `transcript.json` and passes timestamped segments to `build_analysis_prompt()`, which formats them as `[0.08s–4.24s] text` so Claude produces accurate fact timestamps — no storyboard schema changes needed.

**Tech Stack:** Python stdlib (`csv`, `shutil`, `json`), existing `AcquireStage`, `AnalyzeStage`, Typer CLI.

---

## File Map

| Action | Path |
|--------|------|
| Modify | `src/pipeline/stages/acquire.py` |
| Modify | `src/pipeline/stages/analyze.py` |
| Modify | `src/pipeline/cli.py` |
| Create | `tests/unit/test_acquire_local.py` |
| Modify | `tests/unit/test_analyze.py` |

---

## Task 1: `parse_transcript_file()` — local file parser

**Files:**
- Modify: `src/pipeline/stages/acquire.py`
- Create: `tests/unit/test_acquire_local.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_acquire_local.py`:

```python
import csv
import io
from pathlib import Path

import pytest

from pipeline.stages.acquire import parse_transcript_file


# ── CSV format ────────────────────────────────────────────────────────────────

def test_parse_csv_basic(tmp_path: Path):
    f = tmp_path / "t.csv"
    f.write_text(
        "00:00,0.08,4.16,Mrs. Henry, excuse me.\n"
        "00:04,4.24,5.44,Well, I'm bringing my husband.\n",
        encoding="utf-8",
    )
    full_text, raw = parse_transcript_file(f)
    assert len(raw) == 2
    assert raw[0] == {"text": "Mrs. Henry, excuse me.", "start": 0.08, "duration": 4.16}
    assert raw[1] == {"text": "Well, I'm bringing my husband.", "start": 4.24, "duration": 5.44}
    assert "Mrs. Henry" in full_text
    assert "husband" in full_text


def test_parse_csv_skips_blank_rows(tmp_path: Path):
    f = tmp_path / "t.csv"
    f.write_text(
        "00:00,0.08,4.16,Mrs. Henry, excuse me.\n"
        "00:02,1.99,2.25,\n"
        "00:04,4.24,5.44,Well, I'm bringing my husband.\n",
        encoding="utf-8",
    )
    _, raw = parse_transcript_file(f)
    assert len(raw) == 2  # blank row filtered


def test_parse_csv_skips_malformed_rows(tmp_path: Path):
    f = tmp_path / "t.csv"
    f.write_text(
        "00:00,0.08,4.16,Good row.\n"
        "not,enough,cols\n"
        "00:04,bad_float,5.44,Also bad.\n",
        encoding="utf-8",
    )
    _, raw = parse_transcript_file(f)
    assert len(raw) == 1
    assert raw[0]["text"] == "Good row."


# ── TXT format ────────────────────────────────────────────────────────────────

def test_parse_txt_basic(tmp_path: Path):
    f = tmp_path / "t.txt"
    f.write_text(
        "00:00 Mrs. Henry, excuse me.\n"
        "00:04 Well, I'm bringing my husband.\n"
        "00:09 He makes more than I do.\n",
        encoding="utf-8",
    )
    full_text, raw = parse_transcript_file(f)
    assert len(raw) == 3
    assert raw[0]["start"] == 0.0
    assert raw[0]["duration"] == 4.0   # gap to next (4*60+0 - 0*60+0 = 4)
    assert raw[1]["start"] == 4.0
    assert raw[1]["duration"] == 5.0   # gap to 00:09
    assert raw[2]["duration"] == 2.0   # last entry defaults to 2.0s
    assert "Mrs. Henry" in full_text


def test_parse_txt_skips_blank_lines(tmp_path: Path):
    f = tmp_path / "t.txt"
    f.write_text(
        "00:00 First line.\n"
        "\n"
        "00:04 Second line.\n",
        encoding="utf-8",
    )
    _, raw = parse_transcript_file(f)
    assert len(raw) == 2
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd /home/tim-huang/content-creation
uv run pytest tests/unit/test_acquire_local.py -v 2>&1 | head -30
```

Expected: `ImportError` or `AttributeError` — `parse_transcript_file` does not exist yet.

- [ ] **Step 3: Implement `parse_transcript_file()` in `acquire.py`**

Add this function near the top of `src/pipeline/stages/acquire.py`, after the existing imports:

```python
import csv
import shutil
```

Add after the existing `_extract_via_ytdlp` function (before `class AcquireStage`):

```python
def parse_transcript_file(path: Path) -> tuple[str, list[dict]]:
    """Parse a local transcript file into (full_text, raw_data).

    Supports:
    - .csv  →  MM:SS, start_sec, duration_sec, text
    - .txt  →  MM:SS text  (duration inferred from gap to next entry)
    """
    if path.suffix == ".csv":
        return _parse_csv_transcript(path)
    return _parse_txt_transcript(path)


def _parse_csv_transcript(path: Path) -> tuple[str, list[dict]]:
    rows: list[dict] = []
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.reader(f):
            if len(row) < 4:
                continue
            text = row[3].strip()
            if not text:
                continue
            try:
                start = float(row[1])
                duration = float(row[2])
            except ValueError:
                continue
            rows.append({"text": text, "start": start, "duration": duration})
    full_text = " ".join(r["text"] for r in rows)
    return full_text, rows


def _parse_txt_transcript(path: Path) -> tuple[str, list[dict]]:
    entries: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or len(line) < 6 or line[2] != ":":
            continue
        try:
            mm = int(line[:2])
            ss = int(line[3:5])
            text = line[6:].strip()
        except ValueError:
            continue
        if not text:
            continue
        entries.append({"text": text, "start": float(mm * 60 + ss), "duration": 0.0})

    for i in range(len(entries) - 1):
        entries[i]["duration"] = entries[i + 1]["start"] - entries[i]["start"]
    if entries:
        entries[-1]["duration"] = 2.0

    full_text = " ".join(e["text"] for e in entries)
    return full_text, entries
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/unit/test_acquire_local.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/stages/acquire.py tests/unit/test_acquire_local.py
git commit -m "feat(acquire): add parse_transcript_file() for .csv and .txt local transcripts"
```

---

## Task 2: `AcquireStage` local file support

**Files:**
- Modify: `src/pipeline/stages/acquire.py`
- Modify: `tests/unit/test_acquire_local.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_acquire_local.py`:

```python
import json
from unittest.mock import patch

from pipeline.stages.acquire import AcquireStage
from pipeline.stages.base import PipelineContext


# ── AcquireStage with local files ─────────────────────────────────────────────

async def test_acquire_uses_local_transcript(tmp_path: Path):
    """Local transcript file skips YouTube API call."""
    work_dir = tmp_path / "project"
    work_dir.mkdir()
    ctx = PipelineContext(
        project_id=1, source_url="https://youtube.com/watch?v=test",
        locale="zh-TW", work_dir=work_dir,
    )

    transcript_file = tmp_path / "t.csv"
    transcript_file.write_text(
        "00:00,0.08,4.16,Mrs. Henry, excuse me.\n"
        "00:04,4.24,5.44,Well, I'm bringing my husband.\n",
        encoding="utf-8",
    )

    stage = AcquireStage(local_transcript=transcript_file)

    with (
        patch("pipeline.stages.acquire.download_video") as mock_dl,
        patch("pipeline.stages.acquire.extract_transcript") as mock_tr,
    ):
        mock_dl.side_effect = lambda url, out, resolution: _write_fake_video(out)
        ctx = await stage.run(ctx)

    mock_tr.assert_not_called()   # skipped
    assert ctx.transcript_text is not None
    assert "Mrs. Henry" in ctx.transcript_text
    assert ctx.transcript_path is not None
    saved = json.loads(ctx.transcript_path.read_text())
    assert saved[0]["start"] == 0.08


async def test_acquire_uses_local_video(tmp_path: Path):
    """Local video file skips yt-dlp download."""
    work_dir = tmp_path / "project"
    work_dir.mkdir()
    ctx = PipelineContext(
        project_id=1, source_url="https://youtube.com/watch?v=test",
        locale="zh-TW", work_dir=work_dir,
    )

    local_video = tmp_path / "my_video.mp4"
    local_video.write_bytes(b"fake video bytes")

    stage = AcquireStage(local_video=local_video)

    with (
        patch("pipeline.stages.acquire.download_video") as mock_dl,
        patch("pipeline.stages.acquire.extract_transcript") as mock_tr,
    ):
        mock_tr.return_value = ("transcript text", [])
        ctx = await stage.run(ctx)

    mock_dl.assert_not_called()   # skipped
    assert ctx.video_path is not None
    assert ctx.video_path.name == "my_video.mp4"
    assert ctx.video_path.read_bytes() == b"fake video bytes"


async def test_acquire_both_local_skips_all_fetches(tmp_path: Path):
    """Both local flags → no network calls at all."""
    work_dir = tmp_path / "project"
    work_dir.mkdir()
    ctx = PipelineContext(
        project_id=1, source_url="https://youtube.com/watch?v=test",
        locale="zh-TW", work_dir=work_dir,
    )

    local_video = tmp_path / "video.mp4"
    local_video.write_bytes(b"fake")
    transcript_file = tmp_path / "t.csv"
    transcript_file.write_text("00:00,0.08,4.16,Hello world.\n", encoding="utf-8")

    stage = AcquireStage(local_transcript=transcript_file, local_video=local_video)

    with (
        patch("pipeline.stages.acquire.download_video") as mock_dl,
        patch("pipeline.stages.acquire.extract_transcript") as mock_tr,
    ):
        ctx = await stage.run(ctx)

    mock_dl.assert_not_called()
    mock_tr.assert_not_called()
    assert ctx.video_path is not None
    assert "Hello" in ctx.transcript_text


def _write_fake_video(output_dir: Path) -> Path:
    p = output_dir / "video.mp4"
    p.write_bytes(b"fake")
    return p
```

- [ ] **Step 2: Run to confirm they fail**

```bash
uv run pytest tests/unit/test_acquire_local.py -k "local" -v 2>&1 | head -30
```

Expected: `TypeError` — `AcquireStage()` does not accept `local_transcript` / `local_video`.

- [ ] **Step 3: Modify `AcquireStage` in `acquire.py`**

Replace the existing `AcquireStage` class:

```python
class AcquireStage(PipelineStage):
    def __init__(
        self,
        local_transcript: Path | None = None,
        local_video: Path | None = None,
    ) -> None:
        self.local_transcript = local_transcript
        self.local_video = local_video

    @property
    def name(self) -> str:
        return "acquire"

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        logger.info("acquire.start", url=ctx.source_url)

        source_dir = ctx.work_dir / "source"
        source_dir.mkdir(parents=True, exist_ok=True)

        # Video
        if self.local_video:
            dest = source_dir / self.local_video.name
            shutil.copy2(self.local_video, dest)
            ctx.video_path = dest
            logger.info("acquire.video_local", path=str(dest))
        else:
            ctx.video_path = download_video(ctx.source_url, source_dir, resolution="720p")
            logger.info("acquire.video_downloaded", path=str(ctx.video_path))

        # Transcript
        if self.local_transcript:
            full_text, raw_data = parse_transcript_file(self.local_transcript)
            logger.info("acquire.transcript_local", chars=len(full_text))
        else:
            full_text, raw_data = extract_transcript(ctx.source_url)
            logger.info("acquire.transcript_extracted", chars=len(full_text))

        ctx.transcript_text = full_text
        transcript_path = source_dir / "transcript.json"
        transcript_path.write_text(
            json.dumps(raw_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        ctx.transcript_path = transcript_path

        return ctx
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/unit/test_acquire_local.py -v
```

Expected: all 9 tests pass (6 from Task 1 + 3 new).

- [ ] **Step 5: Run existing acquire tests to confirm no regression**

```bash
uv run pytest tests/unit/test_acquire.py -v
```

Expected: all pass. (`AcquireStage()` with no args still works — both params default to `None`.)

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/stages/acquire.py tests/unit/test_acquire_local.py
git commit -m "feat(acquire): accept local_transcript and local_video to skip fetch/download"
```

---

## Task 3: Timestamped transcript formatter in `analyze.py`

**Files:**
- Modify: `src/pipeline/stages/analyze.py`
- Modify: `tests/unit/test_analyze.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_analyze.py`:

```python
from pipeline.stages.analyze import _format_timestamped_transcript


def test_format_timestamped_transcript_basic():
    data = [
        {"text": "Hello world.", "start": 0.08, "duration": 4.16},
        {"text": "How are you?", "start": 4.24, "duration": 3.00},
    ]
    result = _format_timestamped_transcript(data)
    assert "[0.08s–4.24s] Hello world." in result
    assert "[4.24s–7.24s] How are you?" in result


def test_format_timestamped_transcript_merges_mid_sentence():
    # Two entries — first has no sentence-ending punctuation → should merge
    data = [
        {"text": "Mrs. Henry, excuse me. You brought this", "start": 0.08, "duration": 4.16},
        {"text": "case before the court.", "start": 4.24, "duration": 3.00},
    ]
    result = _format_timestamped_transcript(data)
    lines = [l for l in result.splitlines() if l]
    assert len(lines) == 1
    assert lines[0].startswith("[0.08s–")
    assert "Mrs. Henry" in lines[0]
    assert "court." in lines[0]


def test_format_timestamped_transcript_skips_blank_entries():
    data = [
        {"text": "First sentence.", "start": 0.0, "duration": 3.0},
        {"text": "", "start": 3.0, "duration": 2.0},
        {"text": "Second sentence.", "start": 5.0, "duration": 3.0},
    ]
    result = _format_timestamped_transcript(data)
    lines = [l for l in result.splitlines() if l]
    assert len(lines) == 2


def test_build_analysis_prompt_with_transcript_data():
    data = [{"text": "Officer Johnson arrested the suspect.", "start": 1.0, "duration": 3.0}]
    prompt = build_analysis_prompt(
        "Officer Johnson arrested the suspect.",
        "https://youtube.com/watch?v=test",
        "Test Video",
        transcript_data=data,
    )
    assert "[1.00s–4.00s]" in prompt
    assert "timestamps in seconds" in prompt


def test_build_analysis_prompt_without_transcript_data_unchanged():
    # Existing behaviour preserved when transcript_data is None
    prompt = build_analysis_prompt(
        "Plain text transcript.",
        "https://youtube.com/watch?v=test",
        "Test Video",
    )
    assert "Plain text transcript." in prompt
    assert "timestamps in seconds" not in prompt
```

- [ ] **Step 2: Run to confirm they fail**

```bash
uv run pytest tests/unit/test_analyze.py -k "format_timestamped or transcript_data or unchanged" -v 2>&1 | head -30
```

Expected: `ImportError` — `_format_timestamped_transcript` not defined yet.

- [ ] **Step 3: Add `_format_timestamped_transcript()` and update `build_analysis_prompt()`**

In `src/pipeline/stages/analyze.py`, add this helper **before** `build_analysis_prompt`:

```python
_SENTENCE_ENDINGS = frozenset([".", "?", "!", "…"])  # . ? ! …


def _format_timestamped_transcript(transcript_data: list[dict]) -> str:
    """Format structured transcript as [start–end] text, merging mid-sentence splits."""
    merged: list[str] = []
    buf_text: list[str] = []
    buf_start: float | None = None
    buf_end: float = 0.0

    for entry in transcript_data:
        text = entry.get("text", "").strip()
        if not text:
            continue
        start = float(entry["start"])
        end = start + float(entry.get("duration", 0.0))

        if buf_start is None:
            buf_start = start
        buf_text.append(text)
        buf_end = end

        if text[-1] in _SENTENCE_ENDINGS:
            merged.append(f"[{buf_start:.2f}s–{buf_end:.2f}s] {' '.join(buf_text)}")
            buf_text = []
            buf_start = None

    if buf_text and buf_start is not None:
        merged.append(f"[{buf_start:.2f}s–{buf_end:.2f}s] {' '.join(buf_text)}")

    return "\n".join(merged)
```

Then update `build_analysis_prompt` signature and final section:

```python
def build_analysis_prompt(
    transcript: str,
    source_url: str,
    title: str,
    transcript_data: list[dict] | None = None,
) -> str:
    """Build the Claude prompt for knowledge extraction."""
    if transcript_data:
        transcript_body = _format_timestamped_transcript(transcript_data)
        transcript_label = "TRANSCRIPT (with source timestamps in seconds):"
    else:
        transcript_body = transcript
        transcript_label = "TRANSCRIPT:"

    return f"""Analyze this video transcript and extract structured knowledge.

Extract:
1. **Facts**: Individual factual statements with timestamps. Each gets a unique ID (f1, f2, ...).
   Tag each fact with relevant topics (e.g. "crime", "chase", "legal", "geography").
2. **Entities**: People, organizations, locations mentioned. Each gets a unique ID (e1, e2, ...).
3. **Timeline**: Key events in chronological order, referencing fact IDs.
4. **Context bridges**: Cultural context a non-US audience would need explained.

Return ONLY valid JSON:
{{
  "facts": [
    {{"id": "f1", "text": "factual statement", "timestamp": "M:SS",
      "source": "transcript", "verified": false,
      "tags": ["tag1", "tag2"]}}
  ],
  "entities": [
    {{"id": "e1", "name": "Name", "role": "role description", "details": ""}}
  ],
  "timeline": [
    {{"time": "M:SS", "event": "what happened", "facts": ["f1"]}}
  ],
  "context_bridges": [
    "Cultural context statement"
  ]
}}

SOURCE: {source_url}
TITLE: {title}

{transcript_label}
{transcript_body}"""
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/unit/test_analyze.py -v
```

Expected: all tests pass (existing + 5 new).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/stages/analyze.py tests/unit/test_analyze.py
git commit -m "feat(analyze): add timestamped transcript formatter and transcript_data param"
```

---

## Task 4: `AnalyzeStage` reads `transcript.json`

**Files:**
- Modify: `src/pipeline/stages/analyze.py`
- Modify: `tests/unit/test_analyze.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_analyze.py`:

```python
async def test_analyze_uses_structured_transcript_when_available(
    sample_context, analysis_fixture, tmp_path
):
    """AnalyzeStage passes transcript_data to build_analysis_prompt when transcript.json exists."""
    # Set up transcript.json in the project dir
    source_dir = sample_context.work_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = source_dir / "transcript.json"
    transcript_data = [
        {"text": "Officer Johnson arrested the suspect.", "start": 1.0, "duration": 3.0},
        {"text": "He was charged with theft.", "start": 4.0, "duration": 2.5},
    ]
    transcript_path.write_text(
        json.dumps(transcript_data, ensure_ascii=False), encoding="utf-8"
    )
    sample_context.transcript_text = "Officer Johnson arrested the suspect. He was charged with theft."
    sample_context.transcript_path = transcript_path

    stage = AnalyzeStage()

    captured_prompt: list[str] = []

    def mock_create(**kwargs):
        captured_prompt.append(kwargs["messages"][0]["content"])
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(analysis_fixture))]
        return mock_response

    with patch("pipeline.stages.analyze.get_anthropic_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = mock_create
        mock_client_fn.return_value = mock_client
        await stage.run(sample_context)

    prompt = captured_prompt[0]
    assert "[1.00s–4.00s]" in prompt          # structured format used
    assert "timestamps in seconds" in prompt
```

- [ ] **Step 2: Run to confirm it fails**

```bash
uv run pytest tests/unit/test_analyze.py::test_analyze_uses_structured_transcript_when_available -v
```

Expected: FAIL — prompt does not contain `[1.00s–4.00s]`.

- [ ] **Step 3: Update `AnalyzeStage.run()` to load transcript.json**

In `src/pipeline/stages/analyze.py`, update `AnalyzeStage.run()`. Replace the `prompt = build_analysis_prompt(...)` call with:

```python
async def run(self, ctx: PipelineContext) -> PipelineContext:
    if not ctx.transcript_text:
        raise ValueError("No transcript available — run acquire stage first")

    logger.info("analyze.start", transcript_len=len(ctx.transcript_text))

    # Load structured transcript if available (gives Claude precise timestamps)
    transcript_data: list[dict] | None = None
    if ctx.transcript_path and ctx.transcript_path.exists():
        try:
            raw = json.loads(ctx.transcript_path.read_text(encoding="utf-8"))
            if raw and isinstance(raw[0], dict) and "start" in raw[0]:
                transcript_data = [e for e in raw if e.get("text", "").strip()]
        except (json.JSONDecodeError, IndexError, KeyError):
            pass

    client = get_anthropic_client()
    config = PipelineConfig()
    prompt = build_analysis_prompt(
        ctx.transcript_text,
        ctx.source_url,
        getattr(ctx, "source_title", "Untitled"),
        transcript_data=transcript_data,
    )

    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_text = response.content[0].text
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1].rsplit("```", 1)[0]

    result = json.loads(raw_text)

    # Build Knowledge object
    knowledge = Knowledge.from_dict(
        {
            "meta": {
                "source_type": "youtube",
                "source_url": ctx.source_url,
                "title": getattr(ctx, "source_title", "Untitled"),
                "locale": ctx.locale,
                "created_at": "",
                "updated_at": "",
            },
            **result,
        }
    )

    # Save knowledge.json
    knowledge_path = ctx.work_dir / "knowledge.json"
    knowledge.save(knowledge_path)
    ctx.knowledge_path = knowledge_path

    # Backwards compat
    ctx.story_structure = {
        "beats": [
            {"timestamp": t.time, "beat": "event", "description": t.event}
            for t in knowledge.timeline
        ],
    }
    ctx.knowledge_graph = {
        "entities": [
            {"name": e.name, "role": e.role, "details": e.details} for e in knowledge.entities
        ],
        "context_needed_for_target_audience": knowledge.context_bridges,
    }
    ctx.clip_timestamps = []

    logger.info(
        "analyze.complete",
        facts=len(knowledge.facts),
        entities=len(knowledge.entities),
    )
    return ctx
```

- [ ] **Step 4: Run all analyze tests to confirm they pass**

```bash
uv run pytest tests/unit/test_analyze.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/stages/analyze.py tests/unit/test_analyze.py
git commit -m "feat(analyze): load transcript.json for timestamp-aware knowledge extraction"
```

---

## Task 5: CLI flags on `produce` and `acquire`

**Files:**
- Modify: `src/pipeline/cli.py`
- Modify: `tests/unit/test_cli.py`

- [ ] **Step 1: Write the failing test**

Find the `produce` tests in `tests/unit/test_cli.py`. Append:

```python
from unittest.mock import AsyncMock, MagicMock, patch
from typer.testing import CliRunner
from pipeline.cli import app


def test_produce_passes_local_transcript_to_acquire_stage(tmp_path):
    """--transcript flag is forwarded to AcquireStage constructor."""
    transcript_file = tmp_path / "t.csv"
    transcript_file.write_text("00:00,0.08,4.16,Hello world.\n", encoding="utf-8")

    captured: list = []

    original_init = __import__(
        "pipeline.stages.acquire", fromlist=["AcquireStage"]
    ).AcquireStage.__init__

    def capturing_init(self, local_transcript=None, local_video=None):
        captured.append({"local_transcript": local_transcript, "local_video": local_video})
        original_init(self, local_transcript=local_transcript, local_video=local_video)

    runner = CliRunner()
    with (
        patch("pipeline.stages.acquire.AcquireStage.__init__", capturing_init),
        patch("pipeline.cli.Orchestrator") as mock_orch_cls,
    ):
        mock_orch = MagicMock()
        mock_orch.run = AsyncMock(
            return_value=MagicMock(success=False, failed_stage="acquire", error="test stop")
        )
        mock_orch_cls.return_value = mock_orch

        runner.invoke(
            app,
            ["produce", "--url", "https://youtube.com/watch?v=test",
             "--transcript", str(transcript_file)],
        )

    assert len(captured) == 1
    assert captured[0]["local_transcript"] == transcript_file
    assert captured[0]["local_video"] is None
```

- [ ] **Step 2: Run to confirm it fails**

```bash
uv run pytest tests/unit/test_cli.py::test_produce_passes_local_transcript_to_acquire_stage -v 2>&1 | head -30
```

Expected: FAIL — `produce` does not accept `--transcript`.

- [ ] **Step 3: Add `--transcript` and `--video` to `produce` command**

In `src/pipeline/cli.py`, add two options to `produce()` after the existing `niche` option:

```python
    local_transcript: str | None = typer.Option(
        None, "--transcript",
        help="Path to local transcript file (.csv or .txt). Skips YouTube transcript fetch.",
    ),
    local_video: str | None = typer.Option(
        None, "--video",
        help="Path to local video file. Skips yt-dlp download.",
    ),
```

Then update the `AcquireStage` instantiation inside `produce()` (replace both occurrences):

```python
    # Select acquire stage based on source type
    if source_type == "web":
        from pipeline.stages.acquire_web import AcquireWebStage
        acquire = AcquireWebStage()
    else:
        acquire = AcquireStage(
            local_transcript=Path(local_transcript) if local_transcript else None,
            local_video=Path(local_video) if local_video else None,
        )
```

Also update the standalone `acquire` command to accept the same flags:

```python
@app.command()
def acquire(
    url: str = typer.Option(..., "--url", help="YouTube video URL"),
    local_transcript: str | None = typer.Option(
        None, "--transcript",
        help="Path to local transcript file (.csv or .txt).",
    ),
    local_video: str | None = typer.Option(
        None, "--video",
        help="Path to local video file.",
    ),
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

    result = asyncio.run(
        Orchestrator(
            stages=[
                AcquireStage(
                    local_transcript=Path(local_transcript) if local_transcript else None,
                    local_video=Path(local_video) if local_video else None,
                )
            ]
        ).run(ctx)
    )
    if result.success:
        typer.echo(f"Acquired: {result.ctx.video_path}")
        typer.echo(f"Transcript: {result.ctx.transcript_path}")
    else:
        typer.echo(f"Failed: {result.error}")
        raise typer.Exit(code=1)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/unit/test_cli.py::test_produce_passes_local_transcript_to_acquire_stage -v
```

Expected: PASS.

- [ ] **Step 5: Run the full test suite**

```bash
uv run pytest tests/unit/ -x -q 2>&1 | tail -20
```

Expected: all pass, no regressions.

- [ ] **Step 6: Lint and type check**

```bash
uv run ruff check src/pipeline/stages/acquire.py src/pipeline/stages/analyze.py src/pipeline/cli.py
uv run mypy src/pipeline/stages/acquire.py src/pipeline/stages/analyze.py src/pipeline/cli.py
```

Fix any issues before committing.

- [ ] **Step 7: Commit**

```bash
git add src/pipeline/cli.py tests/unit/test_cli.py
git commit -m "feat(cli): add --transcript and --video flags to produce and acquire commands"
```

---

## Smoke Test

After all tasks complete, verify end-to-end with the real transcript file:

```bash
# Should produce a project using local transcript, skipping YouTube fetch
uv run pipeline produce \
  --url "https://youtube.com/watch?v=REPLACE_WITH_ACTUAL_ID" \
  --locale zh-TW \
  --transcript "data/craziest-child-support-backfires/Top 5 CRAZY Child Support Plans That Failed!.csv"

# Check knowledge.json has float timestamps (not "M:SS" strings)
cat output/projects/<ID>/knowledge.json | python3 -c "
import json, sys
k = json.load(sys.stdin)
print('Fact timestamps:', [f['timestamp'] for f in k['facts'][:3]])
"
```

Expected: timestamps are precise floats or decimal-second strings rather than approximate `"M:SS"` guesses.
