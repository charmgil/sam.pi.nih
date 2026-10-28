#!/usr/bin/env bash
# Benchmark Ollama instance: same binary and default settings as the system service, but listening on
# 127.0.0.1:11435 with its model store inside the harness folder (.sam/ollama/models). The load timeout is raised from
# 5 to 30 minutes: on a hard disk a 60-80 GB model takes longer than 5 minutes to read (hart, 2026-10-28).
#   setsid nohup bench/ollama-serve.sh > .sam/ollama/serve.log 2>&1 &
HOME_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
mkdir -p "$HOME_DIR/.sam/ollama/models"
export OLLAMA_HOST=127.0.0.1:11435
export OLLAMA_MODELS="$HOME_DIR/.sam/ollama/models"
export OLLAMA_LOAD_TIMEOUT="${OLLAMA_LOAD_TIMEOUT:-30m}"
exec "$(command -v ollama)" serve
