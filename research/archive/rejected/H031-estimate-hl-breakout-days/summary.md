# Archive: EstimateHL 趨勢爆發日與未觸及日分析

## Status
Rejected

## Summary
探索能否透過盤中放量偵測或 EstHL 預測來辨識趨勢爆發日（10.8%）與完全未觸及日（52.6%），以改善 SatZone 出場策略。Phase 1 發現爆發日無法事前預判，Phase 2 測試分批出場（50/50、40/60 + trailing stop）但 OOS 未通過逐年一致標準。

## Key Evidence
- **爆發日無法預判**：放量訊號最佳 slot 在 13:15（太晚），10:00 前 separation < 0.4，而 53% 的 SatZone 觸及在 10:00 前
- **EstHL 無法預測低振幅日**：F1 僅 0.259，untouched 日的 EstHL/EmaHL 反而最高（~0.97），因為成交量正常但振幅壓縮
- **爆發日續行確實顯著**：觸及 SatZone 後中位數再走 0.79 × EmaHL，83% >= 0.5 × EmaHL
- **分批出場 IS PASS、OOS FAIL**：50/50 和 40/60 在 2022~2024 每年都勝 baseline，但 2025 OOS 略輸（-0.014%）
- **untouched 日占 44~66%**（視 SatZone 版本），前一天狀態無預測力（條件機率 ≈ base rate）
- **大跳空提高 untouched 機率**：Gap > 1.0 × EmaHL 時 untouched 73% vs 小跳空 60%

## Why Rejected
1. 爆發日與未觸及日均無法事前預判（量驅動指標對「量正常但波動壓縮」的情境無效）
2. 分批出場的改善幅度極小（最大 +0.029%/年），且 OOS 2025 年未通過逐年一致標準
3. 分批出場增加了出場不確定性，但 edge 不足以補償

## Derived Hypotheses
- H044：SatZone fraction 優化 — 固定 1.0 × EmaHL 導致 44~66% 的天摸不到 SatZone。測試各策略（S001/S002/S003）是否適用不同 fraction（如 0.85~0.95），提高 touch rate 同時維持出場品質

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Backtest：results/backtest.md
- Tasks：tasks.md
