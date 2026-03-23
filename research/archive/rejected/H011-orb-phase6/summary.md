# Archive: ORB Phase 6 市場機制濾網（Regime Filter）

## Status
Rejected

## Summary
嘗試用 ADX、ATR%、實現波動率、滾動 ORB 勝率等市場機制指標作為 ORB 策略進場濾網，目標是改善 2021 低波動震盪年的虧損。Phase 5 已驗證 OR 均寬濾網無效，Phase 6 進一步探索更廣義的方向性指標，最終因 regime 指標無法有效區分好壞交易而未實作。

## Key Evidence
- Phase 5 最佳可行組合（w=20, min=60）總損益 +5,302，低於無濾網的 +5,653
- OR 均寬是窄義波動指標，濾掉安靜日同時也濾掉有效空單
- 2021 核心問題是「震盪/均值回歸」機制，做多勝率僅 39-43%
- 後續 strategy_health_monitor 完整驗證：所有 regime 指標作為濾網都讓總損益下降

## Why Rejected
OR 均寬是症狀而非病因。所有候選指標（ADX、ATR%、RealVol、滾動勝率）要嘛落後太多（事後才知道），要嘛區分力不足（r < 0.15）。任何能減少 2021 虧損的門檻都會同時犧牲其他年份的獲利。

## Derived Hypotheses
- → H014 Strategy Health Monitor（用 Range%、ER 等做環境預警，同樣被否定）
- → ORBLong long-only 方向（放棄做空而非濾網，已證實有效）

## Links
- Proposal: specs/strategies/2026-03-04-orb_phase6.md
