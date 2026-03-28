from pipeline.utils.ffmpeg import (
    build_extract_clip_cmd,
    build_burn_subtitles_cmd,
    build_concat_cmd,
    check_ffmpeg_available,
)


def test_extract_clip_cmd():
    cmd = build_extract_clip_cmd(
        input_path="video.mp4",
        output_path="clip.mp4",
        start_sec=83.0,
        end_sec=95.0,
    )
    assert "video.mp4" in cmd
    assert "clip.mp4" in cmd
    assert "-ss" in cmd
    assert "83.0" in cmd


def test_burn_subtitles_cmd():
    cmd = build_burn_subtitles_cmd(
        input_path="video.mp4",
        subtitle_path="subs.srt",
        output_path="output.mp4",
        font_name="Noto Sans CJK TC",
    )
    assert "subs.srt" in " ".join(cmd)
    assert "Noto Sans CJK TC" in " ".join(cmd)


def test_concat_cmd(tmp_path):
    filelist = tmp_path / "files.txt"
    cmd = build_concat_cmd(
        filelist_path=str(filelist),
        output_path="final.mp4",
    )
    assert "concat" in " ".join(cmd)
    assert "final.mp4" in cmd
