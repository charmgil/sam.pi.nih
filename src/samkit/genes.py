"""Gene track (Ensembl REST, build-matched) and recombination rate (genetic map)."""

from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd
import requests

from samkit import resources
from samkit.context import Context

ENSEMBL = {"hg19": "https://grch37.rest.ensembl.org", "hg38": "https://rest.ensembl.org"}


def fetch_genes(ctx: Context, chrom: int, start: int, end: int) -> tuple[list[dict], str | None]:
    """Protein-coding genes overlapping the region; cached under output/_cache/genes."""
    host = ENSEMBL.get(ctx.build)
    if host is None:
        return [], f"unknown build {ctx.build}"
    cache = ctx.out("_cache", "genes", f"{ctx.build}_{chrom}_{start}_{end}.json")
    if cache.exists():
        return json.loads(cache.read_text()), None
    url = f"{host}/overlap/region/human/{chrom}:{max(start, 1)}-{end}?feature=gene;content-type=application/json"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        genes = [{"name": g.get("external_name") or g.get("id"), "start": g["start"], "end": g["end"],
                  "strand": g.get("strand", 1)} for g in r.json() if g.get("biotype") == "protein_coding"]
    except (requests.RequestException, ValueError, KeyError) as exc:
        return [], f"gene track unavailable ({exc.__class__.__name__}); plot drawn without genes"
    cache.write_text(json.dumps(genes))
    return genes, None


def recombination(ctx: Context, chrom: int, start: int, end: int, log=None):
    """(positions in Mb, rate in cM/Mb) from a build-matched genetic map, or (None, reason)."""
    comps = [c for c in resources.components(ctx) if c.kind == "genetic_map" and c.meta.get("build") == ctx.build]
    if not comps:
        return None, f"no {ctx.build} genetic map in resources; recombination track omitted"
    comp = comps[0]
    member = next((f for f in comp.files if re.search(rf"\.chr{chrom}\.GRCh\d+\.map$", f)), None)
    if member is None:
        return None, f"genetic map has no chromosome {chrom}"
    root = resources.materialize(ctx, comp, [member], log=log)
    gmap = pd.read_csv(root / member, sep=r"\s+", header=None, names=["chr", "id", "cM", "bp"])
    reg = gmap[(gmap["bp"] >= start - 200_000) & (gmap["bp"] <= end + 200_000)].sort_values("bp")
    if len(reg) < 2:
        return None, "genetic map has too few points in this region"
    mid = (reg["bp"].values[:-1] + reg["bp"].values[1:]) / 2
    dbp = np.diff(reg["bp"].values)
    rate = np.where(dbp > 0, np.diff(reg["cM"].values) / (dbp / 1e6), 0.0)
    m = (mid >= start) & (mid <= end)
    return (mid[m] / 1e6, rate[m]), None
