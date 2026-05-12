# Archive: H084 多頭修正底部訊號 Survey

## Status
**Confirmed** — Survey 型假設成功識別 4 個非冗餘 fear 軸，衍生 H085→S004 live 策略。

## Date Closed
2026-05-12

## Summary

H084 是 survey 型假設，目標：透過台股 zigzag tier 標定 + 多指標分佈研究，
找出在 Tier B/C 底部事件中可重現極值且彼此非冗餘的 fear/regime 指標集，
作為後續合成 score 或單因子驗證的基礎。

Survey 識別 4 個**非冗餘**底部訊號軸：
- `vix_pct`（VIX 百分位）
- `taiex_dist_125ma_z`（125MA 距離 z-score）
- `margin_drop_60d_pct`（融資 60 日跌幅）
- `econ_score`（景氣對策信號分數）

衍生 H085 把這 4 軸合成 `comp_z`，後續變 S004-fg-composite live 策略。
所有試圖找「第 5 個軸」的衍生假設（H087 廣度補強、H089 廣度單獨 Tier C trigger、H090 漲停動量）
全部 rejected → 強化「**4 軸 sufficient**」的結構性結論。

## Key Evidence

### GATE 通過條件

| # | 條件 | 結果 |
|---|---|---|
| 1 | ≥ 3 個指標在 Tier B/C 底部 hit rate ≥ 60% | ✓ — VIX/VIX_pct 88%、z 125MA 82%、dist 250MA 65% 等多個 |
| 2 | ≥ 2 個可靠指標彼此 \|r\| < 0.6 | ✓ — 4 個軸彼此 max \|r\| 都 < 0.6 |
| 3 | 250MA + 景氣信號保險絲區分 Tier A vs B/C | ✓ — `fuse_state.csv` 產出 macro_tier 序列 |
| 4 | 指標涵蓋 2010-2026 無重大缺口 | ✓ — 4 軸皆全 |

### 4 個非冗餘 fear 軸（confirmed）

| 軸 | Hit rate (Tier B/C 21 events) | 用途 |
|---|---:|---|
| vix_pct | 88% | 直接 panic 量化 |
| taiex_dist_125ma_z | 82% | 技術性超賣 |
| margin_drop_60d_pct | 50% | 融資去槓桿確認 |
| econ_score | 24% (但 A tier 45%) | 結構面慢變數 |

兩兩 Pearson |r| 都 < 0.6（彼此資訊正交）。

### 衍生假設 outcome 總覽

| 假設 | 主題 | 結果 |
|---|---|---|
| **H085** | 4 軸合成 comp_z → panic 抄底 | **confirmed → S004 live** |
| H086 | mode-switch 規則調整 | rejected |
| **H087** | 加廣度補強 H085 composite | rejected — 稀釋訊號 |
| H088 | 傳統 fear signals on Tier C | rejected — 無 edge over DCA |
| H089 | 廣度單獨作 Tier C trigger | rejected — continuation 而非 reversal |
| H090 | 漲停熱絡作 momentum trigger | rejected — bull regime tautology |

→ H087/H089/H090 三個失敗形成「H084 4 軸已 sufficient，不存在第 5 個有用軸」的補集證據。

## Why Confirmed

1. **GATE 全部通過**：4 個條件皆達成
2. **下游策略落地**：H085 → S004-fg-composite live 策略，IS+OOS Sharpe 1.83/3.65、100% 勝率
3. **副產出仍在使用**：`indicators.csv` / `tiers.csv` / `fuse_state.csv` 被 6 個衍生假設共用
4. **結構性結論強化**：所有「找第 5 個軸」的衍生研究都 reject，證明 4 軸已是 informationally complete

## Impact / Downstream

### Live 策略
- **S004-fg-composite**（H085 confirmed → live）整合 morning_briefing 每日輸出

### 永久基礎建設
- `data/futures.duckdb` 新增 `market_breadth`、`stock_day`、`econ_signal`、`margin_balance` 表（透過 H087 完成 2010+ 全量回填）
- `src/etl/parse_stock_market.py` / `parse_margin.py` / `parse_econ_signal.py` ETL 工具鍊

### 文件
- 4 個非冗餘軸寫進 S004 spec.md
- H084 fuse_state.csv 與 tiers.csv 變 reference data 給未來假設

## Derived Hypotheses (status update)

| ID | 結果 | 歸檔位置 |
|---|---|---|
| H085-fg-composite | confirmed → S004 live | archive/confirmed/ |
| H086-mode-switch-tuning | rejected | archive/rejected/ |
| H087-margin-breadth-augment | rejected | archive/rejected/ |
| H088-tier-c-entry | rejected | archive/rejected/ |
| H089-breadth-tier-c | rejected | archive/rejected/ |
| H090-limitup-momentum | rejected | archive/rejected/ |

無未追蹤的 derived hypothesis。

## Limitations

- **Survey 設計沒涵蓋 short / mean-reversion 訊號**：只關注底部 entry，未測 top/exit
- **macro_tier 標定 backward-looking**：fuse_state 用 zigzag 算 trough recovery，
  正向使用時要注意 macro_tier 是「事後可知」邊界
- **H085 panic specialist 限定 Tier B 急速 panic**，Tier C 標準回檔已透過 H088+H089 驗證
  結構性無 timing edge → 不要再嘗試擴展到 Tier C

## Files

- `proposal.md` — 原始 survey 設計
- `tasks.md` — Phase 0 任務追蹤
- `distribution.md` — Survey 主結論文件
- `zigzag_tiers.py` — Tier 標定演算法
- `build_indicators.py` — 多指標 ETL pipeline
- `percentile_correlation.py` — 命中率 + 相關矩陣
- `event_study.py` — Event-window forward-return 分析
- `fuse_validation.py` — Macro tier 保險絲驗證
- `results/indicators.csv` — 多指標 daily snapshot（被 H085+ 共用）
- `results/tiers.csv` — 21 個 Tier A/B/C 事件
- `results/fuse_state.csv` — macro_tier 序列
- `results/trough_indicators.csv` — 事件 trough 上的指標值
- `results/percentile_table.csv` / `hit_rates.csv` — Phase 0.5+0.6 命中率分析
- `results/correlation_matrix.csv` / `correlation_heatmap.png` — 非冗餘分析
- `results/event_study.png` / `fuse_chart.png` / `tiers_chart.png` — 視覺化
