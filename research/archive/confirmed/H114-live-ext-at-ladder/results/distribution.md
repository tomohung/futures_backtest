# Distribution Research Results: 即時延伸力 @關卡 分辨續攻 vs 滿足點

## Date
2026-06-10

## Conditions Tested
- 事件：TX 上行擺幅（open-anchor 累計 max）首次觸及 L3/L4/L5（c=0.711/0.977/1.225 × causal EMA20）的分鐘 t_k。
- 即時 ext_long（universe W5/W10，value-weighted tanh）三種衰竭定義：level（水平）、slope（近 5 分斜率）、ddpeak（自當日峰回落，大=滾頭）。皆於 t_k 當下讀（forward-guarded，因果乾淨）。
- 結果：t_k 之後是否再觸及 L_{k+1}（續攻=1）。
- 對照/控制：frozen0915（早盤凍結讀數）、碰觸時點 tk、滿足度代理 satcons（擺幅/EMA20）。
- 切法：強弱以 **IS 母體中位數**切，OOS 只驗（不偷看）。腳本 `explore.py`、原始 `results/distribution_raw.txt`、panel `ladder_live_ext_panel.csv`。

## Sample
- 事件總 N=255（含所有關卡）；窗 2025-06-03~2026-06-09。
- **L3→L4**：IS 碰觸 105 天 / OOS 44 天（base 續攻 50% / 45%）。
- **L4→L5**：IS 53 / OOS 20（base 45% / 45%）。
- 市場：上市 TWSE-only。IS=≤2026-02-26、OOS=≥2026-03-01。

## Key Findings

### 1. 主訊號是「碰觸時點」，不是 ext_long（最強且最穩）
| 轉換 | 時點 gap（早碰−晚碰）IS | OOS |
|---|---|---|
| **L3→L4** | 早碰 70% vs 晚碰 31% = **+39%** | 早碰 65% vs 24% = **+41%** |
| L4→L5 | +25% | +12% |
- **早碰 L3（≤10:05）→ 續攻 L4 機率 ~65-70%；晚碰 → ~24-31%**。gap +40% 且 IS/OOS 幾乎相同 → 極穩、近乎機械（碰得早=後面還有時間/動能延伸）。

### 2. 即時 ext_long：level 崩、ddpeak 守，但**僅在「晚碰層」有增量**
無條件強−弱 gap（IS 中位切）：
| metric | L3→L4 IS | L3→L4 OOS |
|---|---|---|
| level 水平（W10）| +25% | **+0%（崩，同 frozen 過擬合）**|
| slope 斜率 | −5% | +28%（符號不穩=噪音）|
| **ddpeak 自峰回落（W10）**| +17% | **+15%（守住）**|
| frozen0915（W10）| +28% | +12% |

**控制碰觸時點後的增量**（ddpeak W10，L3→L4）：
| 層 | IS 增量 gap | OOS 增量 gap |
|---|---|---|
| 早碰層 | −7% | **−25%（無用/反向）**|
| **晚碰層** | **+18%** | **+22%（守住）**|
- **早碰時 ext_long 冗餘**（反正會續攻）；**晚碰時 ext_long 強（延伸力未滾頭）→ 救回續攻 +22%（OOS）**。方向一致、可用。
- **衰竭定義要用 ddpeak（有沒有滾頭），不是 level（絕對水平 OOS 崩）**。

### 3. L4→L5 無法判定
層內樣本 n=2~6、符號亂跳（早碰 OOS +33%(n6) vs 晚碰 OOS −25%(n4)）→ **不可用**。與既有「L4→L5≈擲銅板、不做強度分級」一致。

### 4. satcons（擺幅/EMA20）滿足度代理無分辨力
L3 IS +1%、L4 IS −9% → 單純「已消耗多少 EMA20 振幅」不分辨續攻（關卡本身已是 EMA20 倍數，代理冗餘）。SatZone 完整版（含當日 vol_ratio）留 Phase 2 正面對撞。

## Vs. Expected
- **部分符合**：即時讀數（ddpeak 形式）確實 OOS 守住且贏過 level/frozen——**但只在晚碰層**，且**被「碰觸時點」這個更強的主訊號蓋過**。
- **意外**：原以為 ext_long 是核心，實測**碰觸時點才是 ladder 續攻的主軸**（+40% 穩）；ext_long 退為「晚碰時的二級修正」。
- **符合預期**：L4→L5 偏難/不可用；level 絕對水平 OOS 崩（呼應 H111 OOS）。

## Gate Decision（待使用者裁決）
證據狀態：
- ✅ 樣本足（L3→L4 IS105/OOS44）；L4→L5 OOS 層內太薄、L5 不判定。
- ✅ 發現一個**強且 OOS 穩的主訊號（碰觸時點 +40%）**，外加**晚碰層的即時 ext_long(ddpeak) 增量 +22% OOS**。
- ⚠ 原假設主角（即時 ext_long）被降為配角；level 形式否決，僅 ddpeak×晚碰層可用。
- ⚠ 尚未對撞完整 SatZone（Phase 2）。

**裁決（2026-06-10，使用者）：B 再接 A** — 先改寫主軸為「碰觸時點為主、ext_long 為晚碰修正」（proposal.md 已改寫），再進 Phase 2。
- [x] 修改假設主軸（已改寫 proposal.md / tasks.md Phase 2）
- [x] 繼續 Phase 2（時點主規則 + 晚碰 ext_long 修正 vs SatZone-only / 固定出場基準）
- [ ] Archive

## Derived Hypotheses
- **H114-d1**：碰觸時點 × 關卡 的續攻地圖本身就是可用出場/加碼框架（ext_long 之外的獨立主訊號）——可能值得單獨立案，因它幾乎機械、最穩。
- **H114-d2**：「晚碰 + 延伸力未滾頭(ddpeak 低)」是否定位出一類「午盤二次發動」的續攻日？值得看 K 線型態。
- **觀察**：ext_long 的可用形式是 **roll-over（自峰回落）**，非絕對水平——與 H111 的 level-OOS-崩一致，延伸力訊號的價值在「動向/衰竭」不在「高低」。
</content>
