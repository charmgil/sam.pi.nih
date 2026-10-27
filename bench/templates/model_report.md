# SAM 로컬 LLM 벤치마크 — {{MODEL_NAME}}

> 실행 ID `{{RUN_ID}}` · 실험 {{STARTED}} → {{FINISHED}} ({{MINUTES}}분) · 이 보고서는 모델 실험이 끝난 직후 자동으로 만들어졌습니다
> (템플릿 `bench/templates/model_report.md`). 다른 모델과의 비교는 [SUMMARY.md](SUMMARY.md)에 있습니다.

## 1. 요약

{{SUMMARY_TABLE}}

{{HIGHLIGHTS}}

## 2. 모델

{{MODEL_TABLE}}

{{COMMON}}

## 5. Track A 결과 — 하네스 운용

{{TRACK_A}}

## 6. Track B 결과 — 지식·해석

{{TRACK_B}}

## 7. 자동 관찰

규칙으로 뽑은 관찰입니다. 사람의 검토 의견은 종합 리포트에 따로 적습니다.

{{OBSERVATIONS}}

## 부록. 원자료

{{FILES}}
