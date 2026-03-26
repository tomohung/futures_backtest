# Archive: Reversal BB Touch + Intraday Level Retest Confluence

## Status
Rejected

## Summary
驗證 BB touch 發生時，如果該價位附近已在當天被多次測試（形成 consolidation range 邊界），
反轉品質是否更好。兩個版本的測試都顯示 confluence 對 BB touch 品質沒有區辨力。

## Key Evidence
- **v1（歷史 30 日 S/R）**：N=2,341，所有閾值下兩組勝率差 < 2%，方向不一致
- **v2（盤中 level retest）**：N=2,341，retest 組勝率 50.8% vs 無 retest 52.0%（反向 -1.2%）
  - 所有 tolerance (±10/20/30pt) × threshold (>=2/3/5) 組合方向一致地反向或持平
  - Retest 組 MFE 更低（54pt vs 74pt），可能因為 BB 在盤整環境中被壓縮
  - Retest 次數與成功率無單調關係

## Why Rejected
1. BB touch + vol_ok 本身已是有效濾網，額外的 price level confluence 不提供增量資訊
2. v1：歷史 S/R 密度太高（66% 的 BB touch 天然在 0.5 EmaHL 內有 S/R），分組無區辨力
3. v2：多次 retest 反映低波動盤整，BB extreme 在此環境下反轉力道更小（非更大）

## Derived Hypotheses
- HXXX-reversal-bypass-audit：回顧 Reversal 策略現有 4 種 CCD bypass 條件的邊際貢獻
- HXXX-sr-exit-enhancement：structural S/R 可能不影響進場品質，但可能影響 exit 目標

## Links
- Proposal：proposal.md
- Distribution v1（歷史 S/R）：results/distribution_v1.md
- Explore v1 script：explore.py
- Explore v2 script：explore_v2.py
