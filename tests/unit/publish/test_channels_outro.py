from __future__ import annotations

import textwrap
from pathlib import Path

from pipeline.publish.channels import load_channel_config


def _write_toml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "channels.toml"
    p.write_text(textwrap.dedent(content))
    return p


def test_outro_fields_loaded(tmp_path: Path) -> None:
    p = _write_toml(
        tmp_path,
        """
        [profiles.my-ch]
        niche = "parenting"
        locale = "zh-TW"
        channel_id = "UC123"
        voice_guide = ""
        default_tags = []
        category_id = 27
        display_name = "理想父母"
        tagline = "陪你走過每個育兒時刻"
        outro_enabled = true

        [routing]
        "parenting/zh-TW" = "my-ch"
    """,
    )
    cfg = load_channel_config(p)
    prof = cfg.profiles["my-ch"]
    assert prof.display_name == "理想父母"
    assert prof.tagline == "陪你走過每個育兒時刻"
    assert prof.outro_enabled is True


def test_outro_fields_default_to_off(tmp_path: Path) -> None:
    p = _write_toml(
        tmp_path,
        """
        [profiles.bare]
        niche = "tech"
        locale = "en"
        channel_id = ""
        voice_guide = ""
        default_tags = []
        category_id = 28

        [routing]
        "tech/en" = "bare"
    """,
    )
    cfg = load_channel_config(p)
    prof = cfg.profiles["bare"]
    assert prof.display_name == ""
    assert prof.tagline == ""
    assert prof.outro_enabled is False
