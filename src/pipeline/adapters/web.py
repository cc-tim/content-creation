"""Web article adapter — fetch and extract article content from URLs.

Produces the same normalized output that the analyze stage consumes,
enabling knowledge extraction from web articles (not just YouTube videos).
Also extracts article images for use as visuals in the storyboard.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
import structlog
import trafilatura
from lxml import html as lxml_html

logger = structlog.get_logger()

# Skip images that are likely UI elements, not article content
_SKIP_PATTERNS = {"logo", "icon", "avatar", "pixel", "tracking", "favicon", "badge", "sprite"}


@dataclass
class ArticleImage:
    """An image extracted from a web article."""

    url: str
    alt: str = ""
    local_path: Path | None = None


@dataclass
class WebArticle:
    """Extracted article content."""

    url: str
    title: str
    text: str
    author: str
    date: str
    source_name: str
    images: list[ArticleImage] = field(default_factory=list)


def _extract_image_urls(html_text: str, base_url: str) -> list[ArticleImage]:
    """Parse HTML to find article content images, resolving relative URLs."""
    tree = lxml_html.fromstring(html_text)
    images: list[ArticleImage] = []
    seen: set[str] = set()

    for img in tree.xpath("//img"):
        src = img.get("src", "")
        alt = img.get("alt", "")
        if not src:
            continue

        # Resolve _next/image proxy URLs (Next.js pattern)
        full_url = urljoin(base_url, src)
        parsed = urlparse(full_url)
        qs = parse_qs(parsed.query)
        if "url" in qs:
            full_url = qs["url"][0]

        # Skip UI elements
        src_lower = full_url.lower()
        if any(p in src_lower for p in _SKIP_PATTERNS):
            continue

        # Skip tiny images (likely icons) and SVGs (likely decorative)
        if full_url.endswith(".svg"):
            continue

        # Deduplicate
        if full_url in seen:
            continue
        seen.add(full_url)

        images.append(ArticleImage(url=full_url, alt=alt))

    return images


def _download_images(
    images: list[ArticleImage], output_dir: Path, timeout: int = 30
) -> list[ArticleImage]:
    """Download article images to output_dir. Returns images with local_path set."""
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[ArticleImage] = []

    for i, img in enumerate(images):
        try:
            resp = httpx.get(img.url, follow_redirects=True, timeout=timeout)
            resp.raise_for_status()

            # Determine extension from content-type or URL
            ct = resp.headers.get("content-type", "")
            if "png" in ct:
                ext = ".png"
            elif "jpeg" in ct or "jpg" in ct:
                ext = ".jpg"
            elif "webp" in ct:
                ext = ".webp"
            elif "gif" in ct:
                ext = ".gif"
            else:
                # Guess from URL
                url_path = urlparse(img.url).path
                ext = Path(url_path).suffix or ".png"

            local = output_dir / f"img_{i + 1:02d}{ext}"
            local.write_bytes(resp.content)
            img.local_path = local
            downloaded.append(img)
            logger.info("web.image_downloaded", index=i + 1, path=str(local))
        except Exception:
            logger.warning("web.image_download_failed", url=img.url)

    return downloaded


def fetch_article(url: str) -> WebArticle:
    """Fetch and extract article text + images from a URL."""
    logger.info("web.fetch", url=url)

    response = httpx.get(url, follow_redirects=True, timeout=30)
    response.raise_for_status()
    raw_html = response.text

    # Extract main content
    result = trafilatura.extract(
        raw_html,
        include_comments=False,
        include_tables=True,
        output_format="txt",
    )

    if not result:
        raise ValueError(f"Could not extract article content from {url}")

    # Extract metadata
    metadata = trafilatura.extract_metadata(raw_html)

    title = metadata.title if metadata and metadata.title else ""
    author = metadata.author if metadata and metadata.author else ""
    date = metadata.date if metadata and metadata.date else ""
    source = metadata.sitename if metadata and metadata.sitename else ""

    # Extract images from HTML
    images = _extract_image_urls(raw_html, url)
    logger.info("web.images_found", count=len(images))

    article = WebArticle(
        url=url,
        title=title,
        text=result,
        author=author,
        date=date,
        source_name=source,
        images=images,
    )

    logger.info(
        "web.extracted",
        title=title,
        chars=len(result),
        author=author,
        images=len(images),
    )
    return article


def save_article(article: WebArticle, output_dir: Path) -> Path:
    """Save extracted article to the project source directory, including images."""
    output_dir.mkdir(parents=True, exist_ok=True)
    article_path = output_dir / "article.txt"
    article_path.write_text(article.text, encoding="utf-8")

    # Download images
    if article.images:
        images_dir = output_dir / "images"
        article.images = _download_images(article.images, images_dir)

    # Save metadata (including image manifest)
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
                "images": [
                    {
                        "url": img.url,
                        "alt": img.alt,
                        "local_path": str(img.local_path) if img.local_path else None,
                    }
                    for img in article.images
                ],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return article_path
