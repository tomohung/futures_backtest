# Tasks: 日盤結構閘做多加權

## Phase 1: Distribution Research  ✅（沿用 H136 regime_detect.py → explore.py）

- [x] 因果結構閘定義（開盤>MA60 且 MA60斜率向上）
- [x] 閘開/閘關日盤全段做多期望（+8.65 / −7.42 pt/天）
- [x] 逐年方向一致性（2022/2024/2025 閘關為負，2023 例外）
- [x] 崩盤段覆蓋率（2022=89%、2025=100%、多頭年 26–34%）

### GATE ✅ 通過（使用者核准進 Phase 2）
- 樣本足夠（N=1092，閘開 653 / 閘關 439）
- 逐年不翻號（優於 H136）
- 崩盤即時可辨識（因果）

---

## Phase 2: Backtest

- [ ] 逐日向量化回測：閘開日 long 08:45→13:45，vs 無條件做多、vs 買進持有  ✅
- [ ] 指標：總點數、mean/天、勝率、年化 Sharpe(%)、maxDD（equity 點數）  ✅
- [ ] IS（2021-12~2023-12）/ OOS（2024-01~2026-07）分割，兩段各含一次崩盤  ✅
- [ ] 逐年 breakdown  ✅
- [ ] 參數敏感度：MA∈{20,60,120} × slope窗∈{10,20,40}  ✅
- [ ] 成本敏感度：round-trip 0/1/2/3 點  ✅
- [ ] 崩盤剝離檢定：扣掉 2022 + 2025 崩盤段後，平時閘開vs閘關是否仍有區辨（invalidation #5）  ✅
- [ ] Verdict：Confirmed / Rejected / Inconclusive
