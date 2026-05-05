from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pipeline.dashboard.server import create_app


@pytest.fixture
def client_with_sfx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    sfx_dir = tmp_path / "assets" / "sfx"
    sfx_dir.mkdir(parents=True)
    (sfx_dir / "page_flip.mp3").write_bytes(b"id3" + b"\x00" * 32)
    (sfx_dir / "whoosh.mp3").write_bytes(b"id3" + b"\x00" * 32)
    (sfx_dir / ".gitkeep").write_text("")
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
