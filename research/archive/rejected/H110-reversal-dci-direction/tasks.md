# Tasks: Reversal 方向濾網改用 DCI 盤中廣度訊號

## Phase 1: Distribution Research（檢查點掃描 × 五分位強度 × 方向歧異 × 誰對）

檢查點 T = {09:05, 09:10, 09:15, 09:20, 09:25, 09:30}；強度=`|dci_long(t)|` **五分位**（逐檢查點各自定界，181 日面板）。

- [x] 算每個檢查點 t 的 `dci_long(t)=W-20 thrust@t`（181 日面板 + 窗內每日）
- [x] **層 A（純訊號品質，全 181 日）**：各 t、各五分位，sign(dci_long) 對「TX 擺更遠的一邊」命中率
      → 強度單調性弱（僅最強分位明顯）、各 t 最強分位皆 ~67-75%
- [x] 算窗內 reversal 進場日的 `base`(5m120MA 斜率=trade Direction) 方向、進場時間（CSV 2025-06~12）
- [x] **層 B（reversal 特定，因果）**：各 t，進場≥t 子集，base vs dci(t) 歧異率、歧異日「誰對」
      → 歧異日 dci 命中 >> base（09:10：dci 72% vs base 28%）
- [x] **因果代價表**：各 t 可用筆數（09:10=71 全覆蓋 → 09:30=36）併入層 B 表
- [ ] 視覺化（熱圖）— 數據已足以 GATE，圖待 Phase 2 需要時補

---
### GATE
**問題：是否存在某個檢查點 t，DCI 方向在強分位明顯贏 base、隨強度單調、且仍覆蓋夠多 reversal 進場？**

- 至少一個 t 滿足：**最強分位**歧異日 dci 命中 **明顯高於** base，且呈 **單調遞增**（機制證據，非單一聚合數）。
- 該 t 的因果可用 reversal 筆數足夠（**強分位歧異日 ≥ 10**；該 t 可用 reversal 總筆數 ≥ 30）。
- 層 A（全 181 日純訊號）在該 t 也呈強度單調 → 排除「只是窗內 reversal 小樣本巧合」。
- data snooping：DCI 公式已在 H095 用同窗校過 → 同窗驗證，正式 OOS 待資料擴充。

**決定：** [ ] 繼續 Phase 2（選定 t* 與分位門檻）　[ ] 直接 Archive（歸 H101 同類）　[ ] 修改假設後重跑

---

## Phase 2: Backtest（base vs dci vs both）

- [x] `reversal.py` `_direction()` 新增 `dir_mode='dci'/'both'`（讀注入 DCI_Dir/DCI_Strong；live `base` 零變動）
- [x] DCI 注入：每日 dci_long(09:10) 方向+強分位 bool 廣播成 bar 欄位（09:10 後且窗日才有值）
- [x] 窗內回測：`base` / `dci` / `both` 三組（唯一變數=方向來源）
- [x] 績效對比：對齊 H101 表格式（見 results/backtest.md）
- [x] 逐筆歸因：**dci−base=+1.11 全來自 1 筆 dci 獨有交易；翻向機制 0 貢獻** → 改善=雜訊
- [~] 敏感度：主結論（機制 0 貢獻）與門檻無關，掃參數無意義，略
- [x] **OOS 註記**：無法做（DCI 單一窗）；但 in-window 歸因已證機制 inert，非樣本不足

### Verdict（backtest.md）：建議 **Rejected** — fade 型策略「方向對≠賺」，DCI 方向結構上幫不上；獨立再確認 H101。

---

## 產出腳本（必須保留於本目錄）
- `explore.py`（Phase 1 歧異/命中分佈）
- `backtest.py`（Phase 2 三組回測）
- 結果存 `results/`
