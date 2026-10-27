# 준비 (설치와 연결)

## 1. 요구 사항

| 항목 | 내용 |
|---|---|
| OS | Linux x86_64 (검증: Debian 13). macOS arm64는 `./sam bootstrap`이 지원하지만 미검증 |
| 필수 명령 | `bash`, `curl`, `tar`, `sha256sum` |
| 디스크 | 하네스 도구 약 3.5 GB. 분석 출력은 데이터에 따라 다름(14K 표본 예: 약 5 GB, 대부분 PRS-CS LD 캐시) |
| 메모리/CPU | regenie step 1이 가장 무거움. 14K × 60만 변이 기준 16코어로 약 5분 |
| GPU | 로컬 LLM을 쓸 때만. 현재 서버(RTX PRO 5000 Blackwell 48 GB)는 30B급 모델까지 무리 없음 |
| 인터넷 | 설치할 때, KNIH PheWeb 다운로드, regional plot 유전자 트랙(Ensembl GRCh37 REST) |

root 권한은 필요 없습니다. 모든 것이 이 폴더 아래에 설치됩니다.

## 2. 설치: `./sam bootstrap`

```bash
cd /projects/NIH/sam.pi.nih
./sam bootstrap
```

하는 일:
1. pixi(v0.81.0)를 `.sam/bin/pixi`에 받고 sha256을 검증합니다.
2. `pixi.lock`에 고정된 다섯 환경을 `.pixi/envs/`에 설치합니다.

   | 환경 | 내용 |
   |---|---|
   | `default` | Python 3.12, pandas/numpy/scipy/matplotlib, plink2 2.0.0-a.7.8, R 4.5 + susieR 0.14.2 |
   | `regenie` | regenie 4.1.3.1 (boost 1.74 고정 때문에 R과 분리) |
   | `ldsc` | Python 3.10 + ldsc 2.0.1(Python 3 포팅) + 호환 numpy/pandas/scipy |
   | `prscs` | Python 3.10 + PRS-CS 1.1.0 + 호환 numpy/scipy/h5py |
   | `agent` | Node.js 24 (pi 실행용) |

3. pi 1.4.0을 `.sam/pi/`에 npm으로 설치합니다.

일부만 설치하려면 `./sam bootstrap --envs default,regenie`. 이후 추가 설치는
`./sam setup --step ldsc`처럼 단계 이름으로 할 수 있고, 에이전트 안에서는 `sam_setup` 도구가
사용자 승인을 받고 같은 일을 합니다.

버전을 바꾸려면 `pixi.toml`을 고치고 `.sam/bin/pixi lock` 후 다시 bootstrap 합니다.
pi 버전은 `SAM_PI_VERSION=1.4.0 ./sam bootstrap --envs agent`처럼 지정합니다.

설치 확인:

```bash
./sam test                                                        # 단위 테스트 (Python 21, 가드 14)
./sam doctor --input sam-data/input --resource sam-data/resource  # 단계별 준비 상태
```

## 3. 데이터 배치

입력과 리소스 위치는 코드에 들어 있지 않습니다. 실행할 때 `--input`, `--resource`로 넘깁니다.
두 폴더는 **읽기만** 합니다. 압축 파일도 그 자리에서 읽고, 필요한 파일만 `./output/_cache/`에 풉니다.

**입력 폴더**(예: `sam-data/input`)에 둘 수 있는 것:

| 파일 | 예 | 용도 |
|---|---|---|
| PLINK 파일셋 (bed/bim/fam 또는 pgen/pvar/psam) | `KBAv2.0AB_14K_COMMON.*` | GWAS, LD, PRS 대상 |
| VCF(.vcf.gz) | 임퓨테이션 결과 | PLINK 파일셋이 없을 때만 pgen으로 변환(R2 ≥ 0.8) |
| 표현형 표 (ID 열 + 표현형/공변량 열) | `KBAv2.0AB_14K_HDL.txt` (`ID SEX AGE HDL`) | GWAS. FID/IID가 없어도 ID 열로 자동 매칭 |
| PheWeb 형식 요약통계 | `phenocode-KBA_187K_HTN.tsv.gz` | PRS-CS 입력 |
| PRS weight | `HTN_PRS_weight.txt.gz` (`CHR SNP BP A1 A2 BETA`, 헤더 없음) | PRS 점수 |

**리소스 폴더**(예: `sam-data/resource`) — 폴더 형태와 zip/tar.gz 형태 모두 인식합니다:

| 구성요소 | 현재 파일 | 필요한 단계 |
|---|---|---|
| LDSC LD score + 가중치 (EAS) | `resource-gwas.zip` 안 `LDSC/baseline.*`, `LDSC/1000G_Phase3_EAS_weights_hm3_no_MHC/` | ldsc |
| rsID 매핑 | `dbSNP/KBAv2.0AB_dbSNP155_HG19_rsID.txt` (probe ID → rsID), `LDSC/pos2rsid.txt` | ldsc, prs |
| 유전 지도 (GRCh37) | `resource-gwas.zip` 안 `genetic_map/plink.chr*.GRCh37.map` | regional (선택) |
| PRS-CS LD reference | `ldblk_1kg_eas.tar.gz` (chr1–22) | prs (PRS-CS) |

인식 결과는 `./sam status --input ... --resource ...`의 `resources.components`에서 볼 수 있습니다.
출처는 [TOOLS.md](TOOLS.md#2-참조-리소스)에 있습니다.

> 데이터를 OS 수준에서도 보호하고 싶다면 소유자가 직접 `chmod -R a-w sam-data/input sam-data/resource`를
> 해 두세요. 하네스는 이 폴더들에 쓰지 않지만, 가드는 실수 방지용이지 보안 경계가 아닙니다.

## 4. 모델 연결

pi의 로그인 정보와 모델 설정은 `.pi-agent/`(이 폴더 안)에 저장됩니다. 사용자 홈의 `~/.pi`와
섞이지 않게 하기 위해서이며, 기존 pi 설정을 쓰려면 `SAM_PI_AGENT_DIR=~/.pi/agent`를 지정하세요.

### 4.1 클라우드 계정 (Claude, ChatGPT)

```bash
./sam agent --input sam-data/input --resource sam-data/resource
```
pi 화면에서:
- `/login` → **Anthropic (Claude Pro/Max)**: 브라우저 인증. 원격 서버라 콜백이 안 오면 최종 리다이렉트 URL(또는 코드)을 pi에 붙여넣습니다.
- `/login` → **OpenAI (ChatGPT Plus/Pro)**: 같은 방식. 모델은 `openai-codex/…`로 나타납니다.
- `/model`로 모델을 고르고 `Ctrl+S`로 기본값 저장.

API 키를 쓰려면 실행 전에 환경 변수를 지정합니다(파일에 저장되지 않음):
```bash
export ANTHROPIC_API_KEY=sk-ant-...      # Claude API
export OPENAI_API_KEY=sk-...             # OpenAI API
./sam agent --input ... --resource ... --model anthropic/claude-sonnet-5-5
```

**개인정보**: 클라우드 모델을 쓰면 `--privacy auto`(기본)에 의해 개인 단위 파일(표현형 표, fam/psam,
PC, 개인별 PRS 점수) 읽기가 차단됩니다. 분석 도구는 원래 집계값만 돌려주므로 분석에는 지장이 없습니다.
자세한 내용은 [USAGE.md](USAGE.md#개인정보-보호).

### 4.2 로컬 모델 (Ollama, 기본)

Ollama 0.40.11이 서버에 이미 설치되어 동작 중입니다(`/usr/local/bin/ollama`, 포트 11434).

```bash
./sam llm list                      # 카탈로그와 설치 상태
./sam llm pull gpt-oss-20b          # 받기 + 'sam-gpt-oss-20b' 변형 생성(num_ctx 65536, num_predict 지정)
./sam llm pull qwen3.6-35b-a3b      # 권장 중형 모델 (24 GB)
./sam llm pull medgemma-27b         # 자문용 의료 특화 모델 (17 GB; 소형 대안 intern-s1-mini 9 GB)
./sam llm models-json               # .pi-agent/models.json 에 등록
./sam agent --input ... --resource ... --model ollama/sam-qwen3.6-35b-a3b \
           --consultant ollama/sam-medgemma-27b
```

`pull`이 별도 변형(`sam-<id>`)을 만드는 이유: Ollama의 OpenAI 호환 API는 요청마다 context 길이를 바꿀 수
없고, 기본값이 VRAM에 따라 32K로 잡힐 수 있습니다. 에이전트는 도구 결과가 길어서 64K를 권장합니다.
변형은 가중치를 복사하지 않으므로 디스크를 더 쓰지 않습니다.

### 4.3 로컬 모델 (vLLM, 선택)

처리량이 높고 tool-call 파서가 모델별로 정확해서, 여러 사용자가 동시에 쓰거나 FP8/NVFP4 모델을 쓸 때 유리합니다.
PyTorch/CUDA 휠이 커서(수 GB) 분석 환경과 분리된 매니페스트(`models/vllm/pixi.toml`, vLLM 0.31.0)로 둡니다.

```bash
./sam llm vllm-install                          # 한 번만 (CUDA 13 휠; 드라이버 595 OK)
./sam llm vllm-command qwen3.8-27b              # 실행 명령 확인
./sam llm vllm-serve qwen3.8-27b                # 다른 터미널에서 서버 실행 (포트 8000)
./sam llm models-json --vllm qwen3.8-27b        # pi에 'vllm' 프로바이더 등록
./sam agent --input ... --resource ... --model vllm/Qwen/Qwen3.8-27B-FP8
```

vLLM 경로는 설정과 명령까지 준비되어 있으나, 이 서버에서 실제 설치·구동 검증은 아직 하지 않았습니다.

## 5. 다른 서버로 옮기기 (예: genome103)

1. 이 폴더를 git으로 옮깁니다(`.pixi/`, `.sam/`, `.pi-agent/`, `output/`, `sam-data/`는 git에 없음).
2. 새 서버에서 `./sam bootstrap`. 같은 `pixi.lock`이므로 같은 버전이 설치됩니다.
3. 데이터 위치만 실행 인자로 바꿉니다: `./sam agent --input /BDATA/.../input --resource /BDATA/.../resource`.
4. 로컬 LLM을 쓰려면 그 서버에 Ollama를 설치하고 `./sam llm pull ...`.

출력 폴더(`./output/sam.json`)는 처음 사용한 입력/리소스 경로를 기록하고, 다른 데이터로 같은 출력
폴더를 쓰려 하면 거부합니다(결과 섞임 방지). 다른 데이터는 다른 디렉토리에서 실행하세요.
