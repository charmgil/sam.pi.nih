# 작동 (사용법)

## 1. 에이전트 시작

분석 결과를 둘 디렉토리로 이동한 뒤 실행합니다. 결과는 **그 디렉토리의 `./output`** 에 생깁니다.

```bash
mkdir -p ~/analysis/hdl && cd ~/analysis/hdl
/projects/NIH/sam.pi.nih/sam agent \
    --input  /projects/NIH/sam.pi.nih/sam-data/input \
    --resource /projects/NIH/sam.pi.nih/sam-data/resource
```

| 실행기 옵션 | 기본값 | 의미 |
|---|---|---|
| `--input DIR` | (필수) | 입력 데이터 폴더, 읽기 전용 |
| `--resource DIR` | 없음 | 참조 리소스 폴더, 읽기 전용 (LDSC, 유전 지도, dbSNP 매핑, PRS-CS LD) |
| `--output DIR` | `./output` | 출력 폴더 |
| `--privacy auto\|on\|off` | `auto` | 개인 단위 파일 읽기 차단. auto = 클라우드 모델일 때만 |
| `--approvals ask\|allow\|deny` | `ask` | 설치·다운로드·부분 PRS 승인. 화면이 없는 실행에서 ask는 deny로 동작 |
| `--consultant P/M` | 없음 | `sam_consult`가 쓸 모델 (예: `ollama/sam-medgemma-27b`) |
| `--threads N`, `--build hg19\|hg38` | 코어 수(최대 16), hg19 | 분석 도구 스레드, 유전체 빌드 |
| 그 밖의 인자 | | 그대로 pi에 전달 (`--model`, `-p`, `--mode json`, `--continue` 등) |

같은 값은 환경 변수(`SAM_INPUT`, `SAM_RESOURCE`, `SAM_PRIVACY`, `SAM_APPROVE`, `SAM_CONSULTANT`)로도 줄 수 있습니다.
pi 하단 상태줄에 `SAM ▸ <입력 폴더> │ privacy on/off`가 표시됩니다.

## 2. 대화 예시

기존 워크숍 시나리오(`arxiv/*/prompt.txt`)를 이 하네스로 하면 다음과 같습니다. 에이전트는
**요청한 단계까지만** 실행하고, 결과를 보고한 뒤 다음 단계를 묻습니다.

```
> 입력 폴더에 있는 데이터로 HDL GWAS 분석해줘. 필요한 프로그램 있는지 확인하고 없으면 설치해줘
  → sam_status, sam_doctor(gwas) → (없으면 sam_setup, 승인 요청) → 표현형 파일/공변량 확인 질문
  → sam_gwas stage=all → 표본 수, λGC, 유의 locus 수, 상위 변이 보고 → "플롯/locus/LDSC 진행할까요?"

> manhattan plot이랑 qq plot 그려줘            → sam_plots (그림을 볼 수 있는 모델이면 그림도 함께 받음)
> 유의한 신호 보여줘                           → sam_peaks → locus 목록을 보여주고 선택을 물음
> 2번 locus로 regional plot 그려줘              → sam_regional locus="2"  (= 11:116662579, APOA5)
> 같은 locus로 susie 분석해줘                   → sam_finemap → credible set, PIP, 순도, LD 일관성
> ldsc 분석해줘                                 → sam_ldsc → h², intercept, 경고

> 한국인 고혈압 PRS weight로 PRS 계산해줘       → sam_status (입력에 HTN_PRS_weight.txt.gz 있음) → sam_prs weights
> 고혈압 GWAS sumstat으로 PRS-CS 해줘. 염색체 16번만 해도 돼
  → sam_pheweb search (KBA+BBJ / KBA_187K 중 선택 질문) → sam_prs prscs chromosomes=16
  → 부분 점수 승인 창 → 결과와 "부분 점수" 경고
```

슬래시 명령(프롬프트 템플릿):

| 명령 | 하는 일 |
|---|---|
| `/gwas HDL [표현형파일]` | GWAS 한 번 (준비→step1→step2) 후 보고 |
| `/post-gwas HDL` | 플롯 + locus 목록 + LDSC, 그 다음 locus 선택 질문 |
| `/locus HDL 2` | fine-mapping + CS가 표시된 regional plot |
| `/prs 고혈압 [weights\|prscs]` | PRS (파일 확인 → 필요하면 PheWeb 검색·선택) |
| `/sam-report` | `output/report.md` 작성 후 요약 |
| `/sam` | 현재 설정(입력·리소스·출력·privacy·승인 정책) 보기 |
| `/sam-data <입력> [리소스]` | 실행 중 데이터 폴더 지정 (출력 폴더에 이미 다른 데이터 결과가 있으면 거부. 다른 데이터는 다른 디렉토리에서 실행) |
| `/sam-privacy auto\|on\|off` | 개인정보 모드 변경 (클라우드에서 off로 바꾸면 확인 창) |
| `/skill:sam-gwas` 등 | 스킬 강제 로드 (모델이 스스로 읽지 않을 때) |

## 3. 도구 (모델이 호출)

| 도구 | 하는 일 | 반환(요약만) |
|---|---|---|
| `sam_status` | 입력·리소스·설치 도구·완료 단계 | 파일 목록, 표는 열 이름과 행 수만 |
| `sam_doctor` | 지정 단계에 필요한 도구·리소스만 점검 | 버전, 누락 항목 |
| `sam_setup` | 지정 단계의 환경 설치 (승인) | 설치된 환경 |
| `sam_gwas` | 표본 QC → step1 변이 → PCA → 표현형 표 → regenie step1/2 | 표본 수, λGC, 유의 변이·locus 수, 상위 10개 |
| `sam_plots` | Manhattan, QQ | λGC, 그림 |
| `sam_peaks` | 독립 유의 locus (±500 kb) | locus 표 |
| `sam_ldsc` | LDSC h² (기본: 단변량, `model=baseline`: 워크숍 방식 S-LDSC) | h², SE, z, intercept, ratio, 평균 χ², SNP 수 |
| `sam_regional` | regional plot (LD는 GWAS 표본에서 계산) | 리드, 창 안 변이 수, 그림 |
| `sam_finemap` | SuSiE-RSS | CS별 크기·대표 변이·PIP·순도, LD 일관성 |
| `sam_pheweb` | KNIH PheWeb 검색/다운로드(승인) | 코호트·코드·N, 저장 위치 |
| `sam_prs` | weight 점수 또는 PRS-CS + 점수 | 매칭률, 포함 염색체, 점수 분포 |
| `sam_report` | `output/report.md` 작성 | |
| `sam_consult` | 자문 모델에 질문. `region`을 주면 Ensembl 유전자 목록을 근거로 붙임 | 답변(미검증 2차 의견 표시) |

모든 결과에는 `warnings`(반드시 사용자에게 전달)와 `next`(다음에 할 수 있는 단계, 지시 아님)가 붙습니다.

## 4. 코드로 강제되는 규칙 (Gate)

| 규칙 | 어디서 |
|---|---|
| 입력·리소스 폴더에 쓰기 금지 (도구, bash, write/edit 모두) | `samkit.context`, 확장 가드 |
| 실행 디렉토리 밖에 쓰기 금지 | 확장 가드 |
| bash로 설치(pip/conda/apt/npm/git clone/curl\|sh)·파일 다운로드·sudo 금지 → `sam_setup`/`sam_pheweb` 사용 | 확장 가드 |
| 설치·다운로드·부분 PRS는 사용자 승인 | 확장 도구 |
| 개인정보 모드: 개인 단위 파일을 read/grep/bash로 읽기 금지 (ls, wc -l, head -1은 허용) | 확장 가드 |
| 부분 유전체 GWAS로 LDSC 금지 | `steps/ldsc.py` |
| PRS-CS가 일부 염색체만 쓰면 승인 필요, 결과에 "partial" 표시 | `steps/prs.py` + 확장 |
| 이 하네스의 GWAS 결과를 PRS-CS 입력으로 쓰기 금지 (표본 중복) | `steps/prs.py` |
| PLINK 파일셋이 있으면 VCF 재변환 안 함 | `steps/gwas.py` |
| 한 출력 폴더는 한 데이터셋에만 (`sam.json`) | `samkit.context` |
| step2 전 step1, regional/finemap 전 GWAS 결과 필수 | 각 단계 |

가드는 실수 방지용입니다. 작정하고 우회하는 명령까지 막는 보안 경계는 아닙니다.

### 개인정보 보호

- `--privacy auto`(기본): 현재 모델이 로컬(ollama, vllm, localhost 등)이면 off, 그 밖(Anthropic, OpenAI 등)이면 on.
- on일 때 차단: 입력 폴더의 개인 단위 파일(요약통계·weight·bim·로그를 제외한 전부), `.fam/.psam/.bed/.pgen`,
  `pheno.tsv`, `*.eigenvec`, `*.sscore`, regenie step1 산출물 등. `ls`, `wc -l`, `head -1`(열 이름)은 허용.
- 분석 도구는 privacy와 관계없이 항상 집계값만 모델에 돌려줍니다(표본 수, 분포 요약(분위수), 통계량).
- 세션 기록은 `./output/.pi-sessions/`에 저장되며, 이 폴더도 개인 단위로 취급합니다.
- **로컬 전용 세션**: 로컬 모델로 privacy가 꺼진 상태에서 개인 단위 파일을 읽으면, 그 세션은 "local-only"로
  표시되고(상태줄) 이후 클라우드 모델로 바꾸거나 `--continue`로 이어 쓰면 입력이 차단됩니다. 새 세션(`/new`)을 쓰세요.
- 사용자가 직접 치는 `!명령`의 출력도 모델에 들어가므로 같은 규칙을 적용합니다. 출력이 모델로 가지 않는 `!!명령`은 허용됩니다.
- `/sam-privacy` 변경은 세션에 기록되어 `/resume`, `/reload` 후에도 유지됩니다.

## 5. 출력 구조

```
output/
├── sam.json                      이 출력이 묶인 입력/리소스/빌드
├── manifest.jsonl                단계마다 1줄: 파라미터, 입력 파일 지문, 도구 버전, 요약, 소요 시간, 로그 경로
├── report.md                     sam_report 결과
├── logs/                         단계별 로그 (외부 도구 출력 전부)
├── gwas/_qc/<유전형>/            표본 QC, step1/PCA 변이 집합, PCA (표현형 간 공유)
├── gwas/<표현형>/                pheno.tsv, step1/, step2/, results.tsv.gz, summary.json
├── plots/<표현형>/               manhattan.png, qq.png
├── ldsc/<표현형>/                h2.log, munged.sumstats.gz, ldsc_regression.png, summary.json
├── loci/<표현형>/peaks.tsv
├── loci/<표현형>/chr11_116662579/  regional.png, susie.png, regional_susie.png, susie_pip.tsv, susie_cs.tsv, ...
├── prs/_target/<유전형>/         rsID 매핑 (대상 유전형 파일은 다시 쓰지 않음)
├── prs/<이름>/                   score.sscore(개인별), weights, summary.json
├── downloads/pheweb/             PheWeb에서 받은 파일 + .meta.json (GWAS N 등)
├── _cache/                       리소스 압축 해제분, 유전자 트랙, PheWeb 목록
└── .pi-sessions/                 pi 대화 기록
```

## 6. 에이전트 없이 실행

같은 코어를 직접 부를 수 있습니다(재현, 일괄 실행, 디버깅용). 결과는 JSON으로 나옵니다.

```bash
S=/projects/NIH/sam.pi.nih/sam; D=/projects/NIH/sam.pi.nih/sam-data
$S status   --input $D/input --resource $D/resource
$S run gwas all --pheno HDL --pheno-file KBAv2.0AB_14K_HDL.txt --input $D/input --resource $D/resource
$S run plots   --pheno HDL --input $D/input
$S run peaks   --pheno HDL --input $D/input
$S run ldsc    --pheno HDL --input $D/input --resource $D/resource
$S run regional --pheno HDL --locus 11:116662579 --input $D/input --resource $D/resource
$S run finemap  --pheno HDL --locus 2 --input $D/input --resource $D/resource
$S run prs score --weights HTN_PRS_weight.txt.gz --input $D/input --resource $D/resource
$S run prs prscs --sumstats phenocode-KBA_187K_HTN.tsv.gz --n-gwas 185805 --input $D/input --resource $D/resource
$S run pheweb search hypertension --input $D/input
$S report --input $D/input
```

`./sam run <명령> --help`로 각 옵션을 볼 수 있습니다.

## 7. 비대화형 실행 (스크립트, 모델 비교)

```bash
./sam agent --input ... --resource ... --model ollama/sam-gpt-oss-20b --approvals deny \
    -p "HDL GWAS 결과에서 유의한 locus 목록을 보여줘" < /dev/null
./sam agent ... --mode json -p "..." < /dev/null > events.jsonl     # 도구 호출까지 JSONL 이벤트로
```

- `< /dev/null`을 꼭 붙이세요. pi는 stdin이 터미널이 아니면 stdin을 추가 입력으로 읽으려고 기다립니다.
- 화면이 없으므로 승인이 필요한 동작은 `--approvals`로 정합니다(기본 ask → 거부).

## 8. 소요 시간 (이 서버, 14,490명 × 875,789 변이, 16스레드 실측)

| 단계 | 시간 |
|---|---|
| gwas prepare (표본 QC, pruning, PCA 10개) | 약 3분 |
| regenie step 1 (605,650 변이) | 약 5분 |
| regenie step 2 (전체) | 약 30초 |
| plots / peaks / LDSC | 6초 / 1초 미만 / 17초 |
| regional / fine-mapping (±500 kb) | 1초 미만 / 9초 |
| PRS weight 점수 | 2초 (rsID 매핑 처음 1회 6초) |
| PRS-CS chr16 / 전체 22개 염색체 (8개씩 병렬) | 약 2분 / 약 6.5분 (처음엔 LD 압축 해제 포함) |

## 9. 문제 해결

| 증상 | 원인과 해결 |
|---|---|
| `input directory is not set` | `--input`을 주지 않음. pi 안에서 `/sam-data <입력> [리소스]` |
| `output directory ... was created for different data` | 다른 데이터로 같은 출력 폴더 사용. 다른 디렉토리에서 실행하거나 `--rebind`(코어) |
| `required tools are not installed` | `./sam setup --step <단계>` 또는 에이전트에 설치 요청(승인) |
| `resource not found: ldsc_ref` 등 | 리소스 폴더에 해당 파일/압축이 없음. [TOOLS.md](TOOLS.md#2-참조-리소스) |
| SAM guard 경고로 명령 차단 | 의도된 동작. 분석은 sam 도구로, 설치는 `sam_setup`, 다운로드는 `sam_pheweb` |
| regional plot에 유전자 트랙 없음 | Ensembl GRCh37 REST 접속 실패. 그림은 그대로 생성, 경고 표시 |
| 로컬 모델이 도구를 잘 안 씀 | 더 큰 모델(`qwen3.6-35b-a3b`, `qwen3.8-27b`)로 바꾸거나 `/gwas` 같은 템플릿 사용 |
| `pi -p`가 끝나지 않음 | `< /dev/null` 누락 |
| 단계 실패 상세 | 오류의 `hint`와 `output/logs/<시각>_<단계>.log` |
