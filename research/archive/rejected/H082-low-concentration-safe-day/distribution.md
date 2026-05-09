# H082 Phase 1 Distribution Report

**研究**：低集中度 × weekday 安全日訊號
**執行日期**：2026-05-09
**樣本期間**：2020-12-31 ~ 2026-05-07（1191 個交易日）

---

## 🚨 方法論限定

1. 同期相關性 ≠ 預測力。
2. **本研究額外加入「實戰窗口檢查」**：除了 H082 proposal 原本的同期 (same-day) 版本（Branch A），同時測試 t-1 prior 版本（Branch B）— 即用「昨日集中度」作為「今日落桶」的盤前 prior。
3. Branch A 通過 = 有同期相關（事後可標記）；Branch B 通過 = 真有實戰可用價值。

---

## 1A 兩 Branch 機率對比

| | cell | n | k_crash | P(crash) | lift | Wilson 95% CI | mean_dir | max_drop |
|---|---|---|---|---|---|---|---|---|
| **A same-day** | Q1×Wed | 43 | 0 | **0.00%** | 0.00 | [0%, **8.20%**] | +0.145% | -0.785% |
|  | Q1×Fri | 39 | 1 | 2.56% | 0.18 | [0.45%, 13.18%] | +0.020% | -0.858% |
|  | (Q1+Q2)×Fri | 90 | 4 | 4.44% | 0.32 | [1.74%, 10.88%] | +0.074% | -1.337% |
| **B t-1 prior** | Q1×Wed | 51 | 6 | **11.76%** | 0.85 | [5.51%, 23.38%] | +0.085% | -1.797% |
|  | Q1×Fri | 47 | 3 | 6.38% | 0.46 | [2.19%, 17.16%] | +0.203% | -0.901% |
|  | (Q1+Q2)×Fri | 100 | 8 | 8.00% | 0.58 | [4.11%, 15.00%] | +0.115% | -3.282% |

baseline P(crash) = 13.85%。

### Branch A → B 衰減分析（核心）

| cell | A same-day | B t-1 prior | 衰減 |
|---|---|---|---|
| **Q1×Wed** | **0.00%** | **11.76%** | 訊號**完全消失** |
| Q1×Fri | 2.56% | 6.38% | 部分衰減 |

**Q1×Wed 從 0% 飆到 11.76%，跟 baseline 13.85% 差距極小**。即使 dev_pct lag-1 auto-corr = 0.62 強，但對「極端尾端 (Q1, bottom 20%)」的預測力不足：t-1 在 Q1 → t 日實際在 Q1 的條件機率只 ~55%，剩下 45% 跑到其他桶，crash 機率回到 baseline。

---

## 1B Wilson CI GATE（threshold < 10%）

| Branch / Cell | Wilson 上限 | 通過 |
|---|---|---|
| A Q1×Wed | 8.20% | ✅ |
| A Q1×Fri | 13.18% | ❌ |
| A (Q1+Q2)×Fri | 10.88% | ❌ |
| **B Q1×Wed** | **23.38%** | **❌** |
| **B Q1×Fri** | **17.16%** | **❌** |
| **B (Q1+Q2)×Fri** | **15.00%** | **❌** |

**Branch B 全部失敗**（實戰版）。Branch A 只有 Q1×Wed 通過（n=43, k=0 的觀察非常 fragile — 一個大跌就會破）。

---

## 1C Permutation Test (cherry-picking corrected)

跑 2000 次 shuffle crash labels，計算「在 25 格 (5 quintile × 5 weekday) 中找最低 P(crash)」的 null distribution：

| Branch | null min mean | null min std | actual min | percentile |
|---|---|---|---|---|
| A same-day | 4.78% | 1.83% | 0.00% | **97.5% ✅** |
| B t-1 prior | 4.86% | 1.78% | 0.00% | **98.1% ✅** |

**兩 Branch 都通過 Permutation Test B**，但這只證明「比隨機低」，不證明「夠低到實戰可用」。Branch B 雖然通過 permutation，但 Q1×Wed 的絕對 P(crash) 11.76% 等於沒效應。

→ Permutation 顯著 + Wilson 不顯著 = **「相對顯著但絕對不夠低」**

---

## 1D 樣本穩定性

| Branch / Cell | H1 前半 | H2 後半 | 兩段 < 10%? |
|---|---|---|---|
| A Q1×Wed | 0% (n=21) | 0% (n=22) | ✅ |
| A Q1×Fri | 0% (n=14) | 4.0% (n=25) | ✅ |
| **B Q1×Wed** | **11.1%** (n=27) | **12.5%** (n=24) | **❌** |
| **B Q1×Fri** | **11.1%** (n=18) | 3.5% (n=29) | **❌** |

Branch B 的 Q1×Wed **兩段都 ~11%** — 不穩定且高。Q1×Fri 後半 3.5% 看似低，但前半 11.1%，**前後差異大**。

---

## 1E Branch A vs B 衰減

| cell | A | B | 衰減倍率 |
|---|---|---|---|
| Q1×Wed | 0.00% | 11.76% | 從 0% → ~baseline |
| Q1×Fri | 2.56% | 6.38% | 2.5x |
| (Q1+Q2)×Fri | 4.44% | 8.00% | 1.8x |

→ **t-1 prior 的安全日訊號顯著弱於 same-day 觀察**，與 Q5×Fri 的 lag-1 振幅預測（衰減 38%）相比，crash 規避訊號的衰減更大（無限大 in Q1×Wed case）。

---

## GATE 總結

| GATE | Branch A | Branch B |
|---|---|---|
| 1 Wilson CI < 10% | 1/3 通過 (only Q1×Wed) | **0/3 通過** |
| 2 Permutation pct ≥ 95% | ✅ 97.5% | ✅ 98.1% |
| 3 樣本穩定 (兩段都 < 10%) | ✅ 兩格都過 | **❌ 兩格都不穩** |

**Branch B（實戰版）3 條中 2 條失敗**。

---

## 整體決定：REJECT（無實戰窗口）

### Reject 推理

按 user 提出的「**無實戰窗口 = reject**」原則：

1. **Branch A Q1×Wed 0% crash 是 same-day 同期觀察**
   - 收盤後才能確定當日真的在 Q1
   - 盤前/盤中無法用此 condition 進場
   - 純學術觀察，無法 actionable

2. **Branch B (t-1 prior) 是「實戰可用版」 → 全部 GATE 失敗**
   - Q1×Wed P(crash) 11.76% ≈ baseline 13.85%
   - 完全沒有規避效應
   - Wilson CI 上限 23.38%（高於 baseline）
   - 兩段穩定性都失敗

3. **這個現象的本質**：
   - Q1（極低集中度）是 fat tail event — 1 in 5 機率
   - lag-1 prior 對 fat tail 的預測力不足（即使 auto-corr 強）
   - 「t-1 在 Q1 → t 日仍在 Q1」只 55% 機率，剩下 45% 跑到較高的集中度桶
   - 那 45% 把 crash 機率拉回 baseline

### 為何不是 inconclusive
- Branch B 衰減為 11.76% **接近 baseline**，不是「邊緣不顯著」是「**幾乎沒效應**」
- 這個衰減是結構性的（lag-1 對極端桶預測力不足），**不會因樣本變大改變**
- 即使再 +2 年資料 confirm 了 Branch A 的 0% — 仍然無實戰窗口

### 與 H081 的相似性
H081 與 H082 都失敗於同樣的 fundamental issue：
- **同期觀察 ≠ 盤前 prior**
- 集中度 lag-1 auto-corr 0.62 看似強，但對「精確的桶位」（Q1 / Q5 極端 quintile）預測力衰減大
- **集中度的研究價值在於 H080 的 same-day regime classification**，不在於可實戰的時序預測

---

## 衍生假設

無。

任何「集中度 → crash 規避」的延伸都會撞同樣的「t-1 prior 對極端 quintile 預測力不足」結構問題。可能的 differentiated direction（不是 H082 變體）：
- **更穩定的 prior 訊號**（如月度集中度、季度集中度）— 但更穩定也更鈍
- **集中度 + 其他訊號的 joint filter**（如集中度 + 夜盤 + weekday）— 但要避免重蹈 H070/H083 negative finding
- 都不是 H082 重啟，是新假設

---

## 主要產出

```
research/active/H082-low-concentration-safe-day/
├── proposal.md
├── tasks.md
├── distribution.md  (本檔)
├── explore.py
└── results/
```
