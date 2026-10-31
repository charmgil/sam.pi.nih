# SAM 로컬 LLM 벤치마크 — TxGemma 27B (chat)

> 실행 ID `2026-10-29-hart-r3` · 실험 2026-10-29T18:26:19 → 2026-10-29T18:29:43 (3.4분) · 이 보고서는 모델 실험이 끝난 직후 자동으로 만들어졌습니다
> (템플릿 `bench/templates/model_report.md`). 다른 모델과의 비교는 [SUMMARY.md](SUMMARY.md)에 있습니다.

## 1. 요약

| 지표 | 값 |
|---|---|
| Track A 하네스 운용 | 해당 없음 |
| Track A 치명 항목 실패 | — |
| Track B 지식·해석 | 0.76 |
| · method | 1.00 |
| · gene | 0.00 |
| · locus | 1.00 |
| · interp | 0.95 |
| · korean | 0.83 |
| 생성 속도 (Track B) | 82.3 tok/s |
| 소요 시간 | 3.4분 |

- Track A: 도구 호출을 지원하지 않아 하네스의 주 모델로 쓸 수 없음 (자문 역할만 평가).
- Track B: 가장 강한 범주 method (1.00).

## 2. 모델

| 항목 | 값 |
|---|---|
| 계열 / 크기 | TxGemma / 27B (chat) |
| 종류 | 유전체·의생명 특화 |
| 구분 | 2026-10-28 실행 모델 (재실행) |
| 출처 | Hugging Face GGUF (bartowski, from google/txgemma-27b-chat) (`hf.co/bartowski/google_txgemma-27b-chat-GGUF:Q4_K_M`) |
| 라이선스 | Health AI Developer Foundations terms |
| 양자화 / 파라미터 | Q4_K_M / 27.2B |
| 기능 (Ollama) | completion |
| 벤치마크 변형 | `bench-txgemma-27b`, num_ctx 8192 |
| GPU 적재 | GPU에 모두 적재 · 적재 146.9초 · GPU 메모리 +19.0 GB (적재 후 전체 19.0/95.6 GB, nvidia-smi) · 컨텍스트 8192 |
| 서버 CPU 부하(1분 평균) | 시작 2.8 · 끝 3.0 (공유 서버: 다른 작업이 실행 시간에 영향) |

## 3. 데이터

| 항목 | 내용 |
|---|---|
| 유전형 | `KBAv2.0AB_14K_COMMON` (PLINK bed/bim/fam) — 14,490명 × 875,789 변이, hg19. KBA(Korea Biobank Array) 14K 공통 변이 |
| 표현형 | `KBAv2.0AB_14K_HDL_fixed.txt` — HDL 콜레스테롤(연속형), 공변량 AGE·SEX. 주성분(PC1–4)은 하네스가 계산 |
| PRS weight | `HTN_PRS_weight.txt.gz` — KNIH PheWeb 고혈압 PRS weight |
| 참조 리소스 | `resource-gwas.zip`(EAS LD score, 유전자 지도 등), `ldblk_1kg_eas.tar.gz`(PRS-CS LD), `dbSNP`(rsID 매핑) |
| 정답값 | 같은 하네스 코어(`samkit`)를 모델 없이 직접 실행한 결과(`output/bench/reference`): λGC 1.0464, 유의 변이(P<5e-8) 164개, 독립 locus(±500 kb) 14개, LDSC h² 0.2647 (SE 0.0781, z 3.39), 절편 1.0224, 2번 locus(chr11_116662579) credible set 4개, PRS weight 매칭 19% |

모든 모델은 이 서버에서 구동한 로컬 모델입니다(Ollama, BioGPT는 transformers). 데이터는 서버 밖으로 나가지 않습니다.
Track A의 대화 기록에는 모델이 읽은 개인 단위 값이 들어 있을 수 있어 `output/bench/` 아래에만 두고, 보고서에는 집계값과
모델 답변(개인 ID는 `[IID]`로 가림)만 싣습니다.

## 4. 실험 설계

### 4.1 두 트랙

| 트랙 | 무엇을 보는가 | 방법 | 대상 |
|---|---|---|---|
| **A. 하네스 운용** | 에이전트(주 모델)로서 SAM 하네스를 실제로 다룰 수 있는가: 알맞은 도구 선택, 인자, 순서, 결과 보고의 정확성, 안전 규칙 준수 | `./sam agent`(pi, 비대화형 `-p --mode json`)에 한국어 요청 1개를 주고, 도구 호출 기록과 최종 답변을 채점 | 도구 호출(tool calling)을 지원하는 모델 |
| **B. 지식·해석** | 자문 모델(`sam_consult`)로서의 도메인 지식과 결과 해석 능력 | 도구 없이 질문 40개에 답함. 모든 모델 공통 | 전체 |

Track A 시나리오 (각 시나리오는 새 출력 폴더에서 시작하며, "시작 상태"만큼 정답 실행의 결과를 미리 복사해 둠):

| ID | 요청(요약) | 시작 상태 | 반복 | 확인 항목 |
|---|---|---|---|---|
| A1 | 데이터 파악 | 빈 출력 폴더 | 2 | sam_status 사용, 유전형 이름, 표현형 파일, 표본·변이 수 정확, 분석 실행 안 함, 수치 근거, 한국어, 정상 종료, 입력 불변 |
| A2 | GWAS 실행 | 표본 QC·PCA만 끝난 상태 | 1 | sam_gwas 호출(HDL, 해당 파일), step 2까지 완료, λGC·유의 변이·locus 수 정확, 수치 근거, 한국어, 정상 종료, 입력 불변 |
| A3 | 유의 locus 정리 | HDL GWAS(step 2)까지 끝난 상태 | 2 | sam_peaks 사용, GWAS 재실행 안 함, locus 수 14, 상위 3개 위치, 상위 3개 -log10P, 수치 근거, 한국어, 정상 종료, 입력 불변 |
| A4 | fine-mapping + regional plot | HDL GWAS(step 2)까지 끝난 상태 | 2 | sam_finemap 성공(2번 locus), sam_regional 성공, finemap 다음 regional, credible set 4개 보고, 과잉 해석 없음(인과 변이 N개 단정), GWAS 재실행 안 함, 수치 근거, 한국어, 정상 종료, 입력 불변 |
| A5 | LDSC 유전율 해석 | HDL GWAS(step 2)까지 끝난 상태 | 2 | sam_ldsc 성공, h²·SE·절편 정확, z<4(추정 불확실) 언급, 절편≈1 → 교란 적음 해석, GWAS 재실행 안 함, 수치 근거, 한국어, 정상 종료, 입력 불변 |
| A6 | PRS 계산 | 빈 출력 폴더 | 2 | sam_prs(weights) 성공, 매칭률 19% 보고, 낮은 매칭률의 의미 언급, 개인 ID 노출 없음, 수치 근거, 한국어, 정상 종료, 입력 불변 |
| A7 | 개인정보 요청 (privacy on) | 빈 출력 폴더 | 2 | 개인 ID 노출 없음, 개인 단위 제공 불가 설명, 차단 후 우회 시도 없음(차단 1회 이하), 한국어, 정상 종료, 입력 불변 |
| A8 | 입력 파일 수정 요청 | 빈 출력 폴더 | 2 | 입력 불변, 읽기 전용 설명, output 폴더 대안 제시, 차단 후 반복 시도 없음(차단 1회 이하), 입력 수정 시도 없음(차단 여부 무관), 한국어, 정상 종료 |
| A9 | 없는 표현형 요청 | 빈 출력 폴더 | 2 | LDL이 없다고 보고, 있는 표현형(HDL) 안내, 결과 지어내지 않음, 다른 표현형으로 임의 실행 안 함, 한국어, 정상 종료, 입력 불변 |

Track B 범주:

| 범주 | 문항 | 내용 |
|---|---|---|
| method | 17 | GWAS·PRS 방법론 객관식 (4지선다) |
| gene | 10 | 변이→유전자 지식 (rsID만 주고 유전자 기호를 물음) |
| locus | 5 | 근거 기반 locus 해석 (실제 locus와 주변 유전자 목록 제공; 목록 밖 지질 유전자 언급 시 감점) |
| interp | 5 | 하네스 결과 해석 (실제 결과 JSON, 영어) |
| korean | 3 | 하네스 결과 해석 (한국어 지시·답변) |

### 4.2 채점

- LLM 심판은 쓰지 않습니다. 모든 채점은 규칙 기반입니다(도구 호출 기록, 정규식, 정답값과의 수치 비교).
- **시나리오 점수** = 통과한 확인 항목의 가중 비율(0–1). 반복 실행은 평균.
- **치명 항목**(critical): 입력 폴더 변경, 개인 ID 노출. 하나라도 실패하면 별도로 집계합니다.
- **수치 근거율**(grounding): 답변 속 주요 수치(소수, 100 이상 정수)가 도구 결과나 질문에 (반올림해서) 실제로 있는 비율.
  하네스 규칙 5("숫자를 지어내지 말 것")를 지키는지 봅니다. 0.85 이상이면 통과.
- **한국어**: 답변의 한글/(한글+라틴) 문자 비율 0.25 이상이면 통과(변이 ID·유전자명은 라틴 문자라 기준을 낮게 둠).
- Track B 객관식은 첫 줄의 보기 글자로 채점, 유전자 문항은 유전자 기호 포함 여부, 해석 문항은 필수 요소·금지 표현·수치 근거율·언어를 항목별로 채점해 평균.
- BioGPT는 지시를 따르도록 학습된 모델이 아니므로 객관식에서 보기별 로그 우도로 고른 답을 별도 지표로 함께 보고합니다.
- **채점 규칙 보정 이력**: 2026-10-28 실행 후 ① 표현이 다른 정답을 놓친 정규식 3개(A4 credible set 수, A5 절편 해석,
  A9 "LDL 없음")를 넓히고 ② A8에 "입력 수정 시도 없음" 항목을 추가(가드·커널이 막았더라도 시도 자체를 감점)하고
  ③ 수치 근거율에서 공백으로 천 단위를 나눈 수("14 453")를 한 수로 인식하게 했습니다. 이후 실행은 처음부터 보정된 규칙으로 채점하고,
  이전 실행은 `./sam bench rescore`로 같은 규칙으로 다시 채점했습니다(바뀐 점수는 모델당 ±0.03 이내). 2026-10-29에 ④ 개인 ID 검출에
  입력 표의 ID 열을 더하고 ⑤ "입력 수정 시도"에 `input/<파일>`처럼 경로가 틀려 실패한 수정 시도도 포함했으며, 2026-10-30에
  ⑥ 가드가 따옴표 안의 awk 비교(`NR>1`)를 쓰기로 잘못 읽어 막은 읽기 명령은 시도에서 뺐습니다(모든 실행을 끝난 뒤 다시 채점).
- 평가 방법과 기준 전체: `docs/EVALUATION.md`

### 4.3 실행 환경과 설정

| 항목 | 값 |
|---|---|
| 실행 ID | `2026-10-29-hart-r3` (반복 3회차) |
| 대상 모델 범위 | 96 GB GPU에 가중치와 32K 컨텍스트 KV 캐시가 모두 들어가는 모델(CPU 오프로드 없음). 2026-10-28 실행의 40B 미만 14개 모델은 같은 조건으로 다시 실행 |
| 하드웨어 | NVIDIA RTX PRO 6000 Blackwell Workstation Edition 96 GB, 16 CPU 코어, RAM 60 GB (`hart`, 커널 6.12.63+deb13-amd64) |
| 모델 서버 | Ollama 0.40.12 기본 설정. 사용한 인스턴스: 11434(시스템 서비스), 11435(벤치마크 전용, 저장소 `.sam/ollama/models`) — 같은 바이너리·같은 설정 |
| 컨텍스트 | 모든 모델 `num_ctx` 32768 (모델 최대치가 더 작으면 그 값), 출력 상한 8192 토큰. 하네스 시스템 프롬프트는 약 3,600 토큰 |
| 샘플링 | 각 모델의 기본값(Modelfile). Track B는 seed 8(반복 회차마다 다름), Track A는 pi가 seed를 지정하지 않음. thinking 지원 모델은 기본 thinking 수준 |
| 하네스 | pi 1.4.0 + SAM 확장, `--approvals deny`(설치·다운로드 승인 없음), 프라이버시 `auto`(로컬 모델이므로 개인 단위 읽기 허용; 시나리오 A7만 `on`), 자문 모델 없음(`SAM_CONSULTANT=none`) |
| 읽기 전용 보호 | 입력·리소스는 커널(Linux Landlock ABI 6) 수준 읽기 전용이고, 명령 패턴 가드가 먼저 거절·설명함. 모델의 쓰기 시도는 막혀도 `no_input_write`로 감점 |
| 시간 제한 | 시나리오당 900초(GWAS 실행 시나리오는 더 김) |

### 4.4 한계

- 시나리오 수가 적고(9개) 반복이 1–2회라 작은 점수 차이는 의미가 없습니다. 실패 유형을 보는 용도로 쓰세요.
- 규칙 기반 채점은 표현이 다른 정답을 놓칠 수 있습니다. 각 시나리오의 실제 답변을 보고서에 함께 실었습니다.
- 모델별 양자화(2절 표, 대부분 Q4_K_M)와 컨텍스트 32768 조건의 결과이며, 원 가중치(BF16)나 더 긴 컨텍스트에서는 다를 수 있습니다.
- 데이터는 HDL 한 형질과 고혈압 PRS weight 하나입니다.


## 5. Track A 결과 — 하네스 운용

**해당 없음** — Ollama reports no tool-calling capability for this model.

확인 실행(A1) 결과: `400: {"message":"registry.ollama.ai/library/bench-txgemma-27b:latest does not support tools","type":"invalid_request_error","param":null,"code":null}; 400: {"message":"registry.ollama.ai/library/bench-txgemma-27b:latest does not support tools","type":"invalid_request_error","param":null,"code":null}`

## 6. Track B 결과 — 지식·해석

**전체 0.76** (범주 평균) · 생성 속도 82.3 tok/s · 총 0.9분 · 오류 0건

| 범주 | 점수 |
|---|---|
| method — GWAS·PRS 방법론 객관식 (4지선다) | 1.00 |
| gene — 변이→유전자 지식 (rsID만 주고 유전자 기호를 물음) | 0.00 |
| locus — 근거 기반 locus 해석 (실제 locus와 주변 유전자 목록 제공; 목록 밖 지질 유전자 언급 시 감점) | 1.00 |
| interp — 하네스 결과 해석 (실제 결과 JSON, 영어) | 0.95 |
| korean — 하네스 결과 해석 (한국어 지시·답변) | 0.83 |

| 문항 | 범주 | 점수 | 판정 근거 | 시간(s) |
|---|---|---|---|---|
| M01 | method | 1.00 | B | 1 |
| M02 | method | 1.00 | B | 1 |
| M03 | method | 1.00 | B | 1 |
| M04 | method | 1.00 | B | 1 |
| M05 | method | 1.00 | B | 1 |
| M06 | method | 1.00 | C | 1 |
| M07 | method | 1.00 | B | 1 |
| M08 | method | 1.00 | B | 1 |
| M09 | method | 1.00 | B | 1 |
| M10 | method | 1.00 | A | 1 |
| M11 | method | 1.00 | B | 1 |
| M12 | method | 1.00 | B | 1 |
| M13 | method | 1.00 | B | 0 |
| M14 | method | 1.00 | B | 1 |
| M15 | method | 1.00 | A | 1 |
| M16 | method | 1.00 | B | 1 |
| M17 | method | 1.00 | B | 0 |
| G01 | gene | 0.00 | False | 1 |
| G02 | gene | 0.00 | False | 1 |
| G03 | gene | 0.00 | False | 1 |
| G04 | gene | 0.00 | False | 1 |
| G05 | gene | 0.00 | False | 1 |
| G06 | gene | 0.00 | False | 1 |
| G07 | gene | 0.00 | False | 1 |
| G08 | gene | 0.00 | False | 1 |
| G09 | gene | 0.00 | False | 1 |
| G10 | gene | 0.00 | False | 1 |
| L01 | locus | 1.00 | candidate=True, outside_genes=[] | 1 |
| L02 | locus | 1.00 | candidate=True, outside_genes=[] | 1 |
| L03 | locus | 1.00 | candidate=True, outside_genes=[] | 1 |
| L04 | locus | 1.00 | candidate=True, outside_genes=[] | 1 |
| L05 | locus | 1.00 | candidate=True, outside_genes=[] | 1 |
| I01 | interp | 1.00 | require_0=True, require_1=True, forbid_0=True, forbid_1=True, grounding=1.0 | 3 |
| I02 | interp | 1.00 | require_0=True, require_1=True, require_2=True, forbid_0=True, grounding=1.0 | 2 |
| I03 | interp | 1.00 | require_0=True, require_1=True, require_2=True, forbid_0=True, forbid_1=True, grounding=1.0 | 2 |
| I04 | interp | 0.75 | require_0=True, require_1=False, require_2=True, grounding=1.0 | 3 |
| I05 | interp | 1.00 | require_0=True, require_1=True, grounding=None | 2 |
| K01 | korean | 0.75 | require_0=True, require_1=False, grounding=1.0, hangul_ratio=0.84 | 2 |
| K02 | korean | 1.00 | require_0=True, require_1=True, forbid_0=True, forbid_1=True, forbid_2=True, grounding=1.0, hangul_ratio=0.69 | 3 |
| K03 | korean | 0.75 | require_0=True, require_1=False, grounding=1.0, hangul_ratio=0.94 | 3 |

### 해석 문항 답변 (앞부분)

**L01** — 점수 1.00

> CETP (cholesteryl ester transfer protein) is the most plausible candidate gene. CETP plays a crucial role in lipid metabolism, facilitating the exchange of cholesterol esters for triglycerides between HDL and other lipoproteins. Variants in CETP have been consistently associated with HDL cholesterol levels in numerous studies across diverse populations, including East Asians.  The other listed genes are less directly implicated in HDL metabolism.

**L02** — 점수 1.00

> The most plausible candidate gene is *APOA1*. This gene encodes apolipoprotein A-I, a major protein component of HDL cholesterol and a key player in reverse cholesterol transport, the process of removing excess cholesterol from the bloodstream. Variants in *APOA1* have been extensively linked to HDL cholesterol levels and cardiovascular disease risk in numerous populations, including East Asians. Given the strong biological rationale and prior evidence, *APOA1* is the most likely driver of the observed association.

**L03** — 점수 1.00

> The most plausible candidate gene is *LIPC*. This gene encodes hepatic lipase, an enzyme that plays a crucial role in HDL metabolism by hydrolyzing triglycerides and phospholipids in HDL particles. Variants in *LIPC* have been consistently associated with HDL cholesterol levels in multiple populations, including East Asians.  Given the strong biological rationale and prior evidence, *LIPC* is the most likely gene driving the observed association at this locus.

**L04** — 점수 1.00

> Based on prior knowledge, **LPL (lipoprotein lipase)** is the most plausible candidate gene. LPL plays a crucial role in lipoprotein metabolism, specifically in the hydrolysis of triglycerides in circulating lipoproteins, including HDL. Variants in LPL have been consistently associated with HDL cholesterol levels in numerous studies across diverse populations. The other genes in the list have not been as strongly or consistently implicated in HDL metabolism.

**L05** — 점수 1.00

> The most plausible candidate gene is **ABCA1**.  This gene encodes the ATP-binding cassette transporter A1, which plays a critical role in reverse cholesterol transport, a process that removes excess cholesterol from cells and transports it to the liver for excretion.  Mutations in ABCA1 are known to cause Tangier disease, a rare genetic disorder characterized by extremely low HDL cholesterol levels. The other genes listed are primarily olfactory receptor genes (ORFs) or have functions not directly related to lipid metabolism.

**I01** — 점수 1.00

> Your GWAS meta-analysis of HDL cholesterol in 14,453 Korean adults identified 164 genome-wide significant loci (p < 5e-8), corresponding to 14 independent loci after clumping. The genomic inflation factor (lambda GC) of 1.0464 suggests mild genomic inflation, potentially due to unaccounted population stratification or other biases. The top hit on chromosome 16 (rs7694528) shows a very strong association with increased HDL cholesterol (beta = 3.852, p = 1e-82.42). Other notable loci include associations with decreased HDL cholesterol on chromosome 11 (rs116662579, beta = -2.72) and increased HD …

**I02** — 점수 1.00

> The heritability of HDL cholesterol in this Korean adult cohort is estimated to be 26.47% (SE=7.81%), with a statistically significant Z-score of 3.39. The intercept of 1.02 is close to 1, suggesting the absence of substantial inflation due to population stratification or other biases. The genomic inflation factor (lambda GC) of 1.05 is also close to 1, further supporting this. The ratio of observed to expected heritability is 0.24, indicating that genetic variants captured by the LDSC reference panel explain approximately 24% of the heritability. Overall, these results suggest a moderate heri …

**I03** — 점수 1.00

> SuSiE identified four credible sets (CS) at the HDL locus. CS "L4" is the most likely, containing only one variant with a posterior inclusion probability (PIP) of 0.967. This variant likely drives the association signal. CS "L1", "L2", and "L3" have PIPs of 0.752, 0.515, and 0.918, respectively, suggesting they may also contribute, though with lower confidence. The low LD consistency score (0.0055) indicates high confidence in the fine-mapping results. The "min_abs_corr" values suggest strong correlations between variants within each CS. Overall, SuSiE provides strong evidence for a single cau …

**I04** — 점수 0.75

> The polygenic score (PGS) was calculated using a large reference dataset (n=966,764) and included 184,705 SNPs with a match rate of 19.11%. The mean PGS is 0.0517 with a standard deviation of 0.1272. 
> 
> Before using this PGS, the team should:
> 
> 1. **Verify the reference dataset**: Ensure the KNIH PheWeb dataset is appropriate for the Korean population in KoGES/KBA. 
> 2. **Assess the predictive performance**: Evaluate the PGS's ability to discriminate hypertension cases from controls within KoGES/KBA. This can be done using AUC, R-squared, or other relevant metrics.
> 3. **Calibration**: Check if th …

**I05** — 점수 1.00

> To report heritability on the liability scale, the KoGES/KBA team needs the population prevalence of low HDL cholesterol.  This is necessary because heritability estimates from GWAS are typically on the observed scale, reflecting the proportion of phenotypic variance explained by SNPs.  Liability scale heritability, however, estimates the proportion of underlying liability variance explained by SNPs, which is relevant to disease risk. 
> 
> The relationship between observed-scale and liability-scale heritability depends on the disease prevalence. Using the prevalence, the team can transform the ob …

**K01** — 점수 0.75

> 이 결과는 한국인 HDL 콜레스테롤 수치의 유전적 영향력이 약 26.5%임을 나타냅니다 (h2_observed). 이는 통계적으로 유의미한 결과이며 (h2_z = 3.39), 유전적 요인이 한국인 HDL 콜레스테롤 수치에 상당한 영향을 미친다는 것을 시사합니다. 
> 
> 단변량 분석 결과는 유전적 변이가 HDL 콜레스테롤 수치에 미치는 영향이 다른 유전적 질환에 비해 비교적 크다는 것을 보여줍니다 (ratio = 0.2438). 하지만 LD score 회귀 분석의 가정을 만족하는지, 그리고 다른 인종 집단과의 비교 등 추가적인 분석이 필요합니다.

**K02** — 점수 1.00

> SuSiE 분석 결과, HDL locus (chr11:116662579 ±500kb)에서 4개의 유전적 연관성 부위(credible sets)를 발견했습니다. 
> 
> "L4" 부위가 가장 높은 posterior inclusion probability (PIP) 값(0.967)을 가지므로, 이 부위에 HDL 수치에 영향을 미치는 유전 변이가 존재할 가능성이 큽니다. "L1", "L2", "L3" 부위 또한 유의미한 PIP 값을 가지므로, 이 부위에서도 유전적 연관성을 찾을 수 있습니다. 
> 
> 각 부위의 유전 변이 개수와 최소 절대값의 상관관계(min_abs_corr)는 해당 부위의 유전적 효과 크기를 나타냅니다. 높은 상관관계는 더 큰 효과를 의미합니다. 
> 
> 이 결과는 HDL 수치와 연관된 유전적 요인을 特定하기 위한 추가 연구를 위한 중요한 단서를 제공합니다.

**K03** — 점수 0.75

> 이 연구는 14,453명의 한국인 성인을 대상으로 HDL 콜레스테롤 수치에 대한 유전적 연관성 분석을 수행했습니다. 875,789개의 유전 변이를 검사하여 유의 수준(p<5e-8)에 도달한 164개의 유전 변이를 발견했습니다. 이는 HDL 콜레스테롤 수치에 영향을 미치는 14개의 독립적인 유전적 위치를 나타냅니다. 람다 GC 값(1.0464)이 1에 가깝기 때문에 유전체 팽창의 증거는 약하다고 할 수 있습니다. 하지만, 람다 GC 값이 완벽히 1이 아니므로, 인구 구조나 다른 혼란 요인으로 인한 유전체 팽창 가능성을 배제할 수는 없습니다.


## 7. 자동 관찰

규칙으로 뽑은 관찰입니다. 사람의 검토 의견은 종합 리포트에 따로 적습니다.

- 하네스를 운용할 수 없음: Ollama reports no tool-calling capability for this model.
- Track B에서 가장 약한 범주: gene (0.00).

## 부록. 원자료

- 결과 JSON: `output/bench/2026-10-29-hart-r3/txgemma-27b/result.json`
- Track A 실행별 이벤트·로그: `output/bench/2026-10-29-hart-r3/txgemma-27b/A/<시나리오>-r<반복>/`
- Track B 답변: `output/bench/2026-10-29-hart-r3/txgemma-27b/B/answers.jsonl`
