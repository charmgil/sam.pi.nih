"""Fine-mapping with SuSiE-RSS (susieR) using in-sample LD.

Allele alignment: plink2 '--r-unphased ref-based' gives correlations of REF
dosages, which equal correlations of ALT dosages. BETA from regenie refers to
ALLELE1; it is flipped where ALLELE1 is the REF allele so that z-scores and R
are coded on the same (ALT) allele. Variants whose alleles do not match the
genotype file are dropped and reported.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from samkit.context import Context, SamError  # noqa: E402
from samkit.io import GW_LOG10P, with_ext  # noqa: E402
from samkit.steps import StepRun  # noqa: E402
from samkit.steps.gwas import geno_flags, load_results  # noqa: E402
from samkit.steps.regional import CS_COLOR, R2_BINS, keep_file, locus_dir, plot_regional, resolve_locus, setup_geno  # noqa: E402
from samkit.tools import tool_path  # noqa: E402

MAX_VARIANTS = 6000


def variant_alleles(geno: dict, ids: set[str]) -> pd.DataFrame:
    """ID, ALT, REF as plink2 sees them (bim: col5 = ALT/A1, col6 = REF/A2)."""
    prefix = Path(geno["prefix"])
    if geno["format"] == "bfile":
        bim = pd.read_csv(with_ext(prefix, ".bim"), sep=r"\s+", header=None, usecols=[1, 4, 5],
                          names=["ID", "ALT", "REF"], dtype=str)
        return bim[bim["ID"].isin(ids)]
    rows = []
    with open(with_ext(prefix, ".pvar")) as fh:
        header = None
        for line in fh:
            if line.startswith("##"):
                continue
            if line.startswith("#"):
                header = line[1:].rstrip("\n").split("\t")
                continue
            f = dict(zip(header, line.rstrip("\n").split("\t")))
            if f["ID"] in ids:
                rows.append((f["ID"], f["ALT"], f["REF"]))
    return pd.DataFrame(rows, columns=["ID", "ALT", "REF"])


def finemap(ctx: Context, pheno: str, locus: str, window_kb: int = 500, L: int = 10, coverage: float = 0.95,
            min_abs_corr: float = 0.5, estimate_residual_variance: bool = True) -> dict:
    """estimate_residual_variance=True follows the susieR advice for in-sample LD (our case)."""
    res, gsum = load_results(ctx, pheno)
    lead = resolve_locus(ctx, pheno, res, locus)
    window = window_kb * 1000
    run = StepRun(ctx, "finemap", f"{pheno}:{lead['CHROM']}:{lead['GENPOS']}",
                  {"locus": locus, "lead": lead["ID"], "window_kb": window_kb, "L": L, "coverage": coverage,
                   "min_abs_corr": min_abs_corr, "estimate_residual_variance": estimate_residual_variance},
                  ["plink2", "Rscript", "python"])
    if not lead["genome_wide_significant"]:
        run.warn(f"lead {lead['ID']} is not genome-wide significant; credible sets would be exploratory")
    d = locus_dir(ctx, pheno, lead)
    geno = setup_geno(ctx, pheno)

    region = res[(res["CHROM"].astype(int) == lead["CHROM"]) &
                 res["GENPOS"].between(lead["GENPOS"] - window, lead["GENPOS"] + window)].copy()
    region = region.drop_duplicates("ID", keep=False)
    if len(region) > MAX_VARIANTS:
        raise SamError(f"{len(region)} variants in ±{window_kb} kb; too many for SuSiE here",
                       hint="use a smaller window_kb")
    alle = variant_alleles(geno, set(region["ID"]))
    region = region.merge(alle, on="ID", how="left")
    same = (region["ALLELE1"] == region["ALT"]) & (region["ALLELE0"] == region["REF"])
    flip = (region["ALLELE1"] == region["REF"]) & (region["ALLELE0"] == region["ALT"])
    n_mismatch = int((~same & ~flip).sum())
    if n_mismatch:
        run.warn(f"{n_mismatch} variant(s) dropped: alleles differ between results and genotype file")
    region = region[same | flip].copy()
    region["sign"] = np.where(flip[same | flip], -1.0, 1.0)
    region["BETA_ALT"] = region["BETA"] * region["sign"]

    ids_file = d / "susie_variants.txt"
    region["ID"].to_csv(ids_file, index=False, header=False)
    ld_prefix = d / "susie_ld"
    pflag, _ = geno_flags(geno)
    run.run([tool_path(ctx, "plink2"), *pflag, "--keep", keep_file(ctx, pheno, d), "--extract", ids_file,
             "--r-unphased", "square", "bin4", "ref-based", "--out", ld_prefix, "--threads", ctx.threads])
    ld_bin = Path(f"{ld_prefix}.unphased.vcor1.bin")
    vars_file = Path(f"{ld_bin}.vars")
    if not vars_file.exists():
        vars_file = Path(f"{ld_prefix}.unphased.vcor1.vars")
    order = pd.read_csv(vars_file, header=None, names=["ID"], dtype=str)
    region = order.merge(region, on="ID", how="left")
    reg_tsv = d / "susie_region.tsv"
    region[["ID", "BETA_ALT", "SE"]].rename(columns={"BETA_ALT": "BETA"}).to_csv(reg_tsv, sep="\t", index=False,
                                                                                  na_rep="NA")
    n = float(np.median(region["N"].dropna()))
    out_prefix = d / "susie"
    run.run([tool_path(ctx, "Rscript"), ctx.home / "src" / "samkit" / "r" / "susie.R", reg_tsv, ld_bin, n, L,
             coverage, min_abs_corr, out_prefix, "TRUE" if estimate_residual_variance else "FALSE"])
    fit = json.loads(Path(f"{out_prefix}_fit.json").read_text())
    pip = pd.read_csv(f"{out_prefix}_pip.tsv", sep="\t", dtype={"ID": str})
    cs = pd.read_csv(f"{out_prefix}_cs.tsv", sep="\t", dtype={"ID": str})

    # r² with the lead from the same matrix (for colouring)
    k = len(order)
    R = np.fromfile(ld_bin, dtype=np.float32).reshape(k, k)
    li = order.index[order["ID"] == lead["ID"]]
    r2 = pd.Series(R[li[0]] ** 2 if len(li) else np.full(k, np.nan), index=order["ID"])
    plot_df = region.merge(pip, on="ID", how="left")
    plot_df["R2"] = plot_df["ID"].map(r2)
    two = d / "susie.png"
    _plot_pip(plot_df, cs, lead, two, f"{pheno}  chr{lead['CHROM']}:{lead['GENPOS']} ±{window_kb} kb")
    reg_plot = d / "regional_susie.png"
    notes = plot_regional(ctx, plot_df, lead, window,
                          f"{pheno}  {lead['ID']}  ±{window_kb} kb  (SuSiE credible sets)", reg_plot, cs, log=run.log)
    for note in notes:
        run.warn(note)

    if fit.get("ld_consistency_s") is not None and fit["ld_consistency_s"] > 0.1:
        run.warn(f"estimate_s_rss = {fit['ld_consistency_s']:.3f} (> 0.1): z-scores and LD look inconsistent; "
                 "treat credible sets with caution")
    if not fit.get("converged"):
        run.warn("SuSiE did not converge; consider a smaller window or different L")
    low_purity = [c["cs"] for c in fit.get("credible_sets", []) if c.get("min_abs_corr", 1) < 0.5]
    if low_purity:
        run.warn(f"low-purity credible sets (min |r| < 0.5): {low_purity}")
    summary = {
        "lead": lead, "window_kb": window_kb, "n_samples": n, "n_variants": fit["n_variants"],
        "n_allele_flipped": int((region["sign"] < 0).sum()), "n_allele_mismatch_dropped": n_mismatch,
        "converged": fit.get("converged"), "n_credible_sets": fit.get("n_credible_sets"),
        "credible_sets": fit.get("credible_sets"), "ld_consistency_s": fit.get("ld_consistency_s"),
        "top_pip": pip.nlargest(5, "PIP")[["ID", "PIP"]].round(4).to_dict(orient="records"),
        "gwas_lambda_gc": gsum.get("summary", {}).get("lambda_gc"),
    }
    return run.finish(summary, {"pip": Path(f"{out_prefix}_pip.tsv"), "credible_sets": Path(f"{out_prefix}_cs.tsv"),
                                "plot": two, "regional_plot": reg_plot}, [], ["regional"],
                      d / "susie_summary.json")


def _plot_pip(df: pd.DataFrame, cs: pd.DataFrame, lead: dict, out: Path, title: str) -> None:
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    x = df["GENPOS"] / 1e6
    colors = np.full(len(df), "#c7c7c7", dtype=object)
    for lo, hi, color, _ in R2_BINS:
        colors[(df["R2"] >= lo).values & (df["R2"] < hi).values] = color
    for ax, y, lab in ((a1, df["LOG10P"], "−log₁₀(P)"), (a2, df["PIP"], "PIP")):
        ax.scatter(x, y, c=colors, s=16, linewidths=0, zorder=2)
        for name, grp in cs.groupby("CS"):
            sub = df[df["ID"].isin(grp["ID"])]
            ax.scatter(sub["GENPOS"] / 1e6, (sub["LOG10P"] if ax is a1 else sub["PIP"]), facecolors="none",
                       edgecolors=CS_COLOR, s=70, linewidths=1.4, zorder=3)
            top = sub.loc[sub["PIP"].idxmax()]
            ax.annotate(name, (top["GENPOS"] / 1e6, top["LOG10P"] if ax is a1 else top["PIP"]), xytext=(0, 6),
                        textcoords="offset points", ha="center", fontsize=7, color=CS_COLOR, fontweight="bold")
        lr = df[df["ID"] == lead["ID"]]
        ax.scatter(lr["GENPOS"] / 1e6, lr["LOG10P"] if ax is a1 else lr["PIP"], marker="D", c="#7f0000", s=55,
                   edgecolors="black", linewidths=0.6, zorder=4)
        ax.set_ylabel(lab)
    a1.axhline(GW_LOG10P, color="#c0392b", ls="--", lw=0.8)
    a2.axhline(0.5, color="#888888", ls=":", lw=0.8)
    a2.set_ylim(-0.03, 1.05)
    a1.set_title(title, fontsize=10)
    a2.set_xlabel(f"Chromosome {lead['CHROM']} position (Mb)")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
