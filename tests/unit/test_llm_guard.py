import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "pipeline"
ALLOWED = {SRC / "llm.py"}


def test_only_the_llm_module_talks_to_anthropic():
    bad = []
    for py in sorted(SRC.rglob("*.py")):
        if py in ALLOWED:
            continue
        text = py.read_text(encoding="utf-8")
        if re.search(r"^\s*(import anthropic|from anthropic)", text, re.M) or "messages.create" in text:
            bad.append(str(py.relative_to(SRC)))
    assert bad == []
