"""
H136 衍生: 崩盤 regime 能否用「盤前可得的因果訊號」即時辨識？

目標 = 日盤全段報酬 (08:45 open -> 13:45 close)，因為「做多有利」是問持有多單的期望。
測幾個 100% 因果 (盤前可算) 的 regime 閘門，看能否把 2022/2025 崩盤段的負漂移隔離出來，
且在其他時間不誤殺長多頭。
"""
import duckdb, numpy as np, pandas as pd

DB = "data/futures.duckdb"
con = duckdb.connect(DB, read_only=True)
df = con.execute("""
    SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, open, close, adj_close
    FROM ohlcv_1m WHERE symbol='TX'
      AND CAST(timestamp AS TIME) BETWEEN '08:45' AND '13:45' ORDER BY timestamp
""").df()
con.close()
for c in ['open','close','adj_close']: df[c]=df[c].astype(float)
df['t']=df['t'].astype(str).str.slice(0,5)

# 日盤全段 open/close (raw) + 每日 adj close for MA
day = df.groupby('d').agg(
    day_open=('open','first'), day_close=('close','last'), adj_last=('adj_close','last')
).reset_index().sort_values('d').reset_index(drop=True)
day['o0845'] = df[df['t']=='08:45'].set_index('d')['open'].reindex(day['d']).values
# 08:45 adj open
adjrow = df[df['t']=='08:45'].copy(); adjrow['adjo']=adjrow['open']+(adjrow['adj_close']-adjrow['close'])
day['adjo'] = adjrow.set_index('d')['adjo'].reindex(day['d']).values

for n in [20,60,120,240]:
    day[f'ma{n}'] = day['adj_last'].rolling(n).mean().shift(1)
# MA60 斜率: 前一日 MA60 vs 20 交易日前的 MA60 (皆因果)
day['ma60_20ago'] = day['ma60'].shift(20)
day['ma60_up'] = day['ma60'] > day['ma60_20ago']

day['day_ret'] = day['day_close'] - day['day_open']
day['day_pct'] = day['day_ret'] / day['day_open'] * 100
day['year'] = pd.to_datetime(day['d']).dt.year
day['ym'] = pd.to_datetime(day['d']).dt.to_period('M').astype(str)
d = day.dropna(subset=['ma240','ma60_20ago']).reset_index(drop=True)
print(f"N={len(d)}  {d['d'].min()} ~ {d['d'].max()}")

def stat(mask, label):
    s = d[mask]
    n=len(s);
    if n==0:
        print(f"{label:32s} N=0"); return
    r=s['day_ret']; up=(r>0).mean()
    sharpe = s['day_pct'].mean()/s['day_pct'].std() if s['day_pct'].std()>0 else 0
    print(f"{label:32s} N={n:4d} ({n/len(d)*100:4.0f}%)  漲%={up*100:4.0f}%  "
          f"meanRet={r.mean():+6.2f}pt  meanPct={s['day_pct'].mean():+.4f}%  日Sharpe={sharpe:+.3f}")

print("\n== 全段 baseline vs 因果 regime 閘門 (日盤全段做多的期望) ==")
stat(pd.Series(True,index=d.index), "全體 (天然做多)")
stat(d.adjo> d.ma60,  "open > MA60")
stat(d.adjo<=d.ma60,  "open < MA60  [關做多?]")
stat(d.adjo> d.ma120, "open > MA120")
stat(d.adjo<=d.ma120, "open < MA120 [關做多?]")
stat(d.ma60_up,               "MA60 斜率向上")
stat(~d.ma60_up,              "MA60 斜率向下 [關做多?]")
stat(d.ma60_up & (d.adjo>d.ma60), "MA60向上 且 open>MA60  [做多開]")
stat(~(d.ma60_up & (d.adjo>d.ma60)), "其餘 [降強度]")

print("\n== 逐年: 「MA60向上且open>MA60」做多 vs 全體 ==")
for yr in sorted(d.year.unique()):
    ys=d[d.year==yr]
    on = ys[ys.ma60_up & (ys.adjo>ys.ma60)]
    off= ys[~(ys.ma60_up & (ys.adjo>ys.ma60))]
    print(f"  {yr}: 全體 mean={ys.day_ret.mean():+6.1f}(N={len(ys):3d}) | "
          f"閘開 mean={on.day_ret.mean():+6.1f}(N={len(on):3d}) | "
          f"閘關 mean={off.day_ret.mean():+6.1f}(N={len(off):3d})")

print("\n== 崩盤段閘門是否亮燈? (閘關=結構弱, 逐月覆蓋率) ==")
d['gate_off'] = ~(d.ma60_up & (d.adjo>d.ma60))
for period,lo,hi in [("2022熊","2022-01","2022-10"),("2025關稅","2025-03","2025-06"),("2023多頭","2023-01","2023-12"),("2024多頭","2024-01","2024-12")]:
    seg=d[(d.ym>=lo)&(d.ym<=hi)]
    print(f"  {period:10s} {lo}~{hi}: 閘關覆蓋率={seg.gate_off.mean()*100:4.0f}%  段內做多 meanRet={seg.day_ret.mean():+6.1f}pt (N={len(seg)})")
