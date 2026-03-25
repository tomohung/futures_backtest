# Archive: 缺口日研究（缺口竭盡反轉）

## Status
Rejected

## Summary
研究台指期夜盤缺口（夜盤收盤 → 日盤開盤）的統計特徵與竭盡反轉策略可行性。Phase 1 發現破 ORB 後補缺口率高達 84%（年年穩定 81~87%），但 Phase 2 回測顯示所有參數組合在 IS 期間皆虧損。

## Key Evidence
- 夜盤缺口均值僅 0.20%（~30pt），遠小於 ORB 寬度（~60pt）
- 破 ORB 後補缺口率 84.2%，年度穩定 81~87%（Phase 1 統計真實存在）
- MFE 中位 1.33R，60.8% 交易至少到過 1R（行進空間存在）
- 但 1R 停利模擬仍虧（PF=0.88），ORB stop 被先觸發的比例太高
- IS（2021-2024）所有參數組合 PF < 1.0，無正期望值配置

## Why Rejected
**R:R 結構性不利**：Target（缺口距離 ~29pt）遠小於 Stop（ORB 寬度 ~57pt），即使 84% 命中率也無法覆蓋虧損。47% 的竭盡反轉 ORB 已穿過夜收價，根本不可交易。MFE 存在但容易被 false break 先洗掉 stop。

核心教訓：**高勝率 ≠ 正期望值**。統計上的「補缺口」和可獲利的「交易」是兩件事——進場點位置決定了實際可用的利潤空間。

## Derived Hypotheses
- H0XX-gap-as-filter：缺口方向 + ORB 失敗作為現有策略的濾網條件
- H0XX-large-night-gap：只鎖定大夜盤缺口（>=0.3%）做竭盡反轉，R:R 可能翻正但樣本量不足
- H0XX-gap-continuation：未觸發竭盡反轉的日子，缺口延續方向操作
- H0XX-orb-break-confirmation：破 ORB 後加確認條件（量能、retest）降低 false break

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Backtest：results/backtest.md
