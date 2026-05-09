# Archive: 週五的權值股集中度方向訊號 (H081)

## Status
**Rejected** — 即使現象在統計上接近顯著，本訊號**無法轉化為可用的實戰參考數據**，故 reject 而非 inconclusive。

## Summary

H081 從 H080 1G 衍生：Q5×Fri p_up=64.71% vs Q1×Fri 48.72% (+15.99pp)，pooled 樣本失敗 (+2.74pp) 但 Friday 條件下顯著。Phase 1 嚴格驗證後得出：
- 統計上邊緣不顯著（MW p=0.09-0.15、Permutation cherry-picking corrected 只 61.7%）
- **更重要的是：此訊號無實戰窗口** — 盤前無法決策（方向未發生）、早盤訊號太弱（P(上漲) 只 51%）、訊號主要在**後半盤才建立**

## Key Evidence

### 統計證據（GATE 1/3 通過）

| GATE | 結果 | 通過 |
|---|---|---|
| MW p < 0.05 (三條比較) | 0.09 / 0.15 / 0.09 | ❌ |
| Permutation cherry-picking corrected | percentile 61.7% (vs 95%) | ❌ |
| 樣本穩定 (前後半 < 10pp) | 1.76 pp | ✅ |

Permutation Test B 揭露：在 5 個 weekday 中**隨機 shuffle 後**，最大 |Q5-Q1| 的 null mean 就是 15.10 pp（std 5.24），實際 +15.99 pp 跟隨機差不多。**+15.99 pp 很可能是 multiple-comparison artifact**。

### 實戰窗口不存在（核心 reject 理由）

| 階段 | 集中度可用 | 方向訊號可用 |
|---|---|---|
| 盤前 8:30 | ✓ t-1 集中度 (lag-1 corr 0.62) | ❌ 訊號未發生 |
| 早盤 8:45-9:00 | ✓ | ❌ P(上漲) 只 51% (random) |
| 早盤 8:45-9:15 | ✓ | ❌ corr(早盤, 全日) = +0.28 / +0.47 (弱) |
| 後半盤 12:00+ | ✓ | ✓ 但出場前才知道，無入場價值 |

### 補充證據
- **N 不單調**：N=1 -4.98pp、N=5 +18.01pp、N=10 +0.55pp、N=20 +15.99pp。如果是真的微結構訊號，期望 monotonic 或同向 — N=10 反常暗示**獨立 noise**
- **前後半穩定但實戰無用**：H1 +14.29pp、H2 +12.52pp。現象一致但**永遠在後半盤建立**

## Why Rejected (而非 Inconclusive)

User 提出的判斷標準：「**如果不能化成實戰參考數據，那就 reject**」。

| | rejected | inconclusive |
|---|---|---|
| 統計顯著性 | 邊緣 | 邊緣 |
| 實戰可用性 | **不可能**（結構性問題） | 可能（樣本累積後） |
| 重啟成本/收益 | 0 | 樣本擴大可能 confirm |

H081 的**死穴是訊號在後半盤建立**，這個**不會因樣本變大改變**。即使再 +2 年資料 confirm 了統計顯著性，仍然無入場窗口 → **永遠無法實戰**。

inconclusive 暗示「未來可能可用」是誤導，所以 reject 才精確。

## Lessons Learned

1. **Phase 1 必須包含「實戰窗口檢查」**：不只看統計顯著，要驗證訊號在「能下單的時點」是否已建立
   - H081 1D 早盤訊號 corr 分析就是這個檢查
   - 未來假設的 GATE 應加入「early-session signal strength ≥ X」這條
2. **同期相關性研究的真正陷阱不是「需要 Phase 1.5 即時資料」，而是「即使有即時資料也救不了」**
   - 如果訊號在後半盤建立，即時資料管線也只是觀察，不是預測
3. **Permutation cherry-picking correction 是必要的**：在 weekday × quintile 多格子分析時，「找最強格」的多重比較風險很大。Test B (controlled max) 比 Test A (specific cell) 更嚴謹
4. **Sample stability ≠ Practical usefulness**：H081 GATE-3 通過（前後半 +12-14pp 一致），但這只證明「現象真實」，不證明「可用」

## Derived Hypotheses
無。

「集中度 → 方向訊號」的延伸都會撞同樣的「訊號在後半盤建立」結構問題。任何 weekday × quintile 變體（結算週分組、N 替換、月初月底）都不會改變這點。

唯一可能的差異化方向是 H082（crash 規避訊號），是獨立研究線，與本 reject 無關。

## Links
- [Proposal](proposal.md)
- [Tasks](tasks.md)
- [Distribution Report](distribution.md)
- [explore.py](explore.py)
- 衍生來源：H080 1G/1I (research/archive/confirmed/H080-top20-concentration-regime/)
