# 04 — Step 4: Regional association plot (`script/04_regional_plot/`)

Execution order:
1. The **peak-listing snippet** (inline Python inside `skill/04_regional_plot.md`). Claude runs it and shows the table.
2. **The user picks a peak.** Claude then edits `LEAD_CHR`, `LEAD_POS`, `LEAD_SNP` and `WINDOW` in `config.sh`.
3. `01_input.sh`: plink2 LD between the lead SNP and every SNP in the window.
4. `02_plot.py`: draws the LocusZoom-style figure.

## Background
- A **regional plot** zooms into ±500 kb around a lead SNP. Each point is a SNP (x = position, y = −log10 p), coloured by its **LD r² with the lead SNP**, so you can see which signals are the same association.
- A **recombination-rate** track (cM/Mb, from a genetic map) shows hotspots, which usually mark the edges of LD blocks.
- A **gene track** shows which genes lie under the peak.

---

## 4.0 Peak-listing snippet (from `skill/04_regional_plot.md`)

```python
import pandas as pd, numpy as np
gwas = pd.read_csv('output/01_gwas/step2/{phenotype}_step2_{phenotype}.regenie', sep=' ')
gwas['LOG10P'] = gwas['LOG10P'].astype(float)
sig = gwas[gwas['LOG10P'] >= -np.log10(5e-8)].sort_values('LOG10P', ascending=False)
peaks, used = [], []
for _, row in sig.iterrows():
    if any(abs(row['GENPOS'] - p[1]) < 500000 and row['CHROM'] == p[0] for p in used):
        continue
    peaks.append(row); used.append((row['CHROM'], row['GENPOS']))
df = pd.DataFrame(peaks)[['CHROM','GENPOS','ALLELE0','ALLELE1','LOG10P']].reset_index(drop=True)
df.index += 1; df['P'] = 10**(-df['LOG10P'])
print(df.to_string())
```
- Keeps genome-wide-significant SNPs (LOG10P ≥ 7.301; NaN compares False, so failed tests drop out) and sorts them strongest first.
- **Greedy distance clumping:** walk down the list and skip any SNP within 500 kb of an already-chosen peak on the same chromosome. Each remaining SNP is the top SNP of its own peak.
- Prints a 1-indexed table with chromosome, position, alleles, LOG10P and P.
- Note: the table has **no `ID` column**, yet `LEAD_SNP` must be the exact variant ID. Claude has to look the ID up separately, which is why `CLAUDE.md` guesses the form `{chr}:{pos}:{ref}:{alt}`. That guess only holds when the IDs are in that format (**I-21**).
- Clumping here uses distance only, not LD, so two peaks just over 500 kb apart may be the same signal.

---

## 4.1 `01_input.sh` — LD of every SNP in the window with the lead SNP

```bash
1  #!/bin/bash
2  source "$(dirname "$0")/../config.sh"
4  mkdir -p "${OUTPUT}/04_regional_plot"
6  FROM_BP=$(( LEAD_POS - WINDOW ))
7  TO_BP=$(( LEAD_POS + WINDOW ))
```
Bash integer arithmetic gives the window edges. ⚠ If `LEAD_POS < WINDOW` (a SNP near the start of a chromosome), `FROM_BP` is negative and plink2 will reject it.

```bash
9   plink2 \
10    ${GENO_FLAG_PLINK} "${GENO_PREFIX}" \
11    --chr ${LEAD_CHR} \
12    --from-bp ${FROM_BP} \
13    --to-bp   ${TO_BP} \
14    --r2-unphased \
15    --ld-snp  "${LEAD_SNP}" \
16    --ld-window 99999 \
17    --ld-window-kb $(( WINDOW / 500 )) \
18    --ld-window-r2 0 \
19    --out "${OUTPUT}/04_regional_plot/chr${LEAD_CHR}_top_ld" \
20    --threads ${N_THREADS}
```
- L11–13: restricts to the region (chromosome and base-pair range).
- L14 `--r2-unphased`: computes unphased r² (from genotypes, with no phasing assumed). It is written to a `.vcor` table.
- L15 `--ld-snp ID`: only reports pairs **involving this variant**. The ID must match the bim/pvar exactly, hence the quoted `LEAD_SNP` (it contains a `|`).
- L16 `--ld-window 99999`: the largest allowed distance, counted in variants, is effectively unlimited.
- L17 `--ld-window-kb $((WINDOW/500))` = 500000/500 = **1000 kb**, the largest distance in kb. The furthest SNP is `WINDOW` (500 kb) from the lead, so 1000 kb covers everything; 500 would already be enough. This works as "twice the window in kb", but the expression reads oddly.
- L18 `--ld-window-r2 0`: report **every** pair, including r² ≈ 0. plink's default only reports r² ≥ 0.2, which would leave low-LD SNPs without a colour.
- L19 output: **`chr{C}_top_ld.vcor`**, with columns `#CHROM_A POS_A ID_A CHROM_B POS_B ID_B UNPHASED_R2` (tab-separated).
- The genotypes are **in-sample** (the same individuals as the GWAS), which is best practice.

---

## 4.2 `02_plot.py` — the figure

Invocation:
```bash
python3 script/04_regional_plot/02_plot.py --gwas output/01_gwas/step2/HDL_step2_HDL.regenie \
  --ld output/04_regional_plot/chr11_top_ld.vcor --lead "<exact ID>" --chr 11 --pos 116662579 \
  --window 500000 --out output/04_regional_plot --prefix HDL [--no-gene] [--susie-cs FILE]
```
⚠ `--chr`, `--pos`, `--window` and `--lead` are **typed by hand** and must match `config.sh`, which `01_input.sh` used. Nothing checks this (**I-5**).

```python
1  import argparse
2  import pandas as pd
3  import numpy as np
4  import matplotlib
5  matplotlib.use('Agg')
6  import matplotlib.pyplot as plt
7  import matplotlib.patches as mpatches
8  import requests, sys, os, pathlib
```
Imports. `mpatches` is **never used**. `requests` is needed for the Ensembl REST call; it is a third-party package, not part of the standard library.

```python
10 parser = argparse.ArgumentParser()
11 parser.add_argument('--gwas',   required=True, help='regenie step2 result file')
12 parser.add_argument('--ld',     required=True, help='plink2 LD result file (.vcor)')
13 parser.add_argument('--lead',   required=True, help='Lead SNP ID (e.g. 11:65461544:G:A)')
14 parser.add_argument('--chr',    required=True, type=int)
15 parser.add_argument('--pos',    required=True, type=int, help='Lead SNP position (bp)')
16 parser.add_argument('--window', default=500000, type=int, help='±window (bp)')
17 parser.add_argument('--out',    required=True, help='output directory')
18 parser.add_argument('--prefix', required=True, help='output file prefix')
19 parser.add_argument('--no-gene', action='store_true', help='skip the gene track')
20 parser.add_argument('--susie-cs', default=None, help='SuSiE CS tsv file (chr{chr}_susie_cs.tsv)')
21 args = parser.parse_args()
23 os.makedirs(args.out, exist_ok=True)
```
Command-line interface. `--no-gene` is a flag: its presence means True. `--susie-cs` switches on the SuSiE overlay and changes the output filename.

```python
25 # ── 1. Load GWAS result & filter to region
26 gwas = pd.read_csv(args.gwas, sep=' ')
27 gwas = gwas[gwas['LOG10P'] != 'NA'].copy()
28 gwas['LOG10P'] = gwas['LOG10P'].astype(float)
30 region = gwas[
31     (gwas['CHROM'] == args.chr) &
32     (gwas['GENPOS'] >= args.pos - args.window) &
33     (gwas['GENPOS'] <= args.pos + args.window)
34 ].copy()
```
- Loads the **whole genome's** results just to keep ±window. That is slow for multi-million-row files, but simple.
- L27 is the no-op filter (**I-10**). Points with NaN are simply not drawn.
- L30–34: keeps SNPs on the target chromosome within [pos−window, pos+window].

```python
36 # ── 2. Load LD → r² dictionary keyed on the lead SNP
37 ld = pd.read_csv(args.ld, sep='\t')
38 r2_dict = {}
39 for _, row in ld.iterrows():
40     if row['ID_A'] == args.lead:
41         r2_dict[row['ID_B']] = row['UNPHASED_R2']
42     elif row['ID_B'] == args.lead:
43         r2_dict[row['ID_A']] = row['UNPHASED_R2']
44 r2_dict[args.lead] = 1.0
45 region['R2'] = region['ID'].map(r2_dict)
```
- Builds `{other_SNP_ID: r² with the lead}`. The lead can appear in either column of a pair, hence both branches. L44 sets the lead's own r² to 1.
- L45: looks up each SNP's r² by **ID**. SNPs with no entry get **NaN**.
- ⚠ **NaN-r² SNPs are never drawn** (see L122–125): no colour bin matches NaN. LocusZoom would show them in grey. If `--lead` is not the ID used in `01_input.sh`, almost every SNP vanishes from the plot. `02_susie.R` can trigger this case (**I-4**).

```python
47 # ── 3. Fetch gene info from the Ensembl REST API
48 def fetch_genes(chrom, start, end):
49     url = (f"https://rest.ensembl.org/overlap/region/human/"
50            f"{chrom}:{start}-{end}?feature=gene&content-type=application/json")
51     try:
52         r = requests.get(url, timeout=15)
53         if r.status_code == 200:
54             genes = r.json()
55             # protein_coding genes only
56             return [g for g in genes if g.get('biotype') == 'protein_coding']
57     except Exception as e:
58         sys.stderr.write(f"gene lookup failed: {e}\n")
59     return []
```
- Asks Ensembl for every gene that overlaps the region, as a JSON list of dicts with `start`, `end`, `strand`, `external_name`, `gene_id`, `biotype` and more. It keeps only protein-coding genes.
- Any failure (network error, timeout, non-200 status) returns an empty list, and the plot is then drawn without genes.
- ⚠ **`rest.ensembl.org` uses GRCh38 coordinates, but this analysis is GRCh37/hg19.** The genes come back for the wrong interval and are **drawn at hg38 positions on an hg19 axis**. At the workshop locus (chr11:116.66 Mb, *APOA5*), GRCh38 coordinates are about 129 kb larger, so the genes appear shifted by roughly that much. For hg19 use `https://grch37.rest.ensembl.org` (**I-1**).

```python
61 from_bp = args.pos - args.window
62 to_bp   = args.pos + args.window
```
Window edges in bp, as Python variables.

```python
64 # ── 4. Recombination rate (cM/Mb) from the Beagle GRCh37 genetic map
65 def fetch_recomb(chrom, start, end):
66     script_dir = pathlib.Path(__file__).parent.parent.parent  # GWAS root
67     map_file = script_dir / 'resource' / 'genetic_map' / f'plink.chr{chrom}.GRCh37.map'
68     if not map_file.exists():
69         sys.stderr.write(f"genetic map not found: {map_file}\n")
70         return None, None
```
- L66: the project root is found from **this script's own location** (going up 3 levels: `02_plot.py` → `04_regional_plot` → `script` → root). This is a third way of locating resources, after config.sh's `GWAS_DIR` and the CWD-relative paths in `02_susie.R`.
- L67: the build is **hard-coded to GRCh37**.
- If the map file is missing, the function returns (None, None) and the plot has no recombination line.

```python
71     try:
72         gmap = pd.read_csv(map_file, sep='\t', header=None, names=['chrom','id','cM','bp'])
73         reg = gmap[(gmap['bp'] >= start - 200000) & (gmap['bp'] <= end + 200000)].copy()
74         if len(reg) < 2:
75             return None, None
76         reg = reg.sort_values('bp').reset_index(drop=True)
77         pos_mid = (reg['bp'].values[:-1] + reg['bp'].values[1:]) / 2
78         dcm  = np.diff(reg['cM'].values)
79         dbp  = np.diff(reg['bp'].values)
80         rate = np.where(dbp > 0, dcm / (dbp / 1e6), 0)
81         mask = (pos_mid >= start) & (pos_mid <= end)
82         return pos_mid[mask] / 1e6, rate[mask]
83     except Exception as e:
84         sys.stderr.write(f"recombination rate calculation failed: {e}\n")
85         return None, None
```
- L72: a PLINK-format map has 4 columns: chromosome, ID, genetic position (cM) and physical position (bp). ⚠ The code assumes **tab** separators. If the file uses spaces, everything lands in one column, the `bp` filter matches nothing, and the recombination track **disappears silently**. `sep=r'\s+'` would handle both (**I-26**; check the actual file).
- L73: keeps map points within the window plus a 200 kb margin, so the edges have neighbours.
- L77–80: for each pair of neighbouring map points, rate = ΔcM / ΔMb, placed at their midpoint. `np.where` returns 0 where Δbp = 0. The division is still evaluated there, which may print a divide-by-zero warning, but the value is discarded.
- L81–82: keeps midpoints inside the window and returns x in **Mb**.

```python
87 recomb_pos, recomb_rate = fetch_recomb(args.chr, from_bp, to_bp)
89 # ── Load SuSiE CS
90 susie_cs = None
91 if args.susie_cs:
92     try:
93         susie_cs = pd.read_csv(args.susie_cs, sep='\t')  # CS, ID columns
94     except Exception as e:
95         sys.stderr.write(f'failed to load SuSiE CS: {e}\n')
97 genes = [] if args.no_gene else fetch_genes(args.chr, from_bp, to_bp)
98 has_genes = len(genes) > 0
```
Runs the loaders. The CS file (from `02_susie.R`) has columns `CS` (`L1`, `L2`, …) and `ID`. `has_genes` decides the figure layout.

```python
100 # ── 4. Plot
101 r2_bins = [
102     (0.8, 1.01, '#E41A1C', '0.8 ≤ r²'),
103     (0.6, 0.8,  '#FF7F00', '0.6 ≤ r² < 0.8'),
104     (0.4, 0.6,  '#4DAF4A', '0.4 ≤ r² < 0.6'),
105     (0.2, 0.4,  '#377EB8', '0.2 ≤ r² < 0.4'),
106     (0.0, 0.2,  '#A6CEE3', 'r² < 0.2'),
107 ]
```
LocusZoom-style colour classes (red, orange, green, blue, light blue) as (lower bound, upper bound, colour, legend label). The top bin's upper bound is 1.01 so that r² = 1.0 falls inside a half-open interval.

```python
109 if has_genes:
110     from matplotlib.gridspec import GridSpec
111     fig = plt.figure(figsize=(10, 7))
112     gs = GridSpec(2, 1, height_ratios=[4, 1], hspace=0.03)
113     ax      = fig.add_subplot(gs[0])
114     ax_gene = fig.add_subplot(gs[1])
115 else:
116     fig, ax = plt.subplots(figsize=(10, 5))
117     ax_gene = None
119 xlim = (from_bp / 1e6, to_bp / 1e6)
```
With genes: two stacked panels, association on top (4 parts) and genes below (1 part). Without genes: a single panel. The x-range is in Mb.

```python
121 # Association panel
122 for r2_min, r2_max, color, label in r2_bins:
123     sub = region[region['R2'].between(r2_min, r2_max, inclusive='left')]
124     ax.scatter(sub['GENPOS'] / 1e6, sub['LOG10P'],
125                c=color, s=15, label=label, linewidths=0, zorder=2)
```
One scatter per r² class, over the half-open interval [min, max) (tested: 0.8 falls in the 0.8 bin, not the 0.6 bin, and NaN falls in none). Each call adds one legend entry. `inclusive='left'` requires **pandas ≥ 1.3** (**I-19**).

```python
127 lead_row = region[region['ID'] == args.lead]
128 if not lead_row.empty:
129     ax.scatter(lead_row['GENPOS'].values / 1e6, lead_row['LOG10P'].values,
130                marker='D', c='red', s=60, zorder=3)
```
Draws the lead SNP as a larger red **diamond** on top. If the ID is not in the region, nothing is drawn, with no warning.

```python
132 # SuSiE CS overlay
133 if susie_cs is not None:
134     cs_labels = susie_cs['CS'].unique()
135     for cs_name in sorted(cs_labels):
136         cs_ids  = susie_cs[susie_cs['CS'] == cs_name]['ID'].values
137         cs_rows = region[region['ID'].isin(cs_ids)]
138         if cs_rows.empty:
139             continue
140         ax.scatter(cs_rows['GENPOS'] / 1e6, cs_rows['LOG10P'],
141                    facecolors='none', edgecolors='#984EA3', linewidths=1.5, s=60, zorder=4)
142         top = cs_rows.loc[cs_rows['LOG10P'].idxmax()]
143         y_range = region['LOG10P'].max() - region['LOG10P'].min()
144         ax.annotate(cs_name,
145                     xy=(top['GENPOS'] / 1e6, top['LOG10P']),
146                     xytext=(0, 8), textcoords='offset points',
147                     ha='center', va='bottom', fontsize=7, color='#984EA3',
148                     fontweight='bold', clip_on=False)
```
- For each credible set: draw **hollow purple circles** around its SNPs, then write its name (`L1`, …) 8 points above the member with the **highest −log10 p**.
- ⚠ `sorted()` compares strings, so `L10` sorts before `L2`. That only affects drawing order.
- `y_range` (L143) is **computed but never used**.
- ⚠ The label goes over the most *significant* member, but `02_susie.R` labels the member with the highest PIP in its PIP panel. The two figures can label different SNPs.

```python
150 ax.axhline(-np.log10(5e-8), color='red', ls='--', lw=0.8)
151 ax.set_ylabel('-log10(P)')
152 ax.set_title(f'{args.prefix}  chr{args.chr}:{args.pos}  ±{args.window//1000}kb')
```
Genome-wide significance line, y-label, and a title such as `HDL  chr11:116662579  ±500kb`.

```python
154 # Legend: LD r² + CS (added only when present)
155 handles, labels = ax.get_legend_handles_labels()
156 if susie_cs is not None:
157     cs_patch = plt.Line2D([0], [0], marker='o', color='none',
158                           markerfacecolor='none', markeredgecolor='#984EA3',
159                           markeredgewidth=1.5, markersize=8, label='Credible Set')
160     handles.append(cs_patch)
161     labels.append('Credible Set')
162 ax.legend(handles=handles, labels=labels, title='LD (r²)',
163           fontsize=8, title_fontsize=8, loc='upper left')
164 ax.set_xlim(xlim)
165 ax.tick_params(axis='x', labelbottom=False)
```
- L155: collects the 5 r² legend entries. The lead diamond has no label, so it is not in the legend.
- L157–161: adds a fake "Credible Set" marker (a line with no line, only a hollow circle) as a legend proxy.
- L164: fixes the x-range.
- L165: **hides the x tick labels** on the top panel, because the gene panel below shows them. ⚠ This runs **even when there is no gene panel**, so a plot without genes has **no x-axis numbers**, although it gets an x-axis title at L222 (**I-6**).

```python
167 # Right-hand y-axis: recombination rate
168 if recomb_pos is not None and len(recomb_pos) > 0:
169     ax2 = ax.twinx()
170     ax2.plot(recomb_pos, recomb_rate, color='steelblue', lw=1.2, alpha=0.8)
171     ax2.set_ylabel('Recombination rate (cM/Mb)', color='steelblue', fontsize=9)
172     ax2.tick_params(axis='y', labelcolor='steelblue')
173     ax2.set_ylim(0, max(recomb_rate) * 2.5)
```
`twinx()` creates a second y-axis that shares the same x. The rate line is drawn against it. Setting ylim to 2.5 × the maximum keeps the line in the lower ~40 % of the panel, out of the way of the points.

```python
175 # Gene track panel
176 if has_genes:
177     # split overlapping genes into rows
178     rows = []
179     for g in sorted(genes, key=lambda x: x['start']):
180         placed = False
181         for row in rows:
182             if g['start'] / 1e6 > row[-1]['end'] / 1e6 + 0.05:
183                 row.append(g); placed = True; break
184         if not placed:
185             rows.append([g])
```
**Greedy interval packing:** take genes in order of start position and put each into the first row where it begins more than **0.05 Mb (50 kb)** after the last gene in that row ends; otherwise open a new row. The gap leaves room for the labels. (It compares against `row[-1]`, the gene most recently placed, which is not always the one that ends furthest right when genes are nested. That is a minor packing imperfection.)

```python
187     n_rows = max(len(rows), 1)
188     # automatically shrink font and bar size with the number of rows (min 5pt)
189     font_size  = max(6, 10 - n_rows)
190     bar_height = max(0.2, 0.4 - n_rows * 0.02)
192     ax_gene.set_ylim(-0.8, n_rows + 0.5)
```
Font size goes 9, 8, 7, 6 and stays at 6 as rows are added. ⚠ The comment says "min 5pt", but the code's floor is **6**. Bar height shrinks from 0.38 down to 0.2. L192 leaves room below row 0 for its labels.

```python
193     for row_i, row in enumerate(rows):
194         for g in row:
195             gs = g['start'] / 1e6
196             ge = g['end']   / 1e6
197             strand = g.get('strand', 1)
198             name   = g.get('external_name', g.get('gene_id', ''))
```
For each gene: start and end in Mb (⚠ the name `gs` **shadows** the `GridSpec` object from L112, which is harmless because that object is no longer used), the strand (+1 or −1), and a display name (the gene symbol, falling back to the Ensembl ID).

```python
200             # gene body
201             ax_gene.barh(row_i, ge - gs, left=gs, height=bar_height,
202                          color='steelblue', alpha=0.7)
203             # direction arrow
204             arrow = '→' if strand == 1 else '←'
205             mid = (gs + ge) / 2
206             ax_gene.text(mid, row_i + bar_height / 2, arrow, ha='center',
207                          va='center', fontsize=font_size, color='white')
208             # gene name (clamped so it doesn't cross the edge)
209             xlo, xhi = xlim
210             label_x = max(xlo, min(xhi, mid))
211             ax_gene.text(label_x, row_i - bar_height / 2 - 0.05, name, ha='center',
212                          va='top', fontsize=font_size, style='italic', clip_on=False)
```
- A horizontal bar for the gene body at y = row index.
- A white arrow for the strand. It sits at the **top edge** of the bar (`row_i + bar_height/2`), not the centre, so it may be half outside the bar.
- The italic gene name goes just below the bar. Its x position is **clamped** into the visible window so genes that stick out past the edges still get a readable label.

```python
214     ax_gene.set_xlim(xlim)
215     ax_gene.set_yticks([])
216     ax_gene.set_ylabel('Genes', fontsize=9)
217     ax_gene.set_xlabel(f'Chromosome {args.chr} position (Mb)')
218     ax_gene.spines['left'].set_visible(False)
219     ax_gene.spines['right'].set_visible(False)
220     ax_gene.spines['top'].set_visible(False)
221 else:
222     ax.set_xlabel(f'Chromosome {args.chr} position (Mb)')
223     if not args.no_gene:
224         sys.stderr.write("no gene information — check your internet connection\n")
```
Styles the gene panel: the same x-range, no y ticks, and only the bottom border. Without genes, the x-label goes on the main panel (whose tick labels were hidden at L165, see **I-6**) and a warning is printed, unless genes were turned off on purpose.

```python
226 plt.tight_layout()
227 plt.subplots_adjust(left=0.08, right=0.88, top=0.95, bottom=0.08, hspace=0.25)
228 suffix = '_susie' if args.susie_cs else ''
229 out_path = f'{args.out}/{args.prefix}_chr{args.chr}_regional{suffix}.png'
230 plt.savefig(out_path, dpi=180)
231 plt.close()
232 sys.stdout.buffer.write(f'saved: {out_path}\n'.encode('utf-8'))
```
- L226–227: automatic layout, then fixed margins. `right=0.88` leaves room for the recombination-rate label on the right. The `hspace=0.25` here does **not** override the GridSpec's own `hspace=0.03`, which was set explicitly (tested), so the two panels stay close together. In the no-gene layout there is only one panel, so it has no effect there either.
- L228–229: output name `{prefix}_chr{C}_regional.png`, or `…_regional_susie.png` with the overlay. The folder is `--out`, which is `output/04_regional_plot` normally and `output/05_susie` for the overlay.
