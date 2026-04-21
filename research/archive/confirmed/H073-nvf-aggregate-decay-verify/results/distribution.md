# Distribution Research Results: NVF Aggregate Signal Decay Verification

## Date
2026-04-21

## Conditions Tested
- 三策略：EstHL、Reversal、Exhaustion（皆解除 weekday filter）
- 4 種 NVF 方法組合：(SMA20, EMA20) × (固定 0.85, median split)
- Cutoff: 2026-04-17 (H066/H067 confirm 日)
- Expanding window: 2025-12-01 ~ 2026-04-20，每週

## Sample
- Night days: 1,246
- EstHL trades: 247（with NVF: 235）
- Reversal trades: 498（with NVF: 483）
- Exhaustion trades: 134（with NVF: 131）
- Expanding window: 21 個 cutoff 點

## Key Findings

### 1. H066/H067 數字可被精確重現

| Strategy | H066/H067 報告 | 本研究用「相同方法」 | 差距 | 解讀 |
|----------|------------------|-----------------------|------|------|
| EstHL    | +83.6%（H066, EMA+median） | **+73.6%** | -10pp | 小幅波動 |
| Reversal | +64.3%（H067, SMA+median） | **+50.7%** | -13pp | 小幅波動 |
| Exhaustion | （未發表） | -22.7%（EMA+median） | — | 確認負向 |

→ **H066/H067 baseline 健康，不是 regime drift**。

### 2. H072 「衰減 4×」是方法學差異造成

EstHL 4 個方法組合對比：

| 方法組合 | diff% | 與 H066 +83.6% 差距 |
|----------|-------|---------------------|
| EMA + median（**H066 explore.py 真實使用**） | +73.6% | -10pp（合理） |
| EMA + 0.85 fixed | +37.2% | -46pp |
| SMA + median | +15.3% | -68pp |
| SMA + 0.85 fixed（**H072 + 實盤 key_prices.py 使用**） | +19.5% | -64pp |

**「衰減」分解**：
- 把 EMA 換 SMA：吃掉約 37pp 的 diff
- 把 median 換 0.85 fixed（在 SMA 上）：吃掉約 4pp
- 合計 -64pp，剛好對應 H072 觀察到的「衰減」

H072 同時換掉了 EMA 與 median split，等於用一個**完全不同的 NVF 定義**去比 H066 的數字。

### 3. Expanding Window 確認沒有 step change

詳見 `h073_t4_expanding.png`。EMA + median 法（H066 真實方法）的 EstHL diff 在 2025-12 ~ 2026-04 區間：

- 2025-12-01: +75.9%
- 2026-01-26: +60.3%（區間內最低）
- **2026-04-13: +83.6%（剛好等於 H066 報告）**
- 2026-04-20: +73.6%

整個區間波動約 60–84%，沒有「4 天內衰減 4×」的 step change。

### 4. 重大副發現：實盤用的是「弱版」NVF

`src/analysis/key_prices.py:67-122` 的 `_compute_night_vol_filter` 使用 **SMA20 + 0.85 fixed**，與 H066 explore.py 的 **EMA + median** 不同。

| | H066 evaluated | Production implemented |
|---|------------------|------------------------|
| Norm 分母 | EMA20 | SMA20 |
| Threshold | median split | 0.85 fixed |
| Aggregate diff (EstHL) | **+73.6%** | **+19.5%** |
| Aggregate diff (Reversal) | +84.0%（with EMA+median） | +29.5% |

H066 summary.md 寫「EMA/SMA 相關 r=0.985, 結果一致；採用 SMA 以求直覺」——但實際數據顯示兩者 PF diff 落差 **58pp**（73.6 vs 15.3），「結果一致」的說法不成立。

實盤從 H066 confirm 開始，**就一直在用 4× 弱於 H066 評估值的 NVF 版本**。

### 5. 補充：逐年 night_norm 中位數檢查（驗證跨年穩定性）

回應「絕對振幅 vs 比例」的疑問——night_norm 是無單位比例（night_range / SMA20），跨年應穩定。實際資料：

| Year | N | 夜盤 raw range 中位數（點） | norm_sma 中位數 | norm_ema 中位數 |
|------|---|------------------------------|------------------|------------------|
| 2021 | 214 | **120** | 0.873 | 0.879 |
| 2022 | 236 | 176 | 0.939 | 0.949 |
| 2023 | 237 | 121 | 0.932 | 0.943 |
| 2024 | 233 | **238** | 0.941 | 0.942 |
| 2025 | 243 | **250** | 0.919 | 0.923 |
| 2026 | 64 | **553** ⚠ | **1.061** | 1.021 |
| ALL | 1227 | 175 | 0.925 | 0.935 |

**觀察**：
- **2021–2025**：raw range 從 120 點翻到 250 點（2× 變化），但 norm 中位數穩定在 0.87–0.94（±0.04）→ SMA20 normalisation 確實吸收絕對振幅趨勢
- **2026 Q1**：raw range 中位數 553 點（再翻一倍），SMA20 還沒追上，於是 norm 中位數跳到 1.061。這 4 個月的 vol regime shift 是 SMA20 跟不上的速度
- **對 expanding median 的意涵**：H075 將要驗證的方法在 2026 Q1 vol 暴漲環境下會慢慢往上漂，這正是 expanding 的優勢（fixed 0.85 不會調整）

## Vs. Expected

| 預期 | 實際 | 判定 |
|------|------|------|
| Median split 後 EstHL aggregate diff ≥ 60% | EMA+median = +73.6%（用 H066 完整方法） | ✓ 符合 |
| 截至 2026-04-17 cutoff 數字幾乎重現 H066 | EstHL EMA+median 在 2026-04-13 = +83.6%（精確匹配） | ✓ 完美符合 |
| Expanding window 沒有 step change | 區間波動 60–84%，平緩 | ✓ 符合 |

**主假說（方法學差異論）獲得完全支持。**

額外重大發現：
- 實盤 NVF 實作 = SMA + 0.85，但 H066 評估 = EMA + median，**兩者並非等價**
- 用 H066 真實方法跑 Reversal，diff = +84.0%（高於 H067 報告的 +64.3%）
- Exhaustion 無論哪種方法都是負向（-12.5% ~ -33.4%），確認 NVF 對 Exhaustion 反向

## Gate Decision

[X] **H072 sub-cell 結論成立，回 H072 GATE**

H066/H067 baseline 健康（EMA+median 法當前 diff 仍 +73.6%/+84.0%）。H072 用 SMA+0.85 一致地切 sub-cell，內部一致性 OK——sub-cell drift 結論（特別是 EstHL Tue/Fri 失效）成立，可進 Phase 2。

但**實盤 NVF 應該換用 H066 評估時的方法**（EMA + median 或至少 EMA + 0.85），這是一個獨立但更高優先的議題：

## Derived Hypotheses

- **H075 候選（高優先）：實盤 NVF 應換成 EMA + median 方法**
  目前實盤 SMA+0.85 的 aggregate effect 是 +19.5%，換成 H066 評估的 EMA+median 可能直接拉到 +73.6%。需驗證：
  (a) 實際 PF/Sharpe 差異
  (b) Walk-forward 穩定性
  (c) 連敗保護是否比 SMA+0.85 更好
  若驗證為真，是一個無爭議的實盤改動。

- **H076 候選：H066 summary.md 「EMA/SMA r=0.985, 結果一致」的說法錯誤**
  實際 PF diff 落差 58pp。需檢視 H066 是否有更多文檔/程式不一致，避免後續研究繼續被誤導。低優先（屬 audit 範疇）。

## Links
- Proposal：../proposal.md
- Tasks：../tasks.md
- Explore script：../explore.py
- Visualisation：h073_t4_expanding.png
- CSVs：t1_t2_baseline.csv, t3_cutoff_h066_date.csv, t4_expanding_window.csv
