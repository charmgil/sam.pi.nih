"""What is in the input directory, described without exposing individual values.

Phenotype tables are reported by column names and row counts only.
"""

from __future__ import annotations

import re
from pathlib import Path

from samkit.context import Context, SamError
from samkit.io import count_lines, header_line, sniff_sep, with_ext

GENO_SETS = {
    "bfile": (".bed", ".bim", ".fam"),
    "pfile": (".pgen", ".pvar", ".psam"),
}
ID_COLUMNS = ("FID", "IID", "ID", "#FID", "#IID", "SAMPLE", "SAMPLE_ID")
PHEWEB_COLS = {"chrom", "pos", "ref", "alt", "pval", "beta"}
TABLE_SUFFIXES = (".txt", ".tsv", ".csv", ".txt.gz", ".tsv.gz", ".csv.gz")


def _files(root: Path, depth: int = 2):
    for p in sorted(root.iterdir()):
        if p.name.startswith("."):
            continue
        if p.is_file():
            yield p
        elif p.is_dir() and depth > 1:
            yield from _files(p, depth - 1)


def count_variants(pvar_or_bim: Path) -> int:
    """Variant records (pvar header and ## meta lines excluded)."""
    n = 0
    with open(pvar_or_bim, "rb") as fh:
        for line in fh:
            if not line.startswith(b"#"):
                n += 1
    return n


def genotype_sets(ctx: Context) -> list[dict]:
    """PLINK filesets and VCF/BGEN files in the input directory (and converted ones in output)."""
    found: list[dict] = []
    roots = [ctx.input_dir, ctx.output_dir / "genotype"]
    for root in roots:
        if not root.is_dir():
            continue
        for p in _files(root):
            for fmt, exts in GENO_SETS.items():
                if p.name.endswith(exts[0]):
                    prefix = Path(str(p)[: -len(exts[0])])
                    if all(with_ext(prefix, e).exists() for e in exts):
                        n_var = count_variants(with_ext(prefix, exts[1]))
                        n_sam = count_variants(with_ext(prefix, exts[2]))
                        found.append({"name": prefix.name, "format": fmt, "prefix": str(prefix),
                                      "variants": n_var, "samples": n_sam,
                                      "location": "input" if root == ctx.input_dir else "output"})
            if re.search(r"\.(vcf|vcf\.gz|bcf|bgen)$", p.name):
                found.append({"name": re.sub(r"\.(vcf\.gz|vcf|bcf|bgen)$", "", p.name),
                              "format": "vcf" if "vcf" in p.name or p.name.endswith(".bcf") else "bgen",
                              "path": str(p), "size_gb": round(p.stat().st_size / 1e9, 2),
                              "location": "input" if root == ctx.input_dir else "output"})
    return found


def classify_table(path: Path) -> dict | None:
    try:
        head = header_line(path)
    except (OSError, UnicodeError, EOFError):
        return None
    if not head:
        return None
    sep = sniff_sep(head)
    cols = [c for c in re.split(sep, head.strip())]
    lower = {c.lower() for c in cols}
    info: dict = {"name": path.name, "path": str(path), "size_mb": round(path.stat().st_size / 1e6, 1)}
    looks_like_data = any(_is_number(c) for c in cols)
    if PHEWEB_COLS <= lower:
        info.update(kind="sumstats", format="pheweb", columns=cols)
        return info
    if {"snp", "a1", "a2"} <= lower and ({"beta", "or"} & lower) and ({"p", "se"} & lower):
        info.update(kind="sumstats", format="generic", columns=cols)
        return info
    # headerless PRS weight: CHR SNP BP A1 A2 BETA
    if len(cols) == 6 and cols[0].isdigit() and cols[1].startswith("rs") and cols[2].isdigit():
        info.update(kind="prs_weight", format="CHR SNP BP A1 A2 BETA (no header)")
        return info
    if {"snp", "a1"} <= lower and ({"beta", "weight", "effect_weight"} & lower):
        info.update(kind="prs_weight", format="header", columns=cols)
        return info
    if len(cols) == 2 and ("rs" in head.lower() or "dbsnp" in head.lower()):
        info.update(kind="id_map", columns=cols)
        return info
    if any(c.upper() in ID_COLUMNS for c in cols):
        info.update(kind="phenotype", columns=cols, rows=max(count_lines(path) - 1, 0),
                    individual_level=True)
        return info
    if looks_like_data:
        # no header line: the first line is data and may be one person's record, so it is not shown
        return {**info, "kind": "other", "columns": None, "n_columns": len(cols),
                "note": "no header line detected; contents not shown"}
    return {**info, "kind": "other", "columns": cols[:20]}


def _is_number(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


def scan_input(ctx: Context) -> dict:
    tables, other = [], []
    for p in _files(ctx.input_dir):
        if p.name.endswith((".bed", ".bim", ".fam", ".pgen", ".pvar", ".psam", ".log", ".bgen",
                            ".vcf", ".vcf.gz", ".bcf", ".tbi", ".csi")):
            continue
        if p.name.endswith(TABLE_SUFFIXES):
            info = classify_table(p)
            if info:
                tables.append(info)
                continue
        other.append({"name": p.name, "size_mb": round(p.stat().st_size / 1e6, 1)})
    downloads = ctx.output_dir / "downloads"
    if downloads.is_dir():
        for p in _files(downloads, depth=3):
            if p.name.endswith(TABLE_SUFFIXES):
                info = classify_table(p)
                if info:
                    tables.append({**info, "location": "output/downloads"})
    return {
        "input_dir": str(ctx.input_dir),
        "genotypes": genotype_sets(ctx),
        "tables": tables,
        "other_files": other,
    }


def resolve_genotype(ctx: Context, name: str | None) -> dict:
    sets = [g for g in genotype_sets(ctx) if g["format"] in ("bfile", "pfile")]
    if name:
        match = [g for g in sets if g["name"] == name or g.get("prefix") == name]
        if not match:
            raise SamError(f"genotype fileset not found: {name}",
                           hint="available: " + ", ".join(g["name"] for g in sets) if sets else
                           "no PLINK filesets; convert a VCF first (sam_gwas stage=prepare with vcf=..., "
                           "or ./sam run gwas prepare --vcf ...)")
        return match[0]
    if len(sets) == 1:
        return sets[0]
    raise SamError("several genotype filesets found; specify one with --geno",
                   hint="available: " + ", ".join(g["name"] for g in sets) if sets else "none found")
