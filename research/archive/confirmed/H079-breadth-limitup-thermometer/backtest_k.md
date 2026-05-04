# H079-K：把 RATIO defense filter 套到既有 live 策略

**目的**：驗證 H079-C 的 RATIO 萎縮事件 defense 訊號，套到 confirmed 策略上是否真的能加值。
**腳本**：`h079k_filter.py`（post-processing 設計，不修改原策略 code）
**樣本**：2021-01-01 ~ 2026-04-30
**IS / OOS 切點**：2024-01-01

## 設計

1. 跑 live 策略 baseline → 取 trades CSV (EntryTime, ExitTime, PnL)
2. 用 H079-C 最佳參數計算 defense window：`logic=RATIO, ma=7, pct=0.15, consec=3, skip_n=10`
3. 把 entry_date 落在 defense window 的交易過濾掉
4. 比較 baseline vs filtered

**Defense window 設定**：覆蓋 1289 天中的 315 天（24.4%），128 個事件天

---

## 結果

### S001 (EstHL, long-only) — Defense **反向**❌

| 切片 | Baseline PnL/Sharpe | Filtered PnL/Sharpe | 跳掉的交易 |
|------|---------------------|----------------------|------------|
| Full | +5119 / **5.35** | +3529 / 4.66 | 35 筆，**+45.4 pts/筆**, 勝率 **74%** |
| IS | +1510 / 3.91 | +887 / 3.13 | 28 筆，+22.2 pts/筆 |
| **OOS** | +3609 / **7.21** | +2642 / 6.31 | 7 筆，**+138 pts/筆**, 勝率 **86%** |

**為什麼反向**：
- S001 已經有強 filter（NVF + VWAP + 30分20MA + skip Thu/Fri）
- 萎縮事件期間 S001 的訊號**反而是逆境中的好機會**
- 加 H079 filter 等於過濾掉好交易

→ **S001 不要套 H079 defense filter**

### S002 (Reversal) — Defense **明顯改善**✅

| 切片 | Baseline (PnL/Sharpe/MaxDD) | Filtered (PnL/Sharpe/MaxDD) | 變化 |
|------|------------------------------|------------------------------|------|
| Full | +3050 / 1.03 / -959 | +3097 / **1.43** / **-631** | PnL +47, Sharpe +0.40, MaxDD **+328 (改善 34%)** |
| IS | +59 / 0.04 / -651 | +127 / 0.19 / -631 | PnL +68, Sharpe +0.15 |
| **OOS** | +2991 / 2.14 / -959 | +2970 / **2.71** / **-622** | PnL -21（持平）, Sharpe **+0.57 (+27%)**, MaxDD **+337 (改善 35%)** |

**為什麼有效**：
- Reversal 是均值回歸策略，依賴震盪
- 萎縮事件期間市場進入趨勢/恐慌模式，反轉訊號失效
- 被跳過的 134 筆平均 -0.4 pts/筆（IS 跳過甚至 -0.8 pts/筆）→ 確實是壞時機

→ **S002 適合套，但需先觀察一段時間**

---

## 解讀：策略類型決定 defense 適用性

| 策略類型 | H079 defense 適用 |
|----------|----------------------|
| **趨勢/突破型**（S001 ORB-EstHL）| ❌ 已有強 filter、訊號日逆境也賺 |
| **反轉/均值回歸型**（S002 Reversal）| ✅ 萎縮期間趨勢化使反轉失效，filter 救回風險 |

完全符合策略本質：均值回歸在「資金結構崩壞」期會失效（市場進入單邊趨勢），而趨勢策略反而能受惠於這種環境。

---

## 決策：先當觀察指標，不立即上 live

考量：
1. S002 已有眾多 filter（NVF、BB latch、exhaust、vol_ratio、near-SatZone、weekday skip 等）
2. 再加 H079 會讓 spec 過度複雜
3. 樣本期不夠長（OOS 只 2.3 年），需更多實況驗證

**最終實作**：
- 寫成 `src/analysis/breadth_thermometer.py` 加入 morning_briefing pipeline
- 每日輸出狀態（綠/黃/橙/紅燈）+ 14 天軌跡
- 觀察 1-3 個月後，再決定是否寫進 S002 spec

整合點：
- `src/etl/daily_update.py`：新增 Step 0c (download_stock_market) + Step 1c (parse_stock_market)
- `src/analysis/morning_briefing.py`：新增 breadth_thermometer 呼叫
- 預設參數：RATIO ma7 pct=0.15 consec=3 skip_n=10

---

## Verdict：✅ Pass（但以觀察形式上線）

S002 的 +27% Sharpe + 35% MaxDD 改善 證實訊號有效，但 OOS 樣本不夠長。先進入「觀察期」，由日常 briefing 累積真實資料再決定。
