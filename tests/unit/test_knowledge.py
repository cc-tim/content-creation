from pathlib import Path

import pytest

from pipeline.knowledge import Knowledge


@pytest.fixture
def sample_knowledge() -> Knowledge:
    path = Path(__file__).parent.parent / "fixtures" / "sample_knowledge.json"
    return Knowledge.load(path)


def test_knowledge_load_from_fixture(sample_knowledge):
    assert sample_knowledge.meta.source_type == "youtube"
    assert len(sample_knowledge.facts) == 3
    assert len(sample_knowledge.entities) == 2
    assert len(sample_knowledge.timeline) == 3
    assert sample_knowledge.facts[0].id == "f1"
    assert sample_knowledge.facts[0].verified is False


def test_knowledge_round_trip(tmp_path, sample_knowledge):
    out = tmp_path / "knowledge.json"
    sample_knowledge.save(out)
    loaded = Knowledge.load(out)
    assert len(loaded.facts) == len(sample_knowledge.facts)
    assert loaded.facts[0].text == sample_knowledge.facts[0].text
    assert loaded.meta.source_url == sample_knowledge.meta.source_url
    assert loaded.meta.updated_at != ""  # save() sets updated_at


def test_add_fact(sample_knowledge):
    new_fact = sample_knowledge.add_fact(
        text="Driver fled on foot after crash",
        source="manual",
        tags=["foot-chase", "arrest"],
    )
    assert new_fact.id == "f4"
    assert new_fact.source == "manual"
    assert len(sample_knowledge.facts) == 4


def test_update_fact(sample_knowledge):
    result = sample_knowledge.update_fact("f1", text="Updated text", verified=True)
    assert result is not None
    assert result.text == "Updated text"
    assert result.verified is True


def test_remove_fact(sample_knowledge):
    assert sample_knowledge.remove_fact("f2") is True
    assert len(sample_knowledge.facts) == 2
    assert sample_knowledge.get_fact("f2") is None


def test_remove_nonexistent_fact(sample_knowledge):
    assert sample_knowledge.remove_fact("f999") is False


def test_facts_by_tags(sample_knowledge):
    chase_facts = sample_knowledge.facts_by_tags(["chase"])
    assert len(chase_facts) == 1
    assert chase_facts[0].id == "f2"

    danger_facts = sample_knowledge.facts_by_tags(["danger", "crime"])
    assert len(danger_facts) == 2  # f1 (crime) + f3 (danger)
