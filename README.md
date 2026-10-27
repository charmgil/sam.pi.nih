# SAM — pi 기반 GWAS + PRS 분석 하네스

이전에 Claude Code용으로 따로 만들었던 GWAS 하네스(`arxiv/GWAS.zip`)와 PRS 하네스(`arxiv/PRS.zip`)를
하나로 합쳐 [pi](https://pi.dev) 코딩 에이전트 위에 다시 구성한 것입니다. pi가 연결하는 모델이면
어떤 것이든 같은 하네스로 분석합니다.

- **클라우드 모델**: Claude(Pro/Max 구독 또는 API 키), ChatGPT(Plus/Pro 구독) 또는 OpenAI API 키
- **로컬 모델**: Ollama(기본), vLLM(선택). 모델 카탈로그와 설치 명령을 함께 제공합니다
- **유전체·의생명 특화 모델**: 결과 해석에 대한 자문용(`sam_consult`)으로 연결합니다

설계 원칙은 **thin skills, thick tools**입니다.

| 누가 | 무엇을 |
|---|---|
| 모델(에이전트) | 무엇을 돌릴지 고르고, 사용자에게 결정할 것을 묻고, 결과를 해석 |
| 코드(`samkit` + pi 확장) | 경로, 파라미터, 전제조건 검사, 대립유전자 정렬, 기록, 읽기 전용 보호, 개인정보 차단 |

그래서 모델이 바뀌어도 분석 절차와 안전장치는 같고, 차이는 판단력으로 좁혀집니다.

## 한눈에 보기

```
./sam agent --input DIR --resource DIR      ← 사용자는 이것만 실행
   │
   ├─ pi (Node.js, .sam/pi)                  모델 연결(/login, models.json), 대화, 세션
   │    └─ pi-package/                       SAM 확장 (도구 13종, 가드, 규칙, 스킬 4종, 프롬프트 5종)
   │
   └─ samkit (Python, src/samkit)            결정론적 분석 코어 — 모든 단계는 JSON 요약만 반환
        ├─ plink2, regenie                   pixi 환경 default / regenie
        ├─ R 4.5 + susieR                    pixi 환경 default (fine-mapping 계산만)
        ├─ ldsc 2.0.1 (Python 3 포팅)        pixi 환경 ldsc
        └─ PRS-CS 1.1.0                      pixi 환경 prscs

입력 DIR, 리소스 DIR   → 읽기만 함 (zip/tar.gz도 풀지 않고 읽음)
./output               → 모든 결과, 로그, 기록(manifest.jsonl), 캐시
```

런타임은 **Python 3와 R 두 가지**입니다. Python 2.7은 없앴습니다(LDSC는 Python 3 포팅본 사용).
모든 도구는 [pixi](https://pixi.sh)로 이 폴더 안(`.pixi/`)에 설치되고, 버전은 `pixi.lock`으로 고정됩니다.
sudo는 필요 없습니다.

## 빠른 시작

```bash
cd /projects/NIH/sam.pi.nih
./sam bootstrap                                   # pixi, 분석 도구, Node.js, pi 설치 (한 번만)
./sam doctor --input sam-data/input --resource sam-data/resource   # 도구·리소스 점검

# 로컬 모델(예: gpt-oss 20B)을 쓸 때
./sam llm pull gpt-oss-20b && ./sam llm models-json

# 에이전트 시작 (결과는 지금 디렉토리의 ./output 에 생김)
./sam agent --input sam-data/input --resource sam-data/resource
#   pi 안에서: /login (Claude·ChatGPT 계정) 또는 /model 로 모델 선택
#   예) "HDL GWAS 분석해줘"  →  "유의한 locus 보여줘"  →  "2번 locus fine-mapping 해줘"
```

자세한 내용:

| 문서 | 내용 |
|---|---|
| [docs/SETUP.md](docs/SETUP.md) | 준비: 설치, 계정·모델 연결, 데이터 배치, 다른 서버로 옮기기 |
| [docs/USAGE.md](docs/USAGE.md) | 작동: 에이전트 사용 예, 명령, 출력 구조, 비대화형 실행, 문제 해결 |
| [docs/TOOLS.md](docs/TOOLS.md) | 필요한 도구와 리소스 목록 (버전, 출처, 어느 단계에 필요한지) |
| [docs/MODELS.md](docs/MODELS.md) | LLM 카탈로그: 클라우드, 로컬 벤치마크 상위 모델, 유전체 특화 모델 |
| [docs/DESIGN.md](docs/DESIGN.md) | 구조와 설계 결정, 이전 구현의 문제(I-1~I-28 등)를 어떻게 처리했는지 |
| [docs/REVIEW-2026-10-27.md](docs/REVIEW-2026-10-27.md) | 디버그·검증 리포트: 이슈 38건과 조치, 외부 기준(KBA 187K) 비교, 로컬 모델 시험 |

## 폴더 구조

```
sam.pi.nih/
├── sam                     실행기 (bootstrap / agent / doctor / run / llm / test)
├── pixi.toml, pixi.lock    분석 도구 환경 정의 (default, regenie, ldsc, prscs, agent)
├── src/samkit/             분석 코어 (Python)
│   ├── steps/              gwas, plots(+peaks), ldsc, regional, finemap, prs, pheweb
│   ├── r/susie.R           susieR 계산만 (설정 파일을 읽지 않음)
│   ├── context.py          입력·리소스 읽기 전용, 출력 경로 강제
│   ├── resources.py        리소스 폴더/압축 파일 인식, 필요한 파일만 캐시로 추출
│   └── llm.py              로컬 모델 관리 (Ollama, vLLM)
├── pi-package/             pi 패키지
│   ├── RULES.md            모델에 주입되는 하네스 규칙
│   ├── extensions/sam/     도구·가드·플래그·명령 (TypeScript)
│   ├── skills/             sam-setup, sam-gwas, sam-post-gwas, sam-prs
│   └── prompts/            /gwas, /post-gwas, /locus, /prs, /sam-report
├── models/                 catalog.json (모델 목록), vllm/pixi.toml (선택 설치)
├── tests/                  Python 단위 테스트 (pi-package/tests: 가드 테스트)
├── docs/                   문서
└── arxiv/                  이전 구현, 비평 노트, 슬라이드 (참고용)
```

`.pixi/`, `.sam/`(pixi·pi 바이너리, 캐시), `.pi-agent/`(로그인 정보, models.json), `output/`, `sam-data/`는
git에 들어가지 않습니다.
