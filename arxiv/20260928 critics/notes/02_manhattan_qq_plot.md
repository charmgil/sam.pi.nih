# 02 — Step 2: Manhattan & QQ plot (`script/02_manhattan_qq_plot/plot.py`)

Invocation (from `skill/02_manhattan_qq_plot.md`):
```bash
python3 script/02_manhattan_qq_plot/plot.py \
  --gwas output/01_gwas/step2/HDL_step2_HDL.regenie --out output/02_manhattan_qq_plot --prefix HDL
```

## Background
- **Manhattan plot**: x = genomic position, with chromosomes laid end to end; y = −log10(p). Horizontal lines mark genome-wide significance (5×10⁻⁸) and a "suggestive" level (1×10⁻⁵).
- **QQ plot**: sorted observed −log10(p) against the values expected under the null (uniform p). The shaded band is the 95 % CI of each order statistic. For the i-th smallest of n uniform p-values, that statistic follows Beta(i, n−i+1).
- **λ_GC** (genomic inflation factor) = median(χ²₁ observed) / median(χ²₁ under the null, ≈ 0.4549). Values near 1 mean little inflation. For a polygenic trait in a large sample, a λ somewhat above 1 is expected even without confounding.

---

## Line by line

```python
1  import argparse
2  import pandas as pd
3  import numpy as np
4  import matplotlib
5  matplotlib.use('Agg')
6  import matplotlib.pyplot as plt
7  from scipy import stats
```
Imports. L5 selects a headless backend, and must run **before** `pyplot` is imported. `scipy.stats` provides the χ² and Beta quantile functions.

```python
9  parser = argparse.ArgumentParser()
10 parser.add_argument('--gwas',   required=True, help='regenie step2 result file (.regenie)')
11 parser.add_argument('--out',    required=True, help='output directory')
12 parser.add_argument('--prefix', required=True, help='output file prefix (e.g. HDL)')
13 args = parser.parse_args()
15 import os; os.makedirs(args.out, exist_ok=True)
```
Command-line interface; creates the output folder if it is missing.

```python
17 # ── Load data
18 df = pd.read_csv(args.gwas, sep=' ')
19 df = df[df['LOG10P'] != 'NA'].copy()
20 df['LOG10P'] = df['LOG10P'].astype(float)
21 df['P'] = 10 ** (-df['LOG10P'])
22 df = df.sort_values(['CHROM', 'GENPOS'])
```
- L18: reads the space-separated regenie output.
- L19: meant to drop failed tests, but it is a **no-op** (README §4, **I-10**). `NA` has already become `NaN`. `.copy()` avoids pandas' SettingWithCopy warning.
- L20: makes sure the column is float (it already is).
- L21: converts back to a raw p-value. ⚠ Doubles cannot go below about 1e-308, so any variant with `LOG10P` > ~308 gets **P = 0.0** (tested: `10**-400 → 0.0`). Those points drop out of the QQ plot at L61 (**I-7**). The Manhattan plot is unaffected because it uses `LOG10P`.
- L22: sorts by chromosome, then position. `CHROM` is numeric; regenie codes X as 23.

```python
28 chrom_sizes = df.groupby('CHROM')['GENPOS'].max().reset_index()
29 chrom_sizes.columns = ['CHROM', 'MAX_POS']
30 chrom_sizes = chrom_sizes.sort_values('CHROM')
31 chrom_sizes['OFFSET'] = [0] + list(chrom_sizes['MAX_POS'].cumsum()[:-1])
32 cum_map = dict(zip(chrom_sizes['CHROM'], chrom_sizes['OFFSET']))
33 df['CUMPOS'] = df['GENPOS'] + df['CHROM'].map(cum_map)
```
Builds a single genome-wide x-axis.
- L28–29: the largest observed position on each chromosome (a proxy for its length).
- L31: each chromosome's **offset** is the sum of the lengths of all earlier chromosomes. `cumsum()[:-1]` gives the running totals without the last one, and `[0]` adds the zero for chromosome 1. So chr1 starts at 0, chr2 at max(chr1), and so on.
- L32–33: `CUMPOS` = position within the chromosome + that chromosome's offset.

```python
35 xtick_pos   = df.groupby('CHROM')['CUMPOS'].mean()
36 COLORS = ['#4C72B0', '#DD8452']
```
- L35: the x-tick for each chromosome sits at the **mean** `CUMPOS` of its SNPs. That is roughly the centre, weighted by SNP density.
- L36: two alternating colours (blue, orange).

```python
38 fig, ax = plt.subplots(figsize=(16, 5))
39 for chrom in sorted(df['CHROM'].unique()):
40     sub = df[df['CHROM'] == chrom]
41     ax.scatter(sub['CUMPOS'], sub['LOG10P'],
42                c=COLORS[int(chrom) % 2], s=4, alpha=0.75, linewidths=0)
```
One scatter per chromosome. `int(chrom) % 2` gives 1 for odd chromosomes (orange) and 0 for even ones (blue). `s=4` makes small points; `linewidths=0` removes marker outlines. NaN `LOG10P` values are simply not drawn.

```python
44 ax.axhline(-np.log10(5e-8), color='red',  ls='--', lw=0.8, label='p = 5×10⁻⁸')
45 ax.axhline(-np.log10(1e-5), color='blue', ls=':',  lw=0.8, label='p = 1×10⁻⁵')
46 ax.set_xticks(xtick_pos.values)
47 ax.set_xticklabels(xtick_pos.index.astype(str), fontsize=7)
48 ax.set_xlabel('Chromosome')
49 ax.set_ylabel('-log₁₀(P)')
50 ax.set_title(f'{args.prefix} Manhattan Plot')
51 ax.legend(fontsize=8)
52 plt.tight_layout()
53 plt.savefig(f'{args.out}/{args.prefix}_manhattan.png', dpi=180)
54 plt.close()
```
The significance lines (y ≈ 7.30 and 5.00), chromosome tick labels, axis titles, a legend (only the two lines carry labels), and the saved **`{prefix}_manhattan.png`** at 180 dpi. `plt.close()` frees the figure.

```python
60 pvals = df['P'].values
61 pvals = pvals[pvals > 0]
62 n = len(pvals)
```
The p-values as a NumPy array. `> 0` removes **NaN** (because `NaN > 0` is False), which is what actually drops failed tests. It also removes the **underflowed zeros** from L21 (**I-7**).

```python
64 obs = -np.log10(np.sort(pvals))          # ascending sort → small p goes to the back
65 exp = -np.log10(np.arange(1, n+1) / n)
```
- L64: after an ascending sort the **smallest p comes first**, so `obs` runs from largest to smallest. ⚠ The Korean comment says "small p goes to the back", which is backwards for p (it is true for `obs`). The code is correct.
- L65: expected quantiles i/n for i = 1..n, also running from largest to smallest −log10. So `obs[k]` pairs with `exp[k]`, the k-th most significant with the k-th expected. Note that `(i−0.5)/n` is also common; with `i/n` the last expected value is exactly 0.

```python
67 chi2_obs = stats.chi2.ppf(1 - pvals, df=1)
68 lam_gc   = np.median(chi2_obs) / stats.chi2.ppf(0.5, df=1)
```
Converts each p to its 1-df χ² value (the inverse survival function) and computes λ_GC = median / 0.4549. `1 - p` loses precision for tiny p, but that does not change the median. regenie's own `CHISQ` column could have been used instead.

```python
70 ranks = np.arange(1, n+1)
71 ci_upper = -np.log10(stats.beta.ppf(0.025, ranks, n - ranks + 1))
72 ci_lower = -np.log10(stats.beta.ppf(0.975, ranks, n - ranks + 1))
```
The 95 % band for each order statistic: the i-th smallest uniform p follows Beta(i, n−i+1). The 2.5 % quantile of p gives the **upper** −log10 bound, and the 97.5 % quantile gives the lower one. (The skill doc calls this "binomial"; it is actually a Beta order-statistic band.) This makes n quantile calls, which is slow but workable for a few million SNPs.

```python
74 fig, ax = plt.subplots(figsize=(6, 6))
75 ax.fill_between(exp, ci_lower, ci_upper, alpha=0.2, color='grey', label='95% CI')
76 ax.plot([0, exp.max()], [0, exp.max()], 'r--', lw=0.8)
77 ax.scatter(exp, obs, c='#4C72B0', s=6, linewidths=0)
78 ax.set_xlabel('Expected -log₁₀(P)')
79 ax.set_ylabel('Observed -log₁₀(P)')
80 ax.set_title(f'{args.prefix} QQ Plot  (λ_GC = {lam_gc:.3f})')
81 ax.legend(fontsize=8)
82 plt.tight_layout()
83 plt.savefig(f'{args.out}/{args.prefix}_qq.png', dpi=180)
84 plt.close()
```
A square figure: the grey CI band, the red dashed y = x reference line, the observed points, and λ_GC in the title. Saved as **`{prefix}_qq.png`**.

```python
86 import sys
87 sys.stdout.buffer.write(f'lambda_GC = {lam_gc:.4f}\n'.encode('utf-8'))
88 sys.stdout.buffer.write(f'Done: {args.out}/{args.prefix}_manhattan.png / _qq.png\n'.encode('utf-8'))
```
Prints λ_GC and the output paths (UTF-8-safe).

**Outputs:** `output/02_manhattan_qq_plot/{prefix}_manhattan.png` and `{prefix}_qq.png`.
