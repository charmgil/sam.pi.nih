# 01 — Step 1: GWAS (`script/01_gwas/`)

## 배경

- **유전형(genotype) 파일 형식**
  - **VCF**: 텍스트 형식이며, `FORMAT/DS` 필드에 imputation된 dosage를 담을 수 있다.
  - **PLINK 1 `.bed/.bim/.fam`**: 바이너리 hard call(0/1/2)이다. `.bim` 파일은 variant 목록이고, `.fam` 파일은 FID와 IID를 가진 샘플 목록이다.
  - **PLINK 2 `.pgen/.pvar/.psam`**: 바이너리이며 dosage를 저장할 수 있다. `.psam`은 샘플 목록이며, FID 컬럼은 선택 사항이다.
- **PCA**: 유전형 행렬의 상위 주성분은 조상(ancestry)을 반영한다. 이를 공변량으로 사용하면 population stratification(집단 층화)을 방지할 수 있다.
- **LD pruning**: 높은 상관을 보이는 SNP 쌍마다 하나를 제거하여, 남은 SNP들이 대략 독립이 되도록 한다. PCA와 regenie step 1 모두 이 pruning된 집합으로 실행된다.
- **regenie의 두 단계**
  - **Step 1**은 pruning된 SNP로 전장 유전체 ridge regression을 적합한다. 한 번에 염색체 하나씩을 제외한(**LOCO**) 샘플별 polygenic 예측값을 생성하며, 이는 친족 관계(relatedness)와 polygenic 배경에 대한 보정 역할을 한다.
  - **Step 2**는 대응하는 LOCO 예측값을 offset으로 사용하여 모든 variant를 하나씩 검정한다.
- **`.regenie` 결과 파일**(공백 구분)의 컬럼은 `CHROM GENPOS ID ALLELE0 ALLELE1 A1FREQ [INFO] N TEST BETA SE CHISQ LOG10P EXTRA`이다.
  - `ALLELE1`이 **effect/tested allele**이다. `BETA`는 `ALLELE1` 한 copy당 효과이고, `A1FREQ`는 그 빈도이다.
  - `LOG10P` = −log10(p).
  - 실패한 검정은 `NA`로 표시된다.
  - dosage 입력의 경우 `INFO`가 나타날 수 있다.
  - 이후 단계에서는 `CHROM`, `GENPOS`, `ID`, `ALLELE0/1`, `A1FREQ`, `N`, `BETA`, `SE`, `CHISQ`, `LOG10P`를 사용한다.

순서: `0_vcf_to_pgen.sh` *(조건부)* → `1-1_ld_pruning.sh` → `1-2_pca.sh` → `1-3_merge_pc.py` *(표현형마다 1회)* → `2-1_qt_step1.sh` / `2-2_bt_step1.sh` → `3-1_qt_step2.sh` / `3-2_bt_step2.sh`.

---

## 1.0 `0_vcf_to_pgen.sh` — VCF → PLINK 2 바이너리 (`.bed`가 이미 있으면 생략)

```bash
1  #!/bin/bash
2  source "$(dirname "$0")/../config.sh"
```
설정을 불러온다(README §4 참조).

```bash
4  mkdir -p "${INPUT}"
```
`input/`이 없으면 생성한다. `-p`는 "이미 존재해도 실패하지 않음"을 뜻한다. VCF가 이미 `input/`에 있으므로 이 줄은 보통 아무 일도 하지 않는다.

```bash
6   plink2 \
7     --vcf "${VCF_FILE}" dosage=DS \
8     --make-pgen \
9     --out "${GENO_PREFIX}" \
10    --threads ${N_THREADS}
```
- `--vcf FILE dosage=DS`: VCF를 읽으면서 `GT` hard call뿐 아니라, imputation이 기록하는 `DS` FORMAT 필드의 **dosage**(ALT allele 기대 개수, 0–2)도 가져온다. imputation 데이터에서는 dosage를 유지하는 것이 중요하다.
- `--make-pgen`: `.pgen`(유전형), `.pvar`(variant), `.psam`(샘플)을 쓴다.
- `--out "${GENO_PREFIX}"`: 파일 이름은 VCF 이름이 아니라 `GENO_NAME`을 따라 `input/${GENO_NAME}.*`가 된다.
- `--threads`: CPU 스레드 수.
- **하지 않는 것:** multi-allelic 분리나 필터가 없고, variant ID 정규화가 없으며(ID는 VCF `ID` 컬럼에서 그대로 복사됨), 성별 정보도 없고, FID도 없다(기본 설정에서 plink2는 VCF 샘플 이름을 IID로 쓰고 FID 컬럼은 쓰지 않는다).

```bash
12-13  # plink2가 생성하는 .psam 헤더가 '#IID'로 시작하면 regenie가 오류를 냄
       # → FID 컬럼을 추가하여 '#FID IID ...' 형식으로 변환
14  PSAM="${GENO_PREFIX}.psam"
15  if head -1 "${PSAM}" | grep -q "^#IID"; then
```
- `head -1`은 헤더 줄을 출력한다. `grep -q "^#IID"`는 그 줄이 `#IID`로 **시작**하면 아무것도 출력하지 않고 성공한다. VCF에서 가져온 일반적인 psam의 헤더는 `#IID SEX`이다.
- 아래 수정이 한 번 실행되면 헤더가 `#FID`로 시작하므로, 스크립트를 다시 실행하면 수정을 건너뛴다. 즉 이 수정은 **idempotent**(멱등)하다.
- 주석은 작성자가 밝힌 이유이다. 어느 쪽이든 이 수정은 표현형 파일이 사용하는 **FID = IID**도 보장하므로, regenie가 FID+IID로 샘플을 매칭할 때 샘플 키가 일치한다.

```bash
16    python3 -c "
17  lines = open('${PSAM}').readlines()
18  out = []
19  for i, line in enumerate(lines):
20      if i == 0:
21          out.append('#FID\t' + line.lstrip('#'))
22      else:
23          iid = line.split('\t')[0]
24          out.append(iid + '\t' + line)
25  open('${PSAM}', 'w').writelines(out)
26  "
```
인라인 Python 프로그램이다. 프로그램 전체가 큰따옴표 안에 있으므로, Python이 실행되기 전에 Bash가 `${PSAM}`을 **Python 소스 텍스트 안으로** 확장한다.
- L17: 모든 줄을 읽으며, 각 줄은 끝의 `\n`을 유지한다.
- L20–21, 헤더: 앞의 `#`을 제거하고 `#FID\t`를 앞에 붙인다. 따라서 `#IID\tSEX\n`은 `#FID\tIID\tSEX\n`이 된다.
- L22–24, 데이터 행: 탭으로 구분된 첫 필드(IID)를 가져와 탭과 함께 앞에 붙인다. 따라서 `S1\tNA\n`은 `S1\tS1\tNA\n`이 된다. **FID는 IID로 설정된다.**
- L25: psam을 제자리에서 덮어쓴다.
- ⚠ 경로에 `'`가 있으면 Python 문법이 깨진다(생성된 코드의 quoting 위험). 공백은 문제없다.

```bash
27    echo "psam FID column added: ${PSAM}"
28  fi
```
상태 메시지를 출력하고 `if`를 닫는다.

---

## 1.1 `1-1_ld_pruning.sh` — variant QC + LD pruning

```bash
4  mkdir -p "${OUTPUT}/01_gwas/pca"
```
pruning 및 PCA 출력용 폴더를 만든다.

```bash
6   plink2 \
7     ${GENO_FLAG_PLINK} "${GENO_PREFIX}" \
8     --maf 0.1 \
9     --hwe 0.001 \
10    --geno 0.01 \
11    --indep-pairwise 1000 100 0.9 \
12    --out "${GENO_QC_PREFIX}_pruned" \
13    --threads ${N_THREADS}
```
- L7: 입력 유전형(config.sh가 선택한 대로 `--bfile …` 또는 `--pfile …`).
- L8 `--maf 0.1`: minor allele frequency가 < 10 %인 variant를 제거한다. 엄격한 값이지만(통상 1–5 %), PCA와 step 1을 위한 compact한 common SNP 집합이 목적이라면 합리적이다.
- L9 `--hwe 0.001`: Hardy–Weinberg equilibrium exact test에서 p < 0.001로 실패하는 variant를 제거한다. 이는 genotyping 오류의 징후이다.
- L10 `--geno 0.01`: 1 %를 초과하는 샘플에서 결측인 variant를 제거한다.
- L11 `--indep-pairwise 1000 100 0.9`: window는 **1000 variants**(`kb` 접미사가 없으므로 개수)이고, 100 variant씩 이동하며, 각 window 안에서 **r² > 0.9**인 쌍마다 SNP 하나를 제거한다.
  - r² 0.9는 느슨한 값으로, regenie step 1용으로 SNP를 솎아낼 때 쓰는 수준의 threshold이다.
  - **PCA**에서는 보통 0.1–0.2를 쓴다. 0.9로는 long-LD 영역(MHC나 inversion 등)의 상관된 SNP들이 일부 PC를 지배할 수 있다(**I-14**).
- L12 출력: `…_pruned.prune.in`(유지된 ID), `…_pruned.prune.out`(제거된 ID), `…_pruned.log`.
- **중요:** 이 QC 필터는 어떤 variant가 **prune set에 들어갈지**만 결정한다. 필터링된 유전형 파일은 생성되지 않는다. Step 2의 GWAS는 여전히 **모든** variant로 실행되며, regenie 내장 최소 minor-allele count 외에는 MAF, HWE, 결측률 필터가 없다(**I-13**). 샘플 수준 QC(`--mind`, heterozygosity, relatedness)도 없다.

---

## 1.2 `1-2_pca.sh` — 주성분(principal components)

```bash
4  plink2 \
5    ${GENO_FLAG_PLINK} "${GENO_PREFIX}" \
6    --extract "${GENO_QC_PREFIX}_pruned.prune.in" \
7    --pca ${N_PC} \
8    --out "${GENO_QC_PREFIX}_pca" \
9    --threads ${N_THREADS}
```
- L6 `--extract FILE`: 목록에 있는 variant(pruning되고 QC를 통과한 집합)만 유지한다.
- L7 `--pca 10`: 상위 10개 PC를 계산한다. `approx` modifier가 없으므로 plink2는 exact 방법을 사용한다. 14K 샘플에서는 문제없지만, plink2는 매우 큰 코호트에는 `approx`를 권장한다.
- L8 출력: `…_pca.eigenvec`(샘플당 한 행, 탭 구분, 헤더 `#FID IID PC1 … PC10`, FID가 없으면 `#IID PC1 …`)과 `…_pca.eigenval`(10개의 eigenvalue, 즉 설명 분산).
- `mkdir`이 없으며, `1-1`이 폴더를 만들어 두었다는 것에 의존한다.

```bash
11-13  # 출력 파일 (output/01_gwas/pca/ 폴더):
       #   ${GENO_NAME}_pca.eigenvec  — 샘플별 PC 값 (1-3_merge_pc.py로 표현형 파일에 병합)
       #   ${GENO_NAME}_pca.eigenval  — 분산 기여도
```

---

## 1.3 `1-3_merge_pc.py` — 표현형 파일에 PC 컬럼 추가

```python
1  #!/usr/bin/env python3
2-11 """
     PCA eigenvec 결과를 표현형 파일에 병합하여 새 파일로 저장합니다.
     1-2_pca.sh 실행 후, 3-1_qt_step1.sh 또는 3-2_bt_step1.sh 실행 전에 반드시 실행하세요.

     사용법:
       python3 script/01_gwas/1-3_merge_pc.py \
         --pheno   input/HDL.txt \
         --eigenvec output/01_gwas/pca/KBA_IMP_pca.eigenvec \
         --out     input/HDL_with_pc.txt
     """
```
⚠ docstring이 더 이상 존재하지 않는 스크립트를 가리킨다. `3-1_qt_step1.sh` / `3-2_bt_step1.sh`는 `2-1_qt_step1.sh` / `2-2_bt_step1.sh`여야 한다(**I-22**). 예시의 eigenvec 이름은 `GENO_NAME=KBA_IMP`를 가정한다.

```python
12 import argparse
13 import io
14 import pandas as pd
```
`io`는 문자열을 파일처럼 파싱하는 데 필요하다(L27).

```python
16 parser = argparse.ArgumentParser()
17 parser.add_argument("--pheno",    required=True, help="표현형 파일 (FID IID AGE SEX ...)")
18 parser.add_argument("--eigenvec", required=True, help="plink2 PCA 출력 .eigenvec 파일")
19 parser.add_argument("--out",      required=True, help="출력 파일 경로 (새 파일로 저장)")
20 parser.add_argument("--n-pc",     type=int, default=4, help="병합할 PC 수 (기본 4)")
21 args = parser.parse_args()
```
명령줄 인터페이스이다. `--n-pc`는 `args.n_pc`가 된다(argparse가 `-`를 `_`로 바꾼다). 기본값 4는 config.sh의 `N_PC=10`과 **독립적**이지만, 우연히 `COVAR_COLS`(PC1–PC4)와 일치한다.

```python
23 pheno = pd.read_csv(args.pheno, sep="\t")
```
표현형 테이블(탭 구분, 헤더 포함)을 읽는다. **`IID` 컬럼이 반드시 있어야 한다**(config.sh L37 참조).

```python
25 with open(args.eigenvec, encoding="utf-8") as f:
26     content = f.read().replace("#IID", "IID")
27 pca = pd.read_csv(io.StringIO(content), sep="\t")
```
eigenvec 파일 전체를 텍스트로 읽어 헤더의 `#IID`를 `IID`로 바꾼 뒤, 그 텍스트를 테이블로 파싱한다. 헤더가 `#FID\tIID\t…`이면 `IID` 컬럼은 이미 깨끗한 이름이므로 replace는 이 컬럼에 아무 영향을 주지 않는다(첫 컬럼은 `#FID`로 남으며 사용되지 않는다).

```python
29 keep = ["IID"] + [f"PC{i+1}" for i in range(args.n_pc)]
30 pca = pca[keep]
```
`IID, PC1 … PCn`만 남기고 나머지는 모두 버린다.

```python
32 merged = pheno.merge(pca, on="IID", how="inner")
```
IID로 join한다. **Inner** join이므로 어느 한쪽 테이블에 없는 샘플은 조용히 제외된다. FID 컬럼은 표현형 파일에서 온다. ⚠ pandas가 한 파일에서는 IID를 숫자로, 다른 파일에서는 텍스트로 읽으면 merge가 실패하거나 아무것도 매칭되지 않을 수 있다.

```python
33 merged.to_csv(args.out, sep="\t", index=False)
```
pandas 행 index 없이 탭 구분 파일로 쓴다. ⚠ 결측값(NaN)은 `NA`가 아니라 **빈 필드**로 쓰인다(테스트 결과: pandas는 `""` / 빈 셀을 쓴다). regenie는 결측값으로 `NA`를 기대하므로, 결측이 있는 표현형이 잘못 읽힐 수 있다. `na_rep="NA"`를 쓰면 이를 피할 수 있다(**I-9**). NaN을 포함한 정수 컬럼은 float이 되기도 한다(`1` → `1.0`).

```python
34 import sys
35 sys.stdout.buffer.write(f"done: {len(merged)} samples -> {args.out}\n".encode("utf-8"))
36 sys.stdout.buffer.write(f"cols: {list(merged.columns)}\n".encode("utf-8"))
```
유지된 샘플 수와 컬럼 목록을 UTF-8 안전 방식으로 출력한다(README §4).

---

## 1.4 `2-1_qt_step1.sh` — regenie step 1, 정량 형질(quantitative trait)

```bash
4  mkdir -p "${OUTPUT}/01_gwas/step1"
6   regenie \
7     --step 1 \
8     ${GENO_FLAG_REGENIE} "${GENO_PREFIX}" \
9     --extract "${GENO_QC_PREFIX}_pruned.prune.in" \
10    --phenoFile "${PHENO_QT_FILE}" \
11    --phenoColList ${PHENO_QT} \
12    --covarFile "${PHENO_QT_FILE}" \
13    --covarColList ${COVAR_COLS} \
14    --qt \
15    --bsize 1000 \
16    --lowmem \
17    --lowmem-prefix "${OUTPUT}/01_gwas/step1/tmp_preds" \
18    --out "${OUTPUT}/01_gwas/step1/${PHENO_QT}_step1" \
19    --threads ${N_THREADS}
```
- L7 `--step 1`: 전장 유전체 ridge-regression 모델을 적합한다.
- L8: 유전형(`--bed PREFIX` 또는 `--pgen PREFIX`).
- L9 `--extract`: **pruning된** SNP만으로 모델을 구축한다. 약 0.5 M개로 솎아낸 SNP 집합을 쓰는 것은 step 1의 표준 관행이다.
- L10–11: 표현형 파일과, 그 안에서 어떤 컬럼이 표현형인지를 지정한다. regenie는 처음 두 컬럼이 `FID IID`일 것을 요구한다.
- L12–13: 공변량이며, **같은 파일**에서 읽는다(AGE, SEX, PC1–4를 포함).
- L14 `--qt`: 형질이 정량형이다(선형 모델).
- L15 `--bsize 1000`: regenie의 level-0 ridge regression에 쓰이는 유전형 block 크기.
- L16–17 `--lowmem` + `--lowmem-prefix`: 중간 level-0 예측값을 RAM이 아니라 디스크의 임시 파일에 저장한다. ⚠ prefix `tmp_preds`가 `2-2`와 같으므로, QT와 BT step 1을 **동시에** 실행하면 충돌할 수 있다(**I-23**).
- L18 출력: `HDL_step1_pred.list`(각 표현형을 해당 LOCO 파일에 매핑), `HDL_step1_1.loco`(표현형 #1의 LOCO 예측값), `HDL_step1.log`.
  - ⚠ `pred.list`는 `.loco` 경로를 `--out`에 쓰인 그대로 기록하는데, 여기서는 (`GWAS_DIR`로부터 구성된) **절대 경로**이다. 따라서 step 1과 step 2 사이에 프로젝트 폴더를 옮기거나 이름을 바꾸면 step 2가 깨진다(**I-24**; 확인 필요).

## 1.5 `2-2_bt_step1.sh` — regenie step 1, 이진 형질(binary trait)
`PHENO_BT_FILE`, `PHENO_BT`(T2D), **`--bt`**(이진 형질: level 1에서 logistic ridge)를 제외하면 `2-1`과 동일하다. 출력은 `T2D_step1_pred.list`이다. 표현형은 0/1(또는 1/2)로 코딩되어야 하며, 결측은 NA로 표시한다.

---

## 1.6 `3-1_qt_step2.sh` — regenie step 2, 정량 형질 (선택적으로 염색체별)

```bash
2-5  # 사용법:
     #   bash 4-1_qt_step2.sh          # 전체 genome
     #   bash 4-1_qt_step2.sh 11       # chr11만
     #   bash 4-1_qt_step2.sh 11 12    # chr11, chr12만
```
⚠ 주석이 옛 파일명(`4-1_…`)을 사용한다. 현재 파일명은 `3-1_qt_step2.sh`이다(**I-22**).

```bash
8  mkdir -p "${OUTPUT}/01_gwas/step2"
10 if [ $# -gt 0 ]; then
11   CHR_OPT="--chr $(IFS=,; echo "$*")"
12   SUFFIX="_chr$(IFS=_; echo "$*")"
13 else
14   CHR_OPT=""
15   SUFFIX=""
16 fi
```
- `$#`는 명령줄 인자의 개수이다.
- `"$*"`는 모든 인자를 **`IFS`의 첫 문자**로 이어 붙인다. `IFS`는 `$( … )` subshell 안에서만 바뀌므로 변경이 밖으로 새지 않는다.
- `bash 3-1_qt_step2.sh 11 12`의 경우(테스트함): `CHR_OPT="--chr 11,12"`, `SUFFIX="_chr11_12"`가 된다.
- ⚠ regenie에서 **`--chr`는 염색체 하나를 받으며**(여러 개를 주려면 플래그를 반복), 쉼표로 구분된 목록을 받는 것은 **`--chrList`** 플래그이다. 따라서 단일 염색체의 경우는 동작하지만, `11 12`를 주면 regenie가 `11,12`를 거부할 가능성이 높다(**I-8**; `regenie --help`로 확인).
- ⚠ 염색체별 실행은 `HDL_step2_chr11_HDL.regenie`를 쓰지만, Step 3은 전장 유전체용 이름 `HDL_step2_HDL.regenie`를 하드코딩한다(LDSC는 전장 유전체가 필요하므로 의도된 설계이다).

```bash
18  regenie \
19    --step 2 \
20    ${GENO_FLAG_REGENIE} "${GENO_PREFIX}" \
21    --phenoFile "${PHENO_QT_FILE}" \
22    --phenoColList ${PHENO_QT} \
23    --covarFile "${PHENO_QT_FILE}" \
24    --covarColList ${COVAR_COLS} \
25    --pred "${OUTPUT}/01_gwas/step1/${PHENO_QT}_step1_pred.list" \
26    --bsize 400 \
27    --qt \
28    ${CHR_OPT} \
29    --out "${OUTPUT}/01_gwas/step2/${PHENO_QT}_step2${SUFFIX}" \
30    --threads ${N_THREADS}
```
- L19 `--step 2`: 각 variant의 연관성을 검정한다.
- L20: **전체** 유전형 집합이다. `--extract`가 없으므로 모든 variant가 검정되며, regenie의 기본 최소 minor-allele count(5)가 유일한 variant 필터이다.
- L21–24: step 1과 같은 표현형 및 공변량(반드시 일치해야 한다).
- L25 `--pred`: step 1의 LOCO 예측값. regenie는 list 파일을 읽고, 이 파일이 `.loco` 파일을 가리킨다.
- L26 `--bsize 400`: block당 검정하는 variant 수(메모리/속도 trade-off).
- L28 `${CHR_OPT}`: 의도적으로 **따옴표 없이** 두어 `--chr 11`이 두 단어로 분리되고, 값이 비어 있으면 사라지게 한다.
- L29: regenie가 `_<phenotype>.regenie`를 덧붙이므로 결과 파일은 다음과 같다: **`output/01_gwas/step2/HDL_step2_HDL.regenie`**. 이것이 이후 모든 단계의 핵심 결과 파일이다.

## 1.7 `3-2_bt_step2.sh` — regenie step 2, 이진 형질
염색체 옵션이 없고 `PHENO_BT*`, `--bt`, step 1의 `T2D_step1_pred.list`를 사용한다는 점을 제외하면 `3-1`과 동일하다. 출력은 `T2D_step2_T2D.regenie`이다.
- ⚠ **`--firth --approx`나 `--spa`가 없다**. 이진 형질, 특히 case/control 비율이 불균형하거나 rare variant인 경우, regenie 저자들은 위양성을 억제하기 위해 이 보정 중 하나를 권장한다. 이 보정이 없으면 저빈도 variant의 p-value가 inflate될 수 있다(**I-12**).
