# Proposal: 出場策略交叉實驗

## ID
H027

## Derived From
H001, H002

## Trading Intuition
現有兩套成熟策略：
- **ORBLong**：寬進場窗口（09:30-11:00），固定 % SL + OR 寬度 TP + trailing stop
- **EstHL**：嚴格早盤進場（08:58-09:05），EmaHL SL + SatZone 兩段式出場 + Dow Trail Stop

兩者比較發現：
- EstHL 早年（2021-2023）明顯較優（2021: +404 vs -498）
- ORBLong 近年（2024-2026）全面碾壓（2025: +1,823 vs +634）
- 差異可能來自**出場機制**，而非進場機制

## Hypothesis
交叉組合兩策略的進場與出場，可驗證出場策略的貢獻是否是主要差異來源：
- **方向 A**：EstHL 進場 x ORBLong 出場 — 嚴格進場 + 靈活出場
- **方向 B**：ORBLong 進場 x EstHL 出場 — 寬鬆進場 + SatZone 出場

## Expected Distribution
### 方向 A
- 全年正報酬（2021 從 -498 修復）
- 跨年穩定性優於單一策略
- 總損益介於 EstHL 與 ORBLong 之間

### 方向 B
- [TODO] — 需驗證 SatZone 出場是否適用於較晚進場

## Invalidation Condition
### 方向 A
- 2021 仍為虧損年 → 進場品質不是核心因素
- 總損益低於 EstHL → 出場改善不足以補償

### 方向 B（已失敗）
- SatZone 出場針對早盤進場設計；09:30-11:00 進場時，當日預估區間目標已部分消化，SatZone 失效

## Notes
### 方向 A 結果（EstHL 進場 x ORBLong 出場）

**最終回測結果（tp_or_multiplier=3.0，entry_end=09:15，只做多）：**

| 年份 | 筆數 | PF | 總損益 | ORBLong | EstHL |
|------|------|----|--------|---------|-------|
| 2021 | 53 | 1.59 | **+867** | -498 | +535 |
| 2022 | 37 | 1.52 | **+484** | +228 | +831 |
| 2023 | 41 | 1.37 | **+389** | +302 | +542 |
| 2024 | 39 | 1.72 | **+980** | +1,037 | +1,153 |
| 2025 | 48 | 1.25 | **+523** | +1,823 | +542 |
| 2026 YTD | 10 | 3.30 | **+978** | +1,723 | +117 |
| **合計** | **228** | | **+4,221** | | |

結論：
- 全年正報酬 — 2021 從 -498 修復至 +867
- 進場窗口延伸至 09:15 — 總損益 +4,221（比 09:05 的 +3,613 多 +608）
- 適合追求**跨年穩定性**的保守配置

### 方向 B 結果（ORBLong 進場 x EstHL 出場）— 失敗

除 2021 略有改善外，其餘年份遠差於兩個母策略。原因：SatZone 出場針對早盤進場設計；09:30-11:00 進場時，當日預估區間目標已部分消化，SatZone 失效。

### 相關檔案
- `src/strategies/orb_crossover.py` — `EstHLEntryORBLongExitStrategy`、`ORBLongWithEstHLExitStrategy`
- `src/backtest/run_orb_crossover.py` — 執行腳本
