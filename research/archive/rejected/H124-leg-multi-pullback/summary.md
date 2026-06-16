# Archive: 同 leg 多次拉回進場（淺拉回不燒名額）

## Status
Rejected（2026-06-16，Phase 1 GATE）

## Summary
H120 衍生：觀察到 2026-06-11 chart-ui H120 圖層在 9:11 沒畫出一個又深又強的拉回續攻，懷疑「每相位只取第一個站回 5MA → 第一個淺站回被深度濾網丟棄卻仍燒掉整個相位名額」是缺陷。假設「淺站回不該燒名額，應續找同相位下一個合格站回（B）」能補捉漏單且淨優於 baseline（A）。**完全 causal 框架下實測：B 救回來的單平均虧錢，全面劣於 A，Rejected。**

## Key Evidence
（TX 日盤全窗，causal streaming detect，alpha=0.75、cost=3pt、<12:00、depth≥0.25）
- **A baseline**：N=1262，tot 16.9%，Sharpe 0.041，avgR 0.02
- **B 淺不燒名額**：N=1566，tot 12.5%，Sharpe 0.025（A 的嚴格超集 = A + 304 rescued）
- **B extra（304 筆 rescued，分布 293 天）**：win 60.2%、EV −3.6pt、tot −4.4%、**avgR −0.03、Sharpe −0.05** → 淨虧，把總報酬與 Sharpe 拖下去
- **C 同相位全取**：N=4997，tot 11.4%，maxLoss 20、mdd −62.5%，更爛
- OOS 同向：A ＞ B ＞ C

## Why Rejected
1. 命中 proposal 兩條無效條件：B extra avgR ≤ 0（−0.03）、整體 PF/期望 R 未優於 A（全面更差）。同相位後續拉回的續攻品質本就較差，救回來只是加爛單；baseline「第一個站回燒掉相位」在 causal 下是對的。
2. **動機案例是雙重假象**：(a) causal A 在 2026-06-11 該日 08:58 就進場且當天 3 筆全贏——「9:11 漏單」根本只存在於 leg-bounded（前視偏誤）圖層的特定 anchoring，causal 下不存在；(b) C 在該日多抓的單也全贏，是典型 data-snooping 倖存者偏誤，全窗一攤就是淨虧。
3. extra 跨 293 天分散，非樣本不足或單日 snooping——是真的沒 edge。

## Lessons
- **絕不用 chart-ui `h120.py` 的 leg-bounded `detect_day` 當 edge 證據**：它含 H120 同款前視偏誤（用未來 leg 終點 em 當搜尋上界），僅作行情參考。任何 P&L 結論必須在 causal streaming 上做（基準 `validate_causal.py::detect_causal`）。
- 視覺上「明顯漏掉的好單」常是非 causal 指標的 anchoring 假象 + 單一好日子，務必先在 causal 全窗對照零策略/baseline 才下結論。

## Derived Hypotheses
- （無）C 全取 OOS tot 為正但 maxLoss/mdd 爆炸，屬高波 regime confound，不值得單獨開假設。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Explore script：explore.py（causal A/B/C）
