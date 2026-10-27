---
description: Run a regenie GWAS for one phenotype (prepare → step1 → step2)
argument-hint: "<phenotype> [phenotype-file]"
---
Run a GWAS for the phenotype `$1`. Phenotype file: ${2:-not given; pick it from sam_status and confirm with me}.
First call sam_status, and confirm the phenotype file, trait type and covariates with me if anything is ambiguous.
Then run sam_gwas with stage "all". Report the sample counts, λGC, the number of genome-wide significant loci and the top hits, relay all warnings, and ask me what to do next. Do not start any other analysis on your own.
