# Distribution Research Results: 同 leg 多次拉回進場（淺拉回不燒名額）

## Date
2026-06-16

## ⚠️ 框架前提
H120/S005 因前視偏誤作廢，chart-ui `h120.py` 的 leg-bounded `detect_day` 僅作行情參考。**本探索一律用完全 causal streaming 偵測**（基準＝`validate_causal.py` 的 `detect_causal`，相位 = [翻上事件, 下一翻下事件)，不碰未來 em）。腳本：`explore.py`。

## Conditions Tested
TX 日盤全窗，三個 causal 變體（detection 內深度判定差異，其餘 EMA20/5MA/overshoot/L3 guard/出場 alpha=0.75/cost=3pt 全相同，進場 <12:00，depth≥0.25）：
- **A** baseline：第一站回(任意深)→done，事後濾 depth≥0.25（淺站回燒掉相位）
- **B** 淺不燒名額：淺站回 reset 續找同相位下一站回，第一個 depth≥0.25 才 done（每相位仍最多一筆）
- **C** 同相位全取：所有 depth≥0.25 站回都進（可多筆）

## Sample
- 時間範圍：全窗（IS < 2025-01-01，OOS ≥ 2025-01-01）
- A=1262 筆、B=1566 筆、C=4997 筆
- B 相對 A 多出（extra）N=304，分布 293 天（高度分散，非集中單日）

## Key Findings

### 整體（ALL）
| 變體 | N | win% | tot% | Sharpe | avgR | maxLoss | mdd% |
|---|---|---|---|---|---|---|---|
| A baseline | 1262 | 62.2 | **16.9** | **0.041** | 0.02 | 6 | −9.0 |
| B 淺不燒名額 | 1566 | 61.8 | 12.5 | 0.025 | 0.01 | 6 | −10.3 |
| C 全取 | 4997 | 57.6 | 11.4 | 0.007 | −0.01 | 20 | −62.5 |

OOS 同向：A tot 16.1%/Sharpe 0.12 ＞ B 11.4%/0.07 ＞ C 15.9%/0.034（但 C maxLoss 16、mdd −17.9%）。

### 關鍵：B「多出來」的單是 -EV（決定性）
B 是 A 的嚴格超集（B = A 的 1262 筆 + 304 筆 rescued）：
- **B extra（N=304）：win 60.2%、EV −3.6pt、tot −4.4%、avgR −0.03、Sharpe −0.05**
- 與 A 重疊 1262 筆：win 62.2%、EV +4.4pt、avgR 0.02

→ 把淺站回後「同相位後續拉回」救回來的那批單，**平均虧錢**，直接把總報酬 16.9%→12.5%、Sharpe 0.041→0.025 拖下去。C 更慘（extra avgR −0.02、maxLoss 22、mdd −54.8%）。

### 2026-06-11 動機案例的真相
causal 下 A 該日就有 3 筆且**全贏**（08:58 多 +112、09:43 空 +339、10:45 多 +196），depth 都 ≥0.25——**「9:11 漏單」根本不存在於 causal A**，那是 leg-bounded 圖層特定 anchoring 造成的視覺假象。C 在該日多抓 09:08(depth0.79,+272) 等 5 筆也都贏，但這正是 data-snooping 陷阱：單一好日子。全窗一攤開，rescued 筆是淨虧。

## Vs. Expected
- 預期「rescued 筆 avgR ≥ baseline」→ **不符**（avgR −0.03 < baseline 0.02，且為負）。
- 預期「整體 PF/期望 R 提升」→ **不符**（B 全面劣於 A）。
- 樣本充足（extra N=304 ≥ 30）、跨 293 天非單日 → 結論不是樣本不足或 snooping，是真的沒 edge。

## Gate Decision
[x] **Archive（Reject）**
[ ] 進入 Phase 2
[ ] 修改假設

**理由**：命中 proposal 三條無效條件中的兩條——B extra avgR ≤ 0（−0.03）、整體 PF/期望 R 未優於 A（全面更差）。baseline「第一個站回燒掉相位」的設計在 causal 下是對的：同相位後續拉回的續攻品質較差，救回來只是加爛單。動機案例（9:11）是非 causal 圖層假象 + 單日倖存者偏誤雙重產物。

## Derived Hypotheses
- （無強訊號）C 全取在 OOS tot 為正但 maxLoss/mdd 爆炸，屬高波 regime confound（memory `oos_equals_highvol_regime`），不值得單獨開假設。
- 附帶觀察：causal A 本身 IS Sharpe 僅 0.003、avgR −0.01，僅 OOS（高波）轉正——再次佐證 H120 母假設 causal 後接近 break-even，非 H124 範疇。
