# Strategy Spec: S004-fg-composite

## ID
S004

## Source Hypothesis
H085-fg-composite (`research/archive/confirmed/H085-fg-composite/`)

## Description
TW Fear & Greed Composite — 用 4 個非冗餘 fear 指標的 IQR 標準化加總（comp_z）
判斷市場系統性恐慌期，達閾值時逢低買入 0050 含息調整收盤、持有 1 年後出場。

針對 **Tier B 急速 panic 事件**（COVID 式、貿易戰式、關稅式急殺）。
歷史平均 3-4 年觸發一次主要 cluster。

## Entry Conditions

每日收盤後計算 `comp_z`，當下列條件**全部成立**時收盤買 1 倉：

```
1. comp_z[today] >= 3.97
2. open_positions < 5
3. trading_days_since_last_entry >= 5
```

### `comp_z` 計算

對每個指標 `x` 取得 fear-direction 標準化 z 值：

```
sign:
  vix_pct             → +1
  taiex_dist_125ma_z  → -1
  margin_drop_60d_pct → -1
  econ_score          → -1

x_oriented = sign × x

# 5 年 rolling，warmup 1 年
roll = x_oriented.rolling(window=1250, min_periods=250)
z_i = (x_oriented - roll.median()) / max(roll.quantile(0.75) - roll.quantile(0.25), 1e-9)

comp_z = sum(z_i for i in 4 indicators)
```

## Exit Conditions

```
for each open position:
    if today_idx - entry_idx >= 250 (trading days):
        SELL at today's close
```

固定 250 個交易日（≈1 年）後收盤出場。**無停損、無停利、無時間以外的出場條件。**

## Parameters

| Parameter | Value | Sensitivity |
|---|---|---|
| score | comp_z | High（不可換 comp_pct）|
| threshold | 3.97 | Low |
| hold_days | 250 | High |
| max_open | 5 | Low |
| cooldown_days | 5 | Low |
| rolling_window | 1250 (≈5 yr) | Medium |

## Universe

- 交易標的：**0050.TW**（台灣 50 ETF，含息調整收盤）
- 排除條件：無

## Execution

- 頻率：日 K，每日收盤後計算 comp_z 並判斷進出場
- 下單時機：收盤價（或隔日開盤模擬）
- 倉位大小：**每筆 = 可用資金 / 5**（最大同時 5 倉，全滿時 100% 投入）
- 倉位獨立：每筆獨立記錄進出場日，FIFO 出場

## Constraints

- 最大同時持倉：**5 倉**
- 單筆最大風險：每筆固定 1/5 配置
- 無加槓桿、無放空
- 觸發頻率低（平均 3-4 年 1 次主要 cluster）→ 大部分時間持現金或併用其他策略

## Coverage / Limitation

H085 是 Tier B 急速 panic specialist，**不涵蓋**：
- Tier A 結構熊緩跌（如 2022-10 主底）
- 大多數 Tier C 標準回檔（10-20% drawdown）

策略觸發頻率低 ≠ 失靈，是 by design。

## Source Code

- Backtest：`strategies/live/S004-fg-composite/backtest.py`
- Daily monitor：`src/analysis/fg_composite_monitor.py`
- Indicator build：`research/active/H084-correction-bottom-survey/build_indicators.py`
