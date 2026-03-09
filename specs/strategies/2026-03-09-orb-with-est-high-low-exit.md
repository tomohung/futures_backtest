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

### 4. Estimated H-L 指標（已實作）
- `EmaHL`：20日平均日波動 EMA
- `SatZoneUpper`、`SatZoneLower`：滿足區間邊界
- 來源：`src/backtest/estimate_hl.py` → `compute_estimate_hl_zones()`

---

## 進場

### 開盤區間（Opening Range, OR）
- **時間**：08:45–08:57（含，共 13 根1分K）
- 追蹤 `or_high = max(High[08:45–08:57])`

### 進場窗口
- **時間**：08:58–09:05（共 8 根1分K）
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
# 基本執行（long-only，預設參數）
uv run python src/backtest/run_orb_est_hl.py --start 2025-01-01 --end 2025-12-31

# 含空單
uv run python src/backtest/run_orb_est_hl.py --start 2025-01-01 --short

# 自訂參數
uv run python src/backtest/run_orb_est_hl.py --start 2022-01-01 --sl-fraction 0.20 --bigcost-days 3
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

### 2021–2024（125 筆）
| 項目 | 數值 |
|------|------|
| 勝率 | 58.4% |
| PF | 1.90 |
| 期望值 | +15.5 點／筆 |
| MDD | -0.16% |

### 2025 全年（38 筆）
| 月份 | 筆數 | 勝/敗 | 月損益 | PF |
|------|------|-------|--------|----|
| 01 | 2 | 2/0 | +178 | ∞ |
| 02 | 5 | 3/2 | +97 | 2.59 |
| 03 | 0 | — | — | — |
| 04 | 2 | 1/1 | +139 | 2.56 |
| 05 | 4 | 1/3 | -143 | 0.22 |
| 06 | 5 | 3/2 | +174 | 2.22 |
| 07 | 2 | 1/1 | +68 | 1.99 |
| 08 | 5 | 2/3 | -36 | 0.85 |
| 09 | 4 | 2/2 | +86 | 1.67 |
| 10 | 4 | 2/2 | +108 | 1.72 |
| 11 | 4 | 2/2 | +24 | 1.17 |
| 12 | 1 | 0/1 | -61 | 0.00 |
| **全年** | **38** | **19/19** | **+634** | **1.50** |

### 2026 YTD（截至 2026-03-06，6 筆）
| 月份 | 筆數 | 勝/敗 | 月損益 | PF |
|------|------|-------|--------|----|
| 01 | 4 | 1/3 | +31 | 1.19 |
| 02 | 2 | 2/0 | +252 | ∞ |
| **YTD** | **6** | **3/3** | **+283** | **2.74** |
