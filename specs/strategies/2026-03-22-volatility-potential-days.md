# 波動潛力日分析工具

## 背景與動機

目前有 EstHL、ORBLong、Reversal 等策略，但不知道：
- 哪些日子有足夠的波動卻沒被任何策略捕捉
- 波動主要集中在什麼時段（早盤？午盤？）
- 這些「潛力日」的共同特徵是什麼

**第一步先不管策略**，純粹從市場資料找出「值得交易的日子」並分類。策略 capture 分析之後再疊加。

## 每日波動指標

從 `ohlcv_1m` 計算：

| 指標 | 說明 |
|------|------|
| day_open | 日盤開盤價 |
| day_high | 日盤最高價 |
| day_low | 日盤最低價 |
| day_close | 日盤收盤價 |
| day_range | day_high - day_low |
| range_pct | day_range / day_open × 100 |
| direction | UP / DOWN |
| volume | 日盤總成交量 |
| oc_pct | (day_close - day_open) / day_open × 100 |

## 潛力日篩選

兩種門檻並列：

| 門檻 | 定義 | 用途 |
|------|------|------|
| P67 | 當年 range_pct 前 1/3 | 相對標準，適應不同波動環境 |
| Fixed 0.8% | range_pct >= 0.8% | 絕對標準，跨年度可比 |

## 時段分析（4 個時段）

| 時段 | 時間 | 對應策略窗口 |
|------|------|------------|
| MorningEarly | 08:45~10:00 | ORB/EstHL 進場區 |
| MorningLate | 10:00~11:00 | 趨勢延伸區 |
| Midday | 11:00~12:00 | 通常較沉悶 |
| Afternoon | 12:00~13:45 | 反轉/收盤行情 |

每時段計算**邊際波幅**（running H/L 增量）和**邊際佔比**。

## 潛力日分類

| 類型 | 定義 | 含義 |
|------|------|------|
| EarlyTrend | MorningEarly >= 50% | 早盤就走出方向 |
| LateTrend | MorningLate >= 40% | 10 點後才啟動 |
| Afternoon | Afternoon >= 40% | 午後行情 |
| Spread | 沒有任何時段 >= 40% | 波動分散全天 |

## 輸出

- **Terminal 報表**：類型分佈、時段佔比、年度趨勢、近 N 日明細
- **CSV**：`output/volatility_potential_days.csv`

## 實作順序

1. 實作 `src/analysis/volatility_capture.py`

## 關鍵參考檔案

- `src/analysis/intraday_swing_research.py` — 邊際波幅演算法
- `src/analysis/regime_health.py` — DuckDB 連線模式
- `src/analysis/daily_range.py` — 報表輸出格式
