---
description: Polygenic risk score for a trait (PheWeb weights or PRS-CS)
argument-hint: "<trait> [weights|prscs]"
---
Compute a polygenic risk score for `$1` on the target genotypes. Route: ${2:-choose weights or prscs depending on the files available, and tell me which}.
Check sam_status for weight or summary-statistics files first. If none fit, search KNIH PheWeb with sam_pheweb, show me the matching cohorts/codes and let me choose before downloading.
Report the variant match rate, the chromosomes covered (say clearly if the score is partial), the score distribution, and the sample-overlap caveat.
