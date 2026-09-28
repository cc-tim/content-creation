import base64
import io

import pytest
from PIL import Image

from pipeline import llm

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(llm.resolve_claude_bin() is None, reason="claude CLI not installed")]


def test_real_text_call():
    assert "ok" in llm.complete("Reply with exactly: ok", tier="check", call_site="it.text").text.lower()


def test_real_image_call():
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (220, 30, 30)).save(buf, "PNG")
    blocks = [{"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                           "data": base64.b64encode(buf.getvalue()).decode()}},
              {"type": "text", "text": "What colour is this image? One word."}]
    assert "red" in llm.complete(blocks, tier="check", call_site="it.image").text.lower()


def test_real_schema_call():
    r = llm.complete("Name one primary colour.", tier="check", call_site="it.schema",
                     json_schema={"type": "object", "properties": {"colour": {"type": "string"}},
                                  "required": ["colour"]})
    assert isinstance(r.data, dict) and r.data.get("colour")
