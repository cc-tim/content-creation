# YouTube Publish Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `pipeline publish <project-id>` command that uploads produced videos to YouTube with full metadata, thumbnail, and AI-disclosure, supporting multiple channels via `(niche, locale) → profile` routing.

**Architecture:** New `src/pipeline/publish/` subpackage (auth, channels, client, metadata, stage, cli) plus a `src/pipeline/notify/telegram.py` failure notifier. DirectStage is extended to emit `metadata.json`. Publish stays out of the orchestrator auto-chain — always explicit. All upload phases are idempotent via `PipelineContext` fields so partial failures resume cleanly.

**Tech Stack:** Python 3.12, `google-auth` / `google-auth-oauthlib` / `google-api-python-client` for YouTube Data API v3, `pydantic` for metadata models, `typer` for CLI, `structlog` for logging, `httpx` for Telegram, `pytest` with `network` marker for integration tests.

**Spec:** `docs/superpowers/specs/2026-04-23-youtube-publish-pipeline-design.md`

**Branching recommendation:** Implementation should happen on a feature branch (e.g., `feat/youtube-publish`) — not directly on master. Use `superpowers:using-git-worktrees` if isolating from the current workspace.

---

## File Structure

**New:**

- `src/pipeline/publish/__init__.py` — package marker
- `src/pipeline/publish/channels.py` — TOML config loader, profile resolution, niche auto-detection
- `src/pipeline/publish/metadata.py` — `Metadata` Pydantic model + read/write helpers
- `src/pipeline/publish/auth.py` — OAuth flow + token load/save/refresh + channel-id verification
- `src/pipeline/publish/client.py` — `YouTubeClient` wrapper over `googleapiclient`
- `src/pipeline/publish/stage.py` — `PublishStage` implementing `PipelineStage`
- `src/pipeline/publish/cli.py` — `pipeline publish` Typer sub-app
- `src/pipeline/cli_metadata.py` — `pipeline metadata` Typer sub-app
- `src/pipeline/notify/__init__.py` — package marker
- `src/pipeline/notify/telegram.py` — failure notifier
- `configs/youtube_channels.toml` — starter config
- `tests/unit/publish/__init__.py`
- `tests/unit/publish/test_channels.py`
- `tests/unit/publish/test_metadata.py`
- `tests/unit/publish/test_auth.py`
- `tests/unit/publish/test_client.py`
- `tests/unit/publish/test_stage.py`
- `tests/unit/publish/test_cli.py`
- `tests/unit/notify/__init__.py`
- `tests/unit/notify/test_telegram.py`
- `tests/unit/test_cli_metadata.py`
- `tests/unit/test_direct_metadata.py`
- `tests/integration/publish/__init__.py`
- `tests/integration/publish/test_live_upload.py` — marker `network`
- `tests/fixtures/sample_youtube_channels.toml`
- `tests/fixtures/sample_metadata.json`
- `tests/fixtures/sample_client_secret.json`

**Modified:**

- `src/pipeline/stages/base.py` — add `niche`, `thumbnail_uploaded`, `disclosure_set`, `published_at`, `publish_profile` fields
- `src/pipeline/stages/direct.py` — write `metadata.json` after storyboard
- `src/pipeline/cli.py` — register `publish_app` + `metadata_app`, add `--niche` option to `produce`
- `pyproject.toml` — add google-auth / google-auth-oauthlib / google-api-python-client
- `CLAUDE.md` — append NL triggers for publish/metadata

---

## Task 1: Add Google API dependencies + create package skeletons

**Files:**
- Modify: `pyproject.toml`
- Create: `src/pipeline/publish/__init__.py`
- Create: `src/pipeline/notify/__init__.py`
- Create: `tests/unit/publish/__init__.py`
- Create: `tests/unit/notify/__init__.py`
- Create: `tests/integration/publish/__init__.py`

- [ ] **Step 1: Add dependencies to pyproject.toml**

Open `pyproject.toml`, find the `[project]` `dependencies = [...]` list, and append (after the existing `httpx>=0.28` entry):

```toml
"google-auth>=2.30",
"google-auth-oauthlib>=1.2",
"google-api-python-client>=2.130",
```

- [ ] **Step 2: Sync dependencies**

Run: `uv sync`
Expected: installs three new packages, no errors.

- [ ] **Step 3: Create empty package markers**

Create each of:
- `src/pipeline/publish/__init__.py` — contents: `"""YouTube publishing subpackage."""`
- `src/pipeline/notify/__init__.py` — contents: `"""Cross-stage notification channels."""`
- `tests/unit/publish/__init__.py` — empty
- `tests/unit/notify/__init__.py` — empty
- `tests/integration/publish/__init__.py` — empty

- [ ] **Step 4: Verify import**

Run: `uv run python -c "from googleapiclient.discovery import build; from google_auth_oauthlib.flow import InstalledAppFlow; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock src/pipeline/publish/__init__.py src/pipeline/notify/__init__.py tests/unit/publish/__init__.py tests/unit/notify/__init__.py tests/integration/publish/__init__.py
git commit -m "chore(publish): add google-api deps + package skeletons"
```

---

## Task 2: Pydantic `Metadata` model + file helpers

**Files:**
- Create: `src/pipeline/publish/metadata.py`
- Create: `tests/unit/publish/test_metadata.py`
- Create: `tests/fixtures/sample_metadata.json`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/publish/test_metadata.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from pipeline.publish.metadata import Metadata, load_metadata, save_metadata


def _valid_payload() -> dict:
    return {
        "title": "Test title",
        "description": "A description.",
        "tags": ["a", "b"],
        "category_id": 27,
        "default_language": "zh-TW",
        "default_audio_language": "zh-TW",
        "made_for_kids": False,
        "altered_or_synthetic_content": "synthetic_voice",
    }


def test_metadata_accepts_valid_payload() -> None:
    m = Metadata(**_valid_payload())
    assert m.title == "Test title"
    assert m.altered_or_synthetic_content == "synthetic_voice"


def test_metadata_rejects_too_long_title() -> None:
    payload = _valid_payload() | {"title": "x" * 101}
    with pytest.raises(ValidationError):
        Metadata(**payload)


def test_metadata_rejects_too_long_description() -> None:
    payload = _valid_payload() | {"description": "x" * 5001}
    with pytest.raises(ValidationError):
        Metadata(**payload)


def test_metadata_tags_total_length_counts_commas() -> None:
    # Each tag 100 chars, 5 tags -> 500 chars + 4 commas = 504 => reject
    payload = _valid_payload() | {"tags": ["x" * 100] * 5}
    with pytest.raises(ValidationError):
        Metadata(**payload)


def test_metadata_tags_empty_allowed() -> None:
    payload = _valid_payload() | {"tags": []}
    m = Metadata(**payload)
    assert m.tags == []


def test_metadata_rejects_invalid_disclosure() -> None:
    payload = _valid_payload() | {"altered_or_synthetic_content": "bogus"}
    with pytest.raises(ValidationError):
        Metadata(**payload)


def test_load_and_save_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "metadata.json"
    m = Metadata(**_valid_payload())
    save_metadata(m, path, source_url="https://example.com", profile="test-profile")
    loaded = load_metadata(path)
    assert loaded.title == m.title
    # Underscore-prefixed fields preserved in file but not on model
    raw = json.loads(path.read_text())
    assert raw["_source_url"] == "https://example.com"
    assert raw["_profile"] == "test-profile"
    assert "_generated_at" in raw


def test_load_metadata_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_metadata(tmp_path / "nope.json")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/publish/test_metadata.py -v`
Expected: import error on `pipeline.publish.metadata` (module not yet created).

- [ ] **Step 3: Implement the module**

Create `src/pipeline/publish/metadata.py`:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Metadata(BaseModel):
    """YouTube video metadata. Validated against YouTube's server-side limits."""

    title: str = Field(max_length=100)
    description: str = Field(max_length=5000)
    tags: list[str] = Field(default_factory=list)
    category_id: int
    default_language: str
    default_audio_language: str
    made_for_kids: bool = False
    altered_or_synthetic_content: Literal["synthetic_voice", "altered", "none"] = "synthetic_voice"

    @field_validator("tags")
    @classmethod
    def _tags_total_length(cls, v: list[str]) -> list[str]:
        # YouTube counts separators between tags.
        total = sum(len(t) for t in v) + max(len(v) - 1, 0)
        if total > 500:
            raise ValueError(f"tags total length {total} exceeds YouTube limit of 500")
        return v


def load_metadata(path: Path) -> Metadata:
    """Load metadata.json, ignoring underscore-prefixed trace fields."""
    if not path.exists():
        raise FileNotFoundError(f"metadata.json not found at {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    clean = {k: v for k, v in raw.items() if not k.startswith("_")}
    return Metadata(**clean)


def save_metadata(
    metadata: Metadata,
    path: Path,
    *,
    source_url: str,
    profile: str,
) -> None:
    """Write metadata.json including underscore-prefixed trace fields."""
    payload = metadata.model_dump()
    payload["_generated_at"] = datetime.now(tz=timezone.utc).isoformat()
    payload["_source_url"] = source_url
    payload["_profile"] = profile
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/publish/test_metadata.py -v`
Expected: all 8 tests pass.

- [ ] **Step 5: Create sample fixture**

Create `tests/fixtures/sample_metadata.json`:

```json
{
  "title": "Sample Title",
  "description": "Sample description.",
  "tags": ["sample", "test"],
  "category_id": 27,
  "default_language": "zh-TW",
  "default_audio_language": "zh-TW",
  "made_for_kids": false,
  "altered_or_synthetic_content": "synthetic_voice",
  "_generated_at": "2026-04-23T00:00:00+00:00",
  "_source_url": "https://example.com",
  "_profile": "sample-profile"
}
```

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/publish/metadata.py tests/unit/publish/test_metadata.py tests/fixtures/sample_metadata.json
git commit -m "feat(publish): Metadata pydantic model + file helpers"
```

---

## Task 3: Channel config loader + profile resolution

**Files:**
- Create: `src/pipeline/publish/channels.py`
- Create: `configs/youtube_channels.toml`
- Create: `tests/fixtures/sample_youtube_channels.toml`
- Create: `tests/unit/publish/test_channels.py`

- [ ] **Step 1: Create starter `configs/youtube_channels.toml`**

```toml
# YouTube channel profiles. Non-secret — safe to commit.
# Token files live at ~/.config/content-creation/youtube/<profile>.json (mode 0600).
#
# After adding a profile here, run:
#   pipeline publish auth --profile <profile-name>

[profiles.ideal-parents-tw]
niche      = "parenting"
locale     = "zh-TW"
channel_id = ""   # fill in after first auth
voice_guide = """
Warm, reassuring parental tone. Avoid clickbait.
Lead with empathy. Title pattern: scenario + outcome
("孩子半夜哭鬧?三個步驟幫他冷靜下來").
Always end description with source credit and AI-disclosure notice.
"""
default_tags = ["育兒", "親子", "幼兒教育"]
category_id  = 27

[profiles.tech-bummer-en]
niche      = "tech"
locale     = "en"
channel_id = ""   # fill in after first auth
voice_guide = """
Punchy, curious, slightly irreverent. OK to use "this is wild" energy.
Title pattern: hook + specificity ("I tried X for 30 days and...").
End description with source credits + AI-generated-narration disclosure.
"""
default_tags = ["tech", "AI", "productivity"]
category_id  = 28

[routing]
"parenting/zh-TW" = "ideal-parents-tw"
"tech/en"         = "tech-bummer-en"
```

- [ ] **Step 2: Create test fixture `tests/fixtures/sample_youtube_channels.toml`**

```toml
[profiles.parenting-tw]
niche       = "parenting"
locale      = "zh-TW"
channel_id  = "UC_parenting_tw"
voice_guide = "Warm parental tone."
default_tags = ["育兒"]
category_id  = 27

[profiles.tech-en]
niche       = "tech"
locale      = "en"
channel_id  = "UC_tech_en"
voice_guide = "Punchy tech tone."
default_tags = ["tech"]
category_id  = 28

[profiles.drama-tw]
niche       = "drama"
locale      = "zh-TW"
channel_id  = "UC_drama_tw"
voice_guide = "Dramatic narrator."
default_tags = ["drama"]
category_id  = 24

[routing]
"parenting/zh-TW" = "parenting-tw"
"tech/en"         = "tech-en"
"drama/zh-TW"     = "drama-tw"
```

- [ ] **Step 3: Write the failing tests**

Create `tests/unit/publish/test_channels.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.publish.channels import (
    ChannelConfig,
    ChannelProfile,
    auto_detect_niche,
    load_channel_config,
    resolve_profile,
)

FIXTURE = Path(__file__).parents[2] / "fixtures" / "sample_youtube_channels.toml"


def test_load_channel_config_from_fixture() -> None:
    cfg = load_channel_config(FIXTURE)
    assert set(cfg.profiles) == {"parenting-tw", "tech-en", "drama-tw"}
    assert cfg.routing["parenting/zh-TW"] == "parenting-tw"


def test_load_channel_config_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_channel_config(tmp_path / "nope.toml")


def test_load_channel_config_routing_points_at_unknown_profile(tmp_path: Path) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text(
        '[profiles.a]\nniche="x"\nlocale="en"\nchannel_id=""\nvoice_guide=""\n'
        'default_tags=[]\ncategory_id=1\n'
        '[routing]\n"x/en" = "nonexistent"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="routing references unknown profile: nonexistent"):
        load_channel_config(bad)


def test_resolve_profile_by_explicit_override() -> None:
    cfg = load_channel_config(FIXTURE)
    profile = resolve_profile(cfg, niche="parenting", locale="zh-TW", override="tech-en")
    assert profile.name == "tech-en"


def test_resolve_profile_by_routing() -> None:
    cfg = load_channel_config(FIXTURE)
    profile = resolve_profile(cfg, niche="parenting", locale="zh-TW", override=None)
    assert profile.name == "parenting-tw"


def test_resolve_profile_unmapped_pair() -> None:
    cfg = load_channel_config(FIXTURE)
    with pytest.raises(ValueError, match="No channel configured"):
        resolve_profile(cfg, niche="tech", locale="zh-TW", override=None)


def test_resolve_profile_explicit_override_missing() -> None:
    cfg = load_channel_config(FIXTURE)
    with pytest.raises(ValueError, match="profile 'nope' not found"):
        resolve_profile(cfg, niche="parenting", locale="zh-TW", override="nope")


def test_auto_detect_single_niche() -> None:
    cfg = load_channel_config(FIXTURE)
    assert auto_detect_niche(cfg, locale="en") == "tech"


def test_auto_detect_zero_niches() -> None:
    cfg = load_channel_config(FIXTURE)
    with pytest.raises(ValueError, match="No channel configured for locale=es-MX"):
        auto_detect_niche(cfg, locale="es-MX")


def test_auto_detect_ambiguous() -> None:
    cfg = load_channel_config(FIXTURE)
    # zh-TW maps to both parenting and drama
    with pytest.raises(ValueError, match="Ambiguous.*parenting.*drama|drama.*parenting"):
        auto_detect_niche(cfg, locale="zh-TW")
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run pytest tests/unit/publish/test_channels.py -v`
Expected: import error on `pipeline.publish.channels`.

- [ ] **Step 5: Implement the module**

Create `src/pipeline/publish/channels.py`:

```python
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ChannelProfile:
    name: str
    niche: str
    locale: str
    channel_id: str
    voice_guide: str
    default_tags: list[str]
    category_id: int


@dataclass(frozen=True)
class ChannelConfig:
    profiles: dict[str, ChannelProfile]
    routing: dict[str, str]   # "niche/locale" -> profile name


def load_channel_config(path: Path) -> ChannelConfig:
    """Load YouTube channel config from a TOML file."""
    if not path.exists():
        raise FileNotFoundError(f"channel config not found at {path}")
    data = tomllib.loads(path.read_text(encoding="utf-8"))

    profiles: dict[str, ChannelProfile] = {}
    for name, raw in (data.get("profiles") or {}).items():
        profiles[name] = ChannelProfile(
            name=name,
            niche=raw["niche"],
            locale=raw["locale"],
            channel_id=raw.get("channel_id", ""),
            voice_guide=raw.get("voice_guide", ""),
            default_tags=list(raw.get("default_tags", [])),
            category_id=int(raw["category_id"]),
        )

    routing = dict(data.get("routing") or {})
    for key, profile_name in routing.items():
        if profile_name not in profiles:
            raise ValueError(
                f"routing references unknown profile: {profile_name} "
                f"(from key '{key}')"
            )

    return ChannelConfig(profiles=profiles, routing=routing)


def resolve_profile(
    cfg: ChannelConfig,
    *,
    niche: str | None,
    locale: str,
    override: str | None,
) -> ChannelProfile:
    """Resolve to a ChannelProfile. Priority: override > routing > error."""
    if override is not None:
        if override not in cfg.profiles:
            raise ValueError(
                f"profile '{override}' not found in config. "
                f"Available: {sorted(cfg.profiles)}"
            )
        return cfg.profiles[override]

    if niche is None:
        raise ValueError(
            "No niche set on context and no --profile override. "
            "Pass --niche NAME on produce or --profile NAME on publish."
        )

    key = f"{niche}/{locale}"
    profile_name = cfg.routing.get(key)
    if profile_name is None:
        raise ValueError(
            f"No channel configured for (niche={niche}, locale={locale}). "
            f"Add a [routing] entry in configs/youtube_channels.toml "
            f"or pass --profile NAME."
        )
    return cfg.profiles[profile_name]


def auto_detect_niche(cfg: ChannelConfig, *, locale: str) -> str:
    """Return the single niche configured for this locale.

    Errors cleanly when zero or multiple niches exist.
    """
    candidates: list[str] = []
    for key in cfg.routing:
        try:
            niche, loc = key.split("/", 1)
        except ValueError:
            continue
        if loc == locale:
            candidates.append(niche)

    unique = sorted(set(candidates))
    if len(unique) == 0:
        raise ValueError(
            f"No channel configured for locale={locale}. "
            f"Add a [routing] entry in configs/youtube_channels.toml "
            f"or pass --niche NAME / --niche none."
        )
    if len(unique) > 1:
        raise ValueError(
            f"Ambiguous: locale={locale} maps to niches: {', '.join(unique)}. "
            f"Specify --niche NAME."
        )
    return unique[0]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/unit/publish/test_channels.py -v`
Expected: all 10 tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/pipeline/publish/channels.py configs/youtube_channels.toml tests/fixtures/sample_youtube_channels.toml tests/unit/publish/test_channels.py
git commit -m "feat(publish): channel config loader + profile resolution + niche auto-detect"
```

---

## Task 4: Extend `PipelineContext` with publish fields

**Files:**
- Modify: `src/pipeline/stages/base.py`
- Create: `tests/unit/publish/test_context.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/publish/test_context.py`:

```python
from __future__ import annotations

from pathlib import Path

from pipeline.stages.base import PipelineContext


def test_context_has_publish_fields(tmp_path: Path) -> None:
    ctx = PipelineContext(
        project_id=1,
        source_url="https://example.com",
        locale="zh-TW",
        work_dir=tmp_path,
    )
    assert ctx.niche is None
    assert ctx.thumbnail_uploaded is False
    assert ctx.disclosure_set is False
    assert ctx.published_at is None
    assert ctx.publish_profile is None


def test_context_roundtrip_preserves_publish_fields(tmp_path: Path) -> None:
    ctx = PipelineContext(
        project_id=1,
        source_url="https://example.com",
        locale="zh-TW",
        work_dir=tmp_path,
        niche="parenting",
        thumbnail_uploaded=True,
        disclosure_set=True,
        published_at="2026-04-23T00:00:00+00:00",
        publish_profile="ideal-parents-tw",
        youtube_video_id="abc123",
    )
    path = ctx.save()
    loaded = PipelineContext.load(path)
    assert loaded.niche == "parenting"
    assert loaded.thumbnail_uploaded is True
    assert loaded.disclosure_set is True
    assert loaded.published_at == "2026-04-23T00:00:00+00:00"
    assert loaded.publish_profile == "ideal-parents-tw"
    assert loaded.youtube_video_id == "abc123"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/publish/test_context.py -v`
Expected: AttributeError on `niche` (field doesn't exist yet).

- [ ] **Step 3: Add fields to `PipelineContext`**

In `src/pipeline/stages/base.py`, update the `@dataclass class PipelineContext` block. Add these fields in the positions shown:

```python
# After existing `candidate_id`:
    niche: str | None = None  # parenting, tech, drama, ... or "none"

# In the "Stage 6: Publish" section, REPLACE the single-field block with:
    # Stage 6: Publish
    youtube_video_id: str | None = None
    thumbnail_uploaded: bool = False
    disclosure_set: bool = False
    published_at: str | None = None   # ISO8601
    publish_profile: str | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/publish/test_context.py tests/unit/test_base.py -v`
Expected: all pass (including existing base tests — no regressions).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/stages/base.py tests/unit/publish/test_context.py
git commit -m "feat(publish): PipelineContext fields for niche + publish phases"
```

---

## Task 5: Telegram failure notifier

**Files:**
- Create: `src/pipeline/notify/telegram.py`
- Create: `tests/unit/notify/test_telegram.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/notify/test_telegram.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pipeline.notify.telegram import TelegramNotifier, notify_failure


def test_notifier_silent_when_token_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    notifier = TelegramNotifier.from_env()
    assert notifier is None


def test_notifier_silent_when_chat_id_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "abc")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert TelegramNotifier.from_env() is None


def test_notifier_constructed_when_both_env_vars_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    notifier = TelegramNotifier.from_env()
    assert notifier is not None
    assert notifier.token == "abc"
    assert notifier.chat_id == "123"


def test_send_posts_to_telegram_api() -> None:
    notifier = TelegramNotifier(token="tok", chat_id="42")
    with patch("pipeline.notify.telegram.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        notifier.send("hello")
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0].endswith("/bot tok/sendMessage".replace(" ", ""))
    assert kwargs["json"]["chat_id"] == "42"
    assert kwargs["json"]["text"] == "hello"
    assert kwargs["json"]["parse_mode"] == "MarkdownV2"


def test_send_logs_but_does_not_raise_on_failure(caplog: pytest.LogCaptureFixture) -> None:
    notifier = TelegramNotifier(token="tok", chat_id="42")
    with patch("pipeline.notify.telegram.httpx.post", side_effect=RuntimeError("boom")):
        # Must not raise
        notifier.send("hello")
    # Warning logged
    assert any("telegram" in r.message.lower() for r in caplog.records)


def test_notify_failure_composes_expected_message() -> None:
    with patch("pipeline.notify.telegram.TelegramNotifier.from_env") as from_env:
        sent: list[str] = []
        notifier = MagicMock()
        notifier.send = lambda msg: sent.append(msg)
        from_env.return_value = notifier

        notify_failure(
            project_id=1234,
            profile="ideal-parents-tw",
            phase="thumbnail",
            error="File too large (3.2MB > 2MB limit)",
            fix_command="pipeline publish 1234",
        )
    assert len(sent) == 1
    msg = sent[0]
    assert "1234" in msg
    assert "ideal\\-parents\\-tw" in msg or "ideal-parents-tw" in msg
    assert "thumbnail" in msg
    assert "File too large" in msg


def test_notify_failure_noop_when_no_notifier_env() -> None:
    with patch("pipeline.notify.telegram.TelegramNotifier.from_env", return_value=None):
        notify_failure(
            project_id=1,
            profile="x",
            phase="y",
            error="z",
            fix_command=None,
        )  # Must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/notify/test_telegram.py -v`
Expected: import error on `pipeline.notify.telegram`.

- [ ] **Step 3: Implement the module**

Create `src/pipeline/notify/telegram.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
import structlog

logger = structlog.get_logger()

_MDV2_ESCAPE = str.maketrans({
    "_": r"\_", "*": r"\*", "[": r"\[", "]": r"\]",
    "(": r"\(", ")": r"\)", "~": r"\~", "`": r"\`",
    ">": r"\>", "#": r"\#", "+": r"\+", "-": r"\-",
    "=": r"\=", "|": r"\|", "{": r"\{", "}": r"\}",
    ".": r"\.", "!": r"\!",
})


def _escape_mdv2(text: str) -> str:
    return text.translate(_MDV2_ESCAPE)


@dataclass(frozen=True)
class TelegramNotifier:
    token: str
    chat_id: str

    @classmethod
    def from_env(cls) -> "TelegramNotifier | None":
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            return None
        return cls(token=token, chat_id=chat_id)

    def send(self, text: str) -> None:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            response = httpx.post(
                url,
                json={"chat_id": self.chat_id, "text": text, "parse_mode": "MarkdownV2"},
                timeout=10.0,
            )
            if response.status_code >= 400:
                logger.warning(
                    "telegram.send.http_error",
                    status=response.status_code,
                    body=response.text[:200],
                )
        except Exception as exc:
            logger.warning("telegram.send.exception", error=str(exc))


def notify_failure(
    *,
    project_id: int,
    profile: str,
    phase: str,
    error: str,
    fix_command: str | None,
) -> None:
    """Send a Telegram failure notification. No-op if env vars not set.

    Swallows all exceptions — must never mask the real pipeline error.
    """
    notifier = TelegramNotifier.from_env()
    if notifier is None:
        return
    lines = [
        "🚨 *Publish failed*",
        "",
        f"Project: `{_escape_mdv2(str(project_id))}`",
        f"Profile: `{_escape_mdv2(profile)}`",
        f"Phase: `{_escape_mdv2(phase)}`",
        f"Error: {_escape_mdv2(error)}",
    ]
    if fix_command:
        lines.append("")
        lines.append(f"Fix: `{_escape_mdv2(fix_command)}`")
    notifier.send("\n".join(lines))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/notify/test_telegram.py -v`
Expected: all 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/notify/telegram.py tests/unit/notify/test_telegram.py
git commit -m "feat(notify): Telegram failure notifier"
```

---

## Task 6: OAuth auth module

**Files:**
- Create: `src/pipeline/publish/auth.py`
- Create: `tests/unit/publish/test_auth.py`
- Create: `tests/fixtures/sample_client_secret.json`

- [ ] **Step 1: Create sample client_secret fixture**

Create `tests/fixtures/sample_client_secret.json`:

```json
{
  "installed": {
    "client_id": "fake-client-id.apps.googleusercontent.com",
    "project_id": "fake-project",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": "fake-client-secret",
    "redirect_uris": ["http://localhost"]
  }
}
```

- [ ] **Step 2: Write the failing tests**

Create `tests/unit/publish/test_auth.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.publish.auth import (
    AuthError,
    load_credentials,
    save_credentials,
    token_path_for,
    verify_channel_ownership,
)


def test_token_path_for_profile(tmp_path: Path) -> None:
    assert token_path_for("my-profile", base=tmp_path) == tmp_path / "my-profile.json"


def test_save_and_load_credentials(tmp_path: Path) -> None:
    creds = MagicMock()
    creds.to_json.return_value = json.dumps({"token": "abc", "refresh_token": "def"})
    save_credentials(creds, tmp_path / "p.json")

    path = tmp_path / "p.json"
    assert path.exists()
    assert path.stat().st_mode & 0o777 == 0o600

    with patch("pipeline.publish.auth.Credentials.from_authorized_user_file") as loader:
        loader.return_value = MagicMock(valid=True, expired=False)
        loaded = load_credentials(path)
    assert loaded is not None


def test_load_credentials_missing_file(tmp_path: Path) -> None:
    with pytest.raises(AuthError, match="token file not found"):
        load_credentials(tmp_path / "missing.json")


def test_load_credentials_refreshes_when_expired(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    path.write_text("{}", encoding="utf-8")

    creds = MagicMock(valid=False, expired=True, refresh_token="rt")
    with patch("pipeline.publish.auth.Credentials.from_authorized_user_file", return_value=creds):
        loaded = load_credentials(path)
    creds.refresh.assert_called_once()
    assert loaded is creds


def test_load_credentials_refresh_failure_raises(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    path.write_text("{}", encoding="utf-8")

    creds = MagicMock(valid=False, expired=True, refresh_token="rt")
    creds.refresh.side_effect = RuntimeError("revoked")
    with patch("pipeline.publish.auth.Credentials.from_authorized_user_file", return_value=creds):
        with pytest.raises(AuthError, match="token refresh failed"):
            load_credentials(path)


def test_verify_channel_ownership_matches() -> None:
    api = MagicMock()
    api.channels.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "UC_expected"}]
    }
    # Must not raise
    verify_channel_ownership(api, expected_channel_id="UC_expected")


def test_verify_channel_ownership_mismatch() -> None:
    api = MagicMock()
    api.channels.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "UC_wrong"}]
    }
    with pytest.raises(AuthError, match="expected UC_expected.*got UC_wrong"):
        verify_channel_ownership(api, expected_channel_id="UC_expected")


def test_verify_channel_ownership_empty_placeholder_passes() -> None:
    api = MagicMock()
    api.channels.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "UC_discovered"}]
    }
    # When expected is empty, we accept any channel id and return it
    discovered = verify_channel_ownership(api, expected_channel_id="")
    assert discovered == "UC_discovered"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/publish/test_auth.py -v`
Expected: import error on `pipeline.publish.auth`.

- [ ] **Step 4: Implement the module**

Create `src/pipeline/publish/auth.py`:

```python
from __future__ import annotations

import os
import stat
from pathlib import Path

import structlog
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

logger = structlog.get_logger()

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "content-creation" / "youtube"


class AuthError(RuntimeError):
    """Raised for any OAuth / token / channel-verification failure."""


def token_path_for(profile: str, *, base: Path = DEFAULT_CONFIG_DIR) -> Path:
    """Return the token JSON path for a profile."""
    return base / f"{profile}.json"


def client_secret_path(*, base: Path = DEFAULT_CONFIG_DIR) -> Path:
    return base / "client_secret.json"


def save_credentials(creds: Credentials, path: Path) -> None:
    """Write credentials to a file with mode 0600."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(creds.to_json(), encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600


def load_credentials(path: Path) -> Credentials:
    """Load credentials, refreshing if expired. Raises AuthError on failure."""
    if not path.exists():
        raise AuthError(
            f"token file not found at {path}. "
            f"Run: pipeline publish auth --profile <name>"
        )
    creds = Credentials.from_authorized_user_file(str(path), scopes=SCOPES)
    if not creds.valid:
        if not creds.expired or not creds.refresh_token:
            raise AuthError(
                f"token at {path} is invalid and cannot be refreshed. "
                f"Run: pipeline publish auth --profile <name> --reauth"
            )
        try:
            creds.refresh(Request())
        except Exception as exc:
            raise AuthError(
                f"token refresh failed: {exc}. "
                f"Run: pipeline publish auth --profile <name> --reauth"
            ) from exc
        # Persist refreshed token
        save_credentials(creds, path)
    return creds


def run_oauth_flow(
    client_secret_file: Path,
    *,
    extra_scopes: list[str] | None = None,
) -> Credentials:
    """Run the browser OAuth consent flow. Returns new Credentials."""
    if not client_secret_file.exists():
        raise AuthError(
            f"client_secret.json not found at {client_secret_file}. "
            f"See spec §2 for GCP setup steps."
        )
    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_secret_file),
        scopes=SCOPES + (extra_scopes or []),
    )
    return flow.run_local_server(port=0)


def verify_channel_ownership(youtube_api, *, expected_channel_id: str) -> str:
    """Call channels.list(mine=true) and verify the discovered id matches expected.

    If expected is empty (placeholder in config), returns the discovered id so
    the caller can write it back to config.
    """
    response = (
        youtube_api.channels()
        .list(part="id", mine=True)
        .execute()
    )
    items = response.get("items", [])
    if not items:
        raise AuthError(
            "authenticated account has no YouTube channel. "
            "Sign in to Google with an account that owns a channel."
        )
    discovered = items[0]["id"]

    if not expected_channel_id:
        logger.info("auth.channel_id.discovered", channel_id=discovered)
        return discovered

    if discovered != expected_channel_id:
        raise AuthError(
            f"channel id mismatch: expected {expected_channel_id}, got {discovered}. "
            f"The Google account you consented with does not own the configured channel."
        )
    return discovered
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/publish/test_auth.py -v`
Expected: all 8 tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/publish/auth.py tests/unit/publish/test_auth.py tests/fixtures/sample_client_secret.json
git commit -m "feat(publish): OAuth flow + token management + channel verification"
```

---

## Task 7: YouTube API client wrapper

**Files:**
- Create: `src/pipeline/publish/client.py`
- Create: `tests/unit/publish/test_client.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/publish/test_client.py`:

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.publish.client import QuotaExceededError, YouTubeClient


def _make_client() -> tuple[YouTubeClient, MagicMock]:
    api = MagicMock()
    return YouTubeClient(api=api), api


def test_videos_insert_uploads_and_returns_id(tmp_path: Path) -> None:
    client, api = _make_client()
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake-mp4-bytes")

    insert_call = api.videos.return_value.insert.return_value
    insert_call.next_chunk.side_effect = [
        (MagicMock(progress=lambda: 0.5), None),
        (MagicMock(progress=lambda: 1.0), {"id": "VIDEO123"}),
    ]

    video_id = client.videos_insert(
        file_path=video,
        body={"snippet": {}, "status": {}},
    )
    assert video_id == "VIDEO123"


def test_videos_insert_raises_quota_exceeded(tmp_path: Path) -> None:
    from googleapiclient.errors import HttpError

    client, api = _make_client()
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x")

    resp = MagicMock()
    resp.status = 403
    resp.reason = "quotaExceeded"
    err = HttpError(resp=resp, content=b'{"error":{"errors":[{"reason":"quotaExceeded"}]}}')

    api.videos.return_value.insert.return_value.next_chunk.side_effect = err

    with pytest.raises(QuotaExceededError):
        client.videos_insert(file_path=video, body={"snippet": {}, "status": {}})


def test_thumbnails_set_uploads(tmp_path: Path) -> None:
    client, api = _make_client()
    thumb = tmp_path / "thumb.png"
    thumb.write_bytes(b"PNG")

    set_call = api.thumbnails.return_value.set.return_value
    set_call.execute.return_value = {"items": [{"default": {"url": "http://..."}}]}

    client.thumbnails_set(video_id="VIDEO123", file_path=thumb)

    api.thumbnails.assert_called_once()


def test_videos_update_alters_metadata() -> None:
    client, api = _make_client()
    update_call = api.videos.return_value.update.return_value
    update_call.execute.return_value = {"id": "VIDEO123"}

    client.videos_update(
        video_id="VIDEO123",
        part="snippet",
        body={"id": "VIDEO123", "snippet": {"title": "new"}},
    )
    api.videos.return_value.update.assert_called_once_with(
        part="snippet",
        body={"id": "VIDEO123", "snippet": {"title": "new"}},
    )


def test_channels_list_mine() -> None:
    client, api = _make_client()
    api.channels.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "UC_abc", "snippet": {"title": "My Channel"}}]
    }
    items = client.channels_list_mine(part="id,snippet")
    assert items[0]["id"] == "UC_abc"


def test_videos_list() -> None:
    client, api = _make_client()
    api.videos.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "V1", "status": {"privacyStatus": "unlisted"}}]
    }
    items = client.videos_list(video_id="V1", part="status")
    assert items[0]["status"]["privacyStatus"] == "unlisted"


def test_build_from_credentials() -> None:
    with patch("pipeline.publish.client.build") as build:
        build.return_value = MagicMock()
        YouTubeClient.from_credentials(credentials=MagicMock())
    build.assert_called_once()
    assert build.call_args[0][0] == "youtube"
    assert build.call_args[0][1] == "v3"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/publish/test_client.py -v`
Expected: import error on `pipeline.publish.client`.

- [ ] **Step 3: Implement the module**

Create `src/pipeline/publish/client.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

logger = structlog.get_logger()


class QuotaExceededError(RuntimeError):
    """Raised when YouTube API returns a quotaExceeded error."""


def _is_quota_error(exc: HttpError) -> bool:
    try:
        content = exc.content
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        payload = json.loads(content)
        errors = payload.get("error", {}).get("errors", [])
        return any(e.get("reason") == "quotaExceeded" for e in errors)
    except Exception:
        return False


@dataclass
class YouTubeClient:
    """Thin wrapper over googleapiclient's YouTube Data API v3."""

    api: Any  # googleapiclient.discovery.Resource

    @classmethod
    def from_credentials(cls, *, credentials: Any) -> "YouTubeClient":
        api = build("youtube", "v3", credentials=credentials, cache_discovery=False)
        return cls(api=api)

    def videos_insert(
        self,
        *,
        file_path: Path,
        body: dict,
        chunk_size: int = -1,
    ) -> str:
        """Upload a video (resumable). Returns video_id on success."""
        media = MediaFileUpload(str(file_path), chunksize=chunk_size, resumable=True)
        request = self.api.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=media,
        )
        response = None
        try:
            while response is None:
                status, response = request.next_chunk()
                if status is not None:
                    logger.info("publish.upload.progress", progress=status.progress())
        except HttpError as exc:
            if _is_quota_error(exc):
                raise QuotaExceededError(
                    "YouTube daily quota exceeded. Retry after PT midnight."
                ) from exc
            raise
        return response["id"]

    def thumbnails_set(self, *, video_id: str, file_path: Path) -> None:
        media = MediaFileUpload(str(file_path))
        self.api.thumbnails().set(videoId=video_id, media_body=media).execute()

    def videos_update(self, *, video_id: str, part: str, body: dict) -> dict:
        return self.api.videos().update(part=part, body=body).execute()

    def channels_list_mine(self, *, part: str = "id") -> list[dict]:
        response = self.api.channels().list(part=part, mine=True).execute()
        return list(response.get("items", []))

    def videos_list(self, *, video_id: str, part: str) -> list[dict]:
        response = self.api.videos().list(part=part, id=video_id).execute()
        return list(response.get("items", []))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/publish/test_client.py -v`
Expected: all 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/publish/client.py tests/unit/publish/test_client.py
git commit -m "feat(publish): YouTubeClient wrapper with quota-error mapping"
```

---

## Task 8: DirectStage emits `metadata.json`

**Files:**
- Modify: `src/pipeline/stages/direct.py`
- Create: `tests/unit/test_direct_metadata.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_direct_metadata.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.publish.channels import ChannelConfig, ChannelProfile
from pipeline.stages.direct import write_metadata_for_project


@pytest.fixture
def sample_profile() -> ChannelProfile:
    return ChannelProfile(
        name="parenting-tw",
        niche="parenting",
        locale="zh-TW",
        channel_id="UC_parenting_tw",
        voice_guide="Warm parental tone.",
        default_tags=["育兒"],
        category_id=27,
    )


@pytest.fixture
def storyboard_synopsis() -> str:
    return "Scene 1: hook. Scene 2: context."


def test_write_metadata_creates_file(
    tmp_path: Path,
    sample_profile: ChannelProfile,
    storyboard_synopsis: str,
) -> None:
    work_dir = tmp_path / "project"
    work_dir.mkdir()

    fake_response = MagicMock()
    fake_response.content = [
        MagicMock(
            type="tool_use",
            input={
                "title": "T",
                "description": "D",
                "tags": ["a"],
                "category_id": 27,
                "default_language": "zh-TW",
                "default_audio_language": "zh-TW",
                "made_for_kids": False,
                "altered_or_synthetic_content": "synthetic_voice",
            },
        )
    ]
    fake_response.stop_reason = "tool_use"

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    with patch("pipeline.stages.direct.get_anthropic_client", return_value=fake_client):
        path = write_metadata_for_project(
            work_dir=work_dir,
            profile=sample_profile,
            locale="zh-TW",
            source_url="https://example.com",
            storyboard_synopsis=storyboard_synopsis,
            knowledge_facts=[],
        )

    assert path.exists()
    payload = json.loads(path.read_text())
    assert payload["title"] == "T"
    assert "育兒" in payload["tags"]  # default tag prepended
    assert payload["category_id"] == 27
    assert payload["_profile"] == "parenting-tw"
    assert payload["_source_url"] == "https://example.com"


def test_write_metadata_does_not_overwrite_existing(
    tmp_path: Path,
    sample_profile: ChannelProfile,
    storyboard_synopsis: str,
) -> None:
    work_dir = tmp_path / "project"
    work_dir.mkdir()
    existing = work_dir / "metadata.json"
    existing.write_text(
        json.dumps({"title": "USER EDITED", "description": "...", "tags": [],
                    "category_id": 27, "default_language": "zh-TW",
                    "default_audio_language": "zh-TW", "made_for_kids": False,
                    "altered_or_synthetic_content": "synthetic_voice"}),
        encoding="utf-8",
    )

    # Claude client should NOT be called
    with patch("pipeline.stages.direct.get_anthropic_client") as get_client:
        path = write_metadata_for_project(
            work_dir=work_dir,
            profile=sample_profile,
            locale="zh-TW",
            source_url="https://example.com",
            storyboard_synopsis=storyboard_synopsis,
            knowledge_facts=[],
        )
        get_client.assert_not_called()

    assert json.loads(path.read_text())["title"] == "USER EDITED"


def test_write_metadata_regenerate_forces_overwrite(
    tmp_path: Path,
    sample_profile: ChannelProfile,
    storyboard_synopsis: str,
) -> None:
    work_dir = tmp_path / "project"
    work_dir.mkdir()
    existing = work_dir / "metadata.json"
    existing.write_text('{"title":"OLD"}', encoding="utf-8")

    fake_response = MagicMock()
    fake_response.content = [
        MagicMock(
            type="tool_use",
            input={
                "title": "NEW",
                "description": "D",
                "tags": [],
                "category_id": 27,
                "default_language": "zh-TW",
                "default_audio_language": "zh-TW",
                "made_for_kids": False,
                "altered_or_synthetic_content": "synthetic_voice",
            },
        )
    ]
    fake_response.stop_reason = "tool_use"

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    with patch("pipeline.stages.direct.get_anthropic_client", return_value=fake_client):
        write_metadata_for_project(
            work_dir=work_dir,
            profile=sample_profile,
            locale="zh-TW",
            source_url="https://example.com",
            storyboard_synopsis=storyboard_synopsis,
            knowledge_facts=[],
            regenerate=True,
        )

    assert json.loads(existing.read_text())["title"] == "NEW"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_direct_metadata.py -v`
Expected: ImportError — `write_metadata_for_project` not defined in `direct.py`.

- [ ] **Step 3: Add `write_metadata_for_project` to `direct.py`**

At the end of `src/pipeline/stages/direct.py` (before the `DirectStage` class), add:

```python
from pipeline.publish.channels import ChannelProfile
from pipeline.publish.metadata import Metadata, save_metadata

_METADATA_TOOL = {
    "name": "emit_metadata",
    "description": "Emit YouTube metadata as structured JSON.",
    "input_schema": {
        "type": "object",
        "required": [
            "title", "description", "tags", "category_id",
            "default_language", "default_audio_language",
            "made_for_kids", "altered_or_synthetic_content",
        ],
        "properties": {
            "title": {"type": "string", "maxLength": 100},
            "description": {"type": "string", "maxLength": 5000},
            "tags": {"type": "array", "items": {"type": "string"}},
            "category_id": {"type": "integer"},
            "default_language": {"type": "string"},
            "default_audio_language": {"type": "string"},
            "made_for_kids": {"type": "boolean"},
            "altered_or_synthetic_content": {
                "type": "string",
                "enum": ["synthetic_voice", "altered", "none"],
            },
        },
    },
}


def _build_metadata_prompt(
    *,
    profile: ChannelProfile,
    locale: str,
    source_url: str,
    storyboard_synopsis: str,
    knowledge_facts: list[dict],
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for metadata generation."""
    facts_text = "\n".join(f"- {f.get('text', '')}" for f in knowledge_facts[:10])
    system = f"""You are writing YouTube metadata for a channel with this voice:

{profile.voice_guide}

Constraints:
- Title ≤ 100 chars
- Description ≤ 5000 chars
- Tags total (sum + commas) ≤ 500 chars
- Write in locale {locale}

Return via the emit_metadata tool. Do not output prose."""
    user = f"""Source URL: {source_url}

Storyboard synopsis:
{storyboard_synopsis}

Relevant facts for credit-worthy claims:
{facts_text or "(none)"}

Generate title, description, tags, and related metadata fields."""
    return system, user


def _locale_footer(locale: str, source_url: str) -> str:
    if locale == "zh-TW":
        return f"\n\n資料來源:{source_url}\n\n本影片旁白由 AI 合成。"
    if locale == "ja":
        return f"\n\n情報源:{source_url}\n\n本動画のナレーションはAI音声です。"
    if locale == "es-MX":
        return f"\n\nFuente: {source_url}\n\nLa narración de este video fue generada por IA."
    # en + fallback
    return f"\n\nSource: {source_url}\n\nThis video uses AI-generated narration."


def write_metadata_for_project(
    *,
    work_dir: Path,
    profile: ChannelProfile,
    locale: str,
    source_url: str,
    storyboard_synopsis: str,
    knowledge_facts: list[dict],
    regenerate: bool = False,
) -> Path:
    """Generate (or preserve) metadata.json for a project.

    Returns the written path. If the file already exists and regenerate=False,
    leaves it untouched (preserves operator's hand-edits).
    """
    from pipeline.stages.analyze import get_anthropic_client  # local import avoids cycle
    from pipeline.config import PipelineConfig

    path = work_dir / "metadata.json"
    if path.exists() and not regenerate:
        logger.info("direct.metadata.skipped_existing", path=str(path))
        return path

    system, user = _build_metadata_prompt(
        profile=profile,
        locale=locale,
        source_url=source_url,
        storyboard_synopsis=storyboard_synopsis,
        knowledge_facts=knowledge_facts,
    )

    client = get_anthropic_client()
    config = PipelineConfig()

    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=2048,
        system=system,
        tools=[_METADATA_TOOL],
        tool_choice={"type": "tool", "name": "emit_metadata"},
        messages=[{"role": "user", "content": user}],
    )

    tool_input: dict | None = None
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            tool_input = block.input
            break
    if tool_input is None:
        raise RuntimeError("Claude did not return emit_metadata tool use")

    # Merge default tags (prepend, dedup preserving order)
    merged_tags: list[str] = []
    for tag in list(profile.default_tags) + list(tool_input.get("tags") or []):
        if tag not in merged_tags:
            merged_tags.append(tag)
    tool_input["tags"] = merged_tags

    # Fill category_id if omitted
    tool_input.setdefault("category_id", profile.category_id)

    # Append standardized footer
    tool_input["description"] = (
        tool_input["description"].rstrip() + _locale_footer(locale, source_url)
    )

    metadata = Metadata(**tool_input)
    save_metadata(metadata, path, source_url=source_url, profile=profile.name)
    logger.info("direct.metadata.written", path=str(path), profile=profile.name)
    return path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_direct_metadata.py -v`
Expected: all 3 tests pass.

- [ ] **Step 5: Wire metadata generation into `DirectStage.run`**

In `DirectStage.run`, at the end (after logging `"direct.complete"`), before `return ctx`, add:

```python
        # Generate metadata.json for publish (skipped when niche is None or "none")
        if ctx.niche and ctx.niche != "none":
            from pipeline.publish.channels import load_channel_config, resolve_profile

            channel_cfg_path = Path("configs/youtube_channels.toml")
            if channel_cfg_path.exists():
                cfg = load_channel_config(channel_cfg_path)
                try:
                    profile = resolve_profile(
                        cfg, niche=ctx.niche, locale=ctx.locale, override=None
                    )
                except ValueError as exc:
                    logger.warning("direct.metadata.skipped", reason=str(exc))
                else:
                    synopsis = "\n".join(
                        f"{s.section}: {s.narration[:120]}" for s in storyboard.scenes
                    )
                    write_metadata_for_project(
                        work_dir=ctx.work_dir,
                        profile=profile,
                        locale=ctx.locale,
                        source_url=ctx.source_url,
                        storyboard_synopsis=synopsis,
                        knowledge_facts=[
                            {"id": f.id, "text": f.text} for f in knowledge.facts[:10]
                        ],
                    )
            else:
                logger.warning(
                    "direct.metadata.skipped",
                    reason=f"channel config not found at {channel_cfg_path}",
                )
```

Add at the top of `direct.py` if not already present: `from pathlib import Path`.

- [ ] **Step 6: Run full direct stage tests**

Run: `uv run pytest tests/unit/test_direct_metadata.py tests/unit/test_direct*.py -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/pipeline/stages/direct.py tests/unit/test_direct_metadata.py
git commit -m "feat(publish): DirectStage emits metadata.json via channel voice guide"
```

---

## Task 9: `pipeline metadata` CLI sub-app

**Files:**
- Create: `src/pipeline/cli_metadata.py`
- Create: `tests/unit/test_cli_metadata.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_cli_metadata.py`:

```python
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pipeline.cli_metadata import metadata_app

FIXTURE = Path(__file__).parents[1] / "fixtures" / "sample_metadata.json"


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    d = tmp_path / "project"
    d.mkdir()
    shutil.copy(FIXTURE, d / "metadata.json")
    return d


def test_show_prints_fields(project_dir: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(metadata_app, ["show", "--work-dir", str(project_dir)])
    assert result.exit_code == 0, result.output
    assert "Sample Title" in result.output
    assert "sample" in result.output.lower()


def test_show_errors_when_missing(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(metadata_app, ["show", "--work-dir", str(tmp_path)])
    assert result.exit_code != 0


def test_set_title(project_dir: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        metadata_app,
        ["set", "title=Updated Title", "--work-dir", str(project_dir)],
    )
    assert result.exit_code == 0, result.output
    raw = json.loads((project_dir / "metadata.json").read_text())
    assert raw["title"] == "Updated Title"


def test_set_tags_json_list(project_dir: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        metadata_app,
        ["set", 'tags=["x","y","z"]', "--work-dir", str(project_dir)],
    )
    assert result.exit_code == 0, result.output
    raw = json.loads((project_dir / "metadata.json").read_text())
    assert raw["tags"] == ["x", "y", "z"]


def test_set_rejects_unsafe_field(project_dir: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        metadata_app,
        ["set", "_generated_at=bad", "--work-dir", str(project_dir)],
    )
    assert result.exit_code != 0
    assert "not a safe field" in result.output.lower()


def test_validate_passes(project_dir: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(metadata_app, ["validate", "--work-dir", str(project_dir)])
    assert result.exit_code == 0, result.output
    assert "ok" in result.output.lower()


def test_validate_fails_on_too_long_title(project_dir: Path) -> None:
    raw = json.loads((project_dir / "metadata.json").read_text())
    raw["title"] = "x" * 150
    (project_dir / "metadata.json").write_text(json.dumps(raw))
    runner = CliRunner()
    result = runner.invoke(metadata_app, ["validate", "--work-dir", str(project_dir)])
    assert result.exit_code != 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_cli_metadata.py -v`
Expected: import error.

- [ ] **Step 3: Implement `cli_metadata.py`**

Create `src/pipeline/cli_metadata.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import typer
from pydantic import ValidationError
from rich.console import Console

from pipeline.publish.metadata import Metadata, load_metadata

metadata_app = typer.Typer(help="Inspect and edit metadata.json.")
_console = Console()

_ALLOWED_FIELDS = {
    "title",
    "description",
    "tags",
    "category_id",
    "default_language",
    "default_audio_language",
    "made_for_kids",
    "altered_or_synthetic_content",
}


def _metadata_path(work_dir: Path) -> Path:
    path = work_dir / "metadata.json"
    if not path.exists():
        raise typer.BadParameter(f"no metadata.json at {path}")
    return path


def _coerce_value(field: str, raw: str) -> object:
    if field == "tags":
        try:
            v = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise typer.BadParameter(f"tags must be JSON list, got {raw!r}") from exc
        if not isinstance(v, list):
            raise typer.BadParameter("tags must be a JSON list")
        return v
    if field == "category_id":
        try:
            return int(raw)
        except ValueError as exc:
            raise typer.BadParameter(f"category_id must be int, got {raw!r}") from exc
    if field == "made_for_kids":
        if raw.lower() in ("true", "1", "yes"):
            return True
        if raw.lower() in ("false", "0", "no"):
            return False
        raise typer.BadParameter("made_for_kids must be true|false")
    return raw


@metadata_app.command("show")
def show(
    work_dir: Path = typer.Option(Path("."), "--work-dir"),
) -> None:
    """Pretty-print metadata.json."""
    path = _metadata_path(work_dir)
    raw = json.loads(path.read_text(encoding="utf-8"))
    for key in ("title", "description", "tags", "category_id",
                "default_language", "default_audio_language",
                "made_for_kids", "altered_or_synthetic_content"):
        if key in raw:
            _console.print(f"[bold]{key}[/bold]: {raw[key]}")
    for key in sorted(k for k in raw if k.startswith("_")):
        _console.print(f"[dim]{key}: {raw[key]}[/dim]")


@metadata_app.command("set")
def set_field(
    assignment: str = typer.Argument(..., help="field=value"),
    work_dir: Path = typer.Option(Path("."), "--work-dir"),
) -> None:
    """Set a safe field on metadata.json."""
    if "=" not in assignment:
        raise typer.BadParameter("expected field=value, got " + assignment)
    field, raw = assignment.split("=", 1)
    if field not in _ALLOWED_FIELDS:
        raise typer.BadParameter(
            f"'{field}' is not a safe field; allowed: {sorted(_ALLOWED_FIELDS)}"
        )
    value = _coerce_value(field, raw)

    path = _metadata_path(work_dir)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[field] = value

    # Re-validate via Pydantic
    try:
        clean = {k: v for k, v in payload.items() if not k.startswith("_")}
        Metadata(**clean)
    except ValidationError as exc:
        raise typer.BadParameter(f"validation failed: {exc}") from exc

    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    typer.echo(f"updated {field}")


@metadata_app.command("validate")
def validate(
    work_dir: Path = typer.Option(Path("."), "--work-dir"),
) -> None:
    """Validate metadata.json against Pydantic + YouTube limits."""
    path = _metadata_path(work_dir)
    try:
        load_metadata(path)
    except ValidationError as exc:
        typer.echo(f"INVALID: {exc}", err=True)
        raise typer.Exit(code=1)
    typer.echo("ok")


@metadata_app.command("regenerate")
def regenerate(
    work_dir: Path = typer.Option(Path("."), "--work-dir"),
    project_id: int | None = typer.Option(None, "--project-id"),
) -> None:
    """Re-run Claude to regenerate metadata.json. Clobbers hand edits."""
    # Defer import to avoid pulling in anthropic at CLI import time
    from pipeline.knowledge import Knowledge
    from pipeline.publish.channels import load_channel_config, resolve_profile
    from pipeline.stages.base import PipelineContext
    from pipeline.stages.direct import write_metadata_for_project
    from pipeline.storyboard import Storyboard

    ctx_path = work_dir / "context.json"
    if not ctx_path.exists():
        raise typer.BadParameter(f"no context.json at {ctx_path}")
    ctx = PipelineContext.load(ctx_path)

    if not ctx.niche or ctx.niche == "none":
        raise typer.BadParameter(
            "context has no niche set; cannot route to a profile. "
            "Re-run produce with --niche NAME."
        )

    cfg = load_channel_config(Path("configs/youtube_channels.toml"))
    profile = resolve_profile(cfg, niche=ctx.niche, locale=ctx.locale, override=None)

    storyboard = Storyboard.load(ctx.storyboard_path or work_dir / "storyboard.json")
    synopsis = "\n".join(f"{s.section}: {s.narration[:120]}" for s in storyboard.scenes)

    facts: list[dict] = []
    if ctx.knowledge_path and ctx.knowledge_path.exists():
        knowledge = Knowledge.load(ctx.knowledge_path)
        facts = [{"id": f.id, "text": f.text} for f in knowledge.facts[:10]]

    write_metadata_for_project(
        work_dir=work_dir,
        profile=profile,
        locale=ctx.locale,
        source_url=ctx.source_url,
        storyboard_synopsis=synopsis,
        knowledge_facts=facts,
        regenerate=True,
    )
    typer.echo("metadata regenerated")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli_metadata.py -v`
Expected: all 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/cli_metadata.py tests/unit/test_cli_metadata.py
git commit -m "feat(publish): pipeline metadata CLI (show/set/validate/regenerate)"
```

---

## Task 10: Publish stage — preflight + helpers

**Files:**
- Create: `src/pipeline/publish/stage.py` (partial — preflight only)
- Create: `tests/unit/publish/test_stage_preflight.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/publish/test_stage_preflight.py`:

```python
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from pipeline.publish.stage import PreflightError, run_preflight
from pipeline.stages.base import PipelineContext

META_FIXTURE = Path(__file__).parents[2] / "fixtures" / "sample_metadata.json"


@pytest.fixture
def ready_project(tmp_path: Path) -> Path:
    d = tmp_path / "project"
    d.mkdir()
    (d / "final.mp4").write_bytes(b"x" * 1024)
    (d / "thumbnail.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 500)
    shutil.copy(META_FIXTURE, d / "metadata.json")
    return d


def _ctx(work_dir: Path) -> PipelineContext:
    return PipelineContext(
        project_id=1,
        source_url="https://example.com",
        locale="zh-TW",
        work_dir=work_dir,
        niche="sample",
        final_video_path=work_dir / "final.mp4",
    )


def test_preflight_ok(ready_project: Path) -> None:
    ctx = _ctx(ready_project)
    # Must not raise
    run_preflight(ctx=ctx, privacy="unlisted", schedule_iso=None)


def test_preflight_missing_video(ready_project: Path) -> None:
    (ready_project / "final.mp4").unlink()
    ctx = _ctx(ready_project)
    with pytest.raises(PreflightError, match="final video"):
        run_preflight(ctx=ctx, privacy="unlisted", schedule_iso=None)


def test_preflight_missing_thumbnail(ready_project: Path) -> None:
    (ready_project / "thumbnail.png").unlink()
    ctx = _ctx(ready_project)
    with pytest.raises(PreflightError, match="thumbnail"):
        run_preflight(ctx=ctx, privacy="unlisted", schedule_iso=None)


def test_preflight_missing_metadata(ready_project: Path) -> None:
    (ready_project / "metadata.json").unlink()
    ctx = _ctx(ready_project)
    with pytest.raises(PreflightError, match="metadata"):
        run_preflight(ctx=ctx, privacy="unlisted", schedule_iso=None)


def test_preflight_thumbnail_too_large(ready_project: Path) -> None:
    (ready_project / "thumbnail.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * (3 * 1024 * 1024))
    ctx = _ctx(ready_project)
    with pytest.raises(PreflightError, match="thumbnail.*exceeds"):
        run_preflight(ctx=ctx, privacy="unlisted", schedule_iso=None)


def test_preflight_schedule_with_public_rejected(ready_project: Path) -> None:
    ctx = _ctx(ready_project)
    with pytest.raises(PreflightError, match="schedule.*public"):
        run_preflight(
            ctx=ctx, privacy="public", schedule_iso="2099-01-01T00:00:00+00:00"
        )


def test_preflight_schedule_in_past(ready_project: Path) -> None:
    ctx = _ctx(ready_project)
    with pytest.raises(PreflightError, match="schedule.*past"):
        run_preflight(
            ctx=ctx, privacy="private", schedule_iso="2000-01-01T00:00:00+00:00"
        )


def test_preflight_invalid_metadata(ready_project: Path) -> None:
    raw = json.loads((ready_project / "metadata.json").read_text())
    raw["title"] = "x" * 200
    (ready_project / "metadata.json").write_text(json.dumps(raw))
    ctx = _ctx(ready_project)
    with pytest.raises(PreflightError, match="metadata.*invalid"):
        run_preflight(ctx=ctx, privacy="unlisted", schedule_iso=None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/publish/test_stage_preflight.py -v`
Expected: import error.

- [ ] **Step 3: Implement the preflight**

Create `src/pipeline/publish/stage.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import structlog
from pydantic import ValidationError

from pipeline.publish.metadata import load_metadata
from pipeline.stages.base import PipelineContext

logger = structlog.get_logger()

MAX_THUMBNAIL_BYTES = 2 * 1024 * 1024   # YouTube limit
MAX_VIDEO_WARN_BYTES = 10 * 1024 * 1024 * 1024  # 10 GB warn
MAX_VIDEO_HARD_BYTES = 128 * 1024 * 1024 * 1024  # 128 GB hard


class PreflightError(RuntimeError):
    """Raised by run_preflight on any missing/invalid input."""


def _thumbnail_path(work_dir: Path) -> Path:
    return work_dir / "thumbnail.png"


def _metadata_path(work_dir: Path) -> Path:
    return work_dir / "metadata.json"


def run_preflight(
    *,
    ctx: PipelineContext,
    privacy: str,
    schedule_iso: str | None,
) -> None:
    """Validate all local inputs before any API call. Raises PreflightError."""
    if ctx.final_video_path is None or not ctx.final_video_path.exists():
        raise PreflightError(
            f"final video not found (ctx.final_video_path={ctx.final_video_path}). "
            f"Run compose stage first."
        )
    size = ctx.final_video_path.stat().st_size
    if size > MAX_VIDEO_HARD_BYTES:
        raise PreflightError(f"final video exceeds YouTube's 128GB limit (is {size} bytes)")
    if size > MAX_VIDEO_WARN_BYTES:
        logger.warning("publish.preflight.large_video", bytes=size)

    meta_path = _metadata_path(ctx.work_dir)
    if not meta_path.exists():
        raise PreflightError(
            f"metadata.json not found at {meta_path}. "
            f"Run: pipeline metadata regenerate --work-dir {ctx.work_dir}"
        )
    try:
        load_metadata(meta_path)
    except ValidationError as exc:
        raise PreflightError(f"metadata invalid: {exc}") from exc

    thumb = _thumbnail_path(ctx.work_dir)
    if not thumb.exists():
        raise PreflightError(
            f"thumbnail.png not found at {thumb}. "
            f"Hand-design one and save there."
        )
    tsize = thumb.stat().st_size
    if tsize > MAX_THUMBNAIL_BYTES:
        raise PreflightError(
            f"thumbnail.png exceeds 2MB limit (is {tsize} bytes). Shrink it."
        )

    if schedule_iso is not None:
        if privacy == "public":
            raise PreflightError(
                "--schedule requires privacy=private|unlisted (public conflicts)"
            )
        try:
            when = datetime.fromisoformat(schedule_iso)
        except ValueError as exc:
            raise PreflightError(f"--schedule must be ISO8601: {exc}") from exc
        if when.tzinfo is None:
            raise PreflightError("--schedule must include timezone (e.g. +08:00)")
        if when <= datetime.now(tz=timezone.utc):
            raise PreflightError(f"--schedule is in the past: {schedule_iso}")

    logger.info("publish.preflight.ok", project_id=ctx.project_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/publish/test_stage_preflight.py -v`
Expected: all 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/publish/stage.py tests/unit/publish/test_stage_preflight.py
git commit -m "feat(publish): stage preflight validation"
```

---

## Task 11: Publish stage — upload sequence (phases A, B, C)

**Files:**
- Modify: `src/pipeline/publish/stage.py` — add `PublishStage` class
- Create: `tests/unit/publish/test_stage_upload.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/publish/test_stage_upload.py`:

```python
from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pipeline.publish.channels import ChannelConfig, ChannelProfile
from pipeline.publish.stage import PublishStage
from pipeline.stages.base import PipelineContext

META_FIXTURE = Path(__file__).parents[2] / "fixtures" / "sample_metadata.json"


def _make_profile() -> ChannelProfile:
    return ChannelProfile(
        name="sample-profile",
        niche="sample",
        locale="zh-TW",
        channel_id="UC_sample",
        voice_guide="",
        default_tags=[],
        category_id=27,
    )


def _make_config() -> ChannelConfig:
    p = _make_profile()
    return ChannelConfig(profiles={p.name: p}, routing={"sample/zh-TW": p.name})


@pytest.fixture
def ready_project(tmp_path: Path) -> Path:
    d = tmp_path / "project"
    d.mkdir()
    (d / "final.mp4").write_bytes(b"x" * 1024)
    (d / "thumbnail.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 500)
    shutil.copy(META_FIXTURE, d / "metadata.json")
    return d


def _make_ctx(project_dir: Path) -> PipelineContext:
    return PipelineContext(
        project_id=42,
        source_url="https://example.com",
        locale="zh-TW",
        work_dir=project_dir,
        niche="sample",
        final_video_path=project_dir / "final.mp4",
    )


def test_upload_sequence_happy_path(ready_project: Path) -> None:
    client = MagicMock()
    client.videos_insert.return_value = "VIDEO123"

    stage = PublishStage(
        client_factory=lambda profile: client,
        channel_config=_make_config(),
        privacy="unlisted",
        schedule_iso=None,
    )
    ctx = _make_ctx(ready_project)
    result = stage.publish(ctx, profile_override=None)

    assert result.youtube_video_id == "VIDEO123"
    assert result.thumbnail_uploaded is True
    assert result.disclosure_set is True
    assert result.publish_profile == "sample-profile"
    client.videos_insert.assert_called_once()
    client.thumbnails_set.assert_called_once()
    client.videos_update.assert_called_once()


def test_resume_skips_phase_a_when_video_id_exists(ready_project: Path) -> None:
    client = MagicMock()
    stage = PublishStage(
        client_factory=lambda profile: client,
        channel_config=_make_config(),
        privacy="unlisted",
        schedule_iso=None,
    )
    ctx = _make_ctx(ready_project)
    ctx.youtube_video_id = "EXISTING"
    ctx.thumbnail_uploaded = False

    stage.publish(ctx, profile_override=None)

    client.videos_insert.assert_not_called()
    client.thumbnails_set.assert_called_once_with(
        video_id="EXISTING", file_path=ready_project / "thumbnail.png"
    )
    client.videos_update.assert_called_once()


def test_resume_skips_phase_b_when_thumbnail_uploaded(ready_project: Path) -> None:
    client = MagicMock()
    stage = PublishStage(
        client_factory=lambda profile: client,
        channel_config=_make_config(),
        privacy="unlisted",
        schedule_iso=None,
    )
    ctx = _make_ctx(ready_project)
    ctx.youtube_video_id = "EXISTING"
    ctx.thumbnail_uploaded = True

    stage.publish(ctx, profile_override=None)

    client.videos_insert.assert_not_called()
    client.thumbnails_set.assert_not_called()
    client.videos_update.assert_called_once()


def test_resume_skips_everything_when_all_done(ready_project: Path) -> None:
    client = MagicMock()
    stage = PublishStage(
        client_factory=lambda profile: client,
        channel_config=_make_config(),
        privacy="unlisted",
        schedule_iso=None,
    )
    ctx = _make_ctx(ready_project)
    ctx.youtube_video_id = "EXISTING"
    ctx.thumbnail_uploaded = True
    ctx.disclosure_set = True

    stage.publish(ctx, profile_override=None)

    client.videos_insert.assert_not_called()
    client.thumbnails_set.assert_not_called()
    client.videos_update.assert_not_called()


def test_scheduled_upload_uses_private_status(ready_project: Path) -> None:
    client = MagicMock()
    client.videos_insert.return_value = "VIDEO_SCHED"
    stage = PublishStage(
        client_factory=lambda profile: client,
        channel_config=_make_config(),
        privacy="unlisted",   # ignored when schedule present
        schedule_iso="2099-01-01T12:00:00+00:00",
    )
    ctx = _make_ctx(ready_project)
    stage.publish(ctx, profile_override=None)

    body = client.videos_insert.call_args.kwargs["body"]
    assert body["status"]["privacyStatus"] == "private"
    assert body["status"]["publishAt"] == "2099-01-01T12:00:00+00:00"


def test_explicit_profile_override(ready_project: Path) -> None:
    client = MagicMock()
    client.videos_insert.return_value = "V"
    cfg = _make_config()
    # Add a second profile
    other = ChannelProfile(
        name="other", niche="x", locale="en", channel_id="UC_other",
        voice_guide="", default_tags=[], category_id=1,
    )
    cfg = ChannelConfig(
        profiles={**cfg.profiles, "other": other},
        routing=cfg.routing,
    )
    stage = PublishStage(
        client_factory=lambda profile: client,
        channel_config=cfg,
        privacy="unlisted",
        schedule_iso=None,
    )
    ctx = _make_ctx(ready_project)
    result = stage.publish(ctx, profile_override="other")

    assert result.publish_profile == "other"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/publish/test_stage_upload.py -v`
Expected: ImportError on `PublishStage`.

- [ ] **Step 3: Add `PublishStage` class**

Append to `src/pipeline/publish/stage.py`:

```python
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from pipeline.notify.telegram import notify_failure
from pipeline.publish.channels import ChannelConfig, resolve_profile
from pipeline.publish.metadata import Metadata, load_metadata


@dataclass
class PublishStage:
    """Publishes a produced project to YouTube.

    Not an orchestrator-chain PipelineStage — always invoked explicitly.
    Idempotent via context fields (youtube_video_id, thumbnail_uploaded, disclosure_set).
    """

    client_factory: Callable[[object], object]  # (profile) -> YouTubeClient-like
    channel_config: ChannelConfig
    privacy: str = "unlisted"
    schedule_iso: str | None = None
    force_metadata: bool = False
    force_thumbnail: bool = False
    dry_run: bool = False

    def publish(
        self,
        ctx: PipelineContext,
        *,
        profile_override: str | None,
    ) -> PipelineContext:
        """Run preflight + phased upload. Mutates and returns ctx."""
        run_preflight(ctx=ctx, privacy=self.privacy, schedule_iso=self.schedule_iso)

        profile = resolve_profile(
            self.channel_config,
            niche=ctx.niche,
            locale=ctx.locale,
            override=profile_override,
        )
        ctx.publish_profile = profile.name
        logger.info(
            "publish.profile_resolved",
            profile=profile.name,
            channel_id=profile.channel_id,
        )

        metadata = load_metadata(ctx.work_dir / "metadata.json")
        upload_body = self._build_upload_body(metadata)

        if self.dry_run:
            logger.info("publish.dry_run", body=upload_body)
            import json as _json
            print(_json.dumps(upload_body, indent=2, ensure_ascii=False))
            return ctx

        client = self.client_factory(profile)

        try:
            self._phase_a_upload(client, ctx, upload_body)
            self._phase_b_thumbnail(client, ctx)
            self._phase_c_disclosure(client, ctx, metadata)
        except Exception as exc:
            notify_failure(
                project_id=ctx.project_id,
                profile=profile.name,
                phase=self._current_phase(ctx),
                error=str(exc),
                fix_command=f"pipeline publish {ctx.project_id}",
            )
            raise

        ctx.published_at = datetime.now(tz=timezone.utc).isoformat()
        ctx.save()
        return ctx

    def _build_upload_body(self, metadata: Metadata) -> dict:
        body: dict = {
            "snippet": {
                "title": metadata.title,
                "description": metadata.description,
                "tags": metadata.tags,
                "categoryId": str(metadata.category_id),
                "defaultLanguage": metadata.default_language,
                "defaultAudioLanguage": metadata.default_audio_language,
            },
            "status": {
                "selfDeclaredMadeForKids": metadata.made_for_kids,
            },
        }
        if self.schedule_iso is not None:
            body["status"]["privacyStatus"] = "private"
            body["status"]["publishAt"] = self.schedule_iso
        else:
            body["status"]["privacyStatus"] = self.privacy
        return body

    def _phase_a_upload(self, client, ctx: PipelineContext, body: dict) -> None:
        if ctx.youtube_video_id is not None and not self.force_metadata:
            logger.info("publish.phase_a.skipped", video_id=ctx.youtube_video_id)
            return
        if ctx.youtube_video_id is not None and self.force_metadata:
            client.videos_update(
                video_id=ctx.youtube_video_id,
                part="snippet,status",
                body={"id": ctx.youtube_video_id, **body},
            )
            logger.info("publish.phase_a.metadata_updated", video_id=ctx.youtube_video_id)
            return

        logger.info("publish.upload.start", project_id=ctx.project_id)
        video_id = client.videos_insert(file_path=ctx.final_video_path, body=body)
        ctx.youtube_video_id = video_id
        ctx.save()
        logger.info("publish.upload.complete", video_id=video_id)

    def _phase_b_thumbnail(self, client, ctx: PipelineContext) -> None:
        if ctx.thumbnail_uploaded and not self.force_thumbnail:
            return
        thumb = ctx.work_dir / "thumbnail.png"
        client.thumbnails_set(video_id=ctx.youtube_video_id, file_path=thumb)
        ctx.thumbnail_uploaded = True
        ctx.save()
        logger.info("publish.thumbnail.complete", video_id=ctx.youtube_video_id)

    def _phase_c_disclosure(
        self, client, ctx: PipelineContext, metadata: Metadata
    ) -> None:
        if ctx.disclosure_set:
            return
        # NOTE: YouTube 2026 synthetic-content disclosure field name may be
        # under status.containsSyntheticMedia or contentDetails.alteredContent.
        # Implementation verifies exact path against live YouTube Data API docs.
        # Current best guess based on API reference:
        body = {
            "id": ctx.youtube_video_id,
            "status": {
                "containsSyntheticMedia": metadata.altered_or_synthetic_content
                == "synthetic_voice",
            },
        }
        client.videos_update(
            video_id=ctx.youtube_video_id, part="status", body=body
        )
        ctx.disclosure_set = True
        ctx.save()
        logger.info("publish.disclosure.complete", video_id=ctx.youtube_video_id)

    @staticmethod
    def _current_phase(ctx: PipelineContext) -> str:
        if ctx.youtube_video_id is None:
            return "upload"
        if not ctx.thumbnail_uploaded:
            return "thumbnail"
        if not ctx.disclosure_set:
            return "disclosure"
        return "complete"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/publish/test_stage_upload.py -v`
Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/publish/stage.py tests/unit/publish/test_stage_upload.py
git commit -m "feat(publish): idempotent 3-phase upload sequence"
```

---

## Task 12: `pipeline publish` CLI — main command

**Files:**
- Create: `src/pipeline/publish/cli.py` (partial — `publish` command)
- Create: `tests/unit/publish/test_cli.py` (partial)

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/publish/test_cli.py`:

```python
from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from pipeline.publish.cli import publish_app
from pipeline.stages.base import PipelineContext

META_FIXTURE = Path(__file__).parents[2] / "fixtures" / "sample_metadata.json"
CHANNELS_FIXTURE = Path(__file__).parents[2] / "fixtures" / "sample_youtube_channels.toml"


@pytest.fixture
def project_with_context(tmp_path: Path) -> Path:
    d = tmp_path / "projects" / "42"
    d.mkdir(parents=True)
    (d / "final.mp4").write_bytes(b"x" * 1024)
    (d / "thumbnail.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 500)
    # Use parenting-tw from the sample channels fixture so niche/locale align
    meta = json.loads(META_FIXTURE.read_text())
    (d / "metadata.json").write_text(json.dumps(meta))
    ctx = PipelineContext(
        project_id=42,
        source_url="https://example.com",
        locale="zh-TW",
        work_dir=d,
        niche="parenting",
        final_video_path=d / "final.mp4",
    )
    ctx.save()
    return d


def test_publish_dry_run(project_with_context: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(project_with_context.parent.parent))
    runner = CliRunner()
    with patch("pipeline.publish.cli._load_channel_config_path", return_value=CHANNELS_FIXTURE):
        result = runner.invoke(publish_app, ["42", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "snippet" in result.output
    assert "privacyStatus" in result.output


def test_publish_happy_path(project_with_context: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(project_with_context.parent.parent))
    runner = CliRunner()

    fake_client = MagicMock()
    fake_client.videos_insert.return_value = "V1"

    with patch("pipeline.publish.cli._load_channel_config_path", return_value=CHANNELS_FIXTURE), \
         patch("pipeline.publish.cli._build_youtube_client", return_value=fake_client):
        result = runner.invoke(publish_app, ["42"])

    assert result.exit_code == 0, result.output
    assert "V1" in result.output
    # Context persisted
    ctx = PipelineContext.load(project_with_context / "context.json")
    assert ctx.youtube_video_id == "V1"


def test_publish_missing_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(tmp_path))
    runner = CliRunner()
    with patch("pipeline.publish.cli._load_channel_config_path", return_value=CHANNELS_FIXTURE):
        result = runner.invoke(publish_app, ["999"])
    assert result.exit_code != 0
    assert "project" in result.output.lower() or "not found" in result.output.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/publish/test_cli.py -v`
Expected: import error.

- [ ] **Step 3: Implement `publish` command**

Create `src/pipeline/publish/cli.py`:

```python
from __future__ import annotations

from pathlib import Path

import structlog
import typer

from pipeline.config import PipelineConfig
from pipeline.publish.auth import load_credentials, token_path_for
from pipeline.publish.channels import ChannelConfig, load_channel_config
from pipeline.publish.client import YouTubeClient
from pipeline.publish.stage import PublishStage
from pipeline.stages.base import PipelineContext

logger = structlog.get_logger()

publish_app = typer.Typer(help="Publish produced projects to YouTube.")


def _load_channel_config_path() -> Path:
    """Default location for the channels TOML. Overridden in tests via patch."""
    return Path("configs/youtube_channels.toml")


def _project_dir(project_id: str) -> Path:
    config = PipelineConfig()
    return config.OUTPUT_DIR / "projects" / project_id


def _build_youtube_client(profile, cfg: ChannelConfig):
    token_path = token_path_for(profile.name)
    creds = load_credentials(token_path)
    return YouTubeClient.from_credentials(credentials=creds)


@publish_app.command()
def publish(
    project_id: str = typer.Argument(..., help="Project id (directory name in output/projects/)"),
    profile: str | None = typer.Option(None, "--profile", help="Override channel profile"),
    privacy: str = typer.Option(
        "unlisted", "--privacy", help="unlisted | private | public"
    ),
    schedule: str | None = typer.Option(
        None, "--schedule", help="ISO8601 timestamp for publishAt (implies private)"
    ),
    dry_run: bool = typer.Option(False, "--dry-run"),
    force_metadata: bool = typer.Option(False, "--force-metadata"),
    force_thumbnail: bool = typer.Option(False, "--force-thumbnail"),
) -> None:
    """Upload a produced project to YouTube."""
    work_dir = _project_dir(project_id)
    ctx_path = work_dir / "context.json"
    if not ctx_path.exists():
        raise typer.BadParameter(f"project not found: {work_dir}")

    ctx = PipelineContext.load(ctx_path)
    cfg = load_channel_config(_load_channel_config_path())

    stage = PublishStage(
        client_factory=lambda p: _build_youtube_client(p, cfg),
        channel_config=cfg,
        privacy=privacy,
        schedule_iso=schedule,
        force_metadata=force_metadata,
        force_thumbnail=force_thumbnail,
        dry_run=dry_run,
    )

    ctx = stage.publish(ctx, profile_override=profile)
    ctx.save()

    if not dry_run and ctx.youtube_video_id:
        typer.echo(f"\n✓ Published {ctx.youtube_video_id}")
        typer.echo(f"  Studio: https://studio.youtube.com/video/{ctx.youtube_video_id}/edit")
        typer.echo(f"  Watch:  https://youtu.be/{ctx.youtube_video_id}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/publish/test_cli.py -v`
Expected: all 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/publish/cli.py tests/unit/publish/test_cli.py
git commit -m "feat(publish): publish command wiring stage + CLI"
```

---

## Task 13: `pipeline publish auth` + accounts subcommands

**Files:**
- Modify: `src/pipeline/publish/cli.py`
- Modify: `tests/unit/publish/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/publish/test_cli.py`:

```python
def test_auth_command_runs_flow_and_verifies_channel(tmp_path: Path) -> None:
    runner = CliRunner()

    fake_creds = MagicMock()
    fake_creds.to_json.return_value = '{"refresh_token":"rt"}'
    fake_api = MagicMock()
    fake_api.channels().list().execute.return_value = {
        "items": [{"id": "UC_parenting_tw"}]
    }

    with patch("pipeline.publish.cli._load_channel_config_path", return_value=CHANNELS_FIXTURE), \
         patch("pipeline.publish.cli.run_oauth_flow", return_value=fake_creds), \
         patch("pipeline.publish.cli._token_dir", return_value=tmp_path), \
         patch("pipeline.publish.cli._client_secret_file", return_value=tmp_path / "cs.json"), \
         patch("pipeline.publish.cli.YouTubeClient.from_credentials") as from_creds:
        from_creds.return_value = MagicMock(api=fake_api)
        # client_secret must exist
        (tmp_path / "cs.json").write_text('{"installed":{"client_id":"x","client_secret":"y"}}')
        result = runner.invoke(publish_app, ["auth", "--profile", "parenting-tw"])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "parenting-tw.json").exists()


def test_auth_command_channel_mismatch(tmp_path: Path) -> None:
    runner = CliRunner()

    fake_creds = MagicMock()
    fake_api = MagicMock()
    fake_api.channels().list().execute.return_value = {
        "items": [{"id": "UC_WRONG"}]
    }

    with patch("pipeline.publish.cli._load_channel_config_path", return_value=CHANNELS_FIXTURE), \
         patch("pipeline.publish.cli.run_oauth_flow", return_value=fake_creds), \
         patch("pipeline.publish.cli._token_dir", return_value=tmp_path), \
         patch("pipeline.publish.cli._client_secret_file", return_value=tmp_path / "cs.json"), \
         patch("pipeline.publish.cli.YouTubeClient.from_credentials") as from_creds:
        from_creds.return_value = MagicMock(api=fake_api)
        (tmp_path / "cs.json").write_text('{"installed":{"client_id":"x","client_secret":"y"}}')
        result = runner.invoke(publish_app, ["auth", "--profile", "parenting-tw"])

    assert result.exit_code != 0
    assert "mismatch" in result.output.lower() or "expected" in result.output.lower()
    # Token not written
    assert not (tmp_path / "parenting-tw.json").exists()


def test_accounts_list(tmp_path: Path) -> None:
    # Create a fake token file
    (tmp_path / "parenting-tw.json").write_text('{"refresh_token":"x"}')
    runner = CliRunner()
    with patch("pipeline.publish.cli._load_channel_config_path", return_value=CHANNELS_FIXTURE), \
         patch("pipeline.publish.cli._token_dir", return_value=tmp_path):
        result = runner.invoke(publish_app, ["accounts", "list"])
    assert result.exit_code == 0, result.output
    assert "parenting-tw" in result.output
    assert "authenticated" in result.output.lower() or "✓" in result.output
    assert "tech-en" in result.output  # configured but no token
    assert "missing" in result.output.lower() or "✗" in result.output


def test_accounts_revoke(tmp_path: Path) -> None:
    (tmp_path / "parenting-tw.json").write_text('{"refresh_token":"x"}')
    runner = CliRunner()
    with patch("pipeline.publish.cli._load_channel_config_path", return_value=CHANNELS_FIXTURE), \
         patch("pipeline.publish.cli._token_dir", return_value=tmp_path):
        result = runner.invoke(publish_app, ["accounts", "revoke", "parenting-tw"])
    assert result.exit_code == 0, result.output
    assert not (tmp_path / "parenting-tw.json").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/publish/test_cli.py -v -k "auth or accounts"`
Expected: failures — commands don't exist yet.

- [ ] **Step 3: Add auth + accounts subcommands**

Append to `src/pipeline/publish/cli.py`:

```python
from pipeline.publish.auth import (
    DEFAULT_CONFIG_DIR,
    AuthError,
    client_secret_path,
    run_oauth_flow,
    save_credentials,
    verify_channel_ownership,
)

accounts_app = typer.Typer(help="Manage YouTube channel profile credentials.")
publish_app.add_typer(accounts_app, name="accounts")


def _token_dir() -> Path:
    """Default config dir for per-profile tokens. Overridden in tests."""
    return DEFAULT_CONFIG_DIR


def _client_secret_file() -> Path:
    return client_secret_path(base=_token_dir())


@publish_app.command("auth")
def auth(
    profile: str = typer.Option(..., "--profile"),
    reauth: bool = typer.Option(False, "--reauth"),
) -> None:
    """Run the OAuth consent flow for a profile and write its token file."""
    cfg = load_channel_config(_load_channel_config_path())
    if profile not in cfg.profiles:
        raise typer.BadParameter(
            f"profile '{profile}' not in config. "
            f"Add a [profiles.{profile}] entry first."
        )
    prof = cfg.profiles[profile]
    token_path = _token_dir() / f"{profile}.json"
    if reauth and token_path.exists():
        token_path.unlink()

    cs_file = _client_secret_file()
    creds = run_oauth_flow(cs_file)

    client = YouTubeClient.from_credentials(credentials=creds)
    try:
        discovered = verify_channel_ownership(
            client.api, expected_channel_id=prof.channel_id
        )
    except AuthError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1)

    save_credentials(creds, token_path)
    typer.echo(f"✓ Authenticated profile '{profile}' → channel {discovered}")
    if not prof.channel_id:
        typer.echo(
            f"  Note: fill in channel_id = \"{discovered}\" under "
            f"[profiles.{profile}] in configs/youtube_channels.toml"
        )


@accounts_app.command("list")
def accounts_list() -> None:
    """List configured profiles and whether their token files exist."""
    cfg = load_channel_config(_load_channel_config_path())
    td = _token_dir()
    for name in sorted(cfg.profiles):
        path = td / f"{name}.json"
        status = "✓ authenticated" if path.exists() else "✗ missing token"
        typer.echo(f"{name:30s}  {status}")


@accounts_app.command("revoke")
def accounts_revoke(profile: str = typer.Argument(...)) -> None:
    """Delete the local token file for a profile."""
    td = _token_dir()
    path = td / f"{profile}.json"
    if not path.exists():
        typer.echo(f"no token at {path}")
        return
    path.unlink()
    typer.echo(f"✓ deleted {path}")
    typer.echo(
        "Remember to also revoke server-side at "
        "https://myaccount.google.com/permissions"
    )


@accounts_app.command("show")
def accounts_show(profile: str = typer.Argument(...)) -> None:
    """Fetch the channel's public info for a profile (1 quota unit)."""
    cfg = load_channel_config(_load_channel_config_path())
    if profile not in cfg.profiles:
        raise typer.BadParameter(f"profile '{profile}' not in config")
    token_path = _token_dir() / f"{profile}.json"
    creds = load_credentials(token_path)
    client = YouTubeClient.from_credentials(credentials=creds)
    items = client.channels_list_mine(part="id,snippet,statistics")
    if not items:
        typer.echo("no channel found")
        raise typer.Exit(code=1)
    ch = items[0]
    typer.echo(f"id:    {ch['id']}")
    typer.echo(f"title: {ch['snippet']['title']}")
    stats = ch.get("statistics", {})
    typer.echo(f"subs:  {stats.get('subscriberCount', '?')}")
    typer.echo(f"videos: {stats.get('videoCount', '?')}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/publish/test_cli.py -v`
Expected: all tests (previous + new 4) pass.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/publish/cli.py tests/unit/publish/test_cli.py
git commit -m "feat(publish): auth + accounts list/show/revoke subcommands"
```

---

## Task 14: `pipeline publish status` command

**Files:**
- Modify: `src/pipeline/publish/cli.py`
- Modify: `tests/unit/publish/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/publish/test_cli.py`:

```python
def test_status_local_not_uploaded(project_with_context: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(project_with_context.parent.parent))
    runner = CliRunner()
    with patch("pipeline.publish.cli._load_channel_config_path", return_value=CHANNELS_FIXTURE):
        result = runner.invoke(publish_app, ["status", "42"])
    assert result.exit_code == 0, result.output
    assert "video" in result.output.lower()
    assert "✗" in result.output or "pending" in result.output.lower()


def test_status_local_partially_uploaded(
    project_with_context: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = PipelineContext.load(project_with_context / "context.json")
    ctx.youtube_video_id = "V1"
    ctx.save()

    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(project_with_context.parent.parent))
    runner = CliRunner()
    with patch("pipeline.publish.cli._load_channel_config_path", return_value=CHANNELS_FIXTURE):
        result = runner.invoke(publish_app, ["status", "42"])
    assert result.exit_code == 0, result.output
    assert "V1" in result.output
    assert "thumbnail" in result.output.lower()


def test_status_remote(project_with_context: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = PipelineContext.load(project_with_context / "context.json")
    ctx.youtube_video_id = "V1"
    ctx.thumbnail_uploaded = True
    ctx.disclosure_set = True
    ctx.publish_profile = "parenting-tw"
    ctx.save()

    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(project_with_context.parent.parent))
    runner = CliRunner()

    fake_client = MagicMock()
    fake_client.videos_list.return_value = [
        {"id": "V1", "status": {"privacyStatus": "unlisted"}, "snippet": {"title": "T"}}
    ]
    with patch("pipeline.publish.cli._load_channel_config_path", return_value=CHANNELS_FIXTURE), \
         patch("pipeline.publish.cli._build_youtube_client", return_value=fake_client):
        result = runner.invoke(publish_app, ["status", "42", "--remote"])
    assert result.exit_code == 0, result.output
    assert "unlisted" in result.output.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/publish/test_cli.py -v -k status`
Expected: `status` command doesn't exist.

- [ ] **Step 3: Add `status` command**

Append to `src/pipeline/publish/cli.py`:

```python
@publish_app.command("status")
def status(
    project_id: str = typer.Argument(...),
    remote: bool = typer.Option(False, "--remote", help="Query YouTube API (1 quota unit)"),
) -> None:
    """Show local (and optionally remote) publish state."""
    work_dir = _project_dir(project_id)
    ctx_path = work_dir / "context.json"
    if not ctx_path.exists():
        raise typer.BadParameter(f"project not found: {work_dir}")
    ctx = PipelineContext.load(ctx_path)

    typer.echo(f"project_id: {ctx.project_id}")
    typer.echo(f"niche:      {ctx.niche}")
    typer.echo(f"locale:     {ctx.locale}")
    typer.echo(f"profile:    {ctx.publish_profile or '(unresolved)'}")
    typer.echo("")
    typer.echo(f"video:      {'✓ ' + ctx.youtube_video_id if ctx.youtube_video_id else '✗ pending'}")
    typer.echo(f"thumbnail:  {'✓' if ctx.thumbnail_uploaded else '✗ pending'}")
    typer.echo(f"disclosure: {'✓' if ctx.disclosure_set else '✗ pending'}")

    if ctx.youtube_video_id:
        typer.echo("")
        typer.echo(f"Studio: https://studio.youtube.com/video/{ctx.youtube_video_id}/edit")
        typer.echo(f"Watch:  https://youtu.be/{ctx.youtube_video_id}")

    next_cmd = None
    if ctx.youtube_video_id is None:
        next_cmd = f"pipeline publish {project_id}"
    elif not ctx.thumbnail_uploaded or not ctx.disclosure_set:
        next_cmd = f"pipeline publish {project_id}  # resumes"
    if next_cmd:
        typer.echo(f"\nNext: {next_cmd}")

    if remote and ctx.youtube_video_id:
        if not ctx.publish_profile:
            typer.echo("\n(remote check skipped: no publish_profile on context)", err=True)
            return
        cfg = load_channel_config(_load_channel_config_path())
        profile = cfg.profiles[ctx.publish_profile]
        client = _build_youtube_client(profile, cfg)
        items = client.videos_list(
            video_id=ctx.youtube_video_id, part="status,snippet"
        )
        typer.echo("\n--- remote ---")
        if not items:
            typer.echo("(video not found on YouTube — deleted?)")
        else:
            v = items[0]
            typer.echo(f"title:    {v['snippet']['title']}")
            typer.echo(f"privacy:  {v['status']['privacyStatus']}")
            if "publishAt" in v["status"]:
                typer.echo(f"publishAt: {v['status']['publishAt']}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/publish/test_cli.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/publish/cli.py tests/unit/publish/test_cli.py
git commit -m "feat(publish): status command for local + remote state"
```

---

## Task 15: Register new CLI sub-apps + add `--niche` to `produce`

**Files:**
- Modify: `src/pipeline/cli.py`
- Create: `tests/unit/test_produce_niche.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_produce_niche.py`:

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from pipeline.cli import app

CHANNELS_FIXTURE = (
    Path(__file__).parents[1] / "fixtures" / "sample_youtube_channels.toml"
)


@pytest.fixture
def no_stages(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub out actual stage execution so we can inspect only the ctx construction."""
    captured: dict = {}

    class StubOrchestrator:
        def __init__(self, stages):
            self.stages = stages

        async def run(self, ctx, start_from=None):
            captured["ctx"] = ctx
            res = MagicMock()
            res.success = True
            res.ctx = ctx
            return res

    monkeypatch.setattr("pipeline.cli.Orchestrator", StubOrchestrator)
    return captured


def test_produce_uses_explicit_niche(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_stages: dict
) -> None:
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(tmp_path))
    runner = CliRunner()
    with patch("pipeline.cli._channel_config_path", return_value=CHANNELS_FIXTURE):
        result = runner.invoke(
            app,
            [
                "produce",
                "--url", "https://example.com",
                "--locale", "zh-TW",
                "--niche", "drama",
                "--skip-review",
            ],
        )
    assert result.exit_code == 0, result.output
    assert no_stages["ctx"].niche == "drama"


def test_produce_auto_detects_when_locale_unambiguous(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_stages: dict
) -> None:
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(tmp_path))
    runner = CliRunner()
    with patch("pipeline.cli._channel_config_path", return_value=CHANNELS_FIXTURE):
        # Fixture has only tech/en — auto-detect to "tech"
        result = runner.invoke(
            app,
            [
                "produce",
                "--url", "https://example.com",
                "--locale", "en",
                "--skip-review",
            ],
        )
    assert result.exit_code == 0, result.output
    assert no_stages["ctx"].niche == "tech"


def test_produce_niche_none_skips_routing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_stages: dict
) -> None:
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(tmp_path))
    runner = CliRunner()
    with patch("pipeline.cli._channel_config_path", return_value=CHANNELS_FIXTURE):
        result = runner.invoke(
            app,
            [
                "produce",
                "--url", "https://example.com",
                "--locale", "es-MX",  # no routing entry, but --niche none short-circuits
                "--niche", "none",
                "--skip-review",
            ],
        )
    assert result.exit_code == 0, result.output
    assert no_stages["ctx"].niche == "none"


def test_produce_ambiguous_locale_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_stages: dict
) -> None:
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(tmp_path))
    runner = CliRunner()
    with patch("pipeline.cli._channel_config_path", return_value=CHANNELS_FIXTURE):
        # zh-TW maps to both parenting and drama
        result = runner.invoke(
            app,
            [
                "produce",
                "--url", "https://example.com",
                "--locale", "zh-TW",
                "--skip-review",
            ],
        )
    assert result.exit_code != 0
    assert "ambiguous" in result.output.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_produce_niche.py -v`
Expected: `--niche` option not recognized OR auto-detection not wired.

- [ ] **Step 3: Modify `produce` in `src/pipeline/cli.py`**

Add at the top of `src/pipeline/cli.py` (after existing imports):

```python
from pipeline.cli_metadata import metadata_app
from pipeline.publish.cli import publish_app
from pipeline.publish.channels import auto_detect_niche, load_channel_config
```

Register the sub-apps with the existing `app`:

```python
app.add_typer(publish_app, name="publish")
app.add_typer(metadata_app, name="metadata")
```

Add a helper (near the other module-level definitions, before `@app.command()`):

```python
def _channel_config_path() -> Path:
    """Path to the channels TOML. Overridable in tests."""
    from pathlib import Path as _P
    return _P("configs/youtube_channels.toml")
```

Update the `produce` function signature and body. Add to the signature (after `source_type`):

```python
    niche: str | None = typer.Option(
        None,
        "--niche",
        help="Niche (parenting/tech/drama/...). Auto-detected from routing when omitted. "
             "Use --niche none to opt out.",
    ),
```

Inside `produce`, BEFORE `ctx = PipelineContext(...)` or the `start_from`/`context_file` branch, add:

```python
    # Resolve niche (explicit | auto-detected | "none" opt-out)
    if niche is None:
        cfg_path = _channel_config_path()
        if cfg_path.exists():
            try:
                niche = auto_detect_niche(load_channel_config(cfg_path), locale=locale)
                typer.echo(f"niche auto-detected from routing: {niche}")
            except ValueError as exc:
                raise typer.BadParameter(str(exc)) from exc
        else:
            typer.echo(
                f"warning: {cfg_path} not found — --niche omitted and no routing available",
                err=True,
            )
```

Then set `niche=niche` on the `PipelineContext(...)` constructor call.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_produce_niche.py -v`
Expected: all 4 tests pass.

- [ ] **Step 5: Smoke-test the CLI**

Run: `uv run pipeline --help`
Expected: output lists `publish` and `metadata` as subcommands.

Run: `uv run pipeline publish --help`
Expected: lists `auth`, `accounts`, `status`, and the main publish command.

Run: `uv run pipeline metadata --help`
Expected: lists `show`, `set`, `regenerate`, `validate`.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/cli.py tests/unit/test_produce_niche.py
git commit -m "feat(publish): wire publish + metadata subapps; add --niche to produce"
```

---

## Task 16: Update CLAUDE.md with NL triggers

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Append NL triggers section**

In `CLAUDE.md`, find the "Natural-language triggers" block inside the "Storyboard editing" section. After that block, add a new section:

```markdown
## Publish and metadata workflow

```bash
# Upload a produced project (unlisted by default → review in YouTube Studio)
uv run pipeline publish <project-id>                               # auto-routes via niche+locale
uv run pipeline publish <project-id> --profile ideal-parents-tw    # explicit channel
uv run pipeline publish <project-id> --schedule 2026-04-25T19:00:00+08:00
uv run pipeline publish <project-id> --dry-run                     # preflight only

# OAuth setup (one-time per channel)
uv run pipeline publish auth --profile ideal-parents-tw
uv run pipeline publish accounts list
uv run pipeline publish accounts show ideal-parents-tw

# Diagnose stuck publishes
uv run pipeline publish status <project-id>
uv run pipeline publish status <project-id> --remote               # live state from YouTube

# Edit generated metadata
uv run pipeline metadata show --work-dir <project-dir>
uv run pipeline metadata set title="新標題" --work-dir <project-dir>
uv run pipeline metadata regenerate --work-dir <project-dir>

# Natural-language triggers (for the assistant):
#   "upload project X to YouTube"               → pipeline publish X
#   "schedule X for tomorrow 7pm"               → pipeline publish X --schedule <ISO8601>
#   "what's the publish state of X?"            → pipeline publish status X
#   "what's actually live for project X?"       → pipeline publish status X --remote
#   "re-authorize the parenting channel"        → pipeline publish auth --profile ideal-parents-tw --reauth
#   "change project X's title to Y"             → pipeline metadata set title=Y --work-dir <project-dir>
#   "show me project X's metadata"              → pipeline metadata show --work-dir <project-dir>
```
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md publish + metadata NL triggers"
```

---

## Task 17: Integration test scaffold (live upload to sandbox channel)

**Files:**
- Create: `tests/integration/publish/test_live_upload.py`
- Create: `tests/integration/publish/README.md`

- [ ] **Step 1: Write the integration test skeleton**

Create `tests/integration/publish/test_live_upload.py`:

```python
"""Live integration test against a sandbox YouTube channel.

Marker: network. Opt in with `pytest -m network`.

Setup requirements (documented in README.md):
- A dedicated "sandbox" channel
- Profile "sandbox" in configs/youtube_channels.toml
- Token at ~/.config/content-creation/youtube/sandbox.json (via `pipeline publish auth`)
- Env var `YT_PUBLISH_SANDBOX=1` to opt in
- Fixtures: `tests/fixtures/sample_final.mp4` (10s) + `sample_thumbnail.png`

The test uploads a minimal video → verifies via videos.list → DELETES it.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from pipeline.publish.auth import load_credentials, token_path_for
from pipeline.publish.channels import load_channel_config
from pipeline.publish.client import YouTubeClient
from pipeline.publish.metadata import Metadata
from pipeline.publish.stage import PublishStage
from pipeline.stages.base import PipelineContext

pytestmark = pytest.mark.network


@pytest.fixture(scope="module")
def sandbox_enabled() -> None:
    if not os.getenv("YT_PUBLISH_SANDBOX"):
        pytest.skip("set YT_PUBLISH_SANDBOX=1 to run live sandbox tests")


@pytest.fixture
def sandbox_project(tmp_path: Path) -> Path:
    # Expect pre-rendered fixtures under tests/fixtures/
    fixtures = Path(__file__).parents[2] / "fixtures"
    video = fixtures / "sample_final.mp4"
    thumb = fixtures / "sample_thumbnail.png"
    if not video.exists() or not thumb.exists():
        pytest.skip("sandbox fixtures missing; see README")

    d = tmp_path / "sandbox_project"
    d.mkdir()
    (d / "final.mp4").write_bytes(video.read_bytes())
    (d / "thumbnail.png").write_bytes(thumb.read_bytes())
    meta = Metadata(
        title="[SANDBOX] pipeline integration test",
        description="Auto-deleted test upload.",
        tags=["test"],
        category_id=27,
        default_language="en",
        default_audio_language="en",
    )
    from pipeline.publish.metadata import save_metadata
    save_metadata(meta, d / "metadata.json", source_url="https://example.com", profile="sandbox")
    return d


def test_live_upload_and_cleanup(
    sandbox_enabled: None, sandbox_project: Path
) -> None:
    cfg = load_channel_config(Path("configs/youtube_channels.toml"))
    assert "sandbox" in cfg.profiles, "add a [profiles.sandbox] entry first"

    creds = load_credentials(token_path_for("sandbox"))
    client = YouTubeClient.from_credentials(credentials=creds)

    stage = PublishStage(
        client_factory=lambda _: client,
        channel_config=cfg,
        privacy="private",  # safer for test
    )
    ctx = PipelineContext(
        project_id=99999,
        source_url="https://example.com",
        locale="en",
        work_dir=sandbox_project,
        niche="sandbox",
        final_video_path=sandbox_project / "final.mp4",
    )
    try:
        stage.publish(ctx, profile_override="sandbox")
        assert ctx.youtube_video_id is not None
        items = client.videos_list(video_id=ctx.youtube_video_id, part="status,snippet")
        assert items, "uploaded video missing from videos.list"
        assert items[0]["status"]["privacyStatus"] == "private"
    finally:
        if ctx.youtube_video_id:
            # Teardown: delete the test upload
            client.api.videos().delete(id=ctx.youtube_video_id).execute()
```

- [ ] **Step 2: Write a setup README**

Create `tests/integration/publish/README.md`:

```markdown
# YouTube publish integration test

Runs a real upload + verify + delete cycle against a **sandbox channel**.

## One-time setup

1. Create a dedicated YouTube channel for testing (separate from any production channel).
2. Add a profile to `configs/youtube_channels.toml`:

   ```toml
   [profiles.sandbox]
   niche        = "sandbox"
   locale       = "en"
   channel_id   = ""   # fill in after first auth
   voice_guide  = "test"
   default_tags = []
   category_id  = 27

   [routing]
   "sandbox/en" = "sandbox"
   ```

3. Run OAuth: `uv run pipeline publish auth --profile sandbox`.
4. Place test fixtures:
   - `tests/fixtures/sample_final.mp4` — e.g. `ffmpeg -f lavfi -i color=c=black:s=1280x720:d=10 -f lavfi -i anullsrc -c:v libx264 -c:a aac -shortest tests/fixtures/sample_final.mp4`
   - `tests/fixtures/sample_thumbnail.png` — 1280x720 PNG (e.g. via `convert -size 1280x720 xc:black tests/fixtures/sample_thumbnail.png`).

## Running

```bash
YT_PUBLISH_SANDBOX=1 uv run pytest -m network tests/integration/publish/
```

Each test upload is deleted in teardown, so the sandbox channel stays clean.
```

- [ ] **Step 3: Run the marker collection to confirm the test is discoverable**

Run: `uv run pytest -m network tests/integration/publish/ --collect-only`
Expected: one test collected, `test_live_upload_and_cleanup`.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/publish/test_live_upload.py tests/integration/publish/README.md
git commit -m "test(publish): integration scaffold for live sandbox upload"
```

---

## Task 18: Final full test run + type check

**Files:** none — verification only.

- [ ] **Step 1: Run the full unit suite**

Run: `uv run pytest tests/unit/ -v`
Expected: all pass (no regressions in existing tests, new tests pass).

- [ ] **Step 2: Run fast suite (excluding slow/network)**

Run: `uv run pytest -m "not slow and not network"`
Expected: all pass.

- [ ] **Step 3: Ruff lint**

Run: `uv run ruff check src/ tests/`
Expected: no errors. If errors, fix and re-run.

- [ ] **Step 4: Ruff format**

Run: `uv run ruff format src/ tests/`
Expected: no changes (or auto-format + review diffs).

- [ ] **Step 5: mypy**

Run: `uv run mypy src/pipeline/publish/ src/pipeline/notify/ src/pipeline/cli_metadata.py`
Expected: no errors on new modules. (Existing mypy warnings elsewhere are out of scope for this PR.)

- [ ] **Step 6: Verify CLI help**

Run: `uv run pipeline --help`
Expected: `publish`, `metadata` visible as subcommands.

Run: `uv run pipeline publish --help`
Run: `uv run pipeline metadata --help`
Expected: all commands documented.

- [ ] **Step 7: Commit any formatting fixes**

```bash
git status
# If uncommitted: git add <paths> && git commit -m "chore: final format/lint pass"
```

---

## Acceptance checklist (from spec §16)

Run through and confirm:

- [ ] `pipeline publish <project-id>` uploads video, sets metadata, uploads thumbnail, sets disclosure, returns Studio + watch URLs
- [ ] `pipeline publish <project-id>` is idempotent: rerun after any-phase failure resumes correctly (verify via unit tests in Task 11)
- [ ] `pipeline publish auth --profile NAME` runs browser OAuth and writes token (verified via unit test with mocked flow in Task 13; real run requires GCP setup)
- [ ] `pipeline publish status <project-id>` prints local phase state without quota cost
- [ ] `pipeline publish status <project-id> --remote` confirms live state on YouTube
- [ ] `pipeline produce --url X --locale zh-TW --niche parenting` writes `metadata.json` tailored to the profile's voice guide
- [ ] `pipeline produce --url X --locale zh-TW` auto-detects `parenting` when only one niche is configured for zh-TW; errors clearly when ambiguous
- [ ] `pipeline metadata show / set / regenerate / validate` all work
- [ ] Adding a third channel = TOML entry + `pipeline publish auth` — no code changes
- [ ] Failure fires Telegram message when env vars set (Task 5)
- [ ] Unit tests pass with no network access
- [ ] Integration test (marker `network`) scaffolded with sandbox setup docs (live run requires operator setup)
