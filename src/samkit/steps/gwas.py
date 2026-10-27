"""GWAS with regenie: genotype/sample QC, pruning, PCA, phenotype table, step 1, step 2.

Layout (all under the output directory):
  genotype/<name>.{pgen,pvar,psam}         only when the input was a VCF
  gwas/_qc/<geno>/                         QC lists, pruning sets, PCA (shared by phenotypes)
  gwas/<pheno>/pheno.tsv                   FID IID covariates PCs phenotype (individual-level)
  gwas/<pheno>/step1/, step2/              regenie outputs
  gwas/<pheno>/results.tsv.gz              standardized step-2 results (summary-level)
  gwas/<pheno>/summary.json
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from samkit import inventory
from samkit.context import Context, SamError
from samkit.io import (
    GW_LOG10P,
    chrom_key,
    count_lines,
    df_to_records,
    header_line,
    lambda_gc_from_log10p,
    open_text,
    parse_chroms,
    read_regenie,
    read_table,
    safe_name,
    with_ext,
    write_tsv,
)
from samkit.steps import StepRun
from samkit.tools import tool_path

MISSING_TOKENS = ["", "NA", "NaN", "nan", ".", "-9"]

DEFAULTS = {
    "sample_mind": 0.05,                       # sample missingness filter
    # --hwe "<p> <k>": threshold p*10^(-n*k). k=0 (fixed) is deliberate for the model-fitting/PCA sets;
    # the tested variants use plink2's sample-size-aware form, which removes only gross failures
    # (on arrays both het excess and het deficit flag genotyping errors).
    "step1": {"maf": 0.01, "geno": 0.01, "hwe": "1e-6 0", "prune": "1000 100 0.9"},
    "pca": {"maf": 0.05, "geno": 0.01, "hwe": "1e-6 0", "prune": "50 5 0.2", "n_pc": 10,
            "exclude": [(6, 25_000_000, 34_000_000, "MHC")]},
    "step2": {"geno": 0.05, "hwe": "1e-5 0.001 midp", "mac": 20},
    "bsize1": 1000, "bsize2": 400,
}


# ── genotype helpers ────────────────────────────────────────────────────────
def geno_flags(geno: dict) -> tuple[list[str], list[str]]:
    """(plink2 flag, regenie flag) for a fileset."""
    prefix = geno["prefix"]
    if geno["format"] == "bfile":
        return ["--bfile", prefix], ["--bed", prefix]
    return ["--pfile", prefix], ["--pgen", prefix]


def read_samples(geno: dict) -> pd.DataFrame:
    """FID/IID of the genotype fileset (fam or psam)."""
    prefix = Path(geno["prefix"])
    if geno["format"] == "bfile":
        fam = pd.read_csv(with_ext(prefix, ".fam"), sep=r"\s+", header=None, dtype=str, usecols=[0, 1])
        fam.columns = ["FID", "IID"]
        return fam
    psam = pd.read_csv(with_ext(prefix, ".psam"), sep="\t", dtype=str)
    psam.columns = [c.lstrip("#") for c in psam.columns]
    if "FID" not in psam.columns:
        psam["FID"] = psam["IID"]
    return psam[["FID", "IID"]]


def convert_vcf(ctx: Context, vcf: Path, min_r2: float | None) -> dict:
    """VCF -> pgen in output/genotype (dosages kept; FID = IID)."""
    name = safe_name(re.sub(r"\.(vcf\.gz|vcf|bcf)$", "", vcf.name))
    existing = [g for g in inventory.genotype_sets(ctx) if g["name"] == name and g["format"] in ("bfile", "pfile")]
    if existing:
        warnings = []
        stamp = ctx.output_dir / "genotype" / f"{name}.conversion.json"
        if existing[0]["location"] == "output" and stamp.exists():
            old = json.loads(stamp.read_text())
            if old.get("min_r2") != min_r2:
                warnings.append(f"existing conversion of {vcf.name} used R2 >= {old.get('min_r2')}, not {min_r2}; "
                                f"delete output/genotype/{name}.* to convert again")
        return {"skipped": True, "reason": f"PLINK fileset '{name}' already exists", "geno": existing[0],
                "warnings": warnings}
    head = []
    with open_text(vcf) as fh:
        for line in fh:
            if not line.startswith("##"):
                break
            head.append(line)
    has_ds = any(line.startswith("##FORMAT=<ID=DS,") for line in head)
    has_r2 = any(line.startswith("##INFO=<ID=R2,") for line in head)
    out_prefix = ctx.out("genotype", name)
    run = StepRun(ctx, "vcf-to-pgen", name, {"vcf": str(vcf), "min_r2": min_r2}, ["plink2"])
    # biallelic only: multiallelic sites crash regenie; duplicate IDs break --extract/--score
    cmd = [tool_path(ctx, "plink2"), "--vcf", vcf] + (["dosage=DS"] if has_ds else []) + [
        "--double-id", "--set-missing-var-ids", "@:#:$r:$a", "--new-id-max-allele-len", "50", "truncate",
        "--max-alleles", "2", "--rm-dup", "exclude-all"]
    if min_r2 is not None and has_r2:
        cmd += ["--extract-if-info", f"R2>={min_r2}"]
    elif min_r2 is not None:
        run.warn("VCF has no INFO/R2 field; no imputation-quality filter applied")
    cmd += ["--make-pgen", "--out", out_prefix, "--threads", ctx.threads]
    run.run(cmd)
    geno = {"name": name, "format": "pfile", "prefix": str(out_prefix), "location": "output",
            "variants": inventory.count_variants(with_ext(out_prefix, ".pvar"))}
    with_ext(out_prefix, ".conversion.json").write_text(json.dumps({"vcf": str(vcf), "min_r2": min_r2}))
    res = run.finish({"dosage": has_ds, "r2_filter": min_r2 if has_r2 else None, **geno},
                     {"pgen": with_ext(out_prefix, ".pgen")}, [vcf])
    return {"skipped": False, "geno": geno, "warnings": res["warnings"]}


# ── QC shared by all phenotypes of one fileset ──────────────────────────────
def qc_dir(ctx: Context, geno: dict) -> Path:
    return ctx.out("gwas", "_qc", safe_name(geno["name"]), is_dir=True)


def ensure_qc(ctx: Context, run: StepRun, geno: dict, params: dict) -> dict:
    """Sample QC, step-1 pruning set, PCA pruning set + PCA, step-2 variant list.

    Each artifact is reused when it exists and was made with the same settings.
    """
    d = qc_dir(ctx, geno)
    pflag, _ = geno_flags(geno)
    plink2 = tool_path(ctx, "plink2")
    stamp_path = d / "qc_settings.json"
    stamp = json.loads(stamp_path.read_text()) if stamp_path.exists() else {}
    settings = {"sample_mind": params["sample_mind"], "step1": params["step1"], "pca": params["pca"],
                "step2": params["step2"], "geno_prefix": geno["prefix"]}
    if stamp != settings:
        for f in d.iterdir():
            if f.is_file():
                f.unlink()
    out: dict[str, Path] = {}

    keep = d / "samples_qc.id"
    if not keep.exists():
        run.log.info("sample QC (missingness)")
        run.run([plink2, *pflag, "--mind", params["sample_mind"], "--write-samples", "--out", d / "samples_qc",
                 "--threads", ctx.threads])
    out["samples"] = keep

    s1 = params["step1"]
    prune1 = d / "step1.prune.in"
    if not prune1.exists():
        run.log.info("step-1 variant set (QC + LD pruning)")
        run.run([plink2, *pflag, "--keep", keep, "--maf", s1["maf"], "--geno", s1["geno"], "--hwe", *s1["hwe"].split(),
                 "--indep-pairwise", *s1["prune"].split(), "--out", d / "step1", "--threads", ctx.threads])
    out["step1_variants"] = prune1

    pca = params["pca"]
    eigenvec = d / "pca.eigenvec"
    if not eigenvec.exists():
        run.log.info("PCA (separate, stricter pruning; MHC excluded)")
        bed = d / "pca_exclude.bed"
        bed.write_text("".join(f"{c}\t{a}\t{b}\t{n}\n" for c, a, b, n in pca["exclude"]))
        run.run([plink2, *pflag, "--keep", keep, "--autosome", "--exclude", "bed1", bed, "--maf", pca["maf"],
                 "--geno", pca["geno"], "--hwe", *pca["hwe"].split(), "--indep-pairwise", *pca["prune"].split(),
                 "--out", d / "pca_prune", "--threads", ctx.threads])
        n_samples = count_lines(keep)
        run.run([plink2, *pflag, "--keep", keep, "--extract", d / "pca_prune.prune.in", "--pca", pca["n_pc"],
                 *(["approx"] if n_samples > 50000 else []), "--out", d / "pca", "--threads", ctx.threads])
    out["pca"] = eigenvec

    s2 = params["step2"]
    snplist = d / "step2.snplist"
    if not snplist.exists():
        run.log.info("step-2 variant QC")
        run.run([plink2, *pflag, "--keep", keep, "--geno", s2["geno"], "--hwe", *s2["hwe"].split(),
                 "--mac", s2["mac"], "--write-snplist", "--out", d / "step2", "--threads", ctx.threads])
    out["step2_variants"] = snplist

    stamp_path.write_text(json.dumps(settings, indent=2))
    return {
        "files": out,
        "n_samples_qc": count_lines(keep) - 1 if header_line(keep).startswith("#") else count_lines(keep),
        "n_step1_variants": count_lines(prune1),
        "n_pca_variants": count_lines(d / "pca_prune.prune.in"),
        "n_step2_variants": count_lines(snplist),
    }


# ── phenotype table ─────────────────────────────────────────────────────────
def _id_columns(cols: list[str]) -> tuple[str | None, str]:
    up = {c.upper().lstrip("#"): c for c in cols}
    if "FID" in up and "IID" in up:
        return up["FID"], up["IID"]
    for k in ("IID", "ID", "SAMPLE", "SAMPLE_ID"):
        if k in up:
            return None, up[k]
    raise SamError("phenotype file has no ID column", hint="expected FID+IID, IID, or ID")


def resolve_columns(columns: list[str], pheno_file: str, pheno: str,
                    covars: list[str] | None) -> tuple[str | None, str, list[str], list[str]]:
    """Check the header before any computation. Returns (FID col, IID col, covariates, notes)."""
    fid_col, iid_col = _id_columns(columns)
    notes: list[str] = []
    if pheno not in columns:
        raise SamError(f"phenotype column '{pheno}' not in {pheno_file}",
                       hint="columns: " + ", ".join(c for c in columns if c not in (fid_col, iid_col)))
    if covars is None:
        by_upper = {c.upper(): c for c in columns}
        covars = [by_upper[k] for k in ("AGE", "SEX") if k in by_upper]
        if not covars:
            notes.append("no AGE/SEX columns found; only principal components are used as covariates")
    pcs = [c for c in covars if re.fullmatch(r"PC\d+", c, flags=re.I)]
    if pcs:
        covars = [c for c in covars if c not in pcs]
        notes.append(f"PC columns {pcs} from the phenotype file are ignored: the harness computes PCs itself "
                     "(set n_pc to choose how many)")
    missing_cov = [c for c in covars if c not in columns]
    if missing_cov:
        raise SamError(f"covariate column(s) not in phenotype file: {missing_cov}",
                       hint="columns: " + ", ".join(columns))
    if pheno in covars:
        raise SamError(f"'{pheno}' is both the phenotype and a covariate")
    return fid_col, iid_col, covars, notes


def build_pheno_table(ctx: Context, run: StepRun, geno: dict, pheno_file: Path, pheno: str, trait: str | None,
                      covars: list[str] | None, n_pc_covar: int, eigenvec: Path, keep: Path,
                      out_path: Path) -> dict:
    df = read_table(pheno_file, dtype=str, keep_default_na=False)
    fid_col, iid_col, covars, notes = resolve_columns(list(df.columns), pheno_file.name, pheno, covars)
    for n in notes:
        run.warn(n)
    n_rows = len(df)
    if df[iid_col].duplicated().any() and fid_col is None:
        raise SamError(f"duplicate IDs in {pheno_file.name} column {iid_col}")

    samples = read_samples(geno)
    kept = pd.read_csv(keep, sep=r"\s+", dtype=str)
    kept.columns = [c.lstrip("#") for c in kept.columns]
    if "FID" not in kept.columns:
        kept["FID"] = kept["IID"]
    samples_qc = samples.merge(kept[["FID", "IID"]], on=["FID", "IID"])

    sub = df[[c for c in [fid_col, iid_col] if c] + covars + [pheno]].copy()
    sub = sub.replace(MISSING_TOKENS, np.nan)
    iid_unique = not samples_qc["IID"].duplicated().any()
    if fid_col:
        sub = sub.rename(columns={fid_col: "FID", iid_col: "IID"})
        merged = samples_qc.merge(sub, on=["FID", "IID"], how="inner")
        if len(merged) == 0 and iid_unique and not sub["IID"].duplicated().any():
            merged = samples_qc.merge(sub.drop(columns="FID"), on="IID", how="inner")
            if len(merged):
                run.warn("FID values differ between the phenotype file and the genotype file; matched on IID only")
    else:
        if not iid_unique:
            raise SamError("genotype IIDs are not unique; phenotype file needs FID and IID columns")
        sub = sub.rename(columns={iid_col: "IID"})
        merged = samples_qc.merge(sub, on="IID", how="inner")
    n_matched = len(merged)
    if n_matched == 0:
        raise SamError(f"no sample of {pheno_file.name} matches the genotype samples",
                       hint=f"phenotype IDs come from column(s) {[c for c in (fid_col, iid_col) if c]}; "
                            "check that they use the same IDs as the .fam/.psam")

    nonnumeric = {}
    for c in covars + [pheno]:
        vals = pd.to_numeric(merged[c], errors="coerce")
        bad = int(vals.isna().sum() - merged[c].isna().sum())
        if bad:
            nonnumeric[c] = bad
        merged[c] = vals
    if nonnumeric:
        run.warn(f"non-numeric values treated as missing: {nonnumeric}")

    y = merged[pheno].dropna()
    values = set(np.unique(y.values)) if len(y) else set()
    if trait is None:
        trait = "bt" if values and values <= {0.0, 1.0} or values == {1.0, 2.0} else "qt"
    recoded = False
    if trait == "bt":
        if values == {1.0, 2.0} or values <= {1.0, 2.0} and 2.0 in values:
            merged[pheno] = merged[pheno].map({1.0: 0.0, 2.0: 1.0})
            recoded = True
        elif not values <= {0.0, 1.0}:
            raise SamError(f"binary trait '{pheno}' has values other than 0/1 (or 1/2)",
                           hint=f"{len(values)} distinct values; use trait 'qt' or recode the column")

    pcs = pd.read_csv(eigenvec, sep=r"\s+", dtype=str)
    pcs.columns = [c.lstrip("#") for c in pcs.columns]
    if "FID" not in pcs.columns:
        pcs["FID"] = pcs["IID"]
    pc_cols = [f"PC{i}" for i in range(1, n_pc_covar + 1)]
    merged = merged.merge(pcs[["FID", "IID"] + pc_cols], on=["FID", "IID"], how="left")
    for c in pc_cols:
        merged[c] = pd.to_numeric(merged[c])

    covar_all = covars + pc_cols
    complete = merged.dropna(subset=covar_all + [pheno])
    table = complete[["FID", "IID"] + covar_all + [pheno]]
    if len(table) < 50:
        raise SamError(f"only {len(table)} samples have complete phenotype and covariate data",
                       hint=f"{n_matched} matched the genotypes; check missing values in {pheno} and {covars}")
    write_tsv(table, out_path)

    summ = {
        "phenotype_file": pheno_file.name,
        "phenotype": pheno,
        "trait": trait,
        "recoded_1_2_to_0_1": recoded,
        "covariates": covar_all,
        "n_rows_in_phenotype_file": n_rows,
        "n_genotyped": len(samples),
        "n_genotyped_after_sample_qc": len(samples_qc),
        "n_matched": n_matched,
        "n_analysed": len(table),
        "n_dropped_missing": n_matched - len(table),
    }
    if trait == "qt":
        yy = table[pheno]
        q = yy.quantile([0.01, 0.5, 0.99])
        # quantiles, not min/max: an extreme value is one person's measurement
        summ["phenotype_distribution"] = {"mean": round(float(yy.mean()), 4), "sd": round(float(yy.std()), 4),
                                          "p01": round(float(q[0.01]), 4), "median": round(float(q[0.5]), 4),
                                          "p99": round(float(q[0.99]), 4)}
    else:
        summ["cases"] = int((table[pheno] == 1).sum())
        summ["controls"] = int((table[pheno] == 0).sum())
        if summ["cases"] < 100:
            run.warn(f"only {summ['cases']} cases; binary-trait results will be unstable")
    if len(table) < 0.5 * len(samples_qc):
        run.warn(f"only {len(table)} of {len(samples_qc)} genotyped samples have complete phenotype data")
    return summ


# ── public steps ────────────────────────────────────────────────────────────
def pheno_dir(ctx: Context, pheno: str) -> Path:
    return ctx.out("gwas", safe_name(pheno), is_dir=True)


def fingerprint(table: Path, settings: dict) -> str:
    """Identity of an analysis setup: the exact phenotype/covariate table plus settings."""
    h = hashlib.sha256(table.read_bytes())
    h.update(json.dumps(settings, sort_keys=True, default=str).encode())
    return h.hexdigest()[:16]


def invalidate(ctx: Context, pheno: str, *, step1_too: bool) -> list[str]:
    """Remove results derived from an older setup so they can never be mixed with new ones."""
    tag = safe_name(pheno)
    targets = [ctx.output_dir / "gwas" / tag / n for n in ("step2", "results.tsv.gz", "summary.json")]
    if step1_too:
        targets.append(ctx.output_dir / "gwas" / tag / "step1")
    targets += [ctx.output_dir / sub / tag for sub in ("plots", "ldsc", "loci")]
    removed = []
    for t in targets:
        if t.is_dir():
            shutil.rmtree(t)
            removed.append(str(t.relative_to(ctx.output_dir)))
        elif t.exists():
            t.unlink()
            removed.append(str(t.relative_to(ctx.output_dir)))
    return removed


def prepare(ctx: Context, geno_name: str | None, pheno_file: str, pheno: str, trait: str | None,
            covars: list[str] | None, n_pc_covar: int = 4, vcf: str | None = None,
            min_r2: float | None = 0.8, overrides: dict | None = None) -> dict:
    params = json.loads(json.dumps(DEFAULTS))
    for k, v in (overrides or {}).items():
        if isinstance(v, dict):
            params[k].update(v)
        else:
            params[k] = v
    if n_pc_covar > params["pca"]["n_pc"]:
        raise SamError(f"n_pc_covar={n_pc_covar} exceeds computed PCs ({params['pca']['n_pc']})")
    pfile = ctx.input_path(pheno_file)
    resolve_columns(read_table(pfile, nrows=0).columns.tolist(), pfile.name, pheno, covars)  # fail before QC
    conversion = None
    if vcf:
        conversion = convert_vcf(ctx, ctx.input_path(vcf), min_r2)
        geno_name = conversion["geno"]["name"]
    geno = inventory.resolve_genotype(ctx, geno_name)
    run = StepRun(ctx, "gwas-prepare", pheno,
                  {"geno": geno["name"], "pheno_file": pfile.name, "pheno": pheno, "trait": trait,
                   "covars": covars, "n_pc_covar": n_pc_covar, **params}, ["plink2", "python"])
    for w in (conversion or {}).get("warnings", []):
        run.warn(w)
    qc = ensure_qc(ctx, run, geno, params)
    d = pheno_dir(ctx, pheno)
    table = d / "pheno.tsv"
    ph = build_pheno_table(ctx, run, geno, pfile, pheno, trait, covars, n_pc_covar, qc["files"]["pca"],
                           qc["files"]["samples"], table)
    fp = fingerprint(table, {"geno": geno["prefix"], "trait": ph["trait"], "covariates": ph["covariates"],
                             "qc": json.loads((qc_dir(ctx, geno) / "qc_settings.json").read_text())})
    setup_file = d / "setup.json"
    old_fp = json.loads(setup_file.read_text()).get("fingerprint") if setup_file.exists() else None
    if old_fp != fp:
        removed = invalidate(ctx, pheno, step1_too=True)
        if removed and old_fp is not None:
            run.warn(f"setup changed; removed results of the previous setup: {', '.join(removed)}")
    setup_file.write_text(json.dumps({"geno": geno, "pheno": ph, "fingerprint": fp,
                                      "qc": {k: str(v) for k, v in qc["files"].items()}}, indent=2))
    summary = {"genotype": {k: geno[k] for k in ("name", "format", "variants", "samples") if k in geno},
               "qc": {k: v for k, v in qc.items() if k != "files"}, "phenotype": ph, "setup_fingerprint": fp}
    if conversion:
        summary["vcf_conversion"] = {k: v for k, v in conversion.items() if k != "warnings"}
    return run.finish(summary, {"pheno_table": table, "pca": qc["files"]["pca"]}, [pfile],
                      ["gwas-step1"], d / "prepare.json")


def _load_setup(ctx: Context, pheno: str) -> dict:
    f = ctx.output_dir / "gwas" / safe_name(pheno) / "setup.json"
    if not f.exists():
        raise SamError(f"phenotype '{pheno}' is not prepared", hint="run gwas-prepare first (sam_gwas stage=prepare)")
    return json.loads(f.read_text())


def step1(ctx: Context, pheno: str) -> dict:
    setup = _load_setup(ctx, pheno)
    geno, ph, qc = setup["geno"], setup["pheno"], setup["qc"]
    d = pheno_dir(ctx, pheno)
    _, rflag = geno_flags(geno)
    run = StepRun(ctx, "gwas-step1", pheno, {"trait": ph["trait"], "covariates": ph["covariates"],
                                            "bsize": DEFAULTS["bsize1"]}, ["regenie"])
    s1 = ctx.out("gwas", safe_name(pheno), "step1", is_dir=True)
    for f in s1.glob("*"):
        f.unlink()
    run.run([tool_path(ctx, "regenie"), "--step", "1", *rflag, "--extract", qc["step1_variants"],
             "--phenoFile", d / "pheno.tsv", "--phenoColList", pheno,
             "--covarFile", d / "pheno.tsv", "--covarColList", ",".join(ph["covariates"]),
             f"--{ph['trait']}", "--bsize", DEFAULTS["bsize1"], "--lowmem",
             "--lowmem-prefix", s1 / f"tmp_{safe_name(pheno)}", "--out", s1 / safe_name(pheno),
             "--threads", ctx.threads], quiet_patterns=(r"block \[\d+\]", r"^\s*$"))
    pred = s1 / f"{safe_name(pheno)}_pred.list"
    if not pred.exists():
        raise SamError("regenie step 1 did not produce a prediction list", hint=f"see {run.log.path}")
    (s1 / "fingerprint").write_text(setup.get("fingerprint", ""))
    invalidate(ctx, pheno, step1_too=False)  # step-2 results of older predictions are no longer valid
    return run.finish({"n_analysed": ph["n_analysed"], "trait": ph["trait"]}, {"pred_list": pred},
                      [d / "pheno.tsv"], ["gwas-step2"])


def step2(ctx: Context, pheno: str, chroms: str | None = None) -> dict:
    setup = _load_setup(ctx, pheno)
    geno, ph, qc = setup["geno"], setup["pheno"], setup["qc"]
    d = pheno_dir(ctx, pheno)
    pred = d / "step1" / f"{safe_name(pheno)}_pred.list"
    if not pred.exists():
        raise SamError("regenie step 1 has not been run for this phenotype", hint="run gwas-step1 first")
    fp_file = d / "step1" / "fingerprint"
    if not fp_file.exists() or fp_file.read_text() != setup.get("fingerprint", ""):
        raise SamError("regenie step 1 predictions belong to an older setup of this phenotype",
                       hint="run gwas-step1 again (or stage=all)")
    chrom_list = parse_chroms(chroms)
    _, rflag = geno_flags(geno)
    trait_flags = ["--qt"] if ph["trait"] == "qt" else ["--bt", "--firth", "--approx", "--pThresh", "0.01"]
    chr_flags: list[str] = []
    if chrom_list and len(chrom_list) == 1:
        chr_flags = ["--chr", str(chrom_list[0])]
    elif chrom_list:
        chr_flags = ["--chrList", ",".join(map(str, chrom_list))]
    run = StepRun(ctx, "gwas-step2", pheno, {"trait": ph["trait"], "chromosomes": chrom_list or "all",
                                            "bsize": DEFAULTS["bsize2"], "trait_flags": trait_flags},
                  ["regenie", "python"])
    invalidate(ctx, pheno, step1_too=False)
    s2 = ctx.out("gwas", safe_name(pheno), "step2", is_dir=True)
    run.run([tool_path(ctx, "regenie"), "--step", "2", *rflag, "--extract", qc["step2_variants"],
             "--phenoFile", d / "pheno.tsv", "--phenoColList", pheno,
             "--covarFile", d / "pheno.tsv", "--covarColList", ",".join(ph["covariates"]),
             *trait_flags, "--pred", pred, "--bsize", DEFAULTS["bsize2"], *chr_flags, "--gz",
             "--out", s2 / safe_name(pheno), "--threads", ctx.threads],
            quiet_patterns=(r"block \[\d+\]", r"^\s*$"))
    raw = s2 / f"{safe_name(pheno)}_{pheno}.regenie.gz"
    if not raw.exists():
        cands = list(s2.glob("*.regenie.gz"))
        if not cands:
            raise SamError("regenie step 2 produced no result file", hint=f"see {run.log.path}")
        raw = cands[0]
    res = read_regenie(raw)
    n_total = count_lines(raw) - 1
    cols = ["CHROM", "GENPOS", "ID", "ALLELE0", "ALLELE1", "A1FREQ", "N", "BETA", "SE", "CHISQ", "LOG10P"]
    res = res[cols].sort_values(["CHROM", "GENPOS"], key=lambda s: s.map(chrom_key) if s.name == "CHROM" else s)
    results = d / "results.tsv.gz"
    write_tsv(res, results, compression="gzip")
    summary = summarize_results(res, n_total)
    summary["trait"] = ph["trait"]
    summary["setup_fingerprint"] = setup.get("fingerprint")
    if not summary["complete_autosomes"]:
        run.warn(f"results cover chromosomes {summary['chromosomes']} only; LDSC needs all autosomes")
    return run.finish(summary, {"results": results, "regenie_raw": raw}, [d / "pheno.tsv"],
                      ["plots", "peaks", "ldsc"], d / "summary.json")


def summarize_results(res: pd.DataFrame, n_total: int | None = None) -> dict:
    chroms = sorted({int(c) for c in res["CHROM"].unique() if str(c).isdigit()})
    sig = res[res["LOG10P"] >= GW_LOG10P]
    top = res.nlargest(10, "LOG10P")[["CHROM", "GENPOS", "ID", "ALLELE0", "ALLELE1", "A1FREQ", "BETA", "SE", "LOG10P"]]
    loci = distance_loci(sig, 500_000)
    return {
        "n_variants_tested": int(len(res)),
        "n_failed_tests": int(n_total - len(res)) if n_total is not None else None,
        "n_samples_median": int(np.median(res["N"])) if len(res) else 0,
        "lambda_gc": round(lambda_gc_from_log10p(res["LOG10P"].values), 4) if len(res) else None,
        "n_genome_wide_significant": int(len(sig)),
        "n_independent_loci_500kb": len(loci),
        "chromosomes": chroms,
        "complete_autosomes": set(range(1, 23)) <= set(chroms),
        "top_hits": df_to_records(top),
    }


def distance_loci(sig: pd.DataFrame, window: int) -> list[dict]:
    """Greedy distance clumping: strongest variant first, absorb others within ±window."""
    loci: list[dict] = []
    if sig.empty:
        return loci
    rest = sig.sort_values("LOG10P", ascending=False)
    taken = np.zeros(len(rest), dtype=bool)
    chrom = rest["CHROM"].astype(str).values
    pos = rest["GENPOS"].values
    for i in range(len(rest)):
        if taken[i]:
            continue
        near = (chrom == chrom[i]) & (np.abs(pos - pos[i]) <= window) & ~taken
        taken |= near
        row = rest.iloc[i]
        loci.append({"CHROM": row["CHROM"], "GENPOS": int(row["GENPOS"]), "ID": row["ID"],
                     "ALLELE0": row["ALLELE0"], "ALLELE1": row["ALLELE1"], "BETA": row["BETA"], "SE": row["SE"],
                     "LOG10P": row["LOG10P"], "n_significant_in_locus": int(near.sum()),
                     "start": int(pos[near].min()), "end": int(pos[near].max())})
    return loci


def load_results(ctx: Context, pheno: str) -> tuple[pd.DataFrame, dict]:
    d = ctx.output_dir / "gwas" / safe_name(pheno)
    f = d / "results.tsv.gz"
    if not f.exists():
        raise SamError(f"no GWAS results for '{pheno}'", hint="run the GWAS (gwas-step2) first")
    summ = json.loads((d / "summary.json").read_text()) if (d / "summary.json").exists() else {}
    setup = json.loads((d / "setup.json").read_text()) if (d / "setup.json").exists() else {}
    made_with = summ.get("summary", {}).get("setup_fingerprint")
    if made_with and setup.get("fingerprint") and made_with != setup["fingerprint"]:
        raise SamError(f"GWAS results for '{pheno}' come from an older setup", hint="rerun gwas-step1 and gwas-step2")
    res = pd.read_csv(f, sep="\t", dtype={"ID": str, "ALLELE0": str, "ALLELE1": str}, na_values=["NA"])
    return res, summ
