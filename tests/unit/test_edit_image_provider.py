from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_FAKE_PNG = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x11\x00\x01\x1b\xb0\xa4G\x00\x00\x00\x00IEND\xaeB`\x82'
_FAKE_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADklEQVQI12P4z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg=="


def test_edit_img2img_returns_provider_result(tmp_path):
    from pipeline.providers.edit_image import EditImageProvider

    inp = tmp_path / "input.png"
    inp.write_bytes(_FAKE_PNG)
    out = tmp_path / "output.png"

    import json

    def fake_urlopen(req, timeout=None):
        resp = MagicMock()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        resp.read.return_value = json.dumps({"images": [{"url": "http://fake/img.png"}]}).encode()
        return resp

    with patch("pipeline.providers.edit_image._get_key", return_value="fake-key"), \
         patch("urllib.request.urlopen", fake_urlopen), \
         patch("urllib.request.urlretrieve", side_effect=lambda url, dest: Path(dest).write_bytes(_FAKE_PNG)):
        result = EditImageProvider().edit_img2img(inp, "keep composition", 0.3, out, "1792x1024")

    assert out.exists()
    assert result.provider == "fal-img2img"
    assert result.path == out


def test_edit_inpaint_returns_provider_result(tmp_path):
    import base64

    from pipeline.providers.edit_image import EditImageProvider

    inp = tmp_path / "input.png"
    inp.write_bytes(_FAKE_PNG)
    out = tmp_path / "output.png"

    fake_b64 = base64.b64encode(_FAKE_PNG).decode()

    mock_response = MagicMock()
    mock_response.data = [MagicMock(b64_json=fake_b64)]

    mock_client = MagicMock()
    mock_client.images.edit.return_value = mock_response

    with patch("pipeline.providers.edit_image._get_key", return_value="fake-key"), \
         patch("pipeline.providers.edit_image.OpenAI", return_value=mock_client):
        result = EditImageProvider().edit_inpaint(inp, "fix expression", out, "1536x1024")

    assert out.exists()
    assert out.read_bytes() == _FAKE_PNG
    assert result.provider == "openai-inpaint"


def test_edit_img2img_raises_on_http_error(tmp_path):
    import urllib.error

    from pipeline.providers.base import ProviderError
    from pipeline.providers.edit_image import EditImageProvider

    inp = tmp_path / "input.png"
    inp.write_bytes(_FAKE_PNG)
    out = tmp_path / "output.png"

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(None, 500, "server error", {}, None)

    with patch("pipeline.providers.edit_image._get_key", return_value="fake-key"), \
         patch("urllib.request.urlopen", fake_urlopen), pytest.raises(ProviderError):
        EditImageProvider().edit_img2img(inp, "fix", 0.3, out)
