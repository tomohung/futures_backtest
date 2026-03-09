# ORB with Estimated H-L Exit Strategy

## 背景與動機
結合 ORB（Opening Range Breakout）進場邏輯與 Estimated H-L Satisfaction Zone 出場機制，
並加入大戶成本過濾、30分K 20MA 方向濾網，以及 9:45 後的 Dow Theory 追蹤停損。

---

## 前置指標

### 1. 30分K 20MA 方向
- 從連續1分K（含夜盤）重採樣為 30分K
- 計算 rolling(20).mean() → `MA30_20`
- 使用最後一根**已收盤**的 30分K（shift(1)，避免 lookahead）
- 判斷方向：`Close30 > MA30_20` → 上升趨勢；`Close30 < MA30_20` → 下降趨勢

### 2. 大戶成本（`BigCost1`, `BigCost2`）
- 每日日盤（08:45–13:45）中，volume ≥ 20MA(volume) 的 bar 才計入
- 大戶成本 = `SUM(close × volume) / SUM(volume)`（篩選後的 VWAP）
- 使用**昨日**（`BigCost1`）與**前日**（`BigCost2`）大戶成本
- 做多：取兩日中**較高者**作為比較基準；做空：取**較低者**

### 3. OR 寬度濾網（`ORWidth`, `RollingOR`）
- `ORWidth`：當日 08:45–08:57 的 H-L 範圍
- `RollingOR`：20日滾動平均 OR 寬度
- 過濾條件：`0.5 × RollingOR ≤ ORWidth ≤ 1.5 × RollingOR`
  - 太窄 → 假突破風險；太寬 → 進場點過遠

### 4. Estimated H-L 指標（已實作）
- `EmaHL`：20日平均日波動 EMA
- `SatZoneUpper`、`SatZoneLower`：滿足區間邊界
- 來源：`src/backtest/estimate_hl.py` → `compute_estimate_hl_zones()`

---

## 進場

### 開盤區間（Opening Range, OR）
- **時間**：08:45–08:57（含，共 13 根1分K）
- 追蹤 `or_high = max(High[08:45–08:57])`，`or_low = min(Low[08:45–08:57])`

### 進場窗口
- **時間**：08:58–09:05（共 8 根1分K）
- 每日最多 1 次進場，第一個觸發訊號優先

### 做多條件（全部成立）
1. Close > or_high（突破開盤區間高點）
2. Close30 > MA30_20（30分K 20MA 上升趨勢）
3. or_high > max(BigCost1, BigCost2) + 0.5 × sl_dist（突破位置高於近兩日大戶成本上緣）
4. 0.5 × RollingOR ≤ ORWidth ≤ 1.5 × RollingOR（OR 寬度正常）

### 做空條件（全部成立）
1. Close < or_low（跌破開盤區間低點）
2. Close30 < MA30_20（30分K 20MA 下降趨勢）
3. or_low < min(BigCost1, BigCost2) - 0.5 × sl_dist（跌破位置低於近兩日大戶成本下緣）
4. 0.5 × RollingOR ≤ ORWidth ≤ 1.5 × RollingOR（OR 寬度正常）

> **BigCost 為 NaN**（資料不足）時：略過大戶成本濾網，仍可進場。
> **RollingOR 為 NaN**（warmup 不足）時：略過 OR 寬度濾網。

---

## 出場（優先順序由高至低）

### 1. 固定停損（SL）
- `sl_dist = 0.25 × EmaHL`（進場當根的 EmaHL 值）
- 做多：`sl_price = entry_price - sl_dist`；做空：`sl_price = entry_price + sl_dist`
- 每根 K 線：若 Close 穿越 sl_price → 出場

### 2. SatZone 兩段式出場
- 觸及 `SatZoneUpper`（做多）或 `SatZoneLower`（做空）後標記
- 標記後，1分K 5MA 反轉 → 出場
- 實作：`EstimateHLExitMixin._record_bar()` + `_check_long/short_exit()`

### 3. Dow Theory 追蹤停損（9:45 後啟動）
- **啟動時間**：09:45（日盤開始後第 60 分鐘）
- **Pivot Lookback Period = 5**（5根1分K視窗）
- Pivot 確認：bar(i-2) 是 pivot low 當且僅當 `low[i-2] == min(low[i-4:i+1])`
  （需等 2 根 K 通過才能確認，無 lookahead）
- 做多：追蹤最新確認的 pivot low 作為停損線；Close < dow_trail_stop → 出場
- 做空：追蹤最新確認的 pivot high；Close > dow_trail_stop → 出場

### 4. 強制平倉
- 時間：**13:30**（不管任何條件，強制出場）

---

## 實作檔案

| 檔案 | 說明 |
|------|------|
| `src/backtest/estimate_hl.py` | EmaHL / SatZone 計算 |
| `src/strategies/estimate_hl_exit.py` | SatZone 兩段式出場 Mixin |
| `src/strategies/orb_est_hl_exit.py` | `ORBWithEstHLExitStrategy` |
| `src/backtest/runner.py` | `load_data_for_orb_est_hl()` |
| `src/backtest/run_orb_est_hl.py` | 獨立執行腳本 |

```bash
uv run python src/backtest/run_orb_est_hl.py --start 2025-01-01 --end 2025-12-31
uv run python src/backtest/run_orb_est_hl.py --start 2026-01-01
```

---

## 濾網實驗紀錄（2025 全年）

基準：BigCost max/min 兩日 + ½ SL 閾值

| 濾網 | 筆數 | PF | 期望值 | 結果 |
|------|------|----|--------|------|
| 基準 | 71 | 1.02 | +0.6 點 | — |
| + R/R ≥ 1.5（SatZone） | 51 | 0.79 | -9.7 點 | ❌ 拿掉（SatZone 近反而是好訊號）|
| + OR 寬度 0.5~1.5× | 58 | **1.22** | +7.8 點 | ✅ 保留 |
| + 夜盤方向對齊 | 44 | 1.03 | +1.1 點 | ❌ 拿掉（30m MA 已涵蓋方向資訊）|
| + 跳空 >0.5 EmaHL 跳過 | 24 | 0.51 | -20.5 點 | ❌ 拿掉（跳空日是 ORB 好機會）|

**最終採用**：BigCost max/min + ½ SL + OR 寬度 0.5~1.5×

---

## 回測結果

### 2025 全年（58 筆）

| 項目 | 數值 |
|------|------|
| 總交易次數 | 58 筆 |
| 做多 / 做空 | 38 / 20 筆 |
| 勝率 | 48.3% |
| 平均獲利 | +91 點 |
| 平均虧損 | -70 點 |
| 獲利因子 (PF) | 1.22 |
| 最大連續虧損 | 4 筆 |
| 最大回撤 | -0.19% |
| 期望值 | +7.8 點／筆 |
| 年度累計 | **+454 點** |

#### 2025 逐月

| 月份 | 筆數 | 勝/敗 | 勝率 | 月損益 | PF |
|------|------|-------|------|--------|----|
| 01 | 3 | 3/0 | 100% | +227 | ∞ |
| 02 | 8 | 5/3 | 62% | +100 | 1.83 |
| 03 | 3 | 2/1 | 67% | +30 | 1.41 |
| 04 | 5 | 2/3 | 40% | -12 | 0.96 |
| 05 | 4 | 1/3 | 25% | -143 | 0.22 |
| 06 | 7 | 4/3 | 57% | +134 | 1.60 |
| 07 | 3 | 2/1 | 67% | +197 | 3.86 |
| 08 | 7 | 2/5 | 29% | -124 | 0.62 |
| 09 | 6 | 3/3 | 50% | +236 | 2.21 |
| 10 | 5 | 2/3 | 40% | +15 | 1.06 |
| 11 | 5 | 2/3 | 40% | -70 | 0.71 |
| 12 | 2 | 0/2 | 0% | -136 | 0.00 |

### 2026 YTD（截至 2026-03-06，9 筆）

| 項目 | 數值 |
|------|------|
| 總交易次數 | 9 筆 |
| 做多 / 做空 | 6 / 3 筆 |
| 勝率 | 55.6% |
| 平均獲利 | +173 點 |
| 平均虧損 | -70 點 |
| 獲利因子 (PF) | 3.12 |
| 最大回撤 | -0.14% |
| 期望值 | +65.3 點／筆 |
| YTD 累計 | **+588 點** |

#### 2026 逐月

| 月份 | 筆數 | 勝/敗 | 勝率 | 月損益 | PF |
|------|------|-------|------|--------|----|
| 01 | 5 | 2/3 | 40% | +217 | 2.33 |
| 02 | 4 | 3/1 | 75% | +371 | 4.23 |
| 03 | 0 | — | — | — | — |
