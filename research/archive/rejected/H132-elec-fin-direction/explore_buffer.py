"""
H132 補充：使用者原始構造 —— 「比率站上均線且持續走高=Risk On；跌破均線下緩衝=Risk Off」。
比 H132 的 sign(r−SMA) 更選擇性（中間留白）。仍以逐年符號穩定性為主關卡（非僅池化 t）。

  RiskOn  = r > SMA_W  AND  r 持續走高(r_t > r_{t-L})
  RiskOff = r < SMA_W − buffer*std_W(r)
  其餘    = Neutral（不進場）

用法：uv run python research/active/H132-elec-fin-direction/explore_buffer.py
"""
from __future__ import annotations
from pathlib import Path
import duckdb, numpy as np, pandas as pd

HERE = Path(__file__).parent; RES = HERE / "results"
DB = HERE.parent.parent.parent / "data" / "futures.duckdb"

def z(x): x=np.asarray(x,float); return (x-np.nanmean(x))/np.nanstd(x)
def ols1(y,x):
    m=np.isfinite(y)&np.isfinite(x); y=y[m];x=x[m]
    X=np.column_stack([np.ones(len(y)),x]); b,*_=np.linalg.lstsq(X,y,rcond=None)
    r=y-X@b; se=np.sqrt(np.diag((r@r)/(len(y)-2)*np.linalg.inv(X.T@X))); return b[1],b[1]/se[1],len(y)

lines=[]
def out(s=""): print(s); lines.append(s)

def main():
    sec=pd.read_csv(RES/"sector_index.csv"); sec["trade_date"]=pd.to_datetime(sec["trade_date"])
    with duckdb.connect(str(DB),read_only=True) as c:
        tx=c.execute("select trade_date,close from taiex_day order by trade_date").df()
    tx["trade_date"]=pd.to_datetime(tx["trade_date"])
    df=sec.merge(tx,on="trade_date").sort_values("trade_date").reset_index(drop=True)
    df["r"]=np.log(df.tse23_close/df.tse28_close); df["year"]=df.trade_date.dt.year
    c_=df.close.values

    out("# H132 補充：使用者原始構造（站上均線+持續走高 / 跌破均線下緩衝）")
    W=20
    df["sma"]=df.r.rolling(W).mean(); df["std"]=df.r.rolling(W).std()
    for K in [5,10,20]:
        df[f"fwd{K}"]=(pd.Series(c_).shift(-K)/pd.Series(c_)-1).values*100

    # 掃 持續走高 lookback L 與 buffer 倍數，但用「逐年符號一致」當選擇準則（非池化 spread）
    out(f"\nMA 窗 W={W}。掃 L(持續走高回看) × buffer(下緩衝=buffer×std)。主視角 K=10。")
    for L in [3,5]:
        for buf in [0.0,0.5,1.0]:
            on = (df.r>df.sma) & (df.r > df.r.shift(L))      # 站上均線且持續走高
            off = (df.r < df.sma - buf*df["std"])             # 跌破均線下緩衝
            K=10; fwd=df[f"fwd{K}"].values
            idx=np.arange(len(df))
            # 池化 spread + t（非重疊）
            sig=np.where(on,1,np.where(off,-1,0)).astype(float)
            nz=(idx%K==0)&(sig!=0)&np.isfinite(fwd)
            up=fwd[nz][sig[nz]>0]; dn=fwd[nz][sig[nz]<0]
            sp=np.median(up)-np.median(dn) if len(up)and len(dn) else np.nan
            b,t,n=ols1(fwd[nz],sig[nz]) if nz.sum()>10 else (np.nan,np.nan,0)
            # 逐年符號一致
            yrs=[]
            for yr,g in df.groupby("year"):
                go=(g.r>g.sma)&(g.r>g.r.shift(L)); go2=(g.r<g.sma-buf*g["std"])
                fu=g[f"fwd{K}"][go].median(); fd=g[f"fwd{K}"][go2].median()
                if go.sum()>=5 and go2.sum()>=5 and np.isfinite(fu) and np.isfinite(fd):
                    yrs.append(fu-fd)
            pos=sum(1 for s in yrs if s>0)
            on_freq=on.mean()*100; off_freq=off.mean()*100
            out(f"  L={L} buf={buf}: RiskOn med={np.median(up):+.2f}% RiskOff med={np.median(dn):+.2f}% spread={sp:+.2f}% t={t:+.2f} (N={n}) | 逐年 {pos}/{len(yrs)} 為正 | 佔比 On {on_freq:.0f}%/Off {off_freq:.0f}%")

    # 詳細逐年表：選 L=5,buf=0.5
    out("\n" + "="*60)
    L,buf,K=5,0.5,10
    out(f"## 逐年明細（L={L}, buf={buf}, K={K}）")
    on=(df.r>df.sma)&(df.r>df.r.shift(L)); off=(df.r<df.sma-buf*df["std"])
    out(f"  {'年':>4} {'N_On':>5} {'N_Off':>6} {'med_On':>8} {'med_Off':>8} {'spread':>8}")
    npos=ntot=0
    for yr,g in df.groupby("year"):
        go=(g.r>g.sma)&(g.r>g.r.shift(L)); go2=(g.r<g.sma-buf*g["std"])
        fu=g[f"fwd{K}"][go].median(); fd=g[f"fwd{K}"][go2].median()
        if go.sum()>=5 and go2.sum()>=5 and np.isfinite(fu) and np.isfinite(fd):
            sp=fu-fd; ntot+=1; npos+= sp>0
            out(f"  {yr:>4} {int(go.sum()):>5} {int(go2.sum()):>6} {fu:>+8.2f} {fd:>+8.2f} {sp:>+8.2f}{'' if sp>0 else '  ←反號'}")
    out(f"  → spread>0：{npos}/{ntot} 年")

    (RES/"explore_buffer_output.txt").write_text("\n".join(lines),encoding="utf-8")
    print(f"[saved] {RES/'explore_buffer_output.txt'}")

if __name__=="__main__":
    main()
