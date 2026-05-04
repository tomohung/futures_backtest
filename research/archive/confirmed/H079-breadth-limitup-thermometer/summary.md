# Archive: H079 廣度 + 漲停成交額溫度計

## Status
**Confirmed**（以觀察指標形式上線，整合於 morning_briefing；待累積實況後決定是否寫入策略 spec）

## Summary

從前輩經驗驗證「漲停萎縮 = 大跌前兆」，從 3 個子假設出發，最終確認**漲停成交額占比 7 日均**（`lu_value_ratio_ma7`）為真訊號。當 ma7 連續 3 天低於歷史 15 分位後 10 天內，市場大跌（單日 < -2%）機率顯著高於基準。已實作為 `breadth_thermometer.py` 加入 `morning_briefing` 每日輸出觀察級別。

## Key Evidence

### Phase 1（distribution）
- A 廣度背離：1/5/10/20 日累積報酬都不顯著（p > 0.2）→ Reject
- B LC-HV 漲停象限：LC-HV vs HC-HV 5/10/20 日累積報酬 p=0.033/0.030/0.008 → Pass
- C 萎縮事件：事件後 P(20 日內單日跌 > -2%) = 100% (基準 55%)，P(20 日累積跌 > -5%) = 50% (基準 26%)，且完美對齊 2024/7 BOJ + 2025/4 關稅事件

### Phase 2（backtest_c）關鍵修正：原 hypothesis「兩條件 AND」是錯的，**RATIO only** 才是真訊號
- AND 漏掉 BOJ + Tariff 兩個關鍵事件
- RATIO only 抓到兩者，OOS Sharpe 1.06、Δ Full +6934 pts
- 訊號天花板：12/18 = 67% recall（剩下的 6/18 是「平靜中黑天鵝」結構性抓不到）

### H079-K（套到既有策略）
- **S002 Reversal**：OOS Sharpe 2.14 → **2.71 (+27%)**，MaxDD -959 → **-622 (-35%)**，PnL 持平
- **S001 EstHL**：反向（自身已有強 filter，被跳過的反而賺）

## Why Confirmed

1. 訊號本身真實（Phase 1 + Phase 2 多角度驗證）
2. 對 S002 證實有效（OOS Sharpe + MaxDD 雙改善）
3. 已實作為觀察指標進 morning_briefing pipeline
4. 結構性限制誠實：抓不到「平靜中黑天鵝」，但能抓「資金結構崩壞」型

不直接進 strategies/live/ 因為：
- S002 已有眾多 filter，避免過度複雜
- OOS 樣本只 2.3 年，需累積更多實況
- 觀察期完成後再決定是否寫進 S002 spec

## Implementation

### 已上線（觀察用）
- `src/analysis/breadth_thermometer.py`：每日輸出溫度計狀態（4 級警示 + 14 天軌跡）
- `src/etl/daily_update.py`：新增 stock_market 下載/解析步驟
- `src/analysis/morning_briefing.py`：自動呼叫溫度計
- DuckDB 新表：`market_breadth`、`stock_day`

### 最佳參數
- `ma = 7`（7 日均）
- `pct = 0.15`（全期 15 分位門檻）
- `consec = 3`（連續 3 天跌破）
- `skip_n = 10`（防禦窗 10 天）
- `logic = RATIO`（只用 `lu_value_ratio_ma`，不用 `up_limit_count`）

## Derived Hypotheses

- **H079-N**：補 2018-2020 TX ohlcv_1m 後重跑，驗證訊號在 2018Q4 貿易戰、2020 Covid 是否仍 robust
- **H079-O**：在 RATIO defense window 期間，疊加 H079-B 的 LC-HV 訊號做更精細的 regime layering
- **H079-P**：「萎縮事件結束」是否有反向做多進場機會？（事件 + N 天平倉 → N+M 天反向做多）
- **H079-Q**：用 lu_ratio_ma 直接設絕對門檻（如 < 2%）而不是 percentile，看訊號是否更穩定 / 解決 2026 高活躍 regime 的問題
- **觀察期決策**（非新假設）：1-3 個月觀察後，根據實況決定是否寫進 S002 spec.md

## Links

- Proposal：proposal.md
- Phase 1：distribution.md（含 post-hoc 修正註記）
- Phase 2 (B 子假設，已 park)：backtest.md
- Phase 2 (C 子假設，主結論)：**backtest_c.md**
- H079-K (套既有策略)：**backtest_k.md**
- 探索腳本：explore.py
- 回測腳本：backtest.py（C1+C3）、backtest_swing.py（A5）、backtest_c.py（C-defense + C-short）、h079k_filter.py
