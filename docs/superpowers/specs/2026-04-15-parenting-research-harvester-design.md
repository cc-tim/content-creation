# Parenting Research Harvester — Design

**Date:** 2026-04-15
**Status:** Spec — approved design, pending implementation plan
**Owner:** Tim

## 1. Motivation

Parenting videos need factual grounding: peer-reviewed research for the *why*,
and reputable institutional guidance (AAP, CDC, Harvard Center on the
Developing Child, etc.) for the *what to actually do*. Without a local corpus,
every video forces ad-hoc googling, inconsistent citations, and no
accumulation of reusable material.

This subsystem is a **local research corpus** for the content pipeline. It
fetches papers and institutional articles from free sources, stores them with
metadata, deduplicates across sources, and exposes a query interface that
feeds Claude during scriptwriting.

It is NOT a video-production stage. It is a standing library the scripting
stage draws from.

## 2. Scope

### In scope (MVP)

- Fetch from **OpenAlex** (peer-reviewed research) and **AAP**
  (`healthychildren.org` — institutional guidance) in English only.
- On-demand manual fetch (`pipeline research fetch ...`) and a one-shot
  harvest command across a small configured topic list.
- Local SQLite store with dedup by `(source, external_id)` and content hash.
- Raw payloads saved to disk for re-parsing.
- Query interface that emits a markdown "context pack" consumable by the
  scriptwriting stage.
- Unit tests for adapters (cassette-based) and store dedup; one
  network-marked integration test.

### Out of scope (tracked as future tasks, not MVP)

- Scheduled/daily harvest cron — revisit after one parenting video ships.
- Additional sources: PubMed/PMC, ERIC, Semantic Scholar, CDC, Harvard Center
  on the Developing Child, Zero to Three.
- zh-TW local sources (衛福部, 親子天下).
- Semantic/embedding retrieval — add when keyword + tag search feels
  insufficient, likely past ~1000 docs.
- A cross-source alias table for content-hash collisions (MVP skips-and-logs;
  we only need aliases once a second collidable source exists).

### MVP success criteria

1. `pipeline research harvest` populates the store with 10–20 documents
   across both OpenAlex and AAP, tagged against 2–3 topics.
2. `pipeline research query "<question>" --topic <t>` returns a usable
   context-pack markdown file.
3. One parenting video script is drafted using that context pack, and we can
   judge whether the corpus felt sufficient.

## 3. Architecture

### Subsystem boundary

A new package `src/pipeline/research/` sitting beside existing pipeline code.
It exposes a CLI and a Python query API, but is **not** a `PipelineStage`. The
scriptwriting stage (or the operator, manually) calls into it to produce a
context pack that gets fed to Claude.

### Directory layout

```
src/pipeline/research/
  __init__.py
  config.py          # topic list, source toggles, data dir path, rate limits
  models.py          # Pydantic: Document, Source, Topic, FetchResult
  store.py           # SQLite schema + CRUD + dedup (no adapter knowledge)
  adapters/
    base.py          # Adapter protocol
    openalex.py      # OpenAlex REST adapter
    aap.py           # healthychildren.org HTML scraper
  harvester.py       # orchestrates: run adapters × topics, write via store
  query.py           # search/filter + context-pack rendering
  cli.py             # Typer subcommands, wired into top-level pipeline CLI

research/            # gitignored data dir (sibling to output/)
  research.db        # SQLite
  raw/
    openalex/<work_id>.json
    aap/<url_hash>.html
```

### Unit responsibilities

- **`adapters/*`** — only source-specific code. Each adapter implements a
  single `search(topic, limit) -> Iterable[Document]`. Adapters handle their
  own HTTP, rate limiting, parsing, and failure logging. They never touch the
  DB or filesystem.
- **`store.py`** — the *only* writer of DB rows and raw files. Enforces both
  dedup gates. Readers go through `store.query(...)` helpers.
- **`harvester.py`** — loops topics × configured adapters, passes yielded
  `Document` objects to `store`, records a `fetch_log` row per run.
- **`query.py`** — filter/rank/render. MVP ranking is topic filter +
  recency + (OpenAlex) citation count. The function that renders a context
  pack is separate from the function that returns raw `Document` rows, so
  future callers (e.g., an embedding-based retriever) can swap ranking
  without touching rendering.
- **`cli.py`** — Typer subcommands. Mounted under the existing top-level
  `pipeline` Typer app as `pipeline research ...`.

## 4. Data model

### SQLite schema

```sql
CREATE TABLE documents (
  id              INTEGER PRIMARY KEY,
  source          TEXT NOT NULL,        -- 'openalex' | 'aap' | ...
  external_id     TEXT NOT NULL,        -- OpenAlex work ID, AAP canonical URL
  content_hash    TEXT NOT NULL,        -- SHA-256 of cleaned text
  title           TEXT NOT NULL,
  authors         TEXT,                 -- JSON array of names
  published_at    TEXT,                 -- ISO date, nullable
  url             TEXT NOT NULL,
  abstract        TEXT,                 -- nullable for AAP
  full_text_path  TEXT,                 -- relative under research/raw/, nullable
  language        TEXT NOT NULL DEFAULT 'en',
  fetched_at      TEXT NOT NULL,        -- ISO datetime
  raw_meta_json   TEXT NOT NULL,        -- full source payload for forensics
  UNIQUE(source, external_id)
);
CREATE INDEX idx_content_hash ON documents(content_hash);

CREATE TABLE document_topics (
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  topic       TEXT NOT NULL,
  PRIMARY KEY (document_id, topic)
);
CREATE INDEX idx_topic ON document_topics(topic);

CREATE TABLE fetch_log (
  id         INTEGER PRIMARY KEY,
  source     TEXT NOT NULL,
  topic      TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ended_at   TEXT,
  ok_count   INTEGER DEFAULT 0,
  dup_count  INTEGER DEFAULT 0,
  error      TEXT
);
```

### Dedup rules

- **Gate 1 — source-level:** `UNIQUE(source, external_id)` catches re-fetch
  of the same doc from the same source. On conflict, bump the existing row's
  `fetched_at`, add any missing topic tags, skip the raw-file rewrite.
- **Gate 2 — cross-source:** before insert, query by `content_hash`. On hit,
  MVP behavior is **skip the insert and log** under `fetch_log.error` as a
  `content_dup` note. An aliases table will be added in Phase 2 when PubMed
  (the most likely collider with OpenAlex) lands.
- `content_hash` is computed over the *cleaned text* (title + abstract for
  OpenAlex; title + article body text for AAP), not the raw JSON/HTML, so
  formatting differences don't break the gate.

### On-disk raw

- OpenAlex: `research/raw/openalex/<work_id>.json` — full Work object,
  including any PDF we successfully downloaded as
  `research/raw/openalex/<work_id>.pdf` when `open_access.oa_url` yields one.
- AAP: `research/raw/aap/<sha1(canonical_url)>.html` — the fetched page.

## 5. Adapters

### Base protocol

```python
from typing import Protocol, Iterable

class Adapter(Protocol):
    source_id: str

    def search(self, topic: str, limit: int) -> Iterable[Document]: ...
```

Adapters handle HTTP, rate limiting, parsing, and per-document failure. They
log errors and move on rather than raising to the harvester.

### OpenAlex

- Endpoint: `https://api.openalex.org/works`
- Auth: none; use the polite pool via `mailto=creditcardtim@gmail.com` query
  param for 10 req/s headroom.
- Filters per topic: `search=<topic>`, `type:article`, `language:en`,
  `from_publication_date:2018-01-01`, `is_oa:true` when we want
  open-access full text.
- Sort: `cited_by_count:desc` — cheapest "insightful" proxy for MVP.
- `external_id`: the last segment of `work.id` (e.g. `W2741809807`).
- Abstract: reconstruct from OpenAlex's inverted-index representation.
- Full-text: when `open_access.oa_url` is present, try GET with a 20s timeout;
  on success save to `raw/openalex/<work_id>.pdf` and set
  `full_text_path`. Failure is non-fatal — we still store the Work.
- Default topic list (editable in `config.py`):
  `sleep`, `screen_time`, `tantrums`, `discipline`, `parenting_styles`,
  `adhd`, `anxiety`, `early_literacy`.

### AAP (`healthychildren.org`)

- No API — HTML via `httpx` + `selectolax`.
- Per topic: hit the site search endpoint with the topic as the query,
  paginate conservatively (MVP: first 2 result pages), collect article URLs,
  fetch each, extract main `<article>` body + `<title>` + meta description +
  last-reviewed date.
- `external_id`: canonical URL with tracking params stripped.
- Rate limit: 1 req/sec. `User-Agent: content-creation-research-bot
  (contact: creditcardtim@gmail.com)`.
- `robots.txt`: honored via `urllib.robotparser`. Disallowed paths are
  skipped and logged, not crawled.

### Failure handling

Network error, parse error, or HTTP 4xx/5xx at the per-document level → the
adapter logs the error and continues. Adapter-level catastrophic failure
(e.g., site returns HTML that breaks the search results parser for every
page) is logged to `fetch_log.error` and the harvester moves to the next
source/topic.

## 6. CLI and consumption

### CLI surface (mounted under `pipeline research ...`)

```bash
# On-demand fetch
uv run pipeline research fetch --topic sleep --source openalex --limit 10
uv run pipeline research fetch --topic screen_time             # all sources

# Full configured harvest (all configured topics × all configured sources)
uv run pipeline research harvest

# Browse the corpus
uv run pipeline research list --topic sleep                    # rich table
uv run pipeline research show <doc_id>                         # full details
uv run pipeline research stats                                 # counts, dup rate

# Produce a context pack for scriptwriting
uv run pipeline research query "<natural-language question>" \
  --topic sleep --limit 10 --format context-pack \
  --output output/<project>/research_context.md
```

### Context pack format

`query --format context-pack` writes a single markdown file:

```markdown
# Research context: <question>
(<N> documents, retrieved <ISO date>)

## [1] <Title>
Authors, Year. Source: OpenAlex. URL: <url>
Abstract: ...

## [2] AAP: <Article title>
AAP healthychildren.org, last reviewed <date>. URL: <url>
Summary: <meta description or first paragraph>

---
```

The scriptwriting Claude prompt is instructed to cite these by number when
making factual claims, preferring peer-reviewed sources for causal/
mechanistic statements and AAP for practical parent-facing guidance.

### Retrieval for MVP

Deliberately dumb: topic filter → recency bias → (for OpenAlex)
citation-count sort → take top N. The ranking function is a single pure
function inside `query.py`; the Phase 3 embedding upgrade replaces its body
without touching the CLI or the context-pack renderer.

## 7. Config

`src/pipeline/research/config.py` uses pydantic-settings, like the rest of
the project, layering env → `.env` → TOML → defaults. Keys:

- `research.data_dir` — default `./research/`
- `research.topics` — default list above
- `research.sources.openalex.enabled` — default `true`
- `research.sources.openalex.mailto` — default
  `creditcardtim@gmail.com`
- `research.sources.aap.enabled` — default `true`
- `research.sources.aap.rate_limit_rps` — default `1.0`
- `research.default_limit_per_topic` — default `10`

## 8. Testing

- **Unit — adapters:** cassette-based (pytest fixtures of recorded JSON/HTML).
  Parsers must round-trip a realistic sample into a complete `Document`.
- **Unit — store dedup:** insert the same `(source, external_id)` twice,
  insert the same `content_hash` from two different sources — both must
  behave per §4 rules. `fetched_at` bump verified; topic-tag union verified.
- **Unit — query/rendering:** context-pack output is stable and deterministic
  for a fixed input set (so Claude prompts don't churn from whitespace).
- **Integration (`@pytest.mark.network`):** one live run of
  `fetch --topic sleep --source openalex --limit 2`, asserts rows land and
  raw files exist. Skipped by default in CI via the existing
  `not network` marker.

## 9. Dependencies

New:
- `httpx` — async-capable HTTP; MVP uses sync mode.
- `selectolax` — fast HTML parsing.

Not new (already in the project or Python stdlib):
- `pydantic`, `pydantic-settings`, `typer`, `sqlite3`, `hashlib`,
  `structlog`, `pytest`.

## 10. Phased follow-ups (tracked as tasks, out of this spec)

1. PubMed/PMC adapter.
2. ERIC adapter.
3. Semantic Scholar adapter (adds TL;DRs).
4. CDC child-development HTML scraper.
5. Harvard Center on the Developing Child scraper.
6. Zero to Three scraper.
7. Cross-source alias table for content-hash collisions.
8. zh-TW local sources (衛福部, 親子天下).
9. Scheduled daily/weekly harvest job.
10. Semantic/embedding retrieval upgrade.

## 11. Open questions

None blocking MVP. Decisions recorded above resolve the five clarifying
questions explored during brainstorming.
