# Archive: 早盤強勢 → 大長紅

## Status
**Confirmed**（限定範圍：Phase 1 的「機率」宣稱。非可獲利策略。）

## Summary
觀察：開盤一路漲、到 10:30 仍守在早盤區間（08:45~10:30）高位的日子，當天容易收大長紅。
驗證結果：此「機率」宣稱為真且穩健 —— 守高位（pos≥0.75）當日大長紅率 21.8%，相對 base rate 9.4% 有 2.3x lift；越貼早盤高點 lift 越大（pos≥0.90 達 3.4x、收黑僅 5.6%）。
但作為可交易多單策略，扣成本後幾乎打平，故 confirmed 的是「現象」，不是「策略」。

## Key Evidence
- 樣本：TX 日盤，N=1289 天（2020-12 ~ 2026-05），adj_close。
- base rate 大長紅（ret≥0.8% & 收盤位於當日全幅上緣≥0.85）= 9.39%。
- 觸發 pos≥0.75（N=412）大長紅率 21.8%（lift 2.33x）；pos≥0.90（N=198）31.8%（lift 3.39x）。
- pos 分桶 vs 大長紅率呈**單調遞增**，非偶然。
- 尾端風險低：pos≥0.75 收黑僅 12.1%、大幅回吐（≤−0.5%）僅 2.9%。
- proposal 三個無效條件（lift≤base / N<100 / 尾端>30%）**全未觸發**。

## Why Confirmed
proposal 的假設陳述是「大長紅機率顯著高於 base rate」，並非「可獲利」。實測 lift 明顯、單調、樣本充足、尾端低，完全符合假設且未觸發任何 invalidation → 現象 confirmed。

**範圍界定（誠實標註）**：可交易性 = Inconclusive。
- 多單（pos≥0.75 + 13:45 出場）扣 3 點成本後全期 PF 0.99（gross +5.9% → net −0.5%），per-trade 期望移動太小被成本吃光。
- 穩健淨正只在 pos≥0.90 小樣本（IS 147 / OOS 51，且有門檻掃描選擇偏誤）。
- 2022 空頭年顯著虧損（PF 0.62），型態不全天候。
- 進場時機優化（等 %B<0 後站上 5MA 再進）→ 反而更差（同日對照 PF 0.98→0.82），因順勢日跌破下軌多為動能轉弱。
- 界線提前到 10:00 → lift 變弱、收黑率翻倍，10:30 為較佳界線。
- **結論：不晉升 strategies/live/**。

## Derived Hypotheses
- **出場優化**：13:45 固定出場吃不到續漲；改 trailing / 動態目標可能把 gross edge 放大到蓋過成本（最有機會救成可交易策略）。
- **regime 濾網**：加多頭/中性 regime 條件去掉 2022 空頭年拖累。
- **反向偏空日**：pos≤0.3（早盤弱勢守低位，N=362）大長紅率僅 1.7%、中位 ret −0.51%，對稱做空可能是更乾淨的 edge。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Backtest：results/backtest.md
- 腳本：explore.py / backtest.py / explore_cutoff.py / backtest_bbentry.py
