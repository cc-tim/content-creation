from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.publish.channels import (
    auto_detect_niche,
    load_channel_config,
    resolve_profile,
)

FIXTURE = Path(__file__).parents[2] / "fixtures" / "sample_youtube_channels.toml"


def test_load_channel_config_from_fixture() -> None:
    cfg = load_channel_config(FIXTURE)
    assert set(cfg.profiles) == {"parenting-tw", "tech-en", "drama-tw"}
    assert cfg.routing["parenting/zh-TW"] == "parenting-tw"


def test_load_channel_config_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_channel_config(tmp_path / "nope.toml")


def test_load_channel_config_routing_points_at_unknown_profile(tmp_path: Path) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text(
        '[profiles.a]\nniche="x"\nlocale="en"\nchannel_id=""\nvoice_guide=""\n'
        "default_tags=[]\ncategory_id=1\n"
        '[routing]\n"x/en" = "nonexistent"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="routing references unknown profile: nonexistent"):
        load_channel_config(bad)


def test_resolve_profile_by_explicit_override() -> None:
    cfg = load_channel_config(FIXTURE)
    profile = resolve_profile(cfg, niche="parenting", locale="zh-TW", override="tech-en")
    assert profile.name == "tech-en"


def test_resolve_profile_by_routing() -> None:
    cfg = load_channel_config(FIXTURE)
    profile = resolve_profile(cfg, niche="parenting", locale="zh-TW", override=None)
    assert profile.name == "parenting-tw"


def test_resolve_profile_unmapped_pair() -> None:
    cfg = load_channel_config(FIXTURE)
    with pytest.raises(ValueError, match="No channel configured"):
        resolve_profile(cfg, niche="tech", locale="zh-TW", override=None)


def test_resolve_profile_explicit_override_missing() -> None:
    cfg = load_channel_config(FIXTURE)
    with pytest.raises(ValueError, match="profile 'nope' not found"):
        resolve_profile(cfg, niche="parenting", locale="zh-TW", override="nope")


def test_auto_detect_single_niche() -> None:
    cfg = load_channel_config(FIXTURE)
    assert auto_detect_niche(cfg, locale="en") == "tech"


def test_auto_detect_zero_niches() -> None:
    cfg = load_channel_config(FIXTURE)
    with pytest.raises(ValueError, match="No channel configured for locale=es-MX"):
        auto_detect_niche(cfg, locale="es-MX")


def test_auto_detect_ambiguous() -> None:
    cfg = load_channel_config(FIXTURE)
    # zh-TW maps to both parenting and drama
    with pytest.raises(ValueError, match="Ambiguous.*parenting.*drama|drama.*parenting"):
        auto_detect_niche(cfg, locale="zh-TW")
