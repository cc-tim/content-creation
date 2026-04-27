# Visual Consistency, Clip Budget & Intro Template — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce a ~60% source-clip scene budget, lock per-niche intro templates, and apply a consistent niche-defined visual style (style-descriptor prefix + deterministic seed + production tier) to all generated images, with a duplicate source-frame guard that automatically replaces repeated clips.

**Architecture:** `DirectStage` receives clip-budget and intro-template constraints injected into the Claude prompt. `ComposeStage` runs `StyleAnchorExtractor` before the scene loop (source suitability → style descriptor → anchor image), stores results in the theme dict, and checks perceptual hashes for duplicate clip frames before rendering. `render_scene` in `base.py` forwards style prefix + seed to `render_generated_image`, which bumps to production tier and includes seed in the cache key.

**Tech Stack:** Python 3.12, anthropic SDK (Haiku for cheap vision calls), fal.ai via gen-image.py (production tier), `imagehash>=4.3` + `Pillow` (already present) for perceptual hashing, `tomllib` (stdlib) for reading TOML, manual TOML writer for saving new niche templates.

**Spec:** `docs/superpowers/specs/2026-04-28-visual-consistency-clip-budget-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `pyproject.toml` | Modify | Add `imagehash>=4.3` dependency |
| `src/pipeline/constraints.py` | Modify | Add `max_source_clip_pct`, `source_suitability`; add `clip_budget_instruction()`, `check_clip_budget()` |
| `src/pipeline/niche_templates.py` | **Create** | `NicheTemplate` dataclass, `load_niche_template()`, `save_niche_template()` |
| `configs/niche_intro_templates.toml` | **Create** | Parenting + true-crime niche profiles |
| `src/pipeline/composer/style_anchor.py` | **Create** | `StyleAnchorResult`, `extract_style_anchor()` — source frame → suitability → style descriptor → anchor image |
| `src/pipeline/composer/base.py` | Modify | Pass `style_prefix`, `seed`, `anchor_image` from theme dict into `render_generated_image` |
| `src/pipeline/composer/image.py` | Modify | Accept `style_prefix`, `seed`, `anchor_image`; prepend prefix; include seed in cache key; use production tier when anchor active |
| `src/pipeline/stages/direct.py` | Modify | Inject clip-budget instruction + intro template constraint into `build_direct_prompt`; validate clip % post-generation |
| `src/pipeline/stages/compose.py` | Modify | Call `extract_style_anchor` before scene loop; add duplicate-frame guard per clip scene |
| `tests/unit/test_constraints_clip.py` | **Create** | Tests for new constraint fields and helpers |
| `tests/unit/test_niche_templates.py` | **Create** | Tests for template load/save |
| `tests/unit/test_style_anchor.py` | **Create** | Tests for style anchor extraction (mocked ffmpeg + Claude) |
| `tests/unit/test_image_style.py` | **Create** | Tests for style_prefix/seed in render_generated_image |
| `tests/unit/test_direct_clip_budget.py` | **Create** | Tests for clip budget prompt injection and validation |
| `tests/unit/test_compose_dup_guard.py` | **Create** | Tests for duplicate frame guard |

---

## Task 1: Add `imagehash` dependency + extend `constraints.py`

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/pipeline/constraints.py`
- Create: `tests/unit/test_constraints_clip.py`

- [ ] **Step 1.1 — Write failing tests**

```python
# tests/unit/test_constraints_clip.py
from pipeline.constraints import ProjectConstraints


def test_default_clip_pct():
    c = ProjectConstraints()
    assert c.max_source_clip_pct == 0.60


def test_clip_budget_instruction_counts():
    c = ProjectConstraints(max_source_clip_pct=0.60)
    instr = c.clip_budget_instruction(scene_count=20)
    assert "12" in instr          # 60% of 20
    assert "20" in instr
    assert "clip" in instr.lower()


def test_check_clip_budget_ok():
    c = ProjectConstraints(max_source_clip_pct=0.60)
    scenes = [{"visual": {"type": "clip"}} for _ in range(10)] + \
             [{"visual": {"type": "generated_image"}} for _ in range(10)]
    assert c.check_clip_budget(scenes) == []


def test_check_clip_budget_exceeded():
    c = ProjectConstraints(max_source_clip_pct=0.60)
    scenes = [{"visual": {"type": "clip"}} for _ in range(18)] + \
             [{"visual": {"type": "generated_image"}} for _ in range(2)]
    violations = c.check_clip_budget(scenes)
    assert len(violations) == 1
    assert "18" in violations[0]


def test_still_frame_counts_against_budget():
    c = ProjectConstraints(max_source_clip_pct=0.60)
    scenes = [{"visual": {"type": "still_frame"}} for _ in range(18)] + \
             [{"visual": {"type": "generated_image"}} for _ in range(2)]
    violations = c.check_clip_budget(scenes)
    assert violations  # still_frame counts as source usage


def test_round_trip_json(tmp_path):
    c = ProjectConstraints(max_source_clip_pct=0.40, source_suitability="low")
    c.save(tmp_path)
    loaded = ProjectConstraints.load(tmp_path)
    assert loaded.max_source_clip_pct == 0.40
    assert loaded.source_suitability == "low"
```

- [ ] **Step 1.2 — Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_constraints_clip.py -v
```
Expected: `AttributeError: 'ProjectConstraints' object has no attribute 'max_source_clip_pct'`

- [ ] **Step 1.3 — Add `imagehash` to `pyproject.toml`**

In `pyproject.toml`, add to the `dependencies` list (after `pillow>=12.2.0`):
```toml
    "imagehash>=4.3",
```

- [ ] **Step 1.4 — Extend `src/pipeline/constraints.py`**

Replace the `ProjectConstraints` dataclass with:

```python
@dataclass
class ProjectConstraints:
    duration_min_minutes: float | None = None
    duration_max_minutes: float | None = None
    max_source_clip_pct: float = 0.60
    source_suitability: str = ""  # "high" | "medium" | "low" | ""
    notes: str = ""

    @classmethod
    def load(cls, work_dir: Path) -> ProjectConstraints | None:
        path = work_dir / _FILENAME
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        valid = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in valid})

    def save(self, work_dir: Path) -> None:
        path = work_dir / _FILENAME
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    def clip_budget_instruction(self, scene_count: int) -> str:
        max_clips = int(scene_count * self.max_source_clip_pct)
        pct = int(self.max_source_clip_pct * 100)
        return (
            f"VISUAL BUDGET: At most {max_clips} of {scene_count} scenes may use type "
            f"'clip' or 'still_frame' from source ({pct}% soft limit). "
            f"Prefer generated_image for explanation, analysis, and concept scenes."
        )

    def check_clip_budget(self, scenes: list[dict]) -> list[str]:
        """Return list of human-readable violations. Empty = OK."""
        source_types = {"clip", "still_frame"}
        clip_count = sum(
            1 for s in scenes
            if (s.get("visual") or {}).get("type") in source_types
        )
        max_clips = int(len(scenes) * self.max_source_clip_pct)
        if clip_count > max_clips:
            return [
                f"Clip budget: {clip_count}/{len(scenes)} scenes use source clips "
                f"(soft limit: {max_clips})"
            ]
        return []

    def format_reminder(self) -> str:
        lines = ["PROJECT CONSTRAINTS (set at initial produce — must be preserved):"]
        lo, hi = self.duration_min_minutes, self.duration_max_minutes
        if lo is not None and hi is not None:
            lines.append(f"  - Duration: {lo}–{hi} minutes (HARD REQUIREMENT)")
        elif lo is not None:
            lines.append(f"  - Duration: at least {lo} minutes (HARD REQUIREMENT)")
        elif hi is not None:
            lines.append(f"  - Duration: at most {hi} minutes (HARD REQUIREMENT)")
        if self.notes:
            lines.append(f"  - Notes: {self.notes}")
        return "\n".join(lines)

    def duration_instruction(self) -> str:
        lo, hi = self.duration_min_minutes, self.duration_max_minutes
        if lo is not None and hi is not None:
            return f"Target {lo}–{hi} minutes total. HARD REQUIREMENT: stay within this range."
        if lo is not None:
            return f"Target at least {lo} minutes total. HARD REQUIREMENT."
        if hi is not None:
            return f"Target at most {hi} minutes total. HARD REQUIREMENT."
        return ""

    def check_storyboard(self, duration_sec: float) -> list[str]:
        violations: list[str] = []
        minutes = duration_sec / 60
        if self.duration_min_minutes is not None and minutes < self.duration_min_minutes:
            violations.append(
                f"Duration {minutes:.1f} min is below the {self.duration_min_minutes} min minimum"
            )
        if self.duration_max_minutes is not None and minutes > self.duration_max_minutes:
            violations.append(
                f"Duration {minutes:.1f} min exceeds the {self.duration_max_minutes} min maximum"
            )
        return violations
```

- [ ] **Step 1.5 — Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_constraints_clip.py -v
```
Expected: all 6 tests PASS.

- [ ] **Step 1.6 — Install new dependency**

```bash
uv sync
python -c "import imagehash; print(imagehash.__version__)"
```
Expected: prints version >= 4.3.

- [ ] **Step 1.7 — Commit**

```bash
git add pyproject.toml uv.lock src/pipeline/constraints.py tests/unit/test_constraints_clip.py
git commit -m "feat(constraints): add clip budget fields and helpers; add imagehash dependency"
```

---

## Task 2: Niche templates — config file + loader

**Files:**
- Create: `configs/niche_intro_templates.toml`
- Create: `src/pipeline/niche_templates.py`
- Create: `tests/unit/test_niche_templates.py`

- [ ] **Step 2.1 — Write failing tests**

```python
# tests/unit/test_niche_templates.py
import tomllib
from pathlib import Path
import pytest
from pipeline.niche_templates import NicheTemplate, load_niche_template, save_niche_template


def test_load_parenting_template():
    t = load_niche_template("parenting")
    assert t is not None
    assert t.niche == "parenting"
    assert t.intro_type == "generated_image"
    assert t.visual_style  # non-empty
    assert t.anchor_prompt  # non-empty


def test_load_unknown_niche_returns_none():
    t = load_niche_template("nonexistent_niche_xyz")
    assert t is None


def test_save_and_reload(tmp_path):
    # Point to a temp TOML file
    import pipeline.niche_templates as nt_mod
    original = nt_mod.TEMPLATES_PATH
    nt_mod.TEMPLATES_PATH = tmp_path / "test_templates.toml"
    try:
        t = NicheTemplate(
            niche="test",
            intro_type="text_card",
            intro_prompt_hint="A test hint",
            visual_style="minimal sketch",
            anchor_prompt="simple scene",
            rationale="testing",
        )
        save_niche_template(t)
        loaded = load_niche_template("test")
        assert loaded is not None
        assert loaded.intro_type == "text_card"
        assert loaded.visual_style == "minimal sketch"
    finally:
        nt_mod.TEMPLATES_PATH = original


def test_save_preserves_existing(tmp_path):
    import pipeline.niche_templates as nt_mod
    original = nt_mod.TEMPLATES_PATH
    nt_mod.TEMPLATES_PATH = tmp_path / "test_templates.toml"
    try:
        t1 = NicheTemplate("a", "generated_image", "hint a", "style a", "anchor a")
        t2 = NicheTemplate("b", "text_card", "hint b", "style b", "anchor b")
        save_niche_template(t1)
        save_niche_template(t2)
        assert load_niche_template("a") is not None
        assert load_niche_template("b") is not None
    finally:
        nt_mod.TEMPLATES_PATH = original
```

- [ ] **Step 2.2 — Run tests to confirm failure**

```bash
uv run pytest tests/unit/test_niche_templates.py -v
```
Expected: `ModuleNotFoundError: No module named 'pipeline.niche_templates'`

- [ ] **Step 2.3 — Create `configs/niche_intro_templates.toml`**

```toml
[parenting]
intro_type = "generated_image"
intro_prompt_hint = "parent and child in a warm home moment, sketch style, relatable, no text"
visual_style = "clean educational sketch, minimal line art, simple warm tones, no clutter, conceptual"
anchor_prompt = "parent and child in a calm home setting, sketch illustration, minimal color, friendly"
rationale = "Parenting source videos reuse the same illustration panels; our hook must be original and our style defined by the story"

[true-crime]
intro_type = "text_card"
intro_prompt_hint = "Dark background, bold white hook text — one sentence, drop viewer mid-action, no setup"
visual_style = "cinematic still, dramatic lighting, documentary aesthetic, high contrast, desaturated"
anchor_prompt = "empty corridor at night, single dim light source, tense atmosphere, photorealistic"
rationale = "True-crime hooks land harder as stark text; cinematic style builds dread"
```

- [ ] **Step 2.4 — Create `src/pipeline/niche_templates.py`**

```python
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

TEMPLATES_PATH = Path(__file__).parent.parent.parent / "configs" / "niche_intro_templates.toml"


@dataclass
class NicheTemplate:
    niche: str
    intro_type: str           # "generated_image" | "text_card" | "slide"
    intro_prompt_hint: str    # injected into Claude prompt for s1
    visual_style: str         # 30-word style descriptor for all generated images
    anchor_prompt: str        # prompt for generating the niche anchor image
    rationale: str = ""


def load_niche_template(niche: str) -> NicheTemplate | None:
    """Return the template for *niche*, or None if not found."""
    if not TEMPLATES_PATH.exists():
        return None
    with open(TEMPLATES_PATH, "rb") as f:
        data = tomllib.load(f)
    if niche not in data:
        return None
    d = data[niche]
    return NicheTemplate(
        niche=niche,
        intro_type=d["intro_type"],
        intro_prompt_hint=d["intro_prompt_hint"],
        visual_style=d["visual_style"],
        anchor_prompt=d["anchor_prompt"],
        rationale=d.get("rationale", ""),
    )


def save_niche_template(template: NicheTemplate) -> None:
    """Append or update *template* in the TOML file."""
    existing: dict = {}
    if TEMPLATES_PATH.exists():
        with open(TEMPLATES_PATH, "rb") as f:
            existing = tomllib.load(f)

    existing[template.niche] = {
        "intro_type": template.intro_type,
        "intro_prompt_hint": template.intro_prompt_hint,
        "visual_style": template.visual_style,
        "anchor_prompt": template.anchor_prompt,
        "rationale": template.rationale,
    }

    TEMPLATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEMPLATES_PATH.write_text(_to_toml(existing), encoding="utf-8")


def _to_toml(data: dict) -> str:
    """Simple TOML serializer for flat string-value sections."""
    lines: list[str] = []
    for section, fields in data.items():
        lines.append(f"[{section}]")
        for k, v in fields.items():
            escaped = str(v).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{k} = "{escaped}"')
        lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 2.5 — Run tests to verify pass**

```bash
uv run pytest tests/unit/test_niche_templates.py -v
```
Expected: all 4 tests PASS.

- [ ] **Step 2.6 — Commit**

```bash
git add configs/niche_intro_templates.toml src/pipeline/niche_templates.py tests/unit/test_niche_templates.py
git commit -m "feat(niche-templates): add per-niche intro + visual style config; seed parenting + true-crime"
```

---

## Task 3: `StyleAnchorExtractor`

**Files:**
- Create: `src/pipeline/composer/style_anchor.py`
- Create: `tests/unit/test_style_anchor.py`

- [ ] **Step 3.1 — Write failing tests**

```python
# tests/unit/test_style_anchor.py
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from pipeline.composer.style_anchor import (
    StyleAnchorResult,
    _derive_seed,
    _synthesize_style,
    extract_style_anchor,
)
from pipeline.niche_templates import NicheTemplate


def test_derive_seed_is_deterministic():
    s1 = _derive_seed("1777161293")
    s2 = _derive_seed("1777161293")
    assert s1 == s2
    assert isinstance(s1, int)
    assert 0 <= s1 < 2**32


def test_derive_seed_differs_by_project():
    assert _derive_seed("111") != _derive_seed("222")


def test_synthesize_style_niche_takes_priority():
    template = NicheTemplate(
        niche="parenting",
        intro_type="generated_image",
        intro_prompt_hint="...",
        visual_style="clean educational sketch",
        anchor_prompt="...",
    )
    result = _synthesize_style(template, source_hint="anime style")
    assert "clean educational sketch" in result
    # source hint referenced but niche comes first
    assert result.startswith("clean educational sketch")


def test_synthesize_style_falls_back_without_template():
    result = _synthesize_style(None, source_hint="")
    assert result  # non-empty fallback


def test_extract_style_anchor_uses_cached_anchor(tmp_path):
    # Create a fake anchor image
    anchor_dir = tmp_path / "niche_anchors" / "parenting"
    anchor_dir.mkdir(parents=True)
    anchor_img = anchor_dir / "style_anchor.png"
    anchor_img.write_bytes(b"fake")

    template = NicheTemplate("parenting", "generated_image", "", "clean sketch", "...", "")

    with patch("pipeline.composer.style_anchor.NICHE_ANCHOR_DIR", tmp_path / "niche_anchors"), \
         patch("pipeline.composer.style_anchor._extract_source_frame", return_value=None), \
         patch("pipeline.composer.style_anchor._generate_anchor_image") as mock_gen:
        result = extract_style_anchor(
            project_id="123", niche="parenting", template=template, source_video=None, work_dir=tmp_path
        )
    mock_gen.assert_not_called()  # cache hit — no generation
    assert result.anchor_image == anchor_img
    assert result.style_descriptor == "clean sketch"


def test_extract_style_anchor_generates_anchor_when_missing(tmp_path):
    fake_anchor = tmp_path / "niche_anchors" / "parenting" / "style_anchor.png"
    template = NicheTemplate("parenting", "generated_image", "", "clean sketch", "simple scene", "")

    with patch("pipeline.composer.style_anchor.NICHE_ANCHOR_DIR", tmp_path / "niche_anchors"), \
         patch("pipeline.composer.style_anchor._extract_source_frame", return_value=None), \
         patch("pipeline.composer.style_anchor._generate_anchor_image", return_value=fake_anchor) as mock_gen:
        result = extract_style_anchor(
            project_id="123", niche="parenting", template=template, source_video=None, work_dir=tmp_path
        )
    mock_gen.assert_called_once()
    assert result.anchor_image == fake_anchor
```

- [ ] **Step 3.2 — Run tests to confirm failure**

```bash
uv run pytest tests/unit/test_style_anchor.py -v
```
Expected: `ModuleNotFoundError: No module named 'pipeline.composer.style_anchor'`

- [ ] **Step 3.3 — Create `src/pipeline/composer/style_anchor.py`**

```python
from __future__ import annotations

import base64
import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

import structlog

from pipeline.niche_templates import NicheTemplate

logger = structlog.get_logger()

NICHE_ANCHOR_DIR = Path(__file__).parent.parent.parent.parent / "configs" / "niche_anchors"
_HAIKU_MODEL = "claude-haiku-4-5-20251001"  # update when this model ID retires
_FALLBACK_STYLE = "clean illustration, simple composition, warm tones, educational, friendly"


@dataclass
class StyleAnchorResult:
    style_descriptor: str       # 30-word style string to prepend to all image prompts
    seed: int                   # deterministic per-project seed for image generation
    anchor_image: Path | None   # path to niche anchor PNG (None if generation failed)
    suitability: str            # "high" | "medium" | "low" | ""


def _derive_seed(project_id: str) -> int:
    return int(hashlib.md5(project_id.encode()).hexdigest()[:8], 16)


def _synthesize_style(template: NicheTemplate | None, source_hint: str) -> str:
    """Combine niche profile (primary) + source hint (reference). Niche wins."""
    if template:
        base = template.visual_style
        if source_hint:
            return f"{base}, referencing {source_hint}"
        return base
    if source_hint:
        return f"{_FALLBACK_STYLE}, inspired by {source_hint}"
    return _FALLBACK_STYLE


def _extract_source_frame(source_video: Path, work_dir: Path) -> Path | None:
    """Extract a frame at ~10% of source duration. Returns path or None on failure."""
    frame_path = work_dir / "style_source_frame.jpg"
    if frame_path.exists():
        return frame_path
    try:
        # Get duration
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(source_video)],
            capture_output=True, text=True, check=True,
        )
        duration = float(result.stdout.strip())
        timestamp = max(5.0, duration * 0.10)
        subprocess.run(
            ["ffmpeg", "-ss", str(timestamp), "-i", str(source_video),
             "-vframes", "1", "-q:v", "2", str(frame_path), "-y"],
            check=True, capture_output=True,
        )
        return frame_path
    except Exception as exc:
        logger.warning("style_anchor.frame_extract_failed", error=str(exc))
        return None


def _assess_source(frame_path: Path) -> tuple[str, str]:
    """Return (suitability, source_hint). Calls Claude Haiku with vision."""
    try:
        import anthropic
        from pipeline.config import PipelineConfig

        img_bytes = frame_path.read_bytes()
        b64 = base64.standard_b64encode(img_bytes).decode()
        client = anthropic.Anthropic(api_key=PipelineConfig().ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=_HAIKU_MODEL,
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": "image/jpeg", "data": b64,
                    }},
                    {"type": "text", "text": (
                        "Answer in exactly 2 lines:\n"
                        "Line 1: ONE word — is this source footage high, medium, or low quality "
                        "for reuse? (high=unique clean footage, medium=OK but some repetition, "
                        "low=repetitive panels or talking-head or watermarked)\n"
                        "Line 2: Describe the visual style in 10 words max (art medium, line style, palette)."
                    )},
                ],
            }],
        )
        lines = resp.content[0].text.strip().splitlines()
        suitability = lines[0].strip().lower() if lines else "medium"
        if suitability not in ("high", "medium", "low"):
            suitability = "medium"
        source_hint = lines[1].strip() if len(lines) > 1 else ""
        return suitability, source_hint
    except Exception as exc:
        logger.warning("style_anchor.assess_failed", error=str(exc))
        return "medium", ""


def _generate_anchor_image(
    anchor_prompt: str, style_descriptor: str, seed: int, out_path: Path
) -> Path | None:
    """Generate one anchor image at production tier. Returns path or None on failure."""
    from pipeline.providers.gen_image import GenImageProvider
    from pipeline.providers.base import ProviderError

    out_path.parent.mkdir(parents=True, exist_ok=True)
    provider = GenImageProvider(tier="production")
    full_prompt = f"{style_descriptor}, {anchor_prompt}"
    try:
        provider.generate(prompt=full_prompt, out_path=out_path, size="1792x1024")
        logger.info("style_anchor.anchor_generated", path=str(out_path))
        return out_path
    except ProviderError as exc:
        logger.warning("style_anchor.anchor_generation_failed", error=str(exc))
        return None


def extract_style_anchor(
    project_id: str,
    niche: str | None,
    template: NicheTemplate | None,
    source_video: Path | None,
    work_dir: Path,
) -> StyleAnchorResult:
    """Orchestrate: source frame → suitability → style descriptor → anchor image.

    Returns a StyleAnchorResult. Fails gracefully — never raises.
    """
    seed = _derive_seed(project_id)

    # 1. Extract source frame for analysis
    source_hint = ""
    suitability = "medium"
    if source_video and source_video.exists():
        frame = _extract_source_frame(source_video, work_dir)
        if frame:
            suitability, source_hint = _assess_source(frame)
            logger.info("style_anchor.suitability", value=suitability, hint=source_hint)

    # 2. Synthesize style descriptor (niche template is primary)
    style_descriptor = _synthesize_style(template, source_hint)

    # 3. Get or generate anchor image
    anchor_image: Path | None = None
    if niche:
        anchor_path = NICHE_ANCHOR_DIR / niche / "style_anchor.png"
        if anchor_path.exists():
            logger.info("style_anchor.anchor_reused", niche=niche)
            anchor_image = anchor_path
        elif template:
            anchor_image = _generate_anchor_image(
                anchor_prompt=template.anchor_prompt,
                style_descriptor=style_descriptor,
                seed=seed,
                out_path=anchor_path,
            )

    return StyleAnchorResult(
        style_descriptor=style_descriptor,
        seed=seed,
        anchor_image=anchor_image,
        suitability=suitability,
    )
```

- [ ] **Step 3.4 — `ANTHROPIC_API_KEY` already exists — no action needed**

`src/pipeline/config.py:11` already has `ANTHROPIC_API_KEY: str = ""` and `analyze.py:19` uses `anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)`. The `style_anchor.py` code imports the same pattern — nothing to change here.

- [ ] **Step 3.5 — Run tests to verify pass**

```bash
uv run pytest tests/unit/test_style_anchor.py -v
```
Expected: all 5 tests PASS.

- [ ] **Step 3.6 — Commit**

```bash
git add src/pipeline/composer/style_anchor.py tests/unit/test_style_anchor.py
git commit -m "feat(style-anchor): add StyleAnchorExtractor — source suitability, niche style, anchor image"
```

---

## Task 4: Extend `image.py` + update `base.py`

**Files:**
- Modify: `src/pipeline/composer/image.py`
- Modify: `src/pipeline/composer/base.py`
- Create: `tests/unit/test_image_style.py`

- [ ] **Step 4.1 — Write failing tests**

```python
# tests/unit/test_image_style.py
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest


def test_style_prefix_prepended_to_prompt(tmp_path):
    from pipeline.composer.image import render_generated_image

    captured = {}
    def fake_try_chain(providers, prompt, out_path, size):
        captured["prompt"] = prompt
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # Write a valid minimal PNG (1x1 white pixel)
        out_path.write_bytes(
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00'
            b'\x00\x11\x00\x01\x1b\xb0\xa4G\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        return MagicMock(provider="test")

    visual = {"type": "generated_image", "prompt": "parent and child"}
    with patch("pipeline.composer.image.try_chain", side_effect=fake_try_chain), \
         patch("pipeline.composer.image.image_to_video"):
        render_generated_image(
            visual, 5.0, 1280, 720, tmp_path, "s1",
            style_prefix="clean sketch style",
        )
    assert captured["prompt"].startswith("clean sketch style")
    assert "parent and child" in captured["prompt"]


def test_seed_included_in_cache_key(tmp_path):
    from pipeline.composer.image import _cache_key_with_seed

    key_no_seed = _cache_key_with_seed("hello", None)
    key_seed_1 = _cache_key_with_seed("hello", 42)
    key_seed_2 = _cache_key_with_seed("hello", 99)

    assert key_no_seed != key_seed_1
    assert key_seed_1 != key_seed_2
    assert _cache_key_with_seed("hello", 42) == key_seed_1  # deterministic


def test_production_tier_used_when_style_prefix_set(tmp_path):
    from pipeline.composer.image import render_generated_image
    from pipeline.providers.gen_image import GenImageProvider

    created_providers = []
    original_init = GenImageProvider.__init__
    def spy_init(self, tier="draft"):
        created_providers.append(tier)
        original_init(self, tier)

    with patch("pipeline.composer.image.GenImageProvider.__init__", spy_init), \
         patch("pipeline.composer.image.try_chain") as mock_chain, \
         patch("pipeline.composer.image.image_to_video"):
        fake_png = tmp_path / "img_cache" / "abc123.png"
        fake_png.parent.mkdir(parents=True)
        fake_png.write_bytes(b"fake")
        # Pre-populate cache so generation is skipped — test tier with cache miss
        visual = {"type": "generated_image", "prompt": "test scene"}
        mock_chain.return_value = MagicMock(provider="test")
        # Write fake output
        def fake_chain(providers, prompt, out_path, size):
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(b"fake")
            return MagicMock(provider="test")
        mock_chain.side_effect = fake_chain
        with patch("pipeline.composer.image.image_to_video"):
            render_generated_image(
                visual, 5.0, 1280, 720, tmp_path, "s2",
                style_prefix="clean sketch",
                seed=12345,
            )
    # Production tier should have been used
    assert "production" in created_providers
```

- [ ] **Step 4.2 — Run tests to confirm failure**

```bash
uv run pytest tests/unit/test_image_style.py -v
```
Expected: `ImportError` or `TypeError` on missing params.

- [ ] **Step 4.3 — Modify `src/pipeline/composer/image.py`**

Add `_cache_key_with_seed` and update `render_generated_image`:

```python
# Add after the existing _cache_key function:
def _cache_key_with_seed(prompt: str, seed: int | None) -> str:
    raw = f"{prompt}|{seed}" if seed is not None else prompt
    return hashlib.md5(raw.encode()).hexdigest()[:12]
```

Update `render_generated_image` signature and internals:

```python
def render_generated_image(
    visual: dict[str, Any],
    duration_sec: float,
    width: int,
    height: int,
    work_dir: Path,
    scene_id: str,
    gallery_path: Path | None = None,
    niche: str | None = None,
    scene_narration: str = "",
    theme: dict | None = None,
    style_prefix: str = "",
    seed: int | None = None,
    anchor_image: Path | None = None,
) -> Path:
    """Generate an image via gen-image.py, convert to video segment."""
    prompt = visual.get("prompt", "abstract background")

    # Prepend niche style prefix (takes priority over scene prompt)
    if style_prefix:
        prompt = f"{style_prefix}, {prompt}".strip(", ")

    # Upgrade to production tier when style anchor is active for better adherence
    tier = visual.get("image_tier", "production" if style_prefix else "draft")

    cache_dir = work_dir / "image_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_name = _cache_key_with_seed(prompt, seed)
    cached_png = cache_dir / f"{cache_name}.png"
    output = work_dir / f"{scene_id}_visual.mp4"

    if cached_png.exists():
        if _is_too_dark(cached_png):
            logger.warning("image.dark_cache_evicted", scene=scene_id, path=str(cached_png))
            cached_png.unlink()
        else:
            logger.info("image.cache_hit", prompt=prompt[:50])

    if not cached_png.exists():
        # Gemini reference_image slot: activated when anchor_image is available
        # and GeminiImageProvider has API credits. Currently a no-op with GenImageProvider.
        provider = GenImageProvider(tier=tier)
        try:
            result = try_chain(
                [provider],
                prompt=prompt,
                out_path=cached_png,
                size=_size_arg(width, height),
            )
            logger.info("image.generated", prompt=prompt[:50], provider=result.provider, tier=tier)
            if _is_too_dark(cached_png):
                logger.warning("image.dark_retry", scene=scene_id)
                cached_png.unlink()
                light_prompt = f"{prompt}, white background, bright cream paper, no dark areas"
                light_key = _cache_key_with_seed(light_prompt, seed)
                light_png = cache_dir / f"{light_key}.png"
                size = _size_arg(width, height)
                try_chain([provider], prompt=light_prompt, out_path=light_png, size=size)
                cached_png = light_png
                bright = not _is_too_dark(cached_png)
                logger.info("image.dark_retry_done", scene=scene_id, bright=bright)
            if gallery_path is not None:
                _write_to_gallery(
                    image_path=cached_png,
                    prompt=prompt,
                    gallery_path=gallery_path,
                    niche=niche or "",
                    scene_narration=scene_narration,
                )
        except ProviderError as exc:
            logger.warning("image.generation_failed", error=str(exc))
            return _fallback_text_card(
                scene_narration or prompt, duration_sec, width, height, work_dir, scene_id, theme
            )

    image_to_video(cached_png, output, duration_sec, width, height)
    return output
```

- [ ] **Step 4.4 — Update `src/pipeline/composer/base.py` render_scene for `generated_image`**

Replace the `generated_image` branch in `render_scene`:

```python
    elif visual_type == "generated_image":
        from pipeline.composer.image import render_generated_image

        # Style prefix: niche visual identity injected via theme (takes priority over image_style)
        style_prefix = theme.get("style_prefix", "")
        image_style = theme.get("image_style", "")

        if "prompt" in visual:
            prompt = visual["prompt"]
            parts: list[str] = []
            if style_prefix:
                parts.append(style_prefix)
            parts.append(prompt)
            # image_style (from storyboard theme) is appended regardless of style_prefix —
            # spec says priority is niche_profile + source_hints + story_tone, all contribute.
            if image_style and image_style not in prompt:
                parts.append(f"Style: {image_style}")
            visual = {**visual, "prompt": ", ".join(p for p in parts if p)}

        seed: int | None = theme.get("_seed")
        anchor_image_raw = theme.get("_anchor_image")
        anchor_image = Path(anchor_image_raw) if anchor_image_raw else None

        gallery_path = Path("output/gallery/gallery_index.json")
        return render_generated_image(
            visual,
            duration_sec,
            width,
            height,
            work_dir,
            scene_id,
            gallery_path=gallery_path,
            niche=theme.get("niche"),
            scene_narration=scene.get("narration", ""),
            theme=theme,
            style_prefix=style_prefix,
            seed=seed,
            anchor_image=anchor_image,
        )
```

- [ ] **Step 4.5 — Run tests**

```bash
uv run pytest tests/unit/test_image_style.py -v
uv run pytest tests/unit/ -v --ignore=tests/unit/test_style_anchor.py -k "not network and not slow"
```
Expected: new tests PASS, no regressions.

- [ ] **Step 4.6 — Commit**

```bash
git add src/pipeline/composer/image.py src/pipeline/composer/base.py tests/unit/test_image_style.py
git commit -m "feat(image): style_prefix + seed + anchor_image slot; production tier with anchor active"
```

---

## Task 5: Modify `DirectStage` — clip budget + intro template

**Files:**
- Modify: `src/pipeline/stages/direct.py`
- Create: `tests/unit/test_direct_clip_budget.py`

- [ ] **Step 5.1 — Write failing tests**

```python
# tests/unit/test_direct_clip_budget.py
from pipeline.stages.direct import build_direct_prompt, _intro_template_block, _validate_clip_budget
from pipeline.niche_templates import NicheTemplate
from pipeline.knowledge import Knowledge


def _minimal_knowledge() -> Knowledge:
    from pipeline.knowledge import Fact
    return Knowledge(facts=[Fact(id="f1", text="test fact", tags=[], source="test")])


def test_clip_budget_instruction_in_prompt():
    k = _minimal_knowledge()
    prompt = build_direct_prompt(
        k, "zh-TW", clip_budget_text="VISUAL BUDGET: at most 12 of 20 scenes may be clip"
    )
    assert "VISUAL BUDGET" in prompt
    assert "12" in prompt


def test_intro_template_block_with_template():
    template = NicheTemplate(
        niche="parenting",
        intro_type="generated_image",
        intro_prompt_hint="parent and child, sketch style",
        visual_style="clean sketch",
        anchor_prompt="...",
    )
    block = _intro_template_block(template)
    assert "s1" in block
    assert "generated_image" in block
    assert "clip" not in block.lower() or "never" in block.lower()
    assert "parent and child" in block


def test_intro_template_block_without_template():
    block = _intro_template_block(None)
    assert "s1" in block
    assert "clip" not in block or "must not" in block.lower()


def test_intro_block_in_prompt():
    k = _minimal_knowledge()
    template = NicheTemplate("parenting", "generated_image", "sketch hint", "clean sketch", "...")
    prompt = build_direct_prompt(
        k, "zh-TW",
        intro_template_text=_intro_template_block(template),
    )
    assert "s1" in prompt
    assert "sketch hint" in prompt


def test_validate_clip_budget_returns_warnings():
    scenes = [{"visual": {"type": "clip"}} for _ in range(18)] + \
             [{"visual": {"type": "generated_image"}} for _ in range(2)]
    warnings = _validate_clip_budget(scenes, max_pct=0.60)
    assert warnings
    assert "18" in warnings[0]


def test_validate_clip_budget_ok():
    scenes = [{"visual": {"type": "clip"}} for _ in range(10)] + \
             [{"visual": {"type": "generated_image"}} for _ in range(10)]
    assert _validate_clip_budget(scenes, max_pct=0.60) == []
```

- [ ] **Step 5.2 — Run tests to confirm failure**

```bash
uv run pytest tests/unit/test_direct_clip_budget.py -v
```
Expected: `ImportError: cannot import name '_intro_template_block'`

- [ ] **Step 5.3 — Add helpers to `src/pipeline/stages/direct.py`**

Add these two functions after `LOCALE_INSTRUCTIONS`:

```python
def _intro_template_block(template) -> str:
    """Build the s1 constraint block for the Claude prompt."""
    if template is None:
        return (
            "INTRO CONSTRAINT (Scene s1):\n"
            "- s1 must NOT use type 'clip' or 'still_frame' from source.\n"
            "- Use 'generated_image', 'text_card', or 'slide' for s1.\n"
            "- No niche intro template found; choose a visually original opening."
        )
    return (
        f"INTRO CONSTRAINT (Scene s1 — niche: {template.niche}):\n"
        f"- s1 MUST use visual type '{template.intro_type}'.\n"
        f"- Never use 'clip' or 'still_frame' for s1.\n"
        f"- Prompt hint for s1: {template.intro_prompt_hint}"
    )


def _validate_clip_budget(scenes: list[dict], max_pct: float = 0.60) -> list[str]:
    """Return list of warning strings if clip budget is exceeded."""
    source_types = {"clip", "still_frame"}
    clip_count = sum(
        1 for s in scenes
        if (s.get("visual") or {}).get("type") in source_types
    )
    max_clips = int(len(scenes) * max_pct)
    if clip_count > max_clips:
        return [
            f"Clip budget warning: {clip_count}/{len(scenes)} scenes use source clips "
            f"(soft limit: {max_clips} at {int(max_pct*100)}%)."
        ]
    return []
```

- [ ] **Step 5.4 — Extend `build_direct_prompt` signature**

Add two new keyword-only parameters to `build_direct_prompt`:

```python
def build_direct_prompt(
    knowledge: Knowledge,
    locale: str,
    fmt: str = "standard",
    tone: str = "dramatic",
    strategies_text: str = "",
    reference_storyboard_json: str | None = None,
    constraints_text: str = "",
    clip_budget_text: str = "",        # NEW
    intro_template_text: str = "",     # NEW
) -> str:
```

In the function body, add a `constraints_block` that combines all constraint strings, and inject it into the prompt before `{visual_note}`:

```python
    constraints_parts = []
    if constraints_text:
        constraints_parts.append(constraints_text)
    if clip_budget_text:
        constraints_parts.append(clip_budget_text)
    if intro_template_text:
        constraints_parts.append(intro_template_text)
    constraints_block = "\n\n".join(constraints_parts)
    constraints_section = f"\n{constraints_block}\n" if constraints_block else ""
```

Then in the returned f-string, add `{constraints_section}` just before `{visual_note}`:

```python
    return f"""You are a video director. Create a scene-by-scene storyboard \
from the knowledge below.
This is NOT a translation — it is a cultural adaptation creating ORIGINAL content.

LOCALE: {locale}
LANGUAGE: {locale_instruction}
TONE: {tone}
{strategies_block}{reference_block}
{structure}
{constraints_section}
{visual_note}
...rest unchanged...
```

- [ ] **Step 5.5 — Wire clip budget + intro template into `DirectStage.run()`**

In `DirectStage.run()`, after loading constraints (around line 409), add:

```python
        from pipeline.niche_templates import load_niche_template
        # _intro_template_block and _validate_clip_budget are module-level in this same file —
        # call them directly, no import needed.

        # Clip budget — use format-based scene count estimate (avoids hardcoding 20)
        clip_budget_text = ""
        if constraints:
            # standard format targets 15-25 scenes; short format targets 2-4 scenes
            estimated_count = 4 if self.fmt == "short" else 20
            clip_budget_text = constraints.clip_budget_instruction(scene_count=estimated_count)

        # Intro template
        niche_template = None
        if ctx.niche and ctx.niche != "none":
            niche_template = load_niche_template(ctx.niche)
        intro_template_text = _intro_template_block(niche_template)
```

And update the `build_direct_prompt` call:

```python
        prompt = build_direct_prompt(
            knowledge, ctx.locale, self.fmt, self.tone,
            strategies_text=strategies_text,
            reference_storyboard_json=reference_storyboard_json,
            constraints_text=constraints_text,
            clip_budget_text=clip_budget_text,
            intro_template_text=intro_template_text,
        )
```

After `storyboard = Storyboard.from_dict(...)`, add clip budget validation:

```python
        # Validate clip budget (soft warning — never blocks)
        scene_dicts = [s.to_dict() for s in storyboard.scenes]
        max_pct = constraints.max_source_clip_pct if constraints else 0.60
        budget_warnings = _validate_clip_budget(scene_dicts, max_pct)
        for w in budget_warnings:
            logger.warning("direct.clip_budget", warning=w)

        # Validate s1 intro constraint
        if storyboard.scenes:
            s1_type = storyboard.scenes[0].visual.get("type", "")
            if s1_type in ("clip", "still_frame"):
                logger.warning(
                    "direct.intro_constraint_violated",
                    scene="s1",
                    visual_type=s1_type,
                    hint="Claude ignored intro constraint — edit s1 visual manually or rescene",
                )
```

- [ ] **Step 5.6 — Run tests**

```bash
uv run pytest tests/unit/test_direct_clip_budget.py -v
uv run pytest tests/unit/ -k "not network and not slow" -v
```
Expected: all tests PASS.

- [ ] **Step 5.7 — Commit**

```bash
git add src/pipeline/stages/direct.py tests/unit/test_direct_clip_budget.py
git commit -m "feat(direct): inject clip budget + per-niche intro template constraint into storyboard prompt"
```

---

## Task 6: Modify `ComposeStage` — StyleAnchorExtractor + duplicate frame guard

**Files:**
- Modify: `src/pipeline/stages/compose.py`
- Create: `tests/unit/test_compose_dup_guard.py`

- [ ] **Step 6.1 — Write failing tests**

```python
# tests/unit/test_compose_dup_guard.py
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest


def test_extract_thumbnail_called_for_clip(tmp_path):
    """Verify a thumbnail is extracted for clip-type scenes."""
    from pipeline.stages.compose import _extract_clip_thumbnail

    fake_source = tmp_path / "source.mp4"
    fake_source.write_bytes(b"fake")

    with patch("pipeline.stages.compose.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        _extract_clip_thumbnail(fake_source, timestamp=30.0, out_path=tmp_path / "thumb.jpg")
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert "ffmpeg" in args
    assert "30.0" in " ".join(str(a) for a in args)


def test_is_duplicate_detects_same_hash():
    import imagehash
    from pipeline.stages.compose import _is_duplicate_frame

    # Same hash twice
    h = imagehash.hex_to_hash("0" * 16)
    seen = {h}
    assert _is_duplicate_frame(h, seen) is True


def test_is_duplicate_allows_unique_hash():
    import imagehash
    from pipeline.stages.compose import _is_duplicate_frame

    h1 = imagehash.hex_to_hash("0" * 16)
    h2 = imagehash.hex_to_hash("f" * 16)
    seen = {h1}
    assert _is_duplicate_frame(h2, seen) is False


def test_duplicate_guard_replaces_scene_visual(tmp_path):
    """When two clip scenes share the same frame, second is replaced with generated_image."""
    from pipeline.stages.compose import _apply_duplicate_guard

    fake_source = tmp_path / "source.mp4"
    fake_source.write_bytes(b"fake")

    scene_clip_a = {"id": "s1", "visual": {"type": "clip", "start_sec": 10}}
    scene_clip_b = {"id": "s8", "visual": {"type": "clip", "start_sec": 20}, "narration": "test narr"}
    scene_generated = {"id": "s2", "visual": {"type": "generated_image", "prompt": "test"}}

    import imagehash
    # Both clips produce the same hash
    same_hash = imagehash.hex_to_hash("0" * 16)
    seen: set = set()

    def fake_thumbnail(source, timestamp, out_path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"fake")

    def fake_phash(img_path):
        return same_hash

    with patch("pipeline.stages.compose._extract_clip_thumbnail", side_effect=fake_thumbnail), \
         patch("pipeline.stages.compose._phash_image", return_value=same_hash):
        result_a, seen = _apply_duplicate_guard(scene_clip_a, fake_source, seen, style_descriptor="sketch")
        result_b, seen = _apply_duplicate_guard(scene_clip_b, fake_source, seen, style_descriptor="sketch")

    assert result_a["visual"]["type"] == "clip"        # first clip: kept
    assert result_b["visual"]["type"] == "generated_image"  # duplicate: replaced
    assert "sketch" in result_b["visual"]["prompt"]
    assert result_a is scene_clip_a  # not mutated

def test_non_clip_scene_passes_through(tmp_path):
    from pipeline.stages.compose import _apply_duplicate_guard
    scene = {"id": "s2", "visual": {"type": "generated_image", "prompt": "test"}}
    result, seen = _apply_duplicate_guard(scene, None, set(), style_descriptor="")
    assert result is scene
    assert seen == set()
```

- [ ] **Step 6.2 — Run tests to confirm failure**

```bash
uv run pytest tests/unit/test_compose_dup_guard.py -v
```
Expected: `ImportError: cannot import name '_apply_duplicate_guard'`

**Note:** `_apply_duplicate_guard` extracts a thumbnail via ffmpeg for each clip scene, then `render_clip` extracts the full clip separately. This is ~2× ffmpeg work per clip scene (~0.5s overhead per scene on a 20-scene video — acceptable). No optimization needed.

- [ ] **Step 6.3 — Add helper functions to `src/pipeline/stages/compose.py`**

Add these imports at the top of `compose.py`:

```python
import subprocess  # already present
from typing import Any  # add if not present
```

Add these helper functions after `_get_duration_sec`:

```python
def _extract_clip_thumbnail(source: Path, timestamp: float, out_path: Path) -> None:
    """Extract one frame from *source* at *timestamp* seconds."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-ss", str(timestamp), "-i", str(source),
         "-vframes", "1", "-q:v", "5", str(out_path), "-y"],
        check=True, capture_output=True,
    )


def _phash_image(img_path: Path):
    """Return perceptual hash of *img_path*. Requires imagehash + Pillow."""
    import imagehash
    from PIL import Image
    return imagehash.phash(Image.open(img_path))


def _is_duplicate_frame(new_hash, seen_hashes: set, threshold: int = 8) -> bool:
    return any(new_hash - h <= threshold for h in seen_hashes)


def _apply_duplicate_guard(
    scene: dict[str, Any],
    source_video: Path | None,
    seen_hashes: set,
    style_descriptor: str,
) -> tuple[dict[str, Any], set]:
    """Check if *scene* is a duplicate clip. Return (possibly-replaced scene, updated seen_hashes)."""
    visual = scene.get("visual", {})
    if visual.get("type") not in ("clip", "still_frame"):
        return scene, seen_hashes
    if source_video is None or not source_video.exists():
        return scene, seen_hashes

    timestamp = float(visual.get("start_sec", visual.get("timestamp_sec", 0)))
    thumb = source_video.parent / f"_thumb_{scene.get('id', 'x')}.jpg"

    try:
        _extract_clip_thumbnail(source_video, timestamp, thumb)
        new_hash = _phash_image(thumb)
    except Exception as exc:
        logger.warning("compose.dup_guard.thumbnail_failed", scene=scene.get("id"), error=str(exc))
        return scene, seen_hashes
    finally:
        if thumb.exists():
            thumb.unlink(missing_ok=True)

    if _is_duplicate_frame(new_hash, seen_hashes):
        logger.warning(
            "compose.clip.duplicate_detected",
            scene=scene.get("id"),
            replaced_with="generated_image",
        )
        narration = scene.get("narration", "")
        replacement_prompt = f"{style_descriptor}, {narration[:80]}".strip(", ")
        replaced = {
            **scene,
            "visual": {"type": "generated_image", "prompt": replacement_prompt},
        }
        return replaced, seen_hashes  # don't add duplicate hash to seen
    else:
        seen_hashes = seen_hashes | {new_hash}
        return scene, seen_hashes
```

- [ ] **Step 6.4 — Wire `extract_style_anchor` and duplicate guard into `_compose_from_storyboard`**

In `ComposeStage._compose_from_storyboard`, add before the scene loop:

```python
        # --- Style anchor extraction ---
        from pipeline.composer.style_anchor import extract_style_anchor
        from pipeline.niche_templates import load_niche_template

        niche = ctx.niche if ctx.niche and ctx.niche != "none" else None
        niche_template = load_niche_template(niche) if niche else None
        style_anchor = extract_style_anchor(
            project_id=str(ctx.project_id),
            niche=niche,
            template=niche_template,
            source_video=ctx.video_path,
            work_dir=compose_dir,
        )
        # Persist suitability to context for DirectStage re-runs
        if style_anchor.suitability:
            from pipeline.constraints import ProjectConstraints
            c = ProjectConstraints.load(ctx.work_dir) or ProjectConstraints()
            if c.source_suitability != style_anchor.suitability:
                c.source_suitability = style_anchor.suitability
                c.save(ctx.work_dir)

        # Inject style anchor data into theme dict (flows to render_scene → image.py)
        theme_dict["style_prefix"] = style_anchor.style_descriptor
        theme_dict["_seed"] = style_anchor.seed
        if style_anchor.anchor_image:
            theme_dict["_anchor_image"] = str(style_anchor.anchor_image)

        # --- Duplicate frame guard state ---
        seen_clip_hashes: set = set()
```

Then, in the scene loop, wrap the `render_scene` call with the duplicate guard. Find the `visual_path = render_scene(...)` call and replace it:

```python
                # Apply duplicate frame guard for clip/still_frame scenes
                scene_dict_guarded, seen_clip_hashes = _apply_duplicate_guard(
                    scene_dict,
                    ctx.video_path,
                    seen_clip_hashes,
                    style_descriptor=style_anchor.style_descriptor,
                )

                # Step 1: Render visual
                try:
                    visual_path = render_scene(
                        scene_dict_guarded,   # <- use guarded (possibly replaced) scene
                        duration,
                        storyboard.aspect_ratio,
                        scenes_dir,
                        source_video=ctx.video_path,
                        theme=theme_dict,
                    )
```

- [ ] **Step 6.5 — Run tests**

```bash
uv run pytest tests/unit/test_compose_dup_guard.py -v
uv run pytest tests/unit/ -k "not network and not slow" -v
```
Expected: all tests PASS.

- [ ] **Step 6.6 — Run lint check**

```bash
uv run ruff check src/pipeline/stages/compose.py src/pipeline/stages/direct.py \
  src/pipeline/composer/style_anchor.py src/pipeline/composer/image.py \
  src/pipeline/composer/base.py src/pipeline/niche_templates.py
```
Fix any issues before committing.

- [ ] **Step 6.7 — Commit**

```bash
git add src/pipeline/stages/compose.py tests/unit/test_compose_dup_guard.py
git commit -m "feat(compose): integrate StyleAnchorExtractor + duplicate clip frame guard"
```

---

## Task 7: Smoke test on project 1777161293

This task verifies the full system works end-to-end on the existing project without a full re-produce.

- [ ] **Step 7.1 — Verify niche templates load correctly**

```bash
uv run python3 -c "
from pipeline.niche_templates import load_niche_template
t = load_niche_template('parenting')
print('Template:', t)
print('Intro type:', t.intro_type)
print('Style:', t.visual_style[:60])
"
```
Expected: prints parenting template fields.

- [ ] **Step 7.2 — Verify style anchor on project source video**

```bash
uv run python3 -c "
from pathlib import Path
from pipeline.composer.style_anchor import extract_style_anchor
from pipeline.niche_templates import load_niche_template
template = load_niche_template('parenting')
result = extract_style_anchor(
    project_id='1777161293',
    niche='parenting',
    template=template,
    source_video=Path('output/projects/1777161293/source/source_video.mp4'),
    work_dir=Path('/tmp/anchor_test'),
)
print('Suitability:', result.suitability)
print('Style:', result.style_descriptor)
print('Seed:', result.seed)
print('Anchor:', result.anchor_image)
"
```
Expected: prints suitability (likely "low" — parenting illustration video), style descriptor, 9-digit seed, anchor path.

- [ ] **Step 7.3 — Check that s1 clip budget warning would fire**

```bash
uv run python3 -c "
from pipeline.stages.direct import _validate_clip_budget
import json
sb = json.load(open('output/projects/1777161293/storyboard.json'))
scenes = sb['scenes']
warnings = _validate_clip_budget(scenes)
print('Warnings:', warnings)
s1 = scenes[0]
print('s1 type:', s1['visual']['type'])  # should be 'clip' — confirm constraint was violated
"
```
Expected: warnings list and confirms s1 is currently `clip` (the problem we're fixing on re-direct).

- [ ] **Step 7.4 — Run full test suite**

```bash
uv run pytest tests/unit/ -v -k "not network and not slow"
```
Expected: all unit tests PASS.

- [ ] **Step 7.5 — Final commit**

```bash
git add -A
git commit -m "chore: run full test suite — visual consistency + clip budget system complete"
```

---

## Post-implementation: re-produce 1777161293

After the system is built and all tests pass, run these in order:

1. **Narration review** (run storytelling + proofreader subagents):
   ```bash
   uv run pipeline proofread run --project-id 1777161293
   ```

2. **Re-direct** (new storyboard with clip budget + intro template):
   ```bash
   uv run pipeline produce --project-id 1777161293 --url https://www.youtube.com/watch?v=XFcFPzQizvM --start-from direct
   ```

3. **Review the new storyboard** — confirm s1 is not a clip, clip count is ≤ 12/19.

4. **Re-compose** (style anchor + duplicate guard active):
   ```bash
   uv run pipeline compose reburn --project-id 1777161293
   ```

5. **Preview** via dashboard and confirm visual consistency.
