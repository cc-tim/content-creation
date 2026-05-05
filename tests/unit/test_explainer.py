from pathlib import Path

import pytest

from pipeline.explainer import (
    Explainer,
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
