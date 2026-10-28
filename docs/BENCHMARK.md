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

## 2. 대상 모델 (2026-10-28 실행)

40B 미만만 포함합니다(팀 결정). 목록과 순서는 [models.json](../bench/models.json).

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

## 3. 실행

```bash
# 0) 벤치마크용 Ollama 인스턴스 (모델 저장소를 하네스 폴더 안에 둠; 기존 서비스와 같은 바이너리·설정)
mkdir -p .sam/ollama .sam/bench
setsid nohup bench/ollama-serve.sh > .sam/ollama/serve.log 2>&1 &     # 127.0.0.1:11435
bench/pull-models.sh > .sam/bench/pull.log 2>&1 &                     # 모델 내려받기 (작은 것부터)
.sam/bin/pixi install --manifest-path bench/hf/pixi.toml               # BioGPT용 환경 (한 번)

# 1) 정답 실행 (한 번, 약 10분): 결과는 output/bench/reference/
bench/make-reference.sh sam-data/input sam-data/resource

# 2) 벤치마크: 내려받기가 끝난 모델부터 차례로 실행, 모델마다 보고서 생성
./sam bench run --run-id 2026-10-28
./sam bench run --run-id test --models llama3.1-8b --scenarios A1,A3 --repeats 1   # 일부만

# 3) 채점 규칙을 고친 뒤 모델을 다시 돌리지 않고 재채점·재작성
./sam bench rescore --run-id 2026-10-28
```

- 같은 `--run-id`로 다시 실행하면 끝난 모델·시나리오는 건너뜁니다(중단 후 이어서 실행).
- 기존 Ollama 서비스(11434)에 이미 있던 모델(gpt-oss 20B, MedGemma 27B, Qwen 3.6)은 그 서비스를 그대로 씁니다.
  벤치마크 중에는 같은 GPU를 다른 작업이 쓰지 않는 것이 좋습니다(속도 지표에 영향).

## 4. 결과물

```
output/bench/<실행 ID>/
├── reports/<모델>.md        모델별 보고서 (그 모델이 끝나는 즉시 생성)
├── reports/SUMMARY.md        비교 요약 (모델이 하나 끝날 때마다 갱신)
├── <모델>/result.json        점수와 세부 기록
├── <모델>/A/<시나리오>-r<n>/  pi 이벤트(events.jsonl), 로그, 그 실행의 하네스 출력(요약·로그만 남기고 큰 파일은 정리)
├── <모델>/B/answers.jsonl    Track B 답변 원문
├── pi-agent/models.json      벤치마크용 pi 모델 설정 (사용자 설정 .pi-agent와 분리)
└── variants.json             모델별 Ollama 변형(bench-*)과 양자화·기능
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
