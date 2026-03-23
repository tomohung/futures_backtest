# Archive: 轉折回歸策略（Reversal Strategy）

## Status
Confirmed

## Summary
針對均值回歸情境的策略：以 BigCost Zone Gate 決定方向、5m K 120MA 斜率判斷趨勢、BB 極值 + 放量 + CCD 確認 setup、1m 5MA 穿越 trigger 進場。出場採 EmaHL-based SL/TP + Pivot Trailing。2021-2026 全期 690 筆交易，總損益 +5,571 點，PF 1.49，Sharpe 1.34，每年都正。後續 EstRange EMA 替換 EmaHL 進一步提升至 +6,032。

## Key Evidence
- 基準結果：690 筆，WR 49.0%，PF 1.49，EV +8.1 pts，Sharpe 1.34，每年都正（含 2022）
- 5m MA period 120（約 30m 20MA）最佳（+6,079），60 太短、200 太慢
- min_slope_pct 0.006% 過濾 MA 走平，減少 20% 低品質交易
- 進場 09:10 最佳（Sharpe 1.05 -> 1.34），避開早盤雜訊
- SL 0.35 x EmaHL 最佳，TP 2.0（trailing 主導 87% 出場）
- EstRange EMA 替換 EmaHL：+5,700 -> +6,032（+5.8%），EMA 近期權重是關鍵
- ReversalFollow（第 2 筆信號）：338 筆 +2,262，PF 1.49，Sharpe 1.16，品質好但需同向確認
- 多筆信號品質遞減：1st EV +7.6、2nd +4.2、3rd +1.0、4th+ 負
- Weekday 濾網候選（L:Tue/Wed/Thu + S:Tue/Thu）：Sharpe 1.34 -> 1.51，但砍 45% 交易量

## Why Confirmed
策略在與現有突破策略（ORBLong、EstHL）完全不同的市場情境下運作（均值回歸 vs 突破），6 年每年正損益，多空都做。進場邏輯清晰（BC Zone + MA 斜率 + BB 極值 + 量確認 + MA 穿越），參數經過系統性網格搜尋。已成為實盤三策略之一。

## Derived Hypotheses
- ReversalFollow 短邊強化（Long 整體 -394，Short +1,721）
- Weekday 濾網實作（已驗證但尚未上線）
- vol_ratio 測試（目前固定 1.5）
- EstRange 正式替換 EmaHL 為預設

## Links
- Proposal: specs/strategies/2026-03-12-reversal.md
