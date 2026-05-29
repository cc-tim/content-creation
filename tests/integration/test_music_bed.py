"""build_bed: full-length 48k/stereo mood bed with crossfades + silent gaps."""
import subprocess

from pipeline.composer.music import Cue, MoodTrack, build_bed


def _tone(path, hz, sec=30):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency={hz}:duration={sec}",
         "-ar", "48000", "-ac", "2", str(path)],
        check=True, capture_output=True,
    )


def _dur(path):
    out = subprocess.run(
        ["ffprobe", "-v", "0", "-show_entries", "format=duration",
         "-of", "default=nk=1:nw=1", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()
    return float(out)


def _mean_db(path, ss, dur):
    out = subprocess.run(
        ["ffmpeg", "-ss", str(ss), "-i", str(path), "-t", str(dur),
         "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    for line in out.splitlines():
        if "mean_volume:" in line:
            return float(line.split("mean_volume:")[1].split("dB")[0].strip())
    return -120.0


def test_build_bed_places_moods_and_silences_gaps(tmp_path):
    _tone(tmp_path / "tense.wav", 110)
    _tone(tmp_path / "hope.wav", 440)
    lib = {
        "tense": MoodTrack("tense", tmp_path / "tense.wav"),
        "hopeful": MoodTrack("hopeful", tmp_path / "hope.wav"),
    }
    cues = [Cue("tense", 2.0, 6.0), Cue("hopeful", 6.0, 10.0)]  # abut at 6.0 -> crossfade
    bed = build_bed(cues, lib, total_sec=14.0, out_path=tmp_path / "bed.m4a")

    assert abs(_dur(bed) - 14.0) < 0.3          # padded/trimmed to full video length
    assert _mean_db(bed, 3.0, 2.0) > -40        # tense region audible
    assert _mean_db(bed, 7.0, 2.0) > -40        # hopeful region audible
    assert _mean_db(bed, 11.5, 2.0) < -55       # post-last-cue gap ~ silent


def test_build_bed_returns_none_for_no_cues(tmp_path):
    assert build_bed([], {}, total_sec=10.0, out_path=tmp_path / "bed.m4a") is None
