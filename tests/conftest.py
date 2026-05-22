from pathlib import Path

import pytest

from pipeline.stages.base import PipelineContext


@pytest.fixture
def sample_context(tmp_path: Path) -> PipelineContext:
    work_dir = tmp_path / "test_project"
    work_dir.mkdir()
    return PipelineContext(
        project_id=1,
        source_url="https://youtube.com/watch?v=test123",
        locale="zh-TW",
        work_dir=work_dir,
    )


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run integration tests (require FFmpeg, dashboard, or live services)",
    )
    parser.addoption(
        "--network",
        action="store_true",
        default=False,
        help="Run network tests (require live API keys)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    run_integration = config.getoption("--integration", default=False)
    run_network = config.getoption("--network", default=False)

    for item in items:
        if item.get_closest_marker("integration") and not run_integration:
            item.add_marker(
                pytest.mark.skip(reason="pass --integration to run")
            )
        if item.get_closest_marker("network") and not run_network:
            item.add_marker(
                pytest.mark.skip(reason="pass --network to run")
            )
