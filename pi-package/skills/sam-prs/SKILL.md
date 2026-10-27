---
name: sam-prs
description: Polygenic risk scores on the SAM target genotypes — from existing PRS weights (e.g. KNIH PheWeb) or from external GWAS summary statistics with PRS-CS — including finding and downloading KNIH PheWeb files and interpreting match rates and score distributions. Use when the user asks for a PRS / polygenic score.
---

# Polygenic risk scores

## Choose the route

| The user has / wants | Route |
|---|---|
| a ready-made weight file (e.g. `HTN_PRS_weight.txt.gz`) | `sam_prs` method=`weights` (fast, seconds) |
| GWAS summary statistics (e.g. `phenocode-KBA_187K_HTN.tsv.gz`) | `sam_prs` method=`prscs` (PRS-CS, long) |
| neither | find them on KNIH PheWeb with `sam_pheweb` |

Check `sam_status` first: the input directory may already contain the files. Files downloaded
earlier are under `output/downloads/pheweb/` and can be passed by that path.

## KNIH PheWeb
1. `sam_pheweb` action=`search` with the trait in English (e.g. "hypertension", "HDL").
2. The same trait often exists in several cohorts (KBA+BBJ meta-analysis, KBA_126K, KBA_187K,
   KBA_HLA, KBA_validated) and PRS weights as PRS or lcPRS. **Show the options and ask the user.**
3. `sam_pheweb` action=`download` with the chosen code; the user approves URL and size.
   Downloads record the GWAS N, so PRS-CS can use it automatically.
   The KNIH server is slow (tens of KB/s); if a download is interrupted or fails, calling `download`
   again with the same code resumes it from the partial file.

## PRS-CS specifics
- `n_gwas` is required; PheWeb downloads provide it. For other files ask the user.
- The tool uses the LD reference in the resource directory (EAS 1000 Genomes by default) and
  reports which chromosomes it covers. If only some chromosomes are available or requested, the
  score is **partial**: explain this and ask whether that is acceptable (the tool also asks).
- Genome-wide PRS-CS takes a long time (chromosomes run in parallel); say so before starting.
- Summary statistics from this harness's own GWAS are refused (sample overlap with the target).

## What the tools do
- Target variants are linked to rsIDs through the dbSNP ID map in the resources; the genotype
  file itself is not rewritten. Weights are matched by rsID and alleles (strand flips fixed for
  non-ambiguous SNPs; mismatches dropped). plink2 `--score` gives `PRS_SUM` per person.

## Reading the results
- `matching.match_rate`: share of weight variants usable on the target. Array data typically
  covers a fraction of a genome-wide model; report the number used, not just the rate.
  < 50 % → the score represents part of the model only.
- `chromosomes` / `partial`: say clearly when the score is not genome-wide.
- `score.distribution`: mean, SD and quantiles of PRS_SUM. Raw PRS values have no absolute
  meaning; they rank people within this cohort.
- **Sample overlap**: KNIH PheWeb statistics come from Korean biobank cohorts; if the target
  samples were part of that GWAS, predictive performance would be inflated. Always mention it.
- Individual scores stay in `output/prs/<name>/score.sscore`; do not try to read them when
  privacy mode is on.
