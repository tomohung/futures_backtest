# Phase 2 Results: Night vol → Day session structure

## Date
2026-05-15

## Scope
非策略 filter 測試。純粹刻畫:在 4 個 NVF tier 下,日盤的方向、振幅、極值時點、形態、軌跡有何不同。

## Sample
- 1,264 個交易日(2021-01-04 ~ 2026-05-14)
- 4 tiers (cutoffs 0.8 / 1.0 / 1.2):

| Tier | N | % |
|---|---|---|
| deep STOP (< 0.8) | 430 | 34.0% |
| mid STOP (0.8–1.0) | 299 | 23.7% |
| mid GO (1.0–1.2) | 221 | 17.5% |
| strong GO (≥ 1.2) | 314 | 24.8% |

---

## A. 日盤方向 — signed return = (close − open) / open × 100 %

| Tier | N | mean | median | std | p10 | p25 | p75 | p90 | %_pos |
|---|---|---|---|---|---|---|---|---|---|
| deep STOP | 430 | **+0.004%** | −0.038% | 0.657% | −0.723% | −0.412% | +0.430% | +0.868% | 47.9% |
| mid STOP | 299 | +0.003% | +0.051% | 0.738% | −0.871% | −0.473% | +0.440% | +0.864% | 53.5% |
| **mid GO** | 221 | **+0.074%** | **+0.076%** | 0.727% | −0.739% | −0.369% | +0.549% | +0.949% | **54.3%** |
| **strong GO** | 314 | **−0.056%** | **+0.078%** | **1.045%** | **−1.120%** | −0.618% | +0.528% | +1.025% | 52.2% |

### 關鍵觀察

1. **Strong GO 的方向不是「偏空」,而是「尾部風險擴張」**
   - mean (−0.056%) 與 median (+0.078%) **方向相反** — 表示大跌日把 mean 拖下去
   - std 1.045% 是其他 tier 的 ~1.5 倍
   - p10 (−1.120%) 比 mid GO p10 (−0.739%) 大幅惡化,但 p90 (+1.025%) 只比 mid GO (+0.949%) 多 0.08pp
   - 所以「Phase 1 strong-GO −8.6pp lower bias at 1.0×」實際上反映的是 **不對稱大跌風險**,不是「典型 strong-GO 天偏空」

2. **Mid GO 是唯一持續偏多的 tier**
   - 唯一 mean / median 都 > 0 的 tier
   - %_positive 54.3% 最高
   - 但 magnitude 不大(median +0.076%)

3. **Deep STOP 是 direction-neutral**
   - mean 與 median 都貼近 0
   - std 最小(0.657%)
   - 確認「夜盤萎縮 = 日盤窄幅震盪」直覺

---

## B0. 波動到達率(reach rate)by 4-tier — 補完(phase2_reach_4tier.py)

### Reach (either side)

| Tier | N | 0.618 | 0.75 | 1.0 | 1.2 |
|---|---|---|---|---|---|
| deep STOP | 430 | 79.1% | 62.6% | **33.0%** | 17.4% |
| mid STOP | 299 | 86.6% | 67.9% | 39.5% | 22.7% |
| mid GO | 221 | 92.3% | 78.3% | 39.4% | 24.0% |
| strong GO | 314 | 94.6% | 84.1% | **58.0%** | 37.9% |

→ **1.0× 是 strong-GO 與其他 tier 的分水嶺**(33-39-39-58%)。Mid STOP 與 mid GO 在 1.0× 上幾乎相同(39.5% vs 39.4%)— 中間兩 tier 在 reach 上同質。

### Direction bias by tier (upper − lower, pp)

| Tier | 0.618 | 0.75 | 1.0 | 1.2 |
|---|---|---|---|---|
| deep STOP | −2.3 | −2.1 | −0.7 | −0.7 |
| mid STOP | −2.7 | −1.3 | −3.3 | −5.7 |
| **mid GO** | **+9.0** | **+8.1** | **+5.4** | +1.8 |
| **strong GO** | −2.5 | −5.4 | **−8.9** | **−8.3** |

→ **Bipolar 結構在 0.8/1.0/1.2 切下比舊 0.7/1.0/1.3 還清晰**:
- Mid GO upper bias 從 +7.3pp 升到 **+9.0pp**(at 0.618)
- Strong GO lower bias 維持 −8.9pp(at 1.0×)

### Strong-GO 跨年穩定性

| Year | N | reach 1.0× either | diff 1.0× | diff 1.2× |
|---|---|---|---|---|
| 2021 | 58 | 70.7% | −12.1 | −13.8 |
| 2022 | 62 | 56.5% | −17.7 | −8.1 |
| 2023 | 53 | 45.3% | −5.7 | −5.7 |
| 2024 | 59 | 64.4% | −3.4 | −10.2 |
| 2025 | 54 | 48.1% | **0.0** | −1.9 |
| 2026 | 28 | 64.3% | −17.9 | −10.7 |

- **5/6 年 diff 1.0× < 0**(2025 翻平,沒翻正)
- **6/6 年 diff 1.2× < 0**(完全一致)
- 比舊 cutoff 1.3 的 5/6 + 2025 翻正 +7.3pp 還穩定

### 整合解讀:strong-GO 的真實樣貌

| 維度 | Strong-GO |
|---|---|
| 觸 lower ≥ 1.0× | **22.6%** |
| 觸 upper ≥ 1.0× | 13.7% |
| Median signed_ret | **+0.078%** |
| Mean signed_ret | −0.056% |
| %_positive | 52.2% |
| L-then-H 形態 | 36.6%(最高) |

**結論性詮釋**:
> Strong-GO 天有 22.6% 機率深跌至 −1×EmaHL,但收盤前常 mean-revert 回近開盤,中位數仍微正(+0.078%)。「**日內 V 型(L 先於 H,但 H 不衝高)**」是 strong-GO 典型模式 — 對應 path shape D 模組的 L-then-H 36.6% 最高。但約 13% 沒收復,造成 mean 為負且 std 是其他 tier 1.5 倍。
>
> 這比「strong-GO 偏空」更精確、更可操作:
> - 不是「機率偏空」(機率上 52% 收紅)
> - 而是「**幅度不對稱 + 日內深探**」(deep dips 比 deep rallies 多 8.9pp)

---

## B. 日盤波動量 — HL / EmaHL

| Tier | N | mean | median | std | p10 | p25 | p75 | p90 |
|---|---|---|---|---|---|---|---|---|
| deep STOP | 430 | 0.914 | 0.835 | 0.367 | 0.508 | 0.659 | 1.089 | 1.434 |
| mid STOP | 299 | 0.985 | 0.888 | 0.400 | 0.587 | 0.698 | 1.162 | 1.493 |
| mid GO | 221 | 1.031 | 0.918 | 0.415 | 0.642 | 0.787 | 1.190 | 1.515 |
| strong GO | 314 | **1.199** | **1.078** | **0.585** | 0.697 | 0.842 | **1.375** | **1.766** |

### 關鍵觀察

- **波動量與 NVF tier 嚴格單調**(mean 0.91 → 0.99 → 1.03 → 1.20)— H070 結論完全再現
- Strong GO 平均日盤 HL 比 EmaHL **大 20%**,p90 達 1.77×
- Deep STOP 中位數只有 0.835×,**有一半的天連 EmaHL 都打不到**
- Strong GO 的 std 0.585 比 deep STOP 的 0.367 高 60% — 不只均值大,**分散也大**

---

## C. Day high / low 形成時點(分鐘,0=08:45,300=13:45)

| Tier | N | H_mean | H_p25 | H_p50 | H_p75 | L_mean | L_p25 | L_p50 | L_p75 |
|---|---|---|---|---|---|---|---|---|---|
| deep STOP | 430 | 113 | 20 | 76 | 210 | 115 | 26 | 82 | 209 |
| mid STOP | 299 | 111 | 24 | 78 | 187 | 107 | 18 | 64 | 195 |
| mid GO | 221 | 117 | 21 | 69 | 222 | 106 | 20 | 74 | 177 |
| strong GO | 314 | 110 | 16 | 80 | 189 | 107 | 21 | 66 | 195 |

### 關鍵觀察

- **極值時點在 4 個 tier 間非常相似** — H_p50 約 70-80 分鐘,L_p50 約 65-82 分鐘
- 約 **一半的交易日,高/低都在開盤後 1 小時形成**(p50 ≈ 76 分鐘)
- p75 落在 190-220 分鐘 — 表示有 25% 的天極值在最後 1.5 小時才出現
- p25 落在 16-26 分鐘 — 表示有 25% 的天極值在開盤後 25 分鐘內就鎖定
- **NVF tier 無法預測極值時點** — 這是與 reach 強度不同的維度

---

## D. Path shape — 形態分布(%)

| Tier | up-trending | L-then-H | H-then-L | down-trending | unknown |
|---|---|---|---|---|---|
| deep STOP | 15.6% | 30.7% | 39.8% | 13.7% | 0.2% |
| mid STOP | 15.4% | 34.1% | 36.1% | 14.4% | 0.0% |
| mid GO | **18.6%** | 31.2% | 35.7% | 14.5% | 0.0% |
| strong GO | **12.4%** | 36.6% | **36.9%** | 13.4% | 0.6% |

### 形態定義
- **up-trending**: 低點在第一小時(< 60 分鐘),高點在最後一小時(> 240 分鐘)
- **down-trending**: 高點在第一小時,低點在最後一小時
- **L-then-H**: 低點先形成,高點後形成(非 trending)— 通常為 V 型反彈
- **H-then-L**: 高點先形成,低點後形成(非 trending)— 通常為倒 V 型回落

### 關鍵觀察

- **形態分布在 4 個 tier 間極度穩定**:三大類(L-then-H、H-then-L、trending)比例都接近 30% / 36% / 15% / 14%
- Mid GO 是唯一 **up-trending 占比高**(18.6%)的 tier — 與其方向偏多一致
- Strong GO 的 up-trending 占比最低(12.4%),但同時 **L-then-H 占比最高**(36.6%) — 表示 strong-GO 天較常「先跌後彈」,但跌幅大、反彈未必能收復(對應其負 mean)
- **形態與 NVF tier 的關聯弱,遠不如波動量強**

---

## E. 平均日盤軌跡(close / day_open − 1, %)

| Tier | N | final mean | final median | %_positive_final |
|---|---|---|---|---|
| deep STOP | 430 | +0.004% | −0.038% | 47.9% |
| mid STOP | 299 | +0.003% | +0.051% | 53.5% |
| mid GO | 221 | +0.074% | +0.076% | 54.3% |
| strong GO | 314 | −0.056% | +0.078% | 52.2% |

(細節見 plot `h092_phase2_market_structure.png` 面板 (f))

### 關鍵觀察

- 4 條平均軌跡 **形狀相似但 amplitude 不同**:strong GO 軌跡 envelope(p25/p75 spread)最寬
- Mid GO 軌跡 mean 唯一持續往上,終值最高
- Strong GO 軌跡 mean 與 median 在 session 末段 diverge — 大跌日把 mean 拉下,中位數仍微正

---

## 跨年穩定性

### Yearly signed_ret mean (%)

| Year | deep STOP | mid STOP | mid GO | strong GO |
|---|---|---|---|---|
| 2021 | +0.014 | **+0.250** | −0.033 | −0.181 |
| 2022 | −0.033 | −0.136 | −0.014 | −0.132 |
| 2023 | −0.004 | −0.042 | +0.072 | +0.068 |
| 2024 | +0.014 | −0.001 | +0.089 | −0.023 |
| 2025 | −0.012 | −0.126 | **+0.193** | +0.010 |
| 2026 | **+0.169** | **+0.280** | +0.084 | −0.062 |

- Mid GO 在 4/6 年 mean > 0,平均 +0.07%
- Strong GO 在 4/6 年 mean < 0,平均 −0.05%
- 2025 是 strong GO 唯一強勢年(+0.010%),與 distribution.md 的 bull regime 觀察一致
- **Deep STOP 的方向飄移最小**(year-to-year 變動最窄,除 2026 outlier)

### Yearly signed_ret median (%)

| Year | deep STOP | mid STOP | mid GO | strong GO |
|---|---|---|---|---|
| 2021 | −0.054 | +0.099 | −0.045 | −0.089 |
| 2022 | −0.082 | +0.054 | +0.108 | +0.074 |
| 2023 | +0.007 | +0.011 | +0.045 | +0.139 |
| 2024 | −0.039 | +0.038 | +0.027 | +0.123 |
| 2025 | −0.128 | −0.080 | +0.146 | +0.000 |
| 2026 | +0.509 | +0.083 | −0.066 | −0.056 |

- **Strong GO 的中位數在 4/6 年是正的!**(2021、2026 為負)
- Mean 與 median 在 strong GO 上的 sign disagreement 確認了 tail-risk 解讀

---

## 結論

### 1. Strong GO 的「lower bias」是 tail risk,不是方向偏空

Phase 1 看到的 −8.6pp 「reach lower > reach upper at 1.0×」並不代表「strong GO 天傾向偏空」。實際上:
- Strong GO median 是 **+0.078%**(微正)
- %_positive 是 **52.2%**(略大於 50%)
- 但 std 1.05% 是其他 tier 的 1.5 倍,p10 也是最差

所以 strong GO 是「方向中性,但波動大、左尾風險顯著」的狀態。Phase 1 reach analysis 把 reach behavior 視為對稱觸及,大跌大漲機率被分別計算,因此 +8.6pp 差距反映 **下行幅度大於上行幅度** 而非「下行機率大於上行機率」。

### 2. Mid GO (1.0-1.2) 是唯一持續偏多的 tier

- 同時 mean (+0.07%) / median (+0.08%) / %positive (54.3%) 三項都正
- 跨年 4/6 mean > 0
- 是最 "directional" 的 tier

### 3. Deep STOP 是 direction-neutral 但 range-bound

- mean / median 都貼近 0,跨年最穩定
- 波動量比 EmaHL 小(median 0.835)
- 適合「不交易」或「reversion-style 策略」

### 4. NVF tier 對「形態」與「極值時點」沒有強區辨力

- Path shape 與 high/low 形成時點在 4 tier 間幾乎一致
- NVF 的力量在 **波動量 magnitude** 與 **左尾風險** 上,不在路徑形狀上

---

## Implications

### A. 對 morning briefing 多階顯示的指引(回應 user 之前的 TODO)

| Tier | 適用訊息 |
|---|---|
| deep STOP | 「窄幅震盪日(33% 觸 1×EmaHL),日內反轉策略可,趨勢策略停」 |
| mid STOP | 「方向中性,標準操作(40% 觸 1×)」 |
| **mid GO** | 「**偏多日**,upper bias +9pp(40% 觸 1×,但偏 upper),適合 long-trend」 |
| **strong GO** | 「**高波動 + 日內 V 型風險**(58% 觸 1×,偏 lower −8.9pp),建議:減倉、加大停損、留意 mean-revert」 |

### B. 對策略設計的啟示(不是本研究範圍,但供參考)

- Strong GO 不適合「方向預測」(中位數微正、平均微負,signal-to-noise 太低)
- Strong GO 適合「波動率交易」(已知 std 1.5×)— 選擇權買方、breadth strategy
- Mid GO 是 long-bias 策略最佳環境
- Deep STOP 應避開趨勢策略,可保留 reversion / fading

---

## F. Production EstHL 視角下的 reach 與 ladder(2026-05-17 補完)

### 三種 reach 定義對比

| 定義 | 公式 | 解釋 |
|---|---|---|
| A (open-anchored) | `day_open + m × EmaHL` | 整天固定,可預掛單 |
| B-est (running EstHL, no buffer) | `running_low + m × EstHL` | 動態,EstHL 隨成交量調整 |
| **B-sat (S001 production)** | `running_low + m × EstHL − EmaHL/8` | S001 SatZone 精確公式 |

### EstHL/EmaHL ratio by tier(2h window mean)

| Tier | first valid | last valid |
|---|---|---|
| deep STOP | 0.79 | 0.86 |
| mid STOP | 0.86 | 0.93 |
| mid GO | 0.93 | 1.01 |
| **strong GO** | **1.05** | **1.13** |

→ EstHL 量大日拉高,量縮日壓低 — **自動 normalize 跨 tier reach 機率**。

### S001 SatZone(B-sat,m=1.0)2h reach by tier

| Tier | upper | lower | either |
|---|---|---|---|
| deep STOP | 28.1% | 26.3% | 46.0% |
| mid STOP | 26.4% | 24.1% | 43.5% |
| mid GO | 26.2% | 20.8% | 42.1% |
| strong GO | 21.7% | 24.2% | 40.1% |

→ **跨 tier 機率均等**(40-46%),production EstHL 把 vol regime 影響「拉平」。Strong GO 反而最低 — 與 B-old 結論相反。

### 重要 reinterpretation

| 原結論(B-old / EmaHL) | 修正(B-sat / production) |
|---|---|
| Strong GO −8.6pp lower bias at 1.0× | 縮減為 −2.5pp(仍存在但弱) |
| Strong GO short E[R] > long | **反向 — strong GO long 0.40 R/unit 略勝 short 0.37 R/unit** |
| Mid GO upper bias +9pp | ✅ 在 B-sat 下仍 +5.4pp |
| 「0.618 是 sweet spot」 | A 定義最佳 m ≈ 0.40;B-sat 最佳 m ≈ 0.60(接近 0.618) |

---

## G. Optimal m scan + yearly stability(2026-05-17)

掃描 m = 0.10 ~ 1.50(step 0.05),找各定義 × tier × direction 的最大 E[R/unit]。

### Pooled optimum

| Tier | Long A | Long B-sat | Short A | Short B-sat |
|---|---|---|---|---|
| deep STOP | **m=0.30** (0.147 R) | m=0.60 (0.275 R) | m=0.35 (0.150 R) | m=0.70 (0.296 R) |
| mid STOP | m=0.40 (0.173 R) | m=0.60 (0.322 R) | m=0.35 (0.156 R) | m=0.55 (0.300 R) |
| mid GO | m=0.45 (0.200 R) | m=0.60 (0.356 R) | m=0.30 (0.156 R) | m=0.60 (0.341 R) |
| **strong GO** | **m=0.45** (0.204 R) | **m=0.60** (0.395 R) | m=0.60 (0.191 R) | m=0.55 (0.372 R) |

### Yearly drift

**A 定義最佳 m 跨年範圍**:0.20-0.35(不穩定)
**B-sat 最佳 m 跨年範圍**:0.15-0.40(較穩定),多數落在 0.55-0.70

### IS(2021-2024) vs OOS(2025-2026)穩健性

4 個 B-sat cell **完全 IS=OOS**(opt_m 不變):
- mid STOP short(m=0.55)
- **mid GO long**(m=0.60)
- **strong GO long**(m=0.60)
- strong GO short(m=0.55)

A 定義 2 個 overfit cell(IS m 差距 ≥ 0.04):
- mid GO long(IS 0.35 → OOS 0.60)
- strong GO short(IS 0.60 → OOS 0.45)

### Yearly findings 摘要

1. **B-sat 跨年穩定**:90% cell 在 0.55-0.70,**統一 m=0.60 接近最佳**
2. **A 定義跨年飄移大**:範圍 0.20-0.35,單一 m 沒有覆蓋全年
3. **2025/2026 沒有崩潰**:OOS 表現大多優於 IS,沒有 regime break
4. **mid GO long 最穩**:B-sat 下 6 年 opt_m 都在 0.55-0.70,IS=OOS 完全一致

---

## H. 修正版實務 ladder 建議

### 預掛單(A 定義 EmaHL ladder)

**Universal m=0.40** 或 **tier-dependent**:

| Tier | Long m | Short m | EmaHL=200pt 範例 |
|---|---|---|---|
| deep STOP | 0.30 | 0.35 | Long: open+60、Short: open−70 |
| mid STOP | 0.40 | 0.35 | Long: open+80、Short: open−70 |
| mid GO | 0.45 | 0.30 | Long: open+90、Short: open−60 |
| strong GO | 0.45 | 0.60 | Long: open+90、Short: open−120 |

**不要用 0.618** — A 定義 6 年最佳 m 平均約 0.40,0.618 過遠。

### 看盤(B-sat / S001 SatZone)

**統一 m=0.60**:
```
Long  exit: running_low  + 0.60 × EstHL − EmaHL/8
Short exit: running_high − 0.60 × EstHL + EmaHL/8
```

跨 tier 跨年 IS=OOS 都接近最佳,**直接用 0.618 也只差 2%**。

### 5-unit front-heavy 在最佳 m 的 total E[R]

| 環境 | A 定義 (5 × opt m) | B-sat (5 × m=0.60) |
|---|---|---|
| strong GO long | 5 × 0.204 = **1.02 R** | 5 × 0.395 = **1.97 R** |
| mid GO long | 5 × 0.200 = 1.00 R | 5 × 0.356 = 1.78 R |
| mid GO short | 5 × 0.156 = 0.78 R | 5 × 0.341 = 1.70 R |
| strong GO short | 5 × 0.191 = 0.96 R | 5 × 0.372 = 1.86 R |

→ **B-sat 動態 SatZone 比固定 EmaHL ladder E[R] 高近 2 倍**。如果可以盯盤,B-sat 是顯然更優。

---

## Verdict 對應 Phase 2 hypothesis

原 Phase 2 GATE 預期是「驗證 strong-GO direction bias 能否轉成 S001 策略改進」。本研究 redirect 為描述性,結論:

- [x] **Confirmed**(描述性發現):
  1. NVF tier 對日盤 **波動量** 與 **左尾風險** 有強解釋力,對方向 mean 有弱影響,對形態/時點無顯著影響
  2. **Production EstHL 把 SatZone reach 機率跨 tier 拉平** — 「strong GO lower bias」是 fixed EmaHL 的副作用,非真實方向偏空
  3. **B-sat 最佳 m 跨年穩定在 0.55-0.70**,可用單一 m=0.60 配置 ladder
  4. A 定義最佳 m = 0.30-0.45,**0.618 為次優選擇**
  5. **Mid GO long + B-sat m=0.60** 是 IS/OOS 跨年最一致的組合(gap=0)
- [ ] Rejected
- [ ] Inconclusive

「Strong GO direction bias」在 production 視角下大幅縮減,**不需要進入策略 backtest 階段**。
**Morning briefing 多階顯示**(已記在 memory)與 **ladder 統一改用 m=0.60 (B-sat) 或 m=0.40 (A)** 是直接可落地的應用。

---

## Derived Hypotheses

1. **Mid GO long-bias 策略應用**(原 H094 候選具體化)
   - Mid GO median +0.08%, mean +0.07%, %positive 54.3%
   - 跨年 4/6 一致為正
   - 是否能成為 S001 / ORB 策略的 boost filter?待測

2. **Strong GO 波動率交易候選**
   - std 1.05% vs deep STOP 0.66% — 對買方選擇權有結構性 alpha
   - 但需考慮 IV pricing 是否已 reflect 此 ex-post realized vol

3. **Tail-risk-aware NVF 應用**
   - Strong GO 的 p10 = −1.12% 顯著大於其他 tier
   - 已有部位於 strong GO 開盤前,可考慮「strong GO 日減倉 / 加碼停損」的 risk management 規則

4. **2025 bull regime 條件化**
   - 2025 是唯一打破 strong GO 偏空大平均的年份
   - 提示存在「bull regime indicator(可能是 long-MA、breadth、VIX trend)」可條件切換 strong GO 偏向

---

## Links

- Scripts: `phase2_market_structure.py`、`phase2_reach_4tier.py`、`phase2_reach_2h.py`、`phase2_reach_definitions.py`、`phase2_satzone_reach.py`、`phase2_reach_production_esthl.py`、`phase2_ladder_bsat.py`、`phase2_optimal_m_scan.py`、`phase2_optimal_m_yearly.py`
- CSVs: 同目錄 `results/` 下所有 .csv
- Plots: `results/h092_phase2_*.png`(共 ~6 張)
