# Highlight Extraction + Gallery System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace raw keyframe scanning in /produce with a signal-scored clip manifest, add a tiered gallery for asset reuse, and add two evaluator sub-agent checkpoints.

**Architecture:** Three independent utilities bolt onto the existing produce flow. `highlight_extractor.py` scores every 5s video window using scene-change count + audio RMS + transcript keyword density, emits `clip_manifest.json` with top-10 candidates and their keyframe paths. `gallery.py` provides tiered lookup (local index → Pexels → Pixabay → signal-to-generate) backed by `output/gallery/gallery_index.json`. The produce skill is updated to call both and dispatch ClipSelector + AssetEvaluator sub-agents at new checkpoints 1c and 3b.

**Tech Stack:** FFmpeg/ffprobe (existing), httpx (existing), Typer (existing), Pydantic-settings (existing), pytest + unittest.mock.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `src/pipeline/utils/highlight_extractor.py` | Signal scoring, candidate selection, CaptionProvider protocol |
| Create | `src/pipeline/utils/gallery.py` | GalleryIndex data model, tiered lookup, write-back |
| Create | `src/pipeline/gallery_cli.py` | `pipeline gallery search` Typer sub-app |
| Modify | `src/pipeline/cli.py` | Mount gallery_app |
| Modify | `src/pipeline/composer/image.py` | Accept optional `gallery_path` + write-back after generation |
| Modify | `.env.example` | Add PEXELS_API_KEY, PIXABAY_API_KEY placeholders |
| Modify | `.claude/commands/produce.md` | Update Step 1b, add Steps 1c and 3b |
| Create | `tests/unit/test_highlight_extractor.py` | Unit tests with mocked ffprobe |
| Create | `tests/unit/test_gallery.py` | Unit tests with mocked httpx |
| Create | `tests/integration/test_highlight_extractor.py` | Real ffprobe against fixture |

---

## Task 1: CaptionProvider protocol + signal scoring helpers

**Files:**
- Create: `src/pipeline/utils/highlight_extractor.py`
- Create: `tests/unit/test_highlight_extractor.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_highlight_extractor.py
from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock, patch
import json
import pytest

from pipeline.utils.highlight_extractor import (
    NullCaptionProvider,
    CaptionProvider,
    _count_scene_changes_per_window,
    _audio_rms_per_window,
    _score_keywords,
)


def test_null_caption_provider_returns_none():
    provider = NullCaptionProvider()
    assert provider.caption(Path("any.jpg")) is None


def test_caption_provider_protocol():
    """NullCaptionProvider satisfies the CaptionProvider protocol."""
    assert isinstance(NullCaptionProvider(), CaptionProvider)


def test_count_scene_changes_per_window_empty():
    with patch("pipeline.utils.highlight_extractor.detect_scene_changes", return_value=[]):
        with patch("pipeline.utils.highlight_extractor._get_duration", return_value=30.0):
            result = _count_scene_changes_per_window(Path("video.mp4"), window_sec=5)
    assert len(result) == 7  # 30s / 5s + 1
    assert all(score == 0.0 for _, score in result)


def test_count_scene_changes_per_window_normalizes():
    # Two changes in window 0, one in window 1
    with patch("pipeline.utils.highlight_extractor.detect_scene_changes", return_value=[1.0, 3.0, 6.0]):
        with patch("pipeline.utils.highlight_extractor._get_duration", return_value=15.0):
            result = _count_scene_changes_per_window(Path("video.mp4"), window_sec=5)
    ts_to_score = {ts: score for ts, score in result}
    assert ts_to_score[0.0] == pytest.approx(1.0)   # 2 changes → max → 1.0
    assert ts_to_score[5.0] == pytest.approx(0.5)   # 1 change → 0.5


def test_score_keywords_no_transcript():
    result = _score_keywords(None, duration_sec=30.0, window_sec=5)
    assert result == []


def test_score_keywords_counts_action_words():
    transcript = [
        {"text": "the officer shot the weapon", "start": 2.0, "duration": 3.0},
        {"text": "they were fleeing", "start": 12.0, "duration": 2.0},
    ]
    import tempfile, json as _json
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        _json.dump(transcript, f)
        fpath = Path(f.name)
    result = _score_keywords(fpath, duration_sec=20.0, window_sec=5)
    ts_to_score = {ts: score for ts, score in result}
    assert ts_to_score[0.0] == pytest.approx(1.0)   # "shot" + "weapon" = 2 hits → max
    assert ts_to_score[10.0] == pytest.approx(0.5)  # "fleeing" = 1 hit


def test_audio_rms_returns_empty_on_ffprobe_failure():
    mock = MagicMock(returncode=1, stdout="")
    with patch("subprocess.run", return_value=mock):
        result = _audio_rms_per_window(Path("video.mp4"), window_sec=5)
    assert result == []
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
cd /home/tim-huang/content-creation
uv run pytest tests/unit/test_highlight_extractor.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError` or `ImportError` — module doesn't exist yet.

- [ ] **Step 3: Create `highlight_extractor.py` with protocol + signal scoring**

```python
# src/pipeline/utils/highlight_extractor.py
"""Signal-scored clip manifest generator.

Replaces raw keyframe scanning in /produce Step 1b. Extracts top-10 highlight
candidates using three cheap signals: scene-change count, audio RMS, and
transcript keyword density. A pluggable CaptionProvider (NullCaptionProvider
by default) can enrich candidates with visual descriptions.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Protocol, runtime_checkable

from pipeline.utils.video_analysis import detect_scene_changes

ACTION_WORDS = [
    "shot", "arrest", "fight", "crash", "verdict", "confronted",
    "screaming", "weapon", "chase", "attack", "guilty", "explosion",
    "threatening", "fleeing", "struggle", "collision", "fired",
]

REJECT_PATTERNS = [
    "talking head at desk", "anchor at desk", "blank screen",
    "empty room", "news lower third", "static title card",
]


@runtime_checkable
class CaptionProvider(Protocol):
    def caption(self, frame_path: Path) -> str | None: ...


class NullCaptionProvider:
    """Default provider: no API call, caption is always None."""

    def caption(self, frame_path: Path) -> str | None:  # noqa: ARG002
        return None


def _get_duration(video_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def _count_scene_changes_per_window(
    video_path: Path,
    window_sec: int = 5,
    threshold: float = 0.1,
) -> list[tuple[float, float]]:
    """Count scene changes per window as a frame-activity proxy.

    Uses a low threshold to catch subtle transitions as well as hard cuts.
    Returns list of (timestamp_sec, normalized_score).
    """
    timestamps = detect_scene_changes(video_path, threshold=threshold)
    duration = _get_duration(video_path)
    n_windows = int(duration / window_sec) + 1
    counts = [0] * n_windows
    for ts in timestamps:
        bucket = int(ts / window_sec)
        if 0 <= bucket < n_windows:
            counts[bucket] += 1
    max_count = max(counts) or 1
    return [(float(i * window_sec), c / max_count) for i, c in enumerate(counts)]


def _audio_rms_per_window(
    video_path: Path,
    window_sec: int = 5,
) -> list[tuple[float, float]]:
    """Sample audio RMS energy per window via ffprobe astats filter.

    Returns list of (timestamp_sec, normalized_score) where 0dB → 1.0,
    -60dB → 0.0, silence → 0.0.
    """
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-f", "lavfi",
            "-i", f"amovie={video_path},astats=metadata=1:reset=1",
            "-show_entries", "frame_tags=lavfi.astats.Overall.RMS_level",
            "-of", "json",
        ],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        return []
    try:
        frames = json.loads(result.stdout).get("frames", [])
    except json.JSONDecodeError:
        return []

    per_second: list[float] = []
    for f in frames:
        rms_str = f.get("tags", {}).get("lavfi.astats.Overall.RMS_level", "-inf")
        try:
            db = float(rms_str)
            normalized = max(0.0, (db + 60.0) / 60.0)
        except ValueError:
            normalized = 0.0
        per_second.append(normalized)

    scores: list[tuple[float, float]] = []
    for start in range(0, len(per_second), window_sec):
        window = per_second[start : start + window_sec]
        if window:
            scores.append((float(start), sum(window) / len(window)))
    return scores


def _score_keywords(
    transcript_path: Path | None,
    duration_sec: float,
    window_sec: int = 5,
) -> list[tuple[float, float]]:
    """Count action-word hits per window from transcript timestamps.

    Returns list of (timestamp_sec, normalized_score).
    """
    if transcript_path is None or not transcript_path.exists():
        return []
    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    n_windows = int(duration_sec / window_sec) + 1
    counts = [0] * n_windows
    for entry in transcript:
        start = float(entry.get("start", 0))
        text = entry.get("text", "").lower()
        bucket = int(start / window_sec)
        if 0 <= bucket < n_windows:
            for word in ACTION_WORDS:
                if word in text:
                    counts[bucket] += 1
    max_count = max(counts) or 1
    return [(float(i * window_sec), c / max_count) for i, c in enumerate(counts)]
```

- [ ] **Step 4: Run tests — should pass**

```bash
uv run pytest tests/unit/test_highlight_extractor.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/utils/highlight_extractor.py tests/unit/test_highlight_extractor.py
git commit -m "feat(highlight): CaptionProvider protocol + signal scoring helpers"
```

---

## Task 2: Candidate selection + `extract_highlights()` public API

**Files:**
- Modify: `src/pipeline/utils/highlight_extractor.py` (append functions)
- Modify: `tests/unit/test_highlight_extractor.py` (append tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_highlight_extractor.py`:

```python
from pipeline.utils.highlight_extractor import (
    _merge_scores,
    _select_candidates,
    extract_highlights,
)


def test_merge_scores_combines_signals():
    fd = [(0.0, 0.8), (5.0, 0.2)]
    ar = [(0.0, 0.6), (5.0, 0.4)]
    kw = [(0.0, 1.0), (5.0, 0.0)]
    result = _merge_scores(fd, ar, kw, duration_sec=10.0, window_sec=5)
    assert len(result) == 3  # 0s, 5s, 10s
    # Window 0: 0.4*0.8 + 0.3*0.6 + 0.3*1.0 = 0.32 + 0.18 + 0.30 = 0.80
    assert result[0]["combined_score"] == pytest.approx(0.80, abs=0.01)
    assert result[0]["timestamp_sec"] == 0.0


def test_select_candidates_enforces_spacing():
    scored = [
        {"timestamp_sec": 0.0, "combined_score": 0.9, "frame_diff": 0.9, "audio_rms": 0.9, "keyword_score": 0.9},
        {"timestamp_sec": 5.0, "combined_score": 0.85, "frame_diff": 0.8, "audio_rms": 0.8, "keyword_score": 0.9},
        {"timestamp_sec": 20.0, "combined_score": 0.7, "frame_diff": 0.7, "audio_rms": 0.7, "keyword_score": 0.7},
    ]
    result = _select_candidates(scored, top_n=10, min_spacing_sec=15.0)
    timestamps = [c["timestamp_sec"] for c in result]
    assert 0.0 in timestamps
    assert 5.0 not in timestamps   # within 15s of 0.0 — rejected
    assert 20.0 in timestamps


def test_select_candidates_respects_top_n():
    scored = [
        {"timestamp_sec": float(i * 20), "combined_score": 1.0 - i * 0.05,
         "frame_diff": 0.5, "audio_rms": 0.5, "keyword_score": 0.5}
        for i in range(20)
    ]
    result = _select_candidates(scored, top_n=5, min_spacing_sec=15.0)
    assert len(result) == 5


def test_extract_highlights_returns_manifest_shape(tmp_path):
    fake_video = tmp_path / "video.mp4"
    fake_video.write_bytes(b"fake")

    with patch("pipeline.utils.highlight_extractor._get_duration", return_value=60.0), \
         patch("pipeline.utils.highlight_extractor.detect_scene_changes", return_value=[10.0, 25.0, 40.0]), \
         patch("pipeline.utils.highlight_extractor._audio_rms_per_window", return_value=[(0.0, 0.5), (5.0, 0.8)]), \
         patch("pipeline.utils.video_analysis.extract_keyframes", return_value=[]):
        manifest = extract_highlights(fake_video, transcript_path=None)

    assert "candidates" in manifest
    assert "rejected" in manifest
    assert manifest["caption_provider"] == "NullCaptionProvider"
    assert manifest["duration_sec"] == pytest.approx(60.0, abs=0.5)
    for c in manifest["candidates"]:
        assert "timestamp_sec" in c
        assert "combined_score" in c
        assert "caption" in c
        assert c["usable"] is True
```

- [ ] **Step 2: Run to confirm new tests fail**

```bash
uv run pytest tests/unit/test_highlight_extractor.py::test_merge_scores_combines_signals -v
```

Expected: `ImportError: cannot import name '_merge_scores'`

- [ ] **Step 3: Append `_merge_scores`, `_select_candidates`, `_is_rejected_caption`, `extract_highlights` to `highlight_extractor.py`**

```python
def _merge_scores(
    frame_diff: list[tuple[float, float]],
    audio_rms: list[tuple[float, float]],
    keywords: list[tuple[float, float]],
    duration_sec: float,
    window_sec: int = 5,
) -> list[dict]:
    """Merge three signal lists into per-window combined scores."""
    def to_dict(scores: list[tuple[float, float]]) -> dict[int, float]:
        out: dict[int, float] = {}
        for ts, val in scores:
            key = round(ts / window_sec)
            out[key] = max(out.get(key, 0.0), val)
        return out

    fd = to_dict(frame_diff)
    ar = to_dict(audio_rms)
    kw = to_dict(keywords)
    n_windows = int(duration_sec / window_sec) + 1
    results = []
    for i in range(n_windows):
        f = fd.get(i, 0.0)
        a = ar.get(i, 0.0)
        k = kw.get(i, 0.0)
        results.append({
            "timestamp_sec": float(i * window_sec),
            "frame_diff": round(f, 3),
            "audio_rms": round(a, 3),
            "keyword_score": round(k, 3),
            "combined_score": round(0.4 * f + 0.3 * a + 0.3 * k, 3),
        })
    return results


def _select_candidates(
    scored: list[dict],
    top_n: int = 10,
    min_spacing_sec: float = 15.0,
) -> list[dict]:
    """Pick top-N candidates, enforcing minimum spacing between timestamps."""
    sorted_by_score = sorted(scored, key=lambda x: x["combined_score"], reverse=True)
    selected: list[dict] = []
    for candidate in sorted_by_score:
        ts = candidate["timestamp_sec"]
        if all(abs(ts - s["timestamp_sec"]) >= min_spacing_sec for s in selected):
            selected.append(candidate)
        if len(selected) >= top_n:
            break
    return selected


def _is_rejected_caption(caption: str) -> bool:
    caption_lower = caption.lower()
    return any(pat in caption_lower for pat in REJECT_PATTERNS)


def extract_highlights(
    video_path: Path,
    transcript_path: Path | None = None,
    caption_provider: CaptionProvider | None = None,
    window_sec: int = 5,
    top_n: int = 10,
    min_spacing_sec: float = 15.0,
) -> dict:
    """Generate clip manifest content for a source video.

    Returns the manifest dict. Caller writes it to disk.
    To swap in vision captioning later, pass a GptVisionCaptionProvider or
    GeminiCaptionProvider — the manifest schema is unchanged.
    """
    from pipeline.utils.video_analysis import extract_keyframes

    if caption_provider is None:
        caption_provider = NullCaptionProvider()

    duration_sec = _get_duration(video_path)

    kf_dir = video_path.parent / "keyframes"
    keyframes = extract_keyframes(video_path, kf_dir, interval_sec=window_sec)
    kf_map = {round(kf["timestamp_sec"] / window_sec): kf["path"] for kf in keyframes}

    frame_diff = _count_scene_changes_per_window(video_path, window_sec)
    audio_rms = _audio_rms_per_window(video_path, window_sec)
    keywords = _score_keywords(transcript_path, duration_sec, window_sec)

    scored = _merge_scores(frame_diff, audio_rms, keywords, duration_sec, window_sec)
    for entry in scored:
        bucket = round(entry["timestamp_sec"] / window_sec)
        entry["keyframe_path"] = kf_map.get(bucket, "")

    raw_candidates = _select_candidates(scored, top_n, min_spacing_sec)

    candidates: list[dict] = []
    rejected: list[dict] = []
    for c in raw_candidates:
        kf_path = Path(c["keyframe_path"]) if c.get("keyframe_path") else None
        caption = (
            caption_provider.caption(kf_path)
            if kf_path and kf_path.exists()
            else None
        )
        c["caption"] = caption
        if caption and _is_rejected_caption(caption):
            c["usable"] = False
            rejected.append({**c, "reject_reason": caption[:80]})
        else:
            c["usable"] = True
            candidates.append(c)

    return {
        "video_id": video_path.parent.parent.name,
        "duration_sec": round(duration_sec, 1),
        "caption_provider": type(caption_provider).__name__,
        "candidates": candidates,
        "rejected": rejected,
    }
```

- [ ] **Step 4: Run all highlight extractor tests**

```bash
uv run pytest tests/unit/test_highlight_extractor.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/utils/highlight_extractor.py tests/unit/test_highlight_extractor.py
git commit -m "feat(highlight): extract_highlights() + candidate selection"
```

---

## Task 3: GalleryIndex data model + local tier

**Files:**
- Create: `src/pipeline/utils/gallery.py`
- Create: `tests/unit/test_gallery.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_gallery.py
from __future__ import annotations
import json
from pathlib import Path
import pytest

from pipeline.utils.gallery import GalleryEntry, GalleryIndex


def test_gallery_index_empty_on_missing_file(tmp_path):
    index_path = tmp_path / "gallery_index.json"
    idx = GalleryIndex.load(index_path)
    assert idx.entries == []


def test_gallery_index_round_trip(tmp_path):
    index_path = tmp_path / "gallery_index.json"
    idx = GalleryIndex(index_path=index_path)
    entry = GalleryEntry(
        id="abc123",
        path=str(tmp_path / "images" / "abc123.png"),
        type="image",
        origin="dalle",
        prompt="courtroom illustration",
        query=None,
        tags=["courtroom", "legal"],
        niche=["bodycam"],
        created_at="2026-04-23",
    )
    idx.append(entry)
    idx.save()

    reloaded = GalleryIndex.load(index_path)
    assert len(reloaded.entries) == 1
    assert reloaded.entries[0].id == "abc123"
    assert reloaded.entries[0].tags == ["courtroom", "legal"]


def test_gallery_index_search_by_tags(tmp_path):
    index_path = tmp_path / "gallery_index.json"
    idx = GalleryIndex(index_path=index_path)
    e1 = GalleryEntry(
        id="e1", path="images/e1.png", type="image", origin="dalle",
        prompt="courtroom", query=None, tags=["courtroom", "legal"],
        niche=["courtroom"], created_at="2026-04-23",
    )
    e2 = GalleryEntry(
        id="e2", path="images/e2.png", type="image", origin="pexels",
        prompt=None, query="police car", tags=["police", "car"],
        niche=["bodycam"], created_at="2026-04-23",
    )
    idx.append(e1)
    idx.append(e2)

    results = idx.search(["courtroom"], niche="courtroom", asset_type="image")
    assert len(results) == 1
    assert results[0].id == "e1"


def test_gallery_index_search_score_threshold(tmp_path):
    index_path = tmp_path / "gallery_index.json"
    idx = GalleryIndex(index_path=index_path)
    entry = GalleryEntry(
        id="e1", path="images/e1.png", type="image", origin="dalle",
        prompt="courtroom illustration", query=None,
        tags=["courtroom", "legal", "interior"],
        niche=["courtroom"], created_at="2026-04-23",
    )
    idx.append(entry)

    # "courtroom" matches 1/1 query terms → score 1.0 > threshold
    hits = idx.search(["courtroom"], niche=None, asset_type=None)
    assert len(hits) == 1

    # "office" doesn't match any tag → score 0.0 < threshold
    misses = idx.search(["office"], niche=None, asset_type=None)
    assert len(misses) == 0
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
uv run pytest tests/unit/test_gallery.py -v 2>&1 | head -10
```

Expected: `ImportError`

- [ ] **Step 3: Create `gallery.py`**

```python
# src/pipeline/utils/gallery.py
"""Tiered gallery for image and video clip asset reuse.

Lookup order:
  Tier 1 — local gallery_index.json (keyword match, $0 cost)
  Tier 2 — Pexels API (photos) + Pixabay API (video clips), free tiers
  Tier 3 — signal to generate new (DALL-E via existing flow)

Generated images from /produce are written back to the gallery by the
compose stage so they are available for future videos.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

GALLERY_DIR = Path("output/gallery")
GALLERY_INDEX_PATH = GALLERY_DIR / "gallery_index.json"
MATCH_THRESHOLD = 0.6


@dataclass
class GalleryEntry:
    id: str
    path: str           # relative or absolute path to file
    type: str           # "image" or "clip"
    origin: str         # "dalle" | "gemini" | "pexels" | "pixabay"
    prompt: str | None  # for generated assets
    query: str | None   # for stock API assets
    tags: list[str]
    niche: list[str]
    created_at: str     # ISO date string

    def match_score(self, query_terms: list[str]) -> float:
        """Fraction of query_terms found in self.tags."""
        if not query_terms:
            return 0.0
        hits = sum(1 for t in query_terms if t.lower() in [tag.lower() for tag in self.tags])
        return hits / len(query_terms)


@dataclass
class GalleryIndex:
    index_path: Path
    entries: list[GalleryEntry] = field(default_factory=list)

    @classmethod
    def load(cls, index_path: Path) -> GalleryIndex:
        if not index_path.exists():
            return cls(index_path=index_path)
        data = json.loads(index_path.read_text(encoding="utf-8"))
        entries = [GalleryEntry(**e) for e in data.get("entries", [])]
        return cls(index_path=index_path, entries=entries)

    def save(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"version": 1, "entries": [asdict(e) for e in self.entries]}
        self.index_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def append(self, entry: GalleryEntry) -> None:
        self.entries.append(entry)

    def search(
        self,
        query_terms: list[str],
        niche: str | None,
        asset_type: str | None,
    ) -> list[GalleryEntry]:
        """Return entries matching query_terms above MATCH_THRESHOLD.

        Filters by niche and asset_type when specified.
        Sorted by match score descending.
        """
        results = []
        for entry in self.entries:
            if asset_type and entry.type != asset_type:
                continue
            if niche and niche not in entry.niche:
                continue
            score = entry.match_score(query_terms)
            if score >= MATCH_THRESHOLD:
                results.append((score, entry))
        results.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in results]
```

- [ ] **Step 4: Run gallery unit tests**

```bash
uv run pytest tests/unit/test_gallery.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/utils/gallery.py tests/unit/test_gallery.py
git commit -m "feat(gallery): GalleryEntry + GalleryIndex data model + local tier"
```

---

## Task 4: Tiered lookup — Pexels + Pixabay + generate signal

**Files:**
- Modify: `src/pipeline/utils/gallery.py` (append `GallerySearcher` + `search_gallery`)
- Modify: `tests/unit/test_gallery.py` (append tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_gallery.py`:

```python
from unittest.mock import patch, MagicMock
from pipeline.utils.gallery import GallerySearcher, GalleryResult


def test_search_gallery_hits_local_first(tmp_path):
    index_path = tmp_path / "gallery_index.json"
    idx = GalleryIndex(index_path=index_path)
    entry = GalleryEntry(
        id="local1", path=str(tmp_path / "img.png"), type="image", origin="dalle",
        prompt="courtroom", query=None, tags=["courtroom"],
        niche=["courtroom"], created_at="2026-04-23",
    )
    (tmp_path / "img.png").write_bytes(b"fake")
    idx.append(entry)
    idx.save()

    searcher = GallerySearcher(index_path=index_path, gallery_dir=tmp_path)
    result = searcher.search(["courtroom"], niche="courtroom", asset_type="image")

    assert result.tier == "local"
    assert result.entry is not None
    assert result.entry.id == "local1"


def test_search_gallery_falls_through_to_generate_when_no_keys(tmp_path):
    index_path = tmp_path / "gallery_index.json"
    GalleryIndex(index_path=index_path).save()  # empty index

    searcher = GallerySearcher(
        index_path=index_path, gallery_dir=tmp_path,
        pexels_api_key=None, pixabay_api_key=None,
    )
    result = searcher.search(["alien landscape"], niche=None, asset_type="image")

    assert result.tier == "generate"
    assert result.entry is None
    assert "alien" in result.suggested_prompt.lower()


def test_search_gallery_pexels_downloads_on_miss(tmp_path):
    index_path = tmp_path / "gallery_index.json"
    GalleryIndex(index_path=index_path).save()

    fake_image_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # minimal fake PNG

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.content = fake_image_bytes
    mock_response.json.return_value = {
        "photos": [{"src": {"original": "https://example.com/photo.jpg"}}]
    }

    with patch("httpx.Client") as MockClient:
        instance = MockClient.return_value.__enter__.return_value
        instance.get.return_value = mock_response

        searcher = GallerySearcher(
            index_path=index_path, gallery_dir=tmp_path,
            pexels_api_key="fake_key", pixabay_api_key=None,
        )
        result = searcher.search(["courtroom"], niche=None, asset_type="image")

    assert result.tier == "pexels"
    assert result.entry is not None
    assert Path(result.entry.path).exists()
```

- [ ] **Step 2: Run to confirm new tests fail**

```bash
uv run pytest tests/unit/test_gallery.py::test_search_gallery_hits_local_first -v
```

Expected: `ImportError: cannot import name 'GallerySearcher'`

- [ ] **Step 3: Append `GalleryResult` + `GallerySearcher` + `search_gallery` to `gallery.py`**

```python
import hashlib
from datetime import date
import httpx


@dataclass
class GalleryResult:
    tier: str                  # "local" | "pexels" | "pixabay" | "generate"
    entry: GalleryEntry | None # None when tier == "generate"
    suggested_prompt: str      # populated for tier == "generate"


class GallerySearcher:
    """Tiered gallery lookup: local → Pexels → Pixabay → generate signal."""

    def __init__(
        self,
        index_path: Path = GALLERY_INDEX_PATH,
        gallery_dir: Path = GALLERY_DIR,
        pexels_api_key: str | None = None,
        pixabay_api_key: str | None = None,
    ):
        self._index_path = index_path
        self._gallery_dir = gallery_dir
        self._pexels_key = pexels_api_key
        self._pixabay_key = pixabay_api_key

    def search(
        self,
        query_terms: list[str],
        niche: str | None,
        asset_type: str | None,
    ) -> GalleryResult:
        idx = GalleryIndex.load(self._index_path)

        # Tier 1: local gallery
        hits = idx.search(query_terms, niche=niche, asset_type=asset_type)
        if hits:
            return GalleryResult(tier="local", entry=hits[0], suggested_prompt="")

        query_str = " ".join(query_terms)

        # Tier 2a: Pexels (images)
        if self._pexels_key and asset_type in (None, "image"):
            entry = self._pexels_search(query_str, niche or "")
            if entry:
                idx.append(entry)
                idx.save()
                return GalleryResult(tier="pexels", entry=entry, suggested_prompt="")

        # Tier 2b: Pixabay (clips)
        if self._pixabay_key and asset_type in (None, "clip"):
            entry = self._pixabay_search(query_str, niche or "")
            if entry:
                idx.append(entry)
                idx.save()
                return GalleryResult(tier="pixabay", entry=entry, suggested_prompt="")

        # Tier 3: signal to generate
        suggested = (
            f"flat minimalist illustration, {query_str}, "
            "simple clean lines, limited color palette"
        )
        return GalleryResult(tier="generate", entry=None, suggested_prompt=suggested)

    def _pexels_search(self, query: str, niche: str) -> GalleryEntry | None:
        query_hash = hashlib.md5(f"pexels:{query}".encode()).hexdigest()[:12]
        images_dir = self._gallery_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        out_path = images_dir / f"{query_hash}.jpg"

        if out_path.exists():
            return self._make_entry(query_hash, str(out_path), "image", "pexels", query, niche)

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(
                    "https://api.pexels.com/v1/search",
                    params={"query": query, "per_page": 3},
                    headers={"Authorization": self._pexels_key},
                )
                resp.raise_for_status()
                photos = resp.json().get("photos", [])
                if not photos:
                    return None
                img_url = photos[0]["src"]["original"]
                img_resp = client.get(img_url)
                img_resp.raise_for_status()
                out_path.write_bytes(img_resp.content)
        except Exception:
            return None

        return self._make_entry(query_hash, str(out_path), "image", "pexels", query, niche)

    def _pixabay_search(self, query: str, niche: str) -> GalleryEntry | None:
        query_hash = hashlib.md5(f"pixabay:{query}".encode()).hexdigest()[:12]
        clips_dir = self._gallery_dir / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)
        out_path = clips_dir / f"{query_hash}.mp4"

        if out_path.exists():
            return self._make_entry(query_hash, str(out_path), "clip", "pixabay", query, niche)

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(
                    "https://pixabay.com/api/videos/",
                    params={"key": self._pixabay_key, "q": query, "per_page": 3},
                )
                resp.raise_for_status()
                hits = resp.json().get("hits", [])
                if not hits:
                    return None
                # Pick smallest available size to save bandwidth
                videos = hits[0].get("videos", {})
                url = (
                    videos.get("small", {}).get("url")
                    or videos.get("medium", {}).get("url")
                )
                if not url:
                    return None
                vid_resp = client.get(url)
                vid_resp.raise_for_status()
                out_path.write_bytes(vid_resp.content)
        except Exception:
            return None

        return self._make_entry(query_hash, str(out_path), "clip", "pixabay", query, niche)

    @staticmethod
    def _make_entry(
        entry_id: str, path: str, asset_type: str, origin: str, query: str, niche: str
    ) -> GalleryEntry:
        tags = [t.lower() for t in query.split()]
        return GalleryEntry(
            id=entry_id, path=path, type=asset_type, origin=origin,
            prompt=None, query=query,
            tags=tags, niche=[niche] if niche else [],
            created_at=date.today().isoformat(),
        )


def search_gallery(
    query_terms: list[str],
    niche: str | None = None,
    asset_type: str | None = None,
    pexels_api_key: str | None = None,
    pixabay_api_key: str | None = None,
) -> GalleryResult:
    """Public API for gallery lookup. Reads keys from env when not provided."""
    import os
    pexels_key = pexels_api_key or os.getenv("PEXELS_API_KEY")
    pixabay_key = pixabay_api_key or os.getenv("PIXABAY_API_KEY")
    searcher = GallerySearcher(
        pexels_api_key=pexels_key,
        pixabay_api_key=pixabay_key,
    )
    return searcher.search(query_terms, niche=niche, asset_type=asset_type)
```

Note: `hashlib` and `date` imports already added — move them to the top of the file with the other imports. The `httpx` import also goes at the top.

- [ ] **Step 4: Fix imports at top of `gallery.py`** — add `hashlib`, `from datetime import date`, `import httpx` to the import block.

- [ ] **Step 5: Run all gallery tests**

```bash
uv run pytest tests/unit/test_gallery.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/utils/gallery.py tests/unit/test_gallery.py
git commit -m "feat(gallery): tiered lookup — local, Pexels, Pixabay, generate signal"
```

---

## Task 5: Gallery CLI subcommand + mount in cli.py

**Files:**
- Create: `src/pipeline/gallery_cli.py`
- Modify: `src/pipeline/cli.py` (2 lines)

- [ ] **Step 1: Create `gallery_cli.py`**

```python
# src/pipeline/gallery_cli.py
"""CLI subcommand: `pipeline gallery search`."""
from __future__ import annotations

import typer

from pipeline.utils.gallery import search_gallery

gallery_app = typer.Typer(name="gallery", help="Asset gallery management")


@gallery_app.command("search")
def gallery_search(
    query: str = typer.Argument(..., help="Search query (space-separated keywords)"),
    niche: str | None = typer.Option(None, "--niche", help="Filter by niche (e.g. bodycam)"),
    asset_type: str | None = typer.Option(
        None, "--type", help="Asset type: image or clip"
    ),
) -> None:
    """Search gallery for an asset. Falls through tiers: local → Pexels → Pixabay → generate."""
    terms = query.split()
    result = search_gallery(terms, niche=niche, asset_type=asset_type)

    if result.tier == "generate":
        typer.echo(f"tier=generate  suggested_prompt=\"{result.suggested_prompt}\"")
    else:
        entry = result.entry
        assert entry is not None
        tags_str = ",".join(entry.tags)
        typer.echo(
            f"tier={result.tier:<10} score=matched  {entry.path}  tags=[{tags_str}]"
        )
```

- [ ] **Step 2: Mount gallery_app in `cli.py`**

In `src/pipeline/cli.py`, add after the existing `from pipeline.research.cli import app as research_app` import:

```python
from pipeline.gallery_cli import gallery_app
```

And add after `app.add_typer(metadata_app, name="metadata")`:

```python
app.add_typer(gallery_app, name="gallery")
```

- [ ] **Step 3: Smoke-test the CLI**

```bash
uv run pipeline gallery --help
uv run pipeline gallery search "courtroom legal" --type image
```

Expected: help text prints; search runs without error (returns `tier=generate` since gallery is empty).

- [ ] **Step 4: Commit**

```bash
git add src/pipeline/gallery_cli.py src/pipeline/cli.py
git commit -m "feat(gallery): CLI subcommand + mount in pipeline app"
```

---

## Task 6: Gallery write-back in compose stage

**Files:**
- Modify: `src/pipeline/composer/image.py` (add gallery write-back after successful generation)

- [ ] **Step 1: Add write-back to `render_generated_image`**

In `src/pipeline/composer/image.py`, modify `render_generated_image` to accept a `gallery_path` parameter and write back when generation succeeds:

Replace the function signature:

```python
def render_generated_image(
    visual: dict,
    duration_sec: float,
    width: int,
    height: int,
    work_dir: Path,
    scene_id: str,
    gallery_path: Path | None = None,
    niche: str | None = None,
    scene_narration: str = "",
) -> Path:
```

After the successful `try_chain` call (after the `logger.info("image.generated", ...)` line), add:

```python
            # Write generated image back to gallery for reuse in future projects
            if gallery_path is not None:
                _write_to_gallery(
                    image_path=cached_png,
                    prompt=prompt,
                    gallery_path=gallery_path,
                    niche=niche or "",
                    scene_narration=scene_narration,
                )
```

Add `_write_to_gallery` function at the bottom of `image.py`:

```python
def _write_to_gallery(
    image_path: Path,
    prompt: str,
    gallery_path: Path,
    niche: str,
    scene_narration: str,
) -> None:
    """Append a successfully generated image to the global gallery index."""
    import hashlib
    import shutil
    from datetime import date
    from pipeline.utils.gallery import GalleryEntry, GalleryIndex, GALLERY_DIR

    gallery_images_dir = GALLERY_DIR / "images"
    gallery_images_dir.mkdir(parents=True, exist_ok=True)

    entry_id = hashlib.md5(prompt.encode()).hexdigest()[:12]
    dest = gallery_images_dir / f"{entry_id}.png"

    if not dest.exists():
        shutil.copy2(image_path, dest)

    # Derive tags from prompt + narration (simple word extraction)
    stop_words = {"a", "an", "the", "of", "in", "for", "with", "and", "or", "is", "are"}
    words = (prompt + " " + scene_narration).lower().split()
    tags = list(dict.fromkeys(w for w in words if len(w) > 3 and w not in stop_words))[:8]

    idx = GalleryIndex.load(gallery_path)
    # Skip if already indexed (same prompt → same entry_id)
    if any(e.id == entry_id for e in idx.entries):
        return
    idx.append(GalleryEntry(
        id=entry_id,
        path=str(dest),
        type="image",
        origin="dalle",
        prompt=prompt,
        query=None,
        tags=tags,
        niche=[niche] if niche else [],
        created_at=date.today().isoformat(),
    ))
    idx.save()
```

- [ ] **Step 2: Update callers in `composer/base.py`** to pass through `gallery_path` and `niche` and `scene_narration` if those come from the compose stage context.

Check `src/pipeline/composer/base.py` to find where `render_generated_image` is called:

```bash
grep -n "render_generated_image" src/pipeline/composer/base.py
```

Update the call site to pass `gallery_path=None, niche=None, scene_narration=""` (defaults — no change in behavior for existing code). The `ComposeStage` can pass real values when it has context.

- [ ] **Step 3: Smoke-test compose does not regress**

```bash
uv run pytest tests/ -v -k "compose" 2>&1 | tail -20
```

Expected: existing compose tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/pipeline/composer/image.py src/pipeline/composer/base.py
git commit -m "feat(gallery): write-back generated images to gallery after DALL-E success"
```

---

## Task 7: Integration test for highlight extractor

**Files:**
- Create: `tests/integration/test_highlight_extractor.py`

- [ ] **Step 1: Write integration test**

```python
# tests/integration/test_highlight_extractor.py
"""Integration test: real ffprobe against a fixture video file.

Requires: ffmpeg installed, fixture video present.
Run with: uv run pytest tests/integration/test_highlight_extractor.py -v
"""
from __future__ import annotations

import pytest
from pathlib import Path

from pipeline.utils.highlight_extractor import extract_highlights

FIXTURE_VIDEO = Path("tests/fixtures/sample_short.mp4")


@pytest.mark.integration
def test_extract_highlights_returns_valid_manifest():
    if not FIXTURE_VIDEO.exists():
        pytest.skip(f"Fixture video not found: {FIXTURE_VIDEO}")

    manifest = extract_highlights(FIXTURE_VIDEO, transcript_path=None)

    assert isinstance(manifest["candidates"], list)
    assert isinstance(manifest["rejected"], list)
    assert manifest["caption_provider"] == "NullCaptionProvider"
    assert manifest["duration_sec"] > 0

    for c in manifest["candidates"]:
        assert 0.0 <= c["combined_score"] <= 1.0
        assert c["usable"] is True
        assert "timestamp_sec" in c
        assert "keyframe_path" in c

    # Spacing check: no two candidates within 15s of each other
    timestamps = sorted(c["timestamp_sec"] for c in manifest["candidates"])
    for i in range(1, len(timestamps)):
        assert timestamps[i] - timestamps[i - 1] >= 14.9, \
            f"Candidates too close: {timestamps[i-1]}s and {timestamps[i]}s"
```

- [ ] **Step 2: Check if fixture video exists**

```bash
ls tests/fixtures/*.mp4 2>/dev/null || echo "no mp4 fixtures"
```

If none exist, create a 30-second silent test video:

```bash
ffmpeg -f lavfi -i color=c=blue:s=640x360:d=30:r=24 -f lavfi -i anullsrc=r=44100:cl=mono -shortest -c:v libx264 -c:a aac tests/fixtures/sample_short.mp4
```

- [ ] **Step 3: Run integration test**

```bash
uv run pytest tests/integration/test_highlight_extractor.py -v -m integration
```

Expected: PASS (solid-color video will have 0 scene changes, 0 audio, 0 keywords — so candidates may all score 0 but the manifest shape is valid).

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_highlight_extractor.py tests/fixtures/sample_short.mp4
git commit -m "test(highlight): integration test against fixture video"
```

---

## Task 8: Update .env.example + update produce skill

**Files:**
- Modify: `.env.example`
- Modify: `.claude/commands/produce.md`

- [ ] **Step 1: Add API key placeholders to `.env.example`**

Append to `.env.example`:

```bash
# Optional: stock photo/video gallery (free tiers)
# PEXELS_API_KEY=your_key_here
# PIXABAY_API_KEY=your_key_here
```

- [ ] **Step 2: Update produce skill — Step 1b block**

In `.claude/commands/produce.md`, find the **Step 1b** section and replace the existing keyframe extraction block with:

```markdown
### Step 1b: Highlight extraction (clip confidence)

Extract signal-scored highlight candidates — replaces raw keyframe scanning:

```bash
uv run python3 -c "
from pipeline.utils.highlight_extractor import extract_highlights
from pathlib import Path
import json

manifest = extract_highlights(
    Path('output/projects/<ID>/source/video.mp4'),
    transcript_path=Path('output/projects/<ID>/source/transcript.json'),
)
Path('output/projects/<ID>/source/clip_manifest.json').write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8'
)
print(f'Highlights: {len(manifest[\"candidates\"])} candidates ({manifest[\"duration_sec\"]}s video)')
for c in manifest['candidates']:
    print(f'  {c[\"timestamp_sec\"]:>6.0f}s  score={c[\"combined_score\"]:.2f}  keyframe={c[\"keyframe_path\"]}')
"
```

**IMPORTANT:** Read each keyframe image listed in `clip_manifest.json` candidates (only those 10, not all keyframes) to understand what's visually at each timestamp before assigning clips in the storyboard.

To swap in vision captions later (reduces image-reading to zero): pass `caption_provider=GptVisionCaptionProvider(api_key=...)` to `extract_highlights()`.
```

- [ ] **Step 3: Add Step 1c — ClipSelector sub-agent block** after Step 1b in produce.md:

```markdown
### Step 1c: ClipSelector sub-agent (QA gate)

**Dispatch a ClipSelector sub-agent** to validate the highlight candidates before proceeding. Do NOT self-evaluate.

```python
Agent(
  subagent_type="general-purpose",
  description="Validate highlight candidates for clip usability",
  prompt="""You are the CLIP SELECTOR — an independent QA agent.

Read: output/projects/<ID>/source/clip_manifest.json
Also read each keyframe image listed in candidates[].keyframe_path

For each candidate, apply the quality rubric:

PASS criteria (all must be true):
- Keyframe shows clear visual action or recognizable setting (not a talking head or blank)
- combined_score >= 0.5
- No sensitive content (explicit violence close-ups, private individuals in harmful context)

FAIL criteria (any triggers rejection):
- Keyframe shows ONLY: news anchor at desk, blank screen, static title card, empty room
- combined_score < 0.3
- Near-duplicate: another candidate within 10s covers the same content

Output STRICTLY in this format:
approved: [<timestamp_sec>, ...]
rejected: [{"timestamp_sec": X, "reason": "..."}]
summary: "X of Y candidates approved"

Under 150 words. Be critical."""
)
```

If 0 candidates are approved: warn the user and continue — all scenes will use designed visuals.
Note the approved timestamps. Reference ONLY approved timestamps when writing `clip` visual types in the storyboard.
```

- [ ] **Step 4: Add Step 3b — Gallery lookup + AssetEvaluator block** between Step 3 (human knowledge review) and Step 4 (storyboard creation) in produce.md:

```markdown
### Step 3b: Gallery lookup + AssetEvaluator sub-agent

Before writing the storyboard, consult the gallery for candidate assets per story section.

For each of the 6 story sections (hook, context, rising, climax, aftermath, analysis), run:

```bash
uv run pipeline gallery search "<section_concept_keywords>" --niche <niche> --type image
```

Example for a bodycam video with a courthouse climax scene:
```bash
uv run pipeline gallery search "courthouse verdict guilty" --niche bodycam --type image
```

Accumulate results and write `assets/manifest.json`:

```python
import json
from pathlib import Path

assets = {
    "hook": {"tier": "local", "path": "output/gallery/images/abc123.png", "tags": ["police", "night"]},
    "context": {"tier": "generate", "suggested_prompt": "flat minimalist map of US state borders"},
    # ... one entry per section
}
Path('output/projects/<ID>/assets').mkdir(parents=True, exist_ok=True)
Path('output/projects/<ID>/assets/manifest.json').write_text(
    json.dumps(assets, indent=2), encoding='utf-8'
)
```

Then **dispatch the AssetEvaluator sub-agent**:

```python
Agent(
  subagent_type="general-purpose",
  description="Validate gallery/stock assets against scene intent",
  prompt="""You are the ASSET EVALUATOR — an independent QA agent.

Read:
1. output/projects/<ID>/assets/manifest.json  (proposed assets per story section)
2. output/projects/<ID>/knowledge.json         (what the video is about)

For each proposed asset:
1. Relevance (1-5): does it illustrate its assigned section?
2. Quality (PASS/FAIL): resolution adequate? No watermarks? No AI faces?
3. Tone match (PASS/FAIL): does the visual mood match the narrative moment?

Hard rejects:
- Watermarked images
- AI photorealism on human faces
- Asset visually unrelated to the video topic

Output per asset: APPROVED / REPLACE (with alternative gallery search query) / GENERATE
Overall verdict: PASS (>80% approved) or NEEDS_WORK

Under 200 words. Be critical."""
)
```

If NEEDS_WORK: re-run gallery search with the suggested alternative queries, then re-evaluate. Fix before proceeding to storyboard.

Use the approved asset paths when setting `visual.type = "article_image"` with `visual.path` in storyboard scenes. Tier-3 (generate) sections will use `visual.type = "generated_image"` as usual.
```

- [ ] **Step 5: Verify produce skill is readable**

```bash
wc -l .claude/commands/produce.md
```

- [ ] **Step 6: Full lint pass**

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run mypy src/pipeline/utils/highlight_extractor.py src/pipeline/utils/gallery.py src/pipeline/gallery_cli.py
```

Fix any errors, then:

- [ ] **Step 7: Run full test suite**

```bash
uv run pytest tests/unit/ -v
```

Expected: all tests PASS.

- [ ] **Step 8: Final commit**

```bash
git add .env.example .claude/commands/produce.md
git commit -m "feat(produce): highlight manifest + gallery lookup + ClipSelector + AssetEvaluator checkpoints"
```

---

## Self-Review Checklist

- [x] **Spec coverage:**
  - Highlight Extractor → Tasks 1–2 + Task 7 integration test
  - CaptionProvider protocol (extensible) → Task 1
  - Gallery tiered lookup → Tasks 3–4
  - Gallery CLI → Task 5
  - Gallery write-back → Task 6
  - ClipSelector sub-agent → Task 8 (produce.md Step 1c)
  - AssetEvaluator sub-agent → Task 8 (produce.md Step 3b)
  - .env.example placeholders → Task 8
  - Future enhancements noted in spec, not in plan

- [x] **Placeholder scan:** No TBD/TODO. All code blocks are complete.

- [x] **Type consistency:**
  - `extract_highlights()` returns `dict` — used in Task 2 tests ✓
  - `GalleryEntry`, `GalleryIndex`, `GallerySearcher`, `GalleryResult` — defined in Task 3, used in Task 4 ✓
  - `search_gallery()` public API — used in Task 5 CLI ✓
  - `render_generated_image` new params `gallery_path`, `niche`, `scene_narration` — all Optional with defaults ✓
