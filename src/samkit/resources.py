"""Reference resources: found in the read-only resource directory, as plain
directories or inside .zip / .tar.gz archives.

Archives are never modified. When a step needs files from an archive, only
those members are extracted into output/_cache/resources/<archive>/ and
reused afterwards (keyed by the archive's size and mtime).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from samkit.context import Context, SamError

ARCHIVE_RE = re.compile(r"\.(zip|tar\.gz|tgz|tar)$")


@dataclass
class Source:
    """A directory or archive inside the resource directory."""
    path: Path
    kind: str  # "dir" | "zip" | "tar"
    members: list[str] = field(default_factory=list)  # relative POSIX paths of files

    @property
    def label(self) -> str:
        return self.path.name


@dataclass
class Component:
    kind: str           # ldsc_ref | ldsc_weights | hm3_snplist | pos2rsid | genetic_map | dbsnp_map | prscs_ld
    source: Source
    prefix: str         # member path prefix (directory or file stem) inside the source
    files: list[str]
    chroms: list[int] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def describe(self) -> dict:
        d = {"kind": self.kind, "source": self.source.label, "source_type": self.source.kind,
             "prefix": self.prefix, "n_files": len(self.files)}
        if self.chroms:
            d["chromosomes"] = _compress_chroms(self.chroms)
            d["complete_autosomes"] = set(range(1, 23)) <= set(self.chroms)
        d.update(self.meta)
        return d


def _compress_chroms(chroms: list[int]) -> str:
    chroms = sorted(set(chroms))
    out, start = [], None
    for i, c in enumerate(chroms):
        if start is None:
            start = c
        if i == len(chroms) - 1 or chroms[i + 1] != c + 1:
            out.append(str(start) if start == c else f"{start}-{c}")
            start = None
    return ",".join(out)


# ── archive listing (cached) ────────────────────────────────────────────────
def _cache_name(src: Path) -> str:
    """Archive name plus a short hash of its full path, so equal names in different folders don't collide."""
    return f"{re.sub(ARCHIVE_RE, '', src.name)}-{hashlib.sha1(str(src.resolve()).encode()).hexdigest()[:8]}"


def _index_path(ctx: Context, src: Path) -> Path:
    return ctx.out("_cache", "resources", f"{_cache_name(src)}.index.json")


def _list_archive(ctx: Context, src: Path, kind: str) -> list[str]:
    st = src.stat()
    key = {"size": st.st_size, "mtime": int(st.st_mtime)}
    idx = _index_path(ctx, src)
    if idx.exists():
        cached = json.loads(idx.read_text())
        if cached.get("key") == key:
            return cached["members"]
    if kind == "zip":
        with zipfile.ZipFile(src) as z:
            members = [i.filename for i in z.infolist() if not i.is_dir()]
    else:
        members = []
        with tarfile.open(src, "r|*") as t:
            for m in t:
                if m.isfile():
                    members.append(m.name)
    members = [m for m in members if "__MACOSX" not in m and not PurePosixPath(m).name.startswith("._")
               and not m.endswith(".DS_Store")]
    idx.write_text(json.dumps({"key": key, "members": members}))
    return members


def sources(ctx: Context) -> list[Source]:
    if ctx.resource_dir is None:
        return []
    out: list[Source] = []
    root = ctx.resource_dir
    # the resource dir itself is a directory source (files at any depth <= 4)
    files = [str(p.relative_to(root).as_posix()) for p in root.rglob("*")
             if p.is_file() and len(p.relative_to(root).parts) <= 4 and not ARCHIVE_RE.search(p.name)
             and not p.name.startswith(".")]
    out.append(Source(root, "dir", files))
    for p in sorted(root.rglob("*")):
        if p.is_file() and ARCHIVE_RE.search(p.name) and len(p.relative_to(root).parts) <= 3:
            kind = "zip" if p.name.endswith(".zip") else "tar"
            try:
                out.append(Source(p, kind, _list_archive(ctx, p, kind)))
            except (OSError, zipfile.BadZipFile, tarfile.TarError, EOFError) as exc:
                out.append(Source(p, "unreadable", []))
                out[-1].members = [f"!error: {exc.__class__.__name__}: {exc}"]
    return out


# ── component detection ─────────────────────────────────────────────────────
_LDSCORE = re.compile(r"^(?P<dir>(?:.*/)?)(?P<stem>[^/]+?)\.(?P<chr>\d{1,2})\.l2\.ldscore\.gz$")
_GMAP = re.compile(r"^(?P<dir>(?:.*/)?)plink\.chr(?P<chr>\d{1,2})\.GRCh(?P<build>37|38)\.map$")
_PRSCS = re.compile(r"^(?P<dir>(?:.*/)?ldblk_(?P<src>1kg|ukbb)_(?P<pop>[a-z]+)/)ldblk_\w+?_chr(?P<chr>\d{1,2})\.hdf5$")


_CACHE: dict[str, list[Component]] = {}


def components(ctx: Context) -> list[Component]:
    cache_key = str(ctx.resource_dir)
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    found: list[Component] = []
    for src in sources(ctx):
        groups: dict[tuple, Component] = {}
        for m in src.members:
            if (mm := _LDSCORE.match(m)):
                stem = mm["stem"]
                kind = "ldsc_weights" if "weight" in (mm["dir"] + stem).lower() else "ldsc_ref"
                key = (kind, mm["dir"], stem)
                comp = groups.setdefault(key, Component(kind, src, mm["dir"] + stem + ".", [], [],
                                                        {"panel": (mm["dir"] + stem).strip("/")}))
                comp.chroms.append(int(mm["chr"]))
                comp.files.append(m)
            elif (mm := _GMAP.match(m)):
                key = ("genetic_map", mm["dir"], mm["build"])
                comp = groups.setdefault(key, Component("genetic_map", src, mm["dir"], [], [],
                                                        {"build": "hg19" if mm["build"] == "37" else "hg38"}))
                comp.chroms.append(int(mm["chr"]))
                comp.files.append(m)
            elif (mm := _PRSCS.match(m)):
                key = ("prscs_ld", mm["dir"])
                comp = groups.setdefault(key, Component("prscs_ld", src, mm["dir"], [], [],
                                                        {"panel": f"{mm['src']}_{mm['pop']}",
                                                         "ancestry": mm["pop"].upper()}))
                comp.chroms.append(int(mm["chr"]))
                comp.files.append(m)
            else:
                name = PurePosixPath(m).name
                if re.match(r"w_hm3.*\.snplist$", name):
                    groups[("hm3_snplist", m)] = Component("hm3_snplist", src, m, [m], [],
                                                           {"snp_only": "snponly" in name})
                elif re.match(r"pos2rsid.*\.txt(\.gz)?$", name):
                    groups[("pos2rsid", m)] = Component("pos2rsid", src, m, [m])
                elif re.search(r"dbsnp", name, re.I) and re.search(r"rs", name, re.I) and \
                        name.endswith((".txt", ".txt.gz", ".tsv", ".tsv.gz")):
                    build = "hg19" if re.search(r"hg19|grch37|b37", name, re.I) else \
                        "hg38" if re.search(r"hg38|grch38", name, re.I) else None
                    groups[("dbsnp_map", m)] = Component("dbsnp_map", src, m, [m], [], {"build": build})
        # PRS-CS panels also need their snpinfo file
        for comp in groups.values():
            if comp.kind == "prscs_ld":
                info = [m for m in src.members if m.startswith(comp.prefix) and
                        PurePosixPath(m).name.startswith("snpinfo_")]
                comp.files.extend(info)
                comp.meta["snpinfo"] = bool(info)
            if comp.kind == "ldsc_ref":
                comp.meta["has_M_5_50"] = any(m.startswith(comp.prefix) and m.endswith(".l2.M_5_50")
                                               for m in src.members)
        found.extend(groups.values())
    _CACHE[cache_key] = found
    return found


def find(ctx: Context, kind: str, prefer: str | None = None) -> Component | None:
    comps = [c for c in components(ctx) if c.kind == kind]
    if prefer:
        pref = [c for c in comps if prefer.lower() in (c.prefix + c.meta.get("panel", "")).lower()]
        comps = pref or comps
    # plain directories before archives (no extraction needed); then the largest set
    comps.sort(key=lambda c: (c.source.kind != "dir", -len(c.chroms), c.prefix))
    return comps[0] if comps else None


def require(ctx: Context, kind: str, prefer: str | None = None, what: str = "") -> Component:
    comp = find(ctx, kind, prefer)
    if comp is None:
        raise SamError(f"resource not found: {kind}{' (' + what + ')' if what else ''}",
                       hint=f"put it in the resource directory {ctx.resource_dir} (plain folder or .zip/.tar.gz); "
                            "see docs/TOOLS.md for sources")
    return comp


# ── materialization ─────────────────────────────────────────────────────────
def _safe_dest(root: Path, member: str) -> Path:
    rel = PurePosixPath(member)
    if rel.is_absolute() or ".." in rel.parts:
        raise SamError(f"unsafe path in archive: {member}")
    return root.joinpath(*rel.parts)


def materialize(ctx: Context, comp: Component, members: list[str] | None = None, log=None) -> Path:
    """Return a local directory where ``comp.prefix`` (plus members) can be read.

    Plain directories are used in place (read-only). Archive members are
    extracted to the output cache on first use.
    """
    src = comp.source
    if src.kind == "dir":
        return src.path
    if src.kind == "unreadable":
        raise SamError(f"cannot read archive {src.path}", hint="; ".join(src.members))
    wanted = set(members if members is not None else comp.files)
    root = ctx.out("_cache", "resources", _cache_name(src.path), is_dir=True)
    st = src.path.stat()
    stamp = root / ".source.json"
    key = {"archive": str(src.path), "size": st.st_size, "mtime": int(st.st_mtime)}
    if stamp.exists() and json.loads(stamp.read_text()) != key:
        shutil.rmtree(root)
        root.mkdir(parents=True)
    todo = {m for m in wanted if not _safe_dest(root, m).exists()}
    if todo:
        if log:
            log.info(f"extracting {len(todo)} file(s) from {src.path.name} into {root}")
        if src.kind == "zip":
            with zipfile.ZipFile(src.path) as z:
                for m in sorted(todo):
                    dest = _safe_dest(root, m)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    tmp = dest.with_name(dest.name + ".part")
                    with z.open(m) as fin, open(tmp, "wb") as fout:
                        shutil.copyfileobj(fin, fout, 1 << 20)
                    tmp.rename(dest)
        else:
            remaining = set(todo)
            with tarfile.open(src.path, "r|*") as t:
                for m in t:
                    if m.name not in remaining or not m.isfile():
                        continue
                    dest = _safe_dest(root, m.name)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    tmp = dest.with_name(dest.name + ".part")
                    fin = t.extractfile(m)
                    assert fin is not None
                    with open(tmp, "wb") as fout:
                        shutil.copyfileobj(fin, fout, 1 << 20)
                    tmp.rename(dest)
                    remaining.discard(m.name)
                    if log:
                        log.info(f"  extracted {m.name}")
                    if not remaining:
                        break
            if remaining:
                raise SamError(f"{len(remaining)} member(s) missing from {src.path.name}",
                               hint=", ".join(sorted(remaining)[:5]))
        stamp.write_text(json.dumps(key))
    return root


def summary(ctx: Context) -> dict:
    comps = components(ctx)
    srcs = sources(ctx)
    return {
        "resource_dir": str(ctx.resource_dir) if ctx.resource_dir else None,
        "sources": [{"name": s.label, "type": s.kind, "files": len(s.members)} for s in srcs],
        "components": [c.describe() for c in comps],
    }
