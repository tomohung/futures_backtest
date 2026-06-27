# Distribution Research Results: 電子/金融 leadership 方向作為 directional risk-on/off

## Date
2026-06-27

## Conditions Tested
- 資料：`results/sector_index.csv`（H131 驗證沿用，N=3924，2010-01-04~2026-06-26）。
- 訊號：`dir = sign(ln(TSE23/TSE28) − SMA_W)`，W∈{10,20}。標的 forward TAIEX 報酬 K∈{5,10,20}。
- 顯著性一律非重疊 stride=K。穩定性測：逐年、pre/post 2019、realized-vol/VIX 三分位、
  增量（控制動能+rvol+VIX）、對稱性、剔除 2025。

## Sample
- 基礎/逐年/rvol：全樣本 2010+。VIX 控制與分層：2016-11 起子樣本。

## Key Findings

### 基礎效應：**重現 H131** ✓（但僅此而已）
- 非重疊 OLS dir t = 2.4~2.9（K≥10），電子領先 med fwdRet > 金融領先，spread 隨 K 擴大。

### 穩定性：**系統性不及格** ✗（核心否決）
1. **逐年符號不一致**：spread>0 僅 **11/17 年**，6 年反號（2011 −1.29, 2012 −0.48,
   2017 −0.83, 2018 −1.72, 2024 −0.67, 2026 −4.05）。含近兩年 2024/2026 反號 → 非持續 edge。
2. **pre/post 2019 雙雙不顯著**：pre t=+0.99（spread **−0.18%**，竟為負）、post t=+0.94。
   全樣本 t=2.6 一切兩半就蒸發 → 池化假象，非穩定效應。
3. **只活在「中間桶」**：
   - realized-vol 三分位 spread：低波 +0.06 / **中波 +1.30** / 高波 +0.14
   - VIX 三分位 spread：低VIX −0.19 / **中VIX +1.09** / 高VIX −0.07
   效應集中在中波/中VIX，低高兩端≈0 甚至負 → 不是單調的「風險偏好」訊號，是中段噪音。
4. **增量勉強**：控制 mom+rvol（全樣本）dir t=2.30 尚存，但 **rvol t=3.49 才是最強**；
   2016+ 再加 VIX 後 dir t **降到 1.96**（破 2）。訊號與波動高度共動。

### 對稱性 / 尾段依賴
- baseline med +0.74%（純 equity drift）。電子領先 Δ=**+0.17%**、金融領先 Δ=−0.25% →
  電子側超額極小，大半是 drift；edge 偏「金融領先時較弱」的單邊、且絕對幅度小。
- **剔除 2025（高波 AI 年）後 spread 由 +0.36 腰斬到 +0.18%**（t=2.01）→ 近年單一 regime 撐盤。
- 每日 long-short（dir20 持 1 日）年化 Sharpe≈0.72（gross，未扣成本），考量上述不穩定不足採信。

## Vs. Expected
- **不符合**。proposal 預期「子期間符號一致為正、不反號」「控制 VIX 後仍有增量」「edge 在 spread」——
  實測：6/17 年反號、pre 期 spread 為負、中間桶獨大、VIX 控制後 t<2、edge 對 2025 高度依賴。
- 命中 Invalidation #1（子期間反號）、#2 邊緣（VIX 控制後 t 1.96）、#4（僅尾段/中段驅動）。
- 教訓：H131 headline t=2.4~2.9 是**池化假象** —— 穩定性電池正是為抓這個而設，且抓到了。
  與 [[project_oos_equals_highvol_regime]] 的 confound 警示同源，但更糟：連「高波驅動」都不是，
  是中段桶+少數年份。

### 補充：使用者原始構造（站上均線+持續走高 / 跌破均線下緩衝）— 同樣失敗
測試比裸 sign 更選擇性的構造（`explore_buffer.py`）：RiskOn = r>SMA 且持續走高(r_t>r_{t-L})；
RiskOff = r<SMA−buf×std。掃 L∈{3,5}×buf∈{0,0.5,1.0}：
- 池化 spread +0.25~0.47%、t 2.3~2.6（一樣漂亮），但 **逐年為正僅 9~11/17**，緩衝/持續性**無助穩定**。
- 反號年相同（2011,2012,2015,2017,2018,2024,2026）。
- **近年關係反轉**：2024 spread −1.32（金融領先 med +2.70 > 電子 +1.38）、2026 spread −4.24
  （金融領先 +6.95 > 電子 +2.71）。「電子強=Risk On」在 2024/2026 **倒過來**（金融股 rally）。
- 結論：使用者原始 framing 直覺合理但資料不支持，且訊號**會隨 regime 翻號、近兩年正在翻號** →
  無法靜態使用。強化 Reject。

## Gate Decision
- [ ] 進入 Phase 2
- [x] **建議 Archive 為 Rejected**（或 Inconclusive）：directional 訊號如本式定義，不具可交易的穩定性。
- 待使用者拍板（見下方 GATE）。

## Derived Hypotheses
- H133（原選配，價值下降）：半導體 vs 金融更細切面 —— 但本研究顯示問題在「方向→報酬」關係本身
  不穩定，換分子未必救得回，優先級調低。
- 方法論備忘：任何「池化 t 顯著」的訊號，晉升前必過逐年符號 + 子期間 + regime 三分位三關，
  否則池化假象會偽裝成 edge。
