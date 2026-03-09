# ORB Phase 2：全參數掃描（含 Trend MA Filter）

## Phase 1 結論

| Filter | 結果 |
|---|---|
| Range Size (`min_range_pct`) | ❌ 無效，PF 反而下降 |
| **Trend MA (`trend_ma_days`)** | ✅ 有效，最佳 PF 1.229（day-only MA） |
| Gap (`max_gap_pct`) | ❌ 無效，PF 反而下降 |

### Trend MA 細掃結果（2023–2025 train）

| `trend_ma_days` | Trades | Win Rate | PF | Expectancy |
|---|---|---|---|---|
| 9 | 325 | 48.0% | 1.229 | +9.7 |
| **10** | **323** | **48.0%** | **1.215** | **+9.1** |
| 7 | 321 | 47.4% | 1.214 | +9.1 |
| 0 (baseline) | 609 | 44.7% | 1.082 | +3.4 |

**選定 `trend_ma_days=10`**（兩週交易日，語意清晰，OOS 與 9 相同）

### 夜盤 MA 比較

Day-only MA 優於 night MA（7~10 天範圍），不引入夜盤 MA。

---

## Phase 2 計畫

### 目標

固定 `trend_ma_days=10`，掃描其餘 5 個基礎參數，找出最佳組合。

### 參數網格

| 參數 | 測試值 | 說明 |
|---|---|---|
| `range_end_minute` | 60, 75, 90, 105 | 08:00+N，OR 窗口 15/30/45/60 分鐘（原 30/45 無效，已移除） |
| `entry_end_minute` | 75, 90, 105, 120, 150 | 必須 > range_end_minute |
| `sl_pct` | 0.003, 0.005, 0.007, 0.010 | 停損比例 |
| `tp_multiplier` | 1.5, 2.0, 2.5, 3.0 | 停利倍數 |
| `trail_activate_minute` | 30, 45, 60, 90 | 移動停損啟動時間（從 09:00 起算） |
| `trend_ma_days` | **10**（固定） | 兩週交易日 MA |

有效組合：**896 組**（已扣除 entry_end ≤ range_end 的無效組合）

### 執行

```bash
uv run python src/backtest/optimize.py
```

Train: 2023–2025 | OOS Test: 2026

### 成功標準

| 指標 | Train 目標 | OOS 門檻 |
|---|---|---|
| 勝率 | ≥ 52% | ≥ 50% |
| 平均盈虧比 | ≥ 1.3 | — |
| 獲利因子 | ≥ 1.2 | ≥ 1.0 |

---

## 待更新：Phase 2 結果

（跑完後填入）
