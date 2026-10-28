# LLM 카탈로그

목록 원본은 [`models/catalog.json`](../models/catalog.json)이고, `./sam llm list`로 설치 상태와 함께 볼 수 있습니다.
Ollama 태그는 2026-10-27에 레지스트리에서 모두 존재를 확인했습니다. 벤치마크 수치는 제작사 발표값입니다.

## 1. 어떤 모델을 쓸까

| 상황 | 권장 |
|---|---|
| 가장 정확한 분석·해석, 계정이 있음 | `anthropic/claude-sonnet-5-5` 또는 `claude-opus-5-5` (Claude Pro/Max), `openai-codex/gpt-6-sol` (ChatGPT Plus/Pro) |
| 데이터를 서버 밖으로 보내면 안 됨 (**기본**) | 로컬 `ollama/sam-gemma4-31b` — 에이전트와 자문 모두 (20 GB, 한 번만 적재) |
| 기본 모델의 대안 | `ollama/sam-qwen3.8-27b` (벤치마크 2위) |
| 빠른 응답 | `ollama/sam-qwen3.6-35b-a3b` (MoE, 약 2배 빠름) 또는 `ollama/sam-gpt-oss-20b` (14 GB, 답이 영어로 나오기 쉬움) |
| 의생명 특화 모델의 2차 의견 | `--consultant ollama/sam-medgemma-27b` (벤치마크에서 범용 모델보다 낫지 않았음) |

**기본값의 근거**: 2026-10-28 로컬 벤치마크([BENCHMARK.md](BENCHMARK.md) 5절)에서 Gemma 4 31B가 하네스 운용 1위(0.99),
지식·해석 2위(0.85)였고 입력 수정 시도·개인 ID 노출이 없었습니다. 기본값은 `models/catalog.json`의 `defaults`에 있습니다.

- 주 모델: `./sam llm models-json`이 pi의 시작 모델(`.pi-agent/settings.json`의 `defaultModel`)을 기본값으로 정합니다.
  pi 안에서 `/model`로 고르고 `Ctrl+S`로 저장한 모델이 있으면 그것을 유지합니다. 한 번만 바꾸려면 `--model`.
- 자문 모델: `--consultant`(또는 `SAM_CONSULTANT`)를 주지 않으면 기본값을 씁니다. 끄려면 `--consultant none`.

**개인정보 관점**: 클라우드 모델을 쓰면 대화와 도구 결과(집계값)가 해당 회사로 전송됩니다.
하네스는 클라우드 모델일 때 개인 단위 파일 읽기를 자동 차단하지만, KoGES/KBA 데이터 사용 약정에서
요약 통계의 외부 전송이 허용되는지는 별도로 확인하세요. 엄격하면 로컬 모델만 쓰면 됩니다.

## 2. 클라우드 (pi `/login` 또는 API 키)

| 프로바이더 | 인증 | 모델 ID 예 |
|---|---|---|
| `anthropic` | `/login` → Anthropic (Claude Pro/Max), 또는 `ANTHROPIC_API_KEY` | `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`, `claude-fable-5-1` |
| `openai-codex` | `/login` → OpenAI (ChatGPT Plus/Pro) | `gpt-6.1-sol`, `gpt-6-sol`, `gpt-6-luna`, `gpt-5.6-sol` |
| `openai` | `OPENAI_API_KEY` | `gpt-6.1-sol`, `gpt-6-sol`, `gpt-5.5`, `gpt-5.4-mini` |

pi는 이 밖에도 Gemini, OpenRouter, Bedrock 등 여러 프로바이더를 지원합니다(`/login`, pi 문서 `providers.md`).

## 3. 로컬 에이전트 모델 (48 GB GPU 기준)

도구 호출(function calling)을 지원하고 주요 벤치마크(SWE-bench, Terminal-Bench, τ-bench, BFCL, GPQA,
MMLU-Pro 등)에 보고된 공개 가중치 모델입니다.

| id (`./sam llm pull <id>`) | Ollama 태그 | 크기 | 구분 | 비고 (제작사 발표) |
|---|---|---|---|---|
| `gemma4-31b` | `gemma4:31b-it-q4_K_M` | 20 GB | **기본** (에이전트·자문) | τ2 76.9, GPQA 84.3. 로컬 벤치마크 1위 |
| `qwen3.8-27b` | `qwen3.8:27b-q8_0` | 30 GB | 최고 품질 | Terminal-Bench 2.1 73.0, GPQA-D 89.2. 로컬 벤치마크 2위(Q4_K_M) |
| `qwen3.6-35b-a3b` | `qwen3.6:35b-a3b-q4_K_M` | 24 GB | 빠름 (MoE) | 활성 3B. SWE-V 73.4, τ3 67.2, GPQA 86.0. 벤치마크에서 입력 덮어쓰기 시도(커널 보호로 차단됨) |
| `gpt-oss-20b` | `gpt-oss:20b` | 14 GB | 소형·빠름 | GPQA 71.5, SWE-V 34.0. 벤치마크에서 영어 답이 많음 |
| `muse-glimmer-30b` | `muse-glimmer:30b` | 18 GB | 대안 (Meta) | MCP-Atlas 75.5, SWE-V 76.0 |
| `glm-4.7-flash` | `glm-4.7-flash:latest` | 19 GB | 대안 | τ2 79.5, SWE-V 59.2 |
| `nemotron-3.5-lightning` | `nemotron-3.5-lightning:30b` | 25 GB | 처리량 | 1M context, 에이전트 점수는 낮은 편 |
| `devstral-small-2` | `devstral-small-2:24b` | 15 GB | 대안 (코딩) | SWE-V 68.0 |
| `granite4.1-30b` | `granite4.1:30b` | 17 GB | 대안 | BFCL v3 73.7, 추론 약함 |
| `qwen3-30b` | `qwen3:30b` | 18 GB | 기준선 (설치됨) | 2025년 Qwen3 |
| `gpt-oss-120b` | `gpt-oss:120b` | 65 GB | 대형 (CPU 오프로드, 느림) | GPQA-D 80.8 |

vLLM 레시피(FP8/NVFP4 저장소, `--tool-call-parser` 등)는 catalog.json의 각 항목 `vllm` 필드에 있습니다.
`./sam llm vllm-command <id>`로 실행 명령을 볼 수 있습니다.

**Ollama 주의**: OpenAI 호환 API는 `tool_choice`를 지원하지 않고, context 길이를 요청마다 바꿀 수 없습니다.
그래서 `./sam llm pull`이 `num_ctx`와 `num_predict`를 지정한 `sam-<id>` 변형을 만듭니다(에이전트 모델 65536,
단 모델 최대치가 더 작으면 그 값; 자문 모델 16384). `models.json`에는 변형의 실제 `num_ctx`가 기록됩니다.

## 4. 유전체·의생명 특화 모델 (자문용)

GWAS Catalog나 변이 문헌으로만 학습한 공개 대화형 LLM은 찾지 못했습니다. 아래는 생물·의학 데이터로
학습된 공개 모델입니다. 대부분 도구 호출이 없어 **에이전트가 아니라 자문(`sam_consult`)** 으로 연결합니다.
자문 답은 "2차 의견"으로 다루며, 분석 수치를 대신하지 않습니다(규칙에 명시).

| id | 받는 곳 | 크기 | 라이선스 | 비고 |
|---|---|---|---|---|
| `intern-s1-mini` (소형 자문) | Ollama `internlm/interns1:mini-q8_0` | 9 GB | Apache-2.0 | 과학 특화(생물·화학, 서열 데이터 포함), Qwen3-8B 기반 |
| `medgemma-27b` | Ollama `medgemma:27b` | 17 GB | HAI-DEF 약관(동의 필요) | Google 의료 특화 Gemma 3, 도구 호출 없음 |
| `medgemma1.5-4b` | Ollama `medgemma1.5:4b` | 3 GB | HAI-DEF 약관 | 소형 |
| `intern-s2-preview` | HF `internlm/Intern-S2-Preview-FP8` (vLLM) | 36 GB | Apache-2.0 | 과학 MoE, **도구 호출 지원** → 에이전트로도 시험 가능 |
| `biomni-r0-32b` | HF `biomni/Biomni-R0-32B-Preview` (vLLM) | 33 GB(FP8) | MIT | 의생명 에이전트용 RL 모델(GWAS 변이 우선순위 과제 포함), 자체 코드 실행 틀 전제 |

기본 자문 모델은 주 모델과 같은 `sam-gemma4-31b`입니다. 특화 모델을 자문으로 쓰려면:
```bash
./sam llm pull medgemma-27b && ./sam llm models-json
./sam agent --input ... --resource ... --consultant ollama/sam-medgemma-27b
> 2번 locus(±500kb)의 유전자들이 HDL과 어떤 관련이 있는지 자문 모델에 물어봐줘
```

`sam_consult`에 `region`(예: `11:116162579-117162579`)을 주면 하네스가 Ensembl(분석 빌드)에서 그 구간의
실제 단백질 코딩 유전자 목록을 받아 질문 앞에 붙이고, 답에는 "미검증 2차 의견" 표시를 붙입니다.

> **시험 결과(2026-10-27)**: 근거 없이 물었을 때 Intern-S1-mini는 이 locus(APOA5 클러스터)를 9번 염색체의
> TLR4라고 답했고, 주 모델(gpt-oss-20b)이 그대로 전달했습니다. 유전자 목록을 붙인 뒤에는 유전자는 맞게
> 답했지만 rs 번호 같은 세부는 여전히 틀린 것이 섞였습니다. 소형 자문 모델의 답은 참고용으로만 쓰고,
> 중요한 해석은 문헌이나 큰 모델로 확인하세요.

Ollama 라이브러리 모델 중에는 기본 출력 한도가 작은 것이 있습니다(예: Intern-S1-mini `num_predict 512`,
`num_ctx 4096`). `./sam llm pull`이 만드는 `sam-*` 변형은 두 값을 함께 늘리고, `models.json`은 Ollama가
따르는 `max_tokens` 필드를 쓰도록 설정합니다(Ollama는 `max_completion_tokens`를 무시함).

## 5. DNA 서열 모델 (문서로만 정리, 미연동)

fine-mapping으로 좁힌 변이의 기능 효과를 점수화하는 데 쓸 수 있는 모델입니다. 대부분 **hg38** 좌표라
현재 hg19 데이터는 liftover가 필요합니다. 연동하려면 별도 도구(예: `sam_variant_effect`)로 추가하는 것을 권합니다.

| 모델 | 가중치/접근 | 변이 점수 방법 | 비고 |
|---|---|---|---|
| Evo 2 7B | HF `arcinstitute/evo2_7b` (Apache-2.0) | ref/alt 서열 창의 Δlog-likelihood | 7B는 bf16로 동작, 1B/20B/40B는 Hopper FP8 필요 |
| GPN-Star / GPN-MSA | HF dataset `songlab/gpn-star-scores` (MIT) | 미리 계산된 전 SNV 점수 조회 | GPU 불필요, 가장 붙이기 쉬움 (hg38) |
| AlphaGenome | API(비상업 무료), 가중치 게이트 | `score_variant` (1 Mb 창) | hg38 |
| Nucleotide Transformer v3 | HF `InstaDeepAI/NTv3_650M_post` (비상업) | MLM 우도비 | |
| Borzoi / Enformer | HF `johahi/borzoi-replicate-0`, `EleutherAI/enformer-official-rough` | ref/alt 트랙 차이 | hg38 |
| HyenaDNA | HF `LongSafari/hyenadna-large-1m-seqlen-hf` | 인과 우도비 | |
| Chorus | github.com/pinellolab/chorus | 여러 서열 모델을 묶은 MCP 서버 | pi의 MCP 지원으로 연결 가능 |
