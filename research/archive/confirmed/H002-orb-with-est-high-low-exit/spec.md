# ORB with Estimated H-L Exit Strategy

## 背景與動機
結合 ORB（Opening Range Breakout）進場邏輯與 Estimated H-L Satisfaction Zone 出場機制，
並加入大戶成本過濾、30分K 20MA 方向濾網，以及 9:45 後的 Dow Theory 追蹤停損。
只做多（long-only）。

---

## 前置指標

### 1. 30分K 20MA 方向
- 從連續1分K（含夜盤）重採樣為 30分K
- 計算 rolling(20).mean() → `MA30_20`
- 使用最後一根**已收盤**的 30分K（shift(1)，避免 lookahead）
- 判斷方向：`Close30 > MA30_20` → 上升趨勢

### 2. 大戶成本（`BigCost1`–`BigCost5`）
- 每日日盤（08:45–13:45）中，volume ≥ 20MA(volume) 的 bar 才計入
- 大戶成本 = `SUM(close × volume) / SUM(volume)`（篩選後的 VWAP）
- 預載最近 5 日（`BigCost1`=昨日 … `BigCost5`=五日前）
- 進場時取前 N 日（預設 N=2）中的**最大值**作為比較基準

### 3. OR 寬度濾網（`ORWidth`, `RollingOR`）
- `ORWidth`：當日 08:45–08:57 的 H-L 範圍
- `RollingOR`：20日滾動平均 OR 寬度
- 過濾條件：`0.5 × RollingOR ≤ ORWidth ≤ 1.5 × RollingOR`

### 4. Estimated H-L 指標（已改用 EstRange EMA）
- `EmaHL`：由 `EstRange_Daily` 替換 — 前一日 EMA(20) of daily range，固定全天（用於 SL）
- `SatZoneUpper`、`SatZoneLower`：由 `EstRange_SatUpper/Lower` 替換 — 日內每 5 分鐘按量更新
- 來源：`src/backtest/estimate_hl.py` → `compute_vol_estimated_range()`
- 舊版使用 `compute_estimate_hl_zones()` + 硬編碼 `TIME_FACTORS` 表，已被取代（2026-03-16）

---

## 進場

### 開盤區間（Opening Range, OR）
- **時間**：08:45–08:57（含，共 13 根1分K）
- 追蹤 `or_high = max(High[08:45–08:57])`

### 進場窗口
- **時間**：08:58–09:15（共 18 根1分K）
- 每日最多 1 次進場

### 做多條件（全部成立）
1. Close > or_high（突破開盤區間高點）
2. Close30 > MA30_20（30分K 20MA 上升趨勢）
3. or_high > max(BigCost1, BigCost2) + 0.5 × sl_dist（突破位置高於大戶成本上緣）
4. 0.5 × RollingOR ≤ ORWidth ≤ 1.5 × RollingOR（OR 寬度正常）

> BigCost / RollingOR 為 NaN 時略過對應濾網。

---

## 出場（優先順序由高至低）

### 1. 固定停損（SL）
- `sl_dist = sl_ema_fraction × EmaHL`（預設 0.25）
- `sl_price = entry_price - sl_dist`
- Close < sl_price → 出場

### 2. SatZone 兩段式出場
- Phase 1：High ≥ SatZoneUpper → 標記觸及
- Phase 2：觸及後，Close < 5MA → 出場
- 實作：`EstimateHLExitMixin`

### 3. Dow Theory 追蹤停損（9:45 後啟動）
- 5根1分K視窗，2根確認延遲
- Pivot low：`low[i-2] == min(low[i-4:i+1])`
- 更新 `dow_trail_stop = max(已確認 pivot lows)`
- Close < dow_trail_stop → 出場

### 4. 強制平倉
- 時間：**13:30**

---

## 策略參數

| 參數 | 預設值 | 說明 |
|------|--------|------|
| `sl_ema_fraction` | 0.25 | SL 距離 = 倍數 × EmaHL |
| `bigcost_days` | 2 | 大戶成本回看天數（1–5） |
| `long_only` | True | 只做多 |
| `adx_min` | 0.0 | 最低 ADX14（0 = 停用） |
| `or_end_min` | 537 | OR 結束時間（分鐘自午夜起算，537 = 8:57） |
| `entry_end_min` | 555 | 進場窗口截止（分鐘自午夜起算，555 = 9:15） |
| `skip_thursday` | **True** | 週四不進場（WR 42%，-164 pts，詳見星期效應分析） |
| `skip_friday` | **True** | 週五不進場（WR 23%，-935 pts，最差星期日） |

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
# 基本執行（long-only，預設參數，自動跳過週四/五）
uv run python src/backtest/run_orb_est_hl.py --start 2025-01-01 --end 2025-12-31

# 含空單
uv run python src/backtest/run_orb_est_hl.py --start 2025-01-01 --short

# 自訂參數
uv run python src/backtest/run_orb_est_hl.py --start 2022-01-01 --sl-fraction 0.20 --bigcost-days 3

# 停用星期濾網（回到原始行為）
uv run python src/backtest/run_orb_est_hl.py --start 2021-01-01 --no-skip-thursday --no-skip-friday
```

---

## 濾網實驗紀錄

### 含空單 vs 只做多（2025）
| 組合 | 筆數 | PF | 期望值 |
|------|------|----|--------|
| 多+空 | 58 | 1.22 | +7.8 點 |
| **只做多** ✅ | **38** | **1.50** | **+16.7 點** |
| 只做空 | 20 | 0.78 | -9.0 點 |

### 進場濾網測試（2025，只做多）
| 濾網 | 筆數 | PF | 期望值 | 結果 |
|------|------|----|--------|------|
| 基準（BigCost 2日 max+½SL） | 71 | 1.02 | +0.6 點 | — |
| + OR 寬度 0.5~1.5× | 58 | 1.22 | +7.8 點 | ✅ 保留 |
| + R/R ≥ 1.5（SatZone） | 51 | 0.79 | -9.7 點 | ❌ |
| + 夜盤方向 | 44 | 1.03 | +1.1 點 | ❌ |
| + 跳空過濾 | 24 | 0.51 | -20.5 點 | ❌ |
| + ADX > 20 | 31 | 0.78 | -10.7 點 | ❌ |

### BigCost 天數（2025，只做多）
| 天數 | 筆數 | PF | 期望值 |
|------|------|----|--------|
| 1 日 | 53 | 1.31 | +10.8 點 |
| **2 日** ✅ | **38** | **1.50** | **+16.7 點** |
| 3 日 | 28 | 1.53 | +16.3 點 |
| 5 日 | 21 | 1.16 | +5.6 點 |

### SL 倍數測試（三個時段）
| SL 倍數 | 2021–24 PF | 2021–24 EV | 2025 PF | 2025 EV | 2026 PF | 2026 EV |
|---------|-----------|-----------|---------|---------|---------|---------|
| 0.10 | 1.39 | +5.8 | 1.42 | +10.9 | 3.43 | +52.7 |
| 0.15 | 1.60 | +9.9 | 1.18 | +5.9 | 2.97 | +49.3 |
| 0.20 | 1.87 | +14.3 | 1.59 | +18.1 | 2.28 | +41.7 |
| **0.25** ✅ | **1.90** | **+15.5** | 1.50 | +16.7 | **2.74** | **+47.2** |
| 0.30 | 1.92 | +16.2 | 1.26 | +10.4 | 2.74 | +47.2 |
| 0.40 | 1.88 | +16.0 | 1.45 | +16.6 | 1.29 | +10.6 |
| 0.50 | 1.73 | +14.1 | 1.59 | +20.8 | 1.29 | +10.6 |

**結論**：0.25 三個時段均表現穩定，無明顯偏科。

---

## 最終回測結果

> 參數：`sl_ema_fraction=0.25`, `bigcost_days=2`, `long_only=True`, `or_end_min=537`, `entry_end_min=555`
> **`skip_thursday=True`, `skip_friday=True`**（2026-03-12 加入）
> loader：`load_data_for_orb_est_hl()`（含 EstRange EMA 替換 EmaHL/SatZone，2026-03-16 更新）

### 年度總覽（含星期濾網，EstRange EMA）

| 年份 | 筆數 | 勝率 | PF | 期望值 | 總損益 |
|------|------|------|----|--------|--------|
| 2021 | 43 | 51.2% | 1.50 | +11.8 pts | +508 |
| 2022 | 29 | 65.5% | 2.75 | +22.5 pts | +653 |
| 2023 | 27 | 55.6% | 1.94 | +13.3 pts | +359 |
| 2024 | 28 | 64.3% | 2.74 | +38.3 pts | +1072 |
| 2025 | 27 | 59.3% | 3.09 | +52.3 pts | +1411 |
| 2026 YTD | 8 | 62.5% | 3.87 | +83.9 pts | +671 |
| **2021–2026** | **162** | **58.6%** | **2.42** | **+28.9 pts** | **+4674** |

Sharpe: 5.12 | MaxDD: -0.2% | Max consec losses: 5
Avg win: +83.9 pts | Avg loss: -50.0 pts | Win/Loss: 1.68

### EstRange EMA vs EmaHL 比較（2026-03-16 測試）

| 模式 | Total | PF | EV | Sharpe | 說明 |
|------|-------|-----|-----|--------|------|
| EmaHL (TIME_FACTORS) | +4240 | 2.40 | +26.2 | ~4.5 | 舊版，硬編碼 15 分鐘比例表 |
| **EstRange EMA** ✅ | **+4674** | **2.42** | **+28.9** | **5.12** | 新版，實際量 EMA，5 分鐘更新 |

改善 +434 點（+10%）。EmaHL 用 `EstRange_Daily`（前一天固定值）替換，SatZone 用 `EstRange_SatUpper/Lower`（日內量更新）替換。

### 星期濾網效果比較（2021–2026）

| 設定 | 筆數 | 勝率 | PF | EV/筆 | 總損益 |
|------|------|------|----|-------|--------|
| Baseline（無濾網） | 246 | 55.7% | 1.73 | +15.1 pts | +3,720 |
| Skip Thu | 202 | 58.4% | 1.90 | +17.3 pts | — |
| Skip Fri | 205 | 59.0% | 2.10 | +20.8 pts | — |
| **Skip Thu + Fri** ✅ | **161** | **63.4%** | **2.53** | **+25.1 pts** | **+4,034** |

---

## EmaHL bfill 說明

`compute_estimate_hl_zones()` 的 slot 設計：8:45–8:59 bar 全屬於 `08:45` slot，
EmaHL 要到 9:00 才廣播（slot 切換時）。但 9:00 bar 的 EmaHL 是**純前日 EMA**，
不含當日盤中資料，因此對 8:58/8:59 bar 執行 bfill 不會 lookahead。

`load_data_for_orb_est_hl()` 已在 date filter 前加入：
```python
for col in ["EmaHL", "EmaVol", "SatZoneUpper", "SatZoneLower", ...]:
    df_day[col] = df_day.groupby(df_day.index.normalize())[col].transform(
        lambda s: s.bfill()
    )
```

### 進場窗口探索結果（2026-03-10）

OR_END 固定 8:57，entry_end 和 EmaHL bfill 影響：

| entry_end | EmaHL | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | TOTAL |
|-----------|-------|------|------|------|------|------|------|-------|
| 9:05（舊）| NaN guard | +404 | +445 | +317 | +774 | +634 | +283 | +2857 |
| 9:05 | bfill | +469 | +480 | +399 | +817 | +765 | +313 | +3243 |
| 9:10 | bfill | +486 | +635 | +579 | +981 | +592 | +194 | +3467 |
| **9:15** ✅ | **bfill** | **+535** | **+831** | **+542** | **+1153** | **+542** | **+117** | **+3720** |

OR 長度探索（entry_end 固定 9:15，bfill）：

| OR_END | Entry_Start | TOTAL |
|--------|------------|-------|
| 8:49 | 8:50 | +2604 |
| 8:50 | 8:51 | +2562 |
| 8:51–8:54 | 8:52–8:55 | +3040–+3272 |
| 8:55 | 8:56 | +3453 |
| 8:56 | 8:57 | +3539 |
| **8:57** ✅ | **8:58** | **+3720** |

**結論**：OR 長度越長越好（8:45~8:57 = 13 bars），不值得縮短。

---

## 星期效應分析（2026-03-12）

### 各星期幾表現（2021–2026，未過濾）

| 星期 | 筆數 | 勝率 | 平均損益 | 總損益 |
|------|------|------|----------|--------|
| 週一 | 28 | 71.4% | +35.0 | +981 |
| 週二 | 26 | 69.2% | +28.2 | +734 |
| 週三 | 42 | 69.0% | +38.4 | +1,612 |
| **週四** | **26** | **42.3%** | **-6.3** | **-164** |
| **週五** | **22** | **22.7%** | **-42.5** | **-935** |

### 週四深度分析

- OR% 高度集中於 < 0.3%（19/26 筆），無法用 OR% 區分好壞。
- SatZone 距離（進場距滿足區 / EmaHL）有些訊號：≥ 1.0x 的 2 筆結果為 +112，但樣本太少不足信任。
- **結論：整體跳過**

### 週五深度分析

- 22 筆全集中於 OR% < 0.5%、SatZone 距離 < 1.0x EmaHL。
- 任何條件切割均為負結果，無可救之處。
- **結論：整體跳過**

### 決策

`skip_thursday=True, skip_friday=True` 設為預設值（2026-03-12 起）。
週四/五若未來累積足夠樣本，可重新評估 SatZone 距離 ≥ 1.0x EmaHL 作為週四條件。
