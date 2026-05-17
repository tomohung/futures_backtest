# Tasks: NVF Reach Multiples & Direction Asymmetry

## Phase 1: Distribution Research

### Data prep
- [x] 從 `ohlcv_1m` 取出每日 day_session 的 `day_open`(08:45 1m open)、`day_high`、`day_low`
- [x] 計算 `up_dist = day_high - day_open`、`dn_dist = day_open - day_low`
- [x] 計算 `EmaHL`(EMA20 of day_session HL, shift 1)— 與 `estimate_hl_exit.py` 一致
- [x] 計算 `night_range`(15:00 ~ 隔日 05:00)
- [x] 計算 NVF norm:**EMA20 + expanding median** 方法,與 `key_prices.py:_compute_night_vol_filter` 一致;warmup < 60 nights → fallback 0.93

### Analysis A:0.75 中段補完
- [x] 5 個 NVF 桶 × 4 個 multiple(0.618 / 0.75 / 1.0 / 1.2)× {upper / lower / either} 的 reach rate 表
- [x] 5 個 NVF 桶 × 4 個 multiple 的 reach `either` rate 與 H070 結果對照(SMA vs EMA 方法差異:Δ ≤ 3.4pp,結構不變)
- [x] 視覺化:reach rate vs multiple 折線圖(每桶一條線)

### Analysis B:方向不對稱
- [x] 每桶 reach_upper_X − reach_lower_X 差距矩陣(5 × 4)
- [x] STOP 桶(norm < threshold)逐年(2021-2026)的 upper / lower / 差距
- [x] Pass/Fail:任一 multiple 跨年方向一致 ≥ 4/6 且差距 ≥ 10pp 標記為「方向 bias 顯著」 → **FAIL**(pooled magnitude < 3pp)
- [x] 視覺化:STOP 桶逐年 upper vs lower 雙 bar 圖

### Sanity checks
- [x] 樣本總數應 ≥ 1,200(對應 H070 的 1,226)→ 1,264 ✅
- [x] 全樣本 reach_either ≥ 1.0× 應與 H070 一致或接近(若差距大需檢查 NVF 升級的影響)→ Δ ≤ 3.4pp ✅
- [x] `up_dist + dn_dist >= day_hl` 應恆成立(sanity)→ True ✅

---

### GATE

**問題 1 (H1: 0.75 中段)**:0.75 reach 在 STOP 桶與相鄰 multiple 是否提供額外資訊?
- 0.75 reach 與 0.618 reach 差距 ≥ 5pp → 0.75 為有資訊量的補完格
- 0.75 reach 與 1.0 reach 差距 ≥ 5pp → 同上(避免兩邊皆貼齊)

**問題 2 (H2: 方向 bias)**:STOP 天的 upper / lower 觸及率是否不對稱?
- ≥ 1 個 multiple,STOP 桶 `|reach_upper − reach_lower| ≥ 10pp`
- 上述差距方向跨年至少 4/6 一致

**決定**:

- [ ] 若 H1 + H2 皆通過 → 進入 Phase 2(探索方向 bias 的策略應用,例如 STOP 天 long-only / short-only bypass)
- [ ] 若僅 H1 通過 → Archive(完善的描述性貢獻,直接更新 H070 結果文檔)
- [ ] 若僅 H2 通過 → 進入 Phase 2(方向 bias 是新的可操作維度)
- [ ] 若兩者皆 fail → Archive rejected(H070 現有結論已足夠)

---

## Phase 2: Market Structure Study(redirected from strategy-filter,per user 2026-05-15)

**研究方向轉向**:不綁定 S001,改為描述夜盤波動 → 日盤方向 / 波動 / 形態的市場結構關係。

- [x] A. Day signed return distribution by NVF tier(4 tier, cutoff 0.8/1.0/1.2)
- [x] B. Day HL / EmaHL volatility distribution
- [x] C. Day high / low formation timing
- [x] D. Day path shape composition (up-trending / down-trending / L-then-H / H-then-L)
- [x] E. Average intraday trajectory per tier
- [x] Yearly cross-stability(signed_ret mean + median per tier)

**Verdict: Confirmed(描述性)**
- Strong-GO 的 Phase 1 lower bias 實為 tail risk(std 1.5×、p10 −1.12%),不是方向偏空
- Mid-GO 是唯一持續方向偏多的 tier
- NVF tier 對波動量 / 左尾風險有強解釋力,對形態/極值時點無顯著影響
