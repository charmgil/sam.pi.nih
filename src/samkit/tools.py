"""External tools: where they live, which step needs which, and how they run.

All tools come from the pixi environments declared in pixi.toml:
  default  Python 3.12, R 4.5 + susieR, plink2
  regenie  regenie (standalone binary)
  ldsc     Python 3.10 + ldsc 2.0.1 (Python 3 port), pinned numpy/pandas/scipy
  prscs    Python 3.10 + PRS-CS 1.1.0, pinned numpy/scipy
A tool can be overridden with SAM_TOOL_<NAME>=/path (e.g. SAM_TOOL_PLINK2).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

from samkit.context import Context, SamError

# name -> (pixi environment, path inside the environment)
TOOLS: dict[str, tuple[str, str]] = {
    "plink2": ("default", "bin/plink2"),
    "regenie": ("regenie", "bin/regenie"),
    "Rscript": ("default", "bin/Rscript"),
    "python": ("default", "bin/python"),
    "prscs-python": ("prscs", "bin/python"),
    "prscs": ("prscs", "bin/PRScs.py"),
    "ldsc-python": ("ldsc", "bin/python"),
    "ldsc": ("ldsc", "bin/ldsc.py"),
    "munge_sumstats": ("ldsc", "bin/munge_sumstats.py"),
}

# step -> tools it needs ("check only what the requested step needs")
STEP_TOOLS: dict[str, list[str]] = {
    "gwas": ["plink2", "regenie", "python"],
    "plots": ["python"],
    "ldsc": ["python", "ldsc-python", "ldsc", "munge_sumstats"],
    "peaks": ["python"],
    "regional": ["plink2", "python"],
    "finemap": ["plink2", "Rscript", "python"],
    "prs": ["plink2", "python", "prscs-python", "prscs"],
    "pheweb": ["python"],
}

ENV_OF_STEP: dict[str, list[str]] = {
    step: sorted({TOOLS[t][0] for t in tools}) for step, tools in STEP_TOOLS.items()
}


def env_prefix(home: Path, env: str) -> Path:
    return home / ".pixi" / "envs" / env


def tool_path(ctx: Context, name: str) -> Path:
    override = os.environ.get("SAM_TOOL_" + re.sub(r"\W", "_", name).upper())
    if override:
        return Path(override)
    env, rel = TOOLS[name]
    return env_prefix(ctx.home, env) / rel


def require(ctx: Context, names: list[str]) -> None:
    missing = [n for n in names if not tool_path(ctx, n).exists()]
    if missing:
        envs = sorted({TOOLS[n][0] for n in missing})
        raise SamError(f"required tools are not installed: {', '.join(missing)}",
                       hint=f"agent: call sam_setup (the user approves); shell: ./sam setup --env {','.join(envs)}")


def _first_line(cmd: list[str]) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        text = (r.stdout or r.stderr).strip().splitlines()
        return text[0] if text else ""
    except Exception as exc:  # noqa: BLE001 - version probing must never fail a step
        return f"unknown ({exc.__class__.__name__})"


def _conda_meta_version(prefix: Path, package: str) -> str | None:
    for f in (prefix / "conda-meta").glob(f"{package}-*.json"):
        try:
            meta = json.loads(f.read_text())
        except ValueError:
            continue
        if meta.get("name") == package:
            return meta.get("version")
    return None


def versions(ctx: Context, names: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for n in names:
        p = tool_path(ctx, n)
        if not p.exists():
            out[n] = "missing"
            continue
        env = env_prefix(ctx.home, TOOLS[n][0])
        if n == "plink2":
            out[n] = _first_line([str(p), "--version"])
        elif n == "regenie":
            out[n] = _first_line([str(p), "--version"])
        elif n == "Rscript":
            out[n] = f"R {_conda_meta_version(env, 'r-base')}, susieR {_conda_meta_version(env, 'r-susier')}"
        elif n == "prscs":
            out[n] = f"PRS-CS {_conda_meta_version(env, 'prscs')}"
        elif n in ("ldsc", "munge_sumstats"):
            dist = list((env / "lib").glob("python3*/site-packages/ldsc-*.dist-info"))
            out[n] = dist[0].name.replace(".dist-info", "") if dist else "ldsc (unknown version)"
        elif n in ("python", "ldsc-python", "prscs-python"):
            out[n] = f"Python {_conda_meta_version(env, 'python')}"
        else:
            out[n] = "present"
    return out


class StepLog:
    """Per-step log file under output/logs, mirrored to stderr for live progress."""

    def __init__(self, ctx: Context, step: str):
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.path = ctx.out("logs", f"{stamp}_{step}.log")
        self._fh = open(self.path, "a", encoding="utf-8")

    def info(self, msg: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        self._fh.write(line + "\n")
        self._fh.flush()
        print(line, file=sys.stderr, flush=True)

    def raw(self, line: str) -> None:
        self._fh.write(line)
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


# child process groups started by run(); terminated when samkit itself is stopped
ACTIVE: set[subprocess.Popen] = set()


def terminate_children(*_args) -> None:
    for proc in list(ACTIVE):
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    deadline = time.time() + 5
    for proc in list(ACTIVE):
        try:
            proc.wait(timeout=max(0.1, deadline - time.time()))
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass


def install_signal_handlers() -> None:
    def handler(signum, _frame):
        terminate_children()
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


_ID_HINT = re.compile(r"\b(sample|samples|individual|IID|FID|person)\b", re.I)


def _redact(line: str) -> str:
    """Error lines that talk about samples may quote sample IDs; mask quoted values there."""
    if _ID_HINT.search(line):
        return re.sub(r"(['\"]).*?\1", r"\1<redacted>\1", line)
    return line


def run(ctx: Context, log: StepLog, cmd: list[str | os.PathLike], *, cwd: Path | None = None,
        threads: int | None = None, echo_every: int = 1, quiet_patterns: tuple[str, ...] = ()) -> None:
    """Run an external command; stream its output to the step log.

    Lines are echoed to stderr (progress for the agent) except those matching
    ``quiet_patterns``. A non-zero exit raises SamError with the last lines.
    The child gets its own process group so cancelling samkit stops it too.
    """
    argv = [str(c) for c in cmd]
    log.info("$ " + " ".join(shlex.quote(a) for a in argv))
    tail: deque[str] = deque(maxlen=12)
    proc = subprocess.Popen(argv, cwd=str(cwd or ctx.tmp_dir()), env=ctx.subprocess_env(threads),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", start_new_session=True)
    ACTIVE.add(proc)
    try:
        assert proc.stdout is not None
        n = 0
        for line in proc.stdout:
            log.raw(line)
            tail.append(_redact(line.rstrip()))
            n += 1
            if line.strip() and not any(re.search(p, line) for p in quiet_patterns) and n % echo_every == 0:
                print("  " + _redact(line.rstrip())[:300], file=sys.stderr, flush=True)
        code = proc.wait()
    finally:
        ACTIVE.discard(proc)
    if code != 0:
        raise SamError(f"{Path(argv[0]).name} exited with code {code}",
                       hint="last output:\n" + "\n".join(tail) + f"\nfull log: {log.path}")
