from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
WORKED = REPO / "assets" / "toy3d" / "scenes" / "001-beat2-break-in.yaml"
DESIGN_VIEW = REPO / "tests" / "fixtures" / "toy3d" / "sheet" / "guo_design_view.yaml"


@pytest.fixture(autouse=True)
def _private_renderer_record(tmp_path_factory, monkeypatch):
    """No test reads or rewrites this machine's real renderer record (the cache key's renderer)."""
    monkeypatch.setenv("TOY3D_CACHE_DIR", str(tmp_path_factory.mktemp("toy3d-cache")))


@pytest.fixture(scope="session")
def bank():
    from toy3d.bank import load_bank

    return load_bank()


@pytest.fixture(scope="session")
def worked(bank):
    from toon.scene import load_scene, read_scene

    return load_scene(read_scene(str(WORKED)), bank.catalog)


@pytest.fixture(scope="session")
def design(bank):
    from toon.scene import load_scene, read_scene

    return load_scene(read_scene(str(DESIGN_VIEW)), bank.catalog)
