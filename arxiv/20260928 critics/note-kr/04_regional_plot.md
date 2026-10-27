# 04 — Step 4: Regional association plot (`script/04_regional_plot/`)

실행 순서:
1. **peak 목록 snippet**(`skill/04_regional_plot.md` 안의 인라인 Python). Claude가 이를 실행하고 표를 보여 준다.
2. **사용자가 peak를 고른다.** 그러면 Claude가 `config.sh`의 `LEAD_CHR`, `LEAD_POS`, `LEAD_SNP`, `WINDOW`를 수정한다.
3. `01_input.sh`: lead SNP와 window 내 모든 SNP 사이의 LD를 plink2로 계산한다.
4. `02_plot.py`: LocusZoom 스타일 그림을 그린다.

## 배경
- **regional plot**은 lead SNP 주변 ±500 kb를 확대해 보여 준다. 각 점은 SNP(x = 위치, y = −log10 p)이며 **lead SNP와의 LD r²**로 색을 칠하므로, 어떤 신호들이 같은 association인지 알 수 있다.
- **recombination rate** 트랙(cM/Mb, genetic map에서 계산)은 hotspot을 보여 주며, hotspot은 대개 LD block의 경계를 나타낸다.
- **gene track**은 peak 아래에 어떤 유전자가 있는지 보여 준다.

---

## 4.0 peak 목록 snippet (`skill/04_regional_plot.md`에서 발췌)

```python
import pandas as pd, numpy as np
gwas = pd.read_csv('output/01_gwas/step2/{phenotype}_step2_{phenotype}.regenie', sep=' ')
gwas['LOG10P'] = gwas['LOG10P'].astype(float)
sig = gwas[gwas['LOG10P'] >= -np.log10(5e-8)].sort_values('LOG10P', ascending=False)
peaks, used = [], []
for _, row in sig.iterrows():
    if any(abs(row['GENPOS'] - p[1]) < 500000 and row['CHROM'] == p[0] for p in used):
        continue
    peaks.append(row); used.append((row['CHROM'], row['GENPOS']))
df = pd.DataFrame(peaks)[['CHROM','GENPOS','ALLELE0','ALLELE1','LOG10P']].reset_index(drop=True)
df.index += 1; df['P'] = 10**(-df['LOG10P'])
print(df.to_string())
```
- genome-wide significant SNP(LOG10P ≥ 7.301; NaN은 비교 결과가 False이므로 실패한 검정은 빠진다)만 남기고 강한 순으로 정렬한다.
- **탐욕적 거리 기반 clumping:** 목록을 위에서부터 내려가며, 같은 염색체에서 이미 선택된 peak로부터 500 kb 이내인 SNP는 건너뛴다. 남은 각 SNP가 자기 peak의 top SNP가 된다.
- 염색체, 위치, allele, LOG10P, P를 담은 1부터 번호가 매겨진 표를 출력한다.
- 참고: 표에 **`ID` 컬럼이 없는데**, `LEAD_SNP`는 정확한 variant ID여야 한다. Claude가 ID를 따로 찾아야 하므로 `CLAUDE.md`는 `{chr}:{pos}:{ref}:{alt}` 형태를 추정한다. 이 추정은 ID가 그 형식일 때만 맞다(**I-21**).
- 여기서의 clumping은 LD가 아니라 거리만 사용하므로, 500 kb를 살짝 넘게 떨어진 두 peak가 같은 신호일 수 있다.

---

## 4.1 `01_input.sh` — window 내 모든 SNP와 lead SNP의 LD

```bash
1  #!/bin/bash
2  source "$(dirname "$0")/../config.sh"
4  mkdir -p "${OUTPUT}/04_regional_plot"
6  FROM_BP=$(( LEAD_POS - WINDOW ))
7  TO_BP=$(( LEAD_POS + WINDOW ))
```
Bash 정수 산술로 window 경계를 구한다. ⚠ `LEAD_POS < WINDOW`이면(염색체 시작 부근의 SNP) `FROM_BP`가 음수가 되어 plink2가 이를 거부한다.

```bash
9   plink2 \
10    ${GENO_FLAG_PLINK} "${GENO_PREFIX}" \
11    --chr ${LEAD_CHR} \
12    --from-bp ${FROM_BP} \
13    --to-bp   ${TO_BP} \
14    --r2-unphased \
15    --ld-snp  "${LEAD_SNP}" \
16    --ld-window 99999 \
17    --ld-window-kb $(( WINDOW / 500 )) \
18    --ld-window-r2 0 \
19    --out "${OUTPUT}/04_regional_plot/chr${LEAD_CHR}_top_ld" \
20    --threads ${N_THREADS}
```
- L11–13: 영역(염색체와 bp 범위)으로 제한한다.
- L14 `--r2-unphased`: unphased r²(phasing을 가정하지 않고 genotype에서 계산)를 계산한다. 결과는 `.vcor` 테이블로 기록된다.
- L15 `--ld-snp ID`: **이 variant가 포함된** 쌍만 보고한다. ID가 bim/pvar와 정확히 일치해야 하므로 `LEAD_SNP`를 따옴표로 감싼다(`|`가 들어 있다).
- L16 `--ld-window 99999`: variant 개수로 센 최대 허용 거리로, 사실상 무제한이다.
- L17 `--ld-window-kb $((WINDOW/500))` = 500000/500 = **1000 kb**로, kb 단위의 최대 거리다. 가장 먼 SNP도 lead로부터 `WINDOW`(500 kb) 떨어져 있으므로 1000 kb면 모두 포함되며, 500이어도 충분하다. "kb 단위 window의 두 배"로서 동작은 하지만 식이 어색하게 읽힌다.
- L18 `--ld-window-r2 0`: r² ≈ 0인 쌍까지 **모든** 쌍을 보고한다. plink 기본값은 r² ≥ 0.2만 보고하므로, 그대로 두면 LD가 낮은 SNP에 색이 없게 된다.
- L19 출력: **`chr{C}_top_ld.vcor`**, 컬럼은 `#CHROM_A POS_A ID_A CHROM_B POS_B ID_B UNPHASED_R2`(탭 구분).
- genotype은 **in-sample**(GWAS와 같은 개인들)이며, 이는 best practice다.

---

## 4.2 `02_plot.py` — 그림

호출 방법:
```bash
python3 script/04_regional_plot/02_plot.py --gwas output/01_gwas/step2/HDL_step2_HDL.regenie \
  --ld output/04_regional_plot/chr11_top_ld.vcor --lead "<exact ID>" --chr 11 --pos 116662579 \
  --window 500000 --out output/04_regional_plot --prefix HDL [--no-gene] [--susie-cs FILE]
```
⚠ `--chr`, `--pos`, `--window`, `--lead`는 **손으로 입력**하며, `01_input.sh`가 사용한 `config.sh`와 일치해야 한다. 이를 확인하는 장치는 없다(**I-5**).

```python
1  import argparse
2  import pandas as pd
3  import numpy as np
4  import matplotlib
5  matplotlib.use('Agg')
6  import matplotlib.pyplot as plt
7  import matplotlib.patches as mpatches
8  import requests, sys, os, pathlib
```
import 부분이다. `mpatches`는 **전혀 사용되지 않는다**. `requests`는 Ensembl REST 호출에 필요하며, 표준 라이브러리가 아닌 서드파티 패키지다.

```python
10 parser = argparse.ArgumentParser()
11 parser.add_argument('--gwas',   required=True, help='regenie step2 결과 파일')
12 parser.add_argument('--ld',     required=True, help='plink2 LD 결과 파일 (.vcor)')
13 parser.add_argument('--lead',   required=True, help='Lead SNP ID (예: 11:65461544:G:A)')
14 parser.add_argument('--chr',    required=True, type=int)
15 parser.add_argument('--pos',    required=True, type=int, help='Lead SNP 위치 (bp)')
16 parser.add_argument('--window', default=500000, type=int, help='±window (bp)')
17 parser.add_argument('--out',    required=True, help='출력 디렉토리')
18 parser.add_argument('--prefix', required=True, help='출력 파일 prefix')
19 parser.add_argument('--no-gene', action='store_true', help='유전자 트랙 생략')
20 parser.add_argument('--susie-cs', default=None, help='SuSiE CS tsv 파일 (chr{chr}_susie_cs.tsv)')
21 args = parser.parse_args()
23 os.makedirs(args.out, exist_ok=True)
```
명령줄 인터페이스다. `--no-gene`은 flag로, 지정하면 True가 된다. `--susie-cs`는 SuSiE overlay를 켜고 출력 파일명을 바꾼다.

```python
25 # ── 1. GWAS 결과 로드 & 영역 필터
26 gwas = pd.read_csv(args.gwas, sep=' ')
27 gwas = gwas[gwas['LOG10P'] != 'NA'].copy()
28 gwas['LOG10P'] = gwas['LOG10P'].astype(float)
30 region = gwas[
31     (gwas['CHROM'] == args.chr) &
32     (gwas['GENPOS'] >= args.pos - args.window) &
33     (gwas['GENPOS'] <= args.pos + args.window)
34 ].copy()
```
- ±window만 남기려고 **전체 genome** 결과를 불러온다. 수백만 행짜리 파일에서는 느리지만 단순하다.
- L27은 no-op 필터다(**I-10**). NaN인 점은 그냥 그려지지 않는다.
- L30–34: 대상 염색체의 [pos−window, pos+window] 안에 있는 SNP만 남긴다.

```python
36 # ── 2. LD 로드 → lead SNP 기준 r² 딕셔너리
37 ld = pd.read_csv(args.ld, sep='\t')
38 r2_dict = {}
39 for _, row in ld.iterrows():
40     if row['ID_A'] == args.lead:
41         r2_dict[row['ID_B']] = row['UNPHASED_R2']
42     elif row['ID_B'] == args.lead:
43         r2_dict[row['ID_A']] = row['UNPHASED_R2']
44 r2_dict[args.lead] = 1.0
45 region['R2'] = region['ID'].map(r2_dict)
```
- `{다른_SNP_ID: lead와의 r²}`를 만든다. lead가 쌍의 어느 컬럼에든 나올 수 있으므로 두 분기가 모두 필요하다. L44는 lead 자신의 r²를 1로 설정한다.
- L45: 각 SNP의 r²를 **ID**로 조회한다. 항목이 없는 SNP는 **NaN**이 된다.
- ⚠ **r²가 NaN인 SNP는 절대 그려지지 않는다**(L122–125 참조). NaN에 해당하는 색 구간이 없기 때문이다. LocusZoom이라면 회색으로 표시한다. `--lead`가 `01_input.sh`에서 쓴 ID와 다르면 거의 모든 SNP가 플롯에서 사라진다. `02_susie.R`이 이 상황을 일으킬 수 있다(**I-4**).

```python
47 # ── 3. Ensembl REST API로 유전자 정보 조회
48 def fetch_genes(chrom, start, end):
49     url = (f"https://rest.ensembl.org/overlap/region/human/"
50            f"{chrom}:{start}-{end}?feature=gene&content-type=application/json")
51     try:
52         r = requests.get(url, timeout=15)
53         if r.status_code == 200:
54             genes = r.json()
55             # protein_coding 유전자만
56             return [g for g in genes if g.get('biotype') == 'protein_coding']
57     except Exception as e:
58         sys.stderr.write(f"유전자 조회 실패: {e}\n")
59     return []
```
- 영역과 겹치는 모든 유전자를 Ensembl에 요청한다. 결과는 `start`, `end`, `strand`, `external_name`, `gene_id`, `biotype` 등을 가진 dict들의 JSON 리스트다. protein-coding 유전자만 남긴다.
- 어떤 실패든(네트워크 오류, timeout, 200이 아닌 status) 빈 리스트를 반환하며, 그러면 유전자 없이 플롯이 그려진다.
- ⚠ **`rest.ensembl.org`는 GRCh38 좌표를 쓰지만 이 분석은 GRCh37/hg19다.** 유전자가 엉뚱한 구간에 대해 반환되고 **hg19 축 위에 hg38 위치로 그려진다**. 워크숍 locus(chr11:116.66 Mb, *APOA5*)에서는 GRCh38 좌표가 약 129 kb 더 크므로 유전자가 대략 그만큼 밀려 보인다. hg19에는 `https://grch37.rest.ensembl.org`를 써야 한다(**I-1**).

```python
61 from_bp = args.pos - args.window
62 to_bp   = args.pos + args.window
```
bp 단위 window 경계를 Python 변수로 둔다.

```python
64 # ── 4. Beagle GRCh37 genetic map에서 recombination rate (cM/Mb) 계산
65 def fetch_recomb(chrom, start, end):
66     script_dir = pathlib.Path(__file__).parent.parent.parent  # GWAS 루트
67     map_file = script_dir / 'resource' / 'genetic_map' / f'plink.chr{chrom}.GRCh37.map'
68     if not map_file.exists():
69         sys.stderr.write(f"genetic map 없음: {map_file}\n")
70         return None, None
```
- L66: 프로젝트 루트를 **이 스크립트 자신의 위치**에서 찾는다(3단계 위로: `02_plot.py` → `04_regional_plot` → `script` → 루트). config.sh의 `GWAS_DIR`, `02_susie.R`의 CWD 기준 상대 경로에 이은 세 번째 리소스 위치 결정 방식이다.
- L67: build가 **GRCh37로 하드코딩**되어 있다.
- map 파일이 없으면 함수는 (None, None)을 반환하고, 플롯에 recombination 선이 없다.

```python
71     try:
72         gmap = pd.read_csv(map_file, sep='\t', header=None, names=['chrom','id','cM','bp'])
73         reg = gmap[(gmap['bp'] >= start - 200000) & (gmap['bp'] <= end + 200000)].copy()
74         if len(reg) < 2:
75             return None, None
76         reg = reg.sort_values('bp').reset_index(drop=True)
77         pos_mid = (reg['bp'].values[:-1] + reg['bp'].values[1:]) / 2
78         dcm  = np.diff(reg['cM'].values)
79         dbp  = np.diff(reg['bp'].values)
80         rate = np.where(dbp > 0, dcm / (dbp / 1e6), 0)
81         mask = (pos_mid >= start) & (pos_mid <= end)
82         return pos_mid[mask] / 1e6, rate[mask]
83     except Exception as e:
84         sys.stderr.write(f"recombination rate 계산 실패: {e}\n")
85         return None, None
```
- L72: PLINK 형식 map은 염색체, ID, genetic position(cM), physical position(bp)의 4컬럼이다. ⚠ 코드는 **탭** 구분을 가정한다. 파일이 공백 구분이면 모든 값이 한 컬럼에 들어가 `bp` 필터에 아무것도 걸리지 않고, recombination 트랙이 **조용히 사라진다**. `sep=r'\s+'`이면 둘 다 처리된다(**I-26**; 실제 파일을 확인할 것).
- L73: window에 200 kb 여유를 더한 범위의 map point를 남겨, 경계에도 이웃 점이 있게 한다.
- L77–80: 이웃한 map point 쌍마다 rate = ΔcM / ΔMb를 구해 두 점의 중간 위치에 둔다. Δbp = 0인 곳은 `np.where`가 0을 반환한다. 그래도 그곳에서 나눗셈은 계산되므로 divide-by-zero 경고가 출력될 수 있지만, 그 값은 버려진다.
- L81–82: window 안의 중간점만 남기고 x를 **Mb** 단위로 반환한다.

```python
87 recomb_pos, recomb_rate = fetch_recomb(args.chr, from_bp, to_bp)
89 # ── SuSiE CS 로드
90 susie_cs = None
91 if args.susie_cs:
92     try:
93         susie_cs = pd.read_csv(args.susie_cs, sep='\t')  # CS, ID 컬럼
94     except Exception as e:
95         sys.stderr.write(f'SuSiE CS 로드 실패: {e}\n')
97 genes = [] if args.no_gene else fetch_genes(args.chr, from_bp, to_bp)
98 has_genes = len(genes) > 0
```
로더들을 실행한다. CS 파일(`02_susie.R`에서 생성)은 `CS`(`L1`, `L2`, …)와 `ID` 컬럼을 가진다. `has_genes`가 그림 레이아웃을 결정한다.

```python
100 # ── 4. 플롯
101 r2_bins = [
102     (0.8, 1.01, '#E41A1C', '0.8 ≤ r²'),
103     (0.6, 0.8,  '#FF7F00', '0.6 ≤ r² < 0.8'),
104     (0.4, 0.6,  '#4DAF4A', '0.4 ≤ r² < 0.6'),
105     (0.2, 0.4,  '#377EB8', '0.2 ≤ r² < 0.4'),
106     (0.0, 0.2,  '#A6CEE3', 'r² < 0.2'),
107 ]
```
LocusZoom 스타일 색 구간(빨강, 주황, 초록, 파랑, 하늘색)을 (하한, 상한, 색, 범례 라벨)로 정의한다. 최상위 구간의 상한을 1.01로 두어 r² = 1.0이 반열린 구간 안에 들어가게 한다.

```python
109 if has_genes:
110     from matplotlib.gridspec import GridSpec
111     fig = plt.figure(figsize=(10, 7))
112     gs = GridSpec(2, 1, height_ratios=[4, 1], hspace=0.03)
113     ax      = fig.add_subplot(gs[0])
114     ax_gene = fig.add_subplot(gs[1])
115 else:
116     fig, ax = plt.subplots(figsize=(10, 5))
117     ax_gene = None
119 xlim = (from_bp / 1e6, to_bp / 1e6)
```
유전자가 있으면 위아래로 쌓인 두 패널로, 위는 association(4 비율), 아래는 유전자(1 비율)다. 유전자가 없으면 단일 패널이다. x 범위는 Mb 단위다.

```python
121 # Association panel
122 for r2_min, r2_max, color, label in r2_bins:
123     sub = region[region['R2'].between(r2_min, r2_max, inclusive='left')]
124     ax.scatter(sub['GENPOS'] / 1e6, sub['LOG10P'],
125                c=color, s=15, label=label, linewidths=0, zorder=2)
```
r² 구간마다 반열린 구간 [min, max)에 대해 scatter를 한 번씩 그린다(테스트 결과: 0.8은 0.6 구간이 아니라 0.8 구간에 들어가고, NaN은 어디에도 들어가지 않는다). 호출마다 범례 항목이 하나씩 추가된다. `inclusive='left'`는 **pandas ≥ 1.3**이 필요하다(**I-19**).

```python
127 lead_row = region[region['ID'] == args.lead]
128 if not lead_row.empty:
129     ax.scatter(lead_row['GENPOS'].values / 1e6, lead_row['LOG10P'].values,
130                marker='D', c='red', s=60, zorder=3)
```
lead SNP를 더 큰 빨간 **다이아몬드**로 맨 위에 그린다. ID가 영역에 없으면 경고 없이 아무것도 그리지 않는다.

```python
132 # SuSiE CS 오버레이
133 if susie_cs is not None:
134     cs_labels = susie_cs['CS'].unique()
135     for cs_name in sorted(cs_labels):
136         cs_ids  = susie_cs[susie_cs['CS'] == cs_name]['ID'].values
137         cs_rows = region[region['ID'].isin(cs_ids)]
138         if cs_rows.empty:
139             continue
140         ax.scatter(cs_rows['GENPOS'] / 1e6, cs_rows['LOG10P'],
141                    facecolors='none', edgecolors='#984EA3', linewidths=1.5, s=60, zorder=4)
142         top = cs_rows.loc[cs_rows['LOG10P'].idxmax()]
143         y_range = region['LOG10P'].max() - region['LOG10P'].min()
144         ax.annotate(cs_name,
145                     xy=(top['GENPOS'] / 1e6, top['LOG10P']),
146                     xytext=(0, 8), textcoords='offset points',
147                     ha='center', va='bottom', fontsize=7, color='#984EA3',
148                     fontweight='bold', clip_on=False)
```
- credible set마다 소속 SNP 주위에 **속이 빈 보라색 원**을 그리고, **−log10 p가 가장 높은** 소속 SNP의 8 point 위에 이름(`L1`, …)을 쓴다.
- ⚠ `sorted()`는 문자열을 비교하므로 `L10`이 `L2`보다 앞에 온다. 그리는 순서에만 영향을 준다.
- `y_range`(L143)는 **계산만 하고 쓰이지 않는다**.
- ⚠ 라벨은 가장 *유의한* 소속 SNP 위에 붙지만, `02_susie.R`은 PIP 패널에서 PIP가 가장 높은 소속 SNP에 라벨을 붙인다. 두 그림이 서로 다른 SNP에 라벨을 붙일 수 있다.

```python
150 ax.axhline(-np.log10(5e-8), color='red', ls='--', lw=0.8)
151 ax.set_ylabel('-log10(P)')
152 ax.set_title(f'{args.prefix}  chr{args.chr}:{args.pos}  ±{args.window//1000}kb')
```
genome-wide significance 선, y축 라벨, 그리고 `HDL  chr11:116662579  ±500kb` 같은 제목.

```python
154 # 레전드: LD r² + CS (있을 때만 추가)
155 handles, labels = ax.get_legend_handles_labels()
156 if susie_cs is not None:
157     cs_patch = plt.Line2D([0], [0], marker='o', color='none',
158                           markerfacecolor='none', markeredgecolor='#984EA3',
159                           markeredgewidth=1.5, markersize=8, label='Credible Set')
160     handles.append(cs_patch)
161     labels.append('Credible Set')
162 ax.legend(handles=handles, labels=labels, title='LD (r²)',
163           fontsize=8, title_fontsize=8, loc='upper left')
164 ax.set_xlim(xlim)
165 ax.tick_params(axis='x', labelbottom=False)
```
- L155: r² 범례 항목 5개를 모은다. lead 다이아몬드는 label이 없으므로 범례에 없다.
- L157–161: 가짜 "Credible Set" 마커(선은 없고 속이 빈 원만 있는 line)를 범례 proxy로 추가한다.
- L164: x 범위를 고정한다.
- L165: 아래 gene 패널이 x tick 라벨을 보여 주므로 위 패널의 **x tick 라벨을 숨긴다**. ⚠ 이 줄은 **gene 패널이 없을 때도 실행되므로**, 유전자 없는 플롯은 L222에서 x축 제목은 받지만 **x축 숫자가 없다**(**I-6**).

```python
167 # 오른쪽 y축: recombination rate
168 if recomb_pos is not None and len(recomb_pos) > 0:
169     ax2 = ax.twinx()
170     ax2.plot(recomb_pos, recomb_rate, color='steelblue', lw=1.2, alpha=0.8)
171     ax2.set_ylabel('Recombination rate (cM/Mb)', color='steelblue', fontsize=9)
172     ax2.tick_params(axis='y', labelcolor='steelblue')
173     ax2.set_ylim(0, max(recomb_rate) * 2.5)
```
`twinx()`는 같은 x를 공유하는 두 번째 y축을 만든다. rate 선은 이 축 기준으로 그린다. ylim을 최댓값의 2.5배로 두어 선이 패널 아래쪽 ~40 %에 머물게 하여 점들을 가리지 않게 한다.

```python
175 # Gene track panel
176 if has_genes:
177     # 겹치는 유전자를 row로 분리
178     rows = []
179     for g in sorted(genes, key=lambda x: x['start']):
180         placed = False
181         for row in rows:
182             if g['start'] / 1e6 > row[-1]['end'] / 1e6 + 0.05:
183                 row.append(g); placed = True; break
184         if not placed:
185             rows.append([g])
```
**탐욕적 interval packing:** 유전자를 시작 위치 순으로 꺼내, 그 row의 마지막 유전자가 끝난 지점보다 **0.05 Mb(50 kb)** 넘게 뒤에서 시작하는 첫 row에 넣는다. 그런 row가 없으면 새 row를 연다. 이 간격은 라벨을 위한 공간이다. (비교 대상은 가장 최근에 배치된 유전자인 `row[-1]`인데, 유전자가 중첩되어 있으면 이것이 항상 가장 오른쪽에서 끝나는 유전자는 아니다. 사소한 packing 결함이다.)

```python
187     n_rows = max(len(rows), 1)
188     # row 수에 따라 폰트·막대 크기 자동 축소 (최소 5pt)
189     font_size  = max(6, 10 - n_rows)
190     bar_height = max(0.2, 0.4 - n_rows * 0.02)
192     ax_gene.set_ylim(-0.8, n_rows + 0.5)
```
row가 늘어남에 따라 글자 크기는 9, 8, 7, 6이 되고 이후 6에 머문다. ⚠ 주석에는 "최소 5pt"라고 되어 있지만 코드의 하한은 **6**이다. 막대 높이는 0.38에서 0.2까지 줄어든다. L192는 row 0 아래에 라벨을 위한 공간을 남긴다.

```python
193     for row_i, row in enumerate(rows):
194         for g in row:
195             gs = g['start'] / 1e6
196             ge = g['end']   / 1e6
197             strand = g.get('strand', 1)
198             name   = g.get('external_name', g.get('gene_id', ''))
```
각 유전자에 대해 Mb 단위 시작·끝(⚠ `gs`라는 이름이 L112의 `GridSpec` 객체를 **가리지만**, 그 객체는 더 이상 쓰이지 않으므로 무해하다), strand(+1 또는 −1), 표시 이름(gene symbol, 없으면 Ensembl ID)을 구한다.

```python
200             # 유전자 몸통
201             ax_gene.barh(row_i, ge - gs, left=gs, height=bar_height,
202                          color='steelblue', alpha=0.7)
203             # 방향 화살표
204             arrow = '→' if strand == 1 else '←'
205             mid = (gs + ge) / 2
206             ax_gene.text(mid, row_i + bar_height / 2, arrow, ha='center',
207                          va='center', fontsize=font_size, color='white')
208             # 유전자 이름 (경계 넘지 않도록 클램핑)
209             xlo, xhi = xlim
210             label_x = max(xlo, min(xhi, mid))
211             ax_gene.text(label_x, row_i - bar_height / 2 - 0.05, name, ha='center',
212                          va='top', fontsize=font_size, style='italic', clip_on=False)
```
- y = row 인덱스 위치에 gene body를 가로 막대로 그린다.
- strand를 흰 화살표로 표시한다. 화살표는 막대 중앙이 아니라 **위쪽 가장자리**(`row_i + bar_height/2`)에 놓이므로 절반쯤 막대 밖으로 나갈 수 있다.
- 기울임꼴 유전자 이름은 막대 바로 아래에 놓인다. x 위치는 보이는 window 안으로 **클램핑**되어, 가장자리 밖으로 삐져나간 유전자도 읽을 수 있는 라벨을 갖는다.

```python
214     ax_gene.set_xlim(xlim)
215     ax_gene.set_yticks([])
216     ax_gene.set_ylabel('Genes', fontsize=9)
217     ax_gene.set_xlabel(f'Chromosome {args.chr} position (Mb)')
218     ax_gene.spines['left'].set_visible(False)
219     ax_gene.spines['right'].set_visible(False)
220     ax_gene.spines['top'].set_visible(False)
221 else:
222     ax.set_xlabel(f'Chromosome {args.chr} position (Mb)')
223     if not args.no_gene:
224         sys.stderr.write("유전자 정보 없음 — 인터넷 연결 확인\n")
```
gene 패널의 스타일을 정한다. x 범위는 같고, y tick은 없으며, 아래쪽 테두리만 남긴다. 유전자가 없으면 x축 라벨은 main 패널에 붙고(그 tick 라벨은 L165에서 숨겨졌다, **I-6** 참조), 일부러 유전자를 끈 경우가 아니면 경고를 출력한다.

```python
226 plt.tight_layout()
227 plt.subplots_adjust(left=0.08, right=0.88, top=0.95, bottom=0.08, hspace=0.25)
228 suffix = '_susie' if args.susie_cs else ''
229 out_path = f'{args.out}/{args.prefix}_chr{args.chr}_regional{suffix}.png'
230 plt.savefig(out_path, dpi=180)
231 plt.close()
232 sys.stdout.buffer.write(f'저장 완료: {out_path}\n'.encode('utf-8'))
```
- L226–227: 자동 레이아웃 후 고정 여백을 적용한다. `right=0.88`은 오른쪽의 recombination rate 라벨을 위한 공간이다. 여기서의 `hspace=0.25`는 GridSpec에 명시적으로 설정된 `hspace=0.03`을 덮어쓰지 **않으므로**(테스트함) 두 패널은 가깝게 붙어 있다. 유전자 없는 레이아웃에서는 패널이 하나뿐이므로 역시 효과가 없다.
- L228–229: 출력 이름은 `{prefix}_chr{C}_regional.png`, overlay가 있으면 `…_regional_susie.png`이다. 폴더는 `--out`으로, 보통은 `output/04_regional_plot`, overlay일 때는 `output/05_susie`다.
