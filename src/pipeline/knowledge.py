from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class Fact:
    id: str
    text: str
    timestamp: str | None = None
    source: str = "transcript"  # transcript | web | manual | enrichment
    verified: bool = False
    tags: list[str] = field(default_factory=list)


@dataclass
class Entity:
    id: str
    name: str
    role: str
    details: str = ""


@dataclass
class TimelineEvent:
    time: str
    event: str
    facts: list[str] = field(default_factory=list)  # fact IDs


@dataclass
class KnowledgeMeta:
    source_type: str  # youtube | web | manual
    source_url: str
    title: str
    locale: str
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Knowledge:
    """Layer 1: Knowledge base — facts, entities, timeline, context bridges."""

    meta: KnowledgeMeta
    facts: list[Fact] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    timeline: list[TimelineEvent] = field(default_factory=list)
    context_bridges: list[str] = field(default_factory=list)

    # --- Serialization ---

    def to_dict(self) -> dict[str, Any]:
        return {
            "meta": {
                "source_type": self.meta.source_type,
                "source_url": self.meta.source_url,
                "title": self.meta.title,
                "locale": self.meta.locale,
                "created_at": self.meta.created_at,
                "updated_at": self.meta.updated_at,
            },
            "facts": [
                {
                    "id": f.id,
                    "text": f.text,
                    "timestamp": f.timestamp,
                    "source": f.source,
                    "verified": f.verified,
                    "tags": f.tags,
                }
                for f in self.facts
            ],
            "entities": [
                {"id": e.id, "name": e.name, "role": e.role, "details": e.details}
                for e in self.entities
            ],
            "timeline": [
                {"time": t.time, "event": t.event, "facts": t.facts} for t in self.timeline
            ],
            "context_bridges": self.context_bridges,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Knowledge:
        if "meta" in data:
            meta = KnowledgeMeta(**data["meta"])
        else:
            # Legacy format: meta fields at top level
            meta = KnowledgeMeta(
                source_type=data.get("source_type", "youtube"),
                source_url=data.get("source_url", ""),
                title=data.get("source_title", data.get("topic", "")),
                locale=data.get("locale", "zh-TW"),
                created_at=data.get("created_at", ""),
                updated_at=data.get("updated_at", ""),
            )
        facts = [Fact(**f) for f in data.get("facts", [])]
        entities = [
            Entity(
                id=e["id"],
                name=e["name"],
                role=e.get("role", e.get("type", "")),
                details=e.get("details", ""),
            )
            for e in data.get("entities", [])
        ]
        timeline = [
            TimelineEvent(
                time=t.get("time", t.get("when", "")),
                event=t.get("event", t.get("what", "")),
                facts=t.get("facts", t.get("facts_ref", [])),
            )
            for t in data.get("timeline", [])
        ]
        context_bridges = data.get("context_bridges", [])
        return cls(
            meta=meta,
            facts=facts,
            entities=entities,
            timeline=timeline,
            context_bridges=context_bridges,
        )

    def save(self, path: Path) -> None:
        self.meta.updated_at = datetime.now().isoformat()
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> Knowledge:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    # --- Fact CRUD ---

    def add_fact(
        self,
        text: str,
        source: str = "manual",
        timestamp: str | None = None,
        tags: list[str] | None = None,
    ) -> Fact:
        next_id = f"f{len(self.facts) + 1}"
        fact = Fact(
            id=next_id,
            text=text,
            timestamp=timestamp,
            source=source,
            tags=tags or [],
        )
        self.facts.append(fact)
        return fact

    def get_fact(self, fact_id: str) -> Fact | None:
        for f in self.facts:
            if f.id == fact_id:
                return f
        return None

    def update_fact(
        self,
        fact_id: str,
        text: str | None = None,
        verified: bool | None = None,
        tags: list[str] | None = None,
    ) -> Fact | None:
        fact = self.get_fact(fact_id)
        if fact is None:
            return None
        if text is not None:
            fact.text = text
        if verified is not None:
            fact.verified = verified
        if tags is not None:
            fact.tags = tags
        return fact

    def remove_fact(self, fact_id: str) -> bool:
        for i, f in enumerate(self.facts):
            if f.id == fact_id:
                self.facts.pop(i)
                return True
        return False

    def facts_by_tags(self, tags: list[str]) -> list[Fact]:
        """Return facts that have ANY of the given tags."""
        tag_set = set(tags)
        return [f for f in self.facts if tag_set & set(f.tags)]
