"""KNIH PheWeb: find and download GWAS summary statistics and PRS weights.

Downloads go to output/downloads/pheweb/ (the input directory is read-only),
each with a <file>.meta.json sidecar that records the GWAS sample size.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import time
from pathlib import Path

import requests

from samkit.context import Context, SamError
from samkit.steps import StepRun

DEFAULT_URL = "http://150.183.252.241:8082"
CATALOG_MAX_AGE = 7 * 24 * 3600


def base_url() -> str:
    return os.environ.get("SAM_PHEWEB_URL", DEFAULT_URL).rstrip("/")


def _num(text: str) -> int | None:
    t = text.replace(",", "").strip()
    return int(t) if t.isdigit() else None


def catalog(ctx: Context, refresh: bool = False) -> list[dict]:
    cache = ctx.out("_cache", "pheweb_catalog.json")
    if cache.exists() and not refresh and time.time() - cache.stat().st_mtime < CATALOG_MAX_AGE:
        return json.loads(cache.read_text())
    try:
        r = requests.get(f"{base_url()}/download", timeout=30)
        r.raise_for_status()
    except requests.RequestException as exc:
        raise SamError(f"cannot reach KNIH PheWeb at {base_url()}: {exc.__class__.__name__}",
                       hint="check network access, or set SAM_PHEWEB_URL") from exc
    page = r.text
    tabs = dict(re.findall(r'href="#(tab\d+)"[^>]*>(.*?)<', page))
    rows: list[dict] = []
    for m in re.finditer(r'<div[^>]*id="(tab\d+)"[^>]*>(.*?)(?=<div[^>]*id="tab\d+"|\Z)', page, re.S):
        tab, body = m.group(1), m.group(2)
        heads = [re.sub(r"<[^>]+>", "", h).strip() for h in re.findall(r"<th[^>]*>(.*?)</th>", body, re.S)]
        for tr in re.findall(r"<tr>(.*?)</tr>", body, re.S):
            cells = [html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c))).strip()
                     for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            links = re.findall(r'href="([^"]+)"', tr)
            if len(cells) < len(heads) or not cells:
                continue
            rec = dict(zip(heads, cells))
            link = links[0] if links else None
            kind = "prs_weight" if link and "/prs/" in link else "sumstats"
            code = link.rstrip("/").rsplit("/", 1)[-1] if link else None
            n = _num(rec.get("No. samples", ""))
            cases, controls = _num(rec.get("No. cases", "")), _num(rec.get("No. controls", ""))
            if n is None and cases and controls:
                n = cases + controls
            rows.append({"tab": tabs.get(tab, tab), "category": rec.get("Category"), "phenotype": rec.get("Phenotype"),
                         "cohort": rec.get("Cohort") or rec.get("Method"), "method": rec.get("Method"),
                         "kind": kind, "code": code, "url": link, "n_gwas": n, "cases": cases, "controls": controls,
                         "downloadable": bool(link)})
    cache.write_text(json.dumps(rows, indent=1))
    return rows


def search(ctx: Context, query: str, kind: str | None = None, refresh: bool = False) -> dict:
    rows = catalog(ctx, refresh)
    words = [w.lower() for w in re.split(r"\s+", query.strip()) if w]
    hits = [r for r in rows if all(w in " ".join(str(v) for v in (r["phenotype"], r["code"], r["category"],
                                                                     r["cohort"])).lower() for w in words)]
    if kind:
        hits = [r for r in hits if r["kind"] == kind]
    return {"ok": True, "query": query, "server": base_url(), "n_hits": len(hits), "hits": hits[:40],
            "note": "same phenotype can exist in several cohorts (KBA+BBJ, KBA_126K, KBA_187K, ...); "
                    "PRS weights have Method PRS or lcPRS. Ask the user which one to use."}


def _entry(ctx: Context, code: str) -> dict:
    for r in catalog(ctx):
        if r["code"] == code:
            return r
    raise SamError(f"unknown PheWeb code: {code}", hint="use pheweb search first")


def head(ctx: Context, code: str) -> dict:
    e = _entry(ctx, code)
    if not e["downloadable"]:
        raise SamError(f"{code} has no download link on PheWeb")
    r = requests.head(e["url"], timeout=30, allow_redirects=True)
    size = int(r.headers.get("Content-Length", 0)) or None
    dest = _dest(ctx, e)
    return {"ok": True, **e, "size_bytes": size, "size_mb": round(size / 1e6, 1) if size else None,
            "destination": ctx.display(dest), "exists": dest.exists()}


def _dest(ctx: Context, e: dict) -> Path:
    fname = f"phenocode-{e['code']}.tsv.gz" if e["kind"] == "sumstats" else f"{e['code']}.txt.gz"
    return ctx.out("downloads", "pheweb", fname)


def download(ctx: Context, code: str) -> dict:
    e = _entry(ctx, code)
    dest = _dest(ctx, e)
    run = StepRun(ctx, "pheweb-download", code, {"url": e["url"]}, ["python"])
    if dest.exists() and dest.with_name(dest.name + ".meta.json").exists():
        run.log.info(f"already downloaded: {dest}")
    else:
        tmp = dest.with_name(dest.name + ".part")
        h = hashlib.sha256()
        got = 0
        with requests.get(e["url"], stream=True, timeout=60) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length", 0))
            with open(tmp, "wb") as fh:
                for chunk in r.iter_content(1 << 20):
                    fh.write(chunk)
                    h.update(chunk)
                    got += len(chunk)
                    if total and got % (50 << 20) < (1 << 20):
                        run.log.info(f"  {got / 1e6:.0f} / {total / 1e6:.0f} MB")
        if total and got != total:
            tmp.unlink()
            raise SamError(f"incomplete download ({got} of {total} bytes)")
        tmp.rename(dest)
        meta = {**e, "downloaded": time.strftime("%Y-%m-%dT%H:%M:%S"), "bytes": got, "sha256": h.hexdigest()}
        dest.with_name(dest.name + ".meta.json").write_text(json.dumps(meta, indent=2))
    summary = {"code": code, "phenotype": e["phenotype"], "cohort": e["cohort"], "kind": e["kind"],
               "n_gwas": e["n_gwas"], "file": ctx.display(dest),
               "size_mb": round(dest.stat().st_size / 1e6, 1)}
    nxt = ["prs-prscs"] if e["kind"] == "sumstats" else ["prs-score"]
    return run.finish(summary, {"file": dest}, [], nxt)
