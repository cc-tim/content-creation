#!/usr/bin/env bash
# Download the local Kokoro v1.1-zh TTS bundle (sherpa-onnx export, Apache-2.0) used by
# voice engine "kokoro". Run once per machine. ~350 MB download, ~400 MB on disk.
set -euo pipefail

NAME="kokoro-multi-lang-v1_1"
URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/$NAME.tar.bz2"
# sha256 of that release asset as GitHub lists it (asset digest, uploaded 2025-06-18).
SHA256="${KOKORO_TTS_SHA256:-a3f4c73d043860e3fd2e5b06f36795eb81de0fc8e8de6df703245edddd87dbad}"
TARGET="${PIPELINE_TTS_KOKORO_MODEL_DIR:-$HOME/.cache/content-creation/tts/$NAME}"
TARGET="${TARGET/#\~/$HOME}"
# Keep in sync with _BUNDLE_FILES / _BUNDLE_DIRS in src/pipeline/voices/kokoro_engine.py.
REQUIRED=(model.onnx voices.bin tokens.txt lexicon-us-en.txt lexicon-zh.txt
          date-zh.fst phone-zh.fst number-zh.fst dict espeak-ng-data)

is_complete() {
  local f
  for f in "${REQUIRED[@]}"; do
    [ -e "$1/$f" ] || return 1
  done
}

if is_complete "$TARGET"; then
  echo "Kokoro already installed at $TARGET"
  exit 0
fi

PARENT="$(dirname "$TARGET")"
mkdir -p "$PARENT"
TMP="$(mktemp -d "$PARENT/.kokoro-download.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

echo "Downloading $NAME (~350 MB)"
curl -fL --progress-bar -o "$TMP/$NAME.tar.bz2" "$URL"

if command -v sha256sum >/dev/null 2>&1; then
  GOT="$(sha256sum "$TMP/$NAME.tar.bz2" | cut -d' ' -f1)"
else
  GOT="$(shasum -a 256 "$TMP/$NAME.tar.bz2" | cut -d' ' -f1)"
fi
if [ "$GOT" != "$SHA256" ]; then
  echo "sha256 mismatch for $NAME.tar.bz2: got $GOT, expected $SHA256" >&2
  exit 1
fi

tar -xjf "$TMP/$NAME.tar.bz2" -C "$TMP"
if ! is_complete "$TMP/$NAME"; then
  echo "Downloaded $NAME is missing files; nothing installed" >&2
  exit 1
fi

# An interrupted earlier install leaves a partial target; mv would nest into it.
if [ -e "$TARGET" ]; then
  STALE="$TARGET.incomplete.$(date +%Y%m%d%H%M%S)"
  mv "$TARGET" "$STALE"
  echo "Moved the incomplete $TARGET aside to $STALE; delete it when convenient."
fi
mv "$TMP/$NAME" "$TARGET"
echo "Kokoro installed at $TARGET"
