# Dashboard Outline View + Per-Locale Narration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a beat-first authoring model and per-locale narration to the storyboard, plus a dashboard outline view and locale switcher, so multi-locale projects can be reviewed and tuned at the storyline level.

**Architecture:** The primary locale's narration stays a plain `str` on `Scene`; secondary locales live in a new `narration_alt: dict[str, str]` sidecar. A new `beat` field carries language-neutral scene intent. `DirectStage` emits the storyboard skeleton (beats, no narration); a revived `ScriptwriteStage` fills narration per locale from the beats. A migration backfills existing projects. The dashboard scanner exposes beats + a per-scene locale map; the dashboard UI gains a section-grouped outline panel and a locale switcher that audio-swaps the preview.

**Tech Stack:** Python 3.12, `uv`, `pytest`, `typer` (CLI), Anthropic SDK, FastAPI (dashboard server), vanilla JS (dashboard static).

**Reference spec:** `docs/superpowers/specs/2026-05-15-dashboard-outline-locale-design.md`

---

## File Structure

**Phase A — Schema & migration**
- Modify: `src/pipeline/storyboard.py` — `Scene` and `Storyboard` dataclasses
- Modify: `src/pipeline/cli_storyboard.py` — add `migrate` subcommand
- Test: `tests/unit/test_storyboard.py`, `tests/unit/test_cli_storyboard_migrate.py` (new)

**Phase B — Pipeline**
- Modify: `src/pipeline/stages/direct.py` — emit `beat` instead of `narration`
- Rewrite: `src/pipeline/stages/scriptwrite.py` — new beat-driven per-locale stage
- Modify: `src/pipeline/cli.py` — add `scriptwrite` to the stage chain
- Modify: `src/pipeline/stages/tts.py` — read `narration_alt` instead of `narration_en`
- Modify: `src/pipeline/verifier.py` — read `narration_alt`
- Test: `tests/unit/test_direct.py`, `tests/unit/test_scriptwrite.py` (new), `tests/unit/test_tts.py`

**Phase C — Dashboard**
- Modify: `src/pipeline/dashboard/scanner.py` — expose `beat`, locale map, `locales`, `primary_locale`
- Modify: `src/pipeline/dashboard/static/index.html` — outline panel + locale switcher
- Modify: `src/pipeline/dashboard/mutation_runtime.py` — locale-aware narration edits
- Test: `tests/unit/test_dashboard_scanner.py`, `tests/unit/test_dashboard_server.py`

---

## Phase A — Schema & Migration

### Task 1: `Scene` model — `narration_alt`, `beat`, `narration_for`

**Files:**
- Modify: `src/pipeline/storyboard.py:140-193` (`Scene` dataclass)
- Test: `tests/unit/test_storyboard.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_storyboard.py`:

```python
from pipeline.storyboard import Scene


def test_scene_from_dict_new_shape():
    scene = Scene.from_dict({
        "id": "s1",
        "section": "hook",
        "beat": "establishes the 600-year design stasis",
        "narration": "西元一千四百四十年……",
        "narration_alt": {"en": "Year 1440..."},
        "narration_est_sec": 8.0,
    })
    assert scene.beat == "establishes the 600-year design stasis"
    assert scene.narration == "西元一千四百四十年……"
    assert scene.narration_alt == {"en": "Year 1440..."}


def test_scene_from_dict_old_shape_folds_narration_en():
    scene = Scene.from_dict({
        "id": "s1",
        "section": "hook",
        "narration": "西元一千四百四十年……",
        "narration_en": "Year 1440...",
        "narration_est_sec": 8.0,
    })
    assert scene.beat == ""
    assert scene.narration == "西元一千四百四十年……"
    assert scene.narration_alt == {"en": "Year 1440..."}


def test_scene_to_dict_round_trip():
    data = {
        "id": "s1",
        "section": "hook",
        "beat": "b",
        "narration": "primary",
        "narration_alt": {"en": "secondary"},
        "narration_est_sec": 8.0,
        "facts_ref": [],
        "visual": {},
        "overlay": None,
        "pause_after_sec": 0.5,
    }
    out = Scene.from_dict(data).to_dict()
    assert out["beat"] == "b"
    assert out["narration"] == "primary"
    assert out["narration_alt"] == {"en": "secondary"}
    assert "narration_en" not in out


def test_scene_to_dict_omits_empty_narration_alt():
    scene = Scene.from_dict({
        "id": "s1", "section": "hook", "narration": "x", "narration_est_sec": 5.0,
    })
    assert "narration_alt" not in scene.to_dict()


def test_scene_narration_for():
    scene = Scene.from_dict({
        "id": "s1", "section": "hook", "narration": "primary",
        "narration_alt": {"en": "english"}, "narration_est_sec": 5.0,
    })
    assert scene.narration_for("zh-TW", "zh-TW") == "primary"
    assert scene.narration_for("en", "zh-TW") == "english"
    assert scene.narration_for("ja", "zh-TW") == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_storyboard.py -k "scene_from_dict_new_shape or old_shape_folds or to_dict_round_trip or omits_empty or narration_for" -v`
Expected: FAIL — `narration_alt` / `beat` not accepted, `narration_for` not defined.

- [ ] **Step 3: Update the `Scene` dataclass**

In `src/pipeline/storyboard.py`, replace the `Scene` dataclass fields and `from_dict`/`to_dict` (lines 140-193) with:

```python
@dataclass
class Scene:
    id: str
    section: str  # hook | context | rising | climax | aftermath | analysis | content | punchline
    narration: str  # primary locale narration text
    narration_est_sec: float
    beat: str = ""  # language-neutral one-line statement of scene intent
    narration_alt: dict[str, str] = field(default_factory=dict)  # secondary locales, keyed by locale code
    facts_ref: list[str] = field(default_factory=list)
    visual: dict[str, Any] = field(default_factory=dict)
    overlay: dict[str, Any] | None = None
    pause_after_sec: float = 0
    compartment: dict[str, Any] | None = None
    narration_source: NarrationSource | None = None
    subtitle_override: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Scene:
        ns_raw = data.get("narration_source")
        narration_source = NarrationSource.from_dict(ns_raw) if ns_raw else None
        narration_alt = dict(data.get("narration_alt", {}))
        # Backward compat: old flat schema stored the English track as narration_en.
        old_en = data.get("narration_en")
        if old_en is not None and "en" not in narration_alt:
            narration_alt["en"] = old_en
        return cls(
            id=data["id"],
            section=data["section"],
            narration=data["narration"],
            narration_est_sec=data["narration_est_sec"],
            beat=data.get("beat", ""),
            narration_alt=narration_alt,
            facts_ref=list(data.get("facts_ref", [])),
            visual=dict(data.get("visual", {})),
            overlay=data.get("overlay"),
            pause_after_sec=float(data.get("pause_after_sec", 0)),
            compartment=data.get("compartment"),
            narration_source=narration_source,
            subtitle_override=data.get("subtitle_override"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "section": self.section,
            "beat": self.beat,
            "narration": self.narration,
            "narration_est_sec": self.narration_est_sec,
            "facts_ref": self.facts_ref,
            "visual": self.visual,
            "overlay": self.overlay,
            "pause_after_sec": self.pause_after_sec,
        }
        if self.narration_alt:
            out["narration_alt"] = self.narration_alt
        if self.compartment is not None:
            out["compartment"] = self.compartment
        if self.narration_source is not None:
            out["narration_source"] = self.narration_source.to_dict()
        if self.subtitle_override is not None:
            out["subtitle_override"] = self.subtitle_override
        return out

    def narration_for(self, locale: str, primary_locale: str) -> str:
        """Return the narration text for a locale; '' if that locale is absent."""
        if locale == primary_locale:
            return self.narration
        return self.narration_alt.get(locale, "")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_storyboard.py -k "scene_from_dict_new_shape or old_shape_folds or to_dict_round_trip or omits_empty or narration_for" -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Run the full storyboard test file for regressions**

Run: `uv run pytest tests/unit/test_storyboard.py -v`
Expected: PASS. If a pre-existing test asserted `narration_en` round-trips, update it to use `narration_alt` — the old key is intentionally removed.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/storyboard.py tests/unit/test_storyboard.py
git commit -m "feat(storyboard): add beat + narration_alt to Scene model"
```

---

### Task 2: `Storyboard` model — `primary_locale`, `*_alt`, `derive_script(locale)`

**Files:**
- Modify: `src/pipeline/storyboard.py:248-330` (`Storyboard` dataclass)
- Test: `tests/unit/test_storyboard.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_storyboard.py`:

```python
from pipeline.storyboard import Storyboard


def _sb(**over):
    base = {
        "version": 1,
        "primary_locale": "zh-TW",
        "scenes": [
            {"id": "s1", "section": "hook", "beat": "b1", "narration": "主要一",
             "narration_alt": {"en": "primary one"}, "narration_est_sec": 5.0,
             "pause_after_sec": 0.0},
            {"id": "s2", "section": "context", "beat": "b2", "narration": "主要二",
             "narration_alt": {"en": "primary two"}, "narration_est_sec": 5.0,
             "pause_after_sec": 0.0},
        ],
    }
    base.update(over)
    return Storyboard.from_dict(base)


def test_storyboard_primary_locale_round_trip():
    sb = _sb()
    assert sb.primary_locale == "zh-TW"
    assert sb.to_dict()["primary_locale"] == "zh-TW"


def test_storyboard_primary_locale_defaults():
    sb = Storyboard.from_dict({"version": 1, "scenes": []})
    assert sb.primary_locale == "zh-TW"


def test_derive_script_defaults_to_primary():
    script = _sb().derive_script()
    assert "主要一" in script and "主要二" in script
    assert "primary one" not in script


def test_derive_script_secondary_locale():
    script = _sb().derive_script(locale="en")
    assert "primary one" in script and "primary two" in script
    assert "主要一" not in script
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_storyboard.py -k "storyboard_primary_locale or derive_script" -v`
Expected: FAIL — `primary_locale` not accepted, `derive_script` takes no `locale`.

- [ ] **Step 3: Update the `Storyboard` dataclass**

In `src/pipeline/storyboard.py`, modify the `Storyboard` dataclass. Add fields after `description` (line 260):

```python
    title_alt: dict[str, str] = field(default_factory=dict)
    description_alt: dict[str, str] = field(default_factory=dict)
    primary_locale: str = "zh-TW"
```

In `to_dict` (after the `description` block, before `transitions`):

```python
        if self.title_alt:
            out["title_alt"] = self.title_alt
        if self.description_alt:
            out["description_alt"] = self.description_alt
        out["primary_locale"] = self.primary_locale
```

In `from_dict`, add to the `cls(...)` call:

```python
            title_alt=dict(data.get("title_alt", {})),
            description_alt=dict(data.get("description_alt", {})),
            primary_locale=data.get("primary_locale", "zh-TW"),
```

Replace `derive_script` (lines 312-330) with:

```python
    def derive_script(self, locale: str | None = None) -> str:
        """Produce clean narration text for TTS, for the given locale.

        Concatenates scene narration with section markers that TTS
        can filter out. `locale` defaults to the primary locale.
        """
        loc = locale or self.primary_locale
        lines: list[str] = []
        for scene in self.scenes:
            lines.append(f"[{scene.section.upper()}]")
            lines.append("")
            lines.append(scene.narration_for(loc, self.primary_locale))
            lines.append("")
            if scene.pause_after_sec > 0:
                lines.append(f"[PAUSE:{int(scene.pause_after_sec)}s]")
                lines.append("")
        return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_storyboard.py -k "storyboard_primary_locale or derive_script" -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the full storyboard test file**

Run: `uv run pytest tests/unit/test_storyboard.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/storyboard.py tests/unit/test_storyboard.py
git commit -m "feat(storyboard): add primary_locale and locale-aware derive_script"
```

---

### Task 3: Migration command — `pipeline storyboard migrate`

**Files:**
- Modify: `src/pipeline/cli_storyboard.py` (add `migrate` subcommand)
- Test: `tests/unit/test_cli_storyboard_migrate.py` (new)

The migration is mechanical (no LLM): fold `narration_en` → `narration_alt["en"]`, drop `narration_en`, and write `primary_locale` derived from the project's `context.json` `locale`. Beat backfill is a separate, optional follow-up — this task ships the schema migration only. (Beat backfill is Task 3b below.)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_cli_storyboard_migrate.py`:

```python
import json
from pathlib import Path

from pipeline.cli_storyboard import migrate_storyboard_file


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_migrate_folds_narration_en(tmp_path: Path):
    sb_path = tmp_path / "storyboard.json"
    _write(sb_path, {
        "version": 1,
        "scenes": [
            {"id": "s1", "section": "hook", "narration": "主要",
             "narration_en": "primary", "narration_est_sec": 5.0},
        ],
    })
    changed = migrate_storyboard_file(sb_path, primary_locale="zh-TW")
    assert changed is True
    data = json.loads(sb_path.read_text(encoding="utf-8"))
    assert data["primary_locale"] == "zh-TW"
    scene = data["scenes"][0]
    assert scene["narration_alt"] == {"en": "primary"}
    assert "narration_en" not in scene
    assert scene["beat"] == ""


def test_migrate_is_idempotent(tmp_path: Path):
    sb_path = tmp_path / "storyboard.json"
    _write(sb_path, {
        "version": 1,
        "primary_locale": "zh-TW",
        "scenes": [
            {"id": "s1", "section": "hook", "beat": "", "narration": "主要",
             "narration_alt": {"en": "primary"}, "narration_est_sec": 5.0},
        ],
    })
    changed = migrate_storyboard_file(sb_path, primary_locale="zh-TW")
    assert changed is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_cli_storyboard_migrate.py -v`
Expected: FAIL — `migrate_storyboard_file` not defined.

- [ ] **Step 3: Add `migrate_storyboard_file` and the `migrate` subcommand**

In `src/pipeline/cli_storyboard.py`, add this function (near the top, after imports) and a CLI command. First the helper:

```python
def migrate_storyboard_file(path: Path, primary_locale: str) -> bool:
    """Migrate one storyboard.json to the beat/narration_alt schema in place.

    Returns True if the file was changed, False if it was already migrated.
    """
    import json as _json

    data = _json.loads(path.read_text(encoding="utf-8"))
    already = "primary_locale" in data and all(
        "narration_en" not in s for s in data.get("scenes", [])
    )
    if already:
        return False
    data["primary_locale"] = data.get("primary_locale", primary_locale)
    for scene in data.get("scenes", []):
        scene.setdefault("beat", "")
        old_en = scene.pop("narration_en", None)
        if old_en is not None:
            alt = scene.setdefault("narration_alt", {})
            alt.setdefault("en", old_en)
    path.write_text(
        _json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return True
```

Then the CLI command. Match the existing pattern in the file (a `typer` app named `storyboard_app` or similar — use whatever the file already defines; the existing `show`/`set` commands show the decorator name). Add:

```python
@storyboard_app.command("migrate")
def migrate(
    project_id: str = typer.Option(None, "--project-id", help="Migrate one project"),
    all_projects: bool = typer.Option(False, "--all", help="Migrate every project"),
) -> None:
    """Migrate storyboard.json files to the beat/narration_alt schema."""
    projects_root = Path("output/projects")
    if all_projects:
        targets = sorted(projects_root.glob("*/"))
    elif project_id:
        targets = [projects_root / project_id]
    else:
        raise typer.BadParameter("Pass --project-id <id> or --all")

    for project_dir in targets:
        sb_path = project_dir / "storyboard.json"
        ctx_path = project_dir / "context.json"
        if not sb_path.exists() or not ctx_path.exists():
            continue
        ctx = json.loads(ctx_path.read_text(encoding="utf-8"))
        primary_locale = ctx.get("locale", "zh-TW")
        changed = migrate_storyboard_file(sb_path, primary_locale=primary_locale)
        status = "migrated" if changed else "already current"
        typer.echo(f"{project_dir.name}: {status}")
```

If the file uses `import json` at module scope already, drop the local `import json as _json` and use `json` directly. Verify the typer app variable name by reading the top of `cli_storyboard.py` before editing.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_cli_storyboard_migrate.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Migrate the baby-walker project and verify**

Run: `uv run pipeline storyboard migrate --project-id 20260504-115232-baby-walker-story`
Expected output: `20260504-115232-baby-walker-story: migrated`

Then verify:
Run: `uv run python -c "import json; d=json.load(open('output/projects/20260504-115232-baby-walker-story/storyboard.json')); print(d['primary_locale']); print(d['scenes'][0].get('narration_alt')); print('narration_en' in d['scenes'][0])"`
Expected: `zh-TW`, a dict with an `en` key, `False`.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/cli_storyboard.py tests/unit/test_cli_storyboard_migrate.py output/projects/20260504-115232-baby-walker-story/storyboard.json
git commit -m "feat(storyboard): add migrate command for beat/narration_alt schema"
```

---

### Task 3b: Beat backfill (LLM) for migrated projects

**Files:**
- Modify: `src/pipeline/cli_storyboard.py` (extend `migrate` with `--backfill-beats`)
- Test: `tests/unit/test_cli_storyboard_migrate.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_cli_storyboard_migrate.py`:

```python
def test_backfill_beats_fills_empty_beats(tmp_path: Path, monkeypatch):
    from pipeline import cli_storyboard

    sb_path = tmp_path / "storyboard.json"
    _write(sb_path, {
        "version": 1,
        "primary_locale": "zh-TW",
        "scenes": [
            {"id": "s1", "section": "hook", "beat": "", "narration": "主要一",
             "narration_alt": {}, "narration_est_sec": 5.0},
            {"id": "s2", "section": "context", "beat": "", "narration": "主要二",
             "narration_alt": {}, "narration_est_sec": 5.0},
        ],
    })

    def fake_generate(scenes):
        return {"s1": "beat one", "s2": "beat two"}

    monkeypatch.setattr(cli_storyboard, "_generate_beats", fake_generate)
    cli_storyboard.backfill_beats_file(sb_path)
    data = json.loads(sb_path.read_text(encoding="utf-8"))
    assert data["scenes"][0]["beat"] == "beat one"
    assert data["scenes"][1]["beat"] == "beat two"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_cli_storyboard_migrate.py -k backfill -v`
Expected: FAIL — `backfill_beats_file` / `_generate_beats` not defined.

- [ ] **Step 3: Implement beat backfill**

In `src/pipeline/cli_storyboard.py`, add:

```python
def _generate_beats(scenes: list[dict]) -> dict[str, str]:
    """Ask Claude for a one-line language-neutral beat per scene."""
    from pipeline.config import PipelineConfig
    from pipeline.stages.analyze import get_anthropic_client

    client = get_anthropic_client()
    config = PipelineConfig()
    scene_lines = "\n".join(
        f"{s['id']} [{s['section']}]: {s['narration'][:200]}" for s in scenes
    )
    prompt = (
        "For each scene below, write a one-line, language-neutral 'beat' — a short "
        "statement of what the scene accomplishes in the story (its intent), NOT a "
        "summary of its wording. Return ONLY valid JSON mapping scene id to beat string.\n\n"
        f"{scene_lines}"
    )
    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(raw)


def backfill_beats_file(path: Path) -> bool:
    """Fill empty `beat` fields in a storyboard via one LLM call. Returns True if changed."""
    data = json.loads(path.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])
    if not scenes or all(s.get("beat") for s in scenes):
        return False
    beats = _generate_beats(scenes)
    for scene in scenes:
        if not scene.get("beat"):
            scene["beat"] = beats.get(scene["id"], "")
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return True
```

Then extend the `migrate` command: add a `backfill_beats: bool = typer.Option(False, "--backfill-beats")` option, and after the `migrate_storyboard_file(...)` call inside the loop:

```python
        if backfill_beats:
            if backfill_beats_file(sb_path):
                typer.echo(f"{project_dir.name}: beats backfilled")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_cli_storyboard_migrate.py -k backfill -v`
Expected: PASS.

- [ ] **Step 5: Backfill beats for baby-walker and verify**

Run: `uv run pipeline storyboard migrate --project-id 20260504-115232-baby-walker-story --backfill-beats`
Expected: `... already current` then `... beats backfilled`.

Run: `uv run python -c "import json; d=json.load(open('output/projects/20260504-115232-baby-walker-story/storyboard.json')); print(d['scenes'][0]['beat'])"`
Expected: a non-empty beat string.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/cli_storyboard.py tests/unit/test_cli_storyboard_migrate.py output/projects/20260504-115232-baby-walker-story/storyboard.json
git commit -m "feat(storyboard): backfill beats via LLM during migrate"
```

---

## Phase B — Pipeline

### Task 4: `DirectStage` emits `beat` instead of `narration`

**Files:**
- Modify: `src/pipeline/stages/direct.py:166-217` (`build_direct_prompt` return) and `:619-624` (`ctx.story_structure`)
- Test: `tests/unit/test_direct.py`

`DirectStage` now produces the storyboard skeleton: each scene carries `beat` and `narration_est_sec` but `narration` is an empty string (filled later by `ScriptwriteStage`).

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_direct.py` (create the file if it does not exist; check for an existing one first):

```python
from pipeline.stages.direct import build_direct_prompt
from pipeline.knowledge import Knowledge


def test_direct_prompt_requests_beat_not_narration():
    knowledge = Knowledge(facts=[], entities=[], timeline=[])
    prompt = build_direct_prompt(
        knowledge, "zh-TW", "standard", "dramatic",
        strategies_text="", reference_storyboard_json=None,
        constraints_text="", clip_budget_text="", intro_template_text="",
        niche=None,
    )
    assert '"beat"' in prompt
    assert "Narration text in target locale" not in prompt
```

If `Knowledge(...)` needs different constructor args, read `src/pipeline/knowledge.py` and build a minimal valid instance.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_direct.py -k beat -v`
Expected: FAIL — prompt still asks for `narration`.

- [ ] **Step 3: Update the prompt schema**

In `src/pipeline/stages/direct.py`, in `build_direct_prompt`'s returned JSON schema (lines 202-214), replace the scene object so it requests `beat` instead of `narration`:

```python
  "scenes": [
    {{
      "id": "s1",
      "section": "hook|context|rising|climax|aftermath|analysis|content|punchline",
      "beat": "language-neutral one-line statement of what this scene accomplishes (intent, NOT narration text, NOT a wording summary)",
      "narration_est_sec": 13,
      "facts_ref": ["f1"],
      "visual": {{"type": "...", ...}},
      "overlay": null or {{"type": "...", "text": "..."}},
      "pause_after_sec": 0.5
    }}
  ]
```

Also update the instruction line near the schema — change any text that says to write narration so it says to write beats. The `LOCALE`/`LANGUAGE` lines stay (titles/descriptions are still locale-specific).

- [ ] **Step 4: Handle the skeleton in `DirectStage.run`**

In `DirectStage.run`, the parsed `result` now has scenes with `beat` and no `narration`. `Scene.from_dict` requires `narration`. In the storyboard-building block (lines 559-570), inject an empty narration into each scene dict before constructing the `Storyboard`:

```python
        result = json.loads(raw_text)
        for scene in result.get("scenes", []):
            scene.setdefault("narration", "")

        # Build storyboard
        storyboard = Storyboard.from_dict(
            {
                "version": 1,
                "format": self.fmt,
                "target_duration_sec": 60 if self.fmt == "short" else 720,
                "aspect_ratio": "9:16" if self.fmt == "short" else "16:9",
                "primary_locale": ctx.locale,
                "title": result.get("title"),
                "description": result.get("description"),
                **{k: v for k, v in result.items() if k not in ("title", "description")},
            }
        )
```

Then update the `ctx.story_structure` block (lines 619-624) to use real beats:

```python
        # Backwards compat: populate old fields
        ctx.story_structure = {
            "beats": [
                {"id": s.id, "section": s.section, "beat": s.beat}
                for s in storyboard.scenes
            ],
        }
```

Remove the `derive_script` / `script_path` write block at lines 611-617 — script derivation now belongs to `ScriptwriteStage` (Task 5). Also update the metadata `synopsis` at lines 646-648 to use `s.beat` instead of `s.narration[:120]` (narration is empty at this stage):

```python
                    synopsis = "\n".join(
                        f"{s.section}: {s.beat}" for s in storyboard.scenes
                    )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_direct.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/stages/direct.py tests/unit/test_direct.py
git commit -m "feat(direct): emit storyboard skeleton with beats, not narration"
```

---

### Task 5: New `ScriptwriteStage` — per-locale narration from beats

**Files:**
- Rewrite: `src/pipeline/stages/scriptwrite.py`
- Test: `tests/unit/test_scriptwrite.py` (new)

`ScriptwriteStage` runs after `DirectStage`. For each locale in `[ctx.locale, ctx.secondary_locale]` (skipping `None`), it makes one Claude call that writes narration for every beat, in that locale, within each scene's `narration_est_sec` budget. It writes `narration` for the primary locale and `narration_alt[locale]` for secondary locales, saves the storyboard, and derives the primary-locale script.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_scriptwrite.py`:

```python
import json
from pathlib import Path

import pytest

from pipeline.stages.base import PipelineContext
from pipeline.stages.scriptwrite import ScriptwriteStage, build_scriptwrite_prompt
from pipeline.storyboard import Scene, Storyboard


def test_build_scriptwrite_prompt_includes_beats_and_locale():
    scenes = [
        Scene(id="s1", section="hook", narration="", narration_est_sec=8.0,
              beat="establishes the 600-year design stasis"),
    ]
    prompt = build_scriptwrite_prompt(scenes, "en")
    assert "establishes the 600-year design stasis" in prompt
    assert "8" in prompt  # duration budget surfaced
    assert "en" in prompt


@pytest.mark.asyncio
async def test_scriptwrite_fills_primary_and_secondary(tmp_path: Path, monkeypatch):
    from pipeline.stages import scriptwrite as sw_mod

    sb = Storyboard(
        primary_locale="zh-TW",
        scenes=[
            Scene(id="s1", section="hook", narration="", narration_est_sec=8.0, beat="b1"),
            Scene(id="s2", section="context", narration="", narration_est_sec=8.0, beat="b2"),
        ],
    )
    sb_path = tmp_path / "storyboard_zh-TW.json"
    sb.save(sb_path)

    calls = []

    def fake_write(scenes, locale):
        calls.append(locale)
        return {"s1": f"{locale}-one", "s2": f"{locale}-two"}

    monkeypatch.setattr(sw_mod, "_write_narration_for_locale", fake_write)

    ctx = PipelineContext(work_dir=tmp_path, locale="zh-TW")
    ctx.secondary_locale = "en"
    ctx.storyboard_path = sb_path

    result = await ScriptwriteStage().run(ctx)

    saved = Storyboard.load(sb_path)
    assert saved.scenes[0].narration == "zh-TW-one"
    assert saved.scenes[0].narration_alt["en"] == "en-one"
    assert saved.scenes[1].narration == "zh-TW-two"
    assert saved.scenes[1].narration_alt["en"] == "en-two"
    assert set(calls) == {"zh-TW", "en"}
    assert result.script_path is not None and result.script_path.exists()
```

If `PipelineContext(...)` requires other args, read `src/pipeline/stages/base.py` and pass the minimum needed.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_scriptwrite.py -v`
Expected: FAIL — `build_scriptwrite_prompt` signature differs, `_write_narration_for_locale` not defined, stage logic is the old markdown writer.

- [ ] **Step 3: Rewrite `scriptwrite.py`**

Replace the entire contents of `src/pipeline/stages/scriptwrite.py` with:

```python
from __future__ import annotations

import json

import structlog

from pipeline.config import PipelineConfig
from pipeline.stages.analyze import get_anthropic_client
from pipeline.stages.base import PipelineContext, PipelineStage
from pipeline.storyboard import Scene, Storyboard

logger = structlog.get_logger()

LOCALE_INSTRUCTIONS = {
    "zh-TW": (
        "Write in Traditional Chinese (zh-TW), Taiwan usage conventions. "
        "Explain US-specific context (legal system, geography, policing norms) "
        "that Taiwanese audiences need. Use conversational but authoritative tone."
    ),
    "en": "Write in clear, conversational English for a US/international audience.",
    "ja": (
        "Write in Japanese. Use appropriate keigo level for documentary narration. "
        "Add cultural context bridging US and Japanese norms."
    ),
    "es-MX": (
        "Write in Latin American Spanish (Mexican variant). "
        "Explain US cultural context for Latin American audiences."
    ),
}


def build_scriptwrite_prompt(scenes: list[Scene], locale: str) -> str:
    """Build the Claude prompt that writes narration for every beat in one locale."""
    locale_instruction = LOCALE_INSTRUCTIONS.get(locale, LOCALE_INSTRUCTIONS["en"])
    beat_lines = "\n".join(
        f'{s.id} [{s.section}] (~{s.narration_est_sec:.0f}s): {s.beat}'
        for s in scenes
    )
    return f"""You are a scriptwriter for a YouTube channel. For each scene beat below,
write the narration in the target locale. This is a cultural adaptation, NOT a
translation — give the narration the locale's own voice and idiom while hitting the
beat's intent.

LOCALE: {locale}
LANGUAGE INSTRUCTION: {locale_instruction}

RULES:
- Each scene's narration must fit its duration budget (the ~Ns hint). Stay close to it.
- Hit the beat's intent; do not invent new story facts.
- Plain narration text only — no markers, no meta-commentary.

SCENE BEATS:
{beat_lines}

Return ONLY valid JSON mapping scene id to narration string, e.g.
{{"s1": "...", "s2": "..."}}"""


def _write_narration_for_locale(scenes: list[Scene], locale: str) -> dict[str, str]:
    """One Claude call: narration for every scene in one locale. Returns id -> text."""
    client = get_anthropic_client()
    config = PipelineConfig()
    prompt = build_scriptwrite_prompt(scenes, locale)
    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=16000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(raw)


class ScriptwriteStage(PipelineStage):
    @property
    def name(self) -> str:
        return "scriptwrite"

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.storyboard_path or not ctx.storyboard_path.exists():
            raise ValueError("No storyboard — run direct stage first")

        logger.info("scriptwrite.start", locale=ctx.locale,
                    secondary=ctx.secondary_locale)

        storyboard = Storyboard.load(ctx.storyboard_path)
        locales: list[str] = [ctx.locale]
        if ctx.secondary_locale and ctx.secondary_locale not in locales:
            locales.append(ctx.secondary_locale)

        for locale in locales:
            narration_by_id = _write_narration_for_locale(storyboard.scenes, locale)
            for scene in storyboard.scenes:
                text = narration_by_id.get(scene.id, "")
                if locale == storyboard.primary_locale:
                    scene.narration = text
                else:
                    scene.narration_alt[locale] = text
            logger.info("scriptwrite.locale_done", locale=locale,
                        scenes=len(storyboard.scenes))

        storyboard.save(ctx.storyboard_path)

        # Derive the primary-locale script for downstream TTS.
        script_dir = ctx.work_dir / "script"
        script_dir.mkdir(parents=True, exist_ok=True)
        script_path = script_dir / f"script_{ctx.locale}.md"
        script_path.write_text(storyboard.derive_script(), encoding="utf-8")
        ctx.script_path = script_path

        logger.info("scriptwrite.complete", locales=locales)
        return ctx
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_scriptwrite.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/stages/scriptwrite.py tests/unit/test_scriptwrite.py
git commit -m "feat(scriptwrite): rewrite as beat-driven per-locale narration stage"
```

---

### Task 6: Wire `ScriptwriteStage` into the `produce` chain

**Files:**
- Modify: `src/pipeline/cli.py:34` (import), `:199-208` (stage list + review sets)
- Test: `tests/unit/test_cli_chain.py` (new, or extend an existing CLI test)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_cli_chain.py`:

```python
def test_scriptwrite_in_pre_review_chain():
    from pipeline.stages.acquire import AcquireStage
    from pipeline.stages.analyze import AnalyzeStage
    from pipeline.stages.direct import DirectStage
    from pipeline.stages.scriptwrite import ScriptwriteStage
    from pipeline.stages.tts import TtsStage
    from pipeline.stages.compose import ComposeStage

    all_stages = [
        AcquireStage(), AnalyzeStage(), DirectStage(),
        ScriptwriteStage(), TtsStage(), ComposeStage(),
    ]
    names = [s.name for s in all_stages]
    assert names == ["acquire", "analyze", "direct", "scriptwrite", "tts", "compose"]
    # scriptwrite must run before the human review gate (pre-review)
    pre_review = {"acquire", "analyze", "direct", "scriptwrite"}
    assert "scriptwrite" in pre_review
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_cli_chain.py -v`
Expected: FAIL — `ScriptwriteStage` import path may differ or `AcquireStage()` needs args. If `AcquireStage()` requires args, construct it with `local_transcript=None, local_video=None` to match `cli.py`'s usage.

- [ ] **Step 3: Wire the stage into `cli.py`**

In `src/pipeline/cli.py`, add the import near line 34:

```python
from pipeline.stages.scriptwrite import ScriptwriteStage
```

Update `all_stages` (lines 199-205):

```python
    all_stages = [
        acquire,
        AnalyzeStage(),
        DirectStage(),
        ScriptwriteStage(),
        TtsStage(),
        ComposeStage(),
    ]
```

Update the review-gate sets (lines 207-208):

```python
    pre_review = {"acquire", "analyze", "direct", "scriptwrite"}
    post_review = {"tts", "compose"}
```

This makes `--start-from scriptwrite` re-run narration generation up to the review gate; `--start-from tts` then resumes rendering. No other change to the gate logic is needed.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_cli_chain.py -v`
Expected: PASS.

- [ ] **Step 5: Verify `--start-from` accepts `scriptwrite`**

Read the `--start-from` option definition in `cli.py` (search for `start_from`). If it is a constrained `Enum` or has a validation list, add `scriptwrite` to it. If it is a free-form `str`, no change is needed. Make the change if required.

Run: `uv run pipeline produce --help`
Expected: help text renders without error; if `--start-from` lists choices, `scriptwrite` appears.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/cli.py tests/unit/test_cli_chain.py
git commit -m "feat(cli): add scriptwrite stage to produce chain"
```

---

### Task 7: TTS + verifier read `narration_alt`

**Files:**
- Modify: `src/pipeline/stages/tts.py:326` (`_run_secondary_tts`)
- Modify: `src/pipeline/verifier.py:75`
- Test: `tests/unit/test_tts.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_tts.py`:

```python
def test_secondary_tts_reads_narration_alt():
    from pipeline.storyboard import Scene

    scenes = [
        Scene(id="s1", section="hook", narration="主要", narration_est_sec=5.0,
              narration_alt={"en": "english one"}),
        Scene(id="s2", section="context", narration="主要二", narration_est_sec=5.0,
              narration_alt={}),
    ]
    # Mirror the segment-collection logic from _run_secondary_tts.
    en_segments = [s.narration_alt.get("en", "") for s in scenes]
    assert en_segments == ["english one", ""]
```

This pins the expected access pattern. (The full `_run_secondary_tts` path is integration-tested elsewhere; this guards the field access.)

- [ ] **Step 2: Run the test to verify it fails or passes trivially**

Run: `uv run pytest tests/unit/test_tts.py -k narration_alt -v`
Expected: PASS only after Task 1 (the `Scene` model already has `narration_alt`). If it passes here, that is fine — the real change is Step 3.

- [ ] **Step 3: Update `tts.py` and `verifier.py`**

In `src/pipeline/stages/tts.py`, find line 326:

```python
        en_segments = [s.narration_en if s.narration_en is not None else "" for s in scenes]
```

Replace with (use the actual secondary locale, not a hardcoded `en`):

```python
        sec_locale = ctx.secondary_locale or "en"
        en_segments = [s.narration_alt.get(sec_locale, "") for s in scenes]
```

Also update the log event at `tts.py:136` (`tts.secondary.missing_narration_en`) — read the surrounding code and change any `narration_en` reference to `narration_alt.get(sec_locale)`. Rename the log key to `tts.secondary.missing_narration` for accuracy.

In `src/pipeline/verifier.py:75`:

```python
        parts.append(scene.get("narration_en", "") or "")
```

Replace with:

```python
        alt = scene.get("narration_alt", {})
        parts.append(" ".join(alt.values()) if isinstance(alt, dict) else "")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_tts.py tests/unit/test_verifier.py -v`
Expected: PASS. Update any pre-existing test in those files that constructed scenes with `narration_en=` to use `narration_alt={"en": ...}`.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/stages/tts.py src/pipeline/verifier.py tests/unit/test_tts.py tests/unit/test_verifier.py
git commit -m "feat(tts): read secondary narration from narration_alt"
```

---

## Phase C — Dashboard

### Task 8: Scanner exposes `beat`, locale map, `locales`, `primary_locale`

**Files:**
- Modify: `src/pipeline/dashboard/scanner.py` — `ProjectInfo` fields, `scan_projects`, `_estimate_scenes_from_storyboard_data`, `_attach_storyboard_scene_metadata`
- Test: `tests/unit/test_dashboard_scanner.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_dashboard_scanner.py` (follow the existing fixture style in that file — it builds a temp project dir; reuse its helper if present):

```python
import json
from pathlib import Path

from pipeline.dashboard.scanner import scan_projects


def _make_project(root: Path, pid: str) -> Path:
    pdir = root / "projects" / pid
    pdir.mkdir(parents=True)
    (pdir / "context.json").write_text(json.dumps({"locale": "zh-TW"}))
    (pdir / "storyboard.json").write_text(json.dumps({
        "version": 1,
        "primary_locale": "zh-TW",
        "scenes": [
            {"id": "s1", "section": "hook", "beat": "the stasis beat",
             "narration": "主要", "narration_alt": {"en": "primary"},
             "narration_est_sec": 8.0, "pause_after_sec": 0.0},
        ],
    }))
    return pdir


def test_scanner_exposes_beat_and_locale_map(tmp_path: Path):
    _make_project(tmp_path, "20260101-000000-test")
    projects = scan_projects(tmp_path)
    assert len(projects) == 1
    p = projects[0]
    assert p.primary_locale == "zh-TW"
    assert "zh-TW" in p.locales and "en" in p.locales
    scene = p.scenes[0]
    assert scene["beat"] == "the stasis beat"
    assert scene["narration_by_locale"] == {"zh-TW": "主要", "en": "primary"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_dashboard_scanner.py -k beat_and_locale -v`
Expected: FAIL — `ProjectInfo` has no `primary_locale` / `locales`; scene dict has no `beat` / `narration_by_locale`.

- [ ] **Step 3: Add `ProjectInfo` fields**

In `src/pipeline/dashboard/scanner.py`, add to the `ProjectInfo` dataclass (after `theme`, before `render_freshness`):

```python
    primary_locale: str = "zh-TW"
    locales: list[str] = field(default_factory=list)
```

- [ ] **Step 4: Populate `beat` and `narration_by_locale` on scene dicts**

In `_estimate_scenes_from_storyboard_data` (around lines 226-245), add `"beat"` to each scene dict it builds:

```python
                "beat": scene.get("beat", ""),
```

In `_attach_storyboard_scene_metadata` (lines 249-272), inside the `for scene in scenes:` loop after the `source` lookup, attach the beat, the locale map, and a `duration_sec` fallback (so the outline panel works whether scenes came from `compose/scenes.json` or storyboard estimation):

```python
        scene["beat"] = source.get("beat", "")
        src_visual = source.get("visual")
        if isinstance(src_visual, dict):
            scene["visual_type"] = src_visual.get("type", "")
        if "duration_sec" not in scene:
            scene["duration_sec"] = float(source.get("narration_est_sec", 0)) + float(
                source.get("pause_after_sec", 0)
            )
        primary = str(storyboard.get("primary_locale", "zh-TW"))
        narration_map: dict[str, str] = {}
        primary_text = source.get("narration", "")
        if primary_text:
            narration_map[primary] = primary_text
        alt = source.get("narration_alt", {})
        if isinstance(alt, dict):
            for loc, text in alt.items():
                if text:
                    narration_map[loc] = text
        scene["narration_by_locale"] = narration_map
```

(The `compose/scenes.json` path may not carry `beat`/`narration_alt`; `_attach_storyboard_scene_metadata` runs in both cases — see `scanner.py:95-96` — so this covers both.)

- [ ] **Step 5: Compute `locales` and `primary_locale` in `scan_projects`**

In `scan_projects`, after `storyboard_data` is loaded (line 87) and before building `ProjectInfo`, compute:

```python
        primary_locale = str(storyboard_data.get("primary_locale", locale)) if storyboard_data else locale
        locale_set: set[str] = {primary_locale} if primary_locale else set()
        for sc in (storyboard_data.get("scenes", []) if storyboard_data else []):
            alt = sc.get("narration_alt", {})
            if isinstance(alt, dict):
                locale_set.update(alt.keys())
        project_locales = sorted(locale_set)
```

Then add to the `ProjectInfo(...)` constructor call:

```python
                primary_locale=primary_locale,
                locales=project_locales,
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_dashboard_scanner.py -v`
Expected: PASS.

- [ ] **Step 7: Verify the server serializes the new fields**

The server endpoint `/api/projects` serializes `ProjectInfo`. Read `src/pipeline/dashboard/server.py` around line 238 (`@app.get("/api/projects")`) and confirm it serializes via `dataclasses.asdict` or an explicit dict. If explicit, add `primary_locale` and `locales`. If `asdict`, no change needed.

Run: `uv run pytest tests/unit/test_dashboard_server.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/pipeline/dashboard/scanner.py src/pipeline/dashboard/server.py tests/unit/test_dashboard_scanner.py
git commit -m "feat(dashboard): scanner exposes beat, narration locale map, locales"
```

---

### Task 9: Outline view panel

**Files:**
- Modify: `src/pipeline/dashboard/static/index.html` — add `buildOutlinePanel(project)` and render it in `makeDetailRow`
- Manual verification (no JS unit-test harness in this repo; the dashboard static layer is verified in-browser)

- [ ] **Step 1: Add the `buildOutlinePanel` function**

In `src/pipeline/dashboard/static/index.html`, add this function next to `buildSceneStrip` (near line 391):

```javascript
function buildOutlinePanel(project) {
  const scenes = project.scenes || [];
  if (!scenes.length) return '';
  // Group consecutive scenes by section, preserving order.
  const bands = [];
  for (const s of scenes) {
    const last = bands[bands.length - 1];
    if (last && last.section === s.section) {
      last.scenes.push(s);
    } else {
      bands.push({ section: s.section, scenes: [s] });
    }
  }
  const bandHtml = bands.map(band => {
    const dur = band.scenes.reduce((a, s) => a + (s.duration_sec || 0), 0);
    const rows = band.scenes.map(s => {
      const vtype = (s.camera_motion && 'image') || (s.visual && s.visual.type) || s.visual_type || '';
      const beat = s.beat || '(no beat)';
      return `<div class="outline-row" data-idx="${scenes.indexOf(s)}" data-edit-token="@${s.id}">
        <span class="outline-id">${s.id}</span>
        <span class="outline-dur">${Math.round(s.duration_sec || 0)}s</span>
        <span class="outline-vtype">${vtype}</span>
        <span class="outline-beat" data-edit-token="@${s.id}/beat">${beat}</span>
      </div>`;
    }).join('');
    return `<div class="outline-band">
      <div class="outline-band-hdr">${band.section} · ${band.scenes.length} scenes · ${Math.round(dur)}s</div>
      ${rows}
    </div>`;
  }).join('');
  return `<details class="outline-panel" open>
    <summary class="outline-summary">Storyline outline</summary>
    ${bandHtml}
  </details>`;
}
```

- [ ] **Step 2: Render the panel in `makeDetailRow`**

In `makeDetailRow` (line 438+), insert the outline panel just before the scene strip. Find the line:

```javascript
    ${p.scenes && p.scenes.length ? buildSceneStrip(p) : ''}
```

Change it to:

```javascript
    ${p.scenes && p.scenes.length ? buildOutlinePanel(p) : ''}
    ${p.scenes && p.scenes.length ? buildSceneStrip(p) : ''}
```

- [ ] **Step 3: Add styles**

In the `<style>` block of `index.html`, add:

```css
.outline-panel { margin:8px 0; border:1px solid #1e293b; border-radius:4px; background:#0f172a; }
.outline-summary { cursor:pointer; padding:6px 10px; font-size:11px; color:#93c5fd; text-transform:uppercase; letter-spacing:.06em; }
.outline-band { border-top:1px solid #1e293b; }
.outline-band-hdr { padding:4px 10px; font-size:10px; color:#64748b; text-transform:uppercase; letter-spacing:.05em; background:#111827; }
.outline-row { display:grid; grid-template-columns:48px 40px 90px 1fr; gap:8px; padding:3px 10px; font-size:12px; color:#cbd5e1; align-items:baseline; }
.outline-row:hover { background:#1e293b; }
.outline-id { font-family:monospace; color:#94a3b8; }
.outline-dur { color:#64748b; }
.outline-vtype { color:#475569; font-size:11px; }
.outline-beat { color:#e2e8f0; }
```

- [ ] **Step 4: Manual verification**

Start the dashboard if not running (`systemctl --user status content-dashboard`; restart with `dashrs` if needed). Open `https://dashboard.keeppro.io`, expand the baby-walker project. Verify:
- An "Storyline outline" panel appears above the scene strip.
- Scenes are grouped into section bands (hook / context / …) with scene count + duration in each header.
- Each row shows `id · duration · visual type · beat`.

If you cannot reach the dashboard in this environment, say so explicitly and leave this step unchecked for the user to verify.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/dashboard/static/index.html
git commit -m "feat(dashboard): add storyline outline panel grouped by section"
```

---

### Task 10: Locale switcher + audio-swap preview

**Files:**
- Modify: `src/pipeline/dashboard/static/index.html` — locale tabs, audio-swap wiring, locale-aware `showSceneNar`
- Manual verification (in-browser)

- [ ] **Step 1: Render locale tabs in `makeDetailRow`**

In `makeDetailRow`, after the `tabsHtml` (variant tabs) block (line 447), add a locale tab row. Insert this just before `${tabsHtml}`:

```javascript
  const locales = p.locales && p.locales.length ? p.locales : [p.locale];
  const localeTabsHtml = locales.length > 1
    ? `<div class="locale-tabs">${locales.map((loc, i) =>
        `<button class="btn-locale${i===0?' active':''}" data-locale="${loc}">${loc}</button>`
      ).join('')}</div>`
    : '';
```

Then in the returned HTML, add `${localeTabsHtml}` on its own line right after `${tabsHtml}`. Also add a hidden `<audio>` element right after the `<video ...>` element:

```javascript
    <video controls src="${firstUrl}" data-edit-token="@s1/visual"></video>
    <audio class="locale-audio" hidden></audio>
```

- [ ] **Step 2: Wire locale switching**

In `toggleDetail`, after the existing `.btn-variant` wiring block (around line 619), add locale-tab wiring. The active locale is held in a closure variable:

```javascript
  let activeLocale = (p.locales && p.locales[0]) || p.locale;
  const localeAudio = detailRow.querySelector('.locale-audio');

  detailRow.querySelectorAll('.btn-locale').forEach(btn => {
    btn.addEventListener('click', () => {
      detailRow.querySelectorAll('.btn-locale').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeLocale = btn.dataset.locale;
      const isPrimary = activeLocale === (p.primary_locale || p.locale);
      if (isPrimary) {
        videoEl.muted = false;
        localeAudio.hidden = true;
        localeAudio.pause();
        localeAudio.removeAttribute('src');
      } else {
        // Audio-swap: shared video plays muted, locale audio plays in sync.
        videoEl.muted = true;
        localeAudio.src = `/output/projects/${p.project_id}/audio/narration_${activeLocale}.mp3`;
        localeAudio.hidden = false;
        localeAudio.currentTime = videoEl.currentTime;
        if (!videoEl.paused) localeAudio.play();
      }
      // Refresh the currently shown scene panel in the new locale.
      const shownIdx = Number(detailRow.querySelector('.scene-chip.active')?.dataset.idx || 0);
      showSceneNar(shownIdx);
    });
  });

  // Keep the swapped audio synced to the video.
  videoEl.addEventListener('play', () => { if (!localeAudio.hidden) localeAudio.play(); });
  videoEl.addEventListener('pause', () => { if (!localeAudio.hidden) localeAudio.pause(); });
  videoEl.addEventListener('seeked', () => { if (!localeAudio.hidden) localeAudio.currentTime = videoEl.currentTime; });
```

- [ ] **Step 3: Make `showSceneNar` locale-aware**

Replace the body of `showSceneNar` (lines 603-616) so it reads the active locale's narration from `narration_by_locale`:

```javascript
  function showSceneNar(idx) {
    const scene = p.scenes[idx];
    const mm = Math.floor(scene.start_sec / 60);
    const ss = String(Math.floor(scene.start_sec % 60)).padStart(2, '0');
    const stamp = `${scene.id} · ${scene.section} · ${mm}:${ss}`;
    const narMap = scene.narration_by_locale || {};
    const text = narMap[activeLocale] || scene.narration || '—';
    narHdr.textContent = `${stamp} · ${activeLocale}`;
    narText.textContent = text;
    subHdr.textContent = stamp;
    subText.textContent = scene.subtitle || '—';
    narPanel?.setAttribute('data-edit-token', `@${scene.id}/narration/${activeLocale}`);
    subPanel?.setAttribute('data-edit-token', `@${scene.id}/subtitle`);
    sourceBtn?.setAttribute('data-edit-token', `@${scene.id}/narration/${activeLocale}`);
    videoEl?.setAttribute('data-edit-token', `@${scene.id}/visual`);
  }
```

- [ ] **Step 4: Add styles for locale tabs**

In the `<style>` block, add (mirror the existing `.btn-variant` styles — read them first and reuse the look):

```css
.locale-tabs { display:flex; gap:4px; margin:4px 0; }
.btn-locale { font-size:11px; padding:3px 10px; border-radius:4px; border:1px solid #2d3748; background:#1e293b; color:#94a3b8; cursor:pointer; }
.btn-locale.active { background:#1e3a5f; border-color:#3b82f6; color:#e2e8f0; }
```

- [ ] **Step 5: Manual verification**

In the browser, expand baby-walker:
- Locale tabs (`zh-TW`, `en`) appear near the variant tabs.
- Click `en`: the video mutes, `narration_en.mp3` plays in sync, the narration panel shows English text and its header says `en`.
- Click a scene chip: the narration panel shows that scene's English narration.
- Click `zh-TW`: video audio returns, panels show Chinese.

If the dashboard is unreachable here, say so and leave unchecked.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/dashboard/static/index.html
git commit -m "feat(dashboard): add locale switcher with audio-swap preview"
```

---

### Task 11: Locale-aware narration edits in the mutation runtime

**Files:**
- Modify: `src/pipeline/dashboard/mutation_runtime.py:262` and surrounding edit-token routing
- Test: `tests/unit/test_dashboard_server.py` or `tests/unit/test_dashboard_draft_endpoints.py` (match where mutation routing is tested)

The new edit token `@<scene>/narration/<locale>` must route to a narration edit scoped to that locale: editing the primary locale writes `scene.narration`; editing a secondary locale writes `scene.narration_alt[locale]`.

- [ ] **Step 1: Read the current routing**

Read `src/pipeline/dashboard/mutation_runtime.py` around lines 120-270. Identify how an edit token like `@s1/narration` is parsed into a field and how `scene.narration = args["text"]` (line 262) is reached. Note the parsing function and the args structure.

- [ ] **Step 2: Write the failing test**

Add to the test file that covers mutation application (search `tests/unit/` for the test that exercises `scene.narration` assignment — likely `test_dashboard_server.py`). Add:

```python
def test_narration_edit_routes_by_locale():
    from pipeline.dashboard.mutation_runtime import apply_narration_edit
    from pipeline.storyboard import Scene

    scene = Scene(id="s1", section="hook", narration="primary",
                  narration_est_sec=5.0, narration_alt={"en": "english"})

    apply_narration_edit(scene, locale="zh-TW", primary_locale="zh-TW", text="new primary")
    assert scene.narration == "new primary"
    assert scene.narration_alt["en"] == "english"

    apply_narration_edit(scene, locale="en", primary_locale="zh-TW", text="new english")
    assert scene.narration == "new primary"
    assert scene.narration_alt["en"] == "new english"
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_dashboard_server.py -k narration_edit_routes -v`
Expected: FAIL — `apply_narration_edit` not defined.

- [ ] **Step 4: Implement `apply_narration_edit` and route to it**

In `src/pipeline/dashboard/mutation_runtime.py`, add:

```python
def apply_narration_edit(scene, locale: str, primary_locale: str, text: str) -> None:
    """Write narration text for a locale onto a Scene."""
    if locale == primary_locale:
        scene.narration = text
    else:
        scene.narration_alt[locale] = text
```

Then update the edit-token routing. Where `@<scene>/narration` is currently parsed, also accept the `@<scene>/narration/<locale>` form: split the token on `/`, and if a third segment exists treat it as the locale. At the call site that currently does `scene.narration = args["text"]` (line 262), replace with:

```python
        locale = args.get("locale") or storyboard.primary_locale
        apply_narration_edit(scene, locale, storyboard.primary_locale, args["text"])
```

Ensure the parser puts the locale segment into `args["locale"]`. If the routing has no access to `storyboard.primary_locale` at that point, load it from the storyboard object already in scope (the runtime loads the storyboard to mutate it — use that instance's `.primary_locale`).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_dashboard_server.py tests/unit/test_dashboard_draft_endpoints.py -v`
Expected: PASS. Fix any pre-existing mutation test that assumed a locale-blind `@s1/narration` token — it should still work (falls back to `primary_locale`).

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/dashboard/mutation_runtime.py tests/unit/test_dashboard_server.py
git commit -m "feat(dashboard): route narration edits by locale"
```

---

## Final Verification

- [ ] **Run the full test suite**

Run: `uv run pytest`
Expected: PASS. Investigate and fix any failure before proceeding.

- [ ] **Run lint and type checks**

Run: `uv run ruff check src/ tests/ && uv run mypy src/`
Expected: clean. Fix any issue introduced by this work.

- [ ] **End-to-end smoke on baby-walker**

The baby-walker storyboard is already migrated (Tasks 3/3b). Confirm the dashboard renders it: outline panel grouped by section, locale tabs `zh-TW`/`en`, audio-swap works. If the dashboard is unreachable in this environment, report that explicitly rather than claiming success.

- [ ] **Update the workflow diagram** — `docs/workflows.html` references the stage chain. The chain changed (added `scriptwrite`). Per `CLAUDE.md`, **ask the user before updating `docs/workflows.html`.**

---

## Notes for the implementer

- **TDD discipline:** every task writes the failing test first, watches it fail, then implements. Do not skip the "verify it fails" step.
- **Commit per task** — the plan commits after each task so a bad task is easy to revert.
- **`scene.narration` stays a `str`** — this is deliberate (low blast radius). Only secondary locales live in `narration_alt`. Do not "improve" this into a single dict; ~15 call sites depend on `scene.narration` being a string.
- **No new locales** — `LOCALE_INSTRUCTIONS` already covers zh-TW / en / ja / es-MX. Do not add more.
- **Out of scope** (do not implement): scene reordering, separate per-locale video renders, changes to the MLA upload workflow.
