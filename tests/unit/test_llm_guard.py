import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "pipeline"
ALLOWED = {SRC / "llm.py", SRC / "utils" / "anthropic_key.py"}

# Anything outside ALLOWED that imports the anthropic SDK directly, calls messages.create /
# messages.stream, or reaches into get_anthropic_api_key is bypassing the pipeline.llm facade.
_VIOLATION_RE = re.compile(
    r"^\s*(import anthropic|from anthropic)|messages\.(create|stream)|get_anthropic_api_key",
    re.M,
)


def _find_violations(src_dir: Path, allowed: set[Path]) -> list[str]:
    bad = []
    for py in sorted(src_dir.rglob("*.py")):
        if py in allowed:
            continue
        text = py.read_text(encoding="utf-8")
        if _VIOLATION_RE.search(text):
            bad.append(str(py.relative_to(src_dir)))
    return bad


def test_only_the_llm_module_talks_to_anthropic():
    assert _find_violations(SRC, ALLOWED) == []


def test_guard_flags_messages_stream_outside_llm(tmp_path):
    bad_file = tmp_path / "somewhere.py"
    bad_file.write_text("resp = client.messages.stream(**kwargs)\n")
    assert _find_violations(tmp_path, set()) == ["somewhere.py"]


def test_guard_flags_get_anthropic_api_key_outside_allowed_files(tmp_path):
    bad_file = tmp_path / "somewhere.py"
    bad_file.write_text("from pipeline.utils.anthropic_key import get_anthropic_api_key\n")
    assert _find_violations(tmp_path, set()) == ["somewhere.py"]


def test_guard_allows_anthropic_key_module_to_define_the_helper(tmp_path):
    allowed_file = tmp_path / "anthropic_key.py"
    allowed_file.write_text("def get_anthropic_api_key():\n    return 'x'\n")
    assert _find_violations(tmp_path, {allowed_file}) == []
