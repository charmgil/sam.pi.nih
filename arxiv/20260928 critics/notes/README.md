# Line-by-line notes — GWAS agent harness (previous implementation)

These notes explain every script in this folder **in the order it runs**, one line (or small group of lines) at a time. Korean comments and messages are translated. Problems found while reading are marked **⚠** inline and collected, with IDs, in [90_issues_and_generalization.md](90_issues_and_generalization.md).

| File | Covers |
|---|---|
| [00_harness_and_config.md](00_harness_and_config.md) | `prompt.txt`, `CLAUDE.md`, `skill/*.md` (the agent layer) and `script/config.sh` |
| [01_gwas.md](01_gwas.md) | Step 1: `0_vcf_to_pgen.sh` → `1-1` → `1-2` → `1-3_merge_pc.py` → `2-1`/`2-2` (regenie step 1) → `3-1`/`3-2` (regenie step 2) |
| [02_manhattan_qq_plot.md](02_manhattan_qq_plot.md) | Step 2: `plot.py` |
| [03_ldsc.md](03_ldsc.md) | Step 3: `02_ldsc.sh` → `01_input.py` → `munge_sumstats.py` → `ldsc.py`, then `03_plot.py` |
| [04_regional_plot.md](04_regional_plot.md) | Step 4: peak-listing snippet (in `skill/04`) → `01_input.sh` → `02_plot.py` |
| [05_susie.md](05_susie.md) | Step 5: `01_input.sh` → `02_susie.R` (which calls `04_regional_plot/02_plot.py` again) |
| [90_issues_and_generalization.md](90_issues_and_generalization.md) | All findings, ranked, plus notes for turning this into a general framework |

---

## 1. What this project is

The project has three layers.

1. **Agent instructions (the "harness").** None of this is code; it is text that steers Claude.
   - `CLAUDE.md`: Claude Code loads it automatically when a session starts in this folder. It states the rules (run only the step that was asked for; check only the tools that step needs), links the step guides, and gives a reference command sequence.
   - `skill/*.md`: one guide per step, plus `resource_downloads.md`. These are **plain Markdown files, not Claude Code Skills** (no `SKILL.md` or frontmatter), so Claude reads them only when it follows a link from `CLAUDE.md`.
   - `prompt.txt`: the workshop instructor's script. It lists the prompts attendees type and what the instructor checks after each one. In effect it is a **manual acceptance test** for the agent.
2. **Configuration.** `script/config.sh` holds every path and parameter. Each `.sh` script `source`s it.
3. **Worker scripts.** Bash wrappers call external CLIs (`plink2`, `regenie`, `ldsc`). Python and R scripts handle data reshaping and plotting.

> **Key architectural fact:** the Python and R scripts **do not read `config.sh`**. Values such as the phenotype name, lead SNP, window, and sample size reach them only as command-line arguments, which Claude (or a human) types by copying from `config.sh` and the skill docs. **Claude is the glue between config and code.** Most of the fragility listed in the issues file comes from this.

---

## 2. Execution order

```
[session start]  CLAUDE.md auto-loaded
[user prompt]    e.g. "run HDL GWAS"  →  Claude opens skill/01_gwas.md, checks tools, edits config.sh if needed

Step 1  GWAS (skill/01_gwas.md)
  script/config.sh               ← sourced by EVERY .sh below
  01_gwas/0_vcf_to_pgen.sh       (only if input/ has no .bed)
  01_gwas/1-1_ld_pruning.sh
  01_gwas/1-2_pca.sh
  01_gwas/1-3_merge_pc.py        (once per phenotype)
  01_gwas/2-1_qt_step1.sh   |  2-2_bt_step1.sh     (regenie step 1)
  01_gwas/3-1_qt_step2.sh   |  3-2_bt_step2.sh     (regenie step 2)
      ── report, ask before continuing ──
Step 2  02_manhattan_qq_plot/plot.py
Step 3  03_ldsc/02_ldsc.sh  ──► 01_input.py ──► munge_sumstats.py (py2.7) ──► ldsc.py --h2 (py2.7)
        03_ldsc/03_plot.py
Step 4  (peak-listing Python snippet in skill/04) → user picks a peak → Claude edits LEAD_* in config.sh
        04_regional_plot/01_input.sh
        04_regional_plot/02_plot.py
Step 5  05_susie/01_input.sh
        05_susie/02_susie.R ──► (automatically) 04_regional_plot/02_plot.py --susie-cs
```

## 3. Data flow (who writes what, who reads it)

Paths are relative to the project root. `{G}` = `GENO_NAME`, `{P}` = phenotype (e.g. `HDL`), `{C}` = `LEAD_CHR`.

| Produced by | File | Read by |
|---|---|---|
| (user) or `0_vcf_to_pgen.sh` | `input/{G}.bed/.bim/.fam` or `input/{G}.pgen/.pvar/.psam` | every plink2 / regenie call |
| `1-1_ld_pruning.sh` | `output/01_gwas/pca/{G}_pruned.prune.in` | `1-2`, `2-1`, `2-2` |
| `1-2_pca.sh` | `output/01_gwas/pca/{G}_pca.eigenvec` | `1-3_merge_pc.py` |
| `1-3_merge_pc.py` | `input/{P}_with_pc.txt` (name chosen by `--out`) | `2-x`, `3-x`, through `PHENO_QT_FILE` / `PHENO_BT_FILE` in config.sh ⚠ matched only by convention |
| `2-1_qt_step1.sh` | `output/01_gwas/step1/{P}_step1_pred.list`, `{P}_step1_1.loco` | `3-1_qt_step2.sh` |
| `3-1_qt_step2.sh` | `output/01_gwas/step2/{P}_step2_{P}.regenie` | `plot.py`, `01_input.py`, `02_plot.py`, `02_susie.R`, skill/04 snippet |
| `01_input.py` | `output/03_ldsc/{P}_for_munge.tsv` | `munge_sumstats.py` |
| `munge_sumstats.py` | `output/03_ldsc/{P}_munged.sumstats.gz` | `ldsc.py`, `03_plot.py` |
| `ldsc.py` | `output/03_ldsc/{P}_h2.log` | `03_plot.py` (optional `--h2-log`) |
| `04_regional_plot/01_input.sh` | `output/04_regional_plot/chr{C}_top_ld.vcor` | `02_plot.py`, `02_susie.R` (for its automatic overlay call) |
| `05_susie/01_input.sh` | `output/05_susie/chr{C}_susie_ld.unphased.vcor1` + `.vars` | `02_susie.R` |
| `02_susie.R` | `chr{C}_susie_pip.tsv`, `chr{C}_susie_cs.tsv`, `chr{C}_susie.png` | `02_plot.py --susie-cs` |

## 4. Idioms used throughout (explained once here)

- **`source "$(dirname "$0")/../config.sh"`**: `$0` is the path the script was started with (e.g. `script/01_gwas/1-1_ld_pruning.sh`). `dirname` strips the filename, and `/../config.sh` goes up one level. `source` runs config.sh **inside the current shell**, so its variables become visible to the script. This only works when the script is started as `bash script/...` (see config.sh for why `sh` would break it).
- **Unquoted `${GENO_FLAG_PLINK}` / `${GENO_FLAG_REGENIE}` / `${N_THREADS}`**: left unquoted on purpose so the value becomes one flag word. Paths are always quoted (`"${GENO_PREFIX}"`) because the project path contains a space (`External NVMe`).
- **`sys.stdout.buffer.write(f"...".encode("utf-8"))`**: writes UTF-8 bytes straight to stdout, bypassing the console's text encoding. This keeps Korean or Greek characters (λ, ², →) from raising `UnicodeEncodeError` on a Windows console that uses cp949. The workshop had a Windows track (`prompt.txt`).
- **`matplotlib.use('Agg')`**: a non-GUI backend, so plots render to PNG on a machine without a display.
- **`pd.read_csv(regenie_file, sep=' ')` followed by `df[df['LOG10P'] != 'NA']`**: regenie writes the literal text `NA` for failed tests, but pandas already turns `NA` into `NaN` while reading. So `!= 'NA'` compares floats with a string, is always `True`, and **removes nothing**. This was checked in a scratch environment: 2 rows in, 2 rows out. The NaN rows are dropped later, or ignored, by other means. See issue **I-10**.
