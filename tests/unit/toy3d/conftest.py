import pytest


@pytest.fixture(autouse=True)
def _private_renderer_record(tmp_path, monkeypatch):
    """No test reads or rewrites this machine's real renderer record (the cache key's renderer)."""
    monkeypatch.setenv("TOY3D_CACHE_DIR", str(tmp_path / "toy3d-cache"))
