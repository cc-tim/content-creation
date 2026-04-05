"""Web article adapter — fetch and extract article content from URLs.

Produces the same normalized output that the analyze stage consumes,
enabling knowledge extraction from web articles (not just YouTube videos).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx
import structlog
import trafilatura

logger = structlog.get_logger()


@dataclass
class WebArticle:
    """Extracted article content."""

    url: str
    title: str
    text: str
    author: str
    date: str
    source_name: str


def fetch_article(url: str) -> WebArticle:
    """Fetch and extract article text from a URL using trafilatura."""
    logger.info("web.fetch", url=url)

    response = httpx.get(url, follow_redirects=True, timeout=30)
    response.raise_for_status()
    html = response.text

    # Extract main content
    result = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=True,
        output_format="txt",
    )

    if not result:
        raise ValueError(f"Could not extract article content from {url}")

    # Extract metadata
    metadata = trafilatura.extract_metadata(html)

    title = metadata.title if metadata and metadata.title else ""
    author = metadata.author if metadata and metadata.author else ""
    date = metadata.date if metadata and metadata.date else ""
    source = metadata.sitename if metadata and metadata.sitename else ""

    article = WebArticle(
        url=url,
        title=title,
        text=result,
        author=author,
        date=date,
        source_name=source,
    )

    logger.info(
        "web.extracted",
        title=title,
        chars=len(result),
        author=author,
    )
    return article


def save_article(article: WebArticle, output_dir: Path) -> Path:
    """Save extracted article to the project source directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    article_path = output_dir / "article.txt"
    article_path.write_text(article.text, encoding="utf-8")

    # Save metadata
    import json

    meta_path = output_dir / "article_meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "url": article.url,
                "title": article.title,
                "author": article.author,
                "date": article.date,
                "source_name": article.source_name,
                "text_length": len(article.text),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return article_path
