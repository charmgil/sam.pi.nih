"""Command line: `python -m samkit [global options] <command> ...`

stdout carries exactly one JSON document (the result or {"ok": false, ...});
progress and tool output go to stderr and to output/logs/.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import traceback
from pathlib import Path

from samkit import __version__, inventory, manifest, resources, tools
from samkit.context import Context, SamError, harness_home

STEP_RESOURCES = {
    "ldsc": [("ldsc_ref", True), ("ldsc_weights", True), ("dbsnp_map|pos2rsid", True)],
    "regional": [("genetic_map", False)],
    "prs": [("dbsnp_map", False), ("prscs_ld", False)],
}


def _ctx(a) -> Context:
    return Context.from_values(a.input, a.resource, a.output, a.build, a.threads, a.rebind)


# ── status / doctor / setup / resources ─────────────────────────────────────
def cmd_status(a) -> dict:
    ctx = _ctx(a)
    ctx.bind()
    done = []
    for (step, key), e in sorted(manifest.latest(ctx).items(), key=lambda kv: kv[1]["finished"]):
        done.append({"step": step, "key": key, "finished": e["finished"], "seconds": e["seconds"]})
    return {
        "ok": True,
        "samkit": __version__,
        "harness_home": str(ctx.home),
        "input_dir": str(ctx.input_dir),
        "resource_dir": str(ctx.resource_dir) if ctx.resource_dir else None,
        "output_dir": str(ctx.output_dir),
        "build": ctx.build,
        "threads": ctx.threads,
        "input": inventory.scan_input(ctx),
        "resources": resources.summary(ctx),
        "completed_steps": done,
        "tools_installed": {n: tools.tool_path(ctx, n).exists() for n in tools.TOOLS},
    }


def cmd_doctor(a) -> dict:
    # works without an input directory: only tools and resources are checked
    ctx = Context.from_values(a.input, a.resource, a.output, a.build, a.threads, a.rebind, require_input=False)
    steps = a.step or list(tools.STEP_TOOLS)
    comps = resources.components(ctx) if ctx.resource_dir else []
    report = {}
    for s in steps:
        if s not in tools.STEP_TOOLS:
            raise SamError(f"unknown step {s}", hint="steps: " + ", ".join(tools.STEP_TOOLS))
        names = tools.STEP_TOOLS[s]
        vers = tools.versions(ctx, names)
        res = []
        for kinds, required in STEP_RESOURCES.get(s, []):
            found = [c.describe() for c in comps if c.kind in kinds.split("|")]
            res.append({"kind": kinds, "required": required, "found": found[:3]})
        ready = all(v != "missing" for v in vers.values()) and all(r["found"] for r in res if r["required"])
        report[s] = {"ready": ready, "tools": vers, "resources": res,
                     "install_env": tools.ENV_OF_STEP[s]}
    return {"ok": True, "steps": report}


def cmd_setup(a) -> dict:
    home = harness_home()
    envs = set()
    for s in a.step or []:
        envs.update(tools.ENV_OF_STEP[s])
    for e in (a.env or "").split(","):
        if e:
            envs.add(e)
    if not envs:
        envs = {"default", "regenie", "ldsc"}
    pixi = home / ".sam" / "bin" / "pixi"
    if not pixi.exists():
        raise SamError("pixi is not installed in this harness", hint="run ./sam bootstrap first")
    env = dict(os.environ, PIXI_CACHE_DIR=str(home / ".sam" / "cache" / "pixi"))
    done = []
    for e in sorted(envs):
        print(f"installing pixi environment '{e}' ...", file=sys.stderr, flush=True)
        r = subprocess.run([str(pixi), "install", "--manifest-path", str(home / "pixi.toml"), "-e", e],
                           env=env, stdout=sys.stderr, stderr=sys.stderr)
        if r.returncode != 0:
            raise SamError(f"pixi install -e {e} failed (exit {r.returncode})")
        done.append(e)
    return {"ok": True, "installed_envs": done}


def cmd_resources(a) -> dict:
    ctx = _ctx(a)
    if a.prepare:
        comp = resources.require(ctx, a.prepare)
        root = resources.materialize(ctx, comp)
        return {"ok": True, "prepared": comp.describe(), "path": str(root / comp.prefix)}
    return {"ok": True, **resources.summary(ctx)}


# ── analysis commands ───────────────────────────────────────────────────────
def cmd_gwas(a) -> dict:
    from samkit.steps import gwas
    ctx = _ctx(a)
    covars = [c for c in a.covars.split(",") if c] if a.covars is not None else None
    if a.stage == "prepare":
        return gwas.prepare(ctx, a.geno, a.pheno_file, a.pheno, a.trait, covars, a.n_pc, a.vcf, a.min_r2)
    if a.stage == "step1":
        return gwas.step1(ctx, a.pheno)
    if a.stage == "step2":
        return gwas.step2(ctx, a.pheno, a.chroms)
    # all
    results = {"prepare": gwas.prepare(ctx, a.geno, a.pheno_file, a.pheno, a.trait, covars, a.n_pc, a.vcf,
                                       a.min_r2)}
    results["step1"] = gwas.step1(ctx, a.pheno)
    results["step2"] = gwas.step2(ctx, a.pheno, a.chroms)
    final = dict(results["step2"])
    final["stages"] = {k: {"summary": v["summary"], "warnings": v["warnings"]} for k, v in results.items()}
    final["warnings"] = [w for v in results.values() for w in v["warnings"]]
    return final


def cmd_plots(a) -> dict:
    from samkit.steps import plots
    return plots.manhattan_qq(_ctx(a), a.pheno)


def cmd_peaks(a) -> dict:
    from samkit.steps import plots
    return plots.peaks(_ctx(a), a.pheno, a.p, a.window_kb)


def cmd_ldsc(a) -> dict:
    from samkit.steps import ldsc
    return ldsc.run_ldsc(_ctx(a), a.pheno, a.pop_prev, a.allow_partial, a.model)


def cmd_regional(a) -> dict:
    from samkit.steps import regional
    return regional.regional(_ctx(a), a.pheno, a.locus, a.window_kb)


def cmd_finemap(a) -> dict:
    from samkit.steps import finemap
    return finemap.finemap(_ctx(a), a.pheno, a.locus, a.window_kb, a.L, a.coverage, a.min_abs_corr,
                           not a.fixed_residual_variance)


def cmd_prs(a) -> dict:
    from samkit.steps import prs
    ctx = _ctx(a)
    if a.action == "target":
        return prs.prs_target(ctx, a.geno)
    if a.action == "score":
        return prs.prs_score(ctx, a.weights, a.name, a.geno)
    return prs.prs_prscs(ctx, a.sumstats, a.n_gwas, a.name, a.chroms, a.ancestry, a.allow_partial, a.geno,
                         a.phi, a.seed, a.parallel)


def cmd_pheweb(a) -> dict:
    from samkit.steps import pheweb
    ctx = _ctx(a)
    if a.action == "search":
        return pheweb.search(ctx, " ".join(a.query), a.kind, a.refresh)
    if a.action == "head":
        return pheweb.head(ctx, a.code)
    return pheweb.download(ctx, a.code)


def cmd_genes(a) -> dict:
    from samkit import genes
    ctx = _ctx(a)
    m = re.fullmatch(r"(?:chr)?(\d{1,2}):(\d+)-(\d+)", a.region.replace(",", ""))
    if not m:
        raise SamError("region must look like CHR:START-END, e.g. 11:116162579-117162579")
    chrom, start, end = int(m[1]), int(m[2]), int(m[3])
    found, note = genes.fetch_genes(ctx, chrom, start, end)
    if note:
        raise SamError(note)
    return {"ok": True, "build": ctx.build, "source": f"Ensembl REST ({genes.ENSEMBL[ctx.build]})",
            "region": f"{chrom}:{start}-{end}", "protein_coding_genes": [g["name"] for g in found]}


def cmd_report(a) -> dict:
    from samkit import report
    return report.build(_ctx(a))


# ── parser ──────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="samkit", description="SAM GWAS + PRS core")
    p.add_argument("--input", help="input data directory (read-only); env SAM_INPUT")
    p.add_argument("--resource", help="reference resource directory (read-only); env SAM_RESOURCE")
    p.add_argument("--output", help="output directory (default ./output); env SAM_OUTPUT")
    p.add_argument("--build", choices=["hg19", "hg38"], help="genome build of the data (default hg19)")
    p.add_argument("--threads", type=int)
    p.add_argument("--rebind", action="store_true", help="allow an output dir created for other data")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="inputs, resources, completed steps").set_defaults(fn=cmd_status)
    s = sub.add_parser("doctor", help="tools/resources needed by steps")
    s.add_argument("--step", action="append", choices=list(tools.STEP_TOOLS))
    s.set_defaults(fn=cmd_doctor)
    s = sub.add_parser("setup", help="install pixi environments")
    s.add_argument("--env", help="comma-separated: default,regenie,ldsc")
    s.add_argument("--step", action="append", choices=list(tools.STEP_TOOLS))
    s.set_defaults(fn=cmd_setup)
    s = sub.add_parser("resources", help="list or prepare reference resources")
    s.add_argument("--prepare", help="component kind to extract into the cache")
    s.set_defaults(fn=cmd_resources)

    s = sub.add_parser("gwas", help="regenie GWAS")
    s.add_argument("stage", choices=["prepare", "step1", "step2", "all"])
    s.add_argument("--pheno", required=True, help="phenotype column name")
    s.add_argument("--pheno-file", help="phenotype table in the input dir (prepare/all)")
    s.add_argument("--geno", help="genotype fileset name (if several)")
    s.add_argument("--vcf", help="VCF to convert when no PLINK fileset exists")
    s.add_argument("--min-r2", type=float, default=0.8, help="imputation R2 filter for VCF input")
    s.add_argument("--trait", choices=["qt", "bt"])
    s.add_argument("--covars", help="comma-separated covariate columns (default: AGE,SEX if present)")
    s.add_argument("--n-pc", type=int, default=4, help="PCs used as covariates")
    s.add_argument("--chroms", help="restrict step 2, e.g. 11 or 1-3,11")
    s.set_defaults(fn=cmd_gwas)

    for name, fn, helptext in (("plots", cmd_plots, "Manhattan + QQ"),):
        s = sub.add_parser(name, help=helptext)
        s.add_argument("--pheno", required=True)
        s.set_defaults(fn=fn)
    s = sub.add_parser("peaks", help="independent genome-wide significant loci")
    s.add_argument("--pheno", required=True)
    s.add_argument("--p", type=float, default=5e-8)
    s.add_argument("--window-kb", type=int, default=500)
    s.set_defaults(fn=cmd_peaks)
    s = sub.add_parser("ldsc", help="LDSC SNP heritability")
    s.add_argument("--pheno", required=True)
    s.add_argument("--pop-prev", type=float, help="population prevalence (binary traits, liability scale)")
    s.add_argument("--allow-partial", action="store_true")
    s.add_argument("--model", choices=["base", "baseline"], default="base",
                   help="base: univariate h2 (default); baseline: stratified LDSC with all panel annotations")
    s.set_defaults(fn=cmd_ldsc)
    for name, fn in (("regional", cmd_regional), ("finemap", cmd_finemap)):
        s = sub.add_parser(name)
        s.add_argument("--pheno", required=True)
        s.add_argument("--locus", required=True, help="CHR:POS, variant ID, or peak rank")
        s.add_argument("--window-kb", type=int, default=500)
        if name == "finemap":
            s.add_argument("--L", type=int, default=10)
            s.add_argument("--coverage", type=float, default=0.95)
            s.add_argument("--min-abs-corr", type=float, default=0.5)
            s.add_argument("--fixed-residual-variance", action="store_true",
                           help="do not estimate the residual variance (use with out-of-sample LD)")
        s.set_defaults(fn=fn)

    s = sub.add_parser("prs", help="polygenic risk scores")
    s.add_argument("action", choices=["target", "score", "prscs"])
    s.add_argument("--geno")
    s.add_argument("--weights", help="PRS weight file (score)")
    s.add_argument("--sumstats", help="external GWAS summary statistics (prscs)")
    s.add_argument("--n-gwas", type=int)
    s.add_argument("--name")
    s.add_argument("--chroms")
    s.add_argument("--ancestry", default="EAS")
    s.add_argument("--allow-partial", action="store_true")
    s.add_argument("--phi", type=float)
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--parallel", type=int)
    s.set_defaults(fn=cmd_prs)

    s = sub.add_parser("pheweb", help="KNIH PheWeb catalog and downloads")
    s.add_argument("action", choices=["search", "head", "download"])
    s.add_argument("query", nargs="*")
    s.add_argument("--code")
    s.add_argument("--kind", choices=["sumstats", "prs_weight"])
    s.add_argument("--refresh", action="store_true")
    s.set_defaults(fn=cmd_pheweb)

    sub.add_parser("report", help="collect step summaries into output/report.md").set_defaults(fn=cmd_report)
    s = sub.add_parser("genes", help="protein-coding genes in a region (Ensembl, build-matched)")
    s.add_argument("--region", required=True, help="CHR:START-END in the analysis build")
    s.set_defaults(fn=cmd_genes)
    return p


def _clean(obj):
    """NaN/inf -> null so the output is strict JSON (JavaScript's JSON.parse rejects NaN)."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    return obj


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "action", None) in ("head", "download") and not args.code and args.query:
        args.code = args.query[0]
    tools.install_signal_handlers()
    out_dir = Path(args.output or os.environ.get("SAM_OUTPUT") or Path.cwd() / "output")
    os.environ.setdefault("MPLCONFIGDIR", str(out_dir / "_cache" / "matplotlib"))
    try:
        result = args.fn(args)
        print(json.dumps(_clean(json.loads(json.dumps(result, default=str))), indent=1, allow_nan=False))
        return 0
    except SamError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "hint": exc.hint}, indent=1))
        return 2
    except SystemExit as exc:
        if isinstance(exc.code, int) and exc.code >= 128:  # stopped by a signal (tool cancelled)
            print(json.dumps({"ok": False, "error": "cancelled", "hint": f"signal {exc.code - 128}"}))
        raise
    except Exception as exc:  # noqa: BLE001 - report unexpected failures as JSON too
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"ok": False, "error": f"{exc.__class__.__name__}: {exc}",
                          "hint": "unexpected failure; see stderr / output/logs"}, indent=1))
        return 1
