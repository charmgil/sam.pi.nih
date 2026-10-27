---
name: sam-setup
description: Check and install the analysis tools and reference resources the SAM harness needs (plink2, regenie, R/susieR, ldsc, PRS-CS; LDSC panel, genetic map, dbSNP map, PRS-CS LD reference). Use when a step reports missing tools or resources, or the user asks what is installed or needed.
---

# Tools and resources

## Check only what the requested step needs
`sam_doctor` with the step(s) about to run: `gwas`, `plots`, `peaks`, `ldsc`, `regional`,
`finemap`, `prs`, `pheweb`. Do not audit everything up front.

| Step | Tools | Resources |
|---|---|---|
| gwas | plink2, regenie, Python | — |
| plots, peaks | Python | — |
| ldsc | Python, ldsc (Python 3 port) | LD scores + weights (EAS), rsID map |
| regional | plink2, Python | genetic map (optional), internet for gene track |
| finemap | plink2, R + susieR | — |
| prs | plink2, Python, PRS-CS | dbSNP ID map; PRS-CS LD reference (for prscs) |
| pheweb | Python | internet access to KNIH PheWeb |

## Installing
- `sam_setup` with the step names installs the matching pixi environments inside the harness
  (no sudo, nothing outside the harness directory). The user approves first.
- Never install with pip/conda/apt/npm or `git clone` through bash; the harness blocks it.

## Missing resources
Resources are read from the resource directory, as folders or as .zip/.tar.gz archives
(archives are read in place; needed members are extracted into `output/_cache/`). If one is
missing, tell the user which file is needed and where it usually comes from (see the harness's
docs/TOOLS.md); do not download reference panels yourself.
