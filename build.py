#!/usr/bin/env python3
"""cache/json/YYYYMMDD/ の取得データ + メディア情報 + モデル → site/data/YYYYMMDD.json を生成。
usage: python3 build.py [YYYYMMDD]"""
import os, sys, json, glob, datetime as dt
import model
ROOT = os.path.dirname(os.path.abspath(__file__))
JST = dt.timezone(dt.timedelta(hours=9))
BASE = "https://www.boatrace.jp/owpc/pc/race"

def load(p, default=None):
    try: return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError): return default

def main(hd):
    d = os.path.join(ROOT, "cache", "json", hd)
    allj = load(os.path.join(d, "_all.json")) or load(os.path.join(d, "_venues.json"))
    if not allj: sys.exit(f"no fetched data for {hd}; run fetch.py {hd}")
    import comments as CM
    cmj = load(os.path.join(d, "_comments.json"), {"venues": {}, "not_covered": {}})
    use_cm = not os.environ.get("NO_COMMENTS")
    media = load(os.path.join(d, "_media.json"), {"venues": {}, "featured": [], "status": ["メディア情報未取得 (media.py 未実行)"]})
    now = dt.datetime.now(JST)
    # 全国平均(取得できた場の単純平均)を場別データが無い場合のフォールバックに
    stats = [v["stadium"]["course"] for v in allj["venues"] if v.get("stadium")]
    natl = {str(c): {k: round(sum(s[str(c)][k] if str(c) in s else s[c][k] for s in stats) / len(stats), 1) for k in ("r1", "r2", "r3")} for c in range(1, 7)} if stats else None
    out = {"hd": hd, "generated_at": now.isoformat(timespec="seconds"), "fetched_at": allj.get("fetched_at"),
           "disclaimer": "本ツールの予想・買い目は公開データに基づく機械的な推定(参考情報)であり、的中や利益を保証するものではありません。舟券の購入は自己責任で、20歳以上・余裕資金の範囲でお楽しみください。",
           "model": {"formula": model.__doc__.strip(), "weights": {k: v[1] + f" → {v[0]:+.2f}" if k not in ("class", "F") else v[1] for k, v in model.WEIGHTS.items()}, "K": model.K, "blend_w": model.BLEND_W, "comment_dict": {"aspects": CM.ASPECTS, "good": CM.GOOD, "mild_good": CM.MILD_GOOD, "bad": CM.BAD, "neutral": CM.NEUTRAL, "hope": CM.HOPE, "conditional": CM.COND}},
           "media_status": media.get("status", []), "venues": [], "national_course": natl}
    allraces = []
    for v in allj["venues"]:
        jcd = v["jcd"]
        cs = (v.get("stadium") or {}).get("course"); cs_src = "場別データ(最近3ヶ月, boatrace.jp)"
        if not cs: cs, cs_src = natl, f"開催{len(stats)}場の平均(場別データ取得失敗のため)"
        cs = {str(k): val for k, val in cs.items()}
        mv = media.get("venues", {}).get(jcd, {})
        fy = mv.get("free_yosou") or {}
        V = {"jcd": jcd, "name": v["name"], "title": v["title"], "grade": v["grade"], "kind": v.get("kind", ""), "period_day": v.get("period_day", ""),
             "status": v.get("status", ""), "course_stats": cs, "course_src": cs_src,
             "media": {"free_yosou_url": mv.get("free_yosou_url"), "free_yosou_title": fy.get("title"), "free_yosou_date_ok": fy.get("date_ok"),
                       "free_yosou_note": mv.get("free_yosou_note"), "outlook": fy.get("outlook"), "senmon_note": fy.get("senmon_note"),
                       "news": mv.get("news", []), "paid": mv.get("paid", [])},
             "races": [], "comment_status": comment_status(cmj, jcd)}
        files = sorted(glob.glob(os.path.join(d, f"{jcd}_*.json")))
        for f in files:
            r = load(f)
            if not r: continue
            q = f"rno={r['rno']}&jcd={jcd}&hd={hd}"
            R = {"rno": r["rno"], "deadline": r.get("deadline"), "race_title": r.get("race_title", ""), "distance": r.get("distance", ""),
                 "errors": r.get("errors", []),
                 "links": {"racelist": f"{BASE}/racelist?{q}", "beforeinfo": f"{BASE}/beforeinfo?{q}", "odds": f"{BASE}/odds3t?{q}", "result": f"{BASE}/raceresult?{q}", "pcexpect": f"{BASE}/pcexpect?{q}"}}
            if not r.get("boats"): R["status"] = "nodata"; V["races"].append(R); continue
            cv = cmj["venues"].get(jcd) or {}
            rc = (cv.get("races") or {}).get(str(r["rno"])) or {}
            cmts = {}
            for b in r["boats"]:
                x = rc.get(str(b["waku"])) or {}
                e = {}
                if x.get("chokuzen"): e["chokuzen"] = {"text": x["chokuzen"], "time": x.get("chokuzen_time", ""), "eval": CM.evaluate(x["chokuzen"])}
                if x.get("zenjitsu"): e["zenjitsu"] = {"text": x["zenjitsu"], "eval": CM.evaluate(x["zenjitsu"])}
                if not e and (cv.get("by_toban") or {}).get(b["toban"]):
                    e["zenjitsu"] = {"text": cv["by_toban"][b["toban"]], "eval": CM.evaluate(cv["by_toban"][b["toban"]])}
                if e: e["source"] = (cv.get("sources") or [cv.get("site")])[0]; cmts[b["waku"]] = e
            if use_cm and cmts: r["comments"] = cmts
            an = model.analyze(r, cs)
            bf = r.get("before") or {}
            bmap = {int(k): x for k, x in (bf.get("boats") or {}).items()}
            rows = {x["waku"]: x for x in an["rows"]} if an else {}
            boats = []
            for b in r["boats"]:
                x = dict(b); x.update({k: rows.get(b["waku"], {}).get(k) for k in ("course", "score", "parts", "p_win", "p_top2", "p_top3", "ex_rank", "r1")})
                x["before"] = bmap.get(b["waku"])
                ori = ((bf.get("original") or {}).get("boats") or {})
                x["original"] = ori.get(str(b["waku"])) or ori.get(b["waku"])
                x["comment"] = cmts.get(b["waku"])
                boats.append(x)
            R.update({"boats": boats, "weather": bf.get("weather"), "start_exhibition": bf.get("start_exhibition"), "before_available": bool(bf.get("available")),
                      "pc": {"focus": r.get("pc_focus", []), "marks": {b["waku"]: b.get("pc_mark") for b in r["boats"] if b.get("pc_mark")}},
                      "odds_updated": (r.get("odds3t") or {}).get("updated", ""),
                      "analysis": {k: an[k] for k in ("confidence", "conf_score", "comment", "rec", "entry_src", "has_before", "has_odds", "ana", "has_ex", "pre")} if an else None,
                      "ex_reflected": bool(an and an.get("has_ex")), "before_checked_at": r.get("before_checked_at"),
                      "original_src": (bf.get("original") or {}).get("source")})
            res = r.get("result")
            R["result"] = res
            R["check"] = model.check_result(an, res) if res else None
            dl = model_time(hd, r.get("deadline"))
            R["status"] = "finished" if res else ("closed" if dl and now > dl else "upcoming")
            # メディア(レース単位)
            mr = []
            fr = (fy.get("races") or {}).get(str(r["rno"]))
            if fr: mr.append({"source": "マクール掲載 無料予想(場提供)", "url": mv.get("free_yosou_url"), "headline": "印 " + " ".join(f"{m['waku']}{m['mark'] or '－'}" for m in fr["marks"]) + (f" / 進入 {fr['entry']}" if fr.get("entry") else ""), "summary": fr["comment"], "buys": fr["buys"]})
            sm = (fy.get("senmon") or {}).get(str(r["rno"]))
            if sm: mr.append({"source": "地元専門紙予想(マクール掲載・競艇タイムス提供)", "url": mv.get("free_yosou_url"), "headline": sm["headline"], "summary": sm["comment"], "buys": sm["buys"]})
            for ft in media.get("featured", []):
                if ft.get("jcd") == jcd and ft.get("rno") == r["rno"]: mr.append({"source": ft["source"], "url": ft["url"], "headline": ft["headline"], "summary": ft["summary"], "buys": ""})
            for p in mv.get("paid", []):
                if p["rno"] == r["rno"]: mr.append({"source": f"マクール イチオシ{p['label']}", "url": p["url"], "headline": "会員限定(有料)のため本文は未取得", "summary": "", "buys": "", "paywalled": True})
            R["media"] = mr
            V["races"].append(R)
            if an: allraces.append((V, R))
        out["venues"].append(V)
    # 今日のおすすめ
    up = [(V, R) for V, R in allraces if R["status"] == "upcoming"]
    pool = up if len(up) >= 5 else allraces
    picks, per = [], {}
    for V, R in sorted(pool, key=lambda vr: -vr[1]["analysis"]["conf_score"]):
        if per.get(V["jcd"], 0) >= 2: continue  # 1場あたり最大2レース
        picks.append((V, R)); per[V["jcd"]] = per.get(V["jcd"], 0) + 1
        if len(picks) >= 5: break
    out["comments_status"] = {"venues": {j: {"races_with_comments": sum(1 for rr in (v.get("races") or {}).values() if any((y.get("zenjitsu") or y.get("chokuzen")) for y in rr.values())),
                                             "racers_by_toban": len(v.get("by_toban") or {}), "note": v.get("note", ""), "robots": v.get("robots", ""), "sources": v.get("sources", [])}
                                         for j, v in cmj["venues"].items()}, "not_covered": cmj.get("not_covered", {}), "used_in_model": use_cm}
    out["picks"] = [{"jcd": V["jcd"], "venue": V["name"], "rno": R["rno"]} for V, R in picks]
    vals = []
    for V, R in up:
        for x in R["analysis"]["rec"]["value"]:
            vals.append(dict(x, jcd=V["jcd"], venue=V["name"], rno=R["rno"], deadline=R["deadline"], odds_updated=R["odds_updated"]))
    out["values"] = sorted(vals, key=lambda x: -x["ev"])[:15]
    out["ana_rules"] = {"tiers": {t: [lo, hi] for t, (lo, hi) in model.ANA_TIERS.items()}, "threshold": model.ARE_THRESHOLD,
                        "rules": model.ARE_RULES, "min_pb": model.ANA_MIN_PB}
    out["ana_picks"] = ana_lists(up)
    out["ana_backtest"] = ana_backtest([R for V, R in allraces if R.get("result")])
    fin = [R for V, R in allraces if R.get("check")]
    out["day_stats"] = {"races": len(allraces), "upcoming": len(up), "finished": len(fin),
                        "fav_win": sum(1 for R in fin if R["check"]["fav_won"]),
                        "honmei_hit": sum(1 for R in fin if any("本命" in h for h in R["check"]["hits"])),
                        "any3_hit": sum(1 for R in fin if any("3連単" in h for h in R["check"]["hits"])),
                        "nitan_hit": sum(1 for R in fin if "2連単的中" in R["check"]["hits"]),
                        "upcoming_ex": sum(1 for V, R in up if R.get("ex_reflected"))}
    sd = os.path.join(ROOT, "site", "data"); os.makedirs(sd, exist_ok=True)
    json.dump(out, open(os.path.join(sd, f"{hd}.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    dates = sorted({os.path.basename(p)[:8] for p in glob.glob(os.path.join(sd, "2*.json"))}, reverse=True)
    json.dump({"dates": dates, "latest": dates[0]}, open(os.path.join(sd, "dates.json"), "w"), ensure_ascii=False)
    print(f"built site/data/{hd}.json: venues={len(out['venues'])} races={len(allraces)} upcoming={len(up)} picks={len(picks)} values={len(out['values'])} stats={out['day_stats']}")

def comment_status(cmj, jcd):
    """場ごとの選手コメント取得状況(表示用)。"""
    cv = (cmj.get("venues") or {}).get(jcd)
    at = (cv or {}).get("checked_at") or cmj.get("collected_at")
    if cv is None:
        why = (cmj.get("not_covered") or {}).get(jcd, "")
        return {"status": "none", "message": "この場は公式サイトで無料のコメントが公開されていません", "detail": why, "checked_at": at}
    st = cv.get("status") or ("ok" if (cv.get("races") or cv.get("by_toban")) else ("pending" if cv.get("note") else "none"))
    msg = {"ok": "このレースの選手コメントは公式サイトに未掲載です",
           "pending": "この場はまだコメントを公開していません（更新待ち）",
           "none": "この場は公式サイトで無料のコメントが公開されていません"}[st]
    return {"status": st, "message": msg, "detail": cv.get("note", ""), "checked_at": at, "site": cv.get("site")}

def ana_lists(up, n=5):
    """未発走レースから荒れ度が閾値以上のものを 中穴/大穴 別に並べる(1場2Rまで)。"""
    res = {}
    for t in model.ANA_TIERS:
        c = [(V, R) for V, R in up if (R["analysis"].get("ana") or {}).get("score", 0) >= model.ARE_THRESHOLD and R["analysis"]["ana"]["tickets"].get(t)]
        c.sort(key=lambda vr: (-vr[1]["analysis"]["ana"]["score"], -vr[1]["analysis"]["ana"]["p_tier"].get(t, 0)))
        lst, per = [], {}
        for V, R in c:
            if per.get(V["jcd"], 0) >= 2: continue
            a = R["analysis"]["ana"]; per[V["jcd"]] = per.get(V["jcd"], 0) + 1
            lst.append({"jcd": V["jcd"], "venue": V["name"], "rno": R["rno"], "deadline": R["deadline"], "score": a["score"], "reasons": a["reasons"],
                        "p_tier": a["p_tier"].get(t), "tickets": a["tickets"][t], "odds_updated": R["odds_updated"]})
            if len(lst) >= n: break
        res[t] = lst
    return res

def ana_backtest(fin):
    """確定レースで、荒れ度≧閾値の『候補』レースが実際に中穴/大穴配当になった割合と、穴買い目の的中・回収。
    注意: 確定後のキャッシュには締切時点に近いオッズ・直前情報が入るため事前判定の再現であり、閾値も本日データを見て決めた(参考値)。"""
    def yen(R): return ((R["result"].get("payout") or {}).get("3連単") or {}).get("yen")
    grp = {"候補": [], "その他": []}
    for R in fin:
        a = R["analysis"] and R["analysis"].get("ana")
        if not a or yen(R) is None: continue
        grp["候補" if a["score"] >= model.ARE_THRESHOLD else "その他"].append(R)
    out = {}
    for g, rs in grp.items():
        n = len(rs)
        out[g] = {"races": n, "chuana": sum(1 for R in rs if 2000 <= yen(R) < 10000), "oana": sum(1 for R in rs if yen(R) >= 10000),
                  "avg_yen": round(sum(yen(R) for R in rs) / n) if n else None}
    for t in model.ANA_TIERS:
        bets = hits = ret = 0
        for R in grp["候補"]:
            tk = R["analysis"]["ana"]["tickets"].get(t) or []
            win = ((R["result"].get("payout") or {}).get("3連単") or {}).get("combo")
            bets += len(tk)
            for x in tk:
                if x["combo"] == win: hits += 1; ret += yen(R)
        out["tickets_" + t] = {"bets": bets, "hits": hits, "stake_yen": bets * 100, "return_yen": ret}
    out["note"] = "確定後に再計算した参考値(閾値は本日データで設定=サンプル内)。少数レースのため偶然の影響が大きい。"
    return out

def model_time(hd, hhmm):
    try:
        h, m = map(int, hhmm.split(":")); return dt.datetime(int(hd[:4]), int(hd[4:6]), int(hd[6:]), h, m, tzinfo=JST)
    except Exception: return None

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else dt.datetime.now(JST).strftime("%Y%m%d"))
