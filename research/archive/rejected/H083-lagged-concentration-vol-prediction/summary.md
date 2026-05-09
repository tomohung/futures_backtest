# Archive: 時序版集中度預測 (H083)

## Status
**Rejected** — 集中度對既有夜盤 vol 訊號在 vol prediction 兩個 metric 都無顯著獨立增量。

## Summary

H083 從 H080 衍生，原本想用「t-1 集中度」當 vol predictor 套到 S001-esthl 的動態倍數調整。但跟既有夜盤訊號比較後，集中度的解釋力遠弱（R² 7 倍差距），且加進夜盤後 conditional t-stat 接近不顯著，增量 R² < 0.01。加上 H070（confirmed）已證類似設計（用 vol 訊號連續縮放 SatZone）無策略增益，H083 純集中度版本不具差異化研究價值。

未執行正式 Phase 1，直接 reject — 兩支探索腳本（`explore_night_vs_concentration.py` + `explore_concentration_reach.py`）已提供決定性證據。

## Key Evidence

### 振幅預測（探索 1）— 樣本 898 天
| 模型 | dev t | night t | R² |
|---|---|---|---|
| dev only | 5.42 | — | 0.032 |
| **night only** | — | **16.62** | **0.236** |
| joint | 2.85 | 15.78 | 0.242 |

夜盤 R² 是集中度的 7 倍。集中度 joint t=2.85 仍顯著，但**增量 R² 只 +0.007**。

### 觸及率預測（探索 2）— 樣本 898 天
| 模型 | dev t | night t | R² |
|---|---|---|---|
| dev only | 3.96 | — | 0.017 |
| night only | — | 11.30 | 0.125 |
| **joint** | **1.60** ⚠️ | 10.62 | 0.127 |

加進夜盤後 dev t-stat 從 3.96 → 1.60（p ≈ 0.11，**邊緣不顯著**）。增量 R² +0.0025。

### 5×5 雙桶矩陣的關鍵發現
集中度只在「夜盤已高」時提供微小補強：
- D1×N5 (集中低夜盤高)：P(reach 1x) = **58.6%**（n=29）
- D5×N5 (雙重高)：P(reach 1x) = 60.7%（n=61）
- 差距 +2.1 pp — **集中度補強微乎其微**

集中度高+夜盤低 (D5×N1)：P(reach 1x) = 38.9% ≈ baseline，集中度高無法救觸及率。

### H070 的重複風險
H070（confirmed）已測過用夜盤訊號做 SatZone 連續縮放：
- Phase 1：夜盤 R²=0.097（顯著）
- Phase 2：「現有規則維持不變」— 縮放策略無策略增益

H083 用更弱的訊號（集中度）重演同樣設計，預期同樣失敗。

## Why Rejected (而非 Inconclusive)

| | rejected | inconclusive |
|---|---|---|
| 證據明確性 | ✓ 兩個 metric 都顯示無實質增量 | 結果不明確 |
| Conditional t-stat | ✓ 1.60-2.85 區間 | 顯著但不一致 |
| 重啟可能性 | 需要全新 differentiated 假設（不是 H083 變體） | 同假設可重新探索 |

H083 假設核心「集中度可獨立提供 vol prediction」已被證據否決。即使未來想到「differentiated 設計」（如 binary filter、極端格倉位），那是新假設，不是 H083 重啟。

## 與 H080 的關係（重要：不否定 H080）

H080（confirmed）的核心結論是「集中度是同期 indicator，能分類行情型態（方向、振幅、crash）」 — 仍成立。

**H083 reject 否定的是**：「集中度可作為**獨立的時序 vol predictor**」這個延伸假設。

H080 的衍生方向（H081 Friday 方向、H082 安全日）並未被本 reject 影響 — 它們不是 vol prediction 角度，而是條件性 direction / crash signal。

## Lessons Learned（防止未來重蹈覆轍）

1. **新衍生假設應檢查既有研究的 negative finding**：H083 設計初期未充分檢查 H070，導致重複設計。建檔流程可加一步「掃描相關既有 archive 的 reject/inconclusive 結論」
2. **Univariate 顯著 ≠ Conditional 顯著**：H080 follow-up 的 corr +0.18 看起來有用，但 conditional on 夜盤後幾乎消失。多訊號 OLS 比較應該是 vol prediction 假設的標準 GATE 之一
3. **避免用更弱訊號重演已 fail 的設計**：H070 用更強訊號（夜盤）測 SatZone scaling 都失敗，用更弱訊號（集中度）做同樣事的先驗就應該很低

## Derived Hypotheses
無（這是 reject 的研究，沒有衍生方向）。

注意：H080 的衍生 H081 / H082 不是從 H083 衍生，跟本 reject 無關。

## Links
- [Proposal](proposal.md)
- [Tasks](tasks.md)
- [Follow-up Note](follow_up_note.md) — 完整探索過程與 reject 推理
- [Exploration script 1: night vs concentration on day range](explore_night_vs_concentration.py)
- [Exploration script 2: concentration on EstRange reach](explore_concentration_reach.py)
- 相關歷史研究：H070 (night-vol-estrange-reach), H075 (NVF method upgrade)
