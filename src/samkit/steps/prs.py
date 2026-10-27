"""Polygenic risk scores on the target genotypes.

Two routes, both scored with plink2 --score on the original target fileset:
  A. external PRS weights (e.g. KNIH PheWeb *_PRS_weight)           -> prs-score
  B. external GWAS summary statistics -> PRS-CS posterior effects   -> prs-prscs (then scored)

Target variants are linked to rsIDs through a variant-ID map (prs-target),
and every weight is checked against the target's alleles before scoring; the
3 GB genotype file is never rewritten. Summary statistics produced by this
harness's own GWAS are refused as PRS-CS input (the discovery and target
samples would overlap).
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import re
from pathlib import Path, PurePosixPath

import numpy as np
import pandas as pd

from samkit import inventory, resources
from samkit.context import Context, SamError
from samkit.io import open_text, parse_chroms, safe_name, sniff_sep, with_ext, write_tsv
from samkit.steps import StepRun
from samkit.steps.ldsc import read_id_map
from samkit.tools import StepLog, tool_path
from samkit.tools import run as run_tool

COMPLEMENT = str.maketrans("ACGT", "TGCA")


# ── target: variant ID <-> rsID ─────────────────────────────────────────────
def target_dir(ctx: Context, geno: dict) -> Path:
    return ctx.out("prs", "_target", safe_name(geno["name"]), is_dir=True)


def _read_bim(geno: dict) -> pd.DataFrame:
    prefix = Path(geno["prefix"])
    if geno["format"] == "bfile":
        return pd.read_csv(with_ext(prefix, ".bim"), sep=r"\s+", header=None,
                           dtype={0: str, 1: str, 4: str, 5: str}, names=["CHR", "ID", "CM", "BP", "ALT", "REF"])
    pvar_path = with_ext(prefix, ".pvar")
    with open(pvar_path) as fh:
        n_meta = sum(1 for line in fh if line.startswith("##"))
    pvar = pd.read_csv(pvar_path, sep="\t", skiprows=n_meta, dtype=str)
    pvar.columns = [c.lstrip("#") for c in pvar.columns]
    return pd.DataFrame({"CHR": pvar["CHROM"], "ID": pvar["ID"], "CM": 0, "BP": pvar["POS"].astype(int),
                         "ALT": pvar["ALT"], "REF": pvar["REF"]})


def prs_target(ctx: Context, geno_name: str | None = None, run: StepRun | None = None) -> dict:
    geno = inventory.resolve_genotype(ctx, geno_name)
    d = target_dir(ctx, geno)
    own = run is None
    if own:
        run = StepRun(ctx, "prs-target", geno["name"], {}, ["python"])
    bim = _read_bim(geno)
    idmap = resources.find(ctx, "dbsnp_map")
    if bim["ID"].str.startswith("rs").mean() > 0.5:
        bim["SNP"] = bim["ID"]
        method = "target IDs are already rsIDs"
    elif idmap is not None:
        root = resources.materialize(ctx, idmap, log=run.log)
        m = read_id_map(root / idmap.prefix)
        bim = bim.merge(m, on="ID", how="left")
        method = f"variant-ID map {idmap.source.label}:{idmap.prefix}"
        if idmap.meta.get("build") and idmap.meta["build"] != ctx.build:
            run.warn(f"ID map is labelled {idmap.meta['build']} but the analysis build is {ctx.build}")
    else:
        raise SamError("target variant IDs are not rsIDs and no dbSNP ID map was found",
                       hint="add a VariantID->rsID map (e.g. *dbSNP*rsID*.txt) to the resource directory")
    mapped = bim.dropna(subset=["SNP"])
    mapped = mapped[mapped["SNP"].str.startswith("rs")]
    # PRS-CS parses CHR as an integer and the LD references cover autosomes only
    chrom = mapped["CHR"].astype(str).str.removeprefix("chr")
    mapped = mapped[chrom.isin([str(c) for c in range(1, 23)])].assign(CHR=chrom)
    dup = mapped["SNP"].duplicated(keep=False)
    uniq = mapped[~dup]
    table = d / "rsid_map.tsv.gz"
    write_tsv(uniq[["ID", "SNP", "CHR", "BP", "ALT", "REF"]], table, compression="gzip")
    rsid_bim = d / f"{safe_name(geno['name'])}_rsid.bim"
    uniq[["CHR", "SNP", "CM", "BP", "ALT", "REF"]].to_csv(rsid_bim, sep="\t", header=False, index=False)
    summary = {"genotype": geno["name"], "method": method, "n_variants": int(len(bim)),
               "n_with_rsid": int(len(mapped)), "n_unique_rsid": int(len(uniq)),
               "n_dropped_duplicate_rsid": int(dup.sum()), "source_key": _target_key(ctx, geno)}
    (d / "summary.json").write_text(json.dumps(summary, indent=2))
    if own:
        return run.finish(summary, {"rsid_map": table, "rsid_bim": rsid_bim}, [], ["prs-score", "prs-prscs"])
    return summary


def _target_key(ctx: Context, geno: dict) -> dict:
    """What the rsID map was built from; a change triggers a rebuild."""
    def stamp(p: Path) -> list:
        st = p.stat()
        return [str(p), st.st_size, int(st.st_mtime)]
    idmap = resources.find(ctx, "dbsnp_map")
    src = None
    if idmap is not None:
        src = idmap.source.path / idmap.prefix if idmap.source.kind == "dir" else idmap.source.path
    variants = with_ext(geno["prefix"], ".bim" if geno["format"] == "bfile" else ".pvar")
    return {"variants": stamp(variants), "id_map": stamp(src) if src else None}


def _target(ctx: Context, geno_name: str | None, run: StepRun) -> tuple[dict, pd.DataFrame, Path]:
    geno = inventory.resolve_genotype(ctx, geno_name)
    d = target_dir(ctx, geno)
    table = d / "rsid_map.tsv.gz"
    summ = d / "summary.json"
    current = _target_key(ctx, geno)
    if not table.exists() or not summ.exists() or json.loads(summ.read_text()).get("source_key") != current:
        run.log.info("building the target rsID map")
        prs_target(ctx, geno["name"], run)
    m = pd.read_csv(table, sep="\t", dtype=str)
    return geno, m, d / f"{safe_name(geno['name'])}_rsid.bim"


# ── weights ────────────────────────────────────────────────────────────────
def read_weights(path: Path) -> pd.DataFrame:
    """Normalize to SNP, A1 (effect), A2 (may be NaN), BETA.

    Accepts headerless CHR SNP BP A1 A2 BETA (KNIH PheWeb) and headed files, including
    PGS-Catalog style files with leading '#' metadata lines. Multi-rsID entries are split
    and rsIDs that still occur more than once are dropped (plink2 --score refuses them).
    """
    with open_text(path) as fh:
        first = next((line for line in fh if not line.startswith("#")), "")
    sep = sniff_sep(first)
    fields = re.split(sep, first.strip())
    if len(fields) == 6 and fields[0].isdigit() and fields[1].startswith("rs"):
        w = pd.read_csv(path, sep=sep, header=None, comment="#", names=["CHR", "SNP", "BP", "A1", "A2", "BETA"],
                        dtype={"SNP": str, "A1": str, "A2": str})
    else:
        w = pd.read_csv(path, sep=sep, dtype=str, comment="#")
        cols = {c.upper(): c for c in w.columns}
        pick = {"SNP": next((cols[k] for k in ("SNP", "RSID", "RSIDS", "ID") if k in cols), None),
                "A1": next((cols[k] for k in ("A1", "EFFECT_ALLELE", "EA") if k in cols), None),
                "A2": next((cols[k] for k in ("A2", "OTHER_ALLELE", "NEA") if k in cols), None),
                "BETA": next((cols[k] for k in ("BETA", "WEIGHT", "EFFECT_WEIGHT") if k in cols), None)}
        if not (pick["SNP"] and pick["A1"] and pick["BETA"]):
            raise SamError(f"cannot read weights from {path.name}", hint=f"columns: {list(w.columns)}")
        w = pd.DataFrame({k: (w[v] if v else np.nan) for k, v in pick.items()})
    w["BETA"] = pd.to_numeric(w["BETA"], errors="coerce")
    w = w.dropna(subset=["SNP", "A1", "BETA"])
    w["SNP"] = w["SNP"].astype(str).str.split(",").map(lambda ids: sorted(set(ids)))
    w = w.explode("SNP")
    return w[~w["SNP"].duplicated(keep=False)]


def match_weights(w: pd.DataFrame, target: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    cols = [c for c in ("SNP", "A1", "A2", "BETA") if c in w.columns]
    m = w[cols].merge(target, on="SNP", how="inner")
    if "A2" not in m:
        m["A2"] = np.nan
    a1, a2 = m["A1"].str.upper(), m["A2"].fillna("").str.upper()
    alt, ref = m["ALT"].str.upper(), m["REF"].str.upper()
    direct = ((a1 == alt) & ((a2 == ref) | (a2 == ""))) | ((a1 == ref) & ((a2 == alt) | (a2 == "")))
    comp_a1, comp_a2 = a1.str.translate(COMPLEMENT), a2.str.translate(COMPLEMENT)
    strand = ~direct & (((comp_a1 == alt) & (comp_a2 == ref)) | ((comp_a1 == ref) & (comp_a2 == alt)))
    ambiguous = ((alt + ref).isin(["AT", "TA", "CG", "GC"]))
    m = m.assign(EFFECT=np.where(strand, comp_a1, a1))
    keep = direct | (strand & ~ambiguous)
    stats = {"n_weights": int(len(w)), "n_in_target": int(len(m)), "n_used": int(keep.sum()),
             "n_strand_flipped": int((strand & ~ambiguous).sum()),
             "n_allele_mismatch_dropped": int((~direct & ~strand).sum()),
             "n_ambiguous_at_cg_used": int((direct & ambiguous).sum())}
    stats["match_rate"] = round(stats["n_used"] / max(stats["n_weights"], 1), 4)
    used = m[keep]
    stats["chromosomes"] = sorted({int(c) for c in used["CHR"].astype(str) if c.isdigit()})
    return used[["ID", "EFFECT", "BETA"]].rename(columns={"EFFECT": "A1"}), stats


def _score(ctx: Context, run: StepRun, geno: dict, used: pd.DataFrame, d: Path) -> dict:
    score_in = d / "score_input.tsv"
    used.rename(columns={"BETA": "PRS"}).to_csv(score_in, sep="\t", index=False)
    flag = ["--bfile", geno["prefix"]] if geno["format"] == "bfile" else ["--pfile", geno["prefix"]]
    out = d / "score"
    run.run([tool_path(ctx, "plink2"), *flag, "--score", score_in, "1", "2", "3", "header-read",
             "cols=+scoresums", "list-variants", "--out", out, "--threads", ctx.threads])
    sc = pd.read_csv(f"{out}.sscore", sep="\t")
    s = sc["PRS_SUM"]
    q = s.quantile([0.01, 0.25, 0.5, 0.75, 0.99]).round(6)
    return {"n_samples": int(len(sc)), "score_column": "PRS_SUM",
            "distribution": {"mean": round(float(s.mean()), 6), "sd": round(float(s.std()), 6),
                             "q01": q[0.01], "q25": q[0.25], "median": q[0.5], "q75": q[0.75], "q99": q[0.99]},
            "allele_ct_mean": round(float(sc["ALLELE_CT"].mean()), 1) if "ALLELE_CT" in sc else None}


def _sample_overlap_note(source: str) -> str:
    return (f"weights/statistics come from {source}; if the target samples took part in that GWAS "
            "(e.g. KoGES samples in KBA meta-analyses), PRS performance will be inflated. "
            "Confirm the target cohort is independent before evaluating prediction.")


def prs_score(ctx: Context, weights: str, name: str | None = None, geno_name: str | None = None) -> dict:
    wpath = ctx.input_path(weights)
    name = safe_name(name or re.sub(r"\.(txt|tsv)(\.gz)?$", "", wpath.name))
    run = StepRun(ctx, "prs-score", name, {"weights": wpath.name, "geno": geno_name}, ["plink2", "python"])
    geno, target, _ = _target(ctx, geno_name, run)
    d = ctx.out("prs", name, is_dir=True)
    w = read_weights(wpath)
    used, mstats = match_weights(w, target)
    if mstats["n_used"] == 0:
        raise SamError("no weight variants matched the target", hint="check build (hg19/hg38) and rsID map")
    if mstats["match_rate"] < 0.5:
        run.warn(f"only {mstats['match_rate']:.0%} of weight variants are usable on the target; the score "
                 "captures part of the model only")
    sc = _score(ctx, run, geno, used, d)
    run.warn(_sample_overlap_note(wpath.name))
    summary = {"name": name, "weights_file": wpath.name, "matching": mstats, "score": sc,
               "genome_wide": len(mstats["chromosomes"]) >= 22}
    return run.finish(summary, {"scores": d / "score.sscore", "variants_used": d / "score.sscore.vars"}, [wpath],
                      [], d / "summary.json")


# ── PRS-CS ─────────────────────────────────────────────────────────────────
def _prepare_sumstats(path: Path, out: Path, keep: set[str] | None = None) -> dict:
    with open_text(path) as fh:
        line = fh.readline().rstrip("\n")
    head = re.split(sniff_sep(line), line.strip())
    low = {c.lower(): c for c in head}
    if {"rsids", "ref", "alt", "beta", "sebeta"} <= set(low):
        want = [low["rsids"], low["alt"], low["ref"], low["beta"], low["sebeta"]]
        df = pd.read_csv(path, sep="\t", usecols=want, dtype=str)[want]  # usecols keeps file order; reorder
        df.columns = ["SNP", "A1", "A2", "BETA", "SE"]  # PheWeb: beta is for the ALT allele
        fmt = "pheweb"
    elif {"snp", "a1", "a2", "beta"} <= set(low) and ("se" in low or "p" in low):
        last = "se" if "se" in low else "p"
        want = [low["snp"], low["a1"], low["a2"], low["beta"], low[last]]
        df = pd.read_csv(path, sep=r"\s+", usecols=want, dtype=str)[want]
        df.columns = ["SNP", "A1", "A2", "BETA", last.upper()]
        fmt = "generic"
    else:
        raise SamError(f"unrecognized summary statistics format: {path.name}", hint=f"header: {head[:12]}")
    n_rows = len(df)
    df["SNP"] = df["SNP"].fillna("").str.split(",").map(lambda ids: sorted(set(ids)))  # 'rs1,rs1' -> rs1
    df = df.explode("SNP")
    df = df[df["SNP"].str.startswith("rs")]
    df = df[~df["SNP"].duplicated(keep=False)]
    n_usable = len(df)
    if keep is not None:  # only SNPs PRS-CS can use: in the LD reference and in the target
        df = df[df["SNP"].isin(keep)]
    for c in df.columns[3:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna()
    if "SE" in df:
        df = df[df["SE"] > 0]
    df.to_csv(out, sep="\t", index=False)
    return {"format": fmt, "n_rows": int(n_rows), "n_usable_rsid": int(n_usable),
            "n_in_ld_reference_and_target": int(len(df)) if keep is not None else None}


def _gwas_n_from_meta(path: Path) -> int | None:
    meta = path.with_name(path.name + ".meta.json")
    if meta.exists():
        return json.loads(meta.read_text()).get("n_gwas")
    return None


def prs_prscs(ctx: Context, sumstats: str, n_gwas: int | None = None, name: str | None = None,
              chroms: str | None = None, ancestry: str = "EAS", allow_partial: bool = False,
              geno_name: str | None = None, phi: float | None = None, seed: int = 1,
              parallel: int | None = None) -> dict:
    spath = ctx.input_path(sumstats)
    gwas_root = (ctx.output_dir / "gwas").resolve()
    if str(spath).startswith(str(gwas_root)) or spath.name == "results.tsv.gz":
        raise SamError("PRS-CS input must be external summary statistics; this harness's own GWAS results are "
                       "not accepted (discovery and target samples would overlap)")
    n_gwas = n_gwas or _gwas_n_from_meta(spath)
    if not n_gwas:
        raise SamError("GWAS sample size (n_gwas) is required for PRS-CS",
                       hint="files fetched with sam_pheweb carry it; otherwise ask the user or check the source")
    name = safe_name(name or re.sub(r"\.(tsv|txt)(\.gz)?$", "", spath.name).replace("phenocode-", "") + "_prscs")
    comp = resources.find(ctx, "prscs_ld", prefer=f"_{ancestry.lower()}")
    if comp is None:
        raise SamError("no PRS-CS LD reference (ldblk_*) in the resource directory",
                       hint="e.g. ldblk_1kg_eas.tar.gz; see docs/TOOLS.md")
    if comp.meta.get("ancestry") != ancestry.upper():
        raise SamError(f"LD reference ancestry {comp.meta.get('ancestry')} does not match requested {ancestry}")
    available = sorted(set(comp.chroms))
    wanted = parse_chroms(chroms) or list(range(1, 23))
    use = [c for c in wanted if c in available]
    missing = [c for c in wanted if c not in available]
    partial = len(use) < 22
    if not use:
        raise SamError(f"LD reference has none of the requested chromosomes {wanted}", hint=f"available: {available}")
    if partial and not allow_partial:
        raise SamError(f"PRS-CS would run on chromosomes {use} only (not genome-wide)",
                       hint="ask the user; rerun with allow_partial=true if a partial score is acceptable")
    run = StepRun(ctx, "prs-prscs", name, {"sumstats": spath.name, "n_gwas": n_gwas, "chromosomes": use,
                                            "ancestry": ancestry, "ld_panel": comp.meta.get("panel"),
                                            "phi": phi or "auto", "seed": seed},
                  ["plink2", "python", "prscs-python", "prscs"])
    if missing:
        run.warn(f"chromosomes without LD reference skipped: {missing}")
    geno, target, rsid_bim = _target(ctx, geno_name, run)
    d = ctx.out("prs", name, is_dir=True)
    members = [f for f in comp.files if PurePosixPath(f).name.startswith("snpinfo_") or
               any(f.endswith(f"_chr{c}.hdf5") for c in use)]
    root = resources.materialize(ctx, comp, members, log=run.log)
    ref_dir = root / comp.prefix.rstrip("/")
    snpinfo = next(ref_dir.glob("snpinfo_*"))
    ld_snps = set(pd.read_csv(snpinfo, sep=r"\s+", usecols=["SNP"], dtype=str)["SNP"])
    target_snps = set(pd.read_csv(rsid_bim, sep="\t", header=None, usecols=[1], dtype=str)[1])
    sst = d / "prscs_sumstats.txt"
    ss_info = _prepare_sumstats(spath, sst, ld_snps & target_snps)
    run.log.info(f"summary statistics: {ss_info}")
    out_dir = ctx.out("prs", name, "prscs", is_dir=True)
    for f in out_dir.glob("*"):
        f.unlink()
    jobs = parallel or max(1, min(len(use), ctx.threads // 2))
    per_job = max(1, ctx.threads // jobs)
    py, prscs = tool_path(ctx, "prscs-python"), tool_path(ctx, "prscs")
    run.log.info(f"running PRS-CS on {len(use)} chromosome(s), {jobs} at a time, {per_job} thread(s) each")

    def one(chrom: int) -> int:
        log = StepLog(ctx, f"prs-prscs_{name}_chr{chrom}")
        try:
            cmd = [py, prscs, f"--ref_dir={ref_dir}", f"--bim_prefix={str(rsid_bim)[:-4]}", f"--sst_file={sst}",
                   f"--n_gwas={int(n_gwas)}", f"--chrom={chrom}", f"--out_dir={out_dir / name}", f"--seed={seed}"]
            if phi:
                cmd.append(f"--phi={phi}")
            run_tool(ctx, log, cmd, threads=per_job, echo_every=50)
        finally:
            log.close()
        return chrom

    with cf.ThreadPoolExecutor(max_workers=jobs) as pool:
        for chrom in pool.map(one, use):
            run.log.info(f"chr{chrom} done")
    parts = sorted(out_dir.glob(f"{name}_pst_eff_*_chr*.txt"))
    if not parts:
        raise SamError("PRS-CS produced no posterior effect files", hint=f"see logs in {ctx.output_dir / 'logs'}")
    post = pd.concat([pd.read_csv(p, sep="\t", header=None, names=["CHR", "SNP", "BP", "A1", "A2", "BETA"],
                                  dtype={"SNP": str, "A1": str, "A2": str}) for p in parts])
    weights = d / "weights.tsv.gz"
    write_tsv(post, weights, compression="gzip")
    used, mstats = match_weights(post, target)
    sc = _score(ctx, run, geno, used, d)
    run.warn(_sample_overlap_note(spath.name))
    if partial:
        run.warn(f"PARTIAL score: chromosomes {use} only; not a genome-wide PRS")
    summary = {"name": name, "sumstats": {**ss_info, "file": spath.name, "n_gwas": n_gwas},
               "ld_reference": comp.meta.get("panel"), "chromosomes": use, "partial": partial,
               "n_posterior_effects": int(len(post)), "matching": mstats, "score": sc}
    return run.finish(summary, {"weights": weights, "scores": d / "score.sscore"}, [spath], [], d / "summary.json")
