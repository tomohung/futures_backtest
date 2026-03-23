# Archive: EstRange Credit Spread 逐 Weekday 參數優化

## Status
Confirmed

## Summary
針對 H008 發現的當沖 credit spread 定價矛盾，改用 min_dte=0 + nearest expiry + 逐 weekday 最佳參數優化。確認排除 Thu（所有 exit time 皆虧損）和 Wed（theta 不足，扣手續費後不划算），最終定案 Mon+Tue+Fri 三天交易，fraction=0.65，各 weekday 獨立 exit time，8.5 個月回測 89 筆交易 WR 91.0%，net +583.7 pts。

## Key Evidence
- Thu 全面虧損：每個 exit time 都是負 PnL，不是參數問題是結構性弱
- Wed 排除：17 筆全勝但 PnL 近 0（+0.2 pts），theta 衰減不足，扣手續費不划算
- 定案 weekday exit：Mon 11:30 / Tue 11:30 / Fri 12:00
- 組合 D（Mon+Tue+Wed+Fri 排除 Thu）PnL +798，PF 12.15；最終排除 Wed 後 Mon+Tue+Fri
- fraction=0.65（平衡方案）：PnL +826，WR 90.7%，PF 11.16
- min_credit=5 過濾 DTE=0 薄利交易，Wed net WR 76.5%->100%，Fri net WR 74.1%->84.2%
- 淨績效（2025-07 ~ 2026-03）：89 筆，gross +732.2 pts，net +583.7 pts（NT$29,183），9 個月全正收益
- Tue 最強：WR 90.3%，PF 15.18，net +255.9 pts
- 成本佔 gross 的 20.3%（手續費 4 腿 x NT$18 + 交易稅）

## Why Confirmed
逐 weekday 優化解決了 H008 的當沖定價矛盾，透過排除 Thu/Wed、配合各 weekday 最佳 exit time 和 DTE=0/1 合約，實現 9 個月全正收益。Fri F 合約（DTE=0）表現優異（PF 7.87 vs W 合約 1.48），驗證 theta 衰減速度是 credit spread 當沖的關鍵。

## Derived Hypotheses
- Fri 從 W 合約切換到 F 合約（DTE=0）可能進一步提升績效，待累積更多樣本
- spread_pct 更大（0.60-0.80）PnL 更高但 max_loss 也更大，受限於下單軟體
- min_credit 門檻可依實戰經驗微調（mc=10 也合理但筆數減少過多）

## Links
- Proposal: specs/strategies/2026-03-19-estrange-options-weekday-optimization.md
