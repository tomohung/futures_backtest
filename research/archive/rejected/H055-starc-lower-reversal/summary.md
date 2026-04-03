# Archive: STARC 下軌觸及後反轉做多

## Status
Rejected

## Summary
測試 STARC 下軌（SMA6 - 2×ATR15）觸及後次日做多的反轉效果。反轉率 65.6%（N=64）、次日平均 +108pt，IS/OOS 一致且參數穩健。但 edge 完全來自隔夜跳空 gap，次日盤中做多為負期望值（PF=0.89）。且與 S003 Exhaustion 重疊率高達 80%，獨立價值有限。

## Key Evidence
- 下軌觸及：N=64, 反轉率 65.6%, AvgPnL=+108pt（Close-to-Close）
- IS/OOS 一致：IS 65.4% / OOS 66.7%
- 參數穩健：所有組合反轉率 55-68%
- 上軌無反轉效果（46%），非對稱性確認
- **次日盤中做多為負期望值**：開盤進場 PF=0.89, AvgPnL=-9pt
- 平均開盤後回檔 186pt，等回檔也無法改善
- 與 S003 Exhaustion 重疊率 79.7%

## Why Rejected
- Edge 來自隔夜跳空 gap，無法作為日盤當沖信號
- 與現有 S003 策略高度重疊，獨立價值不足

## Derived Hypotheses
- STARC 下軌 + 隔夜持倉：收盤做多、次日開盤平倉，捕捉 gap up
- STARC 下軌作為 S003 增強信號：同時觸發時提高 conviction

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Explore Script：explore.py
