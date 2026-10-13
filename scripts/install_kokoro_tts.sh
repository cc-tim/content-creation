#!/usr/bin/env bash
# Download the local Kokoro v1.1-zh TTS bundle (sherpa-onnx export, Apache-2.0) used by
# voice engine "kokoro". Run once per machine. ~350 MB download, ~400 MB on disk.
set -euo pipefail

NAME="kokoro-multi-lang-v1_1"
URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/$NAME.tar.bz2"
TARGET="${PIPELINE_TTS_KOKORO_MODEL_DIR:-$HOME/.cache/content-creation/tts/$NAME}"
TARGET="${TARGET/#\~/$HOME}"

if [ -f "$TARGET/model.onnx" ]; then
  echo "Kokoro already installed at $TARGET"
  exit 0
fi

PARENT="$(dirname "$TARGET")"
mkdir -p "$PARENT"
TMP="$(mktemp -d "$PARENT/.kokoro-download.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

echo "Downloading $NAME (~350 MB)"
curl -fL --progress-bar -o "$TMP/$NAME.tar.bz2" "$URL"
tar -xjf "$TMP/$NAME.tar.bz2" -C "$TMP"
mv "$TMP/$NAME" "$TARGET"

test -f "$TARGET/model.onnx"
echo "Kokoro installed at $TARGET"
