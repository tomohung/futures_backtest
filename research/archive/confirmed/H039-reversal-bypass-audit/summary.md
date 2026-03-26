# Archive: Reversal CCD Bypass Conditions Audit

## Status
Confirmed

## Summary
審計 Reversal 策略 4 種 CCD bypass 條件的邊際貢獻。結果顯示 VWAP bypass 和 Exhaustion
可以安全移除，簡化為「CCD correct → 進場，CCD wrong → 等 2nd BB touch」的邏輯。
Ablation 回測確認簡化版（A+D）總損益 +2,735pt 略優於現行版（A+B+C+D）+2,669pt。

## Key Evidence

### Phase 1: Exclusive trigger 勝率（N=734，5.25 年）
| 條件 | Exclusive N | Exclusive 勝率 |
|------|------------|---------------|
| 2nd BB touch | 119 | **58.8%** |
| CCD correct | 94 | 51.1% |
| Exhaustion | 105 | 51.4% |
| VWAP bypass | 5 | N 太小 |

- CCD correct 進場（49.7%）反而低於 bypass 進場（53.3%）
- 2025 年 exclusive 2nd BB touch 勝率 72%（N=25）
- VWAP bypass 幾乎不獨立觸發（exclusive N=5），2025 年參與的交易勝率僅 37%

### Phase 2: Ablation 回測
| 版本 | N | Total PnL |
|------|---|-----------|
| A+B+C+D (current) | 470 | +2,669 |
| **A+D (simplified)** | **446** | **+2,735** |
| A+B+D (no VWAP) | 473 | +2,736 |

簡化版少 24 筆交易但總損益反而略好。

### 補充：BB touch 時間分析
- 9:30 前 BB touch 勝率 53.0% > 9:30 後 50.4%
- 時間不是有效的分組因子

## Why Confirmed
1. VWAP bypass 幾乎不獨立觸發（N=5），移除零影響
2. Exhaustion 增加交易量但不改善期望值（exclusive 勝率 51.4% ≈ 基準）
3. Ablation 回測確認移除後績效持平或略好
4. 簡化邏輯回歸原始設計直覺：CCD ok → 進場，CCD wrong → 等 2nd BB

## Action Items
- [ ] 修改 `src/strategies/reversal.py`：移除 exhaustion bypass 和 VWAP bypass
- [ ] 簡化後的進場邏輯：`ccd_ok OR bb_count >= 2`
- [ ] Exhaustion 情境（開盤拉高後急殺反轉）保留為未來獨立研究

## Derived Hypotheses
- **HXXX-exhaustion-reversal-pattern**：開盤拉高後急殺的特定 pattern，exhaustion 在此情境可能有效（與一般 BB touch 不同）
- ~~HXXX-2nd-bb-standalone~~：已由本研究覆蓋
- ~~HXXX-ccd-inversion~~：CCD 反向表現較好可能只是 mean-reversion 特性，非獨立假設

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Ablation script：ablation.py
- Explore script：explore.py
