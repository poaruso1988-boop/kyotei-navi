#!/usr/bin/env python3
"""確定済みレースで モデルの K(能力スコアの効き) と γ(3連単分布のシャープ化) を対数尤度で確認する。
usage: python3 calibrate.py 20261018 [20261017 ...]"""
import sys, os, json, glob, math, itertools
import model
ROOT = os.path.dirname(os.path.abspath(__file__))

def races(hds):
    for hd in hds:
        d = os.path.join(ROOT, "cache", "json", hd)
        vj = json.load(open(os.path.join(d, "_all.json" if os.path.exists(os.path.join(d, "_all.json")) else "_venues.json"), encoding="utf-8"))
        for v in vj["venues"]:
            cs = {str(k): x for k, x in ((v.get("stadium") or {}).get("course") or {}).items()}
            for f in glob.glob(os.path.join(d, f"{v['jcd']}_*.json")):
                r = json.load(open(f, encoding="utf-8"))
                res = r.get("result")
                if r.get("boats") and len(r["boats"]) == 6 and res and res.get("payout", {}).get("3連単") and cs:
                    yield r, cs, res["payout"]["3連単"]["combo"], res["order"][0]["waku"]

def sharpen(c, g):
    z = sum(p ** g for p in c.values()); return {k: p ** g / z for k, p in c.items()}

def main(hds):
    R = list(races(hds)); print(f"確定レース {len(R)}件")
    base = model.K
    for K in (0.6, 0.8, 1.0, 1.2, 1.5, 2.0):
        model.K = K
        ll3 = ll1 = 0
        for r, cs, t3, w in R:
            rows, c, _, _ = model.score_boats(r, cs)
            ll3 += math.log(c[t3]); ll1 += math.log(next(x["p_win"] for x in rows if x["waku"] == w))
        print(f"K={K:.1f}: 3連単 平均logL={ll3/len(R):.3f}  1着 平均logL={ll1/len(R):.3f}")
    model.K = base
    for g in (1.0, 1.2, 1.4, 1.6):
        ll = 0
        for r, cs, t3, w in R:
            _, c, _, _ = model.score_boats(r, cs); ll += math.log(sharpen(c, g)[t3])
        print(f"γ={g}: 3連単 平均logL={ll/len(R):.3f}")
    # 市場(最終オッズ)の対数尤度 (控除率込みの暗黙確率を正規化)
    ll = n = 0
    for r, cs, t3, w in R:
        o = ((r.get("odds3t") or {}).get("odds")) or {}
        if o.get(t3):
            z = sum(1 / x for x in o.values() if x); ll += math.log((1 / o[t3]) / z); n += 1
    if n: print(f"参考: 市場オッズ暗黙確率 3連単 平均logL={ll/n:.3f} (n={n})  一様分布={math.log(1/120):.3f}")

if __name__ == "__main__":
    main(sys.argv[1:] or ["20261018"])
