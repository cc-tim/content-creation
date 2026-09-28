# E5 Loud-Failure Sweep, Part 1 (Sprint 10) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A scene that fails to render can never reach a final as a black segment, and can never
be served from the scene cache as a black stand-in. Every such failure refuses assembly with the
step, the reason and a `suggested_fix`. `pipeline validate`, compose and the still-gate resolve
every `clip` / `article_image` path through one resolver.

**Architecture:**
- A new pure module, `src/pipeline/utils/paths.py`, owns media-path resolution. The candidates
  are the project dir, the repo root, then cwd. The validator, `clip.py`, `refit.py`,
  `render_scene`, compose's duplicate guard and the still-gate all delegate to it.
- `ComposeStage._render_one_scene` becomes the one loud scene boundary. Each step runs inside a
  small `_scene_step` context manager that turns any exception into
  `SceneRenderError("<step> failed: <ExcType>: <message>")`. On any failure, both cache paths are
  deleted before the error is raised.
- The gather loop records every failure and deletes every frame-suffix variant through one shared
  `scene_final_cache_paths`. `_black_screen` and image_sequence's `_black_clip` are deleted. AST
  fences stop them from coming back.

**Tech Stack:** Python 3.13, pytest (`asyncio_mode = "auto"`), `unittest.mock.patch`, `ast`,
ffmpeg/ffprobe (Homebrew, on the Mac), structlog.

**Spec:** `docs/superpowers/specs/2026-09-29-e5-loud-failure-sweep-design.md`

**Base and where to build:**
- Base is master `bab18f2`. Its `src/` and `tests/` are identical to the spec's base `3693b09`;
  only docs changed since.
- Build in a worktree:
  `git worktree add .worktrees/e5-loud-failure-sweep -b feat/e5-loud-failure-sweep master`, then
  run `uv sync` inside it.
- Every number below (red messages, pass counts) was measured by running this plan's exact code
  on a scratch export of `bab18f2`.

**Shared master (E10).** The E10 plan (`2026-09-29-claude-cli-llm-backend.md`) builds in
parallel on `feat/llm-cli-backend`. **The spec requires one edit to `cli_storyboard.py`** (§5.5:
"`cli_storyboard.py:382` passes `pdir`"). Sprint 10 touches only the `still_gate` command's
`render_scene_still(...)` call; E10 edits `_generate_beats`. The hunks don't overlap, so
whichever branch merges second does a normal 3-way merge. No other file is shared.

**Rulings on the spec's letter** (the capability is unchanged):
1. **T11 is split across the tasks that own each fix, not held for Task 5.** A1 requires every
   §10 test to be committed red before its fix lands. The fences' fixes land in Tasks 2
   (`Path.cwd()`), 3 (`_black_screen`) and 4 (`_black_clip`), so in Task 5 all three fences
   would already be green. So `test_media_resolution_has_one_owner` lands red in Task 2, and the
   two black-fallback fences land red in Task 4. Task 4 is the first point where one commit
   greens them. The toon/chart comment fixes from §11 step 5 fold into Task 3, which removes
   the fallback those comments describe. Task 5 is the controller's gates and smoke.
2. **The `overlay rule` fix drops "or re-run with `--skip-overlays`".** No CLI has a
   `--skip-overlays` flag; only `PipelineContext.skip_overlays` exists in `context.json`. Also,
   `check_overlay_allowed` runs *before* the `skip_overlays` guard (`compose.py:1160` vs
   `:1166`), so setting it would not bypass the rule. The fix is the collision message, then
   "Remove or change `scene.overlay` (title and namecard overlays fit any visual), then
   `uv run pipeline compose rescene …`". The pre-existing `overlay` step fix keeps its
   `--skip-overlays` text, because `test_overlay_failure_refuses_assembly_and_records_loudly`
   pins it. It is out of scope and is reported to the EM.
3. **`reason` gains an ffmpeg stderr tail.** For a `CalledProcessError`, `_step_reason` appends
   `" | stderr: <last 400 chars>"`. `str(CalledProcessError)` carries no stderr, which would make
   "Inspect the ffmpeg error" non-actionable. Pinned by RF2.
4. **Step labels.** The pause gap and `_fit_to_canvas` are labelled `frame/mux`. An exception
   outside every labelled step (only an executor-dispatch failure can reach it) is also wrapped
   as `frame/mux`.
5. **`image <idx>` is 0-based**, the loop's own `idx`, matching the `{sid}_seq{idx}_visual.mp4`
   naming. T7's "image 1 fails" means the second image.
6. **Smoke drivers.**
   - Runs 1, 2, 4 and 5 use `pipeline compose rescene`.
   - Run 3 ("re-run unchanged") uses `tmp/e5-sweep/smoke/compose_once.py`, which is
     `ComposeStage().run(ctx)` with nothing deleted first. It is the core of
     `produce --start-from compose`. The spec's options don't fit this run:
     - `rescene` deletes the scene's finals before rendering, so it can't prove "no cache hit";
     - `reburn` never runs `ComposeStage` at all;
     - `produce --start-from compose` runs a Claude visual QC after a successful compose, and
       the spec bars Claude calls.
7. **The dedupe key is `Path.resolve()`.** That is what "de-duplicated by resolved path" means.
   It follows symlinks but never checks existence, so "pure" is read as "no existence checks".

## Global Constraints

- Build host is the Mac: "No hub step: no goldens, no provider calls, no Claude calls."
- Axis: "Production quality, defect prevention. … it adds **zero runtime** … Do not cite it as a
  new arsenal item."
- §4: "A fallback that keeps the scene's content … is a designed degradation. A fallback that
  replaces the content … is a failure." A failure raises
  `SceneRenderError(scene, reason, suggested_fix)` and feeds `ctx.render_failures` plus
  `RuntimeError("Compose scene render failed; final assembly refused. …")`.
- I1: `_render_one_scene` "returns a `ComposeSceneResult` whose two cache files are real renders;
  or it raises `SceneRenderError`. When it raises, **neither** cache path its cache check reads
  (`{sid}_final{suffix}.mp4`, `{sid}_final_no_overlay{suffix}.mp4`) exists."
- `reason` format: `"<step> failed: <ExcType>: <message>"`. `<step>` is one of
  `visual (<visual.type>)`, `compartment`, `overlay rule`, `overlay`, `frame/mux`,
  `cached scene`.
- "The internal shape is the builder's choice … Don't add a framework."
- Do NOT touch: `_silence_gap` ("black by design, for `pause_after_sec`") or the rich_slide /
  chart flat paper background on a provider failure.
- A7: "The diff stays inside §6 IN. The `namecard` / `map` / `generated_image` fallbacks are
  untouched." §6 IN:
  - `stages/compose.py`, `cli_compose.py`;
  - `composer/{base,clip,refit,image_sequence,toon,chart}.py` (toon and chart: comments only);
  - `director/storyboard_validator.py`, `director/still_gate/render.py`, `cli_storyboard.py`;
  - the new `utils/paths.py`;
  - tests.
- §5.5: "`project_root=None` keeps today's behaviour minus the fallback, so any other caller is
  unaffected."
- A1: "Every test in §10 is committed failing … **before** its fix lands: a test-only commit,
  then a fix commit. The plan ledger records each red run."
- A2: "`uv run pytest -q`: 0 failed. `uv run ruff check src/ tests/` and `uv run mypy src/` are
  clean. The only new skips allowed are the existing environment and `--integration` gates."
- A4: "Run it in a scratch `PIPELINE_OUTPUT_DIR` under `tmp/e5-sweep/smoke/`. **Don't copy real
  project data to the Mac.**"
- §10 test pattern: "the `sample_context` fixture, a fake `run_ffmpeg` that writes the output
  file, and `check_ffmpeg_available` patched. All patch targets are module-level names in
  `pipeline.stages.compose`."
- Commits:
  - small `type(scope): message` commits;
  - each ends with a blank line and
    `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`;
  - never stage `tmp/`, so always `git add` explicit paths;
  - don't push.

## Review Focus

1. **An unreadable cached scene** (a `{sid}_final.mp4` that a crash or a full disk truncated, so
   ffprobe rejects it) must refuse with a `cached scene` reason. It must delete both cache files
   and re-render on the next run. Pinned by Task 3,
   `test_unreadable_cached_scene_is_deleted_and_refused`.
2. **ffmpeg dies between the two muxes** (`{sid}_final.mp4` written,
   `{sid}_final_no_overlay.mp4` half-written). Neither file may survive, and the reason must carry
   ffmpeg's stderr. Pinned by Task 3, `test_second_mux_failure_leaves_neither_cache_file`.
3. **Several scenes fail in one run, and a good scene's id extends a failed one's** (`s1` and `s2`
   fail, `s10` renders). Every failure is named and recorded. `s10` keeps its cache and isn't
   re-rendered next run. Pinned by Task 3,
   `test_several_failed_scenes_all_reported_and_good_scene_stays_cached`.
4. **A transient image-provider outage in the middle of an image_sequence.** The rerun that the
   `suggested_fix` recommends asks the provider for the failed image only. Pinned by Task 4,
   `test_rerun_after_failed_image_regenerates_only_that_image`.
5. **`storyboard still-gate`, launched from a cwd other than the repo root, on a project-relative
   `article_image`** must render (exit 0), not report `[render_error]`. Pinned by Task 2,
   `test_still_gate_resolves_project_relative_image_with_cwd_elsewhere`.

## Red-run ledger (A1)

"Expected red" was measured on a scratch export of `bab18f2` with the earlier tasks applied.
Fill in the other columns as you go, and commit this file with the task's own commits:
- **Observed red:** paste the failure line at the task's "verify it fails" step. It goes into
  the test-only commit.
- **Red commit:** paste the test-only commit's short SHA at the task's fix step. It goes into the
  fix commit.
- **Fix commit:** paste it at the *next* task's "verify it fails" step, because a commit can't
  record its own SHA. Task 4's fix SHA goes in at Task 5 Step 1.

| ID | Test | Task | Expected red | Observed red | Red commit | Fix commit |
|----|------|------|--------------|--------------|------------|------------|
| T8a | `tests/unit/test_media_paths.py` (10 resolver tests) | 1 | collection `ImportError: cannot import name 'paths' from 'pipeline.utils'` | `ImportError: cannot import name 'paths' from 'pipeline.utils'` | `8c0791a` | `c1fadac` |
| T8b | `test_media_paths.py::test_validator_and_renderers_agree_on_project_relative_paths` | 2 | `TypeError: _resolve_source_video() got an unexpected keyword argument 'project_root'` | `TypeError: _resolve_source_video() got an unexpected keyword argument 'project_root'` | `14064e8` | `46e0e93` |
| T9 | `test_compose_v2.py::test_project_relative_clip_renders_from_project_root` | 2 | `AssertionError: the clip was never extracted from the project's file` (log: `compose.scene.visual_failed error='Source video not found for clip in scene s1'`) | `AssertionError: the clip was never extracted from the project's file` (log: `compose.scene.visual_failed error='Source video not found for clip in scene s1'`) | `14064e8` | `46e0e93` |
| T10 | `tests/director/still_gate/test_render.py::test_render_scene_still_forwards_project_root` | 2 | `TypeError: render_scene_still() got an unexpected keyword argument 'project_root'` | `TypeError: render_scene_still() got an unexpected keyword argument 'project_root'` | `14064e8` | `46e0e93` |
| T11a | `test_loud_failure_fence.py::test_media_resolution_has_one_owner` | 2 | `{'composer/clip.py': [15], 'stages/compose.py': [517], 'director/storyboard_validator.py': [667]}` | `{'composer/clip.py': [15], 'director/storyboard_validator.py': [667], 'stages/compose.py': [517]}` | `14064e8` | `46e0e93` |
| C1 | `test_clip_renderer.py::test_render_clip_no_source` (contract change) | 2 | `FileNotFoundError: Source video not found for clip in scene s1` | `FileNotFoundError: Source video not found for clip in scene s1` | `14064e8` | `46e0e93` |
| C2 | `test_clip_renderer.py::test_render_clip_missing_path_lists_the_candidates_it_tried` | 2 | `TypeError: render_clip() got an unexpected keyword argument 'project_root'` | `TypeError: render_clip() got an unexpected keyword argument 'project_root'` | `14064e8` | `46e0e93` |
| RF5 | `still_gate/test_cli.py::test_still_gate_resolves_project_relative_image_with_cwd_elsewhere` | 2 | `[render_error] s1: s1: article_image path not found: source/busy.png` | `[render_error] s1: s1: article_image path not found: source/busy.png Suggested fix: Replace path or change visual.type to generated_image.` | `14064e8` | `46e0e93` |
| T1 | `test_compose_v2.py::test_generic_visual_failure_refuses_assembly_without_black` | 3 | `DID NOT RAISE <class 'RuntimeError'>` | `DID NOT RAISE <class 'RuntimeError'>` | `a7a113b` | `8b529b4` |
| T2 | `…::test_overlay_rule_violation_refuses_assembly` | 3 | `DID NOT RAISE <class 'RuntimeError'>` | `DID NOT RAISE <class 'RuntimeError'>` | `a7a113b` | `8b529b4` |
| T3 | `…::test_compartment_failure_refuses_assembly` | 3 | `DID NOT RAISE <class 'RuntimeError'>` | `DID NOT RAISE <class 'RuntimeError'>` | `a7a113b` | `8b529b4` |
| T4 | `…::test_render_one_scene_post_visual_failure_raises_and_leaves_no_cache` | 3 | `DID NOT RAISE <class 'pipeline.errors.SceneRenderError'>` | `DID NOT RAISE <class 'pipeline.errors.SceneRenderError'>` | `a7a113b` | `8b529b4` |
| T5 | `…::test_escaped_scene_exception_leaves_no_cached_black` | 3 | `assert ['s1_final.mp4', 's1_final_no_overlay.mp4', 's1_final_open_book_page.mp4'] == []` | `assert ['s1_final.mp4', 's1_final_no_overlay.mp4', 's1_final_open_book_page.mp4'] == []` | `a7a113b` | `8b529b4` |
| T6 | `…::test_refused_compose_rerun_does_not_cache_hit` | 3 | `DID NOT RAISE <class 'RuntimeError'>` | `DID NOT RAISE <class 'RuntimeError'>` | `a7a113b` | `8b529b4` |
| RF1 | `…::test_unreadable_cached_scene_is_deleted_and_refused` | 3 | reason is `"Command '['ffprobe']' returned non-zero exit status 1."`, not `cached scene failed: …` | reason is `"Command '['ffprobe']' returned non-zero exit status 1."`, not `cached scene failed: …` | `a7a113b` | `8b529b4` |
| RF2 | `…::test_second_mux_failure_leaves_neither_cache_file` | 3 | `subprocess.CalledProcessError` escapes (re-raised by the black fallback's own mux) | `subprocess.CalledProcessError` escapes (re-raised by the black fallback's own mux) | `a7a113b` | `8b529b4` |
| RF3 | `…::test_several_failed_scenes_all_reported_and_good_scene_stays_cached` | 3 | `DID NOT RAISE <class 'RuntimeError'>` | `DID NOT RAISE <class 'RuntimeError'>` | `a7a113b` | `8b529b4` |
| T7 | `tests/unit/test_image_sequence.py::test_failed_image_raises_scene_render_error_not_black` | 4 | `DID NOT RAISE <class 'pipeline.errors.SceneRenderError'>` | `DID NOT RAISE <class 'pipeline.errors.SceneRenderError'>` | `b08db91` | `f4f0854` |
| RF4 | `test_image_sequence.py::test_rerun_after_failed_image_regenerates_only_that_image` | 4 | `DID NOT RAISE <class 'pipeline.errors.SceneRenderError'>` | `DID NOT RAISE <class 'pipeline.errors.SceneRenderError'>` | `b08db91` | `f4f0854` |
| T11b | `test_loud_failure_fence.py::test_no_black_fallback_helpers_remain` | 4 | `assert not hasattr(<module 'pipeline.composer.image_sequence'>, '_black_clip')` | `assert not hasattr(<module 'pipeline.composer.image_sequence'>, '_black_clip')` | `b08db91` | `f4f0854` |
| T11c | `test_loud_failure_fence.py::test_black_lavfi_source_only_in_silence_gap` | 4 | `Extra items in the left set: ('composer/image_sequence.py', '_black_clip')` | `Extra items in the left set: ('composer/image_sequence.py', '_black_clip')` | `b08db91` | `f4f0854` |
| RF6 | `test_compose_v2.py::test_legacy_black_standin_dropped_and_rerendered` | 3 (fix round 1, Ruling S2) | `assert 0 == 1` (render_scene never called: a legacy `{sid}_black.mp4` marker beside real-looking cached finals still cache-hits) | `assert 0 == 1` | `6d2c4a9` | `a015b85` |

---

### Task 1: One media-path resolver, `pipeline.utils.paths` (spec §5.5; T8, pure half)

**Files:**
- Create: `src/pipeline/utils/paths.py`
- Test (create): `tests/unit/test_media_paths.py`
- Ledger: this file, row T8a

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `pipeline.utils.paths.REPO_ROOT: Path`, which is `Path(__file__).resolve().parents[3]`, the
    checkout root.
  - `media_path_candidates(raw: str | Path, project_root: Path | None) -> list[Path]`:
    - expands `~`;
    - an absolute path gives `[p]`;
    - a relative path gives `[project_root/p (if given), REPO_ROOT/p, cwd/p]`, de-duplicated by
      `Path.resolve()` with order kept;
    - never checks existence.
  - `resolve_media_path(raw: str | Path, project_root: Path | None) -> Path`: the first existing
    candidate, else `candidates[0]`.
  - Test helper `_touch(p: Path) -> Path` in `tests/unit/test_media_paths.py`. Task 2 appends a
    test that uses it.

- [ ] **Step 1: Write the failing tests.** Create `tests/unit/test_media_paths.py`:

```python
"""One media-path resolver (E5 sweep §5.5): candidates, precedence, and agreement
between `pipeline validate` and the renderers."""
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.utils import paths
from pipeline.utils.paths import media_path_candidates, resolve_media_path


def _touch(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    return p


@pytest.fixture
def layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    """A project dir, a stand-in repo root and a cwd that is neither."""
    project, repo, cwd = tmp_path / "project", tmp_path / "repo", tmp_path / "cwd"
    for d in (project, repo, cwd):
        d.mkdir()
    monkeypatch.setattr(paths, "REPO_ROOT", repo)
    monkeypatch.chdir(cwd)
    return project, repo, cwd


def test_repo_root_is_the_checkout_root():
    assert (paths.REPO_ROOT / "pyproject.toml").is_file()
    assert (paths.REPO_ROOT / "src" / "pipeline" / "utils" / "paths.py").is_file()


def test_absolute_path_is_its_own_only_candidate(layout):
    project, _, _ = layout
    a = _touch(project / "abs.mp4")
    assert media_path_candidates(str(a), project) == [a]
    assert resolve_media_path(a, project) == a


def test_relative_candidates_are_project_then_repo_then_cwd(layout):
    project, repo, cwd = layout
    assert media_path_candidates("raw/x.png", project) == [
        project / "raw/x.png", repo / "raw/x.png", cwd / "raw/x.png",
    ]


def test_project_relative_wins(layout):
    project, repo, cwd = layout
    p = _touch(project / "source/clip.mp4")
    _touch(repo / "source/clip.mp4")
    _touch(cwd / "source/clip.mp4")
    assert resolve_media_path("source/clip.mp4", project) == p


def test_repo_relative_resolves_with_cwd_elsewhere(layout):
    project, repo, _ = layout
    r = _touch(repo / "raw/parenting/a.png")
    assert resolve_media_path("raw/parenting/a.png", project) == r


def test_cwd_relative_still_resolves(layout):
    project, _, cwd = layout
    c = _touch(cwd / "local/b.png")
    assert resolve_media_path("local/b.png", project) == c


def test_nothing_exists_returns_the_project_candidate(layout):
    project, _, _ = layout
    assert resolve_media_path("missing/c.png", project) == project / "missing/c.png"


def test_without_project_root_repo_then_cwd(layout):
    _, repo, cwd = layout
    assert media_path_candidates("x.png", None) == [repo / "x.png", cwd / "x.png"]
    assert resolve_media_path("x.png", None) == repo / "x.png"


def test_expanduser(layout, tmp_path, monkeypatch):
    project, _, _ = layout
    home = tmp_path / "home"
    h = _touch(home / "media/d.png")
    monkeypatch.setenv("HOME", str(home))
    assert media_path_candidates("~/media/d.png", project) == [h]
    assert resolve_media_path("~/media/d.png", project) == h


def test_candidates_that_resolve_to_the_same_file_are_dropped(layout, monkeypatch):
    project, repo, _ = layout
    monkeypatch.chdir(repo)  # the usual launcher case: cwd is the repo root
    assert media_path_candidates("raw/x.png", project) == [project / "raw/x.png", repo / "raw/x.png"]
    assert media_path_candidates("raw/x.png", repo) == [repo / "raw/x.png"]
```

- [ ] **Step 2: Run it to verify it fails.**
  Run `uv run pytest tests/unit/test_media_paths.py -q`.
  Expected: `1 error during collection`, with
  `ImportError: cannot import name 'paths' from 'pipeline.utils'`. Paste that line into ledger
  row T8a.

- [ ] **Step 3: Commit the red tests.**

```bash
git add tests/unit/test_media_paths.py docs/superpowers/plans/2026-09-29-e5-loud-failure-sweep.md
git commit -m "test(paths): red — one media-path resolver (E5 T8)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 4: Implement.** Create `src/pipeline/utils/paths.py`:

```python
"""One resolver for storyboard media paths (`clip`, `article_image`, `image`).

`pipeline validate`, compose and the still-gate all resolve `visual.path` and
`visual.refit_path` through here, so a storyboard that validates clean renders the
same files. Spec: docs/superpowers/specs/2026-09-29-e5-loud-failure-sweep-design.md §5.5
"""
from __future__ import annotations

from pathlib import Path

# src/pipeline/utils/paths.py -> parents[3] is the checkout root. Real storyboards use
# repo-root-relative paths (raw/..., through the repo's /raw symlink); this candidate
# keeps them resolving when the launcher's cwd is not the repo root.
REPO_ROOT: Path = Path(__file__).resolve().parents[3]


def media_path_candidates(raw: str | Path, project_root: Path | None) -> list[Path]:
    """Candidate files for *raw*, highest priority first. No existence checks.

    `~` is expanded. An absolute path is its own only candidate. A relative path tries
    project_root/raw (when project_root is given), REPO_ROOT/raw, then cwd/raw. A
    candidate that resolves to the same path as an earlier one is dropped.
    """
    path = Path(raw).expanduser()
    if path.is_absolute():
        return [path]
    bases = [base for base in (project_root, REPO_ROOT, Path.cwd()) if base is not None]
    candidates: list[Path] = []
    seen: set[Path] = set()
    for base in bases:
        candidate = base / path
        key = candidate.resolve()
        if key not in seen:
            seen.add(key)
            candidates.append(candidate)
    return candidates


def resolve_media_path(raw: str | Path, project_root: Path | None) -> Path:
    """The first candidate that exists; if none does, the first candidate (the path an
    error message should name)."""
    candidates = media_path_candidates(raw, project_root)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]
```

- [ ] **Step 5: Run the tests to verify they pass.**
  - Run `uv run pytest tests/unit/test_media_paths.py -q`. Expected: `10 passed`.
  - Run `uv run ruff check src/pipeline/utils/paths.py tests/unit/test_media_paths.py` and
    `uv run mypy src/`. Expected: clean.
  - Run `uv run pytest -q`. Expected on base: `1353 passed, 59 skipped`.

- [ ] **Step 6: Commit the fix.** First put the red commit's SHA in row T8a. Task 2 Step 2
  records this fix commit's SHA.

```bash
git add src/pipeline/utils/paths.py docs/superpowers/plans/2026-09-29-e5-loud-failure-sweep.md
git commit -m "feat(paths): pipeline.utils.paths — one media-path resolver (E5 §5.5)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Delegation: validate, render and still-gate share the resolver (spec §5.5; T8 agreement, T9, T10, T11a)

**Files:**
- Modify: `src/pipeline/director/storyboard_validator.py`: imports; `_resolve_path` (:663)
- Modify: `src/pipeline/composer/clip.py`: imports; `_resolve_source_video` (:9); `render_clip` (:39)
- Modify: `src/pipeline/composer/refit.py`: imports; `effective_image_path` (:131)
- Modify: `src/pipeline/composer/base.py`: `render_scene` (:327); clip branch (:347-350); image
  branch (:427)
- Modify: `src/pipeline/stages/compose.py`:
  - imports;
  - `_apply_duplicate_guard` (:462);
  - delete `_source_for_clip_visual` (:511-518);
  - `_precompute_duplicate_guard` (:1019) and its call (:720);
  - the `render_scene(` call in `_render_sync` (:1110).
- Modify: `src/pipeline/director/still_gate/render.py`: `render_scene_still` (:40)
- Modify: `src/pipeline/cli_storyboard.py`: the `still_gate` command's call (:382) **only**
- Test: `tests/unit/test_media_paths.py` (append T8b)
- Test: `tests/unit/test_loud_failure_fence.py` (create; T11a)
- Test: `tests/unit/test_compose_v2.py` (5 fake signatures, 2 helpers, T9)
- Test: `tests/director/still_gate/test_render.py` (T10)
- Test: `tests/director/still_gate/test_cli.py` (RF5)
- Test: `tests/unit/test_clip_renderer.py` (C1 replaced, C2 added)

**Interfaces:**
- Consumes (Task 1): `resolve_media_path(raw, project_root) -> Path`,
  `media_path_candidates(raw, project_root) -> list[Path]`, and the test helper `_touch`.
- Produces:
  - `pipeline.composer.clip._resolve_source_video(visual: dict, source_video: Path | None, project_root: Path | None = None) -> Path | None`
  - `pipeline.composer.clip.render_clip(visual, duration_sec, width, height, work_dir, scene_id, source_video: Path | None = None, project_root: Path | None = None) -> Path`.
    A missing source now raises `SceneRenderError`, with a reason starting `clip source not found:`
    that lists the candidates it tried.
  - `pipeline.composer.refit.effective_image_path(visual: dict, project_root: Path | None = None) -> Path`
  - `pipeline.composer.base.render_scene(scene, duration_sec, aspect_ratio, work_dir, source_video=None, theme=None, project_root: Path | None = None) -> Path`
  - `pipeline.director.still_gate.render.render_scene_still(scene, *, variant, work_dir, theme=None, project_root: Path | None = None) -> Path`
  - `pipeline.stages.compose`:
    - `_apply_duplicate_guard(scene, source_video, seen_hashes, style_descriptor, project_root: Path | None = None)`;
    - `ComposeStage._precompute_duplicate_guard(storyboard, source_video, style_descriptor, project_root: Path | None = None)`;
    - `_source_for_clip_visual` no longer exists.
  - Test helpers in `tests/unit/test_compose_v2.py`, which Task 3 uses:
    - `_write_fake_mp4(cmd)` is a `run_ffmpeg` stand-in that writes `cmd[-1]`;
    - `_prep_storyboard(ctx, scenes, seg_sec: float = 5.0) -> Path` saves the storyboard,
      writes one fake audio segment per scene, and returns `compose/scenes/`.
  - `tests/unit/test_loud_failure_fence.py`, with `PKG: Path` (`src/pipeline`) and
    `_parse(rel: str) -> ast.Module`. Task 4 appends to it.

- [ ] **Step 1: Write the failing tests.**

  **1a.** Append T8b to `tests/unit/test_media_paths.py`:

```python


def test_validator_and_renderers_agree_on_project_relative_paths(tmp_path, monkeypatch):
    """`pipeline validate` and the renderers must pick the same file (Sprint 9 hub-smoke
    defect: the validator found project/source/clip.mp4, the renderer looked in cwd)."""
    from pipeline.composer import clip, refit
    from pipeline.director import storyboard_validator as validator

    project = tmp_path / "project"
    clip_file = _touch(project / "source/clip.mp4")
    img = _touch(project / "source/img.png")
    refit_img = _touch(project / "source/img.refit.png")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    clip_visual = {"type": "clip", "path": "source/clip.mp4"}
    refit_visual = {"type": "article_image", "path": "source/img.png",
                    "refit_path": "source/img.refit.png"}
    plain_visual = {"type": "article_image", "path": "source/img.png"}

    assert validator._clip_visual_path(clip_visual, project) == clip_file
    assert clip._resolve_source_video(clip_visual, None, project_root=project) == clip_file
    assert validator._effective_visual_path(refit_visual, project) == refit_img
    assert refit.effective_image_path(refit_visual, project_root=project) == refit_img
    assert validator._effective_visual_path(plain_visual, project) == img
    assert refit.effective_image_path(plain_visual, project_root=project) == img
```

  **1b.** Create `tests/unit/test_loud_failure_fence.py` (T11a):

```python
"""Fences for the E5 loud-failure sweep: guardrails in code, not docs.

Spec: docs/superpowers/specs/2026-09-29-e5-loud-failure-sweep-design.md §5.6
"""
from __future__ import annotations

import ast
from pathlib import Path

import pipeline

PKG = Path(pipeline.__file__).resolve().parent  # src/pipeline

# Every consumer of storyboard media paths delegates to pipeline.utils.paths.
_MEDIA_PATH_CONSUMERS = (
    "composer/clip.py",
    "composer/refit.py",
    "stages/compose.py",
    "director/storyboard_validator.py",
)


def _parse(rel: str) -> ast.Module:
    path = PKG / rel
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _cwd_call_lines(tree: ast.Module) -> list[int]:
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"cwd", "getcwd"}
    ]


def test_media_resolution_has_one_owner():
    offenders = {rel: _cwd_call_lines(_parse(rel)) for rel in _MEDIA_PATH_CONSUMERS}
    offenders = {rel: lines for rel, lines in offenders.items() if lines}
    assert offenders == {}, (
        f"cwd-relative media resolution outside pipeline/utils/paths.py: {offenders}; "
        "use pipeline.utils.paths.resolve_media_path"
    )
```

  **1c.** In `tests/unit/test_compose_v2.py`, five existing `render_scene` fakes lack the new
  keyword. Add it; otherwise they would raise `TypeError` once compose passes `project_root`.
  (Until Task 3, P1's black fallback would hide that `TypeError`.) Edit lines 368, 439, 618,
  669 and 735. Line 368 changes from

```python
    def _fake_render(scene, duration, aspect_ratio, work_dir, source_video=None, theme=None):
```

  to

```python
    def _fake_render(scene, duration, aspect_ratio, work_dir, source_video=None, theme=None, project_root=None):
```

  and each of the four lambdas (439, 618, 669, 735) changes from

```python
        lambda scene, duration, aspect_ratio, work_dir, source_video=None, theme=None:
```

  to

```python
        lambda scene, duration, aspect_ratio, work_dir, source_video=None, theme=None, project_root=None:
```

  Check: `grep -c "theme=None, project_root=None" tests/unit/test_compose_v2.py` prints `5`.

  **1d.** Append the helpers and T9 to the end of `tests/unit/test_compose_v2.py`:

```python


# --- E5 loud-failure sweep (docs/superpowers/specs/2026-09-29-e5-loud-failure-sweep-design.md) ---


def _write_fake_mp4(cmd):
    """Stand-in for run_ffmpeg: create the output file ffmpeg would have written."""
    out = cmd[-1]
    if isinstance(out, str) and out.endswith(".mp4"):
        Path(out).write_bytes(b"fake")


def _prep_storyboard(ctx, scenes, seg_sec: float = 5.0) -> Path:
    """Save *scenes* as ctx's storyboard with one fake audio segment per scene.

    Returns compose/scenes/ (created), where scene cache files live."""
    sb_path = ctx.work_dir / "storyboard.json"
    Storyboard(scenes=scenes).save(sb_path)
    ctx.storyboard_path = sb_path
    audio_dir = ctx.work_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    ctx.narration_path = audio_dir / "narration.mp3"
    ctx.narration_path.write_bytes(b"fake")
    ctx.subtitle_path = audio_dir / "subs.srt"
    ctx.subtitle_path.write_text("1\n00:00:00,000 --> 00:00:05,000\ntest\n")
    ctx.segment_timings = []
    for i, _scene in enumerate(scenes):
        seg = audio_dir / f"seg_{i:03d}.mp3"
        seg.write_bytes(b"fake audio")
        ctx.segment_timings.append({
            "index": i, "text": "t", "path": str(seg),
            "start_ms": int(i * seg_sec * 1000), "duration_ms": int(seg_sec * 1000),
        })
    scenes_dir = ctx.work_dir / "compose" / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    return scenes_dir


async def test_project_relative_clip_renders_from_project_root(sample_context, tmp_path, monkeypatch):
    """Sprint 9 hub-smoke defect, end to end: `path: source/clip.mp4` validated clean against
    the project dir, then compose looked in cwd, hit "Source video not found" and rendered
    black. Compose (render and duplicate guard) must read the project's file."""
    clip_file = sample_context.work_dir / "source" / "clip.mp4"
    clip_file.parent.mkdir(parents=True)
    clip_file.write_bytes(b"fake clip")
    _prep_storyboard(sample_context, [
        Scene(id="s1", section="hook", narration="t", narration_est_sec=5,
              visual={"type": "clip", "path": "source/clip.mp4", "start_sec": 0, "end_sec": 5}),
    ])
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    clip_calls: list[list[str]] = []

    def _clip_ffmpeg(cmd):
        clip_calls.append(list(cmd))
        _write_fake_mp4(cmd)

    thumb_sources: list[Path] = []

    def _no_thumbnail(source, timestamp, out_path):
        thumb_sources.append(source)
        raise RuntimeError("no thumbnails in unit tests")

    with (
        patch("pipeline.stages.compose.check_ffmpeg_available", return_value=True),
        patch("pipeline.stages.compose.run_ffmpeg", side_effect=_write_fake_mp4),
        patch("pipeline.stages.compose._extract_clip_thumbnail", side_effect=_no_thumbnail),
        patch("pipeline.composer.clip._get_source_duration", return_value=10.0),
        patch("pipeline.composer.clip.run_ffmpeg", side_effect=_clip_ffmpeg),
    ):
        await ComposeStage().run(sample_context)

    assert len(clip_calls) == 1, "the clip was never extracted from the project's file"
    cmd = clip_calls[0]
    assert cmd[cmd.index("-i") + 1] == str(clip_file)
    assert thumb_sources == [clip_file]  # the duplicate-frame guard reads the same file
```

  **1e.** Append T10 to `tests/director/still_gate/test_render.py`:

```python


def test_render_scene_still_forwards_project_root(tmp_path: Path, monkeypatch):
    """The still-gate resolves clip/image paths like validate and compose do: it must hand
    the project dir to render_scene."""
    from pipeline.director.still_gate import render as still_render

    seen: dict[str, object] = {}

    def fake_render_scene(scene, duration, aspect_ratio, work_dir, source_video=None,
                          theme=None, project_root=None):
        seen["project_root"] = project_root
        out = work_dir / "visual.mp4"
        out.write_bytes(b"visual")
        return out

    def fake_frame(src, out, *, frame_style, width, height, fps=30):
        out.write_bytes(b"framed")
        return out

    monkeypatch.setattr(still_render, "render_scene", fake_render_scene)
    monkeypatch.setattr(still_render, "composite_scene_frame", fake_frame)
    monkeypatch.setattr(still_render, "run_ffmpeg", lambda cmd: Path(cmd[-1]).write_bytes(b"png"))

    project = tmp_path / "project"
    still_render.render_scene_still(
        {"id": "s1", "visual": {"type": "text_card", "text": "x"}},
        variant="no_overlay", work_dir=tmp_path / "work", theme={}, project_root=project,
    )
    assert seen["project_root"] == project
```

  **1f.** Append RF5 (Review Focus 5) to `tests/director/still_gate/test_cli.py`. It runs
  without mocks, like its neighbours, using real ffmpeg:

```python


def test_still_gate_resolves_project_relative_image_with_cwd_elsewhere(tmp_path, busy_png, monkeypatch):
    """A project-relative article_image that `pipeline validate` accepts must render in the
    still-gate too, whatever the cwd (no [render_error], exit 0)."""
    import shutil

    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(tmp_path))
    scenes = [
        {"id": "s1", "section": "h", "visual": {"type": "article_image", "path": "source/busy.png"}, "overlay": None},
    ]
    pid = _project(tmp_path, scenes)
    source_dir = tmp_path / "projects" / pid / "source"
    source_dir.mkdir()
    shutil.copyfile(busy_png, source_dir / "busy.png")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    result = runner.invoke(storyboard_app, ["still-gate", pid])

    assert "render_error" not in result.output
    assert result.exit_code == 0, result.output
```

  **1g.** In `tests/unit/test_clip_renderer.py`, replace `test_render_clip_no_source`: the
  contract changes from `FileNotFoundError` to `SceneRenderError`, per §5.5. Then add C2.
  Replace the whole existing function with:

```python
def test_render_clip_no_source(tmp_path):
    import pytest

    from pipeline.errors import SceneRenderError

    with pytest.raises(SceneRenderError, match="no visual.path and no primary source video"):
        render_clip(
            visual={"type": "clip", "start_sec": 0, "end_sec": 10},
            duration_sec=10.0,
            width=1280,
            height=720,
            work_dir=tmp_path,
            scene_id="s1",
            source_video=None,
        )


def test_render_clip_missing_path_lists_the_candidates_it_tried(tmp_path, monkeypatch):
    import pytest

    from pipeline.errors import SceneRenderError

    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SceneRenderError) as ei:
        render_clip(
            visual={"type": "clip", "path": "source/missing.mp4", "start_sec": 0, "end_sec": 5},
            duration_sec=5.0,
            width=1280,
            height=720,
            work_dir=tmp_path,
            scene_id="s4",
            project_root=project,
        )
    err = ei.value
    assert err.scene == "s4"
    assert str(project / "source" / "missing.mp4") in err.reason
    assert str(tmp_path / "source" / "missing.mp4") in err.reason
    assert "visual.path" in err.suggested_fix
    assert "--project-id project --scene s4" in err.suggested_fix
```

- [ ] **Step 2: Run it to verify it fails.**
  Run:
  `uv run pytest tests/unit/test_media_paths.py tests/unit/test_loud_failure_fence.py tests/unit/test_compose_v2.py tests/director/still_gate tests/unit/test_clip_renderer.py -q`
  Expected `7 failed`, with the messages in ledger rows T8b, T11a, T9, T10, RF5, C1 and C2.
  Paste each observed line into its ledger row, and put Task 1's fix SHA in row T8a.

- [ ] **Step 3: Commit the red tests.**

```bash
git add tests/unit/test_media_paths.py tests/unit/test_loud_failure_fence.py \
        tests/unit/test_compose_v2.py tests/director/still_gate/test_render.py \
        tests/director/still_gate/test_cli.py tests/unit/test_clip_renderer.py \
        docs/superpowers/plans/2026-09-29-e5-loud-failure-sweep.md
git commit -m "test(compose): red — validate, compose and still-gate agree on media paths (E5 T8-T10)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 4: Implement the delegation.**

  **4a. `src/pipeline/composer/clip.py`.** Replace the imports and `_resolve_source_video`
  (lines 6-16):

```python
from pipeline.errors import SceneRenderError
from pipeline.utils.ffmpeg import run_ffmpeg
from pipeline.utils.paths import media_path_candidates, resolve_media_path


def _resolve_source_video(
    visual: dict, source_video: Path | None, project_root: Path | None = None
) -> Path | None:
    """The clip's source file: `visual.path` via the shared media resolver, else the
    project's primary source video."""
    raw_path = visual.get("path")
    if raw_path:
        return resolve_media_path(str(raw_path), project_root)
    return source_video
```

  In `render_clip`, add the keyword after `source_video: Path | None = None,`:

```python
    project_root: Path | None = None,
```

  and replace

```python
    clip_source = _resolve_source_video(visual, source_video)
    if clip_source is None or not clip_source.exists():
        raise FileNotFoundError(f"Source video not found for clip in scene {scene_id}")
```

  with

```python
    clip_source = _resolve_source_video(visual, source_video, project_root)
    if clip_source is None or not clip_source.exists():
        raw_path = visual.get("path")
        if raw_path:
            tried = ", ".join(str(p) for p in media_path_candidates(str(raw_path), project_root))
            where = f"visual.path {raw_path!r} not found; tried: {tried}"
        else:
            where = "no visual.path and no primary source video"
        pid = project_root.name if project_root else "<project-id>"
        raise SceneRenderError(
            scene=scene_id,
            reason=f"clip source not found: {where}",
            suggested_fix=(
                "Fix visual.path (project-relative, repo-relative or absolute) or re-acquire "
                f"the primary source video, then `uv run pipeline validate {pid}` and "
                f"`uv run pipeline compose rescene --project-id {pid} --scene {scene_id}`."
            ),
        )
```

  **4b. `src/pipeline/composer/refit.py`.** After
  `from pipeline.composer.book_scene import BookSceneSpec`, add
  `from pipeline.utils.paths import resolve_media_path`. Replace `effective_image_path` with:

```python
def effective_image_path(visual: dict[str, Any], project_root: Path | None = None) -> Path:
    """Return the refit sidecar if it exists, otherwise the source image path.

    Both resolve through pipeline.utils.paths.resolve_media_path, the resolver
    `pipeline validate` uses, so validate and render pick the same file.
    """
    refit_path = visual.get("refit_path")
    if refit_path:
        candidate = resolve_media_path(str(refit_path), project_root)
        if candidate.exists():
            return candidate
    return resolve_media_path(str(visual.get("path", "")), project_root)
```

  **4c. `src/pipeline/composer/base.py`, `render_scene`.** Change the signature tail and
  docstring to:

```python
    source_video: Path | None = None,
    theme: dict | None = None,
    project_root: Path | None = None,
) -> Path:
    """Dispatch to the appropriate visual renderer based on scene.visual.type.

    *project_root* is the project dir that relative `clip` / `article_image` / `image`
    paths resolve against (pipeline.utils.paths). Returns the rendered segment (.mp4).
    """
```

  In the clip branch, replace
  `return render_clip(visual, duration_sec, width, height, work_dir, scene_id, source_video)`
  with:

```python
        return render_clip(
            visual, duration_sec, width, height, work_dir, scene_id, source_video,
            project_root=project_root,
        )
```

  In the `article_image` / `image` branch, replace `img_path = effective_image_path(visual)`
  with `img_path = effective_image_path(visual, project_root)`. Leave the `namecard` / `map` and
  `generated_image` branches untouched (A7).

  **4d. `src/pipeline/director/storyboard_validator.py`.** After
  `from pipeline.storyboard import Scene, Storyboard`, add
  `from pipeline.utils.paths import resolve_media_path`. Replace `_resolve_path` with:

```python
def _resolve_path(raw: str, project_root: Path) -> Path:
    """Delegate to the one media-path resolver compose and the still-gate also use."""
    return resolve_media_path(raw, project_root)
```

  **4e. `src/pipeline/stages/compose.py`.**
  - After `from pipeline.composer.base import get_resolution, render_scene`, add
    `from pipeline.composer.clip import _resolve_source_video`.
  - In `_apply_duplicate_guard`, add `project_root: Path | None = None,` after
    `style_descriptor: str,`. Replace
    `clip_source = _source_for_clip_visual(visual, source_video)` with
    `clip_source = _resolve_source_video(visual, source_video, project_root)`.
  - Delete the whole `def _source_for_clip_visual(...)` function (lines 511-518) and its trailing
    blank lines.
  - In `ComposeStage._precompute_duplicate_guard`, add `project_root: Path | None = None,` after
    `style_descriptor: str,`, and change the inner call to:

```python
            guarded, seen_clip_hashes = _apply_duplicate_guard(
                sd, source_video, seen_clip_hashes,
                style_descriptor=style_descriptor,
                project_root=project_root,
            )
```

  - In `_compose_from_storyboard`, change the call to:

```python
        scene_dicts = self._precompute_duplicate_guard(
            storyboard, ctx.video_path, style_anchor.style_descriptor,
            project_root=ctx.work_dir,
        )
```

  - In `_render_sync`, add `project_root=ctx.work_dir,` as the last keyword of the
    `render_scene(...)` call (after `theme=theme_dict,`).

  **4f. `src/pipeline/director/still_gate/render.py`.** Add
  `project_root: Path | None = None,` after `theme: dict | None = None,` in `render_scene_still`,
  and replace its `render_scene` line with:

```python
    visual_mp4 = render_scene(
        scene, _STILL_DURATION_SEC, "16:9", work_dir, theme=theme or {}, project_root=project_root,
    )
```

  **4g. `src/pipeline/cli_storyboard.py`, in the `still_gate` command only.** Replace line 382:

```python
                tmp_png = render_scene_still(
                    scene, variant=variant, work_dir=work / sid, theme={}, project_root=pdir,
                )
```

- [ ] **Step 5: Run the tests to verify they pass.**
  - Run:
    `uv run pytest tests/unit/test_media_paths.py tests/unit/test_loud_failure_fence.py tests/unit/test_compose_v2.py tests/director/still_gate tests/unit/test_clip_renderer.py tests/unit/test_compose_dup_guard.py tests/director/test_storyboard_validator.py tests/unit/test_composer_refit.py tests/unit/test_composer_base.py -q`.
    Expected: `106 passed, 2 skipped`.
  - Run `grep -rn "Path.cwd\|_source_for_clip_visual" src/pipeline/composer/clip.py src/pipeline/composer/refit.py src/pipeline/stages/compose.py src/pipeline/director/storyboard_validator.py`.
    Expected: no output.
  - Run `uv run pytest -q`, `uv run ruff check src/ tests/` and `uv run mypy src/`. Expected on
    base: `1359 passed, 59 skipped`, then clean, then clean.

- [ ] **Step 6: Commit the fix.** First put the red commit's SHA in rows T8b-RF5.

```bash
git add src/pipeline/composer/clip.py src/pipeline/composer/refit.py \
        src/pipeline/composer/base.py src/pipeline/director/storyboard_validator.py \
        src/pipeline/stages/compose.py src/pipeline/director/still_gate/render.py \
        src/pipeline/cli_storyboard.py docs/superpowers/plans/2026-09-29-e5-loud-failure-sweep.md
git commit -m "fix(compose): resolve clip/image paths through utils.paths everywhere (E5 §5.5)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: One loud scene boundary (spec §5.1-5.3; T1-T6, RF1-RF3). Review this one hardest.

**Files:**
- Modify: `src/pipeline/stages/compose.py`. The line numbers are from base `bab18f2`, and Task 2
  shifts them by a few lines, so match on the quoted text:
  - imports;
  - new module helpers before `ComposeSceneResult` (:599) and its docstring;
  - the gather result loop (:769-814);
  - `_render_one_scene` (:1046-1245, replaced whole);
  - delete `ComposeStage._black_screen` (:1492-1521).
- Modify: `src/pipeline/cli_compose.py`: import; delete `_scene_final_cache_paths` (:57-65); use
  the shared helper (:210)
- Modify (comments only): `src/pipeline/composer/toon.py:3-4`, `src/pipeline/composer/chart.py:315-318`
- Test: `tests/unit/test_compose_v2.py` (append)

**Interfaces:**
- Consumes (Task 2):
  - `_write_fake_mp4(cmd)` and `_prep_storyboard(ctx, scenes, seg_sec=5.0) -> Path` in
    `tests/unit/test_compose_v2.py`;
  - `render_scene(..., project_root=)`.
- Produces:
  - `pipeline.stages.compose.scene_final_cache_paths(scenes_dir: Path, scene_id: str) -> list[Path]`
    is the one source of truth for "what makes a scene look cached". It moves here from
    `cli_compose._scene_final_cache_paths`, which is deleted.
  - `_scene_step(scene_id: str, step: str, suggested_fix: str, *, include_error: bool = False)` is
    a context manager. A `SceneRenderError` passes through unchanged; any other exception becomes
    `SceneRenderError(reason=_step_reason(step, exc))`.
  - `_step_reason(step: str, exc: BaseException) -> str` gives
    `"<step> failed: <ExcType>: <message>"`, plus `" | stderr: <tail>"` for a
    `CalledProcessError`.
  - `_scene_fixes(project_id: str, scene_id: str) -> dict[str, str]`, with the keys `visual`,
    `compartment`, `overlay rule` and `frame/mux`.
  - `_render_one_scene` keeps invariant I1. `ComposeStage._black_screen` no longer exists.

- [ ] **Step 1: Write the failing tests.** Append to `tests/unit/test_compose_v2.py`:

```python


def _text_scene(sid: str = "s1", **kwargs) -> Scene:
    return Scene(id=sid, section="hook", narration="t", narration_est_sec=5,
                 visual={"type": "text_card", "text": "Hook"}, **kwargs)


def _visual_file(scenes_dir: Path, sid: str = "s1") -> Path:
    out = scenes_dir / f"{sid}_visual.mp4"
    out.write_bytes(b"fake visual")
    return out


def _scene_ctx(tmp_path: Path):
    from pipeline.stages.base import PipelineContext

    return PipelineContext(project_id=1, source_url="x", locale="zh-TW",
                           work_dir=tmp_path / "proj", burn_subtitles=False)


async def _render_s1_directly(stage, ctx, scenes_dir, frame_style):
    scene = _text_scene()
    return await stage._render_one_scene(
        i=0, scene=scene,
        scene_dict={"id": "s1", "visual": scene.visual, "overlay": None,
                    "compartment": None, "narration": scene.narration},
        duration=1.0, audio_path=None, width=1280, height=720, scenes_dir=scenes_dir,
        source_video=None, theme_dict={}, frame_style=frame_style, ctx=ctx, audio_segments=[],
    )


async def test_generic_visual_failure_refuses_assembly_without_black(sample_context):
    """P1: any non-SceneRenderError from render_scene used to be swapped for a black screen
    and assembled. It must refuse assembly with the step, the error and an actionable fix."""
    scenes_dir = _prep_storyboard(sample_context, [_text_scene()])
    with (
        patch("pipeline.stages.compose.check_ffmpeg_available", return_value=True),
        patch("pipeline.stages.compose.render_scene", side_effect=RuntimeError("provider exploded")),
        patch("pipeline.stages.compose.run_ffmpeg", side_effect=_write_fake_mp4),
        pytest.raises(RuntimeError, match="final assembly refused"),
    ):
        await ComposeStage().run(sample_context)

    failure = sample_context.render_failures["s1"]
    assert "visual (text_card) failed: RuntimeError: provider exploded" in failure["reason"]
    pid = sample_context.work_dir.name
    assert f"uv run pipeline validate {pid}" in failure["suggested_fix"]
    assert f"compose rescene --project-id {pid} --scene s1" in failure["suggested_fix"]
    assert sorted(p.name for p in scenes_dir.glob("s1_final*.mp4")) == []
    assert not (scenes_dir / "s1_black.mp4").exists()


async def test_overlay_rule_violation_refuses_assembly(sample_context):
    """P2: check_overlay_allowed raises OverlayCollisionError (a ValueError the validator never
    checks); it used to fall into the outer black fallback and ship."""
    scenes_dir = _prep_storyboard(
        sample_context, [_text_scene(overlay={"type": "text_top", "text": "hi"})],
    )
    with (
        patch("pipeline.stages.compose.check_ffmpeg_available", return_value=True),
        patch("pipeline.stages.compose.render_scene", return_value=_visual_file(scenes_dir)),
        patch("pipeline.stages.compose.run_ffmpeg", side_effect=_write_fake_mp4),
        pytest.raises(RuntimeError, match="final assembly refused"),
    ):
        await ComposeStage().run(sample_context)

    failure = sample_context.render_failures["s1"]
    assert failure["reason"].startswith("overlay rule failed: OverlayCollisionError:")
    assert "cannot apply 'text_top' overlay to 'text_card' visual" in failure["reason"]
    assert "cannot apply 'text_top'" in failure["suggested_fix"]
    assert "scene.overlay" in failure["suggested_fix"]
    assert sorted(p.name for p in scenes_dir.glob("s1_final*.mp4")) == []


async def test_compartment_failure_refuses_assembly(sample_context):
    """P4: a compartment build failure used to log a warning and ship the scene without it."""
    scenes_dir = _prep_storyboard(
        sample_context, [_text_scene(compartment={"type": "loop", "asset": "missing.png"})],
    )
    with (
        patch("pipeline.stages.compose.check_ffmpeg_available", return_value=True),
        patch("pipeline.stages.compose.render_scene", return_value=_visual_file(scenes_dir)),
        patch("pipeline.stages.compose.build_compartment_loop",
              side_effect=RuntimeError("compartment exploded")),
        patch("pipeline.stages.compose.run_ffmpeg", side_effect=_write_fake_mp4),
        pytest.raises(RuntimeError, match="final assembly refused"),
    ):
        await ComposeStage().run(sample_context)

    failure = sample_context.render_failures["s1"]
    assert failure["reason"] == "compartment failed: RuntimeError: compartment exploded"
    assert "scene.compartment" in failure["suggested_fix"]
    assert sorted(p.name for p in scenes_dir.glob("s1_final*.mp4")) == []


async def test_render_one_scene_post_visual_failure_raises_and_leaves_no_cache(tmp_path):
    """P2 at the frame step: _render_one_scene used to mux black to the frame-suffixed cache
    paths and return normally."""
    from pipeline.errors import SceneRenderError

    ctx = _scene_ctx(tmp_path)
    scenes_dir = ctx.work_dir / "compose" / "scenes"
    scenes_dir.mkdir(parents=True)
    with (
        patch("pipeline.stages.compose.render_scene", return_value=_visual_file(scenes_dir)),
        patch("pipeline.stages.compose.composite_scene_frame",
              side_effect=RuntimeError("frame exploded")),
        patch("pipeline.stages.compose.run_ffmpeg", side_effect=_write_fake_mp4),
        pytest.raises(SceneRenderError) as ei,
    ):
        await _render_s1_directly(ComposeStage(), ctx, scenes_dir, "open_book_page")

    assert ei.value.reason == "frame/mux failed: RuntimeError: frame exploded"
    assert not (scenes_dir / "s1_final_open_book_page.mp4").exists()
    assert not (scenes_dir / "s1_final_no_overlay_open_book_page.mp4").exists()


async def test_escaped_scene_exception_leaves_no_cached_black(sample_context):
    """P3: an exception escaping _render_one_scene used to leave black stand-ins at the
    unsuffixed cache paths, and never cleaned the frame-suffixed ones."""
    scenes_dir = _prep_storyboard(sample_context, [_text_scene()])
    (scenes_dir / "s1_final_open_book_page.mp4").write_bytes(b"stale")  # an earlier framed run

    async def _escaped(self, **kwargs):
        raise RuntimeError("escaped the scene boundary")

    with (
        patch("pipeline.stages.compose.check_ffmpeg_available", return_value=True),
        patch.object(ComposeStage, "_render_one_scene", _escaped),
        patch("pipeline.stages.compose.run_ffmpeg", side_effect=_write_fake_mp4),
        pytest.raises(RuntimeError, match="final assembly refused"),
    ):
        await ComposeStage().run(sample_context)

    assert sorted(p.name for p in scenes_dir.glob("s1_final*.mp4")) == []
    assert "escaped the scene boundary" in sample_context.render_failures["s1"]["reason"]


async def test_refused_compose_rerun_does_not_cache_hit(sample_context):
    """P1 + cache: the first failing run used to assemble and cache black, so the second run
    never retried the visual."""
    _prep_storyboard(sample_context, [_text_scene()])
    with (
        patch("pipeline.stages.compose.check_ffmpeg_available", return_value=True),
        patch("pipeline.stages.compose.render_scene",
              side_effect=RuntimeError("provider exploded")) as mock_render,
        patch("pipeline.stages.compose.run_ffmpeg", side_effect=_write_fake_mp4),
    ):
        for _run in range(2):
            with pytest.raises(RuntimeError, match="final assembly refused"):
                await ComposeStage().run(sample_context)

    assert mock_render.call_count == 2


# Review Focus (E5 plan): inputs the spec implies that §10's tests do not reach.


async def test_unreadable_cached_scene_is_deleted_and_refused(sample_context):
    """RF1: a cached scene file ffprobe cannot read must not be trusted: refuse with the
    `cached scene` step, delete both cache files, and re-render on the next run."""
    import subprocess

    scenes_dir = _prep_storyboard(sample_context, [_text_scene()])
    (scenes_dir / "s1_final.mp4").write_bytes(b"truncated")
    (scenes_dir / "s1_final_no_overlay.mp4").write_bytes(b"truncated")
    unreadable = subprocess.CalledProcessError(1, ["ffprobe"], stderr="moov atom not found")

    with (
        patch("pipeline.stages.compose.check_ffmpeg_available", return_value=True),
        patch("pipeline.stages.compose._get_duration_sec", side_effect=unreadable),
        patch("pipeline.stages.compose.render_scene") as mock_render,
        patch("pipeline.stages.compose.run_ffmpeg", side_effect=_write_fake_mp4),
        pytest.raises(RuntimeError, match="final assembly refused"),
    ):
        await ComposeStage().run(sample_context)

    failure = sample_context.render_failures["s1"]
    assert failure["reason"].startswith("cached scene failed: CalledProcessError:")
    assert "deleted" in failure["suggested_fix"]
    assert mock_render.call_count == 0
    assert sorted(p.name for p in scenes_dir.glob("s1_final*.mp4")) == []

    with (
        patch("pipeline.stages.compose.check_ffmpeg_available", return_value=True),
        patch("pipeline.stages.compose._get_duration_sec", return_value=5.0),
        patch("pipeline.stages.compose.render_scene",
              return_value=_visual_file(scenes_dir)) as mock_render,
        patch("pipeline.stages.compose.run_ffmpeg", side_effect=_write_fake_mp4),
    ):
        await ComposeStage().run(sample_context)
    assert mock_render.call_count == 1


async def test_second_mux_failure_leaves_neither_cache_file(tmp_path):
    """RF2: ffmpeg wrote s1_final.mp4, then died half-way through s1_final_no_overlay.mp4.
    Neither file may survive (the cache check needs only both to exist), and the reason
    must carry ffmpeg's own error so the fix is actionable."""
    import subprocess

    from pipeline.errors import SceneRenderError

    ctx = _scene_ctx(tmp_path)
    scenes_dir = ctx.work_dir / "compose" / "scenes"
    scenes_dir.mkdir(parents=True)

    def _dies_on_no_overlay(cmd):
        out = Path(cmd[-1])
        out.write_bytes(b"partial")
        if out.name.startswith("s1_final_no_overlay"):
            raise subprocess.CalledProcessError(1, cmd, stderr="Error writing trailer: No space left on device")

    with (
        patch("pipeline.stages.compose.render_scene", return_value=_visual_file(scenes_dir)),
        patch("pipeline.stages.compose.run_ffmpeg", side_effect=_dies_on_no_overlay),
        pytest.raises(SceneRenderError) as ei,
    ):
        await _render_s1_directly(ComposeStage(), ctx, scenes_dir, None)

    assert ei.value.reason.startswith("frame/mux failed: CalledProcessError:")
    assert "No space left on device" in ei.value.reason
    assert not (scenes_dir / "s1_final.mp4").exists()
    assert not (scenes_dir / "s1_final_no_overlay.mp4").exists()


async def test_several_failed_scenes_all_reported_and_good_scene_stays_cached(sample_context):
    """RF3: two scenes fail in one run. Both are recorded and named; the good scene s10
    (whose id starts with a failed one's) keeps its cache, so the rescene is cheap."""
    scenes = [_text_scene("s1"), _text_scene("s2"), _text_scene("s10")]
    scenes_dir = _prep_storyboard(sample_context, scenes)
    failing = {"s1", "s2"}
    rendered: list[str] = []

    def _render(scene, duration, aspect_ratio, work_dir, source_video=None, theme=None,
                project_root=None):
        rendered.append(scene["id"])
        if scene["id"] in failing:
            raise RuntimeError(f"provider exploded for {scene['id']}")
        return _visual_file(Path(work_dir), scene["id"])

    with (
        patch("pipeline.stages.compose.check_ffmpeg_available", return_value=True),
        patch("pipeline.stages.compose.render_scene", side_effect=_render),
        patch("pipeline.stages.compose.run_ffmpeg", side_effect=_write_fake_mp4),
        patch("pipeline.stages.compose._get_duration_sec", return_value=5.0),
    ):
        with pytest.raises(RuntimeError, match="final assembly refused") as ei:
            await ComposeStage().run(sample_context)
        assert "s1: " in str(ei.value) and "s2: " in str(ei.value)
        assert set(sample_context.render_failures) == {"s1", "s2"}
        assert (scenes_dir / "s10_final.mp4").exists()
        assert (scenes_dir / "s10_final_no_overlay.mp4").exists()
        assert sorted(p.name for p in scenes_dir.glob("s1_final*.mp4")) == []
        assert sorted(p.name for p in scenes_dir.glob("s2_final*.mp4")) == []

        failing.clear()
        rendered.clear()
        await ComposeStage().run(sample_context)

    assert sorted(rendered) == ["s1", "s2"]  # s10 came from its cache
```

- [ ] **Step 2: Run it to verify it fails.**
  Run `uv run pytest tests/unit/test_compose_v2.py -q`. Expected: `9 failed, 17 passed`, with the
  messages in ledger rows T1-T6 and RF1-RF3. Paste each observed line into its row, and put
  Task 2's fix SHA in rows T8b-RF5.

- [ ] **Step 3: Commit the red tests.**

```bash
git add tests/unit/test_compose_v2.py docs/superpowers/plans/2026-09-29-e5-loud-failure-sweep.md
git commit -m "test(compose): red — scene failures refuse assembly, never black (E5 T1-T6)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 4: Confirm the callers (spec R6).** Run
  `grep -rn "_render_one_scene\|_black_screen\|_scene_final_cache_paths" src/`. Expected:
  - `_render_one_scene`: its `def` and one call, both in `stages/compose.py`;
  - `_black_screen`: its `def` and its three call sites, all in `stages/compose.py`;
  - `_scene_final_cache_paths`: `cli_compose.py:57` and `:210`.

  If anything else calls them, stop and report it.

- [ ] **Step 5: Implement.** All in `src/pipeline/stages/compose.py` unless noted.

  **5a. Imports.** After `import subprocess`, add:

```python
from collections.abc import Iterator
from contextlib import contextmanager
```

  **5b. Module helpers.** Insert these directly above `@dataclass` /
  `class ComposeSceneResult:`, and replace that class's docstring:

```python
_CACHED_SCENE_FIX = "The cached scene file was unreadable and has been deleted; re-run compose."
_OVERLAY_FIX = (
    "Fix or remove scene.overlay (check overlay.type and text), "
    "or re-run with --skip-overlays to bypass overlays."
)


def scene_final_cache_paths(scenes_dir: Path, scene_id: str) -> list[Path]:
    """Every scene-final file that makes a scene look cached, frame-suffix variants included.

    One source of truth for compose's failure cleanup and `compose rescene`.
    """
    paths: list[Path] = [
        scenes_dir / f"{scene_id}_final.mp4",
        scenes_dir / f"{scene_id}_final_no_overlay.mp4",
    ]
    paths.extend(sorted(scenes_dir.glob(f"{scene_id}_final_*.mp4")))
    paths.extend(sorted(scenes_dir.glob(f"{scene_id}_final_no_overlay_*.mp4")))
    return list(dict.fromkeys(paths))


def _scene_fixes(project_id: str, scene_id: str) -> dict[str, str]:
    """Actionable suggested_fix text for each compose scene step (E5 spec §5.1)."""
    rescene = f"`uv run pipeline compose rescene --project-id {project_id} --scene {scene_id}`"
    return {
        "visual": (
            f"Run `uv run pipeline validate {project_id}`, fix `scene.visual`, then {rescene}."
        ),
        "compartment": f"Fix or remove `scene.compartment`, then {rescene}.",
        "overlay rule": (
            "Remove or change `scene.overlay` (title and namecard overlays fit any visual), "
            f"then {rescene}."
        ),
        "frame/mux": f"Inspect the ffmpeg error in the reason, then {rescene}.",
    }


def _step_reason(step: str, exc: BaseException) -> str:
    """`<step> failed: <ExcType>: <message>`, plus the tail of ffmpeg's stderr if any."""
    reason = f"{step} failed: {type(exc).__name__}: {exc}"
    if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
        err = exc.stderr if isinstance(exc.stderr, str) else exc.stderr.decode("utf-8", "replace")
        reason += f" | stderr: {err.strip()[-400:]}"
    return reason


@contextmanager
def _scene_step(
    scene_id: str, step: str, suggested_fix: str, *, include_error: bool = False,
) -> Iterator[None]:
    """Run one scene-render step. A SceneRenderError passes through unchanged; any other
    exception becomes a SceneRenderError naming the step. With *include_error*, the
    error message leads the suggested_fix (it already says what to change)."""
    try:
        yield
    except SceneRenderError:
        raise
    except Exception as exc:
        fix = f"{exc} {suggested_fix}" if include_error else suggested_fix
        raise SceneRenderError(
            scene=scene_id, reason=_step_reason(step, exc), suggested_fix=fix,
        ) from exc


@dataclass
class ComposeSceneResult:
    """One scene that rendered (or cache-hit) cleanly. A failed scene raises
    SceneRenderError instead; there is no stand-in result."""
```

  (The field list of `ComposeSceneResult` stays as it is.)

  **5c. The gather loop (P3, §5.2).** In `_compose_from_storyboard`, replace everything from
  `        # Collect results with fallbacks for failed scenes` up to (not including)
  `        if failures:` with:

```python
        # A failed scene refuses assembly: record why, and leave no file at any of its
        # cache paths (every frame-suffix variant), so the next run re-renders it.
        results: list[ComposeSceneResult] = []
        failures: list[str] = []
        render_failures: dict[str, dict[str, str]] = {}
        for i, maybe in enumerate(done):
            if isinstance(maybe, BaseException):
                sid = storyboard.scenes[i].id
                logger.error("compose.scene.exception", scene_id=sid, error=str(maybe))
                failures.append(f"{sid}: {maybe}")
                if isinstance(maybe, SceneRenderError):
                    render_failures[sid] = maybe.to_dict()
                else:
                    # Unreachable while _render_one_scene keeps I1; kept as a defence.
                    render_failures[sid] = {
                        "scene": sid,
                        "reason": str(maybe),
                        "suggested_fix": "Inspect the scene render logs and fix the visual contract.",
                    }
                for cached in scene_final_cache_paths(scenes_dir, sid):
                    cached.unlink(missing_ok=True)
            else:
                results.append(maybe)

```

  The `if failures:` block after it (save `render_failures`, raise
  `"Compose scene render failed; final assembly refused. …"`) stays unchanged.

  **5d. `_render_one_scene` (§5.1, P1/P2/P4).** Replace the whole method, from
  `    async def _render_one_scene(` up to (not including) the `    @staticmethod` line above
  `    async def _splice_transitions_async(`, with:

```python
    async def _render_one_scene(
        self,
        i: int,
        scene: Any,  # StoryboardScene
        scene_dict: dict[str, Any],
        duration: float,
        audio_path: Path | None,
        width: int,
        height: int,
        scenes_dir: Path,
        source_video: Path | None,
        theme_dict: dict[str, str],
        frame_style: str | None,
        ctx: PipelineContext,
        audio_segments: list[dict],
    ) -> ComposeSceneResult:
        """Render one complete scene (visual → compartment → overlay → frame/mux).

        Runs the synchronous render chain in the shared thread pool so the
        event loop stays free.  Scene-internal steps remain sequential;
        concurrency is across scenes.

        Returns a result whose two cache files are real renders, or raises
        SceneRenderError. When it raises, neither cache path the cache check reads
        exists, so the next run re-renders the scene instead of cache-hitting a
        stand-in (E5 invariant I1).
        """
        frame_suffix = f"_{frame_style}" if frame_style else ""
        scene_final = scenes_dir / f"{scene.id}_final{frame_suffix}.mp4"
        scene_final_no_overlay = scenes_dir / f"{scene.id}_final_no_overlay{frame_suffix}.mp4"
        fixes = _scene_fixes(ctx.work_dir.name, scene.id)

        try:
            # Cache check
            if scene_final.exists() and scene_final_no_overlay.exists():
                with _scene_step(scene.id, "cached scene", _CACHED_SCENE_FIX):
                    logger.info("compose.scene.cached", scene_id=scene.id)
                    if i < len(audio_segments):
                        d_check = audio_segments[i]["duration_ms"] / 1000.0
                        actual = _get_duration_sec(scene_final)
                        if actual < d_check - 0.5:
                            logger.warning(
                                "compose.scene.duration_mismatch",
                                scene_id=scene.id,
                                cached_sec=round(actual, 2),
                                expected_sec=round(d_check, 2),
                                hint="Delete cached scene files and rescene to fix subtitle drift",
                            )
                cached_pause: list[Path] = []
                if scene.pause_after_sec > 0:
                    with _scene_step(scene.id, "frame/mux", fixes["frame/mux"]):
                        cached_pause = [self._silence_gap(
                            scenes_dir, scene.id, scene.pause_after_sec, width, height,
                        )]
                return ComposeSceneResult(
                    index=i,
                    scene_final=scene_final,
                    scene_final_no_overlay=scene_final_no_overlay,
                    pause_paths=cached_pause,
                    pause_paths_no_overlay=list(cached_pause),
                )

            logger.info("compose.scene", scene_id=scene.id, duration=f"{duration:.1f}s")
            visual_type = str((scene_dict.get("visual") or {}).get("type") or "text_card")

            def _render_sync() -> Path | None:
                """Synchronous scene render (thread pool). Returns the pause clip, if any."""
                # Step 1: Render visual
                with _scene_step(scene.id, f"visual ({visual_type})", fixes["visual"]):
                    vis = render_scene(
                        scene_dict,
                        duration,
                        "16:9",  # aspect_ratio default; storyboard-driven is 16:9
                        scenes_dir,
                        source_video=source_video,
                        theme=theme_dict,
                        project_root=ctx.work_dir,
                    )

                # Frameless scenes: scale the visual to fill the full canvas so every
                # clip shares the canvas resolution (the open_book_page frame did this
                # placement for framed scenes; without it, inset-sized refit crops
                # would break the uniform-dimension concat).
                if not frame_style:
                    with _scene_step(scene.id, "frame/mux", fixes["frame/mux"]):
                        vis = self._fit_to_canvas(
                            vis, scenes_dir / f"{scene.id}_fullbleed.mp4", width, height
                        )

                # Step 1b: Compartment animation
                if scene.compartment:
                    with _scene_step(scene.id, "compartment", fixes["compartment"]):
                        comp_vid = build_compartment_loop(
                            compartment=scene.compartment,
                            scene_duration_sec=duration,
                            scene_width=width,
                            scene_height=height,
                            work_dir=scenes_dir,
                            scene_id=scene.id,
                        )
                        vis = composite_compartment_on_scene(
                            scene_video=vis,
                            compartment_video=comp_vid,
                            compartment_config=scene.compartment,
                            scene_width=width,
                            scene_height=height,
                            work_dir=scenes_dir,
                            scene_id=scene.id,
                        )

                # Step 2: Overlay
                vis_before_overlay = vis
                with _scene_step(
                    scene.id, "overlay rule", fixes["overlay rule"], include_error=True,
                ):
                    check_overlay_allowed(
                        scene=scene_dict,
                        overlay=scene.overlay,
                        visual=scene.visual,
                        burn_subtitles=ctx.burn_subtitles,
                    )
                if scene.overlay and not ctx.skip_overlays:
                    with _scene_step(scene.id, "overlay", _OVERLAY_FIX):
                        vis = apply_overlay(
                            visual_path=vis,
                            overlay=scene.overlay,
                            width=width, height=height,
                            work_dir=scenes_dir,
                            scene_id=scene.id,
                            theme=theme_dict,
                        )

                # Step 3: Frame + mux both variants; Step 4: pause gap
                with _scene_step(scene.id, "frame/mux", fixes["frame/mux"]):
                    if frame_style:
                        vis = composite_scene_frame(
                            vis,
                            scenes_dir / f"{scene.id}_visual{frame_suffix}.mp4",
                            frame_style=frame_style,
                            width=width,
                            height=height,
                        )
                        vis_before_overlay = composite_scene_frame(
                            vis_before_overlay,
                            scenes_dir / f"{scene.id}_visual_no_overlay{frame_suffix}.mp4",
                            frame_style=frame_style,
                            width=width,
                            height=height,
                        )
                    self._mux(vis, scene_final, audio_path)
                    no_overlay_vis = vis_before_overlay if scene.overlay else vis
                    self._mux(no_overlay_vis, scene_final_no_overlay, audio_path)
                    if scene.pause_after_sec > 0:
                        return self._silence_gap(
                            scenes_dir, scene.id, scene.pause_after_sec, width, height,
                        )
                return None

            loop = asyncio.get_running_loop()
            pause = await loop.run_in_executor(get_ffmpeg_executor(), _render_sync)
        except Exception as e:
            # I1: no stand-in and no half-written file may stay where the cache check looks.
            scene_final.unlink(missing_ok=True)
            scene_final_no_overlay.unlink(missing_ok=True)
            if isinstance(e, SceneRenderError):
                raise
            raise SceneRenderError(
                scene=scene.id,
                reason=_step_reason("frame/mux", e),
                suggested_fix=fixes["frame/mux"],
            ) from e

        pause_paths = [pause] if pause else []
        return ComposeSceneResult(
            index=i,
            scene_final=scene_final,
            scene_final_no_overlay=scene_final_no_overlay,
            pause_paths=pause_paths,
            pause_paths_no_overlay=list(pause_paths),
        )

```

  **5e. Delete `ComposeStage._black_screen` (§5.3).** Remove the whole method, from
  `    def _black_screen(` up to (not including) `    def _silence_gap(`. Leave
  `_silence_gap` exactly as it is.

  **5f. `src/pipeline/cli_compose.py`.** Replace the import line
  `from pipeline.stages.compose import ComposeStage, _burn_subtitle_pass, verify_theme_fonts`
  with:

```python
from pipeline.stages.compose import (
    ComposeStage,
    _burn_subtitle_pass,
    scene_final_cache_paths,
    verify_theme_fonts,
)
```

  Delete the whole `def _scene_final_cache_paths(...)` function (lines 57-65) and its trailing
  blank lines. In `rescene`, change `for p in _scene_final_cache_paths(scenes_dir, scene_id):` to
  `for p in scene_final_cache_paths(scenes_dir, scene_id):`.

  **5g. Comments that describe the old fallback (§5.6).** In `src/pipeline/composer/toon.py`,
  replace docstring lines 3-4 with:

```python
Every failure is a SceneRenderError carrying the toon-specific fix (`pipeline toon
validate`); compose would otherwise only wrap it generically as `visual (toon) failed`.
```

  In `src/pipeline/composer/chart.py`, replace the four comment lines above
  `raise SceneRenderError(` in `render_chart`'s `except CalloutPlacementError` with:

```python
        # The precise render-time fence for marker density (pin-down #2): convert
        # the geometry exception into a SceneRenderError with a chart-specific fix
        # hint, instead of compose's generic `visual (chart) failed` wrap.
```

- [ ] **Step 6: Run the tests to verify they pass.**
  - Run `uv run pytest tests/unit/test_compose_v2.py -q`. Expected: `26 passed`. This includes
    the existing `test_overlay_failure_refuses_assembly_and_records_loudly` and
    `test_scene_render_error_leaves_no_cached_black_fallback`.
  - Run `grep -rn "_black_screen\|black-screen\|black screen" src/`. Expected: no output.
  - Run
    `uv run pytest tests/unit/test_cli_compose.py tests/unit/test_cli_compose_music.py tests/unit/test_cli_compose_transition_invalidation.py tests/unit/test_composer_toon.py tests/unit/test_chart.py -q`.
    Expected: all pass.
  - Run `uv run pytest -q`, `uv run ruff check src/ tests/` and `uv run mypy src/`. Expected on
    base: `1368 passed, 59 skipped`, then clean, then clean.

- [ ] **Step 7: Commit the fix.** First put the red commit's SHA in rows T1-RF3.

```bash
git add src/pipeline/stages/compose.py src/pipeline/cli_compose.py src/pipeline/composer/toon.py \
        src/pipeline/composer/chart.py docs/superpowers/plans/2026-09-29-e5-loud-failure-sweep.md
git commit -m "fix(compose): one loud scene boundary; no black stand-ins in finals or cache (E5 §5.1-5.3)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: image_sequence refuses instead of a black sub-clip, plus the black-fallback fences (spec §5.4, §5.6; T7, T11b, T11c, RF4)

**Files:**
- Modify: `src/pipeline/composer/image_sequence.py`: imports; `_fetch_image` (:53-91); delete
  `_black_clip` (:94-102); the loop in `render_image_sequence` (:135-143)
- Test (create): `tests/unit/test_image_sequence.py`
- Test: `tests/unit/test_loud_failure_fence.py` (append T11b, T11c)

**Interfaces:**
- Consumes:
  - `pipeline.errors.SceneRenderError`;
  - `PKG` and `ast` from `tests/unit/test_loud_failure_fence.py` (Task 2);
  - `ComposeStage._silence_gap`, which stays the only black lavfi source after Task 3.
- Produces:
  - `_fetch_image(prompt, tier, cache_dir, scene_id, idx, width, height) -> Path`, which raises
    `ProviderError` instead of returning `None`;
  - `render_image_sequence` raises
    `SceneRenderError(reason="image_sequence image <idx> failed to generate: <provider error>")`;
  - `_black_clip` no longer exists.

- [ ] **Step 1: Write the failing tests.**

  **1a.** Create `tests/unit/test_image_sequence.py` (T7 and RF4):

```python
"""image_sequence: one image failing to generate refuses the scene, never a black sub-clip.

Spec: docs/superpowers/specs/2026-09-29-e5-loud-failure-sweep-design.md §5.4
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from pipeline.composer import image_sequence
from pipeline.errors import SceneRenderError
from pipeline.providers.base import ProviderError, ProviderResult

VISUAL = {
    "type": "image_sequence",
    "images": [{"prompt": "a calm kitchen at dawn"}, {"prompt": "a stormy sea at night"}],
}


@pytest.fixture
def fake_media(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Fake provider, Ken Burns and ffmpeg. Prompts containing a word in state["fail"]
    raise ProviderError; the rest write a bright PNG to the prompt-hash cache path."""
    state: dict = {"fail": {"stormy"}, "prompts": [], "ffmpeg": []}

    def fake_try_chain(providers, *, prompt, out_path, size, reference_image=None):
        state["prompts"].append(prompt)
        if any(word in prompt for word in state["fail"]):
            raise ProviderError("all image providers failed; last error: fal 503 upstream")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (64, 36), (240, 240, 230)).save(out_path)
        return ProviderResult(path=out_path, provider="fake")

    def fake_image_to_video(png, out, duration, width, height, **kwargs):
        out.write_bytes(b"clip")
        return out

    def fake_run_ffmpeg(cmd, timeout=600):
        state["ffmpeg"].append([str(c) for c in cmd])
        Path(cmd[-1]).write_bytes(b"mp4")

    monkeypatch.setattr(image_sequence, "try_chain", fake_try_chain)
    monkeypatch.setattr(image_sequence, "image_to_video", fake_image_to_video)
    monkeypatch.setattr(image_sequence, "run_ffmpeg", fake_run_ffmpeg)
    return state


def test_failed_image_raises_scene_render_error_not_black(tmp_path, fake_media):
    with pytest.raises(SceneRenderError) as ei:
        image_sequence.render_image_sequence(VISUAL, 6.0, 1280, 720, tmp_path, "s3")

    err = ei.value
    assert err.scene == "s3"
    assert "image_sequence image 1 failed to generate" in err.reason
    assert "fal 503 upstream" in err.reason
    assert "pipeline doctor" in err.suggested_fix and "--scene s3" in err.suggested_fix
    assert not any("color=c=black" in " ".join(cmd) for cmd in fake_media["ffmpeg"])
    assert not (tmp_path / "s3_seq1_visual.mp4").exists()
    assert not (tmp_path / "s3_visual.mp4").exists()


def test_rerun_after_failed_image_regenerates_only_that_image(tmp_path, fake_media):
    """Review Focus RF4: the images that succeeded stay cached by prompt hash, so the
    retry the suggested_fix recommends asks the provider for the failed image only."""
    with pytest.raises(SceneRenderError):
        image_sequence.render_image_sequence(VISUAL, 6.0, 1280, 720, tmp_path, "s3")

    fake_media["fail"] = set()  # the provider recovered
    fake_media["prompts"].clear()
    out = image_sequence.render_image_sequence(VISUAL, 6.0, 1280, 720, tmp_path, "s3")

    assert out == tmp_path / "s3_visual.mp4"
    assert fake_media["prompts"] == ["a stormy sea at night"]
```

  **1b.** Append T11b and T11c to `tests/unit/test_loud_failure_fence.py`:

```python


def _str_constants_by_scope(tree: ast.Module):
    """Yield (enclosing Class.function qualname, text) for every str constant,
    f-string parts included."""

    def visit(node: ast.AST, scope: tuple[str, ...]):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                yield from visit(child, (*scope, child.name))
                continue
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                yield ".".join(scope), child.value
            yield from visit(child, scope)

    yield from visit(tree, ())


def test_no_black_fallback_helpers_remain():
    from pipeline.composer import image_sequence
    from pipeline.stages.compose import ComposeStage

    assert not hasattr(ComposeStage, "_black_screen")
    assert not hasattr(image_sequence, "_black_clip")


def test_black_lavfi_source_only_in_silence_gap():
    """A black lavfi source is legitimate only for pause_after_sec gaps (black by design).
    Anywhere else it is a stand-in that hides a failed scene."""
    hits = set()
    for py in sorted(PKG.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for scope, text in _str_constants_by_scope(tree):
            if "color=c=black" in text:
                hits.add((py.relative_to(PKG).as_posix(), scope))
    assert hits == {("stages/compose.py", "ComposeStage._silence_gap")}
```

- [ ] **Step 2: Run it to verify it fails.**
  Run `uv run pytest tests/unit/test_image_sequence.py tests/unit/test_loud_failure_fence.py -q`.
  Expected: `4 failed, 1 passed`, with the messages in ledger rows T7, RF4, T11b and T11c. Paste
  each observed line into its row, and put Task 3's fix SHA in rows T1-RF3.

- [ ] **Step 3: Commit the red tests.**

```bash
git add tests/unit/test_image_sequence.py tests/unit/test_loud_failure_fence.py \
        docs/superpowers/plans/2026-09-29-e5-loud-failure-sweep.md
git commit -m "test(compose): red — image_sequence failure refuses; black-fallback fences (E5 T7, T11)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 4: Implement.** All in `src/pipeline/composer/image_sequence.py`.

  **4a.** After `from pipeline.composer.base import image_to_video`, add
  `from pipeline.errors import SceneRenderError`. Keep the `ProviderError`, `try_chain` and
  `run_ffmpeg` imports; the concat still uses `run_ffmpeg`.

  **4b.** Replace `_fetch_image` and `_black_clip` (everything from `def _fetch_image(` up to,
  not including, `def render_image_sequence(`) with:

```python
def _fetch_image(
    prompt: str,
    tier: str,
    cache_dir: Path,
    scene_id: str,
    idx: int,
    width: int,
    height: int,
) -> Path:
    """Return the image for *prompt*: from the prompt-hash cache, else freshly generated.

    Raises ProviderError (with the provider's message) when generation fails.
    """
    cache_name = _cache_key(prompt)
    cached_png = cache_dir / f"{cache_name}.png"

    if cached_png.exists():
        if _is_too_dark(cached_png):
            logger.warning("image_seq.dark_evicted", scene=scene_id, idx=idx)
            cached_png.unlink()
        else:
            logger.info("image_seq.cache_hit", scene=scene_id, idx=idx, prompt=prompt[:50])
            return cached_png

    provider = GenImageProvider(tier=tier)
    result = try_chain(
        [provider],
        prompt=prompt,
        out_path=cached_png,
        size=_size_arg(width, height),
    )
    logger.info("image_seq.generated", scene=scene_id, idx=idx, provider=result.provider)
    if _is_too_dark(cached_png):
        cached_png.unlink()
        light_prompt = f"{prompt}, white background, bright cream paper, no dark areas"
        light_png = cache_dir / f"{_cache_key(light_prompt)}.png"
        try_chain([provider], prompt=light_prompt, out_path=light_png, size=_size_arg(width, height))
        cached_png = light_png
    return cached_png


```

  **4c.** In `render_image_sequence`'s loop, replace

```python
        tier = img_spec.get("image_tier", "draft")
        png = _fetch_image(prompt, tier, cache_dir, scene_id, idx, width, height)

        clip_path = work_dir / f"{scene_id}_seq{idx}_visual.mp4"
        if png:
            image_to_video(png, clip_path, clip_dur, width, height)
        else:
            clip_path = _black_clip(work_dir, scene_id, idx, clip_dur, width, height)
        clip_paths.append(clip_path)
```

  with

```python
        tier = img_spec.get("image_tier", "draft")
        try:
            png = _fetch_image(prompt, tier, cache_dir, scene_id, idx, width, height)
        except ProviderError as exc:
            logger.error("image_seq.generation_failed", scene=scene_id, idx=idx, error=str(exc))
            raise SceneRenderError(
                scene=scene_id,
                reason=f"image_sequence image {idx} failed to generate: {exc}",
                suggested_fix=(
                    "Check `uv run pipeline doctor` (home tool gen-image.py) and the image "
                    "provider's status, then `uv run pipeline compose rescene --project-id "
                    f"<project-id> --scene {scene_id}`. Images that already succeeded stay "
                    f"cached by prompt hash in {cache_dir}, so only image {idx} is regenerated."
                ),
            ) from exc

        clip_path = work_dir / f"{scene_id}_seq{idx}_visual.mp4"
        image_to_video(png, clip_path, clip_dur, width, height)
        clip_paths.append(clip_path)
```

  `<project-id>` is literal text in the user-facing message: `render_image_sequence` has no
  project id. The scene id and the cache dir are real values.

- [ ] **Step 5: Run the tests to verify they pass.**
  - Run
    `uv run pytest tests/unit/test_image_sequence.py tests/unit/test_loud_failure_fence.py tests/unit/test_output_paths.py -q`.
    Expected: all pass.
  - Four `DeprecationWarning: Image.Image.getdata is deprecated` warnings come from the existing
    `_is_too_dark`, which these tests now reach. That code is pre-existing, and the warnings are
    not failures.
  - Run `uv run pytest -q`, `uv run ruff check src/ tests/` and `uv run mypy src/`. Expected on
    base: `1372 passed, 59 skipped`, then clean, then clean.

- [ ] **Step 6: Commit the fix.** First put the red commit's SHA in rows T7-T11c.

```bash
git add src/pipeline/composer/image_sequence.py docs/superpowers/plans/2026-09-29-e5-loud-failure-sweep.md
git commit -m "fix(compose): image_sequence raises SceneRenderError instead of a black sub-clip (E5 §5.4)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5 (controller, on the Mac): gates, the A4 live fault-injection smoke, and reviews

The controller runs this itself, with no implementer subagent. It runs in the worktree, so the code
under test is the branch. The evidence goes to the **main checkout's**
`tmp/e5-sweep/smoke/`, so it survives worktree removal, and is never staged.
**No project data is copied to the Mac:** the scratch project is synthetic (ffmpeg `testsrc`
and silence). Shell variables don't persist between tool calls, so start every shell call with
the `WT` / `SMOKE` / `P` block.

```bash
WT=/Users/tim/content-creation/.worktrees/e5-loud-failure-sweep
SMOKE=/Users/tim/content-creation/tmp/e5-sweep/smoke
export PIPELINE_OUTPUT_DIR=$SMOKE/out
P=$PIPELINE_OUTPUT_DIR/projects/e5smoke
mkdir -p $SMOKE && cd $WT
```

- [ ] **Step 1: Gates (A2, A3, A7) and ledger.**
  - A2: run `uv run pytest -q`, `uv run ruff check src/ tests/` and `uv run mypy src/`. Expected:
    0 failed (base plus this sprint: `1372 passed, 59 skipped`), then clean, then clean.
  - A3:
    - Run
      `uv run pytest tests/unit/test_compose_v2.py tests/director/test_storyboard_validator.py tests/unit/test_composer_refit.py tests/director/still_gate -q`.
      Expected: `83 passed, 2 skipped` (the spec's baseline of 71+2, plus 12 new).
    - Run
      `uv run pytest tests/unit/test_cli_compose.py tests/unit/test_cli_compose_music.py tests/unit/test_cli_compose_transition_invalidation.py tests/unit/test_clip_renderer.py tests/unit/test_compose_dup_guard.py tests/unit/test_composer_base.py tests/unit/test_composer_toon.py tests/unit/test_chart.py -q`.
      Expected: all green.
  - A7: run `git diff --name-only master...HEAD`. Expected: only the §6 IN files (listed under
    Global Constraints), the tests and this plan. Then run
    `git diff master...HEAD -- src/pipeline/composer/base.py | grep -nE '^[+-].*(namecard|"map"|generated_image)'`.
    Expected: no output.
  - Put Task 4's fix SHA in rows T7-T11c, check that every ledger row now has an observed red and
    both SHAs, then commit the plan alone:

```bash
git add docs/superpowers/plans/2026-09-29-e5-loud-failure-sweep.md
git commit -m "docs(compose): E5 plan — red-run ledger complete

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 2: Write the four smoke helpers** into `$SMOKE/`. They live in `tmp/`, so they are
  never committed.

  `$SMOKE/make_project.py`:

```python
"""E5 smoke: build the 3-scene scratch project $PIPELINE_OUTPUT_DIR/projects/e5smoke.

Synthetic media only (ffmpeg testsrc + silence): no project data is copied to the Mac.
"""
import os
import shutil
import subprocess
from pathlib import Path

from pipeline.stages.base import PipelineContext
from pipeline.storyboard import Scene, Storyboard

SEG = 3.0
pdir = Path(os.environ["PIPELINE_OUTPUT_DIR"]) / "projects" / "e5smoke"
(pdir / "source").mkdir(parents=True, exist_ok=True)
(pdir / "audio").mkdir(exist_ok=True)


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


# s1: a 6 s testsrc clip (colour bars + counter). A pristine copy stays outside source/.
ff("-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30:duration=6", "-pix_fmt", "yuv420p",
   str(pdir / "clip_good.mp4"))
shutil.copyfile(pdir / "clip_good.mp4", pdir / "source" / "clip.mp4")

timings = []
for i in range(3):
    seg = pdir / "audio" / f"seg_{i:03d}.mp3"
    ff("-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", str(SEG), "-c:a", "libmp3lame",
       str(seg))
    timings.append({"index": i, "text": f"scene {i + 1}", "path": str(seg),
                    "start_ms": int(i * SEG * 1000), "duration_ms": int(SEG * 1000)})
ff("-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", str(3 * SEG), "-c:a", "libmp3lame",
   str(pdir / "audio" / "narration.mp3"))
(pdir / "audio" / "subs.srt").write_text(
    "1\n00:00:00,000 --> 00:00:03,000\nscene one\n", encoding="utf-8")

Storyboard(scenes=[
    Scene(id="s1", section="hook", narration="scene one", narration_est_sec=SEG,
          visual={"type": "clip", "path": "source/clip.mp4", "start_sec": 0, "end_sec": 3}),
    Scene(id="s2", section="context", narration="scene two", narration_est_sec=SEG,
          visual={"type": "text_card", "text": "Loud failure smoke"}),
    Scene(id="s3", section="analysis", narration="scene three", narration_est_sec=SEG,
          visual={"type": "chart", "chart_type": "stat_big_number", "ai_background": False,
                  "title": "Smoke check", "source_credit": "E5 sweep",
                  "data": {"value": "3", "unit": "scenes"}}),
]).save(pdir / "storyboard.json")

# video_path stays None: style_anchor._assess_source (a Claude call) only runs on a source video.
PipelineContext(
    project_id="e5smoke", source_url="smoke://e5", locale="zh-TW", work_dir=pdir,
    niche="none", storyboard_path=pdir / "storyboard.json",
    narration_path=pdir / "audio" / "narration.mp3", subtitle_path=pdir / "audio" / "subs.srt",
    segment_timings=timings, burn_subtitles=False,
).save()
print(pdir)
```

  `$SMOKE/compose_once.py`:

```python
"""Run ComposeStage once on a saved project, deleting nothing first: the
`produce --start-from compose` path without produce's post-compose Claude visual QC.
Exit 0 = assembled, 1 = refused."""
import asyncio
import sys
from pathlib import Path

from pipeline.stages.base import PipelineContext
from pipeline.stages.compose import ComposeStage

ctx = PipelineContext.load(Path(sys.argv[1]) / "context.json")
try:
    asyncio.run(ComposeStage().run(ctx))
except Exception as exc:
    print(f"REFUSED: {exc}")
    sys.exit(1)
print(f"ASSEMBLED: {ctx.final_video_path}")
```

  `$SMOKE/facts.py`:

```python
"""Print the smoke evidence for one run: render_failures and the scene cache listing."""
import json
import sys
from pathlib import Path

pdir = Path(sys.argv[1])
ctx = json.loads((pdir / "context.json").read_text())
print("render_failures:", json.dumps(ctx.get("render_failures", {}), indent=2, ensure_ascii=False))
print("scene finals:", sorted(p.name for p in (pdir / "compose" / "scenes").glob("s*_final*.mp4")))
```

  `$SMOKE/luma.py`:

```python
"""Mean luma (0-255) of a PNG: black video is ~16, the testsrc frame is far brighter."""
import sys

from PIL import Image, ImageStat

print(round(ImageStat.Stat(Image.open(sys.argv[1]).convert("L")).mean[0], 1))
```

- [ ] **Step 3: Run 1. `pipeline validate` exits 0 and compose assembles, with a real s1 frame.**

```bash
rm -rf $SMOKE/out && uv run python $SMOKE/make_project.py
uv run pipeline validate e5smoke > $SMOKE/run1_validate.log 2>&1; echo "validate exit=$?"
uv run pipeline compose rescene --project-id e5smoke --scene s1 > $SMOKE/run1.log 2>&1; echo "compose exit=$?"
uv run python $SMOKE/facts.py $P
ffmpeg -y -hide_banner -loglevel error -ss 1.0 -i $P/compose/final_zh-TW.mp4 -frames:v 1 $SMOKE/run1_s1.png
uv run python $SMOKE/luma.py $SMOKE/run1_s1.png
```

  Expected:
  - `validate exit=0`;
  - `compose exit=0`, and `run1.log` ends `Done.`;
  - `render_failures: {}`;
  - six scene finals, from `s1_final.mp4` through `s3_final_no_overlay.mp4`;
  - luma well above 16 (the scratch run measured 124.4).

  The `compose.bitrate_low` warning is the existing advisory for synthetic static content, not a
  failure. **Open `$SMOKE/run1_s1.png` with the Read tool** and confirm it shows the testsrc
  colour bars, not black. Note that the cwd (the worktree root) is not the project dir, so this
  run also proves the project-relative `source/clip.mp4` resolved.

- [ ] **Step 4: Run 2. A corrupt clip (the file exists but won't decode) refuses.**

```bash
head -c 2048 $P/clip_good.mp4 > $P/source/clip.mp4
uv run pipeline compose rescene --project-id e5smoke --scene s1 > $SMOKE/run2.log 2>&1; echo "compose exit=$?"
grep -m1 "^RuntimeError: Compose scene render failed" $SMOKE/run2.log | cut -c1-300
uv run python $SMOKE/facts.py $P
```

  Expected:
  - `compose exit=1`;
  - `render_failures.s1.reason` starts `visual (clip) failed: CalledProcessError: Command '['ffprobe'`;
  - `suggested_fix` is
    ``Run `uv run pipeline validate e5smoke`, fix `scene.visual`, then `uv run pipeline compose rescene --project-id e5smoke --scene s1`.``;
  - `scene finals` lists no `s1_final*`, only s2's and s3's.

- [ ] **Step 5: Run 3. Re-run unchanged: it refuses again, with nothing served from cache.**

```bash
uv run python $SMOKE/compose_once.py $P > $SMOKE/run3.log 2>&1; echo "compose exit=$?"
grep -E "compose.scene.cached|compose.scene |render_scene " $SMOKE/run3.log | cut -c1-120
uv run python $SMOKE/facts.py $P | tail -1
```

  Expected:
  - `compose exit=1`;
  - the log shows `compose.scene … scene_id=s1` and `render_scene … scene_id=s1 type=clip` (s1
    was rendered again), and `compose.scene.cached` only for `s2` and `s3`;
  - still no `s1_final*`.

- [ ] **Step 6: Run 4. Restore the file, and compose assembles again.**

```bash
cp $P/clip_good.mp4 $P/source/clip.mp4
uv run pipeline compose rescene --project-id e5smoke --scene s1 > $SMOKE/run4.log 2>&1; echo "compose exit=$?"
uv run python $SMOKE/facts.py $P
ffmpeg -y -hide_banner -loglevel error -ss 1.0 -i $P/compose/final_zh-TW.mp4 -frames:v 1 $SMOKE/run4_s1.png
uv run python $SMOKE/luma.py $SMOKE/run4_s1.png
```

  Expected: `compose exit=0`, `render_failures: {}`, all six finals, and the same luma as run 1.
  Open `$SMOKE/run4_s1.png` with the Read tool and confirm it shows the testsrc bars.

- [ ] **Step 7: Run 5. A `text_top` overlay on the s2 text_card refuses with the overlay-rule
  reason.**

```bash
uv run python - <<'EOF'
import json, os
p = f"{os.environ['PIPELINE_OUTPUT_DIR']}/projects/e5smoke/storyboard.json"
d = json.loads(open(p, encoding="utf-8").read())
d["scenes"][1]["overlay"] = {"type": "text_top", "text": "overlay on a text card"}
open(p, "w", encoding="utf-8").write(json.dumps(d, indent=2, ensure_ascii=False))
EOF
uv run pipeline compose rescene --project-id e5smoke --scene s2 > $SMOKE/run5.log 2>&1; echo "compose exit=$?"
uv run python $SMOKE/facts.py $P
```

  Expected:
  - `compose exit=1`;
  - `render_failures.s2.reason` is
    `overlay rule failed: OverlayCollisionError: scene s2: cannot apply 'text_top' overlay to 'text_card' visual (text-on-text is unreadable).`;
  - `suggested_fix` starts with the same collision message and ends with the `rescene` command;
  - no `s2_final*`.

- [ ] **Step 8: Write `$SMOKE/evidence.md`.** It has one section per run, each with:
  - the exact commands;
  - the exit codes;
  - the `facts.py` output (the `context.json` `render_failures` excerpt and the scene-finals
    listing);
  - for runs 1 and 4, the frame path (`run1_s1.png`, `run4_s1.png`), its luma, and a one-line
    visual confirmation.

  Head it with the branch HEAD SHA (`git -C $WT rev-parse --short HEAD`) and the date. Don't
  stage it.

- [ ] **Step 9: Code-correctness review (A6).** The per-task reviews happened during
  subagent-driven execution. Now dispatch one final whole-branch review (sonnet or opus) over
  `git diff master...HEAD`. Point it at the Review Focus list and invariant I1. Resolve its
  findings with fix commits in the same `type(scope): message` form, then re-run Step 1.

- [ ] **Step 10: EM REVIEW (the definition of done).** Dispatch the `engineering-manager` skill
  in REVIEW mode, lean. Give it the branch name, this plan's path, the spec's path and
  `tmp/e5-sweep/smoke/evidence.md`. The EM runs A1's mutation checks and A5's hub path audit
  itself. On REWORK, fix and re-dispatch. On PASS, finish the branch with
  `superpowers:finishing-a-development-branch`: merge locally, and push only when Tim asks.
