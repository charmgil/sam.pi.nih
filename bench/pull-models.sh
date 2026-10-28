#!/usr/bin/env bash
# Download queue for the local-LLM benchmark, in bench/models.json order (= run order).
# Pulls the models of the "bench" server into the benchmark Ollama instance (bench/ollama-serve.sh) and, if the list
# has BioGPT, its transformers weights. Each finished pull writes .sam/bench/pulled/<tag> so the runner can start
# on it; a pull that fails 5 times writes <tag>.failed so the runner skips the model instead of waiting.
#   bench/pull-models.sh > .sam/bench/pull.log 2>&1 &
# OLLAMA_HOST defaults to the bench server URL in models.json (set it to use another instance).
set -u
cd "$(dirname "${BASH_SOURCE[0]}")/.."
OLLAMA="$(command -v ollama)" || { echo "ollama not found" >&2; exit 1; }
CFG=bench/models.json
URL=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["servers"]["bench"]["url"])' "$CFG")
export OLLAMA_HOST="${OLLAMA_HOST:-${URL#http://}}"
mapfile -t TAGS < <(python3 -c '
import json, sys
for m in json.load(open(sys.argv[1]))["models"]:
    if m.get("server") == "bench":
        print(m["tag"])
' "$CFG")
HF=$(python3 -c 'import json,sys; print(any(m.get("runner") == "hf" for m in json.load(open(sys.argv[1]))["models"]))' "$CFG")
mkdir -p .sam/bench/pulled
for t in "${TAGS[@]}"; do
  f=".sam/bench/pulled/$(echo "$t" | tr '/:' '__')"
  [ -f "$f" ] && continue
  rm -f "$f.failed"
  for try in 1 2 3 4 5; do
    echo "[$(date +%T)] pull $t (try $try)"
    if "$OLLAMA" pull "$t" 2>&1 | tr '\r' '\n' | grep -vE "pulling [0-9a-f]+: +[0-9]+%" | tail -3; then
      "$OLLAMA" show "$t" >/dev/null 2>&1 && { date +%FT%T > "$f"; echo "[$(date +%T)] done $t"; break; }
    fi
    sleep 30
  done
  [ -f "$f" ] || { date +%FT%T > "$f.failed"; echo "[$(date +%T)] FAILED $t"; }
done
if [ "$HF" = True ]; then
  # BioGPT-Large is a transformers model (not GGUF): plain HTTP download with resume (-C -)
  d=.sam/hf/BioGPT-Large; mkdir -p "$d"
  for fn in config.json generation_config.json vocab.json merges.txt tokenizer_config.json special_tokens_map.json pytorch_model.bin; do
    for try in 1 2 3 4 5; do
      curl -sfL -C - -o "$d/$fn" "https://huggingface.co/microsoft/BioGPT-Large/resolve/main/$fn" && break
      sleep 30
    done
  done
  if [ -s "$d/pytorch_model.bin" ]; then date +%FT%T > .sam/bench/pulled/biogpt-large
  else date +%FT%T > .sam/bench/pulled/biogpt-large.failed; fi
fi
echo "[$(date +%T)] all downloads finished"
