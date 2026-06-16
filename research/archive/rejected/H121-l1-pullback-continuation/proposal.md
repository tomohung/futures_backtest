# Proposal: L1 拉回續攻 — 確立門檻從 L2 放寬到 L1

## ID
H121

## Derived From
H120-l2-pullback-continuation 的 backtest 階段（causal re-validation，2026-06-15）。
H120/S005 被診斷為前視偏誤、causal 版無 edge 後退役；本假設針對其**結構性死因**提出修正方向。

## Trading Intuition
H120 的 causal 驗證指出，S005 的失敗不是訊號太弱，而是**進場幾何天生不利**：
波段確立於錨點上方 ~L2 才進場，目標 L3 只剩 ~0.43×L2，停損偏錨點 ~L2 寬
→ **目標比停損近 → 小賺大賠（負偏態）**。原本 80% 勝率幾乎全來自前視剔除失敗站回，
real-time 不可複製。

直覺：若把「趨勢確立 / 進場」的門檻從 L2 降到 L1，進場更早、離目標更遠，
RR 幾何會明顯改善 —— 這正是針對上述死因的槓桿。代價是 L1 的趨勢確立度較弱
（更多只到 L1 就反轉的雜訊 leg），續攻機率下降。是「勝率↓ / 賠率↑ / 訊號量↑」的三方交換。

### 幾何論證（×EMA20 倍率）
階梯：L1=0.385、L2=0.497、L3=0.711、L4=0.977、L5=1.225（`daystats.py:LVL_QUANTILES`）。
停損採 H120 規格 `stop = 拉回極值 − 0.75×(拉回極值 − 錨點)`，寬度 ≈ 0.75×(確立距離)。

| 進場確立點 | 目標 | 剩餘空間到目標 | 停損寬度 ≈0.75×距離 | RR ≈ |
|---|---|---|---|---|
| L2 (0.497) | L3 (0.711) | 0.214 | 0.37 | **0.58**（= H120 死因：目標比停損近） |
| L1 (0.385) | L3 (0.711) | 0.326 | 0.29 | **1.12**（幾乎翻倍） |
| L1 (0.385) | L2 (0.497) | 0.112 | 0.29 | 0.39（更差，僅列為對照） |

→ 關鍵組合是 **L1 進場 → 目標 L3**：RR 從 0.58 提升到 ~1.12。
這是純幾何上界，未計入「L1→L3 續攻機率 < L2→L3」的折損；EV 是否轉正為實證問題。

## Hypothesis
在 **causal 偵測**（沿用 H120 validate_causal.py 的 streaming ZigZag，不使用未來的 leg 終點 `em`）下：
波段確立於 **L1**（0.385×EMA20）後出現拉回站回 1 分 K 5MA、目標 **L3**（0.711×EMA20）的續攻進場，
其 **per-trade EV / Sharpe 顯著優於 H120 的 L2 確立版（causal baseline Sharpe 0.04）**，
且改善來自 RR 幾何（負偏態收斂、avgR 上升），而非更高勝率。

## Expected Distribution
- L1 確立 leg 的數量明顯多於 L2（L1 達成率 90% vs L2 75%），訊號量上升。
- 條件續攻機率：P(摸到 L3 | L1 確立 + 拉回站回) **低於** L2 版（勝率↓，預期 ~50–62%）。
- 但 avgR / per-trade EV **上升**，負偏態（小賺大賠）收斂，Sharpe > 0.04 baseline。
- 將確立門檻當參數連續掃描 L1→L2：應看到 EV/Sharpe 與門檻的單調或單峰關係，
  協助判斷「最佳進場深度」在哪。

### 虛無對照（必做，避免把描述性相關當 edge）
1. **無條件續攻率基準**：所有「leg 確立於 L1」的樣本，**不論是否有拉回站回 5MA**，
   其後續摸到 L3 的無條件機率。若「拉回站回」的條件機率 ≈ 無條件機率，則站回訊號無資訊量
   （見 [[feedback_excursion_needs_forward_tautology_guard]]）。
2. **前瞻條件期望**：站回當下用的所有特徵必須是 causal（進場時點可見）；
   續攻判定不得引用反轉後才確認的未來極值。
3. **IID 洗牌對照**：將 leg 內 bar 順序/方向洗牌後重算續攻率，確認觀測到的續攻不是隨機漂移。
4. **cross-check 防 `em` 復發**：fork validate_causal.py 後，與 H120 causal 重疊樣本須與原版一致
   （證明只動了確立門檻、沒重新引入前視）。

## Invalidation Condition
任一成立即視為 Rejected / 無 edge：
- causal L1 版 per-trade Sharpe 仍 **≤ 0.10**（與 H120 baseline 0.04 無實質差異）；或
- EV 改善無法通過虛無對照（拉回站回條件機率 ≈ 無條件機率，站回無資訊量）；或
- 幾何改善被續攻機率折損吃光：avgR 未上升 / 負偏態未收斂；或
- 任何「救得回」的 causal 濾網都只能靠砍樣本（留存 < ~25%）換取，易過擬合
  （重蹈 H120 causal_validation 結論）。

## Notes
- **硬約束**：必須建在 `research/archive/rejected/H120-l2-pullback-continuation/validate_causal.py`
  的 causal 引擎上（H120 已歸 rejected），**禁止**改用帶 `em` 前視 bug 的
  `strategies/retired/S005-l2-pullback/backtest.py`。
- 階梯定義單一真相源：`src/chart_ui/services/daystats.py` 的 `LVL_QUANTILES`。
- 相關背景記憶：[[project_ladder_reach_timing_map]]、[[project_extlong_lives_in_late_l3_bucket]]、
  [[feedback_isolate_phenomenon_and_test_each_cell]]。
- 注意 OOS≡高波 regime confound（[[project_oos_equals_highvol_regime]]）：逐年/跨 regime 都要看。
