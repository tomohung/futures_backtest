# Archive: Weak-Open OR Break Short（弱勢開局破底續跌）

## Status
Rejected（作為單一可交易策略）— 但 Phase 1 分佈 edge 保留為「情境/濾網」

## Summary
測試「開盤雙雙在昨+前日日盤 VWAP 之下（嚴格弱勢）且 08:58–09:15 破 OR low」的破 OR low 直接做空。
分佈上，弱勢開局破底的**整日下行確實更深**（強且顯著）；但做成可交易策略，含成本後**淨期望為負**，
任何出場階 / 停損設定皆 PF<1 → 拒絕為單一策略。價值在於當作既有空方策略的順勢情境濾網，而非進場訊號。

## Key Evidence
（TX 日盤，N=189 事件日，2021-02 ~ 2026-06）

**Phase 1（分佈，成立）**：弱勢開局破底整日峰谷 reach 最深，呈成本梯度
成本上(48/20/9) < baseline(48/24/12) < 寬鬆B(62/35/17) < **嚴格弱勢(L3=69/L4=41/L5=22)**；虛無檢定第 100 百分位。

**Phase 2（可交易，否定）**（cost=2pt 來回，損益%）：
| 出場 | 勝率 | 總損益% | PF |
|---|---|---|---|
| TP@L2 | 43.4 | −0.74 | 0.98 |
| TP@L3 | 36.5 | −7.75 | 0.84 |
| 抱到收盤 | 34.9 | −4.66 | 0.91 |
- 唯一接近正：TP@L2 在**零成本** +1.3%，1 點即吃光。
- 停損放寬只提升勝率不轉正（PF 上限 0.97）。
- 逐年 6 年僅 2022 / 2026(N=8) 正；IS +0.65% → OOS −1.39%。

## Why Rejected
**方向命中 ≠ P&L。** 整日深跌的幅度多發生在「破 OR low 進場之前」——forward-from-break 只有 27.5% 達 L3。
進場時肉已走掉一截，加上 OR-high 停損偏遠、單筆虧損大，邊際 edge 撐不過手續費滑價。
分佈 edge 真實但不可用此進場法兌現。

## Derived Hypotheses
- **H124（回踩再進空）**：不追破底，等回踩 OR low / 成本帶反彈再進空，改善入場價——最可能把 context 轉成 P&L。
- **H125（context 濾網）**：把「弱勢開局破底」當布林濾網套到現有 EstHL/Reversal 空單，檢驗是否提升空方表現。
- **H126（連續強度因子）**：用 (VWAP−open)/EmaHL 連續距離取代二元成本上/下，回歸 forward reach，找極端弱勢的可交易尾段。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md（Phase 1 edge）
- Backtest：results/backtest.md（Phase 2 否定）
- Scripts：explore.py / backtest.py ｜ 逐筆：results/trades_tp_l3.csv
- 相關：H122（confirmed，本假設的鏡像來源）
