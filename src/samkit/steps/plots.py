"""Manhattan and QQ plots from standardized GWAS results; independent peaks."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

from samkit.context import Context  # noqa: E402
from samkit.io import GW_LOG10P, chrom_key, df_to_records, lambda_gc_from_log10p, safe_name, write_tsv  # noqa: E402
from samkit.steps import StepRun  # noqa: E402
from samkit.steps.gwas import distance_loci, load_results  # noqa: E402

COLORS = ("#3b6ea8", "#9aa7b8")


def manhattan_qq(ctx: Context, pheno: str) -> dict:
    res, gsum = load_results(ctx, pheno)
    run = StepRun(ctx, "plots", pheno, {}, ["python"])
    d = ctx.out("plots", safe_name(pheno), is_dir=True)
    lp = res["LOG10P"].values.astype(float)

    # Manhattan: cumulative positions; thin the null bulk for speed (all points with LOG10P >= 1 kept)
    res = res.assign(_c=res["CHROM"].map(chrom_key))
    chroms = sorted(res["_c"].unique())
    offsets, ticks, start = {}, [], 0
    for c in chroms:
        mx = int(res.loc[res["_c"] == c, "GENPOS"].max())
        offsets[c] = start
        ticks.append(start + mx / 2)
        start += mx + 5_000_000
    x = res["GENPOS"].values + res["_c"].map(offsets).values
    rng = np.random.default_rng(1)
    keep = (lp >= 1) | (rng.random(len(lp)) < 0.25)
    fig, ax = plt.subplots(figsize=(16, 5))
    col = np.array([COLORS[i % 2] for i in range(len(chroms))])[np.searchsorted(chroms, res["_c"].values)]
    ax.scatter(x[keep], lp[keep], c=col[keep], s=3, linewidths=0, rasterized=True)
    ax.axhline(GW_LOG10P, color="#c0392b", ls="--", lw=0.8, label="P = 5×10⁻⁸")
    ax.axhline(5, color="#2471a3", ls=":", lw=0.8, label="P = 1×10⁻⁵")
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(c) if c <= 22 else {23: "X", 24: "Y"}.get(c, str(c)) for c in chroms], fontsize=7)
    ax.set_xlim(x.min() - 2e6, x.max() + 2e6)
    ax.set_xlabel("Chromosome")
    ax.set_ylabel("−log₁₀(P)")
    ax.set_title(f"{pheno} — Manhattan plot (n variants = {len(res):,})")
    ax.legend(fontsize=8, loc="upper right")
    fig.tight_layout()
    man = d / "manhattan.png"
    fig.savefig(man, dpi=150)
    plt.close(fig)

    # QQ: work on -log10 P directly (no underflow for very small P)
    n = len(lp)
    obs = np.sort(lp)[::-1]
    exp = -np.log10((np.arange(1, n + 1) - 0.5) / n)
    ranks = np.arange(1, n + 1)
    ci_hi = -np.log10(stats.beta.ppf(0.025, ranks, n - ranks + 1))
    ci_lo = -np.log10(stats.beta.ppf(0.975, ranks, n - ranks + 1))
    lam = lambda_gc_from_log10p(lp)
    thin = np.unique(np.concatenate([np.arange(min(n, 5000)), np.linspace(0, n - 1, 20000).astype(int)]))
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.fill_between(exp[thin], ci_lo[thin], ci_hi[thin], color="#bbbbbb", alpha=0.5, lw=0, label="95% CI")
    ax.plot([0, exp.max()], [0, exp.max()], color="#c0392b", lw=0.8)
    ax.scatter(exp[thin], obs[thin], s=5, c="#3b6ea8", linewidths=0, rasterized=True)
    ax.set_xlabel("Expected −log₁₀(P)")
    ax.set_ylabel("Observed −log₁₀(P)")
    ax.set_title(f"{pheno} — QQ plot (λGC = {lam:.3f})")
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    qq = d / "qq.png"
    fig.savefig(qq, dpi=150)
    plt.close(fig)

    summary = {"lambda_gc": round(lam, 4), "n_variants": int(n), "max_log10p": round(float(lp.max()), 2),
               "partial_genome": not gsum.get("summary", {}).get("complete_autosomes", True)}
    if lam > 1.1:
        run.warn(f"λGC = {lam:.3f} > 1.1: check stratification/relatedness (or a highly polygenic trait in a large N)")
    return run.finish(summary, {"manhattan": man, "qq": qq}, [], ["peaks", "ldsc"], d / "summary.json")


def peaks(ctx: Context, pheno: str, p_threshold: float = 5e-8, window_kb: int = 500, top: int = 20) -> dict:
    res, _ = load_results(ctx, pheno)
    run = StepRun(ctx, "peaks", pheno, {"p_threshold": p_threshold, "window_kb": window_kb}, ["python"])
    thr = -np.log10(p_threshold)
    sig = res[res["LOG10P"] >= thr]
    loci = distance_loci(sig, window_kb * 1000)
    d = ctx.out("loci", safe_name(pheno), is_dir=True)
    table = pd.DataFrame(loci)
    if not table.empty:
        table.insert(0, "locus", [f"{r.CHROM}:{r.GENPOS}" for r in table.itertuples()])
        table.insert(0, "rank", range(1, len(table) + 1))
    out = d / "peaks.tsv"
    write_tsv(table if not table.empty else pd.DataFrame(columns=["rank", "locus", "ID"]), out)
    summary = {"p_threshold": p_threshold, "window_kb": window_kb, "n_significant_variants": int(len(sig)),
               "n_loci": len(loci), "loci": df_to_records(table.head(top)) if not table.empty else []}
    if not loci:
        best = res.nlargest(5, "LOG10P")[["CHROM", "GENPOS", "ID", "LOG10P"]]
        summary["strongest_variants"] = df_to_records(best)
        run.warn("no variant reaches the threshold; regional plot / fine-mapping of a non-significant locus "
                 "is exploratory only")
    return run.finish(summary, {"peaks": out}, [], ["regional", "finemap"])
