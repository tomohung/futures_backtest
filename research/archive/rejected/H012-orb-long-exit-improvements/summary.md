# Archive: ORBLong 出場機制改進實驗

## Status
Rejected

## Summary
針對 ORBLong 策略 Trailing SL 為唯一虧損來源（81 筆全虧，-4,793 pts）的問題，系統性測試四個改進方向：Breakeven Stop、Trailing SL 過濾、提早出場條件、Late Entry TP 縮放。所有方向均被驗證無效，根本原因是 TSL 輸家與最終贏家在早期走勢無法區分。

## Key Evidence
- Trailing SL 81 筆全部虧損，合計 -4,793 pts，佔總虧損 85.4%
- **Breakeven Stop**：門檻 +20~+50 pts 救了 TSL 但砍掉更多贏家（淨效果 -350 ~ -1,391 pts）；門檻 +70~+88 pts 幾乎不觸發
- **15 筆假突破**：OR%、進場時間、星期等特徵與真突破完全無法區分（OR% 0.568% vs 0.552%）
- **11:00 提早出場**：Force Exit 暫時虧損者與 TSL 慢速停損者 PnL% 分布高度重疊，任何切割條件都誤砍大量贏家
- TSL 輸家平均峰值僅 +33 pts，贏家早期也在同水準（+20~+40 pts）

## Why Rejected
ORBLong 的核心優勢是「讓部位有時間跑」。Trailing SL 虧損是策略結構性的不可避免雜訊（81/232 = 35%），TSL 輸家與贏家在進場條件和中途損益上無法有效區分。任何出場改進都會同時傷害獲利交易。

## Derived Hypotheses
- 15 筆假突破（6.5% 交易量）被確認為不可避免雜訊，應接受
- 後續改善應聚焦在進場品質（如 OR% 濾網）而非出場邏輯

## Links
- Proposal: specs/strategies/2026-03-12-orb-long-exit-improvements.md
