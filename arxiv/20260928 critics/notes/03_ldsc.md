# 03 — Step 3: LD Score Regression (`script/03_ldsc/`)

Execution order: **`02_ldsc.sh`** (the entry point) runs, in sequence, `01_input.py` (python3) → `munge_sumstats.py` (Python 2.7, external) → `ldsc.py --h2` (Python 2.7, external). **`03_plot.py`** is a separate command run afterwards.

## Background
- **LD score** ℓⱼ of SNP j = Σₖ r²ⱼₖ, summed over nearby SNPs. A SNP in a high-LD region "tags" more causal variation.
- Under a polygenic model, **E[χ²ⱼ] ≈ N·h²·ℓⱼ / M + N·a + 1**. Regressing the GWAS χ² statistics on LD scores therefore gives:
  - a **slope** proportional to **SNP heritability h²**;
  - an **intercept**, where ≈ 1 means inflation comes from polygenicity and > 1 points to confounding such as population stratification.
- `ldsc` needs precomputed LD scores for a **reference population**. Here that is 1000 Genomes Phase 3 **EAS** (East Asian), which matches the Korean cohort, restricted to HapMap3 SNPs.
- SNPs are matched **by rsID**. regenie reports position-based array IDs, so an rsID mapping step (`pos2rsid.txt`) is needed.

---

## 3.1 `02_ldsc.sh` — orchestrator

```bash
1  #!/bin/bash
2  source "$(dirname "$0")/../config.sh"
4  PHENO="${PHENO_QT}"          # phenotype to analyse (QT: PHENO_QT / BT: PHENO_BT)
5  LDSC_DIR="${RESOURCE}/LDSC"
6  MUNGE="${HOME}/ldsc/munge_sumstats.py"
7  LDSC="${HOME}/ldsc/ldsc.py"
8  PY27="${HOME}/miniconda3/envs/ldsc/bin/python"  # Python 2.7 environment dedicated to ldsc
10 mkdir -p "${OUTPUT}/03_ldsc"
```
- L4: the phenotype is **hard-coded to the QT phenotype**. To analyse T2D you would edit this line.
- L5: the reference folder (`baseline.*`, weights, `pos2rsid.txt`).
- L6–7: the `ldsc` repository is assumed to be cloned at `~/ldsc` (`resource_downloads.md`).
- L8: ldsc is Python 2 code, so it runs with a dedicated conda env interpreter. Running it with python3 gives `TabError`, because the source mixes tabs and spaces.
- These paths sit **outside the project** (`$HOME`), unlike everything else, so they are machine-specific.

```bash
12 # ── Step 1: GWAS result → munge_sumstats input format
13 python3 "$(dirname "$0")/01_input.py" \
14   --gwas     "${OUTPUT}/01_gwas/step2/${PHENO}_step2_${PHENO}.regenie" \
15   --pos2rsid "${LDSC_DIR}/pos2rsid.txt" \
16   --out      "${OUTPUT}/03_ldsc/${PHENO}_for_munge.tsv"
```
Calls the converter (see 3.2). The input file name is the **genome-wide** step 2 output.

```bash
18 # ── Step 2: munge_sumstats
19 "${PY27}" "${MUNGE}" \
20   --sumstats "${OUTPUT}/03_ldsc/${PHENO}_for_munge.tsv" \
21   --snp SNP \
22   --a1  A1 \
23   --a2  A2 \
24   --signed-sumstats BETA,0 \
25   --p P \
26   --N-col N \
27   --out "${OUTPUT}/03_ldsc/${PHENO}_munged"
```
`munge_sumstats.py` standardises summary statistics into ldsc's format: `SNP A1 A2 Z N`.
- L21–23: which columns hold the rsID, the effect allele and the other allele.
- L24 `--signed-sumstats BETA,0`: the sign of the effect comes from `BETA`, whose null value is 0. munge turns P into |Z| and gives it BETA's sign.
- L25–26: the p-value column and the per-SNP sample-size column.
- It also recognises the `FRQ` column automatically and applies its default filters. It drops SNPs with MAF < 0.01, strand-ambiguous SNPs (A/T and C/G), non-SNP alleles, duplicated rsIDs, missing values, and out-of-range p-values. The unrecognised `CHISQ` column is ignored.
- ⚠ The usual `--merge-alleles w_hm3.snplist` is **not used**. Restricting to HapMap3 SNPs, and checking alleles against them, happens only implicitly: `pos2rsid.txt` apparently contains only EAS HM3 SNPs (`skill/03_ldsc.md`: "only EAS HM3 SNPs remain"). No allele check against a reference is done (**I-15**).
- Output: `{P}_munged.sumstats.gz` and `{P}_munged.log`.

```bash
29 # ── Step 3: LD score regression (h²)
30 "${PY27}" "${LDSC}" \
31   --h2 "${OUTPUT}/03_ldsc/${PHENO}_munged.sumstats.gz" \
32   --ref-ld-chr "${LDSC_DIR}/baseline." \
33   --w-ld-chr   "${LDSC_DIR}/1000G_Phase3_EAS_weights_hm3_no_MHC/weights.EAS.hm3_noMHC." \
34   --out "${OUTPUT}/03_ldsc/${PHENO}_h2"
```
- L31 `--h2`: estimate SNP heritability from the munged file.
- L32 `--ref-ld-chr PREFIX`: ldsc adds `1..22` and `.l2.ldscore.gz` (it also reads the matching `.l2.M_5_50`), so it loads `baseline.1.l2.ldscore.gz` … `baseline.22.…`. All 22 chromosomes must be present. These are the **baseline model v1.2** scores (Finucane et al. 2015; about 50 functional annotations plus the all-SNP `base` annotation), from `1000G_Phase3_EAS_baseline_v1.2_ldscores`. `--h2` with a multi-annotation model fits them jointly and reports the **total** h². That is valid, but it differs from the more common single-annotation "LD score" h².
- L33 `--w-ld-chr`: the regression-weight LD scores (HM3 SNPs, MHC removed).
- L34: writes `{P}_h2.log`, which contains `Total Observed scale h2: X (SE)`, `Lambda GC`, `Mean Chi^2`, `Intercept` and `Ratio`.
- ⚠ The script has no `set -e`: if step 1 or 2 fails, the later commands still run on stale or missing files (**I-16**).

---

## 3.2 `01_input.py` — regenie result → munge input

```python
1  import argparse
2  import sys
3  import pandas as pd
5-9  argparse: --gwas (regenie step2 result), --pos2rsid (path to pos2rsid.txt), --out (output .tsv path)
```

```python
11 gwas = pd.read_csv(args.gwas, sep=' ')
12 gwas = gwas[gwas['CHISQ'] != 'NA'].copy()
13 gwas['CHISQ'] = gwas['CHISQ'].astype(float)
14 gwas['LOG10P'] = gwas['LOG10P'].astype(float)
15 gwas['P'] = 10 ** (-gwas['LOG10P'])
```
- L12: the same **no-op filter** as in `plot.py` (**I-10**). NaN rows go through and are written as **empty fields** (L33). munge splits columns on whitespace, so consecutive tabs merge and the remaining values **shift left into the wrong columns**. Tested: a row with empty BETA/CHISQ/P gets `BETA=14000` (the N value) and P = NaN. That row still ends up with a missing P and N, so munge drops it; the final result is correct **by luck**, not by design (**I-9**, **I-10**).
- L15: back to raw p. ⚠ It underflows to 0 when LOG10P > ~308, and munge's p-value bounds check (0 < p ≤ 1) would then drop the strongest SNPs (**I-7**). The effect on h² is small, because `ldsc` removes SNPs with χ² > max(80, 0.001·N) anyway.

```python
17 pos2rsid = pd.read_csv(args.pos2rsid, sep='\t', header=None,
18                        names=['CHROM', 'GENPOS', 'SNP'])
19 gwas_rsid = gwas.merge(pos2rsid, on=['CHROM', 'GENPOS'], how='inner')
```
- L17–18: reads a headerless, 3-column lookup table (chromosome, position, rsID).
- L19: attaches rsIDs by **position only** (inner join). Unmatched SNPs are dropped, which is expected; skill/03 says the SNP count falls to the HM3 set.
- ⚠ **Alleles are ignored.** A different variant at the same position, such as an indel or another allele of a multi-allelic site, gets that rsID too. Two variants at one position produce duplicate rsIDs, which munge then removes. The genome build of `pos2rsid.txt` must match the GWAS (hg19) (**I-15**).

```python
21 sys.stdout.buffer.write(f'total SNPs: {len(gwas):,}  ->  rsID matched: {len(gwas_rsid):,}\n'.encode('utf-8'))
```
Reports the counts before and after mapping (`:,` adds thousands separators).

```python
23 out_df = pd.DataFrame({
24     'SNP':  gwas_rsid['SNP'],
25     'A1':   gwas_rsid['ALLELE1'],
26     'A2':   gwas_rsid['ALLELE0'],
27     'BETA':  gwas_rsid['BETA'],
28     'CHISQ': gwas_rsid['CHISQ'],
29     'P':     gwas_rsid['P'],
30     'N':     gwas_rsid['N'],
31     'FRQ':  gwas_rsid['A1FREQ'],
32 })
33 out_df.to_csv(args.out, sep='\t', index=False)
34 sys.stdout.buffer.write(f'saved: {args.out}\n'.encode('utf-8'))
```
Renames columns to what munge expects. **A1 = regenie `ALLELE1`**, the effect allele, so the sign of BETA is aligned correctly. `FRQ` = the frequency of A1. munge only uses it to compute MAF. Writes `{P}_for_munge.tsv`.

---

## 3.3 `03_plot.py` — binned LD-score-vs-χ² plot (run separately)

```bash
python3 script/03_ldsc/03_plot.py --sumstats output/03_ldsc/HDL_munged.sumstats.gz \
  --ldsc-dir resource/LDSC --out output/03_ldsc --prefix HDL --h2-log output/03_ldsc/HDL_h2.log
```

```python
1  import argparse
2  import gzip
3  import numpy as np
4  import pandas as pd
5  import matplotlib.pyplot as plt
```
⚠ Unlike the other plotting scripts, this one does **not** call `matplotlib.use('Agg')`. Recent matplotlib versions fall back to Agg when no display is available, so this usually still works.

```python
7-15 argparse:
  --sumstats  path to munged sumstats.gz
  --ldsc-dir  baseline LD score directory (where baseline.{chr}.l2.ldscore.gz lives)
  --out       output directory
  --prefix    output file prefix (phenotype name)
  --bins      number of bins (default 100, as in the original paper)
  --ylim      y-axis range, two floats (default 0.5 1.5)
  --h2-log    optional path to the ldsc.py --h2 log (to print h²_SNP)
```

```python
17 # ── 1. Load sumstats and compute chi-square
18 with gzip.open(args.sumstats, 'rt') as f:
19     sumstats = pd.read_csv(f, sep='\t')
20 sumstats['CHISQ'] = sumstats['Z'] ** 2
```
Opens the gzip file in text mode (`'rt'`) and reads `SNP A1 A2 Z N`. χ² = Z² (1 df).

```python
22 # ── 2. Load baseline LD scores (chr1–22)
23 ld_list = []
24 for chrom in range(1, 23):
25     path = f'{args.ldsc_dir}/baseline.{chrom}.l2.ldscore.gz'
26     df = pd.read_csv(path, sep='\t', compression='gzip')
27     ld_list.append(df[['SNP', 'baseL2']])
28 ld = pd.concat(ld_list, ignore_index=True)
```
Loads all 22 chromosome files and keeps only `SNP` and `baseL2`, the LD score of the all-SNPs "base" annotation in the baseline model. That is the ordinary LD score; the functional annotations are ignored here.

```python
30 merged = sumstats.merge(ld, on='SNP', how='inner')
31 print(f"Merged SNPs: {len(merged):,}")
```
Joins on rsID. This uses plain `print`, not the UTF-8 byte writer, which is fine because the text is ASCII.

```python
33 # ── 3. Percentile-based binning
34 bins = np.percentile(merged['baseL2'], np.linspace(0, 100, args.bins + 1))
35 bins = np.unique(bins)
36 merged['bin'] = pd.cut(merged['baseL2'], bins=bins, include_lowest=True)
37 binned = merged.groupby('bin', observed=True).agg(
38     mean_ld=('baseL2', 'mean'),
39     mean_chisq=('CHISQ', 'mean')
40 ).dropna()
```
- L34: 101 edges at the 0th, 1st, …, 100th percentiles of LD score, so each bin holds about 1 % of SNPs.
- L35: removes duplicate edges (ties), which `pd.cut` would reject.
- L36: assigns each SNP to a bin; `include_lowest` includes the minimum value.
- L37–40: for each bin, the mean LD score (x) and mean χ² (y). `observed=True` skips empty categorical bins. `dropna` is a safety net.

```python
42 x = binned['mean_ld'].values
43 y = binned['mean_chisq'].values
44 coeffs = np.polyfit(x, y, 1)
45 slope, intercept = coeffs
```
A simple **unweighted least-squares** line through the ~100 bin means. It is for display only. The real estimate is ldsc's weighted regression over individual SNPs, which is in the `.log` file.

```python
47 # ── 4. Parse h² (if a log file is given)
48 h2_str = None
49 if args.h2_log:
50     import re
51     h2_val = se_val = lambda_val = None
52     with open(args.h2_log) as f:
53         for line in f:
54             m = re.search(r'Total Observed scale h2:\s*([\d.]+)\s*\(([\d.]+)\)', line)
55             if m:
56                 h2_val, se_val = m.group(1), m.group(2)
57             m2 = re.search(r'Lambda GC:\s*([\d.]+)', line)
58             if m2:
59                 lambda_val = m2.group(1)
60     parts = []
61     if h2_val:
62         parts.append(f"h²_SNP = {h2_val} (SE = {se_val})")
63     if lambda_val:
64         parts.append(f"λ_GC = {lambda_val}")
65     if parts:
66         h2_str = "  |  ".join(parts)
```
Scans the ldsc log line by line. L54 captures `h2` and its `SE` from `Total Observed scale h2: 0.1234 (0.0123)`. L57 captures `Lambda GC: 1.05`. Whatever it finds is joined into one subtitle string; if nothing is found, `h2_str` stays `None`. The values are kept as strings, exactly as printed in the log. ⚠ `[\d.]+` does not match a **minus sign** or **scientific notation**. A negative h² estimate, which is possible with low power, or a value like `1e-04` would be skipped silently and left out of the title (**I-25**).

```python
68 # ── 5. Plot
69 fig, ax = plt.subplots(figsize=(8, 6))
70 ax.scatter(x, y, s=25, color='steelblue', alpha=0.8, zorder=3)
72 x_range = np.linspace(0, x.max() * 1.05, 300)
73 ax.plot(x_range, slope * x_range + intercept, color='red', linewidth=2,
74         label=f'Slope = {slope:.5f}\nIntercept = {intercept:.4f}')
75 ax.axhline(y=intercept, color='gray', linestyle='--', linewidth=1, alpha=0.6)
77 ax.set_xlim(0, x.max() * 1.05)
78 ax.set_ylim(args.ylim[0], args.ylim[1])
79 ax.set_xlabel('LD Score', fontsize=13)
80 ax.set_ylabel(r'Mean $\chi^2$', fontsize=13)
81 title = f'LD Score Regression ({args.prefix})'
82 if h2_str:
83     title += f'\n{h2_str}'
84 ax.set_title(title, fontsize=13)
85 ax.legend(fontsize=11, loc='upper left')
```
- L70: the bin means as points. `zorder=3` draws them above the line.
- L72–74: the fitted line, evaluated from x = 0 to 5 % beyond the largest bin so the intercept is visible. The slope and intercept go in the legend.
- L75: a dashed horizontal reference line at the intercept.
- L80: `$\chi^2$` is matplotlib mathtext, rendered as χ².
- L81–84: the title, plus the h² / λ line when a log was parsed.
- ⚠ The **fixed y-range of 0.5–1.5** would clip bins whose mean χ² exceeds 1.5. That can happen for a highly polygenic trait in a large sample; the user can override it with `--ylim`.

```python
87 import os
88 os.makedirs(args.out, exist_ok=True)
89 out_path = f'{args.out}/{args.prefix}_ldsc_regression.png'
90 plt.tight_layout()
91 plt.savefig(out_path, dpi=150)
92 print(f"saved: {out_path}")
```
Saves **`{prefix}_ldsc_regression.png`**.

**Outputs of Step 3:** `{P}_for_munge.tsv`, `{P}_munged.sumstats.gz` (+ `.log`), `{P}_h2.log`, `{P}_ldsc_regression.png`, all in `output/03_ldsc/`.
