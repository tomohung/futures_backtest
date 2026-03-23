# Archive: 結算日 Volume 校正 + SatZone Fraction 實驗

## Status
Confirmed

## Summary
結算日（每月第三週三）ohlcv_1m 只存主力合約量，但結算日量分散到新舊合約（~55/45），主力量僅為實際的一半，導致 EstRange 低估、SatZone 太窄。實測 61 個結算日合併量/主力量中位數為 1.90，採用固定乘數 1.9 校正。另外嘗試將 SatZone 公式從 `est_range - ema_hl/8` 改為 `est_range * fraction`，實驗失敗，維持原公式。

## Key Evidence
- 61 個結算日（2021-2026）合併量/主力量比值：平均 1.90，盤中各 5 分鐘 slot 幾乎恆定（1.88-1.95）
- 3/18 實案：進場時 SatZoneUpper（34484）已低於進場價（34498），Phase 1 立刻觸碰導致秒殺出場 -43 pts
- SatZone fraction 實驗（2024-2026 EstHL 策略）：原版 (x1.9, -ema/8) +3177 > x2.3 fraction=0.70 +2539 / fraction=0.875 +2688
- `est_range * fraction` 和 `est_range - ema_hl/8` 不等價：舊公式用 ema_hl（前一天固定值）做 offset，新公式用 est_range（盤中變動值）做乘數
- vol_mult=2.3 雖然觸及率更接近一般日（37% vs 59%），但超過實際合併量，缺乏物理依據

## Why Confirmed
vol_mult=1.9 有明確物理意義（實測合併量/主力量中位數），且盤中恆定不需時間函數。SatZone fraction 實驗明確失敗（所有 fraction 組合績效皆低於原公式），確認 `-ema_hl/8` 的固定 offset 設計優於乘數設計，因為 offset 在 est_range 變動時提供穩定的緩衝。

## Derived Hypotheses
- EMA 污染問題：膨脹的量會進入 EMA 歷史影響隔天 EstRange，未來可考慮在 EMA 更新時用原始量
- Est High/Low 做多做空可能需要不同 fraction，但需配合出場機制一起設計

## Links
- Proposal: specs/strategies/2026-03-20-settlement-volume-satzone.md
