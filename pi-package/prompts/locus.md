---
description: Regional plot + SuSiE fine-mapping for one locus
argument-hint: "<phenotype> <locus: rank | CHR:POS | variant ID>"
---
For phenotype `$1`, examine the locus `$2`: run sam_finemap, then sam_regional on the same locus so the credible sets are drawn on the regional plot.
Report the lead variant, the credible sets (size, top variant, PIP, purity), the LD-consistency diagnostic and all warnings, and explain what can and cannot be concluded.
