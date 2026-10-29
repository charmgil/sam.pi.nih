# 로컬 LLM 벤치마크

여러 로컬 LLM이 이 하네스로 풀려는 문제(KoGES/KBA 유전형으로 GWAS·post-GWAS·PRS를 수행하고 해석하기)에
얼마나 맞는지 비교하는 실험입니다. 코드는 [bench/](../bench), 결과는 `output/bench/<실행 ID>/`에 생깁니다.

## 1. 무엇을 재는가

| 트랙 | 역할 | 방법 |
|---|---|---|
| **A. 하네스 운용** | 주 모델(에이전트) | `./sam agent`를 비대화형으로 실행해 한국어 요청 1개를 주고, 도구 호출 기록과 최종 답변을 규칙으로 채점. 시나리오 9개 |
| **B. 지식·해석** | 자문 모델(`sam_consult`) | 도구 없이 질문 40개(방법론 객관식, 변이→유전자, 근거 기반 locus 해석, 실제 결과 해석, 한국어 해석)에 답함 |

정답값은 모델 없이 `samkit`를 직접 돌린 정답 실행(`output/bench/reference/`)에서 가져옵니다. 채점은 모두 결정론적 규칙입니다
(LLM 심판 없음). 시나리오·문항·채점 기준은 [scenarios.json](../bench/scenarios.json), [questions.json](../bench/questions.json),
[score.py](../bench/score.py)에 있고, 모델 보고서의 3–4절에 표로 정리됩니다. 평가 방법과 기준 전체는
[EVALUATION.md](EVALUATION.md)(한국어 + 영문)에 있습니다.

## 2. 대상 모델

지금 [models.json](../bench/models.json)은 96 GB GPU 확장 실행(`2026-10-28-hart`, 2.2절)의 목록입니다. 실행할 때 그 실행 폴더에
`models.json` 사본이 저장되므로, 이전 실행의 보고서는 당시 목록으로 다시 만들어집니다.

### 2.1 2026-10-28 실행 (48 GB GPU)

40B 미만만 포함했습니다(당시 팀 결정).

| 계열 | 크기 | 비고 |
|---|---|---|
| Llama 3.1 | 8B | 70B·405B는 40B 이상 |
| Qwen 3.8 | 27B | 공개 가중치 중 40B 미만은 27B 하나 (Flash-Next 125B-A6B, 2.4T는 제외) |
| GPT-OSS | 20B | 120B는 40B 이상 |
| Gemma 4 | 12B, 31B | |
| Mistral | 7B (v0.3), Small 3.2 24B | 7B는 BioMistral과 같은 계열이라 비교 기준으로 포함 |
| MedGemma | 4B, 27B | 도구 호출 미지원 → Track B만 |
| TxGemma | 9B, 27B (chat) | Hugging Face GGUF(bartowski). 도구 호출 미지원 → Track B만 |
| BioMistral | 7B | Hugging Face GGUF. 도구 호출 미지원 → Track B만 |
| BioGPT | Large 1.5B | transformers(CPU). 지시 학습·채팅 템플릿 없음 → Track B만, 객관식은 로그 우도 지표 병기 |
| (기준) Qwen 3.6 | 35B-A3B | 실행 당시 하네스 권장 모델(당시 카탈로그 기본은 GPT-OSS 20B; 이 결과로 기본을 Gemma 4 31B로 변경) |

제외: **GPT-Rosalind**(OpenAI, 공개 가중치 없음·신뢰 접근 API 전용), **Me-LLaMA**(PhysioNet 자격 인증 후 제공. 팀이 접근권을
얻으면 13B-chat을 추가할 수 있음), 40B 이상 모델.

### 2.2 2026-10-28-hart 실행 (96 GB GPU 확장)

96 GB GPU(RTX PRO 6000 Blackwell)에 가중치와 32K 컨텍스트 KV 캐시가 모두 들어가는 모델(CPU 오프로드 없음)로 범위를 넓혔습니다.
위 14개 모델은 같은 조건으로 다시 실행하고, 아래 8개를 더했습니다. 계획: `output/bench/2026-10-28-hart/reports/PLAN.md`.

| 모델 | 구분 | 크기·양자화 | 비고 |
|---|---|---|---|
| GPT-OSS 120B | 40B 이상 | MoE 117B(활성 5.1B) · MXFP4, 65 GB | GPT-OSS 20B와 비교 |
| Llama 3.3 70B | 40B 이상 | 70B · Q4_K_M, 43 GB | Llama 3.1 8B와 비교. Llama 3.1 70B는 같은 구조의 후속인 3.3으로 대표 |
| Llama 4 Scout | 40B 이상 | MoE 109B(활성 17B) · Q4_K_M, 67 GB | 새 계열. Ollama 기본 템플릿 그대로(Track A에 시스템 프롬프트가 전달되지 않음) |
| Mistral Large 123B (2411) | 40B 이상 | 123B dense · Q4_K_M, 73 GB | Mistral 7B·Small 24B와 비교 |
| Med42 70B | 40B 이상, 의료 특화 | 70B · Q4_K_M(HF GGUF), 43 GB | 임상 지시 학습 Llama 3 70B. Me-LLaMA 대신 |
| Nemotron 3.5 Super 120B | 40B 이상 | MoE 120B(활성 12B) · NVFP4, 80 GB | Q4_K_M(90 GB)은 컨텍스트 자리가 없음 |
| Gemma 4 31B Q8_0 | 양자화 비교 | 31B · Q8_0, 34 GB | 기본 모델의 Q4_K_M과 비교 |
| Qwen 3.8 27B Q8_0 | 양자화 비교 | 27B · Q8_0, 30 GB | 카탈로그가 설치하는 태그 |
| Llama 4 Scout (템플릿 수정) | 템플릿 수정 변형 | Llama 4 Scout와 같은 가중치 | 2026-10-29 추가. Ollama 템플릿이 도구와 함께 시스템 프롬프트를 버리는 문제를 고친 변형([LLAMA4-TEMPLATE-2026-10-29.md](LLAMA4-TEMPLATE-2026-10-29.md)). 2–5회차에 별도 실행기로 추가 |

제외: Qwen 3.8 Flash-Next 125B-A6B(Q4_K_M 120 GB, NVFP4 105 GB), Llama 4 Maverick·Llama 3.1 405B·Qwen 3.8 2.4T(96 GB 초과),
GLM 5.3·DeepSeek V4.1 Flash·MiniMax M3.1 Flash·Mistral Large 4(Ollama에서 클라우드 전용), GPT-Rosalind, Me-LLaMA.

## 3. 실행

```bash
# 0) 벤치마크용 Ollama 인스턴스 (모델 저장소를 하네스 폴더 안에 둠; 기존 서비스와 같은 바이너리·설정)
mkdir -p .sam/ollama .sam/bench
setsid nohup bench/ollama-serve.sh > .sam/ollama/serve.log 2>&1 &     # 127.0.0.1:11435
setsid nohup bench/pull-models.sh > .sam/bench/pull.log 2>&1 &        # models.json 순서대로 내려받기
.sam/bin/pixi install --manifest-path bench/hf/pixi.toml               # BioGPT용 환경 (한 번)

# 1) 정답 실행 (서버마다 한 번, 10–20분): 결과는 output/bench/reference/
bench/make-reference.sh sam-data/input sam-data/resource

# 2) 벤치마크: 내려받기가 끝난 모델부터 차례로 실행, 모델마다 보고서 생성
setsid nohup ./sam bench run --run-id 2026-10-28-hart > .sam/bench/run-2026-10-28-hart.log 2>&1 &
./sam bench run --run-id test --models llama3.1-8b --scenarios A1,A3 --repeats 1   # 일부만

# 3) 채점 규칙이나 보고서 템플릿을 고친 뒤 모델을 다시 돌리지 않고 재채점·재작성
./sam bench rescore --run-id 2026-10-28-hart
./sam bench report --run-id 2026-10-28-hart

# 4) 반복 실행: 회차마다 새 실행 ID와 Track B seed. 동시에 띄워도 GPU에는 한 번에 한 모델(앞 회차 우선)
setsid nohup ./sam bench run --run-id 2026-10-29-hart-r3 --repeat 3 --seed 8 > .sam/bench/run-2026-10-29-hart-r3.log 2>&1 &
./sam bench aggregate --runs 2026-10-28,2026-10-28-hart,2026-10-29-hart-r3,2026-10-29-hart-r4,2026-10-29-hart-r5   # → output/bench/repeats/
```

- 같은 `--run-id`로 다시 실행하면 끝난 모델·시나리오는 건너뜁니다(중단 후 이어서 실행).
- 반복 실행: `--repeat N --seed S`는 처음 시작할 때 실행 폴더의 `run.json`에 고정되고, 같은 실행 ID로 다른 값을 주면 거부합니다.
  여러 회차를 함께 띄우면 `.sam/bench/gpu/` 잠금으로 GPU에는 한 번에 한 모델만 올라가고, 기다리는 회차 중 번호가 작은 쪽이 먼저 씁니다.
  앞 회차가 내려받기를 기다리는 동안 뒤 회차가 이미 받은 모델을 돌려 GPU가 놀지 않습니다.
- `aggregate`는 여러 실행의 `result.json`을 모아 모델별 mean ± SD(표본 표준편차)를 냅니다. 점수는 모델이 있는 모든 회차로,
  생성 속도는 최근 회차와 같은 GPU의 회차만으로 계산합니다.
- `bench/pull-models.sh`는 `models.json`에서 `server: bench`인 모델을 순서대로 받습니다. 받기가 끝나면 `.sam/bench/pulled/<태그>`,
  5회 실패하면 `<태그>.failed`를 만들고, 실행기는 실패한 모델을 기다리지 않고 오류로 기록한 뒤 다음 모델로 넘어갑니다.
  다른 Ollama로 받으려면 `OLLAMA_HOST=127.0.0.1:<포트> bench/pull-models.sh`.
- `server: system` 모델은 기존 Ollama 서비스(11434)에 이미 있는 것을 그대로 씁니다(2026-10-28-hart에서는 Gemma 4 31B만).
- 정답 실행은 입력 파일의 지문(크기·수정 시각·앞부분 해시)을 기록하므로, 입력을 다른 서버로 복사해 수정 시각이 바뀌었으면 다시 만들어야 합니다.
  hart 서버에서 다시 만든 결과는 옛 서버 결과와 요약값 223개가 모두 같았습니다(옛 결과: `output/bench/reference-2026-10-28/`).
- `bench/ollama-serve.sh`는 적재 제한 시간을 30분(`OLLAMA_LOAD_TIMEOUT`)으로 둡니다. 모델 저장소가 하드 디스크에 있으면 60–80 GB 모델을
  읽는 데 기본값 5분보다 오래 걸려 `500` 오류가 납니다(hart 서버 `/projects`).
- 서버 RAM보다 큰 모델은 `models.json` 항목에 `"parameters": {"use_mmap": false}`를 둡니다(벤치마크 변형의 Ollama 매개변수로 들어감).
  mmap으로 읽으면 페이지가 밀려나며 다시 읽혀 30분 안에 적재되지 않을 수 있습니다(hart, Mistral Large 73 GB / RAM 60 GB). 생성 결과에는 영향이 없습니다.
- 모델의 채팅 템플릿을 고쳐야 하면 `bench/chat-templates/<이름>.gotmpl`에 두고 항목에 `"template": "<이름>.gotmpl"`을 적습니다
  (예: Llama 4 Scout, [LLAMA4-TEMPLATE-2026-10-29.md](LLAMA4-TEMPLATE-2026-10-29.md)). 원래 모델은 기본 설정 결과로 함께 둡니다.
- 모든 시나리오는 정답 실행의 압축 파일 목록 캐시(`_cache/resources/*.index.json`)를 넣고 시작합니다. 없으면 빈 출력 폴더의 첫 `sam_status`가
  4.3 GB PRS-CS 묶음을 다시 풀어 읽는데, 붐비는 하드 디스크에서는 15분이 넘어 시나리오가 시간 초과됩니다(2026-10-28-hart).
- 벤치마크 중에는 같은 GPU를 다른 작업이 쓰지 않는 것이 좋습니다(속도 지표에 영향). 실행기는 모델마다 적재 직후 GPU 메모리 사용량과
  CPU 오프로드 여부, 서버 부하(load average)를 기록합니다.
- Track A 시나리오마다 실행기가 시계를 시작하기 전에 모델을 올리고, 실행 중 1분마다 적재 전용 요청(`keep_alive` 30분)을 보냅니다.
  pi의 요청은 Ollama 기본 유지 시간 5분을 쓰므로, 긴 도구 호출(GWAS) 중에 모델이 내려가 다시 올리는 시간이 측정에 섞이는 것을 막습니다.

## 4. 결과물

```
output/bench/<실행 ID>/
├── reports/<모델>.md        모델별 보고서 (그 모델이 끝나는 즉시 생성)
├── reports/SUMMARY.md        비교 요약 (모델이 하나 끝날 때마다 갱신)
├── <모델>/result.json        점수와 세부 기록
├── <모델>/A/<시나리오>-r<n>/  pi 이벤트(events.jsonl), 로그, 그 실행의 하네스 출력(요약·로그만 남기고 큰 파일은 정리)
├── <모델>/B/answers.jsonl    Track B 답변 원문
├── pi-agent/models.json      벤치마크용 pi 모델 설정 (사용자 설정 .pi-agent와 분리)
├── variants.json             모델별 Ollama 변형(bench-*)과 양자화·기능
├── models.json               이 실행을 시작할 때의 bench/models.json 사본 (보고서는 이것을 씀)
├── env.json                  이 실행의 GPU·CPU·RAM·Ollama·pi·Landlock (보고서 4.3절)
└── run.json                  반복 회차 번호와 Track B seed
```

Track A 이벤트 기록에는 로컬 모델이 읽은 개인 단위 값이 들어 있을 수 있습니다. `output/` 아래에만 두고(git 제외),
보고서에는 집계값과 답변만 싣습니다(개인 ID는 `[IID]`로 가림).

보고서 템플릿: [model_report.md](../bench/templates/model_report.md), [common.md](../bench/templates/common.md)
(데이터·실험 설계 공통 절).

## 5. 2026-10-28 실행 결과 요약

종합 보고서: `output/bench/2026-10-28/reports/FINAL.md` (출력 폴더라 git에는 없음)

| 역할 | 결과 |
|---|---|
| 주 모델 (Track A) | Gemma 4 31B 0.99, Qwen 3.8 27B 0.95, Qwen 3.6 35B-A3B 0.91(입력 파일 덮어쓰기 2회), Gemma 4 12B 0.91, GPT-OSS 20B 0.82, Mistral Small 3.2 0.62, Llama 3.1 8B 0.60, Mistral 7B 0.48 |
| 자문 (Track B) | GPT-OSS 20B 0.87, Gemma 4 31B 0.85, Qwen 3.6 0.84, Mistral Small 0.82, MedGemma 27B 0.78, … BioGPT 0.34 |
| 특화 모델 | 6종 모두 도구 호출 미지원, 지식·해석도 상위 범용 모델보다 낮음 |
| 공통 | rsID→유전자 회상은 모든 모델이 신뢰 불가(평균 15%). 유전자 목록을 주면 87–100% |
| 안전 | 개인 ID 노출 0건. 셸 변수 경로로 가드를 우회한 입력 쓰기가 나와 커널(Landlock) 읽기 전용을 추가(REVIEW R40). 확인 재실행: `output/bench/2026-10-28-ro/` |

채점 보정: 실행 후 거짓 음성 정규식 3개를 넓히고, A8에 `no_input_write`(입력 수정 시도 없음) 검사와 공백 천 단위 수 인식을 더해
`./sam bench rescore`로 모든 모델을 다시 채점했습니다(점수 변화 ±0.03 이내, 순위 변화 없음).
