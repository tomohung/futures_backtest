# Archive: Multi-Day Rebound Exhaustion

## Status
Rejected

## Summary
測試「BC zone 與 MA 方向矛盾」情境下（開盤 > BC zone 但 MA 向下，或反之），利用 BB 極端觸碰作為反彈/回調竭盡訊號，順 MA 方向交易。Phase 1 發現此情境的 MFE/MAE 無 edge（MFE>MAE 僅 48.6%），加入跳空距離條件後反而更差。

## Key Evidence
- H043 目標情境出現頻率 20.8%（263/1264 天），逐年穩定
- BB setup 觸發率高（80%），但觸發後反轉品質差：
  - MFE/EmaHL 中位數 0.300 vs MAE 0.338 → Net -0.033
  - MFE > MAE 僅 48.6%（低於 50%）
- 對照組 aligned_short 有正 edge（MFE>MAE 53.8%，Net +0.081）
- 加入跳空距離條件（gap > 0.5~1.0 × EmaHL）後，rebound_short 的 MFE>MAE 從 49% 降到 41%，結果更差
- pullback_long gap >= 1.0 看似有 edge（Net +0.185），但僅 12 筆且 2025 年 MFE>MAE 20%
- 逐年不穩定：2022-2023 偏好、2024-2025 偏差

## Why Rejected
1. 「BC zone 和 MA 方向矛盾」不含均值回歸 edge — 這些情境更可能是趨勢正在轉向（MA 滯後），而非反彈竭盡
2. 跳空越大 MAE 越大，反而是趨勢加速的信號，不是回補壓力
3. 無效條件成立：MAE > MFE，且逐年不一致

## Derived Hypotheses
- 無。aligned_short（BC zone 下方 + MA 向下做空）已是現行 Reversal 的核心場景，無需新假設。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Tasks：tasks.md
