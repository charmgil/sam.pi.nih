# 설계

## 1. 층 구조

| 층 | 위치 | 역할 |
|---|---|---|
| 실행기 | `./sam` | 설치(bootstrap), 데이터 경로를 받아 pi 실행, 코어 직접 실행, 로컬 LLM 관리 |
| 에이전트 | pi 1.4.0 (`.sam/pi`) | 모델 연결(구독 OAuth, API 키, Ollama/vLLM), 대화, 세션 |
| 하네스 | `pi-package/` | 규칙(`RULES.md`), 도구 13종, 가드, 플래그, 명령, 스킬 4종, 프롬프트 5종 |
| 코어 | `src/samkit/` | 결정론적 분석. 모든 경로·파라미터·전제조건·기록 처리. JSON 요약만 반환 |
| 도구 환경 | `pixi.toml` / `pixi.lock` | plink2, regenie, R+susieR, ldsc(Py3), PRS-CS, Node.js |

pi 확장은 코어를 하위 프로세스(`python -m samkit ...`)로 부르고, stderr를 진행 상황으로, stdout JSON을
결과로 받습니다. 그래서 같은 분석을 에이전트 없이(`./sam run ...`) 그대로 재현할 수 있습니다.

### 이전 구현과의 차이

| | 이전 (GWAS.zip / PRS.zip) | 지금 |
|---|---|---|
| 설정 | GWAS: `config.sh`를 모델이 고침 / PRS: 위치 인자를 모델이 채움 | 도구 파라미터(타입 지정) + 코어가 단계 사이 값을 기록·전달 (`setup.json`, `results.tsv.gz`) |
| 규칙 | CLAUDE.md 문장 | 문장(RULES.md) + 코드(가드, 전제조건, 승인) |
| 스킬 | 링크를 따라가야 읽히는 md (PRS는 `.claude/skills` 누락) | pi 스킬(SKILL.md, frontmatter) — 판단·해석 중심 |
| 런타임 | Python 3.6~, Python 2.7(ldsc), R, 사용자 전역 설치 | Python 3 + R, 하네스 폴더 안 pixi 환경, lock 고정 |
| 데이터 | `input/`에 다운로드·변환 결과를 씀 | 입력·리소스 읽기 전용, 모든 쓰기는 `./output` |
| 기록 | 없음 | `manifest.jsonl`(파라미터, 입력 지문, 도구 버전, 요약), 단계별 로그·summary.json |
| 모델 | Claude 전용 | pi가 지원하는 모든 모델 + 로컬 카탈로그 + 자문 모델 |

## 2. 단계 계약

| 단계 | 입력 | 출력 | 전제조건 |
|---|---|---|---|
| gwas-prepare | 유전형 파일셋(또는 VCF), 표현형 표·열 | `gwas/_qc/<g>/`, `gwas/<p>/pheno.tsv`, `setup.json` | ID 열 존재, 공변량 열 존재, 이진형은 0/1 또는 1/2 |
| gwas-step1 | setup.json | `step1/<p>_pred.list` | prepare 완료 |
| gwas-step2 | pred.list | `results.tsv.gz`, `summary.json` | step1 완료 |
| plots / peaks | results | png / `loci/<p>/peaks.tsv` | step2 완료 |
| ldsc | results | `ldsc/<p>/` | 22개 상염색체 모두, LDSC 패널 22개 모두 |
| regional / finemap | results, locus | `loci/<p>/chr<C>_<POS>/` | locus가 결과에 있는 변이 |
| prs-target | 유전형 bim, dbSNP ID 매핑 | `prs/_target/<g>/` | — |
| prs-score | weight 파일 | `prs/<name>/` | 매칭 변이 ≥ 1 |
| prs-prscs | 외부 요약통계, n_gwas, LD ref | `prs/<name>/` | 하네스 GWAS 결과 아님, 부분 염색체는 승인 |

## 3. 기본 파라미터와 근거

워크숍 스크립트 값에서 바꾼 부분은 굵게 표시했습니다. 모두 `output/manifest.jsonl`에 기록됩니다.

| 항목 | 값 | 근거 |
|---|---|---|
| 표본 QC | **call rate ≥ 95 %** (`--mind 0.05`) | 이전에는 표본 QC 없음 (I-13) |
| step1 변이 | **MAF ≥ 1 %**, geno ≤ 1 %, **HWE 1e-6 (고정)**, r² < 0.9 pruning | regenie 권장(MAF>1%, 고품질 변이). 이전 MAF 0.1은 지나치게 엄격 |
| PCA | **별도 pruning: MAF ≥ 5 %, r² < 0.2 (50/5), MHC(chr6:25–34 Mb) 제외**, PC 10개 계산·4개 사용 | 이전엔 r² < 0.9 집합으로 PCA (I-14) |
| step2 변이 | **geno ≤ 5 %, MAC ≥ 20, HWE는 표본 크기 보정형 `1e-5 0.001 midp`** | plink2 a7.8은 큰 표본에 고정 HWE를 거부함. 연관 신호를 지우지 않으면서 심한 이탈(이형접합 과잉·결핍 모두, array 유전형 오류의 흔적)만 제거 |
| 이진형 | **`--firth --approx --pThresh 0.01`** | I-12 |
| 공변량 | AGE, SEX + PC1–4 | 워크숍과 동일 |
| SuSiE | L=10, coverage 0.95, **min_abs_corr 0.5**, **잔차분산 추정(estimate_residual_variance=TRUE)** | susieR 기본값 (I-27; 이전 0.1). in-sample LD일 때 susieR 문서 권장 |
| LDSC | **단변량: EAS baseline v1.2의 base(전체 SNP) LD score**로 `--h2`. 워크숍 방식(53개 주석 S-LDSC)은 `--model baseline` | 총 h²가 주석 모델에 좌우되지 않는 표준 추정 |
| PRS-CS | phi auto, seed 1, 1000G EAS LD | PRS-CS 기본값, 재현성을 위해 seed 고정 |

## 4. 이전 구현 문제의 처리 (arxiv/20260928 critics)

| ID | 문제 | 처리 |
|---|---|---|
| I-1 | 유전자 트랙이 hg38 Ensembl | 빌드에 맞는 서버(GRCh37: `grch37.rest.ensembl.org`) |
| I-2 | CS 없으면 이전 CS 파일이 남음 | CS 파일을 항상 새로 씀(없으면 빈 표) |
| I-3 | R이 상대경로로 Python을 다시 호출 | R은 계산만, 그림은 Python에서 |
| I-4 | r² 없는 점이 안 그려짐, 리드 ID 불일치 | 회색으로 표시, 리드는 결과의 ID 그대로 |
| I-5 | 값을 손으로 옮겨 적음 | 단계 사이 값은 코어가 파일로 전달 |
| I-6 | 유전자 패널 없을 때 x축 숫자 사라짐 | 패널 있을 때만 숨김 |
| I-7 | `10**-LOG10P` underflow | QQ는 LOG10P로 직접, munge는 1e-300 하한 |
| I-8 | 여러 염색체에 `--chr` | `--chrList` 사용 |
| I-9 | 결측을 빈칸으로 저장 | `NA`로 저장 |
| I-10 | `!= 'NA'` 필터가 무효 | `na_values` + `dropna` |
| I-11 | SuSiE에서 BETA와 LD 대립유전자 미정렬 | `--r-unphased ref-based` + ALLELE1/ALT 비교로 부호 정렬, 불일치 제거 (plink2 기본 부호는 major allele 기준이라 실제로 어긋날 수 있었음) |
| I-12 | 이진형 Firth 없음 | 추가 |
| I-13 | step2 변이 QC·표본 QC 없음 | 추가 |
| I-14 | PCA용 pruning이 느슨 | 별도 엄격 pruning + MHC 제외 |
| I-15 | 위치만으로 rsID 매핑 | probe ID→rsID 매핑 우선(변이 단위 정확), 위치 매핑은 대체 경로로만 + 경고. h²는 부호와 무관 |
| I-16 | 실패해도 다음 명령 진행 | 모든 외부 명령의 종료 코드 검사, 오류는 원인+힌트 JSON |
| I-17, I-18, I-22 | bash/문서 문제 | 해당 구조 제거 |
| I-19 | 버전 표기 불일치 | `pixi.lock` |
| I-20 | 체크리스트와 출력 경로 불일치 | 출력 구조 문서화(USAGE.md 5절) |
| I-21 | ID 안의 좌표가 hg38 | ID는 불투명 키로만 사용, 위치는 결과의 GENPOS(hg19). locus는 위치·ID·순위로 지정 |
| I-23 | step1 임시 파일 접두어 충돌 | 표현형별 접두어 |
| I-24 | pred.list 절대경로 | 출력 폴더 안이라 유지. 출력 폴더를 옮기면 step1부터 다시 |
| I-25 | h² 정규식 | 음수·지수 표기 지원 |
| I-26 | 유전 지도 구분자 | 공백 일반 처리 |
| I-27 | min_abs_corr 0.1 | 0.5 (변경 가능) |
| I-28 | 결과 파일 이름이 염색체만 | `loci/<표현형>/chr<C>_<POS>/` |

PRS 쪽(analysis.md에서 지적):

| 문제 | 처리 |
|---|---|
| `.claude/skills` 누락, 스킬 이중 관리 | pi 스킬 하나로 |
| `/tmp`에 임시 파일 | 모든 임시 파일은 `output/_tmp` (TMPDIR) |
| scipy/h5py 누락 | prscs 환경에 고정 |
| 다운로드가 `input/`으로 | `output/downloads/pheweb/` + GWAS N을 담은 `.meta.json` |
| rsID 업데이트를 건너뛸 수 있음 | 점수 계산이 매핑을 자동으로 만들고 매칭률을 보고. 3 GB bed를 다시 쓰지 않음 |
| 여러 rsID(`rs1,rs2`)·중복 rsID | 분리 후 중복 rsID 제거 |
| 대립유전자 확인 없음 | rsID + 대립유전자(strand 보정, 불일치 제거)로 매칭 |
| chr16만 있는 LD를 genome-wide로 착각 | LD ref의 염색체를 인식, 부분이면 승인 필요 + 결과에 `partial` |
| 표본 중복 | KBA 기반 통계 사용 시 항상 경고, 하네스 GWAS 결과는 PRS-CS 입력 거부 |

## 5. 확인된 실행 결과 (개발 검증, 2026-10-27)

입력 `sam-data/input`(KBAv2.0AB_14K_COMMON, 14,490명, 875,789 변이), 결과 `.sam/devrun/output`:

- HDL GWAS: 분석 14,490명, λGC 1.046, 유의 변이 164개, 독립 locus 14개. 1위 CETP(16:56994528, −log10P 82.4),
  2위 APOA5(11:116662579, 62.4 — 워크숍 기대 locus).
- LDSC: 단변량(기본) h² 0.265 (SE 0.078), intercept 1.022 / S-LDSC(`model=baseline`, 워크숍 방식) h² 0.208 (SE 0.058),
  회귀 SNP 약 19.8만 → 경고 2개(z<4, SNP<200k).
- SuSiE(11:116662579 ±500 kb): 460 변이, CS 4개, 리드는 CS L1(크기 2, PIP 0.745), LD 일관성 s=0.0055.
- PRS(HTN PheWeb weight): 966,764개 중 184,705개 사용(19 %, array 데이터라 낮음).
- PRS-CS(KBA_187K_HTN, 22개 염색체): 사후 효과 201,688개, 6.4분.
- 에이전트: 로컬 `gpt-oss-20b`와 `qwen3.6-35b-a3b`로 상태 확인·locus 목록·fine-mapping·regional plot 호출과 보고,
  `--privacy on`에서 개인 단위 파일 읽기 차단, MedGemma 27B 자문 호출 확인. 외부 기준(KBA 187K HDL) 비교는 REVIEW-2026-10-27.md 7절.
- 회귀: 코드 수정 후 새 디렉토리(`.sam/devrun2`)에서 `./sam run`으로 전 단계를 다시 실행해 같은 수치 확인.
- 설치: 빈 폴더에서 `./sam bootstrap`(pixi 다운로드·sha256 검증·환경 설치) 확인.
- 자문: `sam_consult`(Intern-S1-mini) 호출 확인. 근거 없는 답의 오류 사례와 대응은 MODELS.md 4절.

## 6. 한계와 남은 일

- 가드는 실수 방지용 패턴 검사입니다. 확실한 격리가 필요하면 컨테이너나 별도 계정으로 실행하세요.
- LDSC Python 3 포팅과 원본 py2.7의 수치 대조는 하지 않았습니다(TOOLS.md 1.3).
- vLLM은 설정·명령까지 준비했고 설치·구동은 미검증입니다.
- 클라우드 모델(Claude, ChatGPT)로의 실제 대화는 계정 로그인이 필요해 검증하지 않았습니다.
- 모델 비교 벤치(자동 채점)는 이번 범위에서 제외했습니다. `--mode json` 출력으로 나중에 붙일 수 있습니다.
- DNA 서열 모델은 문서로만 정리했습니다(MODELS.md 5절).
- 자체 GWAS → PRS 경로(표본 분할 등)는 열지 않았습니다.
