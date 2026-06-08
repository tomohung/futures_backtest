# Archive: H109 — EstHL 殘留靜日濾網（Residual Quiet-Day Filter over NVF）

## Status
Rejected（殘留靜日 ex-ante 不可約；正面確認既有 NVF 已良好調校）

## Summary
源自 H108（EstHL 靜日淨虧）。問是否有盤前可知波動預測子能在既有 NVF 之上增量濾掉 EstHL 虧損的殘留
靜日。結論：盤前預測子能測「當日振幅」但測不準「EstHL 獲利」、無增量於 NVF、撈不回任何淨負桶 →
殘留靜日 ex-ante 不可約，既有濾網棧已抽乾可預測波動成分。GATE 直接 Archive（rejected）。

## Key Evidence（EstHL N=170 殘留母體 / 全交易日 N=1282，2021–2026）
- **Q1 盤前可預測振幅且夜盤外有增量**：corr(pred, |day move|) VIX 0.253(增量0.236)、OR 0.198、前1日range 0.183、night_norm 僅 0.121。夜盤是弱預測子。
- **Q2/Q3 但對 EstHL 獲利分離弱**：最佳 gap spear 0.187（去 night 增量 0.135），VIX 僅 0.063；連最弱桶仍 +0.04%、夜盤&gap 雙低交集(N=41) 仍 +0.038% → 無淨負桶。
- **濾網淨效果**：砍 gap 底10% 只 +0.6%/5年（N=17 雜訊）；砍底25%+ 即砍掉淨正交易 + 6~9 個 Q3 贏家、總淨利下滑。

## Why Rejected
H108 的「靜日=虧」乾淨單調是 ex-post（用實現 |move| 分桶）；ex-ante 盤前預測子太弱撈不回。EstHL 既有
NVF+OR%+VWAP 已抽乾可預測波動成分，殘留靜日是不可約雜訊。正中無效條件「無增量於 NVF / 濾除含等量
Q3 贏家」。**此為正面確認：既有 NVF 設計穩當，無可改善項。**

## Derived Hypotheses
- **VIX 對日振幅預測強(0.253) 但不預測 EstHL 獲利**：EstHL 獲利取決於趨勢性非振幅（高 VIX 常 choppy）。
  VIX 取代/補強 NVF 不會改善 EstHL（已測否決方向）；但 VIX 對「需要振幅」的策略 / EstRange 估計或有用，另立假設。
- **EstHL 真正需要的是盤前『趨勢性』預測子（非波動）**：先驗低（本 session pattern），但方向不同於波動濾網。
- **方法論**：ex-post 乾淨分桶 ≠ ex-ante 可濾；filter 必用盤前預測子重做看淨效果 + 誤殺（[[feedback_excursion_needs_forward_tautology_guard]]）。

## Links
- Proposal：proposal.md ｜ Distribution：results/distribution.md（GATE：Archive Rejected）
- 腳本：explore.py；圖 results/h109_distribution.png
