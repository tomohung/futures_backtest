# ORBLong 策略重新研究

## 背景與動機

ORBLong 是現有的趨勢跟隨策略（OR 突破 + TrendMA），2021-2026 共 +4,970 pts。
目前與 EstHL 作為研究基準，但有改進空間：

1. 出場仍用固定 % SL + OR×TP + trailing stop，未利用 EstRange/SatZone
2. 未分析與 Regime 健康指標的關係
3. 與 EstHL 的互補性需要量化（目前 daily correlation 0.171，但未做完整研究）

### 現行 ORBLong 參數

```
entry: OR 突破（08:45-09:30 區間），entry_end=11:00
exit:  SL=0.4%, TP=OR×1.5, trailing(09:45+), force=13:00
filter: TrendMA(10d), OR% 0.3-1.0%, thu_or_pct_min=0.7
result: 207 trades, WR 59%, PF 2.33, +4,970 pts
```

---

## 研究方向

### A. ORBLong × Regime 指標交叉分析

用 `strategy_health.py` 的 `compute_daily_regime()` 取得每日 regime 指標，
與 ORBLong 交易結果做交叉分析。

**分析項目：**
- 四分位分析：range_pct / ER / swing_count / ATR% / ADX 各分四組，看勝率/pnl_pct
- Point-biserial correlation（指標 vs win/loss）
- 與 EstHL 的 regime 敏感度比較（EstHL ER r=+0.397，ORBLong 是多少？）

**預期：** ORBLong 對 range_pct 應該也敏感（需要足夠波動才能突破獲利），但可能與 EstHL 不同。

### B. ORBLong × EstHL 重疊分析

跑兩策略全歷史，按 entry_date 比對：
- 同日交易比例（overlap rate）
- 同日交易時兩策略的損益相關性
- 互斥日（只有一邊有交易）的績效
- 組合效果：各半倉 vs 全倉單策略
- 分年度看重疊趨勢

**目的：** 確認兩策略是否真的互補，還是只是進場時間不同的同一策略。

### C. Weekday 效應（百分比化）

ORBLong 各星期績效，全部用 pnl_pct：
- 基本五日統計
- 週四 × OR% 交叉（現行 thu_or_pct_min=0.7 效果）
- 週四/五 × regime 交叉（與 EstHL 結論對比）

**已知：** 週四 WR 43%, PF 0.87（-215 pts），thu_or_pct_min=0.7 有改善。

### D. ORBLong 出場改 SatZone（核心實驗）

**新策略類別 `ORBLongEstRangeStrategy`**（繼承 EstimateHLExitMixin + Strategy）

進場邏輯與 ORBLong 相同：
- OR 區間：08:45-09:30
- 突破進場：close > OR_high + TrendMA 確認
- OR% 濾網：0.3%-1.0%
- 只做多

出場改為 EstRange 系統：
1. **SL**：EmaHL × sl_fraction（取代固定 0.4%）
2. **SatZone 兩階段**：Phase 1 觸碰 + Phase 2 跌破 5MA
3. **Dow pivot trailing**：09:45+ 啟動
4. **Force exit**：13:00

**新參數：`sat_fraction`**
- 控制 SatZone 到達的判定寬鬆度
- 假設：OR% 大 → 趨勢強 → fraction 可以大 → 讓利潤跑更多
- OR% 小 → 波動小 → fraction 應小 → 早點獲利了結

**OR% × fraction 動態調整：**
```python
if or_pct >= 0.7:
    sat_fraction = 1.0    # 大波動日，讓 SatZone 完整觸發
elif or_pct >= 0.5:
    sat_fraction = 0.85   # 中等波動
else:
    sat_fraction = 0.70   # 小波動日，提早了結
```
（需要數據驗證，以上為初始假設）

### E. 參數網格回測

在新策略上測試：

```python
GRID = {
    "sl_ema_fraction": [0.20, 0.25, 0.30, 0.35],
    "sat_fraction":    [0.70, 0.85, 1.0],  # 或動態
    "force_exit_minute": [285, 300],        # 12:45 vs 13:00
    "entry_end_minute":  [90, 105, 120],    # 10:30, 10:45, 11:00
}
```

固定參數：
```python
range_end_minute=90, or_min_width=20, trend_ma_days=10,
or_pct_min=0.3, or_pct_max=1.0, thu_or_pct_min=0.7
```

---

## 資料載入

需新建 `load_data_for_orblong_estrange()` 合併兩邊欄位：

| 來自 load_data_with_night_ma | 來自 load_data_for_orb_est_hl |
|-----|------|
| TrendMA（連續日夜 10d MA） | EmaHL, SatZone*, EstRange* |
| RollingOR | MA30_20, Close30 |
| DailyADX | BigCost1, BigCost2 |
| | ORWidth, GapSize, NightReturn |

## 成功標準

1. **SatZone 出場優於固定 TP**：新策略 PF > 2.33 或 Sharpe > ORBLong baseline
2. **OR% × fraction 有效**：動態 fraction 優於固定 fraction（至少 +5% PnL）
3. **與 EstHL 維持互補**：daily correlation < 0.3，組合 Sharpe > 單策略
4. **2021 不崩**：不比現行 ORBLong 2021 更差（-498 pts baseline）

## 需新建的檔案

| 檔案 | 用途 |
|------|------|
| `src/backtest/explore_orblong_regime.py` | 探索分析（A-C） |
| `src/strategies/orb_long_estrange.py` | 新策略類別（D） |
| `src/backtest/optimize_orblong_estrange.py` | 參數回測（E） |
| `src/backtest/runner.py` | 新增 `load_data_for_orblong_estrange()` |

## 需複用的現有程式碼

| 來源 | 函式/類別 |
|------|----------|
| `src/backtest/strategy_health.py` | `compute_daily_regime()` |
| `src/backtest/runner.py` | `load_data_with_night_ma()`, `load_data_for_orb_est_hl()` |
| `src/strategies/estimate_hl_exit.py` | `EstimateHLExitMixin` |
| `src/strategies/orb.py` | `ORBLongStrategy`（進場邏輯參考） |

## 已知風險

1. **SatZone 為早盤校準**：09:30+ 進場時 zone 可能已部分消耗。先前 `ORBLongWithEstHLExitStrategy` 表現不佳就是這個原因。OR% × fraction 動態調整是嘗試解決此問題。
2. **過度擬合**：五維網格 × 六年 = 參數空間大，需要 IS/OOS 切分驗證。
3. **與 EstHL 過度重疊**：如果新策略與 EstHL 高度相關，組合效果會下降。

## 備選方案

若 SatZone 出場不改善 ORBLong：
- 保持現行 ORBLong 出場，只加入 regime 濾網
- 嘗試 EmaHL 動態 SL（取代固定 0.4%），保留 OR×TP
- 嘗試分時段出場：早期用 OR×TP，達到 SatZone 後轉兩階段出場
