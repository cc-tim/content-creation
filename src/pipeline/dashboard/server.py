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
from pipeline.dashboard.scanner import ProjectInfo, scan_projects
from pipeline.explainer import load_explainer
from pipeline.notify.telegram import LongPollListener, TelegramNotifier
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
        prompt_template = (Path(__file__).parent / "agent_prompt.md").read_text(encoding="utf-8")
        runner = ClaudeAgentRunner(prompt_template=prompt_template, notifier=notifier)
        queue = JobQueue(
            projects_root=projects_root,
            runner=runner,
            notifier=notifier,
        )
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

    app = FastAPI(title="Content Dashboard", lifespan=lifespan)

    @app.get("/api/projects")
    def get_projects() -> list[dict[str, object]]:
        return [_to_dict(p) for p in scan_projects(output_root)]

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
