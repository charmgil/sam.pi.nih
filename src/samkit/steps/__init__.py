"""Step framework: logging, provenance and a uniform JSON result.

A step result always has: ok, step, key, summary, outputs (paths relative to
the output dir), warnings, next (follow-up steps the user may ask for), log.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from samkit import manifest, tools
from samkit.context import Context


class StepRun:
    def __init__(self, ctx: Context, step: str, key: str, params: dict, tool_names: list[str]):
        self.ctx, self.step, self.key, self.params = ctx, step, key, params
        self.tool_names = tool_names
        tools.require(ctx, tool_names)
        self.started = time.time()
        self.log = tools.StepLog(ctx, f"{step}_{key}" if key else step)
        self.warnings: list[str] = []
        self.log.info(f"step {step} [{key}] params={json.dumps(params, default=str)}")

    def run(self, cmd, **kw) -> None:
        tools.run(self.ctx, self.log, cmd, **kw)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)
        self.log.info("WARNING: " + msg)

    def rel(self, p: Path) -> str:
        """Path as the user/agent can open it: relative to the working directory, else absolute."""
        p = Path(p).resolve()
        try:
            return str(p.relative_to(Path.cwd().resolve()))
        except ValueError:
            return str(p)

    def finish(self, summary: dict, outputs: dict[str, Path], inputs: list[Path] | None = None,
               next_steps: list[str] | None = None, summary_path: Path | None = None) -> dict:
        versions = tools.versions(self.ctx, self.tool_names)
        result = {
            "ok": True,
            "step": self.step,
            "key": self.key,
            "summary": summary,
            "outputs": {k: self.rel(v) for k, v in outputs.items()},
            "warnings": self.warnings,
            "next": next_steps or [],
            "log": self.rel(self.log.path),
            "seconds": round(time.time() - self.started, 1),
            "tools": versions,
        }
        if summary_path is not None:
            summary_path.write_text(json.dumps({**result, "params": self.params}, indent=2, default=str))
        manifest.record(self.ctx, self.step, self.key, self.params, inputs or [], outputs, summary,
                        versions, self.started, self.log.path)
        self.log.info(f"done in {result['seconds']} s")
        self.log.close()
        return result
