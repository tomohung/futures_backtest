# Performance Log: S004-fg-composite

## Backtest Summary（定案版本，V1 倉位管理）

| Metric | IS (2018-09 ~ 2022-12) | OOS (2023-01 ~ 2026-04)* | FULL (2018-09 ~ 2026-04) |
|---|---:|---:|---:|
| Sharpe Ratio | 1.83 | 3.65 | **2.10** |
| Total Trades | 10 | 2 | 15 |
| Win Rate | 100% | 100% | **100%** |
| Median Return | +45.5% | +123.3% | +26.3% |
| Mean Return | +52.1% | +123.3% | +55.0% |
| CAGR | 32.9% | 131.8% | 26.2% |
| Max Drawdown | −16.6% | −10.8% | −20.8% |
| Final Equity (per $1) | 2.06× | 2.40× | 5.80× |

*OOS 期理論 5 trades，但 2026-04-30 資料截止限制 → 4/22+ 進場 exit 超出資料邊界、僅 2 筆顯示

### vs Baselines (FULL period)

| Strategy | Sharpe | MaxDD | Final Equity |
|---|---:|---:|---:|
| **S004 (V1)** | **2.10** | **−20.8%** | **5.80×** |
| DCA monthly 250d | 1.0 | −34% | ~3.8× |
| 0050 Buy-and-Hold | 1.0 | −34% | ~5.5× |

## Trade-by-Trade Detail (FULL period, 15 trades, 全勝)

| # | Entry | Entry $ | Exit | Exit $ | Return | comp_z | Event |
|--:|---|---:|---|---:|---:|---:|---|
| 1 | 2018-10-05 | 16.39 | 2019-10-22 | 18.11 | +10.5% | 5.20 | 2018 貿易戰 |
| 2 | 2018-10-15 | 15.55 | 2019-10-29 | 18.27 | +17.4% | 8.73 | |
| 3 | 2018-10-22 | 15.55 | 2019-11-05 | 18.97 | +22.0% | 8.71 | |
| 4 | 2018-10-29 | 14.88 | 2019-11-12 | 18.79 | +26.3% | 9.40 | |
| 5 | 2018-11-05 | 15.37 | 2019-11-19 | 19.11 | +24.4% | 8.28 | |
| 6 | 2020-03-12 | 17.32 | 2021-03-24 | 28.53 | +64.7% | 4.13 | 2020 COVID |
| 7 | 2020-03-19 | 14.45 | 2021-03-31 | 29.24 | +102.3% | 9.00 | |
| 8 | 2020-03-26 | 16.28 | 2021-04-12 | 29.76 | +82.8% | 7.67 | |
| 9 | 2020-04-06 | 16.24 | 2021-04-19 | 30.27 | +86.3% | 6.88 | |
| 10 | 2020-04-13 | 16.61 | 2021-04-26 | 30.64 | +84.4% | 6.00 | |
| 11 | 2022-06-30 | 25.74 | 2023-07-12 | 29.95 | +16.3% | 4.29 | 2022 升息熊 |
| 12 | 2022-07-07 | 24.92 | 2023-07-19 | 30.22 | +21.3% | 4.96 | |
| 13 | 2022-07-14 | 25.34 | 2023-07-26 | 30.17 | +19.0% | 4.62 | |
| 14 | 2025-04-08 | 37.51 | 2026-04-17 | 84.15 | +124.3% | 4.46 | 2025 川普關稅 |
| 15 | 2025-04-15 | 40.48 | 2026-04-24 | 89.95 | +122.2% | 4.64 | (cluster 截斷) |

## Event Coverage

| Event Year | Tier (H084) | Triggers in cluster | Trades filled |
|---|---|---:|---:|
| 2018 中美貿易戰 | C (parent C, 但 cluster 與 49 觸發日) | 49 | 5 |
| 2020 COVID | B macro | 43 | 5 |
| 2022 升息熊 | B-sub (parent A) | 13 | 3 |
| 2025 川普關稅 | B macro | 22 | 2 (資料截止) |

### 未涵蓋（已知 H084 事件）
- 2021-05-17 Tier C — 沒觸發
- 2022-10-25 Tier A 主底 — 沒觸發（緩跌型 panic）
- 2024-08-05 Tier C-sub — 沒觸發
- 2026-03-31 Tier C — 沒觸發

## Research History

- **H084** (correction-bottom-survey) → confirmed: 4 個非冗餘 fear 指標 framework
- **H085** (fg-composite) → **confirmed (limited)**: 本策略
- **H086** (mode-switch-tuning) → in progress
- **H087** (margin-breadth-augment) → in progress
- **H088** (tier-c-entry) → just spawned: 補 Tier C 標準回檔覆蓋
- H089 / H091 / H092 → 候選衍生

## Live Performance Log

| Period | Return | Notes |
|---|---|---|
| 2026-05- | — | 即將開始 live tracking |

## Review Notes

- 2026-05-11 ：策略 confirmed，V1 倉位管理勝出。下一個 monitoring milestone：等下個 fear 事件到來時觀察觸發是否如預期
- 已知盲點：2022-10 緩跌型 Tier A 主底沒命中 → 不適合作為唯一長線進場工具，需配合其他策略

## Status

- [x] Active
- [ ] Under Review
- [ ] Retired

## Operational Reminder

- 觸發極少（3-4 年 1 次），日常監控用 `src/analysis/fg_composite_monitor.py`
- 觸發後當下不一定是最低點，但 cluster 內每筆 trade 都會分散在「panic 各個階段」
- 持有 1 年期間不停損、不停利，需要心理建設與資金紀律
