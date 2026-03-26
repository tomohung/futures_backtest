# Archive: Reversal 實盤 vs 回測比對

## Status
Confirmed

## Summary
比對 Reversal 策略實盤（N=102）與回測（N=131）的差異，找到核心差距來源：69% 的實盤獨有交易被 Near-SatZone latch 永久鎖住。修改為「拉回 EmaHL×0.5 後解鎖」，PF 從 1.28 提升至 1.32，Total +2,757→+3,757，2023 年從虧損翻正。

## Key Evidence
- 實盤 vs 回測重疊率：修改前 52.5%→修改後 61.4%
- Near-SatZone 類別：24 筆→0 筆（全部解決）
- sat_pullback_fraction=0.5 回測：N=556, Win=45.0%, PF=1.32, Total=+3,757
- 年度穩定性：2023 PF 0.87→1.11（唯一翻正的 variant）
- 剩餘 live-only 39 筆：TRIGGER_MISSED 22 + DIR_BLOCKED 12 + NO_BB_SETUP 4

## Why Confirmed
1. 成功定位實盤 vs 回測差距的主因（Near-SatZone permanent latch 過度限制 Reversal 進場）
2. 產出具體策略改善已採用至 `src/strategies/reversal.py`（sat_pullback_fraction=0.5）
3. 回測驗證 PF 和 Total 均提升，且年度穩定性改善
4. 剩餘差距有明確後續假設（H042/H043）承接

## Derived Hypotheses
- H042（BB extreme bypass MA）：解決剩餘 12 筆 DIR_BLOCKED
- H043（multiday rebound exhaustion）：解決剩餘 22 筆 TRIGGER_MISSED
- H042/H043 完成後應回頭比對本研究的 live-only 清單確認捕捉率

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
