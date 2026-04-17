# Archive: Night Vol → EstRange Reach Rate

## Status
Confirmed (finding valid, no strategy change)

## Summary
夜盤波動對日盤 EstRange 觸及率的解釋力是星期的 7.4 倍（R²=0.097 vs 0.013）。夜盤 norm >= 1.30 時 61% 碰到 1× EstRange，norm < 0.70 時只有 30%。但 Phase 2 證明無法轉化為策略改進——縮放 SatZone 和 R/R 門檻都無效，星期濾網不可被夜盤取代。現有規則（星期 + NVF 硬規則）維持不變。

## Key Evidence
- Night norm R²=0.0966 vs weekday R²=0.0130（7.4 倍）
- Reach rate: norm < 0.70 → 30%, norm >= 1.30 → 61%
- 跨年穩定 5/6
- SatZone 縮放：STOP 天所有 scale PF ≈ 1.0，不如不做
- Config A（現狀）IS/OOS 均最佳

## Why Confirmed
Phase 1 發現有學術價值——解釋了為什麼夜盤濾網有效（夜盤波動 → reach rate → 策略品質）。但實務上不改動策略。

## Links
- Proposal：proposal.md
- Phase 1：results/distribution.md
- Phase 2：results/backtest.md, phase2_plan.md
- Scripts：explore.py, backtest.py
