# Proposal: Mode 1 / Mode 2 切換規則調校

## ID
H086

## Derived From
H084-correction-bottom-survey 的 Step 0.8 保險絲層驗證結果

## Trading Intuition

H084 Step 0.8 已確認雙條件 `TAIEX < 250MA AND blue_streak ≥ 3` 概念可行（中位數可分流），但**具體規則有問題**：

- AND 太嚴：2022-10-25 trough 漏抓（streak=1 不足 3）
- OR 太鬆：bull 期 21% 觸發，誤報多

H086 系統性測試規則變體，找出最佳組合，使：
- Tier A regime 觸發率高（≥80%）
- Bull regime 觸發率低（≤10%）
- 規則切換 lag 短（≤ 2 個月）

## Hypothesis

> 透過調整 (1) blue_streak 門檻、(2) 250MA below 持續天數、(3) 邏輯組合（AND/OR/weighted），可以找到一組規則使 Tier A regime recall ≥ 80% 且 bull regime false-positive ≤ 10%。

## Expected Distribution

Phase 1 預期觀察：
- blue_streak ≥ 1（即 current 月 藍/黃藍）會大幅提升 Tier A recall（已知 2022-10 streak=1）
- 250MA below 持續 ≥ 10 天可去除單日 whipsaw
- AND（streak ≥ 1 + 250MA below ≥ 10D）應該是 sweet spot

## Invalidation Condition

下列任一成立 → reject：

1. **無一組規則能同時滿足** Tier A recall ≥ 80% AND bull FPR ≤ 10%（trade-off curve 整體偏離理想點）
2. 最佳規則的 OOS 表現顯著差於 in-sample（recall 下降 > 15%）
3. 任何規則對「景氣燈號」與「250MA」的相對權重都極敏感（Pareto frontier 平坦無 sweet spot）

## Notes

- Tier A regime 定義：H084 events 表中 macro tier == A 的天數（hindsight）
- bull regime 定義：events 表中 macro_tier == 'bull'（事件外）
- Mode 切換的應用：H085 合成 score 的閾值（Mode 2 用較嚴格門檻）、tranche size、是否啟動

## 衍生方向

- Tier A vs Tier B regime 的最佳規則可能不同 → 是否再加 Mode 3（介於 1 和 2 之間）
- 加入廣度指標（H087 完成後）強化 regime detection
