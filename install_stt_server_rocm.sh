#!/bin/bash
set -euo pipefail

VENV_DIR="${VENV_DIR:-$HOME/venvs/voice-input-rocm}"
PYTHON_BIN="${PYTHON_BIN:-python3.12}"
TORCH_INDEX_URL="${TORCH_INDEX_URL:-https://download.pytorch.org/whl/rocm7.0}"

echo "=== STT ROCm server installation ==="
echo "Using Python: $PYTHON_BIN"
echo "Virtualenv:    $VENV_DIR"
echo

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "Python interpreter not found: $PYTHON_BIN"
    echo "Install Python 3.12 first, then rerun this script."
    exit 1
fi

"$PYTHON_BIN" -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip setuptools wheel
python -m pip install --index-url "$TORCH_INDEX_URL" torch torchvision torchaudio
python -m pip install flask numpy transformers accelerate safetensors sentencepiece

echo
echo "Installation complete."
echo
echo "Start server with:"
echo "  source \"$VENV_DIR/bin/activate\""
echo "  cd \"$(cd "$(dirname "$0")" && pwd)\""
echo "  python stt_server_rocm.py"
echo
echo "Optional model override:"
echo "  STT_MODEL_ID=openai/whisper-large-v3 python stt_server_rocm.py"
