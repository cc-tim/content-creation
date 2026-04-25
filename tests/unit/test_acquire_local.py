from pathlib import Path

from pipeline.stages.acquire import parse_transcript_file

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
