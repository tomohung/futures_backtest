# Proposal: EstHL Tue NVF Bypass Patch

## ID
H078

## Derived From
- H072（confirmed, 2026-04-21）：cell matrix 確認 EstHL × Tue × NVF 是 OOS 嚴重 drift cell（Δ -1.24）
- H075（confirmed, 2026-04-21）：升級 NVF 為 EMA + expanding median 後，多數 cell 修復，**但 EstHL Tue 仍失效**（Δ -1.22，幾乎無變化）

H072+H075 雙重證實 EstHL × Tue × NVF 是結構性問題，不是方法 artifact。需要在 production 加入 weekday-aware bypass。

## Trading Intuition
EstHL Tue baseline（不過濾）OOS PF 2.14、勝率 54%——這是健康可獲利的交易日。但套上 NVF 後 PF 掉到 0.90，連敗也加深。Exhaustion control 在同 OOS 期間 Tue NVF Δ 反而 +1.04（方向相反），確認這是 EstHL 策略特性問題。

可能的根因（未必要在本研究解決，但是動機）：
- 大夜盤波動代表美股或國際事件，週二日盤可能延續夜盤趨勢方向 → EstHL 的 ORB 多頭突破在這種「延續趨勢」下勝率反而降低
- 週二的高波動環境讓 EstRange SL 設定偏差最大（EmaHL 過大導致 SL 設太遠 / SatZone 距離過寬）
- 國際事件主導的週二日盤難用 EstHL 的「平靜開盤後突破」邏輯預測

但本研究**不深入根因**，只做 actionable patch：在 EstHL 對週二進場時 bypass NVF。

## Hypothesis
**對 EstHL 在週二進場時 bypass NVF（即週二 ALL trades 不論夜盤波動皆可進），可改善 EstHL OOS PF / 連敗 / 整體報酬，且不傷其他交易日。**

具體預測：
- EstHL Tue OOS PF 從 NVF-filtered 0.90 → bypass 2.14（接近 baseline）
- 全策略 OOS 總 PF 提升（Tue 多收回的利潤 > Tue NVF 過濾掉的虧損）
- max consecutive losses 不增加 ≥ 2 筆（一致於 H075 的標準）
- Walk-forward IS/OOS 一致改善

## Expected Distribution
Phase 1 預期：
- 用新 NVF 方法（EMA + expanding median）重做 Tue baseline vs Tue NVF cell：每年 baseline 都 ≥ NVF（至少 5/6 年）
- 全策略 OOS 加上 bypass 後，aggregate PF 改善
- 連敗 max length 不變或改善

## Invalidation Condition
- Tue NVF-filtered PF 在 walk-forward ≥ 4/6 年 ≥ Tue baseline → 撤回 patch（NVF 對 Tue 其實有效，只是 aggregate 數字誤導）
- bypass 後全策略 max consecutive losses 增加 ≥ 2 → 否決（連敗保護優先）
- bypass 後 OOS aggregate PF 反而下降 → 否決（H072 cell 結論可能 spurious）

## Notes

### 範圍
- 只處理 EstHL（Reversal Tue 在新 NVF 下表現更好，無需動）
- 只 bypass NVF；其他濾網（VWAP、30m MA、OR%、skip Thu/Fri）維持

### 實作位置
**僅修改 `src/analysis/key_prices.py`** 的策略進場建議顯示邏輯：
- S001 EstHL 區塊加入：若 today_wd == 1（Tue）→ 顯示「✅ 可做（Tue NVF bypass）」，不論 nvf_pass
- 其他 weekday 維持現有邏輯

不動策略碼（`src/strategies/orb_est_hl_exit.py`）——保持「策略邏輯」與「外部 gate」的分離。實盤決策來自 morning_briefing 顯示。

### Phase 1 任務
1. 用新 NVF 方法（EMA + expanding median）重做 EstHL Tue cell：年度逐筆比較 baseline vs NVF-filtered
2. 確認 Tue bypass 後的 walk-forward 一致性
3. 連敗結構對比（baseline Tue + NVF 其他天 vs 全 NVF）

### Phase 2 任務
1. 修改 `key_prices.py` morning_briefing 顯示
2. 加 unit test（週二的判定行為）
3. 端對端 smoke test
4. 回測完整 EstHL with Tue bypass 對比 with full NVF
5. 更新 S001 spec.md

### 與 H075 的關係
H075 已修復多數 cells；H078 是 H075 留下的最後一個 sub-cell patch。完成後 H075 + H078 共同構成「NVF 完整實裝」。
