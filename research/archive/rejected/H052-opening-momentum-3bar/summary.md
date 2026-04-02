# Archive: 開盤動能連續收紅/收綠

## Status
Rejected

## Summary
測試開盤連續收紅/收綠 K 棒作為日內動能信號。1mK 連 3 紅做多整體 PF=1.42（N=135），但年度極不穩定（5 年中 3 年虧損），且 MFE/MAE 分析揭示獲利機制是「回檔反彈」而非「動能延續」，與假設核心理念矛盾。補充測試 5mK 連 3 紅/綠、9:00 現貨開盤確認方向均無 edge（PF≈1.0）。1mK 連 7 黑做空 PF=1.95 但 N=8，去除極端值後 edge 消失。

## Key Evidence
- 1mK 連 3 紅做多：PF=1.42, N=135, 但 2021/2022/2024 三年虧損（PF<1.0）
- MFE/MAE 時序：MAE 先出現的交易 avg PnL=+109.6pt，MFE 先出現的反而 avg PnL=-72.3pt → 獲利來自回檔反彈，非動能延續
- 5mK 連 3 紅做多：PF=0.94（無 edge）
- 9:00 現貨開盤收紅+站新高做多：PF=1.00（無 edge），不管怎麼組合條件都 PF≈1.0
- 1mK 連 7 黑做空：PF=1.95, N=8，但去掉 2024-08-05（+792pt）後剩餘 7 筆虧損
- 與 EstHL/Reversal 重疊率 53.3%，互補價值有限

## Why Rejected
1. **年度不穩定**：整體 PF 被 2025-2026 大波動不成比例拉高，非穩定 edge
2. **獲利機制矛盾**：假設是「追價動能延續」，實際獲利來自「回檔反彈」，Reversal 策略已涵蓋
3. **多 timeframe 無效**：切換到 5mK 或 9:00 現貨開盤確認，edge 完全消失
4. **週一效應**：做多在週一 PF=0.37（WR 32.3%），進一步削弱可用性

## Derived Hypotheses
- H0XX：週一缺口反轉——開盤方向在週一特別容易反轉，可獨立研究週一開盤缺口行為
- H0XX：開盤放量收綠做空——1mK 連 3 綠 + 量能>1.2x，PF=1.64（N=33），值得搭配出場策略測試

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Explore scripts：explore.py, explore_5m_and_7bar.py, explore_cash_open.py
