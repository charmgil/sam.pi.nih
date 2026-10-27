"""Regional association plot around a lead variant (LD from the GWAS samples)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.gridspec import GridSpec  # noqa: E402

from samkit import genes  # noqa: E402
from samkit.context import Context, SamError  # noqa: E402
from samkit.io import GW_LOG10P, safe_name  # noqa: E402
from samkit.steps import StepRun  # noqa: E402
from samkit.steps.gwas import geno_flags, load_results  # noqa: E402
from samkit.tools import tool_path  # noqa: E402

R2_BINS = [(0.8, 1.01, "#d7191c", "0.8 ≤ r²"), (0.6, 0.8, "#fdae61", "0.6–0.8"), (0.4, 0.6, "#2ca25f", "0.4–0.6"),
           (0.2, 0.4, "#2b83ba", "0.2–0.4"), (0.0, 0.2, "#9ecae1", "< 0.2")]
NO_LD = "#c7c7c7"
CS_COLOR = "#7b3294"


# ── locus resolution (shared with fine-mapping) ─────────────────────────────
def resolve_locus(ctx: Context, pheno: str, res: pd.DataFrame, locus: str) -> dict:
    """Locus as 'CHR:POS', a variant ID, or a rank from peaks.tsv ('1', '#2')."""
    spec = locus.strip()
    peaks_file = ctx.output_dir / "loci" / safe_name(pheno) / "peaks.tsv"
    peak_ids: set[str] = set()
    if peaks_file.exists():
        pk = pd.read_csv(peaks_file, sep="\t", dtype={"ID": str})
        peak_ids = set(pk.get("ID", pd.Series(dtype=str)).astype(str))
        if re.fullmatch(r"#?\d{1,3}", spec):
            rank = int(spec.lstrip("#"))
            hit = pk[pk["rank"] == rank]
            if hit.empty:
                raise SamError(f"no peak with rank {rank}", hint=f"{len(pk)} peaks in {peaks_file.name}")
            spec = str(hit.iloc[0]["ID"])
    elif re.fullmatch(r"#?\d{1,3}", spec):
        raise SamError("peak ranks need the peak list first", hint="run peaks (sam_peaks) first")
    if (m := re.fullmatch(r"(?:chr)?(\d{1,2})[:_](\d+)", spec, flags=re.I)):
        chrom, pos = int(m[1]), int(m[2])
        cand = res[(res["CHROM"].astype(int) == chrom) & (res["GENPOS"] == pos)]
        if cand.empty:
            near = res[(res["CHROM"].astype(int) == chrom) & ((res["GENPOS"] - pos).abs() <= 50_000)]
            near = near.assign(dist=(near["GENPOS"] - pos).abs()).nsmallest(5, "dist")
            raise SamError(f"no tested variant at {chrom}:{pos}",
                           hint=("nearest tested variants: " + ", ".join(
                               f"{r.ID} ({r.CHROM}:{r.GENPOS}, -log10P {r.LOG10P:.2f})" for r in near.itertuples()))
                           if len(near) else "no tested variant within 50 kb; check the position and build (hg19?)")
        row = cand.loc[cand["LOG10P"].idxmax()]
    else:
        cand = res[res["ID"] == spec]
        if cand.empty:
            raise SamError(f"variant ID not found in results: {spec}")
        row = cand.iloc[0]
    return {"CHROM": int(row["CHROM"]), "GENPOS": int(row["GENPOS"]), "ID": str(row["ID"]),
            "ALLELE0": row["ALLELE0"], "ALLELE1": row["ALLELE1"], "LOG10P": float(row["LOG10P"]),
            "genome_wide_significant": bool(row["LOG10P"] >= GW_LOG10P), "is_peak_lead": str(row["ID"]) in peak_ids}


def locus_dir(ctx: Context, pheno: str, lead: dict) -> Path:
    return ctx.out("loci", safe_name(pheno), f"chr{lead['CHROM']}_{lead['GENPOS']}", is_dir=True)


def keep_file(ctx: Context, pheno: str, d: Path) -> Path:
    """Samples used in the GWAS (so LD matches the association statistics)."""
    table = ctx.output_dir / "gwas" / safe_name(pheno) / "pheno.tsv"
    ids = pd.read_csv(table, sep="\t", usecols=["FID", "IID"], dtype=str)
    out = d / "samples.keep"
    ids.rename(columns={"FID": "#FID"}).to_csv(out, sep="\t", index=False)
    return out


def setup_geno(ctx: Context, pheno: str) -> dict:
    f = ctx.output_dir / "gwas" / safe_name(pheno) / "setup.json"
    return json.loads(f.read_text())["geno"]


# ── plotting ────────────────────────────────────────────────────────────────
def plot_regional(ctx: Context, region: pd.DataFrame, lead: dict, window: int, title: str, out: Path,
                  cs: pd.DataFrame | None = None, log=None) -> list[str]:
    """region needs GENPOS, LOG10P, ID and R2 (NaN allowed). Returns notes about omitted tracks."""
    notes = []
    start, end = lead["GENPOS"] - window, lead["GENPOS"] + window
    gene_list, note = genes.fetch_genes(ctx, lead["CHROM"], start, end)
    if note:
        notes.append(note)
    rec, note = genes.recombination(ctx, lead["CHROM"], start, end, log=log)
    if note:
        notes.append(note)
    has_genes = bool(gene_list)
    fig = plt.figure(figsize=(10, 7 if has_genes else 5))
    gs = GridSpec(2 if has_genes else 1, 1, height_ratios=[4, 1.3] if has_genes else [1], hspace=0.05)
    ax = fig.add_subplot(gs[0])
    x = region["GENPOS"].values / 1e6
    no_ld = region["R2"].isna().values
    ax.scatter(x[no_ld], region["LOG10P"].values[no_ld], c=NO_LD, s=14, linewidths=0, label="r² n/a", zorder=2)
    for lo, hi, color, label in R2_BINS:
        m = (region["R2"].values >= lo) & (region["R2"].values < hi)
        ax.scatter(x[m], region["LOG10P"].values[m], c=color, s=16, linewidths=0, label=label, zorder=3)
    lead_row = region[region["ID"] == lead["ID"]]
    if not lead_row.empty:
        ax.scatter(lead_row["GENPOS"] / 1e6, lead_row["LOG10P"], marker="D", c="#7f0000", s=60, zorder=5,
                   edgecolors="black", linewidths=0.6, label="lead")
    if cs is not None and not cs.empty:
        for name, grp in cs.groupby("CS"):
            sub = region[region["ID"].isin(grp["ID"])]
            if sub.empty:
                continue
            ax.scatter(sub["GENPOS"] / 1e6, sub["LOG10P"], facecolors="none", edgecolors=CS_COLOR, s=70,
                       linewidths=1.4, zorder=4)
            top = sub.loc[sub["LOG10P"].idxmax()]
            ax.annotate(name, (top["GENPOS"] / 1e6, top["LOG10P"]), xytext=(0, 7), textcoords="offset points",
                        ha="center", fontsize=7, color=CS_COLOR, fontweight="bold")
        ax.scatter([], [], facecolors="none", edgecolors=CS_COLOR, s=70, linewidths=1.4, label="credible set")
    ax.axhline(GW_LOG10P, color="#c0392b", ls="--", lw=0.8)
    ax.set_ylabel("−log₁₀(P)")
    ax.set_xlim(start / 1e6, end / 1e6)
    ax.set_title(title, fontsize=10)
    ax.legend(title="LD with lead", fontsize=7, title_fontsize=7, loc="upper left", ncol=2)
    if rec is not None:
        ax2 = ax.twinx()
        ax2.plot(rec[0], rec[1], color="#1f78b4", lw=0.9, alpha=0.45)
        ax2.set_ylabel("Recombination rate (cM/Mb)", color="#1f78b4", fontsize=8)
        ax2.set_ylim(0, max(float(np.max(rec[1])) * 1.5, 1))
        ax.set_zorder(ax2.get_zorder() + 1)  # association points above the recombination line
        ax.patch.set_visible(False)
    if has_genes:
        ax.tick_params(axis="x", labelbottom=False)
        axg = fig.add_subplot(gs[1], sharex=ax)
        rows: list[list[dict]] = []
        for g in sorted(gene_list, key=lambda g: g["start"]):
            for row in rows:
                if g["start"] > row[-1]["end"] + 0.04 * (end - start):
                    row.append(g)
                    break
            else:
                rows.append([g])
        fs = max(5, 9 - len(rows))
        for i, row in enumerate(rows):
            for g in row:
                axg.plot([g["start"] / 1e6, g["end"] / 1e6], [-i, -i], color="#335c81", lw=4, solid_capstyle="butt")
                mid = (max(g["start"], start) + min(g["end"], end)) / 2e6
                arrow = "→" if g["strand"] == 1 else "←"
                axg.text(mid, -i - 0.35, f"{g['name']} {arrow}", ha="center", va="top", fontsize=fs, style="italic")
        axg.set_ylim(-len(rows) - 0.3, 0.6)
        axg.set_yticks([])
        for s in ("left", "right", "top"):
            axg.spines[s].set_visible(False)
        axg.set_xlabel(f"Chromosome {lead['CHROM']} position (Mb, {ctx.build})")
    else:
        ax.set_xlabel(f"Chromosome {lead['CHROM']} position (Mb, {ctx.build})")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return notes


# ── step ────────────────────────────────────────────────────────────────────
def regional(ctx: Context, pheno: str, locus: str, window_kb: int = 500) -> dict:
    res, _ = load_results(ctx, pheno)
    lead = resolve_locus(ctx, pheno, res, locus)
    window = window_kb * 1000
    run = StepRun(ctx, "regional", f"{pheno}:{lead['CHROM']}:{lead['GENPOS']}",
                  {"locus": locus, "lead": lead["ID"], "window_kb": window_kb}, ["plink2", "python"])
    if not lead["genome_wide_significant"]:
        run.warn(f"lead {lead['ID']} is not genome-wide significant (−log10P {lead['LOG10P']:.2f})")
    d = locus_dir(ctx, pheno, lead)
    geno = setup_geno(ctx, pheno)
    pflag, _ = geno_flags(geno)
    ld_prefix = d / "ld_lead"
    run.run([tool_path(ctx, "plink2"), *pflag, "--keep", keep_file(ctx, pheno, d), "--chr", lead["CHROM"],
             "--from-bp", max(lead["GENPOS"] - window, 1), "--to-bp", lead["GENPOS"] + window,
             "--r2-unphased", "--ld-snp", lead["ID"], "--ld-window", 999999, "--ld-window-kb", window_kb * 2 + 1,
             "--ld-window-r2", 0, "--out", ld_prefix, "--threads", ctx.threads])
    ld = pd.read_csv(f"{ld_prefix}.vcor", sep="\t", dtype={"ID_A": str, "ID_B": str})
    r2 = dict(zip(ld["ID_B"], ld["UNPHASED_R2"]))
    r2[lead["ID"]] = 1.0
    region = res[(res["CHROM"].astype(int) == lead["CHROM"]) &
                 (res["GENPOS"].between(lead["GENPOS"] - window, lead["GENPOS"] + window))].copy()
    region["R2"] = region["ID"].map(r2)
    cs = None
    cs_file = d / "susie_cs.tsv"
    if cs_file.exists():
        cs = pd.read_csv(cs_file, sep="\t", dtype={"ID": str})
    out = d / "regional.png"
    notes = plot_regional(ctx, region, lead, window,
                          f"{pheno}  {lead['ID']}  chr{lead['CHROM']}:{lead['GENPOS']} ±{window_kb} kb", out, cs,
                          log=run.log)
    for n in notes:
        run.warn(n)
    summary = {"lead": lead, "window_kb": window_kb, "n_variants_in_window": int(len(region)),
               "n_variants_r2_ge_0.8": int((region["R2"] >= 0.8).sum()),
               "n_variants_without_ld": int(region["R2"].isna().sum()),
               "credible_sets_overlaid": cs is not None and not cs.empty}
    return run.finish(summary, {"plot": out, "ld": Path(f"{ld_prefix}.vcor")}, [], ["finemap"],
                      d / "regional_summary.json")
