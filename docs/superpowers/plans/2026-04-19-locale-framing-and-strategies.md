# Locale-framing Promotional Strategies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable reusable promotional strategy markdown files (first: locale source provenance) that are auto-loaded into `DirectStage`, produce title/description alongside the storyboard, support parallel-locale regeneration that preserves scene structure across languages, and reproduce `output/projects/1776356443` as a ja-JP video.

**Architecture:** Strategy `.md` files live under `configs/promo-strategies/`. A new loader module (`src/pipeline/strategies.py`) filters them by `applies_when` frontmatter predicates against `PipelineContext`, then injects matched strategies into the `DirectStage` Claude prompt. `PipelineContext` gains `source_locale` and `reference_storyboard_path`. `Storyboard` gains optional `title` and `description`. `DirectStage` writes to `storyboard_{locale}.json`, accepts a reference storyboard for parallel-locale generation, and parses title/description from Claude's JSON response.

**Tech Stack:** Python 3.12, Typer CLI, Anthropic SDK, PyYAML (new dep), pytest, structlog, pydantic-settings. Edge-TTS for narration (ja voice `ja-JP-NanamiNeural`). Existing FFmpeg compose.

**Reference spec:** `docs/superpowers/specs/2026-04-19-locale-framing-and-strategies-design.md`.

---

### Task 1: Add PyYAML dependency

**Files:**
- Modify: `pyproject.toml` (dependencies block, lines 6-22)
- Side effect: regenerates `uv.lock`

- [ ] **Step 1: Add `pyyaml` to `dependencies`**

Edit `pyproject.toml`, append `"pyyaml>=6.0"` to the `dependencies` list:

```toml
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
    "trafilatura>=2.0",
    "httpx>=0.28",
    "openai>=2.30.0",
    "google-genai>=0.3.0",
    "pillow>=12.2.0",
    "selectolax>=0.3.21",
    "pyyaml>=6.0",
]
```

- [ ] **Step 2: Sync and verify**

Run: `uv sync`
Expected: resolves and installs `pyyaml`. Then `uv run python -c "import yaml; print(yaml.__version__)"` prints a version string.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add pyyaml dependency for strategy-file frontmatter"
```

---

### Task 2: Add `source_locale` and `reference_storyboard_path` to `PipelineContext`

**Files:**
- Modify: `src/pipeline/stages/base.py` (PipelineContext dataclass, path_fields set)
- Test: `tests/unit/test_base.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_base.py`:

```python
def test_context_roundtrips_source_locale_and_reference_storyboard(tmp_path):
    ctx = PipelineContext(
        project_id=1,
        source_url="original",
        locale="ja",
        work_dir=tmp_path,
        source_locale="US",
        reference_storyboard_path=tmp_path / "storyboard_en.json",
    )

    round = PipelineContext.from_dict(ctx.to_dict())

    assert round.source_locale == "US"
    assert round.reference_storyboard_path == tmp_path / "storyboard_en.json"
```

If `test_base.py` does not already import `PipelineContext`, add:

```python
from pathlib import Path
from pipeline.stages.base import PipelineContext
```

- [ ] **Step 2: Run the test, confirm it fails**

Run: `uv run pytest tests/unit/test_base.py::test_context_roundtrips_source_locale_and_reference_storyboard -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'source_locale'`.

- [ ] **Step 3: Add the fields to `PipelineContext`**

In `src/pipeline/stages/base.py`, inside the `@dataclass` block after `youtube_video_id: str | None = None`:

```python
    # Locale framing (optional, set manually or by analyze stage)
    source_locale: str | None = None
    reference_storyboard_path: Path | None = None
```

And extend `path_fields` in `from_dict`:

```python
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
```

- [ ] **Step 4: Run the test, confirm it passes**

Run: `uv run pytest tests/unit/test_base.py -v`
Expected: PASS (new test plus any existing tests in that file).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/stages/base.py tests/unit/test_base.py
git commit -m "feat(pipeline): add source_locale and reference_storyboard_path to context"
```

---

### Task 3: Add optional `title` and `description` to `Storyboard`

**Files:**
- Modify: `src/pipeline/storyboard.py` (Storyboard dataclass, to_dict, from_dict)
- Test: `tests/unit/test_storyboard.py` (create if absent)

- [ ] **Step 1: Write the failing test**

Create or extend `tests/unit/test_storyboard.py`:

```python
from pipeline.storyboard import Storyboard


def test_storyboard_roundtrips_title_and_description():
    sb = Storyboard.from_dict({
        "version": 1,
        "format": "standard",
        "target_duration_sec": 720,
        "aspect_ratio": "16:9",
        "title": "アメリカの大学研究：子供の癇癪",
        "description": "ブリガム・ヤング大学の研究者による2021年の研究…",
        "scenes": [],
    })

    assert sb.title == "アメリカの大学研究：子供の癇癪"
    assert sb.description.startswith("ブリガム・ヤング大学")

    data = sb.to_dict()
    assert data["title"] == sb.title
    assert data["description"] == sb.description


def test_storyboard_without_title_description_roundtrips():
    sb = Storyboard.from_dict({
        "version": 1,
        "format": "standard",
        "target_duration_sec": 720,
        "aspect_ratio": "16:9",
        "scenes": [],
    })

    assert sb.title is None
    assert sb.description is None
    data = sb.to_dict()
    # Absent fields should NOT be emitted when None (to keep existing files stable)
    assert "title" not in data
    assert "description" not in data
```

- [ ] **Step 2: Run the test, confirm it fails**

Run: `uv run pytest tests/unit/test_storyboard.py -v`
Expected: FAIL — `AttributeError: 'Storyboard' object has no attribute 'title'`.

- [ ] **Step 3: Implement**

In `src/pipeline/storyboard.py`, update the `Storyboard` dataclass:

```python
@dataclass
class Storyboard:
    """Layer 2: Scene-by-scene directing. Regenerable, A/B testable."""

    version: int = 1
    format: str = "standard"
    target_duration_sec: int = 720
    aspect_ratio: str = "16:9"
    scenes: list[Scene] = field(default_factory=list)
    theme: Theme = field(default_factory=Theme)
    title: str | None = None
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "version": self.version,
            "format": self.format,
            "target_duration_sec": self.target_duration_sec,
            "aspect_ratio": self.aspect_ratio,
            "theme": self.theme.to_dict(),
            "scenes": [s.to_dict() for s in self.scenes],
        }
        if self.title is not None:
            out["title"] = self.title
        if self.description is not None:
            out["description"] = self.description
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Storyboard:
        scenes = [Scene.from_dict(s) for s in data.get("scenes", [])]
        theme_data = data.get("theme", {})
        theme = Theme.from_dict(theme_data) if theme_data else Theme()
        return cls(
            version=data.get("version", 1),
            format=data.get("format", "standard"),
            target_duration_sec=data.get("target_duration_sec", 720),
            aspect_ratio=data.get("aspect_ratio", "16:9"),
            scenes=scenes,
            theme=theme,
            title=data.get("title"),
            description=data.get("description"),
        )
```

- [ ] **Step 4: Run the test, confirm it passes**

Run: `uv run pytest tests/unit/test_storyboard.py -v`
Expected: PASS.

- [ ] **Step 5: Run wider test suite to ensure no regressions**

Run: `uv run pytest -m "not slow and not network and not integration" -x`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/storyboard.py tests/unit/test_storyboard.py
git commit -m "feat(storyboard): add optional title and description fields"
```

---

### Task 4: Strategy loader skeleton + `always` and `target_locale_differs_from_source` predicates

**Files:**
- Create: `src/pipeline/strategies.py`
- Create: `tests/unit/test_strategies.py`
- Create: `tests/fixtures/promo_strategies/always.md`
- Create: `tests/fixtures/promo_strategies/locale_differs.md`

- [ ] **Step 1: Create test fixtures**

Create `tests/fixtures/promo_strategies/always.md`:

```markdown
---
name: always-strategy
description: Always applied, used to verify loader
applies_when:
  always: true
---

Always-on strategy body.
```

Create `tests/fixtures/promo_strategies/locale_differs.md`:

```markdown
---
name: locale-differs-strategy
description: Applied only when target differs from source
applies_when:
  target_locale_differs_from_source: true
---

Locale-differs strategy body.
```

- [ ] **Step 2: Write failing tests**

Create `tests/unit/test_strategies.py`:

```python
from pathlib import Path

import pytest

from pipeline.stages.base import PipelineContext
from pipeline.strategies import load_strategies

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "promo_strategies"


def _ctx(tmp_path, **kwargs) -> PipelineContext:
    return PipelineContext(
        project_id=1,
        source_url="original",
        locale=kwargs.pop("locale", "ja"),
        work_dir=tmp_path,
        **kwargs,
    )


def test_load_strategies_returns_empty_when_dir_missing(tmp_path):
    ctx = _ctx(tmp_path)
    out = load_strategies(ctx, strategies_dir=tmp_path / "does_not_exist")
    assert out == ""


def test_always_strategy_always_loads(tmp_path):
    ctx = _ctx(tmp_path, source_locale=None)
    out = load_strategies(ctx, strategies_dir=FIXTURE_DIR)
    assert "Always-on strategy body." in out
    assert "always-strategy" in out  # name appears in heading


def test_locale_differs_strategy_loads_when_locales_differ(tmp_path):
    ctx = _ctx(tmp_path, locale="ja", source_locale="US")
    out = load_strategies(ctx, strategies_dir=FIXTURE_DIR)
    assert "Locale-differs strategy body." in out


def test_locale_differs_strategy_skipped_when_source_locale_is_none(tmp_path):
    ctx = _ctx(tmp_path, locale="ja", source_locale=None)
    out = load_strategies(ctx, strategies_dir=FIXTURE_DIR)
    assert "Locale-differs strategy body." not in out


def test_locale_differs_strategy_skipped_when_locales_match(tmp_path):
    ctx = _ctx(tmp_path, locale="en", source_locale="en")
    out = load_strategies(ctx, strategies_dir=FIXTURE_DIR)
    assert "Locale-differs strategy body." not in out
```

- [ ] **Step 3: Confirm tests fail**

Run: `uv run pytest tests/unit/test_strategies.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.strategies'`.

- [ ] **Step 4: Implement the loader**

Create `src/pipeline/strategies.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import structlog
import yaml

from pipeline.stages.base import PipelineContext

logger = structlog.get_logger()

DEFAULT_STRATEGIES_DIR = Path("configs/promo-strategies")


def _predicate_always(_ctx: PipelineContext, value: Any) -> bool:
    return bool(value)


def _predicate_target_locale_differs_from_source(ctx: PipelineContext, value: Any) -> bool:
    if not bool(value):
        return True  # predicate with value: false means "skip this check"
    if ctx.source_locale is None:
        return False
    return ctx.locale != ctx.source_locale


PREDICATES: dict[str, Callable[[PipelineContext, Any], bool]] = {
    "always": _predicate_always,
    "target_locale_differs_from_source": _predicate_target_locale_differs_from_source,
}


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str] | None:
    """Return (frontmatter_dict, body) or None if malformed / missing."""
    if not text.startswith("---"):
        return None
    try:
        end = text.index("\n---", 3)
    except ValueError:
        return None
    raw = text[3:end].strip()
    body_start = end + len("\n---")
    # Consume a trailing newline after closing ---
    if body_start < len(text) and text[body_start] == "\n":
        body_start += 1
    body = text[body_start:]
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    return data, body


def _applies(ctx: PipelineContext, applies_when: dict[str, Any]) -> bool:
    for key, value in applies_when.items():
        predicate = PREDICATES.get(key)
        if predicate is None:
            logger.warning("strategies.unknown_predicate", key=key)
            return False
        if not predicate(ctx, value):
            return False
    return True


def load_strategies(
    ctx: PipelineContext, strategies_dir: Path | None = None
) -> str:
    """Load all strategy .md files whose applies_when matches ctx.

    Returns a single string ready to inject into a prompt, or empty string
    if no strategies apply / the directory is missing.
    """
    directory = strategies_dir if strategies_dir is not None else DEFAULT_STRATEGIES_DIR
    if not directory.exists() or not directory.is_dir():
        logger.debug("strategies.dir_missing", path=str(directory))
        return ""

    sections: list[str] = []
    for path in sorted(directory.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        parsed = _parse_frontmatter(text)
        if parsed is None:
            logger.warning("strategies.malformed_frontmatter", path=str(path))
            continue
        fm, body = parsed
        name = fm.get("name", path.stem)
        description = fm.get("description", "")
        applies_when = fm.get("applies_when") or {}
        if not isinstance(applies_when, dict):
            logger.warning("strategies.invalid_applies_when", path=str(path))
            continue
        if not _applies(ctx, applies_when):
            continue
        sections.append(f"### {name} — {description}\n{body.strip()}")

    if not sections:
        return ""
    header = "LOADED STRATEGIES (apply these when writing narration, title, and description):\n\n"
    return header + "\n\n".join(sections) + "\n"
```

- [ ] **Step 5: Run tests, confirm pass**

Run: `uv run pytest tests/unit/test_strategies.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/strategies.py tests/unit/test_strategies.py tests/fixtures/promo_strategies/
git commit -m "feat(pipeline): strategy loader with always and locale-differs predicates"
```

---

### Task 5: Add `target_locale_in` / `source_locale_in` predicates and malformed-file handling

**Files:**
- Modify: `src/pipeline/strategies.py` (PREDICATES)
- Modify: `tests/unit/test_strategies.py`
- Create: `tests/fixtures/promo_strategies/target_in_ja.md`
- Create: `tests/fixtures/promo_strategies/malformed.md`

- [ ] **Step 1: Add fixtures**

Create `tests/fixtures/promo_strategies/target_in_ja.md`:

```markdown
---
name: ja-only-strategy
description: Applied only when target locale is ja
applies_when:
  target_locale_in: ["ja"]
---

JA-only strategy body.
```

Create `tests/fixtures/promo_strategies/malformed.md`:

```markdown
---
name: malformed
description: missing closing delimiter
applies_when:
  always: true
no closing dashes here

Body never reached.
```

- [ ] **Step 2: Extend failing tests**

Append to `tests/unit/test_strategies.py`:

```python
def test_target_locale_in_matches(tmp_path):
    ctx = _ctx(tmp_path, locale="ja")
    out = load_strategies(ctx, strategies_dir=FIXTURE_DIR)
    assert "JA-only strategy body." in out


def test_target_locale_in_does_not_match(tmp_path):
    ctx = _ctx(tmp_path, locale="zh-TW")
    out = load_strategies(ctx, strategies_dir=FIXTURE_DIR)
    assert "JA-only strategy body." not in out


def test_malformed_file_skipped_without_crash(tmp_path, caplog):
    ctx = _ctx(tmp_path, locale="ja", source_locale="US")
    # Should not raise even though malformed.md is present in FIXTURE_DIR
    out = load_strategies(ctx, strategies_dir=FIXTURE_DIR)
    assert "Body never reached." not in out
```

- [ ] **Step 3: Run tests, confirm the `target_locale_in` ones fail**

Run: `uv run pytest tests/unit/test_strategies.py -v`
Expected: `test_target_locale_in_matches` FAILS because the predicate is unknown; `test_malformed_file_skipped_without_crash` may PASS already (loader warns on unknown predicate). Note exact failures.

- [ ] **Step 4: Implement predicates**

In `src/pipeline/strategies.py`, add two predicate functions above the `PREDICATES` table and register them:

```python
def _predicate_target_locale_in(ctx: PipelineContext, value: Any) -> bool:
    if not isinstance(value, list):
        return False
    return ctx.locale in value


def _predicate_source_locale_in(ctx: PipelineContext, value: Any) -> bool:
    if not isinstance(value, list) or ctx.source_locale is None:
        return False
    return ctx.source_locale in value


PREDICATES: dict[str, Callable[[PipelineContext, Any], bool]] = {
    "always": _predicate_always,
    "target_locale_differs_from_source": _predicate_target_locale_differs_from_source,
    "target_locale_in": _predicate_target_locale_in,
    "source_locale_in": _predicate_source_locale_in,
}
```

- [ ] **Step 5: Run tests, confirm pass**

Run: `uv run pytest tests/unit/test_strategies.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/strategies.py tests/unit/test_strategies.py tests/fixtures/promo_strategies/
git commit -m "feat(pipeline): target_locale_in / source_locale_in predicates"
```

---

### Task 6: Create the first real strategy file

**Files:**
- Create: `configs/promo-strategies/locale-source-provenance.md`

- [ ] **Step 1: Create the directory and strategy file**

```bash
mkdir -p configs/promo-strategies
```

Create `configs/promo-strategies/locale-source-provenance.md`:

```markdown
---
name: locale-source-provenance
description: Frame source-material origin when target audience differs from source locale
applies_when:
  target_locale_differs_from_source: true
---

# Source Provenance Framing

When the target audience's locale differs from the locale where the research or source material originates, treat the source origin as an engagement hook rather than a background detail.

Apply these instructions:

1. **Name the origin in the HOOK scene.** The first scene's narration (or the second, if the first must be a pure teaser) should attribute the material to its region or institution. Examples:
   - "A study from Brigham Young University in the US found…"
   - "American researchers spent a decade investigating…"
   - "Canadian parents handle this differently."
2. **Tease the origin in the title.** The YouTube title should signal locale-distinct material. Examples:
   - `アメリカの大学研究：子供の癇癪と親の対応`
   - `美國大學研究：當孩子崩潰時，父母該怎麼做`
   - `Padres en EE. UU.: así enfrentan las pataletas`
3. **Bridge locale-specific assumptions.** Before finalizing, list any assumptions the source material makes that the target audience may not share (legal system, geography, policing or parenting norms, school structures, institution names). Address them inline in early scenes.

Keep attribution factual. Do not exaggerate credentials, generalize "US research" into "all Western research," or invent endorsements. If multiple origins are present, name the dominant one(s).
```

- [ ] **Step 2: Quick sanity check via the loader**

Run:
```bash
uv run python -c "
from pathlib import Path
from pipeline.stages.base import PipelineContext
from pipeline.strategies import load_strategies
ctx = PipelineContext(project_id=0, source_url='original', locale='ja', work_dir=Path('/tmp'), source_locale='US')
print(load_strategies(ctx))
"
```
Expected: stdout contains `Source Provenance Framing` and the three numbered instructions.

- [ ] **Step 3: Commit**

```bash
git add configs/promo-strategies/locale-source-provenance.md
git commit -m "feat(strategies): add locale-source-provenance strategy"
```

---

### Task 7: DirectStage — locale-suffixed storyboard output path

**Files:**
- Modify: `src/pipeline/stages/direct.py` (DirectStage.run, around line 258)
- Modify: `tests/unit/test_direct.py`

- [ ] **Step 1: Update the existing test expectation**

In `tests/unit/test_direct.py::test_direct_outputs_storyboard`, after the `ctx = await stage.run(sample_context)` line, append an assertion about the suffixed filename. The fixture context has `locale="zh-TW"`, so:

```python
    assert ctx.storyboard_path.name == "storyboard_zh-TW.json"
```

- [ ] **Step 2: Run the test, confirm it fails**

Run: `uv run pytest tests/unit/test_direct.py::test_direct_outputs_storyboard -v`
Expected: FAIL — `AssertionError: assert 'storyboard.json' == 'storyboard_zh-TW.json'`.

- [ ] **Step 3: Update DirectStage**

In `src/pipeline/stages/direct.py`, find:

```python
        storyboard_path = ctx.work_dir / "storyboard.json"
```

Replace with:

```python
        storyboard_path = ctx.work_dir / f"storyboard_{ctx.locale}.json"
```

- [ ] **Step 4: Run test, confirm pass**

Run: `uv run pytest tests/unit/test_direct.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/stages/direct.py tests/unit/test_direct.py
git commit -m "feat(direct): locale-suffixed storyboard output path"
```

---

### Task 8: DirectStage — inject loaded strategies into the prompt

**Files:**
- Modify: `src/pipeline/stages/direct.py` (build_direct_prompt signature + body, DirectStage.run)
- Modify: `tests/unit/test_direct.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_direct.py`:

```python
from pathlib import Path as _Path


def test_build_direct_prompt_includes_strategies(sample_knowledge):
    strategies_text = "LOADED STRATEGIES\n\n### test — desc\nHello strategy"
    prompt = build_direct_prompt(
        sample_knowledge, "ja", "standard", "dramatic",
        strategies_text=strategies_text,
    )
    assert "LOADED STRATEGIES" in prompt
    assert "Hello strategy" in prompt


def test_build_direct_prompt_omits_strategies_when_empty(sample_knowledge):
    prompt = build_direct_prompt(
        sample_knowledge, "ja", "standard", "dramatic",
        strategies_text="",
    )
    assert "LOADED STRATEGIES" not in prompt


async def test_direct_stage_loads_and_injects_strategies(
    sample_context, direct_fixture, tmp_path, monkeypatch
):
    # Minimal knowledge
    kb = _Path(__file__).parent.parent / "fixtures" / "sample_knowledge.json"
    (sample_context.work_dir / "knowledge.json").write_text(kb.read_text())
    sample_context.knowledge_path = sample_context.work_dir / "knowledge.json"
    sample_context.locale = "ja"
    sample_context.source_locale = "US"

    strat_dir = tmp_path / "promos"
    strat_dir.mkdir()
    (strat_dir / "t.md").write_text(
        "---\n"
        "name: test-strat\n"
        "description: test strat desc\n"
        "applies_when:\n"
        "  target_locale_differs_from_source: true\n"
        "---\n"
        "Body of strategy visible in prompt.\n"
    )

    # Patch the DEFAULT_STRATEGIES_DIR used by DirectStage
    import pipeline.strategies as strategies_mod
    monkeypatch.setattr(strategies_mod, "DEFAULT_STRATEGIES_DIR", strat_dir)

    stage = DirectStage()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(direct_fixture))]
    captured = {}

    with patch("pipeline.stages.direct.get_anthropic_client") as mock_client_fn:
        mock_client = MagicMock()

        def _create(**kwargs):
            captured["messages"] = kwargs["messages"]
            return mock_response

        mock_client.messages.create.side_effect = _create
        mock_client_fn.return_value = mock_client
        await stage.run(sample_context)

    prompt_text = captured["messages"][0]["content"]
    assert "Body of strategy visible in prompt." in prompt_text
```

- [ ] **Step 2: Run tests, confirm failures**

Run: `uv run pytest tests/unit/test_direct.py -v`
Expected: the three new tests FAIL — `build_direct_prompt` does not accept `strategies_text`, and the stage does not call the loader yet.

- [ ] **Step 3: Update `build_direct_prompt`**

In `src/pipeline/stages/direct.py`, change the signature:

```python
def build_direct_prompt(
    knowledge: Knowledge,
    locale: str,
    fmt: str = "standard",
    tone: str = "dramatic",
    strategies_text: str = "",
    reference_storyboard_json: str | None = None,  # added for Task 9; default None here
) -> str:
```

At the top of the returned f-string, right after the `TONE: {tone}` line, insert a placeholder and a helper:

```python
    strategies_block = f"\n{strategies_text}\n" if strategies_text else ""
    reference_block = (
        f"\nREFERENCE STORYBOARD (preserve scene count, ids, facts_ref, visual, overlay; "
        f"rewrite only narration in target locale):\n```json\n{reference_storyboard_json}\n```\n"
        if reference_storyboard_json
        else ""
    )
```

Then splice both into the final prompt. The cleanest change:

```python
    return f"""You are a video director. Create a scene-by-scene storyboard \
from the knowledge below.
This is NOT a translation — it is a cultural adaptation creating ORIGINAL content.

LOCALE: {locale}
LANGUAGE: {locale_instruction}
TONE: {tone}
{strategies_block}{reference_block}
{structure}
```
…and leave the rest of the prompt unchanged.

- [ ] **Step 4: Update `DirectStage.run` to call the loader**

In `src/pipeline/stages/direct.py`, near the top of `run` just after `logger.info("direct.start", …)`:

```python
        from pipeline.strategies import load_strategies

        strategies_text = load_strategies(ctx)
```

Then pass it into `build_direct_prompt`:

```python
        prompt = build_direct_prompt(
            knowledge, ctx.locale, self.fmt, self.tone,
            strategies_text=strategies_text,
        )
```

- [ ] **Step 5: Run tests, confirm pass**

Run: `uv run pytest tests/unit/test_direct.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/stages/direct.py tests/unit/test_direct.py
git commit -m "feat(direct): inject loaded promo strategies into the prompt"
```

---

### Task 9: DirectStage — reference-storyboard parallel-locale mode

**Files:**
- Modify: `src/pipeline/stages/direct.py` (DirectStage.run)
- Modify: `tests/unit/test_direct.py`

- [ ] **Step 1: Write failing test**

Append to `tests/unit/test_direct.py`:

```python
async def test_direct_stage_injects_reference_storyboard(
    sample_context, direct_fixture, tmp_path
):
    kb = _Path(__file__).parent.parent / "fixtures" / "sample_knowledge.json"
    (sample_context.work_dir / "knowledge.json").write_text(kb.read_text())
    sample_context.knowledge_path = sample_context.work_dir / "knowledge.json"
    sample_context.locale = "ja"

    ref_path = sample_context.work_dir / "storyboard_en.json"
    ref_path.write_text(json.dumps({
        "version": 1,
        "format": "standard",
        "target_duration_sec": 720,
        "aspect_ratio": "16:9",
        "scenes": [
            {"id": "s1", "section": "hook", "narration": "English hook",
             "narration_est_sec": 5, "facts_ref": [], "visual": {"type": "clip"},
             "overlay": None, "pause_after_sec": 0}
        ],
    }))
    sample_context.reference_storyboard_path = ref_path

    stage = DirectStage()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(direct_fixture))]
    captured = {}

    with patch("pipeline.stages.direct.get_anthropic_client") as mock_client_fn:
        mock_client = MagicMock()

        def _create(**kwargs):
            captured["messages"] = kwargs["messages"]
            return mock_response

        mock_client.messages.create.side_effect = _create
        mock_client_fn.return_value = mock_client
        await stage.run(sample_context)

    prompt_text = captured["messages"][0]["content"]
    assert "REFERENCE STORYBOARD" in prompt_text
    assert "English hook" in prompt_text
```

- [ ] **Step 2: Run test, confirm failure**

Run: `uv run pytest tests/unit/test_direct.py::test_direct_stage_injects_reference_storyboard -v`
Expected: FAIL — `"REFERENCE STORYBOARD" not in prompt_text`.

- [ ] **Step 3: Implement reference-storyboard loading in DirectStage.run**

In `src/pipeline/stages/direct.py`, inside `run()` after the `strategies_text = load_strategies(ctx)` line:

```python
        reference_storyboard_json: str | None = None
        if ctx.reference_storyboard_path and ctx.reference_storyboard_path.exists():
            reference_storyboard_json = ctx.reference_storyboard_path.read_text(encoding="utf-8")
```

And pass into the prompt:

```python
        prompt = build_direct_prompt(
            knowledge, ctx.locale, self.fmt, self.tone,
            strategies_text=strategies_text,
            reference_storyboard_json=reference_storyboard_json,
        )
```

- [ ] **Step 4: Run test, confirm pass**

Run: `uv run pytest tests/unit/test_direct.py::test_direct_stage_injects_reference_storyboard -v`
Expected: PASS. Also run full `tests/unit/test_direct.py` to check nothing regressed.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/stages/direct.py tests/unit/test_direct.py
git commit -m "feat(direct): parallel-locale mode via reference storyboard injection"
```

---

### Task 10: DirectStage — emit and persist title + description

**Files:**
- Modify: `src/pipeline/stages/direct.py` (prompt JSON contract, DirectStage.run parsing)
- Modify: `tests/unit/test_direct.py`
- Modify: `tests/fixtures/sample_direct_response.json`

- [ ] **Step 1: Extend the fixture with title + description**

Edit `tests/fixtures/sample_direct_response.json`: add two top-level keys before `"scenes"`:

```json
{
  "title": "美國警匪追逐全記錄",
  "description": "芝加哥街頭的驚心動魄追捕——兩名搶劫嫌犯在車流中高速逃竄，差點撞上校車。\n\n這起真實案件揭示了美國執法者面臨的風險…",
  "scenes": [ ...existing scenes... ]
}
```

- [ ] **Step 2: Extend the existing test to assert title/description are persisted**

In `tests/unit/test_direct.py::test_direct_outputs_storyboard`, after the `sb = Storyboard.load(ctx.storyboard_path)` assertions, add:

```python
    assert sb.title == "美國警匪追逐全記錄"
    assert sb.description.startswith("芝加哥街頭")
```

Add a new test for missing title/description:

```python
async def test_direct_handles_missing_title_description(
    sample_context, direct_fixture
):
    kb = _Path(__file__).parent.parent / "fixtures" / "sample_knowledge.json"
    (sample_context.work_dir / "knowledge.json").write_text(kb.read_text())
    sample_context.knowledge_path = sample_context.work_dir / "knowledge.json"

    # Strip title/description from fixture
    response = dict(direct_fixture)
    response.pop("title", None)
    response.pop("description", None)

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(response))]

    with patch("pipeline.stages.direct.get_anthropic_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_client_fn.return_value = mock_client

        ctx = await DirectStage().run(sample_context)

    sb = Storyboard.load(ctx.storyboard_path)
    assert sb.title is None
    assert sb.description is None
```

- [ ] **Step 3: Run tests, confirm failures**

Run: `uv run pytest tests/unit/test_direct.py -v`
Expected: the title/description assertion FAILS; missing-fields test may PASS or FAIL depending on current parsing — note exact failure.

- [ ] **Step 4: Update the prompt contract**

In `src/pipeline/stages/direct.py::build_direct_prompt`, replace the JSON contract section:

```python
Return ONLY valid JSON:
{
  "title": "YouTube title in target locale, ~60 chars, applying loaded strategies",
  "description": "YouTube description in target locale, 2-3 paragraphs, crediting sources",
  "scenes": [
    ...same schema as before...
  ]
}
```

- [ ] **Step 5: Parse title/description in DirectStage.run**

In `src/pipeline/stages/direct.py`, after the `result = json.loads(raw_text)` line and before the `Storyboard.from_dict` call, update the storyboard construction:

```python
        storyboard = Storyboard.from_dict(
            {
                "version": 1,
                "format": self.fmt,
                "target_duration_sec": 60 if self.fmt == "short" else 720,
                "aspect_ratio": "9:16" if self.fmt == "short" else "16:9",
                "title": result.get("title"),
                "description": result.get("description"),
                **{k: v for k, v in result.items() if k not in ("title", "description")},
            }
        )
```

(The `**{...}` block passes through `scenes` etc. but excludes title/description which are now explicit.)

- [ ] **Step 6: Run tests, confirm pass**

Run: `uv run pytest tests/unit/test_direct.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/pipeline/stages/direct.py tests/unit/test_direct.py tests/fixtures/sample_direct_response.json
git commit -m "feat(direct): emit and persist title + description on storyboard"
```

---

### Task 11: DirectStage — warn on parallel-locale scene drift

**Files:**
- Modify: `src/pipeline/stages/direct.py`
- Modify: `tests/unit/test_direct.py`

- [ ] **Step 1: Write failing test**

Append to `tests/unit/test_direct.py`:

```python
async def test_direct_warns_on_scene_count_drift(
    sample_context, direct_fixture, tmp_path, caplog
):
    kb = _Path(__file__).parent.parent / "fixtures" / "sample_knowledge.json"
    (sample_context.work_dir / "knowledge.json").write_text(kb.read_text())
    sample_context.knowledge_path = sample_context.work_dir / "knowledge.json"

    # Reference has 2 scenes, response will have 4 (from direct_fixture)
    ref_path = sample_context.work_dir / "storyboard_en.json"
    ref_path.write_text(json.dumps({
        "version": 1, "format": "standard",
        "target_duration_sec": 720, "aspect_ratio": "16:9",
        "scenes": [
            {"id": "sX", "section": "hook", "narration": "x",
             "narration_est_sec": 1, "facts_ref": [], "visual": {}, "overlay": None,
             "pause_after_sec": 0},
            {"id": "sY", "section": "context", "narration": "y",
             "narration_est_sec": 1, "facts_ref": [], "visual": {}, "overlay": None,
             "pause_after_sec": 0},
        ],
    }))
    sample_context.reference_storyboard_path = ref_path

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(direct_fixture))]

    import logging
    caplog.set_level(logging.WARNING)

    with patch("pipeline.stages.direct.get_anthropic_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_client_fn.return_value = mock_client
        await DirectStage().run(sample_context)

    assert any("scene_drift" in rec.message or "scene_count_mismatch" in rec.message
               for rec in caplog.records)
```

- [ ] **Step 2: Run test, confirm failure**

Run: `uv run pytest tests/unit/test_direct.py::test_direct_warns_on_scene_count_drift -v`
Expected: FAIL — no such warning emitted.

- [ ] **Step 3: Add drift check in DirectStage.run**

In `src/pipeline/stages/direct.py`, after the `storyboard = Storyboard.from_dict(…)` call:

```python
        if reference_storyboard_json is not None:
            ref_scenes = json.loads(reference_storyboard_json).get("scenes", [])
            if len(ref_scenes) != len(storyboard.scenes):
                logger.warning(
                    "direct.scene_drift",
                    reference_count=len(ref_scenes),
                    produced_count=len(storyboard.scenes),
                )
            else:
                ref_ids = [s.get("id") for s in ref_scenes]
                new_ids = [s.id for s in storyboard.scenes]
                if ref_ids != new_ids:
                    logger.warning(
                        "direct.scene_id_mismatch",
                        reference_ids=ref_ids,
                        produced_ids=new_ids,
                    )
```

- [ ] **Step 4: Run test, confirm pass**

Run: `uv run pytest tests/unit/test_direct.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/stages/direct.py tests/unit/test_direct.py
git commit -m "feat(direct): warn on scene drift vs reference storyboard"
```

---

### Task 12: Thread `source_locale` / `reference_storyboard_path` through the CLI

**Files:**
- Modify: `src/pipeline/cli.py` (`produce` command)

- [ ] **Step 1: Read the current signature**

Confirm `produce` in `src/pipeline/cli.py` lines 27-43. It accepts `--locale`, `--start-from`, `--project-id`, etc.

- [ ] **Step 2: Add two new options**

Update the `produce` signature to accept two new `typer.Option` parameters:

```python
    source_locale: str | None = typer.Option(
        None, "--source-locale", help="Origin of source material (e.g. US, CA, en, ja)"
    ),
    reference_storyboard: str | None = typer.Option(
        None, "--reference-storyboard",
        help="Path to an existing storyboard JSON used as parallel-locale reference",
    ),
```

- [ ] **Step 3: Thread into the context**

Inside `produce`, when constructing `PipelineContext(...)` (around lines 62-69), add:

```python
            source_locale=source_locale,
            reference_storyboard_path=(
                Path(reference_storyboard) if reference_storyboard else None
            ),
```

And when loading existing context (around lines 57-60), after `ctx = PipelineContext.load(context_file)`:

```python
        if source_locale is not None:
            ctx.source_locale = source_locale
        if reference_storyboard is not None:
            ctx.reference_storyboard_path = Path(reference_storyboard)
```

Ensure `from pathlib import Path` is imported in `cli.py` (add if missing — search for `from pathlib` in the file first).

- [ ] **Step 4: Verify the CLI help renders**

Run: `uv run pipeline produce --help`
Expected: `--source-locale` and `--reference-storyboard` appear in the options list.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/cli.py
git commit -m "feat(cli): --source-locale and --reference-storyboard on produce"
```

---

### Task 13: Full-suite check and ruff/mypy sweep

**Files:** none (verification only)

- [ ] **Step 1: Run the fast test suite**

Run: `uv run pytest -m "not slow and not network and not integration"`
Expected: all PASS.

- [ ] **Step 2: Ruff and mypy**

Run: `uv run ruff check src/ tests/`
Expected: no errors (fix any that appeared from the edits).

Run: `uv run mypy src/pipeline/strategies.py src/pipeline/stages/direct.py src/pipeline/stages/base.py src/pipeline/storyboard.py`
Expected: no errors (fix any that appeared from the edits).

- [ ] **Step 3: If fixes were needed, commit**

```bash
git add -u
git commit -m "chore: ruff/mypy fixes for locale-framing changes"
```

(Skip this step if nothing was changed.)

---

### Task 14: Reproduce project 1776356443 as ja-JP (operational)

**Files:**
- Rename: `output/projects/1776356443/storyboard.json` → `output/projects/1776356443/storyboard_en.json`
- Modify: `output/projects/1776356443/context.json`
- Outputs (new): `output/projects/1776356443/storyboard_ja.json`, `script/script_ja.md`, `audio/segment_*.mp3` (regenerated), `audio/narration_ja.mp3`, `audio/subtitles_ja.srt`, `compose/final_ja.mp4`

- [ ] **Step 1: Rename the EN storyboard**

```bash
git mv output/projects/1776356443/storyboard.json output/projects/1776356443/storyboard_en.json
```

- [ ] **Step 2: Update context.json**

Edit `output/projects/1776356443/context.json`:
- Set `"locale": "ja"`
- Set `"source_locale": "US"`
- Set `"reference_storyboard_path": "output/projects/1776356443/storyboard_en.json"`
- Set `"storyboard_path": "output/projects/1776356443/storyboard_en.json"` (temporary — DirectStage overwrites)
- Set `"voice_id": "ja-JP-NanamiNeural"`
- Clear stage-4+ paths so they get regenerated:
  - `"narration_path": null`
  - `"subtitle_path": null`
  - `"segment_timings": null`
  - `"final_video_path": null`
  - `"script_path": null`

- [ ] **Step 3: Regenerate the storyboard (direct stage)**

Run:
```bash
uv run pipeline produce \
  --url "original" \
  --locale ja \
  --project-id 1776356443 \
  --source-locale US \
  --reference-storyboard output/projects/1776356443/storyboard_en.json \
  --start-from direct \
  --skip-review
```

If `--start-from direct` is not supported (check: `pre_review = {"acquire", "analyze", "direct"}` in cli.py — yes, it is), the command runs acquire (no-op for `origin=original`) then analyze (no-op if knowledge exists) then direct. If `start_from in pre_review` it re-runs from that stage.

Expected: `output/projects/1776356443/storyboard_ja.json` exists, contains `"title"` and `"description"` in Japanese, and has the same scene ids as `storyboard_en.json`.

- [ ] **Step 4: Sanity-check the JA storyboard**

```bash
uv run python -c "
import json
sb = json.loads(open('output/projects/1776356443/storyboard_ja.json').read())
print('title:', sb.get('title'))
print('description:', (sb.get('description') or '')[:120], '...')
print('scene count:', len(sb['scenes']))
print('first scene narration:', sb['scenes'][0]['narration'][:120], '...')
print('scene ids:', [s['id'] for s in sb['scenes'][:5]])
"
```
Expected: Japanese title that mentions American research / origin, scene count and ids match the EN reference, first scene narration is in Japanese and leads with source attribution.

- [ ] **Step 5: Regenerate TTS and compose**

Run:
```bash
uv run pipeline produce \
  --url "original" \
  --locale ja \
  --project-id 1776356443 \
  --voice ja-JP-NanamiNeural \
  --start-from tts \
  --skip-review
```

Expected: `compose/final_ja.mp4` is produced. The existing `compose/scenes/*_visual.mp4` are reused (scene ids and visuals matched the reference).

- [ ] **Step 6: Quick human review**

Play `output/projects/1776356443/compose/final_ja.mp4` (or at least inspect `audio/segment_000.mp3` and the first ~30 seconds) to confirm:
- Narration is Japanese.
- The hook mentions American research (or Brigham Young / Central Michigan).
- Scene pacing matches the EN reference.

- [ ] **Step 7: Commit the reproduction artifacts**

```bash
git add output/projects/1776356443/
git commit -m "chore(1776356443): reproduce parenting video as ja-JP"
```

---

## Self-Review

Checked against the spec:

**Spec coverage:**
- §1 strategy file format — Task 4 (fixtures) and Task 6 (real file).
- §2 strategy loader — Tasks 4 and 5.
- §3 PipelineContext changes — Task 2.
- §4 Storyboard title/description — Task 3.
- §5.1 locale-suffixed storyboard path — Task 7.
- §5.2 strategy injection — Task 8.
- §5.3 reference-storyboard injection — Task 9.
- §5.4 title + description in prompt/response — Task 10.
- §5.5 derived script file — unchanged, already handled by existing DirectStage code.
- §5.6 prompt skeleton — implemented across Tasks 8/9/10.
- §6 data flow — implemented via Tasks 4/8/9/10.
- §7 reproduction — Task 14 (with Task 12 providing CLI options).
- §8 testing strategy — Tasks 2/3/4/5/7/8/9/10/11.
- §9 risks: parallel-locale drift — Task 11.

**Placeholder scan:** no TBD/TODO; all test and implementation code is shown verbatim. Every step names exact file paths and gives the exact command to run.

**Type consistency:** `strategies_text: str = ""`, `reference_storyboard_json: str | None = None` used consistently in Task 8 and 9. `load_strategies(ctx, strategies_dir=…)` signature matches across Tasks 4 and 5. `title: str | None`, `description: str | None` match across Tasks 3 and 10.

**Gap found and fixed:** CLI needed to thread new context fields — added Task 12.
