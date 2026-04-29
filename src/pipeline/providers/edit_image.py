from __future__ import annotations

import base64
import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from openai import OpenAI

from pipeline.providers.base import ProviderError, ProviderResult

_KM = Path.home() / ".claude" / "bin" / "keymanager.py"

_FAL_SIZE = {
    "1792x1024": "landscape_4_3",
    "1024x1792": "portrait_4_3",
    "1024x1024": "square_hd",
    "1536x1024": "landscape_4_3",
    "1024x1536": "portrait_4_3",
}
_OPENAI_SIZE = {
    "1792x1024": "1536x1024",
    "1024x1792": "1024x1536",
    "1024x1024": "1024x1024",
    "1536x1024": "1536x1024",
    "1024x1536": "1024x1536",
}


def _get_key(provider: str) -> str:
    result = subprocess.run(
        ["python3", str(_KM), "get", provider], capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise ProviderError(f"No {provider} key available: {result.stderr.strip()}")
    return result.stdout.strip()


class EditImageProvider:
    """Provides img2img (fal.ai) and inpaint (OpenAI) edit operations."""

    def edit_img2img(
        self,
        image_path: Path,
        prompt: str,
        strength: float,
        out_path: Path,
        size: str = "1792x1024",
    ) -> ProviderResult:
        """Img2img via fal-ai/flux/dev/image-to-image. Preserves composition at low strength."""
        api_key = _get_key("fal")
        fal_size = _FAL_SIZE.get(size, "landscape_4_3")
        b64 = base64.standard_b64encode(image_path.read_bytes()).decode()
        payload = {
            "image_url": f"data:image/png;base64,{b64}",
            "prompt": prompt,
            "strength": strength,
            "image_size": fal_size,
        }
        req = urllib.request.Request(
            "https://fal.run/fal-ai/flux/dev/image-to-image",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Key {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read())
                url = data["images"][0]["url"]
        except urllib.error.HTTPError as exc:
            body = exc.read().decode()
            raise ProviderError(f"fal.ai img2img HTTP {exc.code}: {body[:200]}") from exc

        out_path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, out_path)
        return ProviderResult(path=out_path, provider="fal-img2img")

    def edit_inpaint(
        self,
        image_path: Path,
        prompt: str,
        out_path: Path,
        size: str = "1792x1024",
    ) -> ProviderResult:
        """Inpaint / restyle via OpenAI images.edit (gpt-image-1) using the SDK."""
        api_key = _get_key("openai")
        openai_size = _OPENAI_SIZE.get(size, "1536x1024")
        client = OpenAI(api_key=api_key)
        try:
            with open(image_path, "rb") as f:
                response = client.images.edit(
                    model="gpt-image-1",
                    image=f,
                    prompt=prompt,
                    size=openai_size,
                    n=1,
                )
        except Exception as exc:
            raise ProviderError(f"OpenAI inpaint failed: {exc}") from exc
        b64_data = response.data[0].b64_json
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(base64.b64decode(b64_data))
        return ProviderResult(path=out_path, provider="openai-inpaint")
