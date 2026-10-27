# 90 — 발견된 문제점과 일반화를 위한 메모

심각도:
- **Bug**: 현실적인 조건에서 잘못되거나 누락된 결과를 만든다.
- **Fragile**: 규칙을 사람이 직접 지켜야만 동작한다.
- **Science**: 재검토할 가치가 있는 방법론적 선택이다.
- **Doc**: 주석이나 문서가 코드와 일치하지 않는다.

*(verify)* 표시 항목은 여기서 실행해 볼 수 없었던 도구의 동작에 근거한다(이 머신에는 plink2, regenie, R이 설치되어 있지 않다). 나머지는 모두 코드를 읽어 얻은 것이며, pandas와 bash 동작은 별도의 임시 환경에서 확인했다.

## A. 순위별 발견 사항

| ID | 심각도 | 위치 | 발견 사항 | 수정 제안 |
|---|---|---|---|---|
| I-1 | Bug | `04_regional_plot/02_plot.py` L49 | 유전자 트랙이 `rest.ensembl.org`(**GRCh38**)를 조회하지만 데이터는 **hg19**이므로, 워크숍 locus(*APOA5*)에서 유전자가 약 129 kb 어긋나게 그려진다. | build가 hg19이면 `grch37.rest.ensembl.org`를 사용하고, build를 config 값으로 만든다. |
| I-2 | Bug | `05_susie/02_susie.R` L61–72, L162 | 실행 결과 CS가 없으면 이전의 `chr{C}_susie_cs.tsv`가 그대로 남고, 자동 오버레이가 **오래된(stale)** credible set을 그린다. | 매 실행마다 CS 파일을 삭제하거나 덮어쓴다(빈 표를 쓴다). |
| I-3 | Bug | `02_susie.R` L160–164 | 오버레이 단계가 작업 디렉터리 기준 상대 경로(`output/…`, `script/…`)를 사용하므로, Rscript를 프로젝트 루트에서 시작하지 않으면 실패하거나 건너뛴다. | 스크립트 위치로부터 경로를 유도하거나 루트를 인자로 전달한다. |
| I-4 | Bug | `02_plot.py` L36–45, L122–125; `02_susie.R` L81, L167 | r² 항목이 없는 SNP는 **아예 그려지지 않는다**. R 스크립트는 `--lead` = `lead_pos`에 가장 가까운 SNP를 넘기는데, 이는 `.vcor` 생성에 쓰인 `LEAD_SNP`와 다를 수 있다. 다르면 거의 모든 점이 사라진다. | r²가 NaN인 점은 회색으로 그리고, `LEAD_SNP`를 그대로 전달하며, lead를 찾지 못하면 경고한다. |
| I-5 | Fragile | `02_plot.py`, `02_susie.R` CLI | chr, pos, window, lead, `n_sample`을 손으로 입력하며, 셸 스크립트가 사용한 `config.sh`와 일치해야 한다. 이를 확인하는 장치가 없다. | 모든 언어가 읽는 단일 config(YAML/TOML)를 두거나, 값을 전달하는 단일 driver를 둔다. |
| I-6 | Bug | `02_plot.py` L165 | 유전자 패널이 **없을 때**(오프라인 또는 `--no-gene`)에도 x 눈금 레이블이 숨겨져 축에 숫자가 없다. | `has_genes`일 때만 숨긴다. |
| I-7 | Bug | `plot.py` L21/L61; `01_input.py` L15 | LOG10P > ~308이면 `10**-LOG10P`가 0으로 underflow된다. 해당 SNP는 QQ plot에서 빠지고 munge에서 제거된다(λ_GC는 중앙값이므로 거의 영향이 없고, ldsc는 어차피 매우 큰 χ²를 제외한다). | QQ plot에는 `LOG10P`를 직접 사용하고, munge용으로는 P를 ~1e-300에서 clip한다. |
| I-8 | Bug *(verify)* | `3-1_qt_step2.sh` L11 | 여러 염색체가 `--chr 11,12`가 된다. regenie의 목록 플래그는 `--chrList`이다(`--chr`는 값 하나를 받으며 반복 가능). | `--chrList`를 사용한다. |
| I-9 | Bug (latent) | `1-3_merge_pc.py` L33; `01_input.py` L33 | 결측값이 **빈 필드**로 기록된다. 공백으로 분리하는 도구(munge는 확인됨; regenie는 `NA`를 기대함)는 연속된 탭을 하나로 합치므로, 값이 **잘못된 열로 밀린다**. | `to_csv(..., na_rep="NA")`. |
| I-10 | Doc / dead code | `plot.py` L19, `01_input.py` L12, `02_plot.py` L27 | `df[col] != 'NA'`는 아무 효과가 없다(pandas가 이미 `NA`를 NaN으로 파싱함). 이후 코드가 NaN을 제거하기 때문에 출력이 여전히 올바를 뿐이다. | `dropna(subset=[col])`. |
| I-11 | Science / fragile | `02_susie.R` L32–48 | BETA(regenie `ALLELE1` 기준)와 plink2 `r`(ALT 기준)이 같은 allele을 가리킨다고 가정하며, 이를 전혀 확인하지 않는다. 중복 ID도 이름 기반 인덱싱을 깨뜨린다. | 정렬 시 allele을 확인하고, ID 중복을 제거하며, `chr:pos:ref:alt` 같은 고유 ID를 사용한다. |
| I-12 | Science | `3-2_bt_step2.sh` | 이진 형질 step 2에 `--firth --approx`나 `--spa`가 없어, case/control이 불균형하거나 희귀 변이인 경우 p-value가 부풀려질 수 있다. | `--firth --approx --pThresh 0.01`(또는 `--spa`)을 추가한다. |
| I-13 | Science | `1-1` vs `3-x` | QC 필터(MAF, HWE, missingness)는 prune set에만 적용되고, step 2는 모든 variant를 검정한다(regenie의 MAC ≥ 5만 적용). 샘플 QC가 없다. | step 2용 명시적 QC(`--minMAC`, INFO, QC된 목록 `--extract`)와 샘플 QC를 추가한다. |
| I-14 | Science | `1-1_ld_pruning.sh` L11 | 같은 r² < 0.9 prune set이 PCA에도 쓰인다. regenie step 1에는 적합하지만 PCA에는 느슨하다(보통 0.1–0.2이며 long-range LD 영역을 제외함). | PCA용으로 별도의 더 엄격한 prune set을 둔다. |
| I-15 | Science | `01_input.py` L19; `02_ldsc.sh` L19–27 | rsID를 **위치만으로** 붙이며(allele 무시), munge를 `--merge-alleles` 없이 실행한다. | allele까지 매칭하거나, munge를 `--merge-alleles w_hm3.snplist`로 실행한다. |
| I-16 | Fragile | `config.sh` L26–32; 모든 `.sh` | `.bed`와 `.pgen`이 모두 없으면 플래그가 설정되지 않아 도구가 불분명한 오류로 실패한다. `set -euo pipefail`을 쓰는 스크립트가 없어 실패 후에도 이후 명령이 실행된다. | 명확한 메시지와 함께 일찍 실패하게 하고, `set -euo pipefail`을 추가한다. |
| I-17 | Fragile | `config.sh` L7 | `BASH_SOURCE`는 bash 전용이다. `sh script.sh`로 실행하거나 zsh에서 source하면 `GWAS_DIR`가 잘못된다. | "bash로 실행"이라고 문서화하거나, 셸을 감지한다. |
| I-18 | Doc | `CLAUDE.md` L109, L123 | `\    # comment`는 줄 연속이 아니므로, 참조 블록을 붙여넣어 실행할 수 없다. | 주석을 명령 위로 옮긴다. |
| I-19 | Doc | `CLAUDE.md` L63 vs `02_plot.py` L123 | 표에는 Python 3.6.8이라고 되어 있지만, `between(inclusive='left')`는 pandas ≥ 1.3이 필요하고 이는 Python ≥ 3.7을 요구한다. | 실제 버전을 고정한다(예: `requirements.txt` 또는 conda env 파일). |
| I-20 | Doc | `prompt.txt` L16 | 체크리스트는 `input/HDL_pc.txt`와 `output/01_gwas/plink2/`를 기대하지만, 스크립트는 `{P}_with_pc.txt`와 `step1/`, `step2/`, `pca/`를 생성한다. | 체크리스트를 코드에 맞춘다. |
| I-21 | Fragile | `config.sh` L48; `CLAUDE.md` L137 | variant ID가 좌표를 포함한 array ID이며, 그 좌표는 아마도 **hg38**이다(hg19 `GENPOS`와 33,912 bp 차이) *(verify)*. `CLAUDE.md`는 `{chr}:{pos}:{ref}:{alt}` ID를 제안하지만, peak 표에는 ID가 표시되지 않는다. | import 시 ID를 정규화하고(`plink2 --set-all-var-ids @:#:$r:$a`), peak 표에 ID를 표시한다. |
| I-22 | Doc | `1-3_merge_pc.py` L4; `3-1_qt_step2.sh` L3–5 | 주석이 예전 스크립트 파일명(`3-1_qt_step1.sh`, `4-1_qt_step2.sh`)을 가리킨다. | 갱신한다. |
| I-23 | Fragile | `2-1` / `2-2` L17 | 둘 다 `--lowmem-prefix …/tmp_preds`를 사용하므로 동시에 실행하면 충돌할 수 있다. | prefix에 표현형을 포함한다. |
| I-24 | Fragile *(verify)* | `2-1` L18 | `pred.list`가 `.loco`의 절대 경로를 저장하므로, step 1과 step 2 사이에 프로젝트를 옮기면 step 2가 깨진다. | 다시 생성하거나, 이동 시 경로를 다시 쓴다. |
| I-25 | Bug (minor) | `03_plot.py` L54, L57 | 정규식 `[\d.]+`는 음수나 지수 표기 값을 놓치며, h²가 조용히 제목에서 빠진다. | `[-+\d.eE]+`. |
| I-26 | Fragile *(verify)* | `02_plot.py` L72 | genetic map을 `sep='\t'`로 읽는다. 파일이 공백 구분이면 recombination 트랙이 조용히 사라진다. | `sep=r'\s+'`. |
| I-27 | Science | `02_susie.R` L47 | `min_abs_corr=0.1`(기본값 0.5)은 purity가 낮은 CS를 유지하므로 더 많은 CS가 보고된다. | 기본값을 사용하거나 purity를 함께 보고한다. |
| I-28 | Fragile | `05_susie` 출력; `04` `.vcor` | 출력 파일 이름이 염색체만으로 정해지므로(`chr{C}_…`), 같은 염색체의 두 번째 표현형이나 locus가 이를 덮어쓴다. | 이름에 표현형과 위치를 포함한다. |

기타 사소한 항목:
- `02_ldsc.sh`가 `PHENO=PHENO_QT`를 하드코딩한다.
- `3-2`에는 `3-1`에 있는 염색체별 실행 옵션이 없다.
- `02_plot.py`에는 사용하지 않는 import(`mpatches`)와 사용하지 않는 변수(`y_range`)가 있고, `gs`가 두 가지 용도로 재사용되며, 주석에는 "min 5pt"라고 되어 있으나 코드는 6을 쓴다.
- `03_plot.py`가 `Agg` backend를 설정하지 않는다.
- 유전자 트랙의 strand 화살표가 막대의 위쪽 가장자리에 놓인다.
- CS 레이블 위치가 Python 플롯(가장 높은 −log10 p)과 R PIP 패널(가장 높은 PIP) 사이에서 다르다.
- `prompt.txt` L7에 개행 문자가 빠져 있다.

## B. 현재 "프레임워크"가 의존하는 것 (암묵적 계약)

일반적인 프레임워크라면 명시적으로 만들어야 할 사항들이다.

1. **단계 간 인터페이스로서의 파일 명명 규칙.** 예: `{P}_step2_{P}.regenie`(regenie가 `_{P}`를 덧붙임), `{G}_pruned.prune.in`, `chr{C}_top_ld.vcor`, `chr{C}_susie_ld.unphased.vcor1(.vars)`, 그리고 파일명에서 다시 파싱해 내는 `pheno_name`(`02_susie.R` L14).
2. **config 연결 고리로서의 agent.** Bash는 `config.sh`를 읽지만, Python과 R은 Claude가 입력하는 인자를 통해서만 값을 받는다. 손으로 복사하는 값 하나하나가 불일치(drift)의 원인이 된다(I-5).
3. **주석으로만 존재하는 수작업 전처리**(config.sh L37: FID 추가, ID→IID 이름 변경).
4. **프로젝트 외부의 도구 위치**(`~/ldsc`, `~/miniconda3/envs/ldsc`, `$HOME/bin`)와 하드코딩된 genome build(GRCh37 map, EAS panel, GRCh38 Ensembl endpoint).
5. **산문으로 기술된 human-in-the-loop 결정 지점**: "요청한 단계만 실행한 뒤 묻는다", "peak을 나열하고 사용자가 고르게 한 뒤 config를 수정한다".
6. **강사용 메모로만 존재하는 인수 테스트**(`prompt.txt`: 기대 파일, 기대 lead SNP `11:116662579`, "필요한 것만 설치").

## C. 일반화를 위한 제안

- **단일 typed config**(예: `config.yaml`)에 경로, build(`hg19|hg38`), ancestry panel, 표현형(이름, 유형, 파일), 공변량, 대상 locus, 도구 경로를 담는다. 언어별로 작은 loader를 하나씩 두거나, 이를 CLI 인자로 풀어 넘기는 driver를 두어 어떤 값도 두 번 입력하지 않게 한다.
- **각 단계를 선언된 계약을 가진 단위로 다룬다:** 입력, 출력, 필요한 도구와 리소스, 파라미터. 그러면 `CLAUDE.md`의 "해당 단계에 필요한 도구만 확인"이 agent가 읽을 수 있는 데이터가 되고, runner가 시작 전에 전제 조건(파일 존재, build 일치)을 확인할 수 있다.
- **현재 고정되어 있는 도메인 선택을 파라미터화한다:** build → Ensembl host와 genetic map; ancestry → LDSC panel; 형질 유형 → regenie 플래그(`--qt` vs `--bt --firth --approx`).
- **Claude Code "skill"을 실제 Skill로 전환한다**(`.claude/skills/<name>/SKILL.md`에 description 포함). 그러면 링크 추적에 의존하지 않고 관련 있을 때 로드된다. `CLAUDE.md`는 전역 규칙(단계 게이팅, 보고)용으로 유지한다.
- **`prompt.txt`를 자동화된 검사로 전환한다:** 각 단계마다 반드시 존재해야 하는 파일, sanity 범위(λ_GC 범위, 테스트 데이터셋의 알려진 lead SNP), "불필요한 설치 없음". 이렇게 하면 스크립트뿐 아니라 agent에 대한 회귀 테스트도 얻는다.
- **실패는 즉시 명확하게 드러나게 하고, 이전 실행의 결과물(stale state)을 남기지 않는다:** `set -euo pipefail`; 단계를 재실행하기 전에 해당 단계의 출력을 삭제; 종료 코드 확인(R의 `system()`).
