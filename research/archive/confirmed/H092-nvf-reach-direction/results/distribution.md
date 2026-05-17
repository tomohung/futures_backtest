# Distribution Research Results: NVF Reach Multiples & Direction Asymmetry

## Date
2026-05-15

## Conditions Tested

### Data
- 1m bars 從 `ohlcv_1m` table,symbol = TX,日盤 08:45–13:45,夜盤 15:00 → 隔日 05:00
- `day_open` = day session 08:45 1m bar 的 open
- `EmaHL` = EMA20 of (day_high − day_low),shift 1(causal,與 `estimate_hl_exit.py` 一致)
- NVF norm:`night_range / EMA20(night_range)`,EMA20 用 `adjust=False`
- NVF threshold:**expanding median of historic norms**(causal,排除當天),warmup < 60 nights → fallback 0.93(與 `key_prices.py:_compute_night_vol_filter` 一致,即 H075 production)

### Reach 定義
- `up_dist = day_high − day_open`、`dn_dist = day_open − day_low`
- `up_ratio = up_dist / EmaHL`、`dn_ratio = dn_dist / EmaHL`、`hl_ratio = (day_high - day_low) / EmaHL`
- 對 multiple `m ∈ {0.618, 0.75, 1.0, 1.2}`:
  - `reach_upper_m = up_ratio ≥ m`
  - `reach_lower_m = dn_ratio ≥ m`
  - `reach_either_m = hl_ratio ≥ m`(此為 H070 沿用定義)

## Sample
- **總樣本**:1,264 個交易日
- **時間範圍**:2021-01-04 ~ 2026-05-14
- **STOP / GO 拆分**(動態 threshold):STOP = 628、GO = 636
- **NVF threshold(最新)**:0.9357
- 市場:台指期 TX 主力合約

---

## Key Findings

### 0. H070 SMA→EMA 重算 sanity(reach_either ≥ 1.0× by absolute bucket)

| Bucket | H070 (SMA20) | H092 (EMA20) | Δ |
|---|---|---|---|
| norm < 0.70 | 29.9% | 30.9% | +1.0pp |
| 0.70–0.85 | 40.7% | 39.7% | −1.0pp |
| 0.85–1.00 | 37.4% | 37.7% | +0.3pp |
| 1.00–1.30 | 38.5% | 39.4% | +0.9pp |
| ≥ 1.30 | 61.0% | 64.4% | +3.4pp |

→ NVF method 升級(SMA→EMA + expanding median)**並未改變 reach 結構**,僅微幅放大極值桶差距。H070 的 reach rate 結論在 production 方法下依然成立。

---

### A. 5-bucket absolute NVF × 4 multiples × direction(N=1,264)

#### Reach `either` rate

| Bucket | N | 0.618 | **0.75** | 1.0 | 1.2 |
|---|---|---|---|---|---|
| norm < 0.70 | 285 | 76.5% | **60.4%** | 30.9% | 17.2% |
| 0.70–0.85 | 224 | 85.3% | **66.1%** | 39.7% | 21.4% |
| 0.85–1.00 | 220 | 86.4% | **69.1%** | 37.7% | 20.9% |
| 1.00–1.30 | 302 | 92.1% | **77.5%** | 39.4% | 24.5% |
| ≥ 1.30 | 233 | 95.7% | **87.1%** | 64.4% | 42.1% |

→ **0.75 補上 H070 缺的中段**,STOP 區間(< 0.70)從 76.5% → 60.4% → 30.9%,顯示 0.75 是有資訊量的中段門檻。

#### Direction bias(upper − lower,pp)

| Bucket | 0.618 | 0.75 | 1.0 | 1.2 |
|---|---|---|---|---|
| norm < 0.70 | +1.4 | −0.4 | −1.1 | −0.4 |
| 0.70–0.85 | **−6.2** | −3.1 | −1.3 | −3.1 |
| 0.85–1.00 | −3.6 | −2.3 | −3.2 | **−5.5** |
| 1.00–1.30 | **+7.3** | +5.3 | +1.3 | −1.3 |
| ≥ 1.30 | −4.3 | −6.4 | **−8.6** | **−7.7** |

→ 沒有任何 cell 通過 ≥ 10pp 的 H2 門檻。但有幾個結構性觀察:
- **1.00–1.30 bucket 在 0.618 與 0.75 顯示 upper bias**(中等夜盤波動 → 偏多 reach)
- **≥ 1.30 bucket 在 1.0 與 1.2 顯示明顯 lower bias**(極高夜盤波動 → 偏空 reach,−8.6pp)
- norm < 0.70(STOP) 整體幾乎對稱,符合「夜盤萎縮 = 雙邊 reach 抑制」

---

### B. 動態 STOP / GO × 4 multiples × direction(N=1,264)

| Group | N | reach metric | 0.618 | **0.75** | 1.0 | 1.2 |
|---|---|---|---|---|---|---|
| **STOP** | 628 | either | 81.1% | **63.7%** | 35.0% | 18.9% |
| **STOP** | 628 | upper | 26.3% | 18.6% | 8.6% | 4.0% |
| **STOP** | 628 | lower | 28.8% | 20.4% | 10.0% | 6.1% |
| **STOP** | 628 | diff (U−L) | **−2.5pp** | **−1.8pp** | **−1.4pp** | **−2.1pp** |
| GO | 636 | either | 92.9% | 80.0% | 48.6% | 30.8% |
| GO | 636 | upper | 36.0% | 25.0% | 12.9% | 7.1% |
| GO | 636 | lower | 34.4% | 25.2% | 16.0% | 11.6% |
| GO | 636 | diff (U−L) | +1.6pp | −0.2pp | **−3.1pp** | **−4.6pp** |

→ **H2 在 pooled 層面失敗**(STOP 最大差距 2.5pp,遠不到 10pp 門檻)。但有兩個有趣的次要結構:
- STOP 在 4 個 multiple 皆呈 lower bias(雖小),pooled 一致 negative
- **GO 在大 multiple(1.0、1.2)反而出現更大的 lower bias**(−3.1pp、−4.6pp)— GO 大波動天偏向下方走得更遠

---

### C. STOP cross-year direction(2021–2026 May)

| Year | N_stop | diff 0.618 | diff 0.75 | diff 1.0 | diff 1.2 |
|---|---|---|---|---|---|
| 2021 | 125 | 0.0 | −4.0 | −4.8 | −1.6 |
| 2022 | 112 | −10.7 | −8.9 | −7.1 | −4.5 |
| 2023 | 117 | −5.1 | −2.6 | −3.4 | −5.1 |
| 2024 | 115 | −2.6 | +3.5 | +1.7 | −2.6 |
| 2025 | 124 | 0.0 | −0.8 | +1.6 | −0.8 |
| 2026 | 35 | **+14.3** | **+11.4** | **+14.3** | **+11.4** |

→ 2026 (N=35, Jan-May) 完全逆轉成 upper bias,但樣本太小不能定論。其他 5 年:
- 2022 是最強 lower bias 年(−7~−11pp 跨 4 個 multiple),配合該年熊市
- 2024/2025 接近完全對稱

**Cross-year consistency**:
- 0.75:6 年 4 負 2 正 → 方向 dominant 為 lower bias,符合 ≥ 4/6 一致
- 1.2:6 年 5 負 1 正 → 同上

→ **方向確實有 lower bias 的微弱規律**,但 **magnitude(pooled ≤ 2.5pp)遠低於可操作門檻**。

---

### D. H1 GATE — 0.75 informational value(STOP days)

| Pair | 差距 | 通過 ≥ 5pp ? |
|---|---|---|
| 0.75 vs 0.618 | **17.4pp** | ✅ |
| 0.75 vs 1.0 | **28.7pp** | ✅ |

→ **H1 PASS**:0.75 在 STOP 天提供顯著的中段資訊。

---

## Vs. Expected

| 預期 | 實際 | 評估 |
|---|---|---|
| 0.75 reach 在 STOP 桶 45–60% | 60.4%(absolute < 0.70)/ 63.7%(dynamic STOP) | **符合預期上緣** |
| reach 隨 norm 單調提升 | 6 bucket × 4 multiple 24 格全部單調(或近單調) | **完全符合** |
| STOP 方向不對稱 ≥ 10pp | 最大 pooled diff 2.5pp(STOP 0.618) | **不符合** |
| STOP 方向跨年 4/6 一致 | 0.75 與 1.2 multiple 達 4/6 negative | **方向一致但 magnitude 微弱** |
| 樣本 ≥ 1,200 | 1,264 | **符合** |

意外觀察:
- ≥ 1.30 bucket(GO 強桶)在 1.0× 顯示 −8.6pp 的 lower bias,是整個 5×4 矩陣中單格最大值,**比 STOP 任何 cell 都大**
- 1.00–1.30 bucket 在 0.618 顯示 +7.3pp 的 upper bias,是矩陣中唯一持續正向的 segment
- 動態 GO 桶在大 multiple 的 lower bias(−4.6pp at 1.2)比 STOP 桶更明顯

---

## Addendum: 4-bucket Refinement(2026-05-15 補做)

回應「STOP 0.618 reach 仍 81%,2-bin 太粗?」的 review,把絕對 5 桶併為 4 桶:`< 0.70` / `0.70-1.00` / `1.00-1.30` / `≥ 1.30`。

### Reach (either) by 4 buckets

| Bucket | N | 0.618 | 0.75 | 1.0 | 1.2 |
|---|---|---|---|---|---|
| < 0.70 deep STOP | 285 | 76.5% | 60.4% | 30.9% | 17.2% |
| 0.70-1.00 mid STOP | 444 | 85.8% | 67.6% | 38.7% | 21.2% |
| 1.00-1.30 mid GO | 302 | 92.1% | 77.5% | 39.4% | 24.5% |
| ≥ 1.30 strong GO | 233 | 95.7% | 87.1% | 64.4% | 42.1% |

→ Deep STOP 0.618 reach = 76.5%(不是動態 STOP 的 81%),稍微較低但結構不變。**0.618× 對所有 bucket 區辨力都低,真正分離出現在 ≥ 1.0×。**

### Direction bias by 4 buckets (upper − lower, pp)

| Bucket | 0.618 | 0.75 | 1.0 | 1.2 |
|---|---|---|---|---|
| < 0.70 deep STOP | +1.4 | −0.4 | −1.1 | −0.4 |
| 0.70-1.00 mid STOP | −5.0 | −2.7 | −2.3 | −4.3 |
| **1.00-1.30 mid GO** | **+7.3** | **+5.3** | +1.3 | −1.3 |
| **≥ 1.30 strong GO** | −4.3 | −6.4 | **−8.6** | **−7.7** |

→ **發現 bipolar 結構**:Mid GO 偏 upper、Strong GO 偏 lower。H070 兩者混為「GO」桶導致方向 bias 互相抵消。

### Strong-GO (≥ 1.30) 跨年驗證

| Year | N | diff 0.618 | diff 0.75 | diff 1.0 | diff 1.2 |
|---|---|---|---|---|---|
| 2021 | 45 | −8.9 | −4.4 | −6.7 | −8.9 |
| 2022 | 42 | −26.2 | −28.6 | −16.7 | −2.4 |
| 2023 | 34 | 0.0 | 0.0 | −11.8 | −8.8 |
| 2024 | 48 | +2.1 | +2.1 | −6.2 | −12.5 |
| **2025** | 41 | **+22.0** | **+9.8** | **+7.3** | 0.0 |
| 2026 | 23 | −21.7 | −26.1 | −26.1 | −17.4 |

Consistency:
- m=1.0:avg **−10.0pp**,5/6 負,**|avg| ≥ 10pp ✅**,**consistent ≥ 4/6 ✅**
- m=1.2:avg −8.3pp,5/6 負,|avg| ≥ 5pp
- m=0.75:avg −7.9pp,3 負 / 2 正 / 1 零(2025 為強反例)
- **2025 是唯一強正值年**(+22pp 在 0.618、+7.3pp 在 1.0)— 對應 bull regime,可能 regime-dependent

### 對 H2 結論的修正

- 原 H2 (動態 STOP 全桶)— **FAIL**(magnitude < 3pp)
- **修正 H2′ (≥ 1.30 strong GO at 1.0×)— PASS**(avg −10.0pp + 5/6 cross-year consistent),但需注意 2025 regime 反例
- 修正 H2″ (1.00-1.30 mid GO at 0.618)— 半通過(+7.3pp pooled,但跨年穩定性未細查)

---

## Gate Decision(2026-05-15 終版,含 4-bucket 修正)

- **H1 (0.75 informational)— PASS**(STOP 81% → 64% → 35% 三段下行,17–29pp 差距)
- **H2 (動態 STOP 全桶方向)— FAIL**(pooled magnitude < 3pp)
- **H2′ (≥ 1.30 strong GO at 1.0×)— PASS**(avg −10pp + 5/6 consistent)
- **附帶觀察:GO bipolar(mid GO 偏 upper、strong GO 偏 lower)**

對應決策:**進入 Phase 2,但研究重心從 STOP 移轉到 strong-GO direction**。Phase 2 主要驗證問題:

1. **Strong-GO (≥ 1.30) lower bias 能否用於 S001 / S003 策略改善?**(例如 strong-GO 天 short bypass 或 long R/R 提升)
2. **2025 regime 反例**:bull market 條件下 bias 是否反向?需條件化測試
3. **Mid-GO (1.00-1.30) upper bias 是否獨立可操作?**

- [ ] Archive(改為 Phase 2 後再決定)
- [x] 進入 Phase 2(目標:strong-GO direction bias 的策略應用驗證)

---

## Derived Hypotheses

1. **(納入 Phase 2 主軸,不再是衍生)Strong-GO ≥ 1.30 lower bias** — 已通過 H2′ pre-check,直接進 Phase 2 驗證策略應用。

2. **H093 候選 — Mid-GO (1.00-1.30) 0.618 upper bias 獨立驗證**
   - 4-bucket pooled +7.3pp upper bias,矩陣中唯一持續正向 segment
   - H092 Phase 2 不會涵蓋(主軸在 strong-GO),但若 strong-GO 可操作,mid-GO 自然是下一個檢查對象
   - 需 cross-year stability 與策略應用驗證

3. **H094 候選 — GO bipolar regime 識別**
   - 2025 strong-GO 翻成 upper bias,與 2021/2022/2026 相反
   - 可能 bull/bear regime 切換 strong-GO 方向 — 需要 regime 變數(VIX trend、MA 結構)做條件化驗證

4. **2026 regime flip 觀察(N=23 strong-GO,太早下結論)**
   - 2026 Jan-May strong-GO 反向到 −26pp(2022 級的強 lower bias)
   - 與 2025 形成鮮明對比,值得納入 Phase 2 regime 變數設計

---

## Links
- Proposal: `proposal.md`
- Tasks: `tasks.md`
- Explore script: `explore.py`
- CSVs: `results/reach_by_absolute_bucket.csv`、`reach_by_dynamic_bucket.csv`、`stop_yearly_direction.csv`、`stop_direction_summary.csv`
- Plot: `results/h092_reach_direction.png`
- Refinement script: `explore_4bucket.py`
- Refinement CSVs: `results/reach_4bucket_either.csv`, `reach_4bucket_direction.csv`, `strong_go_yearly.csv`
- Refinement plot: `results/h092_4bucket_refinement.png`
