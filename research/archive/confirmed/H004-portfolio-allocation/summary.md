# Archive: 策略組合與資金配置（EstHL + ORBLong 最佳組合）

## Status
Confirmed

## Summary
分析 EstHL、DirA、ORBLong 三策略的相關性與資金配置。發現 EstHL 與 DirA 日相關係數高達 0.746（同進場條件），非真正分散。最佳組合為 EstHL + ORBLong 各半口，Sharpe 3.12，全期 +4,346 點，2021-2026 每年正損益（最差年 +18），優於三策略均分。

## Key Evidence
- 日相關係數：EstHL vs ORBLong 0.171（低，真正分散），EstHL vs DirA 0.746（高，假分散）
- EstHL + ORBLong 各半口：Sharpe 3.12，合計 +4,346，無虧損年，最差年 +18
- 三策略均分各三分之一口：Sharpe 2.93，合計 +4,304，最差年 +301
- 單獨 ORBLong：Sharpe 2.35，合計 +4,970，但 2021 虧 -498（1 個虧損年）
- ORBLong 強制出場 13:00 Sharpe 最高（3.23），尾盤持倉平均為拖累
- ORBLong 週四效應：OR% < 0.7% 的 42 筆勝率 41%，thu_or_pct_min=0.7 合計 +5,649

## Why Confirmed
EstHL 與 ORBLong 進場時段不重疊（09:15 前 vs 09:30 後）、日相關僅 0.171，是真正的策略分散。加入高度相關的 DirA 在固定資金下為負效益。此配置已成為實盤執行方案。

## Derived Hypotheses
- EstRange Credit Spread（第三策略候選，與突破策略低相關）
- 績效標準化 PnL%（跨年度公平比較）
- ORBLong 全濾網版（OR% + force_exit 13:00 + thu_or_pct_min 0.7）

## Links
- Proposal: specs/strategies/2026-03-11-portfolio-allocation.md
