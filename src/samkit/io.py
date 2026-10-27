"""Small file helpers shared by steps (tables, regenie results, statistics)."""

from __future__ import annotations

import gzip
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

GW_LOG10P = -np.log10(5e-8)  # 7.30103
CHISQ_MEDIAN_1DF = stats.chi2.ppf(0.5, 1)  # 0.454936


def with_ext(prefix, ext: str) -> Path:
    """prefix + extension; Path.with_suffix would cut names such as 'KBAv2.0AB_14K'."""
    return Path(f"{prefix}{ext}")


def open_text(path: Path):
    return gzip.open(path, "rt", encoding="utf-8", errors="replace") if str(path).endswith(".gz") \
        else open(path, encoding="utf-8", errors="replace")


def header_line(path: Path) -> str:
    with open_text(path) as fh:
        return fh.readline().rstrip("\n\r")


def sniff_sep(line: str) -> str:
    if "\t" in line:
        return "\t"
    if "," in line and " " not in line.strip():
        return ","
    return r"\s+"


def read_table(path: Path, **kw) -> pd.DataFrame:
    return pd.read_csv(path, sep=sniff_sep(header_line(path)), **kw)


def write_tsv(df: pd.DataFrame, path: Path, **kw) -> None:
    """Tab-separated with explicit NA so whitespace-splitting readers keep columns aligned."""
    df.to_csv(path, sep="\t", index=False, na_rep="NA", **kw)


def chrom_key(c) -> int:
    s = str(c).upper().removeprefix("CHR")
    return {"X": 23, "Y": 24, "XY": 25, "MT": 26, "M": 26}.get(s, int(s) if s.isdigit() else 99)


def parse_chroms(spec: str | None) -> list[int] | None:
    """'1-22', '16', '1,2,5-7' -> sorted list; None/'' -> None (all)."""
    if not spec:
        return None
    out: set[int] = set()
    for part in str(spec).replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    bad = [c for c in out if not 1 <= c <= 22]
    if bad:
        raise ValueError(f"chromosomes must be autosomes 1-22, got {bad}")
    return sorted(out)


def read_regenie(path: Path) -> pd.DataFrame:
    """Read a regenie step-2 file; failed tests (NA) become NaN and are dropped."""
    df = pd.read_csv(path, sep=r"\s+", na_values=["NA"], dtype={"ID": str, "ALLELE0": str, "ALLELE1": str})
    df = df.dropna(subset=["LOG10P"])
    return df


def lambda_gc_from_log10p(log10p: np.ndarray) -> float:
    """λGC from -log10 P without underflow: χ² = isf(P) computed via logsf."""
    p = np.power(10.0, -np.asarray(log10p, dtype=float))
    chisq = stats.chi2.isf(np.clip(p, 1e-300, 1.0), 1)
    return float(np.median(chisq) / CHISQ_MEDIAN_1DF)


def p_from_log10p(log10p, floor: float = 1e-300) -> np.ndarray:
    return np.clip(np.power(10.0, -np.asarray(log10p, dtype=float)), floor, 1.0)


def count_lines(path: Path) -> int:
    n = 0
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            n += chunk.count(b"\n")
    return n


def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_") or "x"


def df_to_records(df: pd.DataFrame, digits: int = 4) -> list[dict]:
    out = []
    for rec in df.to_dict(orient="records"):
        clean = {}
        for k, v in rec.items():
            if isinstance(v, (float, np.floating)):
                v = None if not np.isfinite(v) else float(f"{v:.{digits}g}")
            elif isinstance(v, np.integer):
                v = int(v)
            clean[k] = v
        out.append(clean)
    return out
