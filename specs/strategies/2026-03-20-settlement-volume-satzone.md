# 結算日 Volume 校正 + SatZone Fraction 實驗

## 日期
2026-03-20

## 背景

3/18（月結算日）EstHL 策略在 08:58 進場後 2 分鐘就被 SatZone 出場（-43 pts），原因：

1. ohlcv_1m 只存主力合約的量，結算日量分散到新舊合約（~55/45），主力量約為實際的一半
2. EstRange 用量估算振幅，量少一半 → 預估振幅偏小 → SatZone 太窄
3. 進場時 SatZoneUpper（34484）已低於進場價（34498），Phase 1 立刻觸碰 → Phase 2 秒殺出場

## 分析

### 結算日量分佈

61 個結算日（2021-2026）的合併量/主力量比值：
- 全日平均 ≈ 1.90，盤中各 5 分鐘 slot 幾乎恆定（1.88~1.95）
- 不需要時間函數，固定乘數即可

### Vol_mult 搜尋（目標：100% EstRange either ≈ 一般日 38%）

2024-2026 結算日 27 筆：

| vol_mult | 100% either |
|:---:|:---:|
| 1.0 | 96% |
| 1.5 | 89% |
| 1.9 | 59% |
| 2.1 | 56% |
| **2.3** | **37%** ← |
| 2.5 | 30% |

**結論：vol_mult = 2.3**

### SatZone Fraction 實驗

嘗試將 SatZone 公式從 `est_range - ema_hl/8` 改為 `est_range * fraction`。

一般日 fraction 分析（2024-2026, n=504）：

| fraction | H觸及 | H獲利 | H錯過 | L觸及 | L獲利 | L錯過 | either |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 0.65 | 61% | 102 | 92 | 58% | 94 | 95 | 86% |
| 0.70 | 53% | 117 | 90 | 49% | 108 | 96 | 81% |
| 0.75 | 45% | 134 | 90 | 42% | 123 | 97 | 72% |
| 0.80 | 39% | 152 | 88 | 36% | 142 | 98 | 65% |
| 0.85 | 33% | 171 | 90 | 30% | 158 | 103 | 57% |

觀察：H_miss（錯過利潤）在所有 fraction 都差不多 88~101 pts，fraction 大小主要影響捕獲利潤。

### 回測比較（2024-2026, EstHL 策略）

| 設定 | 2024 | 2025 | 2026 | 合計 |
|------|------:|------:|------:|------:|
| 原版 (×1.9, -ema/8) | +1326 (64.3%) | +1309 (57.7%) | +542 (60.0%) | +3177 |
| ×2.3, fraction=0.70 | +1184 (71.4%) | +1064 (57.7%) | +291 (60.0%) | +2539 |
| ×2.3, fraction=0.875 | +1192 (60.7%) | +1120 (53.8%) | +376 (50.0%) | +2688 |
| ×1.9, fraction=0.875 | +1239 (60.7%) | +1099 (53.8%) | +376 (50.0%) | +2714 |
| **×2.3, -ema/8** | **+1240 (64.3%)** | **+1197 (57.7%)** | **+510 (60.0%)** | **+2947** |

### 關鍵發現

1. `est_range * fraction` 和 `est_range - ema_hl/8` **不等價**，即使 fraction ≈ 0.875（1-1/8）
   - 舊公式用 **ema_hl**（前一天固定值）做 offset
   - 新公式用 **est_range**（盤中變動值）做乘數
   - 當 est_range > ema_hl 時，新公式 SatZone 更寬；反之更窄
2. fraction=0.70 勝率略高但平均獲利低（太早出場）
3. fraction=0.875 勝率明顯下降（2024 從 64.3% → 60.7%）
4. 舊公式 `-ema/8` 在各年度表現最穩定

## 最終決策

- **vol_mult = 1.9**（實測合併量/主力量中位數，物理意義明確）
- **SatZone 公式維持 `est_range - ema_hl/8`**（fraction 實驗失敗）
- Volume 調整方式：`adjust_settlement_volume()` 在載入後直接修改 Volume 欄位
- 結算日偵測：第三個週三，遇假日順延到下一個交易日
- 放棄 vol_mult=2.3（雖然觸及率更接近一般日，但超過實際合併量，缺乏物理依據）

## 實作範圍

### Python
- `src/backtest/estimate_hl.py` — `compute_vol_estimated_range` + `compute_estimate_hl_zones` 新增 `settlement_dates` / `settlement_vol_mult` 參數
- `src/backtest/runner.py` — `adjust_settlement_volume()` 函式 + `_settlement_dates()` 偵測邏輯
- 所有 loader 函式（load_data_for_orb_est_hl, load_data_for_reversal, load_data 等）套用

### Pine Scripts
- `est_range_tx.pine` — 結算日偵測 + `settle_vol_mult = 2.3`
- `orb_est_hl_tx.pine` — 同上
- `estrange_credit_spread_signal.pine` — 同上 + `skip_settlement` 改用 `is_settlement_day`

### 探索性 script
- `src/backtest/explore_satzone_fraction.py` — 本次實驗的分析工具

## 未來方向

- SatZone 目前只是出場機制之一，未來可搭配多種出場策略平均出場價分佈
- Est High/Low 的 fraction 做多做空可能需要不同值，但需要配合出場機制一起設計
- 結算日 EMA 污染問題：vol_mult 膨脹的量會進入 EMA 歷史，影響隔天的 EstRange；目前接受此行為，未來可考慮在 EMA 更新時用原始量
