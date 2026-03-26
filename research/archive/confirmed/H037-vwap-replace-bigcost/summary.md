# Summary: VWAP 取代大戶成本

## ID
H037

## Status
Confirmed (2026-03-26)

## One-Line
大戶成本（volume-filtered VWAP）與全日 VWAP 差異極小（median 3 點），直接用 VWAP 取代，簡化計算。

## Key Evidence
- N=1,265 交易日，BigCost - VWAP 的 mean=0.0, median=0.0, std=6.1
- 93.1% 的日子差異 ≤ 10 點
- 差異/振幅比在各波動等級穩定（1.4%~1.8%），無系統性偏移
- 結算日與非結算日無差異

## Action Taken
- 移除所有 volume-filtered SQL（20MA volume filter CTE）
- `runner.py` 兩個 loader 改用簡單 VWAP SQL
- 欄位名 BigCostN → VWAPN，參數名 bigcost_days → vwap_days
- `key_prices.py` 移除大戶成本區塊，表格只顯示 VWAP
- 全部 Python 策略/回測/分析檔案已同步更新
- Pine Script 待後續更新
