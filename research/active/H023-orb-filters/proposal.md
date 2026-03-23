# Proposal: ORB 策略過濾器優化

## ID
H023

## Derived From
H022

## Trading Intuition
裸 ORB 突破有太多低品質進場（假突破），需要從「區間幅度」「趨勢方向」「開盤跳空」三個維度過濾，減少低品質進場以提高期望值。

## Hypothesis
三類過濾器可獨立或組合改善 ORB 表現：
1. **開盤區間幅度過濾（OR Range Size）**：區間過窄（< 0.X%）時突破容易是假突破；區間夠大才代表有方向性共識
2. **趨勢方向過濾（Trend Filter）**：順大趨勢的 ORB 突破成功率較高；逆勢突破容易被打回
3. **開盤跳空過濾（Gap Filter）**：昨收與今開跳空過大時，行情已提前反應，ORB 的預測力下降

## Expected Distribution
| 指標 | 目標 |
|---|---|
| 勝率 | >= 52%（放寬至合理範圍） |
| 平均盈虧比 | >= 1.3 |
| 獲利因子 | >= 1.2 |
| 2026 OOS 勝率 | >= 50%（不退化） |
| 2026 OOS 獲利因子 | >= 1.0（不虧損） |

## Invalidation Condition
- Range Size 與 Gap Filter 均無效（PF 反而下降）
- 僅 Trend MA Filter 有效（Phase 1 結論）
- 若任何單一 filter 在 train 期間無法達標，該 filter 方向放棄

## Notes
### Phase 1 結論

| Filter | 結果 |
|---|---|
| Range Size (`min_range_pct`) | 無效，PF 反而下降 |
| **Trend MA (`trend_ma_days`)** | 有效，最佳 PF 1.229（day-only MA） |
| Gap (`max_gap_pct`) | 無效，PF 反而下降 |

### Trend MA 細掃結果（2023-2025 train）

| `trend_ma_days` | Trades | Win Rate | PF | Expectancy |
|---|---|---|---|---|
| 9 | 325 | 48.0% | 1.229 | +9.7 |
| **10** | **323** | **48.0%** | **1.215** | **+9.1** |
| 7 | 321 | 47.4% | 1.214 | +9.1 |
| 0 (baseline) | 609 | 44.7% | 1.082 | +3.4 |

**選定 `trend_ma_days=10`**（兩週交易日，語意清晰，OOS 與 9 相同）

Day-only MA 優於 night MA（7~10 天範圍），不引入夜盤 MA。

### Filter 實作
```python
class ORBStrategy(Strategy):
    min_range_pct: float = 0.0     # Filter 1: 最小區間幅度（0=不過濾）
    trend_ma_days: int = 0         # Filter 2: 趨勢均線天數（0=不過濾）
    max_gap_pct: float = 0.0       # Filter 3: 最大開盤跳空（0=不過濾）
```

### 相關檔案
- `src/strategies/orb.py` — Filter 參數及對應邏輯
- `src/backtest/optimize.py` — Filter 參數加入 `PARAM_GRID`
