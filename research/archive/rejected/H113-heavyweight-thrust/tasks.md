# Tasks: 重權值推力（Heavyweight Thrust）

## Phase 1: Distribution Research（HT vs ext_long，含套套邏輯防護）

定義 HT = 前 N 大權值的 (p@t−open)/range_i，近似指數權重加權、linear（不 tanh）。N∈{5,10,15}。

- [x] 近似 TAIEX 權重 hardcode + 等權對照
- [x] HT(09:15/09:30)：N=5/10/15、linear/tanh、cap-weight/等權
- [x] **核心對打**：ext_long r=+0.224 略勝 HT(+0.199~0.206)；等權 HT 近無效(+0.06)
- [x] **subsume**：控制 ext_long 後 HT partial=+0.044；控制 HT 後 ext_long 仍 +0.114 → **ext_long subsume HT（反向）**
- [x] **★套套邏輯防護**：corr(HT,TX自身)=+0.59；控制後 HT +0.091 < ext_long +0.132 → HT 更像指數鏡子
- [x] **窄基案例**：2/25 ext_long −0.13 漏、HT5 +0.18/HT10 +0.14 翻強 → 補漏成立（少數尾部）
- [x] 敏感度：N 差異小、等權崩、cap-weight 才有訊號
- [~] 連續擺幅：結論一致，略

---
### GATE
**問題：HT 是否為「更強且非套套邏輯」的多方 reach 預測，值得取代/並列 ext_long？**

- HT forward L4 鑑別力 ≥ ext_long，且 **控制 TX 自身 09:30 擺幅後仍顯著**（過套套邏輯防護）。
- subsume 成立（HT 在、ext_long 邊際趨近 0）→ 用戶「更強非互補」假設得證；
  若兩者控制彼此後都顯著 → 改判「互補」（記錄，仍可用）。
- 樣本足夠（forward L4 達標日 N≈53；強分位每格 ≥ ~10）。
- data snooping：同窗描述，OOS 待資料擴充。

**決定：** [ ] 繼續 Phase 2　[ ] 改判互補　[ ] Archive（HT 非更強/純套套邏輯）　[ ] 修改假設

---

## Phase 2:（若 HT 勝出）穩定性 + 接 chart-ui
- [ ] 穩定性分段（2025-H2 vs 2026、月別，附 N）
- [ ] 定可用門檻（HT 強 cutoff）+ 與 ext_long lift 對比
- [ ] OOS 待資料；下游：chart-ui「延伸力·多」改用/並列 HT；回修 H111 多方結論
- [ ] 若改判互補：設計 HT + ext_long 合成的多方 gauge

## 產出腳本（保留於本目錄）
- `explore.py`（HT vs ext_long 對打 + 套套邏輯防護）；重用 H111 explore.py / src/chart_ui/services/extension.py 框架。
