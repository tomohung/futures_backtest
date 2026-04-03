# Distribution Research Results: Night Session Momentum Exhaustion

## Date
2026-04-04

## Conditions Tested
在所有 S003 信號日（BB%B extreme + MA direction + 夜盤新高低 + ORB 反向突破 + ORB% ≥ 0.25% + 排除 Wed/Thu），計算夜盤四個衰竭指標，分組比較日盤反轉績效。

PnL 計算簡化為 entry → 13:30 收盤，未套用 SatZone / SL / Trailing 等 S003 出場邏輯。

## Sample
- 總樣本數：N=67（short=38, long=29）
- 時間範圍：2021-01-01 ~ 2026-04-02
- 年度分佈：2021(10), 2022(11), 2023(5), 2024(12), 2025(21), 2026(8)
- 基準績效：WR=62.7%, PF=2.50, AvgPnL=+57.2pt

## 夜盤成交量趨勢
| 年份 | Avg Vol/Bar |
|------|-------------|
| 2021 | 98.0 |
| 2022 | 154.1 |
| 2023 | 111.6 |
| 2024 | 156.5 |
| 2025 | 116.8 |
| 2026 | 179.2 |

確認夜盤成交量整體呈上升趨勢，2022/2024/2026 特別活躍。

## Key Findings

### 四個衰竭指標分組比較

| Indicator | YES | | | | NO | | | |
|-----------|-----|------|------|--------|-----|------|------|--------|
| | N | WR | PF | AvgPnL | N | WR | PF | AvgPnL |
| RSI Divergence | 44 | 59.1% | 1.96 | +42.8 | 22 | 68.2% | 3.90 | +78.0 |
| Extreme Time ≤01:00 | 22 | 63.6% | 3.88 | +90.2 | 44 | 61.4% | 1.87 | +36.8 |
| Tail Retracement ≥median(0.153) | 33 | 69.7% | 3.90 | +85.0 | 33 | 54.5% | 1.50 | +24.1 |
| Volume Decay <median(0.520) | 33 | 69.7% | 3.41 | +68.6 | 33 | 54.5% | 1.83 | +40.5 |

### 逐指標分析

**1. RSI Divergence — 反直覺，方向相反**
- 有 RSI 背離（N=44）：WR=59.1%, PF=1.96 — 反而更差
- 無 RSI 背離（N=22）：WR=68.2%, PF=3.90 — 反而更好
- 解讀：夜盤 RSI 背離太常見（44/67 = 65.6%），幾乎是 baseline noise，無區分力。且在近年（2024-2026）方向完全反轉（有背離 PF=1.32 vs 無背離 PF=8.20）。**此指標無效。**

**2. Extreme Time ≤01:00 — 有潛力但方向與假設相反**
- 極值在 01:00 前出現（N=22）：PF=3.88, AvgPnL=+90.2pt — 顯著更好
- 極值在 01:00 後出現（N=44）：PF=1.87, AvgPnL=+36.8pt
- PF 差異 = 2.01，AvgPnL 差異 = +53.4pt
- 解讀：proposal 預期「極值越早 → 後段推不動 → 反轉更好」，數據確認此邏輯成立。**這是最有區分力的指標。**
- 但注意：median cutoff（26.7h ≈ 02:41）效果相反，說明 cutoff 選擇很敏感。

**3. Tail Retracement — 方向符合，中等區分力**
- 高回落（≥ median 0.153, N=33）：WR=69.7%, PF=3.90, AvgPnL=+85.0
- 低回落（< median, N=33）：WR=54.5%, PF=1.50, AvgPnL=+24.1
- PF 差異 = 2.40，有顯著區分力
- 但固定門檻 0.3 的 YES 組只有 N=12，樣本太少。**建議用 median split。**

**4. Volume Decay — 方向符合，中等區分力**
- 量衰減（< median 0.520, N=33）：WR=69.7%, PF=3.41, AvgPnL=+68.6
- 量不衰減（≥ median, N=33）：WR=54.5%, PF=1.83, AvgPnL=+40.5
- PF 差異 = 1.58
- 注意：固定門檻 0.8 效果反轉（量大反而好），說明多數夜盤本來就量衰減，0.8 cutoff 太寬。**median split 有效。**

### Combined Signals
| 門檻 | N | WR | PF | AvgPnL |
|------|---|----|----|--------|
| ≥0 | 67 | 62.7% | 2.50 | +57.2 |
| ≥1 | 64 | 62.5% | 2.45 | +56.5 |
| ≥2 | 49 | 59.2% | 2.28 | +54.5 |
| ≥3 | 16 | 50.0% | 2.06 | +49.1 |
| ≥4 | 5 | 80.0% | 3.13 | +84.6 |

組合指標未能改善績效。堆疊更多衰竭條件反而降低 PF（除 ≥4 外但 N=5 無統計意義）。

### 年度分析
| 時期 | N | WR | PF | AvgPnL |
|------|---|----|----|--------|
| 2021-2023 (早期) | 26 | 57.7% | 3.31 | +53.2 |
| 2024-2026 (近年) | 41 | 65.9% | 2.25 | +59.7 |

近年 WR 提升但 PF 下降（虧損擴大：AvgLoss 從 -54.3 → -139.9）。夜盤量放大並未明確改善訊號品質。RSI 背離在不同年代方向完全相反，穩定性存疑。

## Vs. Expected

| 預期 | 實際 | 符合 |
|------|------|------|
| 衰竭組 win rate / PF 顯著高於非衰竭 | Tail Retracement 和 Volume Decay 的 median split 有顯著差異（PF 差 2.4 和 1.6），但 RSI 背離方向相反 | 部分符合 |
| 夜盤量大年份訊號更有效 | 近年 WR 提升但 PF 反而下降，RSI 在不同年代不穩定 | 不符合 |
| 極值越早反轉越好 | ≤01:00 cutoff 確認（PF 3.88 vs 1.87），但 median cutoff 反轉 | 部分符合 |

## Gate Decision
[ ] 進入 Phase 2
[ ] Archive（原因：）
[ ] 修改假設（修改內容：）

## GATE 問題

### 1. 樣本數是否足夠？
- 總樣本 N=67 尚可
- 但分組後最佳的 Extreme Time ≤01:00 只有 N=22，Tail Retracement ≥ median 也僅 N=33
- 考慮到 S003 本身年均交易僅 ~14 筆，積累 20+ 筆需 1.5 年以上

### 2. 分佈方向是否符合預期？
- **Tail Retracement** 和 **Volume Decay** 方向正確，有中等區分力
- **Extreme Time** 在 ≤01:00 cutoff 下方向正確且區分力最強
- **RSI Divergence** 完全失敗，方向相反且不穩定
- Combined signals 未能改善，堆疊反而稀釋

### 3. 是否有 data snooping 疑慮？
- median split 本身就是 in-sample 最佳化，有 overfitting 風險
- Extreme Time 的 cutoff 敏感（01:00 有效但 median 02:41 反轉），穩健性存疑
- 簡化 PnL（未用 S003 出場邏輯）可能高估或低估實際效果
- N=67 做 4 個指標 × 2 個 cutoff = 8 次分組比較，multiple testing 風險

### 4. 總結建議
**有條件通過**：Tail Retracement 和 Volume Decay 各自有中等區分力（PF 差 1.5~2.4），值得在 Phase 2 用 S003 完整出場邏輯驗證。但：
- RSI Divergence 應捨棄
- Extreme Time 需更穩健的 cutoff 驗證
- 必須做 IS/OOS 分割，避免 median 最佳化的 overfitting

## Derived Hypotheses
- H0XX：**Tail Retracement 作為跨策略通用衰竭指標** — 如果尾段回落在 S003 有效，可能也適用於其他反轉型策略（S002 Reversal）
- H0XX：**夜盤極值時間與隔日開盤方向** — 極值在 01:00 前出現是否與隔日開盤 gap 方向有關聯（不限於 S003 條件）
