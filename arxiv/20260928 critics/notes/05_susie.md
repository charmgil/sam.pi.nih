# 05 — Step 5: Fine-mapping with SuSiE (`script/05_susie/`)

Execution order: `01_input.sh` (LD matrix) → `02_susie.R` (fine-mapping, tables, 2-panel plot). At the end, `02_susie.R` **calls `04_regional_plot/02_plot.py` itself** to draw the SuSiE overlay version of the regional plot.

(`script/05_susie/.Rhistory` is an empty R session-history file, a leftover of interactive R. It is not part of the pipeline.)

## Background
- **Fine-mapping** asks which SNP(s) in an associated region are most likely causal, given that LD makes many SNPs look alike.
- **SuSiE** (Sum of Single Effects) models the signal as the sum of up to **L** single-effect components, each with exactly one causal SNP.
  - For each component it gives a posterior distribution over SNPs, and from that a **95 % credible set (CS)**: the smallest set of SNPs that holds the causal one with 95 % probability.
  - **PIP** (posterior inclusion probability) is the probability that a SNP has a non-zero effect in any component.
  - **Purity** is the smallest absolute correlation between members of a CS. CSs below `min_abs_corr` are thrown out as not meaningful.
- **SuSiE-RSS** runs from summary statistics (β̂ and SE, or z) plus an **LD correlation matrix R** and sample size n, with no individual-level data. The **signs** in R and β̂ must refer to the **same allele**, and R should come from the same samples (in-sample LD) where possible.

---

## 5.1 `01_input.sh` — signed LD correlation matrix for the region

```bash
1  #!/bin/bash
2  source "$(dirname "$0")/../config.sh"
4  mkdir -p "${OUTPUT}/05_susie"
6  FROM_BP=$(( LEAD_POS - WINDOW ))
7  TO_BP=$(( LEAD_POS + WINDOW ))
9   plink2 \
10    ${GENO_FLAG_PLINK} "${GENO_PREFIX}" \
11    --chr ${LEAD_CHR} \
12    --from-bp ${FROM_BP} \
13    --to-bp   ${TO_BP} \
14    --r-unphased square \
15    --out "${OUTPUT}/05_susie/chr${LEAD_CHR}_susie_ld" \
16    --threads ${N_THREADS}
```
- L6–13: the same region as Step 4 (**same `LEAD_POS` and `WINDOW` from config**).
- L14 `--r-unphased square`: the **signed correlation r** (not r²) between **every pair** of variants in the region, written as a full square matrix. SuSiE needs the sign. plink2 writes:
  - `chr{C}_susie_ld.unphased.vcor1`: an n × n matrix, one row per variant, tab-separated, with no header.
  - `chr{C}_susie_ld.unphased.vcor1.vars`: the n variant IDs in matrix order.
- ⚠ **No QC filter** is applied. Monomorphic or near-monomorphic variants in the region give **NaN** rows and columns. Most are removed later when `02_susie.R` intersects with the GWAS IDs (regenie skips variants with MAC < 5), but a NaN or non-positive-definite R would make `susie_rss` fail.
- The matrix size grows with the square of the number of variants. For a 1 Mb window of imputed variants (roughly 3–5 k SNPs), that means tens of millions of numbers as text. That is fine, but it grows fast with larger windows.

---

## 5.2 `02_susie.R`

Invocation:
```bash
Rscript script/05_susie/02_susie.R \
  output/01_gwas/step2/HDL_step2_HDL.regenie output/05_susie/chr11_susie_ld output/05_susie \
  11 116662579 500000 <n_sample>
```
⚠ This **must be run from the project root**, because section 6 uses CWD-relative paths (**I-3**). `chr`, `pos` and `window` are typed by hand and must match `config.sh` (**I-5**). `n_sample` comes from the regenie `N` column.

```r
1  library(susieR)
3  args <- commandArgs(trailingOnly = TRUE)
4  # Usage: Rscript 02_susie.R <gwas_file> <ld_prefix> <output_dir> <chr> <pos> <window> <n_sample>
5  gwas_file  <- args[1]  # regenie step2 result file
6  ld_prefix  <- args[2]  # plink2 LD output prefix (e.g. chr11_susie_ld)
7  out_dir    <- args[3]  # output directory
8  lead_chr   <- as.integer(args[4])
9  lead_pos   <- as.integer(args[5])
10 window     <- as.integer(args[6])
11 n_sample   <- as.integer(args[7])
```
Loads susieR. `trailingOnly = TRUE` returns only the user's arguments, not R's own. The arguments are **positional**, with no names and no checking; a wrong order fails silently or confusingly.

```r
13 # phenotype name: extracted from the gwas filename
14 pheno_name <- sub('_step2_.*', '', basename(gwas_file))
16 dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)
```
- L14: `HDL_step2_HDL.regenie` becomes `HDL`, by deleting everything from `_step2_` onwards. It depends on the file-naming convention.
- L16: the R equivalent of `mkdir -p`.

```r
18 # ── 1. Load GWAS summary stats & filter to region
19 gwas   <- read.table(gwas_file, header = TRUE, sep = ' ')
20 region <- gwas[
21   gwas$CHROM == lead_chr &
22   gwas$GENPOS >= lead_pos - window &
23   gwas$GENPOS <= lead_pos + window, ]
24 region <- region[order(region$GENPOS), ]
```
Reads the **whole** regenie file (slow for millions of rows; `data.table::fread` would be faster), keeps the window, and sorts by position. R's `read.table` reads `NA` as missing. ⚠ Rows with NA `BETA`/`SE` (failed tests) are **not removed**, and `susie_rss` would fail on them.

```r
26 # ── 2. Load LD matrix
27 ld_vars <- readLines(paste0(ld_prefix, '.unphased.vcor1.vars'))
28 ld_mat  <- as.matrix(read.table(paste0(ld_prefix, '.unphased.vcor1')))
29 rownames(ld_mat) <- colnames(ld_mat) <- ld_vars
```
Reads the variant IDs and the matrix (`read.table`'s default separator is any whitespace, which handles tabs), then names the rows and columns by variant ID so they can be indexed by ID.

```r
31 # Align to the intersection of GWAS SNPs and the LD matrix
32 common <- intersect(region$ID, ld_vars)
33 region <- region[region$ID %in% common, ]
34 region <- region[match(common, region$ID), ]
35 ld_mat <- ld_mat[common, common]
```
- L32: IDs present in both, **in `region` order** (position-sorted), because `intersect` keeps the order of its first argument.
- L33–34: drops GWAS rows with no LD entry, then reorders to `common` (a safety step, since the order already matches).
- L35: cuts the matrix down to the same IDs in the same order. From here on, **row i of `region` corresponds to row/column i of `ld_mat`**.
- ⚠ **Duplicate IDs** (for example `.` or repeated array IDs) would break the name-based indexing. **Allele alignment is not checked.** The code assumes regenie's `BETA` (per `ALLELE1`) and plink2's `r` (per ALT allele) refer to the same allele. For bed input this normally holds, but it is not verified, and a flipped allele would give wrong CSs (**I-11**).

```r
37 cat(sprintf('Number of SNPs used: %d\n', nrow(region)))
```

```r
39 # ── 3. Run SuSiE RSS
40 fit <- susie_rss(
41   bhat     = region$BETA,
42   shat     = region$SE,
43   R        = ld_mat,
44   n        = n_sample,
45   L        = 10,
46   coverage = 0.95,
47   min_abs_corr = 0.1
48 )
```
- `bhat`/`shat`: the effect estimates and standard errors. susieR turns them into z-scores internally.
- `R`: the signed LD correlation matrix.
- `n`: the GWAS sample size (a single number, although `N` can vary by SNP).
- `L = 10`: at most 10 causal signals.
- `coverage = 0.95`: 95 % credible sets.
- `min_abs_corr = 0.1`: the purity threshold. **Much looser than the default of 0.5.** Low-purity CSs, which are really "somewhere in this big LD block", are kept. That helps explain the note in `skill/05` that small samples produce "too many CSs" (**I-27**).

```r
50 # ── 4. Save results
51 pip_df <- data.frame(
52   ID     = region$ID,
53   CHROM  = region$CHROM,
54   GENPOS = region$GENPOS,
55   PIP    = fit$pip
56 )
57 write.table(pip_df,
58   file = file.path(out_dir, paste0('chr', lead_chr, '_susie_pip.tsv')),
59   sep = '\t', row.names = FALSE, quote = FALSE)
```
One row per SNP with its PIP, written to **`chr{C}_susie_pip.tsv`**. The file name has no phenotype, so running a second trait on the same chromosome **overwrites** it (**I-28**).

```r
61 cs_list <- fit$sets$cs
62 if (!is.null(cs_list)) {
63   cs_df <- do.call(rbind, lapply(seq_along(cs_list), function(i) {
64     data.frame(CS = paste0('L', i), ID = region$ID[cs_list[[i]]])
65   }))
66   write.table(cs_df,
67     file = file.path(out_dir, paste0('chr', lead_chr, '_susie_cs.tsv')),
68     sep = '\t', row.names = FALSE, quote = FALSE)
69   cat(sprintf('Number of Credible Sets: %d\n', length(cs_list)))
70 } else {
71   cat('No significant Credible Set\n')
72 }
```
- L61: `fit$sets$cs` is a list of integer index vectors, one per kept CS, pointing into `region`. It is NULL when there are none.
- L63–65: builds a long table with columns `CS` and `ID`, one row per (CS, SNP) pair, and writes **`chr{C}_susie_cs.tsv`**.
- ⚠ CSs are **renumbered 1..k** (`paste0('L', i)`). susieR's own names (for example `L1`, `L3`, `L7`, from the effect index in `names(cs_list)`) are thrown away, so `L2` in the output may be susie effect 3.
- ⚠ When there is no CS, **no cs.tsv is written, but an older one from a previous run is left in place.** Section 6 would then overlay **stale** CSs (**I-2**).

```r
74 # ── 5. 2-panel plot (Regional assoc + PIP)
75 png(file.path(out_dir, paste0('chr', lead_chr, '_susie.png')),
76     width = 1600, height = 1200, res = 150)
78 par(mfrow = c(2, 1), mar = c(3, 4, 3, 1))
```
Opens a PNG device (1600 × 1200 px at 150 dpi). `mfrow = c(2,1)` gives 2 rows × 1 column of panels. `mar` sets the margins (bottom, left, top, right) in lines of text.

```r
80 # LD r² colours (relative to the lead SNP)
81 lead_id   <- region$ID[which.min(abs(region$GENPOS - lead_pos))]
82 r2_vals   <- ld_mat[lead_id, region$ID]^2
83 r2_color  <- ifelse(r2_vals >= 0.8, '#E41A1C',
84              ifelse(r2_vals >= 0.6, '#FF7F00',
85              ifelse(r2_vals >= 0.4, '#4DAF4A',
86              ifelse(r2_vals >= 0.2, '#377EB8', '#A6CEE3'))))
87 r2_color[region$ID == lead_id] <- '#E41A1C'
```
- L81: the "lead" here is **the SNP closest to `lead_pos`**, not the `LEAD_SNP` ID from config and not necessarily the most significant SNP. If the true lead SNP failed QC or has no LD row, a neighbour takes its place without any warning.
- L82: the lead's row of the correlation matrix, **squared** to give r².
- L83–86: the same 5 colour classes as `02_plot.py`. A NaN r² gives NA as the colour, and R then draws no fill.
- L87: forces the lead to red.

```r
89  # Panel 1: Regional association
90  log10p <- region$LOG10P
91  main_title <- sprintf('%s  chr%d:%d  +-%dkb',
92                        pheno_name, lead_chr, lead_pos, window %/% 1000)
93  plot(region$GENPOS / 1e6, log10p,
94       pch = 21, bg = r2_color,
95       cex = 0.8, xlab = '', ylab = '-log10(P)',
96       main = main_title)
97  abline(h = -log10(5e-8), col = 'red', lty = 2, lwd = 0.8)
```
- The title is e.g. `HDL  chr11:116662579  +-500kb` (`%/%` is integer division).
- `pch = 21` is a filled circle with a border, and `bg` is its fill colour.
- The red dashed line is genome-wide significance.

```r
99  # Highlight Credible Set outlines + CS number labels
100 if (!is.null(cs_list)) {
101   for (i in seq_along(cs_list)) {
102     cs_ids  <- region$ID[cs_list[[i]]]
103     cs_rows <- region[region$ID %in% cs_ids, ]
104     points(cs_rows$GENPOS / 1e6, cs_rows$LOG10P,
105            pch = 21, bg = NA, col = '#984EA3', lwd = 1.5, cex = 1.4)
106     # show the CS number above the most significant SNP
107     top_row <- cs_rows[which.max(cs_rows$LOG10P), ]
108     text(top_row$GENPOS / 1e6, top_row$LOG10P,
109          labels = paste0('L', i), pos = 3, cex = 0.65, col = '#984EA3', font = 2, xpd = NA)
110   }
111 }
```
- Draws larger hollow purple circles around each CS's members.
- The label `Li` goes above the **most significant** member. `pos = 3` means above the point; `font = 2` is bold; `xpd = NA` lets the text go outside the plot area.
- (Note: `skill/05` says this label goes on the highest-**PIP** SNP. That is true for the PIP panel below, but on this panel the code uses the highest −log10 p.)

```r
113 # Lead SNP diamond
114 lead_row <- region[region$ID == lead_id, ]
115 points(lead_row$GENPOS / 1e6, lead_row$LOG10P,
116        pch = 23, bg = '#E41A1C', col = 'black', cex = 1.5)
117 # Legend
118 legend('topright',
119        legend = c('Lead SNP', 'Credible Set', '0.8 <= r2', '0.6 <= r2 < 0.8',
120                   '0.4 <= r2 < 0.6', '0.2 <= r2 < 0.4', 'r2 < 0.2'),
121        pt.bg  = c('#E41A1C', NA, '#E41A1C', '#FF7F00',
122                   '#4DAF4A', '#377EB8', '#A6CEE3'),
123        col    = c('black', '#984EA3', rep('black', 5)),
124        pch    = c(23, 21, rep(21, 5)),
125        pt.lwd = c(1, 1.5, rep(1, 5)),
126        pt.cex = 1.2, bty = 'n', cex = 0.8)
```
- `pch = 23` draws a filled diamond for the lead.
- The legend is built by hand: 7 entries with matching fill, border, symbol and line width. `bty = 'n'` removes the legend box. The "Credible Set" entry is shown even when there are no CSs.

```r
128 # Panel 2: PIP (same r² colours)
129 plot(region$GENPOS / 1e6, pip_df$PIP,
130      pch = 21, bg = r2_color,
131      cex = 0.8, ylim = c(0, 1),
132      xlab = paste0('Chromosome ', lead_chr, ' position (Mb)'),
133      ylab = 'PIP',
134      main = 'Posterior Inclusion Probability')
135 abline(h = 0.5, col = 'grey50', lty = 2, lwd = 0.8)
```
PIP against position, with a fixed y-range of 0–1 and a reference line at PIP = 0.5. `pip_df` and `region` share the same row order, so the colours line up.

```r
137 # PIP panel: CS outline + CS number (select the exact SNP by ID match)
138 if (!is.null(cs_list)) {
139   for (i in seq_along(cs_list)) {
140     cs_ids      <- region$ID[cs_list[[i]]]
141     cs_pip_rows <- pip_df[pip_df$ID %in% cs_ids, ]
142     points(cs_pip_rows$GENPOS / 1e6, cs_pip_rows$PIP,
143            pch = 21, bg = NA, col = '#984EA3', lwd = 1.5, cex = 1.4)
144     top_pip <- cs_pip_rows[which.max(cs_pip_rows$PIP), ]
145     text(top_pip$GENPOS / 1e6, top_pip$PIP,
146          labels = paste0('L', i), pos = 3, cex = 0.65, col = '#984EA3', font = 2, xpd = NA)
147   }
148 }
150 # PIP panel: lead SNP diamond
151 lead_pip <- pip_df[pip_df$ID == lead_id, ]
152 points(lead_pip$GENPOS / 1e6, lead_pip$PIP,
153        pch = 23, bg = '#E41A1C', col = 'black', cex = 1.5)
155 dev.off()
156 cat(sprintf('Plot saved: %s/chr%d_susie.png\n', out_dir, lead_chr))
```
The same overlay on the PIP panel, except that here the label goes on the **highest-PIP** member of each CS. `dev.off()` closes the device and writes the PNG, **`chr{C}_susie.png`**.

```r
158 # ── 6. Automatically generate Regional plot + SuSiE CS overlay
159 cs_tsv      <- file.path(out_dir, paste0('chr', lead_chr, '_susie_cs.tsv'))
160 regional_ld <- file.path('output', '04_regional_plot',
161                          paste0('chr', lead_chr, '_top_ld.vcor'))
162 if (file.exists(cs_tsv) && file.exists(regional_ld)) {
163   cmd <- sprintf(
164     paste('python3 script/04_regional_plot/02_plot.py',
165           '--gwas %s --ld %s --lead %s --chr %d --pos %d --window %d',
166           '--out %s --prefix %s --susie-cs %s'),
167     shQuote(gwas_file), shQuote(regional_ld), shQuote(lead_id),
168     lead_chr, lead_pos, window,
169     shQuote(out_dir), shQuote(pheno_name), shQuote(cs_tsv)
170   )
171   cat('Generating Regional+SuSiE plot...\n')
172   system(cmd)
173   cat(sprintf('Plot saved: %s/%s_chr%d_regional_susie.png\n',
174               out_dir, pheno_name, lead_chr))
175 } else {
176   cat('no regional LD file — skipping regional_susie plot\n')
177 }
```
- **Chaining one script from another.** If both a CS file and the Step 4 LD file exist, the R script builds a shell command and runs the Python plotter with `--susie-cs`.
- L160–161, L164: **paths relative to the working directory** (`output/…`, `script/…`), so this only works when Rscript is started from the project root (**I-3**).
- L167: `shQuote` wraps each argument in single quotes, which protects spaces and the `|` in IDs from the shell.
- ⚠ It passes **`--lead lead_id`** (the SNP nearest `lead_pos`), but the `.vcor` from Step 4 was computed with `--ld-snp ${LEAD_SNP}`. If those two IDs differ, `02_plot.py` finds almost no r² values and **drops nearly every point** (**I-4**).
- ⚠ `file.exists(cs_tsv)` can be true because of a **stale** file from an earlier run (**I-2**).
- ⚠ `system(cmd)`'s exit status is ignored, and "Plot saved" is printed even if Python failed.
- Output: `output/05_susie/{P}_chr{C}_regional_susie.png`.

**Outputs of Step 5:** `chr{C}_susie_ld.unphased.vcor1` (+ `.vars`), `chr{C}_susie_pip.tsv`, `chr{C}_susie_cs.tsv`, `chr{C}_susie.png`, and `{P}_chr{C}_regional_susie.png`, all in `output/05_susie/`.
