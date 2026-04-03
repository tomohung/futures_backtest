# Archive: Night-Day Volatility Correlation

## Status
Rejected

## Summary
假設夜盤振幅可預測隔天日盤振幅。Raw 相關性強（r=0.65），但主要來自台美市場連動的波動 regime 共變。
EMA 標準化後增量預測力有限（r=0.34），且跨年不穩定（2022-2023 r<0.2）。
無法建立精確預測公式，但「夜盤偏離預期」的異常警示有實用價值，已整合到 key_prices 與 daily_range 圖表。

## Key Evidence
- Pearson r=0.653 (raw), 0.338 (normalized), N=937
- Q4/Q1 day range ratio: 2.15x (raw), 1.31x (normalized)
- 跨年不穩定：2021 r=0.54, 2022 r=0.16, 2023 r=0.09, 2024 r=0.73, 2025 r=0.43, 2026 r=0.58
- EMA20-only MAE=46.1 vs blended MAE=43.9 — 僅改善 5%
- Weekday 交叉：Q4 night override 所有 weekday 效應（uplift 1.6~1.9x）

## Why Rejected
1. 相關性存在但來自 regime 共變（台美連動），非穩定結構性 edge
2. 無法建立比 day_EMA20 顯著更好的預測公式
3. 但作為異常警示（預期 vs 實際不一致）仍有實用價值
4. 已直接整合到 `key_prices.py`（文字）和 `daily_range.py`（圖表），不需進 Phase 2

## Derived Hypotheses
- （無 — 實用價值已直接整合到分析工具中）

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Explore script：explore.py
