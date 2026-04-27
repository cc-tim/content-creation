# tests/unit/test_voice_variant.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.stages.base import PipelineContext


def _base_ctx(work_dir: Path) -> PipelineContext:
    return PipelineContext(
        project_id=9000,
        source_url="https://youtube.com/watch?v=abc",
        locale="zh-TW",
        work_dir=work_dir,
    )


def test_parent_project_id_defaults_none(tmp_path):
    ctx = _base_ctx(tmp_path)
    assert ctx.parent_project_id is None
    assert ctx.variant_label is None


def test_variant_fields_round_trip(tmp_path):
    ctx = _base_ctx(tmp_path)
    ctx.parent_project_id = 1776997800
    ctx.variant_label = "tim-zhtw-fish"
    ctx.save()

    loaded = PipelineContext.load(tmp_path / "context.json")
    assert loaded.parent_project_id == 1776997800
    assert loaded.variant_label == "tim-zhtw-fish"


def test_from_dict_ignores_missing_variant_fields(tmp_path):
    """Old context.json without new fields loads without error."""
    ctx = _base_ctx(tmp_path)
    d = ctx.to_dict()
    d.pop("parent_project_id", None)
    d.pop("variant_label", None)
    loaded = PipelineContext.from_dict(d)
    assert loaded.parent_project_id is None
    assert loaded.variant_label is None
