from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pipeline.dashboard.scanner import ProjectInfo, scan_projects

_STATIC_DIR = Path(__file__).parent / "static"


def create_app(output_dir: Path) -> FastAPI:
    output_dir.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="Content Dashboard")

    @app.get("/api/projects")
    def get_projects() -> list[dict[str, object]]:
        return [_to_dict(p) for p in scan_projects(output_dir)]

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

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
        "session_logs": p.session_logs[-3:],  # latest 3 only
    }
