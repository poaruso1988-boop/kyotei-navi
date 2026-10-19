#!/usr/bin/env python3
"""boatrace.jp 公開ページから指定日の 開催場/出走表/直前情報/オッズ/結果 を取得し cache/json/YYYYMMDD/ に保存する。

robots.txt (https://www.boatrace.jp/robots.txt) は "User-agent: * / Disallow:" (全許可) を確認済み。
1ホストあたりリクエスト開始間隔 >= 1秒、ディスクキャッシュ有り。
usage: python3 fetch.py [YYYYMMDD] [--workers 6] [--no-odds]
"""
import os, re, sys, json, time, argparse, warnings, datetime as dt
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import bhttp
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

BASE = "https://www.boatrace.jp/owpc/pc"
ROOT = os.path.dirname(os.path.abspath(__file__))
JST = dt.timezone(dt.timedelta(hours=9))
Z2H = str.maketrans("０１２３４５６７８９．", "0123456789.")
VENUES = {"01":"桐生","02":"戸田","03":"江戸川","04":"平和島","05":"多摩川","06":"浜名湖","07":"蒲郡","08":"常滑",
          "09":"津","10":"三国","11":"びわこ","12":"住之江","13":"尼崎","14":"鳴門","15":"丸亀","16":"児島",
          "17":"宮島","18":"徳山","19":"下関","20":"若松","21":"芦屋","22":"福岡","23":"唐津","24":"大村"}
MARKS = {"1": "◎", "2": "○", "3": "▲", "4": "△"}

def soup(h): return BeautifulSoup(h, "lxml")
def txt(e): return re.sub(r"\s+", " ", e.get_text(" ", strip=True)).strip() if e else ""
def num(s):
    try: return float(str(s).translate(Z2H).replace("%", "").strip())
    except (ValueError, TypeError): return None

# ---------------- parsers ----------------
def parse_index(h):
    s = soup(h); out = []
    for tb in s.select("div.table1 table tbody"):
        a = tb.select_one('a[href*="raceindex?jcd="]')
        if not a: continue
        jcd = re.search(r"jcd=(\d+)", a["href"]).group(1)
        tds = tb.select("tr")[0].select("td")
        cls = " ".join(" ".join(td.get("class", [])) for td in tds)
        grade = next((g for g in ["SG", "G1", "G2", "G3"] if re.search(rf"is-{g}[ab]?\b", cls)), "一般")
        if "is-venus" in cls: grade += "・ヴィーナス"
        kind = "ナイター" if "is-nighter" in cls else "ミッドナイト" if "is-midnight" in cls else "モーニング" if "is-morning" in cls else "デイ"
        day = ""
        for td in tds:
            t = txt(td)
            if re.search(r"日目|初日|最終日", t) and "/" in t: day = t
        out.append({"jcd": jcd, "name": VENUES.get(jcd, jcd), "title": txt(a), "grade": grade, "kind": kind,
                    "period_day": day, "status": txt(tds[1]) if len(tds) > 1 else ""})
    return out

def parse_deadlines(s):
    for t in s.select("div.table1 table"):
        tt = txt(t)
        if "締切予定時刻" in tt:
            return [txt(td) for td in t.select("tbody td")[1:]]
    return []

def parse_racelist(h):
    """pcexpect (= 出走表 + 公式コンピューター予想印/フォーカス) or racelist page."""
    s = soup(h)
    title = txt(s.select_one("h3.title16_titleDetail__add2020"))
    m = re.match(r"(.*?)\s*(\d{3,4}m)", title)
    race = {"race_title": (m.group(1) if m else title).strip(), "distance": m.group(2) if m else "",
            "deadlines": parse_deadlines(s), "boats": []}
    tbl = None
    for t in s.select("div.table1 table"):
        if "登録番号" in txt(t.select_one("thead")): tbl = t; break
    if not tbl: return None
    for tb in tbl.select("tbody"):
        trs = tb.select("tr"); tds = trs[0].select("td")
        mark = None
        img = tds[0].select_one("img")
        if img and "icon_mark1_" in img.get("src", ""):
            mark = MARKS.get(re.search(r"icon_mark1_(\d)", img["src"]).group(1))
        idx = next(i for i, td in enumerate(tds) if "is-boatColor" in " ".join(td.get("class", [])))
        waku = int(num(txt(tds[idx])))
        info = tds[idx + 2]
        t0 = txt(info.select_one("div.is-fs11"))
        toban, cls = re.match(r"(\d+)\s*/\s*(\S+)", t0).groups()
        name = re.sub(r"[\s\u3000]+", " ", info.select_one("div.is-fs18").get_text(strip=True)).strip()
        divs = info.select("div.is-fs11")
        bio = txt(divs[1]) if len(divs) > 1 else ""
        bm = re.match(r"(\S+?)\s*/\s*(\S+)\s+(\d+)歳\s*/\s*([\d.]+)kg", bio.replace(" / ", "/").replace("/ ", "/").replace(" /", "/"))
        def three(i): return [num(x) for x in txt(tds[idx + i]).split()]
        fl = txt(tds[idx + 3]).split()
        nat, loc, mot, boa = three(4), three(5), three(6), three(7)
        series = []
        if len(trs) >= 4:
            courses = [txt(td) for td in trs[1].select("td")]
            sts = [txt(td) for td in trs[2].select("td")]
            ranks = [txt(td).translate(Z2H) for td in trs[3].select("td")]
            rnos = [txt(td) for td in tds[idx + 9: idx + 9 + 14]]
            for i, r in enumerate(ranks):
                if r: series.append({"course": courses[i] if i < len(courses) else "", "st": sts[i] if i < len(sts) else "", "rank": r})
        race["boats"].append({
            "waku": waku, "toban": toban, "class": cls, "name": name,
            "branch": bm.group(1) if bm else "", "home": bm.group(2) if bm else "",
            "age": int(bm.group(3)) if bm else None, "weight": float(bm.group(4)) if bm else None,
            "F": int(num(fl[0][1:]) or 0), "L": int(num(fl[1][1:]) or 0), "avg_st": num(fl[2]) if len(fl) > 2 else None,
            "nat_win": nat[0], "nat_2r": nat[1], "nat_3r": nat[2],
            "loc_win": loc[0], "loc_2r": loc[1], "loc_3r": loc[2],
            "motor_no": int(mot[0]) if mot[0] else None, "motor_2r": mot[1], "motor_3r": mot[2],
            "boat_no": int(boa[0]) if boa[0] else None, "boat_2r": boa[1], "boat_3r": boa[2],
            "pc_mark": mark, "series": series})
    # 公式コンピューター予想フォーカス
    focus = [re.sub(r"\s+", "", txt(r)) for r in s.select(".numberSet2_row")]
    race["pc_focus"] = focus
    conf = None
    e = s.find(string=re.compile("自信度"))
    if e:
        blk = e.find_parent("div")
        for _ in range(3):
            if blk is None: break
            img = blk.select_one('img[src*="icon_"]')
            if img: conf = img.get("alt") or img.get("src"); break
            blk = blk.parent
    race["pc_confidence_raw"] = conf
    return race

def parse_beforeinfo(h):
    s = soup(h); out = {"boats": {}, "start_exhibition": [], "weather": {}}
    tbls = s.select("div.table1 table")
    main = next((t for t in tbls if "展示" in txt(t.select_one("thead"))), None)
    if main:
        for tb in main.select("tbody"):
            tds = tb.select("tr")[0].select("td")
            w = int(num(txt(tds[0])))
            ex = num(txt(tds[4])); tilt = num(txt(tds[5]))
            out["boats"][w] = {"ex_time": ex, "tilt": tilt, "propeller": txt(tds[6]),
                               "parts": txt(tds[7]), "adj_weight": num(txt(tb.select("tr")[2].select("td")[0]))}
    se = next((t for t in tbls if "スタート展示" in txt(t)), None)
    if se:
        for i, d in enumerate(se.select(".table1_boatImage1")):
            n = txt(d.select_one(".table1_boatImage1Number")); st = txt(d.select_one(".table1_boatImage1Time"))
            if n: out["start_exhibition"].append({"course": i + 1, "waku": int(n), "st": st})
    w = s.select_one(".weather1")
    if w:
        out["weather"]["title"] = txt(w.select_one(".weather1_title"))
        for u in w.select(".weather1_bodyUnit"):
            t = txt(u.select_one(".weather1_bodyUnitLabelTitle")); d = txt(u.select_one(".weather1_bodyUnitLabelData"))
            c = " ".join(u.get("class", []))
            if "is-weather" in c: out["weather"]["weather"] = t
            elif "is-wind" in c and "Direction" not in c: out["weather"]["wind_mps"] = num(d.replace("m", ""))
            elif "is-wave" in c: out["weather"]["wave_cm"] = num(d.replace("cm", ""))
            elif "is-waterTemperature" in c: out["weather"]["water_temp"] = d
            elif "is-direction" in c: out["weather"]["air_temp"] = d
            if "is-windDirection" in c:
                p = u.select_one("p"); m = re.search(r"is-wind(\d+)", " ".join(p.get("class", []))) if p else None
                out["weather"]["wind_dir_code"] = int(m.group(1)) if m else None
    out["available"] = any(b["ex_time"] for b in out["boats"].values())
    return out

# 場独自の「オリジナル展示データ」(半周・まわり足・直線)。robots.txt で /modules/yosou/ が許可されていることを確認済みの場のみ。
# 現状は桐生(独自計測値)のみ書式確認済み。表示専用でスコアには使わない(検証データ不足のため)。
ORITEN_SITES = {"01": "https://www.kiryu-kyotei.com/modules/yosou/cyokuzen.php?race={rno}"}

def parse_oriten(h, boats):
    """→ {waku: {"half": 半周, "mawari": まわり足, "straight": 直線}}。登番が出走表と一致する行だけ採用(別レース/別日の混入防止)。"""
    s = soup(h); t = next((t for t in s.select("table") if "オリジナル展示データ" in txt(t)), None)
    if not t: return {}
    tob = {str(b["toban"]): b["waku"] for b in boats if b.get("toban")}
    out = {}
    for tr in t.select("tr"):
        tds = [txt(td) for td in tr.select("td")]
        if len(tds) < 8 or not re.fullmatch(r"[1-6]", tds[0]): continue
        m = re.match(r"(\d{4})", tds[1]); w = int(tds[0])
        if not m or tob.get(m.group(1)) != w: continue
        v = [num(x) for x in tds[5:8]]
        if any(v): out[w] = {"half": v[0], "mawari": v[1], "straight": v[2]}
    return out

def parse_odds3t(h):
    s = soup(h); tbls = s.select("div.table1 table")
    t = next((t for t in tbls if len(t.select("td.oddsPoint")) >= 100), None)
    if not t: return None
    odds = {}; seconds = [None] * 6
    for tr in t.select("tbody tr"):
        tds = tr.select("td"); per = len(tds) // 6
        for c in range(6):
            cell = tds[c * per:(c + 1) * per]
            if per == 3: seconds[c] = int(num(txt(cell[0])))
            third = int(num(txt(cell[-2]))); o = num(txt(cell[-1]))
            odds[f"{c+1}-{seconds[c]}-{third}"] = o if o else None
    upd = s.find(string=re.compile("オッズ更新時間"))
    return {"odds": odds, "updated": txt(upd.parent) if upd else ""}

def parse_odds2t(h):
    s = soup(h); tbls = [t for t in s.select("div.table1 table") if t.select("td.oddsPoint")]
    if not tbls: return None
    odds = {}
    for tr in tbls[0].select("tbody tr"):
        tds = tr.select("td")
        for c in range(6):
            sec, o = txt(tds[2 * c]), num(txt(tds[2 * c + 1]))
            if sec: odds[f"{c+1}-{int(num(sec))}"] = o if o else None
    return {"odds": odds}

def parse_result(h):
    s = soup(h); tbls = s.select("div.table1 table")
    rt = next((t for t in tbls if "レースタイム" in txt(t.select_one("thead"))), None)
    if not rt: return None
    order = []
    for tb in rt.select("tbody"):
        tds = tb.select("td")
        if len(tds) < 3 or not txt(tds[1]): continue
        order.append({"rank": txt(tds[0]).translate(Z2H), "waku": int(num(txt(tds[1]))), "name": txt(tds[2].select_one(".is-fs18")), "time": txt(tds[3]) if len(tds) > 3 else ""})
    if not order: return None
    pay = {}
    pt = next((t for t in tbls if "払戻金" in txt(t)), None)
    if pt:
        T = txt(pt)
        for k, pat in [("3連単", r"3連単\s+(\d)\s*-\s*(\d)\s*-\s*(\d)\s+¥([\d,]+)"), ("2連単", r"2連単\s+(\d)\s*-\s*(\d)\s+¥([\d,]+)")]:
            m = re.search(pat, T)
            if m: pay[k] = {"combo": "-".join(m.groups()[:-1]), "yen": int(m.groups()[-1].replace(",", ""))}
    kim = next((txt(t.select_one("tbody")) for t in tbls if "決まり手" in txt(t.select_one("thead"))), "")
    return {"order": order, "payout": pay, "kimarite": kim}

def parse_stadium(h):
    """場別データ: 最近3ヶ月のコース別入着率(1~3着)と決まり手."""
    s = soup(h)
    for t in s.select("table"):
        th = txt(t.select_one("thead"))
        if "コース" in th and "1着" in th:
            rows = {}
            for tr in t.select("tbody tr"):
                v = [num(txt(td)) for td in tr.select("td")]
                if v and v[0] in (1, 2, 3, 4, 5, 6):
                    c = int(v[0]); rows[c] = {"r1": v[1], "r2": v[2], "r3": v[3], "kimarite": v[7:13] if len(v) >= 13 else []}
            if len(rows) == 6:
                return {"period": "最近3ヶ月", "course": rows, "source": "boatrace.jp 場別データ"}
    return None

# ---------------- driver ----------------
def jdump(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f: json.dump(obj, f, ensure_ascii=False, indent=1)

def race_time(hd, hhmm):
    try:
        h, m = map(int, hhmm.split(":")); return dt.datetime(int(hd[:4]), int(hd[4:6]), int(hd[6:]), h, m, tzinfo=JST)
    except Exception: return None

def fetch_before(hd, jcd, rno, boats, fresh):
    q = f"rno={rno}&jcd={jcd}&hd={hd}"
    h = bhttp.get(f"{BASE}/race/beforeinfo?{q}", max_age=fresh)
    bf = parse_beforeinfo(h) if h else None
    if bf is not None and jcd in ORITEN_SITES and bf.get("available") and boats:
        try:
            ho = bhttp.get(ORITEN_SITES[jcd].format(rno=rno), max_age=fresh)
            o = parse_oriten(ho, boats) if ho else {}
            if o: bf["original"] = {"source": ORITEN_SITES[jcd].format(rno=rno), "note": "場独自計測(半周・まわり足・直線)", "boats": o}
        except Exception: pass
    return bf, h is None

def fetch_race(hd, v, rno, deadline, odds=True):
    jcd = v["jcd"]; q = f"rno={rno}&jcd={jcd}&hd={hd}"
    now = dt.datetime.now(JST); dl = race_time(hd, deadline)
    finished_guess = dl and now > dl + dt.timedelta(minutes=8)
    past_day = hd < now.strftime("%Y%m%d")
    rec = {"rno": rno, "deadline": deadline, "errors": []}
    h = bhttp.get(f"{BASE}/race/pcexpect?{q}", max_age=None if past_day else 3 * 3600)
    rl = parse_racelist(h) if h else None
    if not rl:
        h = bhttp.get(f"{BASE}/race/racelist?{q}", max_age=None if past_day else 3 * 3600)
        rl = parse_racelist(h) if h else None
    if not rl: rec["errors"].append("出走表取得失敗"); return rec
    rec.update({k: rl[k] for k in ("race_title", "distance", "boats", "pc_focus", "pc_confidence_raw")})
    # 直前情報: 締切前は5分キャッシュ, 済みなら固定
    fresh = None if (finished_guess or past_day) else 240
    rec["before"], failed = fetch_before(hd, jcd, rno, rec.get("boats"), fresh)
    rec["before_checked_at"] = now.isoformat(timespec="seconds")
    if failed: rec["errors"].append("直前情報取得失敗")
    if finished_guess or past_day:
        h = bhttp.get(f"{BASE}/race/raceresult?{q}", max_age=None)
        rec["result"] = parse_result(h) if h else None
        if rec["result"] is None:  # 未確定ならキャッシュを消して次回再取得
            try: os.remove(bhttp.cache_path(f"{BASE}/race/raceresult?{q}"))
            except OSError: pass
    if odds:
        h = bhttp.get(f"{BASE}/race/odds3t?{q}", max_age=None if (finished_guess or past_day) else 300)
        rec["odds3t"] = parse_odds3t(h) if h else None
        if not finished_guess and not past_day:
            h = bhttp.get(f"{BASE}/race/odds2tf?{q}", max_age=300)
            rec["odds2t"] = parse_odds2t(h) if h else None
    return rec

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("hd", nargs="?", default=dt.datetime.now(JST).strftime("%Y%m%d"))
    ap.add_argument("--workers", type=int, default=6); ap.add_argument("--no-odds", action="store_true")
    ap.add_argument("--venues", default="", help="comma separated jcd filter")
    ap.add_argument("--intraday", action="store_true", help="軽量更新: 確定済みは再利用、締切まで--window時間以内のレースのみ直前情報/オッズ再取得")
    ap.add_argument("--window", type=float, default=3.0)
    ap.add_argument("--ex-only", action="store_true", help="展示専用の高速更新: 締切まで--ex-window分以内の未確定レースの直前情報(展示)だけ再取得。オッズ等は前回分を再利用")
    ap.add_argument("--ex-window", type=float, default=50.0)
    a = ap.parse_args(); hd = a.hd
    t0 = time.time()
    h = bhttp.get(f"{BASE}/race/index?hd={hd}", max_age=600)
    if not h: sys.exit("開催一覧の取得に失敗しました")
    venues = parse_index(h)
    if a.venues: venues = [v for v in venues if v["jcd"] in a.venues.split(",")]
    print(f"{hd}: {len(venues)}場 {' '.join(v['name'] for v in venues)}", flush=True)
    outdir = os.path.join(ROOT, "cache", "json", hd)
    # 場別データ + 1R の出走表(締切時刻)
    def prep(v):
        hs = bhttp.get(f"{BASE}/data/stadium?jcd={v['jcd']}", max_age=7 * 86400)
        v["stadium"] = parse_stadium(hs) if hs else None
        h1 = bhttp.get(f"{BASE}/race/pcexpect?rno=1&jcd={v['jcd']}&hd={hd}", max_age=3 * 3600)
        v["deadlines"] = parse_deadlines(soup(h1)) if h1 else []
        return v
    with ThreadPoolExecutor(a.workers) as ex: venues = list(ex.map(prep, venues))
    jdump({"hd": hd, "venues": venues}, os.path.join(outdir, "_venues.json"))
    jobs = [(v, r) for v in venues for r in range(1, len(v["deadlines"]) + 1)]
    stat = {"reused": 0, "fetched": 0}
    def run(job):
        v, r = job
        path = os.path.join(outdir, f"{v['jcd']}_{r:02d}.json")
        if a.ex_only:
            try: old = json.load(open(path, encoding="utf-8"))
            except (OSError, ValueError): old = None
            if not old or not old.get("boats"): stat["reused"] += 1; return old or {"rno": r, "deadline": v["deadlines"][r - 1], "errors": ["未取得(通常更新を先に実行)"]}
            dl = race_time(hd, v["deadlines"][r - 1]); now = dt.datetime.now(JST)
            if old.get("result") or not dl or now > dl + dt.timedelta(minutes=2) or now + dt.timedelta(minutes=a.ex_window) < dl:
                stat["reused"] += 1; return old
            stat["fetched"] += 1
            bf, failed = fetch_before(hd, v["jcd"], r, old.get("boats"), 240)
            if bf is not None:
                prev = old.get("before") or {}
                if prev.get("available") and not bf.get("available"): bf = prev  # 一時的な欠測で展示を消さない
                old["before"] = bf; old["before_checked_at"] = now.isoformat(timespec="seconds")
                jdump(old, path)
            return old
        if a.intraday and os.path.exists(path):
            try: old = json.load(open(path, encoding="utf-8"))
            except ValueError: old = None
            dl = race_time(hd, v["deadlines"][r - 1]); now = dt.datetime.now(JST)
            if old and old.get("boats") and (old.get("result") or (dl and now + dt.timedelta(hours=a.window) < dl)):
                stat["reused"] += 1; return old
        stat["fetched"] += 1
        try: rec = fetch_race(hd, v, r, v["deadlines"][r - 1], odds=not a.no_odds)
        except Exception as e: rec = {"rno": r, "deadline": v["deadlines"][r - 1], "errors": [f"例外: {e!r}"]}
        jdump(rec, os.path.join(outdir, f"{v['jcd']}_{r:02d}.json"))
        return rec
    done = 0
    with ThreadPoolExecutor(a.workers) as ex:
        for v, rec in zip([j[0] for j in jobs], ex.map(run, jobs)):
            v.setdefault("races", []).append(rec); done += 1
            if done % 12 == 0: print(f"  {done}/{len(jobs)} races ({time.time()-t0:.0f}s) {bhttp.STATS}", flush=True)
    for v in venues: v["races"].sort(key=lambda r: r["rno"])
    jdump({"hd": hd, "fetched_at": dt.datetime.now(JST).isoformat(timespec="seconds"), "venues": venues}, os.path.join(outdir, "_all.json"))
    print(f"done {time.time()-t0:.0f}s {bhttp.STATS} {stat if (a.intraday or a.ex_only) else ''} -> {outdir}/_all.json")

if __name__ == "__main__":
    main()
