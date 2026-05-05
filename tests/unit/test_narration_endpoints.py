from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from pipeline.dashboard.server import create_app
from pipeline.storyboard import Scene, Storyboard


@pytest.fixture
def project_tree(tmp_path: Path) -> Path:
    out_root = tmp_path / "output"
    proj = out_root / "projects" / "42"
    proj.mkdir(parents=True)
    sb = Storyboard(scenes=[
        Scene(id="s1", section="content", narration="hello", narration_est_sec=1.0),
        Scene(id="s2", section="content", narration="world", narration_est_sec=1.0),
    ])
    sb.save(proj / "storyboard.json")
    (proj / "context.json").write_text(
        json.dumps({"project_id": 42, "source_url": "x", "locale": "zh-TW",
                    "work_dir": str(proj)}),
        encoding="utf-8",
    )
    return out_root


@pytest.fixture
def client(project_tree: Path) -> TestClient:
    app = create_app(output_dir=project_tree / "projects")
    return TestClient(app)


def test_set_source_endpoint_writes_storyboard(client: TestClient, project_tree: Path):
    resp = client.post(
        "/api/narration/42/set-source",
        json={"scene": "s1", "engine": "edge", "voice": "zh-tw-default-f"},
    )
    assert resp.status_code == 200, resp.text
    sb = Storyboard.load(project_tree / "projects" / "42" / "storyboard.json")
    s1 = sb.get_scene("s1")
    assert s1 is not None and s1.narration_source is not None
    assert s1.narration_source.engine == "edge"


def test_set_source_endpoint_rejects_unknown_engine(client: TestClient):
    resp = client.post(
        "/api/narration/42/set-source",
        json={"scene": "s1", "engine": "elevenlabs", "voice": "x"},
    )
    assert resp.status_code == 400


def test_set_source_endpoint_rejects_unknown_scene(client: TestClient):
    resp = client.post(
        "/api/narration/42/set-source",
        json={"scene": "s99", "engine": "edge", "voice": "zh-tw-default-f"},
    )
    assert resp.status_code == 404


def test_set_source_endpoint_404_on_unknown_project(client: TestClient):
    resp = client.post(
        "/api/narration/9999/set-source",
        json={"scene": "s1", "engine": "edge", "voice": "any"},
    )
    assert resp.status_code == 404


def test_upload_endpoint_normalizes_and_saves(
    client: TestClient, project_tree: Path, tmp_path: Path,
):
    # Build a tiny webm input to upload.
    import subprocess
    src = tmp_path / "rec.webm"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
         "-c:a", "libopus", str(src)],
        check=True,
    )
    with src.open("rb") as fh:
        resp = client.post(
            "/api/narration/42/upload",
            params={"scene": "s2"},
            files={"file": ("rec.webm", fh, "audio/webm")},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    expected_rel = "narration_overrides/s2.wav"
    assert body["path"] == expected_rel
    saved = project_tree / "projects" / "42" / expected_rel
    assert saved.exists() and saved.stat().st_size > 0


def test_upload_endpoint_rejects_scene_id_with_path_traversal(client: TestClient):
    resp = client.post(
        "/api/narration/42/upload",
        params={"scene": "../../etc/passwd"},
        files={"file": ("rec.webm", b"x", "audio/webm")},
    )
    assert resp.status_code == 400


def test_upload_endpoint_rejects_unknown_scene(client: TestClient):
    resp = client.post(
        "/api/narration/42/upload",
        params={"scene": "s99"},
        files={"file": ("rec.webm", b"x", "audio/webm")},
    )
    assert resp.status_code == 404


def test_transcribe_endpoint_returns_transcript(
    client: TestClient, project_tree: Path, tmp_path: Path,
):
    # Place a recording inside the project tree.
    overrides = project_tree / "projects" / "42" / "narration_overrides"
    overrides.mkdir(parents=True)
    (overrides / "s1.wav").write_bytes(b"RIFF....WAVEfmt ")

    with patch("pipeline.dashboard.server.transcribe_audio", return_value="你好"):
        resp = client.post(
            "/api/narration/42/transcribe",
            json={"scene": "s1", "file": "narration_overrides/s1.wav", "language": "zh"},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["transcript"] == "你好"


def test_transcribe_endpoint_rejects_path_traversal(client: TestClient):
    resp = client.post(
        "/api/narration/42/transcribe",
        json={"scene": "s1", "file": "../../etc/passwd", "language": "zh"},
    )
    assert resp.status_code == 400


def test_transcribe_endpoint_rejects_missing_file(client: TestClient):
    resp = client.post(
        "/api/narration/42/transcribe",
        json={"scene": "s1", "file": "narration_overrides/missing.wav", "language": "zh"},
    )
    assert resp.status_code == 404
