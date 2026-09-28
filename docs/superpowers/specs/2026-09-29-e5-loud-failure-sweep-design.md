# Sprint 10 — E5 loud-failure sweep, part 1: no silent black scenes + one media-path resolver

**Epic:** E5 (scene validation & loud failure) · **Status:** 🟢 shipped (EM REVIEW PASS 2026-09-29);
greenlit by Tim 2026-09-29 ("do this now"), built via writing-plans + subagent-driven execution · **Acceptance owner:**
engineering-manager (REVIEW gate) · **Build host:** Mac. No hub step: no goldens, no provider
calls, no Claude calls.

> **As built (EM REVIEW PASS 2026-09-29, `feat/e5-loud-failure-sweep` at `bb16aa0`).** The plan
> (`docs/superpowers/plans/2026-09-29-e5-loud-failure-sweep.md`) corrected four errors in this
> spec against the code; the plan binds where they differ.
> 1. No CLI has a `--skip-overlays` flag (§5.1). The fix text says to remove or change
>    `scene.overlay`, then `rescene`.
> 2. `reburn` never runs ComposeStage, and `produce --start-from compose` makes a Claude QC call
>    (§9 A4). So smoke run 3 drives `ComposeStage().run` directly.
> 3. The review rounds added legacy-stand-in handling. A `{sid}_black.mp4` marker is dropped on
>    cache hit, and `reburn` refuses while one exists. `restore` also uses
>    `scene_final_cache_paths`.
> 4. §6's deferral premise for atomic writes, "I1's cleanup covers the failure case", is wrong
>    for SIGTERM and Ctrl-C.
>    - Today the cache probe checks both files, so a torn write refuses once and then
>      re-renders. That is loud, never black.
>    - Atomic writes are ROADMAP E5 part 1b.

---

## 1. Goal

A scene that fails to render can never reach a final as a black (or partly black) segment, and can
never be served from the scene cache as a black stand-in on the next run. Every such failure refuses
assembly with the step, the reason and a `suggested_fix`. `pipeline validate`, compose and the
still-gate resolve every `clip` / `article_image` path the same way.

## 2. Axis (two-axes guard)

**Production quality, defect prevention.** This is not a capability lift and it adds **zero
runtime**. A failed scene now stops assembly instead of shipping black at the same length, so no
seconds are added or removed. Do not cite it as a new arsenal item.

## 3. Problem (grounded 2026-09-29 on master `3693b09`)

### 3.1 The silent paths

| # | Site | Trigger | Outcome today |
|---|------|---------|---------------|
| P1 | `stages/compose.py:1109-1122`, `_render_sync` inner `except Exception` | Any non-`SceneRenderError` from `render_scene`: a provider error, a missing clip source (`FileNotFoundError`), an ffprobe failure, an unknown visual type (`ValueError`, `base.py:478`) | Logs `compose.scene.visual_failed` as a warning, substitutes `_black_screen`, muxes it with the narration into **both scene-cache paths**, and returns. **The final is assembled with a black scene, and the next run cache-hits the black file.** |
| P2 | `stages/compose.py:1216-1233`, `_render_one_scene` outer `except` | Any non-`SceneRenderError` after the visual step, including `OverlayCollisionError` from `check_overlay_allowed` (`compose.py:1160`, a `ValueError` that the validator never checks) and failures in the frame composite, `_fit_to_canvas` or `_mux` | Black is muxed into the frame-suffixed cache paths, and the function **returns normally**, so the final is **assembled**. The ROADMAP's "(c) … that run refuses assembly" is wrong for this path. |
| P3 | `stages/compose.py:778-807`, the `asyncio.gather` result loop | Any non-`SceneRenderError` that escapes `_render_one_scene` | Assembly is refused, but black stand-ins are written at the **unsuffixed** `{sid}_final.mp4` / `{sid}_final_no_overlay.mp4`, so the next `--start-from compose` cache-hits them. A framed scene caches at `{sid}_final_<frame>.mp4`, so the stand-in lands on a path the cache check doesn't read: a second mismatch. |
| P4 | `stages/compose.py:1134-1157`, compartment | `build_compartment_loop` / `composite_compartment_on_scene` raises | A warning only. The scene ships without its compartment animation. |
| P5 | `composer/image_sequence.py:139-143` | One image of the sequence fails to generate (`_fetch_image` → `None`) | A black sub-clip (`_black_clip`) inside the scene, with a warning only. |
| P6 | Path resolution in four places | A project-relative `visual.path` | See 3.2. |

**Proven red on master (EM probe, scratch copy, 2026-09-29).** These are drafts of T1, T2, T5 and T9
below; each fails on today's code:
- **T1:** a generic visual failure → `DID NOT RAISE`.
- **T2:** `text_top` overlay on a `text_card` → `DID NOT RAISE`, and a black scene is assembled.
- **T5:** an exception escaping `_render_one_scene` → `s1_final.mp4` and `s1_final_no_overlay.mp4`
  are left behind.
- **T9:** a project-relative clip → "Source video not found", then a silent black render.

### 3.2 Four resolvers, three behaviours

| Resolver | Candidates | Used by |
|----------|------------|---------|
| `director/storyboard_validator.py:663` `_resolve_path` | absolute, else `project_root/p`, then `cwd/p` | `pipeline validate`; compose's own pre-render validation (`compose.py:658`) |
| `composer/clip.py:9` `_resolve_source_video` | absolute or cwd-existing, else `cwd/p` | `render_clip` |
| `stages/compose.py:511` `_source_for_clip_visual` | the same as clip.py (a duplicate) | duplicate-frame guard (`compose.py:476`) |
| `composer/refit.py:131` `effective_image_path` | the raw path, so effectively cwd | `article_image` / `image` branch (`base.py:427`) |

So a project-relative clip validates clean, then fails with `FileNotFoundError` and renders black
through P1. That is the Sprint 9 hub-smoke defect. A project-relative `article_image` validates clean,
then fails loudly with "path not found": loud, but still wrong.

**Hub audit (EM, 2026-09-29, every `output/projects/*/storyboard*.json`):**
- 42 `article_image` and 3 `clip` paths are **repo-root-relative** (`raw/parenting/...`, through the
  repo's `/raw` symlink).
- 3 `clip` paths are `TBD/...` placeholders; the validator already blocks them.
- **No** project-relative paths are in use, and **no** path resolves to different files under the
  different candidate lists.

So unifying the resolvers changes no live project's resolution.

### 3.3 Designed fallbacks this sprint must NOT touch

- `_silence_gap` (`compose.py:1523`): black by design, for `pause_after_sec`.
- rich_slide / chart flat paper background on a provider failure: it keeps the content and is
  codified in the standards anatomy.

## 4. Design principle (applies to every item)

**A fallback that keeps the scene's content** (flat paper under real chart text) **is a designed
degradation. A fallback that replaces the content** (black; narration text in place of an image)
**is a failure.** A failure raises `SceneRenderError(scene, reason, suggested_fix)` and feeds the
existing refuse-assembly machinery:
- `ctx.render_failures`, which is saved and shown by the dashboard (`server.py:1186`);
- `RuntimeError("Compose scene render failed; final assembly refused. …")`.

Part 1 (this sprint) removes the black family. Part 2, the text_card family, is deferred (§6).

## 5. Approach

### 5.1 One loud scene boundary: `ComposeStage._render_one_scene`

**Invariant I1.** `_render_one_scene` does exactly one of two things:
- it returns a `ComposeSceneResult` whose two cache files are real renders; or
- it raises `SceneRenderError`. When it raises, **neither** cache path its cache check reads
  (`{sid}_final{suffix}.mp4`, `{sid}_final_no_overlay{suffix}.mp4`) exists.

What changes:
- Remove the P1 inner `except Exception` → `_black_screen`.
- Remove the P2 outer black path.
- Any exception in the function body, **including the cache-check block** (a corrupt cached file that
  ffprobe can't read), deletes both cache paths, then:
  - re-raises a `SceneRenderError` unchanged;
  - wraps anything else as `SceneRenderError(..., reason=..., suggested_fix=...)` using `from e`.
- `reason` format: `"<step> failed: <ExcType>: <message>"`. `<step>` is one of `visual (<visual.type>)`,
  `compartment`, `overlay rule`, `overlay` (already exists), `frame/mux`, `cached scene`.
- `suggested_fix` per step (the builder words it; each must be actionable):
  - `visual`: "Run `uv run pipeline validate <project-id>`, fix `scene.visual`, then
    `uv run pipeline compose rescene --project-id <id> --scene <sid>`."
  - `compartment`: "Fix or remove `scene.compartment`."
  - `overlay rule`: pass the `OverlayCollisionError` message through, plus "remove or change
    `scene.overlay`, or re-run with `--skip-overlays`."
  - `frame/mux`: "Inspect the ffmpeg error above; `rescene` the scene."
  - `cached scene`: "The cached scene file was unreadable and has been deleted; re-run compose."
- P4: the compartment `try/except` raises instead of warning.
- The internal shape is the builder's choice (for example, a small helper that runs one step and
  wraps it). Don't add a framework.
- Update the docstrings: `ComposeSceneResult` (`compose.py:600`, "Failures produce black-screen
  fallbacks") and `_render_one_scene` (`compose.py:1068`, "Never raises").

### 5.2 The gather loop (`_compose_from_storyboard`, P3)

- Delete the black muxing.
- For each failed scene, record `render_failures[sid]`:
  - a `SceneRenderError` → `.to_dict()`;
  - anything else → the existing generic record. This should be unreachable after 5.1, but keep it
    as a defence.
- Then delete **all** of that scene's final cache files through **one shared helper**. Move
  `cli_compose._scene_final_cache_paths` (`cli_compose.py:57`, which already globs every
  frame-suffix variant) into `stages/compose.py` as `scene_final_cache_paths(scenes_dir, sid)`, and
  have `cli_compose` import it. That gives one source of truth for "what makes a scene look cached".
- Refuse assembly as today. The refusal message carries `str(SceneRenderError)`, which already
  includes the `suggested_fix`.

### 5.3 Delete `ComposeStage._black_screen`

No caller remains after 5.1 and 5.2. Keep `_silence_gap`.

### 5.4 image_sequence (P5)

When an image fails to generate, raise `SceneRenderError(scene, reason="image_sequence image <idx>
failed to generate: <provider error>", suggested_fix=…)`.
- Change `_fetch_image` so the provider error text reaches the reason: return it, or raise.
- Delete `_black_clip`.
- Images that succeeded stay cached by prompt hash (`image_cache/`), so a `rescene` regenerates only
  the one that failed. Put that in the `suggested_fix`, together with "check `uv run pipeline doctor`
  (image tool) / provider status".

### 5.5 One media-path resolver: `src/pipeline/utils/paths.py` (new)

```python
REPO_ROOT: Path  # Path(__file__).resolve().parents[3]

def media_path_candidates(raw: str | Path, project_root: Path | None) -> list[Path]:
    """expanduser; absolute -> [p]; else [project_root/p (if given), REPO_ROOT/p, cwd/p],
    de-duplicated by resolved path, order preserved. Pure: no I/O."""

def resolve_media_path(raw: str | Path, project_root: Path | None) -> Path:
    """First existing candidate; if none exists, candidates[0] (the path an error should name)."""
```

Why `REPO_ROOT`: real storyboards use repo-root-relative `raw/...` paths (§3.2). They resolve today
only because every launcher's cwd happens to be the repo root (the dashboard unit has
`WorkingDirectory=/home/tim-huang/content-creation`). Adding the repo root to both the validator and
the renderer keeps the two in agreement and removes the cwd dependence.

**Consumers.** All of them delegate; no other candidate list survives in these files:
- `storyboard_validator._resolve_path` → delegates. `_clip_visual_path` and `_effective_visual_path`
  follow automatically.
- `composer/clip.py`:
  - `_resolve_source_video(visual, source_video, project_root=None)` → delegates for `visual.path`;
  - `render_clip(..., project_root=None)`;
  - a missing source raises **`SceneRenderError`**, not `FileNotFoundError`, and its reason lists the
    candidates it tried.
- `stages/compose.py::_source_for_clip_visual` → **deleted**. The duplicate-frame guard
  (`_precompute_duplicate_guard` → `_apply_duplicate_guard`) calls `clip._resolve_source_video` with
  `project_root`.
- `composer/refit.py::effective_image_path(visual, project_root=None)` → delegates for both
  `refit_path` and `path`.
- `composer/base.py::render_scene(..., project_root: Path | None = None)` → forwards to the `clip` and
  `article_image` / `image` branches.
- compose's `_render_sync` passes `project_root=ctx.work_dir`.
- still-gate:
  - `director/still_gate/render.py::render_scene_still(..., project_root=None)` → forwards;
  - `cli_storyboard.py:382` passes `pdir`.

`project_root=None` keeps today's behaviour minus the fallback, so any other caller is unaffected.

### 5.6 Fences in code (the standing lesson: guardrails in code, not docs)

`tests/unit/test_loud_failure_fence.py`:
1. `ComposeStage` has no `_black_screen`, and `pipeline.composer.image_sequence` has no `_black_clip`.
2. The literal `color=c=black` appears in `src/pipeline/**/*.py` **only inside
   `ComposeStage._silence_gap`**. Check this through the AST (the enclosing `FunctionDef` name), not
   by counting lines.
3. `Path.cwd()` does not appear in `composer/clip.py`, `composer/refit.py`, `stages/compose.py` or
   `director/storyboard_validator.py`. The resolver owns cwd.

Also correct the comments that describe the old fallback:
- `composer/toon.py:3-4`;
- `composer/chart.py:315-318`.

## 6. Scope

**IN:** §5.1–5.6. Only these files:
- `stages/compose.py`, `cli_compose.py`;
- `composer/{base,clip,refit,image_sequence,toon,chart}.py` (toon and chart: comments only);
- `director/storyboard_validator.py`, `director/still_gate/render.py`, `cli_storyboard.py`;
- the new `utils/paths.py`;
- tests.

**OUT (deliberately deferred):**
- **Part 2, "silent text_card downgrades"** (ROADMAP Later, E5 🔵). It is split out because it is
  not a black-scene path and needs decisions this sprint shouldn't make:
  - `namecard` / `map` → text_card (`base.py:461-470`). The director taxonomy **emits both**
    (`direct.py:216-217, 257`), and hub storyboards hold 6 `map` scenes and 1 `namecard` scene, so
    going loud needs a taxonomy decision first (retire `namecard` to `overlay.namecard`; give `map` a
    real type or route it to `generated_image`). It rides the next `stages/direct.py` sprint.
  - `generated_image` provider failure → a narration text_card (`image.py:177-181`). This is a
    policy call tied to provider budget.
  - The `image.py` edit-mode fallback (`image.py:129-133`).
- The Haiku visual-QC opt-out and "QC did not run" surfacing (ROADMAP Later, cross-linked to
  E10; same call site, `cli.py` ~421-449).
- `style_anchor._assess_source` falls back to `"medium"` when the call fails. The E10 spec
  (`2026-09-29-claude-cli-llm-backend-design.md`) keeps that site advisory, printing the real
  reason, by Tim's call. Not this sprint.
- A validator-side overlay-collision check. The validator lacks `burn_subtitles`; the loud failure
  at compose is enough. ⚪ idea.
- Atomic temp-then-rename for scene-cache writes. ⚪; I1's cleanup covers the failure case.
- `transitions._resolve_asset_path` (already loud, with its own search order), and the `_REPO_ROOT`
  duplicates in `transitions.py` and `music.py`. Hygiene; they may adopt `utils/paths.py` later.
- `COMPOSE_FPS` single source (⚪ Later). The E8 (B) s31 tofu.

## 7. Dependencies / unblocks

- **Dependencies: none blocking.**
  - No provider or Claude calls. The exhausted Anthropic credit doesn't block the tests or the
    smoke: `style_anchor` is skipped with niche `none`, and its failure is swallowed anyway.
  - No goldens, so there is no hub step.
- **Unblocks:**
  - A final can no longer carry a silent black scene or a cached black stand-in.
  - A storyboard that validates clean resolves every clip and image path the same way at compose
    and in the still-gate.
  - The first finals produced after E10 restores the Claude-backed stages are protected.
- **Does NOT:** add runtime or a capability. It doesn't fix the text_card downgrades (part 2).

## 8. Cost / size

**$0.** About **1 session**, as five subagent tasks (§11).

## 9. Acceptance criteria (the EM runs all of these at REVIEW)

- **A1. Red first.** Every test in §10 is committed failing on base `3693b09` **before** its fix
  lands: a test-only commit, then a fix commit. The plan ledger records each red run. At REVIEW the EM
  mutation-checks the key ones in a `git archive` scratch copy:
  - re-add the black fallback → T1, T2 and T11 go red;
  - restore the cwd resolver → T8 and T9 go red.
- **A2.** `uv run pytest -q`: 0 failed. `uv run ruff check src/ tests/` and `uv run mypy src/` are
  clean. The only new skips allowed are the existing environment and `--integration` gates.
- **A3.** No regressions in the suites the sweep touches:
  - baseline today: `tests/unit/test_compose_v2.py tests/director/test_storyboard_validator.py
    tests/unit/test_composer_refit.py tests/director/still_gate` → 71 passed, 2 skipped;
  - plus `tests/unit/test_cli_compose*.py`, `test_clip_renderer.py`, `test_compose_dup_guard.py`,
    `test_composer_base.py`, `test_composer_toon.py`, `test_chart.py`: all green.
- **A4. Live fault-injection smoke on the Mac.**
  - Run it in a scratch `PIPELINE_OUTPUT_DIR` under `tmp/e5-sweep/smoke/`. **Don't copy real project
    data to the Mac.**
  - Evidence goes in `tmp/e5-sweep/smoke/`: commands, exit codes, `context.json` excerpts and one
  extracted frame per assembled run.
  - The scratch project has 3 scenes:
    - `s1`: a `clip` with a **project-relative** `path`, pointing at a short `testsrc` mp4 made with
      ffmpeg;
    - `s2`: a `text_card` on one line (no `\n`, to avoid the open E8 s31 bug);
    - `s3`: a `chart` with `ai_background: false`.
  - Narration: any short audio (silent `anullsrc` segments or free edge-tts). Drive the runs with
    `pipeline compose rescene` / `reburn`, or `produce --start-from compose`; the builder's choice.
  - The runs:
    1. `pipeline validate` exits 0, and compose **assembles**. The extracted s1 frame is the testsrc
       picture, not black.
    2. Swap s1's file for a corrupt mp4 (the file exists but won't decode). Compose **refuses**;
       `context.json` `render_failures.s1` has the step, the reason and the `suggested_fix`; and
       `compose/scenes/` holds no `s1_final*.mp4`.
    3. Re-run unchanged. It **refuses again**: nothing is served from cache.
    4. Restore the file. Compose **assembles** again.
    5. Give s2 a `text_top` overlay. Compose **refuses**, with the overlay-rule reason.
- **A5. Hub path audit.** At REVIEW the EM re-runs the self-contained read-only audit (§3.2) on the
  hub. For every `clip` / `article_image` path in every hub storyboard, the old renderer resolution
  must equal `resolve_media_path(p, project_dir)`. No push is needed for this.
- **A6.** A separate code-correctness review happened (for example sonnet or opus, per task plus a
  final whole-branch review), and its findings were resolved. The EM requires it and doesn't redo it.
- **A7. No scope creep.** The diff stays inside §6 IN. The `namecard` / `map` / `generated_image`
  fallbacks are untouched.

## 10. Tests the build must create (red first)

Use the patterns in `tests/unit/test_compose_v2.py:781-893`: the `sample_context` fixture, a fake
`run_ffmpeg` that writes the output file, and `check_ffmpeg_available` patched. All patch targets are
module-level names in `pipeline.stages.compose` (`render_scene`, `build_compartment_loop`,
`composite_scene_frame`, `run_ffmpeg`).

| ID | Test | Red today because |
|----|------|-------------------|
| T1 | `tests/unit/test_compose_v2.py::test_generic_visual_failure_refuses_assembly_without_black`. `render_scene` raises `RuntimeError("provider exploded")`. Expect `RuntimeError` "final assembly refused"; `render_failures["s1"]["reason"]` contains `visual` and `RuntimeError: provider exploded`; the `suggested_fix` is non-empty; no `s1_final*.mp4` and no `s1_black.mp4` | P1: it completes, and black is assembled (EM probe: `DID NOT RAISE`) |
| T2 | `…::test_overlay_rule_violation_refuses_assembly`. A real `check_overlay_allowed`, with a `text_top` overlay on a `text_card` visual. Expect a refusal whose reason carries the collision message, and no `s1_final*.mp4` | P2: black is assembled (EM probe: `DID NOT RAISE`) |
| T3 | `…::test_compartment_failure_refuses_assembly`. The scene has a `compartment`; `build_compartment_loop` raises. Expect a refusal with the `compartment` step | P4: a warning only, and the final is assembled |
| T4 | `…::test_render_one_scene_post_visual_failure_raises_and_leaves_no_cache`. Call `_render_one_scene` directly with `frame_style="open_book_page"`, while `composite_scene_frame` raises. Expect `SceneRenderError`, and neither `s1_final_open_book_page.mp4` nor `s1_final_no_overlay_open_book_page.mp4` exists | P2: it returns normally, with black at the suffixed paths |
| T5 | `…::test_escaped_scene_exception_leaves_no_cached_black`. Patch `ComposeStage._render_one_scene` to raise `RuntimeError`. Expect a refusal and `glob("s1_final*.mp4") == []` | P3: the black stand-ins stay (EM probe: `['s1_final.mp4', 's1_final_no_overlay.mp4']`) |
| T6 | `…::test_refused_compose_rerun_does_not_cache_hit`. Run compose twice with a failing visual. Both runs refuse, and `render_scene` is called on both | P1: the first run assembles and caches black |
| T7 | `tests/unit/test_image_sequence.py::test_failed_image_raises_scene_render_error_not_black` (new file). Of 2 images, image 1 fails. Expect `SceneRenderError` naming image 1 and the provider error; `run_ffmpeg` is never called with `color=c=black` | P5: a black sub-clip |
| T8 | `tests/unit/test_media_paths.py` (new). The pure resolver: absolute path; project-relative wins; repo-relative with cwd elsewhere; cwd-relative still resolves; none exist → the project candidate; `expanduser`; de-duplication. Plus `test_validator_and_renderers_agree_on_project_relative_paths`: with cwd elsewhere, the validator's clip and image resolution equals `clip._resolve_source_video(..., project_root=)` and `refit.effective_image_path(..., project_root=)`, and both exist | The module and the `project_root` kwargs don't exist yet |
| T9 | `tests/unit/test_compose_v2.py::test_project_relative_clip_renders_from_project_root`. The Sprint 9 smoke defect end to end: `path: "source/clip.mp4"` under `work_dir`, `monkeypatch.chdir` elsewhere, `pipeline.composer.clip._get_source_duration` → 10.0. Expect compose to complete, with the clip ffmpeg `-i` equal to `work_dir/source/clip.mp4` | P6 + P1: "Source video not found", then black (EM probe: the project path is never extracted) |
| T10 | `tests/director/still_gate/test_render.py::test_render_scene_still_forwards_project_root`. `render_scene` patched; assert `project_root` is forwarded | `TypeError` (no kwarg) |
| T11 | `tests/unit/test_loud_failure_fence.py`: `test_no_black_fallback_helpers_remain`, `test_black_lavfi_source_only_in_silence_gap`, `test_media_resolution_has_one_owner` (§5.6) | `_black_screen` and `_black_clip` exist; `color=c=black` appears in 3 functions; `Path.cwd()` appears in clip.py and compose.py |

## 11. Suggested task order (for writing-plans; each task commits tests red, then the fix)

1. **Resolver.** `utils/paths.py` + T8 (pure half).
2. **Delegation.** Validator, `clip.py`, `refit.py`, `render_scene`, compose (drop
   `_source_for_clip_visual`), still-gate + CLI. Covers T8 (agreement), T9 and T10.
3. **Scene boundary.** §5.1–5.3 + T1–T6. This is the largest task; review it hardest.
4. **image_sequence.** §5.4 + T7.
5. **Fence + docs + smoke.** T11, the comment and docstring fixes, and the A4 live smoke with its
   evidence.

## 12. Risks

- **R1. More runs stop.** A long compose now refuses at the end because of one bad scene. That is
  intended. Mitigations: the refusal names every failed scene and its fix, and good scenes stay
  cached, so `rescene` is cheap.
- **R2. Transient image failures now refuse** (image_sequence). Mitigation: the prompt-hash cache
  keeps successes, so a rerun retries only the failure.
- **R3. The `REPO_ROOT` candidate** changes resolution only when cwd ≠ repo root. Today those runs
  fail, so the change only turns failures into successes. The audit shows no disagreement when cwd is
  the repo root.
- **R4. Deleting an unreadable cached scene** costs one re-render if ffprobe glitched. That's
  acceptable.
- **R5. Concurrency.** The cleanup runs inside each scene's own task, and scenes share no files. The
  transitions cache is unaffected.
- **R6. Callers that relied on "never raises".** `rescene`, `reburn` and the dashboard job queue
  already go through `ComposeStage.run` and surface `render_failures`
  (`cli_compose.py:231-240`), so nothing needs to change there. The builder confirms no other caller
  of `_render_one_scene` exists; today only tests call it.
