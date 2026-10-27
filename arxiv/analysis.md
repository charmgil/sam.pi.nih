GWAS.zip과 PRS.zip 간 차이를 비교해줄래?



----

GWAS.zip과 PRS.zip의 내용을 열어서 비교해 보겠습니다.

두 압축 파일은 겉모양이 같습니다. 둘 다 KOGO 2026 워크숍 실습용 Claude 작업 폴더이고, `CLAUDE.md` + `skill/` + `script/` + `prompt.txt`로 되어 있습니다. 하지만 설계 방식은 꽤 다릅니다.

## 구조 비교

| | **GWAS.zip** | **PRS.zip** |
|---|---|---|
| 흐름 | 순서대로 이어지는 5단계: regenie → Manhattan/QQ → LDSC → regional plot → SuSiE | 서로 대안인 2가지 방식: ① sumstat → PRS-CS → score, ② 이미 만든 weight로 바로 score |
| 설정 방식 | 공통 `config.sh` 하나에 몰려 있음. 스크립트는 인자 없이 `source config.sh` | 설정 파일 없음. 스크립트마다 위치 인자를 받고 Usage 검사를 함 |
| Claude의 역할 | `config.sh` 값을 고침 (LEAD_CHR/POS 등) | 명령어 인자를 실제 파일명으로 채움 |
| 스킬 형태 | `skill/01_gwas.md` 같은 단계 번호 문서. CLAUDE.md 표에서 링크 | `skill/prs-*.md` 같은 스킬 이름 문서. `.claude/skills/<name>/SKILL.md`와 쌍이라고 명시 |
| 행동 규칙 | **실행 원칙**: 요청받은 단계까지만 실행. 해당 단계에 필요한 프로그램만 확인 | **Claude 행동 지침**: 오류는 스크립트부터 확인. placeholder 금지. plink2/PRS-CS 말고는 다른 도구 제안 금지. 단계를 건너뛰면 경고 |
| 다운로드 전 확인 | 규칙 없음 | URL, 저장 경로, 파일 크기를 보여주고 승인받기 (sumstat·weight·dbSNP·LD ref 모두) |
| 프로그램 목록 | 버전까지 적음 (python 3.6.8, Python 2.7 for ldsc, R 4.4.0, susieR 0.14.2) | plink2, PRS-CS v1.1.0, Python3만 적음 |
| 외부 데이터 | Zenodo (LDSC), Beagle genetic map, Ensembl REST API | KNIH PheWeb 서버 (`150.183.252.241:8082`), PRS-CS Dropbox |
| 테스트 프롬프트 | 5개, 약 35분 | 2개, 약 6분 |

두 문서의 행동 규칙은 서로 보완 관계입니다. GWAS에는 "다른 도구 제안 금지"와 "다운로드 전 확인"이 없습니다. PRS에는 "필요한 프로그램만 확인"과 "요청받은 단계까지만 실행"이 없습니다. 두 패키지를 같은 형식으로 맞추려면 이 규칙들을 합치는 것부터 하면 됩니다.

**같은 부분:** plink2 v2.0.0-a.7.1, hg19, EAS를 쓰는 점, 그리고 `prompt.txt`의 무료(Haiku + desktop commander)/유료(Code + Sonnet) 구분이 같습니다. dbSNP 다운로드 섹션은 문장까지 똑같습니다.

## 고치면 좋을 불일치

**PRS.zip**
- **`.claude/skills/`가 압축 파일에 없습니다.** CLAUDE.md는 이 폴더를 Claude Code가 자동으로 인식한다고 쓰는데 실제로는 빠져 있습니다. GWAS.zip에는 `.DS_Store`까지 들어 있으니, 압축하다 빠졌다기보다 원래 폴더에 없거나 일부만 골라서 압축했을 가능성이 큽니다. 이대로면 유료(Code) 실습에서 스킬이 자동으로 잡히지 않습니다.
- 스크립트 헤더 Usage 주석에 옛 파일 번호가 남아 있습니다 (`03_method1_prscs.sh`, `04_method2_prs_weight.sh`). 예시 경로도 헤더는 `../input/`(script 폴더 기준), 스킬 문서는 `input/`(최상위 폴더 기준)으로 서로 다릅니다.
- PRS-CS에 필요한 Python 패키지(scipy, h5py)가 프로그램 목록에 없습니다. 프롬프트가 "필요한 프로그램 확인"을 테스트하는 만큼 영향이 있습니다.
- CLAUDE.md 디렉토리 트리에는 sumstat 이름이 `<phenotype>_sumstat.tsv.gz`인데, 실제로 받으면 `phenocode-<CODE>.tsv.gz`로 저장됩니다.

**GWAS.zip**
- **`config.sh`가 배포용이 아니라 개발 중 로컬 상태로 보입니다.** `GENO_NAME="KBAv2.0AB_14K_COMMON"`이고 "원본 VCF 삭제됨, bfile 그대로 사용"이라는 주석이 있습니다. 그런데 `prompt.txt`는 `input/KBAv2.0_KOGO_IMP.vcf.gz`를 pgen으로 바꾸는 것을 기대합니다. 그대로 배포하면 `0_vcf_to_pgen.sh`가 VCF를 찾지 못합니다.
- 예시 파일 이름이 서로 다릅니다. 문서에는 `KBA_IMP_pca.eigenvec`, `HDL_with_pc.txt`가 있고, config대로라면 `KBAv2.0AB_14K_COMMON_pca.eigenvec`, `KBAv2.0AB_14K_HDL_with_pc.txt`가 되며, prompt는 `HDL_pc.txt`를 확인하라고 합니다.
- **LEAD 타깃이 다릅니다.** config는 `chr16:56994528`인데 prompt와 `05_susie.md`는 `11:116662579`를 기대합니다.
  - `LEAD_SNP="AX-95823215|chr16:56960616:C:T"`의 ID 안 좌표가 `LEAD_POS`와 33,912bp 차이 납니다. 이 구간의 hg19↔hg38 좌표 차이와 같아 보여서, ID 문자열에 hg38 좌표가 들어 있는 것 같습니다.
  - 그런데 CLAUDE.md는 `LEAD_SNP="{chr}:{pos}:{ref}:{alt}"`로 만들라고 안내합니다. 이 안내대로 하면 `--ld-snp`에 실제 bim에 없는 ID가 들어갑니다.
- `01_gwas.md`는 `3-2_bt_step2.sh`도 "(동일)"하게 염색체 인자를 받는다고 쓰지만, 스크립트는 인자를 처리하지 않습니다 (qt 버전만 처리). `3-1` 주석에도 옛 이름 `4-1_qt_step2.sh`가 남아 있습니다.
- dbSNP 다운로드 섹션이 있지만 GWAS 스크립트 어디에서도 dbSNP를 쓰지 않습니다 (LDSC는 `resource/LDSC/pos2rsid.txt`를 씀). PRS에서 복사해 온 것으로 보입니다. 게다가 20~30GB인데 다운로드 전 확인 규칙이 없습니다.

원하시면 두 CLAUDE.md의 행동 규칙을 합쳐 한 형식으로 맞추고, 위 불일치를 고친 버전을 폴더에 따로 만들어 드리겠습니다.



