# Archive: 策略健康監測（Regime 預警系統）

## Status
Rejected

## Summary
建立日盤振幅百分比（Range%）、效率比率（ER）、方向翻轉次數等 regime 指標，嘗試提前預警 EstHL/Reversal 策略績效衰退。經完整驗證（EMA 閾值、Lookback window、連續天數等多種規則），所有暫停規則都讓總損益下降，無法作為交易濾網或提前預警。

## Key Evidence
- ER 是最強單筆預測指標（r=+0.397），但為事後指標（進場時無法得知當日 ER）
- Range% EMA(20) 暫停閾值 <0.74%：僅過濾 4 筆且全部獲利（WR 100%）
- Lookback window 預警（lb20/40/60, <0.90%, >50%）：被過濾交易 WR 57-62%，全部暫停規則都降低總損益
- EMA(20) 連續低於閾值 1-5 天：WR 31.2%，但僅 16 筆，統計不足
- Reversal 對所有 regime 指標不敏感（|r| < 0.07）
- 週四/五 × Regime 交叉：EMA(20) 太平滑，85 筆中 80 筆通過基本閾值

## Why Rejected
EstHL 已有足夠的內建濾網（weekday、OR width、BigCost、ADX），低品質交易已被大量過濾。Range% 偏低期間，通過濾網的交易反而品質不差。所有暫停規則的淨效果都是「過濾掉賺錢的交易」。

## Derived Hypotheses
- regime_health.py 保留供未來研究，但已從 morning_briefing.py 移除
- 確認 EstHL 內建濾網已足夠，不需外部環境預警

## Links
- Proposal: specs/strategies/2026-03-21-strategy-health-monitor.md
