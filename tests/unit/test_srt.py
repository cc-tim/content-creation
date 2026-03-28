from pathlib import Path

from pipeline.utils.srt import SrtEntry, parse_srt, write_srt


def test_parse_srt():
    fixture = Path(__file__).parent.parent / "fixtures" / "sample.srt"
    entries = parse_srt(fixture)
    assert len(entries) == 3
    assert entries[0].text == "This is the first subtitle."
    assert entries[0].start_ms == 1000
    assert entries[0].end_ms == 4000


def test_write_srt(tmp_path: Path):
    entries = [
        SrtEntry(index=1, start_ms=0, end_ms=3000, text="你好世界"),
        SrtEntry(index=2, start_ms=3500, end_ms=7000, text="這是測試"),
    ]
    out = tmp_path / "output.srt"
    write_srt(entries, out)
    # Round-trip
    parsed = parse_srt(out)
    assert len(parsed) == 2
    assert parsed[0].text == "你好世界"
    assert parsed[1].start_ms == 3500
