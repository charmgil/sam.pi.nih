#!/usr/bin/env bash
# Reference run for the benchmark: the analyses the scenarios ask for, run directly with samkit (no model).
# Its results are the expected values of Track A and the inputs embedded in Track B (docs/EVALUATION.md).
#   bench/make-reference.sh INPUT_DIR RESOURCE_DIR [REF_DIR]     (default REF_DIR: output/bench/reference)
# About 10 minutes on 16 threads; the runner reads REF_DIR/output and REF_DIR/json.
set -euo pipefail
[ $# -ge 2 ] || { echo "usage: $0 INPUT_DIR RESOURCE_DIR [REF_DIR]" >&2; exit 2; }
HOME_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
IN="$(cd "$1" && pwd -P)"
RES="$(cd "$2" && pwd -P)"
REF="${3:-$HOME_DIR/output/bench/reference}"
mkdir -p "$REF/json"
REF="$(cd "$REF" && pwd -P)"
j() {
	"$HOME_DIR/sam" run --input "$IN" --resource "$RES" --output "$REF/output" "$@" \
		> "$REF/json/$(echo "$*" | tr ' /' '__' | cut -c1-80).json"
}
j status
j gwas all --pheno HDL --pheno-file KBAv2.0AB_14K_HDL_fixed.txt
j plots --pheno HDL
j peaks --pheno HDL
j ldsc --pheno HDL
j finemap --pheno HDL --locus 2
j regional --pheno HDL --locus 2
j prs score --weights HTN_PRS_weight.txt.gz
j report
echo "reference written to $REF"
