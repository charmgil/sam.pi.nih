# 줄 단위 해설 — GWAS 에이전트 하네스 (이전 구현)

이 노트는 이 폴더의 모든 스크립트를 **실행 순서대로**, 한 줄(또는 몇 줄 묶음)씩 설명한다. 한국어 주석과 메시지는 영어판에서는 번역했으나, 이 한국어판에서는 원문 그대로 둔다. 읽으면서 발견한 문제는 본문에 **⚠**로 표시하고, ID를 붙여 [90_issues_and_generalization.md](90_issues_and_generalization.md)에 모았다.

| 파일 | 다루는 내용 |
|---|---|
| [00_harness_and_config.md](00_harness_and_config.md) | `prompt.txt`, `CLAUDE.md`, `skill/*.md`(에이전트 계층)와 `script/config.sh` |
| [01_gwas.md](01_gwas.md) | Step 1: `0_vcf_to_pgen.sh` → `1-1` → `1-2` → `1-3_merge_pc.py` → `2-1`/`2-2` (regenie step 1) → `3-1`/`3-2` (regenie step 2) |
| [02_manhattan_qq_plot.md](02_manhattan_qq_plot.md) | Step 2: `plot.py` |
| [03_ldsc.md](03_ldsc.md) | Step 3: `02_ldsc.sh` → `01_input.py` → `munge_sumstats.py` → `ldsc.py`, 이어서 `03_plot.py` |
| [04_regional_plot.md](04_regional_plot.md) | Step 4: peak 목록 코드 조각(`skill/04` 안) → `01_input.sh` → `02_plot.py` |
| [05_susie.md](05_susie.md) | Step 5: `01_input.sh` → `02_susie.R` (내부에서 `04_regional_plot/02_plot.py`를 다시 호출) |
| [90_issues_and_generalization.md](90_issues_and_generalization.md) | 모든 발견 사항(우선순위순)과, 이를 일반 프레임워크로 만들기 위한 메모 |

---

## 1. 이 프로젝트는 무엇인가

프로젝트는 세 계층으로 이루어진다.

1. **에이전트 지시문("하네스").** 이 계층에는 코드가 없다. Claude를 조종하는 텍스트다.
   - `CLAUDE.md`: 이 폴더에서 세션이 시작되면 Claude Code가 자동으로 불러온다. 규칙(요청받은 단계만 실행한다, 그 단계에 필요한 도구만 확인한다)을 명시하고, 단계별 가이드로 링크하며, 참고용 명령 순서를 제시한다.
   - `skill/*.md`: 단계마다 하나씩 있는 가이드와 `resource_downloads.md`. 이들은 **Claude Code Skills가 아니라 일반 Markdown 파일**이다(`SKILL.md`나 frontmatter가 없다). 따라서 Claude는 `CLAUDE.md`의 링크를 따라갈 때에만 이 파일들을 읽는다.
   - `prompt.txt`: 워크숍 강사의 진행 스크립트. 참가자가 입력할 프롬프트와, 각 프롬프트 뒤에 강사가 확인할 사항을 나열한다. 사실상 에이전트에 대한 **수동 인수 테스트(manual acceptance test)** 역할을 한다.
2. **설정.** `script/config.sh`가 모든 경로와 파라미터를 담는다. 각 `.sh` 스크립트가 이를 `source`한다.
3. **작업 스크립트.** Bash 래퍼가 외부 CLI(`plink2`, `regenie`, `ldsc`)를 호출한다. Python과 R 스크립트는 데이터 변환과 플롯을 담당한다.

> **핵심 구조적 사실:** Python과 R 스크립트는 **`config.sh`를 읽지 않는다**. 표현형 이름, lead SNP, window, 샘플 수 같은 값은 명령행 인자로만 전달되며, 이 인자는 Claude(또는 사람)가 `config.sh`와 skill 문서에서 복사해 입력한다. **config와 코드를 잇는 접착제는 Claude다.** issues 파일에 정리한 취약점 대부분이 여기서 비롯된다.

---

## 2. 실행 순서

```
[세션 시작]       CLAUDE.md 자동 로드
[사용자 프롬프트] 예: "HDL GWAS 분석해줘"  →  Claude가 skill/01_gwas.md를 열고, 도구를 확인하고, 필요하면 config.sh를 수정

Step 1  GWAS (skill/01_gwas.md)
  script/config.sh               ← 아래의 모든 .sh가 source함
  01_gwas/0_vcf_to_pgen.sh       (input/에 .bed가 없을 때만)
  01_gwas/1-1_ld_pruning.sh
  01_gwas/1-2_pca.sh
  01_gwas/1-3_merge_pc.py        (표현형마다 한 번)
  01_gwas/2-1_qt_step1.sh   |  2-2_bt_step1.sh     (regenie step 1)
  01_gwas/3-1_qt_step2.sh   |  3-2_bt_step2.sh     (regenie step 2)
      ── 결과 보고, 계속할지 확인 ──
Step 2  02_manhattan_qq_plot/plot.py
Step 3  03_ldsc/02_ldsc.sh  ──► 01_input.py ──► munge_sumstats.py (py2.7) ──► ldsc.py --h2 (py2.7)
        03_ldsc/03_plot.py
Step 4  (skill/04의 peak 목록 Python 코드 조각) → 사용자가 peak 선택 → Claude가 config.sh의 LEAD_* 수정
        04_regional_plot/01_input.sh
        04_regional_plot/02_plot.py
Step 5  05_susie/01_input.sh
        05_susie/02_susie.R ──► (자동으로) 04_regional_plot/02_plot.py --susie-cs
```

## 3. 데이터 흐름 (누가 무엇을 쓰고, 누가 읽는가)

경로는 프로젝트 루트 기준이다. `{G}` = `GENO_NAME`, `{P}` = 표현형(예: `HDL`), `{C}` = `LEAD_CHR`.

| 생성 주체 | 파일 | 읽는 쪽 |
|---|---|---|
| (사용자) 또는 `0_vcf_to_pgen.sh` | `input/{G}.bed/.bim/.fam` 또는 `input/{G}.pgen/.pvar/.psam` | 모든 plink2 / regenie 호출 |
| `1-1_ld_pruning.sh` | `output/01_gwas/pca/{G}_pruned.prune.in` | `1-2`, `2-1`, `2-2` |
| `1-2_pca.sh` | `output/01_gwas/pca/{G}_pca.eigenvec` | `1-3_merge_pc.py` |
| `1-3_merge_pc.py` | `input/{P}_with_pc.txt` (이름은 `--out`으로 지정) | `2-x`, `3-x` (config.sh의 `PHENO_QT_FILE` / `PHENO_BT_FILE`을 통해) ⚠ 이름 관례로만 맞춰짐 |
| `2-1_qt_step1.sh` | `output/01_gwas/step1/{P}_step1_pred.list`, `{P}_step1_1.loco` | `3-1_qt_step2.sh` |
| `3-1_qt_step2.sh` | `output/01_gwas/step2/{P}_step2_{P}.regenie` | `plot.py`, `01_input.py`, `02_plot.py`, `02_susie.R`, skill/04 코드 조각 |
| `01_input.py` | `output/03_ldsc/{P}_for_munge.tsv` | `munge_sumstats.py` |
| `munge_sumstats.py` | `output/03_ldsc/{P}_munged.sumstats.gz` | `ldsc.py`, `03_plot.py` |
| `ldsc.py` | `output/03_ldsc/{P}_h2.log` | `03_plot.py` (선택 인자 `--h2-log`) |
| `04_regional_plot/01_input.sh` | `output/04_regional_plot/chr{C}_top_ld.vcor` | `02_plot.py`, `02_susie.R` (자동 오버레이 호출용) |
| `05_susie/01_input.sh` | `output/05_susie/chr{C}_susie_ld.unphased.vcor1` + `.vars` | `02_susie.R` |
| `02_susie.R` | `chr{C}_susie_pip.tsv`, `chr{C}_susie_cs.tsv`, `chr{C}_susie.png` | `02_plot.py --susie-cs` |

## 4. 전반에 쓰이는 관용구 (여기서 한 번만 설명)

- **`source "$(dirname "$0")/../config.sh"`**: `$0`은 스크립트를 시작할 때 쓴 경로다(예: `script/01_gwas/1-1_ld_pruning.sh`). `dirname`이 파일명을 떼어 내고, `/../config.sh`로 한 단계 위로 올라간다. `source`는 config.sh를 **현재 셸 안에서** 실행하므로, 그 변수들이 스크립트에서 보이게 된다. 이 방식은 스크립트를 `bash script/...`로 시작할 때만 동작한다(`sh`로 실행하면 왜 깨지는지는 config.sh 설명 참고).
- **따옴표 없는 `${GENO_FLAG_PLINK}` / `${GENO_FLAG_REGENIE}` / `${N_THREADS}`**: 값이 하나의 플래그 단어가 되도록 일부러 따옴표를 붙이지 않았다. 경로는 항상 따옴표로 감싼다(`"${GENO_PREFIX}"`). 프로젝트 경로에 공백(`External NVMe`)이 있기 때문이다.
- **`sys.stdout.buffer.write(f"...".encode("utf-8"))`**: 콘솔의 텍스트 인코딩을 거치지 않고 UTF-8 바이트를 stdout에 직접 쓴다. cp949를 쓰는 Windows 콘솔에서 한국어나 그리스 문자(λ, ², →)가 `UnicodeEncodeError`를 일으키지 않게 하기 위함이다. 워크숍에는 Windows 트랙이 있었다(`prompt.txt`).
- **`matplotlib.use('Agg')`**: GUI가 없는 backend로, 디스플레이가 없는 머신에서도 플롯을 PNG로 렌더링한다.
- **`pd.read_csv(regenie_file, sep=' ')` 뒤의 `df[df['LOG10P'] != 'NA']`**: regenie는 실패한 검정에 문자열 `NA`를 그대로 쓰지만, pandas는 읽는 시점에 이미 `NA`를 `NaN`으로 바꾼다. 따라서 `!= 'NA'`는 float과 문자열을 비교하게 되어 항상 `True`이고, **아무것도 제거하지 않는다**. 임시 환경에서 확인했다: 2행 입력, 2행 출력. NaN 행은 나중에 다른 방식으로 제거되거나 무시된다. 이슈 **I-10** 참고.
