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
    part = dest.with_name(dest.name + ".part")
    return {"ok": True, **e, "size_bytes": size, "size_mb": round(size / 1e6, 1) if size else None,
            "resumable": _probe_ranges(e["url"]),
            "destination": ctx.display(dest), "exists": dest.exists(),
            "partial_mb": round(part.stat().st_size / 1e6, 1) if part.exists() else None}


def _probe_ranges(url: str) -> bool | None:
    """Whether the server honours Range requests (the KNIH server does, without Accept-Ranges)."""
    try:
        with requests.get(url, headers={"Range": "bytes=0-0"}, stream=True, timeout=30) as r:
            return r.status_code == 206
    except requests.RequestException:
        return None


def _dest(ctx: Context, e: dict) -> Path:
    fname = f"phenocode-{e['code']}.tsv.gz" if e["kind"] == "sumstats" else f"{e['code']}.txt.gz"
    return ctx.out("downloads", "pheweb", fname)


RETRIES = 5
NET_ERRORS = (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError)


def _validator(r: requests.Response) -> str | None:
    """A strong validator for If-Range (weak ETags are not allowed there)."""
    etag = r.headers.get("ETag")
    if etag and not etag.startswith("W/"):
        return etag
    return r.headers.get("Last-Modified")


def fetch(url: str, part: Path, log) -> tuple[int, bool]:
    """Download url into part, resuming an earlier partial download with an HTTP Range request.

    <part>.json keeps the URL, size and validator of the first response. On resume the validator
    is sent as If-Range, so a file that changed on the server comes back whole (200) and is
    fetched again from the start. Network errors are retried, each time from the bytes already
    on disk; if every retry fails the partial file is kept for the next call.
    Returns (size, resumed).
    """
    state_f = part.with_name(part.name + ".json")
    state = json.loads(state_f.read_text()) if state_f.exists() else {}
    if state.get("url") != url or not part.exists():
        state = {}
    resumed = False
    for attempt in range(1, RETRIES + 1):
        have = part.stat().st_size if state and part.exists() else 0
        headers = {"Range": f"bytes={have}-"} if have else {}
        if have and state.get("validator"):
            headers["If-Range"] = state["validator"]
        try:
            with requests.get(url, stream=True, timeout=60, headers=headers) as r:
                if r.status_code == 416 and have and have == state.get("total"):
                    return have, resumed
                if r.status_code == 416:  # partial file larger than the remote file: start over
                    part.unlink(missing_ok=True)
                    state = {}
                    continue
                r.raise_for_status()
                m = re.fullmatch(r"bytes (\d+)-\d+/(\d+|\*)", r.headers.get("Content-Range", ""))
                if r.status_code == 206 and m and int(m.group(1)) == have and (
                        m.group(2) == "*" or state.get("total") in (None, int(m.group(2)))):
                    mode, resumed = "ab", True
                    log.info(f"  resuming at {have / 1e6:.0f} MB")
                else:  # full body: first attempt, no range support, or the file changed
                    if have:
                        log.info("  server sent the whole file (changed or no range support); starting over")
                    have, mode = 0, "wb"
                    state = {"url": url, "total": int(r.headers.get("Content-Length", 0)) or None,
                             "validator": _validator(r)}
                    state_f.write_text(json.dumps(state))
                total, got = state.get("total"), have
                with open(part, mode) as fh:
                    for chunk in r.iter_content(1 << 20):
                        fh.write(chunk)
                        got += len(chunk)
                        if total and got % (50 << 20) < (1 << 20):
                            log.info(f"  {got / 1e6:.0f} / {total / 1e6:.0f} MB")
            if not total or got == total:
                state_f.unlink(missing_ok=True)
                return got, resumed
            log.info(f"  WARNING: connection closed at {got / 1e6:.0f} of {total / 1e6:.0f} MB; resuming")
        except NET_ERRORS as exc:
            log.info(f"  WARNING: network error ({exc.__class__.__name__}), attempt {attempt}/{RETRIES}")
        time.sleep(min(60, 5 * attempt))
    done = part.stat().st_size if part.exists() else 0
    raise SamError(f"download interrupted after {RETRIES} attempts ({done / 1e6:.0f} MB kept)",
                   hint="run the same download again; it resumes from the partial file")


def download(ctx: Context, code: str) -> dict:
    e = _entry(ctx, code)
    dest = _dest(ctx, e)
    run = StepRun(ctx, "pheweb-download", code, {"url": e["url"]}, ["python"])
    resumed = False
    if dest.exists() and dest.with_name(dest.name + ".meta.json").exists():
        run.log.info(f"already downloaded: {dest}")
    else:
        part = dest.with_name(dest.name + ".part")
        got, resumed = fetch(e["url"], part, run.log)
        h = hashlib.sha256()
        with open(part, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        part.rename(dest)
        meta = {**e, "downloaded": time.strftime("%Y-%m-%dT%H:%M:%S"), "bytes": got, "sha256": h.hexdigest(),
                "resumed": resumed}
        dest.with_name(dest.name + ".meta.json").write_text(json.dumps(meta, indent=2))
    summary = {"code": code, "phenotype": e["phenotype"], "cohort": e["cohort"], "kind": e["kind"],
               "n_gwas": e["n_gwas"], "file": ctx.display(dest),
               "size_mb": round(dest.stat().st_size / 1e6, 1), "resumed": resumed}
    nxt = ["prs-prscs"] if e["kind"] == "sumstats" else ["prs-score"]
    return run.finish(summary, {"file": dest}, [], nxt)
