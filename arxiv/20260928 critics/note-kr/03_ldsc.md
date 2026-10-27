# 03 — Step 3: LD Score Regression (`script/03_ldsc/`)

실행 순서: 진입점인 **`02_ldsc.sh`** 가 `01_input.py`(python3) → `munge_sumstats.py`(Python 2.7, 외부) → `ldsc.py --h2`(Python 2.7, 외부)를 차례로 실행한다. **`03_plot.py`** 는 그 뒤에 따로 실행하는 별도 명령이다.

## 배경
- SNP j의 **LD score** ℓⱼ = Σₖ r²ⱼₖ로, 주변 SNP에 대해 합산한 값이다. LD가 높은 영역의 SNP는 더 많은 causal variation을 "tag"한다.
- polygenic 모델에서 **E[χ²ⱼ] ≈ N·h²·ℓⱼ / M + N·a + 1**이다. 따라서 GWAS χ² 통계량을 LD score에 회귀하면 다음을 얻는다.
  - **SNP heritability h²**에 비례하는 **slope**
  - **intercept**: ≈ 1이면 inflation이 polygenicity에서 온 것이고, > 1이면 population stratification 같은 confounding을 시사한다.
- `ldsc`는 **reference population**에 대해 미리 계산된 LD score가 필요하다. 여기서는 한국인 코호트에 맞는 1000 Genomes Phase 3 **EAS**(동아시아인)를 쓰며, HapMap3 SNP로 제한되어 있다.
- SNP는 **rsID로** 매칭한다. regenie는 위치 기반 array ID를 출력하므로 rsID 매핑 단계(`pos2rsid.txt`)가 필요하다.

---

## 3.1 `02_ldsc.sh` — orchestrator

```bash
1  #!/bin/bash
2  source "$(dirname "$0")/../config.sh"
4  PHENO="${PHENO_QT}"          # 분석할 표현형 (QT: PHENO_QT / BT: PHENO_BT)
5  LDSC_DIR="${RESOURCE}/LDSC"
6  MUNGE="${HOME}/ldsc/munge_sumstats.py"
7  LDSC="${HOME}/ldsc/ldsc.py"
8  PY27="${HOME}/miniconda3/envs/ldsc/bin/python"  # ldsc 전용 Python 2.7 환경
10 mkdir -p "${OUTPUT}/03_ldsc"
```
- L4: 표현형이 **QT 표현형으로 하드코딩**되어 있다. T2D를 분석하려면 이 줄을 수정해야 한다.
- L5: reference 폴더(`baseline.*`, weights, `pos2rsid.txt`).
- L6–7: `ldsc` 저장소가 `~/ldsc`에 clone되어 있다고 가정한다(`resource_downloads.md`).
- L8: ldsc는 Python 2 코드이므로 전용 conda env 인터프리터로 실행한다. python3로 실행하면 소스에 탭과 스페이스가 섞여 있어 `TabError`가 난다.
- 이 경로들은 나머지와 달리 **프로젝트 밖**(`$HOME`)에 있으므로 머신마다 다르다.

```bash
12 # ── Step 1: GWAS 결과 → munge_sumstats 입력 형식 변환
13 python3 "$(dirname "$0")/01_input.py" \
14   --gwas     "${OUTPUT}/01_gwas/step2/${PHENO}_step2_${PHENO}.regenie" \
15   --pos2rsid "${LDSC_DIR}/pos2rsid.txt" \
16   --out      "${OUTPUT}/03_ldsc/${PHENO}_for_munge.tsv"
```
변환 스크립트를 호출한다(3.2 참조). 입력 파일명은 **genome-wide** step 2 출력이다.

```bash
18 # ── Step 2: munge_sumstats
19 "${PY27}" "${MUNGE}" \
20   --sumstats "${OUTPUT}/03_ldsc/${PHENO}_for_munge.tsv" \
21   --snp SNP \
22   --a1  A1 \
23   --a2  A2 \
24   --signed-sumstats BETA,0 \
25   --p P \
26   --N-col N \
27   --out "${OUTPUT}/03_ldsc/${PHENO}_munged"
```
`munge_sumstats.py`는 summary statistics를 ldsc 형식 `SNP A1 A2 Z N`으로 표준화한다.
- L21–23: rsID, effect allele, other allele이 들어 있는 컬럼을 지정한다.
- L24 `--signed-sumstats BETA,0`: 효과의 부호를 `BETA`에서 가져오며, 그 null 값은 0이다. munge는 P를 |Z|로 바꾸고 BETA의 부호를 붙인다.
- L25–26: p-value 컬럼과 SNP별 sample size 컬럼.
- `FRQ` 컬럼도 자동으로 인식해 기본 필터를 적용한다. MAF < 0.01인 SNP, strand-ambiguous SNP(A/T, C/G), SNP가 아닌 allele, 중복 rsID, 결측값, 범위를 벗어난 p-value를 제거한다. 인식하지 못하는 `CHISQ` 컬럼은 무시된다.
- ⚠ 흔히 쓰는 `--merge-alleles w_hm3.snplist`를 **사용하지 않는다**. HapMap3 SNP로의 제한과 그에 대한 allele 확인은 암묵적으로만 일어난다. `pos2rsid.txt`에 EAS HM3 SNP만 들어 있는 것으로 보인다(`skill/03_ldsc.md`: "EAS HM3 SNP만 남음"). reference에 대한 allele 확인은 수행하지 않는다(**I-15**).
- 출력: `{P}_munged.sumstats.gz`, `{P}_munged.log`.

```bash
29 # ── Step 3: LD score regression (h²)
30 "${PY27}" "${LDSC}" \
31   --h2 "${OUTPUT}/03_ldsc/${PHENO}_munged.sumstats.gz" \
32   --ref-ld-chr "${LDSC_DIR}/baseline." \
33   --w-ld-chr   "${LDSC_DIR}/1000G_Phase3_EAS_weights_hm3_no_MHC/weights.EAS.hm3_noMHC." \
34   --out "${OUTPUT}/03_ldsc/${PHENO}_h2"
```
- L31 `--h2`: munge된 파일로 SNP heritability를 추정한다.
- L32 `--ref-ld-chr PREFIX`: ldsc가 `1..22`와 `.l2.ldscore.gz`를 붙여(대응하는 `.l2.M_5_50`도 읽는다) `baseline.1.l2.ldscore.gz` … `baseline.22.…`를 불러온다. 22개 염색체가 모두 있어야 한다. 이는 **baseline model v1.2** score(Finucane et al. 2015; 약 50개 functional annotation과 모든 SNP를 포함하는 `base` annotation)로, `1000G_Phase3_EAS_baseline_v1.2_ldscores`에서 온 것이다. multi-annotation 모델로 `--h2`를 돌리면 annotation들을 함께 적합하고 **total** h²를 보고한다. 이는 타당하지만, 더 일반적인 single-annotation "LD score" h²와는 다르다.
- L33 `--w-ld-chr`: regression weight용 LD score(HM3 SNP, MHC 제거).
- L34: `{P}_h2.log`를 쓰며, 여기에 `Total Observed scale h2: X (SE)`, `Lambda GC`, `Mean Chi^2`, `Intercept`, `Ratio`가 들어 있다.
- ⚠ 스크립트에 `set -e`가 없다. step 1이나 2가 실패해도 이후 명령이 오래된 파일이나 없는 파일로 계속 실행된다(**I-16**).

---

## 3.2 `01_input.py` — regenie 결과 → munge 입력

```python
1  import argparse
2  import sys
3  import pandas as pd
5-9  argparse: --gwas (regenie step2 결과 파일), --pos2rsid (pos2rsid.txt 경로), --out (출력 파일 경로 (.tsv))
```

```python
11 gwas = pd.read_csv(args.gwas, sep=' ')
12 gwas = gwas[gwas['CHISQ'] != 'NA'].copy()
13 gwas['CHISQ'] = gwas['CHISQ'].astype(float)
14 gwas['LOG10P'] = gwas['LOG10P'].astype(float)
15 gwas['P'] = 10 ** (-gwas['LOG10P'])
```
- L12: Step 2 `plot.py`와 같은 **no-op 필터**다(**I-10**). NaN 행이 그대로 통과해 **빈 필드**로 기록된다(L33). munge는 공백 기준으로 컬럼을 나누므로 연속된 탭이 하나로 합쳐지고, 남은 값들이 **왼쪽으로 밀려 엉뚱한 컬럼에 들어간다**. 테스트 결과: BETA/CHISQ/P가 빈 행은 `BETA=14000`(N 값)과 P = NaN을 갖게 된다. 이 행은 결국 P와 N이 결측이 되어 munge에서 제거되므로, 최종 결과가 맞는 것은 설계가 아니라 **운**이다(**I-9**, **I-10**).
- L15: 원래의 p로 되돌린다. ⚠ LOG10P > ~308이면 0으로 underflow되고, munge의 p-value 범위 검사(0 < p ≤ 1)가 가장 강한 SNP들을 제거하게 된다(**I-7**). `ldsc`가 어차피 χ² > max(80, 0.001·N)인 SNP를 제거하므로 h²에 대한 영향은 작다.

```python
17 pos2rsid = pd.read_csv(args.pos2rsid, sep='\t', header=None,
18                        names=['CHROM', 'GENPOS', 'SNP'])
19 gwas_rsid = gwas.merge(pos2rsid, on=['CHROM', 'GENPOS'], how='inner')
```
- L17–18: 헤더 없는 3컬럼 조회 테이블(염색체, 위치, rsID)을 읽는다.
- L19: **위치만으로** rsID를 붙인다(inner join). 매칭되지 않은 SNP는 제거되며, 이는 의도된 동작이다. skill/03에 따르면 SNP 수가 HM3 세트 수준으로 줄어든다.
- ⚠ **allele을 무시한다.** 같은 위치의 다른 variant(indel이나 multi-allelic site의 다른 allele 등)도 그 rsID를 받는다. 한 위치에 variant가 둘이면 rsID가 중복되고, munge가 이를 제거한다. `pos2rsid.txt`의 genome build가 GWAS(hg19)와 같아야 한다(**I-15**).

```python
21 sys.stdout.buffer.write(f'total SNPs: {len(gwas):,}  ->  rsID matched: {len(gwas_rsid):,}\n'.encode('utf-8'))
```
매핑 전후의 개수를 출력한다(`:,`는 천 단위 구분 기호를 넣는다).

```python
23 out_df = pd.DataFrame({
24     'SNP':  gwas_rsid['SNP'],
25     'A1':   gwas_rsid['ALLELE1'],
26     'A2':   gwas_rsid['ALLELE0'],
27     'BETA':  gwas_rsid['BETA'],
28     'CHISQ': gwas_rsid['CHISQ'],
29     'P':     gwas_rsid['P'],
30     'N':     gwas_rsid['N'],
31     'FRQ':  gwas_rsid['A1FREQ'],
32 })
33 out_df.to_csv(args.out, sep='\t', index=False)
34 sys.stdout.buffer.write(f'saved: {args.out}\n'.encode('utf-8'))
```
컬럼명을 munge가 기대하는 이름으로 바꾼다. **A1 = regenie `ALLELE1`**(effect allele)이므로 BETA의 부호가 올바르게 정렬된다. `FRQ` = A1의 빈도이며, munge는 이를 MAF 계산에만 쓴다. `{P}_for_munge.tsv`를 쓴다.

---

## 3.3 `03_plot.py` — bin별 LD score 대 χ² 플롯(별도 실행)

```bash
python3 script/03_ldsc/03_plot.py --sumstats output/03_ldsc/HDL_munged.sumstats.gz \
  --ldsc-dir resource/LDSC --out output/03_ldsc --prefix HDL --h2-log output/03_ldsc/HDL_h2.log
```

```python
1  import argparse
2  import gzip
3  import numpy as np
4  import pandas as pd
5  import matplotlib.pyplot as plt
```
⚠ 다른 플롯 스크립트와 달리 `matplotlib.use('Agg')`를 호출하지 **않는다**. 최근 matplotlib은 디스플레이가 없으면 Agg로 fallback하므로 대개는 그래도 동작한다.

```python
7-15 argparse:
  --sumstats  munged sumstats.gz 경로
  --ldsc-dir  baseline LD score 디렉토리 (baseline.{chr}.l2.ldscore.gz 위치)
  --out       출력 디렉토리
  --prefix    출력 파일 접두어 (표현형명)
  --bins      bin 수 (기본값: 100, 원논문 기준)
  --ylim      y축 범위 (기본값: 0.5 1.5) — 실수 2개 (YMIN YMAX)
  --h2-log    ldsc.py --h2 출력 log 파일 경로 (h²_SNP 표기용) — 선택 인자
```

```python
17 # ── 1. sumstats 로드 및 chi-square 계산
18 with gzip.open(args.sumstats, 'rt') as f:
19     sumstats = pd.read_csv(f, sep='\t')
20 sumstats['CHISQ'] = sumstats['Z'] ** 2
```
gzip 파일을 텍스트 모드(`'rt'`)로 열어 `SNP A1 A2 Z N`을 읽는다. χ² = Z²(자유도 1).

```python
22 # ── 2. baseline LD score 로드 (chr1~22)
23 ld_list = []
24 for chrom in range(1, 23):
25     path = f'{args.ldsc_dir}/baseline.{chrom}.l2.ldscore.gz'
26     df = pd.read_csv(path, sep='\t', compression='gzip')
27     ld_list.append(df[['SNP', 'baseL2']])
28 ld = pd.concat(ld_list, ignore_index=True)
```
22개 염색체 파일을 모두 불러와 `SNP`와 `baseL2`만 남긴다. `baseL2`는 baseline 모델에서 모든 SNP를 포함하는 "base" annotation의 LD score로, 보통의 LD score에 해당한다. functional annotation은 여기서 무시된다.

```python
30 merged = sumstats.merge(ld, on='SNP', how='inner')
31 print(f"Merged SNPs: {len(merged):,}")
```
rsID로 join한다. UTF-8 바이트 writer가 아닌 일반 `print`를 쓰지만, 텍스트가 ASCII이므로 문제없다.

```python
33 # ── 3. 백분위수 기반 bin 집계
34 bins = np.percentile(merged['baseL2'], np.linspace(0, 100, args.bins + 1))
35 bins = np.unique(bins)
36 merged['bin'] = pd.cut(merged['baseL2'], bins=bins, include_lowest=True)
37 binned = merged.groupby('bin', observed=True).agg(
38     mean_ld=('baseL2', 'mean'),
39     mean_chisq=('CHISQ', 'mean')
40 ).dropna()
```
- L34: LD score의 0, 1, …, 100 백분위수에 해당하는 101개 경계를 만들어, 각 bin에 SNP의 약 1 %가 들어가게 한다.
- L35: 중복 경계(tie)를 제거한다. `pd.cut`은 중복 경계를 거부하기 때문이다.
- L36: 각 SNP를 bin에 할당한다. `include_lowest`는 최솟값을 포함시킨다.
- L37–40: bin마다 평균 LD score(x)와 평균 χ²(y)를 구한다. `observed=True`는 비어 있는 categorical bin을 건너뛴다. `dropna`는 안전장치다.

```python
42 x = binned['mean_ld'].values
43 y = binned['mean_chisq'].values
44 coeffs = np.polyfit(x, y, 1)
45 slope, intercept = coeffs
```
~100개 bin 평균에 대한 단순 **비가중 최소제곱** 직선이다. 표시용일 뿐이다. 실제 추정치는 개별 SNP에 대한 ldsc의 가중 회귀 결과이며 `.log` 파일에 있다.

```python
47 # ── 4. h² 파싱 (log 파일 제공 시)
48 h2_str = None
49 if args.h2_log:
50     import re
51     h2_val = se_val = lambda_val = None
52     with open(args.h2_log) as f:
53         for line in f:
54             m = re.search(r'Total Observed scale h2:\s*([\d.]+)\s*\(([\d.]+)\)', line)
55             if m:
56                 h2_val, se_val = m.group(1), m.group(2)
57             m2 = re.search(r'Lambda GC:\s*([\d.]+)', line)
58             if m2:
59                 lambda_val = m2.group(1)
60     parts = []
61     if h2_val:
62         parts.append(f"h²_SNP = {h2_val} (SE = {se_val})")
63     if lambda_val:
64         parts.append(f"λ_GC = {lambda_val}")
65     if parts:
66         h2_str = "  |  ".join(parts)
```
ldsc log를 한 줄씩 훑는다. L54는 `Total Observed scale h2: 0.1234 (0.0123)`에서 `h2`와 그 `SE`를 잡는다. L57은 `Lambda GC: 1.05`를 잡는다. 찾은 값은 하나의 부제 문자열로 합쳐지고, 아무것도 못 찾으면 `h2_str`은 `None`으로 남는다. 값은 log에 출력된 그대로 문자열로 유지된다. ⚠ `[\d.]+`는 **마이너스 부호**나 **과학적 표기법**에 매칭되지 않는다. 검정력이 낮을 때 나올 수 있는 음수 h² 추정치나 `1e-04` 같은 값은 조용히 건너뛰어져 제목에서 빠진다(**I-25**).

```python
68 # ── 5. 플롯
69 fig, ax = plt.subplots(figsize=(8, 6))
70 ax.scatter(x, y, s=25, color='steelblue', alpha=0.8, zorder=3)
72 x_range = np.linspace(0, x.max() * 1.05, 300)
73 ax.plot(x_range, slope * x_range + intercept, color='red', linewidth=2,
74         label=f'Slope = {slope:.5f}\nIntercept = {intercept:.4f}')
75 ax.axhline(y=intercept, color='gray', linestyle='--', linewidth=1, alpha=0.6)
77 ax.set_xlim(0, x.max() * 1.05)
78 ax.set_ylim(args.ylim[0], args.ylim[1])
79 ax.set_xlabel('LD Score', fontsize=13)
80 ax.set_ylabel(r'Mean $\chi^2$', fontsize=13)
81 title = f'LD Score Regression ({args.prefix})'
82 if h2_str:
83     title += f'\n{h2_str}'
84 ax.set_title(title, fontsize=13)
85 ax.legend(fontsize=11, loc='upper left')
```
- L70: bin 평균을 점으로 찍는다. `zorder=3`으로 직선 위에 그린다.
- L72–74: 적합 직선을 x = 0부터 가장 큰 bin보다 5 % 더 먼 지점까지 그려 intercept가 보이게 한다. slope와 intercept는 범례에 표시한다.
- L75: intercept 위치에 점선 수평 기준선을 긋는다.
- L80: `$\chi^2$`는 matplotlib mathtext로, χ²로 렌더링된다.
- L81–84: 제목. log를 파싱한 경우 h² / λ 줄을 덧붙인다.
- ⚠ **0.5–1.5로 고정된 y 범위** 때문에 평균 χ²가 1.5를 넘는 bin은 잘린다. 대규모 표본의 고도로 polygenic한 형질에서 일어날 수 있으며, 사용자가 `--ylim`으로 바꿀 수 있다.

```python
87 import os
88 os.makedirs(args.out, exist_ok=True)
89 out_path = f'{args.out}/{args.prefix}_ldsc_regression.png'
90 plt.tight_layout()
91 plt.savefig(out_path, dpi=150)
92 print(f"saved: {out_path}")
```
결과 파일: **`{prefix}_ldsc_regression.png`**

**Step 3의 출력:** `{P}_for_munge.tsv`, `{P}_munged.sumstats.gz`(+ `.log`), `{P}_h2.log`, `{P}_ldsc_regression.png`. 모두 `output/03_ldsc/`에 있다.
