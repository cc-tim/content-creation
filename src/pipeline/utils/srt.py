from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class SrtEntry:
    index: int
    start_ms: int
    end_ms: int
    text: str


def _ms_to_srt_time(ms: int) -> str:
    """Convert milliseconds to SRT timestamp: HH:MM:SS,mmm"""
    hours = ms // 3_600_000
    ms %= 3_600_000
    minutes = ms // 60_000
    ms %= 60_000
    seconds = ms // 1_000
    millis = ms % 1_000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _srt_time_to_ms(ts: str) -> int:
    """Parse SRT timestamp to milliseconds."""
    time_part, millis_str = ts.replace(",", ".").rsplit(".", 1)
    parts = time_part.split(":")
    hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])
    return hours * 3_600_000 + minutes * 60_000 + seconds * 1_000 + int(millis_str)


def parse_srt(path: Path) -> list[SrtEntry]:
    """Parse an SRT file into a list of entries."""
    text = path.read_text(encoding="utf-8")
    entries: list[SrtEntry] = []
    blocks = text.strip().split("\n\n")
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        index = int(lines[0])
        start_str, end_str = lines[1].split(" --> ")
        content = "\n".join(lines[2:])
        entries.append(
            SrtEntry(
                index=index,
                start_ms=_srt_time_to_ms(start_str.strip()),
                end_ms=_srt_time_to_ms(end_str.strip()),
                text=content,
            )
        )
    return entries


def write_srt(entries: list[SrtEntry], path: Path) -> None:
    """Write SRT entries to a file."""
    blocks: list[str] = []
    for entry in entries:
        blocks.append(
            f"{entry.index}\n"
            f"{_ms_to_srt_time(entry.start_ms)} --> {_ms_to_srt_time(entry.end_ms)}\n"
            f"{entry.text}"
        )
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
