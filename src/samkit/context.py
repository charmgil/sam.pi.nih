"""Run context: where data is read from and where results may be written.

Input and resource directories are read-only. Every path a step writes is
created through ``Context.out()``, which refuses anything outside the output
directory or inside a protected directory.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from samkit import __version__


class SamError(Exception):
    """An error the user or the agent can act on (bad parameter, missing input)."""

    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.hint = hint


def _resolve_dir(value: str | os.PathLike | None, what: str, must_exist: bool = True) -> Path | None:
    if value in (None, ""):
        return None
    p = Path(value).expanduser().resolve()
    if must_exist and not p.is_dir():
        raise SamError(f"{what} directory does not exist: {p}")
    return p


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def harness_home() -> Path:
    env = os.environ.get("SAM_HOME")
    if env:
        return Path(env).resolve()
    # src/samkit/context.py -> repository root
    return Path(__file__).resolve().parents[2]


@dataclass
class Context:
    home: Path
    input_dir: Path | None
    resource_dir: Path | None
    output_dir: Path
    build: str = "hg19"
    threads: int = 4
    rebind: bool = False
    _bound: bool = field(default=False, repr=False)

    # ── construction ────────────────────────────────────────────────────────
    @classmethod
    def from_values(cls, input_dir=None, resource_dir=None, output_dir=None,
                    build=None, threads=None, rebind=False, require_input: bool = True) -> "Context":
        input_dir = input_dir or os.environ.get("SAM_INPUT")
        resource_dir = resource_dir or os.environ.get("SAM_RESOURCE")
        output_dir = output_dir or os.environ.get("SAM_OUTPUT") or (Path.cwd() / "output")
        if not input_dir and require_input:
            raise SamError("input directory is not set",
                           hint="pass --input DIR (or set SAM_INPUT) when starting the harness")
        inp = _resolve_dir(input_dir, "input")
        res = _resolve_dir(resource_dir, "resource")
        out = Path(output_dir).expanduser().resolve()
        for name, prot in (("input", inp), ("resource", res)):
            if prot is None:
                continue
            if _is_within(out, prot):
                raise SamError(f"output directory {out} is inside the read-only {name} directory {prot}")
            if _is_within(prot, out):
                raise SamError(f"read-only {name} directory {prot} is inside the output directory {out}")
        nthreads = int(threads or os.environ.get("SAM_THREADS") or min(os.cpu_count() or 4, 16))
        return cls(home=harness_home(), input_dir=inp, resource_dir=res, output_dir=out,
                   build=(build or os.environ.get("SAM_BUILD") or "hg19"), threads=nthreads,
                   rebind=rebind)

    # ── protection ──────────────────────────────────────────────────────────
    def protected_dirs(self) -> list[Path]:
        return [p for p in (self.input_dir, self.resource_dir) if p is not None]

    def is_protected(self, path: os.PathLike | str) -> bool:
        p = Path(path).resolve()
        return any(_is_within(p, d) for d in self.protected_dirs())

    def check_writable(self, path: os.PathLike | str) -> Path:
        p = Path(path).resolve()
        if self.is_protected(p):
            raise SamError(f"refusing to write into a read-only data directory: {p}")
        if not _is_within(p, self.output_dir):
            raise SamError(f"refusing to write outside the output directory {self.output_dir}: {p}")
        return p

    def out(self, *parts: str, is_dir: bool = False) -> Path:
        """Path below the output directory; parent directories are created."""
        self.bind()
        p = self.check_writable(self.output_dir.joinpath(*parts))
        (p if is_dir else p.parent).mkdir(parents=True, exist_ok=True)
        return p

    def display(self, path: os.PathLike | str) -> str:
        """Path relative to the working directory when possible (what a user or agent can open)."""
        p = Path(path).resolve()
        try:
            return str(p.relative_to(Path.cwd().resolve()))
        except ValueError:
            return str(p)

    def input_path(self, name: str) -> Path:
        """Resolve a user-supplied input file name (relative to the input dir, or absolute)."""
        p = Path(name).expanduser()
        if not p.is_absolute():
            rel = Path(*p.parts[1:]) if p.parts and p.parts[0] == "output" else p
            for cand in (self.input_dir / p, self.output_dir / rel, Path.cwd() / p):
                if cand.exists():
                    p = cand
                    break
            else:
                p = self.input_dir / p
        p = p.resolve()
        if not p.exists():
            raise SamError(f"file not found: {name}", hint=f"files are looked up in {self.input_dir}")
        return p

    # ── binding: one output directory belongs to one input/resource pair ─────
    def bind(self) -> None:
        if self._bound:
            return
        self.output_dir.mkdir(parents=True, exist_ok=True)
        meta_path = self.output_dir / "sam.json"
        meta = {
            "input": str(self.input_dir),
            "resource": str(self.resource_dir) if self.resource_dir else None,
            "build": self.build,
        }
        if meta_path.exists():
            old = json.loads(meta_path.read_text())
            changed = {k: (old.get(k), v) for k, v in meta.items()
                       if old.get(k) != v and v is not None and old.get(k) is not None}
            for k, v in meta.items():
                if old.get(k) is None and v is not None:
                    old[k] = v
                    meta_path.write_text(json.dumps(old, indent=2))
            if changed and not self.rebind:
                detail = "; ".join(f"{k}: {a} -> {b}" for k, (a, b) in changed.items())
                raise SamError(
                    f"output directory {self.output_dir} was created for different data ({detail})",
                    hint="run from another working directory, or pass --rebind if this is intended")
            if changed:
                old.setdefault("rebinds", []).append({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **meta})
                old.update(meta)
                meta_path.write_text(json.dumps(old, indent=2))
        else:
            meta.update(created=time.strftime("%Y-%m-%dT%H:%M:%S"), samkit=__version__)
            meta_path.write_text(json.dumps(meta, indent=2))
        self._bound = True

    # ── subprocess environment ──────────────────────────────────────────────
    def tmp_dir(self) -> Path:
        return self.out("_tmp", is_dir=True)

    def subprocess_env(self, threads: int | None = None) -> dict[str, str]:
        env = dict(os.environ)
        t = str(threads or self.threads)
        env.update(TMPDIR=str(self.tmp_dir()), OMP_NUM_THREADS=t, MKL_NUM_THREADS=t,
                   OPENBLAS_NUM_THREADS=t, PYTHONIOENCODING="utf-8", MPLBACKEND="Agg",
                   MPLCONFIGDIR=str(self.out("_cache", "matplotlib", is_dir=True)), PYTHONDONTWRITEBYTECODE="1")
        return env
