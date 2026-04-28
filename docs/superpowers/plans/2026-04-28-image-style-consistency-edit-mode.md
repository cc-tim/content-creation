# Image Style Consistency & Edit Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix image style drift across scenes, add per-scene `visual.style_modifier`, wire up img2img + inpaint edit mode with a history-based undo mechanism, and extend `storyboard set` for `visual.*` fields.

**Architecture:** Three-level style hierarchy (niche template → `theme.visual_style` → `visual.style_modifier`) assembled in `composer/base.py`. Edit mode dispatches to a new `EditImageProvider` (fal.ai img2img + OpenAI inpaint). History saved in `compose/scenes/image_history/` before any overwrite; auto-purged after 7 days. Restore via a `_restore.png` sidecar that bypasses generation.

**Tech Stack:** Python, fal.ai REST API (raw HTTP, no SDK), `openai` Python SDK (already in deps), existing `GenImageProvider` / `ProviderResult` patterns, Typer CLI.

**Spec:** `docs/superpowers/specs/2026-04-28-image-style-consistency-edit-mode-design.md`

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `src/pipeline/storyboard.py` | Add `visual_style` to `Theme`; `from_dict` handles it automatically |
| Modify | `src/pipeline/composer/base.py` | New style hierarchy in `render_scene` for `generated_image` |
| **Create** | `src/pipeline/composer/image_history.py` | `save_to_history`, `find_history`, `purge_old`, `restore_scene` |
| **Create** | `src/pipeline/providers/edit_image.py` | `EditImageProvider.edit_img2img` + `.edit_inpaint` |
| Modify | `src/pipeline/composer/image.py` | Sidecar PNG, restore override, edit mode dispatch |
| Modify | `src/pipeline/stages/compose.py` | Auto-clear `edit_mode` after successful scene render |
| Modify | `src/pipeline/cli_storyboard.py` | Dotted `visual.*` field support in `set` command |
| Modify | `src/pipeline/cli_compose.py` | Add `history` + `restore` commands; call `purge_old` in `rescene`/`reburn` |
| Modify | `src/pipeline/stages/direct.py` | Update `generated_image` schema: prompt = concept only |
| Modify | `output/projects/1777161293/storyboard.json` | Set `theme.visual_style`; fix s5, s7b, s12b prompts |
| Extend | `tests/unit/test_image_style.py` | Tests for visual_style override + style_modifier |
| **Create** | `tests/unit/test_image_history.py` | History module tests |
| **Create** | `tests/unit/test_edit_image_provider.py` | EditImageProvider tests (mocked HTTP) |
| **Create** | `tests/unit/test_cli_storyboard_visual.py` | Dotted visual.* field tests |

**Path convention:** `compose/scenes/` is the `work_dir` inside `render_generated_image`.
- Sidecar PNG: `compose/scenes/{scene_id}_source.png`
- Restore override: `compose/scenes/{scene_id}_restore.png`
- Image history: `compose/scenes/image_history/{scene_id}_{YYYYMMDDTHHMMSS}.png`

---

## Task 1: Add `visual_style` to Theme

**Files:**
- Modify: `src/pipeline/storyboard.py:55-74`
- Extend: `tests/unit/test_image_style.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/unit/test_image_style.py

def test_theme_visual_style_roundtrip():
    from pipeline.storyboard import Theme
    t = Theme(visual_style="warm semi-realistic, soft digital painting")
    d = t.to_dict()
    assert d["visual_style"] == "warm semi-realistic, soft digital painting"
    t2 = Theme.from_dict(d)
    assert t2.visual_style == "warm semi-realistic, soft digital painting"

def test_theme_visual_style_default_empty():
    from pipeline.storyboard import Theme
    assert Theme().visual_style == ""

def test_theme_from_dict_ignores_unknown_fields():
    from pipeline.storyboard import Theme
    # Should not raise — unknown keys are filtered by from_dict
    t = Theme.from_dict({"background": "#fff", "visual_style": "warm", "unknown_field": "x"})
    assert t.visual_style == "warm"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/tim-huang/content-creation
uv run pytest tests/unit/test_image_style.py::test_theme_visual_style_roundtrip -v
```
Expected: `AttributeError: Theme has no field 'visual_style'`

- [ ] **Step 3: Add `visual_style` field to `Theme`**

In `src/pipeline/storyboard.py`, in the `Theme` dataclass, add after `image_style`:

```python
visual_style: str = ""  # per-video style override; takes priority over niche template
```

In `Theme.to_dict()`, add:
```python
"visual_style": self.visual_style,
```

`from_dict` already filters by `cls.__dataclass_fields__`, so no change needed there.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_image_style.py -v
```
Expected: all pass (existing tests must still pass)

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/storyboard.py tests/unit/test_image_style.py
git commit -m "feat(storyboard): add visual_style field to Theme for per-video style override"
```

---

## Task 2: New Style Hierarchy in `base.py`

**Files:**
- Modify: `src/pipeline/composer/base.py:128-167`
- Extend: `tests/unit/test_image_style.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/unit/test_image_style.py

def test_visual_style_overrides_style_prefix(tmp_path):
    """theme.visual_style wins over theme.style_prefix (niche template)."""
    from pipeline.composer.base import render_scene
    captured = {}

    def fake_render(visual, duration, width, height, work_dir, scene_id, **kwargs):
        captured["prompt"] = visual.get("prompt", "")
        out = work_dir / f"{scene_id}_visual.mp4"
        out.write_bytes(b"fake")
        return out

    with patch("pipeline.composer.image.render_generated_image", side_effect=fake_render), \
         patch("pipeline.composer.base.render_generated_image", side_effect=fake_render):
        from unittest.mock import patch
        with patch("pipeline.composer.image.render_generated_image", side_effect=fake_render):
            render_scene(
                {"id": "s1", "visual": {"type": "generated_image", "prompt": "parent and child"}},
                5.0, "16:9", tmp_path,
                theme={"visual_style": "warm semi-realistic", "style_prefix": "clean sketch"},
            )
    assert "warm semi-realistic" in captured["prompt"]
    assert "clean sketch" not in captured["prompt"]
    assert "parent and child" in captured["prompt"]


def test_style_modifier_appended_after_base_style(tmp_path):
    from unittest.mock import patch
    captured = {}

    def fake_render(visual, duration, width, height, work_dir, scene_id, **kwargs):
        captured["prompt"] = visual.get("prompt", "")
        out = work_dir / f"{scene_id}_visual.mp4"
        out.write_bytes(b"fake")
        return out

    with patch("pipeline.composer.image.render_generated_image", side_effect=fake_render):
        from pipeline.composer.base import render_scene
        render_scene(
            {"id": "s7", "visual": {
                "type": "generated_image",
                "prompt": "parent at door",
                "style_modifier": "darker, tense atmosphere",
            }},
            5.0, "16:9", tmp_path,
            theme={"visual_style": "warm semi-realistic"},
        )
    p = captured["prompt"]
    assert "warm semi-realistic" in p
    assert "darker, tense atmosphere" in p
    assert "parent at door" in p
    # order: base_style, modifier, content
    assert p.index("warm semi-realistic") < p.index("darker, tense atmosphere") < p.index("parent at door")


def test_fallback_to_style_prefix_when_no_visual_style(tmp_path):
    from unittest.mock import patch
    captured = {}

    def fake_render(visual, duration, width, height, work_dir, scene_id, **kwargs):
        captured["prompt"] = visual.get("prompt", "")
        out = work_dir / f"{scene_id}_visual.mp4"
        out.write_bytes(b"fake")
        return out

    with patch("pipeline.composer.image.render_generated_image", side_effect=fake_render):
        from pipeline.composer.base import render_scene
        render_scene(
            {"id": "s1", "visual": {"type": "generated_image", "prompt": "content here"}},
            5.0, "16:9", tmp_path,
            theme={"style_prefix": "clean educational sketch"},
        )
    assert "clean educational sketch" in captured["prompt"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_image_style.py::test_visual_style_overrides_style_prefix -v
```
Expected: FAIL (currently `style_prefix` wins regardless)

- [ ] **Step 3: Rewrite style assembly in `render_scene` for `generated_image`**

Replace the `elif visual_type == "generated_image":` block in `src/pipeline/composer/base.py:128-167` with:

```python
elif visual_type == "generated_image":
    from pipeline.composer.image import render_generated_image

    # Style hierarchy: theme.visual_style > theme.style_prefix (niche template) > fallback
    base_style = theme.get("visual_style") or theme.get("style_prefix", "")
    modifier = visual.get("style_modifier", "")
    content = visual.get("prompt", "abstract background")

    parts = [p for p in [base_style, modifier, content] if p]
    visual = {**visual, "prompt": ", ".join(parts)}

    seed_raw = theme.get("_seed")
    seed: int | None = int(seed_raw) if seed_raw is not None else None
    anchor_raw = theme.get("_anchor_image")
    anchor_image: Path | None = Path(anchor_raw) if anchor_raw else None

    gallery_path = Path("output/gallery/gallery_index.json")
    return render_generated_image(
        visual,
        duration_sec,
        width,
        height,
        work_dir,
        scene_id,
        gallery_path=gallery_path,
        niche=theme.get("niche"),
        scene_narration=scene.get("narration", ""),
        theme=theme,
        style_prefix=base_style,
        seed=seed,
        anchor_image=anchor_image,
    )
```

- [ ] **Step 4: Run all image style tests**

```bash
uv run pytest tests/unit/test_image_style.py -v
```
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/composer/base.py tests/unit/test_image_style.py
git commit -m "feat(compose): three-level style hierarchy: visual_style > style_prefix > fallback"
```

---

## Task 3: Create `image_history.py`

**Files:**
- Create: `src/pipeline/composer/image_history.py`
- Create: `tests/unit/test_image_history.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_image_history.py
from __future__ import annotations
import os
import time
from pathlib import Path
import pytest


_FAKE_PNG = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x11\x00\x01\x1b\xb0\xa4G\x00\x00\x00\x00IEND\xaeB`\x82'


def test_save_to_history_creates_timestamped_file(tmp_path):
    from pipeline.composer.image_history import save_to_history
    src = tmp_path / "s5_source.png"
    src.write_bytes(_FAKE_PNG)
    dest = save_to_history(src, "s5", tmp_path)
    assert dest.exists()
    assert dest.parent == tmp_path / "image_history"
    assert dest.name.startswith("s5_")
    assert dest.suffix == ".png"


def test_save_to_history_preserves_content(tmp_path):
    from pipeline.composer.image_history import save_to_history
    src = tmp_path / "s5_source.png"
    src.write_bytes(_FAKE_PNG)
    dest = save_to_history(src, "s5", tmp_path)
    assert dest.read_bytes() == _FAKE_PNG


def test_find_history_returns_most_recent_first(tmp_path):
    from pipeline.composer.image_history import find_history
    hist = tmp_path / "image_history"
    hist.mkdir()
    (hist / "s5_20260427T000000.png").write_bytes(_FAKE_PNG)
    (hist / "s5_20260428T000000.png").write_bytes(_FAKE_PNG)
    entries = find_history("s5", tmp_path)
    assert len(entries) == 2
    assert entries[0][1].name == "s5_20260428T000000.png"


def test_find_history_ignores_other_scenes(tmp_path):
    from pipeline.composer.image_history import find_history
    hist = tmp_path / "image_history"
    hist.mkdir()
    (hist / "s5_20260428T000000.png").write_bytes(_FAKE_PNG)
    (hist / "s12b_20260428T000000.png").write_bytes(_FAKE_PNG)
    entries = find_history("s5", tmp_path)
    assert len(entries) == 1
    assert "s5" in entries[0][1].name


def test_purge_old_removes_stale_entries(tmp_path):
    from pipeline.composer.image_history import purge_old
    hist = tmp_path / "image_history"
    hist.mkdir()
    old = hist / "s5_20260101T000000.png"
    old.write_bytes(_FAKE_PNG)
    # set mtime to 8 days ago
    old_mtime = time.time() - (8 * 24 * 3600)
    os.utime(old, (old_mtime, old_mtime))
    removed = purge_old(tmp_path, max_age_days=7)
    assert removed == 1
    assert not old.exists()


def test_purge_old_keeps_recent_entries(tmp_path):
    from pipeline.composer.image_history import purge_old
    hist = tmp_path / "image_history"
    hist.mkdir()
    recent = hist / "s5_20260428T000000.png"
    recent.write_bytes(_FAKE_PNG)
    removed = purge_old(tmp_path, max_age_days=7)
    assert removed == 0
    assert recent.exists()


def test_purge_old_returns_zero_when_no_history(tmp_path):
    from pipeline.composer.image_history import purge_old
    assert purge_old(tmp_path, max_age_days=7) == 0


def test_restore_scene_copies_most_recent(tmp_path):
    from pipeline.composer.image_history import restore_scene
    hist = tmp_path / "image_history"
    hist.mkdir()
    (hist / "s5_20260427T000000.png").write_bytes(b"old")
    (hist / "s5_20260428T000000.png").write_bytes(b"new")
    result = restore_scene("s5", tmp_path)
    assert result is not None
    assert result == tmp_path / "s5_restore.png"
    assert result.read_bytes() == b"new"


def test_restore_scene_specific_timestamp(tmp_path):
    from pipeline.composer.image_history import restore_scene
    hist = tmp_path / "image_history"
    hist.mkdir()
    (hist / "s5_20260427T000000.png").write_bytes(b"old")
    (hist / "s5_20260428T000000.png").write_bytes(b"new")
    result = restore_scene("s5", tmp_path, timestamp_str="20260427T000000")
    assert result is not None
    assert result.read_bytes() == b"old"


def test_restore_scene_returns_none_when_no_history(tmp_path):
    from pipeline.composer.image_history import restore_scene
    assert restore_scene("s5", tmp_path) is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_image_history.py -v
```
Expected: `ModuleNotFoundError: No module named 'pipeline.composer.image_history'`

- [ ] **Step 3: Implement `image_history.py`**

Create `src/pipeline/composer/image_history.py`:

```python
from __future__ import annotations

import shutil
import time
from datetime import datetime
from pathlib import Path

_HISTORY_DIR = "image_history"
_TS_FMT = "%Y%m%dT%H%M%S"


def _hist_dir(work_dir: Path) -> Path:
    return work_dir / _HISTORY_DIR


def save_to_history(source_png: Path, scene_id: str, work_dir: Path) -> Path:
    """Copy source_png to image_history/{scene_id}_{timestamp}.png before overwriting."""
    d = _hist_dir(work_dir)
    d.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime(_TS_FMT)
    dest = d / f"{scene_id}_{ts}.png"
    shutil.copy2(source_png, dest)
    return dest


def find_history(scene_id: str, work_dir: Path) -> list[tuple[datetime, Path]]:
    """Return (datetime, path) pairs for scene_id, most-recent first."""
    d = _hist_dir(work_dir)
    if not d.exists():
        return []
    results: list[tuple[datetime, Path]] = []
    prefix = f"{scene_id}_"
    for p in d.glob(f"{scene_id}_*.png"):
        ts_str = p.stem[len(prefix):]
        try:
            ts = datetime.strptime(ts_str, _TS_FMT)
            results.append((ts, p))
        except ValueError:
            continue
    return sorted(results, key=lambda x: x[0], reverse=True)


def purge_old(work_dir: Path, max_age_days: int = 7) -> int:
    """Delete history entries older than max_age_days. Returns count deleted."""
    d = _hist_dir(work_dir)
    if not d.exists():
        return 0
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for p in d.glob("*.png"):
        if p.stat().st_mtime < cutoff:
            p.unlink()
            removed += 1
    return removed


def restore_scene(
    scene_id: str, work_dir: Path, timestamp_str: str | None = None
) -> Path | None:
    """Copy a history entry to work_dir/{scene_id}_restore.png. Returns path or None."""
    entries = find_history(scene_id, work_dir)
    if not entries:
        return None
    if timestamp_str:
        matched = [p for ts, p in entries if ts.strftime(_TS_FMT) == timestamp_str]
        if not matched:
            return None
        src = matched[0]
    else:
        _, src = entries[0]
    dest = work_dir / f"{scene_id}_restore.png"
    shutil.copy2(src, dest)
    return dest
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/test_image_history.py -v
```
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/composer/image_history.py tests/unit/test_image_history.py
git commit -m "feat(compose): add image_history module for scene undo (save/find/purge/restore)"
```

---

## Task 4: Create `EditImageProvider`

**Files:**
- Create: `src/pipeline/providers/edit_image.py`
- Create: `tests/unit/test_edit_image_provider.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_edit_image_provider.py
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

    import json, urllib.request

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
    from pipeline.providers.edit_image import EditImageProvider
    import base64, json

    inp = tmp_path / "input.png"
    inp.write_bytes(_FAKE_PNG)
    out = tmp_path / "output.png"

    fake_b64 = base64.b64encode(_FAKE_PNG).decode()

    def fake_urlopen(req, timeout=None):
        resp = MagicMock()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        resp.read.return_value = json.dumps({"data": [{"b64_json": fake_b64}]}).encode()
        return resp

    with patch("pipeline.providers.edit_image._get_key", return_value="fake-key"), \
         patch("urllib.request.urlopen", fake_urlopen):
        result = EditImageProvider().edit_inpaint(inp, "fix expression", out, "1536x1024")

    assert out.exists()
    assert result.read_bytes() == _FAKE_PNG
    assert result.provider == "openai-inpaint"


def test_edit_img2img_raises_on_http_error(tmp_path):
    from pipeline.providers.edit_image import EditImageProvider
    from pipeline.providers.base import ProviderError
    import urllib.error

    inp = tmp_path / "input.png"
    inp.write_bytes(_FAKE_PNG)
    out = tmp_path / "output.png"

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(None, 500, "server error", {}, None)

    with patch("pipeline.providers.edit_image._get_key", return_value="fake-key"), \
         patch("urllib.request.urlopen", fake_urlopen):
        with pytest.raises(ProviderError):
            EditImageProvider().edit_img2img(inp, "fix", 0.3, out)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_edit_image_provider.py -v
```
Expected: `ModuleNotFoundError: No module named 'pipeline.providers.edit_image'`

- [ ] **Step 3: Implement `EditImageProvider`**

Create `src/pipeline/providers/edit_image.py`:

```python
from __future__ import annotations

import base64
import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

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
        """Inpaint / region edit via OpenAI images.edit (gpt-image-1)."""
        from openai import OpenAI
        api_key = _get_key("openai")
        openai_size = _OPENAI_SIZE.get(size, "1536x1024")
        client = OpenAI(api_key=api_key)
        with open(image_path, "rb") as f:
            try:
                response = client.images.edit(
                    model="gpt-image-1",
                    image=f,
                    prompt=prompt,
                    size=openai_size,
                )
            except Exception as exc:
                raise ProviderError(f"OpenAI inpaint failed: {exc}") from exc
        b64_data = response.data[0].b64_json
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(base64.b64decode(b64_data))
        return ProviderResult(path=out_path, provider="openai-inpaint")
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/test_edit_image_provider.py -v
```
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/providers/edit_image.py tests/unit/test_edit_image_provider.py
git commit -m "feat(providers): add EditImageProvider with img2img (fal.ai) and inpaint (OpenAI)"
```

---

## Task 5: Sidecar PNG + Edit Mode Dispatch in `image.py`

**Files:**
- Modify: `src/pipeline/composer/image.py`
- Extend: `tests/unit/test_image_style.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/unit/test_image_style.py
import shutil

def test_sidecar_png_written_after_generation(tmp_path):
    from pipeline.composer.image import render_generated_image

    def fake_chain(providers, prompt, out_path, size):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(_FAKE_PNG)
        return MagicMock(provider="test")

    visual = {"type": "generated_image", "prompt": "parent and child"}
    with patch("pipeline.composer.image.try_chain", side_effect=fake_chain), \
         patch("pipeline.composer.image.image_to_video"):
        render_generated_image(visual, 5.0, 1280, 720, tmp_path, "s5")
    assert (tmp_path / "s5_source.png").exists()


def test_restore_override_used_when_present(tmp_path):
    """If {scene_id}_restore.png exists, it's used directly without API call."""
    from pipeline.composer.image import render_generated_image

    restore = tmp_path / "s5_restore.png"
    restore.write_bytes(_FAKE_PNG)
    called = []

    def fake_chain(*a, **kw):
        called.append(True)
        return MagicMock(provider="test")

    with patch("pipeline.composer.image.try_chain", side_effect=fake_chain), \
         patch("pipeline.composer.image.image_to_video"):
        render_generated_image(
            {"type": "generated_image", "prompt": "test"},
            5.0, 1280, 720, tmp_path, "s5",
        )
    assert not called, "API should not be called when restore.png present"
    assert not restore.exists(), "restore.png should be consumed"
    assert (tmp_path / "s5_source.png").exists()


def test_edit_mode_calls_edit_provider(tmp_path):
    from pipeline.composer.image import render_generated_image

    source = tmp_path / "s5_source.png"
    source.write_bytes(_FAKE_PNG)
    captured = {}

    def fake_edit_img2img(image_path, prompt, strength, out_path, size):
        captured["called"] = True
        captured["strength"] = strength
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(_FAKE_PNG)
        from pipeline.providers.base import ProviderResult
        return ProviderResult(path=out_path, provider="fal-img2img")

    mock_provider = MagicMock()
    mock_provider.edit_img2img.side_effect = fake_edit_img2img

    visual = {
        "type": "generated_image",
        "prompt": "parent and child",
        "edit_mode": True,
        "edit_type": "img2img",
        "edit_instruction": "keep composition, fix style",
        "edit_strength": 0.25,
    }
    with patch("pipeline.composer.image.EditImageProvider", return_value=mock_provider), \
         patch("pipeline.composer.image.save_to_history"), \
         patch("pipeline.composer.image.image_to_video"):
        render_generated_image(visual, 5.0, 1280, 720, tmp_path, "s5")

    assert captured.get("called"), "EditImageProvider.edit_img2img should be called"
    assert captured["strength"] == 0.25


def test_edit_mode_falls_through_when_no_source(tmp_path):
    """With edit_mode=True but no source PNG, falls through to normal generation."""
    from pipeline.composer.image import render_generated_image

    called = []

    def fake_chain(providers, prompt, out_path, size):
        called.append(True)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(_FAKE_PNG)
        return MagicMock(provider="test")

    visual = {
        "type": "generated_image",
        "prompt": "test",
        "edit_mode": True,
        "edit_instruction": "fix it",
    }
    with patch("pipeline.composer.image.try_chain", side_effect=fake_chain), \
         patch("pipeline.composer.image.image_to_video"):
        render_generated_image(visual, 5.0, 1280, 720, tmp_path, "s5")
    assert called, "should fall through to normal generation"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_image_style.py::test_sidecar_png_written_after_generation tests/unit/test_image_style.py::test_edit_mode_calls_edit_provider -v
```
Expected: FAIL

- [ ] **Step 3: Add imports and helper functions to `image.py`**

Add at the top of `src/pipeline/composer/image.py` (after existing imports):

```python
import shutil
```

Add these functions before `render_generated_image`:

```python
def _find_source_png(scene_id: str, work_dir: Path) -> Path | None:
    p = work_dir / f"{scene_id}_source.png"
    return p if p.exists() else None


def _edit_image(
    visual: dict,
    existing_png: Path,
    combined_prompt: str,
    work_dir: Path,
    scene_id: str,
    width: int,
    height: int,
) -> Path | None:
    from pipeline.providers.edit_image import EditImageProvider
    edit_type = visual.get("edit_type", "img2img")
    instruction = visual.get("edit_instruction") or combined_prompt
    strength = float(visual.get("edit_strength", 0.3))
    size = _size_arg(width, height)

    cache_key = _cache_key(f"edit|{edit_type}|{instruction}|{existing_png.stat().st_size}")
    out_png = work_dir / "image_cache" / f"{cache_key}.png"
    out_png.parent.mkdir(parents=True, exist_ok=True)

    provider = EditImageProvider()
    try:
        if edit_type == "img2img":
            provider.edit_img2img(existing_png, instruction, strength, out_png, size)
        elif edit_type == "inpaint":
            provider.edit_inpaint(existing_png, instruction, out_png, size)
        else:
            logger.warning("image.edit.unknown_type", edit_type=edit_type)
            return None
        return out_png
    except Exception as exc:
        logger.warning("image.edit.failed", error=str(exc), scene=scene_id)
        return None
```

- [ ] **Step 4: Rewrite `render_generated_image` to add restore + edit + sidecar logic**

Replace `render_generated_image` in `src/pipeline/composer/image.py` with:

```python
def render_generated_image(
    visual: dict[str, Any],
    duration_sec: float,
    width: int,
    height: int,
    work_dir: Path,
    scene_id: str,
    gallery_path: Path | None = None,
    niche: str | None = None,
    scene_narration: str = "",
    theme: dict | None = None,
    style_prefix: str = "",
    seed: int | None = None,
    anchor_image: Path | None = None,
) -> Path:
    prompt = visual.get("prompt", "abstract background")
    # style_prefix already folded into prompt by base.py; kept as param for tier selection
    tier = visual.get("image_tier", "production" if style_prefix else "draft")

    output = work_dir / f"{scene_id}_visual.mp4"
    sidecar = work_dir / f"{scene_id}_source.png"
    restore = work_dir / f"{scene_id}_restore.png"

    # --- Restore override: use history image directly, skip all generation ---
    if restore.exists():
        logger.info("image.restore_override", scene=scene_id)
        shutil.move(str(restore), str(sidecar))
        image_to_video(sidecar, output, duration_sec, width, height)
        return output

    # --- Edit mode: modify existing sidecar via img2img or inpaint ---
    if visual.get("edit_mode"):
        source_png = _find_source_png(scene_id, work_dir)
        if source_png:
            from pipeline.composer.image_history import save_to_history
            save_to_history(source_png, scene_id, work_dir)
            edited = _edit_image(visual, source_png, prompt, work_dir, scene_id, width, height)
            if edited and edited.exists():
                shutil.copy2(edited, sidecar)
                image_to_video(edited, output, duration_sec, width, height)
                return output
        logger.warning("image.edit_mode.fallback", scene=scene_id,
                       reason="no source PNG found" if not source_png else "edit failed")

    # --- Normal text-to-image generation ---
    cache_dir = work_dir / "image_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_name = _cache_key_with_seed(prompt, seed)
    cached_png = cache_dir / f"{cache_name}.png"

    if cached_png.exists():
        if _is_too_dark(cached_png):
            logger.warning("image.dark_cache_evicted", scene=scene_id)
            cached_png.unlink()
        else:
            logger.info("image.cache_hit", prompt=prompt[:50])

    if not cached_png.exists():
        provider = GenImageProvider(tier=tier)
        try:
            result = try_chain(
                [provider],
                prompt=prompt,
                out_path=cached_png,
                size=_size_arg(width, height),
            )
            logger.info("image.generated", prompt=prompt[:50], provider=result.provider)
            if _is_too_dark(cached_png):
                logger.warning("image.dark_retry", scene=scene_id)
                cached_png.unlink()
                light_prompt = f"{prompt}, white background, bright cream paper, no dark areas"
                light_key = _cache_key_with_seed(light_prompt, seed)
                light_png = cache_dir / f"{light_key}.png"
                try_chain([provider], prompt=light_prompt, out_path=light_png, size=_size_arg(width, height))
                cached_png = light_png
                logger.info("image.dark_retry_done", scene=scene_id, bright=not _is_too_dark(cached_png))
            if gallery_path is not None:
                _write_to_gallery(cached_png, prompt, gallery_path, niche or "", scene_narration)
        except ProviderError as exc:
            logger.warning("image.generation_failed", error=str(exc))
            return _fallback_text_card(scene_narration or prompt, duration_sec, width, height, work_dir, scene_id, theme)

    # Write sidecar for future edit mode use
    if not sidecar.exists():
        shutil.copy2(cached_png, sidecar)

    image_to_video(cached_png, output, duration_sec, width, height)
    return output
```

- [ ] **Step 5: Run all image style tests**

```bash
uv run pytest tests/unit/test_image_style.py -v
```
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/composer/image.py tests/unit/test_image_style.py
git commit -m "feat(compose): sidecar PNG, restore override, edit mode dispatch in render_generated_image"
```

---

## Task 6: Auto-Clear `edit_mode` After Successful Scene Render

**Files:**
- Modify: `src/pipeline/stages/compose.py:256-275`

- [ ] **Step 1: Locate the scene render success point**

In `_compose_from_storyboard`, find the block at ~line 259 where `scene_final.exists()` is False (the else branch). After `visual_path = render_scene(...)` succeeds and before the overlay step, add the auto-clear.

- [ ] **Step 2: Add auto-clear logic**

After the `render_scene` call (after any `except` that falls back to black screen) and before Step 2 (overlay), insert:

```python
# Auto-clear edit_mode after successful render
if (scene.visual or {}).get("edit_mode"):
    scene.visual["edit_mode"] = False
    storyboard.save(ctx.storyboard_path)
    logger.info("compose.edit_mode.cleared", scene_id=scene.id)
```

Place it right after:
```python
except Exception as e:
    logger.warning("compose.scene.visual_failed", ...)
    visual_path = self._black_screen(...)
```
And right before:
```python
# Step 1b: Composite compartment animation if present
```

- [ ] **Step 3: Verify no existing tests break**

```bash
uv run pytest tests/unit/test_cli_compose.py tests/unit/test_image_style.py -v
```
Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add src/pipeline/stages/compose.py
git commit -m "feat(compose): auto-clear edit_mode in storyboard after successful scene render"
```

---

## Task 7: `storyboard set` Dotted `visual.*` Fields

**Files:**
- Modify: `src/pipeline/cli_storyboard.py`
- Create: `tests/unit/test_cli_storyboard_visual.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_cli_storyboard_visual.py
from __future__ import annotations
import json
from pathlib import Path
import pytest
from typer.testing import CliRunner

from pipeline.cli import app

runner = CliRunner()

_MINIMAL_SB = {
    "scenes": [{
        "id": "s5",
        "section": "hook",
        "narration": "test narration",
        "narration_est_sec": 5,
        "pause_after_sec": 0,
        "visual": {"type": "generated_image", "prompt": "parent and child"},
    }],
    "theme": {},
}


def _write_sb(tmp_path: Path) -> Path:
    p = tmp_path / "storyboard.json"
    p.write_text(json.dumps(_MINIMAL_SB))
    return p


def test_set_style_modifier(tmp_path):
    _write_sb(tmp_path)
    result = runner.invoke(app, [
        "storyboard", "set", "s5", "visual.style_modifier=darker, tense",
        "--work-dir", str(tmp_path),
    ])
    assert result.exit_code == 0, result.output
    sb = json.loads((tmp_path / "storyboard.json").read_text())
    assert sb["scenes"][0]["visual"]["style_modifier"] == "darker, tense"


def test_set_edit_mode_true(tmp_path):
    _write_sb(tmp_path)
    result = runner.invoke(app, [
        "storyboard", "set", "s5", "visual.edit_mode=true",
        "--work-dir", str(tmp_path),
    ])
    assert result.exit_code == 0, result.output
    sb = json.loads((tmp_path / "storyboard.json").read_text())
    assert sb["scenes"][0]["visual"]["edit_mode"] is True


def test_set_edit_mode_false(tmp_path):
    _write_sb(tmp_path)
    result = runner.invoke(app, [
        "storyboard", "set", "s5", "visual.edit_mode=false",
        "--work-dir", str(tmp_path),
    ])
    assert result.exit_code == 0
    sb = json.loads((tmp_path / "storyboard.json").read_text())
    assert sb["scenes"][0]["visual"]["edit_mode"] is False


def test_set_edit_strength_coerced_to_float(tmp_path):
    _write_sb(tmp_path)
    result = runner.invoke(app, [
        "storyboard", "set", "s5", "visual.edit_strength=0.25",
        "--work-dir", str(tmp_path),
    ])
    assert result.exit_code == 0
    sb = json.loads((tmp_path / "storyboard.json").read_text())
    assert sb["scenes"][0]["visual"]["edit_strength"] == 0.25


def test_set_edit_type_validated(tmp_path):
    _write_sb(tmp_path)
    result = runner.invoke(app, [
        "storyboard", "set", "s5", "visual.edit_type=bad_value",
        "--work-dir", str(tmp_path),
    ])
    assert result.exit_code != 0


def test_set_unknown_visual_field_rejected(tmp_path):
    _write_sb(tmp_path)
    result = runner.invoke(app, [
        "storyboard", "set", "s5", "visual.unknown_field=value",
        "--work-dir", str(tmp_path),
    ])
    assert result.exit_code != 0


def test_existing_fields_still_work(tmp_path):
    _write_sb(tmp_path)
    result = runner.invoke(app, [
        "storyboard", "set", "s5", "narration=new text",
        "--work-dir", str(tmp_path),
    ])
    assert result.exit_code == 0
    sb = json.loads((tmp_path / "storyboard.json").read_text())
    assert sb["scenes"][0]["narration"] == "new text"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_cli_storyboard_visual.py -v
```
Expected: FAIL on `test_set_style_modifier`

- [ ] **Step 3: Extend `cli_storyboard.py`**

Add after the existing `_ALLOWED_FIELDS` constant in `src/pipeline/cli_storyboard.py`:

```python
_ALLOWED_VISUAL_FIELDS = {"style_modifier", "edit_mode", "edit_type", "edit_instruction", "edit_strength"}


def _coerce_visual_value(field: str, raw: str) -> object:
    if field == "edit_mode":
        if raw.lower() in ("true", "1", "yes"):
            return True
        if raw.lower() in ("false", "0", "no"):
            return False
        raise typer.BadParameter(f"edit_mode must be true/false, got {raw!r}")
    if field == "edit_strength":
        try:
            v = float(raw)
        except ValueError as exc:
            raise typer.BadParameter(f"edit_strength must be a float 0.0–1.0, got {raw!r}") from exc
        if not 0.0 <= v <= 1.0:
            raise typer.BadParameter(f"edit_strength must be 0.0–1.0, got {v}")
        return v
    if field == "edit_type":
        if raw not in ("img2img", "inpaint"):
            raise typer.BadParameter(f"edit_type must be 'img2img' or 'inpaint', got {raw!r}")
        return raw
    return raw
```

Replace the `set_field` command with:

```python
@storyboard_app.command("set")
def set_field(
    scene_id: str = typer.Argument(...),
    assignment: str = typer.Argument(..., help="field=value or visual.subfield=value"),
    work_dir: Path = typer.Option(Path("."), "--work-dir"),
) -> None:
    """Set a safe field on a scene. Use visual.subfield=value for visual sub-fields."""
    if "=" not in assignment:
        raise typer.BadParameter("expected field=value, got " + assignment)
    field, raw_value = assignment.split("=", 1)

    sb = _load_storyboard(work_dir)
    scene = sb.get_scene(scene_id)
    if scene is None:
        raise typer.BadParameter(f"scene '{scene_id}' not found")

    if field.startswith("visual."):
        subfield = field[len("visual."):]
        if subfield not in _ALLOWED_VISUAL_FIELDS:
            raise typer.BadParameter(
                f"'{subfield}' is not a safe visual field; allowed: {sorted(_ALLOWED_VISUAL_FIELDS)}. "
                "Edit storyboard.json directly for other fields."
            )
        value = _coerce_visual_value(subfield, raw_value)
        if scene.visual is None:
            scene.visual = {}
        scene.visual[subfield] = value
        label = f"{scene_id}.visual.{subfield}"
    else:
        if field not in _ALLOWED_FIELDS:
            raise typer.BadParameter(
                f"'{field}' is not a safe field; allowed: {sorted(_ALLOWED_FIELDS)}. "
                "Edit storyboard.json directly for complex fields."
            )
        value = _coerce_value(field, raw_value)
        setattr(scene, field, value)
        label = f"{scene_id}.{field}"

    sb_path = work_dir / "storyboard.json"
    sb.save(sb_path)
    typer.echo(f"updated {label}")

    from pipeline.session_log import SessionEntry, append_session, new_session_id
    append_session(work_dir, SessionEntry(
        session_id=new_session_id(),
        timestamp=datetime.now().isoformat(timespec="seconds"),
        command=f"storyboard set {scene_id} {field}=...",
        summary=f"storyboard set: {label}",
    ))
```

- [ ] **Step 4: Run all storyboard tests**

```bash
uv run pytest tests/unit/test_cli_storyboard_visual.py -v
```
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/cli_storyboard.py tests/unit/test_cli_storyboard_visual.py
git commit -m "feat(cli): storyboard set supports visual.* dotted fields (edit_mode, style_modifier, etc)"
```

---

## Task 8: `compose history` + `compose restore` + Auto-Purge

**Files:**
- Modify: `src/pipeline/cli_compose.py`

- [ ] **Step 1: Add `purge_old` calls to `rescene` and `reburn`**

In `rescene`, after `work_dir = _resolve_work_dir(project_id)`, add:

```python
from pipeline.composer.image_history import purge_old
purge_old(work_dir / "compose" / "scenes")
```

In `reburn`, after `work_dir = _resolve_work_dir(project_id)`, add:

```python
from pipeline.composer.image_history import purge_old
purge_old(work_dir / "compose" / "scenes")
```

- [ ] **Step 2: Add `history` command**

Add at the end of `src/pipeline/cli_compose.py`, before `promote_voice`:

```python
@compose_app.command("history")
def history(
    project_id: int = typer.Option(..., "--project-id"),
    scene: str = typer.Option(..., "--scene"),
) -> None:
    """List image history entries for a scene."""
    from pipeline.composer.image_history import find_history
    work_dir = _resolve_work_dir(project_id)
    scenes_dir = work_dir / "compose" / "scenes"
    entries = find_history(scene, scenes_dir)
    if not entries:
        typer.echo(f"No history for scene '{scene}'")
        return
    now = datetime.now()
    for ts, path in entries:
        age = now - ts
        if age.days:
            age_str = f"{age.days}d ago"
        else:
            age_str = f"{age.seconds // 3600}h ago" if age.seconds >= 3600 else f"{age.seconds // 60}m ago"
        typer.echo(f"  {path.name}  ({age_str})")
```

- [ ] **Step 3: Add `restore` command**

```python
@compose_app.command("restore")
def restore(
    project_id: int = typer.Option(..., "--project-id"),
    scene: str = typer.Option(..., "--scene"),
    timestamp: str | None = typer.Option(None, "--timestamp", help="e.g. 20260428T143022"),
) -> None:
    """Restore most-recent (or timestamped) history entry for a scene, then re-render."""
    from pipeline.composer.image_history import restore_scene
    work_dir = _resolve_work_dir(project_id)
    scenes_dir = work_dir / "compose" / "scenes"

    restore_path = restore_scene(scene, scenes_dir, timestamp)
    if restore_path is None:
        typer.echo(f"No history entries for scene '{scene}'", err=True)
        raise typer.Exit(code=1)

    # Clear scene finals so ComposeStage re-renders this scene
    for suffix in ("_final.mp4", "_final_no_overlay.mp4"):
        p = scenes_dir / f"{scene}{suffix}"
        if p.exists():
            p.unlink()

    typer.echo(f"Restored {restore_path.name} — re-rendering scene {scene}...")
    ctx = PipelineContext.load(work_dir / "context.json")
    entry = SessionEntry(
        session_id=new_session_id(),
        timestamp=datetime.now().isoformat(timespec="seconds"),
        command=f"compose restore --scene {scene}",
    )
    try:
        asyncio.run(ComposeStage().run(ctx))
        entry.summary = f"restore: {scene}"
        typer.echo("Done.")
    except Exception as exc:
        entry.outcome = "failed"
        entry.error = str(exc)[:200]
        entry.summary = f"restore failed: {scene}"
        append_session(work_dir, entry)
        raise
    append_session(work_dir, entry)
```

- [ ] **Step 4: Run existing compose tests**

```bash
uv run pytest tests/unit/test_cli_compose.py -v
```
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/cli_compose.py
git commit -m "feat(cli): add compose history + compose restore; purge_old on rescene/reburn"
```

---

## Task 9: DirectStage Prompt — `visual.prompt` = Concept Only

**Files:**
- Modify: `src/pipeline/stages/direct.py:154-158`

- [ ] **Step 1: Update the `generated_image` entry in VISUAL TYPES**

In `src/pipeline/stages/direct.py`, replace:

```python
- generated_image: {{"type": "generated_image", "prompt": "description", "style": "cinematic"}}
```

with:

```python
- generated_image: {{"type": "generated_image", "prompt": "subject + action + spatial layout + mood — NO style words"}}
  Optional: "style_modifier": "single mood modifier e.g. 'darker tone' or 'soft light'" (NOT full style descriptors)
  RULE: visual.prompt = concept only. Style is global (theme.visual_style). Do NOT write 'watercolor', 'sketch', 'realistic', etc. in prompt.
  Good: "exhausted parent kneeling at toddler eye level in hallway, worried expression"
  Bad:  "warm watercolor illustration of parent kneeling"
```

Also update the shorts storyboard prompt at line ~229 to the same pattern:

```python
- generated_image: {{"type": "generated_image", "prompt": "concept only — no style words"}}
```

- [ ] **Step 2: Verify the pipeline still runs (smoke test)**

```bash
uv run pytest tests/unit/ -v -k "not slow and not network" --tb=short
```
Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add src/pipeline/stages/direct.py
git commit -m "feat(direct): enforce concept-only visual.prompt in storyboard prompt schema"
```

---

## Task 10: Fix Project 1777161293

**Files:**
- Modify: `output/projects/1777161293/storyboard.json`

- [ ] **Step 1: Set `theme.visual_style` and fix scene prompts**

Read the current storyboard, then apply these edits to `output/projects/1777161293/storyboard.json`:

**In `theme` object**, add:
```json
"visual_style": "warm semi-realistic illustration, soft digital painting, cozy domestic setting, gentle charcoal outline"
```

**For every scene** with `visual.type == "generated_image"`, strip style words from `visual.prompt`, keeping only concept/content. Style words to remove: "warm semi-realistic illustration", "soft digital painting", "cozy home interior", "warm domestic", "soft lighting", "children's book aesthetic", "watercolor", "sketch", etc.

**s5** — replace `visual.prompt` with:
```
enormous adult hand and worn shoe filling the frame, tiny toddler fingers gripping the lace tightly refusing to let go, extreme size contrast between parent hand and child
```

**s7b** — strip style words from prompt; the concept (whatever it was) should remain. After setting `theme.visual_style`, a fresh rescene will fix the watercolor drift automatically.

**s12b** — replace `visual.prompt` with:
```
parent standing at closed bedroom door, hand raised to knock, face showing worry and confusion, child silhouette visible through frosted glass turned away unreachable
```

- [ ] **Step 2: Clear cached scene files for affected scenes**

```bash
rm -f /home/tim-huang/content-creation/output/projects/1777161293/compose/scenes/s5_*.mp4
rm -f /home/tim-huang/content-creation/output/projects/1777161293/compose/scenes/s5_source.png
rm -f /home/tim-huang/content-creation/output/projects/1777161293/compose/scenes/s7b_*.mp4
rm -f /home/tim-huang/content-creation/output/projects/1777161293/compose/scenes/s7b_source.png
rm -f /home/tim-huang/content-creation/output/projects/1777161293/compose/scenes/s12b_*.mp4
rm -f /home/tim-huang/content-creation/output/projects/1777161293/compose/scenes/s12b_source.png
```

- [ ] **Step 3: Rescene**

```bash
cd /home/tim-huang/content-creation
uv run pipeline compose rescene --project-id 1777161293 --scene s5 --scene s7b --scene s12b
```
Expected: Three new scene videos rendered. Check dashboard to verify s5 shows size-contrast concept, s7b/s12b match the semi-realistic style of s1.

- [ ] **Step 4: Commit storyboard fix**

```bash
git add output/projects/1777161293/storyboard.json
git commit -m "fix(1777161293): set theme.visual_style; fix s5 concept, s12b concept, s7b style drift"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Style hierarchy (niche → video → scene modifier) — Tasks 1, 2
- [x] `theme.visual_style` field — Task 1
- [x] `visual.style_modifier` field — Tasks 2, 7
- [x] Edit mode fields (`edit_mode`, `edit_type`, `edit_instruction`, `edit_strength`) — Tasks 5, 7
- [x] img2img via fal.ai — Task 4
- [x] inpaint via OpenAI — Task 4
- [x] Edit mode dispatch in `render_generated_image` — Task 5
- [x] Auto-clear `edit_mode` after render — Task 6
- [x] `storyboard set visual.*` dotted fields — Task 7
- [x] Image history: save before overwrite — Task 5 (calls `save_to_history`)
- [x] Image history: `image_history/` module — Task 3
- [x] Auto-purge > 7 days — Tasks 3, 8
- [x] `compose history` CLI — Task 8
- [x] `compose restore` CLI — Task 8
- [x] `storyboard show [hist:N]` — NOT implemented (deferred; adds complexity to show command for minimal gain; can be added as a follow-up)
- [x] DirectStage prompt update — Task 9
- [x] Immediate project 1777161293 fixes — Task 10

**Type consistency:**
- `save_to_history(source_png, scene_id, work_dir)` — matches call in image.py Task 5 ✓
- `purge_old(work_dir / "compose" / "scenes")` — called in cli_compose, implemented in image_history ✓
- `restore_scene(scene, scenes_dir, timestamp)` — used in cli_compose.restore ✓
- `EditImageProvider().edit_img2img(image_path, instruction, strength, out_png, size)` — matches provider definition ✓
- `EditImageProvider().edit_inpaint(image_path, instruction, out_png, size)` — matches provider definition ✓

**Note on `storyboard show [hist:N]`:** Deferred. The `compose history --scene s5` command provides equivalent discoverability with zero changes to the show command.
