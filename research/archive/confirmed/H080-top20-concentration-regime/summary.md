# Archive: 前 20 權值股成交集中度的行情分類

## Status
**Confirmed** — GATE 4/4 通過（修正版對稱閾值）

## Summary

本研究探討「前 20 權值股當日成交金額占大盤總額相對 20 日均的偏離百分比」（`top20_dev_pct`）能否區分當日 TX 日盤的行情形態。

**主要結論**：集中度是清楚、穩定的 **volatility predictor**（4 個 N 全通過），但**不是 direction predictor**（pooled p_up 首尾差距僅 +2.74 pp）。weekday 條件下衍生兩個獨立訊號：Friday 的方向 effect (+15.99 pp) 與 Q1 × Wed/Fri 的「安全日」effect（43 天無一次大跌）。

⚠️ **方法論限定**：本研究是**同期相關性**（同一天的集中度 vs 同一天的行情），不是預測。實戰可用性建立在「核心假設 A：早盤集中度 ≈ 全日集中度」之上，需 Phase 1.5（即時集中度日記）驗證才能轉為實戰策略。

## Key Evidence

### GATE-2（振幅）— 主結論
- 5 桶 quintile：Q1 振幅 0.93% → Q5 振幅 1.50% = **+61%**，單調上升
- 4 個 N (1/5/10/20) 全通過，Q5/Q1-1 比例 +52% ~ +61%
- 跨 weekday 都成立：Wed 1.89x（最強）、Mon 1.74、Tue 1.66、Fri 1.43、Thu 1.33
- chi-square (27 格): p < 1e-6

### GATE-1'（Friday 方向，weekday-conditional）
- Q5×Fri p_up = **64.71%** (n=51) vs Q1×Fri = **48.72%** (n=39) → **+15.99 pp**
- 唯一通過 8pp 門檻的 weekday；其他 weekday 接近零或反向（Mon -1.99, Tue -2.83, Wed -3.81, Thu +6.06）

### GATE-3/4（規避 + 極端格，對稱閾值版）
- Q1 × Wed（n=43）：**P(crash) = 0%**，最深跌 -0.79%（vs baseline P(crash) 13.85%）
- Q1 × Fri（n=39）：P(crash) 2.56%，crash lift 0.185
- Q5 × Mon（n=45）：P(crash) 24.4%，crash lift 1.76（最深跌 -6.46% on 2024-08-05）

### 1F：與 H079 完全獨立
- 4 個 N × 2 個 H079 訊號全部 |corr| < 0.15
- → 高增量價值，可疊加既有 H079 廣度溫度計

### 1K：全格 Pattern Map（25 格）
- **真平靜日**（雙邊都被壓制）集中在 Q1（低集中度）
- **明確下跌格**集中在 Q3×Tue 與 Q2×Thu（mean -0.19% / -0.21%）
- **漲跌雙向放大**集中在 Q5 × Mon/Tue/Wed
- **沒有單一格是「漲容易+不容易跌」的極端**

## Why Confirmed

- **GATE-2 強通過**且跨 N、跨 weekday 一致 — 振幅訊號最穩健
- **與既有研究獨立**（與 H079 |corr|<0.15）— 非冗餘
- **三個衍生方向明確**（H081/H082 已單獨建檔）
- 雖然 GATE-1 pooled 失敗，但 weekday-conditional 與「規避」維度提供額外價值
- 即使方法論上是「同期相關」，結論作為**研究素材**（餵給衍生假設）與**統計基準**已有完整價值

## Sample & Methodology

- **期間**：2020-12-31 ~ 2026-05-07（1191 個交易日，受 TX 期貨資料起始日限制）
- **樣本期受限說明**：原計畫 2018-01 起，但 ohlcv_1m 中 TX 期貨資料只回溯到 2020-12-30
- **訊號定義**：`top20_dev_pct = (top20_share - ma20) / ma20 * 100`，N=20 為主，1/5/10 為輔
- **清單來源**：用 stock_day 計算的「上月成交金額前 20」近似 TAIEX 市值權重前 20
  - 妥協理由：零外部 ETL，但會在妖股月（2018 國巨、2021 長榮、2024 廣達）偏離真值
  - 1E 顯示 96/97 個月份都有清單變動 → 實際分析對象是「當期最熱門 20 強」的集中度

## Derived Hypotheses

### 已建立 proposal
- **H081** — Friday 條件下的權值股集中度方向訊號（+15.99 pp）
- **H082** — Q1 × Wed/Fri 安全日（P(crash) ~0–3%）

### 待建立（候選）
- **H08X 「明確下跌格」**：Q3×Tue / Q2×Thu mean -0.19% / -0.21%，與 H071 tuesday-vol-paradox 可能相關
- **H08Y 「H080 + H079 訊號合併」**：兩訊號 |corr|<0.15，疊加可能有效益
- **H08Z 「最佳 N 探索」**：4 個 N 都通過 GATE-2，但 N=20 最強。中間值（N=15）或真權重月報是否更純？

### Phase 1.5（後續延伸，不在本研究範圍）
- 建立即時集中度日記管線（盤中 8 個時點）
- 累積 60–100 日後驗證早盤集中度 ≈ 全日集中度
- 通過後，本研究結論才能轉為實戰策略

## Links

- [Proposal](proposal.md)
- [Tasks](tasks.md)
- [Plan](plan.md)
- [Distribution Report](distribution.md) — 完整 1A–1K 結果與 GATE 評估
- [explore.py](explore.py) — Phase 1 主分析腳本
- ETL 腳本：`src/etl/build_top_lists.py`、`src/etl/build_concentration_index.py`
- 結果：`results/`（10 個 csv + 2 個 png）

## 不進入 strategies/live 的原因

H080 是**indicator** 不是 **strategy**：
- 主要作為其他策略的 risk filter / vol-targeting 訊號
- 沒有獨立的進出場邏輯
- 衍生 H081/H082 才是「策略候選」，等它們 confirmed 後再考慮 live
