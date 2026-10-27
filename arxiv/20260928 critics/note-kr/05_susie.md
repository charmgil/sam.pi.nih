# 05 — Step 5: SuSiE를 이용한 fine-mapping (`script/05_susie/`)

실행 순서: `01_input.sh` (LD matrix) → `02_susie.R` (fine-mapping, 표, 2-panel 플롯). `02_susie.R`은 마지막에 **`04_regional_plot/02_plot.py`를 직접 호출**하여 SuSiE 오버레이 버전의 regional plot을 그린다.

(`script/05_susie/.Rhistory`는 비어 있는 R 세션 히스토리 파일로, 대화형 R 사용의 잔재이다. 파이프라인의 일부가 아니다.)

## 배경
- **Fine-mapping**은 LD 때문에 여러 SNP가 비슷해 보이는 상황에서, 연관 영역 안의 어떤 SNP가 인과(causal) SNP일 가능성이 가장 높은지를 묻는다.
- **SuSiE**(Sum of Single Effects)는 신호를 최대 **L**개의 single-effect 성분의 합으로 모델링하며, 각 성분은 정확히 하나의 causal SNP를 가진다.
  - 각 성분에 대해 SNP들에 대한 사후분포(posterior distribution)를 제공하고, 이로부터 **95 % credible set (CS)**, 즉 95 % 확률로 causal SNP를 포함하는 가장 작은 SNP 집합을 구한다.
  - **PIP**(posterior inclusion probability, 사후 포함 확률)는 어떤 SNP가 임의의 성분에서 0이 아닌 효과를 가질 확률이다.
  - **Purity**는 CS 구성원 간 절대 상관계수의 최솟값이다. `min_abs_corr` 미만인 CS는 의미 없는 것으로 간주되어 버려진다.
- **SuSiE-RSS**는 개인 수준 데이터 없이 요약통계(β̂와 SE, 또는 z)와 **LD 상관 행렬 R**, 표본 크기 n만으로 실행된다. R과 β̂의 **부호**는 **같은 allele** 기준이어야 하며, R은 가능하면 같은 표본에서 계산한 것(in-sample LD)이어야 한다.

---

## 5.1 `01_input.sh` — 영역의 부호 있는(signed) LD 상관 행렬

```bash
1  #!/bin/bash
2  source "$(dirname "$0")/../config.sh"
4  mkdir -p "${OUTPUT}/05_susie"
6  FROM_BP=$(( LEAD_POS - WINDOW ))
7  TO_BP=$(( LEAD_POS + WINDOW ))
9   plink2 \
10    ${GENO_FLAG_PLINK} "${GENO_PREFIX}" \
11    --chr ${LEAD_CHR} \
12    --from-bp ${FROM_BP} \
13    --to-bp   ${TO_BP} \
14    --r-unphased square \
15    --out "${OUTPUT}/05_susie/chr${LEAD_CHR}_susie_ld" \
16    --threads ${N_THREADS}
```
- L6–13: Step 4와 같은 영역이다(**config의 동일한 `LEAD_POS`와 `WINDOW`**).
- L14 `--r-unphased square`: 영역 내 **모든 variant 쌍** 사이의 **부호 있는 상관계수 r**(r²가 아님)을 완전한 정사각 행렬로 출력한다. SuSiE에는 부호가 필요하다. plink2는 다음을 출력한다.
  - `chr{C}_susie_ld.unphased.vcor1`: n × n 행렬. variant당 한 행이며, 탭으로 구분되고 헤더가 없다.
  - `chr{C}_susie_ld.unphased.vcor1.vars`: 행렬 순서대로 나열된 n개의 variant ID.
- ⚠ **QC 필터가 적용되지 않는다.** 영역 내 monomorphic 또는 거의 monomorphic인 variant는 **NaN** 행과 열을 만든다. 대부분은 이후 `02_susie.R`에서 GWAS ID와 교집합을 취할 때 제거되지만(regenie는 MAC < 5인 variant를 건너뜀), R에 NaN이 있거나 R이 양의 정부호(positive-definite)가 아니면 `susie_rss`가 실패한다.
- 행렬 크기는 variant 수의 제곱에 비례한다. imputed variant 기준 1 Mb 윈도우(대략 3–5 k SNP)라면 수천만 개의 숫자가 텍스트로 저장된다. 이 정도는 괜찮지만, 윈도우가 커지면 빠르게 증가한다.

---

## 5.2 `02_susie.R`

호출:
```bash
Rscript script/05_susie/02_susie.R \
  output/01_gwas/step2/HDL_step2_HDL.regenie output/05_susie/chr11_susie_ld output/05_susie \
  11 116662579 500000 <n_sample>
```
⚠ 섹션 6이 CWD 기준 상대 경로를 사용하므로 **반드시 프로젝트 루트에서 실행해야 한다**(**I-3**). `chr`, `pos`, `window`는 손으로 입력하며 `config.sh`와 일치해야 한다(**I-5**). `n_sample`은 regenie의 `N` 열에서 가져온다.

```r
1  library(susieR)
3  args <- commandArgs(trailingOnly = TRUE)
4  # 사용법: Rscript 02_susie.R <gwas_file> <ld_prefix> <output_dir> <chr> <pos> <window> <n_sample>
5  gwas_file  <- args[1]  # regenie step2 결과 파일
6  ld_prefix  <- args[2]  # plink2 LD 출력 prefix (chr11_susie_ld 등)
7  out_dir    <- args[3]  # 출력 디렉토리
8  lead_chr   <- as.integer(args[4])
9  lead_pos   <- as.integer(args[5])
10 window     <- as.integer(args[6])
11 n_sample   <- as.integer(args[7])
```
susieR를 로드한다. `trailingOnly = TRUE`는 R 자체 인자가 아닌 사용자 인자만 반환한다. 인자는 이름 없이 **위치(positional)** 로만 전달되며 검사도 없다. 순서가 틀리면 조용히 실패하거나 혼란스러운 방식으로 실패한다.

```r
13 # 표현형 이름: gwas 파일명에서 추출
14 pheno_name <- sub('_step2_.*', '', basename(gwas_file))
16 dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)
```
- L14: `_step2_`부터 끝까지를 삭제하여 `HDL_step2_HDL.regenie`를 `HDL`로 만든다. 파일 명명 규칙에 의존한다.
- L16: R에서 `mkdir -p`에 해당한다.

```r
18 # ── 1. GWAS 요약통계 로드 & 영역 필터
19 gwas   <- read.table(gwas_file, header = TRUE, sep = ' ')
20 region <- gwas[
21   gwas$CHROM == lead_chr &
22   gwas$GENPOS >= lead_pos - window &
23   gwas$GENPOS <= lead_pos + window, ]
24 region <- region[order(region$GENPOS), ]
```
regenie 파일 **전체**를 읽고(수백만 행이면 느리다. `data.table::fread`가 더 빠르다), 윈도우 안의 행만 남긴 뒤 위치 순으로 정렬한다. R의 `read.table`은 `NA`를 결측으로 읽는다. ⚠ `BETA`/`SE`가 NA인 행(검정 실패)은 **제거되지 않으며**, 이 경우 `susie_rss`가 실패한다.

```r
26 # ── 2. LD matrix 로드
27 ld_vars <- readLines(paste0(ld_prefix, '.unphased.vcor1.vars'))
28 ld_mat  <- as.matrix(read.table(paste0(ld_prefix, '.unphased.vcor1')))
29 rownames(ld_mat) <- colnames(ld_mat) <- ld_vars
```
variant ID와 행렬을 읽고(`read.table`의 기본 구분자는 임의의 공백이므로 탭도 처리된다), ID로 인덱싱할 수 있도록 행과 열 이름을 variant ID로 지정한다.

```r
31 # GWAS SNP과 LD matrix의 교집합으로 정렬
32 common <- intersect(region$ID, ld_vars)
33 region <- region[region$ID %in% common, ]
34 region <- region[match(common, region$ID), ]
35 ld_mat <- ld_mat[common, common]
```
- L32: 양쪽에 모두 있는 ID를 **`region` 순서**(위치 정렬 순)로 구한다. `intersect`는 첫 번째 인자의 순서를 유지하기 때문이다.
- L33–34: LD 항목이 없는 GWAS 행을 제거한 뒤 `common` 순서로 재정렬한다(순서가 이미 일치하므로 안전 장치에 해당한다).
- L35: 행렬을 같은 ID, 같은 순서로 잘라낸다. 이후로는 **`region`의 i번째 행이 `ld_mat`의 i번째 행/열에 대응한다**.
- ⚠ **중복 ID**(예: `.` 또는 반복되는 array ID)가 있으면 이름 기반 인덱싱이 깨진다. **Allele 정렬(alignment)은 확인하지 않는다.** 코드는 regenie의 `BETA`(`ALLELE1` 기준)와 plink2의 `r`(ALT allele 기준)이 같은 allele을 가리킨다고 가정한다. bed 입력에서는 보통 성립하지만 검증되지 않으며, allele이 뒤집히면 잘못된 CS가 나온다(**I-11**).

```r
37 cat(sprintf('사용 SNP 수: %d\n', nrow(region)))
```

```r
39 # ── 3. SuSiE RSS 실행
40 fit <- susie_rss(
41   bhat     = region$BETA,
42   shat     = region$SE,
43   R        = ld_mat,
44   n        = n_sample,
45   L        = 10,
46   coverage = 0.95,
47   min_abs_corr = 0.1
48 )
```
- `bhat`/`shat`: 효과 추정치와 표준오차. susieR는 내부적으로 이를 z-score로 변환한다.
- `R`: 부호 있는 LD 상관 행렬.
- `n`: GWAS 표본 크기(`N`은 SNP마다 다를 수 있지만 여기서는 단일 값을 쓴다).
- `L = 10`: 최대 10개의 causal 신호.
- `coverage = 0.95`: 95 % credible set.
- `min_abs_corr = 0.1`: purity 임계값. **기본값 0.5보다 훨씬 느슨하다.** 사실상 "이 큰 LD 블록 어딘가"를 뜻하는 purity가 낮은 CS도 유지된다. `skill/05`에서 표본이 작으면 "CS가 너무 많이" 나온다고 적은 이유를 부분적으로 설명한다(**I-27**).

```r
50 # ── 4. 결과 저장
51 pip_df <- data.frame(
52   ID     = region$ID,
53   CHROM  = region$CHROM,
54   GENPOS = region$GENPOS,
55   PIP    = fit$pip
56 )
57 write.table(pip_df,
58   file = file.path(out_dir, paste0('chr', lead_chr, '_susie_pip.tsv')),
59   sep = '\t', row.names = FALSE, quote = FALSE)
```
SNP당 한 행으로 PIP를 담아 **`chr{C}_susie_pip.tsv`** 에 쓴다. 파일 이름에 표현형이 없으므로, 같은 염색체에서 두 번째 형질을 실행하면 **덮어쓴다**(**I-28**).

```r
61 cs_list <- fit$sets$cs
62 if (!is.null(cs_list)) {
63   cs_df <- do.call(rbind, lapply(seq_along(cs_list), function(i) {
64     data.frame(CS = paste0('L', i), ID = region$ID[cs_list[[i]]])
65   }))
66   write.table(cs_df,
67     file = file.path(out_dir, paste0('chr', lead_chr, '_susie_cs.tsv')),
68     sep = '\t', row.names = FALSE, quote = FALSE)
69   cat(sprintf('Credible Set 수: %d\n', length(cs_list)))
70 } else {
71   cat('유의한 Credible Set 없음\n')
72 }
```
- L61: `fit$sets$cs`는 유지된 CS마다 하나씩, `region`을 가리키는 정수 인덱스 벡터의 리스트이다. CS가 없으면 NULL이다.
- L63–65: `CS`와 `ID` 열을 가진 long 형식 표를 (CS, SNP) 쌍당 한 행으로 만들어 **`chr{C}_susie_cs.tsv`** 에 쓴다.
- ⚠ CS는 **1..k로 번호가 다시 매겨진다**(`paste0('L', i)`). susieR 자체 이름(예: `names(cs_list)`의 effect 인덱스에서 온 `L1`, `L3`, `L7`)은 버려지므로, 출력의 `L2`가 susie effect 3일 수 있다.
- ⚠ CS가 없으면 **cs.tsv를 쓰지 않지만, 이전 실행에서 만든 파일은 그대로 남는다.** 그러면 섹션 6이 **오래된(stale)** CS를 오버레이한다(**I-2**).

```r
74 # ── 5. 2-panel 플롯 (Regional assoc + PIP)
75 png(file.path(out_dir, paste0('chr', lead_chr, '_susie.png')),
76     width = 1600, height = 1200, res = 150)
78 par(mfrow = c(2, 1), mar = c(3, 4, 3, 1))
```
PNG 디바이스(1600 × 1200 px, 150 dpi)를 연다. `mfrow = c(2,1)`은 2행 × 1열 패널을 만든다. `mar`는 여백(아래, 왼쪽, 위, 오른쪽)을 텍스트 줄 단위로 지정한다.

```r
80 # LD r² 색상 (lead SNP 기준)
81 lead_id   <- region$ID[which.min(abs(region$GENPOS - lead_pos))]
82 r2_vals   <- ld_mat[lead_id, region$ID]^2
83 r2_color  <- ifelse(r2_vals >= 0.8, '#E41A1C',
84              ifelse(r2_vals >= 0.6, '#FF7F00',
85              ifelse(r2_vals >= 0.4, '#4DAF4A',
86              ifelse(r2_vals >= 0.2, '#377EB8', '#A6CEE3'))))
87 r2_color[region$ID == lead_id] <- '#E41A1C'
```
- L81: 여기서의 "lead"는 **`lead_pos`에 가장 가까운 SNP**이다. config의 `LEAD_SNP` ID가 아니며, 가장 유의한 SNP라는 보장도 없다. 실제 lead SNP가 QC에서 탈락했거나 LD 행이 없으면, 아무 경고 없이 이웃 SNP가 그 자리를 대신한다.
- L82: 상관 행렬에서 lead의 행을 가져와 **제곱**하여 r²를 구한다.
- L83–86: `02_plot.py`와 같은 5개 색상 구간. r²가 NaN이면 색상이 NA가 되어 R이 채우기를 그리지 않는다.
- L87: lead를 강제로 빨간색으로 지정한다.

```r
89  # Panel 1: Regional association
90  log10p <- region$LOG10P
91  main_title <- sprintf('%s  chr%d:%d  +-%dkb',
92                        pheno_name, lead_chr, lead_pos, window %/% 1000)
93  plot(region$GENPOS / 1e6, log10p,
94       pch = 21, bg = r2_color,
95       cex = 0.8, xlab = '', ylab = '-log10(P)',
96       main = main_title)
97  abline(h = -log10(5e-8), col = 'red', lty = 2, lwd = 0.8)
```
- 제목은 예를 들어 `HDL  chr11:116662579  +-500kb`이다(`%/%`는 정수 나눗셈).
- `pch = 21`은 테두리가 있는 채워진 원이며, `bg`는 채우기 색이다.
- 빨간 점선은 genome-wide significance 기준선이다.

```r
99  # Credible Set 테두리 강조 + CS 번호 레이블
100 if (!is.null(cs_list)) {
101   for (i in seq_along(cs_list)) {
102     cs_ids  <- region$ID[cs_list[[i]]]
103     cs_rows <- region[region$ID %in% cs_ids, ]
104     points(cs_rows$GENPOS / 1e6, cs_rows$LOG10P,
105            pch = 21, bg = NA, col = '#984EA3', lwd = 1.5, cex = 1.4)
106     # CS 번호를 가장 유의한 SNP 위에 표시
107     top_row <- cs_rows[which.max(cs_rows$LOG10P), ]
108     text(top_row$GENPOS / 1e6, top_row$LOG10P,
109          labels = paste0('L', i), pos = 3, cex = 0.65, col = '#984EA3', font = 2, xpd = NA)
110   }
111 }
```
- 각 CS 구성원 주위에 더 큰 속이 빈 보라색 원을 그린다.
- 레이블 `Li`는 **가장 유의한** 구성원 위에 표시된다. `pos = 3`은 점의 위쪽, `font = 2`는 굵게, `xpd = NA`는 텍스트가 플롯 영역 밖으로 나가도록 허용한다.
- (참고: `skill/05`는 이 레이블이 PIP가 **가장 높은** SNP에 붙는다고 설명한다. 아래 PIP 패널에서는 맞지만, 이 패널에서는 코드가 가장 높은 −log10 p를 사용한다.)

```r
113 # Lead SNP 다이아몬드
114 lead_row <- region[region$ID == lead_id, ]
115 points(lead_row$GENPOS / 1e6, lead_row$LOG10P,
116        pch = 23, bg = '#E41A1C', col = 'black', cex = 1.5)
117 # 레전드
118 legend('topright',
119        legend = c('Lead SNP', 'Credible Set', '0.8 <= r2', '0.6 <= r2 < 0.8',
120                   '0.4 <= r2 < 0.6', '0.2 <= r2 < 0.4', 'r2 < 0.2'),
121        pt.bg  = c('#E41A1C', NA, '#E41A1C', '#FF7F00',
122                   '#4DAF4A', '#377EB8', '#A6CEE3'),
123        col    = c('black', '#984EA3', rep('black', 5)),
124        pch    = c(23, 21, rep(21, 5)),
125        pt.lwd = c(1, 1.5, rep(1, 5)),
126        pt.cex = 1.2, bty = 'n', cex = 0.8)
```
- `pch = 23`은 lead를 채워진 다이아몬드로 그린다.
- 레전드는 수작업으로 구성된다. 채우기, 테두리, 기호, 선 굵기를 맞춘 7개 항목이다. `bty = 'n'`은 레전드 상자를 없앤다. "Credible Set" 항목은 CS가 없어도 표시된다.

```r
128 # Panel 2: PIP (r² 색상 동일 적용)
129 plot(region$GENPOS / 1e6, pip_df$PIP,
130      pch = 21, bg = r2_color,
131      cex = 0.8, ylim = c(0, 1),
132      xlab = paste0('Chromosome ', lead_chr, ' position (Mb)'),
133      ylab = 'PIP',
134      main = 'Posterior Inclusion Probability')
135 abline(h = 0.5, col = 'grey50', lty = 2, lwd = 0.8)
```
위치에 대한 PIP를 y 범위 0–1로 고정하여 그리고, PIP = 0.5에 기준선을 긋는다. `pip_df`와 `region`은 행 순서가 같으므로 색상이 일치한다.

```r
137 # PIP 패널: CS 테두리 + CS 번호 (ID 매칭으로 정확한 SNP 선택)
138 if (!is.null(cs_list)) {
139   for (i in seq_along(cs_list)) {
140     cs_ids      <- region$ID[cs_list[[i]]]
141     cs_pip_rows <- pip_df[pip_df$ID %in% cs_ids, ]
142     points(cs_pip_rows$GENPOS / 1e6, cs_pip_rows$PIP,
143            pch = 21, bg = NA, col = '#984EA3', lwd = 1.5, cex = 1.4)
144     top_pip <- cs_pip_rows[which.max(cs_pip_rows$PIP), ]
145     text(top_pip$GENPOS / 1e6, top_pip$PIP,
146          labels = paste0('L', i), pos = 3, cex = 0.65, col = '#984EA3', font = 2, xpd = NA)
147   }
148 }
150 # PIP 패널: lead SNP 다이아몬드
151 lead_pip <- pip_df[pip_df$ID == lead_id, ]
152 points(lead_pip$GENPOS / 1e6, lead_pip$PIP,
153        pch = 23, bg = '#E41A1C', col = 'black', cex = 1.5)
155 dev.off()
156 cat(sprintf('플롯 저장: %s/chr%d_susie.png\n', out_dir, lead_chr))
```
PIP 패널에도 같은 오버레이를 그리되, 여기서는 레이블을 각 CS에서 **PIP가 가장 높은** 구성원에 붙인다. `dev.off()`는 디바이스를 닫고 PNG **`chr{C}_susie.png`** 를 쓴다.

```r
158 # ── 6. Regional plot + SuSiE CS 오버레이 자동 생성
159 cs_tsv      <- file.path(out_dir, paste0('chr', lead_chr, '_susie_cs.tsv'))
160 regional_ld <- file.path('output', '04_regional_plot',
161                          paste0('chr', lead_chr, '_top_ld.vcor'))
162 if (file.exists(cs_tsv) && file.exists(regional_ld)) {
163   cmd <- sprintf(
164     paste('python3 script/04_regional_plot/02_plot.py',
165           '--gwas %s --ld %s --lead %s --chr %d --pos %d --window %d',
166           '--out %s --prefix %s --susie-cs %s'),
167     shQuote(gwas_file), shQuote(regional_ld), shQuote(lead_id),
168     lead_chr, lead_pos, window,
169     shQuote(out_dir), shQuote(pheno_name), shQuote(cs_tsv)
170   )
171   cat('Regional+SuSiE 플롯 생성 중...\n')
172   system(cmd)
173   cat(sprintf('플롯 저장: %s/%s_chr%d_regional_susie.png\n',
174               out_dir, pheno_name, lead_chr))
175 } else {
176   cat('regional LD 파일 없음 — regional_susie 플롯 생략\n')
177 }
```
- **한 스크립트에서 다른 스크립트를 연쇄 호출한다.** CS 파일과 Step 4 LD 파일이 모두 있으면, R 스크립트가 셸 명령을 조립하여 Python 플로터를 `--susie-cs`와 함께 실행한다.
- L160–161, L164: **작업 디렉터리 기준 상대 경로**(`output/…`, `script/…`)이므로, Rscript를 프로젝트 루트에서 시작한 경우에만 동작한다(**I-3**).
- L167: `shQuote`는 각 인자를 작은따옴표로 감싸 공백과 ID 안의 `|`를 셸로부터 보호한다.
- ⚠ **`--lead lead_id`**(`lead_pos`에 가장 가까운 SNP)를 넘기지만, Step 4의 `.vcor`는 `--ld-snp ${LEAD_SNP}`로 계산되었다. 두 ID가 다르면 `02_plot.py`가 r² 값을 거의 찾지 못해 **거의 모든 점을 누락한다**(**I-4**).
- ⚠ 이전 실행의 **오래된(stale)** 파일 때문에 `file.exists(cs_tsv)`가 참이 될 수 있다(**I-2**).
- ⚠ `system(cmd)`의 종료 상태는 무시되며, Python이 실패해도 "플롯 저장"이 출력된다.
- 출력: `output/05_susie/{P}_chr{C}_regional_susie.png`.

**Step 5의 출력:** `chr{C}_susie_ld.unphased.vcor1` (+ `.vars`), `chr{C}_susie_pip.tsv`, `chr{C}_susie_cs.tsv`, `chr{C}_susie.png`, `{P}_chr{C}_regional_susie.png`. 모두 `output/05_susie/`에 저장된다.
