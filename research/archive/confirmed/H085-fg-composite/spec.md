# Strategy Spec: TW Fear & Greed Composite (H085-fg-composite)

## Source Hypothesis
H085-fg-composite (Confirmed 2026-05-11)

## Description
4 個非冗餘 fear 指標的 IQR 標準化加總（comp_z），達閾值時逢低買入 0050 含息，
持有 1 年後出場。針對「Tier B 急速 panic」型市場恐慌（COVID 式、關稅式），
平均約 3-4 年觸發一次主要事件。

## Signal Computation

### 4 個輸入指標（H084 確認非冗餘）

| 指標 | 定義 | fear 方向 | 來源 |
|---|---|---|---|
| `vix_pct` | 台指 VIX 過去 1 年 rolling 百分位 | high (sign=+1) | DuckDB `vixtwn` |
| `taiex_dist_125ma_z` | 加權指數距 125MA 的 z-score | low (sign=−1) | TAIEX 250d hist |
| `margin_drop_60d_pct` | 融資餘額過去 60 日 % 變化 | low (sign=−1) | DuckDB `margin_balance` |
| `econ_score` | 景氣對策信號分數 9-45 | low (sign=−1) | DuckDB `econ_signal` |

### 標準化（每指標）

每個指標：
1. fear 方向化：`x_oriented = sign × x`
2. 用過去 5 年（rolling 1250 個交易日，min_periods=250 warmup）：
   - `roll_median = x_oriented.rolling(1250, 250).median()`
   - `roll_q25 = x_oriented.rolling(1250, 250).quantile(0.25)`
   - `roll_q75 = x_oriented.rolling(1250, 250).quantile(0.75)`
   - `roll_iqr = max(roll_q75 - roll_q25, 1e-9)`
3. z 值：`z_i = (x_oriented - roll_median) / roll_iqr`

### 合成

```
comp_z = z_vix_pct + z_taiex_dist_125ma_z + z_margin_drop_60d_pct + z_econ_score
```

## Entry Conditions

每日收盤後檢查：

```
if comp_z[today] >= 3.97
   AND open_positions < 5
   AND days_since_last_entry >= 5:
       BUY 1 unit at today's close
       record (entry_date=today, entry_price=close)
```

`3.97` = IS-fitted threshold (2018-09 ~ 2022-12 期間 comp_z 的 top 10% quantile)

## Exit Conditions

```
for each open position:
    if today_idx - entry_idx >= 250 (trading days):
        SELL at today's close
```

固定 250 個交易日（≈1 年）持有，不停損、不停利。

## Parameters

| Parameter | Value | Sensitivity |
|---|---|---|
| score | comp_z | High (comp_pct rejected) |
| threshold | 3.97 | Low（top 5/10/15/20% Sharpe 1.35–1.99 接近）|
| hold_days | 250 trading days | High（60d Sharpe 大降）|
| max_open | 5 | Low（紀律 C：強 fear 才滿倉）|
| cooldown_days | 5 trading days | Low |
| rolling_window | 1250 trading days (5 yr) | Medium |

## Universe

- 交易標的：**0050.TW**（含息調整收盤；台灣 50 ETF）
- 排除條件：無

## Execution

- 頻率：日 K 級別判斷，每日收盤後計算 comp_z
- 下單時機：當日收盤（或隔日開盤模擬）
- 倉位大小：每筆固定金額（如可用資金 / 5）
- 單筆獨立出場（FIFO 或 trade-by-trade）

## Constraints

- 最大同時持倉：5 倉
- 單筆最大風險：每筆固定 1/5 配置 → 個別倉位最大可能損失 ~25-30%（歷史最差 trade +10.5%，未實現 dd 約 -16%）
- 無加槓桿、無放空、無停損

## Source Code

- Daily monitor：`src/analysis/fg_composite_monitor.py`
- Live backtest：`strategies/live/S004-fg-composite/backtest.py`
- 研究腳本：
  - Phase 1：`research/archive/confirmed/H085-fg-composite/explore.py`
  - Phase 2：`research/archive/confirmed/H085-fg-composite/backtest.py`
  - Phase 2.5（倉位管理）：`research/archive/confirmed/H085-fg-composite/backtest_v2.py`
- Indicator dependencies：H084 build_indicators.py

## Coverage Note

H085 主抓 Tier B 急速 panic 事件（4/8 ≈ 50% hit rate），不覆蓋：
- Tier A 結構熊緩跌（2022-10 主底未命中）
- 大多數 Tier C 標準回檔（H088 處理）

## Operational Notes

- 觸發頻率低（平均 3-4 年 1 次主要 cluster），需配合長期持有耐心
- comp_z 反向時不出場（依固定 250d）— 出場規則升級留待 H088/H089
- 與其他策略（EstHL/Reversal）互補：H085 屬長線資產配置層
