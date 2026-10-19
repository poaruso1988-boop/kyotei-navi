"""透明なスコアリングモデル (参考値。的中を保証するものではありません)。

勝率推定:  P(1着=i) ∝ コース別1着率(場別データ, 進入=スタート展示の並び or 枠なり) × exp(K × 能力スコア_i)
能力スコア = レース内平均との差を固定スケールで加点/減点した合計(下の WEIGHTS)。
3連単: P(a-b-c) = P1(a) × Q2(b)/ΣQ2(≠a) × Q3(c)/ΣQ3(≠a,b)  (Q2,Q3 はコース別2着率/3着率 × exp(K×スコア))
"""
import math, itertools

K = 0.8   # calibrate.py で 2026-10-18 確定53R の対数尤度が最良だった値
BLEND_W = 0.3  # 妙味判定用: 補正確率 ∝ モデル確率^0.3 × 市場暗黙確率^0.7 (同53Rで市場単独より僅かに良好)
WEIGHTS = {  # 項目: (重み, 単位)  単位あたりのスコア
    "nat_win":  (0.55, "全国勝率 +1.00 ごと"),
    "loc_win":  (0.15, "当地勝率 +1.00 ごと(当地出走歴ありのみ)"),
    "avg_st":   (0.10, "平均ST 0.02秒速いごと"),
    "motor_2r": (0.20, "モーター2連率 +10% ごと"),
    "boat_2r":  (0.05, "ボート2連率 +10% ごと"),
    "ex_time":  (0.12, "展示タイム レース平均より0.05秒速いごと(±0.10秒で頭打ち, 展示発表後のみ)"),
    "ex_rank":  (0.08, "展示タイム順位 1位+0.08 / 2位+0.04 / 5位-0.04 / 6位-0.08 (展示発表後のみ)"),
    "class":    (1.00, "級別 A1 +0.25 / A2 +0.10 / B1 0 / B2 -0.25"),
    "F":        (1.00, "F1 -0.15 / F2以上 -0.35 (スタート慎重化)"),
    "comment":  (0.10, "選手コメント足色 1ポイントごと(±2で頭打ち, 直前1.0+前日0.6, コース別に観点を重み付け)"),
}
# 足色の観点重み (進入コース別): インは出足・回り足、アウトは伸び・行き足を重視
ASPECT_W = {"in": {"出足": 1.2, "回り足": 1.2, "行き足": 0.8, "伸び": 0.6, "総合": 1.0},
            "mid": {"出足": 1.0, "回り足": 1.0, "行き足": 1.0, "伸び": 1.0, "総合": 1.0},
            "out": {"出足": 0.8, "回り足": 0.8, "行き足": 1.2, "伸び": 1.2, "総合": 1.0}}

def comment_feel(cm, course):
    """cm = {"chokuzen": eval, "zenjitsu": eval}  → コース重み付き足色ポイント"""
    if not cm: return None
    w = ASPECT_W["in" if course <= 2 else "mid" if course <= 4 else "out"]
    tot = 0.0; used = False
    for key, k in (("chokuzen", 1.0), ("zenjitsu", 0.6)):
        ev = (cm.get(key) or {}).get("eval")
        if ev and ev.get("aspects"):
            used = True; tot += k * sum(w.get(a, 1.0) * v for a, v in ev["aspects"].items())
    return max(-2.0, min(2.0, tot)) if used else None
EX_RANK_PTS = {1: 1.0, 2: 0.5, 3: 0.0, 4: 0.0, 5: -0.5, 6: -1.0}
CLASS_PTS = {"A1": 0.25, "A2": 0.10, "B1": 0.0, "B2": -0.25}
GRADE_ORDER = {"A1": 0, "A2": 1, "B1": 2, "B2": 3}

def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None

def course_map(race):
    """枠→進入コース。スタート展示の並びがあればそれを採用(本番と異なる場合あり)。"""
    se = (race.get("before") or {}).get("start_exhibition") or []
    if len(se) == 6 and sorted(x["waku"] for x in se) == [1, 2, 3, 4, 5, 6]:
        return {x["waku"]: x["course"] for x in se}, "スタート展示"
    return {w: w for w in range(1, 7)}, "枠なり想定"

def score_boats(race, course_stats):
    boats = race["boats"]; bi = (race.get("before") or {}).get("boats") or {}
    bi = {int(k): v for k, v in bi.items()}
    ex = {b["waku"]: (bi.get(b["waku"]) or {}).get("ex_time") for b in boats}
    if sum(1 for x in ex.values() if x) < 4: ex = {}  # 展示タイムが4艇以上揃った時だけ反映(未発表/欠測時は従来どおり)
    exrank = {}
    if ex:
        for i, (w, t) in enumerate(sorted([(w, t) for w, t in ex.items() if t], key=lambda x: x[1])):
            exrank[w] = 1 + sum(1 for t2 in ex.values() if t2 and t2 < t)  # 同タイムは同順位
    cm, entry_src = course_map(race)
    m = {k: _mean([b.get(k) for b in boats]) for k in ["nat_win", "motor_2r", "boat_2r", "avg_st"]}
    locs = [b["loc_win"] for b in boats if b.get("loc_win")]; m["loc_win"] = _mean(locs)
    m["ex_time"] = _mean(list(ex.values())) if ex else None
    mclass = _mean([CLASS_PTS.get(b["class"], 0) for b in boats])
    rows = []
    for b in boats:
        parts = {}
        def add(k, v):
            if v is not None: parts[k] = round(v, 3)
        if b.get("nat_win") is not None: add("nat_win", WEIGHTS["nat_win"][0] * (b["nat_win"] - m["nat_win"]))
        if b.get("loc_win") and m["loc_win"]: add("loc_win", WEIGHTS["loc_win"][0] * (b["loc_win"] - m["loc_win"]))
        if b.get("avg_st") and m["avg_st"]: add("avg_st", WEIGHTS["avg_st"][0] * (m["avg_st"] - b["avg_st"]) / 0.02)
        if b.get("motor_2r") is not None and m["motor_2r"] is not None: add("motor_2r", WEIGHTS["motor_2r"][0] * (b["motor_2r"] - m["motor_2r"]) / 10)
        if b.get("boat_2r") is not None and m["boat_2r"] is not None: add("boat_2r", WEIGHTS["boat_2r"][0] * (b["boat_2r"] - m["boat_2r"]) / 10)
        if ex and ex.get(b["waku"]) and m["ex_time"]:
            add("ex_time", WEIGHTS["ex_time"][0] * max(-2.0, min(2.0, (m["ex_time"] - ex[b["waku"]]) / 0.05)))
            rb = EX_RANK_PTS.get(exrank.get(b["waku"]), 0)
            if rb: add("ex_rank", WEIGHTS["ex_rank"][0] * rb)
        add("class", CLASS_PTS.get(b["class"], 0) - mclass)
        if b.get("F"): add("F", -0.15 if b["F"] == 1 else -0.35)
        fe = comment_feel((race.get("comments") or {}).get(b["waku"]) or (race.get("comments") or {}).get(str(b["waku"])), cm[b["waku"]])
        if fe: add("comment", WEIGHTS["comment"][0] * fe)
        s = sum(parts.values())
        c = cm[b["waku"]]; cs = course_stats.get(c) or course_stats.get(str(c))
        rows.append({"waku": b["waku"], "course": c, "score": round(s, 3), "parts": parts,
                     "r1": cs["r1"], "r2": cs["r2"], "r3": cs["r3"], "ex_time": ex.get(b["waku"]) if ex else None})
    # 展示タイム順位
    for r in rows:
        if r["waku"] in exrank: r["ex_rank"] = exrank[r["waku"]]
    w1 = {r["waku"]: max(r["r1"], 0.3) * math.exp(K * r["score"]) for r in rows}
    w2 = {r["waku"]: max(r["r2"], 0.3) * math.exp(K * r["score"]) for r in rows}
    w3 = {r["waku"]: max(r["r3"], 0.3) * math.exp(K * r["score"]) for r in rows}
    t1 = sum(w1.values())
    for r in rows: r["p_win"] = w1[r["waku"]] / t1
    combos = {}
    W = list(w1)
    for a, b, c in itertools.permutations(W, 3):
        p = (w1[a] / t1) * (w2[b] / sum(w2[j] for j in W if j != a)) * (w3[c] / sum(w3[j] for j in W if j not in (a, b)))
        combos[f"{a}-{b}-{c}"] = p
    z = sum(combos.values()); combos = {k: v / z for k, v in combos.items()}
    ex2 = {}
    for k, v in combos.items():
        a, b, _ = k.split("-"); ex2[f"{a}-{b}"] = ex2.get(f"{a}-{b}", 0) + v
    # 2着以内/3着以内確率
    for r in rows:
        w = str(r["waku"])
        r["p_top2"] = sum(v for k, v in combos.items() if w in k.split("-")[:2])
        r["p_top3"] = sum(v for k, v in combos.items() if w in k.split("-"))
    return rows, combos, ex2, entry_src

def ev(p, o): return round(p * o, 3) if (p is not None and o) else None

def blend(combos, odds, w=None, min_n=60):
    """モデル確率と市場オッズ暗黙確率の対数線形プール。オッズが無ければ None."""
    w = BLEND_W if w is None else w
    if not odds or sum(1 for x in odds.values() if x) < min_n: return None
    z = sum(1 / x for x in odds.values() if x)
    q = {k: (p ** w) * (((1 / odds[k]) / z) if odds.get(k) else 1e-4) ** (1 - w) for k, p in combos.items()}
    t = sum(q.values()); return {k: v / t for k, v in q.items()}

def recommend(race, rows, combos, ex2):
    o3 = ((race.get("odds3t") or {}).get("odds")) or {}
    o2 = ((race.get("odds2t") or {}).get("odds")) or {}
    b3 = blend(combos, o3)
    b2 = blend(ex2, o2, min_n=20)  # 2連単は2連単オッズ自身とブレンド(プール間の歪みを避ける)
    ranked = sorted(combos.items(), key=lambda kv: -kv[1])
    def item(k, p, odds, bl):
        pb = bl.get(k) if bl else None
        return {"combo": k, "prob": round(p, 4), "pb": round(pb, 4) if pb else None, "odds": odds.get(k), "ev": ev(pb, odds.get(k))}
    honmei = [item(k, p, o3, b3) for k, p in ranked[:3]]
    osae = [item(k, p, o3, b3) for k, p in ranked[3:6]]
    fav = max(rows, key=lambda r: r["p_win"])["waku"]
    used = {x["combo"] for x in honmei + osae}
    if b3:
        cands = [(k, p) for k, p in ranked if k not in used and o3.get(k) and o3[k] >= 30 and p >= 0.008]
        cands.sort(key=lambda kv: -(b3[kv[0]] * o3[kv[0]]))
        ana = [item(k, p, o3, b3) for k, p in cands[:3]]
        ana_basis = "30倍以上で補正期待値の高い順"
    else:
        cands = [(k, p) for k, p in ranked if k not in used and int(k[0]) != fav]
        ana = [item(k, p, o3, b3) for k, p in cands[:3]]
        ana_basis = "オッズ未取得: 本命艇以外が1着の推定上位"
    r2 = sorted(ex2.items(), key=lambda kv: -kv[1])
    nitan = [item(k, p, o2, b2 if o2 else None) for k, p in r2[:3]]
    values = []
    if b3:
        for k, p in combos.items():
            if o3.get(k) and b3[k] >= 0.01 and b3[k] * o3[k] >= 1.0: values.append(dict(item(k, p, o3, b3), bet="3連単"))
    if b2 and o2:
        for k, p in ex2.items():
            if o2.get(k) and b2[k] >= 0.03 and b2[k] * o2[k] >= 1.0: values.append(dict(item(k, p, o2, b2), bet="2連単"))
    values.sort(key=lambda x: -x["ev"])
    return {"honmei": honmei, "osae": osae, "ana": ana, "ana_basis": ana_basis, "nitan": nitan, "value": values[:6]}

def confidence(rows, race):
    ps = sorted((r["p_win"] for r in rows), reverse=True)
    w = ((race.get("before") or {}).get("weather")) or {}
    rough = (w.get("wind_mps") or 0) >= 5 or (w.get("wave_cm") or 0) >= 5
    if ps[0] >= 0.60 and not rough: label = "鉄板"
    elif ps[0] < 0.38 or (rough and ps[0] < 0.5): label = "荒れそう"
    else: label = "混戦"
    score = round(ps[0] - 0.5 * ps[1] + (-0.05 if rough else 0), 4)
    return label, score

def comment(race, rows, entry_src):
    B = {b["waku"]: b for b in race["boats"]}
    R = sorted(rows, key=lambda r: -r["p_win"])
    f = R[0]; fb = B[f["waku"]]
    rank = lambda key, rev=True: sorted([b for b in race["boats"] if b.get(key) is not None], key=lambda b: b[key], reverse=rev)
    good, tops = [], []
    mot = rank("motor_2r")
    if mot and mot[0]["waku"] == f["waku"]: tops.append(f"モーター2連率{fb['motor_2r']:.0f}%")
    elif fb.get("motor_2r") and fb["motor_2r"] >= 40: good.append(f"モーターも良好({fb['motor_2r']:.0f}%)")
    nw = rank("nat_win")
    if nw and nw[0]["waku"] == f["waku"]: tops.append(f"勝率{fb['nat_win']:.2f}")
    if tops: good.insert(0, "・".join(tops) + "がメンバー最上位")
    if f.get("ex_rank") == 1: good.append("展示タイム1位")
    sts = rank("avg_st", rev=False)
    if sts and sts[0]["waku"] == f["waku"] and fb["avg_st"]: good.append(f"平均ST{fb['avg_st']:.2f}は最速")
    c = f["course"]
    style = {1: "逃げ有力", 2: "差し有力", 3: "まくり・まくり差し狙い", 4: "カドから攻める", 5: "展開を突く", 6: "展開待ち"}[c]
    head = f"{f['waku']}号艇{fb['name'].replace(' ', '')}({fb['class']})"
    if c != f["waku"]: head += f"は{c}コース進入想定"
    s = head + ("で" + "、".join(good[:2]) if good else "") + "、" + style + f"（推定1着率{f['p_win']*100:.0f}%）。"
    one = next(r for r in rows if r["course"] == 1)
    if one["waku"] != f["waku"]:
        ob = B[one["waku"]]; why = []
        if ob["class"] in ("B1", "B2"): why.append(f"{ob['class']}級")
        if ob.get("F"): why.append(f"F{ob['F']}持ち")
        if ob.get("motor_2r") is not None and ob["motor_2r"] < 30: why.append("モーター低調")
        if ob.get("nat_win") and nw and ob["nat_win"] < nw[len(nw)//2]["nat_win"]: why.append("勝率見劣り")
        s += f"イン{one['waku']}号艇{ob['name'].replace(' ', '')}は" + ("・".join(why) if why else "相手関係") + "で信頼度やや低い。"
    s2 = R[1]; sb = B[s2["waku"]]
    s += f"相手筆頭は{s2['waku']}号艇{sb['name'].replace(' ', '')}。"
    cms = race.get("comments") or {}
    notes = []
    for r in sorted(rows, key=lambda r: -r["p_win"])[:4]:
        fe = (r.get("parts") or {}).get("comment")
        if fe is None or abs(fe) < 0.08: continue
        c = cms.get(r["waku"]) or cms.get(str(r["waku"])) or {}
        ev = (c.get("chokuzen") or {}).get("eval") or (c.get("zenjitsu") or {}).get("eval") or {}
        asp = sorted(ev.get("aspects", {}).items(), key=lambda kv: -abs(kv[1]))
        a = asp[0][0] if asp else "舟足"
        a = "舟足" if a == "総合" else a
        nm = B[r["waku"]]["name"].split(" ")[0]
        notes.append(f"{r['waku']}号艇{nm}は{a}{'に好感触' if fe > 0 else 'に不安'}")
    if notes: s += "選手コメントでは" + "、".join(notes[:2]) + "。"
    fl = [f"{b['waku']}号艇F{b['F']}" for b in race["boats"] if b.get("F")]
    if fl: s += "、".join(fl) + "持ちはスタート慎重か。"
    w = ((race.get("before") or {}).get("weather")) or {}
    if (w.get("wind_mps") or 0) >= 5: s += f"風{w['wind_mps']:.0f}mで波乱含み。"
    if (w.get("wave_cm") or 0) >= 5: s += f"波高{w['wave_cm']:.0f}cm、水面荒れに注意。"
    if entry_src == "枠なり想定": s += "(直前情報前のため枠なり進入・展示なしで算出)"
    return s

def pre_exhibition(race, course_stats):
    """展示(直前情報)が無かった場合の予想 = 展示前予想。展示反映後との比較表示用。"""
    r0 = dict(race); r0["before"] = None
    rows, combos, _, _ = score_boats(r0, course_stats)
    fav = max(rows, key=lambda r: r["p_win"])
    top = sorted(combos.items(), key=lambda kv: -kv[1])[:3]
    return {"fav": fav["waku"], "fav_p": round(fav["p_win"], 4), "honmei": [k for k, _ in top],
            "p_win": {r["waku"]: round(r["p_win"], 4) for r in rows}}

def analyze(race, course_stats):
    if not race.get("boats") or len(race["boats"]) != 6: return None
    rows, combos, ex2, entry_src = score_boats(race, course_stats)
    has_ex = any(r.get("ex_time") for r in rows) and any("ex_time" in r["parts"] for r in rows)
    rec = recommend(race, rows, combos, ex2)
    label, cscore = confidence(rows, race)
    return {"rows": rows, "rec": rec, "confidence": label, "conf_score": cscore, "entry_src": entry_src,
            "ana": ana_pick(race, rows, combos, course_stats),
            "comment": comment(race, rows, entry_src), "has_before": bool((race.get("before") or {}).get("available")),
            "has_odds": bool((race.get("odds3t") or {}).get("odds")),
            "has_ex": has_ex, "pre": pre_exhibition(race, course_stats) if has_ex else None}

def check_result(an, result):
    if not result or not an: return None
    pay = result.get("payout", {})
    t3 = pay.get("3連単", {}).get("combo"); t2 = pay.get("2連単", {}).get("combo")
    hits = []
    for grp, name in [("honmei", "本命"), ("osae", "押え"), ("ana", "穴")]:
        if t3 and any(x["combo"] == t3 for x in an["rec"][grp]): hits.append(f"3連単{name}的中")
    if t2 and any(x["combo"] == t2 for x in an["rec"]["nitan"]): hits.append("2連単的中")
    fav = max(an["rows"], key=lambda r: r["p_win"])["waku"]
    win = result["order"][0]["waku"] if result.get("order") else None
    return {"trifecta": t3, "trifecta_yen": pay.get("3連単", {}).get("yen"), "exacta": t2, "exacta_yen": pay.get("2連単", {}).get("yen"),
            "kimarite": result.get("kimarite"), "hits": hits, "fav_won": fav == win, "winner": win}

# ---------------- 穴狙い (荒れ度 + 中穴/大穴の買い目) ----------------
# 配当帯 (3連単オッズ基準): 中穴 = 20倍以上100倍未満 / 大穴 = 100倍以上 (2,000円〜/10,000円〜の配当)
ANA_TIERS = {"中穴": (20.0, 100.0), "大穴": (100.0, None)}
ANA_MIN_PB = {"中穴": 0.010, "大穴": 0.003}   # 補正確率がこれ未満の目は候補外(極端な目を除く)
ARE_THRESHOLD = 45                             # 荒れ度がこれ以上を「穴狙い候補」とする
ARE_RULES = [  # (表示名, 点数の説明) — areido() の実装と同じ内容
    ("イン(1コース)艇の推定1着率", "40%未満 +25 / 50%未満 +15 / 60%未満 +5"),
    ("イン艇の級別・F", "B級 +10 / F持ち +8"),
    ("外枠(3〜6コース)の有力艇", "推定1着率20%以上の艇がいれば +10"),
    ("上位拮抗", "推定1着率の1位と2位の差が10%未満 +10"),
    ("風・波", "風5m以上または波5cm以上 +10 / 風7m以上または波8cm以上 +15"),
    ("場の荒れやすさ", "場の1コース1着率 50%未満 +10 / 55%未満 +5 (最近3ヶ月)"),
    ("選手コメント", "イン艇が不安コメント +5 / 外枠艇に好気配コメント +5"),
    ("市場(オッズ)", "補正確率で3連単20倍以上が決まる確率 60%以上 +10 / 45%以上 +5"),
]

def tier_of(odds):
    for t, (lo, hi) in ANA_TIERS.items():
        if odds is not None and odds >= lo and (hi is None or odds < hi): return t
    return None

def areido(race, rows, cs):
    """荒れ度(0〜100)と理由。cs = 場のコース別成績 {"1": {"r1": ..}}"""
    pts, why = 0, []
    B = {b["waku"]: b for b in race["boats"]}
    R = sorted(rows, key=lambda r: -r["p_win"])
    one = next(r for r in rows if r["course"] == 1); ob = B[one["waku"]]
    p1 = one["p_win"]
    if p1 < 0.40: pts += 25; why.append(f"イン{one['waku']}号艇の推定1着率{p1*100:.0f}%と低い")
    elif p1 < 0.50: pts += 15; why.append(f"イン{one['waku']}号艇の推定1着率{p1*100:.0f}%で信頼度不足")
    elif p1 < 0.60: pts += 5; why.append(f"イン{one['waku']}号艇の推定1着率{p1*100:.0f}%")
    if ob["class"] in ("B1", "B2"): pts += 10; why.append(f"イン艇が{ob['class']}級")
    if ob.get("F"): pts += 8; why.append(f"イン艇F{ob['F']}持ち(スタート慎重)")
    outs = [r for r in rows if r["course"] >= 3 and r["p_win"] >= 0.20]
    if outs:
        o = max(outs, key=lambda r: r["p_win"]); pts += 10
        why.append(f"{o['course']}コース{o['waku']}号艇{B[o['waku']]['name'].split(' ')[0]}が推定1着率{o['p_win']*100:.0f}%と有力")
    if R[0]["p_win"] - R[1]["p_win"] < 0.10: pts += 10; why.append(f"上位拮抗({R[0]['waku']}号艇{R[0]['p_win']*100:.0f}%・{R[1]['waku']}号艇{R[1]['p_win']*100:.0f}%)")
    w = ((race.get("before") or {}).get("weather")) or {}
    wm, wv = w.get("wind_mps") or 0, w.get("wave_cm") or 0
    if wm >= 7 or wv >= 8: pts += 15; why.append(f"風{wm:.0f}m・波{wv:.0f}cmで水面荒れ")
    elif wm >= 5 or wv >= 5: pts += 10; why.append(f"風{wm:.0f}m・波{wv:.0f}cm")
    c1 = (cs.get("1") or cs.get(1) or {}).get("r1")
    if c1 is not None:
        if c1 < 50: pts += 10; why.append(f"イン1着率{c1:.0f}%の荒れやすい水面")
        elif c1 < 55: pts += 5; why.append(f"イン1着率{c1:.0f}%とやや低い水面")
    fe1 = (one.get("parts") or {}).get("comment")
    if fe1 is not None and fe1 <= -0.05: pts += 5; why.append("イン艇のコメントに不安")
    if any(r["course"] >= 3 and ((r.get("parts") or {}).get("comment") or 0) >= 0.08 for r in rows):
        pts += 5; why.append("外枠艇に好気配コメント")
    return pts, why

def ana_pick(race, rows, combos, cs):
    """荒れ度と、配当帯ごとの買い目(補正期待値順 上位3)。オッズ未取得なら買い目なし。"""
    pts, why = areido(race, rows, cs)
    o3 = ((race.get("odds3t") or {}).get("odds")) or {}
    b3 = blend(combos, o3)
    out = {"score": None, "reasons": why, "p_tier": {}, "tickets": {}, "has_odds": bool(b3)}
    if b3:
        for t in ANA_TIERS: out["p_tier"][t] = round(sum(p for k, p in b3.items() if tier_of(o3.get(k)) == t), 4)
        pr = out["p_tier"]["中穴"] + out["p_tier"]["大穴"]
        if pr >= 0.60: pts += 10; why.append(f"オッズ込みの推定で20倍以上の決着{pr*100:.0f}%")
        elif pr >= 0.45: pts += 5; why.append(f"オッズ込みの推定で20倍以上の決着{pr*100:.0f}%")
        for t in ANA_TIERS:
            c = [k for k in b3 if tier_of(o3.get(k)) == t and b3[k] >= ANA_MIN_PB[t]]
            c.sort(key=lambda k: -(b3[k] * o3[k]))
            out["tickets"][t] = [{"combo": k, "odds": o3[k], "pb": round(b3[k], 4), "prob": round(combos[k], 4), "ev": ev(b3[k], o3[k])} for k in c[:3]]
    out["score"] = min(100, pts)
    return out
