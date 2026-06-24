# Distribution Research Results: L1-reset 同相位再進場

## Date
2026-06-24

## Conditions Tested
causal L1-reset 狀態機（進場→回 L1 線 reset→重新碰 L2→拉回站回 5MA→再進場）逐日掃 2021-01-29~2026-06-24，
每筆標 `reentry_idx`（同相位第幾次，≥2 = L1-reset 再進場）+ entry_min；零策略 forward excursion（碰
L3/L4/L5、MFE/MAE，自 phase anchor 計，與 H126 同法）。三組對照 + 時間配對 + overfit 檢查。
腳本 `explore.py`，明細 `results/entries.csv`，圖 `results/reset_excursion.png`。

## Sample
- 總進場 N=3653，涵蓋 1241 交易日。**L1-reset 再進場 N=1252**（short 612 / long 640）。
- 每側次數：short 1776（首1164/2次421/3+191），long 1877（首1237/2次436/3+204）。
- 具 L1-reset 的日：short 404 / long 419。**樣本充足**（遠多於 H126 的 318）。

## Key Findings

### 1. Overfit 檢查 — 完全過關（規則普遍存在、非 6/24 專屬）
- L1-reset 再進場分佈在 **717 個不同交易日**，單日最多 7 筆；碰 L5 的 132 筆來自 **98 個不同日**。
- **去掉 6/24**：reset reach 52.7/22.2/10.5% ≈ 全樣本 52.7/22.3/10.5%（零變化）。→ 結論不靠單日。

### 2. Edge — 不成立：時間配對後 reset ≈ 首次，無增量（與 H126 相反）
時間配對（reach L3/L4/L5 %）：

| 時段 | reset | 同時段首次 | N(reset) |
|---|---|---|---|
| <09:30 | 80/44/20 | 74/44/24 | 70 |
| 09:30–10:30 | 67/**34/18** | 66/**33/18** | 434 |
| 10:30–11:30 | 58/**21/9** | 57/**23/10** | 297 |
| ≥11:30 | 31/8/3 | 37/10/4 | 451 |

→ 各時段 reset 與首次**幾乎重疊**（深目標 L4/L5 無差或略低）。

### 3. 純 reset 效應（C vs B，同相位再進場 vs 首次）為負
- C(reset) pooled 52.7/22.3/10.5% ≪ B(會出現 reset 的相位之首次) 59.8/27.4/14.4% ≈ A(不會的首次) 60.5/30.6/15.4%。
- 但這個「差」**全由 reset 進場較晚造成**（emin 651 vs 595/615）；§2 時間配對後即拉平。
- **無論用哪種對照，L1-reset 再進場都沒有續攻溢價。**

### 4. 為什麼與 H126 相反（機制解讀）
H126「跨相位第 2 次」需要一段 **≥L2 反向 swing 失敗**——該失敗本身是趨勢轉強的選擇性訊號，故 2nd+ 的
L4/L5 約 2× 首次。H130 的 **L1-retrace 太淺（未翻相位）**，只是趨勢內雜訊，不構成「測試趨勢」，因此其後
再進場與同時段任一首次無異。6/24 抱到 L5 = 強趨勢日隨便進都跑遠，那筆 reset 並不特別。

## Vs. Expected
**不符合**（命中 Invalidation #2）：預期「L1-reset 再進場續航顯著優於首次/時間配對基準」→ 實際**時間配對後
無增量**（reset ≈ 首次）。Invalidation #4（overfit）**未成立**——規則不靠 6/24，但這反而證明它只是「普通的
延遲 L2 拉回進場」，沒有特殊 edge。母體（任一 L2 拉回）causal 後 break-even（H120），reset 子集無時間配對
增量 → 推論其 P&L 亦約 break-even，非 H126 那種正 EV 子集。

## Gate Decision
[ ] 進入 Phase 2
[x] Archive（**Rejected/Inconclusive**：L1-reset 再進場無時間配對 edge，續航與同時段首次無異）
[ ] 修改假設

**理由**：核心賭注是「L1-reset 再進場有選擇性續攻 edge」，三組對照（pooled C<B、時間配對 reset≈首次、
overfit 去 6/24 不變）一致顯示**無增量**。不建議以此單獨進 Phase 2（預期 ≈ break-even 母體）。
**但**：reset 進場在 09:30–10:30 的絕對 reach（L4 34%/L5 18%）與首次相當，可作 H126 訊號的**覆蓋擴充**
（提供更多同質續攻進場機會），只是**不是 edge**——若要併入，須以「覆蓋/再進場機制」而非「alpha」定位。

## Derived Hypotheses
- **H131（候選）**：edge 來自「反向 swing 的深度」——reset 深度 dose-response：把「中間反彈幅度」當連續變數
  （L1-retrace=淺→無 edge、≥L2 翻相位=H126 有 edge），測「反彈愈深、再進場續攻 edge 愈強」的單調關係，
  把 H126/H130 統一成一條「counter-move depth」軸（這才是真正的 driver 假設）。
- **H128/H129**（沿 H126）：2nd+ 更寬停損賠率、序數 dose-response。
