# 필요한 도구와 리소스

모든 도구는 `./sam bootstrap`이 이 폴더 안에 설치합니다(pixi, conda-forge/bioconda/PyPI/npm).
버전은 `pixi.lock`과 실행기의 `PI_VERSION`으로 고정됩니다. 런타임은 **Python 3 + R** 두 가지입니다.

## 1. 소프트웨어

### 1.1 분석 도구

| 도구 | 버전 | 출처 | 환경 | 쓰는 단계 | 비고 |
|---|---|---|---|---|---|
| PLINK 2 | 2.0.0-a.7.8 (2026-09-19) | bioconda `plink2` | default | gwas, regional, finemap, prs | QC, pruning, PCA, LD, `--score` |
| regenie | 4.1.3.1 | bioconda `regenie` | regenie | gwas | boost 1.74 고정이 R 4.5와 충돌해 별도 환경 |
| R | 4.5.3 | conda-forge `r-base` | default | finemap | susieR 계산만 |
| susieR | 0.14.2 | conda-forge `r-susier` | default | finemap | `susie_rss`, `estimate_s_rss` |
| jsonlite (R) | 최신 | conda-forge | default | finemap | 결과 요약 저장 |
| ldsc | 2.0.1 (Python 3 포팅) | PyPI `ldsc` | ldsc | ldsc | 아래 1.3 참고 |
| PRS-CS | 1.1.0 | bioconda `prscs` | prscs | prs | 아래 1.3 참고 |
| htslib (bgzip, tabix) | ≥ 1.20 | bioconda | default | (보조) | |

### 1.2 런타임과 라이브러리

| 항목 | 버전 | 환경 | 용도 |
|---|---|---|---|
| Python | 3.12 | default | samkit 코어, 플롯 |
| numpy / pandas / scipy / matplotlib | 2.5 / 2.3 / 1.18 / 3.11 | default | |
| requests, pyyaml | | default | PheWeb, Ensembl REST |
| Python + numpy/pandas/scipy/bitarray | 3.10 + 1.26 / 1.5 / 1.11 / 2.9 | ldsc | ldsc 호환 스택 |
| Python + numpy/scipy/h5py | 3.10 + 1.26 / 1.11 / 3.x | prscs | PRS-CS 호환 스택 |
| Node.js | 24.21 | agent | pi 실행 |
| pi (`@earendil-works/pi-coding-agent`) | 1.4.0 | `.sam/pi` (npm) | 에이전트 |
| pixi | 0.81.0 | `.sam/bin` | 환경 관리 |
| pytest, ruff, TypeScript | | default / `.sam/pi` | 테스트·린트·타입 검사 |

선택 설치:

| 항목 | 버전 | 위치 | 용도 |
|---|---|---|---|
| Ollama | 0.40.11 (서버에 이미 설치) | 시스템 | 로컬 LLM 서버 (기본) |
| vLLM | 0.31.0 | `models/vllm/.pixi` (`./sam llm vllm-install`) | 로컬 LLM 서버 (고성능, 선택) |

### 1.3 Python 2.7을 없앤 방법

- **LDSC**: 원본 `bulik/ldsc`는 Python 2.7 전용입니다. PyPI의 `ldsc` 2.0.1은 원본 1.0.1을 Python 3 문법으로만
  옮긴 것입니다. 핵심 파일을 원본과 비교했고 차이는 다음뿐입니다:
  `xrange→range`, `map→list(map)`, `.ix→.iloc`, `as_matrix→to_numpy`, `lstsq(rcond=None)`, 상대 import,
  그리고 Python 2에서 리스트 컴프리헨션 변수가 새어 나오던 곳(`parse.annot`)의 수정. 회귀 알고리즘은 같습니다.
  이 포팅본은 gzip으로 압축된 입력의 헤더를 바이트로 읽는 버그가 있어, 하네스가 munge 입력을 비압축으로 넘깁니다.
  최신 numpy/pandas와는 맞지 않아 호환 버전으로 고정한 전용 환경(`ldsc`)을 씁니다.
  > 원본(py2.7)과 수치가 완전히 같은지 1회 대조는 아직 하지 않았습니다. 필요하면 임시 py2.7 환경에서
  > 같은 munged 파일로 `--h2`를 돌려 비교하면 됩니다.
- **PRS-CS**: Python 3에서 동작하지만 bioconda 1.1.0은 SciPy 1.12에서 제거된 별칭(`scipy.sqrt`, `scipy.array` 등)을
  씁니다. 그래서 SciPy 1.11로 고정한 전용 환경(`prscs`)을 씁니다.
- **R**: susieR만 씁니다. 그림은 Python으로 옮겼고, R이 Python을 다시 부르던 구조(이전 `02_susie.R`)는 없앴습니다.

### 1.4 설치하지 않는 것

- conda/miniconda, 사용자 전역 `~/bin`, `~/ldsc` 같은 위치는 쓰지 않습니다.
- 시스템 패키지(apt), sudo는 필요 없습니다.
- 에이전트가 bash로 pip/conda/apt/npm/git clone을 실행하는 것은 가드가 막습니다.

## 2. 참조 리소스

리소스 폴더에 폴더 그대로 또는 zip/tar.gz로 둡니다. 하네스는 이름 규칙으로 찾습니다.

| 구성요소 (`kind`) | 인식하는 이름 | 현재 파일 | 출처 |
|---|---|---|---|
| LDSC LD score (`ldsc_ref`) | `<dir>/<stem>.{1..22}.l2.ldscore.gz` (+ `.l2.M_5_50`) | `resource-gwas.zip:LDSC/baseline.*` (EAS baseline v1.2) | Zenodo [10.5281/zenodo.7768714](https://doi.org/10.5281/zenodo.7768714) `1000G_Phase3_EAS_baseline_v1.2_ldscores.tgz` |
| LDSC 가중치 (`ldsc_weights`) | 경로에 `weight`가 있는 `*.{1..22}.l2.ldscore.gz` | `resource-gwas.zip:LDSC/1000G_Phase3_EAS_weights_hm3_no_MHC/` | 같은 Zenodo `1000G_Phase3_EAS_weights_hm3_no_MHC.tgz` |
| HM3 SNP 목록 (`hm3_snplist`) | `w_hm3*.snplist` | `resource-gwas.zip:LDSC/w_hm3_eas*.snplist` | (대립유전자 열이 없어 현재는 참고용) |
| 위치→rsID (`pos2rsid`) | `pos2rsid*.txt` | `resource-gwas.zip:LDSC/pos2rsid.txt` | 이전 워크숍 자료 |
| ID→rsID (`dbsnp_map`) | 이름에 `dbsnp`와 `rs`가 있는 2열 표 | `dbSNP/KBAv2.0AB_dbSNP155_HG19_rsID.txt` (KBA probe ID → rsID, 167만 행) | dbSNP b155(hg19)로 만든 KBA 전용 매핑 |
| 유전 지도 (`genetic_map`) | `plink.chr{N}.GRCh37.map` / `GRCh38` | `resource-gwas.zip:genetic_map/` | Beagle `plink.GRCh37.map.zip` (bochet.gcc.biostat.washington.edu/beagle/genetic_maps) |
| PRS-CS LD (`prscs_ld`) | `ldblk_{1kg\|ukbb}_{pop}/ldblk_*_chr{N}.hdf5` + `snpinfo_*` | `ldblk_1kg_eas.tar.gz` (chr1–22, 4.3 GB) | [PRS-CS](https://github.com/getian107/PRScs) README (Dropbox / Broad 미러) |

네트워크로 가져오는 것:

| 대상 | 주소 | 쓰는 곳 |
|---|---|---|
| KNIH PheWeb (요약통계, PRS weight) | `http://150.183.252.241:8082` (`SAM_PHEWEB_URL`로 변경) | `sam_pheweb` |
| Ensembl REST GRCh37 / GRCh38 | `grch37.rest.ensembl.org` / `rest.ensembl.org` | regional plot 유전자 트랙 (결과는 `_cache/genes`에 저장) |

## 3. 단계별로 필요한 것

| 단계 | 도구 | 리소스 | 네트워크 |
|---|---|---|---|
| gwas | plink2, regenie, Python | — | — |
| plots, peaks | Python | — | — |
| ldsc | Python, ldsc | ldsc_ref, ldsc_weights, dbsnp_map 또는 pos2rsid | — |
| regional | plink2, Python | genetic_map (없으면 재조합률 생략) | Ensembl (없으면 유전자 트랙 생략) |
| finemap | plink2, R + susieR | — | (regional 그림용 Ensembl) |
| prs (weights) | plink2, Python | dbsnp_map (대상 ID가 rsID가 아니면) | — |
| prs (prscs) | plink2, PRS-CS | dbsnp_map, prscs_ld | — |
| pheweb | Python | — | KNIH PheWeb |

`./sam doctor --step <단계>`(에이전트에서는 `sam_doctor`)가 이 표를 실제 설치 상태와 비교해 보여줍니다.
