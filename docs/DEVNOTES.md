# 개발 노트와 변경 이력

다른 서버에서 작업을 이어가기 위한 인수인계 문서입니다. 지금 상태, 옮기는 방법, 지금까지의 결정, 개발할 때의 주의점, 남은 일,
변경 이력을 한곳에 모았습니다. 사용법은 [USAGE.md](USAGE.md), 설계 근거는 [DESIGN.md](DESIGN.md), 단계별 입력·출력은
[WORKFLOW.md](WORKFLOW.md)를 보세요.

> 마지막 갱신: 2026-10-28 · 저장소 `git@github.com:charmgil/sam.pi.nih.git` (main)
> 이 문서에 적힌 결정 사항은 지금까지 Claude Code의 서버별 메모리에만 있던 내용을 옮긴 것입니다. 새 서버에는 그 메모리가 없으므로
> **이 문서가 기준**입니다.

## 1. 지금 상태 (2026-10-28)

| 영역 | 상태 |
|---|---|
| 분석 코어 (`samkit`) | GWAS(regenie), Manhattan/QQ, 유의 locus, LDSC, regional plot, SuSiE fine-mapping, PRS(weights, PRS-CS), KNIH PheWeb 검색·다운로드(이어받기), 보고서. KBA 14K × HDL로 전 단계 검증 |
| 에이전트 (pi 1.4.0 + SAM 확장) | 도구 13종, 규칙(RULES.md), 스킬 4종, 프롬프트 템플릿 5종, 가드(설치·다운로드·sudo 금지, privacy) |
| 읽기 전용 보장 | 입력·리소스 쓰기를 **커널(Linux Landlock)** 이 막음(`src/samkit/sandbox.py`, R40). 가드는 먼저 거절하고 이유를 설명 |
| 기본 모델 | 로컬 **Gemma 4 31B**(`ollama/sam-gemma4-31b`), 에이전트·자문 공용. 클라우드 모델은 쓰지 않음(팀 결정) |
| 로컬 LLM 벤치마크 | 14개 모델 완료(실행 ID `2026-10-28`). 종합 보고서 `output/bench/2026-10-28/reports/FINAL.md`(git에 있음) |
| 문서 | README, SETUP, USAGE, USECASES, WORKFLOW, DESIGN, TOOLS, MODELS, BENCHMARK, EVALUATION, REVIEW-2026-10-27, ISSUES-2026-10-28, EXPERT-INPUT, 이 문서 |
| 테스트 | `./sam test`: Python 43개 + 가드 14개 통과, `ruff check src tests bench` 통과 |

검증에 쓴 서버: NVIDIA RTX PRO 5000 Blackwell 48 GB, RAM 123 GB, 16코어, Debian 13(커널 6.12), Ollama 0.40.11(`/usr/local/bin/ollama`,
시스템 서비스 11434). Gemma 4 31B(Q4_K_M, context 64K)는 GPU 메모리 약 29 GB를 씁니다.

## 2. 새 서버로 옮기기

### 2.1 git에 없는 것

`.gitignore` 기준입니다. 크기는 지금 서버의 값입니다.

| 항목 | 위치 (크기) | 새 서버에서 |
|---|---|---|
| 코드·문서·벤치마크 정의·벤치마크 보고서 | git | `git clone` |
| 입력 데이터 | `sam-data/input` (3.2 GB) | **복사**(통제 데이터: 이용 약정 범위 안에서). 경로는 실행할 때 `--input`으로 주므로 위치는 자유 |
| 참조 리소스 | `sam-data/resource` (4.4 GB: `resource-gwas.zip`, `ldblk_1kg_eas.tar.gz`, `dbSNP/`) | **복사**. 출처는 [TOOLS.md](TOOLS.md) 2절 |
| 분석 환경 | `.pixi/`, `.sam/bin`, `.sam/pi`, `.sam/cache` | `./sam bootstrap`이 다시 만듦(복사하지 말 것: 경로가 박혀 있음) |
| pi 설정 | `.pi-agent/` (`models.json`, `settings.json`, `auth.json`) | `./sam llm models-json`이 다시 만듦. `auth.json`은 로그인 정보라 옮기지 않음 |
| 기본 모델 | 시스템 Ollama 저장소 | `./sam llm pull gemma4-31b` (약 20 GB) |
| 벤치마크 모델 저장소 | `.sam/ollama/models` (94 GB, 11435 인스턴스용) | 벤치마크를 다시 돌릴 때만. `bench/pull-models.sh`로 받거나 이 폴더를 그대로 복사(Ollama 저장소 형식은 서버 간 호환) |
| BioGPT-Large | `.sam/hf/BioGPT-Large` (5.9 GB) | 벤치마크용. `bench/pull-models.sh`가 받음 |
| 벤치마크 정답 실행 | `output/bench/reference` | **다시 만들기**: `bench/make-reference.sh <입력> <리소스>`(`sam.json`에 절대 경로가 있어 복사본은 쓸 수 없음) |
| 벤치마크 원자료 | `output/bench/2026-10-28/<모델>/` (1.3 GB) | 재채점이 필요할 때만 복사. Track A 기록(`events.jsonl`)에는 로컬 모델이 읽은 개인 단위 값이 있을 수 있어 **통제 데이터로 취급** |
| 개발 시험 출력 | `.sam/devrun*`, `.sam/devtest_*`, `.sam/review1` | 필요 없음 |
| 이전 구현 자료 | `arxiv/GWAS.zip`, `arxiv/PRS.zip`, `arxiv/temp/`, `slides/` | 참고가 필요하면 복사 |
| Claude Code 메모리 | `~/.claude/projects/-projects-NIH-sam-pi-nih/memory/` | 옮기지 않아도 됨(내용은 이 문서 4절) |

### 2.2 순서

```bash
# 0) 요구 사항: Linux x86_64(pixi 잠금 파일이 linux-64만), 커널 5.13+ (Landlock), NVIDIA 드라이버, Ollama, 디스크 약 40 GB(+벤치마크 시 120 GB)
git clone git@github.com:charmgil/sam.pi.nih.git && cd sam.pi.nih
rsync -a <옛 서버>:/projects/NIH/sam.pi.nih/sam-data/ ./sam-data/      # 또는 원본에서 복사

# 1) 분석 환경 (pixi, 분석 도구, Node.js, pi)
./sam bootstrap
./sam test                                                          # Python 43 + 가드 14
./sam doctor --input sam-data/input --resource sam-data/resource    # 단계별 준비 상태 + read_only_enforcement(landlock_abi > 0 확인)

# 2) 로컬 모델 (Ollama가 없으면 먼저 설치: https://ollama.com, 검증 버전 0.40.11)
./sam llm pull gemma4-31b            # 받기 + sam-gemma4-31b 변형(num_ctx 65536)
./sam llm models-json                # pi에 등록 + 시작 모델을 기본값으로
./sam llm list                       # defaults 줄과 "ready as ollama/sam-gemma4-31b" 확인

# 3) 동작 확인 (모델 지정 없이 → 기본 모델, 자문도 같은 모델)
./sam agent --input sam-data/input --resource sam-data/resource --approvals deny \
    -p "sam_status로 유전형 표본 수를 한 줄로 알려줘" < /dev/null
```

벤치마크를 다시 돌리려면 [BENCHMARK.md](BENCHMARK.md) 3절과 아래 6.3절을 보세요.

### 2.3 GPU 메모리가 큰 서버에서 다시 볼 것

| 항목 | 지금 | 큰 GPU에서 |
|---|---|---|
| 컨텍스트 | 에이전트 변형 65,536(`models/catalog.json`의 `context_length`) | `./sam llm pull gemma4-31b --context 131072`처럼 늘릴 수 있음. 도구 결과가 긴 세션에 유리. 늘린 뒤 `./sam llm models-json` |
| 자문 모델 | 주 모델과 같은 Gemma 4 31B(추가 메모리 없음) | 다른 모델을 동시에 올려 독립된 2차 의견 가능(벤치마크 Track B 1위 GPT-OSS 20B). `--consultant ollama/sam-gpt-oss-20b` |
| 40B 이상 모델 | 벤치마크에서 제외(팀 결정) | GPT-OSS 120B, Llama 3.1 70B, Qwen 3.8 Flash-Next 125B-A6B 등을 시험할지 **팀이 결정**. 추가하면 `bench/models.json`과 `bench/pull-models.sh`에 넣고 같은 실행 ID로 이어서 실행 |
| 양자화 | 대부분 Q4_K_M | Q8_0이나 BF16으로 같은 모델을 비교해 양자화 영향 확인(카탈로그의 qwen3.8 태그는 q8_0이지만 벤치마크는 Q4_K_M) |
| vLLM | 레시피만 있고 미검증(O5) | FP8 가중치로 처리량을 높일 때 `./sam llm vllm-install`, `vllm-command <id>` |

## 3. 구조 한눈에

```
./sam (bash 실행기)
 ├─ bootstrap / setup         pixi 환경(default, regenie, ldsc, prscs, agent) + pi(npm)를 이 폴더 안에 설치
 ├─ run / status / doctor     → python -m samkit (분석 코어, JSON 한 개를 stdout으로)
 ├─ llm                       → samkit.llm (Ollama 변형 sam-<id>, pi models.json/settings.json)
 ├─ bench                     → bench/run.py (로컬 LLM 벤치마크)
 └─ agent                     → samkit/sandbox.py(Landlock: 입력·리소스 읽기 전용) → node pi
                                  └─ pi-package/extensions/sam (도구 13종 → samkit 호출, 가드, privacy, 명령)
```

| 파일 | 역할 |
|---|---|
| `sam` | 실행기. `cmd_agent`에서 sandbox 경유로 pi 실행 |
| `src/samkit/cli.py`, `context.py` | 명령 처리, 출력 경로 강제(`Context.out`), 입력 파일 찾기(`input_path`: 입력 폴더 → 출력 폴더 순) |
| `src/samkit/steps/*.py` | 단계별 구현(gwas, plots·peaks, ldsc, regional, finemap, prs, pheweb) |
| `src/samkit/manifest.py` | 실행 기록, 입력 지문(크기·mtime·첫 1 MiB 해시) |
| `src/samkit/sandbox.py` | Landlock 규칙 계산·적용 |
| `src/samkit/llm.py` | 모델 받기, 변형 만들기, pi 설정 쓰기 |
| `pi-package/extensions/sam/index.ts` | 도구 정의, 플래그, `/sam` 명령, 세션 오염(taint) 추적, 자문 기본값 |
| `pi-package/extensions/sam/guard.ts` | bash/read/write/edit/grep 가드 |
| `pi-package/RULES.md` | 모델에 주입되는 하네스 규칙 10개 |
| `models/catalog.json` | 모델 목록과 `defaults`(agent, consultant) |
| `bench/` | 벤치마크(시나리오, 문항, 채점, 보고서 템플릿, 모델 목록, 서버·다운로드 스크립트, 정답 실행 스크립트) |

## 4. 결정 사항

팀(사용자)이 정한 것들입니다. 바꿀 때는 먼저 팀에 확인하세요.

| 날짜 | 결정 |
|---|---|
| 10-27 | 입력·리소스 폴더는 실행할 때 매개변수로 받고(코드에 고정하지 않음) **읽기만** 한다. 쓰기는 실행 위치 쪽에서만, 결과는 `./output` 아래 |
| 10-27 | 런타임은 Python 3 + R(susieR만). LDSC는 Python 3 포팅을 쓰고 py2.7은 쓰지 않음 |
| 10-27 | 개인 단위 데이터 읽기는 **클라우드 모델일 때만** 막는다(로컬 모델은 허용). 도구 결과는 항상 집계값만 |
| 10-27 | 유전체 특화 LLM은 카탈로그와 자문 도구(`sam_consult`)로 연결. DNA 서열 모델(Evo 2 등)은 문서에만 |
| 10-27 | 이 하네스의 GWAS 결과를 PRS-CS 입력으로 쓰지 않음(표본 중복). PRS는 외부 요약 통계·weight(KNIH PheWeb 등)만 |
| 10-27 | 워크숍 스크립트와 다른 기본 파라미터(step1 MAF 1%, 별도 PCA pruning, Firth, SuSiE min_abs_corr 0.5, 단변량 LDSC 기본)는 일단 수용, 근거는 DESIGN.md 3절 |
| 10-27 | genome103의 gwas-agent-kit과는 비교하지 않음 |
| 10-28 | **로컬 LLM 중심.** Claude/GPT 등 상용 모델은 당분간 쓰지 않음. 클라우드 시험과 genome103 시험은 팀이 요청할 때 |
| 10-28 | 도메인 전문가·협력 연구자와 논의 후 필요하면 요청: PCA 친족 제거, 장거리 LD 구간 제외, MAC 기준, dosage VCF 기준(O1), py2.7 LDSC와의 수치 비교(O2). **요청 전에는 바꾸지 않음**. 검토 항목 전체: [EXPERT-INPUT.md](EXPERT-INPUT.md) |
| 10-28 | 가드 패턴은 충분하다고 판단(그 뒤 가드 우회가 실제로 나와 커널 보호를 추가, R40) |
| 10-28 | 벤치마크는 40B 미만 모델만 |
| 10-28 | 기본 모델을 Gemma 4 31B로(에이전트·자문) |
| 10-28 | 벤치마크 중 덮어써진 입력 파일의 수정 시각을 원래 값(2026-10-27 18:38:46)으로 복원 |

## 5. 개발할 때의 주의점

**실행 중에는 코드를 고치지 않기**
- 벤치마크나 에이전트 실행 중에는 `sam`, `src/`, `pi-package/`를 수정하지 마세요. bash는 스크립트를 실행 중에 줄 단위로 읽어서,
  실행 중인 `./sam`이 반쯤 고친 파일을 읽고 `syntax error`로 멈춘 적이 있습니다. `bench/`의 JSON·채점 코드는 시작할 때 읽으므로 비교적 안전합니다.

**프로세스 다루기**
- `pkill -f "<명령 일부>"`가 작업 중인 셸 자신과 일치해 셸이 종료된 적이 두 번 있습니다. PID를 확인해 정확히 지정하세요.
- pi를 비대화형으로 실행할 때는 `-p "<요청>" < /dev/null`이 필요합니다. 기록이 필요하면 `--mode json`을 쓰세요.
- 다른 모델·설정으로 시험할 때는 `SAM_PI_AGENT_DIR`로 pi 설정 폴더를 분리하세요(벤치마크가 그렇게 함).

**경로와 캐시**
- `PIXI_CACHE_DIR`는 절대 경로여야 합니다(상대 경로면 pixi가 패닉).
- npm 캐시는 `.sam/cache/npm`에 둡니다(홈 디렉터리에 쓰지 않음, R38).

**커널 보호(Landlock)**
- 입력 폴더가 실행 폴더 안에 있으면(`./sam-data/input`) 실행 폴더 **바로 아래**에는 새 파일을 만들 수 없습니다. 하위 폴더(`output/` 등)는 정상입니다.
- 임시 폴더가 입력의 상위 폴더면 `TMPDIR`이 `output/_tmp/agent`로 바뀝니다.
- `chmod`·`touch` 같은 메타데이터 변경, 다른 마운트 경로, 하드 링크는 Landlock 범위 밖입니다.
- 세션 중 `/sam-data`로 바꾼 폴더는 가드만 적용됩니다.
- 끄기는 `SAM_SANDBOX=off`, 확인은 `./sam doctor`의 `read_only_enforcement`와 pi 안 `/sam`입니다.

**Ollama**
- OpenAI 호환 API로는 요청마다 `num_ctx`를 바꿀 수 없어 `sam-<id>` 변형을 만듭니다. pi 설정에는 `compat.maxTokensField: "max_tokens"`를 둡니다.
- `/api/ps`의 `size_vram`은 실제보다 작게 나올 수 있습니다(Gemma 4 31B가 4.2 GB로 표시됐지만 실제 29 GB). `nvidia-smi`로 확인하세요.

**결과 무효화**
- 입력 파일의 크기·mtime·내용이 바뀌면 지문이 달라져 이후 단계가 다시 실행되거나 거부됩니다. 입력 파일을 `touch`하지 마세요.
- 같은 표현형을 다른 설정(공변량, PC 수, 표현형 파일)으로 다시 돌리면 이전 step1/step2와 후속 결과가 지워집니다. 결과 폴더 키는 표현형 이름입니다.
- 한 출력 폴더는 한 데이터셋에만 쓸 수 있습니다(`output/sam.json`이 입력·리소스 경로를 기록).

**privacy와 세션 오염**
- privacy `auto`면 로컬 모델은 개인 단위 파일을 읽을 수 있습니다. 그렇게 읽은 세션은 오염(taint)으로 기록되고, 클라우드 모델로 이어 쓸 수 없습니다.

**벤치마크**
- 채점 규칙을 고친 뒤에는 모델을 다시 돌리지 않고 `./sam bench rescore --run-id <ID>`로 재채점합니다.
- 보고서 템플릿을 고쳤으면 `./sam bench report --run-id <ID>`로 다시 만듭니다.
- 벤치마크는 `SAM_CONSULTANT=none`으로 돌립니다(자문 모델 없이, 2026-10-28 조건과 같게).

**품질 검사**
- 커밋 전에 `./sam test`와 `.pixi/envs/default/bin/ruff check src tests bench`를 돌리세요. 확장(TypeScript)은 가드 테스트만 `./sam test`에 들어 있고 타입 검사·린트는 없습니다. 확장을 고쳤으면 `./sam agent ... -p` 한 번으로 로드를 확인하세요.

## 6. 남은 일

### 6.1 팀 결정이 필요한 것

| ID | 내용 |
|---|---|
| O1 | PCA 친족 제거, MHC 외 장거리 LD 구간 제외, MAC 기준(분석 부분집합 기준으로), dosage VCF의 `--mind/--geno` 기준 |
| O2 | LDSC Python 3 포팅 대 원본 py2.7 수치 대조(같은 munged 파일로 1회) |
| — | 40B 이상 모델 시험 여부(큰 GPU 서버에서) |
| — | genome103 데이터로 시험, 클라우드 모델 시험(보류 중) |
| — | Me-LLaMA: PhysioNet 자격 인증을 받으면 13B-chat 추가 |
| — | 옛 서버의 벤치마크 Ollama 인스턴스(11435)와 저장소(94 GB) 정리 |

### 6.2 알려진 한계

| ID | 내용 |
|---|---|
| O3 | privacy 모드의 개인 단위 **읽기** 차단은 패턴 기반(쓰기는 커널이 막음). 클라우드 모델로 개인 단위 데이터를 다룰 때 주의 |
| O4 | 로컬 판정이 프로바이더 이름·호스트 기준이라 원격 vLLM이나 Ollama `*-cloud` 모델도 로컬로 취급 → 그런 경우 `--privacy on` |
| O5 | vLLM 설치·구동, Claude/ChatGPT 대화 미검증 |
| O6 | macOS 미검증 |
| R17·O7 | 자문 모델의 세부 사실 오류. `region`을 주면 Ensembl 유전자 목록이 근거로 붙지만 완전하지 않음. rsID→유전자 기억은 모든 로컬 모델이 신뢰 불가(벤치마크 평균 15%) |
| — | 성별 하위 분석처럼 값이 하나뿐인 공변량은 사용자가 공변량에서 빼야 함(자동 감지 없음) |

### 6.3 벤치마크 개선과 이식성

- 방법론 객관식이 천장 효과(17문항 중 12문항 전 모델 정답) → 더 어려운 문항 추가
- locus 문항은 정답 후보를 어디서든 언급하면 점수 → 1순위 판정으로 엄격하게
- 반복 3회 이상, 다른 형질(LDL, TG, 이진형), 다른 PRS weight
- 커널 보호 아래에서 모든 도구 호출 모델의 A8 재실행(선택. 모델 성향은 `no_input_write`로 이미 측정)
- **이식성**: 아래 세 가지는 새 서버에 맞게 손봐야 합니다
  - `bench/pull-models.sh`는 Ollama 주소(127.0.0.1:11435)와 실행 파일 경로(`/usr/local/bin/ollama`)가 고정돼 있습니다.
  - `bench/run.py`는 `server: bench` 모델의 다운로드 완료 표시(`.sam/bench/pulled/<태그>`)를 기다립니다.
  - 모든 모델을 시스템 Ollama 하나로 돌리려면 `bench/models.json`의 `servers.bench.url`을 `http://127.0.0.1:11434`로 바꾸고, 표시 파일은 `pull-models.sh`가 만들게 하세요(스크립트의 `export OLLAMA_HOST=...` 줄을 시스템 주소로 바꿔 실행).

### 6.4 코드 정리 후보

- `bench/pull-models.sh`의 서버 주소를 환경 변수로
- 벤치마크 실행기에 "이미 설치된 모델이면 표시 파일 없이 진행" 옵션
- 확장(TypeScript) 린트·타입 검사를 `./sam test`에 포함

## 7. 변경 이력

커밋 메시지만으로는 내용을 알기 어려워 각 커밋의 내용을 여기 적어 둡니다.
R 번호는 [REVIEW-2026-10-27.md](REVIEW-2026-10-27.md)의 이슈 번호입니다.

### 2026-10-27 — 하네스 구축과 검증 (커밋 전, `e83fd64`에 포함)

- 이전 Claude Code 기반 GWAS·PRS 하네스(`arxiv/GWAS.zip`, `arxiv/PRS.zip`)를 pi 기반 하네스 하나로 합침
  - 분석 코어 `samkit`: regenie GWAS, 플롯, locus, LDSC(Python 3 포팅), regional plot, SuSiE, PRS(weights, PRS-CS), KNIH PheWeb, 보고서
  - pi 확장: 도구 13종, 가드, privacy(클라우드 모델만 차단), 승인(설치·다운로드·부분 PRS), 세션 오염 추적, 스킬 4종, 템플릿 5종
  - 실행기 `sam`: pixi로 Python 3 + R + Node.js + pi를 폴더 안에 설치, 입력·리소스 경로는 매개변수
  - 모델 카탈로그(클라우드, 로컬 에이전트, 유전체·의생명 자문), Ollama 변형 관리, vLLM 레시피
  - 문서: README, SETUP, USAGE, DESIGN, TOOLS, MODELS
- 디버그·검증(REVIEW-2026-10-27): 실데이터·합성 데이터 실행, 독립 코드 리뷰 2건, 로컬 LLM 에이전트 시험
  - 이슈 R01–R37 처리(R17은 부분 대응). 높음: 설정 지문(R01), 세션 오염(R02), 하위 프로세스 취소(R03), 입력 폴더 안 출력 생성(R04)
  - 외부 기준(KBA 187K HDL)과 비교
  - 로컬 모델 재시험: Qwen 3.6 + MedGemma

### 2026-10-28 00:11 — `e83fd64` Initial commit

- 10-27까지의 하네스 전체(70개 파일)

### 2026-10-28 08:24 — `84596fd`

- R38: npm 캐시를 `.sam/cache/npm`으로(원래 요구사항 재점검 중 발견)
- O8: KNIH PheWeb 다운로드 HTTP Range 이어받기(`.part` + 상태 파일, ETag/Last-Modified 확인, 5회 재시도), 테스트 5개
- R39: 워크플로우 문서 작성 중 발견한 코드·문서 불일치 11건 수정(VCF 변환 조건, finemap의 genetic_map, `sam_doctor` 입력 없이 동작 등)
- `docs/WORKFLOW.md`: task 19개의 역할·입력·출력·외부 도구, 흐름도
- 로컬 LLM 벤치마크
  - `bench/`: Track A 시나리오 9개, Track B 문항 40개, 규칙 기반 채점, 모델별·요약 보고서 템플릿, BioGPT 실행기, 벤치마크용 Ollama 인스턴스
  - 정답 실행 생성, 14개 모델 실행(00:40–04:15)
  - `docs/BENCHMARK.md`
- R40: Qwen 3.6이 셸 변수 경로로 가드를 우회해 입력 파일을 덮어씀(내용 동일, mtime만 변경)
  - `src/samkit/sandbox.py`(Landlock)로 `./sam agent` 전체를 입력·리소스 읽기 전용으로
  - `./sam doctor`·`/sam`에 상태 표시, 테스트 13개, 같은 모델로 재실행해 차단 확인(`output/bench/2026-10-28-ro`)
- 벤치마크 채점 보정(거짓 음성 정규식 3개, A8 `no_input_write`, 공백 천 단위 수 인식)과 재채점
- 종합 보고서 `FINAL.md`

### 2026-10-28 08:30 · 08:39 — `d0fb487`, `c6806a0`

- `.gitignore` 조정, 벤치마크 보고서(`output/bench/*/reports/*.md`)를 git에 추가

### 2026-10-28 11:48 — `a2e55ee`

- `docs/EVALUATION.md`: Track A·B 평가 방법과 기준(한국어 + 영문)
- 기본 모델을 Gemma 4 31B로
  - `models/catalog.json`에 `defaults`를 두고, `./sam llm models-json`이 pi 시작 모델을 설정(이미 저장된 선택은 유지)
  - 자문 모델 기본값도 같은 모델로(`--consultant none`으로 끔). 벤치마크는 `SAM_CONSULTANT=none`
  - 테스트 4개
- 문서의 seed 설명 정정: seed 7은 Track B에만 적용, Track A는 pi가 seed를 지정하지 않음
- `docs/USECASES.md`: 기능별 한국어·영어 프롬프트 모음
- 입력 파일 `KBAv2.0AB_14K_HDL_fixed.txt`의 수정 시각 복원(git 밖 작업)

### 2026-10-28 (이 문서와 함께, 미커밋)

- `docs/DEVNOTES.md`(이 문서)
- `bench/make-reference.sh`: 정답 실행 스크립트를 경로를 받는 형태로 저장소에 추가(이전 것은 `output/` 아래에 절대 경로로 있었음)
- REVIEW O3 갱신(쓰기는 커널 보호, 읽기는 여전히 패턴 기반)
