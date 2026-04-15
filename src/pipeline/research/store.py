from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
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

        content_match = cur.execute(
            "SELECT id FROM documents WHERE content_hash = ?",
            (doc.content_hash,),
        ).fetchone()
        if content_match is not None:
            self.conn.commit()
            return UpsertResult(
                status="content_duplicate", document_id=content_match[0]
            )

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
            (source, topic, datetime.now(UTC).isoformat()),
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
                datetime.now(UTC).isoformat(),
                ok,
                duplicates,
                error,
                fetch_id,
            ),
        )
        self.conn.commit()
