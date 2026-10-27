#!/usr/bin/env bash
# Benchmark Ollama instance: same binary and default settings as the system service, but listening on
# 127.0.0.1:11435 with its model store inside the harness folder (.sam/ollama/models).
#   setsid nohup bench/ollama-serve.sh > .sam/ollama/serve.log 2>&1 &
HOME_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
mkdir -p "$HOME_DIR/.sam/ollama/models"
export OLLAMA_HOST=127.0.0.1:11435
export OLLAMA_MODELS="$HOME_DIR/.sam/ollama/models"
exec "$(command -v ollama)" serve
