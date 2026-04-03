# Archive: Leading Indicator Regime — 領先指標長線進出

## Status
Confirmed

## Summary
國發會領先指標不含趨勢指數的底部拐點，搭配週 MACD 多頭確認進場、月 KD(9,3,3) 跌破 80 出場，
構成一個三重確認的長線做多框架。5 年回測 3 筆已平倉交易全勝（net +30.7%），
雖然樣本少、絕對報酬不及 Buy-and-Hold，但作為長線持股的進出場參考點具有實用價值。

## Key Evidence
- 領先指標 bottom 拐點後 +3M 報酬 mean=+5.01%, hit=82%, p=0.025（N=11）
- 領先指標 bottom 拐點後 +6M 報酬 mean=+13.03%, hit=91%, p=0.003（N=11）
- 三重確認策略（v4）：3 筆已平倉全勝，net +7.4% / +1.4% / +20.0%
- 週 MACD 確認有效避開假訊號（2025/02 案例：避開 -13% 下跌）
- 月 KD 跌破 80 後 +6M 平均報酬近零 → 出場時機合理
- MACD 參數完全不敏感（穩健），KD 參數較敏感（需注意）

### Drawdown 比較 — 策略核心優勢

| | Buy-and-Hold | 策略 |
|---|---|---|
| Max Drawdown | **-30.5%** (2022/01→2022/10, 18357→12764) | **-2.5%** |
| Total Return | +121.3% | +30.7% (net) |

策略完美避開 2022 熊市（-30.5%），持倉期間最大未實現虧損：
- Trade 1：-2.5%（進場後小回檔）
- Trade 2：-1.1%
- Trade 3：0.0%（幾乎沒回檔）

### 期貨槓桿可行性

因為回檔極小，用期貨（TX 槓桿 ~13x）放大報酬是可行的：
- 1 口 TX 累計保證金報酬：**+432.9%**（30 個月，年化 +95%）
- 最大保證金回檔：-33.6%（Trade 1），其餘兩筆 < -15%
- 若控制在 2-3 口 / 目標 MDD 15-20%，風險報酬比非常好

## Why Confirmed
- 策略邏輯清晰：景氣底部 + 技術確認 + 動態出場
- **回檔控制是核心價值**：策略 MDD -2.5% vs B&H -30.5%，適合長線持股進出場參考
- 低回檔特性使期貨操作可行，槓桿放大後報酬可觀
- 做為長線持股（如 0050 ETF）的參考框架，月 KD 出場訊號是核心價值
- 雖然期貨回測樣本僅 3 筆，但 Phase 1 分佈探索有統計顯著支持
- 實際用途不限於期貨交易，更適合作為 regime awareness 工具
- Top 拐點做空完全無效（台股長期上漲偏差）→ 僅做多

## Derived Hypotheses
- H0XX：用 TAIEX 加權指數（更長歷史 2000-2026）重跑，增加樣本
- H0XX：0050 ETF 回測（無換倉成本，含除權息）
- H0XX：月 KD 跌破 80 作為獨立風控訊號（跨策略共用）
- H0XX：領先指標 regime 作為現有當沖策略的開關濾網

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Backtest：results/backtest.md
- Explore scripts：explore.py, explore_kd.py, explore_kd_exit.py, explore_kd_exit_v2.py, explore_kd_macd_v3.py, explore_kd_macd_v4.py
- Backtest script：backtest.py
