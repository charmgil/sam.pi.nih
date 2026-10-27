---
name: sam-post-gwas
description: Post-GWAS analyses on finished SAM GWAS results — Manhattan/QQ plots, independent significant loci, LDSC SNP heritability, regional association plots and SuSiE fine-mapping — and how to interpret them. Use after a GWAS when the user asks for plots, peaks, heritability, a regional plot or fine-mapping.
---

# Post-GWAS: plots, loci, LDSC, regional plot, fine-mapping

Each analysis is a separate request. Run only the one asked for, then report and ask.

## Manhattan / QQ — `sam_plots`
- Report λGC and the maximum −log10P; describe the plots' notable peaks.
- QQ inflation across the whole range suggests confounding; departure only in the tail is
  consistent with real signals.

## Significant loci — `sam_peaks`
- Lists independent loci (distance clumping, ±500 kb) with lead variant, position, alleles, BETA, −log10P.
- Show the list (rank, locus, ID, −log10P) and **ask the user which locus** to examine next.
- If nothing reaches 5e-8, the tool lists the strongest variants; a regional plot or fine-mapping
  of such a locus is exploratory and must be labelled so.

## LDSC heritability — `sam_ldsc`
- Needs genome-wide results (all autosomes) and the EAS LD-score panel.
- Default `model`: univariate h² from the panel's all-SNP ("base") LD score — the standard estimate.
  `model: "baseline"` fits stratified LDSC with every annotation of the panel (the workshop's original
  command); its total h² depends on the annotation model and is noisier at N ≈ 15k.
- Report: observed-scale h² (SE), z = h²/SE, intercept (SE), ratio, mean χ², λGC, regression SNPs.
  λGC is genome-wide; never call it a local or per-locus value.
- Interpretation:
  - intercept ≈ 1 → inflation is mostly polygenic signal; intercept > 1.1 → confounding likely;
  - ratio = (intercept − 1)/(mean χ² − 1): share of inflation not explained by polygenicity;
  - h² z < 4, h² outside [0, 1], or N < 5,000 → the estimate is not interpretable; say so plainly;
  - array data with few regression SNPs (< 200k) gives unstable estimates.
- Binary traits: liability-scale h² needs the population prevalence — ask the user for it.

## Regional plot — `sam_regional`
- `locus` = rank from `sam_peaks` (e.g. "1"), "CHR:POS" (hg19), or the variant ID. Use the locus the
  user chose; if they did not choose, show the peaks and ask.
- LD r² is computed in the GWAS samples; grey points have no LD value.
- The gene track comes from Ensembl GRCh37 (needs internet; the tool warns if missing).

## Fine-mapping — `sam_finemap`
- Use the same locus as the regional plot unless the user asks otherwise.
- Report per credible set: size, top variant and its PIP, purity (min |r|).
- Interpretation:
  - a 95 % credible set contains a causal variant with ≥ 95 % probability (under the model);
  - size 1–3 with high PIP → a well-resolved signal; large sets → only localised;
  - several credible sets → *possibly* several independent signals. Say "N credible sets", not "N causal
    variants" or "at least N independent signals": in-sample LD from ~15k people can split one signal;
  - low-purity sets (min |r| < 0.5) are unreliable;
  - `ld_consistency_s` > 0.1 → z-scores and LD disagree (allele/sample mismatch); be cautious;
  - PIP is not an effect size; a high-PIP variant is a candidate, not a proven causal variant.
- Afterwards `sam_regional` on the same locus draws the credible sets on the regional plot.

## Second opinion
`sam_consult` can ask a biomedical domain model about the known biology of a locus. Present its
answer as background to be verified, never as an analysis result.
