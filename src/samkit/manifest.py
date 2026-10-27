"""Provenance: one JSON line per step run in output/manifest.jsonl."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from samkit.context import Context


def fingerprint(path: Path) -> dict:
    """Cheap identity of an input file: size, mtime, and a hash of its first 1 MiB."""
    st = path.stat()
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        h.update(fh.read(1 << 20))
    return {"path": str(path), "size": st.st_size, "mtime": int(st.st_mtime), "head_sha256": h.hexdigest()[:16]}


def record(ctx: Context, step: str, key: str, params: dict, inputs: list[Path], outputs: dict,
           summary: dict, tool_versions: dict, started: float, log_path: Path) -> None:
    entry = {
        "step": step,
        "key": key,
        "finished": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "seconds": round(time.time() - started, 1),
        "params": params,
        "inputs": [fingerprint(p) for p in inputs if p.exists() and p.is_file()],
        "outputs": {k: str(v) for k, v in outputs.items()},
        "summary": summary,
        "tools": tool_versions,
        "log": str(log_path),
        "user": os.environ.get("USER"),
    }
    with open(ctx.out("manifest.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, default=str) + "\n")


def latest(ctx: Context) -> dict[tuple[str, str], dict]:
    """Most recent manifest entry per (step, key)."""
    path = ctx.output_dir / "manifest.jsonl"
    out: dict[tuple[str, str], dict] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        out[(e["step"], e["key"])] = e
    return out
