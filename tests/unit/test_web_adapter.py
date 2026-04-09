from unittest.mock import MagicMock, patch

import pytest

from pipeline.adapters.web import (
    ArticleImage,
    WebArticle,
    _extract_image_urls,
    fetch_article,
    save_article,
)


def test_save_article(tmp_path):
    article = WebArticle(
        url="https://example.com/article",
        title="Test Article",
        text="This is the article body with important content.",
        author="John Doe",
        date="2026-04-05",
        source_name="Example Blog",
    )
    path = save_article(article, tmp_path / "source")
    assert path.exists()
    assert "important content" in path.read_text()

    meta_path = tmp_path / "source" / "article_meta.json"
    assert meta_path.exists()
    import json

    meta = json.loads(meta_path.read_text())
    assert meta["title"] == "Test Article"
    assert meta["author"] == "John Doe"


def test_fetch_article_extracts_content():
    fake_html = """
    <html><body>
    <article><h1>Big Title</h1><p>This is the main article content.</p></article>
    </body></html>
    """

    with (
        patch("pipeline.adapters.web.httpx.get") as mock_get,
        patch("pipeline.adapters.web.trafilatura.extract") as mock_extract,
        patch("pipeline.adapters.web.trafilatura.extract_metadata") as mock_meta,
    ):
        mock_response = MagicMock()
        mock_response.text = fake_html
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        mock_extract.return_value = "This is the main article content."

        mock_metadata = MagicMock()
        mock_metadata.title = "Big Title"
        mock_metadata.author = "Author Name"
        mock_metadata.date = "2026-04-05"
        mock_metadata.sitename = "Test Site"
        mock_meta.return_value = mock_metadata

        article = fetch_article("https://example.com/test")

    assert article.title == "Big Title"
    assert article.text == "This is the main article content."
    assert article.author == "Author Name"


def test_fetch_article_empty_content():
    with (
        patch("pipeline.adapters.web.httpx.get") as mock_get,
        patch("pipeline.adapters.web.trafilatura.extract", return_value=None),
    ):
        mock_response = MagicMock()
        mock_response.text = "<html></html>"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with pytest.raises(ValueError, match="Could not extract"):
            fetch_article("https://example.com/empty")


def test_extract_image_urls_basic():
    html = """
    <html><body>
    <img src="https://cdn.example.com/photo1.png" alt="Diagram 1">
    <img src="/images/photo2.jpg" alt="Diagram 2">
    <img src="https://cdn.example.com/logo.svg" alt="Logo">
    <img src="https://cdn.example.com/favicon.ico" alt="">
    </body></html>
    """
    images = _extract_image_urls(html, "https://example.com/article")
    # Should skip SVG and favicon
    assert len(images) == 2
    assert images[0].url == "https://cdn.example.com/photo1.png"
    assert images[0].alt == "Diagram 1"
    assert images[1].url == "https://example.com/images/photo2.jpg"


def test_extract_image_urls_nextjs_proxy():
    """Resolve Next.js _next/image proxy URLs."""
    html = """
    <html><body>
    <img src="/_next/image?url=https%3A%2F%2Fcdn.example.com%2Fphoto.png&w=1920&q=75">
    </body></html>
    """
    images = _extract_image_urls(html, "https://example.com/post")
    assert len(images) == 1
    assert images[0].url == "https://cdn.example.com/photo.png"


def test_save_article_with_images(tmp_path):
    """Images are downloaded and manifest is saved in metadata."""
    img = ArticleImage(url="https://cdn.example.com/photo.png", alt="Test diagram")
    article = WebArticle(
        url="https://example.com/article",
        title="With Images",
        text="Article body.",
        author="",
        date="",
        source_name="",
        images=[img],
    )

    fake_resp = MagicMock()
    fake_resp.content = b"fake png bytes"
    fake_resp.headers = {"content-type": "image/png"}
    fake_resp.raise_for_status = MagicMock()

    with patch("pipeline.adapters.web.httpx.get", return_value=fake_resp):
        save_article(article, tmp_path / "source")

    images_dir = tmp_path / "source" / "images"
    assert images_dir.exists()
    assert (images_dir / "img_01.png").exists()

    import json

    meta = json.loads((tmp_path / "source" / "article_meta.json").read_text())
    assert len(meta["images"]) == 1
    assert meta["images"][0]["alt"] == "Test diagram"
