# Archive: OR% 濾網（Opening Range 相對寬度過濾）

## Status
Confirmed

## Summary
以 OR% = OR 寬度 / 開盤價 x 100 取代固定點數門檻過濾安靜日和過度波動日，解決跨年度指數水位不同導致固定門檻失效的問題。最佳範圍 0.3%-1.0%，ORBLong 全期 Sharpe 從 1.36 提升至 1.54，2021 年虧損從 -498 縮減至 -123。

## Key Evidence
- 2023-2025 共 190 筆分析：OR% < 0.3% 勝率 40%（假突破多），0.3-1.0% 勝率 57%（甜蜜帶），> 1.0% 勝率 51%（過度波動）
- 全期效果：325 筆 -> 274 筆，合計 +4,615 -> +5,262（+547 點），Sharpe 1.36 -> 1.54
- 2021 改善最多：-498 -> -123（+375 點），其他年份中性或正效益
- OR% 為指數水位無關指標，2021 OR=50/Open=17,500 -> 0.29%，2025 OR=70/Open=22,000 -> 0.32%

## Why Confirmed
OR% 濾網在全年份均有正向或中性效益，概念清晰（相對指標優於絕對指標），且改善最需要幫助的 2021 年。雖然 2021 仍虧，但已從 -498 縮減至可接受範圍。已整合至 ORBLong 策略預設參數及 TradingView Pine Script。

## Derived Hypotheses
- H004: 組合配置（EstHL + ORBLong 含 OR% 濾網）
- ORBLong 週四 OR% >= 0.7% 濾網（thu_or_pct_min）
- 績效標準化 PnL%（跨年度公平比較方法論）

## Links
- Proposal: specs/strategies/2026-03-11-orb-or-pct-filter.md
