# Archive: EstRange Credit Spread — 用預估振幅賣選擇權

## Status
Confirmed

## Summary
利用 EstRange 的觸及率特性（碰到一邊後另一邊安全率 65-82%），在價格觸及 EstRange x fraction 的一側後賣對側 OTM credit spread。3 年回測（2023-2026）579 筆交易，勝率 86.5%，PF 21.01，39 個月全部正收益。但發現當沖 x Credit Spread 的核心矛盾：DTE>=2 的 spread 日內 theta 衰減極小（Win 只 captured 8-12% credit），12:30 平倉後 PF 從 23.3 降至 1.70，需改用 DTE=0 合約或逐 weekday 優化。

## Key Evidence
- 3 年回測（f=0.70, exit 12:30, spread=ER x 50%, skip settlement）：579 筆，WR 86.5%，PF 21.01，total +21,236 pts
- 逐年穩定：2023 +5,749 / 2024 +6,607 / 2025 +7,071 / 2026 +1,811
- 條件機率（f=0.75）：碰高後不碰低 66.0%，碰低後不碰高 64.6%
- Fri 最安全（Safe 83.7%/79.7%），Wed 最危險（雙邊 13.4%）
- 修正出場定價後（12:30 實際 spread 市值平倉）：PF 從 23.3 降至 1.70，avg/trade 從 +38.8 降至 +1.2
- DTE=0 captured 78-88%，DTE=1 captured 24-39%，DTE>=2 captured 僅 8-13%
- VIX 不影響觸及率（r=+0.033），不需額外 VIX 濾網

## Why Confirmed
EstRange 觸及率分析（碰到一邊後另一邊安全率高）的核心假設成立，3 年 579 筆交易驗證了統計穩定性。但同時發現當沖 credit spread 的定價矛盾，促成後續 weekday 優化研究（H009），最終轉向 DTE=0/1 合約 + 逐 weekday exit time 的設計。

## Derived Hypotheses
- H009: 逐 weekday 參數優化（不同 DTE 用不同 exit time）
- DTE=0 合約（到期日）theta 最快，是主力收益來源
- Thu 表現系統性差（所有 exit time 都虧損），應排除

## Links
- Proposal: specs/strategies/2026-03-17-estrange-options.md
