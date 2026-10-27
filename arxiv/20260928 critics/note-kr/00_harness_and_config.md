# 00 — 하네스 계층 (`prompt.txt`, `CLAUDE.md`, `skill/`)과 `script/config.sh`

Markdown과 텍스트 파일은 코드가 아닌 산문이므로 **섹션 단위**로 요약한다. `config.sh`는 **한 줄씩** 설명한다.

---

## A. `prompt.txt` — 워크숍 진행 스크립트 (원문 인용)

이 파일은 Claude가 읽지 않는다. 강사가 세션 진행에 사용한다.

| 행 | 의미 |
|---|---|
| 2–6 | **무료 플랜:** claude.ai 홈(chat)에서 Haiku 모델로 진행한다(원문 표기는 "Haiku 확장 모델 사용"). 작업 폴더는 Claude에게 `…\Downloads\2026_KOGO_WORKSHOP\GWAS_Windows`(Windows) 또는 `…/GWAS`(Mac)를 **Desktop Commander**로 접근할 수 있게 해 달라고 요청해 설정한다. Desktop Commander는 채팅 Claude에게 로컬 파일과 셸 접근 권한을 주는 MCP 서버다. |
| 7 | Mac 경로와 헤더 `# 유료`가 한 줄에 붙어 있다. 줄바꿈이 빠진 오타다. |
| 8–10 | **유료 플랜:** Claude Code에서 Sonnet으로 진행한다. 작업 폴더는 폴더 아이콘을 클릭해 직접 선택한다. |
| 12–16 | *(10+10분)* 프롬프트: "CLAUDE.md 파일 참고해서 분석할거고 input 폴더에 잇는 KBAv2.0_KOGO_IMP.vcf.gz 파일로 HDL GWAS 분석할건데 분석에 필요한 프로그램 있는지 확인하고 없으면 다운로드 받고 분석해줘". **확인 사항:** 실제 분석에 필요한 프로그램만 설치하는지, `input/`에 `pgen`과 `HDL_pc.txt`가 생기는지, `output/01_gwas` 아래 `plink2`, `pca` 폴더에 결과가 생기는지. ⚠ 스크립트는 `step1/`, `step2/`, `pca/`에 쓰며(`plink2/` 폴더는 없다), 병합된 표현형 파일 이름은 `HDL_pc.txt`가 아니라 `{P}_with_pc.txt`다. 체크리스트가 예전 구조를 기준으로 한 것으로 보인다 (**I-20**). |
| 18–21 | *(5분)* Manhattan + QQ plot. **확인:** `output/02_manhattan_qq_plot`에 플롯이 생기는지. |
| 23–26 | *(5분)* LDSC. **확인:** `output/03_ldsc`에 결과가 생기는지. |
| 28–31 | *(5분)* Regional plot. **확인:** Claude가 top signal 중에서 고르는지, 그리고 최종적으로 **`11:116662579`**(hg19, *APOA5–APOA4–APOC3–APOA1* 클러스터의 *APOA5* 내부)에 도달하는지. `output/04_regional_plot`에 플롯이 생기는지. |
| 33–36 | *(10분)* SuSiE. **확인:** Claude가 top signal을 고르거나 regional plot에서 쓴 SNP을 그대로 쓰는지, `output/05_susie`에 결과가 생기는지. |

**시사점:** 각 블록은 자연어 프롬프트 하나와 관찰 가능한 사후 조건(생겨야 할 파일, 설치되어야 하거나 설치되지 말아야 할 도구, 선택된 SNP) 목록을 짝지운다. 일반 프레임워크라면 이를 자동화된 검사로 구현할 수 있다.

---

## B. `CLAUDE.md` — Claude용 프로젝트 지시문 (요약)

| 행 | 섹션 | 내용 |
|---|---|---|
| 1–3 | 제목 | "GWAS 분석 가이드 — 유전체 데이터를 이용해 연속형·이진형 형질에 대해 GWAS를 수행하고 결과 시각화 및 사후 분석". |
| 7–10 | **실행 원칙** | (1) **요청받은 단계까지만 실행.** "GWAS 분석해줘"는 Step 1(regenie step1/step2)까지만 의미한다. Step 2–5는 명시적으로 요청하거나 "전체 파이프라인 돌려줘"라고 한 경우에만 진행한다. 한 단계를 마치면 결과를 보고하고 다음 단계 진행 여부를 먼저 확인한다. (2) **필요한 프로그램만 확인.** 도구 표 전체를 한번에 미리 점검하지 않는다. Step 1: plink2, regenie, python3. Step 2: python3. Step 3: python3, ldsc용 Python 2.7, LDSC 참조 패널. Step 4: plink2, python3, genetic map. Step 5: R, susieR. |
| 14–22 | 단계 표 | 각 단계를 해당 `skill/0X_*.md` 가이드에 연결한다. |
| 26–53 | 디렉토리 트리 | `input/`, `resource/{LDSC,dbSNP,genetic_map}`, `script/…`, `skill/…`, `output/`. "(여기만 수정)"이라는 주석은 `config.sh`에 달려 있다. |
| 57–69 | 도구 버전 | plink2 v2.0.0-a.7.1, regenie v4.1, python3 3.6.8, python2 2.7 (ldsc 전용, `~/miniconda3/envs/ldsc/bin/python`), R 4.4.0, susieR 0.14.2, ldsc. PATH 안내: `export PATH="$HOME/bin:$PATH"`. ⚠ `02_plot.py`는 `Series.between(..., inclusive='left')`를 호출하는데, 이는 pandas ≥ 1.3이 필요하고 pandas 1.3은 Python ≥ 3.7이 필요하다. 따라서 "3.6.8"은 스크립트가 실제로 실행된 환경일 수 없다 (**I-19**). |
| 73–91 | Config 템플릿 | `config.sh`의 **단순화된** placeholder 버전. 실제 파일은 이와 다르다. `GWAS_DIR` 자동 감지, `GENO_PREFIX`, `GENO_QC_PREFIX`, 포맷 자동 감지가 들어 있다. |
| 95–150 | 참고용 명령 순서 | `{phenotype}`, `{chr}`, `{pos}` placeholder를 쓴 셸 명령으로 전체 파이프라인을 정리했다. 97행은 참고용일 뿐이며 단계 사이를 자동으로 넘어가지 말라고 적혀 있다. ⚠ 109행과 123행은 `python3 … \     # 주석` 형태다. 백슬래시 뒤에 공백이 오면 줄 이어쓰기가 **아니므로**, 다음 줄(`--pheno …`)은 별도 명령으로 실행된다. 이 블록은 그대로 붙여 넣어 쓸 수 없다 (**I-18**). |
| 153–159 | 공통 주의사항 | config.sh에 경로가 빠지면 모든 스크립트가 실패한다. `1-3_merge_pc.py`는 필수다(PC 컬럼이 없으면 regenie step 1 실패). `munge_sumstats.py`와 `ldsc.py`는 Python 2.7 전용이다(python3로 실행하면 `TabError`). LDSC는 전체 genome 결과가 필요하다. regional plot과 SuSiE 타깃은 `LEAD_CHR`, `LEAD_POS`, `LEAD_SNP`를 수정해 바꾼다. |

## C. `skill/*.md` — 단계별 가이드 (각각이 Claude에게 지시하는 내용)

각 단계 노트(01–05)는 해당 단계에 중요한 부분을 다시 다룬다. 요약하면 다음과 같다.

- **`01_gwas.md`**: 스크립트 표. **"0단계" 규칙:** 먼저 `input/`을 확인한다. `{GENO_NAME}.bed/.bim/.fam`이 있으면 VCF→pgen을 **건너뛴다**(config.sh가 `--bfile`/`--bed`를 자동 감지한다). VCF만 있을 때에만 변환한다. QC 기준(MAF ≥ 0.1, HWE p ≥ 0.001, call rate ≥ 0.99), 공변량(AGE, SEX, PC1–4), block size(1000 / 400), 출력 폴더도 제시한다. 주의사항: regenie v4.1에서 `--no-fid`가 제거되었다. step 2의 `--pred` = step 1의 `--out` + `_pred.list`. ⚠ 예시의 eigenvec 이름(`KBA_IMP_pca.eigenvec`)은 `GENO_NAME=KBA_IMP`일 때만 맞다.
- **`02_manhattan_qq_plot.md`**: 실행 명령과, `LOG10P`를 직접 사용한다는 점. Manhattan 기준선은 5e-8과 1e-5, QQ plot은 λ_GC와 95 % 신뢰구간을 표시한다. ⚠ 신뢰구간을 "binomial"이라고 적었지만, 코드는 실제로 Beta 순서통계량(order statistic) 분위수를 쓴다.
- **`03_ldsc.md`**: `02_ldsc.sh`가 세 가지를 순서대로 실행한다. EAS 참조 패널 경로를 명시하고, 22개 염색체가 모두 필요하다고 하며, 출력 목록과 플롯 명령(`CLAUDE.md` 버전에는 빠진 `--h2-log` 포함)을 제시한다. pos2rsid 매핑 후 SNP 수가 줄어드는 것은 정상이라고도 적었다.
- **`04_regional_plot.md`**: (1) 독립적인 genome-wide 유의 peak를 나열하는 **inline Python 코드 조각**을 실행하고 **사용자가 고르게 한다**. (2) 선택한 값을 config.sh에 쓴다. (3) `01_input.sh` + `02_plot.py`를 실행한다. LD 색상 범례, genetic map 출처, 유전자 트랙 출처(Ensembl REST), SuSiE 오버레이 변형도 제시한다.
- **`05_susie.md`**: config.sh에 타깃을 설정하고 `01_input.sh`를 실행한 뒤 `Rscript 02_susie.R <gwas> <ld_prefix> <out_dir> <chr> <pos> <window> <n_sample>`를 실행한다. 설정: L = 10, coverage 0.95, `min_abs_corr` 0.1. 플롯 구성과 결과 해석 방법을 설명하고, `n_sample` = regenie 출력의 `N` 컬럼이라고 한다.
- **`resource_downloads.md`**: dbSNP b155(hg19/hg38, 약 20–30 GB), LDSC EAS baseline LD score와 weight(Zenodo 7768714, Broad 서버는 이제 유료), `ldsc` 저장소(`git clone … ~/ldsc`), Beagle genetic map(GRCh37/38)의 다운로드 명령. **현재 분석은 hg19 기준**이라고 명시한다.

---

## D. `script/config.sh` — 한 줄씩

```bash
1  #!/bin/bash
```
Shebang. 이 파일은 항상 `source`되고 직접 실행되지 않으므로 실질적인 효과는 없다.

```bash
2-4  # ══════════════════════════════════════════════════════
     #  GWAS 실습 공통 설정 — 이 파일만 수정하면 됩니다
     # ══════════════════════════════════════════════════════
6    # ── 경로 (config.sh 위치 기준 자동 설정 — 수정 불필요)
7    GWAS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
```
- `${BASH_SOURCE[0]}`은 **현재 읽고 있는 파일**(config.sh)의 경로다. source된 파일 안에서는 호출한 스크립트를 가리키는 `$0`과 다르다.
- `dirname …`은 `…/script`를 돌려주고, `cd …/..`로 프로젝트 루트로 이동한 뒤, `pwd`가 이를 절대 경로로 출력한다. 이 모든 것이 `$( … )` 서브셸 안에서 실행되므로 호출한 쪽의 작업 디렉토리는 바뀌지 않는다.
- 결과: 현재 디렉토리가 어디든 `GWAS_DIR`은 프로젝트 루트의 절대 경로가 된다. ⚠ `BASH_SOURCE`는 **bash**에만 있다. `sh`(dash)에서 실행하거나 zsh에서 source하면 비어 있어서, `GWAS_DIR`이 현재 디렉토리의 상위 디렉토리가 된다 (**I-17**).

```bash
8   INPUT="${GWAS_DIR}/input"
9   OUTPUT="${GWAS_DIR}/output"
10  RESOURCE="${GWAS_DIR}/resource"
```
최상위 데이터 폴더 세 개의 절대 경로.

```bash
12  # ── PATH (plink2, regenie 등이 설치된 위치를 모두 포함)
13  export PATH="$HOME/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"
```
흔히 쓰는 설치 위치를 검색 경로 맨 앞에 둔다. `export` 덕분에 `plink2`, `regenie`, `python3` 같은 자식 프로세스에도 적용된다. export되는 변수는 이것 **하나뿐**이다. 나머지는 일반 셸 변수라서 source한 스크립트에서는 보이지만 Python과 R에서는 보이지 않는다.

```bash
15  # ── 입력 VCF (원본 213GB VCF는 삭제되어 없음 — pgen 변환 없이 기존 bfile 그대로 사용)
16  VCF_FILE="${INPUT}/KBAv2.0AB_14K_COMMON_REHEADER_SORT_PHASING_IMPUTATION_HWE1E-6_R20.8.vcf.gz"   # 입력 VCF 파일명
```
VCF 경로로, `0_vcf_to_pgen.sh`에서만 쓴다. 주석을 보면 **이 config는 작성자 본인의 실행 환경**, 즉 이미 bed 포맷으로 된 14K 샘플 KBA v2.0 데이터셋을 기술한다. 워크숍 데이터셋(`prompt.txt`에 따르면 `KBAv2.0_KOGO_IMP.vcf.gz`)이 아니다. 워크숍에서는 Claude가 이 값들을 다시 쓰는 것을 전제로 한다.

```bash
18  # ── Genotype prefix
19  GENO_NAME="KBAv2.0AB_14K_COMMON"
20  GENO_PREFIX="${INPUT}/${GENO_NAME}"            # bed/bim/fam 또는 pgen/pvar/psam 공통 경로
21  GENO_QC_PREFIX="${OUTPUT}/01_gwas/pca/${GENO_NAME}"  # pruned / pca 결과 prefix
```
- `GENO_NAME`은 genotype 파일의 basename이다. VCF 이름에서 **파생되지 않는다**는 점에 유의한다.
- `GENO_PREFIX`는 plink2와 regenie가 `--bfile`, `--pfile`, `--bed`, `--pgen` 뒤에 받는 값이다. 확장자는 각 도구가 직접 붙인다.
- `GENO_QC_PREFIX`는 pruning과 PCA 출력(`…_pruned.prune.in`, `…_pca.eigenvec`)의 stem이다.

```bash
23-25  # ── Genotype 입력 포맷 자동 감지
       #    input/${GENO_NAME}.bed 가 이미 있으면 pgen 변환 없이 그대로 사용 (--bfile / --bed)
       #    없고 .pgen 만 있으면 VCF→pgen 변환된 것이므로 그걸 사용 (--pfile / --pgen)
26  if [ -f "${GENO_PREFIX}.bed" ]; then
27    GENO_FLAG_PLINK="--bfile"
28    GENO_FLAG_REGENIE="--bed"
29  elif [ -f "${GENO_PREFIX}.pgen" ]; then
30    GENO_FLAG_PLINK="--pfile"
31    GENO_FLAG_REGENIE="--pgen"
32  fi
```
- `[ -f X ]`는 X가 존재하는 일반 파일이면 참이다.
- **bed가 pgen보다 우선**한다.
- 이 검사는 **config.sh가 source될 때마다** 실행된다. 따라서 `0_vcf_to_pgen.sh`가 `.pgen`을 만들고 나면 이후 스크립트는 자동으로 `--pfile`/`--pgen`을 고른다.
- ⚠ 두 파일 모두 없으면 두 플래그가 **설정되지 않은** 채로 남는다. 그러면 스크립트는 입력 플래그 없이 `plink2 "<prefix>" …`를 호출하고, 명확한 메시지 대신 알아보기 힘든 오류로 실패한다 (**I-16**). `0_vcf_to_pgen.sh`는 이 플래그를 쓰지 않으므로 영향이 없다.
- plink2와 regenie는 같은 포맷에 다른 플래그 이름을 쓴다(`--bfile` 대 `--bed`, `--pfile` 대 `--pgen`). 그래서 변수가 두 개다.

```bash
34  # ── 표현형 파일 & 컬럼명
35  PHENO_QT_FILE="${INPUT}/KBAv2.0AB_14K_HDL_with_pc.txt"
36  PHENO_QT="HDL"
37  # 표현형 파일이 ID,SEX,AGE,HDL 형식이라 1-3_merge_pc.py 실행 전 FID 컬럼 추가 + ID→IID 변경 필요했음
```
- `PHENO_QT_FILE`은 `1-3_merge_pc.py`의 **출력**(PC 컬럼이 붙은 표현형 파일)이다. 연속형 형질(QT) regenie 실행에서 `--phenoFile`과 `--covarFile`로 모두 쓰인다.
- `PHENO_QT`는 표현형의 컬럼명이다. regenie는 이 값으로 출력 파일 이름을 짓는다(`HDL_step2_HDL.regenie`).
- 37행은 **어떤 스크립트도 수행하지 않는 수동 전처리 단계**를 기록한다. 원본 표현형 파일에는 `ID`가 있었는데, regenie는 앞의 두 컬럼으로 `FID IID`를 요구한다. 작성자가 FID를 추가하고 ID→IID로 이름을 직접 바꿨거나 Claude에게 시켰다.

```bash
39  PHENO_BT_FILE="${INPUT}/T2D_with_pc.txt"
40  PHENO_BT="T2D"
```
이진형 형질(BT) 실행(`2-2`, `3-2`)을 위한 같은 쌍으로, 2형 당뇨병을 예로 들었다.

```bash
42  # ── 공변량
43  COVAR_COLS="AGE,SEX,PC1,PC2,PC3,PC4"
```
regenie `--covarColList`에 넘기는 쉼표 구분 목록. 이 컬럼들이 표현형 파일에 있어야 하므로 `1-3_merge_pc.py`를 먼저 실행해야 한다. PC는 10개를 계산하지만(`N_PC`) 4개만 사용한다.

```bash
45  # ── Regional plot / fine-mapping 타깃 영역
46  LEAD_CHR=16
47  LEAD_POS=56994528
48  LEAD_SNP="AX-95823215|chr16:56960616:C:T"   # bim의 실제 variant ID (LD 계산 --ld-snp에 필요)
49  WINDOW=500000                  # lead SNP ± 500kb
```
- Step 4와 5의 타깃 locus다. 현재 값은 chr16:56.99 Mb로, 대표적인 HDL locus인 ***CETP*** 영역이다.
- `LEAD_SNP`는 bim/pvar의 **ID 컬럼과 정확히 일치**해야 한다(따라서 regenie 출력의 `ID` 컬럼과도 일치해야 한다). 여기서는 Affymetrix array probe ID에 좌표 문자열이 붙은 형태다.
- ⚠ ID 안의 위치(56,960,616)는 `LEAD_POS`(56,994,528)보다 **33,912 bp** 작다. 이 차이는 *CETP* 부근의 GRCh37→GRCh38 좌표 이동과 일치하므로, **ID 문자열은 hg38 좌표를, `GENPOS` 값은 hg19 좌표를 담고 있을 가능성이 높다**(검증하지 않음, liftOver로 확인 필요). ID에서 위치를 파싱하는 코드가 있다면 여기서 틀린 값을 얻게 된다 (**I-21**).
- `WINDOW`는 영역의 반폭(half-width)이다.
- Step 4에서 사용자가 peak를 고르면 Claude가 이 값들을 다시 쓴다. 워크숍의 기대값은 `LEAD_CHR=11`, `LEAD_POS=116662579`이다.

```bash
51  # ── 공통 옵션
52  N_PC=10
53  N_THREADS=4
```
- `N_PC`는 `1-2_pca.sh`가 계산하는 PC 개수다. `1-3_merge_pc.py`는 이 값을 읽지 **않으며**, 자체 `--n-pc` 기본값 4를 쓴다.
- `N_THREADS`는 plink2와 regenie의 스레드 수다.
