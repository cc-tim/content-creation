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
