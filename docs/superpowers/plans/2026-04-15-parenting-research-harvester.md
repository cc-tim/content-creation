# Parenting Research Harvester Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local research corpus subsystem that fetches parenting research from OpenAlex and AAP (`healthychildren.org`), deduplicates it, and emits markdown context packs for Claude scriptwriting.

**Architecture:** New `src/pipeline/research/` package. Source-specific adapters yield `Document` objects; a single `store` module writes them to SQLite + raw files with two dedup gates (source+external_id, content hash). A query module renders context-pack markdown from corpus rows. All functionality exposed via `pipeline research ...` Typer subcommands.

**Tech Stack:** Python 3.12, Pydantic, pydantic-settings, Typer, httpx (sync), selectolax, sqlite3 (stdlib), pytest, structlog. Follows existing project conventions (ruff+mypy strict, `uv run pytest`, markers `slow` / `integration` / `network`).

**Spec:** `docs/superpowers/specs/2026-04-15-parenting-research-harvester-design.md`

---

## File Structure

**Create:**
- `src/pipeline/research/__init__.py`
- `src/pipeline/research/config.py` — pydantic-settings for this subsystem
- `src/pipeline/research/models.py` — Pydantic `Document`, `FetchResult`
- `src/pipeline/research/store.py` — SQLite schema + upsert + dedup + queries
- `src/pipeline/research/adapters/__init__.py`
- `src/pipeline/research/adapters/base.py` — `Adapter` Protocol
- `src/pipeline/research/adapters/openalex.py` — OpenAlex REST adapter
- `src/pipeline/research/adapters/aap.py` — healthychildren.org HTML adapter
- `src/pipeline/research/harvester.py` — loop topics × adapters → store
- `src/pipeline/research/query.py` — rank + context-pack rendering
- `src/pipeline/research/cli.py` — Typer subcommands
- `tests/unit/research/__init__.py`
- `tests/unit/research/test_store.py`
- `tests/unit/research/test_openalex_adapter.py`
- `tests/unit/research/test_aap_adapter.py`
- `tests/unit/research/test_harvester.py`
- `tests/unit/research/test_query.py`
- `tests/unit/research/fixtures/openalex_sleep_sample.json`
- `tests/unit/research/fixtures/aap_search_results.html`
- `tests/unit/research/fixtures/aap_article.html`
- `tests/integration/test_research_live.py` — `@pytest.mark.network`

**Modify:**
- `pyproject.toml` — add `selectolax` dependency
- `.gitignore` — add `research/`
- `src/pipeline/cli.py` — mount `research_app` under the top-level `pipeline` app

---

## Task 1: Package skeleton, dependencies, gitignore

**Files:**
- Modify: `pyproject.toml`
- Modify: `.gitignore`
- Create: `src/pipeline/research/__init__.py`
- Create: `src/pipeline/research/adapters/__init__.py`

- [ ] **Step 1: Add selectolax dependency**

Edit `pyproject.toml` dependencies array — add after `"pillow>=12.2.0",`:

```toml
    "selectolax>=0.3.21",
```

- [ ] **Step 2: Ignore local research data dir**

Append to `.gitignore`:

```
research/
```

- [ ] **Step 3: Create empty package files**

Write `src/pipeline/research/__init__.py`:

```python
"""Local research corpus subsystem: fetch, store, query parenting research."""
```

Write `src/pipeline/research/adapters/__init__.py`:

```python
"""Source-specific fetch adapters."""
```

- [ ] **Step 4: Install and verify**

Run: `cd /home/tim-huang/content-creation && uv sync`
Expected: exits 0, `selectolax` appears in `uv.lock`.

Run: `uv run python -c "import selectolax; import pipeline.research"`
Expected: no output, exit 0.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock .gitignore src/pipeline/research/__init__.py src/pipeline/research/adapters/__init__.py
git commit -m "feat(research): scaffold research package + selectolax dep"
```

---

## Task 2: Domain models

**Files:**
- Create: `src/pipeline/research/models.py`
- Create: `tests/unit/research/__init__.py` (empty)
- Create: `tests/unit/research/test_models.py`

- [ ] **Step 1: Write the failing model tests**

Create `tests/unit/research/__init__.py` (empty file).

Write `tests/unit/research/test_models.py`:

```python
from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from pipeline.research.models import Document, FetchResult


def test_document_computes_content_hash_when_missing() -> None:
    doc = Document(
        source="openalex",
        external_id="W1",
        title="Sleep in toddlers",
        url="https://example.org/w1",
        abstract="A study of toddler sleep.",
        cleaned_text="Sleep in toddlers\n\nA study of toddler sleep.",
        fetched_at=datetime(2026, 4, 15, 12, 0, 0),
    )
    assert len(doc.content_hash) == 64  # sha256 hex


def test_document_same_cleaned_text_gives_same_hash() -> None:
    kwargs = dict(
        source="openalex",
        external_id="W1",
        title="T",
        url="https://example.org/w1",
        cleaned_text="identical body",
        fetched_at=datetime(2026, 4, 15, 12, 0, 0),
    )
    assert Document(**kwargs).content_hash == Document(**kwargs).content_hash


def test_document_requires_cleaned_text() -> None:
    with pytest.raises(ValidationError):
        Document(
            source="openalex",
            external_id="W1",
            title="T",
            url="https://example.org/w1",
            fetched_at=datetime(2026, 4, 15, 12, 0, 0),
        )  # type: ignore[call-arg]


def test_fetch_result_counts() -> None:
    r = FetchResult(source="openalex", topic="sleep", ok=3, duplicates=2)
    assert r.total == 5
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `uv run pytest tests/unit/research/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.research.models'`.

- [ ] **Step 3: Implement models**

Write `src/pipeline/research/models.py`:

```python
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Document(BaseModel):
    """A single research item landed in the corpus."""

    model_config = ConfigDict(frozen=True)

    source: str
    external_id: str
    title: str
    url: str
    cleaned_text: str = Field(
        ...,
        min_length=1,
        description="Normalized text used for content_hash (title + abstract/body).",
    )
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    published_at: str | None = None  # ISO date
    language: str = "en"
    full_text_path: str | None = None
    raw_meta: dict[str, Any] = Field(default_factory=dict)
    topics: list[str] = Field(default_factory=list)
    fetched_at: datetime
    content_hash: str = ""

    @model_validator(mode="after")
    def _fill_hash(self) -> Document:
        if not self.content_hash:
            digest = hashlib.sha256(self.cleaned_text.encode("utf-8")).hexdigest()
            object.__setattr__(self, "content_hash", digest)
        return self


class FetchResult(BaseModel):
    """Summary of one (source, topic) fetch pass."""

    source: str
    topic: str
    ok: int = 0
    duplicates: int = 0
    errors: list[str] = Field(default_factory=list)

    @property
    def total(self) -> int:
        return self.ok + self.duplicates
```

- [ ] **Step 4: Run the tests to verify pass**

Run: `uv run pytest tests/unit/research/test_models.py -v`
Expected: 4 passed.

- [ ] **Step 5: Lint + typecheck**

Run: `uv run ruff check src/pipeline/research tests/unit/research && uv run mypy src/pipeline/research`
Expected: both exit 0.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/research/models.py tests/unit/research/__init__.py tests/unit/research/test_models.py
git commit -m "feat(research): Document + FetchResult models with content hashing"
```

---

## Task 3: Config

**Files:**
- Create: `src/pipeline/research/config.py`

- [ ] **Step 1: Implement config**

Write `src/pipeline/research/config.py`:

```python
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OpenAlexConfig(BaseModel):
    enabled: bool = True
    mailto: str = "creditcardtim@gmail.com"
    from_publication_date: str = "2018-01-01"
    sort: str = "cited_by_count:desc"


class AAPConfig(BaseModel):
    enabled: bool = True
    rate_limit_rps: float = 1.0
    max_result_pages: int = 2
    user_agent: str = (
        "content-creation-research-bot (contact: creditcardtim@gmail.com)"
    )


class ResearchSources(BaseModel):
    openalex: OpenAlexConfig = Field(default_factory=OpenAlexConfig)
    aap: AAPConfig = Field(default_factory=AAPConfig)


class ResearchConfig(BaseSettings):
    """Config for the local research corpus subsystem."""

    model_config = SettingsConfigDict(
        env_prefix="RESEARCH_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )

    data_dir: Path = Path("./research")
    default_limit_per_topic: int = 10
    topics: list[str] = Field(
        default_factory=lambda: [
            "sleep",
            "screen_time",
            "tantrums",
            "discipline",
            "parenting_styles",
            "adhd",
            "anxiety",
            "early_literacy",
        ]
    )
    sources: ResearchSources = Field(default_factory=ResearchSources)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "research.db"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"
```

- [ ] **Step 2: Quick smoke test**

Run: `uv run python -c "from pipeline.research.config import ResearchConfig; c = ResearchConfig(); print(c.db_path, c.sources.openalex.mailto)"`
Expected: prints `research/research.db creditcardtim@gmail.com`.

- [ ] **Step 3: Lint + typecheck**

Run: `uv run ruff check src/pipeline/research && uv run mypy src/pipeline/research`
Expected: both exit 0.

- [ ] **Step 4: Commit**

```bash
git add src/pipeline/research/config.py
git commit -m "feat(research): pydantic-settings config for topics and sources"
```

---

## Task 4: Store — schema init + insert

**Files:**
- Create: `src/pipeline/research/store.py`
- Create: `tests/unit/research/test_store.py`

- [ ] **Step 1: Write the failing store tests (schema + insert + gate 1)**

Write `tests/unit/research/test_store.py`:

```python
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from pipeline.research.models import Document
from pipeline.research.store import ResearchStore


def _doc(
    *,
    source: str = "openalex",
    external_id: str = "W1",
    cleaned_text: str = "body A",
    topics: list[str] | None = None,
) -> Document:
    return Document(
        source=source,
        external_id=external_id,
        title="T",
        url="https://example.org/" + external_id,
        abstract="abs",
        cleaned_text=cleaned_text,
        topics=topics or ["sleep"],
        fetched_at=datetime(2026, 4, 15, 12, 0, 0),
    )


@pytest.fixture()
def store(tmp_path: Path) -> ResearchStore:
    return ResearchStore(data_dir=tmp_path)


def test_store_creates_schema(store: ResearchStore) -> None:
    tables = {row[0] for row in store.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert {"documents", "document_topics", "fetch_log"}.issubset(tables)


def test_insert_returns_inserted(store: ResearchStore) -> None:
    result = store.upsert(_doc(), raw_bytes=b"{}", raw_ext="json")
    assert result.status == "inserted"
    row = store.conn.execute(
        "SELECT source, external_id, content_hash FROM documents"
    ).fetchone()
    assert row == ("openalex", "W1", _doc().content_hash)


def test_insert_writes_raw_file(store: ResearchStore, tmp_path: Path) -> None:
    store.upsert(_doc(), raw_bytes=b'{"hello":true}', raw_ext="json")
    raw = tmp_path / "raw" / "openalex" / "W1.json"
    assert raw.read_bytes() == b'{"hello":true}'


def test_same_source_and_external_id_is_source_dup(store: ResearchStore) -> None:
    store.upsert(_doc(topics=["sleep"]), raw_bytes=b"{}", raw_ext="json")
    result = store.upsert(
        _doc(topics=["sleep", "toddler"]), raw_bytes=b"{}", raw_ext="json"
    )
    assert result.status == "source_duplicate"
    topics = {
        t for (t,) in store.conn.execute(
            "SELECT topic FROM document_topics"
        ).fetchall()
    }
    assert topics == {"sleep", "toddler"}
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/research/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.research.store'`.

- [ ] **Step 3: Implement store (schema + upsert + gate 1)**

Write `src/pipeline/research/store.py`:

```python
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pipeline.research.models import Document

UpsertStatus = Literal["inserted", "source_duplicate", "content_duplicate"]


@dataclass(frozen=True)
class UpsertResult:
    status: UpsertStatus
    document_id: int | None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  id              INTEGER PRIMARY KEY,
  source          TEXT NOT NULL,
  external_id     TEXT NOT NULL,
  content_hash    TEXT NOT NULL,
  title           TEXT NOT NULL,
  authors         TEXT,
  published_at    TEXT,
  url             TEXT NOT NULL,
  abstract        TEXT,
  full_text_path  TEXT,
  language        TEXT NOT NULL DEFAULT 'en',
  fetched_at      TEXT NOT NULL,
  raw_meta_json   TEXT NOT NULL,
  UNIQUE(source, external_id)
);
CREATE INDEX IF NOT EXISTS idx_content_hash ON documents(content_hash);

CREATE TABLE IF NOT EXISTS document_topics (
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  topic       TEXT NOT NULL,
  PRIMARY KEY (document_id, topic)
);
CREATE INDEX IF NOT EXISTS idx_topic ON document_topics(topic);

CREATE TABLE IF NOT EXISTS fetch_log (
  id         INTEGER PRIMARY KEY,
  source     TEXT NOT NULL,
  topic      TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ended_at   TEXT,
  ok_count   INTEGER DEFAULT 0,
  dup_count  INTEGER DEFAULT 0,
  error      TEXT
);
"""


class ResearchStore:
    """Single writer for the research corpus (SQLite + raw files)."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "raw").mkdir(exist_ok=True)
        self.conn = sqlite3.connect(self.data_dir / "research.db")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def upsert(
        self, doc: Document, *, raw_bytes: bytes, raw_ext: str
    ) -> UpsertResult:
        cur = self.conn.cursor()
        existing = cur.execute(
            "SELECT id FROM documents WHERE source = ? AND external_id = ?",
            (doc.source, doc.external_id),
        ).fetchone()
        if existing is not None:
            doc_id = existing[0]
            cur.execute(
                "UPDATE documents SET fetched_at = ? WHERE id = ?",
                (doc.fetched_at.isoformat(), doc_id),
            )
            self._merge_topics(doc_id, doc.topics)
            self.conn.commit()
            return UpsertResult(status="source_duplicate", document_id=doc_id)

        raw_path = self._write_raw(doc, raw_bytes, raw_ext)
        cur.execute(
            """
            INSERT INTO documents (
                source, external_id, content_hash, title, authors,
                published_at, url, abstract, full_text_path, language,
                fetched_at, raw_meta_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc.source,
                doc.external_id,
                doc.content_hash,
                doc.title,
                json.dumps(doc.authors),
                doc.published_at,
                doc.url,
                doc.abstract,
                doc.full_text_path or str(raw_path.relative_to(self.data_dir)),
                doc.language,
                doc.fetched_at.isoformat(),
                json.dumps(doc.raw_meta),
            ),
        )
        doc_id = int(cur.lastrowid or 0)
        self._merge_topics(doc_id, doc.topics)
        self.conn.commit()
        return UpsertResult(status="inserted", document_id=doc_id)

    def _merge_topics(self, document_id: int, topics: list[str]) -> None:
        self.conn.executemany(
            "INSERT OR IGNORE INTO document_topics (document_id, topic) VALUES (?, ?)",
            [(document_id, t) for t in topics],
        )

    def _write_raw(self, doc: Document, raw_bytes: bytes, ext: str) -> Path:
        target_dir = self.data_dir / "raw" / doc.source
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_id = doc.external_id.replace("/", "_")
        path = target_dir / f"{safe_id}.{ext}"
        path.write_bytes(raw_bytes)
        return path

    def start_fetch(self, source: str, topic: str) -> int:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO fetch_log (source, topic, started_at) VALUES (?, ?, ?)",
            (source, topic, datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def finish_fetch(
        self,
        fetch_id: int,
        *,
        ok: int,
        duplicates: int,
        error: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE fetch_log
               SET ended_at = ?, ok_count = ?, dup_count = ?, error = ?
             WHERE id = ?
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                ok,
                duplicates,
                error,
                fetch_id,
            ),
        )
        self.conn.commit()
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/unit/research/test_store.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/research/store.py tests/unit/research/test_store.py
git commit -m "feat(research): SQLite store with source-level dedup and raw-file layout"
```

---

## Task 5: Store — content-hash dedup (Gate 2)

**Files:**
- Modify: `src/pipeline/research/store.py`
- Modify: `tests/unit/research/test_store.py`

- [ ] **Step 1: Add the failing content-dup test**

Append to `tests/unit/research/test_store.py`:

```python
def test_same_content_from_different_source_is_content_dup(
    store: ResearchStore,
) -> None:
    first = _doc(source="openalex", external_id="W1", cleaned_text="same body")
    second = _doc(source="aap", external_id="https://aap/x", cleaned_text="same body")
    assert store.upsert(first, raw_bytes=b"{}", raw_ext="json").status == "inserted"
    result = store.upsert(second, raw_bytes=b"<html>", raw_ext="html")
    assert result.status == "content_duplicate"
    count = store.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    assert count == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/research/test_store.py::test_same_content_from_different_source_is_content_dup -v`
Expected: FAIL — current code inserts the second doc as a fresh row.

- [ ] **Step 3: Add Gate 2 to `upsert`**

In `src/pipeline/research/store.py`, inside `upsert(...)` *after* the Gate 1 `existing is not None` block and *before* `raw_path = self._write_raw(...)`, insert:

```python
        content_match = cur.execute(
            "SELECT id FROM documents WHERE content_hash = ?",
            (doc.content_hash,),
        ).fetchone()
        if content_match is not None:
            self.conn.commit()
            return UpsertResult(
                status="content_duplicate", document_id=content_match[0]
            )
```

- [ ] **Step 4: Run full store test file**

Run: `uv run pytest tests/unit/research/test_store.py -v`
Expected: 5 passed.

- [ ] **Step 5: Lint + typecheck**

Run: `uv run ruff check src/pipeline/research tests/unit/research && uv run mypy src/pipeline/research`
Expected: both exit 0.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/research/store.py tests/unit/research/test_store.py
git commit -m "feat(research): content-hash dedup across sources"
```

---

## Task 6: Store — query helpers

**Files:**
- Modify: `src/pipeline/research/store.py`
- Modify: `tests/unit/research/test_store.py`

- [ ] **Step 1: Write the failing query tests**

Append to `tests/unit/research/test_store.py`:

```python
def test_list_by_topic_returns_tagged_docs(store: ResearchStore) -> None:
    store.upsert(
        _doc(external_id="W1", cleaned_text="a", topics=["sleep"]),
        raw_bytes=b"{}",
        raw_ext="json",
    )
    store.upsert(
        _doc(external_id="W2", cleaned_text="b", topics=["discipline"]),
        raw_bytes=b"{}",
        raw_ext="json",
    )
    sleep_docs = store.list_documents(topic="sleep")
    assert [d.external_id for d in sleep_docs] == ["W1"]


def test_list_all_when_no_topic(store: ResearchStore) -> None:
    store.upsert(
        _doc(external_id="W1", cleaned_text="a"),
        raw_bytes=b"{}",
        raw_ext="json",
    )
    store.upsert(
        _doc(external_id="W2", cleaned_text="b"),
        raw_bytes=b"{}",
        raw_ext="json",
    )
    assert {d.external_id for d in store.list_documents()} == {"W1", "W2"}


def test_stats_summarizes_corpus(store: ResearchStore) -> None:
    store.upsert(
        _doc(source="openalex", external_id="W1", cleaned_text="a",
             topics=["sleep"]),
        raw_bytes=b"{}",
        raw_ext="json",
    )
    store.upsert(
        _doc(source="aap", external_id="https://aap/x", cleaned_text="b",
             topics=["sleep", "discipline"]),
        raw_bytes=b"<html>",
        raw_ext="html",
    )
    stats = store.stats()
    assert stats["by_source"] == {"openalex": 1, "aap": 1}
    assert stats["by_topic"] == {"sleep": 2, "discipline": 1}
    assert stats["total"] == 2
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/research/test_store.py -v`
Expected: 3 new tests FAIL with `AttributeError: 'ResearchStore' object has no attribute 'list_documents'` (and `stats`).

- [ ] **Step 3: Add query helpers to store**

At end of `ResearchStore` class in `src/pipeline/research/store.py`, add these methods and the needed import:

Import addition (top of file, alongside existing imports):

```python
from typing import Any as _Any
```

Methods (append inside the class):

```python
    def list_documents(
        self,
        *,
        topic: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, _Any]]:
        if topic:
            rows = self.conn.execute(
                """
                SELECT d.* FROM documents d
                  JOIN document_topics t ON t.document_id = d.id
                 WHERE t.topic = ?
                 ORDER BY COALESCE(d.published_at, '') DESC, d.id DESC
                 LIMIT ?
                """,
                (topic, limit or 10_000),
            )
        else:
            rows = self.conn.execute(
                """
                SELECT * FROM documents
                 ORDER BY COALESCE(published_at, '') DESC, id DESC
                 LIMIT ?
                """,
                (limit or 10_000,),
            )
        cols = [c[0] for c in rows.description]
        results: list[dict[str, _Any]] = []
        for row in rows:
            rec = dict(zip(cols, row, strict=True))
            rec["external_id"] = rec["external_id"]
            results.append(_RowView(rec))
        return results  # type: ignore[return-value]

    def stats(self) -> dict[str, _Any]:
        total = self.conn.execute(
            "SELECT COUNT(*) FROM documents"
        ).fetchone()[0]
        by_source = dict(
            self.conn.execute(
                "SELECT source, COUNT(*) FROM documents GROUP BY source"
            ).fetchall()
        )
        by_topic = dict(
            self.conn.execute(
                "SELECT topic, COUNT(*) FROM document_topics GROUP BY topic"
            ).fetchall()
        )
        return {"total": total, "by_source": by_source, "by_topic": by_topic}
```

Add this helper class at module top-level (below the imports, above `UpsertStatus`):

```python
class _RowView(dict[str, _Any]):
    """Dict subclass that also exposes keys as attributes (for tests + query)."""

    def __getattr__(self, name: str) -> _Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/unit/research/test_store.py -v`
Expected: 8 passed.

- [ ] **Step 5: Lint + typecheck**

Run: `uv run ruff check src/pipeline/research tests/unit/research && uv run mypy src/pipeline/research`
Expected: both exit 0.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/research/store.py tests/unit/research/test_store.py
git commit -m "feat(research): store query helpers (list_documents, stats)"
```

---

## Task 7: Adapter base protocol

**Files:**
- Create: `src/pipeline/research/adapters/base.py`

- [ ] **Step 1: Implement base**

Write `src/pipeline/research/adapters/base.py`:

```python
from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from pipeline.research.models import Document


@runtime_checkable
class Adapter(Protocol):
    """A source-specific fetcher. Does NOT touch the store or filesystem.

    Adapters yield Document objects with cleaned_text populated and the
    raw payload available via .raw_meta (for JSON sources) or by
    returning (Document, raw_bytes, raw_ext) tuples via `search_raw`.
    """

    source_id: str

    def search_raw(
        self, topic: str, limit: int
    ) -> Iterable[tuple[Document, bytes, str]]:
        """Yield (doc, raw_bytes, raw_ext) for each result.

        raw_ext is the file extension to store raw_bytes under
        (e.g. 'json' for API payloads, 'html' for scraped pages).
        """
        ...
```

- [ ] **Step 2: Lint + typecheck**

Run: `uv run ruff check src/pipeline/research && uv run mypy src/pipeline/research`
Expected: both exit 0.

- [ ] **Step 3: Commit**

```bash
git add src/pipeline/research/adapters/base.py
git commit -m "feat(research): Adapter protocol"
```

---

## Task 8: OpenAlex adapter — parse fixture

**Files:**
- Create: `tests/unit/research/fixtures/openalex_sleep_sample.json`
- Create: `tests/unit/research/test_openalex_adapter.py`
- Create: `src/pipeline/research/adapters/openalex.py`

- [ ] **Step 1: Create a realistic fixture**

Write `tests/unit/research/fixtures/openalex_sleep_sample.json`:

```json
{
  "results": [
    {
      "id": "https://openalex.org/W2741809807",
      "title": "Sleep regulation in early childhood",
      "publication_date": "2022-03-15",
      "language": "en",
      "authorships": [
        {"author": {"display_name": "Jane Smith"}},
        {"author": {"display_name": "Carlos Ruiz"}}
      ],
      "abstract_inverted_index": {
        "Sleep": [0],
        "patterns": [1],
        "in": [2],
        "toddlers": [3],
        "vary": [4],
        "widely.": [5]
      },
      "cited_by_count": 42,
      "open_access": {"is_oa": true, "oa_url": null},
      "primary_location": {"landing_page_url": "https://journal.example/w/1"}
    }
  ]
}
```

- [ ] **Step 2: Write the failing parser test**

Write `tests/unit/research/test_openalex_adapter.py`:

```python
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pipeline.research.adapters.openalex import OpenAlexAdapter

FIXTURE = Path(__file__).parent / "fixtures" / "openalex_sleep_sample.json"


def test_parse_work_builds_document() -> None:
    payload = json.loads(FIXTURE.read_text())
    work = payload["results"][0]
    adapter = OpenAlexAdapter(mailto="test@example.com")
    doc, raw_bytes, raw_ext = adapter.parse_work(work, topic="sleep",
                                                 fetched_at=datetime(2026, 4, 15))
    assert doc.source == "openalex"
    assert doc.external_id == "W2741809807"
    assert doc.title == "Sleep regulation in early childhood"
    assert doc.published_at == "2022-03-15"
    assert doc.authors == ["Jane Smith", "Carlos Ruiz"]
    assert doc.abstract == "Sleep patterns in toddlers vary widely."
    assert "sleep" in doc.topics
    assert doc.raw_meta["cited_by_count"] == 42
    assert raw_ext == "json"
    assert json.loads(raw_bytes)["id"].endswith("W2741809807")
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/unit/research/test_openalex_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.research.adapters.openalex'`.

- [ ] **Step 4: Implement OpenAlex parse + search_raw**

Write `src/pipeline/research/adapters/openalex.py`:

```python
from __future__ import annotations

import json
import time
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

from pipeline.research.models import Document

log = structlog.get_logger(__name__)

_BASE = "https://api.openalex.org/works"


class OpenAlexAdapter:
    source_id = "openalex"

    def __init__(
        self,
        *,
        mailto: str,
        from_publication_date: str = "2018-01-01",
        sort: str = "cited_by_count:desc",
        client: httpx.Client | None = None,
    ) -> None:
        self.mailto = mailto
        self.from_publication_date = from_publication_date
        self.sort = sort
        self._client = client or httpx.Client(
            timeout=20.0,
            headers={"User-Agent": f"content-creation-research-bot ({mailto})"},
        )

    def search_raw(
        self, topic: str, limit: int
    ) -> Iterable[tuple[Document, bytes, str]]:
        params = {
            "search": topic,
            "per_page": str(min(limit, 50)),
            "filter": (
                f"type:article,language:en,"
                f"from_publication_date:{self.from_publication_date}"
            ),
            "sort": self.sort,
            "mailto": self.mailto,
        }
        log.info("openalex.search", topic=topic, limit=limit)
        resp = self._client.get(_BASE, params=params)
        resp.raise_for_status()
        payload = resp.json()
        fetched_at = datetime.now(timezone.utc)
        for work in payload.get("results", [])[:limit]:
            try:
                yield self.parse_work(work, topic=topic, fetched_at=fetched_at)
            except Exception as exc:  # adapter-local tolerance
                log.warning("openalex.parse_failed",
                            id=work.get("id"), error=str(exc))
            time.sleep(0.1)  # polite pool headroom

    def parse_work(
        self,
        work: dict[str, Any],
        *,
        topic: str,
        fetched_at: datetime,
    ) -> tuple[Document, bytes, str]:
        external_id = work["id"].rsplit("/", 1)[-1]
        title = work.get("title") or ""
        authors = [
            a["author"]["display_name"]
            for a in work.get("authorships", [])
            if a.get("author", {}).get("display_name")
        ]
        abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))
        url = (
            work.get("primary_location", {}).get("landing_page_url")
            or work["id"]
        )
        cleaned_text = f"{title}\n\n{abstract or ''}".strip()
        raw_meta = {
            "cited_by_count": work.get("cited_by_count", 0),
            "is_oa": work.get("open_access", {}).get("is_oa"),
            "oa_url": work.get("open_access", {}).get("oa_url"),
        }
        doc = Document(
            source=self.source_id,
            external_id=external_id,
            title=title,
            url=url,
            abstract=abstract,
            cleaned_text=cleaned_text,
            authors=authors,
            published_at=work.get("publication_date"),
            language=work.get("language") or "en",
            raw_meta=raw_meta,
            topics=[topic],
            fetched_at=fetched_at,
        )
        raw_bytes = json.dumps(work, ensure_ascii=False).encode("utf-8")
        return doc, raw_bytes, "json"


def _reconstruct_abstract(inv: dict[str, list[int]] | None) -> str | None:
    if not inv:
        return None
    positions: dict[int, str] = {}
    for word, idxs in inv.items():
        for i in idxs:
            positions[i] = word
    ordered = [positions[i] for i in sorted(positions)]
    return " ".join(ordered)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/unit/research/test_openalex_adapter.py -v`
Expected: 1 passed.

- [ ] **Step 6: Lint + typecheck**

Run: `uv run ruff check src/pipeline/research tests/unit/research && uv run mypy src/pipeline/research`
Expected: both exit 0.

- [ ] **Step 7: Commit**

```bash
git add tests/unit/research/fixtures/openalex_sleep_sample.json tests/unit/research/test_openalex_adapter.py src/pipeline/research/adapters/openalex.py
git commit -m "feat(research): OpenAlex adapter with Work parsing"
```

---

## Task 9: OpenAlex adapter — search_raw with mocked HTTP

**Files:**
- Modify: `tests/unit/research/test_openalex_adapter.py`

- [ ] **Step 1: Write failing search_raw test using MockTransport**

Append to `tests/unit/research/test_openalex_adapter.py`:

```python
import httpx


def test_search_raw_yields_documents_via_mock_transport() -> None:
    payload = json.loads(FIXTURE.read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/works"
        assert "mailto=test%40example.com" in str(request.url)
        assert "search=sleep" in str(request.url)
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = OpenAlexAdapter(mailto="test@example.com", client=client)
    results = list(adapter.search_raw("sleep", limit=10))
    assert len(results) == 1
    doc, _raw, ext = results[0]
    assert doc.external_id == "W2741809807"
    assert ext == "json"
```

- [ ] **Step 2: Run to verify pass (the implementation already covers this)**

Run: `uv run pytest tests/unit/research/test_openalex_adapter.py -v`
Expected: 2 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/research/test_openalex_adapter.py
git commit -m "test(research): OpenAlex search_raw covered via MockTransport"
```

---

## Task 10: AAP adapter — fixtures + parser

**Files:**
- Create: `tests/unit/research/fixtures/aap_search_results.html`
- Create: `tests/unit/research/fixtures/aap_article.html`
- Create: `tests/unit/research/test_aap_adapter.py`
- Create: `src/pipeline/research/adapters/aap.py`

- [ ] **Step 1: Create search-results fixture**

Write `tests/unit/research/fixtures/aap_search_results.html`:

```html
<!doctype html>
<html><body>
<div class="srch-Results">
  <a class="srch-Title" href="https://www.healthychildren.org/English/ages-stages/toddler/Pages/Healthy-Sleep-Habits.aspx">Healthy Sleep Habits</a>
  <a class="srch-Title" href="https://www.healthychildren.org/English/ages-stages/baby/sleep/Pages/Getting-Your-Baby-to-Sleep.aspx">Getting Your Baby to Sleep</a>
</div>
</body></html>
```

- [ ] **Step 2: Create article fixture**

Write `tests/unit/research/fixtures/aap_article.html`:

```html
<!doctype html>
<html>
<head>
  <title>Healthy Sleep Habits — HealthyChildren.org</title>
  <meta name="description" content="Consistent routines support toddler sleep.">
</head>
<body>
<article>
  <h1>Healthy Sleep Habits</h1>
  <p>Toddlers need 11 to 14 hours of sleep, including naps.</p>
  <p>Keep bedtimes consistent, even on weekends.</p>
  <span class="last-reviewed">Last reviewed: 2024-07-12</span>
</article>
</body></html>
```

- [ ] **Step 3: Write failing AAP parser tests**

Write `tests/unit/research/test_aap_adapter.py`:

```python
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import httpx

from pipeline.research.adapters.aap import AAPAdapter

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_article_extracts_fields() -> None:
    html = (FIXTURES / "aap_article.html").read_text()
    adapter = AAPAdapter()
    doc, raw, ext = adapter.parse_article(
        url="https://www.healthychildren.org/English/ages-stages/toddler/"
            "Pages/Healthy-Sleep-Habits.aspx",
        html=html,
        topic="sleep",
        fetched_at=datetime(2026, 4, 15),
    )
    assert doc.source == "aap"
    assert doc.external_id.startswith("https://www.healthychildren.org/")
    assert doc.title.startswith("Healthy Sleep Habits")
    assert "Toddlers need 11 to 14 hours" in doc.cleaned_text
    assert doc.published_at == "2024-07-12"
    assert doc.abstract == "Consistent routines support toddler sleep."
    assert ext == "html"
    assert raw == html.encode("utf-8")


def test_parse_search_results_extracts_urls() -> None:
    html = (FIXTURES / "aap_search_results.html").read_text()
    adapter = AAPAdapter()
    urls = adapter.parse_search_results(html)
    assert urls == [
        "https://www.healthychildren.org/English/ages-stages/toddler/Pages/Healthy-Sleep-Habits.aspx",
        "https://www.healthychildren.org/English/ages-stages/baby/sleep/Pages/Getting-Your-Baby-to-Sleep.aspx",
    ]


def test_search_raw_fetches_article_pages_via_mock_transport() -> None:
    search_html = (FIXTURES / "aap_search_results.html").read_text()
    article_html = (FIXTURES / "aap_article.html").read_text()

    def handler(request: httpx.Request) -> httpx.Response:
        if "search-results" in request.url.path or "search" in request.url.path:
            return httpx.Response(200, text=search_html)
        return httpx.Response(200, text=article_html)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = AAPAdapter(client=client, rate_limit_rps=1000.0)
    results = list(adapter.search_raw("sleep", limit=2))
    assert len(results) == 2
    for doc, raw, ext in results:
        assert doc.source == "aap"
        assert ext == "html"
        assert raw == article_html.encode("utf-8")
```

- [ ] **Step 4: Run to verify failure**

Run: `uv run pytest tests/unit/research/test_aap_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.research.adapters.aap'`.

- [ ] **Step 5: Implement AAP adapter**

Write `src/pipeline/research/adapters/aap.py`:

```python
from __future__ import annotations

import re
import time
from collections.abc import Iterable
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

import httpx
import structlog
from selectolax.parser import HTMLParser

from pipeline.research.models import Document

log = structlog.get_logger(__name__)

_SEARCH_URL = "https://www.healthychildren.org/English/search-results/Pages/results.aspx"


class AAPAdapter:
    source_id = "aap"

    def __init__(
        self,
        *,
        user_agent: str = "content-creation-research-bot "
                         "(contact: creditcardtim@gmail.com)",
        rate_limit_rps: float = 1.0,
        max_result_pages: int = 2,
        client: httpx.Client | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.rate_delay = 1.0 / rate_limit_rps if rate_limit_rps > 0 else 0.0
        self.max_result_pages = max_result_pages
        self._client = client or httpx.Client(
            timeout=20.0,
            headers={"User-Agent": user_agent},
            follow_redirects=True,
        )

    def search_raw(
        self, topic: str, limit: int
    ) -> Iterable[tuple[Document, bytes, str]]:
        log.info("aap.search", topic=topic, limit=limit)
        yielded = 0
        for page in range(1, self.max_result_pages + 1):
            try:
                resp = self._client.get(
                    _SEARCH_URL,
                    params={"k": topic, "pg": str(page)},
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                log.warning("aap.search_failed", page=page, error=str(exc))
                break
            urls = self.parse_search_results(resp.text)
            if not urls:
                break
            for url in urls:
                if yielded >= limit:
                    return
                time.sleep(self.rate_delay)
                try:
                    article_resp = self._client.get(url)
                    article_resp.raise_for_status()
                except httpx.HTTPError as exc:
                    log.warning("aap.article_failed", url=url, error=str(exc))
                    continue
                try:
                    yield self.parse_article(
                        url=url,
                        html=article_resp.text,
                        topic=topic,
                        fetched_at=datetime.now(timezone.utc),
                    )
                except Exception as exc:
                    log.warning("aap.parse_failed", url=url, error=str(exc))
                    continue
                yielded += 1
            time.sleep(self.rate_delay)

    def parse_search_results(self, html: str) -> list[str]:
        tree = HTMLParser(html)
        out: list[str] = []
        for node in tree.css("a.srch-Title"):
            href = node.attributes.get("href")
            if href:
                out.append(_canonicalize(href))
        return out

    def parse_article(
        self,
        *,
        url: str,
        html: str,
        topic: str,
        fetched_at: datetime,
    ) -> tuple[Document, bytes, str]:
        tree = HTMLParser(html)

        title_node = tree.css_first("h1") or tree.css_first("title")
        title = (title_node.text(strip=True) if title_node else "").split(" — ")[0]

        desc_node = tree.css_first('meta[name="description"]')
        abstract = (
            desc_node.attributes.get("content") if desc_node is not None else None
        )

        article = tree.css_first("article") or tree.body
        body_text = article.text(separator="\n", strip=True) if article else ""

        published_at: str | None = None
        reviewed = tree.css_first(".last-reviewed")
        if reviewed is not None:
            m = re.search(r"(\d{4}-\d{2}-\d{2})", reviewed.text())
            if m:
                published_at = m.group(1)

        cleaned_text = f"{title}\n\n{body_text}".strip()
        doc = Document(
            source=self.source_id,
            external_id=_canonicalize(url),
            title=title,
            url=_canonicalize(url),
            abstract=abstract,
            cleaned_text=cleaned_text,
            authors=[],
            published_at=published_at,
            language="en",
            raw_meta={},
            topics=[topic],
            fetched_at=fetched_at,
        )
        return doc, html.encode("utf-8"), "html"


def _canonicalize(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/unit/research/test_aap_adapter.py -v`
Expected: 3 passed.

- [ ] **Step 7: Lint + typecheck**

Run: `uv run ruff check src/pipeline/research tests/unit/research && uv run mypy src/pipeline/research`
Expected: both exit 0.

- [ ] **Step 8: Commit**

```bash
git add tests/unit/research/fixtures/aap_search_results.html tests/unit/research/fixtures/aap_article.html tests/unit/research/test_aap_adapter.py src/pipeline/research/adapters/aap.py
git commit -m "feat(research): AAP healthychildren.org adapter"
```

---

## Task 11: Harvester

**Files:**
- Create: `src/pipeline/research/harvester.py`
- Create: `tests/unit/research/test_harvester.py`

- [ ] **Step 1: Write the failing harvester test**

Write `tests/unit/research/test_harvester.py`:

```python
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from pipeline.research.harvester import Harvester
from pipeline.research.models import Document
from pipeline.research.store import ResearchStore


class _StubAdapter:
    def __init__(self, source: str, docs: list[Document]) -> None:
        self.source_id = source
        self._docs = docs

    def search_raw(
        self, topic: str, limit: int
    ) -> Iterable[tuple[Document, bytes, str]]:
        for d in self._docs:
            yield d, b"{}", "json"


def _doc(source: str, ext_id: str, body: str) -> Document:
    return Document(
        source=source,
        external_id=ext_id,
        title="T",
        url=f"https://x/{ext_id}",
        abstract="a",
        cleaned_text=body,
        topics=["sleep"],
        fetched_at=datetime(2026, 4, 15),
    )


def test_harvester_writes_new_and_counts_dups(tmp_path: Path) -> None:
    store = ResearchStore(data_dir=tmp_path)
    adapter = _StubAdapter(
        "openalex",
        [
            _doc("openalex", "W1", "body A"),
            _doc("openalex", "W2", "body B"),
            _doc("openalex", "W1", "body A"),  # source dup
        ],
    )
    h = Harvester(store=store, adapters=[adapter])
    results = h.harvest_topic("sleep", limit=10)
    assert len(results) == 1
    assert results[0].ok == 2
    assert results[0].duplicates == 1


def test_harvester_runs_all_configured_topics(tmp_path: Path) -> None:
    store = ResearchStore(data_dir=tmp_path)
    adapter = _StubAdapter("openalex", [_doc("openalex", "W1", "b")])
    h = Harvester(store=store, adapters=[adapter])
    results = h.harvest(topics=["sleep", "discipline"], limit=5)
    assert len(results) == 2
    assert {r.topic for r in results} == {"sleep", "discipline"}
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/research/test_harvester.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.research.harvester'`.

- [ ] **Step 3: Implement harvester**

Write `src/pipeline/research/harvester.py`:

```python
from __future__ import annotations

from collections.abc import Sequence

import structlog

from pipeline.research.adapters.base import Adapter
from pipeline.research.models import FetchResult
from pipeline.research.store import ResearchStore

log = structlog.get_logger(__name__)


class Harvester:
    def __init__(self, *, store: ResearchStore, adapters: Sequence[Adapter]) -> None:
        self.store = store
        self.adapters = list(adapters)

    def harvest(self, *, topics: Sequence[str], limit: int) -> list[FetchResult]:
        results: list[FetchResult] = []
        for topic in topics:
            results.extend(self.harvest_topic(topic, limit=limit))
        return results

    def harvest_topic(self, topic: str, *, limit: int) -> list[FetchResult]:
        results: list[FetchResult] = []
        for adapter in self.adapters:
            fetch_id = self.store.start_fetch(adapter.source_id, topic)
            ok = 0
            dups = 0
            errors: list[str] = []
            try:
                for doc, raw_bytes, raw_ext in adapter.search_raw(topic, limit):
                    try:
                        res = self.store.upsert(
                            doc, raw_bytes=raw_bytes, raw_ext=raw_ext
                        )
                    except Exception as exc:
                        errors.append(f"{doc.external_id}: {exc}")
                        continue
                    if res.status == "inserted":
                        ok += 1
                    else:
                        dups += 1
            except Exception as exc:
                log.warning(
                    "harvester.adapter_failed",
                    source=adapter.source_id,
                    topic=topic,
                    error=str(exc),
                )
                errors.append(str(exc))
            self.store.finish_fetch(
                fetch_id,
                ok=ok,
                duplicates=dups,
                error="; ".join(errors) if errors else None,
            )
            results.append(
                FetchResult(
                    source=adapter.source_id, topic=topic,
                    ok=ok, duplicates=dups, errors=errors,
                )
            )
        return results
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/unit/research/test_harvester.py -v`
Expected: 2 passed.

- [ ] **Step 5: Lint + typecheck**

Run: `uv run ruff check src/pipeline/research tests/unit/research && uv run mypy src/pipeline/research`
Expected: both exit 0.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/research/harvester.py tests/unit/research/test_harvester.py
git commit -m "feat(research): harvester orchestrating adapters × topics"
```

---

## Task 12: Query + context pack renderer

**Files:**
- Create: `src/pipeline/research/query.py`
- Create: `tests/unit/research/test_query.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/unit/research/test_query.py`:

```python
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pipeline.research.models import Document
from pipeline.research.query import render_context_pack, rank
from pipeline.research.store import ResearchStore


def _doc(ext_id: str, *, cited: int, year: str,
         source: str = "openalex", topic: str = "sleep") -> Document:
    return Document(
        source=source,
        external_id=ext_id,
        title=f"Title {ext_id}",
        url=f"https://x/{ext_id}",
        abstract="Abstract text.",
        cleaned_text=f"body {ext_id}",
        topics=[topic],
        published_at=f"{year}-01-01",
        raw_meta={"cited_by_count": cited},
        authors=["Anon"],
        fetched_at=datetime(2026, 4, 15),
    )


def test_rank_prefers_openalex_high_citations_then_recency() -> None:
    a = _doc("W1", cited=5, year="2020")
    b = _doc("W2", cited=100, year="2019")
    c = _doc("https://aap/x", cited=0, year="2024", source="aap")
    ordered = rank([a, b, c], question="sleep")
    assert [d.external_id for d in ordered] == ["W2", "W1", "https://aap/x"]


def test_context_pack_renders_citations_and_topics(tmp_path: Path) -> None:
    store = ResearchStore(data_dir=tmp_path)
    docs = [
        _doc("W1", cited=10, year="2022"),
        _doc("https://aap/sleep", cited=0, year="2024", source="aap"),
    ]
    md = render_context_pack(
        question="toddler sleep regression",
        documents=docs,
        now=datetime(2026, 4, 15),
    )
    assert md.startswith("# Research context: toddler sleep regression")
    assert "## [1] Title W1" in md
    assert "## [2] " in md
    assert "Source: OpenAlex" in md
    assert "AAP healthychildren.org" in md
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/research/test_query.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.research.query'`.

- [ ] **Step 3: Implement query module**

Write `src/pipeline/research/query.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any

from pipeline.research.models import Document


def rank(documents: list[Document], *, question: str) -> list[Document]:
    """MVP ranking: source priority, then citation count, then recency.

    OpenAlex peer-reviewed work outranks AAP for the "insightful research"
    slot, but both always show up. Within each bucket, higher citation count
    wins; ties broken by newer publication date.
    """

    def key(d: Document) -> tuple[int, int, str]:
        source_rank = 0 if d.source == "openalex" else 1
        cited = int(d.raw_meta.get("cited_by_count", 0) or 0)
        pub = d.published_at or ""
        return (source_rank, -cited, _neg_date(pub))

    return sorted(documents, key=key)


def _neg_date(iso: str) -> str:
    # Sort newest first lexicographically by inverting components.
    if not iso:
        return "~"
    return "".join(chr(255 - ord(c)) if c.isdigit() else c for c in iso)


def render_context_pack(
    *,
    question: str,
    documents: list[Document],
    now: datetime,
) -> str:
    ordered = rank(documents, question=question)
    lines: list[str] = [
        f"# Research context: {question}",
        f"({len(ordered)} documents, retrieved {now.date().isoformat()})",
        "",
    ]
    for i, doc in enumerate(ordered, start=1):
        lines.append(f"## [{i}] {doc.title}")
        if doc.source == "openalex":
            year = (doc.published_at or "").split("-")[0]
            authors = ", ".join(doc.authors) or "Unknown"
            lines.append(
                f"{authors}, {year}. Source: OpenAlex. URL: {doc.url}"
            )
            if doc.abstract:
                lines.append(f"Abstract: {doc.abstract}")
        elif doc.source == "aap":
            reviewed = doc.published_at or "n/a"
            lines.append(
                f"AAP healthychildren.org, last reviewed {reviewed}. "
                f"URL: {doc.url}"
            )
            if doc.abstract:
                lines.append(f"Summary: {doc.abstract}")
        else:
            lines.append(f"Source: {doc.source}. URL: {doc.url}")
            if doc.abstract:
                lines.append(f"Summary: {doc.abstract}")
        lines.append("")
    lines.append("---")
    return "\n".join(lines) + "\n"


def rows_to_documents(rows: list[dict[str, Any]]) -> list[Document]:
    """Adapt store rows (see ResearchStore.list_documents) to Document models."""
    import json as _json

    out: list[Document] = []
    for row in rows:
        out.append(
            Document(
                source=row["source"],
                external_id=row["external_id"],
                title=row["title"],
                url=row["url"],
                abstract=row.get("abstract"),
                cleaned_text=row.get("title", "") + "\n\n" +
                (row.get("abstract") or ""),
                authors=_json.loads(row.get("authors") or "[]"),
                published_at=row.get("published_at"),
                language=row.get("language") or "en",
                full_text_path=row.get("full_text_path"),
                raw_meta=_json.loads(row.get("raw_meta_json") or "{}"),
                topics=[],
                fetched_at=datetime.fromisoformat(row["fetched_at"]),
                content_hash=row["content_hash"],
            )
        )
    return out
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/research/test_query.py -v`
Expected: 2 passed.

- [ ] **Step 5: Lint + typecheck**

Run: `uv run ruff check src/pipeline/research tests/unit/research && uv run mypy src/pipeline/research`
Expected: both exit 0.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/research/query.py tests/unit/research/test_query.py
git commit -m "feat(research): ranking and context-pack renderer"
```

---

## Task 13: CLI subcommands

**Files:**
- Create: `src/pipeline/research/cli.py`
- Modify: `src/pipeline/cli.py` — mount the new Typer app

- [ ] **Step 1: Implement the research Typer app**

Write `src/pipeline/research/cli.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import typer

from pipeline.research.adapters.aap import AAPAdapter
from pipeline.research.adapters.base import Adapter
from pipeline.research.adapters.openalex import OpenAlexAdapter
from pipeline.research.config import ResearchConfig
from pipeline.research.harvester import Harvester
from pipeline.research.query import render_context_pack, rows_to_documents
from pipeline.research.store import ResearchStore

app = typer.Typer(name="research", help="Local parenting-research corpus.")


def _build_adapters(cfg: ResearchConfig, only: str | None) -> list[Adapter]:
    out: list[Adapter] = []
    if cfg.sources.openalex.enabled and only in (None, "openalex"):
        out.append(
            OpenAlexAdapter(
                mailto=cfg.sources.openalex.mailto,
                from_publication_date=cfg.sources.openalex.from_publication_date,
                sort=cfg.sources.openalex.sort,
            )
        )
    if cfg.sources.aap.enabled and only in (None, "aap"):
        out.append(
            AAPAdapter(
                user_agent=cfg.sources.aap.user_agent,
                rate_limit_rps=cfg.sources.aap.rate_limit_rps,
                max_result_pages=cfg.sources.aap.max_result_pages,
            )
        )
    return out


@app.command()
def fetch(
    topic: str = typer.Option(..., "--topic"),
    source: str | None = typer.Option(None, "--source",
                                      help="openalex | aap (default: all)"),
    limit: int = typer.Option(10, "--limit"),
) -> None:
    """Fetch one topic from one or all configured sources."""
    cfg = ResearchConfig()
    store = ResearchStore(data_dir=cfg.data_dir)
    adapters = _build_adapters(cfg, only=source)
    if not adapters:
        raise typer.BadParameter(f"no enabled source matches --source={source}")
    results = Harvester(store=store, adapters=adapters).harvest_topic(
        topic, limit=limit
    )
    for r in results:
        typer.echo(f"{r.source} / {r.topic}: ok={r.ok} dup={r.duplicates}"
                   + (f" errors={len(r.errors)}" if r.errors else ""))


@app.command()
def harvest(
    limit: int | None = typer.Option(None, "--limit"),
) -> None:
    """Run all configured topics × all enabled sources."""
    cfg = ResearchConfig()
    store = ResearchStore(data_dir=cfg.data_dir)
    adapters = _build_adapters(cfg, only=None)
    if not adapters:
        raise typer.BadParameter("no sources enabled in config")
    results = Harvester(store=store, adapters=adapters).harvest(
        topics=cfg.topics,
        limit=limit or cfg.default_limit_per_topic,
    )
    for r in results:
        typer.echo(f"{r.source} / {r.topic}: ok={r.ok} dup={r.duplicates}")


@app.command(name="list")
def list_docs(
    topic: str | None = typer.Option(None, "--topic"),
    limit: int = typer.Option(50, "--limit"),
) -> None:
    """Browse the corpus."""
    cfg = ResearchConfig()
    store = ResearchStore(data_dir=cfg.data_dir)
    rows = store.list_documents(topic=topic, limit=limit)
    for row in rows:
        typer.echo(
            f"[{row['id']}] ({row['source']}) {row['published_at'] or '    '} "
            f"{row['title']}"
        )


@app.command()
def show(doc_id: int = typer.Argument(...)) -> None:
    cfg = ResearchConfig()
    store = ResearchStore(data_dir=cfg.data_dir)
    row = store.conn.execute(
        "SELECT * FROM documents WHERE id = ?", (doc_id,)
    ).fetchone()
    if row is None:
        raise typer.Exit(code=1)
    cols = [c[0] for c in store.conn.execute(
        "SELECT * FROM documents WHERE id = ?", (doc_id,)
    ).description]
    rec = dict(zip(cols, row, strict=True))
    typer.echo(f"Title:   {rec['title']}")
    typer.echo(f"Source:  {rec['source']}  ({rec['external_id']})")
    typer.echo(f"URL:     {rec['url']}")
    typer.echo(f"Pub:     {rec['published_at']}")
    typer.echo(f"Abstract:\n{rec['abstract'] or '(none)'}")


@app.command()
def stats() -> None:
    cfg = ResearchConfig()
    store = ResearchStore(data_dir=cfg.data_dir)
    s = store.stats()
    typer.echo(f"total: {s['total']}")
    typer.echo(f"by source: {s['by_source']}")
    typer.echo(f"by topic:  {s['by_topic']}")


@app.command()
def query(
    question: str = typer.Argument(...),
    topic: str | None = typer.Option(None, "--topic"),
    limit: int = typer.Option(10, "--limit"),
    output: Path = typer.Option(..., "--output"),
    fmt: str = typer.Option("context-pack", "--format"),
) -> None:
    """Produce a context pack markdown file for scriptwriting."""
    if fmt != "context-pack":
        raise typer.BadParameter("only --format context-pack is supported in MVP")
    cfg = ResearchConfig()
    store = ResearchStore(data_dir=cfg.data_dir)
    rows = store.list_documents(topic=topic, limit=limit)
    docs = rows_to_documents(rows)
    md = render_context_pack(
        question=question,
        documents=docs,
        now=datetime.now(timezone.utc),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(md, encoding="utf-8")
    typer.echo(f"wrote {len(docs)} documents to {output}")
```

- [ ] **Step 2: Mount the app in the top-level CLI**

In `src/pipeline/cli.py`, add under the existing `app.add_typer(...)` lines:

```python
from pipeline.research.cli import app as research_app
app.add_typer(research_app, name="research")
```

(Place the import near the other `pipeline.*` imports and the `add_typer` call beside the others.)

- [ ] **Step 3: Smoke-test the CLI**

Run: `uv run pipeline research --help`
Expected: lists subcommands `fetch`, `harvest`, `list`, `show`, `stats`, `query`.

Run: `uv run pipeline research stats`
Expected: prints `total: 0`, empty dicts (creates an empty `research/research.db` on first run).

- [ ] **Step 4: Lint + typecheck**

Run: `uv run ruff check src/pipeline && uv run mypy src/pipeline/research src/pipeline/cli.py`
Expected: both exit 0.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/research/cli.py src/pipeline/cli.py
git commit -m "feat(research): Typer CLI + top-level mount"
```

---

## Task 14: Network-marked live integration test

**Files:**
- Create: `tests/integration/test_research_live.py`

- [ ] **Step 1: Write the live test (skipped by default in CI)**

Write `tests/integration/test_research_live.py`:

```python
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
```

- [ ] **Step 2: Verify it's skipped by default**

Run: `uv run pytest tests/integration/test_research_live.py -v -m "not network"`
Expected: deselected (0 run).

- [ ] **Step 3: Run it for real (requires network)**

Run: `uv run pytest tests/integration/test_research_live.py -v -m network`
Expected: 1 passed.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_research_live.py
git commit -m "test(research): network-marked live OpenAlex fetch"
```

---

## Task 15: Full-suite sanity + MVP smoke

**Files:** none (verification only)

- [ ] **Step 1: Run the full fast test suite**

Run: `uv run pytest -m "not slow and not network and not integration"`
Expected: all pass.

- [ ] **Step 2: Lint + typecheck the whole package**

Run: `uv run ruff check src/ tests/ && uv run mypy src/pipeline/research`
Expected: both exit 0.

- [ ] **Step 3: Run a real MVP harvest**

Run: `uv run pipeline research harvest --limit 5`
Expected: logs `openalex / <topic>: ok=N dup=M` for each topic; non-zero total.

Run: `uv run pipeline research stats`
Expected: totals across multiple topics, both `openalex` and `aap` represented (if AAP is reachable; if blocked by robots.txt/site changes, we still want openalex counts and AAP errors in the fetch log — investigate before claiming MVP complete).

- [ ] **Step 4: Produce a sample context pack**

Run:
```bash
uv run pipeline research query "toddler sleep regression" \
  --topic sleep --limit 8 \
  --output output/smoke/research_context.md
```
Expected: writes the file, `wc -l output/smoke/research_context.md` > 20.

- [ ] **Step 5: Commit nothing (verification task)**

No commit. If any of steps 1–4 failed, open a follow-up task before declaring MVP complete.

---

## Self-Review Checklist

- [x] Spec §2 (scope MVP) — covered by Tasks 1–15.
- [x] Spec §3 (architecture/layout) — Task 1 creates the layout; Tasks 2–13 fill it; Task 13 wires the CLI.
- [x] Spec §4 (data model incl. dedup gates) — Tasks 4–6.
- [x] Spec §5 (adapters: OpenAlex + AAP) — Tasks 7–10.
- [x] Spec §6 (CLI + consumption) — Task 13 (CLI), Task 12 (context pack).
- [x] Spec §7 (config) — Task 3.
- [x] Spec §8 (testing: adapter cassettes, store dedup, network-marked integration) — covered by Tasks 4–6, 8–10, 14.
- [x] Spec §9 (dependencies) — Task 1 adds `selectolax`; `httpx` already present.
- [x] Placeholder scan — no "TBD", "TODO", or vague steps. All code blocks are complete.
- [x] Type consistency — `UpsertResult`/`UpsertStatus` used consistently in Tasks 4/5/11. `FetchResult` fields (`ok`, `duplicates`, `errors`, `total`) consistent across Tasks 2/11. `Document` field names stable across Tasks 2/4/6/8/10/11/12.
