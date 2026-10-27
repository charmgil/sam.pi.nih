# 02 — Step 2: Manhattan & QQ plot (`script/02_manhattan_qq_plot/plot.py`)

실행 방법(`skill/02_manhattan_qq_plot.md`에서 발췌):
```bash
python3 script/02_manhattan_qq_plot/plot.py \
  --gwas output/01_gwas/step2/HDL_step2_HDL.regenie --out output/02_manhattan_qq_plot --prefix HDL
```

## 배경
- **Manhattan plot**: x = 유전체 위치(염색체를 끝에서 끝으로 이어 붙임), y = −log10(p)이다. 수평선은 genome-wide significance(5×10⁻⁸)와 "suggestive" 수준(1×10⁻⁵)을 표시한다.
- **QQ plot**: 정렬된 관측 −log10(p)를 귀무가설(균일 분포 p) 하에서 기대되는 값에 대해 그린다. 음영 띠는 각 order statistic의 95 % CI이다. n개의 균일 p-value 중 i번째로 작은 값에 대해, 이 통계량은 Beta(i, n−i+1)를 따른다.
- **λ_GC**(genomic inflation factor) = median(관측 χ²₁) / median(귀무가설 하 χ²₁, ≈ 0.4549). 1에 가까우면 inflation이 거의 없다는 뜻이다. 대규모 표본의 polygenic 형질에서는 confounding이 없어도 λ가 1보다 다소 큰 것이 예상된다.

---

## 줄 단위 해설

```python
1  import argparse
2  import pandas as pd
3  import numpy as np
4  import matplotlib
5  matplotlib.use('Agg')
6  import matplotlib.pyplot as plt
7  from scipy import stats
```
임포트 부분이다. L5는 headless backend를 선택하며, `pyplot`을 임포트하기 **전에** 실행되어야 한다. `scipy.stats`는 χ²와 Beta 분위수 함수를 제공한다.

```python
9  parser = argparse.ArgumentParser()
10 parser.add_argument('--gwas',   required=True, help='regenie step2 결과 파일 (.regenie)')
11 parser.add_argument('--out',    required=True, help='출력 디렉토리')
12 parser.add_argument('--prefix', required=True, help='출력 파일 prefix (예: HDL)')
13 args = parser.parse_args()
15 import os; os.makedirs(args.out, exist_ok=True)
```
명령줄 인터페이스이며, 출력 폴더가 없으면 생성한다.

```python
17 # ── 데이터 로드
18 df = pd.read_csv(args.gwas, sep=' ')
19 df = df[df['LOG10P'] != 'NA'].copy()
20 df['LOG10P'] = df['LOG10P'].astype(float)
21 df['P'] = 10 ** (-df['LOG10P'])
22 df = df.sort_values(['CHROM', 'GENPOS'])
```
- L18: 공백 구분 regenie 출력을 읽는다.
- L19: 실패한 검정을 제거하려는 의도이지만 **no-op**이다(README §4, **I-10**). `NA`는 이미 `NaN`으로 변환되어 있다. `.copy()`는 pandas의 SettingWithCopy 경고를 피하기 위한 것이다.
- L20: 컬럼이 float임을 보장한다(이미 float이다).
- L21: 원래의 p-value로 되돌린다. ⚠ double은 약 1e-308 아래로 내려갈 수 없으므로, `LOG10P` > ~308인 variant는 **P = 0.0**이 된다(테스트 결과: `10**-400 → 0.0`). 이 점들은 L61에서 QQ plot에서 빠진다(**I-7**). Manhattan plot은 `LOG10P`를 사용하므로 영향이 없다.
- L22: 염색체, 그다음 위치 순으로 정렬한다. `CHROM`은 숫자형이며, regenie는 X를 23으로 코딩한다.

```python
28 chrom_sizes = df.groupby('CHROM')['GENPOS'].max().reset_index()
29 chrom_sizes.columns = ['CHROM', 'MAX_POS']
30 chrom_sizes = chrom_sizes.sort_values('CHROM')
31 chrom_sizes['OFFSET'] = [0] + list(chrom_sizes['MAX_POS'].cumsum()[:-1])
32 cum_map = dict(zip(chrom_sizes['CHROM'], chrom_sizes['OFFSET']))
33 df['CUMPOS'] = df['GENPOS'] + df['CHROM'].map(cum_map)
```
전장 유전체에 걸친 단일 x축을 만든다.
- L28–29: 각 염색체에서 관측된 최대 위치(염색체 길이의 대용치).
- L31: 각 염색체의 **offset**은 앞선 모든 염색체 길이의 합이다. `cumsum()[:-1]`은 마지막 값을 제외한 누적합을 주고, `[0]`은 염색체 1에 해당하는 0을 추가한다. 따라서 chr1은 0에서, chr2는 max(chr1)에서 시작하는 식이다.
- L32–33: `CUMPOS` = 염색체 내 위치 + 해당 염색체의 offset.

```python
35 xtick_pos   = df.groupby('CHROM')['CUMPOS'].mean()
36 COLORS = ['#4C72B0', '#DD8452']
```
- L35: 각 염색체의 x-tick은 그 염색체 SNP들의 `CUMPOS` **평균**에 놓인다. 이는 SNP 밀도로 가중된, 대략적인 중심이다.
- L36: 번갈아 쓰는 두 가지 색(파랑, 주황).

```python
38 fig, ax = plt.subplots(figsize=(16, 5))
39 for chrom in sorted(df['CHROM'].unique()):
40     sub = df[df['CHROM'] == chrom]
41     ax.scatter(sub['CUMPOS'], sub['LOG10P'],
42                c=COLORS[int(chrom) % 2], s=4, alpha=0.75, linewidths=0)
```
염색체마다 scatter를 하나씩 그린다. `int(chrom) % 2`는 홀수 염색체에 1(주황), 짝수 염색체에 0(파랑)을 준다. `s=4`는 작은 점을 만들고, `linewidths=0`은 marker 외곽선을 없앤다. NaN인 `LOG10P` 값은 그냥 그려지지 않는다.

```python
44 ax.axhline(-np.log10(5e-8), color='red',  ls='--', lw=0.8, label='p = 5×10⁻⁸')
45 ax.axhline(-np.log10(1e-5), color='blue', ls=':',  lw=0.8, label='p = 1×10⁻⁵')
46 ax.set_xticks(xtick_pos.values)
47 ax.set_xticklabels(xtick_pos.index.astype(str), fontsize=7)
48 ax.set_xlabel('Chromosome')
49 ax.set_ylabel('-log₁₀(P)')
50 ax.set_title(f'{args.prefix} Manhattan Plot')
51 ax.legend(fontsize=8)
52 plt.tight_layout()
53 plt.savefig(f'{args.out}/{args.prefix}_manhattan.png', dpi=180)
54 plt.close()
```
유의성 기준선(y ≈ 7.30 및 5.00), 염색체 tick 레이블, 축 제목, 범례(레이블이 있는 것은 두 선뿐)를 그린 뒤 180 dpi로 저장한다: **`{prefix}_manhattan.png`**. `plt.close()`는 figure를 해제한다.

```python
60 pvals = df['P'].values
61 pvals = pvals[pvals > 0]
62 n = len(pvals)
```
p-value를 NumPy 배열로 가져온다. `> 0`은 **NaN**을 제거하며(`NaN > 0`은 False이므로), 실패한 검정을 실제로 제거하는 것은 이 부분이다. L21에서 생긴 **underflow된 0**도 함께 제거한다(**I-7**).

```python
64 obs = -np.log10(np.sort(pvals))          # 오름차순 정렬 → 작은 p가 뒤
65 exp = -np.log10(np.arange(1, n+1) / n)
```
- L64: 오름차순 정렬 후에는 **가장 작은 p가 맨 앞에 오므로**, `obs`는 큰 값에서 작은 값 순으로 나열된다. ⚠ 주석의 "작은 p가 뒤"는 p 기준으로는 거꾸로이다(`obs` 기준으로는 맞다). 코드는 올바르다.
- L65: i = 1..n에 대한 기대 분위수 i/n이며, 역시 −log10 기준으로 큰 값에서 작은 값 순이다. 따라서 `obs[k]`는 `exp[k]`와 짝을 이루어, k번째로 유의한 값이 k번째 기대값과 대응한다. `(i−0.5)/n`도 흔히 쓰인다는 점에 유의한다. `i/n`을 쓰면 마지막 기대값은 정확히 0이다.

```python
67 chi2_obs = stats.chi2.ppf(1 - pvals, df=1)
68 lam_gc   = np.median(chi2_obs) / stats.chi2.ppf(0.5, df=1)
```
각 p를 자유도 1의 χ² 값으로 변환하고(inverse survival function), λ_GC = median / 0.4549를 계산한다. `1 - p`는 아주 작은 p에서 정밀도를 잃지만 median에는 영향을 주지 않는다. regenie 자체의 `CHISQ` 컬럼을 대신 사용할 수도 있었다.

```python
70 ranks = np.arange(1, n+1)
71 ci_upper = -np.log10(stats.beta.ppf(0.025, ranks, n - ranks + 1))
72 ci_lower = -np.log10(stats.beta.ppf(0.975, ranks, n - ranks + 1))
```
각 order statistic에 대한 95 % 띠이다. i번째로 작은 균일 p는 Beta(i, n−i+1)를 따른다. p의 2.5 % 분위수가 −log10의 **상한**을, 97.5 % 분위수가 하한을 준다. (skill 문서는 이를 "binomial"이라고 부르지만, 실제로는 Beta order-statistic 띠이다.) 분위수 함수를 n번 호출하므로 느리지만, 수백만 SNP 정도는 감당할 수 있다.

```python
74 fig, ax = plt.subplots(figsize=(6, 6))
75 ax.fill_between(exp, ci_lower, ci_upper, alpha=0.2, color='grey', label='95% CI')
76 ax.plot([0, exp.max()], [0, exp.max()], 'r--', lw=0.8)
77 ax.scatter(exp, obs, c='#4C72B0', s=6, linewidths=0)
78 ax.set_xlabel('Expected -log₁₀(P)')
79 ax.set_ylabel('Observed -log₁₀(P)')
80 ax.set_title(f'{args.prefix} QQ Plot  (λ_GC = {lam_gc:.3f})')
81 ax.legend(fontsize=8)
82 plt.tight_layout()
83 plt.savefig(f'{args.out}/{args.prefix}_qq.png', dpi=180)
84 plt.close()
```
정사각형 figure에 회색 CI 띠, 빨간 점선의 y = x 기준선, 관측 점을 그리고, 제목에 λ_GC를 넣는다. 저장 파일명: **`{prefix}_qq.png`**.

```python
86 import sys
87 sys.stdout.buffer.write(f'lambda_GC = {lam_gc:.4f}\n'.encode('utf-8'))
88 sys.stdout.buffer.write(f'Done: {args.out}/{args.prefix}_manhattan.png / _qq.png\n'.encode('utf-8'))
```
λ_GC와 출력 경로를 출력한다(UTF-8 안전).

**출력:** `output/02_manhattan_qq_plot/{prefix}_manhattan.png` 및 `{prefix}_qq.png`.
