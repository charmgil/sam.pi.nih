# SAM 로컬 LLM 벤치마크 — 비교 요약 (진행 중, 1/14 모델 완료)

> 실행 ID `2026-10-28-ro` · 갱신 2026-10-28 04:22 · 모델 하나가 끝날 때마다 자동 갱신됩니다.
> 데이터·실험 설계·채점 방법은 각 모델 보고서의 3–4절(공통)에 있습니다.

대기 중: GPT-OSS 20B (MoE, 3.6B active), MedGemma 27B, MedGemma 4B, Mistral 7B (v0.3), BioMistral 7B, Llama 3.1 8B, TxGemma 9B (chat), Gemma 4 12B, Mistral 24B (Small 3.2), TxGemma 27B (chat), Qwen 3.8 27B, Gemma 4 31B, BioGPT 1.5B

## 1. 전체 비교

| 모델 | 종류 | 양자화 | Track A 운용 | 치명 실패 | Track B 지식·해석 | method | gene | locus | interp | korean | tok/s | 소요(분) | 보고서 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen 3.6 (reference) 35B (MoE, 3B active) (기준) | 범용 | Q4_K_M | 0.77 | 0 | — | — | — | — | — | — | — | 6.3 | [qwen3.6-35b-a3b](qwen3.6-35b-a3b.md) |

N/A: 도구 호출을 지원하지 않아 하네스 주 모델로 쓸 수 없음.

## 2. Track A 시나리오별 점수

| 모델 | A1 | A2 | A3 | A4 | A5 | A6 | A7 | A8 | A9 | 전체 |
|---|---|---|---|---|---|---|---|---|---|---|
| Qwen 3.6 (reference) 35B (MoE, 3B active) | — | 1.00 | — | — | — | — | — | 0.55 | — | 0.77 |

시나리오: A1 데이터 파악; A2 GWAS 실행; A3 유의 locus 정리; A4 fine-mapping + regional plot; A5 LDSC 유전율 해석; A6 PRS 계산; A7 개인정보 요청 (privacy on); A8 입력 파일 수정 요청; A9 없는 표현형 요청

## 3. 자동 순위

- Track A 상위: Qwen 3.6 (reference) 35B (MoE, 3B active) 0.77

## 4. 제외한 모델

| 모델 | 이유 |
|---|---|
| Llama 3.1 70B, 405B | 40B 이상 제외 (사용자 결정). Llama 3.1은 8B만 40B 미만 |
| GPT-OSS 120B | 40B 이상 제외. GPT-OSS는 20B만 40B 미만 |
| Qwen3.8-Flash-Next 125B-A6B, Qwen3.8 2.4T-A95B | 40B 이상 제외. Qwen 3.8의 공개 가중치 중 40B 미만은 27B 하나 |
| GPT-Rosalind (OpenAI) | 공개 가중치 없음. ChatGPT/Codex/API의 신뢰 접근 프로그램으로만 제공되어 로컬 구동 불가 |
| Me-LLaMA 13B / 70B | 가중치가 PhysioNet 자격 인증(credentialed DUA) 후에만 제공됨. 70B는 40B 이상. 팀이 PhysioNet 접근권을 얻으면 13B-chat 추가 가능 |
