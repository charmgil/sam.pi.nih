"""output/report.md: the latest result of every step, summary-level only."""

from __future__ import annotations

import json
import time

from samkit import manifest
from samkit.context import Context

ORDER = ["gwas-prepare", "gwas-step1", "gwas-step2", "plots", "peaks", "ldsc", "regional", "finemap",
         "pheweb-download", "prs-target", "prs-score", "prs-prscs"]


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.4g}"
    if isinstance(v, (list, dict)):
        s = json.dumps(v, ensure_ascii=False, default=str)
        return s if len(s) < 160 else s[:157] + "..."
    return str(v)


def build(ctx: Context) -> dict:
    latest = manifest.latest(ctx)
    meta = json.loads((ctx.output_dir / "sam.json").read_text()) if (ctx.output_dir / "sam.json").exists() else {}
    lines = ["# SAM analysis report", "",
             f"- generated: {time.strftime('%Y-%m-%d %H:%M')}",
             f"- input: `{meta.get('input')}`", f"- resource: `{meta.get('resource')}`",
             f"- build: {meta.get('build')}", ""]
    entries = sorted(latest.values(), key=lambda e: (ORDER.index(e["step"]) if e["step"] in ORDER else 99,
                                                      e["finished"]))
    for e in entries:
        lines += [f"## {e['step']} — {e['key']}", "", f"finished {e['finished']} ({e['seconds']} s)", ""]
        for k, v in e["summary"].items():
            if k in ("top_hits", "loci") and isinstance(v, list):
                lines.append(f"- **{k}** (top {min(len(v), 5)}):")
                for r in v[:5]:
                    lines.append(f"  - {_fmt(r)}")
            else:
                lines.append(f"- **{k}**: {_fmt(v)}")
        imgs = [p for p in e["outputs"].values() if str(p).endswith(".png")]
        for p in imgs:
            rel = str(p).replace(str(ctx.output_dir) + "/", "")
            lines.append(f"\n![{rel}]({rel})")
        tools = ", ".join(f"{k}: {v}" for k, v in e.get("tools", {}).items())
        lines += ["", f"<sub>tools: {tools}</sub>", ""]
    out = ctx.out("report.md")
    out.write_text("\n".join(lines), encoding="utf-8")
    return {"ok": True, "report": ctx.display(out), "n_steps": len(entries)}
