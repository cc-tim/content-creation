---
name: knowledge
description: View and edit the Layer 1 knowledge base (facts, entities, timeline, context bridges) for a pipeline project.
---

# Knowledge Base Manager

View and edit the Layer 1 knowledge base for a project.

## Input

- **Arguments:** $ARGUMENTS
- Formats: `<project-id>`, `show <project-id>`, `edit <project-id>`
- If no project ID, ask for one.

## Show (default)

Display the knowledge base contents:

```bash
uv run python3 -c "
from pathlib import Path
from pipeline.knowledge import Knowledge
k = Knowledge.load(Path('output/projects/<ID>/knowledge.json'))
print(f'Source: {k.meta.source_url}')
print(f'Title: {k.meta.title}')
print()
print('=== FACTS ===')
for f in k.facts:
    status = 'VERIFIED' if f.verified else 'unverified'
    tags = ', '.join(f.tags) if f.tags else 'none'
    print(f'  [{f.id}] ({status}) {f.text}')
    print(f'        tags: {tags}')
print()
print('=== ENTITIES ===')
for e in k.entities:
    print(f'  [{e.id}] {e.name} — {e.role}')
print()
print('=== TIMELINE ===')
for t in k.timeline:
    refs = ', '.join(t.facts)
    print(f'  {t.time}: {t.event} (refs: {refs})')
print()
print('=== CONTEXT BRIDGES ===')
for c in k.context_bridges:
    print(f'  - {c}')
"
```

Present to the user and ask what they'd like to change.

## Editing

When the user wants changes, use Python to load, modify, and save:

**Update a fact:**
```bash
uv run python3 -c "
from pathlib import Path
from pipeline.knowledge import Knowledge
k = Knowledge.load(Path('output/projects/<ID>/knowledge.json'))
k.update_fact('<FACT_ID>', text='<NEW_TEXT>', verified=True)
k.save(Path('output/projects/<ID>/knowledge.json'))
print('Updated <FACT_ID>')
"
```

**Add a fact:**
```bash
uv run python3 -c "
from pathlib import Path
from pipeline.knowledge import Knowledge
k = Knowledge.load(Path('output/projects/<ID>/knowledge.json'))
f = k.add_fact(text='<TEXT>', source='manual', tags=['<tag1>'])
k.save(Path('output/projects/<ID>/knowledge.json'))
print(f'Added {f.id}: {f.text}')
"
```

**Remove a fact:**
```bash
uv run python3 -c "
from pathlib import Path
from pipeline.knowledge import Knowledge
k = Knowledge.load(Path('output/projects/<ID>/knowledge.json'))
k.remove_fact('<FACT_ID>')
k.save(Path('output/projects/<ID>/knowledge.json'))
print('Removed <FACT_ID>')
"
```

**Verify a fact:**
```bash
uv run python3 -c "
from pathlib import Path
from pipeline.knowledge import Knowledge
k = Knowledge.load(Path('output/projects/<ID>/knowledge.json'))
k.update_fact('<FACT_ID>', verified=True)
k.save(Path('output/projects/<ID>/knowledge.json'))
print('Verified <FACT_ID>')
"
```

## Important

- Always show the current state after any edit
- Ask for confirmation before removing facts
- When the user describes changes in natural language, map to the right operation
- Multiple edits in one interaction are fine — save after each one
