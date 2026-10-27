"""LD score regression (SNP heritability) with the Python 3 port of ldsc.

rsID assignment, in order of preference:
  1. variant-ID map (resource 'dbsnp_map', e.g. array probe ID -> rsID): exact per variant
  2. position map (resource 'pos2rsid'): CHR+BP -> rsID; positions with several rsIDs are dropped
Allele orientation does not affect h2 (χ² is sign-free), so no allele merge is needed here.
"""

from __future__ import annotations

import gzip
import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from samkit import resources  # noqa: E402
from samkit.context import Context, SamError  # noqa: E402
from samkit.io import p_from_log10p, safe_name, write_tsv  # noqa: E402
from samkit.steps import StepRun  # noqa: E402
from samkit.steps.gwas import load_results  # noqa: E402
from samkit.tools import tool_path  # noqa: E402

NUM = r"(-?[\d.]+(?:[eE][-+]?\d+)?|NA|nan)"


def read_id_map(path: Path) -> pd.DataFrame:
    with (gzip.open(path, "rt") if str(path).endswith(".gz") else open(path)) as fh:
        first = fh.readline().split()
    has_header = len(first) >= 2 and not first[1].startswith("rs")
    m = pd.read_csv(path, sep=r"\s+", header=0 if has_header else None, usecols=[0, 1], dtype=str)
    m.columns = ["ID", "SNP"]
    return m


def assign_rsids(ctx: Context, run: StepRun, res: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    info: dict = {}
    idmap = resources.find(ctx, "dbsnp_map")
    if idmap is not None:
        root = resources.materialize(ctx, idmap, log=run.log)
        m = read_id_map(root / idmap.prefix)
        out = res.merge(m, on="ID", how="inner")
        if len(out) >= 0.5 * len(res):
            info.update(method="variant-ID map", source=f"{idmap.source.label}:{idmap.prefix}")
            return out, info
        run.log.info(f"ID map matched only {len(out)}/{len(res)} variants; trying position map")
    pmap = resources.find(ctx, "pos2rsid")
    if pmap is None:
        raise SamError("no rsID mapping resource for LDSC", hint="need a dbSNP ID map or LDSC/pos2rsid.txt")
    root = resources.materialize(ctx, pmap, log=run.log)
    m = pd.read_csv(root / pmap.prefix, sep=r"\s+", dtype={"SNP": str})
    m.columns = ["CHROM", "GENPOS", "SNP"][: len(m.columns)]
    m = m[~m.duplicated(["CHROM", "GENPOS"], keep=False)]
    out = res.merge(m, on=["CHROM", "GENPOS"], how="inner")
    info.update(method="position map (CHR+BP)", source=f"{pmap.source.label}:{pmap.prefix}")
    run.warn("rsIDs assigned by position only; fine for h2, not sufficient for genetic correlation")
    return out, info


def parse_h2_log(text: str) -> dict:
    def grab(pattern):
        m = re.search(pattern, text)
        return m.groups() if m else None

    def num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    out: dict = {}
    if (g := grab(rf"Total Observed scale h2:\s*{NUM}\s*\({NUM}\)")):
        out["h2_observed"], out["h2_observed_se"] = num(g[0]), num(g[1])
    if (g := grab(rf"Total Liability scale h2:\s*{NUM}\s*\({NUM}\)")):
        out["h2_liability"], out["h2_liability_se"] = num(g[0]), num(g[1])
    if (g := grab(rf"Lambda GC:\s*{NUM}")):
        out["lambda_gc"] = num(g[0])
    if (g := grab(rf"Mean Chi\^2:\s*{NUM}")):
        out["mean_chi2"] = num(g[0])
    if (g := grab(rf"Intercept:\s*{NUM}\s*\({NUM}\)")):
        out["intercept"], out["intercept_se"] = num(g[0]), num(g[1])
    if (g := grab(rf"Ratio:\s*{NUM}\s*\({NUM}\)")):
        out["ratio"], out["ratio_se"] = num(g[0]), num(g[1])
    elif "Ratio < 0" in text:
        out["ratio"] = "< 0 (usually indicates GC correction)"
    snps = re.findall(r"(\d+) SNPs remain", text)
    if snps:
        out["n_snps_regression"] = int(snps[-1])
    return out


def single_annotation(ctx: Context, ref_root: Path, prefix: str, log) -> Path:
    """Univariate LD scores from a multi-annotation panel: its 'base' column (all SNPs).

    Returns the --ref-ld-chr prefix of a cached copy holding CHR SNP BP L2 and the matching
    M / M_5_50 counts (the first entry, which belongs to the base annotation).
    """
    src = ref_root / prefix
    out_dir = ctx.out("_cache", "ldsc_base", safe_name(prefix.strip("./")), is_dir=True)
    for c in range(1, 23):
        dst = out_dir / f"base.{c}.l2.ldscore.gz"
        if dst.exists():
            continue
        cols = pd.read_csv(f"{src}{c}.l2.ldscore.gz", sep="\t", nrows=0).columns
        base = "baseL2" if "baseL2" in cols else cols[3]
        df = pd.read_csv(f"{src}{c}.l2.ldscore.gz", sep="\t", usecols=["CHR", "SNP", "BP", base])
        df.rename(columns={base: "L2"}).to_csv(dst, sep="\t", index=False, compression="gzip")
        for suffix in (".l2.M_5_50", ".l2.M"):
            m = Path(f"{src}{c}{suffix}")
            if m.exists():
                (out_dir / f"base.{c}{suffix}").write_text(m.read_text().split()[0] + "\n")
    log.info(f"univariate LD scores (base annotation) cached in {out_dir}")
    return out_dir / "base."


def run_ldsc(ctx: Context, pheno: str, pop_prev: float | None = None, allow_partial: bool = False,
             model: str = "base") -> dict:
    """model='base': standard univariate h2 (all-SNP LD score of the panel);
    model='baseline': stratified LDSC with every annotation of the panel (total h2 is model-dependent)."""
    res, gsum = load_results(ctx, pheno)
    g = gsum.get("summary", {})
    if not g.get("complete_autosomes", False) and not allow_partial:
        raise SamError("LDSC needs genome-wide results (all 22 autosomes); these results are partial",
                       hint=f"chromosomes present: {g.get('chromosomes')}; rerun gwas-step2 without --chroms")
    run = StepRun(ctx, "ldsc", pheno, {"pop_prev": pop_prev, "allow_partial": allow_partial, "model": model},
                  ["python", "ldsc-python", "ldsc", "munge_sumstats"])
    ref = resources.require(ctx, "ldsc_ref", what="LD scores, e.g. baseline.{1..22}.l2.ldscore.gz")
    wts = resources.require(ctx, "ldsc_weights", what="regression weights, e.g. weights.EAS.hm3_noMHC.*")
    for comp in (ref, wts):
        if not set(range(1, 23)) <= set(comp.chroms):
            raise SamError(f"{comp.kind} {comp.prefix} lacks some autosomes", hint=f"has {comp.chroms}")
    # extract only what --h2 reads (no .annot files)
    ref_root = resources.materialize(ctx, ref, [f for f in ref.source.members if f.startswith(ref.prefix) and
                                               re.search(r"\.l2\.(ldscore\.gz|M_5_50|M)$", f)], log=run.log)
    wts_root = resources.materialize(ctx, wts, [f for f in wts.source.members if f.startswith(wts.prefix) and
                                               re.search(r"\.l2\.(ldscore\.gz|M_5_50|M)$", f)], log=run.log)
    d = ctx.out("ldsc", safe_name(pheno), is_dir=True)

    mapped, map_info = assign_rsids(ctx, run, res)
    dup = mapped["SNP"].duplicated(keep=False)
    mapped = mapped[~dup & mapped["SNP"].str.startswith("rs")]
    frm = pd.DataFrame({"SNP": mapped["SNP"], "A1": mapped["ALLELE1"], "A2": mapped["ALLELE0"],
                        "BETA": mapped["BETA"], "P": p_from_log10p(mapped["LOG10P"]), "N": mapped["N"],
                        "FRQ": mapped["A1FREQ"]})
    # uncompressed on purpose: ldsc 2.0.1's munge_sumstats reads a gzipped header as bytes and fails
    for_munge = d / "for_munge.tsv"
    write_tsv(frm, for_munge)
    run.log.info(f"rsID mapping: {len(frm):,} of {len(res):,} variants ({map_info['method']})")

    py = tool_path(ctx, "ldsc-python")
    munged = d / "munged"
    run.run([py, tool_path(ctx, "munge_sumstats"), "--sumstats", for_munge, "--snp", "SNP", "--a1", "A1",
             "--a2", "A2", "--signed-sumstats", "BETA,0", "--p", "P", "--N-col", "N", "--frq", "FRQ",
             "--out", munged])
    h2 = d / "h2"
    ref_ld = single_annotation(ctx, ref_root, ref.prefix, run.log) if model == "base" else ref_root / ref.prefix
    cmd = [py, tool_path(ctx, "ldsc"), "--h2", f"{munged}.sumstats.gz",
           "--ref-ld-chr", str(ref_ld), "--w-ld-chr", str(wts_root / wts.prefix), "--out", h2]
    trait = gsum.get("summary", {}).get("trait")
    if trait == "bt" and pop_prev is None:
        run.warn("binary trait without population prevalence: h2 is on the observed (case/control) scale; "
                 "give population_prevalence for the liability scale")
    if trait == "qt" and pop_prev is not None:
        run.warn("population prevalence is ignored for a quantitative trait")
    if trait == "bt" and pop_prev is not None:
        setup = ctx.output_dir / "gwas" / safe_name(pheno) / "setup.json"
        ph = json.loads(setup.read_text())["pheno"]
        samp_prev = ph["cases"] / (ph["cases"] + ph["controls"])
        cmd += ["--samp-prev", f"{samp_prev:.6f}", "--pop-prev", str(pop_prev)]
    run.run(cmd)
    est = parse_h2_log(Path(f"{h2}.log").read_text())
    est["rsid_mapping"] = {**map_info, "n_mapped": int(len(frm)), "n_results": int(len(res))}
    est["reference"] = {"ld_scores": ref.meta.get("panel"), "weights": wts.meta.get("panel"),
                        "model": "univariate (base annotation)" if model == "base" else "stratified (all annotations)"}

    h, se = est.get("h2_observed"), est.get("h2_observed_se")
    if h is not None and se:
        est["h2_z"] = round(h / se, 2)
        if not 0 <= h <= 1:
            run.warn(f"h2 = {h} is outside [0, 1]; the estimate is not interpretable (low power or model misfit)")
        if h / se < 4:
            run.warn("h2 z-score < 4: LDSC authors advise against interpreting estimates this weak")
    if est.get("intercept") and est["intercept"] > 1.1:
        run.warn(f"intercept {est['intercept']} > 1.1 suggests confounding (stratification/cryptic relatedness)")
    if est.get("n_snps_regression", 1e9) < 200_000:
        run.warn(f"only {est.get('n_snps_regression')} regression SNPs (< 200k); estimate may be unstable")
    if g.get("n_samples_median", 1e9) < 5000:
        run.warn("N < 5,000: LDSC h2 estimates are imprecise at this sample size")

    plot = d / "ldsc_regression.png"
    _plot(f"{munged}.sumstats.gz", ref_root / ref.prefix, plot, pheno, est)
    return run.finish(est, {"h2_log": Path(f"{h2}.log"), "munged": Path(f"{munged}.sumstats.gz"), "plot": plot},
                      [], [], d / "summary.json")


def _plot(sumstats: str, ref_prefix: Path, out: Path, pheno: str, est: dict, bins: int = 50) -> None:
    ss = pd.read_csv(sumstats, sep="\t").dropna(subset=["Z"])
    ld = []
    for c in range(1, 23):
        f = Path(f"{ref_prefix}{c}.l2.ldscore.gz")
        cols = pd.read_csv(f, sep="\t", nrows=0).columns
        col = "baseL2" if "baseL2" in cols else cols[3]
        ld.append(pd.read_csv(f, sep="\t", usecols=["SNP", col]).rename(columns={col: "L2"}))
    m = ss.merge(pd.concat(ld), on="SNP")
    m["chi2"] = m["Z"] ** 2
    m["bin"] = pd.qcut(m["L2"], bins, duplicates="drop")
    b = m.groupby("bin", observed=True).agg(L2=("L2", "mean"), chi2=("chi2", "mean"))
    slope, icpt = np.polyfit(b["L2"], b["chi2"], 1)
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(b["L2"], b["chi2"], s=18, c="#3b6ea8", zorder=3)
    xs = np.linspace(0, b["L2"].max() * 1.05, 100)
    ax.plot(xs, slope * xs + icpt, color="#c0392b", lw=1.5, label="OLS on bins (illustration)")
    ax.axhline(1, color="#888888", ls=":", lw=0.8)
    title = f"{pheno} — LD score regression"
    if est.get("h2_observed") is not None:
        title += (f"\nh²(obs) = {est['h2_observed']} (SE {est.get('h2_observed_se')}),  "
                  f"intercept = {est.get('intercept')} (SE {est.get('intercept_se')})")
    ax.set_title(title, fontsize=10)
    ax.set_xlabel("LD score (bin mean)")
    ax.set_ylabel("Mean χ²")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
