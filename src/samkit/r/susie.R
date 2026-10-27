# SuSiE-RSS on one region. Receives resolved paths and values only (no config).
# Usage: Rscript susie.R <region.tsv> <ld.bin> <n> <L> <coverage> <min_abs_corr> <out_prefix> [estimate_resid_var]
#   region.tsv : ID BETA SE (BETA already aligned to the allele the LD matrix is coded on),
#                rows in the same order as the LD matrix
#   ld.bin     : float32 square correlation matrix (plink2 --r-unphased square bin4 ref-based)
suppressPackageStartupMessages({
  library(susieR)
  library(jsonlite)
})

args <- commandArgs(trailingOnly = TRUE)
if (!length(args) %in% c(7, 8)) stop("usage: susie.R region.tsv ld.bin n L coverage min_abs_corr out_prefix [TRUE|FALSE]")
region_file <- args[1]; ld_file <- args[2]
n <- as.numeric(args[3]); L <- as.integer(args[4])
coverage <- as.numeric(args[5]); min_abs_corr <- as.numeric(args[6]); out <- args[7]
# susieR advises estimating the residual variance when the LD matrix is in-sample (as here)
est_resid <- if (length(args) == 8) as.logical(args[8]) else TRUE

region <- read.table(region_file, header = TRUE, sep = "\t", stringsAsFactors = FALSE,
                     colClasses = c(ID = "character"))
k <- nrow(region)
con <- file(ld_file, "rb")
R <- matrix(readBin(con, "numeric", n = k * k, size = 4), nrow = k, ncol = k)
close(con)

# variants whose LD is undefined (monomorphic in these samples) cannot be fine-mapped
ok <- !apply(is.na(R), 1, all) & !is.na(region$BETA) & !is.na(region$SE) & region$SE > 0
dropped_na <- region$ID[!ok]
region <- region[ok, , drop = FALSE]
R <- R[ok, ok, drop = FALSE]
R[is.na(R)] <- 0
diag(R) <- 1
R <- (R + t(R)) / 2

z <- region$BETA / region$SE
s_rss <- tryCatch(estimate_s_rss(z, R, n = n), error = function(e) NA_real_)

fit <- susie_rss(bhat = region$BETA, shat = region$SE, R = R, n = n, L = L,
                 coverage = coverage, min_abs_corr = min_abs_corr,
                 estimate_residual_variance = est_resid)

pip <- data.frame(ID = region$ID, PIP = fit$pip, Z = z)
write.table(pip, paste0(out, "_pip.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)

cs_rows <- list()
cs_info <- list()
if (!is.null(fit$sets$cs)) {
  purity <- fit$sets$purity
  for (i in seq_along(fit$sets$cs)) {
    idx <- fit$sets$cs[[i]]
    name <- names(fit$sets$cs)[i]
    cs_rows[[i]] <- data.frame(CS = name, ID = region$ID[idx], PIP = fit$pip[idx])
    cs_info[[i]] <- list(cs = name, size = length(idx),
                         min_abs_corr = purity[i, "min.abs.corr"],
                         mean_abs_corr = purity[i, "mean.abs.corr"],
                         top_variant = region$ID[idx][which.max(fit$pip[idx])],
                         top_pip = max(fit$pip[idx]),
                         coverage = fit$sets$coverage[i])
  }
}
cs_df <- if (length(cs_rows)) do.call(rbind, cs_rows) else data.frame(CS = character(), ID = character(), PIP = numeric())
# always (re)written, so an old credible-set file never survives a run that finds none
write.table(cs_df, paste0(out, "_cs.tsv"), sep = "\t", quote = FALSE, row.names = FALSE)

summary <- list(
  n_variants = nrow(region),
  dropped_undefined_ld = dropped_na,
  n = n, L = L, coverage = coverage, min_abs_corr = min_abs_corr,
  estimate_residual_variance = est_resid,
  converged = isTRUE(fit$converged), iterations = fit$niter,
  n_credible_sets = length(cs_info), credible_sets = cs_info,
  ld_consistency_s = s_rss,
  susieR = as.character(packageVersion("susieR"))
)
writeLines(toJSON(summary, auto_unbox = TRUE, pretty = TRUE, digits = 6, na = "null"),
           paste0(out, "_fit.json"))
cat(sprintf("SuSiE: %d variants, %d credible set(s), converged=%s\n",
            nrow(region), length(cs_info), isTRUE(fit$converged)))
