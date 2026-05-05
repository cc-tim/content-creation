from __future__ import annotations

import asyncio
import contextlib
import json
import tomllib
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import typer
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pipeline.cli_transition import apply_clear_transition, apply_set_transition
from pipeline.config import PipelineConfig
from pipeline.dashboard.agent_runner import ClaudeAgentRunner
from pipeline.dashboard.job_queue import EditJob, JobQueue
from pipeline.dashboard.mutation_runtime import (
    MutationCoordinator,
    MutationProposal,
    MutationProposed,
    MutationResult,
    apply_mutation,
)
from pipeline.dashboard.scanner import ProjectInfo, scan_projects
from pipeline.dashboard.sse_emitter import FileWatcher, SSEEmitter, SSEEvent
from pipeline.dashboard.trust_gate import classify_tier
from pipeline.explainer import load_explainer
from pipeline.notify.telegram import LongPollListener, TelegramNotifier
from pipeline.session_log import recent_mutations
from pipeline.storyboard import NarrationSource, Storyboard
from pipeline.transcribe import transcribe_audio
from pipeline.utils.audio import normalize_to_wav
from pipeline.verifier import (
    load_verifier_state,
    run_auto_checks,
    save_verifier_state,
)

_STATIC_DIR = Path(__file__).parent / "static"
_CHANNELS_TOML = Path("configs/youtube_channels.toml")
_CHANNELS_DIR = Path("configs/channels")
_SFX_DIR = Path("assets/sfx")
_ALLOWED_SFX_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a"}
_MAX_DRAFT_BYTES = 64 * 1024


class _SkipBody(BaseModel):
    item_id: str
    skipped: bool


class _ManualCheckBody(BaseModel):
    item_id: str
    checked: bool


class _SetSourceBody(BaseModel):
    scene: str
    engine: str
    voice: str | None = None
    file: str | None = None


class _TranscribeBody(BaseModel):
    scene: str
    file: str
    language: str = "zh"


class _TransitionSetBody(BaseModel):
    from_scene: str
    to_scene: str
    style: str
    duration_sec: float
    sfx: str | None = None


class _TransitionClearBody(BaseModel):
    from_scene: str
    to_scene: str


class _DraftBody(BaseModel):
    tokens: list[str]
    instruction: str


class _JobSubmitBody(BaseModel):
    tokens: list[str] = []
    instruction: str


_VALID_NARRATION_ENGINES = {"edge", "fish_audio", "prerecorded"}


def create_app(output_dir: Path, dev_mode: bool = False) -> FastAPI:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_root = output_dir.parent if output_dir.name == "projects" else output_dir
    projects_root = output_dir if output_dir.name == "projects" else output_dir / "projects"
    projects_root.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        notifier = TelegramNotifier.from_env()
        app.state.notifier = notifier
        app.state.telegram_notifier = notifier
        sse_emitter = SSEEmitter()
        app.state.sse_emitter = sse_emitter
        watcher = FileWatcher(sse_emitter, projects_root=projects_root)
        await watcher.start()
        app.state.file_watcher = watcher
        if not hasattr(app.state, "mutation_coordinator"):
            app.state.mutation_coordinator = MutationCoordinator()
        prompt_template = (Path(__file__).parent / "agent_prompt.md").read_text(encoding="utf-8")
        runner = ClaudeAgentRunner(prompt_template=prompt_template, notifier=notifier)
        queue = JobQueue(
            projects_root=projects_root,
            runner=runner,
            notifier=notifier,
            sse_emitter=sse_emitter,
        )
        queue.set_coordinator(app.state.mutation_coordinator)
        queue.reload_on_startup()
        await queue.start()
        app.state.job_queue = queue

        listener_task: asyncio.Task[None] | None = None
        if notifier is not None:
            listener = LongPollListener(notifier, on_callback_query=queue.handle_callback_query)
            app.state.telegram_listener = listener
            listener_task = asyncio.create_task(listener.run(), name="telegram-long-poll")

        try:
            yield
        finally:
            if listener_task is not None:
                app.state.telegram_listener.stop()
                listener_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await listener_task
            await queue.shutdown()
            await watcher.stop()

    app = FastAPI(title="Content Dashboard", lifespan=lifespan)

    @app.get("/api/projects")
    def get_projects() -> list[dict[str, object]]:
        return [_to_dict(p) for p in scan_projects(output_root)]

    @app.get("/api/projects/{project_id}/recent-mutations")
    def get_recent_mutations(project_id: str) -> JSONResponse:
        proj = _project_root(project_id)
        return JSONResponse([
            {
                "session_id": entry.session_id,
                "timestamp": entry.timestamp,
                "command": entry.command,
                "outcome": entry.outcome,
                "stages": entry.stages,
                "summary": entry.summary,
                "error": entry.error,
                "mutation_id": entry.mutation_id,
                "revert_payload": entry.revert_payload,
            }
            for entry in recent_mutations(proj, n=10)
        ])

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

    @app.get("/channels")
    def channels_page() -> FileResponse:
        return FileResponse(_STATIC_DIR / "channels.html")

    @app.get("/api/channels")
    def get_channels() -> JSONResponse:
        profiles: list[dict[str, Any]] = []
        if _CHANNELS_TOML.exists():
            data = tomllib.loads(_CHANNELS_TOML.read_text(encoding="utf-8"))
            for name, raw in (data.get("profiles") or {}).items():
                outro_path = _CHANNELS_DIR / name / "outro.mp4"
                profile_png = _CHANNELS_DIR / name / "profile.png"
                profiles.append({
                    "name": name,
                    "display_name": raw.get("display_name", ""),
                    "tagline": raw.get("tagline", ""),
                    "locale": raw.get("locale", ""),
                    "niche": raw.get("niche", ""),
                    "channel_id": raw.get("channel_id", ""),
                    "outro_enabled": bool(raw.get("outro_enabled", False)),
                    "outro_built": outro_path.exists(),
                    "outro_url": f"/configs-static/{name}/outro.mp4"
                    if outro_path.exists() else None,
                    "profile_png_url": f"/configs-static/{name}/profile.png"
                    if profile_png.exists() else None,
                    "outro_size_kb": outro_path.stat().st_size // 1024
                    if outro_path.exists() else None,
                })
        return JSONResponse(profiles)

    if _CHANNELS_DIR.exists():
        app.mount(
            "/configs-static",
            StaticFiles(directory=str(_CHANNELS_DIR)),
            name="configs",
        )

    def _project_root(project_id: str) -> Path:
        proj = projects_root / project_id
        if not proj.exists():
            raise HTTPException(status_code=404, detail=f"project {project_id} not found")
        return proj

    def _resolve_within_project(project_root: Path, rel_path: str) -> Path:
        """Resolve rel_path inside project_root. Raises HTTPException(400) on escape."""
        candidate = (project_root / rel_path).resolve()
        if not str(candidate).startswith(str(project_root.resolve())):
            raise HTTPException(
                status_code=400,
                detail=f"path {rel_path!r} resolves outside project tree",
            )
        return candidate

    def _explainer_path(proj: Path) -> Path:
        candidate = proj / "source" / "explainer.md"
        if not candidate.exists():
            raise HTTPException(
                status_code=409,
                detail="this project has no explainer.md (not produced from a wiki explainer)",
            )
        return candidate

    @app.get("/api/verify/{project_id}")
    def get_verify(project_id: str) -> JSONResponse:
        proj = _project_root(project_id)
        explainer = load_explainer(_explainer_path(proj))
        sb_path = proj / "storyboard.json"
        if not sb_path.exists():
            raise HTTPException(status_code=409, detail="storyboard.json not yet generated")
        storyboard = json.loads(sb_path.read_text(encoding="utf-8"))
        scenes_overview = [
            {
                "id": scene.get("id"),
                "section": scene.get("section"),
                "start_sec": scene.get("start_sec", 0),
                "subtitle": scene.get("subtitle", ""),
            }
            for scene in storyboard.get("scenes", [])
            if scene.get("id")
        ]
        state = load_verifier_state(proj / "verifier_state.json")
        result = run_auto_checks(explainer.manifest, storyboard, state=state)
        return JSONResponse({
            "project_id": project_id,
            "manifest": explainer.manifest.model_dump(),
            "items": [it.model_dump() for it in result.items],
            "scenes_overview": scenes_overview,
            "used_count": result.used_count,
            "missing_count": result.missing_count,
            "skipped_count": result.skipped_count,
        })

    @app.post("/api/verify/{project_id}/skip")
    def post_skip(project_id: str, body: _SkipBody) -> JSONResponse:
        proj = _project_root(project_id)
        state_path = proj / "verifier_state.json"
        state = load_verifier_state(state_path)
        if body.skipped:
            state.skipped.add(body.item_id)
        else:
            state.skipped.discard(body.item_id)
        save_verifier_state(
            state_path,
            skipped=state.skipped,
            manual_checked=state.manual_checked,
        )
        return JSONResponse({"ok": True})

    @app.post("/api/verify/{project_id}/manual-check")
    def post_manual_check(project_id: str, body: _ManualCheckBody) -> JSONResponse:
        proj = _project_root(project_id)
        state_path = proj / "verifier_state.json"
        state = load_verifier_state(state_path)
        if body.checked:
            state.manual_checked.add(body.item_id)
        else:
            state.manual_checked.discard(body.item_id)
        save_verifier_state(
            state_path,
            skipped=state.skipped,
            manual_checked=state.manual_checked,
        )
        return JSONResponse({"ok": True})

    @app.get("/verify/{project_id}")
    def verify_page(project_id: str) -> FileResponse:
        return FileResponse(_STATIC_DIR / "verify.html")

    if dev_mode:

        def _static_mtime() -> float:
            return max(
                (p.stat().st_mtime for p in _STATIC_DIR.rglob("*") if p.is_file()),
                default=0.0,
            )

        @app.get("/_hmr")
        async def hmr_sse() -> StreamingResponse:
            async def stream() -> AsyncIterator[str]:
                last = _static_mtime()
                while True:
                    await asyncio.sleep(0.5)
                    current = _static_mtime()
                    if current != last:
                        last = current
                        yield "data: reload\n\n"

            return StreamingResponse(stream(), media_type="text/event-stream")

    @app.post("/api/narration/{project_id}/set-source")
    def post_set_source(project_id: str, body: _SetSourceBody) -> JSONResponse:
        proj = _project_root(project_id)
        sb_path = proj / "storyboard.json"
        if not sb_path.exists():
            raise HTTPException(status_code=409, detail="storyboard.json not yet generated")

        if body.engine not in _VALID_NARRATION_ENGINES:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown narration engine {body.engine!r}",
            )
        if body.engine in ("edge", "fish_audio") and not body.voice:
            raise HTTPException(
                status_code=400,
                detail=f"engine={body.engine!r} requires 'voice'",
            )
        if body.engine == "prerecorded":
            if not body.file:
                raise HTTPException(
                    status_code=400,
                    detail="engine='prerecorded' requires 'file'",
                )
            resolved = _resolve_within_project(proj, body.file)
            if not resolved.exists():
                raise HTTPException(status_code=404, detail=f"file not found: {body.file}")

        sb = Storyboard.load(sb_path)
        target = sb.get_scene(body.scene)
        if target is None:
            raise HTTPException(status_code=404, detail=f"scene {body.scene!r} not found")
        target.narration_source = NarrationSource(
            engine=body.engine, voice=body.voice, file=body.file,
        )
        sb.save(sb_path)
        return JSONResponse({
            "ok": True,
            "scene": body.scene,
            "narration_source": target.narration_source.to_dict(),
        })

    @app.post("/api/narration/{project_id}/upload")
    async def post_upload(
        project_id: str,
        scene: str,
        file: UploadFile = File(...),  # noqa: B008
    ) -> JSONResponse:
        proj = _project_root(project_id)
        sb_path = proj / "storyboard.json"
        if not sb_path.exists():
            raise HTTPException(status_code=409, detail="storyboard.json not yet generated")

        # Defensive: scene id must look like a storyboard id, no path separators.
        if "/" in scene or "\\" in scene or ".." in scene or scene.startswith("."):
            raise HTTPException(status_code=400, detail=f"invalid scene id {scene!r}")

        sb = Storyboard.load(sb_path)
        if sb.get_scene(scene) is None:
            raise HTTPException(status_code=404, detail=f"scene {scene!r} not found")

        overrides_dir = proj / "narration_overrides"
        overrides_dir.mkdir(parents=True, exist_ok=True)
        tmp_upload = overrides_dir / f".{scene}.upload"
        try:
            with tmp_upload.open("wb") as out:
                while chunk := await file.read(1024 * 64):
                    out.write(chunk)
            dst = overrides_dir / f"{scene}.wav"
            normalize_to_wav(tmp_upload, dst)
        finally:
            tmp_upload.unlink(missing_ok=True)

        rel = f"narration_overrides/{scene}.wav"
        return JSONResponse({"ok": True, "path": rel})

    @app.post("/api/narration/{project_id}/transcribe")
    def post_transcribe(project_id: str, body: _TranscribeBody) -> JSONResponse:
        proj = _project_root(project_id)
        resolved = _resolve_within_project(proj, body.file)
        if not resolved.exists():
            raise HTTPException(status_code=404, detail=f"file not found: {body.file}")
        api_key = PipelineConfig().OPENAI_API_KEY
        try:
            transcript = transcribe_audio(resolved, language=body.language, api_key=api_key)
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return JSONResponse({"ok": True, "transcript": transcript})

    @app.post("/api/transition/{project_id}/set")
    def post_transition_set(project_id: str, body: _TransitionSetBody) -> JSONResponse:
        _project_root(project_id)
        try:
            project_id_int = int(project_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"project_id {project_id!r} is not numeric; "
                    "transition CLI requires int ids"
                ),
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
            raise HTTPException(
                status_code=409,
                detail=(
                    f"storyboard.json missing for project {project_id}; "
                    "run `pipeline produce` past the storyboard stage first"
                ),
            ) from exc
        return JSONResponse({"ok": True, "summary": summary})

    @app.post("/api/transition/{project_id}/clear")
    def post_transition_clear(project_id: str, body: _TransitionClearBody) -> JSONResponse:
        _project_root(project_id)
        try:
            project_id_int = int(project_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"project_id {project_id!r} is not numeric; "
                    "transition CLI requires int ids"
                ),
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

    @app.get("/api/sfx/list")
    def get_sfx_list() -> JSONResponse:
        if not _SFX_DIR.exists():
            return JSONResponse([])
        entries: list[dict[str, object]] = []
        for path in sorted(_SFX_DIR.iterdir()):
            if not path.is_file():
                continue
            if path.name.startswith("."):
                continue
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
        raw = file.filename or ""
        if "/" in raw or "\\" in raw or ".." in raw or raw.startswith(".") or not raw:
            raise HTTPException(status_code=400, detail=f"invalid filename {raw!r}")
        suffix = Path(raw).suffix.lower()
        if suffix not in _ALLOWED_SFX_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"unsupported extension {suffix!r}; "
                    f"allowed: {sorted(_ALLOWED_SFX_EXTENSIONS)}"
                ),
            )
        _SFX_DIR.mkdir(parents=True, exist_ok=True)
        dst = _SFX_DIR / raw
        with dst.open("wb") as out:
            while chunk := await file.read(1024 * 64):
                out.write(chunk)
        return JSONResponse({"ok": True, "path": f"assets/sfx/{raw}"})

    @app.get("/api/jobs/{project_id}/draft")
    def get_draft(project_id: str) -> JSONResponse:
        proj = _project_root(project_id)
        path = proj / "edit_draft.json"
        if not path.exists():
            return JSONResponse({"tokens": [], "instruction": ""})
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return JSONResponse({"tokens": [], "instruction": ""})
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

    if _SFX_DIR.exists():
        app.mount("/sfx", StaticFiles(directory=str(_SFX_DIR)), name="sfx")

    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
    app.mount("/output", StaticFiles(directory=str(output_root)), name="output")
    register_job_endpoints(app, output_dir=output_root)
    register_mutation_endpoints(app, output_dir=output_root)
    register_sse_endpoint(app)

    return app


def register_job_endpoints(app: FastAPI, *, output_dir: Path) -> None:
    """Register job submit/cancel endpoints backed by app.state.job_queue."""

    def _project_root(project_id: str) -> Path:
        proj = output_dir / "projects" / project_id
        if not proj.exists():
            raise HTTPException(status_code=404, detail=f"project {project_id} not found")
        return proj

    @app.post("/api/jobs/{project_id}/submit")
    async def post_submit(project_id: str, body: _JobSubmitBody) -> JSONResponse:
        _project_root(project_id)
        if not body.instruction.strip():
            raise HTTPException(status_code=400, detail="instruction must not be empty")
        queue: JobQueue = app.state.job_queue
        job = EditJob(
            job_id=uuid.uuid4().hex[:12],
            project_id=project_id,
            tokens=list(body.tokens),
            instruction=body.instruction,
        )
        await queue.submit(job)
        return JSONResponse({"ok": True, "job_id": job.job_id, "status": job.status})

    @app.post("/api/jobs/{project_id}/{job_id}/cancel")
    async def post_cancel(project_id: str, job_id: str) -> JSONResponse:
        queue: JobQueue = app.state.job_queue
        cancelled = await queue.cancel(project_id, job_id)
        return JSONResponse({"ok": True, "cancelled": cancelled})

    @app.post("/api/jobs/{project_id}/{mutation_id}/revert")
    async def post_revert(project_id: str, mutation_id: str) -> JSONResponse:
        _project_root(project_id)
        queue: JobQueue = app.state.job_queue
        queued = await queue.enqueue_revert(project_id, mutation_id)
        if not queued:
            raise HTTPException(
                status_code=404,
                detail=f"mutation {mutation_id!r} not found or not revertable",
            )
        return JSONResponse({"ok": True, "queued": True, "mutation_id": mutation_id})


def register_sse_endpoint(app: FastAPI) -> None:
    """Register project-scoped Server-Sent Events stream."""

    @app.get("/api/sse/{project_id}")
    async def get_sse(project_id: str, keepalive_sec: float = 15.0) -> StreamingResponse:
        emitter: SSEEmitter = app.state.sse_emitter
        sub = emitter.subscribe(project_id)

        async def stream() -> AsyncIterator[str]:
            try:
                yield ": connected\n\n"
                while True:
                    try:
                        event = await asyncio.wait_for(sub.__anext__(), timeout=keepalive_sec)
                    except TimeoutError:
                        event = SSEEvent(kind="ping", payload={})
                    except StopAsyncIteration:
                        return
                    yield event.to_sse_line()
            finally:
                emitter.unsubscribe(sub)

        return StreamingResponse(stream(), media_type="text/event-stream")


def register_mutation_endpoints(app: FastAPI, *, output_dir: Path) -> None:
    """Register mutation propose/await endpoints backed by the dashboard trust gate."""

    def _project_root_from_job(job_id: str) -> Path:
        projects_dir = output_dir / "projects"
        if not projects_dir.exists():
            raise HTTPException(status_code=404, detail="projects directory not found")
        for project_dir in projects_dir.iterdir():
            if not project_dir.is_dir():
                continue
            sidecar = project_dir / "edit_jobs" / f"{job_id}.json"
            if sidecar.exists():
                return project_dir
        raise HTTPException(status_code=404, detail=f"job {job_id} not found")

    def _coordinator() -> MutationCoordinator:
        coord = getattr(app.state, "mutation_coordinator", None)
        if coord is None:
            coord = MutationCoordinator()
            app.state.mutation_coordinator = coord
        return coord

    @app.post("/api/mutations/{job_id}/propose")
    async def post_propose(job_id: str, proposal: MutationProposal) -> JSONResponse:
        if proposal.job_id != job_id:
            raise HTTPException(status_code=400, detail="job_id in path and body must match")

        project_root = _project_root_from_job(job_id)
        storyboard_path = project_root / "storyboard.json"
        if not storyboard_path.exists():
            raise HTTPException(status_code=409, detail="storyboard.json missing")

        storyboard = Storyboard.load(storyboard_path)
        tier = classify_tier(proposal.verb, proposal.args, storyboard)
        if tier == "auto_apply":
            result = apply_mutation(proposal, project_root=project_root)
            await _post_mutation_result(app, result=result, proposal=proposal, project_root=project_root)
            return JSONResponse(result.model_dump())

        coord = _coordinator()
        mutation_id = coord.register(proposal=proposal, project_root=project_root)
        await _post_mutation_proposal(
            app,
            mutation_id=mutation_id,
            proposal=proposal,
            project_root=project_root,
        )
        proposed = MutationProposed(
            mutation_id=mutation_id,
            proposal_message=f"proposal {mutation_id} awaiting user decision",
        )
        return JSONResponse(proposed.model_dump())

    @app.get("/api/mutations/{mutation_id}/await")
    async def get_await(mutation_id: str, timeout: float = 25.0) -> JSONResponse:
        coord = _coordinator()
        future = coord.future_for(mutation_id)
        if future is None:
            raise HTTPException(status_code=404, detail=f"mutation {mutation_id} not found")

        try:
            decision, pending = await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
        except TimeoutError:
            return JSONResponse({"status": "pending", "mutation_id": mutation_id}, status_code=504)

        if decision == "cancel":
            coord.pop(mutation_id)
            result = MutationResult(
                status="cancelled",
                mutation_id=mutation_id,
                message="mutation cancelled",
            )
            await _post_mutation_result(
                app,
                result=result,
                proposal=pending.proposal,
                project_root=pending.project_root,
            )
            return JSONResponse(result.model_dump())

        if decision == "edit":
            coord.pop(mutation_id)
            result = MutationResult(
                status="cancelled",
                mutation_id=mutation_id,
                message="mutation edit requested",
            )
            await _post_mutation_result(
                app,
                result=result,
                proposal=pending.proposal,
                project_root=pending.project_root,
            )
            return JSONResponse(result.model_dump())

        result = apply_mutation(pending.proposal, project_root=pending.project_root)
        coord.pop(mutation_id)
        await _post_mutation_result(
            app,
            result=result,
            proposal=pending.proposal,
            project_root=pending.project_root,
        )
        return JSONResponse(result.model_dump())


async def _post_mutation_proposal(
    app: FastAPI,
    *,
    mutation_id: str,
    proposal: MutationProposal,
    project_root: Path,
) -> None:
    notifier = getattr(app.state, "notifier", None)
    if notifier is None:
        return
    text = (
        f"[{project_root.name}] mutation proposal {mutation_id}\n"
        f"verb: {proposal.verb}\n"
        f"args: {json.dumps(proposal.args, ensure_ascii=False, sort_keys=True)}"
    )
    reply_markup = {
        "inline_keyboard": [[
            {"text": "Apply", "callback_data": f"apply:{project_root.name}:{mutation_id}"},
            {
                "text": "Edit",
                "callback_data": f"edit_proposal:{project_root.name}:{mutation_id}:{proposal.job_id}",
            },
            {"text": "Cancel", "callback_data": f"cancel_proposal:{project_root.name}:{mutation_id}"},
        ]]
    }
    await asyncio.to_thread(
        notifier.send_message,
        text,
        parse_mode="",
        reply_markup=reply_markup,
    )


async def _post_mutation_result(
    app: FastAPI,
    *,
    result: MutationResult,
    proposal: MutationProposal,
    project_root: Path,
) -> None:
    notifier = getattr(app.state, "telegram_notifier", None)
    if notifier is None:
        return
    if result.status != "applied":
        text = (
            f"[{project_root.name}] mutation {result.status}\n"
            f"verb: {proposal.verb}\n"
            f"message: {result.message}"
        )
        await asyncio.to_thread(notifier.send_message, text, parse_mode="")
        return

    from pipeline.dashboard.preview import build_preview

    revert_payload = _session_revert_payload(project_root, result.mutation_id)
    old_text = None
    if isinstance(revert_payload, dict):
        args = revert_payload.get("args")
        if isinstance(args, dict) and "text" in args:
            old_text = str(args["text"])

    preview = build_preview(
        verb=proposal.verb,
        args=proposal.args,
        project_root=project_root,
        old_text=old_text,
    )
    keyboard = None
    if result.mutation_id and revert_payload is not None:
        keyboard = {
            "inline_keyboard": [[
                {
                    "text": "Revert",
                    "callback_data": f"revert:{project_root.name}:{result.mutation_id}",
                }
            ]]
        }

    caption = f"[{project_root.name}] mutation applied\n{result.message}"
    if preview.kind == "photo" and preview.path is not None and hasattr(notifier, "send_photo"):
        await asyncio.to_thread(
            notifier.send_photo,
            preview.path,
            caption=preview.caption or caption,
            reply_markup=keyboard,
        )
        return
    if preview.kind == "video" and preview.path is not None and hasattr(notifier, "send_video"):
        await asyncio.to_thread(
            notifier.send_video,
            preview.path,
            caption=preview.caption or caption,
            reply_markup=keyboard,
        )
        return

    text = (
        f"[{project_root.name}] mutation applied\n"
        f"verb: {proposal.verb}\n"
        f"message: {result.message}\n\n"
        f"{preview.body}"
    )
    await asyncio.to_thread(notifier.send_message, text, parse_mode="", reply_markup=keyboard)


def _session_revert_payload(project_root: Path, mutation_id: str | None) -> dict[str, Any] | None:
    if mutation_id is None:
        return None
    sessions_path = project_root / "sessions.json"
    if not sessions_path.exists():
        return None
    try:
        rows = json.loads(sessions_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    for row in reversed(rows):
        if row.get("mutation_id") == mutation_id:
            payload = row.get("revert_payload")
            return payload if isinstance(payload, dict) else None
    return None


def _to_dict(p: ProjectInfo) -> dict[str, object]:
    return {
        "project_id": p.project_id,
        "status": p.status,
        "title": p.title,
        "locale": p.locale,
        "niche": p.niche,
        "source_url": p.source_url,
        "youtube_video_id": p.youtube_video_id,
        "published_at": p.published_at,
        "has_video": p.has_video,
        "video_variants": p.video_variants,
        "tags": p.tags,
        "final_video_url_path": p.final_video_url_path,
        "session_logs": p.session_logs[-20:],  # latest 20
        "scenes": p.scenes,
    }
