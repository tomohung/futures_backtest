# Archive: ORB 策略過濾器優化

## Status
Confirmed

## Summary
測試三類過濾器（開盤區間幅度、趨勢方向、跳空）對裸 ORB 的改善效果。結論：僅 Trend MA Filter（MA10）有效，PF 從 1.02 提升至 1.215。Range Size 與 Gap Filter 無效。

## Key Evidence
- Trend MA(10) Filter：PF 1.02 → 1.215（顯著改善）
- Range Size Filter：PF 未改善，放棄
- Gap Filter：PF 未改善，放棄
- 僅單一 filter 有效，無法做組合

## Why Confirmed
Trend MA Filter 是 ORB 策略第一個被驗證有效的訊號品質過濾器，成為後續所有 ORB 迭代的基礎。

## Derived Hypotheses
- H024：固定 Trend MA(10)，進入全參數掃描

## Links
- Proposal：research/active/H023-orb-filters/proposal.md
- Spec：research/active/H023-orb-filters/spec.md
- Tasks：research/active/H023-orb-filters/tasks.md
