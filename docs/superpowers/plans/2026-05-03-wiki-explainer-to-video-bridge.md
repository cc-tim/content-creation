# Wiki Explainer → Video Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bridge `know-fountains` wiki explainers to the `content-creation` video pipeline by treating the explainer's video-intent frontmatter as the production manifest, with a dashboard verifier that surfaces manifest ↔ rendered video and treats user-driven drops as a first-class action.

**Architecture:** A small Python module in content-creation parses the manifest from an explainer's YAML frontmatter; a verifier module compares the manifest to the rendered storyboard; FastAPI endpoints + a static page render the dashboard view. Skill files in both projects orchestrate the user-facing workflow — wiki authoring becomes video-aware when `intent: video` is set, and `produce` accepts an explainer path as an alternative to a YouTube URL.

**Tech Stack:** Python 3.11+, uv, Pydantic, FastAPI, pytest, vanilla HTML/JS for the verifier page, markdown for skill files, YAML for manifest blocks.

**Spec:** `docs/superpowers/specs/2026-05-03-wiki-explainer-to-video-bridge-design.md`

---

## File Structure

**Files this plan creates:**

| Path | Responsibility |
|---|---|
| `src/pipeline/explainer.py` | Pydantic models for the manifest; loader that parses an explainer .md file |
| `src/pipeline/verifier.py` | VerifierResult model; auto-check logic; state load/save |
| `src/pipeline/dashboard/static/verify.html` | Dashboard verifier UI (two-column layout) |
| `tests/unit/test_explainer.py` | Manifest loader tests |
| `tests/unit/test_verifier.py` | Verifier logic + state tests |
| `tests/integration/test_dashboard_verifier_api.py` | API endpoint tests with httpx test client |
| `tests/fixtures/explainers/sample-explainer.md` | Test fixture (small but realistic) |
| `tests/fixtures/explainers/no-intent-explainer.md` | Test fixture (no `intent: video`) |
| `~/know-fountains/.claude/skills/video-intent-authoring/SKILL.md` | Wiki-authoring skill that fires on `intent: video` pages |

**Files this plan modifies:**

| Path | Change |
|---|---|
| `src/pipeline/dashboard/server.py` | Add `/api/verify/<project_id>` (GET) and `/api/verify/<project_id>/skip` (POST) endpoints + static route for `verify.html` |
| `skills/produce/SKILL.md` | Add explainer-path branch with manifest review |
| `skills/storyboard/SKILL.md` | Add manifest-as-hard-input rules |
| `~/content-creation/.claude/settings.local.json` | Add `additionalDirectories: ["~/know-fountains"]` |
| `~/know-fountains/.claude/settings.local.json` | Add `additionalDirectories: ["~/content-creation"]` (create file) |
| `~/know-fountains/CLAUDE.md` | Append manifest schema reference for `intent: video` pages |

---

## Task 1: Manifest Pydantic models

**Files:**
- Create: `src/pipeline/explainer.py`
- Test: `tests/unit/test_explainer.py`
- Fixture: `tests/fixtures/explainers/sample-explainer.md`
- Fixture: `tests/fixtures/explainers/no-intent-explainer.md`

- [ ] **Step 1: Write the test fixtures**

Create `tests/fixtures/explainers/sample-explainer.md`:

```markdown
---
title: "Sample Explainer"
type: explainer
domain: parenting
intent: video
video_brief: |
  Short test brief. Tone is neutral.
verbatim_lines:
  - "this exact line must appear"
  - "and so must this one"
key_facts:
  - "X dropped 90% from year A to year B"
required_images:
  - path: raw/parenting/sample/assets/img1.jpg
    role: intro_candidate
    caption: "Sample caption"
  - path: raw/parenting/sample/assets/img2.jpg
required_clips: []
required_sequence:
  - "history → stats → conclusion"
sources: ["[[some-source]]"]
created: 2026-05-03
updated: 2026-05-03
---

# Sample Explainer

This is the body. It contains a `![](raw/parenting/sample/assets/img1.jpg)` image
and a quote: > "this exact line must appear"

End of body.
```

Create `tests/fixtures/explainers/no-intent-explainer.md`:

```markdown
---
title: "Not Video Intent"
type: explainer
domain: parenting
sources: []
created: 2026-05-03
updated: 2026-05-03
---

# Body without video intent

Just regular wiki content.
```

- [ ] **Step 2: Write the failing test**

Create `tests/unit/test_explainer.py`:

```python
from pathlib import Path

import pytest

from pipeline.explainer import (
    Explainer,
    Manifest,
    RequiredImage,
    load_explainer,
)


FIXTURES = Path(__file__).parent.parent / "fixtures" / "explainers"


def test_load_full_explainer_parses_all_manifest_blocks():
    explainer = load_explainer(FIXTURES / "sample-explainer.md")

    assert isinstance(explainer, Explainer)
    assert explainer.title == "Sample Explainer"
    assert explainer.domain == "parenting"

    m = explainer.manifest
    assert m.intent == "video"
    assert "neutral" in m.video_brief
    assert m.verbatim_lines == [
        "this exact line must appear",
        "and so must this one",
    ]
    assert m.key_facts == ["X dropped 90% from year A to year B"]
    assert len(m.required_images) == 2
    assert m.required_images[0] == RequiredImage(
        path="raw/parenting/sample/assets/img1.jpg",
        role="intro_candidate",
        caption="Sample caption",
    )
    assert m.required_images[1].path == "raw/parenting/sample/assets/img2.jpg"
    assert m.required_images[1].role is None
    assert m.required_clips == []
    assert m.required_sequence == ["history → stats → conclusion"]


def test_load_explainer_without_video_intent_returns_empty_manifest():
    explainer = load_explainer(FIXTURES / "no-intent-explainer.md")

    assert explainer.manifest.intent is None
    assert explainer.manifest.verbatim_lines == []
    assert explainer.manifest.required_images == []
    assert explainer.manifest.video_brief is None


def test_load_explainer_preserves_body_after_frontmatter():
    explainer = load_explainer(FIXTURES / "sample-explainer.md")

    assert "# Sample Explainer" in explainer.body
    assert "End of body." in explainer.body
    assert "intent: video" not in explainer.body  # frontmatter stripped


def test_manifest_is_video_intent_true_only_when_set():
    sample = load_explainer(FIXTURES / "sample-explainer.md")
    no_intent = load_explainer(FIXTURES / "no-intent-explainer.md")

    assert sample.manifest.is_video_intent is True
    assert no_intent.manifest.is_video_intent is False


def test_load_explainer_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_explainer(FIXTURES / "does-not-exist.md")
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd /home/tim-huang/content-creation && uv run pytest tests/unit/test_explainer.py -v`
Expected: ImportError / ModuleNotFoundError on `pipeline.explainer`.

- [ ] **Step 4: Implement minimal code to pass**

Create `src/pipeline/explainer.py`:

```python
from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class RequiredImage(BaseModel):
    path: str
    role: str | None = None
    caption: str | None = None


class RequiredClip(BaseModel):
    path: str
    role: str | None = None
    caption: str | None = None


class Manifest(BaseModel):
    intent: str | None = None
    video_brief: str | None = None
    verbatim_lines: list[str] = Field(default_factory=list)
    key_facts: list[str] = Field(default_factory=list)
    required_images: list[RequiredImage] = Field(default_factory=list)
    required_clips: list[RequiredClip] = Field(default_factory=list)
    required_sequence: list[str] = Field(default_factory=list)

    @property
    def is_video_intent(self) -> bool:
        return self.intent == "video"


class Explainer(BaseModel):
    path: Path
    title: str
    domain: str
    manifest: Manifest
    body: str

    model_config = {"arbitrary_types_allowed": True}


_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)


def load_explainer(path: Path) -> Explainer:
    if not path.exists():
        raise FileNotFoundError(path)

    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError(f"{path} has no YAML frontmatter")

    fm_raw, body = match.group(1), match.group(2)
    fm = yaml.safe_load(fm_raw) or {}

    manifest = Manifest(
        intent=fm.get("intent"),
        video_brief=fm.get("video_brief"),
        verbatim_lines=list(fm.get("verbatim_lines") or []),
        key_facts=list(fm.get("key_facts") or []),
        required_images=[
            RequiredImage(**img) if isinstance(img, dict) else RequiredImage(path=img)
            for img in (fm.get("required_images") or [])
        ],
        required_clips=[
            RequiredClip(**clip) if isinstance(clip, dict) else RequiredClip(path=clip)
            for clip in (fm.get("required_clips") or [])
        ],
        required_sequence=list(fm.get("required_sequence") or []),
    )

    return Explainer(
        path=path,
        title=str(fm.get("title", "")),
        domain=str(fm.get("domain", "")),
        manifest=manifest,
        body=body,
    )
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd /home/tim-huang/content-creation && uv run pytest tests/unit/test_explainer.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/explainer.py tests/unit/test_explainer.py tests/fixtures/explainers/
git commit -m "feat(pipeline): add explainer manifest loader

Parses video-intent frontmatter blocks from a wiki explainer .md file
into a typed Manifest. Foundation for the wiki→video bridge."
```

---

## Task 2: Verifier auto-check logic

**Files:**
- Create: `src/pipeline/verifier.py`
- Test: `tests/unit/test_verifier.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_verifier.py`:

```python
import json
from pathlib import Path

import pytest

from pipeline.explainer import Manifest, RequiredImage
from pipeline.verifier import (
    ItemStatus,
    VerifierResult,
    load_verifier_state,
    run_auto_checks,
    save_verifier_state,
)


def _fake_storyboard():
    return {
        "scenes": [
            {
                "id": "s1",
                "narration": "Welcome. this exact line must appear in narration.",
                "visual": {
                    "type": "article_image",
                    "path": "raw/parenting/sample/assets/img1.jpg",
                },
                "overlay": None,
            },
            {
                "id": "s2",
                "narration": "Next scene narration with no quote.",
                "visual": {"type": "generated_image", "path": "scenes/s2.png"},
                "overlay": {"text": "and so must this one"},
            },
        ]
    }


def _full_manifest():
    return Manifest(
        intent="video",
        verbatim_lines=[
            "this exact line must appear",
            "and so must this one",
            "missing line",
        ],
        key_facts=["fact A", "fact B"],
        required_images=[
            RequiredImage(path="raw/parenting/sample/assets/img1.jpg"),
            RequiredImage(path="raw/parenting/sample/assets/img-missing.jpg"),
        ],
    )


def test_run_auto_checks_marks_verbatim_line_used_when_in_narration():
    result = run_auto_checks(_full_manifest(), _fake_storyboard())
    line0 = next(i for i in result.items if i.item_id == "verbatim_line:0")
    assert line0.status == "used"


def test_run_auto_checks_marks_verbatim_line_used_when_in_overlay():
    result = run_auto_checks(_full_manifest(), _fake_storyboard())
    line1 = next(i for i in result.items if i.item_id == "verbatim_line:1")
    assert line1.status == "used"


def test_run_auto_checks_marks_verbatim_line_missing_when_nowhere():
    result = run_auto_checks(_full_manifest(), _fake_storyboard())
    line2 = next(i for i in result.items if i.item_id == "verbatim_line:2")
    assert line2.status == "missing"


def test_run_auto_checks_marks_image_used_when_path_in_visual():
    result = run_auto_checks(_full_manifest(), _fake_storyboard())
    img0 = next(i for i in result.items if i.item_id == "required_image:0")
    assert img0.status == "used"


def test_run_auto_checks_marks_image_missing_when_not_referenced():
    result = run_auto_checks(_full_manifest(), _fake_storyboard())
    img1 = next(i for i in result.items if i.item_id == "required_image:1")
    assert img1.status == "missing"


def test_run_auto_checks_marks_key_facts_for_manual_review():
    result = run_auto_checks(_full_manifest(), _fake_storyboard())
    fact0 = next(i for i in result.items if i.item_id == "key_fact:0")
    assert fact0.status == "missing"  # manual until user toggles
    assert fact0.auto_checked is False


def test_run_auto_checks_counts_summary():
    result = run_auto_checks(_full_manifest(), _fake_storyboard())
    assert result.used_count == 3       # 2 lines + 1 image
    assert result.missing_count == 4    # 1 line + 1 image + 2 facts
    assert result.skipped_count == 0


def test_run_auto_checks_applies_persisted_skips(tmp_path: Path):
    manifest = _full_manifest()
    state_path = tmp_path / "verifier_state.json"
    state_path.write_text(json.dumps({
        "skipped": ["verbatim_line:2"],
        "manual_checked": [],
    }))

    state = load_verifier_state(state_path)
    result = run_auto_checks(manifest, _fake_storyboard(), state=state)

    line2 = next(i for i in result.items if i.item_id == "verbatim_line:2")
    assert line2.status == "user_skipped"
    assert result.skipped_count == 1
    assert result.missing_count == 3


def test_run_auto_checks_applies_manual_checked(tmp_path: Path):
    manifest = _full_manifest()
    state_path = tmp_path / "verifier_state.json"
    state_path.write_text(json.dumps({
        "skipped": [],
        "manual_checked": ["key_fact:0"],
    }))

    state = load_verifier_state(state_path)
    result = run_auto_checks(manifest, _fake_storyboard(), state=state)

    fact0 = next(i for i in result.items if i.item_id == "key_fact:0")
    assert fact0.status == "used"


def test_save_and_load_verifier_state_roundtrip(tmp_path: Path):
    state_path = tmp_path / "verifier_state.json"
    save_verifier_state(state_path, skipped={"a", "b"}, manual_checked={"c"})
    loaded = load_verifier_state(state_path)
    assert loaded.skipped == {"a", "b"}
    assert loaded.manual_checked == {"c"}


def test_load_verifier_state_missing_file_returns_empty(tmp_path: Path):
    loaded = load_verifier_state(tmp_path / "does-not-exist.json")
    assert loaded.skipped == set()
    assert loaded.manual_checked == set()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_verifier.py -v`
Expected: ImportError on `pipeline.verifier`.

- [ ] **Step 3: Implement minimal code to pass**

Create `src/pipeline/verifier.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from pipeline.explainer import Manifest

ItemStatusValue = Literal["used", "modified", "missing", "user_skipped"]
ItemCategory = Literal[
    "verbatim_line",
    "key_fact",
    "required_image",
    "required_clip",
    "required_sequence",
]


class ItemStatus(BaseModel):
    item_id: str           # e.g. "verbatim_line:0"
    category: ItemCategory
    label: str             # display text
    status: ItemStatusValue
    auto_checked: bool


class VerifierResult(BaseModel):
    items: list[ItemStatus]
    used_count: int
    missing_count: int
    skipped_count: int


@dataclass
class VerifierState:
    skipped: set[str] = field(default_factory=set)
    manual_checked: set[str] = field(default_factory=set)


def load_verifier_state(path: Path) -> VerifierState:
    if not path.exists():
        return VerifierState()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return VerifierState(
        skipped=set(raw.get("skipped", [])),
        manual_checked=set(raw.get("manual_checked", [])),
    )


def save_verifier_state(
    path: Path,
    *,
    skipped: set[str],
    manual_checked: set[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"skipped": sorted(skipped), "manual_checked": sorted(manual_checked)},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _haystack_for_lines(storyboard: dict[str, Any]) -> str:
    parts: list[str] = []
    for scene in storyboard.get("scenes", []):
        parts.append(scene.get("narration", "") or "")
        overlay = scene.get("overlay") or {}
        if isinstance(overlay, dict):
            parts.append(overlay.get("text", "") or "")
        for sub in scene.get("subtitles", []) or []:
            if isinstance(sub, dict):
                parts.append(sub.get("text", "") or "")
            else:
                parts.append(str(sub))
    return "\n".join(parts)


def _scene_visual_paths(storyboard: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for scene in storyboard.get("scenes", []):
        visual = scene.get("visual") or {}
        if isinstance(visual, dict) and visual.get("path"):
            paths.add(visual["path"])
    return paths


def _resolve_status(
    item_id: str,
    auto_status: ItemStatusValue,
    state: VerifierState | None,
) -> ItemStatusValue:
    if state is None:
        return auto_status
    if item_id in state.skipped:
        return "user_skipped"
    if item_id in state.manual_checked:
        return "used"
    return auto_status


def run_auto_checks(
    manifest: Manifest,
    storyboard: dict[str, Any],
    *,
    state: VerifierState | None = None,
) -> VerifierResult:
    haystack = _haystack_for_lines(storyboard)
    visual_paths = _scene_visual_paths(storyboard)

    items: list[ItemStatus] = []

    for i, line in enumerate(manifest.verbatim_lines):
        auto = "used" if line in haystack else "missing"
        item_id = f"verbatim_line:{i}"
        items.append(ItemStatus(
            item_id=item_id,
            category="verbatim_line",
            label=line,
            status=_resolve_status(item_id, auto, state),
            auto_checked=True,
        ))

    for i, fact in enumerate(manifest.key_facts):
        item_id = f"key_fact:{i}"
        items.append(ItemStatus(
            item_id=item_id,
            category="key_fact",
            label=fact,
            status=_resolve_status(item_id, "missing", state),
            auto_checked=False,
        ))

    for i, image in enumerate(manifest.required_images):
        auto = "used" if image.path in visual_paths else "missing"
        item_id = f"required_image:{i}"
        items.append(ItemStatus(
            item_id=item_id,
            category="required_image",
            label=image.path,
            status=_resolve_status(item_id, auto, state),
            auto_checked=True,
        ))

    for i, clip in enumerate(manifest.required_clips):
        auto = "used" if clip.path in visual_paths else "missing"
        item_id = f"required_clip:{i}"
        items.append(ItemStatus(
            item_id=item_id,
            category="required_clip",
            label=clip.path,
            status=_resolve_status(item_id, auto, state),
            auto_checked=True,
        ))

    for i, seq in enumerate(manifest.required_sequence):
        item_id = f"required_sequence:{i}"
        items.append(ItemStatus(
            item_id=item_id,
            category="required_sequence",
            label=seq,
            status=_resolve_status(item_id, "missing", state),
            auto_checked=False,
        ))

    used = sum(1 for it in items if it.status == "used")
    missing = sum(1 for it in items if it.status == "missing")
    skipped = sum(1 for it in items if it.status == "user_skipped")

    return VerifierResult(
        items=items,
        used_count=used,
        missing_count=missing,
        skipped_count=skipped,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/unit/test_verifier.py -v`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/verifier.py tests/unit/test_verifier.py
git commit -m "feat(pipeline): add manifest verifier with auto-checks + skip state

Cross-references manifest verbatim_lines / required_images / etc. against
a storyboard.json; persists user 'OK to drop' decisions per project."
```

---

## Task 3: Dashboard verifier API endpoints

**Files:**
- Modify: `src/pipeline/dashboard/server.py`
- Test: `tests/integration/test_dashboard_verifier_api.py`

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_dashboard_verifier_api.py`:

```python
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pipeline.dashboard.server import create_app


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    proj_root = tmp_path / "projects"
    proj = proj_root / "abc123"
    (proj / "source").mkdir(parents=True)
    (proj / "compose").mkdir()

    (proj / "source" / "explainer.md").write_text(
        """---
title: T
type: explainer
domain: parenting
intent: video
verbatim_lines:
  - "needle line"
required_images:
  - path: raw/parenting/x/img.jpg
sources: []
created: 2026-05-03
updated: 2026-05-03
---

# T
""",
        encoding="utf-8",
    )
    (proj / "storyboard.json").write_text(
        json.dumps({"scenes": [
            {
                "id": "s1",
                "narration": "the needle line is here",
                "visual": {"path": "raw/parenting/x/img.jpg"},
            }
        ]}),
        encoding="utf-8",
    )
    return proj_root


def test_get_verify_returns_manifest_and_items(project_dir: Path):
    client = TestClient(create_app(output_dir=project_dir))
    res = client.get("/api/verify/abc123")
    assert res.status_code == 200
    data = res.json()
    assert data["manifest"]["intent"] == "video"
    assert any(it["item_id"] == "verbatim_line:0" and it["status"] == "used" for it in data["items"])
    assert any(it["item_id"] == "required_image:0" and it["status"] == "used" for it in data["items"])
    assert data["used_count"] == 2
    assert data["missing_count"] == 0


def test_get_verify_unknown_project_returns_404(project_dir: Path):
    client = TestClient(create_app(output_dir=project_dir))
    res = client.get("/api/verify/nope")
    assert res.status_code == 404


def test_get_verify_project_without_explainer_returns_409(project_dir: Path, tmp_path: Path):
    # Create a project with no explainer.md
    other = tmp_path / "projects" / "noex"
    (other / "source").mkdir(parents=True)
    (other / "storyboard.json").write_text("{}", encoding="utf-8")
    client = TestClient(create_app(output_dir=tmp_path / "projects"))
    res = client.get("/api/verify/noex")
    assert res.status_code == 409
    assert "explainer" in res.json()["detail"].lower()


def test_post_skip_toggles_status(project_dir: Path):
    client = TestClient(create_app(output_dir=project_dir))

    res = client.post("/api/verify/abc123/skip", json={
        "item_id": "verbatim_line:0",
        "skipped": True,
    })
    assert res.status_code == 200

    res2 = client.get("/api/verify/abc123")
    line0 = next(it for it in res2.json()["items"] if it["item_id"] == "verbatim_line:0")
    assert line0["status"] == "user_skipped"

    # Toggle back off
    client.post("/api/verify/abc123/skip", json={
        "item_id": "verbatim_line:0",
        "skipped": False,
    })
    res3 = client.get("/api/verify/abc123")
    line0_again = next(it for it in res3.json()["items"] if it["item_id"] == "verbatim_line:0")
    assert line0_again["status"] == "used"


def test_post_manual_check_marks_fact_used(project_dir: Path):
    # Add a key_fact to the explainer first
    explainer_path = project_dir / "abc123" / "source" / "explainer.md"
    text = explainer_path.read_text(encoding="utf-8")
    text = text.replace("verbatim_lines:", "key_facts:\n  - 'a stated fact'\nverbatim_lines:")
    explainer_path.write_text(text, encoding="utf-8")

    client = TestClient(create_app(output_dir=project_dir))
    res = client.post("/api/verify/abc123/manual-check", json={
        "item_id": "key_fact:0",
        "checked": True,
    })
    assert res.status_code == 200

    res2 = client.get("/api/verify/abc123")
    fact0 = next(it for it in res2.json()["items"] if it["item_id"] == "key_fact:0")
    assert fact0["status"] == "used"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/integration/test_dashboard_verifier_api.py -v`
Expected: 404 / 405 errors (endpoints don't exist yet).

- [ ] **Step 3: Implement the endpoints**

Modify `src/pipeline/dashboard/server.py`. Add these imports near the top with the existing imports:

```python
from fastapi import HTTPException
from pydantic import BaseModel

from pipeline.explainer import load_explainer
from pipeline.verifier import (
    load_verifier_state,
    run_auto_checks,
    save_verifier_state,
)
```

Inside `create_app`, after the existing `/api/channels` endpoint and before the `if dev_mode:` block, add:

```python
    class _SkipBody(BaseModel):
        item_id: str
        skipped: bool

    class _ManualCheckBody(BaseModel):
        item_id: str
        checked: bool

    def _project_root(project_id: str) -> Path:
        proj = output_dir / project_id
        if not proj.exists():
            raise HTTPException(status_code=404, detail=f"project {project_id} not found")
        return proj

    def _explainer_path(proj: Path) -> Path:
        candidate = proj / "source" / "explainer.md"
        if not candidate.exists():
            raise HTTPException(
                status_code=409,
                detail="this project has no explainer.md (not produced from a wiki explainer)",
            )
        return candidate

    @app.get("/api/verify/{project_id}")
    def get_verify(project_id: str) -> JSONResponse:
        proj = _project_root(project_id)
        explainer = load_explainer(_explainer_path(proj))
        sb_path = proj / "storyboard.json"
        if not sb_path.exists():
            raise HTTPException(status_code=409, detail="storyboard.json not yet generated")
        import json as _json
        storyboard = _json.loads(sb_path.read_text(encoding="utf-8"))
        state = load_verifier_state(proj / "verifier_state.json")
        result = run_auto_checks(explainer.manifest, storyboard, state=state)
        return JSONResponse({
            "project_id": project_id,
            "manifest": explainer.manifest.model_dump(),
            "items": [it.model_dump() for it in result.items],
            "used_count": result.used_count,
            "missing_count": result.missing_count,
            "skipped_count": result.skipped_count,
        })

    @app.post("/api/verify/{project_id}/skip")
    def post_skip(project_id: str, body: _SkipBody) -> JSONResponse:
        proj = _project_root(project_id)
        state_path = proj / "verifier_state.json"
        state = load_verifier_state(state_path)
        if body.skipped:
            state.skipped.add(body.item_id)
        else:
            state.skipped.discard(body.item_id)
        save_verifier_state(
            state_path,
            skipped=state.skipped,
            manual_checked=state.manual_checked,
        )
        return JSONResponse({"ok": True})

    @app.post("/api/verify/{project_id}/manual-check")
    def post_manual_check(project_id: str, body: _ManualCheckBody) -> JSONResponse:
        proj = _project_root(project_id)
        state_path = proj / "verifier_state.json"
        state = load_verifier_state(state_path)
        if body.checked:
            state.manual_checked.add(body.item_id)
        else:
            state.manual_checked.discard(body.item_id)
        save_verifier_state(
            state_path,
            skipped=state.skipped,
            manual_checked=state.manual_checked,
        )
        return JSONResponse({"ok": True})

    @app.get("/verify/{project_id}")
    def verify_page(project_id: str) -> FileResponse:
        return FileResponse(_STATIC_DIR / "verify.html")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/integration/test_dashboard_verifier_api.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/dashboard/server.py tests/integration/test_dashboard_verifier_api.py
git commit -m "feat(dashboard): add verify API endpoints

GET /api/verify/<id> returns manifest + items + statuses.
POST /api/verify/<id>/skip toggles user-skipped state per item.
POST /api/verify/<id>/manual-check marks key_fact / required_sequence as used."
```

---

## Task 4: Dashboard verifier UI page

**Files:**
- Create: `src/pipeline/dashboard/static/verify.html`

- [ ] **Step 1: Write the static page**

Create `src/pipeline/dashboard/static/verify.html`:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Verify — Content Dashboard</title>
  <style>
    body { font-family: ui-sans-serif, system-ui, sans-serif; margin: 0; background: #0f172a; color: #f1f5f9; }
    header { padding: 12px 20px; border-bottom: 1px solid #334155; display: flex; gap: 16px; align-items: baseline; }
    header h1 { font-size: 18px; margin: 0; }
    header .summary { color: #94a3b8; font-size: 13px; }
    header .badge { padding: 2px 8px; border-radius: 4px; margin-right: 8px; }
    .ok { background: #166534; color: #f0fdf4; }
    .miss { background: #991b1b; color: #fef2f2; }
    .skip { background: #475569; color: #f1f5f9; }
    main { display: grid; grid-template-columns: minmax(360px, 1fr) 2fr; min-height: calc(100vh - 50px); }
    section { padding: 16px 20px; overflow-y: auto; }
    section.left { border-right: 1px solid #334155; }
    h2 { font-size: 14px; text-transform: uppercase; letter-spacing: 1px; color: #94a3b8; margin-top: 24px; }
    .brief { white-space: pre-wrap; font-size: 13px; background: #1e293b; padding: 12px; border-radius: 6px; }
    .item { padding: 8px 10px; border-radius: 6px; background: #1e293b; margin-bottom: 6px; display: flex; gap: 10px; align-items: flex-start; font-size: 13px; }
    .item .label { flex: 1; word-break: break-word; }
    .item .status { font-size: 11px; padding: 2px 6px; border-radius: 4px; }
    .item.used { border-left: 4px solid #16a34a; }
    .item.missing { border-left: 4px solid #dc2626; }
    .item.user_skipped { border-left: 4px solid #64748b; opacity: 0.7; }
    .item button { background: #334155; color: #f1f5f9; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 11px; }
    video { width: 100%; max-height: 60vh; background: #000; border-radius: 6px; }
  </style>
</head>
<body>
<header>
  <h1>Verify <span id="proj"></span></h1>
  <div class="summary">
    <span class="badge ok"><span id="cnt-used">0</span> used</span>
    <span class="badge miss"><span id="cnt-missing">0</span> missing</span>
    <span class="badge skip"><span id="cnt-skipped">0</span> skipped</span>
  </div>
</header>
<main>
  <section class="left">
    <h2>Directorial brief</h2>
    <div id="brief" class="brief"></div>

    <h2>Verbatim lines</h2>
    <div id="verbatim_line" class="bucket"></div>
    <h2>Key facts</h2>
    <div id="key_fact" class="bucket"></div>
    <h2>Required images</h2>
    <div id="required_image" class="bucket"></div>
    <h2>Required clips</h2>
    <div id="required_clip" class="bucket"></div>
    <h2>Required sequence</h2>
    <div id="required_sequence" class="bucket"></div>
  </section>
  <section class="right">
    <h2>Final video</h2>
    <video id="video" controls></video>
    <h2>Scenes</h2>
    <div id="scenes"></div>
  </section>
</main>
<script>
const projectId = location.pathname.split("/").pop();
document.getElementById("proj").textContent = projectId;

async function refresh() {
  const res = await fetch(`/api/verify/${projectId}`);
  if (!res.ok) {
    document.body.innerHTML = `<p style="padding:40px">Error: ${res.status} — ${(await res.json()).detail || res.statusText}</p>`;
    return;
  }
  const data = await res.json();
  document.getElementById("cnt-used").textContent = data.used_count;
  document.getElementById("cnt-missing").textContent = data.missing_count;
  document.getElementById("cnt-skipped").textContent = data.skipped_count;
  document.getElementById("brief").textContent = data.manifest.video_brief || "(no brief)";

  const buckets = ["verbatim_line", "key_fact", "required_image", "required_clip", "required_sequence"];
  for (const b of buckets) document.getElementById(b).innerHTML = "";

  for (const it of data.items) {
    const el = document.createElement("div");
    el.className = `item ${it.status}`;
    const skipBtn = document.createElement("button");
    skipBtn.textContent = it.status === "user_skipped" ? "un-skip" : "OK to drop";
    skipBtn.onclick = async () => {
      await fetch(`/api/verify/${projectId}/skip`, {
        method: "POST",
        headers: {"content-type": "application/json"},
        body: JSON.stringify({item_id: it.item_id, skipped: it.status !== "user_skipped"}),
      });
      refresh();
    };
    const manualBtn = document.createElement("button");
    if (!it.auto_checked && it.status !== "user_skipped") {
      manualBtn.textContent = it.status === "used" ? "✓ unmark" : "mark used";
      manualBtn.onclick = async () => {
        await fetch(`/api/verify/${projectId}/manual-check`, {
          method: "POST",
          headers: {"content-type": "application/json"},
          body: JSON.stringify({item_id: it.item_id, checked: it.status !== "used"}),
        });
        refresh();
      };
    }
    el.innerHTML = `<div class="label">${escapeHtml(it.label)}</div>
                    <span class="status">${it.status}</span>`;
    if (!it.auto_checked && it.status !== "user_skipped") el.appendChild(manualBtn);
    el.appendChild(skipBtn);
    document.getElementById(it.category).appendChild(el);
  }

  // Best-effort video loader (project may not have rendered yet)
  const v = document.getElementById("video");
  v.src = `/projects/${projectId}/compose/final_zh-TW.mp4`;
  v.onerror = () => { v.style.display = "none"; };
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
}

refresh();
</script>
</body>
</html>
```

- [ ] **Step 2: Verify route resolves**

Existing tests already cover the API. The static page is served by `GET /verify/{project_id}` (added in Task 3). To smoke-test it locally:

```bash
./scripts/start-dashboard.sh --local-only
# Open http://localhost:8765/verify/<an-existing-project-id>
```

If the project lacks `source/explainer.md` (legacy YouTube projects), the page shows the API error gracefully — that's expected.

- [ ] **Step 3: Commit**

```bash
git add src/pipeline/dashboard/static/verify.html
git commit -m "feat(dashboard): add verify.html — manifest ↔ scene checklist UI

Two-column layout: directorial brief + per-category items on the left;
final video + scene strip on the right. OK-to-drop and manual-check
toggles call back to the verify API."
```

---

## Task 5: Settings cross-link (`additionalDirectories`)

**Files:**
- Modify or create: `~/content-creation/.claude/settings.local.json`
- Modify or create: `~/know-fountains/.claude/settings.local.json`

- [ ] **Step 1: Read current content-creation local settings**

```bash
cat ~/content-creation/.claude/settings.local.json
```

- [ ] **Step 2: Add `additionalDirectories` to content-creation settings**

If the file already has top-level keys (e.g. `permissions`), merge — keep them and add `additionalDirectories`. Otherwise create the file with this content:

```json
{
  "additionalDirectories": [
    "/home/tim-huang/know-fountains"
  ]
}
```

If the file already exists and has other keys, the result should be e.g.:

```json
{
  "permissions": { "...": "..." },
  "additionalDirectories": [
    "/home/tim-huang/know-fountains"
  ]
}
```

- [ ] **Step 3: Create know-fountains local settings**

```bash
mkdir -p ~/know-fountains/.claude
```

Then write `~/know-fountains/.claude/settings.local.json`:

```json
{
  "additionalDirectories": [
    "/home/tim-huang/content-creation"
  ]
}
```

- [ ] **Step 4: Verify both files load**

```bash
cat ~/content-creation/.claude/settings.local.json | python3 -m json.tool
cat ~/know-fountains/.claude/settings.local.json | python3 -m json.tool
```

Expected: both pretty-print without errors.

- [ ] **Step 5: Commit (content-creation only — know-fountains is a separate repo)**

```bash
# In content-creation:
# settings.local.json is typically gitignored; check first
git check-ignore -v .claude/settings.local.json && echo "(gitignored — skip commit)" || \
  (git add .claude/settings.local.json && git commit -m "chore(claude): add know-fountains as additional working dir")
```

For know-fountains:

```bash
cd ~/know-fountains
git check-ignore -v .claude/settings.local.json && echo "(gitignored — skip commit)" || \
  (git add .claude/settings.local.json && git commit -m "chore(claude): add content-creation as additional working dir")
cd -
```

Note: The change takes effect on the **next** Claude Code session. The current session can use `/add-dir` for one-off behavior.

---

## Task 6: know-fountains `video-intent-authoring` skill

**Files:**
- Create: `~/know-fountains/.claude/skills/video-intent-authoring/SKILL.md`

- [ ] **Step 1: Create the skill directory**

```bash
mkdir -p ~/know-fountains/.claude/skills/video-intent-authoring
```

- [ ] **Step 2: Write the SKILL.md**

Create `~/know-fountains/.claude/skills/video-intent-authoring/SKILL.md`:

````markdown
---
name: video-intent-authoring
description: Use when adding material (images, quotes, facts, structure) to a wiki page that has `intent: video` in frontmatter, or when the user mentions porting a wiki page to a video. Asks the video-shaping question for each addition and keeps prose + frontmatter manifest blocks in sync.
---

# Video-Intent Authoring

When a wiki page has `intent: video` in its frontmatter, treat each addition as
both a wiki edit AND a manifest update. The frontmatter becomes the production
manifest read by the `content-creation` `produce` skill.

## Trigger

Activate when:
- The user is adding/editing a wiki page (typically under `wiki/<domain>/explainers/`)
  with `intent: video` already in frontmatter, OR
- The user explicitly says they intend to make a video from a wiki page (in which
  case, set `intent: video` in frontmatter first).

## The manifest blocks (frontmatter)

```yaml
intent: video
video_brief: |
  Free-form directorial intent. Tone, transition styles for scene ranges,
  intro framing concepts, what NOT to do.
verbatim_lines:        # must appear unchanged in narration/overlay/subtitle
  - "..."
key_facts:             # must be stated, paraphrasing OK
  - "..."
required_images:       # must appear in some scene
  - path: raw/<domain>/<slug>/assets/<file>.jpg
    role: intro_candidate | historical | comparison  # optional
    caption: "..."                                   # optional
required_clips:        # external video files, same shape
  - path: ...
required_sequence:     # ordering constraints, free-form phrases
  - "history → stats → conclusion"
```

All blocks except `intent: video` are optional. They grow over time.

## Behavior per addition

| User says... | Do this |
|---|---|
| *"add this image"* | (1) add `![](raw/...)` link to prose. (2) ask: required for the video? if yes, what role? → append to `required_images`. |
| *"keep this quote"* / *"this exact line"* | (1) add `> blockquote` to prose. (2) ask: verbatim or paraphrasable? → append to `verbatim_lines` OR `key_facts`. |
| *"this fact matters"* | (1) optionally inline-bold in prose. (2) append to `key_facts`. |
| *"open with this"* / *"end with this"* | (1) note in `video_brief`. (2) for an image, set role accordingly in `required_images`. |
| *"first half should..."* / transition / pacing notes | append to `video_brief` (preserve existing text — don't overwrite). |
| *"this should come before that"* | append a phrase to `required_sequence`. |

Always update `updated:` in frontmatter to today's date after edits.

## What "considered" vs "required" means

- Anything `![](...)` in prose is **considered** for the video (the assistant
  doing storyboard generation will see it as a candidate).
- Anything in `> blockquote` is **considered** for verbatim use.
- Promotion to **required** happens by adding the item to the corresponding
  frontmatter block. The user weighs the difference.

## When the user is ready to produce a video

Tell them to switch to the `content-creation` working directory and run
`/produce <path-to-this-explainer.md>`. The `produce` skill there reads this
manifest, runs an interactive review, and starts the pipeline.

## Out of scope

- Don't run `produce` from this skill — the user crosses to content-creation
  for that.
- Don't infer manifest items the user didn't explicitly call out. When in
  doubt, ask.
````

- [ ] **Step 3: Commit (in know-fountains repo)**

```bash
cd ~/know-fountains
git add .claude/skills/video-intent-authoring/SKILL.md
git commit -m "feat(skills): video-intent-authoring — wiki authoring becomes video-aware

When a wiki page has intent: video in frontmatter, every material addition
prompts the video-shaping question and updates the right manifest block."
cd -
```

---

## Task 7: know-fountains CLAUDE.md — manifest schema reference

**Files:**
- Modify: `~/know-fountains/CLAUDE.md`

- [ ] **Step 1: Read current CLAUDE.md**

```bash
cat ~/know-fountains/CLAUDE.md
```

Identify where the existing "Page conventions" section ends — append after that.

- [ ] **Step 2: Append a new section**

Append to `~/know-fountains/CLAUDE.md`:

```markdown

## Video-intent pages

A wiki page with `intent: video` in its frontmatter is a video production
manifest. The `video-intent-authoring` skill auto-activates on those pages —
see `.claude/skills/video-intent-authoring/SKILL.md` for the full behavior
contract.

When you encounter a page with `intent: video`, treat each material addition
(image, quote, fact, sequence note) as both a wiki edit AND a manifest update
in the corresponding frontmatter block (`verbatim_lines`, `key_facts`,
`required_images`, `required_clips`, `required_sequence`, `video_brief`).

The full design rationale lives at:
`/home/tim-huang/content-creation/docs/superpowers/specs/2026-05-03-wiki-explainer-to-video-bridge-design.md`
```

- [ ] **Step 3: Commit**

```bash
cd ~/know-fountains
git add CLAUDE.md
git commit -m "docs(claude): document video-intent page convention"
cd -
```

---

## Task 8: `produce` skill — explainer-path branch

**Files:**
- Modify: `skills/produce/SKILL.md`

- [ ] **Step 1: Read current SKILL.md**

```bash
cat skills/produce/SKILL.md
```

(Already 102 lines. The change adds a parallel branch — see size watch in Task 11.)

- [ ] **Step 2: Add the explainer-path branch**

In `skills/produce/SKILL.md`:

1. Update the `description` field to mention the new path:
   ```yaml
   description: Run the full YouTube porting pipeline OR the wiki-explainer porting pipeline. For YouTube: pass a URL. For wiki explainers: pass a path to a `.md` file with `intent: video` frontmatter. Covers: acquire → analyze → storyboard → TTS → compose.
   ```

2. Update the `## Input` section:
   ```markdown
   ## Input
   - YouTube URL OR explainer path (one is required)
     - YouTube URL → existing flow (acquire → analyze)
     - Path to `.md` with `intent: video` frontmatter → explainer flow (manifest review → analyze)
   - Locale (default: zh-TW)
   - Project ID (optional — to resume an existing project)
   - Voice ID (optional — default uses locale default from registry)
   ```

3. Add a new section between the existing `## Phase 1 — Acquire` and `## Phase 2 — Analyze`:

   ````markdown
   ## Phase 1 (alternate) — Explainer path

   When the input is a path to a `.md` file (not a URL), use this branch instead.

   ### Load the manifest

   ```bash
   cd /home/tim-huang/content-creation
   uv run python3 -c "
   from pathlib import Path
   import json
   from pipeline.explainer import load_explainer
   ex = load_explainer(Path('<EXPLAINER_PATH>'))
   print(json.dumps({
     'title': ex.title,
     'domain': ex.domain,
     'manifest': ex.manifest.model_dump(),
   }, indent=2, ensure_ascii=False))
   "
   ```

   ### Create project + copy explainer in

   ```bash
   PROJECT_ID="$(date +%Y%m%d-%H%M%S)-$(basename '<EXPLAINER_PATH>' .md)"
   PROJ="output/projects/$PROJECT_ID"
   mkdir -p "$PROJ/source"
   cp '<EXPLAINER_PATH>' "$PROJ/source/explainer.md"
   echo "$PROJECT_ID"
   ```

   ### Interactive manifest review (in chat, no extra API)

   Show the user a structured summary:
   - Title, domain, intent
   - `video_brief` (full text)
   - count of: verbatim_lines, key_facts, required_images, required_clips, required_sequence
   - first 3 of each list as a sample

   Then raise questions where the manifest is ambiguous. Always check:
   - Required images with no `role` hint → ask role (`intro_candidate`,
     `historical`, `comparison`, `aftermath`, etc.)
   - `verbatim_lines` longer than ~25 words → flag (will break narration cadence)
   - Conflicting `required_sequence` vs prose section order → ask which wins
   - Long explainer (>2000 words body) with empty `video_brief` → ask for direction
   - Required images with no caption → ask for one (used for storyboard scene generation)

   If the user wants changes, edit the manifest block(s) in the **wiki**
   explainer (the source of truth), then re-copy into `output/projects/<ID>/source/`.

   When the user approves, continue with Phase 2.
   ````

4. Update `## Phase 2 — Analyze` so it ends with this note:

   ```markdown
   **For explainer-path projects:** the manifest is the analyze input. Build
   `knowledge.json` from the explainer body + manifest (entities, facts cited
   in `key_facts`, etc.) — do NOT extract from a transcript (there isn't one).
   ```

5. Update `## Phase 3 — Storyboard` so it ends with:

   ```markdown
   **For explainer-path projects (manifest-aware):** treat the manifest as
   hard input — see `skills/storyboard/SKILL.md` "Manifest constraints" section.
   In short: every `verbatim_lines` entry must appear unmodified somewhere
   (narration/overlay/subtitle); every `required_images` path must appear in
   at least one scene's visual; `required_sequence` shapes scene order;
   `video_brief` shapes pacing and intro feel.
   ```

- [ ] **Step 3: Sanity-check the loader call works**

```bash
uv run python3 -c "
from pathlib import Path
from pipeline.explainer import load_explainer
ex = load_explainer(Path('tests/fixtures/explainers/sample-explainer.md'))
print(ex.title, ex.manifest.is_video_intent)
"
```

Expected output: `Sample Explainer True`

- [ ] **Step 4: Commit**

```bash
git add skills/produce/SKILL.md
git commit -m "feat(skills): produce — accept explainer path with manifest review

Adds an alternate Phase 1 branch when input is a path to an intent: video
explainer .md instead of a YouTube URL. The interactive manifest review
runs in-session — no extra API calls."
```

---

## Task 9: `storyboard` skill — manifest constraints

**Files:**
- Modify: `skills/storyboard/SKILL.md`

- [ ] **Step 1: Read current SKILL.md**

```bash
cat skills/storyboard/SKILL.md
```

- [ ] **Step 2: Append the Manifest constraints section**

Add at the end of `skills/storyboard/SKILL.md`:

```markdown

## Manifest constraints (explainer-path projects only)

When the project was started from a wiki explainer (i.e.
`output/projects/<ID>/source/explainer.md` exists with `intent: video`),
the manifest in its frontmatter is a HARD INPUT to storyboard generation:

| Manifest block | Constraint when generating storyboard |
|---|---|
| `verbatim_lines` | Each entry must appear *unmodified* in some scene's `narration`, `overlay.text`, or subtitle text. Don't paraphrase; the user marked these as exact. |
| `key_facts` | Each fact must be *stated* somewhere (narration is fine). Paraphrasing is OK. |
| `required_images` | Each `path` must appear as the `visual.path` of at least one scene. Use the `role` hint to choose placement (e.g. `intro_candidate` → s1 or s2). |
| `required_clips` | Same rule as `required_images`. |
| `required_sequence` | Phrases are free-form; honor the implied ordering when arranging scenes. |
| `video_brief` | Shapes pacing, transitions, intro feel. Read it before starting. Mention any constraints in your storyboard summary so the user can check. |

After writing the storyboard, do a self-check pass:

```bash
uv run python3 -c "
import json
from pathlib import Path
from pipeline.explainer import load_explainer
from pipeline.verifier import run_auto_checks
proj = Path('output/projects/<ID>')
ex = load_explainer(proj / 'source/explainer.md')
sb = json.loads((proj / 'storyboard.json').read_text())
result = run_auto_checks(ex.manifest, sb)
for it in result.items:
    if it.status == 'missing' and it.auto_checked:
        print(f'MISSING: {it.category} — {it.label}')
print(f'used={result.used_count} missing={result.missing_count}')
"
```

If any auto-checked item is `MISSING`, surface it to the user before proceeding to TTS.
```

- [ ] **Step 3: Commit**

```bash
git add skills/storyboard/SKILL.md
git commit -m "feat(skills): storyboard — manifest constraints for explainer projects"
```

---

## Task 10: End-to-end smoke test on the baby-walker explainer

**Files:**
- (No code changes; manual run)

- [ ] **Step 1: Confirm the baby-walker explainer has `intent: video`**

```bash
head -20 ~/know-fountains/wiki/parenting/explainers/baby-walker-story.md
```

If `intent: video` is not present, add it (and at minimum a placeholder `video_brief`) — this is the test data for the smoke run. Do this through the wiki repo (so the change is committed there):

```bash
cd ~/know-fountains
# (edit the file by hand or via the wiki skill)
# Add to frontmatter:
#   intent: video
#   video_brief: |
#     Smoke-test brief.
#   verbatim_lines:
#     - "Wheels + suspended seat = the one to avoid"
#   required_images:
#     - path: raw/parenting/baby-walker/assets/Jesus_in_a_baby_walker_from_the_Hours_of_Catherine_of_Cleves.jpg
#       role: intro_candidate
git add wiki/parenting/explainers/baby-walker-story.md
git commit -m "wiki: mark baby-walker explainer intent: video (smoke-test data)"
cd -
```

- [ ] **Step 2: Run produce against the explainer**

In a Claude Code session inside `content-creation`, invoke:

```
/produce ~/know-fountains/wiki/parenting/explainers/baby-walker-story.md
```

The skill should:
- Detect path-not-URL
- Load the manifest
- Create `output/projects/<NEW_ID>/source/explainer.md`
- Run the interactive review
- (After approval) generate storyboard

- [ ] **Step 3: Verify the verifier auto-checks**

After storyboard generation:

```bash
PROJECT_ID="<the new project id>"
uv run python3 -c "
import json
from pathlib import Path
from pipeline.explainer import load_explainer
from pipeline.verifier import run_auto_checks
proj = Path('output/projects/$PROJECT_ID')
ex = load_explainer(proj / 'source/explainer.md')
sb = json.loads((proj / 'storyboard.json').read_text())
r = run_auto_checks(ex.manifest, sb)
print(f'used={r.used_count} missing={r.missing_count}')
for it in r.items:
    print(f'  [{it.status}] {it.category}: {it.label[:60]}')
"
```

Expected: each `verbatim_lines` and `required_images` entry shows `used` (assuming storyboard honored the manifest).

- [ ] **Step 4: Open the dashboard verifier view**

```bash
./scripts/start-dashboard.sh --local-only
```

Then in a browser: `http://localhost:8765/verify/<PROJECT_ID>`

Expected: two-column layout. Click "OK to drop" on any item; refresh; status persists. Click "mark used" on a `key_fact`; refresh; status updates.

Inspect `output/projects/<PROJECT_ID>/verifier_state.json` — should reflect the toggles.

- [ ] **Step 5: Commit any docs/spec touch-ups discovered during smoke**

If you found anything wrong (assistant didn't honor a manifest item, UI didn't render correctly, etc.), fix and commit. Otherwise, no commit needed.

---

## Task 11: `produce` skill-size check + optional split

**Files:**
- Read: `skills/produce/SKILL.md`
- Maybe-create: `skills/import-explainer/SKILL.md` (only if size threshold crossed)

- [ ] **Step 1: Measure**

```bash
wc -l skills/produce/SKILL.md
```

- [ ] **Step 2: Decide**

Heuristic:
- Under ~250 lines: leave as-is. Stop.
- 250–400: optional split. If you have time, proceed; otherwise leave for now.
- Over 400: split.

- [ ] **Step 3: If splitting — dispatch codex:rescue**

If a split is warranted, dispatch the `codex:rescue` agent with this prompt:

> Split `skills/produce/SKILL.md`: extract the explainer-path branch into a
> separate `skills/import-explainer/SKILL.md` skill. The new skill's
> description should trigger when the user passes a path to a `.md` file
> with `intent: video` frontmatter to `/produce`. The original `produce`
> skill should refer to this new skill at the appropriate point and stay
> under 250 lines. Don't change the actual workflow content — just
> reorganize. Verify both files render valid YAML frontmatter.

- [ ] **Step 4: Commit (only if split occurred)**

```bash
git add skills/
git commit -m "refactor(skills): split explainer-path branch into import-explainer

produce/SKILL.md exceeded the 250-line readability heuristic; extracting
the explainer-path workflow keeps each skill focused."
```

---

## Done

After all tasks complete:

- All unit + integration tests pass: `uv run pytest tests/unit/test_explainer.py tests/unit/test_verifier.py tests/integration/test_dashboard_verifier_api.py -v`
- The baby-walker explainer (or any other `intent: video` page) can drive `/produce` end to end.
- The dashboard verifier view at `/verify/<id>` renders manifest ↔ scenes with toggles for "OK to drop" and "mark used."
- Both projects' settings are cross-linked.
- `skills/produce/SKILL.md` is at a healthy size.

Future work tracked in spec's "Open questions" section: semantic matching for `key_facts`, automatic sequence-honoring check, multi-explainer projects, drift detection, verifier export.
