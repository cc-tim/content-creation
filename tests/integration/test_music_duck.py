"""duck_bed (sidechain) + mux_music_onto_final (raw-sourced, idempotent)."""
import subprocess

from pipeline.composer.music import duck_bed, mux_music_onto_final


def _tone(path, hz, sec):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency={hz}:duration={sec}",
         "-ar", "48000", "-ac", "2", str(path)],
        check=True, capture_output=True,
    )


def _av(path, hz, sec=2):
    subprocess.run(
        ["ffmpeg", "-y",
         "-f", "lavfi", "-i", f"testsrc2=size=320x240:rate=30:duration={sec}",
         "-f", "lavfi", "-i", f"sine=frequency={hz}:duration={sec}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)],
        check=True, capture_output=True,
    )


def _speech_then_silence(path):  # 0-4s tone ("speech"), 4-8s silence
    subprocess.run(
        ["ffmpeg", "-y",
         "-f", "lavfi", "-i", "sine=frequency=300:duration=4",
         "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo:d=4",
         "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[a]", "-map", "[a]",
         "-ar", "48000", "-ac", "2", str(path)],
        check=True, capture_output=True,
    )


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


def test_duck_reduces_under_speech_and_recovers(tmp_path):
    _tone(tmp_path / "bed.wav", 220, 8)
    _speech_then_silence(tmp_path / "key.wav")
    ducked = duck_bed(tmp_path / "bed.wav", tmp_path / "key.wav",
                      tmp_path / "ducked.m4a", duck_db=15.0)
    speech = _mean_db(ducked, 0.5, 3.0)
    pause = _mean_db(ducked, 4.5, 3.0)
    assert pause - speech > 4.0                       # recovers (louder) in the pause
    key_speech = _mean_db(tmp_path / "key.wav", 0.5, 3.0)
    assert key_speech - speech > 8.0                  # bed sits well below speech


def test_mux_sources_narration_from_raw_so_reapply_is_idempotent(tmp_path):
    _av(tmp_path / "final0.mp4", 300, 2)
    _av(tmp_path / "raw.mp4", 300, 2)                 # pristine narration (separate file)
    _tone(tmp_path / "ducked.m4a", 220, 2)
    mux_music_onto_final(tmp_path / "final0.mp4", tmp_path / "raw.mp4",
                         tmp_path / "ducked.m4a", tmp_path / "A.mp4")
    # Re-apply over an already-musicked final; narration still taken from raw, not A's audio.
    mux_music_onto_final(tmp_path / "A.mp4", tmp_path / "raw.mp4",
                         tmp_path / "ducked.m4a", tmp_path / "B.mp4")
    a = _mean_db(tmp_path / "A.mp4", 0.2, 1.5)
    b = _mean_db(tmp_path / "B.mp4", 0.2, 1.5)
    assert abs(a - b) < 1.5                            # no music doubling on re-apply
    v = subprocess.run(
        ["ffprobe", "-v", "0", "-select_streams", "v", "-show_entries",
         "stream=codec_type", "-of", "csv=p=0", str(tmp_path / "B.mp4")],
        capture_output=True, text=True,
    ).stdout
    assert "video" in v                                # video stream preserved
