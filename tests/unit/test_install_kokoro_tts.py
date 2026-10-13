"""scripts/install_kokoro_tts.sh against a stubbed curl and a tiny fake bundle (no network)."""

from __future__ import annotations

import hashlib
import io
import os
import subprocess
import tarfile
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "install_kokoro_tts.sh"
_NAME = "kokoro-multi-lang-v1_1"
_FILES = [
    "model.onnx", "voices.bin", "tokens.txt", "lexicon-us-en.txt", "lexicon-zh.txt",
    "date-zh.fst", "phone-zh.fst", "number-zh.fst", "dict/jieba.dict.utf8",
    "espeak-ng-data/phontab",
]


def _fake_bundle(path: Path) -> str:
    with tarfile.open(path, "w:bz2") as tar:
        for rel in _FILES:
            data = rel.encode()
            info = tarfile.TarInfo(f"{_NAME}/{rel}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(tmp_path: Path, target: Path, sha: str) -> subprocess.CompletedProcess[str]:
    bundle = tmp_path / "bundle.tar.bz2"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    curl = bin_dir / "curl"
    # Stub curl: copy the fake bundle to the -o path.
    curl.write_text(
        "#!/usr/bin/env bash\n"
        'while [ $# -gt 0 ]; do if [ "$1" = "-o" ]; then out="$2"; shift; fi; shift; done\n'
        f'cp "{bundle}" "$out"\n'
    )
    curl.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "PIPELINE_TTS_KOKORO_MODEL_DIR": str(target),
        "KOKORO_TTS_SHA256": sha,
    }
    return subprocess.run(["bash", str(_SCRIPT)], env=env, capture_output=True, text=True)


@pytest.fixture
def bundle_sha(tmp_path: Path) -> str:
    return _fake_bundle(tmp_path / "bundle.tar.bz2")


def test_install_replaces_a_stale_partial_target_instead_of_nesting(tmp_path, bundle_sha):
    target = tmp_path / "cache" / _NAME
    target.mkdir(parents=True)
    (target / "model.onnx").write_bytes(b"half")  # interrupted earlier install

    result = _run(tmp_path, target, bundle_sha)

    assert result.returncode == 0, result.stderr
    for rel in _FILES:
        assert (target / rel).exists(), rel
    assert not (target / _NAME).exists()
    set_aside = [p for p in target.parent.iterdir() if p.name.startswith(f"{_NAME}.incomplete")]
    assert len(set_aside) == 1
    assert (set_aside[0] / "model.onnx").read_bytes() == b"half"


def test_install_refuses_a_download_with_the_wrong_sha256(tmp_path, bundle_sha):
    target = tmp_path / "cache" / _NAME

    result = _run(tmp_path, target, "0" * 64)

    assert result.returncode != 0
    assert "sha256" in result.stderr
    assert not target.exists()


def test_install_is_a_no_op_on_a_complete_target(tmp_path, bundle_sha):
    target = tmp_path / "cache" / _NAME
    assert _run(tmp_path, target, bundle_sha).returncode == 0

    again = _run(tmp_path, target, "0" * 64)  # no download, so no sha check either

    assert again.returncode == 0
    assert "already installed" in again.stdout
