# Tasks: dci_short × 盤中下行關卡觸及 × 各時間點 — 空方關係地圖

## Phase 1: Distribution Research（空方條件地圖）

時間點 T={09:01,09:05,09:10,09:15,09:20,09:25,09:30}；下行關卡 L1–L5；連續 dn_full/EMA20。
dci_short 成分：s_thr=−thrust(W-100)、s_B=−B(家數)、合成=z(s_thr)+z(s_B)。

- [x] 算每個 t 的 s_thr/s_B/合成 dci_short(t)（181 日）
- [x] 算 TX open-anchor 下行擺幅 + L1–L5 達成 + 連續 dn_full/EMA20
- [x] **核心地圖**：合成 L4 強分位 forward lift 僅 +2~8%（多方同位 +17~23%）→ 弱
- [x] **成分對照**：合成 corr+0.357 > s_thr+0.298/s_B+0.261（互補成立）；家數主導下行 L4(+11%)
- [x] **成熟曲線**：非單調、無乾淨 t*（09:30 Q1-5=[14 14 19 11 25]）
- [x] **forward vs 全日**：L1/L2 負(已達)、深關卡正但弱
- [x] **關卡深度 + 薄度**：下行 L4 N達=39、forward 30、強分位∩L4 ≈9 日（核心限制）
- [~] 與多方對照：連續 +0.357≈多方 +0.39，但離散弱很多（已記於 distribution.md）

---
### GATE
**問題：空方是否存在可用的「dci_short → 下行關卡達成」條件結構？**

- 某些 (t, L_k)：強分位 forward 達成率顯著高於 base，五分位單調，**樣本足夠（強分位達成 ≥ 8 日，誠實標薄）**。
- forward-guard 後仍在。合成 ≥ 單一成分（互補成立）。能定出 t*。
- 若下行深關卡樣本太薄無法判 → **Inconclusive 待資料**（非硬 Reject；proposal Invalidation #5）。
- data snooping：dci_short 公式沿用 H095（同窗）→ 同窗描述，OOS 待資料擴充。

**決定：** [ ] 繼續 Phase 2　[ ] Inconclusive 待資料　[ ] Archive　[ ] 修改假設

---

## Phase 2:（條件結構成立後）穩定性與門檻（同 H111 框架）
- [ ] 絕對門檻掃描：P(forward 下行 L4 | dci_short ≥ x) vs base，找最大穩定 lift
- [ ] 穩定性：2025-H2 vs 2026、月別（樣本允許範圍，附 N，誠實標薄）
- [ ] OOS：待 stock_min 擴充（→2026-06 + 回補 + TPEX + 不同 regime）
- [ ] 下游接口：輸出「強 dci_short → forward 達下行 L4 機率」條件，供空方順勢/突破下殺族引用

## 產出腳本（保留於本目錄）
- `explore.py`（可重用 H111 explore.py 框架 + H095 dci_short_combine.py / dci_universe_sweep.py 的 W-100/B 計算）
