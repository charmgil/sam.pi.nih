# 사용 사례별 프롬프트 모음 (한국어 · English)

SAM 에이전트에게 그대로 입력할 수 있는 프롬프트를 기능별로 모았습니다. 모든 예시는 한국어(KO)와 영어(EN) 두 가지로 적었고,
그 아래 화살표(→)는 에이전트가 부를 도구와 돌려줄 결과입니다. 도구와 옵션의 전체 목록은 [USAGE.md](USAGE.md) 3절,
각 단계의 입력·출력은 [WORKFLOW.md](WORKFLOW.md)에 있습니다.

> *English readers*: explanations are in Korean, but every prompt has an English version (lines starting with `EN:`).
> The agent answers in the language of your message.

예시의 파일·표현형 이름은 이 서버의 시험 데이터입니다(`KBAv2.0AB_14K_COMMON`, `KBAv2.0AB_14K_HDL_fixed.txt`의 `HDL`,
`HTN_PRS_weight.txt.gz`). 자신의 데이터 이름으로 바꿔 쓰세요.

## 목차

0. [잘 듣는 프롬프트를 쓰는 요령](#0-잘-듣는-프롬프트를-쓰는-요령)
1. [시작: 데이터·도구·설정 확인](#1-시작-데이터도구설정-확인)
2. [GWAS 실행](#2-gwas-실행)
3. [GWAS 결과 보기: 그림과 유의 locus](#3-gwas-결과-보기-그림과-유의-locus)
4. [유전율 (LDSC)](#4-유전율-ldsc)
5. [locus 분석: regional plot과 fine-mapping](#5-locus-분석-regional-plot과-fine-mapping)
6. [유전자·생물학적 해석 (자문 모델)](#6-유전자생물학적-해석-자문-모델)
7. [KNIH PheWeb 탐색과 다운로드](#7-knih-pheweb-탐색과-다운로드)
8. [PRS (다유전자 위험 점수)](#8-prs-다유전자-위험-점수)
9. [보고서와 정리](#9-보고서와-정리)
10. [한 번에 여러 단계](#10-한-번에-여러-단계)
11. [개인정보와 데이터 보호](#11-개인정보와-데이터-보호)
12. [로컬 모델에서만 되는 작업](#12-로컬-모델에서만-되는-작업)
13. [문제가 생겼을 때](#13-문제가-생겼을-때)
14. [하네스가 거절하는 요청](#14-하네스가-거절하는-요청)
15. [슬래시 명령과 비대화형 실행](#15-슬래시-명령과-비대화형-실행)

## 0. 잘 듣는 프롬프트를 쓰는 요령

| 요령 | 이유 |
|---|---|
| **파일·열·공변량을 이름으로 적기** | 에이전트는 애매하면 되묻습니다(규칙 6). 처음부터 적으면 한 번에 진행됩니다 |
| **한 번에 한 단계** | 하네스는 요청한 단계까지만 실행하고 다음 단계를 묻습니다(규칙 1). 여러 단계를 원하면 명시하세요(10절) |
| **locus는 순위·위치·변이 ID로** | `2번 locus`, `11:116662579`, `AX-95821414` 모두 됩니다. 순위는 `sam_peaks` 목록 기준 |
| **수치를 물을 때는 "도구 결과로"** | 모든 수치는 도구 결과에서 옵니다(규칙 5). "논문 값으로 추정해줘" 같은 요청에는 배경 지식이라고 표시하고 수치는 빼고 답합니다 |
| **결정은 직접** | PheWeb 코호트 선택, 다운로드, 부분 PRS 허용 여부는 에이전트가 묻습니다. 미리 답을 적어 두면 빨라집니다 |
| **긴 단계는 기다리기** | GWAS 전체 약 8–9분, PRS-CS 전체 약 6.5분(이 서버 실측, [USAGE.md](USAGE.md) 8절). `Esc`로 취소할 수 있습니다 |

## 1. 시작: 데이터·도구·설정 확인

**입력 데이터 둘러보기**
```
KO: 입력 폴더에 어떤 유전형 파일과 표현형 파일이 있는지 알려줘. 분석은 아직 하지 마.
EN: What genotype and phenotype files are in the input folder? Don't run any analysis yet.
```
→ `sam_status`: 유전형 세트(표본·변이 수), 표현형 표(열 이름·행 수만), sumstats·PRS weight 파일, 리소스, 완료된 단계

**표현형 파일의 열 확인**
```
KO: KBAv2.0AB_14K_HDL_fixed.txt에 어떤 열이 있어? GWAS에 쓸 수 있는 공변량도 골라줘.
EN: Which columns does KBAv2.0AB_14K_HDL_fixed.txt have, and which of them can be used as GWAS covariates?
```
→ `sam_status`(열 이름·행 수). 개인 값은 보여 주지 않습니다

**GWAS에 필요한 프로그램 점검**
```
KO: GWAS를 돌리기 전에 필요한 프로그램과 리소스가 다 있는지 확인해줘.
EN: Before running a GWAS, check that all required programs and resources are installed.
```
→ `sam_doctor steps=[gwas]`: plink2·regenie 버전, 누락 항목

**후속 분석 준비 상태 점검**
```
KO: LDSC, regional plot, fine-mapping, PRS에 필요한 도구와 참조 리소스가 준비됐는지 단계별로 알려줘.
EN: For LDSC, regional plots, fine-mapping and PRS, tell me step by step whether the tools and reference resources are ready.
```
→ `sam_doctor steps=[ldsc, regional, finemap, prs]`

**없는 도구 설치**
```
KO: PRS-CS를 쓸 수 있게 필요한 환경을 설치해줘.
EN: Install what is needed to run PRS-CS.
```
→ `sam_doctor steps=[prs]` → `sam_setup steps=[prs]`(설치 전 승인 창). bash로 pip/conda를 쓰지 않습니다

**현재 설정 보기 / 데이터 폴더 바꾸기**: 프롬프트 대신 명령을 씁니다.
```
/sam
/sam-data /data/KoGES/input /data/KoGES/resource
```

## 2. GWAS 실행

**기본 (연속형)**
```
KO: KBAv2.0AB_14K_HDL_fixed.txt의 HDL로 GWAS를 돌려줘. 공변량은 AGE, SEX와 주성분 4개.
EN: Run a GWAS of HDL from KBAv2.0AB_14K_HDL_fixed.txt with AGE, SEX and 4 principal components as covariates.
```
→ `sam_gwas stage=all`(표본 QC → step1 변이 → PCA → 표현형 표 → regenie step 1·2) → 표본 수, λGC, 유의 변이·locus 수, 상위 변이

**공변량·주성분 수 바꾸기**
```
KO: 같은 HDL GWAS를 공변량 AGE, SEX, BMI와 주성분 10개로 돌려줘.
EN: Run the HDL GWAS with AGE, SEX and BMI plus 10 principal components as covariates.
```
→ `sam_gwas covariates=[AGE,SEX,BMI] n_pc=10`. 열이 파일에 없으면 이유와 함께 멈춤

> 같은 표현형을 다른 설정으로 다시 돌리면 이전 step1·step2와 후속 결과(플롯, LDSC, locus)가 지워집니다(설정 지문, [WORKFLOW.md](WORKFLOW.md) 3.3).
> 두 설정을 비교하려면 출력 폴더를 따로 쓰세요(다른 디렉토리에서 `./sam agent` 실행).

**이진형 (환자-대조군)**
```
KO: 표현형 파일 pheno_t2d.txt의 T2D 열로 이진형 GWAS를 해줘. 1/2로 코딩돼 있어.
EN: Run a binary-trait GWAS of the T2D column in pheno_t2d.txt. It is coded 1/2.
```
→ `sam_gwas trait=bt`: 1/2를 0/1로 바꾸고 Firth 회귀. 환자 수가 100명 미만이면 경고

**단계별로 확인하며 실행**
```
KO: HDL GWAS를 prepare 단계까지만 해줘. 표본이 몇 명 매칭되고 몇 명이 빠지는지 먼저 보고 싶어.
EN: Run only the prepare stage of the HDL GWAS. I want to see how many samples match and how many are dropped first.
```
→ `sam_gwas stage=prepare`: 유전형 표본 수, QC 후 표본, 표현형 매칭 수, 결측 제외 수, 표현형 분포
```
KO: 좋아, 이제 step1과 step2를 이어서 돌려줘.
EN: Good, now run step 1 and then step 2.
```

**특정 염색체만 (빠른 확인)**
```
KO: 시간을 아끼고 싶어. HDL step2를 11번 염색체만 돌려줘.
EN: To save time, run HDL step 2 on chromosome 11 only.
```
→ `sam_gwas stage=step2 chromosomes=11`. 결과에 "부분 유전체" 경고. 부분 결과로는 LDSC를 하지 않습니다

**VCF에서 시작**
```
KO: 입력 폴더에는 imputed VCF만 있어. chr_all.dose.vcf.gz를 변환해서 HDL GWAS를 해줘. 기본 R² 기준을 써.
EN: The input folder only has an imputed VCF. Convert chr_all.dose.vcf.gz and run an HDL GWAS with the default R² filter.
```
→ `sam_gwas vcf=chr_all.dose.vcf.gz`(PLINK 변환은 `output/genotype/`에. 입력 폴더는 건드리지 않음)

**유전형 세트가 여러 개일 때**
```
KO: KBAv2.0AB_14K_COMMON 유전형으로 HDL GWAS를 해줘.
EN: Run the HDL GWAS on the KBAv2.0AB_14K_COMMON genotype set.
```
→ `sam_gwas genotype=KBAv2.0AB_14K_COMMON`

## 3. GWAS 결과 보기: 그림과 유의 locus

**Manhattan·QQ plot**
```
KO: HDL GWAS의 Manhattan plot과 QQ plot을 그려줘.
EN: Draw the Manhattan and QQ plots of the HDL GWAS.
```
→ `sam_plots`: λGC, 그림 파일(`output/plots/HDL/`). 그림을 볼 수 있는 모델이면 그림 설명도 함께

**유의한 locus 목록**
```
KO: HDL GWAS에서 유의한 locus를 보여줘. 각 locus의 위치, lead variant, -log10P를 표로 정리해줘.
EN: Show the significant loci of the HDL GWAS as a table with position, lead variant and -log10P.
```
→ `sam_peaks`: 독립 locus(P<5e-8, ±500 kb)

**기준 바꾸기**
```
KO: P<1e-6인 suggestive locus까지 보여줘. 묶는 거리는 250 kb로.
EN: Also show suggestive loci with P<1e-6, using a 250 kb clumping distance.
```
→ `sam_peaks p_threshold=1e-6 window_kb=250`

**상위 결과 요약**
```
KO: 가장 강한 3개 locus만 골라서 위치와 효과 방향(beta 부호)을 설명해줘.
EN: Pick the three strongest loci and describe their positions and effect directions (sign of beta).
```
→ `sam_peaks`의 결과로 답함(GWAS를 다시 돌리지 않음)

## 4. 유전율 (LDSC)

**단변량 SNP 유전율**
```
KO: HDL의 SNP 유전율을 LDSC로 추정하고 결과를 해석해줘.
EN: Estimate the SNP heritability of HDL with LDSC and interpret the result.
```
→ `sam_ldsc`: h²(SE, z), 절편, ratio, 평균 χ², 회귀 SNP 수, 경고(z<4, SNP<20만 등)

**워크숍 방식 (stratified LDSC)**
```
KO: 이전 워크숍처럼 baseline 주석을 모두 쓰는 stratified LDSC로도 돌려서 단변량 결과와 비교해줘.
EN: Also run stratified LDSC with all baseline annotations, as in the earlier workshop, and compare it with the univariate result.
```
→ `sam_ldsc model=baseline` 후 두 결과 비교

**이진형의 liability 척도**
```
KO: T2D LDSC 결과를 liability 척도로 바꿔줘. 모집단 유병률은 0.1로 해.
EN: Convert the T2D LDSC result to the liability scale with a population prevalence of 0.1.
```
→ `sam_ldsc population_prevalence=0.1`

**해석만 다시 묻기**
```
KO: 절편이 1.02인데 이게 교란이 있다는 뜻이야, 아니면 다유전 신호야? 방금 결과로만 설명해줘.
EN: The intercept is 1.02 — does that mean confounding or polygenic signal? Explain using only the result we just got.
```

## 5. locus 분석: regional plot과 fine-mapping

**regional plot**
```
KO: 2번 locus로 regional plot을 그려줘.
EN: Draw a regional plot for locus 2.
```
→ `sam_regional locus=2`: LD(r², GWAS 표본에서 계산), 재조합률, 유전자 트랙(Ensembl)

**위치나 변이 ID로 지정, 창 크기 바꾸기**
```
KO: 11:116662579 주변 ±250 kb로 regional plot을 그려줘.
EN: Draw a regional plot of ±250 kb around 11:116662579.
```
→ `sam_regional locus=11:116662579 window_kb=250`
```
KO: AX-95821414 변이를 중심으로 regional plot을 그려줘.
EN: Draw a regional plot centred on the variant AX-95821414.
```

**fine-mapping (SuSiE)**
```
KO: 2번 locus를 SuSiE로 fine-mapping 해줘. credible set마다 크기, 대표 변이, PIP, 순도를 정리해줘.
EN: Fine-map locus 2 with SuSiE. For each credible set, give its size, top variant, PIP and purity.
```
→ `sam_finemap locus=2`: credible set, PIP, 순도, LD 일관성 진단

**fine-mapping 결과를 그림에 표시**
```
KO: 같은 locus에서 fine-mapping을 하고 credible set이 표시된 regional plot도 그려줘.
EN: Fine-map the same locus and draw the regional plot with the credible sets marked.
```
→ `sam_finemap` → `sam_regional`(순서가 중요: fine-mapping이 먼저여야 그림에 표시됨). 템플릿 `/locus HDL 2`와 같음

**SuSiE 설정 바꾸기**
```
KO: 신호 수 최대 5개, coverage 0.99로 다시 fine-mapping 해줘.
EN: Re-run the fine-mapping with at most 5 signals and 99% coverage.
```
→ `sam_finemap L=5 coverage=0.99`
```
KO: 순도 기준을 0.8로 올려서 신뢰할 만한 credible set만 남겨줘.
EN: Raise the purity threshold to 0.8 so that only reliable credible sets remain.
```
→ `sam_finemap min_abs_corr=0.8`

**결과의 한계 묻기**
```
KO: credible set이 4개 나왔는데, 인과 변이가 4개라고 말해도 돼? 무엇을 더 확인해야 해?
EN: There are 4 credible sets. Can I say there are 4 causal variants? What else should I check?
```

## 6. 유전자·생물학적 해석 (자문 모델)

자문 모델(`sam_consult`, 기본은 주 모델과 같은 Gemma 4 31B)은 "미검증 2차 의견"입니다. `region`을 주면 하네스가 Ensembl에서
그 구간의 실제 유전자 목록을 받아 근거로 붙입니다. **rsID로 유전자를 맞히는 것은 모든 로컬 모델이 자주 틀립니다**
([BENCHMARK.md](BENCHMARK.md) 5절). 유전자는 반드시 구간을 주고 물으세요.

**locus 주변 유전자와 HDL의 관련**
```
KO: 2번 locus(±500kb)의 유전자 중 HDL과 관련 있을 만한 후보를 자문 모델에 물어봐줘.
EN: Ask the consultant model which genes within ±500 kb of locus 2 are plausible candidates for HDL.
```
→ `sam_consult region=11:116162579-117162579`: 실제 유전자 목록을 붙여 질문, 답에 "미검증" 표시

**결과 해석에 대한 2차 의견**
```
KO: 방금 LDSC 결과(h², 절편, z)를 자문 모델에게 보여주고 해석이 타당한지 물어봐줘.
EN: Show the LDSC result we just got (h², intercept, z) to the consultant model and ask whether the interpretation holds.
```

**특정 유전자에 대한 배경 지식**
```
KO: CETP가 HDL에 어떤 영향을 주는지 배경 지식으로 짧게 설명해줘. 수치는 빼고.
EN: Briefly explain, as background knowledge, how CETP affects HDL. Leave out numbers.
```
→ 도구 없이 답하되 "배경 지식"으로 표시(규칙 5)

## 7. KNIH PheWeb 탐색과 다운로드

KNIH PheWeb에는 같은 표현형이 여러 코호트(KBA+BBJ, KBA_126K, KBA_187K, KBA_HLA, KBA_validated)로 있고, PRS weight는 PRS와 lcPRS
두 방식이 있습니다. 서버가 느리지만(수십 KB/s), 끊겨도 같은 요청으로 이어 받습니다.

**표현형 찾기**
```
KO: KNIH PheWeb에 LDL 콜레스테롤 GWAS 요약 통계가 어떤 코호트로 있는지 보여줘. 표본 수도 같이.
EN: Which cohorts in KNIH PheWeb have GWAS summary statistics for LDL cholesterol? Include the sample sizes.
```
→ `sam_pheweb action=search query="LDL" kind=sumstats`: 코드(예: `KBA_BBJ_LDL-C`, `KBA_126K_LDL-C`, `KBA_187K_LDL-C`), N

**PRS weight만 찾기**
```
KO: 혈압 관련 PRS weight 파일이 있는지 찾아줘. PRS와 lcPRS를 구분해서.
EN: Find blood-pressure PRS weight files, separating PRS and lcPRS.
```
→ `sam_pheweb action=search query="blood pressure" kind=prs_weight`(예: `SBP_PRS_weight`, `DBP_lcPRS_weight`)

**다운로드**
```
KO: KBA_187K_TG 요약 통계를 받아줘.
EN: Download the KBA_187K_TG summary statistics.
```
→ `sam_pheweb action=download code=KBA_187K_TG`: URL·크기를 보여 주고 승인 후 `output/downloads/`에 저장

**끊긴 다운로드 이어 받기**
```
KO: 아까 받다가 끊긴 KBA_187K_HTN 다운로드를 이어서 받아줘.
EN: Resume the KBA_187K_HTN download that was interrupted earlier.
```
→ 같은 `sam_pheweb download`. 남아 있는 `.part` 파일에서 이어 받음

## 8. PRS (다유전자 위험 점수)

**입력 폴더의 weight 파일로 점수 계산**
```
KO: 입력 폴더의 HTN_PRS_weight.txt.gz로 PRS를 계산하고, 사용된 변이 비율과 점수 분포를 요약해줘.
EN: Compute a PRS with HTN_PRS_weight.txt.gz in the input folder and summarize the share of variants used and the score distribution.
```
→ `sam_prs method=weights`: 매칭률(이 데이터 19%), 점수 분포. 매칭률이 낮으면 경고

**PheWeb weight를 찾아서 계산**
```
KO: 수축기 혈압 PRS를 계산하고 싶어. PheWeb에서 weight 파일을 찾아서 고르게 해줘.
EN: I want a systolic blood pressure PRS. Find weight files in PheWeb and let me choose.
```
→ `sam_pheweb search` → 사용자 선택 → `download`(승인) → `sam_prs method=weights`

**PRS-CS (요약 통계에서 새 weight 추정)**
```
KO: KBA_187K_HTN 요약 통계로 PRS-CS를 돌려서 고혈압 PRS를 계산해줘. LD 참조는 동아시아(EAS)로.
EN: Run PRS-CS on the KBA_187K_HTN summary statistics to compute a hypertension PRS, with the East Asian (EAS) LD reference.
```
→ (없으면 `sam_pheweb download`) → `sam_prs method=prscs`: GWAS 표본 수는 PheWeb 정보에서 자동, 22개 염색체 약 6.5분

**일부 염색체만 (빠른 시험)**
```
KO: 시험 삼아 PRS-CS를 16번 염색체만 돌려줘. 부분 점수라는 건 알고 있어.
EN: As a quick test, run PRS-CS on chromosome 16 only. I understand the score will be partial.
```
→ `sam_prs method=prscs chromosomes=16`(부분 점수 승인 창, 결과에 "partial" 표시)

**외부 요약 통계 파일로**
```
KO: 입력 폴더의 my_bmi_sumstats.txt로 PRS-CS를 해줘. GWAS 표본 수는 120000이야.
EN: Run PRS-CS with my_bmi_sumstats.txt in the input folder. The GWAS sample size is 120000.
```
→ `sam_prs method=prscs sumstats_file=my_bmi_sumstats.txt n_gwas=120000`(PheWeb 형식, 또는 SNP A1 A2 BETA와 SE나 P 열)

**결과 이름 붙이기와 해석**
```
KO: 결과 이름은 HTN_prscs_full로 해줘. 끝나면 이 점수를 연구에 쓸 때 주의할 점(표본 중복, 검증)을 알려줘.
EN: Name the result HTN_prscs_full. When it finishes, tell me what to watch out for when using this score (sample overlap, validation).
```
→ `sam_prs name=HTN_prscs_full`

## 9. 보고서와 정리

**보고서 파일 만들기**
```
KO: 지금까지 한 분석을 output/report.md로 정리하고 핵심 결과를 요약해줘.
EN: Write everything run so far to output/report.md and summarize the key results.
```
→ `sam_report`. 템플릿 `/sam-report`와 같음

**발표용 요약**
```
KO: 랩 미팅용으로 HDL 분석 결과를 슬라이드 3장 분량 bullet로 정리해줘. 수치는 도구 결과만 써.
EN: Summarize the HDL results as bullets for three lab-meeting slides, using only numbers from tool results.
```

**방법 단락 초안**
```
KO: 논문 Methods에 넣을 GWAS·LDSC·fine-mapping 방법 단락을 영어로 써줘. 실제로 쓴 프로그램 버전과 설정을 기록에서 가져와.
EN: Draft a Methods paragraph for the GWAS, LDSC and fine-mapping, taking program versions and settings from the run records.
```
→ `sam_status`, `output/manifest.jsonl`·각 단계 `summary.json`의 버전·파라미터 사용

**남은 경고 정리**
```
KO: 지금까지 나온 경고를 모두 모아서 무엇이 문제이고 어떻게 해결할 수 있는지 정리해줘.
EN: Collect every warning so far and explain what each means and how it could be addressed.
```

## 10. 한 번에 여러 단계

하네스는 요청한 단계까지만 실행합니다. 여러 단계를 이어서 원하면 명시하세요.

**GWAS 후 기본 후속 분석까지**
```
KO: HDL GWAS를 하고, 끝나면 묻지 말고 Manhattan/QQ plot, 유의 locus 목록, LDSC까지 이어서 해줘.
EN: Run the HDL GWAS and then, without asking, go on to the Manhattan/QQ plots, the list of significant loci and LDSC.
```
→ `sam_gwas` → `sam_plots` → `sam_peaks` → `sam_ldsc`. 템플릿 `/gwas HDL` + `/post-gwas HDL`과 같음

**상위 locus 모두 fine-mapping**
```
KO: 유의 locus 상위 3개에 대해 각각 fine-mapping과 credible set이 표시된 regional plot을 만들어줘.
EN: For each of the top 3 significant loci, run fine-mapping and draw a regional plot with the credible sets.
```
→ locus마다 `sam_finemap` → `sam_regional`

**전체 파이프라인**
```
KO: HDL로 GWAS부터 플롯, locus, LDSC, 상위 locus fine-mapping, 고혈압 PRS(weight 파일), 보고서까지 전부 해줘.
EN: Do the whole pipeline for HDL: GWAS, plots, loci, LDSC, fine-mapping of the top locus, the hypertension PRS from the weight file, and the report.
```

## 11. 개인정보와 데이터 보호

클라우드 모델을 쓰면 개인 단위 파일(표현형 값, .fam, PC, 개인별 점수) 읽기가 자동으로 막힙니다. 로컬 모델은 기본으로 허용입니다.
입력·리소스 폴더는 어떤 모델이든 쓸 수 없습니다(커널 수준 보호).

**지금 보호 상태 묻기**
```
KO: 지금 개인정보 모드가 켜져 있어? 입력 폴더는 쓰기가 막혀 있어?
EN: Is privacy mode on right now? Is the input folder write-protected?
```
→ 시스템 안내에 있는 설정으로 답함. 정확한 값은 `/sam`

**집계 정보로 바꿔 묻기** (개인 값 대신)
```
KO: HDL 값의 분포(평균, 표준편차, 백분위)를 알려줘. 개인 값은 필요 없어.
EN: Give me the distribution of HDL (mean, SD, percentiles). I don't need individual values.
```
→ `sam_gwas stage=prepare` 결과의 `phenotype_distribution`(이미 했다면 그 결과 사용)

**로컬 모델에서도 개인 값 보호**
```
/sam-privacy on
```

## 12. 로컬 모델에서만 되는 작업

로컬 모델은 개인 단위 파일을 직접 읽고, 결과를 `output/` 아래에 쓸 수 있습니다(입력 폴더는 읽기만). 클라우드 모델에서는
개인정보 모드 때문에 거절됩니다.

**표현형 변환 후 GWAS**
```
KO: KBAv2.0AB_14K_HDL_fixed.txt의 HDL을 rank-based inverse normal 변환한 열 HDL_rint를 만든 표를 output/derived/HDL_rint.txt로 저장하고, 그 표로 HDL_rint GWAS를 해줘. 원본 파일은 건드리지 마.
EN: Create a table with an HDL_rint column (rank-based inverse normal transform of HDL in KBAv2.0AB_14K_HDL_fixed.txt), save it as output/derived/HDL_rint.txt, and run an HDL_rint GWAS from it. Do not touch the original file.
```
→ bash(Python)로 `output/derived/`에 새 표 작성 → `sam_gwas phenotype=HDL_rint phenotype_file=output/derived/HDL_rint.txt`
  (표현형 파일 이름은 입력 폴더 다음으로 출력 폴더에서도 찾습니다)

**결측 제외한 사본 만들기**
```
KO: HDL이 결측인 행을 뺀 사본을 output/derived/에 만들어줘. 몇 행이 빠졌는지도 알려줘.
EN: Make a copy without the rows where HDL is missing in output/derived/, and tell me how many rows were removed.
```

**하위 집단 분석용 표**
```
KO: 여성(SEX=2)만 남기고 HDL 열 이름을 HDL_female로 바꾼 표를 output/derived/HDL_female.txt로 만들고, 그 표로 HDL_female GWAS를 해줘. 공변량은 AGE와 주성분 4개.
EN: Make a table with women only (SEX=2) and the HDL column renamed to HDL_female, save it as output/derived/HDL_female.txt, and run an HDL_female GWAS on it with AGE and 4 principal components as covariates.
```
→ 결과는 표현형 이름별로 저장됩니다(`output/gwas/<표현형>/`). 열 이름을 그대로 `HDL`로 두면 기존 HDL 결과를 덮어씁니다.
  한 성별만 남기면 SEX는 값이 하나뿐이라 공변량에서 빼야 합니다

## 13. 문제가 생겼을 때

**실패 원인 묻기**
```
KO: 방금 단계가 왜 실패했는지 오류와 로그를 보고 설명하고, 고칠 방법을 제안해줘.
EN: Explain why the last step failed, using its error and log, and suggest a fix.
```
→ 도구 오류의 `hint`와 `output/logs/<시각>_<단계>.log`를 읽고 원인·해결 제안

**경고의 의미**
```
KO: "regression SNP가 20만 개 미만"이라는 LDSC 경고는 무슨 뜻이고 결과를 얼마나 믿어도 돼?
EN: What does the LDSC warning "fewer than 200k regression SNPs" mean, and how much can I trust the result?
```

**어디까지 했는지 확인**
```
KO: 이 출력 폴더에서 지금까지 끝난 단계와 각 결과 파일 위치를 알려줘.
EN: Which steps have been completed in this output folder, and where are their result files?
```
→ `sam_status`의 완료 단계와 출력 위치

**같은 단계 다시 실행**
```
KO: HDL step2만 다시 돌려줘.
EN: Re-run step 2 of the HDL GWAS only.
```
→ `sam_gwas stage=step2`(step1 결과가 현재 설정과 맞을 때만)

## 14. 하네스가 거절하는 요청

이런 요청에는 에이전트가 이유를 설명하고 대안을 제시하는 것이 정상입니다.

| 요청 예 (KO / EN) | 하네스의 반응 |
|---|---|
| 입력 파일을 고쳐서 같은 파일에 덮어써줘 / Edit the input file and overwrite it | 읽기 전용이라 거절, `output/`에 사본을 제안. 다른 방식으로 시도해도 커널이 막음 |
| HDL 상위 10명의 IID를 보여줘 (클라우드 또는 privacy on) / Show the IIDs of the top 10 people | 개인 단위 정보라 거절, 분포 같은 집계를 제안 |
| conda로 regenie를 설치해줘 / Install regenie with conda | bash 설치 금지, `sam_doctor` → `sam_setup`으로 안내(승인) |
| wget으로 이 파일 받아줘 / Download this file with wget | bash 다운로드 금지. KNIH PheWeb은 `sam_pheweb`, 그 밖은 사용자가 입력 폴더에 두도록 안내 |
| 내 HDL GWAS 결과로 PRS-CS를 해줘 / Run PRS-CS on my own HDL GWAS | 발견 표본과 대상 표본이 같아 거절, 외부 요약 통계(PheWeb)를 제안 |
| 11번 염색체만 돌린 GWAS로 LDSC를 해줘 / Run LDSC on the chromosome-11-only GWAS | 부분 유전체라 거절(에이전트는 우회 불가), 전체 step2를 제안 |
| LDL로 GWAS를 해줘 (LDL 열이 없음) / Run a GWAS of LDL (no LDL column) | 없다고 보고하고 있는 표현형을 안내. 결과를 지어내지 않음 |

## 15. 슬래시 명령과 비대화형 실행

**프롬프트 템플릿** (자주 쓰는 요청의 단축형)

| 명령 | 같은 뜻의 프롬프트 |
|---|---|
| `/gwas HDL KBAv2.0AB_14K_HDL_fixed.txt` | "이 파일의 HDL로 GWAS를 해줘" / "Run a GWAS of HDL from this file" |
| `/post-gwas HDL` | "플롯, 유의 locus, LDSC를 하고 어느 locus를 볼지 물어봐줘" / "Plots, significant loci and LDSC, then ask which locus to examine" |
| `/locus HDL 2` | "2번 locus를 fine-mapping하고 credible set이 표시된 regional plot을 그려줘" / "Fine-map locus 2 and draw the regional plot with credible sets" |
| `/prs 고혈압 weights` | "고혈압 PRS를 weight 파일로 계산해줘" / "Compute a hypertension PRS from a weight file" |
| `/sam-report` | "보고서를 만들고 요약해줘" / "Write the report and summarize" |

**스크립트에서 한 번에 실행** (화면 없이)
```bash
./sam agent --input sam-data/input --resource sam-data/resource --approvals deny \
    -p "HDL GWAS 결과에서 유의한 locus 목록을 보여줘" < /dev/null
./sam agent --input sam-data/input --resource sam-data/resource --approvals deny --mode json \
    -p "Show the significant loci of the HDL GWAS" < /dev/null > events.jsonl
```
- 화면이 없으면 승인이 필요한 동작(설치, 다운로드, 부분 PRS)은 `--approvals`로 정합니다(기본 ask → 거부).
- `< /dev/null`을 꼭 붙이세요([USAGE.md](USAGE.md) 7절).
