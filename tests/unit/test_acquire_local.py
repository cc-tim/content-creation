import json
from pathlib import Path
from unittest.mock import patch

from pipeline.stages.acquire import AcquireStage, parse_transcript_file
from pipeline.stages.base import PipelineContext

# ── CSV format ────────────────────────────────────────────────────────────────

def test_parse_csv_basic(tmp_path: Path):
    f = tmp_path / "t.csv"
    f.write_text(
        "00:00,0.08,4.16,Mrs. Henry, excuse me.\n"
        "00:04,4.24,5.44,Well, I'm bringing my husband.\n",
        encoding="utf-8",
    )
    full_text, raw = parse_transcript_file(f)
    assert len(raw) == 2
    assert raw[0] == {"text": "Mrs. Henry, excuse me.", "start": 0.08, "duration": 4.16}
    assert raw[1] == {"text": "Well, I'm bringing my husband.", "start": 4.24, "duration": 5.44}
    assert "Mrs. Henry" in full_text
    assert "husband" in full_text


def test_parse_csv_skips_blank_rows(tmp_path: Path):
    f = tmp_path / "t.csv"
    f.write_text(
        "00:00,0.08,4.16,Mrs. Henry, excuse me.\n"
        "00:02,1.99,2.25,\n"
        "00:04,4.24,5.44,Well, I'm bringing my husband.\n",
        encoding="utf-8",
    )
    _, raw = parse_transcript_file(f)
    assert len(raw) == 2  # blank row filtered


def test_parse_csv_skips_malformed_rows(tmp_path: Path):
    f = tmp_path / "t.csv"
    f.write_text(
        "00:00,0.08,4.16,Good row.\n"
        "not,enough,cols\n"
        "00:04,bad_float,5.44,Also bad.\n",
        encoding="utf-8",
    )
    _, raw = parse_transcript_file(f)
    assert len(raw) == 1
    assert raw[0]["text"] == "Good row."


# ── TXT format ────────────────────────────────────────────────────────────────

def test_parse_txt_basic(tmp_path: Path):
    f = tmp_path / "t.txt"
    f.write_text(
        "00:00 Mrs. Henry, excuse me.\n"
        "00:04 Well, I'm bringing my husband.\n"
        "00:09 He makes more than I do.\n",
        encoding="utf-8",
    )
    full_text, raw = parse_transcript_file(f)
    assert len(raw) == 3
    assert raw[0]["start"] == 0.0
    assert raw[0]["duration"] == 4.0   # gap to next (4*60+0 - 0*60+0 = 4)
    assert raw[1]["start"] == 4.0
    assert raw[1]["duration"] == 5.0   # gap to 00:09
    assert raw[2]["duration"] == 2.0   # last entry defaults to 2.0s
    assert "Mrs. Henry" in full_text


def test_parse_txt_skips_blank_lines(tmp_path: Path):
    f = tmp_path / "t.txt"
    f.write_text(
        "00:00 First line.\n"
        "\n"
        "00:04 Second line.\n",
        encoding="utf-8",
    )
    _, raw = parse_transcript_file(f)
    assert len(raw) == 2


# ── AcquireStage with local files ─────────────────────────────────────────────

async def test_acquire_uses_local_transcript(tmp_path: Path):
    """Local transcript file skips YouTube API call."""
    work_dir = tmp_path / "project"
    work_dir.mkdir()
    ctx = PipelineContext(
        project_id=1, source_url="https://youtube.com/watch?v=test",
        locale="zh-TW", work_dir=work_dir,
    )

    transcript_file = tmp_path / "t.csv"
    transcript_file.write_text(
        "00:00,0.08,4.16,Mrs. Henry, excuse me.\n"
        "00:04,4.24,5.44,Well, I'm bringing my husband.\n",
        encoding="utf-8",
    )

    stage = AcquireStage(local_transcript=transcript_file)

    with (
        patch("pipeline.stages.acquire.download_video") as mock_dl,
        patch("pipeline.stages.acquire.extract_transcript") as mock_tr,
    ):
        mock_dl.side_effect = lambda url, out, resolution: _write_fake_video(out)
        ctx = await stage.run(ctx)

    mock_tr.assert_not_called()   # skipped
    assert ctx.transcript_text is not None
    assert "Mrs. Henry" in ctx.transcript_text
    assert ctx.transcript_path is not None
    saved = json.loads(ctx.transcript_path.read_text())
    assert saved[0]["start"] == 0.08


async def test_acquire_uses_local_video(tmp_path: Path):
    """Local video file skips yt-dlp download."""
    work_dir = tmp_path / "project"
    work_dir.mkdir()
    ctx = PipelineContext(
        project_id=1, source_url="https://youtube.com/watch?v=test",
        locale="zh-TW", work_dir=work_dir,
    )

    local_video = tmp_path / "my_video.mp4"
    local_video.write_bytes(b"fake video bytes")

    stage = AcquireStage(local_video=local_video)

    with (
        patch("pipeline.stages.acquire.download_video") as mock_dl,
        patch("pipeline.stages.acquire.extract_transcript") as mock_tr,
    ):
        mock_tr.return_value = ("transcript text", [])
        ctx = await stage.run(ctx)

    mock_dl.assert_not_called()   # skipped
    assert ctx.video_path is not None
    assert ctx.video_path.name == "my_video.mp4"
    assert ctx.video_path.read_bytes() == b"fake video bytes"


async def test_acquire_both_local_skips_all_fetches(tmp_path: Path):
    """Both local flags → no network calls at all."""
    work_dir = tmp_path / "project"
    work_dir.mkdir()
    ctx = PipelineContext(
        project_id=1, source_url="https://youtube.com/watch?v=test",
        locale="zh-TW", work_dir=work_dir,
    )

    local_video = tmp_path / "video.mp4"
    local_video.write_bytes(b"fake")
    transcript_file = tmp_path / "t.csv"
    transcript_file.write_text("00:00,0.08,4.16,Hello world.\n", encoding="utf-8")

    stage = AcquireStage(local_transcript=transcript_file, local_video=local_video)

    with (
        patch("pipeline.stages.acquire.download_video") as mock_dl,
        patch("pipeline.stages.acquire.extract_transcript") as mock_tr,
    ):
        ctx = await stage.run(ctx)

    mock_dl.assert_not_called()
    mock_tr.assert_not_called()
    assert ctx.video_path is not None
    assert "Hello" in ctx.transcript_text


def _write_fake_video(output_dir: Path) -> Path:
    p = output_dir / "video.mp4"
    p.write_bytes(b"fake")
    return p
