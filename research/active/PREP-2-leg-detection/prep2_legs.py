"""
PREP-2 leg 偵測原語（ATR-正規化 ZigZag，錨在開盤 08:45）

用途：為 GA-04（等幅等時投射）、GA-05（第二腳失敗→反轉）、GA-06、GA-10 提供共用的「腿」定義。
定義（依使用者裁示）：
  θ = k × ATR(近10日日盤range均, shift 無 lookahead)；leg1 從開盤起。
  ZigZag：自開盤逐分鐘走，價格從擺動極值反轉 ≥ θ 即確認一個轉折(pivot)。
  pivots = [P0(開盤), P1, P2, ...] 交替方向；leg_i = P_{i-1}→P_i。
  「第二隻腳」= leg2 = P2→P3（與 leg1 同向的續勢腳）；回撤 = leg1→leg2 間的反向段(P1→P2)。

本檔同時可當 module（detect_legs）與 distribution 腳本跑。
"""
import numpy as np


def detect_legs(prices, theta):
    """ZigZag 轉折偵測。prices: 1D array（開盤起逐分鐘 close）。theta: 門檻(點)。
    回傳 pivots: list of (idx, price)，P0=開盤、交替方向。

    leg1 必須是「自開盤 ≥θ 的真實衝勢」：先確立方向（價格自開盤移動 ≥θ）才開始記轉折，
    避免把開盤 <θ 的微幅試探誤當第一隻腳。確立後每次反轉 ≥θ 記一個 pivot。"""
    n = len(prices)
    if n == 0:
        return []
    o = float(prices[0])
    pivots = [(0, o)]
    H = L = o; iH = iL = 0
    trend = 0  # 0 未確立 / +1 上升腳 / -1 下降腳
    for i in range(1, n):
        p = float(prices[i])
        if p > H:
            H, iH = p, i
        if p < L:
            L, iL = p, i
        if trend == 0:
            # 確立 leg1 方向：自開盤 ≥θ 的那一側先成立（同時達標取較大位移側）
            up_ok, dn_ok = (H - o) >= theta, (o - L) >= theta
            if up_ok and (not dn_ok or (H - o) >= (o - L)):
                trend = +1
            elif dn_ok:
                trend = -1
                H, iH = o, 0           # 下降腳：捨棄開盤後的上方雜訊高點
            if trend == +1:
                L, iL = o, 0           # 上升腳：捨棄開盤後的下方雜訊低點
        elif trend == +1 and (H - p) >= theta:
            pivots.append((iH, H)); trend = -1; L, iL = p, i
        elif trend == -1 and (p - L) >= theta:
            pivots.append((iL, L)); trend = +1; H, iH = p, i
    last = (iH, H) if trend == 1 else (iL, L) if trend == -1 else (iH, H)
    if last[0] != pivots[-1][0]:
        pivots.append((last[0], last[1]))
    return pivots


def legs_from_pivots(pivots):
    """轉成 legs: list of dict(i0,i1,p0,p1,dir,dp(點),dt(分))。"""
    legs = []
    for a, b in zip(pivots[:-1], pivots[1:]):
        dp = b[1] - a[1]
        legs.append(dict(i0=a[0], i1=b[0], p0=a[1], p1=b[1],
                         dir=int(np.sign(dp)), dp=dp, adp=abs(dp), dt=b[0] - a[0]))
    return legs


def find_two_legs(prices, atr, k=0.3, leg1_min=0.5, retr=(0.3, 0.9),
                  anchor="anywhere", all_matches=False):
    """語意『第二隻腳』偵測（valid two-leg measured-move 結構）。

    定義：leg1(衝勢, ≥leg1_min×ATR) → 回撤(P1→P2, 深度∈retr×leg1, 即真回撤非反轉) → leg2(同向續勢)。
    anchor='open'：只用開盤錨的第一隻腳當 leg1（震盪開盤日 leg1<leg1_min 自然不成立 → 此模式只在
                   開盤即驅動日觸發）。
    anchor='intraday'：跳過開盤錨那隻腳（leg1 從盤中起 i0>0），第一組符合者（純盤中型，與 open 不重疊）。
    anchor='anywhere'：掃所有 leg triple（含開盤），第一組符合者（= open ∪ intraday）。
    回傳 list of dict：P0..P3(idx,price)、leg1/retr/leg2 大小(×ATR)、retr_ratio、leg2_over_leg1、
                       success(leg2 是否突破 P1 = 成功腳 vs GA-05 失敗腳)。
    """
    theta = k * atr
    legs = legs_from_pivots(detect_legs(prices, theta))
    out = []
    if anchor == "open":
        starts = [0]
    elif anchor == "intraday":
        starts = range(1, max(1, len(legs) - 2))
    else:
        starts = range(max(0, len(legs) - 2))
    for j in starts:
        if j + 2 >= len(legs):
            break
        l1, rt, l2 = legs[j], legs[j + 1], legs[j + 2]
        if l1["adp"] < leg1_min * atr:
            continue
        r = rt["adp"] / l1["adp"]
        if not (retr[0] <= r <= retr[1]):
            continue
        success = (l2["p1"] > l1["p1"]) if l1["dir"] > 0 else (l2["p1"] < l1["p1"])
        out.append(dict(
            P0=(l1["i0"], l1["p0"]), P1=(l1["i1"], l1["p1"]),
            P2=(rt["i1"], rt["p1"]), P3=(l2["i1"], l2["p1"]),
            dir=l1["dir"], leg1=l1["adp"] / atr, retr=rt["adp"] / atr, leg2=l2["adp"] / atr,
            retr_ratio=r, leg2_over_leg1=l2["adp"] / l1["adp"], success=bool(success),
        ))
        if not all_matches:
            break
    return out


# ---------------------------------------------------------------- self-test
def _selftest():
    # 合成：上 100 → 回 40 → 上 80（兩腳一回撤），θ=30 應抓到 P0,P1(100),P2(60),P3(140)
    seq = list(np.linspace(0, 100, 21)) + list(np.linspace(100, 60, 9))[1:] + list(np.linspace(60, 140, 17))[1:]
    piv = detect_legs(np.array(seq), theta=30)
    pv = [round(p, 1) for _, p in piv]
    print("self-test pivots(price):", pv, "→ legs:", len(piv) - 1)
    assert pv[0] == 0.0 and 99 <= pv[1] <= 101 and 59 <= pv[2] <= 61 and pv[3] >= 139, "ZigZag 邏輯異常"
    # 噪音不應生腳：θ 大於擺動
    piv2 = detect_legs(np.array([0, 5, -5, 8, -3, 6, 0]), theta=30)
    assert len(piv2) - 1 <= 1, "噪音被誤判成腳"
    # find_two_legs：上100→回50→上80（回撤0.5、leg2突破P1）ATR=100,k=0.3→θ=30
    seq = (list(np.linspace(0, 100, 21)) + list(np.linspace(100, 50, 11))[1:]
           + list(np.linspace(50, 130, 17))[1:])
    tl = find_two_legs(np.array(seq), atr=100, k=0.3, leg1_min=0.5)
    assert len(tl) == 1 and tl[0]["success"] and abs(tl[0]["retr_ratio"] - 0.5) < 0.05, "two-leg 偵測異常"
    print("self-test ✅ (detect_legs + find_two_legs)")


if __name__ == "__main__":
    _selftest()
