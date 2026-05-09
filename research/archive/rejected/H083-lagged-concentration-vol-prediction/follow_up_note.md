# H083 Follow-up Note: 與夜盤訊號的比較與 reject 決定

**日期**：2026-05-09
**最終狀態**：**REJECTED** — 集中度對既有夜盤 vol 訊號在 vol prediction 兩個關鍵 metric（振幅 mean、reach rate）上都無顯著獨立增量。

## 起因

User 在 H083 proposal 寫好之後，提出新問題：
> 之前研究過夜盤的振幅和接下來的日盤有相關性。那夜盤振幅跟集中度哪個對當天日振幅相關性比較大？又或者兩者可以互補？交集時預測性更高？

跑了一次性探索（`explore_night_vs_concentration.py`）比較兩者，並重看既有 NVF 研究脈絡，得出**暫停 H083 純集中度版本**的決定。

## 探索結果（n=898 個交易日，2020-12 ~ 2026-05）

### Univariate correlation 對 t 日盤振幅
- corr(dev_lag1, d_range) = **+0.18**
- corr(n_range, d_range) = **+0.49** ← 夜盤振幅遠強
- corr(dev_lag1, n_range) = +0.20（兩訊號間，大部分獨立）

### OLS 比較
| 模型 | dev_lag1 t | n_range t | R² |
|---|---|---|---|
| dev_lag1 only | 5.42 | — | 0.0318 |
| **n_range only** | — | **16.62** | **0.2356** |
| joint (兩個) | 2.85 | 15.78 | 0.2424 |

**結論**：
- 夜盤振幅是壓倒性主導 (R² 0.236 vs 集中度 0.032，差 7 倍)
- 集中度在 joint model 中 t=2.85 (p<0.005) 統計顯著，但**實質增量 R² 只 +0.0069**

### 5×5 雙桶矩陣 d_range mean (%)
```
                夜盤振幅 →
集中度↓        N1      N2      N3      N4      N5
D1            0.88    0.87    1.05    1.17    1.45
D2            0.81    1.03    1.03    1.16    1.44
D3            0.92    0.92    1.09    1.22    1.64
D4            0.89    1.12    1.11    1.15    1.59
D5            0.93    1.14    1.11    1.43    1.88   ← 雙重高
```

baseline 1.17%。

### 四個極端格
| 組合 | n | d_range | vs baseline |
|---|---|---|---|
| 雙重高 D5×N5 | 55 | 1.88% | 1.61x |
| 集中低夜盤高 D1×N5 | 20 | 1.45% | 1.24x |
| 集中高夜盤低 D5×N1 | 21 | 0.93% | 0.79x |
| 雙重低 D1×N1 | 60 | 0.88% | 0.75x |

### 關鍵 pattern
1. **夜盤 dominant**：N 維度差異大（N1 0.88% → N5 1.50%+，+70%），D 維度差異小（±5–15%）
2. **集中度只在夜盤高時放大**：D5×N5 vs D1×N5 = +30%；D5×N1 vs D1×N1 ≈ 0
3. **集中度高 + 夜盤低 = 中和**：D5×N1 ≈ baseline

## 與既有 NVF 研究的衝突

H070 (`night-vol-estrange-reach`, confirmed) 已測過用夜盤訊號做**連續倍數調整**：
- Phase 1：夜盤 norm 對 EstRange 觸及率 R²=0.097（顯著）
- Phase 2：嘗試把夜盤訊號變成 SatZone 縮放倍數 → **無策略增益**
- 結論：「現有規則（星期 + NVF 硬規則）維持不變」

H075 (`nvf-method-upgrade`, confirmed) 已將 NVF 從 SMA20+0.85 升級為 EMA20+expanding median，作為 EstHL（S001）+ Reversal（S002）的 production binary filter。

## 為何暫停 H083

| | H070 已測 | H083 想做 |
|---|---|---|
| 訊號 | 夜盤 norm | 集中度 dev_lag1 |
| 設計 | SatZone 連續縮放 | EstHL 倍數連續調整 |
| Phase 1 R² | 0.097 | 0.032（更弱） |
| Phase 2 預期 | 已證無效 | 大概率重複無效 |

H083 純集中度版本在「研究設計」上是 H070 negative finding 的重演，且訊號更弱。直接執行 Phase 1 / Phase 2 預期得到 inconclusive。

## 重啟條件

H083 不是永久 reject，而是等到有 differentiated 設計再啟動。可能的方向：

### Direction A：集中度作為 NVF binary filter 的補充
- 把集中度也轉為 binary（threshold-based）
- 看是否與既有 NVF 互補：兩者都 pass 才交易、或 NVF fail 但集中度 pass 時挽救
- 不踩 H070 「縮放」的負面結果

### Direction B：聚焦極端格交易（不是縮放）
- D5×N5 雙重高（n=55，d_range mean 1.88%，baseline 1.6x）
- 這類日子加大倉位（不是縮放振幅倍數）
- 樣本邊緣，permutation test 是必要的

### Direction C：條件性（only Tue/Wed）
- H080 顯示集中度的 weekday-conditional 訊號在 Tue/Wed 最強
- 純集中度 + Tue/Wed limit 可能繞過「全天候縮放」的 H070 失敗模式

執行任一 direction 前，先重寫 proposal，明確跟 H070 的差異點與 differentiated value。

## 補充探索：集中度對 EstRange 觸及率的影響（2026-05-09 後續）

User 提出新問題：「集中度高的時候，能不能更常觸及 1× EstRange？」執行 `explore_concentration_reach.py` 驗證。

### EstRange 定義（沿用 H070）
- `ema_hl[t]` = EMA20 of `day_hl`, shifted 1
- `hl_ratio[t]` = `day_hl[t] / ema_hl[t]`
- `reach_1x` = `hl_ratio >= 1.0`

### 集中度單變量 → P(reach 1x)
| 集中度桶 | n | P(reach 1x) |
|---|---|---|
| D1 | 180 | 37.2% |
| D2 | 179 | 35.8% (非單調，比 D1 低) |
| D3 | 180 | 39.4% |
| D4 | 179 | 41.9% |
| D5 | 180 | **49.4%** |

baseline 40.8%。D5/D1 = +12 pp，但**非單調**。

### 夜盤單變量（對照）
| 夜盤桶 | n | P(reach 1x) |
|---|---|---|
| N1 | 180 | 32.2% |
| N5 | 180 | **60.0%** |

N5/N1 = +27.8 pp，**強 2.3 倍且單調**。

### OLS 比較
| 模型 | dev t | night t | R² |
|---|---|---|---|
| dev only | 3.96 | — | 0.017 |
| night only | — | 11.30 | **0.125** |
| joint | **1.60** ⚠️ | 10.62 | 0.127 |

**joint model 中 dev_lag1 t-stat 從 3.96 → 1.60，p ≈ 0.11 邊緣不顯著。增量 R² 只 +0.0025**。

### 5×5 矩陣 P(reach 1x) % 關鍵格
- 雙重高 D5×N5：60.7% (n=61)
- **集中低夜盤高 D1×N5：58.6% (n=29)** ← 跟雙重高幾乎一樣
- 集中高夜盤低 D5×N1：38.9% (n=18) ← 集中度高無法救觸及率
- 雙重低 D1×N1：39.6% (n=53)

→ **集中度只在夜盤已經高的日子提供 +2 pp 微小補強，在夜盤低的日子完全無效**。

## Reject 的證據鏈

### 三條獨立證據都指向同一結論

1. **振幅預測（之前已測）**：集中度 joint t=2.85 顯著但增量 R² 只 +0.007
2. **觸及率預測（本次測）**：集中度 joint t=1.60 邊緣不顯著，增量 R² +0.0025
3. **H070 negative finding**：用夜盤 vol 連續縮放 SatZone 的 Phase 2 已證無效；集中度版本是更弱的重演

### 為何是 rejected 不是 inconclusive
- **inconclusive** 適用「結果不明確、可能未來重新探索」
- 本研究**不是不明確** — 兩個 metric 都顯示集中度對既有夜盤訊號無實質增量，conditional t-stat 接近不顯著
- 即使未來想到「differentiated 設計」，那會是新假設（HXXX），不是 H083 重啟
- Reject 並不否定 H080（同期相關 indicator） — 只否定「將集中度當作獨立的 vol predictor」這個 H083 假設核心

## 已執行
- `explore_night_vs_concentration.py`：振幅 mean 比較
- `explore_concentration_reach.py`：reach rate 比較
- 兩支腳本保留作為 reject 證據與未來防誤

## 未執行（且不再執行）
- Phase 1 正式 explore（無此必要 — 證據已收斂）
- Phase 2 backtest（H070 已證類似設計無效）
- Phase 1.5 即時資料管線（不為 H083 建，但可為其他研究建）
