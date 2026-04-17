# Backtest Results: Night Vol → EstRange Reach Rate

## Date
2026-04-17

## Phase 2 Key Findings

### SatZone 出場機制 × 夜盤波動

| | EstHL STOP | EstHL GO | Reversal STOP | Reversal GO |
|--|-----------|---------|--------------|------------|
| SatZone 觸發率 | 49.5% | 57.9% | 45.8% | 45.4% |
| R/R median | 1.59 | 2.13 | 2.76 | 2.92 |
| SL 比例 | 24.8% | 25.4% | 20.8% | 20.6% |

EstHL 出場受夜盤影響（SatZone 觸發率差 8%），Reversal 不受影響（差 0.4%）。

### SatZone 縮放：無效

低夜盤日縮放 SatZone（scale 0.65~0.90）無法讓 PF 超過 1.0。不如直接不做。

### R/R 門檻：無效

R/R ratio 對績效無顯著區分力。

### Config 比較（IS/OOS）

**EstHL：**
| Config | IS PF / Sharpe | OOS PF / Sharpe |
|--------|---------------|-----------------|
| A: 現狀 (weekday+NVF) | 3.02 / 6.77 | 3.46 / 8.21 |
| B: NVF only (無星期) | 2.37 / 5.39 | 1.71 / 3.26 |

**Reversal：**
| Config | IS PF / Sharpe | OOS PF / Sharpe |
|--------|---------------|-----------------|
| A: 現狀 (weekday+NVF) | 1.55 / 2.54 | 2.21 / 3.73 |
| B: NVF only (無星期) | 1.03 / 0.09 | 2.16 / 3.85 |

星期濾網不能被夜盤濾網取代。兩者各自解釋不同因素。

## Verdict

**Confirmed**（2026-04-17）

Phase 1 發現正確：夜盤波動解釋力是星期的 7.4 倍。但 Phase 2 證明無法轉化為策略改進：
- 縮放 SatZone 無效
- R/R 門檻無效
- 星期濾網不可取代

現有規則（星期 + NVF 硬規則）維持不變。
