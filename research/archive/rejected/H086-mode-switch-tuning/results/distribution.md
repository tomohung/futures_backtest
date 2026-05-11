# Distribution Research Results: Mode 1 / Mode 2 切換規則調校

## Date
2026-05-11

## Conditions Tested

### 規則 grid（70 個 + 4 個 baseline）
- **A 條件**：cond_A_below_250ma 連續 ≥ N 天，N ∈ {0, 5, 10, 20, 60}（5 變體）
- **B 條件**（econ-related）：
  - `blue_streak ≥ {1, 2, 3, 4, 6}`
  - `econ_score ≤ {16 (藍燈), 22 (黃藍以下)}`
  - 共 7 變體
- **邏輯**：AND, OR
- 總計：5 × 7 × 2 = 70 rules

### Baseline（H084 既有）
- cond_A only (TAIEX < 250MA, 單日)
- cond_B only (blue_streak ≥ 3)
- mode2_AND
- mode2_OR

### Ground truth
- Tier A days（macro_tier == 'A'）：2015 天
- bull days（macro_tier == 'bull'）：667 天
- 兼觀察 Tier B/C/D 觸發率

### IS / OOS 切分
- IS：2008-01 ~ 2018-12（2705 天，A=1505, bull=261）
- OOS：2019-01 ~ 2026-05（1779 天，A=510, bull=406）

---

## Sample

- 總交易日：4484（2008-01-02 ~ 2026-05-08）
- 評估的 rules：70 grid + 4 baseline = 74，每個跑 IS / OOS / FULL → 共 222 列指標

---

## Key Findings

### 1️⃣ Target zone（recall_A ≥ 80% AND FPR_bull ≤ 10%）— **0 rules 通過**

```
FULL 期間 target zone 規則數：0
```

→ **Invalidation Condition #1 觸發**：「無一組規則能同時滿足 Tier A recall ≥ 80% AND bull FPR ≤ 10%」

### 2️⃣ Top-10 by Youden J (recall_A − FPR_bull, FULL period)

| Rank | Rule | recall_A | FPR_bull | hit_B | hit_C | hit_D | Youden J | median lag (days) |
|--:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | A≥0d OR streak≥6 | 60.2% | **7.6%** | 46.3% | 42.0% | 0.0% | **0.525** | 73 |
| 2 | A≥5d OR streak≥6 | 58.3% | 7.6% | 41.1% | 37.4% | 0.0% | 0.506 | 88 |
| 3 | A≥10d OR streak≥6 | 57.1% | 7.6% | 38.5% | 35.9% | 0.0% | 0.495 | 93 |
| 4 | A≥0d OR streak≥4 | 65.0% | 16.3% | 46.3% | 42.8% | 2.8% | 0.487 | 64 |
| 5 | A≥0d OR score≤16 | 48.3% | **0.0%** | 40.9% | 23.2% | 0.0% | 0.483 | 53 |
| 6 | A≥20d OR streak≥6 | 55.1% | 7.6% | 35.1% | 34.0% | 0.0% | 0.475 | 103 |
| 7 | A≥5d OR streak≥4 | 63.6% | 16.3% | 41.1% | 38.2% | 2.8% | 0.472 | 77 |
| 8 | A≥5d OR score≤16 | 46.7% | 0.0% | 36.3% | 16.7% | 0.0% | 0.467 | 65 |
| 9 | A≥10d OR streak≥4 | 62.7% | 16.3% | 38.5% | 36.7% | 2.8% | 0.463 | 79 |
| 10 | A≥0d OR streak≥3（=H084 mode2_OR） | 67.2% | 21.4% | 47.8% | 42.8% | 2.8% | 0.458 | 53 |

→ 最佳實用規則 `A≥0d OR streak≥6`：recall 60% / FPR 8% / Youden J = 0.53。
→ 比 H084 既有 mode2_OR (0.46) 進步約 **+0.07 J**，但仍不到 80% recall 目標。

### 3️⃣ IS vs OOS 一致性（FULL Top-5）

| Rule | IS recall | OOS recall | Δ recall | IS FPR | OOS FPR | Δ FPR |
|---|---:|---:|---:|---:|---:|---:|
| A≥0d OR streak≥6 | 52.3% | **83.5%** | **+31.2%** | 0% | 12.6% | +12.6% |
| A≥5d OR streak≥6 | 50.7% | 80.6% | +29.9% | 0% | 12.6% | +12.6% |
| A≥10d OR streak≥6 | 49.5% | 79.6% | +30.1% | 0% | 12.6% | +12.6% |
| A≥0d OR streak≥4 | 56.5% | 90.2% | +33.7% | 8.0% | 21.7% | +13.7% |
| A≥0d OR score≤16 | 37.7% | 79.6% | +41.9% | 0% | 0% | 0% |

**OOS recall 全面顯著高於 IS（差距 +30~+42%）**，但 FPR 也同步上升（+12~+14%）。
→ 不是「OOS 退化」而是「OOS 環境讓相同規則更容易觸發」。

→ **Invalidation #2** (OOS recall 下降 > 15%) **未觸發**（反向）

### 4️⃣ tier 結構性（理想：A > B > C > D > bull）

最佳規則 `A≥0d OR streak≥6`：60.2% / 46.3% / 42.0% / 0.0% / 7.6%
- A > B > C > D ✓ 結構正確
- bull < D ✓
- A vs bull 差距 0.53 ✓
- 但 B 與 C 差距太小（46% vs 42%），未能有效區分大型 vs 標準回檔

---

## Vs. Expected

| Proposal 預期 | 觀察 | 評估 |
|---|---|---|
| `streak ≥ 1` 大幅提升 Tier A recall | streak≥1 → recall 72.3% / FPR 27.6% | ✅ 提升但 FPR 過高 |
| `250MA below ≥ 10D` 去除單日 whipsaw | A≥10d AND streak≥1: recall 8.4%, FPR 1.7% | ⚠️ 太嚴 |
| AND（streak≥1 + 250MA below ≥10D）是 sweet spot | 同上：recall 8.4% 太低 | ❌ AND 整體都太嚴 |
| 找到 recall ≥ 80% AND FPR ≤ 10% 的規則 | **0 個** | ❌ **失敗** |

---

## 為何沒有規則達標？

兩個結構性因素：

### (a) Tier A 定義過於寬廣

H084 zigzag 把 2008-2014 整段標為 Tier A（連續 ~7 年）— 包含金融海嘯後的長期復甦期。
這段期間：
- 多數時候 TAIEX 在 250MA 之上（漲回）
- 景氣燈號常落在綠燈、甚至 2010-2011 紅燈
- → 「現在是否處於急性 panic」 ≠ 「H084 zigzag 標 Tier A」

任何只看當下 panic 訊號的規則，都無法捕捉這 7 年中 75%+ 的 「Tier A but not panic」 日子。

### (b) bull 期間有非典型 panic 出現

OOS 期 bull 有 12.6% FPR，主要是 2024-08 的 yen-carry unwind（市場曾短暫 panic 但歸類 C-sub parent B），blue_streak 短暫上升。

---

## Gate Decision

### Invalidation 對照

| 條件 | 觸發？ |
|---|:---:|
| #1 無一組規則同時滿足 recall ≥ 80% AND FPR ≤ 10% | **✅ 觸發** |
| #2 OOS recall 下降 > 15% | ❌ 未觸發（反向上升）|
| #3 對權重極敏感、無 sweet spot | ⚠️ 部分（streak≥6 系列接近 frontier，但不在 target zone）|

### 決定（待使用者確認）

- [ ] **Reject**：原始假設目標（80%/10%）達不到，接受 Mode 切換規則本質上做不到「乾淨二分」
- [ ] **修改假設後重跑**：
  - 降低目標到 recall ≥ 60% AND FPR ≤ 10%（最佳 `A≥0d OR streak≥6` 通過）
  - 或重新定義 Tier A ground truth（只取 trough ±60 天的 acute period，排除復甦期）
  - 或加入 VIX_pct / margin_drop_60d 作為 B 條件變體
- [ ] **Inconclusive**：本次達不到目標但有可用次優規則，先暫停研究、不影響 H085 既有定案

### 可用的次優結論（即使整體 reject）

如果之後想要「soft Mode 2 detector」（規則調節而非啟停），最佳選擇：
- `A≥0d OR streak≥6`：recall 60%、FPR 8%，比 H084 mode2_OR 略優
- 但**不建議用作 H085 啟停判斷**（會誤殺 60% 的 Tier A panic 機會）

---

## Derived Hypotheses

範圍界定：以下假設改變 ground truth 定義或加入新訊號，超出 H086 原始範圍。

- **H08X-tier-A-acute-redefine**：把 ground truth 從「H084 macro_tier=A」改成「trough ±60 天的 acute period」，重做 grid search。可能根本問題不在規則而在標籤太寬。
- **H08X-vix-margin-mode-trigger**：將 grid 擴展到 `VIX_pct ≥ 80%` 與 `margin_drop_60d ≤ -10%` 為 B 條件變體，看是否能穿透 80% recall 上限。
- **H08X-margin-tier-classifier**：用融資餘額作為 regime 分類器，與 econ_score 互補（econ 慢、margin 快）。

---

## Phase 2 提議

H086 原本設計為**純結構性研究，無 Phase 2**（最佳規則直接餵 H085）。
- 若 reject → 不影響 S004 已 confirmed 的策略（S004 不依賴 mode 切換）
- 若 inconclusive → 暫停研究，待 H087（廣度增強）完成後重評估

---

## Output 檔案

- `explore.py` — grid search 完整腳本
- `rules_grid.csv` — 222 列（74 rules × 3 splits）完整指標
- `is_oos_consistency.csv` — Top-5 規則的 IS/OOS 對比
- `pareto_frontier.png` — 3-panel scatter（IS/OOS/FULL，標 target zone 與 baseline）
