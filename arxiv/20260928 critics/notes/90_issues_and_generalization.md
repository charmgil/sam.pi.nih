# 90 — Issues found and notes for generalisation

Severity:
- **Bug**: produces a wrong or missing result under realistic conditions.
- **Fragile**: works only if conventions are followed by hand.
- **Science**: a methodological choice worth revisiting.
- **Doc**: comment or documentation does not match the code.

Items marked *(verify)* rest on tool behaviour that could not be run here (plink2, regenie and R are not installed on this machine). Everything else comes from reading the code, and the pandas and bash behaviours were confirmed in a scratch environment.

## A. Ranked findings

| ID | Sev. | Where | Finding | Suggested fix |
|---|---|---|---|---|
| I-1 | Bug | `04_regional_plot/02_plot.py` L49 | Gene track queries `rest.ensembl.org` (**GRCh38**), but the data is **hg19**, so genes are drawn about 129 kb off at the workshop locus (*APOA5*). | Use `grch37.rest.ensembl.org` when the build is hg19; make the build a config value. |
| I-2 | Bug | `05_susie/02_susie.R` L61–72, L162 | If a run finds no CS, the old `chr{C}_susie_cs.tsv` is left in place and the automatic overlay plots **stale** credible sets. | Delete or overwrite the CS file on every run (write an empty table). |
| I-3 | Bug | `02_susie.R` L160–164 | Overlay step uses paths relative to the working directory (`output/…`, `script/…`), so it fails or is skipped unless Rscript is started from the project root. | Derive paths from the script location or pass the root in. |
| I-4 | Bug | `02_plot.py` L36–45, L122–125; `02_susie.R` L81, L167 | SNPs with no r² entry are **not drawn at all**. The R script passes `--lead` = the SNP nearest `lead_pos`, which may differ from the `LEAD_SNP` used to build the `.vcor`; if so, nearly every point disappears. | Draw NaN-r² points in grey; pass `LEAD_SNP` through; warn when the lead is not found. |
| I-5 | Fragile | `02_plot.py`, `02_susie.R` CLIs | chr, pos, window, lead and `n_sample` are typed by hand and must match `config.sh`, which the shell scripts used. Nothing checks this. | One config (YAML/TOML) read by every language, or a single driver that passes values through. |
| I-6 | Bug | `02_plot.py` L165 | x tick labels are hidden even when there is **no** gene panel (offline or `--no-gene`), so the axis has no numbers. | Only hide them when `has_genes`. |
| I-7 | Bug | `plot.py` L21/L61; `01_input.py` L15 | `10**-LOG10P` underflows to 0 when LOG10P > ~308. Those SNPs drop out of the QQ plot and are removed by munge (λ_GC, being a median, is hardly affected; ldsc drops huge χ² anyway). | Use `LOG10P` directly for the QQ plot; clip P at ~1e-300 for munge. |
| I-8 | Bug *(verify)* | `3-1_qt_step2.sh` L11 | Several chromosomes become `--chr 11,12`; regenie's list flag is `--chrList` (`--chr` takes one value, repeatable). | Use `--chrList`. |
| I-9 | Bug (latent) | `1-3_merge_pc.py` L33; `01_input.py` L33 | Missing values are written as **empty fields**. Tools that split on whitespace (munge, confirmed; regenie expects `NA`) merge consecutive tabs, so values **shift into the wrong columns**. | `to_csv(..., na_rep="NA")`. |
| I-10 | Doc / dead code | `plot.py` L19, `01_input.py` L12, `02_plot.py` L27 | `df[col] != 'NA'` does nothing (pandas already parsed `NA` as NaN). The outputs are still correct only because later code drops NaN. | `dropna(subset=[col])`. |
| I-11 | Science / fragile | `02_susie.R` L32–48 | Assumes BETA (per regenie `ALLELE1`) and plink2 `r` (per ALT) refer to the same allele; this is never checked. Duplicate IDs would also break name-based indexing. | Check alleles when aligning; de-duplicate IDs; use unique IDs such as `chr:pos:ref:alt`. |
| I-12 | Science | `3-2_bt_step2.sh` | Binary-trait step 2 has no `--firth --approx` or `--spa`, so p-values can be inflated for unbalanced case/control and rare variants. | Add `--firth --approx --pThresh 0.01` (or `--spa`). |
| I-13 | Science | `1-1` vs `3-x` | QC filters (MAF, HWE, missingness) apply only to the prune set; step 2 tests every variant (only regenie's MAC ≥ 5). No sample QC. | Add explicit QC for step 2 (`--minMAC`, INFO, `--extract` a QC'd list) and sample QC. |
| I-14 | Science | `1-1_ld_pruning.sh` L11 | The same r² < 0.9 prune set feeds PCA. That suits regenie step 1, but is lenient for PCA (usually 0.1–0.2, excluding long-range-LD regions). | A separate, stricter prune set for PCA. |
| I-15 | Science | `01_input.py` L19; `02_ldsc.sh` L19–27 | rsIDs are attached **by position only** (alleles ignored), and munge runs without `--merge-alleles`. | Match on alleles too, or run munge with `--merge-alleles w_hm3.snplist`. |
| I-16 | Fragile | `config.sh` L26–32; all `.sh` | If neither `.bed` nor `.pgen` exists, the flags are unset and tools fail with unclear errors. No script uses `set -euo pipefail`, so later commands run after a failure. | Fail early with a clear message; add `set -euo pipefail`. |
| I-17 | Fragile | `config.sh` L7 | `BASH_SOURCE` is bash-only; `sh script.sh` or sourcing from zsh gives the wrong `GWAS_DIR`. | Document "run with bash", or detect the shell. |
| I-18 | Doc | `CLAUDE.md` L109, L123 | `\    # comment` is not a line continuation, so the reference block cannot be pasted and run. | Move comments above the command. |
| I-19 | Doc | `CLAUDE.md` L63 vs `02_plot.py` L123 | The table says Python 3.6.8, but `between(inclusive='left')` needs pandas ≥ 1.3, which needs Python ≥ 3.7. | Pin real versions (e.g. a `requirements.txt` or conda env file). |
| I-20 | Doc | `prompt.txt` L16 | The checklist expects `input/HDL_pc.txt` and `output/01_gwas/plink2/`; the scripts produce `{P}_with_pc.txt` and `step1/`, `step2/`, `pca/`. | Align the checklist with the code. |
| I-21 | Fragile | `config.sh` L48; `CLAUDE.md` L137 | Variant IDs are array IDs with an embedded coordinate that is probably **hg38** (33,912 bp from the hg19 `GENPOS`) *(verify)*. `CLAUDE.md` suggests `{chr}:{pos}:{ref}:{alt}` IDs; the peak table does not show IDs. | Normalise IDs at import (`plink2 --set-all-var-ids @:#:$r:$a`); show the ID in the peak table. |
| I-22 | Doc | `1-3_merge_pc.py` L4; `3-1_qt_step2.sh` L3–5 | Comments name old script files (`3-1_qt_step1.sh`, `4-1_qt_step2.sh`). | Update. |
| I-23 | Fragile | `2-1` / `2-2` L17 | Both use `--lowmem-prefix …/tmp_preds`, so running both at once can clash. | Include the phenotype in the prefix. |
| I-24 | Fragile *(verify)* | `2-1` L18 | `pred.list` stores the absolute `.loco` path, so moving the project between step 1 and step 2 breaks step 2. | Regenerate, or rewrite paths on move. |
| I-25 | Bug (minor) | `03_plot.py` L54, L57 | Regex `[\d.]+` misses negative or scientific-notation values; h² is silently left out of the title. | `[-+\d.eE]+`. |
| I-26 | Fragile *(verify)* | `02_plot.py` L72 | Genetic map read with `sep='\t'`; if the file is space-separated, the recombination track silently disappears. | `sep=r'\s+'`. |
| I-27 | Science | `02_susie.R` L47 | `min_abs_corr=0.1` (default 0.5) keeps low-purity CSs, so more CSs are reported. | Use the default, or report purity alongside. |
| I-28 | Fragile | `05_susie` outputs; `04` `.vcor` | Output files are named by chromosome only (`chr{C}_…`), so a second phenotype or locus on the same chromosome overwrites them. | Include phenotype and position in names. |

Other small items:
- `02_ldsc.sh` hard-codes `PHENO=PHENO_QT`.
- `3-2` lacks the per-chromosome option that `3-1` has.
- `02_plot.py` has an unused import (`mpatches`), an unused variable (`y_range`), `gs` is reused for two things, and a comment says "min 5pt" where the code uses 6.
- `03_plot.py` does not set the `Agg` backend.
- The gene-track strand arrow sits on the bar's top edge.
- CS labels differ between the Python plot (highest −log10 p) and the R PIP panel (highest PIP).
- `prompt.txt` L7 is missing a newline.

## B. What the "framework" currently depends on (implicit contracts)

These are things a general framework would need to make explicit.

1. **File-name conventions as the interface between steps.** For example `{P}_step2_{P}.regenie` (regenie appends `_{P}`), `{G}_pruned.prune.in`, `chr{C}_top_ld.vcor`, `chr{C}_susie_ld.unphased.vcor1(.vars)`, and `pheno_name` parsed back out of a filename (`02_susie.R` L14).
2. **The agent as the config bridge.** Bash reads `config.sh`; Python and R get values only through arguments Claude types. Every hand-copied value is a place for drift (I-5).
3. **Manual preprocessing that only exists as a comment** (config.sh L37: add FID, rename ID→IID).
4. **Tool locations outside the project** (`~/ldsc`, `~/miniconda3/envs/ldsc`, `$HOME/bin`), plus a hard-coded genome build (GRCh37 map, EAS panel, and a GRCh38 Ensembl endpoint).
5. **Human-in-the-loop decision points** encoded in prose: "run only the requested step, then ask", and "list peaks, let the user choose, then edit config".
6. **An acceptance test that exists only as instructor notes** (`prompt.txt`: expected files, expected lead SNP `11:116662579`, "installs only what's needed").

## C. Suggestions for generalising

- **A single typed config** (e.g. `config.yaml`) holding paths, build (`hg19|hg38`), ancestry panel, phenotypes (name, type, file), covariates, target loci, and tool paths. Have one small loader per language, or a driver that writes it into CLI arguments, so no value is typed twice.
- **Treat each step as a unit with a declared contract:** inputs, outputs, required tools and resources, and parameters. `CLAUDE.md`'s "check only the tools the step needs" then becomes data the agent can read, and a runner can check preconditions (files exist, build matches) before starting.
- **Parameterise the domain choices** that are now baked in: build → Ensembl host and genetic map; ancestry → LDSC panel; trait type → regenie flags (`--qt` vs `--bt --firth --approx`).
- **Turn Claude Code "skills" into real Skills** (`.claude/skills/<name>/SKILL.md` with a description) so they load when relevant instead of depending on link-following. Keep `CLAUDE.md` for the global rules (step gating, reporting).
- **Turn `prompt.txt` into automated checks:** for each step, the files that must exist, sanity bounds (λ_GC range, a known lead SNP for a test dataset), and "no unnecessary installs". This gives you regression tests for the agent, not only the scripts.
- **Make scripts fail loudly and leave no stale state:** `set -euo pipefail`; delete a step's outputs before re-running it; check exit codes (`system()` in R).
