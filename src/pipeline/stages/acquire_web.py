"""Acquire stage for web articles.

Downloads and extracts article content, stores as transcript-equivalent
so the analyze stage can process it the same way as YouTube transcripts.
"""

from __future__ import annotations

import structlog

from pipeline.adapters.web import fetch_article, save_article
from pipeline.stages.base import PipelineContext, PipelineStage

logger = structlog.get_logger()


class AcquireWebStage(PipelineStage):
    @property
    def name(self) -> str:
        return "acquire"

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        logger.info("acquire_web.start", url=ctx.source_url)

        source_dir = ctx.work_dir / "source"
        source_dir.mkdir(parents=True, exist_ok=True)

        # Fetch and extract article
        article = fetch_article(ctx.source_url)

        # Save article text and metadata
        article_path = save_article(article, source_dir)

        # Set context fields — article text goes where transcript would
        ctx.transcript_text = article.text
        ctx.transcript_path = article_path
        # No video for web articles
        ctx.video_path = None

        logger.info(
            "acquire_web.complete",
            title=article.title,
            chars=len(article.text),
        )
        return ctx
