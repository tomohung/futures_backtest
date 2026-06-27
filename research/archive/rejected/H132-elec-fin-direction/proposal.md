# Proposal: 電子/金融 leadership 方向作為日線 directional risk-on/off 訊號

## ID
H132

## Derived From
H131 的 distribution 階段。H131 主假設（比率「趨勢強度」偵測 trend-vs-chop regime）被
Rejected，但附帶檢驗的「方向」效應意外強且穩健 —— 本假設專門承接並嚴謹驗證該方向效應。

## Trading Intuition
電子是台股高 beta 攻擊主體、金融是低 beta 防禦主體。當電子相對金融轉強（電子/金融比率
站上自身均線）＝資金偏攻擊（Risk On）；金融轉強＝偏防禦（Risk Off）。H131 Phase 1 已觀察到：
電子領先時，**未來** TAIEX 報酬中位數明顯高於金融領先時，且差距隨持有期擴大 —— 暗示這個
leadership 方向帶有「風險偏好」的前瞻資訊，而非只是事後同步。

定位：**日線層級的方向型 risk-on/off 訊號**（非當沖、非趨勢度 regime）。

## Hypothesis
令 `r = ln(TSE23/TSE28)`、`dir = sign(r − SMA_W(r))`（W∈{10,20}）。
則 **dir=+1（電子領先）時，未來 K 日 TAIEX 報酬顯著高於 dir=−1（金融領先）時**，且此預測力
**獨立於 TAIEX 自身價格動能**（控制 trailing return 後仍顯著）。K∈{5,10,20}，效應隨 K 增強。

### H131 已建立的先驗證據（非重疊 OLS，誠實 N）
- dir 對 forward TAIEX 報酬：t = 1.63/2.89/2.79（W10）、2.69/2.63/2.44（W20），K≥10 穩定 t>2.4。
- 控制 TAIEX trailing return 後 dir t 幾乎不變；TAIEX 動能自身 t<1.2（已死）。
- 電子領先 vs 金融領先 median fwdRet：(W20,K20) +1.67% vs +0.80%；(W20,K5) +0.52% vs +0.16%。

## Expected Distribution
- 子期間（pre/post 2019 改名界、逐年/逐 regime）中，dir 的符號方向**一致為正**（電子領先→較高 fwdRet），
  即使顯著性在小樣本子期間減弱也不應反號。
- 控制 VIX regime / fg-composite comp_z 後，dir 仍保有增量（非單純恐懼貪婪指標換句話說）。
- 多空對稱性：理想上電子領先帶來「相對更高」、金融領先帶來「相對更低/防禦」；但 H131 顯示
  兩組 median 皆為正（受 equity drift 影響），edge 在 **spread** 而非單邊翻空。

## Invalidation Condition
任一即視為不成立 / 大幅下修：
1. **子期間反號**：在主要子期間或 OOS≡高波 regime（[[project_oos_equals_highvol_regime]]）中
   dir 效應翻號或消失 → 原 t 由單次低波→高波切換 confound 撐起，非穩定 edge。
2. **被恐懼貪婪吸收**：控制 VIX regime / fg-composite 後 dir 增量歸零 → 只是既有 risk 指標代理。
3. **不可交易**：扣成本（手續費+滑價）後、合理門檻/持有期下，spread 無法轉成正 EV 且回撤可接受
   （[[feedback_filter_eval_includes_streaks]]：須看連敗/drawdown 非只看 PF）。
4. **僅尾段驅動**：效應集中在少數極端時段（如 2025 高波），剔除後消失。

## Notes
- 資料：`results/sector_index.csv`（N=3924，2010-01-04~2026-06-26）由 H131 Phase 0 驗證後沿用
  （TWSE MI_INDEX type=IND，電子工業類=TSE23、金融保險類=TSE28，價格指數；0 污染）。
- 方法論硬規則（[[feedback_excursion_needs_forward_tautology_guard]]）：forward 窗重疊 →
  顯著性用非重疊 stride=K 子樣本；虛無對照含 TAIEX 自身動能、VIX regime、fg-composite。
- 警示（[[project_oos_equals_highvol_regime]]）：2026-03~06 OOS≡高波 regime，所有單次 IS/OOS
  結論與 regime 切換 confounded → H132 穩定性檢驗以逐年/逐 regime 分層為主，不靠單一 OOS 切點。
- 經濟詮釋：電子領先 ≈ 全球科技/AI beta ON ≈ 風險偏好，與 fg-composite 家族互補。
- 相鄰：[[project_dci_is_extension_signal]]（DCI 為方向/延伸訊號，配順勢有效）—— 本訊號同屬方向族，
  Phase 2 應優先測「與順勢應用結合」而非 fade。
