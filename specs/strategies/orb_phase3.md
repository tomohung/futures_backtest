# ORB Phase 3：動態 SL/TP 優化

## Phase 2 結論

最佳參數：`range_end=90, entry_end=120, sl_pct=0.005, tp_multiplier=1.5, trail=45, trend_ma=10`

| 指標 | 整體 | 做多 | 做空 |
|---|---|---|---|
| 交易筆數 | 100 | 65 | 35 |
| 勝率 | 62.0% | 66.2% | 54.3% |
| 獲利因子 | 2.13 | 2.78 | 1.33 |
| 期望值 | +35.1 pts | +47.0 pts | +13.1 pts |
| 最大回撤 | -374 pts | -276 pts | -359 pts |

### 關鍵發現：13:30 強制出場佔 41%

| 出場類型 | 筆數 | 勝率 | 平均獲利 |
|---|---|---|---|
| 13:30 強制出場 | 41 | 92.7% | +58.5 pts |
| SL/TP 出場 | 59 | 40.7% | +18.8 pts |

**根本問題**：`tp_multiplier=1.5` 太小，趨勢強的日子過早出場；真正跑出大行情的單子靠 13:30 收割，而非主動管理。目標是讓趨勢日有更大的獲利空間。

---

## 策略核心思想

9:30 突破新高/低 = 當日趨勢方向確認，期待 higher high / lower low。
進場後應讓趨勢跑，**不應設固定 TP 過早鎖利**。

---

## 方向 A：OR 寬度動態 SL/TP

用開盤區間（OR）的寬度作為 SL 和 TP 的基準，讓風險管理跟當天的市場結構掛鉤。

### SL 設計
- 做多：SL = OR low（突破失效 = 跌回 OR 內）
- 做空：SL = OR high
- 邏輯：比固定百分比更有結構意義；OR 窄的日子 SL 小，OR 寬的日子 SL 大

### TP 設計
- TP = 進場價 ± N × OR 寬度
- N 為待優化參數（如 1.5、2.0、2.5、3.0）
- 波動大的日子 OR 寬 → TP 距離更遠，讓獲利空間與動能成比例

### Trailing Stop
- 改用「跌破前 N 根 K 棒低點（做多）/ 高點（做空）」
- 比固定百分比更跟價格結構走

### 優化參數
| 參數 | 測試值 |
|---|---|
| `tp_or_multiplier` | 1.5, 2.0, 2.5, 3.0 |
| `trail_bars` | 3, 5, 10（trailing stop 回看 N 根） |

### 注意事項
- OR 很寬的日子 SL 距離大，固定 size=1 的風險不一樣 → Phase 3 先不做 position sizing，記錄 OR 寬度分布後再考慮

---

## 方向 B：Super Trend 出場

用 Super Trend 指標取代固定 SL/TP，讓指標決定何時趨勢結束。

### 概念
- Super Trend = ATR-based trailing stop，動態跟隨價格
- 做多持倉：價格跌破 Super Trend 線 → 出場
- 做空持倉：價格漲破 Super Trend 線 → 出場
- 不設固定 TP，讓趨勢跑到反轉

### 參數
- `atr_period`：ATR 計算週期（常用 7, 10, 14）
- `atr_multiplier`：帶狀寬度倍數（常用 2.0, 3.0）

### 優化參數
| 參數 | 測試值 |
|---|---|
| `atr_period` | 7, 10, 14 |
| `atr_multiplier` | 2.0, 2.5, 3.0 |

### 注意事項
- Super Trend 在 backtesting.py 裡需要用 `self.I()` 自行實作（無內建）
- ATR 需要足夠的歷史 bar 做 warmup
- 進場 SL 仍建議保留（OR low/high），Super Trend 只負責出場

---

## 測試計畫

1. 先跑方向 A（OR-based SL/TP）
2. 再跑方向 B（Super Trend）
3. 比較兩者在相同 train/test 分割下的結果

### Train / Test 分割
- Train：2025-01-01 ~ 2025-12-31
- OOS Test：2026-01-01 ~

### 成功標準（同 Phase 2）
| 指標 | Train 目標 | OOS 門檻 |
|---|---|---|
| 勝率 | ≥ 52% | ≥ 50% |
| 平均盈虧比 | ≥ 1.3 | — |
| 獲利因子 | ≥ 1.2 | ≥ 1.0 |

額外關注：13:30 強制出場比例應下降（代表策略主動管理出場）。

---

## 固定參數（沿用 Phase 2 最佳值）

| 參數 | 值 |
|---|---|
| `range_end_minute` | 90 |
| `entry_end_minute` | 120 |
| `trail_activate_minute` | 45 |
| `trend_ma_days` | 10 |
