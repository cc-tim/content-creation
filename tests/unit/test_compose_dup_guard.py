from unittest.mock import MagicMock, patch


def test_extract_thumbnail_called_for_clip(tmp_path):
    from pipeline.stages.compose import _extract_clip_thumbnail

    fake_source = tmp_path / "source.mp4"
    fake_source.write_bytes(b"fake")

    with patch("pipeline.stages.compose.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        _extract_clip_thumbnail(fake_source, timestamp=30.0, out_path=tmp_path / "thumb.jpg")
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert "ffmpeg" in args
    assert "30.0" in " ".join(str(a) for a in args)


def test_is_duplicate_detects_same_hash():
    import imagehash

    from pipeline.stages.compose import _is_duplicate_frame

    h = imagehash.hex_to_hash("0" * 16)
    seen = {h}
    assert _is_duplicate_frame(h, seen) is True


def test_is_duplicate_allows_unique_hash():
    import imagehash

    from pipeline.stages.compose import _is_duplicate_frame

    h1 = imagehash.hex_to_hash("0" * 16)
    h2 = imagehash.hex_to_hash("f" * 16)
    seen = {h1}
    assert _is_duplicate_frame(h2, seen) is False


def test_duplicate_guard_replaces_scene_visual(tmp_path):
    import imagehash

    from pipeline.stages.compose import _apply_duplicate_guard

    fake_source = tmp_path / "source.mp4"
    fake_source.write_bytes(b"fake")

    scene_clip_a = {"id": "s1", "visual": {"type": "clip", "start_sec": 10}, "narration": "first"}
    scene_clip_b = {"id": "s8", "visual": {"type": "clip", "start_sec": 20}, "narration": "test narr"}

    same_hash = imagehash.hex_to_hash("0" * 16)
    seen: set = set()

    def fake_thumbnail(source, timestamp, out_path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"fake")

    with patch("pipeline.stages.compose._extract_clip_thumbnail", side_effect=fake_thumbnail), \
         patch("pipeline.stages.compose._phash_image", return_value=same_hash):
        result_a, seen = _apply_duplicate_guard(scene_clip_a, fake_source, seen, style_descriptor="sketch")
        result_b, seen = _apply_duplicate_guard(scene_clip_b, fake_source, seen, style_descriptor="sketch")

    assert result_a["visual"]["type"] == "clip"            # first clip: kept
    assert result_b["visual"]["type"] == "generated_image" # duplicate: replaced
    assert "sketch" in result_b["visual"]["prompt"]
    assert result_a is scene_clip_a  # original not mutated


def test_non_clip_scene_passes_through(tmp_path):
    from pipeline.stages.compose import _apply_duplicate_guard
    scene = {"id": "s2", "visual": {"type": "generated_image", "prompt": "test"}}
    result, seen = _apply_duplicate_guard(scene, None, set(), style_descriptor="")
    assert result is scene
    assert seen == set()
