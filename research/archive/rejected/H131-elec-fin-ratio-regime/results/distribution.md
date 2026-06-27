# Distribution Research Results: 電子/金融比率趨勢強度作為 regime 偵測器

## Date
2026-06-26

## Conditions Tested
- 資料：TWSE MI_INDEX type=IND 逐日抓取。電子工業類指數（2019H1 前名「電子類指數」，
  同一連續序列）= TSE23；金融保險類指數 = TSE28。價格指數（非報酬）。
- 比率 `r = ln(TSE23/TSE28)`。
- **趨勢強度（測 B）**：`ratioER` = r 過去 W 日 Efficiency Ratio，W ∈ {10,20}。
- **方向（測 A）**：`dir = sign(r − SMA_W(r))`。
- **標的**：TAIEX 未來 K 日 ER（測 B）/ 未來 K 日報酬（測 A），K ∈ {5,10,20}。
- 顯著性：forward 窗重疊 → 一律用 **非重疊 stride=K 子樣本** OLS（誠實 N）。
- 虛無對照：B = TAIEX 自身 trailing ER；A = TAIEX 自身 trailing 報酬（動能）。

## Sample
- N = 3,924 交易日，2010-01-04 ~ 2026-06-26（涵蓋 ~97% 交易日，缺漏 114 日均勻分布）。
- 資料驗證：0 重複日、0 污染（無跨期相同 (tse23,tse28) 值對）、最大單日 9.7%/9.9%（2025-04-07 關稅崩跌，真實）。

## Key Findings

### (B) 主假設「趨勢強度 → trend-vs-chop regime」：**不成立** ✗
- **共線意外低**：spearman(ratioER, taiexER) 僅 +0.12~0.15 —— 比率自己會不會走趨勢，跟
  TAIEX 會不會走趨勢幾乎無關。但即便如此，ratioER 對 forward TAIEX-ER 仍：
- **相關 ≈ 0**：spearman(ratioER, fwdER) = −0.021/+0.019/+0.010（W10）、−0.002/+0.017/+0.048（W20）。全部貼近 0。
- **五分位非單調**：6 個 (W,K) 組合 **全部** ✗非單調（見 `ratioER_vs_fwdER.png`）。
- **零增量**：非重疊 OLS 中 ratioER 的 t = 0.25~0.79（全不顯著），ΔR² = +0.0003~0.0008（可忽略）。
- 雙重排序 3×3：控制 taiexER 後，ratioER 由低到高無一致 fwdER 變化。
- 旁證：**taiexER β 為負且顯著（t −2.1~−2.7）** → TAIEX 趨勢度本身在 5~20 日尺度是
  **均值回歸** 的（高趨勢度後傾向回落），與「trend regime 很黏」的先驗相反。這是 TAIEX
  自身性質，與本假設正交。

→ 命中 Invalidation #1（無單調）＋ #2（無增量）。**(B) 該被 Reject。**
比率的「果斷 leadership = 市場在 trend」這個機制，在資料上不存在。

### (A) 附帶「方向 → 風險偏好」：**強烈正向且穩健** ✓（意外亮點）
- 電子領先（r 在 MA 上方）→ forward TAIEX 報酬中位數明顯高於金融領先，且隨 K 擴大：
  | (W,K) | 電子領先 median | 金融領先 median |
  |---|---|---|
  | (20,5) | +0.52% (N=442) | +0.16% (N=338) |
  | (20,10) | +0.82% (N=217) | +0.46% (N=173) |
  | (20,20) | +1.67% (N=109) | +0.80% (N=86) |
  （W=10 同向，K=20 達 +1.76% vs +0.41%。）
- **通過動能對照（關鍵）**：fwdRet ~ z(dir)+z(TAIEX trailing return) 非重疊 OLS：
  - dir 的 t-stat：1.63 / 2.89 / 2.79（W10）、2.69 / 2.63 / 2.44（W20）—— K≥10 穩定 t>2.4。
  - 控制動能後 dir t 幾乎不變（1.73 / 2.66 / 2.67 / 2.80 / 2.48 / 2.48）。
  - **TAIEX 自身動能 t = −0.78~+1.15（全不顯著）** —— 指數動能本身在此尺度已死。
  - dir 對動能的 ΔR² = +0.004~+0.036（隨 K 成長）。
- → 電子/金融 leadership 的 **方向**，對 forward TAIEX 報酬有 **獨立於價格動能** 的預測力。
  經濟意義合理：電子領先 = 全球科技/AI beta = 風險偏好 ON。

## Vs. Expected
- (B) 與預期 **相反**：proposal 預期 ratioER 分位對 fwdER 單調遞增且有增量 → 完全沒有。
  proposal 自己標註「最可能的死法 = 控制 TAIEX-ER 後 partial 歸零」**正中**。
- (A) **超出預期**：原列為次要、可接受不顯著；實際是全研究最強、最穩健的訊號。
- 與記憶一致：leadership/breadth 類（如 DCI, project_dci_is_extension_signal）屬「方向/延伸」
  訊號，不是「趨勢度 regime」預測器 —— 本研究再次印證此分野。

## Gate Decision
- [ ] 進入 Phase 2（B 形式）
- [x] **(B) Archive 為 Rejected**：趨勢強度無法偵測 trend-vs-chop regime（零相關、非單調、零增量）。
- [x] **(A) 衍生為新假設**：方向型 risk-on/off 預測 forward TAIEX 報酬，穩健通過動能對照，
      值得獨立、嚴謹驗證（子期間穩定性、regime 切割、實際可交易性）。
  > 待使用者拍板：要把 (A) 留在 H131 內續做，或開新 HXXX。

## Derived Hypotheses
- **H132（建議）**：電子/金融 leadership 方向（`sign(r − SMA_W)`）作為 **日線 directional
  risk-on/off 訊號**，預測 forward TAIEX 報酬。Phase 1 已顯示 t>2.4（K≥10）、獨立於動能。
  需補：(1) 子期間穩定性（pre/post 2019、含 OOS≡高波 regime confound，見
  project_oos_equals_highvol_regime）；(2) 與 VIX regime / fg-composite 的增量；(3) 多空對稱性
  （目前兩組皆正，差的是 spread）；(4) 可交易化（門檻、持有期、成本）。
- **H133（選配）**：更細切面「半導體類 vs 金融」是否比大分類電子/金融更強（電子工業類含
  非半導體雜訊）。
