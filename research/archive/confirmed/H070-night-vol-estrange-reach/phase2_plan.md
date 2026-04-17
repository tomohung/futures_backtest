# H070 Phase 2 計畫：Night Vol × SatZone 調整

## 背景

Phase 1 發現夜盤波動決定日盤能不能走到 EstRange（R² 是星期的 7.4 倍）。
目前 SatZone 不看夜盤波動，低夜盤日的 SatZone 目標太遠，交易常等不到停利。

## 目標

測試兩個方向：
1. **夜盤低波動時縮小 SatZone**，讓停利更容易觸發
2. **進場時檢查 R/R ratio**，太差就不做

## Step 1：現狀分析（不改策略）

對 EstHL 和 Reversal 的每筆交易，記錄：
- 出場原因（SatZone Phase 2 / Dow trailing / 固定 SL / 時間停損 13:30）
- 進場時 SatZone 距離（entry_price 到 SatZoneUpper/Lower）
- 停損距離（sl_ema_fraction × EmaHL）
- R/R ratio = SatZone 距離 / 停損距離
- night_norm

分析：
- 高/低夜盤分組的出場原因分佈（SatZone 觸發率 vs 時間停損率）
- R/R ratio 的分佈 × night_norm

**這步的重點是理解「為什麼低夜盤日績效差」的機制。**

## Step 2：SatZone 縮放測試

在低夜盤波動（norm < 0.85）的日子，把 est_avg 乘以 scale factor：
- scale = 0.7, 0.75, 0.8, 0.85, 0.9, 1.0（1.0 = 不改）

測量：
- SatZone Phase 1 觸發率（是否更容易碰到）
- 整體 PF、WR、Sharpe 的變化
- 與「直接 STOP 不做」的比較

**關鍵問題：縮小 SatZone 後低夜盤日是否從負期望值變正？還是不如直接不做？**

## Step 3：R/R 門檻測試

進場時計算 reward/risk ratio：
- reward = SatZone 距離（可能已被 scale factor 調整）
- risk = 停損距離

如果 R/R < 門檻，跳過該交易。門檻測試範圍：0.5, 0.8, 1.0, 1.2, 1.5

**這是夜盤波動的間接效果——低夜盤 → SatZone 不縮的話離進場近 → R/R 差 → 自然被過濾。**

## Step 4：整合比較

| 配置 | 說明 |
|------|------|
| A | 現狀：星期濾網 + night_norm >= 0.85（H066/H067/H068） |
| B | 低夜盤縮放 SatZone + 保留星期濾網 |
| C | 低夜盤縮放 SatZone + R/R 門檻 + 保留星期濾網 |
| D | 所有日子都做 + 夜盤縮放 SatZone + R/R 門檻（無星期濾網）|
| E | 只用 night_norm 調整，完全不看星期（測試能否取代星期濾網）|

對 EstHL 和 Reversal 都測 IS/OOS。

## 預期結果

- Config A（現狀硬規則）可能仍是最簡單有效的
- Config B/C 如果能讓低夜盤日從負轉正，則增加交易機會
- Config D 是最激進的版本，看能否取代硬規則

## 實作注意

- SatZone 縮放需要修改 `estimate_hl.py` 或在 strategy 層面 override
- R/R 計算需要在進場時知道 SatZone 位置（已有：SatZoneUpper/Lower 欄位）
- night_norm 需要在 runner 層面計算並加入 DataFrame
