# Archive: H103 — 跳空跌破成本 → 折價回補做多（Gap-Down Cost Reversion Long）

## Status
Inconclusive（傾向正面 / promising，未達 Confirmed 門檻）

## Summary
源自 H102 distribution 階段收斂出的唯一穩健訊號。開盤跌破昨日與前日成本（VWAP）、且上方最近
成本隔著 ≥1 個日均振幅（`up_clear_norm ≥ 1.0`）→ 折價回補做多（只做多，H102 已證對稱 gap-up
做空無 edge）。Phase 2 真實成本回測：訊號真實但 OOS 偏薄，定為 Inconclusive、傾向正面。

## Key Evidence（N=106，2021–2026，成本 3 點/round-trip）
| Metric | IS (21–23, N=57) | OOS (24–26, N=49) | 全期 |
|---|---|---|---|
| 勝率 | 63% | 49% | 57% |
| PF | 2.31 | 1.24 | 1.67 |
| 均損益% | +0.223% | +0.070% | +0.152% |
| 年化 SR | 1.61 | 0.43 | 1.01 |
| MaxDD | 3.58% | 3.34% | 3.58% |

- **穩健性全過**：成本 0~7 點全正（不被成本殺死）；門檻 0.95–1.05 為平台、1.0 居中微優（非刀鋒）；
  目標/停損 6 組全正。
- **濾網真實**：控制組 `<L4` 同規則 PF 0.74、總 −23%、連敗 10 → `≥L4` 非裝飾。
- **出場貢獻巨大**：同 ≥L4 日「開盤多→收盤」PF 1.10/MDD 13.4%；加固定目標停損 → PF 1.65/MDD 3.6%。
- 逐年 5/6 正，2024 唯一虧年（勝率 35%），獲利集中 2021/2023/2026，每年 N 小（10–31）。

## Why Inconclusive
訊號真實（控制組強烈為負、全敏感度正、IS SR 1.59）——不是雜訊。但 OOS 太薄（SR 0.43、勝率跌破
50%、靠 winner>loser 撐正期望）、N 偏小、獲利集中少數年份、`≥L4` 為事後選點。達不到「IS/OOS 一致
穩健」的 Confirmed 標準，但明顯優於 Rejected。
**處置**：已落地 `src/analysis/h103_alert.py`（觀察用盤前提醒，進 morning_briefing，commit 08a1fb7），
持續累積前推樣本；建議小注 / paper-trade，或併入組合當低相關衛星訊號再定。

## 四象限總地圖（本研究最大產出）
開盤位置 × 成本距離 × 方向交叉，只有 **「跳空下方 × 成本遠 → 做多」** 一格穩健（IS_PF 2.31 / OOS_PF 1.24）。
其餘三格（跳空下方近做空、跳空上方遠做空、跳空上方近做多）excursion 有暗示但路徑回測 OOS 翻負/兩平、
連敗長。原因一致：唯一穩健格同時順均值回歸（折價回升）＋台指長期上飄；鏡像逆長多又逢 gap-up 低能量
死水。**市場不對稱，單邊（做多／開低／離成本遠）才站得住。**

## Derived Hypotheses
- **H103c-exit-only**：固定 reach 目標 + 0.5 停損出場框架（把 ≥L4 日 MDD 13.4%→3.6%、PF 1.10→1.65），
  可移植到其他日內多單訊號測試。
- **H103d-2024-regime**：2024 唯一虧年（勝率 35%），查結構變化（夜盤波動體制 / gap 行為），
  可能需 regime 濾網（連結 NVF / H092）。
- **H10X-gap-energy**（觀察，沿 H102）：gap 大小 ≈ 當日振幅能量前瞻估計。
- **對稱做空（rejected）**：gap-down 近<1.0 做空、gap-up 遠≥1.0 做空、gap-up 近<1.0 做多——
  路徑回測皆 OOS 翻負/兩平 + 連敗長。市場不對稱，不採。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md（GATE：進入 Phase 2）
- Backtest：results/backtest.md（Verdict：Inconclusive）
- 腳本：explore.py、backtest.py、make_chart_list.py；明細 results/h103_trades.csv、h103_backtest_trades.csv
