---
name: knowledge
description: View and edit the Layer 1 knowledge base (facts, entities, timeline, context bridges) for a pipeline project. Use when asked to show knowledge, add facts, fix entities, or update context bridges.
version: 1.0.0
metadata:
  openclaw:
    requirements:
      binaries: [uv]
---

# Knowledge — View & Edit

The knowledge base is `output/projects/<ID>/knowledge.json`. It's the structured
representation of the source video — the foundation for storyboard and script.

## View

```bash
cd /home/tim-huang/content-creation

# Summary view
cat output/projects/<ID>/knowledge.json | python3 -c "
import json, sys
k = json.load(sys.stdin)
print(f'Facts:    {len(k.get(\"facts\",[]))}')
print(f'Entities: {len(k.get(\"entities\",[]))}')
print(f'Timeline: {len(k.get(\"timeline\",[]))} events')
print()
for f in k.get('facts',[])[:10]:
    print(f'  {f[\"id\"]}: {f[\"text\"][:100]}')
"

# Full JSON
cat output/projects/<ID>/knowledge.json
```

## Schema

```json
{
  "facts": [
    {
      "id": "f1",
      "text": "...",
      "timestamp_sec": 45,
      "tags": ["person", "event"],
      "source": "transcript"
    }
  ],
  "entities": [
    {"id": "e1", "type": "person", "name": "...", "role": "..."}
  ],
  "timeline": [
    {"timestamp_sec": 0, "event": "...", "facts_ref": ["f1", "f2"]}
  ],
  "context_bridges": [
    {"concept": "...", "explanation": "..."}
  ]
}
```

## Edit

To add or modify facts, read the file, make changes in Python, and write back:

```bash
uv run python3 - <<'EOF'
import json
from pathlib import Path

path = Path('output/projects/<ID>/knowledge.json')
k = json.loads(path.read_text())

# Add a fact
k['facts'].append({
    "id": f"f{len(k['facts'])+1}",
    "text": "新增的事實描述",
    "timestamp_sec": None,
    "tags": ["custom"],
    "source": "enrichment"
})

path.write_text(json.dumps(k, indent=2, ensure_ascii=False))
print(f'Updated: {len(k["facts"])} facts')
EOF
```

After editing knowledge, re-derive the script if the storyboard references changed facts.
