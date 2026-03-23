# Proposal: ORBLong 策略重新研究

## ID
H030

## Derived From
H002, H025

## Trading Intuition
ORBLong 是現有的趨勢跟隨策略（OR 突破 + TrendMA），2021-2026 共 +4,970 pts。但有改進空間：
1. 出場仍用固定 % SL + OR x TP + trailing stop，未利用 EstRange/SatZone
2. 未分析與 Regime 健康指標的關係
3. 與 EstHL 的互補性需要量化（目前 daily correlation 0.171，但未做完整研究）

## Hypothesis
四個研究方向：

### A. ORBLong x Regime 指標交叉分析
用 `strategy_health.py` 的 `compute_daily_regime()` 取得每日 regime 指標，與 ORBLong 交易結果做交叉分析。預期 ORBLong 對 range_pct 應該也敏感。

### B. ORBLong x EstHL 重疊分析
跑兩策略全歷史，按 entry_date 比對重疊率、損益相關性、互斥日績效。確認兩策略是否真的互補，還是只是進場時間不同的同一策略。

### C. Weekday 效應（百分比化）
ORBLong 各星期績效全部用 pnl_pct，基本五日統計、週四 x OR% 交叉、週四/五 x regime 交叉。

### D. ORBLong 出場改 SatZone（核心實驗）
新策略類別 `ORBLongEstRangeStrategy`，進場邏輯與 ORBLong 相同，出場改為 EstRange 系統：
- SL：EmaHL x sl_fraction（取代固定 0.4%）
- SatZone 兩階段：Phase 1 觸碰 + Phase 2 跌破 5MA
- Dow pivot trailing：09:45+ 啟動
- 新參數 `sat_fraction`：OR% 大 → fraction 大 → 讓利潤跑更多

## Expected Distribution
1. SatZone 出場優於固定 TP：新策略 PF > 2.33 或 Sharpe > ORBLong baseline
2. OR% x fraction 有效：動態 fraction 優於固定 fraction（至少 +5% PnL）
3. 與 EstHL 維持互補：daily correlation < 0.3，組合 Sharpe > 單策略
4. 2021 不崩：不比現行 ORBLong 2021 更差（-498 pts baseline）

## Invalidation Condition
- SatZone 為早盤校準，09:30+ 進場時 zone 可能已部分消耗（先前 `ORBLongWithEstHLExitStrategy` 表現不佳就是這個原因）
- OR% x fraction 動態調整無法解決此問題
- 與 EstHL 高度相關（daily correlation > 0.5），組合效果下降

## Notes
### 現行 ORBLong 參數
```
entry: OR 突破（08:45-09:30 區間），entry_end=11:00
exit:  SL=0.4%, TP=OR x 1.5, trailing(09:45+), force=13:00
filter: TrendMA(10d), OR% 0.3-1.0%, thu_or_pct_min=0.7
result: 207 trades, WR 59%, PF 2.33, +4,970 pts
```

### OR% x fraction 動態調整（初始假設）
```python
if or_pct >= 0.7:
    sat_fraction = 1.0    # 大波動日，讓 SatZone 完整觸發
elif or_pct >= 0.5:
    sat_fraction = 0.85   # 中等波動
else:
    sat_fraction = 0.70   # 小波動日，提早了結
```

### 參數網格
```python
GRID = {
    "sl_ema_fraction": [0.20, 0.25, 0.30, 0.35],
    "sat_fraction":    [0.70, 0.85, 1.0],
    "force_exit_minute": [285, 300],        # 12:45 vs 13:00
    "entry_end_minute":  [90, 105, 120],    # 10:30, 10:45, 11:00
}
```

### 備選方案
若 SatZone 出場不改善 ORBLong：
- 保持現行 ORBLong 出場，只加入 regime 濾網
- 嘗試 EmaHL 動態 SL（取代固定 0.4%），保留 OR x TP
- 嘗試分時段出場：早期用 OR x TP，達到 SatZone 後轉兩階段出場

### 相關檔案
- `src/backtest/explore_orblong_regime.py` — 探索分析（A-C）
- `src/strategies/orb_long_estrange.py` — 新策略類別（D）
- `src/backtest/optimize_orblong_estrange.py` — 參數回測（E）
- `src/backtest/runner.py` — `load_data_for_orblong_estrange()`
- `src/backtest/strategy_health.py` — `compute_daily_regime()`
- `src/strategies/estimate_hl_exit.py` — `EstimateHLExitMixin`
