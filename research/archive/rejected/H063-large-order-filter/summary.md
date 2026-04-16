# Archive: Large Order Filter

## Status
Rejected

## Summary
用 tick 層級的「連續大單 burst」作為 1 分 K 突破策略（H018 / H062）的品質濾網。測試 V1（5 口門檻）、V2（11 種 config sweep）、V3（年度 P99 動態門檻 + 大單行為研究）後，確認**1 分 K 層級的大單聚集對後續方向完全沒有預測力**。

## Key Evidence

### V1（單筆 ≥5 口 / 10 秒 / 5 筆）
- H018：95.5% 的突破都觸發條件，等於不過濾
- H062：WITH burst 49.5% vs NO burst 47.0%，delta 僅 +2.5%（< 3% 門檻）

### V2（11 種 config sweep）
最佳 config：50_2_5（單筆 ≥50 口、2 筆、5 秒內）
- H062: WR_with = 53.2%, delta = +4.6%（N_with = 479）
- 邊際 edge，可能僅為統計波動，扣 2 點成本後期望值緊繃

### V3（年度 P99 + 行為研究）
用每年 P99 作動態門檻（2021 為 20 口、2026 為 14 口），分析 840,701 筆 P99 大單：

**⚠️ Data leakage 教訓**：用 pos_in_day（當日整天 high/low）看到 98% 反轉率是 tautology。

**用 pos_in_rolling（合法實時資訊）後：**
```
低點區 <10%：+60m 51.8% 上漲，平均 +0.3 點
高點區 >90%：+60m 52.9% 上漲，平均 +2.3 點
中段 20-80%：+60m 51.0% 上漲
整體：+60m 51.9% 上漲（= 台指長期 drift）
```

**P99 大單在任何位置都沒有方向預測力**。

## Why Rejected

1. **大單聚集本身不含方向資訊**：不論出現在什麼位置、什麼時間、什麼強度，後續走勢都接近 50/50
2. **V2 的微弱 edge 可能僅為統計波動**：50_2_5 config 的 +4.6% 在 N=479 下的 95% CI 約 ±4-5%
3. **結構性問題**：1 分 K 層級大單的聚集，對「這分鐘 K 的收盤」已經是因果關係——有大單所以收盤突破，但這個因果鏈沒延伸到後續走勢
4. **保證金調整的觀察是對的**：年度 P99 從 20 → 14 口，確實反映市場結構變化，但修正門檻後結論不變

## Key Lesson

**Data leakage 的警示**：pos_in_day 看起來完美的 98% 反轉率，其實是用了事後才知道的當日 high/low。未來研究涉及「某 tick/bar 在當天的相對位置」時，必須明確區分：
- `pos_in_rolling`：到當下為止的 cumulative max/min（合法）
- `pos_in_day`：整日 max/min（含未來資訊，不可用）

這個教訓比假設本身的 reject 更重要。

## Derived Hypotheses

（大部分衍生想法已被 V3 結論否定）

可能仍值得單獨探索：
- **單筆 ≥100 口巨單的反向訊號**：V2 看到 H018+100_1_10 WR=47.9%（反向 52.1%）、H062+100_2_10 WR=48.8%。但樣本小（每日 <10 筆），且接近隨機
- **掛單簿分析**：需外部資料源（非本 project）

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md（V1 / V2 / V3 完整結果）
- 探索腳本：explore.py、explore_v2.py、explore_v3.py
