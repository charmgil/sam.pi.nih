두 개의 하네스를 합쳐서 하나로 만들고자 하고, pi 플랫폼을 사용하여 작성하고 싶어.

외부 도구나 파일들은 모두 확보할 수 있어.
필요한 도구를 온라인에서 다운로드 받아 설치해도 좋고,
데이터나 ld의 경우 파일이 필요할 것 같고, 
도구들의 경우는 준비 과정에서 함께 마련하거나, 자동으로 다운로드 + 컴파일을 하도록 최종 패키지에 루틴을 포함 시키고 싶어. 

어떻게 작업을 진행하면 좋을까?

----

두 하네스를 합치는 작업은 **pi 패키지(코드), 실행 환경(도구), 작업 폴더(데이터)** 세 층으로 나눠서 진행하는 걸 권합니다.

pi로 옮길 때 가장 중요한 결정은 지금의 "LLM이 마크다운을 읽고 bash 명령을 직접 조립하는" 구조를 "**입력 형식이 정해진 도구 + 코드가 강제하는 확인 지점(Gate)**" 구조로 바꾸는 것입니다. 지금 두 하네스는 "요청한 단계까지만 실행", "다운로드 전 확인", "rsID 업데이트를 건너뛰면 경고" 같은 규칙이 모두 CLAUDE.md의 문장으로만 존재합니다. Claude는 이런 문장을 잘 따라도 로컬 LLM은 놓칠 가능성이 큽니다. 모델 간 벤치마크를 하실 거라면 역할을 이렇게 나누는 게 공정한 비교의 전제가 됩니다.
- **skill**: 판단과 해석
- **extension**: 실행, 검증, Gate

## 1. 목표 구조

**① pi 패키지** (git 저장소. 코드만 들어감)
```
statgen-agent/                     # 가칭
├── package.json                   # "pi": { skills, extensions, prompts }
├── skills/
│   ├── statgen-setup/             # 환경 점검·설치
│   ├── gwas-association/          # QC → PCA → regenie step1/2
│   ├── gwas-plots/
│   ├── gwas-ldsc/
│   ├── gwas-regional-finemap/     # regional + SuSiE (S11)
│   ├── variant-rsid/              # GWAS pos2rsid + PRS dbSNP 매핑 통합
│   ├── knih-pheweb-fetch/
│   ├── prs-prscs/                 # 단일/전체 염색체 버전을 하나로
│   └── prs-weight/
├── extensions/statgen/index.ts    # 도구 등록, Gate, 체크포인트
├── prompts/                       # /gwas-full, /prs-pheweb 같은 워크숍 시나리오
├── runtime/
│   ├── scripts/                   # 기존 bash/py/R 정리본
│   ├── pyproject.toml, uv.lock
│   ├── tools.lock.yaml            # 도구별 버전·URL·sha256·설치 방법
│   └── resources.spec.yaml        # 필요한 참조 파일 명세 (파일 자체는 아님)
├── bin/statgen                    # init / doctor / setup (pi 없이도 동작)
└── templates/workspace/           # AGENTS.md, statgen.yaml 템플릿
```

**② 작업 폴더** (데이터는 여기에만 둠)
```
my-analysis/
├── AGENTS.md            # 두 하네스의 행동 규칙을 합친 것
├── .pi/settings.json    # 패키지 선언
├── statgen.yaml         # genome build, ancestry, 유전형 prefix, 표현형, 참조 파일 경로
├── input/  resource/  output/
└── .statgen/tools/      # setup이 설치한 도구들
```

## 2. 도구와 데이터 준비

**데이터와 참조 파일** (유전형, LD ref, LDSC baseline, dbSNP 매핑, genetic map)
- 패키지에 넣지 않고 따로 배포합니다. 패키지에는 `resources.spec.yaml`만 둡니다. 여기에 파일명, 크기, sha256, build, ancestry, **포함된 염색체**를 적습니다.
- `statgen doctor`는 파일이 있는지와 sha256이 맞는지만 검사합니다.
- 포함 염색체를 명세에 적어 두면 문제 하나를 코드로 잡을 수 있습니다. 지금 PRS LD ref에는 chr16만 있는데, 이 상태에서 나온 결과를 genome-wide로 착각하는 문제입니다. 지금은 문장 경고에만 의존하고 있습니다.

**도구**는 `tools.lock.yaml` 하나로 두 경로를 모두 지원합니다.
- **오프라인**: 이미 확보한 파일을 `vendor/` 폴더에 넣으면 sha256을 확인한 뒤 설치합니다. 워크숍 현장의 네트워크 문제를 피할 수 있습니다.
- **온라인**: 같은 항목의 URL로 다운로드하고, 실패하면 소스에서 빌드합니다.

| 도구 | 권장 방식 |
|---|---|
| plink2 a7.1 | 공식 바이너리 우선, 소스 빌드는 대체 경로 |
| regenie 4.1 | 바이너리 우선. 소스 빌드는 Boost·cmake·BGEN이 필요해서 무겁습니다. Homebrew에는 Apple Silicon·Linux용 바이너리(bottle)가 있습니다 |
| Python 3 쪽 (그래프, PRS-CS의 numpy/scipy/h5py) | uv 프로젝트 하나로 버전 고정 |
| **ldsc** | **Python 2.7이라 uv로 관리할 수 없습니다.** 두 가지 선택지가 있습니다: ① micromamba로 py27 환경을 유지, ② Python 3판으로 교체 (PyPI의 `ldsc` 2.0.x가 Python 3용으로 올라와 있음). ②를 고른다면 원본과 h² 수치가 같은지 확인한 뒤 채택 |
| R + susieR 0.14.2 | R 본체는 사전 설치 요구사항으로 두고, susieR만 버전을 고정해 설치 |
| PRS-CS 1.1.0 | git 커밋을 고정하고 uv 환경에서 실행 |

- **설치 위치**: 지금처럼 `$HOME/bin`, `~/miniconda3` 같은 사용자 전역 위치가 아니라 `.statgen/tools/` 아래에 설치합니다. extension이 도구를 실행할 때 PATH를 넣어 주면 사용자의 셸 설정을 건드리지 않아도 됩니다.
- **하드코딩 제거**: 지금 스크립트에 박혀 있는 `$HOME/bin`, `~/ldsc`, `~/miniconda3/envs/ldsc`, `/tmp/...` 경로도 이 단계에서 함께 없앱니다.
- **단계별 점검**: `statgen doctor --step ldsc`처럼 단계별로 필요한 도구만 점검하게 합니다. GWAS CLAUDE.md의 "필요한 프로그램만 확인" 원칙을 코드로 옮기는 것입니다.

## 3. 진행 순서

1. **기준 결과 고정**
   - 두 zip을 새 저장소의 `legacy/`에 그대로 커밋합니다.
   - 지난번에 찾은 불일치(config.sh가 로컬 상태로 남은 문제, LEAD_SNP 형식, bt step2 인자)만 고칩니다.
   - 워크숍 데이터로 처음부터 끝까지 한 번 실행해 기준 결과를 저장합니다: regenie 결과, λGC, h², credible set(CS), `SCORE1_SUM`.
   - 이후 모든 리팩토링은 이 결과와 비교해 회귀 여부를 확인합니다.
2. **명세 통합**
   - `GWAS_PROCEDURE_consolidated.md`의 S0–S11 단계와 Gate/Decision/Checkpoint 체계에 PRS 단계를 같은 방식으로 추가합니다.
   - rsID 매핑을 하나로 합칩니다. 지금 두 방식이 있습니다: chr+pos만 보는 GWAS의 `pos2rsid.txt`와 대립유전자까지 보는 PRS의 `dbSNP155_HG19.txt`. 대립유전자까지 보는 쪽으로 통일하는 게 안전합니다.
   - 자체 GWAS 결과를 PRS-CS 입력으로 쓰는 경로를 열지 정합니다. 연다면 GWAS를 돌린 표본과 PRS를 계산할 표본이 겹치는지 확인하는 Gate가 반드시 필요합니다.
3. **환경 층** (pi와 무관하게 동작)
   - `statgen init / doctor / setup`을 만듭니다.
   - 깨끗한 Linux 컨테이너와 새 macOS 계정에서 설치를 테스트합니다.
4. **실행 층**
   - 스크립트를 "명시적 인자 + `statgen.yaml` 기본값" 방식으로 통일합니다.
   - GWAS 방식(`source config.sh`)은 LLM이 설정 파일을 직접 고쳐야 해서 무엇이 바뀌었는지 추적하기 어렵습니다. PRS 방식(위치 인자)은 기본값이 없습니다. 통일하면 두 방식의 장점만 취할 수 있습니다.
5. **pi 층**: skills, extension, prompts, AGENTS.md 템플릿을 작성합니다.
6. **검증**
   - 1번의 기준 결과와 비교하는 회귀 테스트를 돌립니다.
   - `prompt.txt`의 시나리오 7개를 pi 비대화형 모드로 모델별로 실행합니다. 이 결과가 그대로 벤치마크 초판이 됩니다.
7. **패키징**
   - `pi install git:...` 또는 로컬 경로로 설치하게 합니다.
   - 참조 데이터 묶음은 패키지와 따로 배포합니다.

## 4. pi에서 신경 쓸 점

- **Gate는 `tool_call` 이벤트에서 코드로 처리합니다.** 다음 같은 경우를 `{ block: true }`나 `ctx.ui.confirm`으로 막습니다. 지금 문장으로만 있는 규칙 대부분이 여기로 옮겨집니다.
  - rsID 업데이트를 안 한 타깃 데이터로 PRS 계산
  - bed 파일이 이미 있는데 VCF→pgen 재변환
  - 수 GB 다운로드
- **비대화형 모드에는 UI가 없습니다.** print/JSON 모드로 벤치마크를 돌리면 확인 창을 띄울 수 없습니다. 사용자가 정해야 하는 값(Decision)을 미리 적은 파일로 답하는 방식이 필요하고, 그래야 모델 간 비교가 재현됩니다.
- **ablation 실험을 설정만으로 할 수 있습니다.** `settings.json`의 패키지 필터에서 `"extensions": []`로 extension만 끄면, 같은 패키지로 "skill 지침만"과 "코드로 강제"를 비교할 수 있습니다. 논문의 평가 축으로 쓸 만합니다.
- **skill 이름 규칙**: 소문자, 숫자, 하이픈만 쓸 수 있고 64자 이내여야 합니다. 그래서 지금의 `01_gwas` 같은 이름은 바꿔야 합니다. description은 1024자 이내입니다.
- **컨텍스트 파일**: pi는 CLAUDE.md도 읽지만 AGENTS.md 하나로 통일하는 게 깔끔합니다. 단, 프로젝트의 `.pi/` 설정(패키지 선언 포함)은 사용자가 project trust를 승인해야 로드됩니다. 워크숍 안내문에 한 줄 넣어야 합니다.
- **extension 의존성**: pi 쪽 패키지(`@earendil-works/pi-coding-agent` 등)는 `dependencies`가 아니라 `peerDependencies "*"`로 선언합니다.

**PROCEDURE 문서의 확인 항목:** 이번 zip으로 PROCEDURE 문서에 남아 있던 확인 항목 두 개가 정리됩니다.
- **BT 덮어쓰기 버그는 없습니다.** BT 스크립트는 `--out`과 `--pred`에 `PHENO_BT`를 씁니다.
- **다만 다른 문제가 두 개 있습니다.**
  - QT와 BT의 step1이 같은 `--lowmem-prefix tmp_preds`를 씁니다. 동시에 돌리면 임시 파일이 충돌합니다.
  - `02_ldsc.sh`가 `PHENO_QT`를 하드코딩하고 있어서 BT 표현형은 LDSC를 돌릴 수 없습니다.
- **Step2에는 MAF 필터가 없습니다.** regenie 기본값인 minMAC 5만 적용됩니다.

## 5. 먼저 정해 주실 것

- **지원 플랫폼**: macOS arm64 + Linux x86_64로 하고 Windows는 WSL로 안내할지 정해 주세요. 워크숍에 `_Windows` 폴더가 따로 있었는데, Windows에서 WSL 없이 바로 돌아가야 한다면 bash 스크립트를 Python으로 옮기는 편이 낫습니다.
- **ldsc**: Python 3판으로 바꿀지, py2.7을 유지할지
- **자체 GWAS → PRS 경로**: 포함할지 여부
- **배포 방식**: 비공개 git으로 할지, npm에 공개할지

정해 주시면 1단계(저장소 뼈대, legacy 고정, 불일치 수정)부터 폴더에 바로 만들겠습니다.

Sources:
- [pi docs — Packages](https://pi.dev/docs/latest/packages)
- [pi docs — Skills](https://pi.dev/docs/latest/skills)
- [pi docs — Extensions](https://pi.dev/docs/latest/extensions)
- [pi docs — Configuration](https://pi.dev/docs/latest/configuration)
- [pi.dev deep dive (urandom.io)](https://urandom.io/blog/2026-03-07-pi-dev-deep-dive)
- [Homebrew — regenie](https://formulae.brew.sh/formula/regenie)
- [PyPI — ldsc](https://pypi.org/project/ldsc)