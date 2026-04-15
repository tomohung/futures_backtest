# Archive: 選擇權成交量作為支撐壓力

## Status
Inconclusive

## Summary
用前日近月 Put 成交量最大的履約價作為支撐，Call 最大作為壓力。969 天分析發現 Put 支撐命中率 26.8% 顯著高於隨機 21.3%（p<0.0001），但 Call 壓力無效。回測做多策略 IS Sharpe 2.02、OOS 1.39，方向一致但 OOS 樣本太少（16 筆），且交易頻率低（~35 筆/年）。

## Key Evidence
- Put S1 支撐命中率 26.8% vs 隨機 21.3%（p<0.0001，N=1237）
- Call R1 壓力命中率 18.3% vs 隨機 21.3%（p=0.009，更差）
- IS: 89 筆, 勝率 49%, Sharpe 2.02, 累計 +2.80%
- OOS: 16 筆, 勝率 50%, Sharpe 1.39, 累計 +0.35%
- 參數穩健區：SL 0.20~0.25 × TP 0.30

## Why Inconclusive
有統計顯著的正面訊號（Put 支撐），IS/OOS 方向一致。但 OOS 樣本不足、交易頻率太低、絕對獲利空間小，不足以作為獨立策略。已整合進 morning_briefing 作為每日支撐參考。

## Derived Hypotheses
- Put S1 可作為現有策略（ORB、Reversal）的方向濾網
- 補充 OI 資料後可以做更完整的籌碼面分析（Max Pain 等）

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Backtest：results/backtest.md
- 探索腳本：explore.py
- 回測腳本：backtest.py
