# Archive: 低集中度 × weekday 安全日訊號 (H082)

## Status
**Rejected** — t-1 prior 版本（Branch B，實戰可用版）的 Q1×Wed P(crash) 從 same-day 0% 衰減到 11.76%，幾乎等於 baseline 13.85%。無實戰窗口。

## Summary

H082 從 H080 1I 衍生：Q1 × Wed/Fri 的「same-day」P(crash) 為 0%/2.56%（baseline 13.85%）。Phase 1 嚴格驗證採雙 Branch 設計：
- **Branch A (same-day)**：H082 proposal 原版，同期相關
- **Branch B (t-1 prior)**：盤前可用版，符合「實戰窗口」標準

結果：Branch B 衰減劇烈（Q1×Wed 11.76%、不穩定），所有 GATE 失敗。Branch A 雖然 Q1×Wed 數字漂亮（0%），但是 same-day 觀察，盤前無法 actionable。

跟 H081 相同 fail mode：**現象（A）真實但無法盤前判斷**。

## Key Evidence

### Branch A → Branch B 衰減（核心）

| cell | A same-day P(crash) | B t-1 prior P(crash) | 衰減倍率 |
|---|---|---|---|
| **Q1×Wed** | **0.00%** | **11.76%** | 訊號完全消失 |
| Q1×Fri | 2.56% | 6.38% | 2.5x |
| (Q1+Q2)×Fri | 4.44% | 8.00% | 1.8x |

Branch B Q1×Wed 11.76% vs baseline 13.85% = **規避效應只 -2 pp**。

### Wilson CI GATE（threshold < 10%）

| | A Q1×Wed | A Q1×Fri | A (Q1+Q2)×Fri | B Q1×Wed | B Q1×Fri | B (Q1+Q2)×Fri |
|---|---|---|---|---|---|---|
| Wilson 上限 | **8.20%** ✅ | 13.18% ❌ | 10.88% ❌ | **23.38%** ❌ | 17.16% ❌ | 15.00% ❌ |

Branch B 全部失敗（實戰版完全無效）。

### Permutation 通過但無用

| | percentile (cherry-picking corrected) |
|---|---|
| Branch A Test B | 97.5% ✅ |
| Branch B Test B | 98.1% ✅ |

兩 Branch 都通過 Permutation。但 Branch B 雖然「比隨機低」（98.1%），絕對機率 11.76% 仍**不夠低到實戰**。

→ **Permutation 顯著 + Wilson 不顯著** = 「相對顯著但絕對不夠低」 = 無實戰價值。

### 樣本穩定性

| | H1 前半 P(crash) | H2 後半 P(crash) | 兩段 < 10%? |
|---|---|---|---|
| A Q1×Wed | 0% (n=21) | 0% (n=22) | ✅ |
| A Q1×Fri | 0% (n=14) | 4.0% (n=25) | ✅ |
| **B Q1×Wed** | 11.1% (n=27) | 12.5% (n=24) | **❌** |
| **B Q1×Fri** | 11.1% (n=18) | 3.5% (n=29) | **❌** |

Branch B 的 Q1×Wed **兩段都 ~11%** — 不只是衰減，前後也不穩定。

## Why Rejected

1. **Branch A Q1×Wed 0% crash 是 same-day 同期觀察** — 收盤才能 confirm，盤前無法 actionable
2. **Branch B (t-1 prior) 全部 GATE 失敗** — 實戰版本完全無效
3. **衰減是結構性的，不會因樣本變大改變**：
   - Q1（極端 quintile bottom 20%）是 fat tail event
   - lag-1 auto-corr 0.62 強，但對極端桶預測力不足
   - 「t-1 在 Q1 → t 日仍在 Q1」機率只 ~55%，剩下 45% 跑到其他桶把 crash rate 拉回 baseline

按 user 提出的「**無實戰窗口 = reject**」原則：current 證據已充分顯示「t-1 prior 安全日訊號不存在」，未來樣本擴大也無法改變這個結構問題。

## 與 H081 的共同 fail mode

H081 與 H082 都在 H080 衍生線中失敗於相同的 fundamental issue：
- **同期觀察 ≠ 盤前 prior**
- 集中度 lag-1 auto-corr 看似強，但對精確的「極端桶位」預測力衰減大
- 集中度的研究價值止於 H080 的 same-day regime classification

## Lessons Learned

1. **Phase 1 GATE 應強制雙 Branch（same-day vs t-1 prior）對比**：避免「same-day 漂亮數字」誤導決策
2. **lag-k auto-corr 強 ≠ 對特定條件預測力強**：dev_pct lag-1 corr 0.62 對「整體分佈」強，但對「極端 20% quintile 的精確命中」弱
3. **Permutation 顯著與 Wilson 顯著要分開檢驗**：前者是「比隨機低」（相對），後者是「夠低到可用」（絕對）。實戰需要絕對閾值
4. **Fat tail event 的條件機率比一般 event 衰減更快**：Q1 (bottom 20%) 比 Q3 (median) 對 prior 的預測敏感度低，下次設計類似研究時應預期此衰減

## Derived Hypotheses

無。任何「集中度 → crash 規避」的延伸都撞同樣的「t-1 prior 對極端 quintile 預測力不足」結構問題。

## Links

- [Proposal](proposal.md)
- [Tasks](tasks.md)
- [Distribution Report](distribution.md)
- [explore.py](explore.py)
- 衍生來源：H080 1I (research/archive/confirmed/H080-top20-concentration-regime/)
