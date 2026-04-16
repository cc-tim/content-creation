from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.research.adapters.openalex import OpenAlexAdapter
from pipeline.research.harvester import Harvester
from pipeline.research.store import ResearchStore


@pytest.mark.network
def test_live_openalex_sleep_fetch(tmp_path: Path) -> None:
    store = ResearchStore(data_dir=tmp_path)
    adapter = OpenAlexAdapter(mailto="creditcardtim@gmail.com")
    results = Harvester(store=store, adapters=[adapter]).harvest_topic(
        "sleep", limit=2
    )
    assert len(results) == 1
    r = results[0]
    assert r.source == "openalex"
    assert (r.ok + r.duplicates) >= 1, f"got no results, errors={r.errors}"
    rows = store.list_documents(topic="sleep")
    assert len(rows) >= 1
    raw_dir = tmp_path / "raw" / "openalex"
    assert any(raw_dir.iterdir())
