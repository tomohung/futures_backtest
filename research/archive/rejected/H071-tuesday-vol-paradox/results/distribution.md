# Distribution Research Results: Tuesday Volatility Paradox

## Date
2026-04-21

## Conditions Tested
- 三策略：EstHL（ORBWithEstHLExitStrategy）、Reversal（ReversalStrategy）、Exhaustion（ExhaustionStrategy）
- **所有 weekday 過濾解掉**（EstHL 不 skip Thu/Fri、Exhaustion 不 skip Wed/Thu），確保五個星期都有樣本可比較
- 期間：資料集起始 → 2026-04-21（資料庫最新日）
- TrendMA：10 日連續日+夜 1m close 滾動平均
- NVF 閾值：night_norm ≥ 0.85（與 H067 一致）

## Sample
- Intraday 交易日：1,278 天
- EstHL 交易：247 筆（Tue 61）
- Reversal 交易：498 筆（Tue 97）
- Exhaustion 交易：134 筆（Tue 21）
- Tue 樣本合計：179 筆
- 跨年涵蓋：2021–2026

## Key Findings

### T1：Weekday × Strategy 績效（2021–2026 全期）

| Strategy   | Tue PF | Tue WR | Tue N | Tue 排名 | All-day PF | 結論 |
|------------|--------|--------|-------|----------|-------------|------|
| EstHL      | 1.74   | 54.1%  | 61    | **3 / 5**| 1.88        | 中段，**不是最弱** |
| Reversal   | 2.16   | 53.6%  | 97    | **5 / 5**| 1.27        | **全週最佳** |
| Exhaustion | 1.56   | 61.9%  | 21    | **5 / 5**| 1.00        | **全週最佳**（N 偏小） |

**比對 EstHL 實際交易日（Mon/Tue/Wed，因 Thu/Fri 已 skip）**：
- Mon PF=2.54, Tue PF=1.74, Wed PF=3.35 → Tue 是三天裡最弱的，與 Mon+Wed 平均 2.93 相比 -41%
- 但 Tue 仍然 **獲利**（PF > 1），不夠壞到值得新增濾網

**比對 Reversal 實際交易日（Tue/Wed/Thu，因 Mon/Fri 已 skip from H068）**：
- Tue PF=2.16, Wed PF=1.28, Thu PF=1.58 → Tue 是三天裡最強的

**Cross-year（Tue only）**：

| Year | EstHL Tue | Reversal Tue | Exhaustion Tue |
|------|-----------|--------------|----------------|
| 2021 | 1.36(19)  | 2.13(16)     | 1.12(4)        |
| 2022 | 1.51(11)  | 2.67(20)     | 3.31(2)        |
| 2023 | 1.32(9)   | 5.85(16)     | —              |
| 2024 | 0.78(9)   | 0.97(16)     | 0.86(4)        |
| 2025 | 1.54(9)   | 1.24(25)     | 2.87(9)        |
| 2026 | inf(4)    | 8.11(4)      | 1.09(2)        |

→ 2024 是三策略 Tue 都偏弱的特殊年；2025 EstHL/Reversal Tue 也較弱（1.54、1.24 都低於各自歷史均值），可能是使用者最近觀察到「Tue 不好」的來源（**recency bias**）。

**2026 Q1（截至 4/21）Tue 細節 — 完全反轉，N 偏小**：

| Strategy | 2026 Tue N | WR | avg P&L | 與全週對比 |
|----------|------------|----|---------|------------|
| EstHL    | 4 | 100.0% | **+156** | Mon +44 / Wed +6 / Thu +5 / Fri +44，**Tue 全週最強** |
| Reversal | 4 | 75.0%  | **+172** | Mon −25 / Wed +78 / Thu +226 / Fri +144，Tue 第二強 |
| Exhaustion | 2 | 50.0% | +8 | 樣本不足 |

→ 2026 三策略 Tue 都恢復成獲利日（EstHL 4/4 全勝、Reversal PF 8.11），但 N 都 ≤ 4 筆，統計上不可靠。整體圖像是「**2024 異常 → 2025 過渡 → 2026 回到歷史常態**」。

### T2：雙向甩動假說 — **被反駁**

| Day | N   | eff_mean | eff_med | time_high std | time_low std | range_mean |
|-----|-----|----------|---------|---------------|--------------|------------|
| Mon | 249 | 0.0638   | 0.0519  | 103.1         | 98.5         | 234.3      |
| Tue | 261 | **0.0749** | **0.0680** | 104.9     | 102.9        | **247.9**  |
| Wed | 262 | 0.0665   | 0.0594  | 103.9         | 101.5        | 225.7      |
| Thu | 256 | 0.0628   | 0.0510  | 100.5         | 98.7         | 219.8      |
| Fri | 250 | 0.0634   | 0.0581  | 104.6         | 103.5        | 217.3      |

- Tue eff_mean = 0.0749 vs 其他四天均值 0.0641 → **+16.8%（更趨勢、更不甩動）**
- H/L 出現時間分散度：Tue 與其他天接近（差距 < 4 分鐘 std），無顯著分散
- Tue range_mean 247.9 確認 H060 的觀察（振幅最大）

**結論**：Tue 不是「大振幅但雙向甩動」，反而是「大振幅+明確方向」——這實際上對趨勢策略是好事，與 Reversal/Exhaustion Tue 表現最佳吻合。

### T3：MAE/MFE 反轉率

| Strategy   | Tue MAE/MFE_med | Others MAE/MFE_med | 差距   |
|------------|-----------------|---------------------|--------|
| EstHL      | 0.80            | 0.67                | **+20.2%**（反轉壓力高） |
| Reversal   | 0.48            | 0.80                | **−40.1%**（反轉壓力低） |
| Exhaustion | 0.71            | 0.96                | **−25.8%**（反轉壓力低） |

→ EstHL 是唯一一個 Tue MAE/MFE 上升的策略，幅度 +20%（剛好接近 H071 預設的 15% 門檻）。但這個壓力沒有把 PF 打到 1 以下（仍 1.74），代表 EstHL 出場機制有效消化了反轉。

### T4：趨勢濾網交叉 — **無顯著新訊息**

- EstHL 是 long_only，247 筆裡只有 1 筆 against_trend（在 Mon），無法切片週二
- Exhaustion 結構上是逆勢進場，全部 against_trend，同樣無法做對比
- Reversal Tue：with_trend N=89 PF=1.82, against_trend N=8 PF=12.71（against N 太小，無統計意義）

→ TrendMA 切片在這三策略上不適用（兩個策略有方向偏好），無法驗證「Tue 趨勢逆向」假說。

### T5：夜盤波動濾網交叉

| Strategy   | Tue base PF | Tue NVF PF | Δ       | 其他天 NVF 平均效果 |
|------------|-------------|------------|---------|---------------------|
| EstHL      | 1.74        | 1.38       | **−0.36** | Mon +1.34、Wed +2.88（NVF 對其他天有幫助） |
| Reversal   | 2.16        | 2.53       | +0.37   | NVF 普遍中性偏正 |
| Exhaustion | 1.56        | 2.10       | +0.54   | NVF 對 Wed/Thu 反而有害 |

- **EstHL 的 Tue 是唯一 NVF 反向作用的組合**（其他天 NVF 都正向）
- Reversal/Exhaustion Tue 經 NVF 後更好，但本來就不弱
- 結論：Tue 的「弱」（對 EstHL 而言）**無法被夜盤濾網解釋**，反而會被夜盤濾網放大

## Vs. Expected

| 預期 | 實際 | 符合 |
|------|------|------|
| 至少 2/3 策略的 Tue PF 落於後 40% | 0/3（Reversal/Exhaustion 是 1/5，EstHL 是 3/5） | **❌ 不符合** |
| Tue 進場 MAE/MFE 顯著高於其他（>15%） | 只有 EstHL +20%，Reversal/Exhaustion 反而 −25~40% | **❌ 部分相反** |
| Tue H/L 出現時間分散度更高 | 與其他天接近 | **❌ 不符合** |

→ 三項預期都未獲支持。使用者觀察的「禮拜二績效不好」很可能是 **2024–2025 短期的 recency bias**，不是穩定現象。

## Gate Decision

**[X] Archive（Rejected）** — 主要假設未獲支持。

從證據看：
- **歷史上 Tue 並不弱**：對 Reversal/Exhaustion 反而是最佳交易日；對 EstHL 是中段
- **EstHL Tue 邊緣弱勢**（PF 1.74 vs Mon 2.54/Wed 3.35），但仍獲利
- **「雙向甩動」假說反駁**：Tue 是更趨勢的一天（efficiency +17%）
- **TrendMA 切片不適用**這三個策略

但本研究的副發現極具價值——**套用 NVF 後**，EstHL × Tue × 2024–2025 是真正的弱點組合（PF 0.00 / 0.29），且 H066 Phase 1 其實已經露出 Tue HIGH PF=1.75（其他天 HIGH 都 ≥ 2.28）的端倪，當時未被當成決策依據。這引出 H072。

## Derived Hypotheses

- **H072（採納）：NVF 效果 by weekday × strategy × year 重審**
  H066/H067 confirm 時用 6 年總體 PF 差異 +83%、跨年 6/6，未深入切 weekday × year sub-cell。本研究發現 EstHL × Tue × NVF 在 2024–2025 已破功（PF 0/0.29）。需系統性重審 NVF 在所有 (strategy × weekday × period) 切片下的穩定性，找出其他可能也悄悄失效的 cell。包含 Exhaustion 作為 control。詳見 H072 proposal。

- **H073 候選（暫不採納，併入 H072）：EstHL 為何在 Tue + NVF 反向作用**
  屬 H072 內的一個 cell，由 H072 系統性檢查涵蓋。

- **H074 候選（暫不採納）：Reversal Tue 為何特別好**
  Reversal Tue PF 2.16，全週最佳。Tue 振幅大、效率高，可能特別契合 BB 觸碰反轉邏輯。短期內不打算動實盤策略，先擱置。

## Links
- Proposal：../proposal.md
- Tasks：../tasks.md
- Explore script：../explore.py
- Visualisation：h071_overview.png
- Raw CSVs：t1_weekday_breakdown.csv, t2_intraday_summary.csv, t3_mae_mfe.csv, t4_trend_cross.csv, t5_nvf_cross.csv
- Trade-level data：trades_esthl.csv, trades_reversal.csv, trades_exhaustion.csv
