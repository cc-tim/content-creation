from __future__ import annotations

import json
import subprocess
from pathlib import Path

import structlog

from pipeline.stages.base import PipelineContext, PipelineStage

logger = structlog.get_logger()


def download_video(url: str, output_dir: Path, resolution: str = "720p") -> Path:
    """Download video via yt-dlp. Returns path to downloaded file."""
    output_template = str(output_dir / "video.%(ext)s")
    cmd = [
        "yt-dlp",
        "-f",
        f"bestvideo[height<={resolution[:-1]}]+bestaudio/best[height<={resolution[:-1]}]",
        "--merge-output-format",
        "mp4",
        "-o",
        output_template,
        url,
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)

    # Find the downloaded file
    for f in output_dir.iterdir():
        if f.suffix == ".mp4" and f.stem.startswith("video"):
            return f
    raise FileNotFoundError(f"No video file found in {output_dir}")


def extract_transcript(url: str) -> tuple[str, list[dict]]:
    """Extract transcript. Tries youtube-transcript-api first, falls back to yt-dlp subs."""
    video_id = _extract_video_id(url)
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id, languages=["en"])
        transcript_data = [
            {"text": entry.text, "start": entry.start, "duration": entry.duration}
            for entry in transcript
        ]
        full_text = " ".join(entry["text"] for entry in transcript_data)
        return full_text, transcript_data
    except Exception as e:
        logger.warning("youtube-transcript-api failed, trying yt-dlp subs", error=str(e))
        return _extract_via_ytdlp(url)


def _extract_video_id(url: str) -> str:
    """Extract video ID from various YouTube URL formats."""
    if "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]
    if "v=" in url:
        return url.split("v=")[1].split("&")[0]
    raise ValueError(f"Cannot extract video ID from: {url}")


def _extract_via_ytdlp(url: str) -> tuple[str, list[dict]]:
    """Fallback: use yt-dlp to download auto-subs."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        cmd = [
            "yt-dlp",
            "--write-auto-sub",
            "--sub-lang",
            "en",
            "--skip-download",
            "-o",
            f"{tmpdir}/subs",
            url,
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)

        tmppath = Path(tmpdir)
        for f in tmppath.iterdir():
            if f.suffix in (".vtt", ".srt"):
                text = f.read_text(encoding="utf-8")
                return text, []

    raise RuntimeError("No transcript available via any method")


class AcquireStage(PipelineStage):
    @property
    def name(self) -> str:
        return "acquire"

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        logger.info("acquire.start", url=ctx.source_url)

        source_dir = ctx.work_dir / "source"
        source_dir.mkdir(parents=True, exist_ok=True)

        # Download video
        ctx.video_path = download_video(ctx.source_url, source_dir, resolution="720p")
        logger.info("acquire.video_downloaded", path=str(ctx.video_path))

        # Extract transcript
        full_text, raw_data = extract_transcript(ctx.source_url)
        ctx.transcript_text = full_text

        # Save transcript for reference
        transcript_path = source_dir / "transcript.json"
        transcript_path.write_text(
            json.dumps(raw_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        ctx.transcript_path = transcript_path
        logger.info("acquire.transcript_extracted", chars=len(full_text))

        return ctx
