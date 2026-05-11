# Archive: Mode 1 / Mode 2 切換規則調校 (H086)

## Status
**Rejected** — 70 個規則 grid + 4 baseline 共 74 個變體，**0 個達到 recall_A ≥ 80% AND FPR_bull ≤ 10%** 的 GATE 目標。Invalidation #1 觸發。

## Date Closed
2026-05-11

## Summary

H086 從 H084 Step 0.8 衍生：H084 的 mode2 雙條件 `TAIEX<250MA AND blue_streak≥3` 太嚴（recall 16.5%）、`OR` 太鬆（FPR 21.4%）。H086 系統性測試 5 (A-persistence) × 7 (B-econ) × 2 (logic) = 70 個變體加 4 baseline。

結果：沒有任何規則能同時達到 recall_A ≥ 80% AND FPR_bull ≤ 10%。**根本問題在 ground truth 定義**：H084 zigzag 把 2008-2014 整段（~7 年）標 Tier A，包含長期復甦期，其中多數日子 TAIEX 在 250MA 之上、景氣燈號甚至紅燈 — 「H084 標 Tier A」≠「正在 panic」。

## Key Evidence

### Pareto frontier 最佳點（依 Youden J）

| Rank | Rule | recall_A | FPR_bull | Youden J |
|--:|---|---:|---:|---:|
| 1 | A≥0d OR streak≥6 | 60.2% | 7.6% | 0.53 |
| 2 | A≥5d OR streak≥6 | 58.3% | 7.6% | 0.51 |
| 4 | A≥0d OR streak≥4 | 65.0% | 16.3% | 0.49 |
| 5 | A≥0d OR score≤16 | 48.3% | 0.0% | 0.48 |
| baseline | H084 mode2_OR | 67.2% | 21.4% | 0.46 |

最佳變體 J=0.53 比 H084 baseline (0.46) 略優，但**所有變體 recall 上限 ~67%**，距 80% 目標還差 13+ pp。

### IS vs OOS（反直覺）

最佳規則 `A≥0d OR streak≥6` 的 OOS recall **反而比 IS 高 +30 pp**（52% → 84%），FPR 也升 +12 pp。Invalidation #2（OOS 退化）未觸發。

說明這不是 overfit 問題，是 Tier A 標籤本身在 IS（2008-2018，含 7 年 long recovery）vs OOS（2019-2026，含 2022 急熊）的「panic 密度」不同。

## Why Rejected

### 結構性原因：Tier A 標籤過寬

H084 用 HWM zigzag macro 標 Tier A 涵蓋整個「從 ATH-recovery 到新 ATH」的長週期：
- 2008-11 trough → 2014 才回到 ATH（~6 年）整段都是 Tier A
- 期間 2010/2011/2013/2014 多數時候市場是上漲的、景氣有時紅燈
- 任何 panic-based 規則最多只能抓 Tier A 中的 acute panic 子集（約 50-65%）

對「Mode 切換是否啟動 H085」的決策來說，這個 ground truth 不合適。

### 衍生方向（建議後續研究）

- **Tier A acute redefine**：把 ground truth 從「H084 macro_tier=A」改成「trough ±60 天的 acute period」，重做 grid search。可能根本問題不在規則而在標籤。
- **加入快訊號**：將 grid B 擴展到 `VIX_pct ≥ 80%` 與 `margin_drop_60d ≤ -10%`，看是否能突破 80% recall。
- **margin tier classifier**：用融資餘額作為 regime 分類器補強。

## Impact on Other Strategies

**不影響 S004-fg-composite（H085）confirmed 狀態**：S004 不依賴 Mode 1/2 切換，是「全期間統一閾值」的單一規則。H086 原本要為 H085 提供 mode-conditional 規則，現在這個延伸被擱置。

## Files

- `proposal.md` — 原始假設文件
- `tasks.md` — Phase 1 任務追蹤（Step 1.1-1.4 全部 checked）
- `explore.py` — grid search 完整腳本，可獨立重跑
- `results/distribution.md` — 完整結果與 GATE 決策
- `results/rules_grid.csv` — 222 列 metrics
- `results/is_oos_consistency.csv` — Top-5 規則 IS/OOS 對比
- `results/pareto_frontier.png` — Pareto 散點圖
