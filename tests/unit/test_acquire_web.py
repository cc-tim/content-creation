from unittest.mock import patch

from pipeline.adapters.web import WebArticle
from pipeline.stages.acquire_web import AcquireWebStage


async def test_acquire_web_extracts_article(sample_context):
    stage = AcquireWebStage()
    assert stage.name == "acquire"

    fake_article = WebArticle(
        url="https://example.com/test",
        title="Test Article",
        text="Article body content for testing.",
        author="Author",
        date="2026-04-05",
        source_name="Example",
    )

    with (
        patch("pipeline.stages.acquire_web.fetch_article", return_value=fake_article),
        patch("pipeline.stages.acquire_web.save_article") as mock_save,
    ):
        mock_save.return_value = sample_context.work_dir / "source" / "article.txt"
        (sample_context.work_dir / "source").mkdir(parents=True)
        (sample_context.work_dir / "source" / "article.txt").write_text("content")

        ctx = await stage.run(sample_context)

    assert ctx.transcript_text == "Article body content for testing."
    assert ctx.video_path is None  # No video for web articles
    assert ctx.transcript_path is not None
