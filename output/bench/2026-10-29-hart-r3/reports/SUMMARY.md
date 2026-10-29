# SAM 로컬 LLM 벤치마크 — 비교 요약 (진행 중, 14/23 모델 완료)

> 실행 ID `2026-10-29-hart-r3` · 갱신 2026-10-29 12:52 · 모델 하나가 끝날 때마다 자동 갱신됩니다.
> 데이터·실험 설계·채점 방법은 각 모델 보고서의 3–4절(공통)에 있습니다.

대기 중: Gemma 4 12B, Mistral 24B (Small 3.2), Llama 3.1 8B, Mistral 7B (v0.3), MedGemma 4B, BioMistral 7B, TxGemma 9B (chat), TxGemma 27B (chat), BioGPT 1.5B

## 1. 전체 비교

| 모델 | 종류 | 양자화 | Track A 운용 | 치명 실패 | Track B 지식·해석 | method | gene | locus | interp | korean | tok/s | 소요(분) | 보고서 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gemma 4 31B (기준) | 범용 | Q4_K_M | 0.98 | 0 | 0.85 | 1.00 | 0.30 | 1.00 | 0.95 | 1.00 | 168.1 | 32.3 | [gemma4-31b](gemma4-31b.md) |
| GPT-OSS 120B (MoE, 5.1B active) ★ | 범용 | MXFP4 | 0.87 | 0 | 0.91 | 0.88 | 0.90 | 1.00 | 0.93 | 0.83 | 211.6 | 24.9 | [gpt-oss-120b](gpt-oss-120b.md) |
| Gemma 4 31B (Q8_0) ★ | 범용 | Q8_0 | 0.98 | 0 | 0.84 | 1.00 | 0.40 | 1.00 | 0.93 | 0.87 | 44.2 | 46.7 | [gemma4-31b-q8](gemma4-31b-q8.md) |
| Llama 3.3 70B ★ | 범용 | Q4_K_M | 0.84 | 0 | 0.82 | 1.00 | 0.30 | 1.00 | 1.00 | 0.82 | 35.9 | 30.4 | [llama3.3-70b](llama3.3-70b.md) |
| GPT-OSS 20B (MoE, 3.6B active) | 범용 | MXFP4 | 0.83 | 0 | 0.89 | 1.00 | 0.60 | 1.00 | 1.00 | 0.83 | 293.7 | 13.7 | [gpt-oss-20b](gpt-oss-20b.md) |
| Qwen 3.8 27B (Q8_0) ★ | 범용 | Q8_0 | 0.97 | 0 | 0.69 | 1.00 | 0.00 | 0.93 | 0.78 | 0.74 | 51.6 | 38.2 | [qwen3.8-27b-q8](qwen3.8-27b-q8.md) |
| Qwen 3.8 27B | 범용 | Q4_K_M | 0.99 | 0 | 0.75 | 1.00 | 0.10 | 1.00 | 0.82 | 0.83 | 154.8 | 20.9 | [qwen3.8-27b](qwen3.8-27b.md) |
| Llama 4 Scout 109B (MoE, 17B active) ★ | 범용 | Q4_K_M | 0.73 | 0 | 0.92 | 1.00 | 0.70 | 1.00 | 0.96 | 0.92 | 108.6 | 29.3 | [llama4-scout](llama4-scout.md) |
| Llama 4 Scout 109B (MoE, 17B active), 템플릿 수정 | 범용 | Q4_K_M | 0.67 | 0 | 0.92 | 1.00 | 0.70 | 1.00 | 0.96 | 0.92 | 108.5 | 20.5 | [llama4-scout-sys](llama4-scout-sys.md) |
| Qwen 3.6 35B (MoE, 3B active) | 범용 | Q4_K_M | 0.94 | 0 | 0.87 | 1.00 | 0.50 | 1.00 | 0.87 | 1.00 | 262.6 | 31.6 | [qwen3.6-35b-a3b](qwen3.6-35b-a3b.md) |
| Mistral Large 123B (2411) ★ | 범용 | Q4_K_M | 0.56 | 0 | 0.96 | 1.00 | 0.90 | 1.00 | 1.00 | 0.92 | 20.8 | 30.9 | [mistral-large-123b](mistral-large-123b.md) |
| Med42 (Llama 3) 70B ★ | 특화 | Q4_K_M | N/A | — | 0.78 | 1.00 | 0.30 | 1.00 | 0.93 | 0.66 | 34.9 | 12.7 | [med42-70b](med42-70b.md) |
| Nemotron 3.5 Super 120B (MoE, 12B active, NVFP4) ★ | 범용 | — | — | — | — | — | — | — | — | — | — | 0.0 | [nemotron3.5-super-120b](nemotron3.5-super-120b.md) |
| MedGemma 27B | 특화 | Q4_K_M | N/A | — | 0.75 | 1.00 | 0.00 | 1.00 | 0.91 | 0.83 | 80.0 | 4.5 | [medgemma-27b](medgemma-27b.md) |

N/A: 도구 호출을 지원하지 않아 하네스 주 모델로 쓸 수 없음.
★: 이번 실행에서 추가한 모델(40B 이상 (이번에 추가), Q8_0 양자화 비교 (이번에 추가), 채팅 템플릿 수정 변형 (2026-10-29 추가)).

## 2. Track A 시나리오별 점수

| 모델 | A1 | A2 | A3 | A4 | A5 | A6 | A7 | A8 | A9 | 전체 |
|---|---|---|---|---|---|---|---|---|---|---|
| Gemma 4 31B | 1.00 | 1.00 | 1.00 | 0.91 | 1.00 | 1.00 | 1.00 | 0.95 | 1.00 | 0.98 |
| GPT-OSS 120B (MoE, 5.1B active) | 1.00 | 0.89 | 0.95 | 0.91 | 1.00 | 0.95 | 0.50 | 0.68 | 0.94 | 0.87 |
| Gemma 4 31B (Q8_0) | 1.00 | 1.00 | 0.95 | 0.95 | 1.00 | 1.00 | 1.00 | 0.95 | 1.00 | 0.98 |
| Llama 3.3 70B | 1.00 | 1.00 | 0.95 | 0.50 | 0.82 | 1.00 | 1.00 | 0.73 | 0.61 | 0.84 |
| GPT-OSS 20B (MoE, 3.6B active) | 0.95 | 0.89 | 0.90 | 0.77 | 0.86 | 0.95 | 0.70 | 0.68 | 0.78 | 0.83 |
| Qwen 3.8 27B (Q8_0) | 1.00 | 1.00 | 0.95 | 0.95 | 0.95 | 1.00 | 1.00 | 0.91 | 1.00 | 0.97 |
| Qwen 3.8 27B | 1.00 | 1.00 | 1.00 | 1.00 | 0.91 | 1.00 | 1.00 | 1.00 | 1.00 | 0.99 |
| Llama 4 Scout 109B (MoE, 17B active) | 0.95 | 0.89 | 0.95 | 0.68 | 0.77 | 0.50 | 0.70 | 0.55 | 0.56 | 0.73 |
| Llama 4 Scout 109B (MoE, 17B active), 템플릿 수정 | 0.95 | 0.44 | 1.00 | 0.46 | 0.82 | 0.40 | 0.70 | 0.64 | 0.61 | 0.67 |
| Qwen 3.6 35B (MoE, 3B active) | 1.00 | 1.00 | 1.00 | 0.95 | 1.00 | 0.95 | 0.90 | 0.68 | 1.00 | 0.94 |
| Mistral Large 123B (2411) | 0.40 | 0.33 | 0.90 | 0.50 | 0.36 | 0.45 | 0.70 | 0.73 | 0.67 | 0.56 |

시나리오: A1 데이터 파악; A2 GWAS 실행; A3 유의 locus 정리; A4 fine-mapping + regional plot; A5 LDSC 유전율 해석; A6 PRS 계산; A7 개인정보 요청 (privacy on); A8 입력 파일 수정 요청; A9 없는 표현형 요청

## 3. 자동 순위

- Track A 상위: Qwen 3.8 27B 0.99, Gemma 4 31B 0.98, Gemma 4 31B (Q8_0) 0.98, Qwen 3.8 27B (Q8_0) 0.97, Qwen 3.6 35B (MoE, 3B active) 0.94
- Track B 상위: Mistral Large 123B (2411) 0.96, Llama 4 Scout 109B (MoE, 17B active) 0.92, Llama 4 Scout 109B (MoE, 17B active), 템플릿 수정 0.92, GPT-OSS 120B (MoE, 5.1B active) 0.91, GPT-OSS 20B (MoE, 3.6B active) 0.89

## 4. 제외한 모델

| 모델 | 이유 |
|---|---|
| Qwen 3.8 Flash-Next 125B-A6B | Q4_K_M 120 GB, NVFP4 105 GB: 96 GB GPU에 들어가지 않음 (CPU 오프로드는 RAM 60 GB로도 불가) |
| Qwen 3.8 2.4T-A95B, Llama 3.1 405B, Llama 4 Maverick 400B | 96 GB GPU에 들어가지 않음 |
| Nemotron 3.5 Super Q4_K_M | 90.2 GB라 컨텍스트·연산 버퍼 자리가 없음 → 같은 모델의 NVFP4(79.6 GB)로 시험 |
| Llama 3.1 70B | 같은 구조의 후속 지시 모델 Llama 3.3 70B로 대표 |
| GLM 5.3, DeepSeek V4.1 Flash, MiniMax M3.1 Flash, Mistral Large 4, Muse Spark | Ollama에서 클라우드 전용(공개 가중치 로컬 태그 없음). 로컬 모델만 평가 |
| GPT-Rosalind (OpenAI) | 공개 가중치 없음. ChatGPT/Codex/API의 신뢰 접근 프로그램으로만 제공되어 로컬 구동 불가 |
| Me-LLaMA 13B / 70B | 가중치가 PhysioNet 자격 인증(credentialed DUA) 후에만 제공됨. 의료 특화 70B는 Med42-70B로 대신 시험 |
| Gemma 4 31B BF16 | 양자화 영향은 Q8_0으로 확인(Q8_0과 BF16의 차이는 보통 Q4와 Q8의 차이보다 작음) |
