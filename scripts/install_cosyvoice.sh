#!/usr/bin/env bash
# Install CosyVoice2 into a local directory for voice cloning.
# Run once per workstation. Requires ~5 GB disk + a working CUDA or CPU torch.
set -euo pipefail

TARGET="${COSYVOICE_DIR:-$HOME/.local/share/CosyVoice}"
MODEL_DIR="$TARGET/pretrained_models/CosyVoice2-0.5B"

echo "Installing CosyVoice2 to $TARGET"
mkdir -p "$TARGET"

if [ ! -d "$TARGET/.git" ]; then
  git clone --depth 1 https://github.com/FunAudioLLM/CosyVoice.git "$TARGET"
else
  echo "Repo already present; pulling latest"
  (cd "$TARGET" && git pull --ff-only)
fi

cd "$TARGET"

# Install the Python deps that CosyVoice bundles.
uv pip install --python "$(command -v python3)" -r requirements.txt

# Download the 0.5B model weights (Hugging Face mirror).
if [ ! -d "$MODEL_DIR" ]; then
  echo "Downloading CosyVoice2-0.5B weights"
  uv run python3 -c "
from modelscope import snapshot_download
snapshot_download('iic/CosyVoice2-0.5B', local_dir='$MODEL_DIR')
"
fi

echo ""
echo "Done. Add this to your shell rc:"
echo "  export PYTHONPATH=\"$TARGET:$TARGET/third_party/Matcha-TTS:\$PYTHONPATH\""
