# 01 — Step 1: GWAS (`script/01_gwas/`)

## Background

- **Genotype file formats**
  - **VCF**: text; can carry imputed dosages in the `FORMAT/DS` field.
  - **PLINK 1 `.bed/.bim/.fam`**: binary hard calls (0/1/2). The `.bim` file lists variants; the `.fam` file lists samples with an FID and an IID.
  - **PLINK 2 `.pgen/.pvar/.psam`**: binary and can store dosages. `.psam` lists samples, and its FID column is optional.
- **PCA**: the top principal components of the genotype matrix capture ancestry. Using them as covariates guards against population stratification.
- **LD pruning**: removes one SNP from each highly correlated pair, so the remaining SNPs are roughly independent. PCA and regenie step 1 both run on this pruned set.
- **regenie, two steps**
  - **Step 1** fits a whole-genome ridge regression on the pruned SNPs. It produces a polygenic prediction for each sample, with one chromosome left out at a time (**LOCO**), which acts as a correction for relatedness and polygenic background.
  - **Step 2** tests every variant, one at a time, using the matching LOCO prediction as an offset.
- **The `.regenie` result file** (space-separated) has the columns `CHROM GENPOS ID ALLELE0 ALLELE1 A1FREQ [INFO] N TEST BETA SE CHISQ LOG10P EXTRA`.
  - `ALLELE1` is the **effect/tested allele**. `BETA` is the effect per copy of `ALLELE1`. `A1FREQ` is its frequency.
  - `LOG10P` = −log10(p).
  - Failed tests show `NA`.
  - `INFO` may appear for dosage input.
  - Later steps use `CHROM`, `GENPOS`, `ID`, `ALLELE0/1`, `A1FREQ`, `N`, `BETA`, `SE`, `CHISQ` and `LOG10P`.

Order: `0_vcf_to_pgen.sh` *(conditional)* → `1-1_ld_pruning.sh` → `1-2_pca.sh` → `1-3_merge_pc.py` *(once per phenotype)* → `2-1_qt_step1.sh` / `2-2_bt_step1.sh` → `3-1_qt_step2.sh` / `3-2_bt_step2.sh`.

---

## 1.0 `0_vcf_to_pgen.sh` — VCF → PLINK 2 binary (skip if `.bed` already exists)

```bash
1  #!/bin/bash
2  source "$(dirname "$0")/../config.sh"
```
Loads the configuration (see README §4).

```bash
4  mkdir -p "${INPUT}"
```
Creates `input/` if it does not exist. `-p` means "don't fail if it already exists". This line normally does nothing, since the VCF is already in `input/`.

```bash
6   plink2 \
7     --vcf "${VCF_FILE}" dosage=DS \
8     --make-pgen \
9     --out "${GENO_PREFIX}" \
10    --threads ${N_THREADS}
```
- `--vcf FILE dosage=DS`: reads the VCF and imports **dosages** (the expected ALT-allele count, 0–2) from the `DS` FORMAT field that imputation writes, not only the `GT` hard calls. Keeping dosages matters for imputed data.
- `--make-pgen`: writes `.pgen` (genotypes), `.pvar` (variants) and `.psam` (samples).
- `--out "${GENO_PREFIX}"`: the files are named `input/${GENO_NAME}.*`, from `GENO_NAME` rather than the VCF's name.
- `--threads`: the number of CPU threads.
- **What it does not do:** no multi-allelic split or filter, no normalisation of variant IDs (IDs are copied from the VCF `ID` column), no sex information, and no FID (with default settings plink2 uses the VCF sample name as IID and writes no FID column).

```bash
12-13  # If the .psam header that plink2 writes starts with '#IID', regenie throws an error
       # → add an FID column to turn it into '#FID IID ...' format
14  PSAM="${GENO_PREFIX}.psam"
15  if head -1 "${PSAM}" | grep -q "^#IID"; then
```
- `head -1` prints the header line. `grep -q "^#IID"` succeeds, printing nothing, when that line **starts** with `#IID`. A typical psam from VCF import has the header `#IID SEX`.
- Once the fix below has run, the header starts with `#FID`, so running the script again skips the fix. The fix is **idempotent**.
- The comment gives the author's reason. Either way, the fix also guarantees **FID = IID**, which is what the phenotype files use, so the sample keys line up when regenie matches samples by FID+IID.

```bash
16  python3 -c "
17  lines = open('${PSAM}').readlines()
18  out = []
19  for i, line in enumerate(lines):
20      if i == 0:
21          out.append('#FID\t' + line.lstrip('#'))
22      else:
23          iid = line.split('\t')[0]
24          out.append(iid + '\t' + line)
25  open('${PSAM}', 'w').writelines(out)
26  "
```
An inline Python program. Bash expands `${PSAM}` **into the Python source text** before Python runs, because the whole program is in double quotes.
- L17: reads all lines, each keeping its trailing `\n`.
- L20–21, header: removes the leading `#` and puts `#FID\t` in front, so `#IID\tSEX\n` becomes `#FID\tIID\tSEX\n`.
- L22–24, data rows: takes the first tab-separated field (the IID) and prepends it plus a tab, so `S1\tNA\n` becomes `S1\tS1\tNA\n`. **FID is set to the IID.**
- L25: overwrites the psam in place.
- ⚠ A `'` in the path would break the Python syntax (a quoting hazard in generated code). Spaces are fine.

```bash
27  echo "psam FID column added: ${PSAM}"
28  fi
```
Status message; closes the `if`.

---

## 1.1 `1-1_ld_pruning.sh` — variant QC + LD pruning

```bash
4  mkdir -p "${OUTPUT}/01_gwas/pca"
```
Creates the folder for pruning and PCA outputs.

```bash
6   plink2 \
7     ${GENO_FLAG_PLINK} "${GENO_PREFIX}" \
8     --maf 0.1 \
9     --hwe 0.001 \
10    --geno 0.01 \
11    --indep-pairwise 1000 100 0.9 \
12    --out "${GENO_QC_PREFIX}_pruned" \
13    --threads ${N_THREADS}
```
- L7: the input genotypes (`--bfile …` or `--pfile …`, as chosen by config.sh).
- L8 `--maf 0.1`: drops variants whose minor allele frequency is < 10 %. That is strict (usual values are 1–5 %), but reasonable when the aim is a compact set of common SNPs for PCA and step 1.
- L9 `--hwe 0.001`: drops variants that fail the Hardy–Weinberg equilibrium exact test at p < 0.001, a sign of genotyping error.
- L10 `--geno 0.01`: drops variants that are missing in more than 1 % of samples.
- L11 `--indep-pairwise 1000 100 0.9`: the window is **1000 variants** (a count, because there is no `kb` suffix), it slides by 100 variants, and within each window one SNP of any pair with **r² > 0.9** is removed.
  - r² 0.9 is lenient, the kind of threshold used to thin SNPs for regenie step 1.
  - For **PCA** the usual threshold is 0.1–0.2. With 0.9, correlated SNPs from long-LD regions (such as the MHC or inversions) can dominate some PCs (**I-14**).
- L12 outputs: `…_pruned.prune.in` (IDs kept), `…_pruned.prune.out` (IDs removed) and `…_pruned.log`.
- **Important:** these QC filters only decide which variants go **into the prune set**. No filtered genotype file is written. The GWAS in step 2 still runs on **all** variants, with no MAF, HWE or missingness filter apart from regenie's built-in minimum minor-allele count (**I-13**). There is also no sample-level QC (`--mind`, heterozygosity, relatedness).

---

## 1.2 `1-2_pca.sh` — principal components

```bash
4  plink2 \
5    ${GENO_FLAG_PLINK} "${GENO_PREFIX}" \
6    --extract "${GENO_QC_PREFIX}_pruned.prune.in" \
7    --pca ${N_PC} \
8    --out "${GENO_QC_PREFIX}_pca" \
9    --threads ${N_THREADS}
```
- L6 `--extract FILE`: keeps only the variants listed (the pruned, QC-passing set).
- L7 `--pca 10`: computes the top 10 PCs. No `approx` modifier is given, so plink2 uses its exact method. That works for 14K samples, though plink2 suggests `approx` for very large cohorts.
- L8 outputs: `…_pca.eigenvec` (one row per sample, tab-separated, header `#FID IID PC1 … PC10`, or `#IID PC1 …` when there is no FID) and `…_pca.eigenval` (the 10 eigenvalues, i.e. variance explained).
- There is no `mkdir`; the script relies on `1-1` having created the folder.

```bash
11-13  # Output files (in output/01_gwas/pca/):
       #   ${GENO_NAME}_pca.eigenvec — per-sample PC values (merged into the phenotype file by 1-3_merge_pc.py)
       #   ${GENO_NAME}_pca.eigenval — variance contribution
```

---

## 1.3 `1-3_merge_pc.py` — add PC columns to the phenotype file

```python
1  #!/usr/bin/env python3
2-11 """ Merges the PCA eigenvec result into the phenotype file and saves it as a new file.
        Must be run after 1-2_pca.sh and before 3-1_qt_step1.sh or 3-2_bt_step1.sh.
        Usage: python3 script/01_gwas/1-3_merge_pc.py --pheno input/HDL.txt
               --eigenvec output/01_gwas/pca/KBA_IMP_pca.eigenvec --out input/HDL_with_pc.txt """
```
⚠ The docstring names scripts that no longer exist: `3-1_qt_step1.sh` / `3-2_bt_step1.sh` should be `2-1_qt_step1.sh` / `2-2_bt_step1.sh` (**I-22**). The eigenvec name in the example assumes `GENO_NAME=KBA_IMP`.

```python
12 import argparse
13 import io
14 import pandas as pd
```
`io` is needed to parse a string as if it were a file (L27).

```python
16 parser = argparse.ArgumentParser()
17 parser.add_argument("--pheno",    required=True, help="phenotype file (FID IID AGE SEX ...)")
18 parser.add_argument("--eigenvec", required=True, help="plink2 PCA output .eigenvec file")
19 parser.add_argument("--out",      required=True, help="output path (saved as a new file)")
20 parser.add_argument("--n-pc",     type=int, default=4, help="number of PCs to merge (default 4)")
21 args = parser.parse_args()
```
Command-line interface. `--n-pc` becomes `args.n_pc` (argparse turns `-` into `_`). Its default of 4 is **independent** of `N_PC=10` in config.sh, but it happens to match `COVAR_COLS` (PC1–PC4).

```python
23 pheno = pd.read_csv(args.pheno, sep="\t")
```
Reads the phenotype table (tab-separated, with a header). It **must contain an `IID` column** (see config.sh L37).

```python
25 with open(args.eigenvec, encoding="utf-8") as f:
26     content = f.read().replace("#IID", "IID")
27 pca = pd.read_csv(io.StringIO(content), sep="\t")
```
Reads the whole eigenvec file as text and renames the header `#IID` to `IID`, then parses the text as a table. If the header is `#FID\tIID\t…`, the `IID` column already has a clean name and the replace does nothing to it (the first column stays `#FID` and is unused).

```python
29 keep = ["IID"] + [f"PC{i+1}" for i in range(args.n_pc)]
30 pca = pca[keep]
```
Keeps `IID, PC1 … PCn` and drops everything else.

```python
32 merged = pheno.merge(pca, on="IID", how="inner")
```
Joins on IID. **Inner** join: samples missing from either table are dropped silently. The FID column comes from the phenotype file. ⚠ If pandas reads IID as a number in one file and as text in the other, the merge can fail or match nothing.

```python
33 merged.to_csv(args.out, sep="\t", index=False)
```
Writes a tab-separated file without the pandas row index. ⚠ Missing values (NaN) are written as **empty fields**, not `NA` (tested: pandas writes `""` / an empty cell). regenie expects `NA` for missing values, so a phenotype with gaps may be misread; `na_rep="NA"` would avoid this (**I-9**). Integer columns that contain NaN also become floats (`1` → `1.0`).

```python
34 import sys
35 sys.stdout.buffer.write(f"done: {len(merged)} samples -> {args.out}\n".encode("utf-8"))
36 sys.stdout.buffer.write(f"cols: {list(merged.columns)}\n".encode("utf-8"))
```
Prints how many samples were kept and the column list, as UTF-8-safe output (README §4).

---

## 1.4 `2-1_qt_step1.sh` — regenie step 1, quantitative trait

```bash
4  mkdir -p "${OUTPUT}/01_gwas/step1"
6   regenie \
7     --step 1 \
8     ${GENO_FLAG_REGENIE} "${GENO_PREFIX}" \
9     --extract "${GENO_QC_PREFIX}_pruned.prune.in" \
10    --phenoFile "${PHENO_QT_FILE}" \
11    --phenoColList ${PHENO_QT} \
12    --covarFile "${PHENO_QT_FILE}" \
13    --covarColList ${COVAR_COLS} \
14    --qt \
15    --bsize 1000 \
16    --lowmem \
17    --lowmem-prefix "${OUTPUT}/01_gwas/step1/tmp_preds" \
18    --out "${OUTPUT}/01_gwas/step1/${PHENO_QT}_step1" \
19    --threads ${N_THREADS}
```
- L7 `--step 1`: fit the whole-genome ridge-regression model.
- L8: the genotypes (`--bed PREFIX` or `--pgen PREFIX`).
- L9 `--extract`: build the model from the **pruned** SNPs only. Using a thinned set of about 0.5 M SNPs is standard practice for step 1.
- L10–11: the phenotype file and which column(s) in it are phenotypes. regenie requires the first two columns to be `FID IID`.
- L12–13: covariates, read from **the same file** (it contains AGE, SEX and PC1–4).
- L14 `--qt`: the trait is quantitative (linear model).
- L15 `--bsize 1000`: the genotype block size for regenie's level-0 ridge regressions.
- L16–17 `--lowmem` + `--lowmem-prefix`: store the intermediate level-0 predictions in temporary files on disk rather than in RAM. ⚠ The prefix `tmp_preds` is the same in `2-2`, so running QT and BT step 1 **at the same time** could collide (**I-23**).
- L18 outputs: `HDL_step1_pred.list` (maps each phenotype to its LOCO file), `HDL_step1_1.loco` (the LOCO predictions for phenotype #1) and `HDL_step1.log`.
  - ⚠ `pred.list` records the `.loco` path as written in `--out`, which is **absolute** here (built from `GWAS_DIR`). Moving or renaming the project folder between step 1 and step 2 would therefore break step 2 (**I-24**; worth confirming).

## 1.5 `2-2_bt_step1.sh` — regenie step 1, binary trait
Identical to `2-1`, except for `PHENO_BT_FILE`, `PHENO_BT` (T2D) and **`--bt`** (binary trait: logistic ridge at level 1). The output is `T2D_step1_pred.list`. The phenotype must be coded 0/1 (or 1/2), with NA for missing.

---

## 1.6 `3-1_qt_step2.sh` — regenie step 2, quantitative trait (optionally per chromosome)

```bash
2-5  # Usage:
     #   bash 4-1_qt_step2.sh          # whole genome
     #   bash 4-1_qt_step2.sh 11       # chr11 only
     #   bash 4-1_qt_step2.sh 11 12    # chr11 and chr12 only
```
⚠ The comment uses an old filename (`4-1_…`); the file is now `3-1_qt_step2.sh` (**I-22**).

```bash
8  mkdir -p "${OUTPUT}/01_gwas/step2"
10 if [ $# -gt 0 ]; then
11   CHR_OPT="--chr $(IFS=,; echo "$*")"
12   SUFFIX="_chr$(IFS=_; echo "$*")"
13 else
14   CHR_OPT=""
15   SUFFIX=""
16 fi
```
- `$#` is the number of command-line arguments.
- `"$*"` joins all arguments using the **first character of `IFS`**. `IFS` is changed only inside the `$( … )` subshell, so the change does not leak out.
- For `bash 3-1_qt_step2.sh 11 12` (tested): `CHR_OPT="--chr 11,12"` and `SUFFIX="_chr11_12"`.
- ⚠ In regenie, **`--chr` takes one chromosome** (repeat the flag to give several), and the comma-separated form is **`--chrList`**. So the single-chromosome case works, but `11 12` probably makes regenie reject `11,12` (**I-8**; check with `regenie --help`).
- ⚠ A per-chromosome run writes `HDL_step2_chr11_HDL.regenie`, but Step 3 hard-codes the genome-wide name `HDL_step2_HDL.regenie` (by design, since LDSC needs the whole genome).

```bash
18  regenie \
19    --step 2 \
20    ${GENO_FLAG_REGENIE} "${GENO_PREFIX}" \
21    --phenoFile "${PHENO_QT_FILE}" \
22    --phenoColList ${PHENO_QT} \
23    --covarFile "${PHENO_QT_FILE}" \
24    --covarColList ${COVAR_COLS} \
25    --pred "${OUTPUT}/01_gwas/step1/${PHENO_QT}_step1_pred.list" \
26    --bsize 400 \
27    --qt \
28    ${CHR_OPT} \
29    --out "${OUTPUT}/01_gwas/step2/${PHENO_QT}_step2${SUFFIX}" \
30    --threads ${N_THREADS}
```
- L19 `--step 2`: test each variant for association.
- L20: the **full** genotype set. There is no `--extract`, so every variant is tested; regenie's default minimum minor-allele count (5) is the only variant filter.
- L21–24: the same phenotype and covariates as step 1 (they must match).
- L25 `--pred`: the step 1 LOCO predictions. regenie reads the list file, which points to the `.loco` file.
- L26 `--bsize 400`: the number of variants tested per block (a memory/speed trade-off).
- L28 `${CHR_OPT}`: deliberately **unquoted**, so `--chr 11` splits into two words, and an empty value disappears.
- L29: regenie adds `_<phenotype>.regenie`, giving **`output/01_gwas/step2/HDL_step2_HDL.regenie`**. This is the central result file for all later steps.

## 1.7 `3-2_bt_step2.sh` — regenie step 2, binary trait
Identical to `3-1` without the chromosome option, using `PHENO_BT*`, `--bt` and the `T2D_step1_pred.list` from step 1. The output is `T2D_step2_T2D.regenie`.
- ⚠ There is **no `--firth --approx` or `--spa`**. For binary traits, especially unbalanced case/control ratios and rare variants, the regenie authors recommend one of these corrections to keep false positives in check. Without them, p-values for low-frequency variants can be inflated (**I-12**).
