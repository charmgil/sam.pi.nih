#!/usr/bin/env bash
# Download queue for the local-LLM benchmark (models < 40B only), smallest first.
# Each finished pull writes .sam/bench/pulled/<tag> so the benchmark runner can start on it.
set -u
export OLLAMA_HOST=127.0.0.1:11435
cd "$(dirname "${BASH_SOURCE[0]}")/.."
mkdir -p .sam/bench/pulled
TAGS=(
  medgemma:4b
  mistral:7b
  hf.co/BioMistral/BioMistral-7B-GGUF:Q4_K_M
  llama3.1:8b
  hf.co/bartowski/google_txgemma-9b-chat-GGUF:Q4_K_M
  gemma4:12b
  mistral-small3.2:24b
  hf.co/bartowski/google_txgemma-27b-chat-GGUF:Q4_K_M
  qwen3.8:27b
  gemma4:31b
)
for t in "${TAGS[@]}"; do
  f=".sam/bench/pulled/$(echo "$t" | tr '/:' '__')"
  [ -f "$f" ] && continue
  for try in 1 2 3 4 5; do
    echo "[$(date +%T)] pull $t (try $try)"
    if /usr/local/bin/ollama pull "$t" 2>&1 | tr '\r' '\n' | grep -vE "pulling [0-9a-f]+: +[0-9]+%" | tail -3; then
      /usr/local/bin/ollama show "$t" >/dev/null 2>&1 && { date +%FT%T > "$f"; break; }
    fi
    sleep 30
  done
done
# BioGPT-Large is a transformers model (not GGUF): plain HTTP download with resume (-C -)
d=.sam/hf/BioGPT-Large; mkdir -p "$d"
for fn in config.json generation_config.json vocab.json merges.txt tokenizer_config.json special_tokens_map.json pytorch_model.bin; do
  for try in 1 2 3 4 5; do
    curl -sfL -C - -o "$d/$fn" "https://huggingface.co/microsoft/BioGPT-Large/resolve/main/$fn" && break
    sleep 30
  done
done
[ -s "$d/pytorch_model.bin" ] && date +%FT%T > .sam/bench/pulled/biogpt-large
echo "[$(date +%T)] all downloads finished"
