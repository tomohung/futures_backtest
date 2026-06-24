# Proposal: L1-reset 同相位再進場（回 L1 線 reset → 重新碰 L2 → 拉回站回 5MA）

## ID
H130

## Derived From
H126-second-l2-pullback 的 distribution/backtest 階段 + 2026-06-24 盤面複盤。
H126 確認「跨相位的第 2 次同向 L2 拉回」有 edge，但發現它**抓不到 6/24 那種「強趨勢單一 leg 內、
回 L1 後再做一次 L2 拉回」的形態**（6/24 整段下殺中間反彈 < L2、未翻相位 → detect_day 一段一次只給 1 筆）。
H130 把「同相位內的 L1-reset 再進場」獨立出來測。

## Trading Intuition
2026-06-24 空方：第一次 L2 拉回放空（09:01）→ 價格**反彈回到 L1 線（46702）後又跌破**→ 重新碰 L2 線 →
拉回站回 5MA → **第二次放空（10:13）**→ 續攻到下方 L5。整段是**同一個下跌相位**（中間反彈僅 +426 < L2，
未翻相位），但在 L1 位置「重置並再做一次」L2 拉回。使用者實盤即抓此第二筆。

核心直覺：強趨勢中，價格 retrace 回 L1 線代表「修正到位、未轉勢」，在**同一關卡位置（固定 L1/L2 線）**
重新形成 L2 拉回 = 趨勢再確認，可同向再進場、續攻更遠（L3/L4/L5）。

## Hypothesis
在已確立的同向相位內（錨=該相位 zigzag 極值，L1/L2 為自錨固定的關卡線），當「**進場後 → 價格 retrace
回 L1 線（reset）→ 重新同向觸及 L2 線（再確立）→ 拉回 ≥pb_floor 後收盤站回 5MA**」時的**第 2 次（含以上）
同相位再進場**，其進場後續航（碰 L3/L4/L5 比率、賠率）顯著優於隨機/無條件基準，且為正 EV（真實停損+成本下）。

> 規則精確化（causal，已於 6/24 驗證重現 09:01 + 10:13 兩筆）：
> 狀態機（空方對稱多方）：相位確立(ext−anchor≥L2d)→`extend`→`pullback`(dip≥pb_floor)→收盤破5MA `進場`
> →`needL1`(待 high≥anchor−L1d 回 L1 線=reset)→`touchL2`(待 low≤anchor−L2d 重新碰 L2)→`extend`…循環。
> 相位由 ≥L2 反向 swing 結束（翻相位後不屬本假設，歸 H126）。

## Expected Distribution
- 多數強趨勢日會出現 ≥1 次 L1-reset 再進場；具此形態的日子是少數但可觀（待 Phase 1 給 N，多/空分計）。
- 第 2 次（L1-reset 後）進場碰 L3/L4/L5 比率不低於第 1 次（趨勢再確認），MFE 右偏。
- **虛無對照**（記憶 feedback_excursion_needs_forward_tautology_guard）：須對比「同為趨勢日的第 1 次」/
  時間配對 / 條件期望，確認「L1-reset 再進場」的續航不是純 selection（趨勢日本來就延伸）。
- entry_min 仍可能是強因子（H126/H127：≥11:30 死區），需分時段看。

## Invalidation Condition
任一成立即視為不支持：
1. 具 L1-reset 再進場的樣本數過少（< GATE 門檻），不足以下結論。
2. 第 2 次（L1-reset 後）續航/賠率相對第 1 次或時間配對基準**無顯著增益**，或增益在虛無對照後消失。
3. 真實停損+成本下 EV 不為正（碰更遠目標的機率被更深停損吃光）。
4. 規則只對 6/24 有效（少數幾天貢獻絕大多數 P&L、其餘日無 edge）= overfit 到單一觀察。

## Notes
- **與 H126 的界線**：H126=跨相位（中間有 ≥L2 反向 swing 翻相位）；H130=同相位內（中間反彈 <L2、僅 retrace
  到 L1）。兩者互斥，可在 Phase 1 一併統計「同向再進場」整體拆成這兩類各佔多少。
- **overfit 風險（首要警戒）**：規則的 L1-reset / L2-retouch 門檻是對 6/24 校出來的，Phase 1 必須全樣本看
  頻率與分佈、並做 leave-6/24-out 的穩健性檢查，避免單日驅動結論。
- **參數**：reset=high≥anchor−L1d（觸 L1 線）、re-arm=low≤anchor−L2d（觸 L2 線）、pb_floor=0.05×EMA20、
  5MA 站回；overshoot 上限 L5。這些先沿用 6/24 校準值，Phase 1 做敏感度。
- **記憶連結**：[[project_second_l2_pullback_signal]]（H126，母體/序數）、
  [[project_ladder_reach_timing_map]]（reach 時序）、[[project_oos_equals_highvol_regime]]（OOS confound）。
- 6/24 概念驗證腳本暫存 /tmp/h130_viz.py，Phase 1 正式化後移入本目錄 explore.py。
