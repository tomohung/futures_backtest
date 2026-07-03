# Archive: 開盤相對均線位置 → 早盤時間窗方向

## Status
Rejected

## Summary
測試「當日 08:45 開盤價相對日線均線（5/10/20/60/120/240）位置」是否預測三個早盤時間窗（08:45-09:45 / 09:00-10:00 / 09:15-10:15）的窗內收紅/收黑機率與 EV。結論：無可用預測力。

## Key Evidence（N=1092 交易日，2021-12~2026-07）
- Baseline 三窗收紅 50–52%、僅微幅正漂移。
- 「開盤站上均線→收紅」基本不存在：所有 above cell Δ 在 ±2pp 內（N=655~816，非樣本不足）。
- 唯一訊號「開盤破 120/240 日均 → 窗 B/C 偏黑」約 −5pp，但**逐年翻號**：MA120 窗B below 收紅% 2022=46.9% / 2023=63.2% / 2024=69.2% / 2025=40.3%。
- 該訊號樣本高度集中崩盤段（2022 升息熊、2025 關稅崩盤 3–6月），是 regime 池化假象而非均線位置效果。

## Why Rejected
命中無正 EV、above 側落在抽樣誤差內、唯一 below 訊號逐年翻號且為 regime 混淆，符合 proposal 無效條件 #1/#2/#4。

## Derived Hypotheses
- **H137（Confirmed）**：把「開盤破長均」從方向訊號翻轉為**做多強度閘門**（風控 regime tile）→ 已確認並落地 key_prices。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md、explore.py、results/heatmap_dred.png
- 衍生分析：regime_detect.py（→ H137 Phase 1 基礎）
