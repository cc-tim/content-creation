from __future__ import annotations

import asyncio
import tomllib
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pipeline.config import PipelineConfig
from pipeline.dashboard.scanner import ProjectInfo, scan_projects
from pipeline.explainer import load_explainer
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


_VALID_NARRATION_ENGINES = {"edge", "fish_audio", "prerecorded"}


def create_app(output_dir: Path, dev_mode: bool = False) -> FastAPI:
    output_dir.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="Content Dashboard")

    @app.get("/api/projects")
    def get_projects() -> list[dict[str, object]]:
        return [_to_dict(p) for p in scan_projects(output_dir)]

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

    @app.get("/channels")
    def channels_page() -> FileResponse:
        return FileResponse(_STATIC_DIR / "channels.html")

    @app.get("/api/channels")
    def get_channels() -> JSONResponse:
        profiles: list[dict] = []
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
        proj = output_dir / project_id
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
        import json as _json
        storyboard = _json.loads(sb_path.read_text(encoding="utf-8"))
        state = load_verifier_state(proj / "verifier_state.json")
        result = run_auto_checks(explainer.manifest, storyboard, state=state)
        return JSONResponse({
            "project_id": project_id,
            "manifest": explainer.manifest.model_dump(),
            "items": [it.model_dump() for it in result.items],
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
            async def stream():
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

    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
    app.mount("/output", StaticFiles(directory=str(output_dir)), name="output")

    return app


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
