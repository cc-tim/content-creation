from __future__ import annotations

import asyncio
import tomllib
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from pipeline.dashboard.scanner import ProjectInfo, scan_projects

_STATIC_DIR = Path(__file__).parent / "static"
_CHANNELS_TOML = Path("configs/youtube_channels.toml")
_CHANNELS_DIR = Path("configs/channels")


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
