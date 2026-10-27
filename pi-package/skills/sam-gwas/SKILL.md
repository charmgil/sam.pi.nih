---
name: sam-gwas
description: Run a genome-wide association study with regenie on the SAM input data (QC, PCA, phenotype table, step 1, step 2) and interpret sample counts, λGC and top hits. Use when the user asks for a GWAS or association analysis of a phenotype.
---

# GWAS with regenie

## Before running

1. Call `sam_status` to see the genotype filesets and phenotype tables (column names only).
2. Settle with the user, unless already clear from the request:
   - **phenotype file and column** (e.g. `KBAv2.0AB_14K_HDL.txt`, column `HDL`). If several files hold
     the same column (raw / "fixed" / "with_pc" versions), prefer the raw file: the tool matches IDs,
     adds FID/IID and computes its own PCs. Mention which file you chose.
   - **trait type**: auto-detected (0/1 or 1/2 → binary, else quantitative). Confirm when unsure.
   - **covariates**: default AGE + SEX if present, plus PC1–4.
3. If tools may be missing, `sam_doctor` with `steps: ["gwas"]`.

## Running

- `sam_gwas` with `stage: "all"` runs prepare → step1 → step2. It takes from several minutes
  (prepare) to tens of minutes (step 1 on ~600k variants). Tell the user it is long-running.
- To resume after a failure, run the remaining stage only (`step1` or `step2`).
- `chromosomes` (step 2 only) gives a partial-genome result: fine for a quick look, but LDSC
  will refuse it and plots will show only those chromosomes. Say so if you use it.
- A VCF input (`vcf`) is converted to pgen only when no PLINK fileset of that name exists.

## What the tool does (so you can explain it)

- Sample QC: call rate ≥ 95 %.
- Step 1 variants: MAF ≥ 1 %, call rate ≥ 99 %, HWE p ≥ 1e-6, LD-pruned r² < 0.9.
- PCA: separate stricter pruning (MAF ≥ 5 %, r² < 0.2, MHC excluded), 10 PCs computed.
- Step 2 variants: call rate ≥ 95 %, MAC ≥ 20, HWE (sample-size aware threshold; removes gross failures only).
- Binary traits: Firth correction (approximate) for P < 0.01.
- Missing values (`NA`, `-9`, empty) are excluded; the result reports how many samples were analysed.
- PC columns already present in the phenotype file are ignored (the harness computes its own PCs).
- Re-running prepare with a different file, covariates or trait removes the old step-1/step-2 results and
  everything derived from them; the tool says so in its warnings.

## Reading the results

- `n_analysed` vs `n_genotyped`: large losses mean ID mismatch or missing phenotype; report it.
- `lambda_gc`: about 1.00–1.05 is typical; > 1.1 suggests stratification or relatedness, though a
  very polygenic trait in a large sample can also raise it. Do not over-interpret alone.
- `n_genome_wide_significant` / `n_independent_loci_500kb`: counts at P < 5e-8.
- `top_hits`: report ID, position (hg19), effect allele (ALLELE1), BETA, SE, −log10P.
  For known loci you may add what is established in the literature, clearly marked as background.

Then ask whether the user wants plots, the list of significant loci, or LDSC.
