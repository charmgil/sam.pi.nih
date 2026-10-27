"""Local model management for the SAM harness (Ollama first, vLLM optional).

  python -m samkit.llm list                    catalog + what is installed
  python -m samkit.llm pull <id|ollama-tag>    ollama pull + a 'sam-<id>' variant with a larger context
  python -m samkit.llm models-json [--vllm ID] write pi's models.json (ollama + optional vllm provider)
  python -m samkit.llm vllm-command <id>       print the vllm serve command for a catalog model

Ollama's OpenAI-compatible API cannot set the context size per request, so
`pull` creates a variant with PARAMETER num_ctx (default 65536, the catalog's
context_length) and num_predict instead of changing the server configuration.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

from samkit.context import harness_home

CATALOG = harness_home() / "models" / "catalog.json"


def ollama_url() -> str:
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    return host if host.startswith("http") else f"http://{host}"


def load_catalog() -> dict:
    return json.loads(CATALOG.read_text())


def entries(cat: dict) -> list[dict]:
    return cat["local"] + cat["consultants"]


def installed() -> set[str] | None:
    """Model names known to Ollama, or None when Ollama cannot be reached."""
    try:
        r = requests.get(f"{ollama_url()}/api/tags", timeout=5)
        r.raise_for_status()
        return {m["name"] for m in r.json().get("models", [])}
    except requests.RequestException:
        return None


def num_ctx(name: str) -> int | None:
    """Context length the Ollama model actually runs with (its num_ctx parameter)."""
    try:
        r = requests.post(f"{ollama_url()}/api/show", json={"model": name}, timeout=10)
        r.raise_for_status()
        for line in (r.json().get("parameters") or "").splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] == "num_ctx":
                return int(parts[1])
    except (requests.RequestException, ValueError):
        pass
    return None


def find(cat: dict, key: str) -> dict | None:
    for e in entries(cat):
        if key in (e["id"], e.get("ollama")):
            return e
    return None


def max_tokens(ctx: int) -> int:
    return min(32768, ctx // 2)


def variant(e: dict) -> str:
    return f"sam-{e['id']}"


def agent_dir() -> Path:
    return Path(os.environ.get("PI_CODING_AGENT_DIR", harness_home() / ".pi-agent"))


# ── commands ────────────────────────────────────────────────────────────────
def cmd_list(_a) -> int:
    cat = load_catalog()
    found = installed()
    have = found or set()
    tags = {t.removesuffix(":latest") for t in have} | have
    print(f"ollama: {ollama_url()} ({'not reachable' if found is None else f'{len(have)} model(s)'})\n")
    print(f"{'id':24} {'role':17} {'tier':28} {'ollama tag':34} {'GB':>4}  status")
    for e in entries(cat):
        tag = e.get("ollama")
        status = []
        if tag and (tag in tags or tag.removesuffix(":latest") in tags):
            status.append("pulled")
        if f"{variant(e)}:latest" in have:
            status.append(f"ready as ollama/{variant(e)}")
        if not tag:
            status.append("vLLM only")
        print(f"{e['id']:24} {e['role']:17} {e['tier'][:28]:28} {(tag or '-'):34} {e.get('size_gb', '?'):>4}  "
              f"{', '.join(status) or '-'}")
    print("\ncloud (via /login in pi):")
    for c in cat["cloud"]:
        print(f"  {c['provider']:13} {', '.join(c['models'])}   [{c['login']}]")
    return 0


def cmd_pull(a) -> int:
    cat = load_catalog()
    e = find(cat, a.model)
    if e is None:
        print(f"unknown model {a.model}; see `./sam llm list`", file=sys.stderr)
        return 2
    if not e.get("ollama"):
        print(f"{e['id']} has no Ollama build; see `./sam llm vllm-command {e['id']}`", file=sys.stderr)
        return 2
    tag = e["ollama"]
    print(f"pulling {tag} (~{e.get('size_gb', '?')} GB) ...", file=sys.stderr)
    if subprocess.run(["ollama", "pull", tag]).returncode != 0:
        return 1
    ctx = min(a.context or e.get("num_ctx") or cat["context_length"], e.get("context", 10 ** 9))
    with tempfile.NamedTemporaryFile("w", suffix=".Modelfile", delete=False,
                                     dir=harness_home() / ".sam") as fh:
        # some library models ship small defaults (e.g. num_ctx 4096, num_predict 512)
        fh.write(f"FROM {tag}\nPARAMETER num_ctx {ctx}\nPARAMETER num_predict {max_tokens(ctx)}\n")
        modelfile = fh.name
    try:
        r = subprocess.run(["ollama", "create", variant(e), "-f", modelfile])
    finally:
        os.unlink(modelfile)
    if r.returncode != 0:
        return 1
    print(f"ready: ollama/{variant(e)} (num_ctx {ctx}). Run `./sam llm models-json` to register it with pi.")
    return 0


def cmd_models_json(a) -> int:
    cat = load_catalog()
    have = installed()
    if have is None:
        print(f"Ollama is not reachable at {ollama_url()}; models.json left unchanged", file=sys.stderr)
        return 1
    path = agent_dir() / "models.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    data.setdefault("$schema", "https://pi.dev/schemas/models.schema.json")
    providers = data.setdefault("providers", {})
    models = []
    for e in entries(cat):
        if f"{variant(e)}:latest" not in have:
            continue
        # the context the variant really runs with, so pi compacts in time
        ctx = num_ctx(variant(e)) or min(e.get("num_ctx") or cat["context_length"], e.get("context", 10 ** 9))
        models.append({"id": variant(e), "name": f"{e['id']} (Ollama, {e['role']})",
                       "reasoning": e.get("reasoning", False),
                       "input": ["text", "image"] if e.get("vision") else ["text"], "contextWindow": ctx,
                       "maxTokens": max_tokens(ctx),
                       # Ollama honours max_tokens but ignores max_completion_tokens
                       "compat": {"maxTokensField": "max_tokens"}})
    # merge: keep models the user added by hand; replace the sam-* entries with the current ones
    ollama = providers.setdefault("ollama", {})
    ollama.update(baseUrl=f"{ollama_url()}/v1", api="openai-completions", apiKey=ollama.get("apiKey", "ollama"))
    mine = {m["id"] for m in models}
    kept = [m for m in ollama.get("models", [])
            if not str(m.get("id", "")).startswith("sam-") and m.get("id") not in mine]
    ollama["models"] = kept + models
    if a.vllm:
        e = find(cat, a.vllm)
        if e is None or "vllm" not in e:
            print(f"no vLLM recipe for {a.vllm}", file=sys.stderr)
            return 2
        providers["vllm"] = {"baseUrl": a.vllm_url, "api": "openai-completions", "apiKey": "vllm",
                             "models": [{"id": e["vllm"]["model"], "name": f"{e['id']} (vLLM)",
                                         "reasoning": e.get("reasoning", False),
                                         "input": ["text", "image"] if e.get("vision") else ["text"],
                                         "contextWindow": min(cat["context_length"], e.get("context", 10 ** 9)),
                                         "maxTokens": 32768}]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    print(f"wrote {path}: ollama models {[m['id'] for m in models]}"
          + (f"; vllm {providers['vllm']['models'][0]['id']}" if a.vllm else ""))
    if not models:
        print("no sam-* Ollama variants found; run `./sam llm pull <id>` first", file=sys.stderr)
    return 0


def cmd_vllm_command(a) -> int:
    cat = load_catalog()
    e = find(cat, a.model)
    if e is None or "vllm" not in e:
        print(f"no vLLM recipe for {a.model}", file=sys.stderr)
        return 2
    ctx = min(cat["context_length"], e.get("context", 10 ** 9))
    cmd = ["vllm", "serve", e["vllm"]["model"], "--host", "127.0.0.1", "--port", "8000",
           "--max-model-len", str(ctx), "--gpu-memory-utilization", "0.90", *e["vllm"]["args"]]
    print(" ".join(shlex.quote(c) for c in cmd))
    if e["vllm"].get("note"):
        print(f"# note: {e['vllm']['note']}")
    return 0


def cmd_vllm_serve(a) -> int:
    cat = load_catalog()
    e = find(cat, a.model)
    if e is None or "vllm" not in e:
        print(f"no vLLM recipe for {a.model}", file=sys.stderr)
        return 2
    vbin = harness_home() / "models" / "vllm" / ".pixi" / "envs" / "default" / "bin"
    if not (vbin / "vllm").exists():
        print("vLLM is not installed; run ./sam llm vllm-install", file=sys.stderr)
        return 2
    ctx = min(cat["context_length"], e.get("context", 10 ** 9))
    argv = [str(vbin / "vllm"), "serve", e["vllm"]["model"], "--host", "127.0.0.1", "--port", str(a.port),
            "--max-model-len", str(ctx), "--gpu-memory-utilization", "0.90", *e["vllm"]["args"]]
    print("sam: " + " ".join(shlex.quote(x) for x in argv), file=sys.stderr)
    os.execve(argv[0], argv, {**os.environ, "PATH": f"{vbin}:{os.environ.get('PATH', '')}"})
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sam llm")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    s = sub.add_parser("pull")
    s.add_argument("model")
    s.add_argument("--context", type=int)
    s.set_defaults(fn=cmd_pull)
    s = sub.add_parser("models-json")
    s.add_argument("--vllm", help="catalog id served by vLLM")
    s.add_argument("--vllm-url", default="http://127.0.0.1:8000/v1")
    s.set_defaults(fn=cmd_models_json)
    s = sub.add_parser("vllm-command")
    s.add_argument("model")
    s.set_defaults(fn=cmd_vllm_command)
    s = sub.add_parser("vllm-serve")
    s.add_argument("model")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(fn=cmd_vllm_serve)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
