from __future__ import annotations

import importlib.util
from pathlib import Path


HELPER = Path.home() / ".claude" / "bin" / "gen-image-edit.py"


def _load_helper():
    spec = importlib.util.spec_from_file_location("gen_image_edit", HELPER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_outpaint_instruction_prefix_added():
    helper = _load_helper()
    prompt = helper.build_instruction("make room on both sides", "outpaint")
    assert prompt.startswith("Extend the image to the target aspect ratio.")
    assert "make room on both sides" in prompt


def test_generic_instruction_has_no_outpaint_prefix():
    helper = _load_helper()
    assert helper.build_instruction("remove glare", "generic") == "remove glare"


def test_cache_key_uses_source_bytes_instruction_aspect_and_mode(tmp_path):
    helper = _load_helper()
    source = tmp_path / "source.png"
    source.write_bytes(b"abc")

    a = helper.cache_key(source, "extend", "947:484", "outpaint")
    b = helper.cache_key(source, "extend", "16:9", "outpaint")
    c = helper.cache_key(source, "extend", "947:484", "generic")

    assert a != b
    assert a != c
    assert len(a) == 64


def test_nearest_fal_aspect_for_book_inset():
    helper = _load_helper()
    assert helper.nearest_fal_aspect("947:484") == "16:9"
    assert helper.nearest_fal_aspect("720:1280") == "9:16"
    assert helper.nearest_fal_aspect("1000:1000") == "1:1"


def test_key_reset_hint_uses_label_when_known(tmp_path, monkeypatch):
    helper = _load_helper()
    key = "fal_secret_key"
    monkeypatch.setattr(helper, "KEY_CONFIG", tmp_path / "api-keys.json")
    (tmp_path / "api-keys.json").write_text(
        '{"fal": {"keys": [{"label": "fal-main", "key": "fal_secret_key", "exhausted": false}]}}',
        encoding="utf-8",
    )

    assert helper.key_reset_hint("fal", key).endswith("keymanager.py reset fal fal-main")
