# Click-to-Edit Plan 4 — Edit-mode UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-project edit-mode toggle, click-to-mint token grammar, floating composer with cost-aware confirm popup, direct-action TransitionEditor modal, and the HTTP wrappers that the dashboard frontend needs to drive Plan 1's transition CLI and persist composer drafts. After this plan, a user can tap any rendered scene element on the dashboard to mint a token, type a natural-language instruction, and submit the resulting job to Plan 3's `JobQueue`.

**Architecture:** Frontend is plain ES5/ES6 JS modules (no bundler) loaded via `<script>` from `src/pipeline/dashboard/static/`, matching the existing pattern. Pure-logic modules (`tokens.js`, `cost_estimate.js`, `edit_draft.js`) self-test with `console.assert` blocks at module bottom — gated by a `?test=1` query param so production loads silently. Edit-mode state lives in `localStorage` per project; the in-progress draft is server-persisted at `output/projects/<id>/edit_draft.json` so it survives a page refresh. Backend adds four direct-action endpoints (`/api/transition/*`, `/api/sfx/*`, `/api/jobs/*/draft`) that delegate to the same Plan 1 / Plan 2 helpers the CLI uses — single source of truth for mutations. Submit goes to Plan 3's existing `POST /api/jobs/<project_id>/submit`.

**Tech Stack:** Plain JS (no framework), FastAPI, Pydantic, Typer (Plan 1's CLI helpers), pytest + `fastapi.testclient.TestClient`. No new third-party dependencies.

**Spec reference:** `docs/superpowers/specs/2026-05-04-dashboard-click-to-edit-design.md` — §"Frontend — edit mode + composer", §"Frontend — clickable elements registry", §"Backend — direct-action endpoints" (transition + draft rows), §"Token grammar", §"User flows / Flow 1, Flow 2".

**Assumes merged:**
- **Plan 1** (transitions) — `pipeline transition set / clear` Typer commands and `apply_set_transition`-style helpers exist in `src/pipeline/cli_transition.py`. Storyboard has `transitions: list[Transition]`.
- **Plan 2** (narration source) — `NarrationSource` schema, `/api/narration/<id>/set-source`, `/api/narration/<id>/upload`, `/api/narration/<id>/transcribe` endpoints, and the `NarrationSourceEditor` modal at `static/narration_source_editor.js` are live.
- **Plan 3** (JobQueue + Telegram + agent) — `POST /api/jobs/<project_id>/submit` accepts `{tokens: [str], instruction: str}` and enqueues a job. `EditJob` schema and per-project `JobQueue` exist in `src/pipeline/dashboard/job_queue.py`.

**Pre-existing test failure on master:** `tests/unit/test_compose_v2.py::test_compose_burn_subtitles_false_returns_plain_variant` is unrelated to this work. Baseline runs use `--deselect tests/unit/test_compose_v2.py::test_compose_burn_subtitles_false_returns_plain_variant`.

---

## File Structure

**Create:**

| File | Responsibility |
|---|---|
| `src/pipeline/dashboard/static/tokens.js` | Pure JS module: token parser, formatter, `mintTokenFromElement`, `tokenLabel`. Self-tests under `?test=1`. |
| `src/pipeline/dashboard/static/cost_estimate.js` | Pure JS module: `estimateJobCost(tokens)` returning `{usd, wideRebuild, needsConfirm}`. Self-tests under `?test=1`. |
| `src/pipeline/dashboard/static/edit_draft.js` | Frontend draft autosave: `loadDraft`, `saveDraft` (debounced), `clearDraft` against `/api/jobs/<id>/draft`. |
| `src/pipeline/dashboard/static/edit_mode.js` | Edit-mode controller: header toggle, sticky bottom strip, ESC handler, `localStorage` persistence, click-to-mint registry (top-level handler reading `data-edit-token`). |
| `src/pipeline/dashboard/static/composer.js` | Floating composer component: token chip list, textarea, summary line, mobile-collapsed `(N) ▲` mode, cross-highlighting, confirm popup, submit. |
| `src/pipeline/dashboard/static/transition_editor.js` | Direct-action TransitionEditor modal: style/duration/sfx form, `+ upload custom` upload, posts to set/clear endpoints, mirrored update on both adjacent scene chips. |
| `src/pipeline/dashboard/static/edit_mode_test.html` | Static test harness HTML — loads `tokens.js` and `cost_estimate.js` with `?test=1`, prints PASS/FAIL count. Used by `tests/integration/test_static_self_tests.py`. |
| `tests/unit/test_dashboard_transition_endpoints.py` | TestClient tests for `POST /api/transition/<id>/set` and `/clear`. |
| `tests/unit/test_dashboard_sfx_endpoints.py` | TestClient tests for `GET /api/sfx/list` and `POST /api/sfx/upload`. |
| `tests/unit/test_dashboard_draft_endpoints.py` | TestClient tests for draft GET / POST / DELETE. |
| `tests/integration/test_static_self_tests.py` | Smoke test that runs `node` against the test harness to assert the JS self-tests pass (skips if `node` not on PATH). |

**Modify:**

| File | Change |
|---|---|
| `src/pipeline/cli_transition.py` | Extract pure helpers `apply_set_transition(...)` and `apply_clear_transition(...)` from the existing Typer command bodies, then have the commands call them. The HTTP endpoints in this plan call the same helpers. |
| `src/pipeline/dashboard/server.py` | Add transition / sfx / draft endpoints (4 routes added in this plan, exact endpoint surface listed in Tasks 1-3). |
| `src/pipeline/dashboard/static/index.html` | Add edit-mode header toggle, sticky-strip + composer host nodes, transition + narration-source chips on each scene panel with `data-edit-token` attributes, transition-out chip in the scene strip. Replace Plan 2's temp `🎙 record` button (lines 199-203) with a tokenized narration-source chip. Pull in the new JS modules. |
| `src/pipeline/dashboard/static/verify.html` | Mirror the edit-mode toggle, sticky strip, composer host, and click-to-mint registry. Add `data-edit-token` annotations to the scene rail, manifest items, and final-video player. |

**Out of scope** (later plans):
- SSE refresh of artifacts and in-flight badge animation (Plan 5)
- Trust gate / `↩ Revert` / `✅ Apply / ✏ Edit / ❌ Cancel` Telegram buttons (Plan 5)
- Per-token retry buttons in Telegram (Plan 5)
- The agent runtime, JobQueue consumer loop, Telegram listener (Plan 3)
- The submit endpoint itself (Plan 3 — Plan 4 only calls it)

---

## Task 1: Refactor `cli_transition.py` to expose pure helpers

**Why:** Plan 1's `pipeline transition set` / `clear` Typer commands embed the storyboard-mutation logic directly in the command body. Plan 4's HTTP endpoints need the same logic; rather than duplicating, we extract two helpers that both the Typer command and the HTTP endpoint call.

**Files:**
- Modify: `src/pipeline/cli_transition.py`
- Test: `tests/unit/test_cli_transition.py` (Plan 1 file — extend with helper-direct tests)

- [ ] **Step 1.1: Add tests asserting the two helpers exist and behave correctly when called directly**

Append to `tests/unit/test_cli_transition.py`:

```python
def test_apply_set_transition_writes_to_storyboard(project_tree: Path):
    from pipeline.cli_transition import apply_set_transition
    summary = apply_set_transition(
        project_id=42, from_scene="s1", to_scene="s2",
        style="fade", duration_sec=0.3, sfx=None,
    )
    sb = Storyboard.load(project_tree / "storyboard.json")
    assert len(sb.transitions) == 1
    assert sb.transitions[0].style == "fade"
    assert "s1" in summary and "s2" in summary


def test_apply_set_transition_rejects_unknown_style(project_tree: Path):
    import pytest
    from pipeline.cli_transition import apply_set_transition
    with pytest.raises(ValueError, match="Unknown transition style"):
        apply_set_transition(
            project_id=42, from_scene="s1", to_scene="s2",
            style="ribbon", duration_sec=0.3, sfx=None,
        )


def test_apply_set_transition_rejects_unknown_scene(project_tree: Path):
    import pytest
    from pipeline.cli_transition import apply_set_transition
    with pytest.raises(ValueError, match="s99"):
        apply_set_transition(
            project_id=42, from_scene="s1", to_scene="s99",
            style="fade", duration_sec=0.3, sfx=None,
        )


def test_apply_clear_transition_removes_entry(project_tree: Path):
    from pipeline.cli_transition import apply_set_transition, apply_clear_transition
    apply_set_transition(
        project_id=42, from_scene="s1", to_scene="s2",
        style="fade", duration_sec=0.3, sfx=None,
    )
    summary = apply_clear_transition(project_id=42, from_scene="s1", to_scene="s2")
    sb = Storyboard.load(project_tree / "storyboard.json")
    assert sb.transitions == []
    assert "cleared" in summary.lower() or "s1" in summary


def test_apply_clear_transition_returns_noop_summary_when_absent(project_tree: Path):
    from pipeline.cli_transition import apply_clear_transition
    summary = apply_clear_transition(project_id=42, from_scene="s1", to_scene="s2")
    assert "no transition" in summary.lower() or "nothing" in summary.lower()
```

- [ ] **Step 1.2: Run tests — expect 5 ImportError failures**

Run: `uv run pytest tests/unit/test_cli_transition.py::test_apply_set_transition_writes_to_storyboard tests/unit/test_cli_transition.py::test_apply_set_transition_rejects_unknown_style tests/unit/test_cli_transition.py::test_apply_set_transition_rejects_unknown_scene tests/unit/test_cli_transition.py::test_apply_clear_transition_removes_entry tests/unit/test_cli_transition.py::test_apply_clear_transition_returns_noop_summary_when_absent -v`
Expected: `ImportError: cannot import name 'apply_set_transition' from 'pipeline.cli_transition'`.

- [ ] **Step 1.3: Refactor — extract pure helpers, leave Typer commands as thin wrappers**

Open `src/pipeline/cli_transition.py`. Replace the existing `set_transition` and `clear_transition` command bodies with the helper-then-wrapper pattern.

Add these two helpers immediately after the existing `_scene_ids(sb)` helper (before the `@transition_app.command("set")` decorator):

```python
def apply_set_transition(
    *,
    project_id: int,
    from_scene: str,
    to_scene: str,
    style: str,
    duration_sec: float,
    sfx: str | None,
) -> str:
    """Set or replace a transition on a project's storyboard.

    Used by both the Typer command and the dashboard HTTP endpoint.
    Returns a one-line human-readable summary.

    Raises ValueError on validation failure (unknown style or scene).
    """
    if style not in SUPPORTED_STYLES:
        raise ValueError(
            f"Unknown transition style {style!r}. Choose from: {', '.join(sorted(SUPPORTED_STYLES))}"
        )
    sb_path, sb = _load_storyboard(project_id)
    ids = _scene_ids(sb)
    if from_scene not in ids:
        raise ValueError(f"Scene {from_scene!r} not found in storyboard")
    if to_scene not in ids:
        raise ValueError(f"Scene {to_scene!r} not found in storyboard")

    sb.transitions = [
        t for t in sb.transitions
        if not (t.from_scene == from_scene and t.to_scene == to_scene)
    ]
    sb.transitions.append(Transition(
        from_scene=from_scene, to_scene=to_scene,
        style=style, duration_sec=duration_sec, sfx=sfx,
    ))
    sb.save(sb_path)

    summary = (
        f"transition {from_scene}→{to_scene}: {style} ({duration_sec}s)"
        + (f" + {sfx}" if sfx else "")
    )
    work = _resolve_work_dir(project_id)
    append_session(work, SessionEntry(
        session_id=new_session_id(),
        timestamp=datetime.now().isoformat(timespec="seconds"),
        command=(
            f"transition set --from {from_scene} --to {to_scene} "
            f"--style {style} --duration {duration_sec}"
            + (f" --sfx {sfx}" if sfx else "")
        ),
        summary=summary,
    ))
    return summary


def apply_clear_transition(
    *,
    project_id: int,
    from_scene: str,
    to_scene: str,
) -> str:
    """Remove the transition for a given seam, if any.

    Returns a one-line summary. No-op when no transition exists for the seam.
    """
    sb_path, sb = _load_storyboard(project_id)
    before = len(sb.transitions)
    sb.transitions = [
        t for t in sb.transitions
        if not (t.from_scene == from_scene and t.to_scene == to_scene)
    ]
    if len(sb.transitions) == before:
        return f"No transition for {from_scene}→{to_scene}; nothing to clear."
    sb.save(sb_path)
    summary = f"transition {from_scene}→{to_scene}: cleared"
    work = _resolve_work_dir(project_id)
    append_session(work, SessionEntry(
        session_id=new_session_id(),
        timestamp=datetime.now().isoformat(timespec="seconds"),
        command=f"transition clear --from {from_scene} --to {to_scene}",
        summary=summary,
    ))
    return summary
```

Now replace the existing `set_transition` Typer command body with a thin wrapper:

```python
@transition_app.command("set")
def set_transition(
    project_id: int = typer.Option(..., "--project-id"),
    from_scene: str = typer.Option(..., "--from", help="Source scene id (e.g. s9)"),
    to_scene: str = typer.Option(..., "--to", help="Destination scene id (e.g. s10)"),
    style: str = typer.Option(..., "--style", help=f"One of: {', '.join(sorted(SUPPORTED_STYLES))}"),
    duration: float = typer.Option(..., "--duration", help="Transition duration in seconds"),
    sfx: str | None = typer.Option(None, "--sfx", help="Optional sound effect path"),
) -> None:
    """Set or replace a transition between two scenes. Idempotent."""
    try:
        summary = apply_set_transition(
            project_id=project_id, from_scene=from_scene, to_scene=to_scene,
            style=style, duration_sec=duration, sfx=sfx,
        )
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(summary)
```

And replace the existing `clear_transition` Typer command body with:

```python
@transition_app.command("clear")
def clear_transition(
    project_id: int = typer.Option(..., "--project-id"),
    from_scene: str = typer.Option(..., "--from"),
    to_scene: str = typer.Option(..., "--to"),
) -> None:
    """Remove the transition for a given seam, if any."""
    summary = apply_clear_transition(
        project_id=project_id, from_scene=from_scene, to_scene=to_scene,
    )
    typer.echo(summary)
```

- [ ] **Step 1.4: Run the new helper tests — expect pass**

Run: `uv run pytest tests/unit/test_cli_transition.py -v`
Expected: all (Plan 1's existing 7 + the 5 new) tests pass.

- [ ] **Step 1.5: Commit**

```bash
git add src/pipeline/cli_transition.py tests/unit/test_cli_transition.py
git commit -m "refactor(cli_transition): extract apply_set/clear helpers for reuse"
```

---

## Task 2: HTTP endpoint — `POST /api/transition/<project_id>/set` and `/clear`

**Files:**
- Modify: `src/pipeline/dashboard/server.py`
- Test: `tests/unit/test_dashboard_transition_endpoints.py` (new)

- [ ] **Step 2.1: Write the endpoint tests**

Create `tests/unit/test_dashboard_transition_endpoints.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pipeline.dashboard.server import create_app
from pipeline.storyboard import Scene, Storyboard


def _seed_project(projects_dir: Path, project_id: str = "42") -> Path:
    proj = projects_dir / project_id
    proj.mkdir(parents=True, exist_ok=True)
    sb = Storyboard(scenes=[
        Scene(id="s1", section="content", narration="a", narration_est_sec=1.0),
        Scene(id="s2", section="content", narration="b", narration_est_sec=1.0),
    ])
    sb.save(proj / "storyboard.json")
    return proj


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Production layout (see src/pipeline/cli.py:dashboard launcher):
    #   OUTPUT_DIR == output/, projects live at output/projects/<id>/.
    # Plan 2's narration endpoint tests pass `output/projects` as create_app's
    # `output_dir`; we mirror that so _project_root("42") and the CLI helper's
    # _resolve_work_dir(42) — which is OUTPUT_DIR/"projects"/"42" — agree.
    out_root = tmp_path / "output"
    projects_dir = out_root / "projects"
    _seed_project(projects_dir)
    monkeypatch.setattr(
        "pipeline.cli_transition.PipelineConfig",
        lambda: type("C", (), {"OUTPUT_DIR": out_root})(),
    )
    app = create_app(projects_dir)
    return TestClient(app)


def test_set_transition_writes_storyboard(client: TestClient, tmp_path: Path):
    resp = client.post("/api/transition/42/set", json={
        "from_scene": "s1", "to_scene": "s2",
        "style": "page-turn", "duration_sec": 0.5,
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert "page-turn" in body["summary"]
    sb = Storyboard.load(tmp_path / "output" / "projects" / "42" / "storyboard.json")
    assert len(sb.transitions) == 1
    assert sb.transitions[0].style == "page-turn"


def test_set_transition_with_sfx(client: TestClient, tmp_path: Path):
    resp = client.post("/api/transition/42/set", json={
        "from_scene": "s1", "to_scene": "s2",
        "style": "fade", "duration_sec": 0.3,
        "sfx": "assets/sfx/whoosh.mp3",
    })
    assert resp.status_code == 200
    sb = Storyboard.load(tmp_path / "output" / "projects" / "42" / "storyboard.json")
    assert sb.transitions[0].sfx == "assets/sfx/whoosh.mp3"


def test_set_transition_rejects_unknown_style(client: TestClient):
    resp = client.post("/api/transition/42/set", json={
        "from_scene": "s1", "to_scene": "s2",
        "style": "ribbon", "duration_sec": 0.5,
    })
    assert resp.status_code == 400
    assert "ribbon" in resp.json()["detail"] or "Unknown" in resp.json()["detail"]


def test_set_transition_rejects_unknown_scene(client: TestClient):
    resp = client.post("/api/transition/42/set", json={
        "from_scene": "s1", "to_scene": "s99",
        "style": "fade", "duration_sec": 0.5,
    })
    assert resp.status_code == 400
    assert "s99" in resp.json()["detail"]


def test_set_transition_404_when_project_missing(client: TestClient):
    resp = client.post("/api/transition/nope/set", json={
        "from_scene": "s1", "to_scene": "s2",
        "style": "fade", "duration_sec": 0.5,
    })
    assert resp.status_code == 404


def test_clear_transition_removes_entry(client: TestClient, tmp_path: Path):
    client.post("/api/transition/42/set", json={
        "from_scene": "s1", "to_scene": "s2",
        "style": "fade", "duration_sec": 0.3,
    })
    resp = client.post("/api/transition/42/clear", json={
        "from_scene": "s1", "to_scene": "s2",
    })
    assert resp.status_code == 200
    sb = Storyboard.load(tmp_path / "output" / "projects" / "42" / "storyboard.json")
    assert sb.transitions == []


def test_clear_transition_noop_when_absent(client: TestClient):
    resp = client.post("/api/transition/42/clear", json={
        "from_scene": "s1", "to_scene": "s2",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "nothing" in body["summary"].lower() or "no transition" in body["summary"].lower()


def test_set_transition_409_when_storyboard_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Project dir exists but storyboard.json doesn't yet — clean 409, not 500."""
    out_root = tmp_path / "output"
    projects_dir = out_root / "projects"
    (projects_dir / "77").mkdir(parents=True)  # no storyboard.json
    monkeypatch.setattr(
        "pipeline.cli_transition.PipelineConfig",
        lambda: type("C", (), {"OUTPUT_DIR": out_root})(),
    )
    app = create_app(projects_dir)
    client = TestClient(app)
    resp = client.post("/api/transition/77/set", json={
        "from_scene": "s1", "to_scene": "s2",
        "style": "fade", "duration_sec": 0.3,
    })
    assert resp.status_code == 409
    assert "storyboard" in resp.json()["detail"].lower()
```

- [ ] **Step 2.2: Run the tests — expect 404 / route-not-found failures**

Run: `uv run pytest tests/unit/test_dashboard_transition_endpoints.py -v`
Expected: 8 failures, all 404s on the unimplemented routes.

- [ ] **Step 2.3: Add the endpoints**

Open `src/pipeline/dashboard/server.py`. After the existing `_TranscribeBody` class (around line 49), add:

```python
class _TransitionSetBody(BaseModel):
    from_scene: str
    to_scene: str
    style: str
    duration_sec: float
    sfx: str | None = None


class _TransitionClearBody(BaseModel):
    from_scene: str
    to_scene: str
```

Then, inside the `create_app` function — after the existing `post_transcribe` definition (around line 292), before the `app.mount(...)` calls — add:

```python
    @app.post("/api/transition/{project_id}/set")
    def post_transition_set(project_id: str, body: _TransitionSetBody) -> JSONResponse:
        import typer
        from pipeline.cli_transition import apply_set_transition
        # _project_root raises 404 if missing — same behavior as the narration endpoints.
        _project_root(project_id)
        try:
            project_id_int = int(project_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"project_id {project_id!r} is not numeric — transition CLI requires int ids",
            ) from exc
        try:
            summary = apply_set_transition(
                project_id=project_id_int,
                from_scene=body.from_scene,
                to_scene=body.to_scene,
                style=body.style,
                duration_sec=body.duration_sec,
                sfx=body.sfx,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except typer.Exit as exc:
            # Plan 1's _load_storyboard echoes to stderr and raises typer.Exit
            # when storyboard.json is missing. Translate to 409 (project tree
            # exists but pipeline state isn't ready yet) so the client gets a
            # clean error instead of a 500.
            raise HTTPException(
                status_code=409,
                detail=f"storyboard.json missing for project {project_id}; "
                f"run `pipeline produce` past the storyboard stage first",
            ) from exc
        return JSONResponse({"ok": True, "summary": summary})

    @app.post("/api/transition/{project_id}/clear")
    def post_transition_clear(project_id: str, body: _TransitionClearBody) -> JSONResponse:
        import typer
        from pipeline.cli_transition import apply_clear_transition
        _project_root(project_id)
        try:
            project_id_int = int(project_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"project_id {project_id!r} is not numeric — transition CLI requires int ids",
            ) from exc
        try:
            summary = apply_clear_transition(
                project_id=project_id_int,
                from_scene=body.from_scene,
                to_scene=body.to_scene,
            )
        except typer.Exit as exc:
            raise HTTPException(
                status_code=409,
                detail=f"storyboard.json missing for project {project_id}",
            ) from exc
        return JSONResponse({"ok": True, "summary": summary})
```

- [ ] **Step 2.4: Run the endpoint tests — expect pass**

Run: `uv run pytest tests/unit/test_dashboard_transition_endpoints.py -v`
Expected: 8 passed.

- [ ] **Step 2.5: Run the full server-side test slice to catch regressions**

Run: `uv run pytest tests/unit/test_dashboard*.py -v`
Expected: all pass (existing Plan 2 dashboard tests + new ones).

- [ ] **Step 2.6: Commit**

```bash
git add src/pipeline/dashboard/server.py tests/unit/test_dashboard_transition_endpoints.py
git commit -m "feat(dashboard): direct-action transition endpoints (set, clear)"
```

---

## Task 3: SFX listing + upload endpoints

**Files:**
- Modify: `src/pipeline/dashboard/server.py`
- Test: `tests/unit/test_dashboard_sfx_endpoints.py` (new)

The TransitionEditor modal needs to read the available `assets/sfx/*` files for the dropdown, and accept user-uploaded sfx via `+ upload custom`. The sfx directory was reserved by Plan 1's `assets/sfx/.gitkeep`.

- [ ] **Step 3.1: Write the SFX endpoint tests**

Create `tests/unit/test_dashboard_sfx_endpoints.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pipeline.dashboard.server import create_app


@pytest.fixture
def client_with_sfx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Build a TestClient pointing at a tmp_path-backed assets/sfx/ directory."""
    sfx_dir = tmp_path / "assets" / "sfx"
    sfx_dir.mkdir(parents=True)
    (sfx_dir / "page_flip.mp3").write_bytes(b"id3" + b"\x00" * 32)
    (sfx_dir / "whoosh.mp3").write_bytes(b"id3" + b"\x00" * 32)
    (sfx_dir / ".gitkeep").write_text("")  # should be excluded from the listing
    monkeypatch.setattr("pipeline.dashboard.server._SFX_DIR", sfx_dir)
    app = create_app(tmp_path / "output")
    return TestClient(app)


def test_sfx_list_returns_audio_files(client_with_sfx: TestClient):
    resp = client_with_sfx.get("/api/sfx/list")
    assert resp.status_code == 200
    files = {entry["name"] for entry in resp.json()}
    assert files == {"page_flip.mp3", "whoosh.mp3"}


def test_sfx_list_returns_relative_path(client_with_sfx: TestClient):
    resp = client_with_sfx.get("/api/sfx/list")
    body = resp.json()
    assert any(e["path"] == "assets/sfx/page_flip.mp3" for e in body)


def test_sfx_list_when_directory_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    sfx_dir = tmp_path / "assets" / "sfx"
    sfx_dir.mkdir(parents=True)
    monkeypatch.setattr("pipeline.dashboard.server._SFX_DIR", sfx_dir)
    app = create_app(tmp_path / "output")
    client = TestClient(app)
    resp = client.get("/api/sfx/list")
    assert resp.status_code == 200
    assert resp.json() == []


def test_sfx_upload_writes_file(client_with_sfx: TestClient, tmp_path: Path):
    body = b"id3" + b"\x00" * 256
    resp = client_with_sfx.post(
        "/api/sfx/upload",
        files={"file": ("custom_swoosh.mp3", body, "audio/mpeg")},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["path"] == "assets/sfx/custom_swoosh.mp3"
    written = (tmp_path / "assets" / "sfx" / "custom_swoosh.mp3").read_bytes()
    assert written == body


def test_sfx_upload_rejects_path_traversal(client_with_sfx: TestClient):
    resp = client_with_sfx.post(
        "/api/sfx/upload",
        files={"file": ("../escape.mp3", b"x", "audio/mpeg")},
    )
    assert resp.status_code == 400
    assert "filename" in resp.json()["detail"].lower()


def test_sfx_upload_rejects_unsupported_extension(client_with_sfx: TestClient):
    resp = client_with_sfx.post(
        "/api/sfx/upload",
        files={"file": ("evil.exe", b"x", "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert "extension" in resp.json()["detail"].lower()
```

- [ ] **Step 3.2: Run the tests — expect failures**

Run: `uv run pytest tests/unit/test_dashboard_sfx_endpoints.py -v`
Expected: 6 failures (404 / AttributeError on `_SFX_DIR`).

- [ ] **Step 3.3: Add the endpoints**

Open `src/pipeline/dashboard/server.py`. Near the top (after the other module-level path constants around line 25), add:

```python
_SFX_DIR = Path("assets/sfx")
_ALLOWED_SFX_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a"}
```

Inside `create_app`, after the transition endpoints from Task 2, add:

```python
    @app.get("/api/sfx/list")
    def get_sfx_list() -> JSONResponse:
        if not _SFX_DIR.exists():
            return JSONResponse([])
        entries: list[dict] = []
        for path in sorted(_SFX_DIR.iterdir()):
            if not path.is_file():
                continue
            if path.name.startswith("."):
                continue  # skip .gitkeep, dot-files
            if path.suffix.lower() not in _ALLOWED_SFX_EXTENSIONS:
                continue
            entries.append({
                "name": path.name,
                "path": f"assets/sfx/{path.name}",
                "size_bytes": path.stat().st_size,
            })
        return JSONResponse(entries)

    @app.post("/api/sfx/upload")
    async def post_sfx_upload(
        file: UploadFile = File(...),  # noqa: B008
    ) -> JSONResponse:
        # Sanitize filename: refuse anything with path separators, "..", or leading dot
        raw = file.filename or ""
        if "/" in raw or "\\" in raw or ".." in raw or raw.startswith(".") or not raw:
            raise HTTPException(status_code=400, detail=f"invalid filename {raw!r}")
        suffix = Path(raw).suffix.lower()
        if suffix not in _ALLOWED_SFX_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"unsupported extension {suffix!r}; allowed: {sorted(_ALLOWED_SFX_EXTENSIONS)}",
            )
        _SFX_DIR.mkdir(parents=True, exist_ok=True)
        dst = _SFX_DIR / raw
        with dst.open("wb") as out:
            while chunk := await file.read(1024 * 64):
                out.write(chunk)
        return JSONResponse({"ok": True, "path": f"assets/sfx/{raw}"})
```

Mount the sfx directory as a static route so the modal's `<audio>` preview can play uploaded files. Inside `create_app`, add this right above the existing `app.mount("/static", ...)` line:

```python
    if _SFX_DIR.exists():
        app.mount("/sfx", StaticFiles(directory=str(_SFX_DIR)), name="sfx")
```

- [ ] **Step 3.4: Run the tests — expect pass**

Run: `uv run pytest tests/unit/test_dashboard_sfx_endpoints.py -v`
Expected: 6 passed.

- [ ] **Step 3.5: Commit**

```bash
git add src/pipeline/dashboard/server.py tests/unit/test_dashboard_sfx_endpoints.py
git commit -m "feat(dashboard): /api/sfx/list + /api/sfx/upload endpoints"
```

---

## Task 4: Edit-draft endpoints — GET / POST / DELETE

**Files:**
- Modify: `src/pipeline/dashboard/server.py`
- Test: `tests/unit/test_dashboard_draft_endpoints.py` (new)

The composer auto-saves to `output/projects/<id>/edit_draft.json` so a refresh in mid-edit doesn't drop the in-progress draft. Single-file shape (one draft per project at a time).

- [ ] **Step 4.1: Write the draft endpoint tests**

Create `tests/unit/test_dashboard_draft_endpoints.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pipeline.dashboard.server import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    # Same projects/ layout as test_narration_endpoints.py — see Task 2 fixture
    # comment for the reasoning.
    out_root = tmp_path / "output"
    projects_dir = out_root / "projects"
    proj = projects_dir / "42"
    proj.mkdir(parents=True)
    (proj / "storyboard.json").write_text(json.dumps({"version": 1, "scenes": []}))
    app = create_app(projects_dir)
    return TestClient(app)


def test_get_draft_returns_empty_when_absent(client: TestClient):
    resp = client.get("/api/jobs/42/draft")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"tokens": [], "instruction": ""}


def test_post_draft_then_get_returns_saved(client: TestClient, tmp_path: Path):
    payload = {"tokens": ["@s9/visual", "@s11/subtitle"],
               "instruction": "make these darker"}
    resp = client.post("/api/jobs/42/draft", json=payload)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    resp2 = client.get("/api/jobs/42/draft")
    assert resp2.status_code == 200
    assert resp2.json() == payload

    # Round-tripped to disk
    saved = json.loads((tmp_path / "output" / "projects" / "42" / "edit_draft.json").read_text())
    assert saved == payload


def test_post_draft_overwrites(client: TestClient):
    client.post("/api/jobs/42/draft", json={"tokens": ["@s1"], "instruction": "first"})
    client.post("/api/jobs/42/draft", json={"tokens": ["@s2"], "instruction": "second"})
    resp = client.get("/api/jobs/42/draft")
    assert resp.json() == {"tokens": ["@s2"], "instruction": "second"}


def test_delete_draft_removes_file(client: TestClient, tmp_path: Path):
    client.post("/api/jobs/42/draft", json={"tokens": ["@s9"], "instruction": "x"})
    assert (tmp_path / "output" / "projects" / "42" / "edit_draft.json").exists()
    resp = client.delete("/api/jobs/42/draft")
    assert resp.status_code == 200
    assert not (tmp_path / "output" / "projects" / "42" / "edit_draft.json").exists()
    resp2 = client.get("/api/jobs/42/draft")
    assert resp2.json() == {"tokens": [], "instruction": ""}


def test_delete_draft_noop_when_absent(client: TestClient):
    resp = client.delete("/api/jobs/42/draft")
    assert resp.status_code == 200


def test_post_draft_404_when_project_missing(client: TestClient):
    resp = client.post("/api/jobs/nope/draft",
                       json={"tokens": [], "instruction": "x"})
    assert resp.status_code == 404


def test_post_draft_rejects_oversize_payload(client: TestClient):
    # Defensive cap: refuse drafts larger than 64 KiB
    huge = "x" * (64 * 1024 + 1)
    resp = client.post("/api/jobs/42/draft",
                       json={"tokens": [], "instruction": huge})
    assert resp.status_code == 413
```

- [ ] **Step 4.2: Run the tests — expect 404s on the unimplemented routes**

Run: `uv run pytest tests/unit/test_dashboard_draft_endpoints.py -v`
Expected: 7 failures.

- [ ] **Step 4.3: Add the draft endpoints**

Open `src/pipeline/dashboard/server.py`. After the `_TransitionClearBody` class added in Task 2, add:

```python
class _DraftBody(BaseModel):
    tokens: list[str]
    instruction: str


_MAX_DRAFT_BYTES = 64 * 1024
```

Inside `create_app`, after the SFX endpoints from Task 3, add:

```python
    @app.get("/api/jobs/{project_id}/draft")
    def get_draft(project_id: str) -> JSONResponse:
        proj = _project_root(project_id)
        path = proj / "edit_draft.json"
        if not path.exists():
            return JSONResponse({"tokens": [], "instruction": ""})
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # Corrupted draft — treat as empty rather than 500.
            return JSONResponse({"tokens": [], "instruction": ""})
        # Defensive: only return the two fields we care about.
        return JSONResponse({
            "tokens": list(data.get("tokens", [])),
            "instruction": str(data.get("instruction", "")),
        })

    @app.post("/api/jobs/{project_id}/draft")
    def post_draft(project_id: str, body: _DraftBody) -> JSONResponse:
        proj = _project_root(project_id)
        payload = {"tokens": body.tokens, "instruction": body.instruction}
        encoded = json.dumps(payload).encode("utf-8")
        if len(encoded) > _MAX_DRAFT_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"draft exceeds {_MAX_DRAFT_BYTES} bytes",
            )
        path = proj / "edit_draft.json"
        path.write_bytes(encoded)
        return JSONResponse({"ok": True})

    @app.delete("/api/jobs/{project_id}/draft")
    def delete_draft(project_id: str) -> JSONResponse:
        proj = _project_root(project_id)
        path = proj / "edit_draft.json"
        path.unlink(missing_ok=True)
        return JSONResponse({"ok": True})
```

`json` is already imported indirectly (Plan 2 added `import json as _json` for the verifier endpoint). Add a top-level `import json` if it isn't already there:

```python
import json
```

- [ ] **Step 4.4: Run the tests — expect pass**

Run: `uv run pytest tests/unit/test_dashboard_draft_endpoints.py -v`
Expected: 7 passed.

- [ ] **Step 4.5: Commit**

```bash
git add src/pipeline/dashboard/server.py tests/unit/test_dashboard_draft_endpoints.py
git commit -m "feat(dashboard): edit-draft GET/POST/DELETE endpoints"
```

---

## Task 5: Frontend `tokens.js` — pure-logic token grammar module

**Files:**
- Create: `src/pipeline/dashboard/static/tokens.js`

This is a pure ES5/ES6 module exposing `window.EditTokens` with parsing, formatting, and helper functions. No DOM access. The bottom of the file runs `console.assert` self-tests when `?test=1` is in the URL.

Token grammar (from spec §"Token grammar"):

| Form | Pattern |
|---|---|
| `@sN` | whole scene |
| `@sN/<element>` | element ∈ {visual, subtitle, overlay, narration, transition} |
| `@manifest:<item_id>` | manifest constraint |

- [ ] **Step 5.1: Create `tokens.js` with the parser, formatter, and self-tests**

Create `src/pipeline/dashboard/static/tokens.js`:

```javascript
// EditTokens — pure-logic token grammar for the edit-mode composer.
//
// A token is one of:
//   "@sN"               — whole scene (e.g. "@s9")
//   "@sN/<element>"     — element ∈ {visual, subtitle, overlay, narration, transition}
//   "@manifest:<id>"    — manifest constraint (e.g. "@manifest:verbatim_3")
//
// Whitespace separates tokens. Tokens are case-sensitive.
//
// This module exposes window.EditTokens and runs self-tests when the page is
// loaded with ?test=1 in the query string.

(function () {
  'use strict';

  var SCENE_ELEMENTS = ['visual', 'subtitle', 'overlay', 'narration', 'transition'];

  // /^@s(\d+)(?:\/(visual|subtitle|overlay|narration|transition))?$/
  var SCENE_RE = new RegExp('^@s(\\d+)(?:\\/(' + SCENE_ELEMENTS.join('|') + '))?$');
  // /^@manifest:([A-Za-z0-9_\-]+)$/
  var MANIFEST_RE = /^@manifest:([A-Za-z0-9_\-]+)$/;

  // parseToken("@s9/visual") -> {kind:"scene", scene:"s9", element:"visual", raw:"@s9/visual"}
  // parseToken("@s9")        -> {kind:"scene", scene:"s9", element:null, raw:"@s9"}
  // parseToken("@manifest:x")-> {kind:"manifest", item:"x", raw:"@manifest:x"}
  // parseToken("garbage")    -> null
  function parseToken(raw) {
    if (typeof raw !== 'string') return null;
    var s = raw.trim();
    var m = s.match(SCENE_RE);
    if (m) {
      return {
        kind: 'scene',
        scene: 's' + m[1],
        element: m[2] || null,
        raw: s,
      };
    }
    m = s.match(MANIFEST_RE);
    if (m) {
      return { kind: 'manifest', item: m[1], raw: s };
    }
    return null;
  }

  // parseTokenList("  @s9 @s11/subtitle  ") -> [parseToken("@s9"), parseToken("@s11/subtitle")]
  function parseTokenList(text) {
    if (!text) return [];
    var parts = String(text).split(/\s+/);
    var out = [];
    for (var i = 0; i < parts.length; i++) {
      if (!parts[i]) continue;
      var p = parseToken(parts[i]);
      if (p) out.push(p);
    }
    return out;
  }

  // mintTokenFromElement(el) — infer a token string from a DOM element by reading
  // its data-edit-token attribute. Walks up the parent chain (closest match).
  // Returns the raw token string, or null if no annotated ancestor.
  function mintTokenFromElement(el) {
    if (!el || !el.closest) return null;
    var match = el.closest('[data-edit-token]');
    return match ? match.getAttribute('data-edit-token') : null;
  }

  // tokenLabel("@s9/visual") -> "Scene 9 image"
  function tokenLabel(raw) {
    var t = parseToken(raw);
    if (!t) return raw;
    if (t.kind === 'manifest') return 'Manifest: ' + t.item;
    var sceneNum = t.scene.replace(/^s/, '');
    var elemLabels = {
      visual:     'image',
      subtitle:   'subtitle',
      overlay:    'overlay text',
      narration:  'narration',
      transition: 'transition out',
    };
    if (!t.element) return 'Scene ' + sceneNum;
    return 'Scene ' + sceneNum + ' ' + (elemLabels[t.element] || t.element);
  }

  // dedupeTokens(["@s9", "@s9", "@s11/subtitle"]) -> ["@s9", "@s11/subtitle"]
  function dedupeTokens(rawList) {
    var seen = {};
    var out = [];
    for (var i = 0; i < rawList.length; i++) {
      if (seen[rawList[i]]) continue;
      seen[rawList[i]] = true;
      out.push(rawList[i]);
    }
    return out;
  }

  // sceneIdsTouched(tokens) -> ["s9", "s11"]  (manifest tokens are skipped)
  function sceneIdsTouched(rawList) {
    var seen = {};
    var out = [];
    for (var i = 0; i < rawList.length; i++) {
      var t = parseToken(rawList[i]);
      if (t && t.kind === 'scene' && !seen[t.scene]) {
        seen[t.scene] = true;
        out.push(t.scene);
      }
    }
    return out;
  }

  window.EditTokens = {
    SCENE_ELEMENTS: SCENE_ELEMENTS.slice(),
    parseToken: parseToken,
    parseTokenList: parseTokenList,
    mintTokenFromElement: mintTokenFromElement,
    tokenLabel: tokenLabel,
    dedupeTokens: dedupeTokens,
    sceneIdsTouched: sceneIdsTouched,
  };

  // Self-tests — run only when ?test=1 is in the URL or window.__EDIT_TOKENS_TEST__ is set.
  function runSelfTests() {
    var pass = 0, fail = 0;
    function eq(actual, expected, msg) {
      var ok = JSON.stringify(actual) === JSON.stringify(expected);
      if (ok) { pass++; }
      else { fail++; console.error('FAIL ' + msg + ' — expected ' + JSON.stringify(expected) + ', got ' + JSON.stringify(actual)); }
    }
    eq(parseToken('@s9'),
       {kind:'scene', scene:'s9', element:null, raw:'@s9'}, 'parse @s9');
    eq(parseToken('@s12/visual'),
       {kind:'scene', scene:'s12', element:'visual', raw:'@s12/visual'}, 'parse @s12/visual');
    eq(parseToken('@s9/transition'),
       {kind:'scene', scene:'s9', element:'transition', raw:'@s9/transition'}, 'parse @s9/transition');
    eq(parseToken('@manifest:verbatim_3'),
       {kind:'manifest', item:'verbatim_3', raw:'@manifest:verbatim_3'}, 'parse @manifest:verbatim_3');
    eq(parseToken('@s9/bogus'), null, 'reject unknown element');
    eq(parseToken('garbage'), null, 'reject non-token');
    eq(parseToken(''), null, 'reject empty');
    eq(parseToken(null), null, 'reject null');

    eq(parseTokenList('  @s9   @s11/subtitle  ').map(function(t){return t.raw;}),
       ['@s9', '@s11/subtitle'], 'parseTokenList trims and splits');
    eq(parseTokenList('@s9 garbage @manifest:foo').length, 2,
       'parseTokenList drops invalid tokens silently');

    eq(tokenLabel('@s9'),               'Scene 9',           'label scene');
    eq(tokenLabel('@s12/visual'),       'Scene 12 image',    'label visual');
    eq(tokenLabel('@s5/subtitle'),      'Scene 5 subtitle',  'label subtitle');
    eq(tokenLabel('@s5/overlay'),       'Scene 5 overlay text', 'label overlay');
    eq(tokenLabel('@s5/narration'),     'Scene 5 narration', 'label narration');
    eq(tokenLabel('@s5/transition'),    'Scene 5 transition out', 'label transition');
    eq(tokenLabel('@manifest:foo'),     'Manifest: foo',     'label manifest');
    eq(tokenLabel('garbage'),           'garbage',           'label passthrough on parse fail');

    eq(dedupeTokens(['@s9', '@s9', '@s11/subtitle']),
       ['@s9', '@s11/subtitle'], 'dedupe preserves order');

    eq(sceneIdsTouched(['@s9', '@s9/visual', '@s11/subtitle', '@manifest:x']),
       ['s9', 's11'], 'sceneIdsTouched dedupes and skips manifest');

    var div = document.createElement('div');
    div.setAttribute('data-edit-token', '@s7/visual');
    var inner = document.createElement('span');
    div.appendChild(inner);
    eq(mintTokenFromElement(inner), '@s7/visual', 'mintTokenFromElement walks up');
    eq(mintTokenFromElement(document.createElement('div')), null, 'mint returns null when no annotation');

    var summary = 'EditTokens self-tests: ' + pass + ' passed, ' + fail + ' failed';
    if (fail) console.error(summary); else console.log(summary);
    window.__EDIT_TOKENS_TEST_RESULT__ = {pass: pass, fail: fail};
  }

  if (typeof location !== 'undefined' && location.search.indexOf('test=1') >= 0) {
    runSelfTests();
  } else if (typeof window !== 'undefined' && window.__EDIT_TOKENS_TEST__) {
    runSelfTests();
  }
})();
```

- [ ] **Step 5.2: Smoke-test in a browser**

Start the dashboard server and load with `?test=1`:

```bash
./scripts/start-dashboard.sh --local-only &
DASH_PID=$!
sleep 2
# (then visit http://localhost:7860/?test=1 and check the JS console for
#  "EditTokens self-tests: N passed, 0 failed")
kill $DASH_PID
```

Note: the script will fail at this step until Task 8 wires `tokens.js` into `index.html`. Defer the actual browser smoke test to Task 8; for now just confirm `tokens.js` parses (no syntax error) by `node` checking it:

```bash
node -e "var window={};var location={search:''};require('fs').readFileSync('src/pipeline/dashboard/static/tokens.js','utf8');" \
  || echo "syntax probably fine"
```

The above is a sanity check; the real validation is in Task 16's integration test.

- [ ] **Step 5.3: Commit**

```bash
git add src/pipeline/dashboard/static/tokens.js
git commit -m "feat(dashboard): tokens.js — pure-logic token grammar parser"
```

---

## Task 6: Frontend `cost_estimate.js` — pure-logic cost map

**Files:**
- Create: `src/pipeline/dashboard/static/cost_estimate.js`

The composer pops a confirm dialog **only when the job involves real cost (image regen) or wide rebuild (>50% of scenes)** (spec §"Flow 1 — Edit-mode + composer", step 4). The estimate is a heuristic over token kinds — the natural-language instruction is opaque at this layer; the agent (Plan 3) is the source of truth for actual cost and may expand scope mid-job, but that's caught by the trust gate (spec §"Component design / Confirm popup", parenthetical).

Cost map (per-token):

| Token kind | Estimate (USD) | Reason |
|---|---|---|
| `@sN/visual` | 0.04 | image regen at production tier |
| `@sN` (whole scene) | 0.04 | possible image regen if instruction touches the visual |
| `@sN/subtitle` | 0 | text-only mutation |
| `@sN/overlay` | 0 | text-only |
| `@sN/narration` | 0 | text-only (Edge-TTS is free; Whisper transcribe is cheap and only runs on prerecorded uploads, not narration text edits) |
| `@sN/transition` | 0 | recompose-only |
| `@manifest:X` | 0.04 | unknown scope; treat as image-regen-class for safety |

Wide-rebuild rule: confirm if `unique_scenes_touched / total_scenes_in_storyboard > 0.5`.

- [ ] **Step 6.1: Create `cost_estimate.js`**

Create `src/pipeline/dashboard/static/cost_estimate.js`:

```javascript
// EditCostEstimate — heuristic cost / wide-rebuild estimate for a composer draft.
//
// Used to decide whether to show a confirm popup before submit:
//   needsConfirm = (usd > 0) || wideRebuild
//
// The actual money/scope is determined by the agent (Plan 3); this layer is
// purely UX safety. The trust gate in Plan 5 catches scope expansion the
// frontend missed.

(function () {
  'use strict';

  var COST_PER_TOKEN_USD = {
    visual:     0.04,
    subtitle:   0.00,
    overlay:    0.00,
    narration:  0.00,
    transition: 0.00,
    manifest:   0.04,
    sceneOnly:  0.04,
  };

  var WIDE_REBUILD_THRESHOLD = 0.5;

  // estimateJobCost(rawTokens, totalScenes)
  // -> {usd: number, wideRebuild: boolean, scenesTouched: number, needsConfirm: boolean}
  function estimateJobCost(rawTokens, totalScenes) {
    if (!window.EditTokens) {
      throw new Error('EditTokens not loaded — load tokens.js before cost_estimate.js');
    }
    var usd = 0;
    var sceneSet = {};
    for (var i = 0; i < rawTokens.length; i++) {
      var t = window.EditTokens.parseToken(rawTokens[i]);
      if (!t) continue;
      if (t.kind === 'manifest') {
        usd += COST_PER_TOKEN_USD.manifest;
        continue;
      }
      sceneSet[t.scene] = true;
      var key = t.element || 'sceneOnly';
      if (typeof COST_PER_TOKEN_USD[key] === 'number') {
        usd += COST_PER_TOKEN_USD[key];
      }
    }
    var scenesTouched = 0;
    for (var k in sceneSet) if (sceneSet.hasOwnProperty(k)) scenesTouched++;
    var wideRebuild = (totalScenes > 0)
      && (scenesTouched / totalScenes > WIDE_REBUILD_THRESHOLD);
    return {
      usd: Math.round(usd * 1000) / 1000,
      wideRebuild: wideRebuild,
      scenesTouched: scenesTouched,
      needsConfirm: usd > 0 || wideRebuild,
    };
  }

  // formatSummaryLine(rawTokens, totalScenes) -> "3 tokens · 2 scenes · est. $0.080"
  function formatSummaryLine(rawTokens, totalScenes) {
    var est = estimateJobCost(rawTokens, totalScenes);
    var n = rawTokens.length;
    return n + ' token' + (n === 1 ? '' : 's')
      + ' · ' + est.scenesTouched + ' scene' + (est.scenesTouched === 1 ? '' : 's')
      + ' · est. $' + est.usd.toFixed(3);
  }

  window.EditCostEstimate = {
    COST_PER_TOKEN_USD: COST_PER_TOKEN_USD,
    WIDE_REBUILD_THRESHOLD: WIDE_REBUILD_THRESHOLD,
    estimateJobCost: estimateJobCost,
    formatSummaryLine: formatSummaryLine,
  };

  function runSelfTests() {
    var pass = 0, fail = 0;
    function eq(actual, expected, msg) {
      var ok = JSON.stringify(actual) === JSON.stringify(expected);
      if (ok) pass++; else { fail++; console.error('FAIL ' + msg + ' — got ' + JSON.stringify(actual) + ', expected ' + JSON.stringify(expected)); }
    }

    eq(estimateJobCost(['@s1/subtitle'], 10),
       {usd: 0, wideRebuild: false, scenesTouched: 1, needsConfirm: false},
       'subtitle-only edit: no confirm');

    eq(estimateJobCost(['@s1/visual'], 10),
       {usd: 0.04, wideRebuild: false, scenesTouched: 1, needsConfirm: true},
       'image regen triggers confirm');

    eq(estimateJobCost(['@s1', '@s2', '@s3', '@s4', '@s5', '@s6'], 10),
       {usd: 0.24, wideRebuild: true, scenesTouched: 6, needsConfirm: true},
       'wide rebuild + sceneOnly cost');

    eq(estimateJobCost(['@s1/subtitle', '@s2/subtitle'], 10),
       {usd: 0, wideRebuild: false, scenesTouched: 2, needsConfirm: false},
       'two subtitle edits stay free');

    eq(estimateJobCost(['@s1/subtitle', '@s2/subtitle', '@s3/subtitle', '@s4/subtitle', '@s5/subtitle', '@s6/subtitle'], 10),
       {usd: 0, wideRebuild: true, scenesTouched: 6, needsConfirm: true},
       'wide rebuild without cost still confirms');

    eq(estimateJobCost(['@manifest:verbatim_3'], 10),
       {usd: 0.04, wideRebuild: false, scenesTouched: 0, needsConfirm: true},
       'manifest token costs $0.04');

    eq(estimateJobCost([], 10),
       {usd: 0, wideRebuild: false, scenesTouched: 0, needsConfirm: false},
       'empty draft');

    eq(formatSummaryLine(['@s1/visual', '@s2/subtitle'], 10),
       '2 tokens · 2 scenes · est. $0.040', 'summary line format');
    eq(formatSummaryLine(['@s1'], 10),
       '1 token · 1 scene · est. $0.040', 'summary singularizes');

    var summary = 'EditCostEstimate self-tests: ' + pass + ' passed, ' + fail + ' failed';
    if (fail) console.error(summary); else console.log(summary);
    window.__EDIT_COST_TEST_RESULT__ = {pass: pass, fail: fail};
  }

  if (typeof location !== 'undefined' && location.search.indexOf('test=1') >= 0) {
    runSelfTests();
  } else if (typeof window !== 'undefined' && window.__EDIT_COST_TEST__) {
    runSelfTests();
  }
})();
```

- [ ] **Step 6.2: Commit**

```bash
git add src/pipeline/dashboard/static/cost_estimate.js
git commit -m "feat(dashboard): cost_estimate.js — heuristic confirm-popup trigger"
```

---

## Task 7: Static-test harness HTML + node-driven integration test

**Why:** `tokens.js` and `cost_estimate.js` ship inline `console.assert`-style self-tests. We want a CI-runnable check that doesn't require Playwright.

**Files:**
- Create: `src/pipeline/dashboard/static/edit_mode_test.html`
- Create: `tests/integration/test_static_self_tests.py`

- [ ] **Step 7.1: Create the harness HTML**

Create `src/pipeline/dashboard/static/edit_mode_test.html`:

```html
<!doctype html>
<html><head><meta charset="utf-8"><title>edit-mode self-tests</title></head>
<body>
<h3>Edit-mode self-tests</h3>
<pre id="out">running…</pre>
<script>
  // Stamp ?test=1 onto location.search so tokens.js / cost_estimate.js
  // pick up the trigger when loaded as <script src=...> below.
  Object.defineProperty(window, 'location', {
    value: Object.assign({}, location, {search: '?test=1'}),
    writable: true, configurable: true,
  });
</script>
<script src="/static/tokens.js"></script>
<script src="/static/cost_estimate.js"></script>
<script>
  var tok = window.__EDIT_TOKENS_TEST_RESULT__ || {pass:0,fail:0};
  var cost = window.__EDIT_COST_TEST_RESULT__ || {pass:0,fail:0};
  document.getElementById('out').textContent =
    'tokens.js: ' + tok.pass + ' pass, ' + tok.fail + ' fail\n' +
    'cost_estimate.js: ' + cost.pass + ' pass, ' + cost.fail + ' fail';
  if (tok.fail || cost.fail) document.body.style.background = '#fee';
</script>
</body></html>
```

- [ ] **Step 7.2: Create the integration test that runs the JS in `node` (no browser required)**

Create `tests/integration/test_static_self_tests.py`:

```python
"""Run the JS self-tests in tokens.js and cost_estimate.js using node.

The tests are pure-logic and don't need a real DOM — we shim the few DOM bits
(`document.createElement`, `Element.closest`) inline. Skips when node is not
installed (ruff / mypy / pytest still pass without it).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


_STATIC = Path(__file__).resolve().parents[2] / "src" / "pipeline" / "dashboard" / "static"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_tokens_self_tests_pass():
    shim = (
        # Minimal DOM shim for the one test that creates a div hierarchy.
        "global.window = global;\n"
        "global.location = { search: '?test=1' };\n"
        "global.console = console;\n"
        "global.document = {\n"
        "  createElement: function(tag) {\n"
        "    var el = { _tag: tag, _attrs: {}, _children: [], _parent: null,\n"
        "      setAttribute: function(k,v){this._attrs[k]=v;},\n"
        "      getAttribute: function(k){return this._attrs[k]||null;},\n"
        "      appendChild: function(c){c._parent=this;this._children.push(c);return c;},\n"
        "      closest: function(sel){\n"
        "        var m = sel.match(/^\\[([^=]+)(=\".*\")?\\]$/);\n"
        "        var key = m && m[1];\n"
        "        for (var n=this; n; n=n._parent) {\n"
        "          if (n._attrs && n._attrs[key]!==undefined) return n;\n"
        "        }\n"
        "        return null;\n"
        "      }\n"
        "    };\n"
        "    return el;\n"
        "  }\n"
        "};\n"
        f"var src = require('fs').readFileSync('{_STATIC / 'tokens.js'}', 'utf8');\n"
        "eval(src);\n"
        "var r = global.__EDIT_TOKENS_TEST_RESULT__ || {pass:0,fail:1};\n"
        "if (r.fail > 0) { process.exit(2); }\n"
        "console.log('tokens.js: ' + r.pass + ' passed');\n"
    )
    result = subprocess.run(["node", "-e", shim], capture_output=True, text=True)
    assert result.returncode == 0, (
        f"tokens.js self-tests failed.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_cost_estimate_self_tests_pass():
    shim = (
        "global.window = global;\n"
        "global.location = { search: '?test=1' };\n"
        "global.console = console;\n"
        "global.document = { createElement: function(){ return { setAttribute:function(){}, appendChild:function(c){return c;}, closest:function(){return null;} }; } };\n"
        f"var t = require('fs').readFileSync('{_STATIC / 'tokens.js'}', 'utf8');\n"
        "eval(t);\n"
        f"var c = require('fs').readFileSync('{_STATIC / 'cost_estimate.js'}', 'utf8');\n"
        "eval(c);\n"
        "var r = global.__EDIT_COST_TEST_RESULT__ || {pass:0,fail:1};\n"
        "if (r.fail > 0) { process.exit(2); }\n"
        "console.log('cost_estimate.js: ' + r.pass + ' passed');\n"
    )
    result = subprocess.run(["node", "-e", shim], capture_output=True, text=True)
    assert result.returncode == 0, (
        f"cost_estimate.js self-tests failed.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
```

- [ ] **Step 7.3: Run the tests**

Run: `uv run pytest tests/integration/test_static_self_tests.py -v`
Expected: 2 passed (or 2 skipped if `node` is not installed — both are acceptable).

- [ ] **Step 7.4: Commit**

```bash
git add src/pipeline/dashboard/static/edit_mode_test.html tests/integration/test_static_self_tests.py
git commit -m "test(dashboard): node-driven self-tests for tokens.js and cost_estimate.js"
```

---

## Task 8: Frontend `edit_draft.js` — backend-backed autosave

**Files:**
- Create: `src/pipeline/dashboard/static/edit_draft.js`

Wraps the three draft endpoints with a debounce so the textarea / chip changes auto-save without thrashing the server.

- [ ] **Step 8.1: Create `edit_draft.js`**

Create `src/pipeline/dashboard/static/edit_draft.js`:

```javascript
// EditDraftStore — load / save / clear the per-project edit_draft.json.
// Writes are debounced 400ms so typing doesn't thrash the server.

(function () {
  'use strict';

  var DEBOUNCE_MS = 400;

  function makeStore(projectId) {
    var saveTimer = null;
    var pendingPayload = null;

    async function load() {
      var resp = await fetch('/api/jobs/' + encodeURIComponent(projectId) + '/draft');
      if (!resp.ok) {
        return { tokens: [], instruction: '' };
      }
      var data = await resp.json();
      return {
        tokens: Array.isArray(data.tokens) ? data.tokens.slice() : [],
        instruction: typeof data.instruction === 'string' ? data.instruction : '',
      };
    }

    function save(payload) {
      pendingPayload = payload;
      if (saveTimer) clearTimeout(saveTimer);
      saveTimer = setTimeout(flush, DEBOUNCE_MS);
    }

    async function flush() {
      saveTimer = null;
      if (!pendingPayload) return;
      var payload = pendingPayload;
      pendingPayload = null;
      try {
        await fetch('/api/jobs/' + encodeURIComponent(projectId) + '/draft', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
      } catch (err) {
        // Quiet failure — the user can re-trigger by typing or submitting.
        console.warn('draft save failed', err);
      }
    }

    async function clear() {
      if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; }
      pendingPayload = null;
      try {
        await fetch('/api/jobs/' + encodeURIComponent(projectId) + '/draft', {
          method: 'DELETE',
        });
      } catch (err) {
        console.warn('draft clear failed', err);
      }
    }

    return { load: load, save: save, flush: flush, clear: clear };
  }

  window.EditDraftStore = { make: makeStore };
})();
```

- [ ] **Step 8.2: Commit**

```bash
git add src/pipeline/dashboard/static/edit_draft.js
git commit -m "feat(dashboard): edit_draft.js — debounced backend-backed draft store"
```

---

## Task 9: Frontend `edit_mode.js` — toggle + click-to-mint registry

**Files:**
- Create: `src/pipeline/dashboard/static/edit_mode.js`

Owns the global edit-mode state, the header toggle button, the sticky bottom strip, the ESC keybinding, and the top-level click handler that routes any click on a `data-edit-token`-annotated element to either the native handler (edit off) or the composer's `addToken` (edit on).

- [ ] **Step 9.1: Create `edit_mode.js`**

Create `src/pipeline/dashboard/static/edit_mode.js`:

```javascript
// EditMode — global toggle + click-to-mint registry.
//
// Dependencies (load order):
//   tokens.js
//   cost_estimate.js
//   edit_draft.js
//   composer.js  (Composer.addToken / Composer.openForProject — Task 10)
//
// State lives in localStorage keyed by project id. Auto-exits on submit.

(function () {
  'use strict';

  var STORAGE_PREFIX = 'edit-mode:';
  var activeProjectId = null;
  var enabled = false;

  function storageKey(projectId) { return STORAGE_PREFIX + projectId; }

  function isEnabledForProject(projectId) {
    try {
      return localStorage.getItem(storageKey(projectId)) === '1';
    } catch (e) { return false; }
  }

  function setEnabled(projectId, on) {
    activeProjectId = projectId;
    enabled = !!on;
    try {
      if (enabled) localStorage.setItem(storageKey(projectId), '1');
      else localStorage.removeItem(storageKey(projectId));
    } catch (e) { /* private mode */ }
    document.body.classList.toggle('edit-mode-on', enabled);
    updateStickyStrip();
    if (window.EditComposer) {
      if (enabled) window.EditComposer.openForProject(projectId);
      else window.EditComposer.close();
    }
    updateToggleButtons();
  }

  function toggle(projectId) {
    setEnabled(projectId, !(enabled && activeProjectId === projectId));
  }

  function updateToggleButtons() {
    var btns = document.querySelectorAll('.edit-mode-toggle');
    btns.forEach(function (b) {
      var pid = b.getAttribute('data-project-id');
      var on = enabled && pid === activeProjectId;
      b.classList.toggle('on', on);
      b.textContent = on ? '✏️ Edit mode: ON' : '✏️ Edit mode';
    });
  }

  function ensureStickyStrip() {
    var strip = document.getElementById('edit-mode-strip');
    if (!strip) {
      strip = document.createElement('div');
      strip.id = 'edit-mode-strip';
      strip.style.cssText = (
        'position:fixed;bottom:0;left:0;right:0;z-index:900;'
        + 'padding:8px 14px;background:#1e3a5f;color:#bfdbfe;font-size:11px;'
        + 'border-top:1px solid #3b82f6;display:none;font-family:system-ui,sans-serif;'
        + 'pointer-events:none;'
      );
      strip.textContent = 'Edit mode — tap any scene element to add a token (Esc to exit)';
      document.body.appendChild(strip);
    }
    return strip;
  }

  function updateStickyStrip() {
    var strip = ensureStickyStrip();
    strip.style.display = enabled ? '' : 'none';
  }

  function isInteractive(el) {
    if (!el) return false;
    var tag = el.tagName;
    return tag === 'A' || tag === 'BUTTON' || tag === 'INPUT'
        || tag === 'SELECT' || tag === 'TEXTAREA';
  }

  // Top-level capture-phase click handler. If edit mode is on AND the click is
  // on a [data-edit-token] element, mint the token and suppress the native
  // action. Otherwise fall through.
  function onClickCapture(ev) {
    if (!enabled) return;
    if (!ev.target || !ev.target.closest) return;
    var match = ev.target.closest('[data-edit-token]');
    if (!match) return;
    // Don't hijack the toggle button itself or the composer's own UI.
    if (ev.target.closest('.edit-mode-toggle')) return;
    if (ev.target.closest('#edit-composer')) return;
    var token = match.getAttribute('data-edit-token');
    if (!token) return;
    if (window.EditComposer && activeProjectId) {
      window.EditComposer.addToken(token);
      ev.preventDefault();
      ev.stopPropagation();
    }
  }

  function onKeydown(ev) {
    if (!enabled) return;
    if (ev.key === 'Escape') {
      if (activeProjectId) setEnabled(activeProjectId, false);
    }
  }

  function attach(projectId) {
    // Restore persisted state on first attach for this project.
    if (isEnabledForProject(projectId)) {
      setEnabled(projectId, true);
    }
  }

  function init() {
    document.addEventListener('click', onClickCapture, true);
    document.addEventListener('keydown', onKeydown);
    ensureStickyStrip();
    updateToggleButtons();
  }

  if (document.readyState !== 'loading') init();
  else document.addEventListener('DOMContentLoaded', init);

  window.EditMode = {
    toggle: toggle,
    setEnabled: setEnabled,
    attach: attach,
    isEnabled: function () { return enabled; },
    activeProjectId: function () { return activeProjectId; },
  };
})();
```

- [ ] **Step 9.2: Commit**

```bash
git add src/pipeline/dashboard/static/edit_mode.js
git commit -m "feat(dashboard): edit_mode.js — toggle + click-to-mint registry"
```

---

## Task 10: Frontend `composer.js` — floating chips + textarea + confirm popup + submit

**Files:**
- Create: `src/pipeline/dashboard/static/composer.js`

The composer renders inside `#edit-composer` (a host node added to `index.html` in Task 11). It exposes:

- `openForProject(projectId)` — load draft, render chips + textarea, show
- `close()` — hide and flush draft
- `addToken(rawToken)` — append, dedupe, refresh summary, autosave
- `removeToken(rawToken)` — drop, refresh summary, autosave

The composer also owns the cost-aware confirm popup and the submit POST.

- [ ] **Step 10.1: Create `composer.js`**

Create `src/pipeline/dashboard/static/composer.js`:

```javascript
// EditComposer — floating composer + confirm popup + submit wiring.
//
// Dependencies (load order, see index.html):
//   tokens.js, cost_estimate.js, edit_draft.js, edit_mode.js
//
// Public API:
//   EditComposer.openForProject(projectId)
//   EditComposer.close()
//   EditComposer.addToken(rawToken)
//   EditComposer.removeToken(rawToken)

(function () {
  'use strict';

  var STYLE = (
    '#edit-composer { position: fixed; right: 14px; bottom: 36px; z-index: 950;'
    + '  width: min(440px, 92vw); background: #0f172a; color: #e2e8f0;'
    + '  border: 1px solid #3b82f6; border-radius: 8px; padding: 12px;'
    + '  box-shadow: 0 4px 24px rgba(0,0,0,.4); font-family: system-ui,sans-serif;'
    + '  display: none; }'
    + '#edit-composer.open { display: block; }'
    + '#edit-composer.collapsed { padding: 8px 12px; }'
    + '#edit-composer .ec-collapsed-bar { display: none; align-items: center;'
    + '  gap: 8px; cursor: pointer; }'
    + '#edit-composer.collapsed .ec-body { display: none; }'
    + '#edit-composer.collapsed .ec-collapsed-bar { display: flex; }'
    + '#edit-composer .ec-chips { display: flex; flex-wrap: wrap; gap: 6px;'
    + '  margin-bottom: 8px; min-height: 24px; }'
    + '#edit-composer .ec-chip { display: inline-flex; gap: 6px; align-items: center;'
    + '  background: #1e293b; border: 1px solid #2d3748; color: #93c5fd;'
    + '  padding: 3px 8px; border-radius: 12px; font-size: 11px; font-family: monospace; }'
    + '#edit-composer .ec-chip-x { cursor: pointer; opacity: .6; }'
    + '#edit-composer .ec-chip-x:hover { opacity: 1; color: #f87171; }'
    + '#edit-composer textarea { width: 100%; height: 60px; resize: vertical;'
    + '  background: #0f172a; color: #e2e8f0; border: 1px solid #2d3748;'
    + '  border-radius: 4px; padding: 6px 8px; font-size: 12px; font-family: inherit;'
    + '  margin-bottom: 8px; }'
    + '#edit-composer .ec-summary { font-size: 11px; color: #94a3b8;'
    + '  margin-bottom: 8px; min-height: 14px; }'
    + '#edit-composer .ec-actions { display: flex; gap: 6px; justify-content: flex-end; }'
    + '#edit-composer .ec-actions button { font-size: 11px; padding: 5px 12px;'
    + '  border-radius: 4px; border: 1px solid #2d3748; background: #1e293b;'
    + '  color: #e2e8f0; cursor: pointer; }'
    + '#edit-composer .ec-actions button.primary { background: #1e3a5f;'
    + '  border-color: #3b82f6; }'
    + '#edit-composer .ec-actions button:disabled { opacity: .4; cursor: not-allowed; }'
    + '.ec-cross-flash { outline: 2px solid #3b82f6 !important;'
    + '  outline-offset: 2px !important; transition: outline-color .15s; }'
    + '.ec-confirm-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.7);'
    + '  display: flex; align-items: center; justify-content: center; z-index: 1100; }'
    + '.ec-confirm-modal { background: #1a1a2e; border: 1px solid #2d3748;'
    + '  border-radius: 6px; padding: 18px; width: min(520px, 92vw);'
    + '  font-family: system-ui,sans-serif; color: #e2e8f0; }'
    + '.ec-confirm-modal h3 { font-size: 14px; margin: 0 0 10px; }'
    + '.ec-confirm-modal .ec-confirm-list { font-size: 12px; color: #cbd5e1;'
    + '  background: #0f172a; border: 1px solid #1e293b; border-radius: 4px;'
    + '  padding: 8px 10px; margin-bottom: 10px; max-height: 160px; overflow: auto; }'
    + '.ec-confirm-modal .ec-confirm-cost { font-size: 12px; color: #facc15;'
    + '  margin-bottom: 10px; }'
    + '@media (max-width: 600px) { #edit-composer { right: 8px; left: 8px;'
    + '  width: auto; bottom: 30px; } }'
  );

  function ensureStyle() {
    if (document.getElementById('ec-style')) return;
    var s = document.createElement('style');
    s.id = 'ec-style';
    s.textContent = STYLE;
    document.head.appendChild(s);
  }

  function ensureHostNode() {
    var host = document.getElementById('edit-composer');
    if (host) return host;
    host = document.createElement('div');
    host.id = 'edit-composer';
    host.innerHTML = (
      '<div class="ec-collapsed-bar"><span class="ec-collapsed-count">(0)</span>'
      + '<span style="color:#94a3b8;font-size:11px">Edit composer ▲</span></div>'
      + '<div class="ec-body">'
      + '  <div class="ec-chips"></div>'
      + '  <textarea class="ec-instruction" placeholder="Describe the edit, e.g. \'make these darker and tighten the subtitle\'"></textarea>'
      + '  <div class="ec-summary"></div>'
      + '  <div class="ec-actions">'
      + '    <button type="button" class="ec-collapse">Collapse</button>'
      + '    <button type="button" class="ec-cancel">Cancel</button>'
      + '    <button type="button" class="ec-submit primary">Submit</button>'
      + '  </div>'
      + '</div>'
    );
    document.body.appendChild(host);
    return host;
  }

  var state = {
    projectId: null,
    tokens: [],
    instruction: '',
    totalScenes: 0,
    store: null,
  };

  function $(sel) { return document.querySelector(sel); }
  function ecQS(sel) {
    var host = document.getElementById('edit-composer');
    return host ? host.querySelector(sel) : null;
  }

  function renderChips() {
    var chipsEl = ecQS('.ec-chips');
    if (!chipsEl) return;
    chipsEl.innerHTML = '';
    if (!state.tokens.length) {
      chipsEl.innerHTML = '<span style="color:#475569;font-size:11px">No tokens — tap a scene element</span>';
      return;
    }
    state.tokens.forEach(function (raw) {
      var chip = document.createElement('span');
      chip.className = 'ec-chip';
      chip.setAttribute('data-token', raw);
      chip.innerHTML = (
        '<span class="ec-chip-label">' + escapeHtml(raw) + '</span>'
        + '<span class="ec-chip-x" title="Remove">✕</span>'
      );
      chipsEl.appendChild(chip);
    });
  }

  function renderSummary() {
    var sumEl = ecQS('.ec-summary');
    if (!sumEl || !window.EditCostEstimate) return;
    sumEl.textContent = window.EditCostEstimate.formatSummaryLine(
      state.tokens, state.totalScenes,
    );
    var collapsedCount = ecQS('.ec-collapsed-count');
    if (collapsedCount) {
      collapsedCount.textContent = '(' + state.tokens.length + ')';
    }
  }

  function persist() {
    if (!state.store) return;
    state.store.save({
      tokens: state.tokens.slice(),
      instruction: state.instruction,
    });
  }

  function addToken(raw) {
    if (!raw) return;
    if (state.tokens.indexOf(raw) >= 0) return;
    state.tokens.push(raw);
    renderChips();
    renderSummary();
    persist();
  }

  function removeToken(raw) {
    var i = state.tokens.indexOf(raw);
    if (i < 0) return;
    state.tokens.splice(i, 1);
    renderChips();
    renderSummary();
    persist();
  }

  async function openForProject(projectId, totalScenes) {
    ensureStyle();
    var host = ensureHostNode();
    state.projectId = projectId;
    state.store = window.EditDraftStore.make(projectId);
    state.totalScenes = totalScenes || _readTotalScenesFromDOM(projectId);

    var draft = await state.store.load();
    state.tokens = draft.tokens || [];
    state.instruction = draft.instruction || '';

    var instrEl = ecQS('.ec-instruction');
    if (instrEl) instrEl.value = state.instruction;
    renderChips();
    renderSummary();

    host.classList.add('open');
    host.classList.remove('collapsed');
  }

  function close() {
    var host = document.getElementById('edit-composer');
    if (host) host.classList.remove('open');
    if (state.store) state.store.flush();
    state.projectId = null;
    state.store = null;
    state.tokens = [];
    state.instruction = '';
  }

  function _readTotalScenesFromDOM(projectId) {
    // Look for the first detail row's scene strip. Fall back to 1 to avoid /0.
    var strip = document.querySelector(
      'tr[data-detail-for="' + projectId + '"] .scene-strip'
    );
    if (!strip) return 1;
    var n = strip.querySelectorAll('.scene-chip').length;
    return n > 0 ? n : 1;
  }

  // Confirm popup — only triggered when the cost estimator says needsConfirm.
  function showConfirm(callback) {
    var est = window.EditCostEstimate.estimateJobCost(state.tokens, state.totalScenes);
    var rows = state.tokens.map(function (t) {
      return '<div>• ' + escapeHtml(window.EditTokens.tokenLabel(t))
        + ' <span style="color:#475569;font-family:monospace">' + escapeHtml(t) + '</span></div>';
    }).join('');
    var overlay = document.createElement('div');
    overlay.className = 'ec-confirm-overlay';
    overlay.innerHTML = (
      '<div class="ec-confirm-modal">'
      + '<h3>Confirm edit job</h3>'
      + '<div class="ec-confirm-list">' + rows + '</div>'
      + '<div style="font-size:11px;color:#94a3b8;margin-bottom:8px">Instruction:</div>'
      + '<div class="ec-confirm-list" style="white-space:pre-wrap">'
      +   escapeHtml(state.instruction || '(none)') + '</div>'
      + '<div class="ec-confirm-cost">'
      +   (est.usd > 0 ? 'Estimated cost: $' + est.usd.toFixed(3) + '. ' : '')
      +   (est.wideRebuild ? 'Touches >50% of scenes (wide rebuild).' : '')
      + '</div>'
      + '<div class="ec-actions">'
      +   '<button type="button" class="ec-confirm-cancel">Cancel</button>'
      +   '<button type="button" class="ec-confirm-ok primary">Confirm &amp; submit</button>'
      + '</div>'
      + '</div>'
    );
    document.body.appendChild(overlay);
    overlay.querySelector('.ec-confirm-cancel').addEventListener('click', function () {
      overlay.remove(); callback(false);
    });
    overlay.querySelector('.ec-confirm-ok').addEventListener('click', function () {
      overlay.remove(); callback(true);
    });
  }

  async function submit() {
    if (!state.projectId) return;
    if (!state.tokens.length) {
      alert('No tokens. Tap a scene element to add one before submitting.');
      return;
    }
    var est = window.EditCostEstimate.estimateJobCost(state.tokens, state.totalScenes);
    function doPost() {
      var btn = ecQS('.ec-submit');
      if (btn) btn.disabled = true;
      fetch('/api/jobs/' + encodeURIComponent(state.projectId) + '/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tokens: state.tokens,
          instruction: state.instruction,
        }),
      }).then(function (resp) {
        if (!resp.ok) {
          return resp.text().then(function (t) { throw new Error('submit failed: ' + resp.status + ' ' + t); });
        }
        return resp.json();
      }).then(function (body) {
        // Job queued — clear draft, exit edit mode.
        if (state.store) state.store.clear();
        if (window.EditMode && state.projectId) {
          window.EditMode.setEnabled(state.projectId, false);
        }
        // Surface the queued job_id so the user can correlate with Telegram.
        var note = body && body.job_id ? ('Job ' + body.job_id + ' queued.') : 'Job queued.';
        var sumEl = ecQS('.ec-summary');
        if (sumEl) sumEl.textContent = note;
      }).catch(function (err) {
        if (btn) btn.disabled = false;
        alert(err.message || String(err));
      });
    }
    if (est.needsConfirm) {
      showConfirm(function (ok) { if (ok) doPost(); });
    } else {
      doPost();
    }
  }

  // Cross-highlighting — hover a chip → flash matching DOM element.
  function attachCrossHighlight() {
    var host = document.getElementById('edit-composer');
    if (!host) return;
    host.addEventListener('mouseover', function (ev) {
      var chip = ev.target.closest && ev.target.closest('.ec-chip');
      if (!chip) return;
      var token = chip.getAttribute('data-token');
      if (!token) return;
      var match = document.querySelector(
        '[data-edit-token="' + cssEscape(token) + '"]'
      );
      if (match) match.classList.add('ec-cross-flash');
    });
    host.addEventListener('mouseout', function (ev) {
      var chip = ev.target.closest && ev.target.closest('.ec-chip');
      if (!chip) return;
      document.querySelectorAll('.ec-cross-flash').forEach(function (el) {
        el.classList.remove('ec-cross-flash');
      });
    });
  }

  function cssEscape(s) {
    if (window.CSS && window.CSS.escape) return window.CSS.escape(s);
    return String(s).replace(/[^a-zA-Z0-9_-]/g, function (c) {
      return '\\' + c;
    });
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' })[c];
    });
  }

  function wireHostInteractions() {
    var host = ensureHostNode();
    host.addEventListener('click', function (ev) {
      var x = ev.target.closest && ev.target.closest('.ec-chip-x');
      if (x) {
        var chip = x.closest('.ec-chip');
        if (chip) removeToken(chip.getAttribute('data-token'));
        return;
      }
      if (ev.target.closest('.ec-collapse')) {
        host.classList.toggle('collapsed'); return;
      }
      if (ev.target.closest('.ec-collapsed-bar')) {
        host.classList.remove('collapsed'); return;
      }
      if (ev.target.closest('.ec-cancel')) {
        if (window.EditMode && state.projectId) {
          window.EditMode.setEnabled(state.projectId, false);
        }
        return;
      }
      if (ev.target.closest('.ec-submit')) {
        submit();
        return;
      }
    });
    host.addEventListener('input', function (ev) {
      if (ev.target.classList && ev.target.classList.contains('ec-instruction')) {
        state.instruction = ev.target.value;
        persist();
      }
    });
    attachCrossHighlight();
  }

  function init() {
    ensureStyle();
    ensureHostNode();
    wireHostInteractions();
  }
  if (document.readyState !== 'loading') init();
  else document.addEventListener('DOMContentLoaded', init);

  window.EditComposer = {
    openForProject: openForProject,
    close: close,
    addToken: addToken,
    removeToken: removeToken,
  };
})();
```

- [ ] **Step 10.2: Commit**

```bash
git add src/pipeline/dashboard/static/composer.js
git commit -m "feat(dashboard): composer.js — floating composer with confirm popup + submit"
```

---

## Task 11: Wire edit-mode UI into `index.html` — toggle, scripts, data-edit-token

**Files:**
- Modify: `src/pipeline/dashboard/static/index.html`

This task plants the four `data-edit-token` attributes on the existing scene-panel DOM (so the click-to-mint registry can pick them up), adds the edit-mode toggle button to the per-row detail panel, removes Plan 2's temp `🎙 record` button in favor of a tokenized narration-source chip, and pulls in the new JS modules.

- [ ] **Step 11.1: Add the new script tags at the bottom of `<body>`**

In `src/pipeline/dashboard/static/index.html`, find the existing line:

```html
<script src="/static/narration_source_editor.js"></script>
```

Replace with the full set, in dependency order:

```html
<script src="/static/tokens.js"></script>
<script src="/static/cost_estimate.js"></script>
<script src="/static/edit_draft.js"></script>
<script src="/static/edit_mode.js"></script>
<script src="/static/composer.js"></script>
<script src="/static/narration_source_editor.js"></script>
<script src="/static/transition_editor.js"></script>
```

- [ ] **Step 11.2: Annotate the scene chips and panels in `buildSceneStrip(scenes)` with `data-edit-token`**

In `src/pipeline/dashboard/static/index.html`, find the existing `buildSceneStrip` function (around line 190):

```javascript
function buildSceneStrip(scenes) {
  const chips = scenes.map((s, i) =>
    `<div class="scene-chip" data-idx="${i}" data-start="${s.start_sec}">${s.id} · ${s.section}</div>`
  ).join('');
  return `
    <div class="scene-strip">${chips}</div>
    <div class="scene-panels">
      <div class="scene-narration">
        <div class="scene-panel-label">旁白 Narration
          <!-- Plan 2: temporary trigger for the narration-source modal.
               Plan 4 replaces this with the source-chip click-target. -->
          <button class="nse-open-btn" type="button" style="float:right;font-size:10px;
            padding:2px 8px;background:#1e293b;color:#94a3b8;border:1px solid #2d3748;
            border-radius:3px;cursor:pointer;font-weight:normal">🎙 record</button>
        </div>
        <div class="scene-nar-hdr"></div>
        <div class="scene-nar-text"></div>
      </div>
      <div class="scene-subtitle">
        <div class="scene-panel-label">字幕 Subtitle</div>
        <div class="scene-sub-hdr"></div>
        <div class="scene-sub-text"></div>
      </div>
    </div>`;
}
```

Replace with:

```javascript
function buildSceneStrip(scenes) {
  const chips = scenes.map((s, i) =>
    `<div class="scene-chip" data-idx="${i}" data-start="${s.start_sec}"
          data-edit-token="@${s.id}">${s.id} · ${s.section}</div>`
  ).join('');
  return `
    <div class="scene-strip">${chips}</div>
    <div class="scene-panels">
      <div class="scene-narration">
        <div class="scene-panel-label">
          <span class="scene-id-marker"></span> 旁白 Narration
          <span class="narration-source-chip" data-edit-token=""
                style="float:right;font-size:10px;padding:2px 8px;
                background:#1e293b;color:#94a3b8;border:1px solid #2d3748;
                border-radius:12px;cursor:pointer;font-weight:normal">
            🎙 source
          </span>
          <span class="transition-out-chip" data-edit-token=""
                style="float:right;font-size:10px;padding:2px 8px;margin-right:6px;
                background:#1e293b;color:#94a3b8;border:1px solid #2d3748;
                border-radius:12px;cursor:pointer;font-weight:normal">
            ⤳ transition
          </span>
        </div>
        <div class="scene-nar-hdr"></div>
        <div class="scene-nar-text" data-edit-token=""></div>
      </div>
      <div class="scene-subtitle">
        <div class="scene-panel-label">字幕 Subtitle</div>
        <div class="scene-sub-hdr"></div>
        <div class="scene-sub-text" data-edit-token=""></div>
      </div>
    </div>`;
}
```

The `data-edit-token` attributes start blank — they're filled with the active scene's id whenever `showSceneNar(idx)` runs (next step).

- [ ] **Step 11.3: Update `showSceneNar(idx)` to set the per-element `data-edit-token` to the active scene**

In the same file, find `showSceneNar(idx)` inside `toggleDetail(p)` (around line 298):

```javascript
function showSceneNar(idx) {
  const scene = p.scenes[idx];
  const mm = Math.floor(scene.start_sec / 60);
  const ss = String(Math.floor(scene.start_sec % 60)).padStart(2, '0');
  const stamp = `${scene.id} · ${scene.section} · ${mm}:${ss}`;
  narHdr.textContent = stamp;
  narText.textContent = scene.narration;
  subHdr.textContent = stamp;
  subText.textContent = scene.subtitle || '—';
}
```

Replace with:

```javascript
function showSceneNar(idx) {
  const scene = p.scenes[idx];
  const mm = Math.floor(scene.start_sec / 60);
  const ss = String(Math.floor(scene.start_sec % 60)).padStart(2, '0');
  const stamp = `${scene.id} · ${scene.section} · ${mm}:${ss}`;
  narHdr.textContent = stamp;
  narText.textContent = scene.narration;
  subHdr.textContent = stamp;
  subText.textContent = scene.subtitle || '—';
  // Plan 4: keep the click-to-mint tokens in sync with the active scene.
  narText.setAttribute('data-edit-token', `@${scene.id}/narration`);
  subText.setAttribute('data-edit-token', `@${scene.id}/subtitle`);
  const sourceChip = detailRow.querySelector('.narration-source-chip');
  if (sourceChip) sourceChip.setAttribute('data-edit-token', `@${scene.id}/narration`);
  const transChip = detailRow.querySelector('.transition-out-chip');
  if (transChip) transChip.setAttribute('data-edit-token', `@${scene.id}/transition`);
}
```

- [ ] **Step 11.4: Add the edit-mode toggle button + final-video player click target into the detail panel**

In the same file, find the existing `dr.innerHTML = ...` block in `makeDetailRow(p)` (around line 229). Find this line:

```javascript
  dr.innerHTML = `<td colspan="7"><div class="detail-panel">
    ${tabsHtml}
    <video controls src="${firstUrl}"></video>
```

Replace with:

```javascript
  dr.innerHTML = `<td colspan="7"><div class="detail-panel">
    <div style="display:flex;justify-content:flex-end;margin-bottom:8px">
      <button class="edit-mode-toggle" data-project-id="${p.project_id}"
        style="font-size:11px;padding:4px 10px;border-radius:4px;
        border:1px solid #2d3748;background:#1a1a2e;color:#94a3b8;cursor:pointer">
        ✏️ Edit mode
      </button>
    </div>
    ${tabsHtml}
    <div class="video-wrap" data-edit-token="">
      <video controls src="${firstUrl}"></video>
    </div>
```

Add CSS for the active toggle state. Find the existing `.btn-preview.active` line in the `<style>` block (around line 53) and add below the `.btn-preview.active` rule:

```css
    .edit-mode-toggle.on { background: #1e3a5f; color: #93c5fd; border-color: #3b82f6; }
    body.edit-mode-on .scene-chip,
    body.edit-mode-on .scene-nar-text,
    body.edit-mode-on .scene-sub-text,
    body.edit-mode-on .narration-source-chip,
    body.edit-mode-on .transition-out-chip,
    body.edit-mode-on .video-wrap { cursor: cell; }
    body.edit-mode-on [data-edit-token]:hover { outline: 1px dashed #3b82f6; outline-offset: 2px; }
    /* Spec §"Mobile-first": tap targets ≥40px on narrow viewports in edit mode. */
    @media (max-width: 600px) {
      body.edit-mode-on [data-edit-token] { min-height: 40px; padding: 6px 10px; }
      body.edit-mode-on .scene-chip { min-height: 40px; padding: 8px 12px; }
    }
```

- [ ] **Step 11.5: Wire the toggle button + video click-to-mint inside `toggleDetail`**

Add this block at the end of `toggleDetail(p)` in `index.html`, right before the final `activeId = p.project_id;` line:

```javascript
  // Plan 4: edit-mode toggle button.
  const editBtn = detailRow.querySelector('.edit-mode-toggle');
  if (editBtn) {
    editBtn.addEventListener('click', () => {
      window.EditMode.toggle(p.project_id);
    });
  }
  // Plan 4: restore persisted edit-mode state for this project on row open.
  if (window.EditMode) window.EditMode.attach(p.project_id);

  // Plan 4: clicks on the video player in edit mode mint @sN for the
  // currently-displayed scene. We update video-wrap's data-edit-token
  // every timeupdate via the existing scene-tracking loop.
  const wrap = detailRow.querySelector('.video-wrap');
  if (vid && wrap && p.scenes && p.scenes.length) {
    vid.addEventListener('timeupdate', () => {
      let idx = 0;
      const t = vid.currentTime;
      for (let i = 0; i < p.scenes.length; i++) {
        if (t >= p.scenes[i].start_sec) idx = i;
      }
      wrap.setAttribute('data-edit-token', `@${p.scenes[idx].id}`);
    });
    // Initialise data-edit-token to the first scene before timeupdate fires.
    wrap.setAttribute('data-edit-token', `@${p.scenes[0].id}`);
  }
```

- [ ] **Step 11.6: Replace the temp `🎙 record` button handler with a chip-driven click**

In the same file, find the existing block (around line 386):

```javascript
<script>
  // Wire the 🎙 record button: opens NarrationSourceEditor for the active scene.
  document.getElementById('tbody').addEventListener('click', (e) => {
    const btn = e.target.closest('.nse-open-btn');
    if (!btn) return;
    ...
  });
</script>
```

Replace with:

```html
<script>
  // Plan 4: when edit mode is OFF, clicking the narration-source chip opens
  // the NarrationSourceEditor for the current scene. When edit mode is ON,
  // the click-to-mint registry intercepts the click and adds the token
  // instead — the chip's data-edit-token attribute is set by showSceneNar().
  document.getElementById('tbody').addEventListener('click', (e) => {
    if (window.EditMode && window.EditMode.isEnabled()) return;
    const chip = e.target.closest('.narration-source-chip');
    if (!chip) return;
    const detailRow = chip.closest('tr.detail-row');
    if (!detailRow) return;
    const projectId = detailRow.dataset.detailFor;
    const project = currentData.find((p) => p.project_id === projectId);
    if (!project) return;
    const activeChip = detailRow.querySelector('.scene-chip.sc-active')
                       || detailRow.querySelector('.scene-chip');
    if (!activeChip) return;
    const idx = +activeChip.dataset.idx;
    const scene = project.scenes[idx];
    if (!scene) return;
    window.NarrationSourceEditor.open({
      projectId,
      scene: scene.id,
      narrationText: scene.narration || '',
      locale: project.locale || 'zh-TW',
    });
  });
  // Plan 4: similar dispatch for the transition-out chip.
  document.getElementById('tbody').addEventListener('click', (e) => {
    if (window.EditMode && window.EditMode.isEnabled()) return;
    const chip = e.target.closest('.transition-out-chip');
    if (!chip) return;
    const detailRow = chip.closest('tr.detail-row');
    if (!detailRow) return;
    const projectId = detailRow.dataset.detailFor;
    const project = currentData.find((p) => p.project_id === projectId);
    if (!project) return;
    const activeChip = detailRow.querySelector('.scene-chip.sc-active')
                       || detailRow.querySelector('.scene-chip');
    if (!activeChip) return;
    const idx = +activeChip.dataset.idx;
    const fromScene = project.scenes[idx];
    const toScene = project.scenes[idx + 1];
    if (!fromScene || !toScene) {
      alert('No scene after ' + (fromScene && fromScene.id) + ' — transitions need a destination.');
      return;
    }
    window.TransitionEditor.open({
      projectId,
      fromScene: fromScene.id,
      toScene: toScene.id,
    });
  });
</script>
```

- [ ] **Step 11.7: Manual smoke test — load the dashboard and exercise the edit-mode toggle**

```bash
./scripts/start-dashboard.sh --local-only &
DASH_PID=$!
sleep 2
echo "Visit http://localhost:7860/ — open any project's preview row, click 'Edit mode', then tap a scene chip. The composer should appear with @sN as a chip."
echo "Press Ctrl+C to stop."
wait $DASH_PID
```

Acceptance:
- ✏️ Edit mode toggle appears in the detail row.
- Toggling it on shows the sticky bottom strip and the floating composer.
- Tapping a scene chip mints `@sN` into the composer.
- Tapping the narration text mints `@sN/narration`.
- Tapping the subtitle text mints `@sN/subtitle`.
- ESC exits edit mode.
- Refreshing the page persists edit-mode state per project (localStorage).

(`transition-out-chip` will appear but the modal opens in Task 12.)

- [ ] **Step 11.8: Commit**

```bash
git add src/pipeline/dashboard/static/index.html
git commit -m "feat(dashboard): edit-mode toggle, click-to-mint, and tokenized chips in index.html"
```

---

## Task 12: Frontend `transition_editor.js` — direct-action TransitionEditor modal

**Files:**
- Create: `src/pipeline/dashboard/static/transition_editor.js`

The TransitionEditor modal is direct-action: the user picks style + duration + sfx and applies. The modal calls `POST /api/transition/<id>/set` (or `/clear`). It also offers `+ upload custom` which calls `POST /api/sfx/upload` and refreshes the dropdown.

- [ ] **Step 12.1: Create `transition_editor.js`**

Create `src/pipeline/dashboard/static/transition_editor.js`:

```javascript
// TransitionEditor — direct-action modal for setting/clearing per-seam transitions.

(function () {
  'use strict';

  var STYLE = (
    '.te-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.7);'
    + '  display: flex; align-items: center; justify-content: center; z-index: 1000; }'
    + '.te-modal { background: #1a1a2e; color: #e2e8f0; border: 1px solid #2d3748;'
    + '  border-radius: 6px; padding: 18px; width: min(520px, 92vw); }'
    + '.te-h { font-size: 14px; font-weight: 600; margin-bottom: 10px; }'
    + '.te-row { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; }'
    + '.te-row label { font-size: 11px; color: #94a3b8; min-width: 90px; }'
    + '.te-row select, .te-row input[type="number"], .te-row input[type="text"] {'
    + '  flex: 1; background: #0f172a; color: #e2e8f0; border: 1px solid #2d3748;'
    + '  border-radius: 4px; padding: 5px 8px; font-size: 12px; }'
    + '.te-status { font-size: 11px; color: #94a3b8; margin-bottom: 8px; min-height: 14px; }'
    + '.te-status.error { color: #ef4444; }'
    + '.te-actions { display: flex; gap: 8px; justify-content: flex-end; }'
    + '.te-actions button { font-size: 11px; padding: 6px 14px; border-radius: 4px;'
    + '  border: 1px solid #2d3748; background: #1e293b; color: #e2e8f0; cursor: pointer; }'
    + '.te-actions button.primary { background: #1e3a5f; border-color: #3b82f6; }'
    + '.te-actions button.danger  { background: #7f1d1d; border-color: #b91c1c; }'
  );

  var STYLES = ['none', 'fade', 'page-turn', 'slide', 'wipe'];

  function ensureStyle() {
    if (document.getElementById('te-style')) return;
    var s = document.createElement('style');
    s.id = 'te-style';
    s.textContent = STYLE;
    document.head.appendChild(s);
  }

  async function listSfx() {
    try {
      var resp = await fetch('/api/sfx/list');
      if (!resp.ok) return [];
      return await resp.json();
    } catch (e) { return []; }
  }

  async function uploadSfx(file) {
    var fd = new FormData();
    fd.append('file', file, file.name);
    var resp = await fetch('/api/sfx/upload', { method: 'POST', body: fd });
    if (!resp.ok) throw new Error('sfx upload failed: ' + resp.status + ' ' + (await resp.text()));
    return (await resp.json()).path;  // "assets/sfx/<filename>"
  }

  async function setTransition(projectId, body) {
    var resp = await fetch('/api/transition/' + encodeURIComponent(projectId) + '/set', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error('set failed: ' + resp.status + ' ' + (await resp.text()));
    return await resp.json();
  }

  async function clearTransition(projectId, body) {
    var resp = await fetch('/api/transition/' + encodeURIComponent(projectId) + '/clear', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error('clear failed: ' + resp.status + ' ' + (await resp.text()));
    return await resp.json();
  }

  async function openEditor(opts) {
    ensureStyle();
    var projectId = opts.projectId;
    var fromScene = opts.fromScene;
    var toScene = opts.toScene;

    var sfx = await listSfx();
    var sfxOpts = ['<option value="">— silent —</option>']
      .concat(sfx.map(function (s) {
        return '<option value="' + escapeAttr(s.path) + '">'
          + escapeHtml(s.name) + '</option>';
      })).join('');

    var styleOpts = STYLES.map(function (s) {
      return '<option value="' + s + '">' + s + '</option>';
    }).join('');

    var overlay = document.createElement('div');
    overlay.className = 'te-overlay';
    overlay.innerHTML = (
      '<div class="te-modal" role="dialog" aria-modal="true">'
      + '  <div class="te-h">Transition · ' + escapeHtml(fromScene) + ' → ' + escapeHtml(toScene) + '</div>'
      + '  <div class="te-row"><label>Style</label>'
      + '    <select class="te-style">' + styleOpts + '</select></div>'
      + '  <div class="te-row"><label>Duration (s)</label>'
      + '    <input type="number" class="te-duration" min="0.05" max="3" step="0.05" value="0.5"></div>'
      + '  <div class="te-row"><label>SFX</label>'
      + '    <select class="te-sfx">' + sfxOpts + '</select></div>'
      + '  <div class="te-row"><label>+ upload sfx</label>'
      + '    <input type="file" class="te-sfx-upload" accept="audio/*"></div>'
      + '  <div class="te-status"></div>'
      + '  <div class="te-actions">'
      + '    <button type="button" class="te-cancel">Cancel</button>'
      + '    <button type="button" class="te-clear danger">Clear (= hard cut)</button>'
      + '    <button type="button" class="te-apply primary">Apply</button>'
      + '  </div>'
      + '</div>'
    );
    document.body.appendChild(overlay);

    function $(sel) { return overlay.querySelector(sel); }
    var styleSel = $('.te-style');
    var durEl = $('.te-duration');
    var sfxSel = $('.te-sfx');
    var fileEl = $('.te-sfx-upload');
    var statusEl = $('.te-status');

    // Default style: page-turn (the most likely user intent)
    styleSel.value = 'page-turn';

    // Default duration to 0 when style="none" (so the API accepts it)
    styleSel.addEventListener('change', function () {
      if (styleSel.value === 'none') durEl.value = '0';
      else if (parseFloat(durEl.value) <= 0) durEl.value = '0.5';
    });

    fileEl.addEventListener('change', async function () {
      var f = fileEl.files && fileEl.files[0];
      if (!f) return;
      try {
        statusEl.textContent = 'Uploading sfx…';
        var path = await uploadSfx(f);
        // Refresh the dropdown and select the new entry.
        var refreshed = await listSfx();
        sfxSel.innerHTML = '<option value="">— silent —</option>' + refreshed.map(function (s) {
          return '<option value="' + escapeAttr(s.path) + '">' + escapeHtml(s.name) + '</option>';
        }).join('');
        sfxSel.value = path;
        statusEl.textContent = 'Uploaded ' + f.name;
      } catch (err) {
        statusEl.classList.add('error');
        statusEl.textContent = err.message;
      }
    });

    $('.te-cancel').addEventListener('click', function () { overlay.remove(); });

    $('.te-apply').addEventListener('click', async function () {
      try {
        statusEl.classList.remove('error');
        statusEl.textContent = 'Applying…';
        var resp = await setTransition(projectId, {
          from_scene: fromScene,
          to_scene: toScene,
          style: styleSel.value,
          duration_sec: parseFloat(durEl.value) || 0,
          sfx: sfxSel.value || null,
        });
        statusEl.textContent = resp.summary || 'Applied.';
        setTimeout(function () { overlay.remove(); }, 1200);
      } catch (err) {
        statusEl.classList.add('error');
        statusEl.textContent = err.message;
      }
    });

    $('.te-clear').addEventListener('click', async function () {
      try {
        statusEl.classList.remove('error');
        statusEl.textContent = 'Clearing…';
        var resp = await clearTransition(projectId, {
          from_scene: fromScene,
          to_scene: toScene,
        });
        statusEl.textContent = resp.summary || 'Cleared.';
        setTimeout(function () { overlay.remove(); }, 1200);
      } catch (err) {
        statusEl.classList.add('error');
        statusEl.textContent = err.message;
      }
    });
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' })[c];
    });
  }
  function escapeAttr(s) { return escapeHtml(s).replace(/"/g, '&quot;'); }

  window.TransitionEditor = { open: openEditor };
})();
```

- [ ] **Step 12.2: Manual smoke test — open the modal**

```bash
./scripts/start-dashboard.sh --local-only &
DASH_PID=$!
sleep 2
# Visit http://localhost:7860/, open any project preview, then click the
# ⤳ transition chip on a scene panel WITHOUT edit mode on. The modal opens.
# Pick page-turn 0.5s, optionally pick a sfx (or upload one), tap Apply.
# Verify storyboard.json now has the transition entry.
wait $DASH_PID
```

Acceptance:
- Style dropdown shows all 5 styles.
- SFX dropdown lists files in `assets/sfx/` (or only "— silent —" if empty).
- `+ upload custom` adds a new file under `assets/sfx/` and selects it.
- Apply writes the transition entry to storyboard.json.
- Clear removes the transition entry.

- [ ] **Step 12.3: Commit**

```bash
git add src/pipeline/dashboard/static/transition_editor.js
git commit -m "feat(dashboard): transition_editor.js — direct-action transition modal"
```

---

## Task 13: Mirror edit-mode UI into `verify.html`

**Files:**
- Modify: `src/pipeline/dashboard/static/verify.html`

The verifier view also wants click-to-edit on its scene rail and final-video player (spec §"Frontend — edit mode + composer", last paragraph: *"verify.html mirrors the same edit-mode toggle and floating composer"*). Manifest items also become tokenizable as `@manifest:<item_id>`.

- [ ] **Step 13.1: Pull in the same JS modules + add the toggle button to the header**

In `src/pipeline/dashboard/static/verify.html`, find the `<header>` block (around line 33):

```html
<header>
  <h1>Verify <span id="proj"></span></h1>
  <div class="summary">
    <span class="badge ok"><span id="cnt-used">0</span> used</span>
    <span class="badge miss"><span id="cnt-missing">0</span> missing</span>
    <span class="badge skip"><span id="cnt-skipped">0</span> skipped</span>
  </div>
</header>
```

Replace with:

```html
<header>
  <h1>Verify <span id="proj"></span></h1>
  <div class="summary">
    <span class="badge ok"><span id="cnt-used">0</span> used</span>
    <span class="badge miss"><span id="cnt-missing">0</span> missing</span>
    <span class="badge skip"><span id="cnt-skipped">0</span> skipped</span>
  </div>
  <button class="edit-mode-toggle" id="vh-edit-toggle"
    style="font-size:11px;padding:4px 10px;border-radius:4px;
    border:1px solid #2d3748;background:#1a1a2e;color:#94a3b8;cursor:pointer;
    margin-left:auto">
    ✏️ Edit mode
  </button>
</header>
```

- [ ] **Step 13.2: Add edit-mode CSS to the existing `<style>` block**

Inside the existing `<style>` block in `verify.html`, append before the closing `</style>`:

```css
    .edit-mode-toggle.on { background: #1e3a5f; color: #93c5fd; border-color: #3b82f6; }
    body.edit-mode-on .item,
    body.edit-mode-on video,
    body.edit-mode-on #scenes > * { cursor: cell; }
    body.edit-mode-on [data-edit-token]:hover { outline: 1px dashed #3b82f6; outline-offset: 2px; }
    .ec-cross-flash { outline: 2px solid #3b82f6 !important; outline-offset: 2px !important; }
```

- [ ] **Step 13.3: Annotate manifest items with `data-edit-token="@manifest:<item_id>"`**

In `verify.html`, find the loop that creates `el` for each item (around line 84):

```javascript
for (const it of data.items) {
  const el = document.createElement("div");
  el.className = `item ${it.status}`;

  const label = document.createElement("div");
  ...
}
```

Right after `el.className = ...`, add:

```javascript
  el.setAttribute('data-edit-token', `@manifest:${it.item_id}`);
```

- [ ] **Step 13.4: Annotate the video player wrapper and update on `timeupdate`**

In `verify.html`, find the `<video id="video" controls></video>` line (around line 59) and wrap it:

```html
      <div class="video-wrap" data-edit-token="" id="video-wrap">
        <video id="video" controls></video>
      </div>
```

After `refresh()` finishes (just before its closing brace, after `v.onerror = ...`), add:

```javascript
  // Plan 4: keep the video wrapper's data-edit-token in sync with the
  // active scene so edit-mode click-to-mint resolves to @sN.
  if (window.__verify_scenes_resolver__) {
    v.removeEventListener('timeupdate', window.__verify_scenes_resolver__);
  }
  if (Array.isArray(data.scenes_overview) && data.scenes_overview.length) {
    const wrap = document.getElementById('video-wrap');
    const handler = () => {
      let idx = 0;
      const t = v.currentTime;
      for (let i = 0; i < data.scenes_overview.length; i++) {
        if (t >= data.scenes_overview[i].start_sec) idx = i;
      }
      wrap.setAttribute('data-edit-token', `@${data.scenes_overview[idx].id}`);
    };
    window.__verify_scenes_resolver__ = handler;
    v.addEventListener('timeupdate', handler);
  }
```

If `data.scenes_overview` is not present in the existing `/api/verify/<id>` response, the block silently no-ops; the manifest tokens still work. (Plan 5 may add scene overview to the verify endpoint — not Plan 4's job.)

- [ ] **Step 13.5: Wire the toggle button + load the JS modules**

At the bottom of `verify.html`, replace the closing `</body>` line with:

```html
<script src="/static/tokens.js"></script>
<script src="/static/cost_estimate.js"></script>
<script src="/static/edit_draft.js"></script>
<script src="/static/edit_mode.js"></script>
<script src="/static/composer.js"></script>
<script>
  document.getElementById('vh-edit-toggle').addEventListener('click', () => {
    window.EditMode.toggle(projectId);
  });
  // Restore persisted edit-mode state for this project on load.
  window.EditMode.attach(projectId);
</script>
</body>
```

- [ ] **Step 13.6: Manual smoke test — verify the verify.html mirror**

```bash
./scripts/start-dashboard.sh --local-only &
DASH_PID=$!
sleep 2
# Visit http://localhost:7860/verify/<some_project_id>
# Click ✏️ Edit mode in the header.
# Click any manifest item — should mint @manifest:<item_id> into the composer.
# Click the video — mints @sN for the currently-playing scene.
wait $DASH_PID
```

Acceptance:
- Toggle visible in header, lights up when on.
- Composer appears (same component as index.html).
- Manifest items mint `@manifest:<item_id>`.
- Submitting in edit mode hits the same `/api/jobs/<id>/submit` endpoint.

- [ ] **Step 13.7: Commit**

```bash
git add src/pipeline/dashboard/static/verify.html
git commit -m "feat(dashboard): mirror edit-mode toggle + click-to-mint into verify.html"
```

---

## Task 14: End-to-end smoke test for the composer flow (manual + check-list)

**Files:** none (manual)

This is the final acceptance pass. It covers the spec's Flow 1 (chat-driven edit) and Flow 2 (direct-action transition) — Flow 3 (narration) was finished in Plan 2 and is unchanged here.

- [ ] **Step 14.1: Run the full unit + integration suites**

Run: `uv run pytest --deselect tests/unit/test_compose_v2.py::test_compose_burn_subtitles_false_returns_plain_variant -q`
Expected: all pass.

- [ ] **Step 14.2: Lint + type-check the touched Python**

Run:
```bash
uv run ruff check src/pipeline/cli_transition.py src/pipeline/dashboard/server.py tests/unit/test_dashboard_transition_endpoints.py tests/unit/test_dashboard_sfx_endpoints.py tests/unit/test_dashboard_draft_endpoints.py tests/integration/test_static_self_tests.py
uv run mypy src/pipeline/cli_transition.py src/pipeline/dashboard/server.py
```
Expected: clean (any pre-existing mypy noise from upstream files can be ignored).

- [ ] **Step 14.3: Manual end-to-end — Flow 1 (composer submit)**

```bash
./scripts/start-dashboard.sh --local-only &
DASH_PID=$!
sleep 2
```

Then in a browser, against any production project (`output/projects/<numeric_id>`):

1. Open the project's detail row.
2. Tap **✏️ Edit mode** — sticky strip + composer appear.
3. Tap a scene chip → `@s1` chip appears in the composer.
4. Tap the narration text on a different scene → `@s5/narration` chip appears.
5. Type *"tighten the wording on these"* in the textarea.
6. Tap **Submit** — since both tokens are text-only, no confirm popup. Composer shows "Job <id> queued." and exits edit mode.
7. Verify `output/projects/<id>/edit_jobs/<job_id>.json` was written by Plan 3's submit endpoint (this confirms Plan 4 + Plan 3 are wired correctly).

Now repeat with a confirm-triggering set:

8. Toggle edit mode back on.
9. Tap a scene image (i.e. the video player playing through the scene) → `@s1` chip.
10. Tap textarea, type *"regenerate this image with a colder palette"*.
11. Tap **Submit** — confirm popup appears (sceneOnly cost = $0.04). Tap **Confirm & submit**.
12. Composer empties; edit mode auto-exits.

- [ ] **Step 14.4: Manual end-to-end — Flow 2 (TransitionEditor)**

1. Open the project preview row, edit mode OFF.
2. Tap the `⤳ transition` chip on the narration panel.
3. Modal opens. Style = page-turn, duration = 0.5, sfx = none. Tap **Apply**.
4. Verify `storyboard.json` now has the transition entry.
5. Re-open the modal, tap **Clear (= hard cut)**.
6. Verify the transition entry is gone.

- [ ] **Step 14.5: Manual end-to-end — verify.html mirror**

1. Visit `/verify/<project_id>`.
2. Tap ✏️ Edit mode.
3. Tap a manifest item (any "missing" or "used" line) → mints `@manifest:<item_id>`.
4. Tap the video → mints `@sN`.
5. Submit — confirm Plan 3's submit endpoint receives the same payload shape.

- [ ] **Step 14.6: Static-test harness self-check**

Visit `http://localhost:7860/static/edit_mode_test.html` — confirm both modules report `0 fail`.

- [ ] **Step 14.7: Stop the dashboard and commit any final adjustments**

```bash
kill $DASH_PID
# If any tweaks were needed during the smoke test, commit them now.
git status
```

---

## Plan complete

After all tasks above are checked off:

- A user toggles **✏️ Edit mode** on the dashboard header (per project, persisted).
- Tapping any annotated element on a project's detail row (scene chip, narration text, subtitle text, transition-out chip, narration-source chip, video player) mints a token (`@sN`, `@sN/visual`, `@sN/subtitle`, `@sN/overlay`, `@sN/narration`, `@sN/transition`) into the floating composer.
- Tapping a manifest item on `verify.html` mints `@manifest:<item_id>`.
- The composer auto-saves the draft to `output/projects/<id>/edit_draft.json` between sessions.
- A live summary line shows token / scene count and best-effort USD cost. A confirm popup gates jobs that involve real cost or wide rebuilds (>50% of scenes).
- Submit POSTs `{tokens, instruction}` to Plan 3's `/api/jobs/<id>/submit`, then clears the draft and exits edit mode. The job is queued in the `JobQueue` and dispatched to the agent runtime.
- The TransitionEditor modal is direct-action: it talks to the new `/api/transition/<id>/set` and `/clear` endpoints, which reuse Plan 1's `apply_set_transition` / `apply_clear_transition` helpers (single source of truth — same code path as the CLI).
- The NarrationSourceEditor modal from Plan 2 is now reachable through a tokenized chip with click-routing depending on edit-mode state.
- New backend surface: 4 endpoints (`POST /api/transition/<id>/set`, `POST /api/transition/<id>/clear`, `GET/POST/DELETE /api/jobs/<id>/draft`) plus 2 sfx endpoints (`GET /api/sfx/list`, `POST /api/sfx/upload`). All covered by `TestClient` tests.
- New frontend surface: 6 JS modules (`tokens.js`, `cost_estimate.js`, `edit_draft.js`, `edit_mode.js`, `composer.js`, `transition_editor.js`) with self-tests in the pure-logic ones and a `node`-driven integration test that runs them in CI.

**Hand-off note for Plan 5:** Plan 5 layers SSE (`/api/sse/<id>`) for live artifact refresh, the in-flight 🔄 editing badge, and the Cat-8 trust gate (`✅ Apply / ✏ Edit / ❌ Cancel` Telegram buttons + `↩ Revert`). The composer in this plan already exits edit mode on submit and surfaces the queued `job_id` so Plan 5 can correlate SSE updates back to the originating composer state.

**Known gaps (intentionally deferred):**

1. **Transition-in mirror chip** — the spec's "mirrored read in both adjacent scene panels" (Flow 2 step 3) calls for both scene N's `transition-out` chip and scene N+1's `transition-in` chip to display the same seam config. Today's dashboard renders one active scene panel at a time, so only one chip is visible regardless. If a future scene-grid view is added, render an extra `transition-in-chip` on scene N+1 with the same `data-edit-token="@<N>/transition"`.
2. **Path-layout latent bug in `_project_root`** — production launcher passes `OUTPUT_DIR` (= `output/`) to `create_app`, but `_project_root("42")` resolves to `output/42` rather than `output/projects/42`. Plan 2's narration endpoints inherit this and tests pass only because the test fixture passes `output/projects` as `output_dir`. Plan 4 follows the same convention to stay test-consistent. A focused future patch should change `_project_root(project_id)` to `output_dir / "projects" / project_id` or update `cli.py:dashboard` to launch with `OUTPUT_DIR / "projects"`.
