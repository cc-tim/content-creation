from pathlib import Path

import pytest

from pipeline.stages.base import PipelineContext
from pipeline.strategies import load_strategies

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "promo_strategies"


def _ctx(tmp_path, **kwargs) -> PipelineContext:
    return PipelineContext(
        project_id=1,
        source_url="original",
        locale=kwargs.pop("locale", "ja"),
        work_dir=tmp_path,
        **kwargs,
    )


def test_load_strategies_returns_empty_when_dir_missing(tmp_path):
    ctx = _ctx(tmp_path)
    out = load_strategies(ctx, strategies_dir=tmp_path / "does_not_exist")
    assert out == ""


def test_always_strategy_always_loads(tmp_path):
    ctx = _ctx(tmp_path, source_locale=None)
    out = load_strategies(ctx, strategies_dir=FIXTURE_DIR)
    assert "Always-on strategy body." in out
    assert "always-strategy" in out  # name appears in heading


def test_locale_differs_strategy_loads_when_locales_differ(tmp_path):
    ctx = _ctx(tmp_path, locale="ja", source_locale="US")
    out = load_strategies(ctx, strategies_dir=FIXTURE_DIR)
    assert "Locale-differs strategy body." in out


def test_locale_differs_strategy_skipped_when_source_locale_is_none(tmp_path):
    ctx = _ctx(tmp_path, locale="ja", source_locale=None)
    out = load_strategies(ctx, strategies_dir=FIXTURE_DIR)
    assert "Locale-differs strategy body." not in out


def test_locale_differs_strategy_skipped_when_locales_match(tmp_path):
    ctx = _ctx(tmp_path, locale="en", source_locale="en")
    out = load_strategies(ctx, strategies_dir=FIXTURE_DIR)
    assert "Locale-differs strategy body." not in out


def test_target_locale_in_matches(tmp_path):
    ctx = _ctx(tmp_path, locale="ja")
    out = load_strategies(ctx, strategies_dir=FIXTURE_DIR)
    assert "JA-only strategy body." in out


def test_target_locale_in_does_not_match(tmp_path):
    ctx = _ctx(tmp_path, locale="zh-TW")
    out = load_strategies(ctx, strategies_dir=FIXTURE_DIR)
    assert "JA-only strategy body." not in out


def test_malformed_file_skipped_without_crash(tmp_path, caplog):
    ctx = _ctx(tmp_path, locale="ja", source_locale="US")
    # Should not raise even though malformed.md is present in FIXTURE_DIR
    out = load_strategies(ctx, strategies_dir=FIXTURE_DIR)
    assert "Body never reached." not in out
