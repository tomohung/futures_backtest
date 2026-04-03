# Archive: Night Session 30m MACD + SMA Regime Classification

## Status
Rejected

## Summary
嘗試用夜盤 30 分 K 的 MACD(12,26,9) + SMA(5/21/65) 排列，在日盤開盤前分類 regime（趨勢多/空/反轉/中性），預測日盤前四根 30m K（08:45~10:45）的方向與振幅。發現方向信號是反轉而非順勢，且 edge 不足以支撐交易。

## Key Evidence
- N=957 日（2021-01 ~ 2026-04）
- 夜盤 MACD < 0 → 晨盤上漲率 57%, mean +17 pts, t-test p=0.010（反轉效應）
- 夜盤 MACD ≥ 0 → 晨盤下跌率 53%, mean -5.6 pts, p=0.293（不顯著）
- 前兩根確認方向後，剩餘空間 R/R < 1（已走幅度中等以上時 R/R = 0.59~0.74）
- 前兩根 K 棒型態本身的預測力遠大於 MACD 方向

## Why Rejected
30 分 K 級別的 MACD/SMA 太慢，產生的方向信號粒度不夠細：
1. **開盤前就進場**：勝率只有 57%、mean +17 pts，edge 太薄無法實戰
2. **等前兩根確認再進場**：振幅已消耗 1/3，R/R 急劇惡化至 < 1
3. **兩難無解**：方向判讀與進場時機存在根本矛盾
4. 原假設的「順勢」方向完全不成立，實際是 mean-reversion，進一步削弱可用性

## Derived Hypotheses
（無。30 分 K 級別技術指標不適合作日盤當沖方向濾網。）

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- 探索腳本：explore.py、explore_patterns.py
