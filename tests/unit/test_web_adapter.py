from unittest.mock import MagicMock, patch

import pytest

from pipeline.adapters.web import WebArticle, fetch_article, save_article


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
