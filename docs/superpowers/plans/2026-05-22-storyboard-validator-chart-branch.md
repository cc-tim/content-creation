# Sprint 4 — Storyboard validator: chart branch + `pipeline validate` CLI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote chart schema validation from render-time-only into the storyboard-write-time validator, and expose the validator as a standalone `pipeline validate <project-id>` CLI so an edited storyboard can be re-checked without rerunning `direct`.

**Architecture:** Refactor `composer/chart.py:_validate_chart` into a pure list-returning `validate_chart_visual(visual, scene_id, duration_sec=None) -> list[str]` and keep the existing raising path as a thin wrapper (defense-in-depth). Add a `chart` branch in `director/storyboard_validator.py:_validate_scene` that calls the pure function and wraps each issue as a `SceneValidationError`. Add a new top-level Typer subcommand `pipeline validate <project-id>` that loads the saved storyboard and prints the existing `format_visual_decision_table`, exiting 0/1/2 by outcome.

**Tech Stack:** Python 3.11+, Typer (existing CLI framework), dataclasses, `pytest`, `typer.testing.CliRunner`. No new dependencies.

---

## Context

### Why this sprint exists
- A chart authoring mistake (`chart_type: "lne"`, missing `data`, `reveal_duration_sec > duration − 0.5s`) currently survives the `direct`-stage validator because `_validate_scene` has no `chart` branch. It only fails ~30 min later when `composer/chart.py:_validate_chart` raises mid-compose.
- Post-proofread or post-manual-edit, there is no command to re-validate; the only option today is to rerun `direct`, which regenerates the storyboard and defeats manual edits.

### What already exists (do not rebuild)
- `src/pipeline/director/storyboard_validator.py` (599 lines): per-type validators for `article_image`/`image`, `slide`, `rich_slide`, `generated_image`, `text_card`, `clip`, `still_frame`, `namecard`, `map` + `validate_storyboard()` + `visual_decisions_for_storyboard()` + `format_visual_decision_table()` + `raise_for_validation_errors()`. Wired into `stages/direct.py:698–710`.
- `src/pipeline/composer/chart.py:_validate_chart()` (lines 53–163): raises `ValueError` on first issue. Covers `chart_type` enum, per-type schema (`stat_big_number` length, `bar` xy parity, `comparison` sides, `proportion_blocks.ratio`, `timeline` non-empty list, `line` points/markers shape), and animate-block (variant whitelist, easing, `reveal_duration_sec ≤ duration_sec - HOLD_TAIL_MIN_SEC`).
- `tests/director/test_storyboard_validator.py` (185 lines, 9 tests): covers `article_image`/`slide`/`generated_image`/`clip` + decision-table formatting. No `chart` coverage.

### Storyboard filename note
- `stages/direct.py:694` saves to `storyboard_{ctx.locale}.json`.
- However, real projects on disk (e.g. `20260504-115232-baby-walker-story/storyboard.json`) have NO locale suffix — older projects + the style CLI both use `storyboard.json`.
- **The CLI must auto-discover BOTH patterns:** look for `storyboard.json` first, then `storyboard_*.json`. If multiple match, require `--locale`. If none, exit 1.

### Greenlit decisions (from `.agent-memory/engineering-manager/sprint-log.md` Sprint 4 GREENLIT entry)
1. Chart schema lives in `composer/chart.py` (validator imports it). Composer is source of truth.
2. CLI surface = top-level `pipeline validate <project-id>` (verb-first).
3. Exit codes: 0 clean / 1 load-failure / 2 validation-errors.
4. Locale = auto-discover lone `storyboard.json` / `storyboard_<locale>.json`; require `--locale` if multiple.
5. Smoke tests for un-tested existing branches (rich_slide/text_card/still_frame/namecard/map) included.

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/pipeline/composer/chart.py` | Add `validate_chart_visual(visual, scene_id, duration_sec=None) -> list[str]` returning issue strings; rewrite `_validate_chart()` as a thin raise-on-first-issue wrapper |
| Modify | `src/pipeline/director/storyboard_validator.py` | Add `_validate_chart` dispatch branch in `_validate_scene`; calls `validate_chart_visual`, wraps issues as `SceneValidationError(severity="error")` |
| Create | `src/pipeline/cli_validate.py` | Typer `validate_app`: `pipeline validate <project-id> [--locale]`; auto-discovers storyboard file; prints `format_visual_decision_table`; exits 0/1/2 |
| Modify | `src/pipeline/cli.py` | Import `validate_app`; register via `app.add_typer(validate_app, name="validate")` |
| Modify | `tests/director/test_storyboard_validator.py` | +12 chart-branch negative tests +1 happy-path +5 smoke tests for untested branches (rich_slide/text_card/still_frame/namecard/map) |
| Create | `tests/unit/test_cli_validate.py` | CLI smoke (clean exits 0; broken chart exits 2; missing project exits 1; multi-locale requires `--locale`; `--locale` override works) |

---

## Task 1: Extract `validate_chart_visual` as a pure list-returning function

**Files:**
- Modify: `src/pipeline/composer/chart.py:53–163` (replace `_validate_chart` body)
- Test: `tests/unit/test_chart.py` (existing — extend with new tests)

The refactor must preserve the render-time behavior: `_validate_chart` still raises on the first issue (back-compat for `render_chart` at line 227). The new `validate_chart_visual` returns ALL issues (for the validator branch).

- [ ] **Step 1: Add a failing test for `validate_chart_visual` returning a list**

Add to `tests/unit/test_chart.py` (find an existing import block and extend; otherwise add after existing imports):

```python
def test_validate_chart_visual_returns_empty_list_for_valid_input():
    from pipeline.composer.chart import validate_chart_visual

    visual = {
        "type": "chart",
        "chart_type": "stat_big_number",
        "data": {"value": "230,676"},
    }
    issues = validate_chart_visual(visual, "s1")
    assert issues == []


def test_validate_chart_visual_returns_all_issues_not_just_first():
    from pipeline.composer.chart import validate_chart_visual

    # Two independent issues: too-long stat value AND animate on unsupported variant
    visual = {
        "type": "chart",
        "chart_type": "stat_big_number",
        "data": {"value": "12345678901234"},  # > 8 chars
        "animate": {"enabled": True, "easing": "bogus_easing"},
    }
    issues = validate_chart_visual(visual, "s1", duration_sec=10.0)
    assert len(issues) >= 2
    assert any("> 8 chars" in i for i in issues)
    assert any("easing" in i for i in issues)


def test_validate_chart_visual_returns_issue_strings_not_raises():
    from pipeline.composer.chart import validate_chart_visual

    visual = {"type": "chart"}  # missing chart_type
    # Must NOT raise
    issues = validate_chart_visual(visual, "s1")
    assert len(issues) == 1
    assert "chart_type" in issues[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_chart.py::test_validate_chart_visual_returns_empty_list_for_valid_input tests/unit/test_chart.py::test_validate_chart_visual_returns_all_issues_not_just_first tests/unit/test_chart.py::test_validate_chart_visual_returns_issue_strings_not_raises -v`

Expected: 3 FAIL (ImportError: cannot import name 'validate_chart_visual').

- [ ] **Step 3: Implement `validate_chart_visual` and refactor `_validate_chart`**

Replace lines 53–163 of `src/pipeline/composer/chart.py` with the following. The new public function returns a list; the old name remains as a raise-on-first-issue wrapper for back-compat with `render_chart`.

```python
def validate_chart_visual(
    visual: dict[str, Any],
    scene_id: str,
    duration_sec: float | None = None,
) -> list[str]:
    """Return all chart schema issues as strings; does not raise.

    The storyboard-write-time validator uses this to surface multiple problems
    in one pass. ``_validate_chart`` below wraps this and raises on the first
    issue for render-time defense-in-depth.

    When ``duration_sec`` is provided AND ``visual.animate.enabled`` is true,
    also validates the animate block (variant support, easing name, duration
    ceiling). The duration ceiling is the in-code expression of the two-axes
    rule: animation is a visual-quality lift, never a runtime extender.
    """
    issues: list[str] = []
    chart_type = visual.get("chart_type")
    if not chart_type:
        issues.append(
            f"chart {scene_id}: missing 'chart_type' (one of {sorted(CHART_TYPES)})"
        )
        return issues  # downstream schema checks need chart_type
    if chart_type not in CHART_TYPES:
        issues.append(
            f"chart {scene_id}: unknown chart_type={chart_type!r}; "
            f"use one of {sorted(CHART_TYPES)}"
        )
        return issues  # don't try schema-checks against an unknown type

    data = visual.get("data")
    if not data:
        issues.append(
            f"chart {scene_id}: missing 'data' for chart_type={chart_type!r}"
        )
        # Schema checks below would all blow up on None — return here.
        return issues + _validate_animate(visual, scene_id, chart_type, duration_sec)

    if chart_type == "stat_big_number":
        value = str(data.get("value", ""))
        if not value:
            issues.append(f"chart {scene_id}: stat_big_number needs data.value")
        elif len(value) > 8:
            issues.append(
                f"chart {scene_id}: stat_big_number value {value!r} > 8 chars "
                f"(won't fit big serif); shorten or use a bar/timeline."
            )
    elif chart_type == "bar":
        x, y = data.get("x"), data.get("y")
        if not isinstance(x, list) or not isinstance(y, list) or len(x) != len(y) or not x:
            issues.append(
                f"chart {scene_id}: bar data needs equal-length non-empty 'x' and 'y' "
                f"lists; got x={x!r} y={y!r}"
            )
    elif chart_type == "comparison":
        for side_name in ("left", "right"):
            side = data.get(side_name)
            if not isinstance(side, dict) or "label" not in side or "value" not in side:
                issues.append(
                    f"chart {scene_id}: comparison needs {side_name} with "
                    f"'label' and 'value'"
                )
    elif chart_type == "proportion_blocks":
        if "ratio" not in data:
            issues.append(
                f"chart {scene_id}: proportion_blocks needs data.ratio (0..1)"
            )
    elif chart_type == "timeline":
        if not isinstance(data, list) or not data:
            issues.append(
                f"chart {scene_id}: timeline data must be a non-empty list of "
                f"{{year, label}} entries"
            )
    elif chart_type == "line":
        points = data.get("points")
        if not isinstance(points, list) or not points:
            issues.append(
                f"chart {scene_id}: line data needs non-empty 'points' list of "
                f"{{x, y}} entries; got {points!r}"
            )
        else:
            for i, p in enumerate(points):
                if not isinstance(p, dict) or "x" not in p or "y" not in p:
                    issues.append(
                        f"chart {scene_id}: line points[{i}] must be {{x, y}}; got {p!r}"
                    )
        markers = data.get("markers") or []
        if not isinstance(markers, list):
            issues.append(
                f"chart {scene_id}: line 'markers' must be a list; got {markers!r}"
            )
        else:
            for i, m in enumerate(markers):
                if not isinstance(m, dict) or "x" not in m:
                    issues.append(
                        f"chart {scene_id}: line marker[{i}] must be {{x, label}}; "
                        f"got {m!r}"
                    )

    issues.extend(_validate_animate(visual, scene_id, chart_type, duration_sec))
    return issues


def _validate_animate(
    visual: dict[str, Any],
    scene_id: str,
    chart_type: str,
    duration_sec: float | None,
) -> list[str]:
    """Animate-block validation; returns issues without raising."""
    out: list[str] = []
    animate = visual.get("animate") or {}
    if not animate.get("enabled"):
        return out

    if chart_type not in {"line", "bar", "stat_big_number"}:
        out.append(
            f"chart {scene_id}: chart_type={chart_type!r} has no animated "
            f"variant (supported: line, bar, stat_big_number); set "
            f"animate.enabled=false or pick a supported chart_type"
        )
    from pipeline.composer.chart_anim import EASING, HOLD_TAIL_MIN_SEC
    easing_name = animate.get("easing", "ease_out_cubic")
    if easing_name not in EASING:
        out.append(
            f"chart {scene_id}: unknown easing {easing_name!r}; "
            f"use one of {sorted(EASING)}"
        )
    if duration_sec is not None:
        reveal = animate.get("reveal_duration_sec")
        if reveal is not None and float(reveal) > duration_sec - HOLD_TAIL_MIN_SEC:
            out.append(
                f"chart {scene_id}: reveal_duration_sec={reveal} > "
                f"duration_sec({duration_sec}) - hold_tail({HOLD_TAIL_MIN_SEC}); "
                f"shorten the reveal — animation cannot extend the scene "
                f"(two-axes rule: arsenal items do not add runtime)"
            )
    return out


def _validate_chart(
    visual: dict[str, Any],
    scene_id: str,
    duration_sec: float | None = None,
) -> None:
    """Render-time wrapper: raise on first issue. Defense-in-depth.

    The storyboard-write-time validator (`director/storyboard_validator.py`)
    should catch chart schema problems earlier via `validate_chart_visual`;
    this wrapper ensures `render_chart` still fails loud if a bad chart
    slips through (e.g. a programmatic caller that bypasses the storyboard
    validator).
    """
    issues = validate_chart_visual(visual, scene_id, duration_sec=duration_sec)
    if issues:
        raise ValueError(issues[0])
```

- [ ] **Step 4: Run the new tests and verify they pass**

Run: `uv run pytest tests/unit/test_chart.py::test_validate_chart_visual_returns_empty_list_for_valid_input tests/unit/test_chart.py::test_validate_chart_visual_returns_all_issues_not_just_first tests/unit/test_chart.py::test_validate_chart_visual_returns_issue_strings_not_raises -v`

Expected: 3 PASS.

- [ ] **Step 5: Run the full chart test file to verify back-compat (existing `_validate_chart` callers still see raises)**

Run: `uv run pytest tests/unit/test_chart.py tests/unit/test_chart_anim.py -v`

Expected: all existing tests still pass (the render-time wrapper still raises with the same message format).

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/composer/chart.py tests/unit/test_chart.py
git commit -m "refactor(chart): extract validate_chart_visual as list-returning pure function

Pre-Sprint 4 (E5) refactor: the storyboard-write-time validator needs to
surface all chart issues at once, not just the first. Extract the schema
checks into validate_chart_visual(visual, scene_id, duration_sec=None) ->
list[str]; keep _validate_chart() as a thin wrapper that raises on the
first issue for render-time defense-in-depth."
```

---

## Task 2: Add `chart` branch in `storyboard_validator._validate_scene`

**Files:**
- Modify: `src/pipeline/director/storyboard_validator.py` (extend `_validate_scene` + add `_validate_chart` helper)
- Test: `tests/director/test_storyboard_validator.py` (extend with chart-branch tests)

The validator must call `validate_chart_visual` for chart visuals. Each returned string becomes a `SceneValidationError(severity="error")`. The validator does not have access to scene `duration_sec` from `Scene` directly — pass `scene.narration_est_sec` as the duration estimate so the animate-duration check is meaningful.

- [ ] **Step 1: Add failing chart-branch tests in `test_storyboard_validator.py`**

Append to `tests/director/test_storyboard_validator.py` (after the existing tests; preserve the `_scene` / `_errors` helpers already defined at the top):

```python
# ── chart visual: schema validation ────────────────────────────────────────


def test_chart_missing_chart_type_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[_scene("s1", {"type": "chart"})])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any("chart_type" in i.issue for i in errs)
    assert all(i.scene_id == "s1" for i in errs)


def test_chart_unknown_chart_type_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[_scene("s1", {"type": "chart", "chart_type": "lne"})])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any("unknown chart_type" in i.issue and "lne" in i.issue for i in errs)


def test_chart_missing_data_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[
        _scene("s1", {"type": "chart", "chart_type": "bar"}),
    ])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any("missing 'data'" in i.issue for i in errs)


def test_chart_stat_big_number_value_too_long_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[
        _scene("s1", {
            "type": "chart",
            "chart_type": "stat_big_number",
            "data": {"value": "12,345,678,901"},
        }),
    ])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any("> 8 chars" in i.issue for i in errs)


def test_chart_bar_uneven_xy_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[
        _scene("s1", {
            "type": "chart",
            "chart_type": "bar",
            "data": {"x": ["a", "b"], "y": [1]},
        }),
    ])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any("equal-length" in i.issue for i in errs)


def test_chart_comparison_missing_side_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[
        _scene("s1", {
            "type": "chart",
            "chart_type": "comparison",
            "data": {"left": {"label": "L", "value": "1"}},  # right missing
        }),
    ])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any("right" in i.issue and "label" in i.issue for i in errs)


def test_chart_line_malformed_points_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[
        _scene("s1", {
            "type": "chart",
            "chart_type": "line",
            "data": {"points": [{"x": 1990}]},  # missing y
        }),
    ])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any("points[0] must be {x, y}" in i.issue for i in errs)


def test_chart_line_malformed_markers_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[
        _scene("s1", {
            "type": "chart",
            "chart_type": "line",
            "data": {
                "points": [{"x": 1990, "y": 100}, {"x": 2000, "y": 50}],
                "markers": [{"label": "no x"}],  # missing x
            },
        }),
    ])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any("marker[0]" in i.issue for i in errs)


def test_chart_animate_unsupported_variant_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[
        _scene("s1", {
            "type": "chart",
            "chart_type": "timeline",
            "data": [{"year": 1990, "label": "a"}],
            "animate": {"enabled": True},
        }),
    ])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any("no animated" in i.issue for i in errs)


def test_chart_animate_unknown_easing_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[
        _scene("s1", {
            "type": "chart",
            "chart_type": "bar",
            "data": {"x": ["a"], "y": [1]},
            "animate": {"enabled": True, "easing": "bouncy"},
        }),
    ])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any("unknown easing" in i.issue and "bouncy" in i.issue for i in errs)


def test_chart_animate_reveal_exceeds_duration_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    # Scene est duration = 5s; reveal_duration_sec = 6.0s > 5 - 0.5 = 4.5
    sb = Storyboard(scenes=[
        _scene("s1", {
            "type": "chart",
            "chart_type": "bar",
            "data": {"x": ["a"], "y": [1]},
            "animate": {"enabled": True, "reveal_duration_sec": 6.0},
        }),
    ])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any(
        "reveal_duration_sec=6.0" in i.issue and "hold_tail" in i.issue
        for i in errs
    )


def test_chart_valid_returns_no_issues(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[
        _scene("s1", {
            "type": "chart",
            "chart_type": "line",
            "data": {
                "points": [{"x": 1990, "y": 100}, {"x": 2000, "y": 50}],
                "markers": [{"x": 1995, "label": "regulation"}],
            },
            "animate": {"enabled": True, "reveal_duration_sec": 3.0},
        }),
    ])
    issues = validate_storyboard(sb, tmp_path)
    assert _errors(issues) == []
```

- [ ] **Step 2: Run new tests to verify they fail (no chart branch yet)**

Run: `uv run pytest tests/director/test_storyboard_validator.py -k "chart" -v`

Expected: most pass if `validate_storyboard` ignores unknown types — but the `unknown_chart_type` test should fail because the current `_validate_scene` falls through chart silently (the `visual_type not in VISUAL_TYPES` check returns early on truly-unknown types, but `chart` IS in VISUAL_TYPES so the function falls through with no branch).

Actually, the current behavior is: when `visual_type == "chart"`, no branch matches in `_validate_scene` (lines 192–222), so an empty `issues` list is returned. This means ALL the new chart tests will fail with `assert any(...) for i in errs` because `errs` is empty.

Expected: 12 FAIL (`assert any(...)` against empty list).

- [ ] **Step 3: Add `_validate_chart` helper and dispatch branch in `storyboard_validator.py`**

Open `src/pipeline/director/storyboard_validator.py` and:

A) Add this helper function near the other `_validate_*` helpers (after `_validate_text_card` is a logical place, around line 417):

```python
def _validate_chart_visual(scene: Scene, visual: dict[str, Any]) -> list[SceneValidationError]:
    """Promote composer/chart.py:validate_chart_visual into validator errors."""
    from pipeline.composer.chart import validate_chart_visual

    duration: float | None = None
    if scene.narration_est_sec:
        duration = float(scene.narration_est_sec)

    issues_text = validate_chart_visual(visual, scene.id, duration_sec=duration)
    out: list[SceneValidationError] = []
    for msg in issues_text:
        out.append(_issue(
            scene,
            "error",
            "visual",
            msg,
            "Fix the chart schema; see composer/chart.py:CHART_TYPES for valid types.",
        ))
    return out
```

B) Find the `_validate_scene` dispatch (line 192–222), and add a `chart` branch. The current code is:

```python
    if visual_type in _IMAGE_TYPES:
        issues.extend(_validate_image_visual(scene, visual, project_root))
    elif visual_type == "slide":
        issues.extend(_validate_slide(scene, visual))
    elif visual_type == "rich_slide":
        issues.extend(_validate_rich_slide(scene, visual))
    elif visual_type == "generated_image":
        issues.extend(_validate_generated_image(scene, visual))
    elif visual_type == "text_card":
        issues.extend(_validate_text_card(scene, visual))
    elif visual_type == "clip":
        issues.extend(_validate_clip(scene, visual, project_root))
    elif visual_type == "still_frame":
        issues.extend(_validate_still_frame(scene, visual, project_root))
    elif visual_type == "namecard" and not str(visual.get("name") or "").strip():
```

Insert a chart branch after `still_frame` and before `namecard`:

```python
    if visual_type in _IMAGE_TYPES:
        issues.extend(_validate_image_visual(scene, visual, project_root))
    elif visual_type == "slide":
        issues.extend(_validate_slide(scene, visual))
    elif visual_type == "rich_slide":
        issues.extend(_validate_rich_slide(scene, visual))
    elif visual_type == "generated_image":
        issues.extend(_validate_generated_image(scene, visual))
    elif visual_type == "text_card":
        issues.extend(_validate_text_card(scene, visual))
    elif visual_type == "clip":
        issues.extend(_validate_clip(scene, visual, project_root))
    elif visual_type == "still_frame":
        issues.extend(_validate_still_frame(scene, visual, project_root))
    elif visual_type == "chart":
        issues.extend(_validate_chart_visual(scene, visual))
    elif visual_type == "namecard" and not str(visual.get("name") or "").strip():
```

- [ ] **Step 4: Run the new chart tests and verify they pass**

Run: `uv run pytest tests/director/test_storyboard_validator.py -k "chart" -v`

Expected: 12 PASS.

- [ ] **Step 5: Run the full validator test file to check no regression**

Run: `uv run pytest tests/director/test_storyboard_validator.py -v`

Expected: all original 9 + new 12 = 21+ tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/director/storyboard_validator.py tests/director/test_storyboard_validator.py
git commit -m "feat(validator): add chart visual branch using validate_chart_visual

Chart authoring mistakes (unknown chart_type, missing data, malformed
schema, animate-block violations) now fire at storyboard-write time,
not 30 min into compose. The validator wraps each issue returned by
composer/chart.py:validate_chart_visual as a SceneValidationError with
severity=error. Render-time wrapper in chart.py still raises for
defense-in-depth."
```

---

## Task 3: Add smoke tests for previously-untested validator branches

**Files:**
- Modify: `tests/director/test_storyboard_validator.py` (add 5 smoke tests)

The validator already handles `rich_slide`, `text_card`, `still_frame`, `namecard`, and `map` but has no tests for them. The file is open from Task 2 — lock current behavior with one happy-path + one error per branch.

- [ ] **Step 1: Add smoke tests**

Append to `tests/director/test_storyboard_validator.py`:

```python
# ── existing-branch smoke tests (lock current behavior) ────────────────────


def test_rich_slide_empty_text_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[_scene("s1", {"type": "rich_slide"})])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any(i.field == "visual.text" for i in errs)


def test_text_card_empty_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[_scene("s1", {"type": "text_card", "text": ""})])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any(i.field == "visual.text" for i in errs)


def test_still_frame_missing_source_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[
        _scene("s1", {"type": "still_frame", "timestamp_sec": 1.0}),
    ])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any(i.field == "visual.source" for i in errs)


def test_namecard_missing_name_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[_scene("s1", {"type": "namecard"})])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any(i.field == "visual.name" for i in errs)


def test_map_missing_query_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[_scene("s1", {"type": "map"})])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any(i.field == "visual.query" for i in errs)
```

- [ ] **Step 2: Run new smoke tests**

Run: `uv run pytest tests/director/test_storyboard_validator.py -k "rich_slide or text_card or still_frame or namecard or map" -v`

Expected: 5 PASS (these test pre-existing validator branches that were never covered).

- [ ] **Step 3: Run the full validator test file**

Run: `uv run pytest tests/director/test_storyboard_validator.py -v`

Expected: 21 + 5 = 26 tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/director/test_storyboard_validator.py
git commit -m "test(validator): add smoke tests for rich_slide/text_card/still_frame/namecard/map

The validator already covers these branches but had no test coverage —
lock current behavior with one error test per branch."
```

---

## Task 4: Create `cli_validate.py` with `pipeline validate` command

**Files:**
- Create: `src/pipeline/cli_validate.py`
- Test: `tests/unit/test_cli_validate.py`

The CLI loads the storyboard for a project, runs `format_visual_decision_table` + `raise_for_validation_errors`, prints the table, and exits with the right code. Storyboard auto-discovery: prefer `storyboard.json`; if absent, look for `storyboard_*.json`; if exactly one, use it; if multiple, require `--locale`. Pattern mirrors `src/pipeline/style/cli.py`.

- [ ] **Step 1: Write the failing CLI smoke tests**

Create `tests/unit/test_cli_validate.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pipeline.cli_validate import validate_app


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a project dir under a temp OUTPUT_DIR and switch OUTPUT_DIR there."""
    output = tmp_path / "output"
    project_id = "20990101-000000-test-project"
    pdir = output / "projects" / project_id
    pdir.mkdir(parents=True)
    # cli_validate reads OUTPUT_DIR via PipelineConfig() at call time
    monkeypatch.setenv("OUTPUT_DIR", str(output))
    return pdir


def _write_storyboard(pdir: Path, scenes: list[dict], filename: str = "storyboard.json") -> Path:
    payload = {"scenes": scenes, "theme": {}}
    sb = pdir / filename
    sb.write_text(json.dumps(payload), encoding="utf-8")
    return sb


def test_validate_clean_storyboard_exits_zero(project_dir: Path) -> None:
    _write_storyboard(project_dir, [
        {
            "id": "s1",
            "section": "hook",
            "narration": "ok",
            "narration_est_sec": 5,
            "visual": {"type": "text_card", "text": "hi"},
        },
    ])
    runner = CliRunner()
    result = runner.invoke(validate_app, ["--project-id", project_dir.name])
    assert result.exit_code == 0, result.output


def test_validate_broken_chart_exits_two(project_dir: Path) -> None:
    _write_storyboard(project_dir, [
        {
            "id": "s1",
            "section": "hook",
            "narration": "ok",
            "narration_est_sec": 5,
            "visual": {"type": "chart"},  # missing chart_type
        },
    ])
    runner = CliRunner()
    result = runner.invoke(validate_app, ["--project-id", project_dir.name])
    assert result.exit_code == 2, result.output
    assert "chart_type" in result.output


def test_validate_missing_project_exits_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setenv("OUTPUT_DIR", str(output))
    runner = CliRunner()
    result = runner.invoke(validate_app, ["--project-id", "does-not-exist"])
    assert result.exit_code == 1, result.output


def test_validate_no_storyboard_exits_one(project_dir: Path) -> None:
    # project_dir exists, but no storyboard*.json
    runner = CliRunner()
    result = runner.invoke(validate_app, ["--project-id", project_dir.name])
    assert result.exit_code == 1, result.output
    assert "storyboard" in result.output.lower()


def test_validate_multiple_storyboards_requires_locale(project_dir: Path) -> None:
    _write_storyboard(project_dir, [
        {
            "id": "s1",
            "section": "hook",
            "narration": "ok",
            "narration_est_sec": 5,
            "visual": {"type": "text_card", "text": "hi"},
        },
    ], filename="storyboard_zh-TW.json")
    _write_storyboard(project_dir, [
        {
            "id": "s1",
            "section": "hook",
            "narration": "ok",
            "narration_est_sec": 5,
            "visual": {"type": "text_card", "text": "hi"},
        },
    ], filename="storyboard_ja.json")
    runner = CliRunner()
    result = runner.invoke(validate_app, ["--project-id", project_dir.name])
    assert result.exit_code == 1, result.output
    assert "--locale" in result.output


def test_validate_locale_override_picks_correct_file(project_dir: Path) -> None:
    _write_storyboard(project_dir, [
        {
            "id": "s1",
            "section": "hook",
            "narration": "ok",
            "narration_est_sec": 5,
            "visual": {"type": "text_card", "text": "hi"},
        },
    ], filename="storyboard_zh-TW.json")
    _write_storyboard(project_dir, [
        {
            "id": "s1",
            "section": "hook",
            "narration": "broken",
            "narration_est_sec": 5,
            "visual": {"type": "chart"},  # missing chart_type
        },
    ], filename="storyboard_ja.json")
    runner = CliRunner()
    # zh-TW is clean → exit 0
    result_zh = runner.invoke(
        validate_app, ["--project-id", project_dir.name, "--locale", "zh-TW"]
    )
    assert result_zh.exit_code == 0, result_zh.output
    # ja is broken → exit 2
    result_ja = runner.invoke(
        validate_app, ["--project-id", project_dir.name, "--locale", "ja"]
    )
    assert result_ja.exit_code == 2, result_ja.output


def test_validate_prefers_unsuffixed_storyboard_when_both_exist(project_dir: Path) -> None:
    """If both `storyboard.json` and `storyboard_<locale>.json` exist (mixed-vintage
    project), pick `storyboard.json` first — it's the canonical name used by compose."""
    _write_storyboard(project_dir, [
        {
            "id": "s1",
            "section": "hook",
            "narration": "canonical",
            "narration_est_sec": 5,
            "visual": {"type": "text_card", "text": "hi"},
        },
    ], filename="storyboard.json")
    _write_storyboard(project_dir, [
        {
            "id": "s1",
            "section": "hook",
            "narration": "broken locale",
            "narration_est_sec": 5,
            "visual": {"type": "chart"},  # would fail
        },
    ], filename="storyboard_ja.json")
    runner = CliRunner()
    result = runner.invoke(validate_app, ["--project-id", project_dir.name])
    # storyboard.json is clean → exit 0 (proves we picked it, not the broken locale)
    assert result.exit_code == 0, result.output
```

- [ ] **Step 2: Run the tests and verify they fail (ImportError)**

Run: `uv run pytest tests/unit/test_cli_validate.py -v`

Expected: all 7 FAIL with `ModuleNotFoundError: No module named 'pipeline.cli_validate'`.

- [ ] **Step 3: Write `src/pipeline/cli_validate.py`**

```python
"""pipeline validate — re-runs the storyboard validator on a saved project.

Wraps `pipeline.director.storyboard_validator.format_visual_decision_table`
+ `raise_for_validation_errors` so an edited storyboard can be re-checked
without rerunning `direct`. Exit codes match lint convention:

  0 — clean
  1 — load failure (missing project / missing storyboard / bad CLI usage)
  2 — validation errors found
"""
from __future__ import annotations

from pathlib import Path

import typer

from pipeline.config import PipelineConfig

validate_app = typer.Typer(help="Re-run the storyboard validator on a saved project.")


def _output_dir() -> Path:
    """Resolve OUTPUT_DIR at call time (env-overridable in tests)."""
    return PipelineConfig().OUTPUT_DIR


def _project_dir(project_id: str) -> Path:
    return _output_dir() / "projects" / project_id


def _discover_storyboard(pdir: Path, locale: str | None) -> Path | None:
    """Find the storyboard file to validate.

    Order of resolution:
    - Explicit ``--locale`` → ``storyboard_<locale>.json`` if it exists.
    - Otherwise prefer ``storyboard.json`` (canonical name used by compose).
    - Otherwise, if exactly one ``storyboard_*.json`` exists, use it.
    - If multiple locale files exist and no override, return None (caller
      raises with a "--locale required" message).
    - If nothing matches, return None (caller raises "no storyboard").
    """
    if locale is not None:
        candidate = pdir / f"storyboard_{locale}.json"
        return candidate if candidate.exists() else None

    canonical = pdir / "storyboard.json"
    if canonical.exists():
        return canonical

    locale_files = sorted(pdir.glob("storyboard_*.json"))
    if len(locale_files) == 1:
        return locale_files[0]
    if len(locale_files) > 1:
        return None  # signal "multiple, need --locale"
    return None  # signal "no storyboard at all"


@validate_app.callback(invoke_without_command=True)
def run(
    project_id: str = typer.Option(
        ..., "--project-id", help="Project ID (folder name under output/projects/)"
    ),
    locale: str | None = typer.Option(
        None,
        "--locale",
        help="Locale suffix when multiple storyboard_<locale>.json exist.",
    ),
) -> None:
    """Validate the saved storyboard for a project and print the decision table."""
    pdir = _project_dir(project_id)
    if not pdir.exists():
        typer.echo(f"Project not found: {pdir}", err=True)
        raise typer.Exit(1)

    sb_path = _discover_storyboard(pdir, locale)
    if sb_path is None:
        # Distinguish "multiple, need --locale" from "no storyboard at all"
        locale_files = sorted(pdir.glob("storyboard_*.json"))
        if len(locale_files) > 1:
            names = ", ".join(p.name for p in locale_files)
            typer.echo(
                f"Multiple storyboard files in {pdir}: {names}\n"
                f"Pass --locale <code> to pick one.",
                err=True,
            )
        else:
            typer.echo(f"No storyboard file in {pdir}.", err=True)
        raise typer.Exit(1)

    from pipeline.director.storyboard_validator import (
        format_visual_decision_table,
        validate_storyboard,
    )
    from pipeline.storyboard import Storyboard

    sb = Storyboard.load(sb_path)
    typer.echo(format_visual_decision_table(sb, pdir, project_id=project_id))

    errors = [
        issue for issue in validate_storyboard(sb, pdir) if issue.severity == "error"
    ]
    if errors:
        raise typer.Exit(2)
```

- [ ] **Step 4: Verify the tests pass against the new CLI module**

Run: `uv run pytest tests/unit/test_cli_validate.py -v`

Expected: 7 PASS.

If `test_validate_no_storyboard_exits_one` fails because `Storyboard.load` raises on an empty file or similar — the `_discover_storyboard` returns None first, so the `Storyboard.load` line is never reached. Confirm the order of operations in the implementation is "discover first, then load."

If `test_validate_locale_override_picks_correct_file` fails because the OUTPUT_DIR env var isn't being picked up by `PipelineConfig`, verify that `PipelineConfig` is a `pydantic_settings.BaseSettings` subclass that auto-reads env vars (line 7 of `src/pipeline/config.py`: `class PipelineConfig(BaseSettings)`).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/cli_validate.py tests/unit/test_cli_validate.py
git commit -m "feat(cli): add 'pipeline validate' command for storyboard re-validation

Loads a project's saved storyboard, prints the existing visual-decision
table from director/storyboard_validator.py, and exits non-zero on
validation errors. Auto-discovers storyboard.json (canonical) or
storyboard_<locale>.json; requires --locale when multiple locales exist.
Exit codes: 0 clean / 1 load failure / 2 validation errors."
```

---

## Task 5: Register `validate_app` in the main CLI

**Files:**
- Modify: `src/pipeline/cli.py`

The new Typer app needs to be registered via `app.add_typer` alongside the other sub-apps.

- [ ] **Step 1: Add import and registration**

In `src/pipeline/cli.py`, find the imports block at the top (lines 10–39) and add (alphabetically, near `cli_transition`):

```python
from pipeline.cli_validate import validate_app
```

Then find the `app.add_typer(...)` block (lines 43–62) and add (near `app.add_typer(transition_app, name="transition")`):

```python
app.add_typer(validate_app, name="validate")
```

- [ ] **Step 2: Smoke-test the CLI registration**

Run: `uv run pipeline validate --help`

Expected: prints the help text for the validate command, including `--project-id` and `--locale` options.

- [ ] **Step 3: End-to-end smoke test on baby-walker**

Run: `uv run pipeline validate --project-id 20260504-115232-baby-walker-story`

Expected: exits 0; prints the decision table for the baby-walker storyboard. (The baby-walker storyboard is post-Sprint-2 with a clean chart at s21.)

If the storyboard at `output/projects/20260504-115232-baby-walker-story/storyboard.json` has a known unrelated validation error (e.g. a missing source image referenced by an `article_image` scene), the command will exit 2 instead of 0. In that case, inspect the table output to confirm the chart scene s21 is NOT among the errors (the goal is "the chart branch is wired up correctly", not "the entire baby-walker is clean").

- [ ] **Step 4: Commit**

```bash
git add src/pipeline/cli.py
git commit -m "feat(cli): register 'pipeline validate' subcommand"
```

---

## Task 6: Run full quality gates

**Files:** all touched files.

- [ ] **Step 1: Full pytest run**

Run: `uv run pytest`

Expected: ≥ 1016 tests pass (Sprint 3 baseline) + new tests from this sprint = no regressions. The 2 pre-existing failures in `test_memory_sync.py` (unrelated to this sprint, per multi-agent hygiene) may still be present — those are not introduced by Sprint 4 and should be left alone.

- [ ] **Step 2: Ruff lint check on touched files**

Run: `uv run ruff check src/pipeline/composer/chart.py src/pipeline/director/storyboard_validator.py src/pipeline/cli_validate.py src/pipeline/cli.py tests/director/test_storyboard_validator.py tests/unit/test_cli_validate.py tests/unit/test_chart.py`

Expected: all clean. (Pre-existing ruff errors in unrelated files `test_cli_chain.py`/`test_memory_sync.py` left alone per multi-agent hygiene.)

- [ ] **Step 3: Mypy type-check on touched src files**

Run: `uv run mypy src/pipeline/composer/chart.py src/pipeline/director/storyboard_validator.py src/pipeline/cli_validate.py src/pipeline/cli.py`

Expected: clean on the touched files. Pre-existing mypy issues in other files (`dashboard/server.py` etc.) are not in scope.

- [ ] **Step 4: Verify back-compat — chart.py render-time wrapper still raises**

The refactor preserves the render-time raise behavior. Quick sanity check via a one-off Python invocation:

```bash
uv run python -c "
from pipeline.composer.chart import _validate_chart
try:
    _validate_chart({'type': 'chart'}, 's1')
except ValueError as e:
    print('OK: raised:', e)
"
```

Expected output: `OK: raised: chart s1: missing 'chart_type' (one of ['bar', 'comparison', 'line', 'proportion_blocks', 'stat_big_number', 'timeline'])`

- [ ] **Step 5: Final commit (only if not already covered)**

If there's no remaining diff, skip. Otherwise:

```bash
git add -A
git commit -m "chore: Sprint 4 cleanup"
```

---

## Self-review checklist (for the implementing engineer)

After all tasks complete:

- **Spec coverage**
  - [x] Chart branch in `_validate_scene`? Task 2.
  - [x] List-returning `validate_chart_visual`? Task 1.
  - [x] Render-time wrapper still raises? Task 1 step 3 + Task 6 step 4.
  - [x] `pipeline validate <project-id>` Typer command? Task 4.
  - [x] Auto-discover storyboard file (canonical + locale-suffixed)? Task 4 (`_discover_storyboard`).
  - [x] Exit codes 0/1/2? Task 4.
  - [x] 12 chart-branch negatives + 1 happy-path? Task 2.
  - [x] 5 smoke tests for untested branches? Task 3.
  - [x] CLI smoke tests (clean/broken/missing/multi-locale/locale-override)? Task 4.
  - [x] Registered in `cli.py`? Task 5.
  - [x] Pytest/ruff/mypy green? Task 6.
  - [x] End-to-end smoke on baby-walker? Task 5 step 3.

- **Roadmap close-out (post-merge, not part of this plan):**
  - Move Sprint 4 from `▶ next` to `🟢 *shipped 2026-05-22*` in `docs/ROADMAP.md`.
  - Append a SHIPPED entry to `.agent-memory/engineering-manager/sprint-log.md`.
  - Update `.agent-memory/engineering-manager/arsenal-state.md` "Storyboard validator" section to remove the chart-gap line and note the new `pipeline validate` CLI.
  - These are EM-skill tasks for the next dispatch, not implementer tasks.
