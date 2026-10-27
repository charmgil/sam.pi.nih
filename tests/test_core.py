"""Unit tests for samkit that need no external tools (plink2/regenie/R/ldsc/PRS-CS)."""

from __future__ import annotations

import gzip
import io
import json
import tarfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from samkit import inventory, resources
from samkit.context import Context, SamError
from samkit.io import lambda_gc_from_log10p, parse_chroms
from samkit.steps import gwas, ldsc, pheweb, prs, regional


@pytest.fixture()
def dirs(tmp_path: Path):
    inp, res, run = tmp_path / "input", tmp_path / "resource", tmp_path / "run"
    for d in (inp, res, run):
        d.mkdir()
    return inp, res, run


def make_ctx(inp, res, run, **kw) -> Context:
    resources._CACHE.clear()
    return Context.from_values(inp, res, run / "output", threads=2, **kw)


# ── context: read-only data, writes only under output ───────────────────────
def test_output_inside_input_is_refused(dirs):
    inp, res, _ = dirs
    with pytest.raises(SamError):
        Context.from_values(inp, res, inp / "output")


def test_writes_are_confined(dirs):
    ctx = make_ctx(*dirs)
    assert ctx.out("a", "b.txt").parent.is_dir()
    with pytest.raises(SamError):
        ctx.check_writable(dirs[0] / "x.txt")
    with pytest.raises(SamError):
        ctx.check_writable(dirs[2] / "elsewhere.txt")


def test_output_bound_to_one_dataset(dirs, tmp_path):
    inp, res, run = dirs
    make_ctx(inp, res, run).bind()
    other = tmp_path / "other_input"
    other.mkdir()
    with pytest.raises(SamError):
        make_ctx(other, res, run).bind()
    make_ctx(other, res, run, rebind=True).bind()


def test_input_path_accepts_output_prefix(dirs):
    ctx = make_ctx(*dirs)
    f = ctx.out("downloads", "pheweb", "x.tsv.gz")
    f.write_text("x")
    assert ctx.input_path("output/downloads/pheweb/x.tsv.gz") == f.resolve()
    with pytest.raises(SamError):
        ctx.input_path("missing.txt")


# ── inventory ────────────────────────────────────────────────────────────────
def test_classify_tables(dirs):
    inp = dirs[0]
    with gzip.open(inp / "phenocode-X.tsv.gz", "wt") as fh:
        fh.write("chrom\tpos\tref\talt\trsids\tnearest_genes\tpval\tbeta\tsebeta\tmaf\taf\n")
    with gzip.open(inp / "X_PRS_weight.txt.gz", "wt") as fh:
        fh.write("1\trs1\t100\tA\tG\t0.1\n")
    (inp / "pheno.txt").write_text("ID\tSEX\tAGE\tHDL\n1\t1\t50\t40\n2\t2\t60\t55\n")
    (inp / "map.txt").write_text("VariantID\tdbSNP_HG19\nAX-1\trs1\n")
    kinds = {t["name"]: t["kind"] for t in (inventory.classify_table(p) for p in inp.iterdir())}
    assert kinds == {"phenocode-X.tsv.gz": "sumstats", "X_PRS_weight.txt.gz": "prs_weight",
                     "pheno.txt": "phenotype", "map.txt": "id_map"}
    pheno = inventory.classify_table(inp / "pheno.txt")
    assert pheno["rows"] == 2 and pheno["individual_level"]


def test_dotted_plink_prefix_is_found(dirs):
    inp = dirs[0]
    for ext in (".bed", ".bim", ".fam"):
        (inp / f"KBAv2.0AB_14K{ext}").write_text("x\n")
    sets = inventory.genotype_sets(make_ctx(*dirs))
    assert [g["name"] for g in sets] == ["KBAv2.0AB_14K"]


# ── resources: archives are read in place, members extracted on demand ─────
def _resource_archives(res: Path) -> None:
    with zipfile.ZipFile(res / "resource-gwas.zip", "w") as z:
        for c in range(1, 23):
            z.writestr(f"LDSC/baseline.{c}.l2.ldscore.gz", b"x")
            z.writestr(f"LDSC/baseline.{c}.l2.M_5_50", b"1")
            z.writestr(f"LDSC/w/weights.EAS.hm3_noMHC.{c}.l2.ldscore.gz", b"x")
            z.writestr(f"genetic_map/plink.chr{c}.GRCh37.map", b"1 . 0.0 100\n")
        z.writestr("__MACOSX/._junk", b"x")
    with tarfile.open(res / "ldblk_1kg_eas.tar.gz", "w:gz") as t:
        for name in ("ldblk_1kg_eas/snpinfo_1kg_hm3", "ldblk_1kg_eas/ldblk_1kg_chr16.hdf5"):
            data = name.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))


def test_resource_components_and_extraction(dirs):
    inp, res, run = dirs
    _resource_archives(res)
    before = {p.name: p.stat().st_mtime for p in res.iterdir()}
    ctx = make_ctx(inp, res, run)
    kinds = {c.kind: c for c in resources.components(ctx)}
    assert set(kinds) >= {"ldsc_ref", "ldsc_weights", "genetic_map", "prscs_ld"}
    assert kinds["ldsc_ref"].describe()["complete_autosomes"]
    assert kinds["genetic_map"].meta["build"] == "hg19"
    ld = kinds["prscs_ld"]
    assert ld.chroms == [16] and ld.meta["ancestry"] == "EAS" and ld.meta["snpinfo"]
    root = resources.materialize(ctx, ld, ["ldblk_1kg_eas/ldblk_1kg_chr16.hdf5"])
    assert (root / "ldblk_1kg_eas" / "ldblk_1kg_chr16.hdf5").read_bytes() == b"ldblk_1kg_eas/ldblk_1kg_chr16.hdf5"
    assert root.is_relative_to(ctx.output_dir)
    assert {p.name: p.stat().st_mtime for p in res.iterdir()} == before  # archives untouched


def test_unsafe_archive_member_rejected(tmp_path):
    with pytest.raises(SamError):
        resources._safe_dest(tmp_path, "../escape.txt")


# ── PRS: allele matching and sumstat preparation ────────────────────────────
def test_match_weights_alleles():
    target = pd.DataFrame({"ID": ["v1", "v2", "v3", "v4", "v5"], "SNP": ["rs1", "rs2", "rs3", "rs4", "rs5"],
                           "CHR": ["1"] * 5, "BP": ["1"] * 5, "ALT": ["A", "A", "A", "A", "A"],
                           "REF": ["G", "G", "G", "T", "C"]})
    w = pd.DataFrame({"SNP": ["rs1", "rs2", "rs3", "rs4", "rs5", "rs9"], "A1": ["A", "G", "T", "A", "G"] + ["A"],
                      "A2": ["G", "A", "C", "T", "A"] + ["G"], "BETA": [0.1] * 6})
    used, stats = prs.match_weights(w, target)
    assert stats["n_weights"] == 6 and stats["n_in_target"] == 5
    assert stats["n_strand_flipped"] == 1          # rs3: T/C is the complement of A/G
    assert stats["n_allele_mismatch_dropped"] == 1  # rs5: G/A vs A/C (no strand fixes it)
    assert stats["n_ambiguous_at_cg_used"] == 1     # rs4: A/T, matched directly
    eff = dict(zip(used["ID"], used["A1"]))
    assert eff == {"v1": "A", "v2": "G", "v3": "A", "v4": "A"}


def test_prepare_pheweb_sumstats_column_order(tmp_path):
    src = tmp_path / "phenocode-X.tsv.gz"
    with gzip.open(src, "wt") as fh:
        fh.write("chrom\tpos\tref\talt\trsids\tnearest_genes\tpval\tbeta\tsebeta\tmaf\taf\n")
        fh.write("1\t100\tG\tA\trs1\tG1\t0.01\t0.2\t0.05\t0.1\t0.1\n")
        fh.write("1\t200\tC\tT\trs2,rs3\tG1\t0.5\t-0.1\t0.1\t0.2\t0.2\n")
        fh.write("1\t300\tC\tT\t\tG1\t0.5\t-0.1\t0.1\t0.2\t0.2\n")
        fh.write("1\t400\tC\tT\trs1\tG1\t0.5\t-0.1\t0.1\t0.2\t0.2\n")
    out = tmp_path / "sst.txt"
    info = prs._prepare_sumstats(src, out)
    df = pd.read_csv(out, sep="\t")
    assert list(df.columns) == ["SNP", "A1", "A2", "BETA", "SE"]
    assert set(df["SNP"]) == {"rs2", "rs3"}      # rs1 appears twice -> dropped; empty rsid dropped
    assert (df["A1"] == "T").all() and (df["A2"] == "C").all()  # A1 = ALT (effect allele in PheWeb)
    assert info["n_rows"] == 4


def test_read_headerless_weights(tmp_path):
    f = tmp_path / "w.txt.gz"
    with gzip.open(f, "wt") as fh:
        fh.write("1\trs1\t100\tC\tT\t-2.3e-04\n1\trs2\t200\tG\tA\t6.0e-05\n")
    w = prs.read_weights(f)
    assert list(w["A1"]) == ["C", "G"] and np.isclose(w["BETA"].iloc[0], -2.3e-4)


# ── LDSC log parsing (negative and scientific values) ───────────────────────
def test_parse_h2_log():
    text = ("Total Observed scale h2: -0.0123 (0.0456)\nLambda GC: 1.0496\nMean Chi^2: 1.07\n"
            "Intercept: 1.0159 (0.01)\nRatio: 2.28e-01 (0.1432)\nAfter merging ... 197796 SNPs remain\n")
    out = ldsc.parse_h2_log(text)
    assert out["h2_observed"] == -0.0123 and out["ratio"] == 0.228 and out["n_snps_regression"] == 197796


# ── GWAS helpers ─────────────────────────────────────────────────────────────
def test_parse_chroms_and_lambda():
    assert parse_chroms("1-3,11") == [1, 2, 3, 11]
    assert parse_chroms(None) is None
    with pytest.raises(ValueError):
        parse_chroms("23")
    rng = np.random.default_rng(0)
    p = rng.uniform(size=200_000)
    assert abs(lambda_gc_from_log10p(-np.log10(p)) - 1.0) < 0.02


def test_distance_loci():
    sig = pd.DataFrame({"CHROM": [1, 1, 1, 2], "GENPOS": [1_000_000, 1_200_000, 3_000_000, 5_000],
                        "ID": list("abcd"), "ALLELE0": "A", "ALLELE1": "G", "BETA": 0.1, "SE": 0.01,
                        "LOG10P": [10, 20, 9, 8]})
    loci = gwas.distance_loci(sig, 500_000)
    assert [x["ID"] for x in loci] == ["b", "c", "d"]
    assert loci[0]["n_significant_in_locus"] == 2


# ── locus resolution ─────────────────────────────────────────────────────────
def test_resolve_locus(dirs):
    ctx = make_ctx(*dirs)
    res = pd.DataFrame({"CHROM": [11, 11, 16], "GENPOS": [116662579, 116663707, 56994528],
                        "ID": ["AX-1|chr11:1:C:T", "AX-2", "AX-3"], "ALLELE0": "T", "ALLELE1": "C",
                        "LOG10P": [62.4, 50.0, 82.4]})
    peaks = ctx.out("loci", "HDL", "peaks.tsv")
    pd.DataFrame({"rank": [1, 2], "locus": ["16:56994528", "11:116662579"],
                  "ID": ["AX-3", "AX-1|chr11:1:C:T"]}).to_csv(peaks, sep="\t", index=False)
    assert regional.resolve_locus(ctx, "HDL", res, "11:116662579")["ID"] == "AX-1|chr11:1:C:T"
    assert regional.resolve_locus(ctx, "HDL", res, "2")["GENPOS"] == 116662579
    assert regional.resolve_locus(ctx, "HDL", res, "AX-2")["is_peak_lead"] is False
    with pytest.raises(SamError) as e:
        regional.resolve_locus(ctx, "HDL", res, "11:116662000")
    assert "AX-1" in (e.value.hint or "")


# ── KNIH PheWeb catalog parsing ──────────────────────────────────────────────
PHEWEB_HTML = """
<ul><li><a href="#tab3">KBA_187K</a></li><li><a href="#tab6">PRS_weight</a></li></ul>
<div class="tab-pane" id="tab3"><table>
<tr><th>No.</th><th>Category</th><th>Phenotype</th><th>Cohort</th><th>No. samples</th><th>No. cases</th>
<th>No. controls</th><th>Download link</th></tr>
<tr><td>54</td><td>Self-reported</td><td>Hypertension</td><td>KBA_187K</td><td>-</td><td>40,036 </td>
<td>145,769 </td><td><a href="http://x:8082/download/KBA_187K_HTN">Download</a></td></tr>
</table></div>
<div class="tab-pane" id="tab6"><table>
<tr><th>No.</th><th>Category</th><th>Phenotype</th><th>Method</th><th>No. samples</th><th>No. cases</th>
<th>No. controls</th><th>Download link</th></tr>
<tr><td>5</td><td>Self-reported</td><td>Hypertension</td><td>PRS</td><td>-</td><td>-</td><td>-</td>
<td><a href="http://x:8082/prs/HTN_PRS_weight">Download</a></td></tr>
</table></div>
"""


def test_pheweb_catalog(dirs, monkeypatch):
    ctx = make_ctx(*dirs)

    class Resp:
        text = PHEWEB_HTML

        def raise_for_status(self):
            return None

    monkeypatch.setattr(pheweb.requests, "get", lambda *a, **k: Resp())
    hits = pheweb.search(ctx, "hypertension", refresh=True)["hits"]
    by_code = {h["code"]: h for h in hits}
    assert by_code["KBA_187K_HTN"]["n_gwas"] == 185805 and by_code["KBA_187K_HTN"]["kind"] == "sumstats"
    assert by_code["HTN_PRS_weight"]["kind"] == "prs_weight"
    assert json.loads((ctx.output_dir / "_cache" / "pheweb_catalog.json").read_text())


# ── regression tests for the 2026-10-27 review ──────────────────────────────
def test_weights_dedup_multi_rsid_and_comments(tmp_path):
    f = tmp_path / "pgs.txt"
    f.write_text("#pgs_id=PGS000001\n#genome_build=GRCh37\nrsID\teffect_allele\tother_allele\teffect_weight\n"
                 "rs1\tA\tG\t0.1\nrs2,rs2\tC\tT\t0.2\nrs3\tA\tG\t0.3\nrs3\tA\tG\t0.4\n")
    w = prs.read_weights(f)
    assert list(w["SNP"]) == ["rs1", "rs2"]          # rs2,rs2 -> rs2; duplicated rs3 dropped
    assert list(w["A1"]) == ["A", "C"]


def test_space_delimited_generic_sumstats(tmp_path):
    src = tmp_path / "gen.txt"
    src.write_text("SNP A1 A2 BETA SE P\nrs1 A G 0.1 0.01 1e-5\nrs2 C T -0.2 0.02 0.3\n")
    info = prs._prepare_sumstats(src, tmp_path / "out.txt")
    assert info["format"] == "generic" and info["n_usable_rsid"] == 2


def test_headerless_table_is_not_echoed(tmp_path):
    f = tmp_path / "covar.txt"
    f.write_text("FAM001\tIND001\t35.2\t1\nFAM002\tIND002\t41.0\t2\n")
    info = inventory.classify_table(f)
    assert info["columns"] is None and "IND001" not in json.dumps(info)


def test_resolve_columns_case_and_pcs():
    fid, iid, covars, notes = gwas.resolve_columns(["FID", "IID", "age", "sex", "PC1", "HDL"], "x.txt", "HDL", None)
    assert covars == ["age", "sex"] and fid == "FID" and iid == "IID"
    cols = ["ID", "AGE", "PC1", "PC2", "HDL"]
    _, _, covars, notes = gwas.resolve_columns(cols, "x.txt", "HDL", ["AGE", "PC1", "PC2"])
    assert covars == ["AGE"] and any("PC columns" in n for n in notes)
    with pytest.raises(SamError):
        gwas.resolve_columns(["ID", "AGE", "HDL"], "x.txt", "LDL", None)


def test_cli_json_has_no_nan():
    from samkit.cli import _clean
    out = json.dumps(_clean({"a": float("nan"), "b": [1.0, float("inf")], "c": {"d": 2.5}}), allow_nan=False)
    assert out == '{"a": null, "b": [1.0, null], "c": {"d": 2.5}}'
