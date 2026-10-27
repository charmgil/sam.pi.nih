# 00 — Harness layer (`prompt.txt`, `CLAUDE.md`, `skill/`) and `script/config.sh`

The Markdown and text files are summarised **section by section** because they are prose, not code. `config.sh` is explained **line by line**.

---

## A. `prompt.txt` — the workshop script (translated)

This file is not read by Claude. The instructor uses it to run the session.

| Lines | Meaning |
|---|---|
| 2–6 | **Free plan:** work in claude.ai Home (chat) with the Haiku model (listed as the "extended" option). Set the working folder by asking Claude to open `…\Downloads\2026_KOGO_WORKSHOP\GWAS_Windows` (Windows) or `…/GWAS` (Mac) through **Desktop Commander**, an MCP server that gives chat-Claude access to local files and a shell. |
| 7 | Holds the Mac path **and** the header `# 유료` ("Paid") on one line. A newline is missing (a typo). |
| 8–10 | **Paid plan:** work in Claude Code with Sonnet. Pick the working folder by clicking the folder icon. |
| 12–16 | *(10+10 min)* Prompt: "Using CLAUDE.md, run an HDL GWAS on `input/KBAv2.0_KOGO_IMP.vcf.gz`. Check whether the needed programs exist, download any that are missing, then analyse." **Checks:** only the programs actually needed get installed; `pgen` and `HDL_pc.txt` appear in `input/`; results appear in the `plink2` and `pca` folders under `output/01_gwas`. ⚠ The scripts write `step1/`, `step2/` and `pca/` (there is no `plink2/` folder), and they name the merged phenotype file `{P}_with_pc.txt`, not `HDL_pc.txt`. The checklist seems to target an older layout (**I-20**). |
| 18–21 | *(5 min)* Manhattan + QQ plot. **Check:** plots appear in `output/02_manhattan_qq_plot`. |
| 23–26 | *(5 min)* LDSC. **Check:** results appear in `output/03_ldsc`. |
| 28–31 | *(5 min)* Regional plot. **Check:** Claude picks from the top signals and should end up at **`11:116662579`** (hg19, inside *APOA5* in the *APOA5–APOA4–APOC3–APOA1* cluster). Plot appears in `output/04_regional_plot`. |
| 33–36 | *(10 min)* SuSiE. **Check:** Claude picks a top signal, or the same SNP used for the regional plot; results appear in `output/05_susie`. |

**Takeaway:** each block pairs a natural-language prompt with a list of observable post-conditions (files that should exist, tools that should or should not be installed, which SNP was chosen). A general framework could encode these as automated checks.

---

## B. `CLAUDE.md` — project instructions for Claude (translated summary)

| Lines | Section | Content |
|---|---|---|
| 1–3 | Title | "GWAS Analysis Guide: run GWAS on quantitative and binary traits using genomic data, then visualise and do post-GWAS analysis." |
| 7–10 | **Execution principles** | (1) **Run only up to the requested step.** "Do the GWAS analysis" means Step 1 only (regenie step 1 and 2). Steps 2–5 run only when explicitly asked, or on "run the whole pipeline". After each step, report the results and ask before continuing. (2) **Check only the programs that step needs.** Do not audit the whole tool table up front. Step 1: plink2, regenie, python3. Step 2: python3. Step 3: python3, Python 2.7 for ldsc, LDSC reference panel. Step 4: plink2, python3, genetic map. Step 5: R, susieR. |
| 14–22 | Step table | Links each step to its `skill/0X_*.md` guide. |
| 26–53 | Directory tree | `input/`, `resource/{LDSC,dbSNP,genetic_map}`, `script/…`, `skill/…`, `output/`. The note "(edit only here)" is on `config.sh`. |
| 57–69 | Tool versions | plink2 v2.0.0-a.7.1, regenie v4.1, python3 3.6.8, python2 2.7 (ldsc only, `~/miniconda3/envs/ldsc/bin/python`), R 4.4.0, susieR 0.14.2, ldsc. PATH note: `export PATH="$HOME/bin:$PATH"`. ⚠ `02_plot.py` calls `Series.between(..., inclusive='left')`, which needs pandas ≥ 1.3, and pandas 1.3 needs Python ≥ 3.7. So "3.6.8" cannot be the environment the scripts actually ran in (**I-19**). |
| 73–91 | Config template | A **simplified** placeholder version of `config.sh`. The real file differs: it has `GWAS_DIR` auto-detection, `GENO_PREFIX`, `GENO_QC_PREFIX` and format auto-detection. |
| 95–150 | Reference command sequence | Full pipeline as shell commands with `{phenotype}`, `{chr}`, `{pos}` placeholders. Line 97 says it is for reference only; do not auto-advance between steps. ⚠ Lines 109 and 123 read `python3 … \     # comment`. A backslash followed by spaces is **not** a line continuation, so the next line (`--pheno …`) would run as a separate command. The block cannot be pasted as-is (**I-18**). |
| 153–159 | Common cautions | Missing paths in config.sh make everything fail. `1-3_merge_pc.py` is mandatory (regenie step 1 fails without PC columns). `munge_sumstats.py` and `ldsc.py` are Python 2.7 only (python3 gives `TabError`). LDSC needs genome-wide results. For regional plot and SuSiE, edit `LEAD_CHR`, `LEAD_POS` and `LEAD_SNP`. |

## C. `skill/*.md` — per-step guides (what each tells Claude)

Each step note (01–05) repeats the parts that matter for that step. In short:

- **`01_gwas.md`**: script table. **"Step 0" rule:** look in `input/` first. If `{GENO_NAME}.bed/.bim/.fam` exist, **skip** VCF→pgen (config.sh auto-detects `--bfile`/`--bed`). Only convert when there is just a VCF. It also gives the QC thresholds (MAF ≥ 0.1, HWE p ≥ 0.001, call rate ≥ 0.99), covariates (AGE, SEX, PC1–4), block sizes (1000 / 400), and output folders. Notes: regenie v4.1 dropped `--no-fid`; step 2's `--pred` = step 1's `--out` + `_pred.list`. ⚠ The eigenvec name in the examples (`KBA_IMP_pca.eigenvec`) only holds when `GENO_NAME=KBA_IMP`.
- **`02_manhattan_qq_plot.md`**: the command, and that `LOG10P` is used directly. Manhattan lines at 5e-8 and 1e-5; the QQ plot shows λ_GC and a 95 % CI. ⚠ It calls the CI "binomial"; the code actually uses Beta order-statistic quantiles.
- **`03_ldsc.md`**: `02_ldsc.sh` runs three things in order. It names the EAS reference-panel paths, notes that all 22 chromosomes are needed, lists outputs, and gives the plot command (with `--h2-log`, which the `CLAUDE.md` version omits). It also notes that a drop in SNP count after the pos2rsid mapping is expected.
- **`04_regional_plot.md`**: (1) run an **inline Python snippet** that lists independent genome-wide-significant peaks, and **let the user choose**; (2) write the choice into config.sh; (3) run `01_input.sh` + `02_plot.py`. It also gives the LD colour legend, genetic-map source, gene-track source (Ensembl REST), and the SuSiE overlay variant.
- **`05_susie.md`**: set the target in config.sh, run `01_input.sh`, then `Rscript 02_susie.R <gwas> <ld_prefix> <out_dir> <chr> <pos> <window> <n_sample>`. Settings: L = 10, coverage 0.95, `min_abs_corr` 0.1. It describes the plot layout and how to interpret results, and says `n_sample` = the `N` column of the regenie output.
- **`resource_downloads.md`**: download commands for dbSNP b155 (hg19/hg38, ~20–30 GB), LDSC EAS baseline LD scores and weights (Zenodo 7768714; the Broad server now charges), the `ldsc` repo (`git clone … ~/ldsc`), and Beagle genetic maps (GRCh37/38). It states that **the current analysis is hg19**.

---

## D. `script/config.sh` — line by line

```bash
1  #!/bin/bash
```
Shebang. It has no real effect, because the file is always `source`d and never executed directly.

```bash
2-4  # ═══ Common settings for the GWAS practical — you only need to edit this file ═══
6    # ── Paths (set automatically from where config.sh lives — no need to edit)
7    GWAS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
```
- `${BASH_SOURCE[0]}` is the path of **the file currently being read** (config.sh). Inside a sourced file this differs from `$0`, which would be the calling script.
- `dirname …` gives `…/script`, `cd …/..` moves to the project root, and `pwd` prints it as an absolute path. All of this runs in a `$( … )` subshell, so the caller's working directory does not change.
- Result: `GWAS_DIR` is the absolute project root, whatever the current directory is. ⚠ `BASH_SOURCE` exists only in **bash**. Under `sh` (dash) or when sourced from zsh it is empty, and `GWAS_DIR` becomes the parent of the current directory (**I-17**).

```bash
8   INPUT="${GWAS_DIR}/input"
9   OUTPUT="${GWAS_DIR}/output"
10  RESOURCE="${GWAS_DIR}/resource"
```
The three top-level data folders, as absolute paths.

```bash
12  # ── PATH (include every location where plink2, regenie, etc. are installed)
13  export PATH="$HOME/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"
```
Puts the usual install locations first on the search path. `export` makes this apply to child processes such as `plink2`, `regenie` and `python3`. It is the **only** exported variable; the others are plain shell variables that the sourcing script can see but Python and R cannot.

```bash
15  # ── Input VCF (the original 213 GB VCF was deleted — use the existing bfile as-is, no pgen conversion)
16  VCF_FILE="${INPUT}/KBAv2.0AB_14K_COMMON_REHEADER_SORT_PHASING_IMPUTATION_HWE1E-6_R20.8.vcf.gz"   # input VCF filename
```
Path to the VCF, used only by `0_vcf_to_pgen.sh`. The comment shows that **this config describes the author's own run** on a 14K-sample KBA v2.0 dataset that is already in bed format. It is not the workshop dataset (`KBAv2.0_KOGO_IMP.vcf.gz`, per `prompt.txt`). Claude is expected to rewrite these values for the workshop.

```bash
18  # ── Genotype prefix
19  GENO_NAME="KBAv2.0AB_14K_COMMON"
20  GENO_PREFIX="${INPUT}/${GENO_NAME}"                  # shared path for bed/bim/fam or pgen/pvar/psam
21  GENO_QC_PREFIX="${OUTPUT}/01_gwas/pca/${GENO_NAME}"  # prefix for pruned / pca outputs
```
- `GENO_NAME` is the basename of the genotype files. Note that it does **not** come from the VCF name.
- `GENO_PREFIX` is what plink2 and regenie get after `--bfile`, `--pfile`, `--bed` or `--pgen`. Those tools add the extensions themselves.
- `GENO_QC_PREFIX` is the stem for pruning and PCA outputs (`…_pruned.prune.in`, `…_pca.eigenvec`).

```bash
23-25  # ── Auto-detect genotype input format
       #    if input/${GENO_NAME}.bed already exists, use it without pgen conversion (--bfile / --bed)
       #    if not and only .pgen exists, it came from VCF→pgen conversion, so use that (--pfile / --pgen)
26  if [ -f "${GENO_PREFIX}.bed" ]; then
27    GENO_FLAG_PLINK="--bfile"
28    GENO_FLAG_REGENIE="--bed"
29  elif [ -f "${GENO_PREFIX}.pgen" ]; then
30    GENO_FLAG_PLINK="--pfile"
31    GENO_FLAG_REGENIE="--pgen"
32  fi
```
- `[ -f X ]` is true when X is an existing regular file.
- **bed takes priority** over pgen.
- The check runs **each time config.sh is sourced**, so once `0_vcf_to_pgen.sh` creates a `.pgen`, later scripts pick `--pfile`/`--pgen` automatically.
- ⚠ If neither file exists, both flags stay **unset**. Scripts then call `plink2 "<prefix>" …` with no input flag and fail with a confusing error rather than a clear message (**I-16**). `0_vcf_to_pgen.sh` is not affected because it does not use these flags.
- plink2 and regenie use different flag names for the same format (`--bfile` vs `--bed`, `--pfile` vs `--pgen`), which is why there are two variables.

```bash
34  # ── Phenotype files & column names
35  PHENO_QT_FILE="${INPUT}/KBAv2.0AB_14K_HDL_with_pc.txt"
36  PHENO_QT="HDL"
37  # the phenotype file was in ID,SEX,AGE,HDL format, so before running 1-3_merge_pc.py
    # an FID column had to be added and ID renamed to IID
```
- `PHENO_QT_FILE` is the **output** of `1-3_merge_pc.py` (the phenotype file with PC columns). It serves as both `--phenoFile` and `--covarFile` for the quantitative-trait (QT) regenie runs.
- `PHENO_QT` is the column name of the phenotype. regenie uses it to name output files (`HDL_step2_HDL.regenie`).
- Line 37 records a **manual preprocessing step that no script does**. The raw phenotype file had `ID`; regenie needs `FID IID` as the first two columns. The author added FID and renamed ID→IID by hand, or had Claude do it.

```bash
39  PHENO_BT_FILE="${INPUT}/T2D_with_pc.txt"
40  PHENO_BT="T2D"
```
The same pair for the binary-trait (BT) runs (`2-2`, `3-2`), using type 2 diabetes as the example.

```bash
42  # ── Covariates
43  COVAR_COLS="AGE,SEX,PC1,PC2,PC3,PC4"
```
A comma-separated list passed to regenie `--covarColList`. These columns must exist in the phenotype file, which is why `1-3_merge_pc.py` has to run first. Only 4 PCs are used, although 10 are computed (`N_PC`).

```bash
45  # ── Regional plot / fine-mapping target region
46  LEAD_CHR=16
47  LEAD_POS=56994528
48  LEAD_SNP="AX-95823215|chr16:56960616:C:T"   # the actual variant ID in the bim (needed for LD calculation --ld-snp)
49  WINDOW=500000                                # lead SNP ± 500 kb
```
- The target locus for Steps 4 and 5. The current value is chr16:56.99 Mb, in the ***CETP*** region, a classic HDL locus.
- `LEAD_SNP` must **exactly match the ID column** of the bim/pvar (and so the `ID` column in the regenie output). Here it is an Affymetrix array probe ID with a coordinate string attached.
- ⚠ The position inside the ID (56,960,616) is **33,912 bp** lower than `LEAD_POS` (56,994,528). That offset matches the GRCh37→GRCh38 shift near *CETP*, so the **ID string probably carries hg38 coordinates while the `GENPOS` values are hg19** (not verified; check with liftOver). Any code that parsed positions out of IDs would be wrong here (**I-21**).
- `WINDOW` is the half-width of the region.
- Claude rewrites these after the user picks a peak in Step 4. For the workshop the expected values are `LEAD_CHR=11`, `LEAD_POS=116662579`.

```bash
51  # ── Common options
52  N_PC=10
53  N_THREADS=4
```
- `N_PC` is the number of PCs that `1-2_pca.sh` computes. `1-3_merge_pc.py` does **not** read it; it has its own `--n-pc` default of 4.
- `N_THREADS` is the thread count for plink2 and regenie.
