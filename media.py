#!/usr/bin/env python3
"""情報誌/メディアの無料公開情報を収集 (マクール sp.macour.jp の無料ページのみ)。

- 予想ページ /predictions/ : 本日の注目レース(無料コメント) と 各場の「無料予想」リンク
- 無料予想ページ /c/kyotei_info_new/<id>/ : 各場公式提供の無料予想(印・進入・コメント・買い目), 地元専門紙予想, 今節の展望
- ニュース /news/ : 見出し・日時・リンク, 記事冒頭(無料公開部分)の要約
有料部分(イチオシ予想 /d/ichioshi/, 超抜モード, 記事の「続きはスタンダードコース」以降)は取得しない。
robots.txt の Disallow (/m/, /d/premium/boatracer/ 等) には触れない。
"""
import re, json, os, sys, datetime as dt, warnings
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import bhttp
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
M = "https://sp.macour.jp"
ROOT = os.path.dirname(os.path.abspath(__file__))
JST = dt.timezone(dt.timedelta(hours=9))
NAME2JCD = {"桐生":"01","戸田":"02","江戸川":"03","平和島":"04","多摩川":"05","浜名湖":"06","蒲郡":"07","常滑":"08","津":"09","三国":"10",
            "びわこ":"11","琵琶湖":"11","住之江":"12","尼崎":"13","鳴門":"14","丸亀":"15","児島":"16","宮島":"17","徳山":"18","下関":"19",
            "若松":"20","芦屋":"21","福岡":"22","唐津":"23","大村":"24"}
CIRC = "①②③④⑤⑥"

def S(h): return BeautifulSoup(h, "lxml")
def T(e): return re.sub(r"\s+", " ", e.get_text(" ", strip=True)).strip() if e else ""

def predictions_page(hd):
    h = bhttp.get(f"{M}/predictions/", max_age=1800)
    out = {"featured": [], "free_links": {}, "paid_links": {}}
    if not h: return out
    s = S(h)
    for a in s.select("a.race-root"):
        m = re.search(r"/(\w+)/racecards/(\d{8})/(\d+)/", a.get("href", ""))
        name = T(a.select_one(".badge"))
        if not m or m.group(2) != hd: continue
        out["featured"].append({"jcd": NAME2JCD.get(name), "rno": int(m.group(3)), "source": "マクール 本日の注目レース",
                                "headline": T(a.select_one(".comment-headline")), "summary": T(a.select_one(".comment")),
                                "url": M + a["href"]})
    pending = None
    for a in s.select("a"):
        href = a.get("href", ""); t = T(a)
        if t == "無料予想": pending = href; continue
        m = re.search(r"/premium-race/jo-list/date/(\d{8})/jid/(\d+)/", href)
        if m and pending:
            out["free_links"][m.group(2).zfill(2)] = pending; pending = None
        m = re.search(r"/d/ichioshi/detail-api/date/(\d{8})/jid/(\d+)/rn/(\d+)/", href)
        if m and m.group(1) == hd:
            out["paid_links"].setdefault(m.group(2).zfill(2), []).append({"rno": int(m.group(3)), "label": t.split(" ")[0], "url": href if href.startswith("http") else M + href})
    return out

def parse_free_yosou(h):
    """マクール無料予想ページ(携帯向け簡易HTML)を行単位でパース."""
    s = S(h)
    for x in s(["script", "style"]): x.decompose()
    title = T(s.select_one("h2")) or next((l for l in s.get_text("\n").split("\n") if re.search(r"\d+月\d+日予想", l)), "").strip()
    lines = [l.strip().replace("\u3000", " ") for l in s.get_text("\n").split("\n")]
    lines = [l for l in lines if l]
    races, senmon, outlook = {}, {}, []
    cur = None; mode = "race"
    for l in lines:
        if mode != "senmon" and re.fullmatch(r"☆?\d{1,2}R", l): cur = {"rno": int(l.strip("☆")[:-1]), "marks": [], "lines": []}; races[cur["rno"]] = cur; mode = "race"; continue
        if "地元専門" in l and "予想" in l and not l.startswith(":"): mode = "senmon"; cur = None; senmon["_note"] = []; continue
        if l == "今節の展望": mode = "outlook"; cur = None; continue
        if l.startswith((":", "□", "無料予想")) or re.fullmatch(r"予想|ボートレース\S+", l): continue
        if mode == "senmon":
            m = re.match(r"☆(\d{1,2})R(.*)", l)
            if m: cur = {"rno": int(m.group(1)), "race": m.group(2).strip("() （）"), "lines": []}; senmon[cur["rno"]] = cur; continue
            (cur["lines"] if cur else senmon["_note"]).append(l); continue
        if mode == "outlook": outlook.append(l); continue
        if cur is None: continue
        m = re.match(rf"([{CIRC}])\s*([◎○▲△×☆注]?)\s*(.+)", l)
        if m and len(cur["marks"]) < 6 and not re.search(r"[-=]", l):
            cur["marks"].append({"waku": CIRC.index(m.group(1)) + 1, "mark": m.group(2) or "", "name": m.group(3).strip()}); continue
        cur["lines"].append(l)
    res = {}
    for r, c in races.items():
        buys, lab = [], ""
        for l in c["lines"]:
            if l in ("2連単", "3連単", "2連複", "3連複"): lab = l + " "; continue
            if re.search(rf"[{CIRC}]\s*[-=]", l) or re.match(r"\[[23]連[単複]\]", l): buys.append(lab + l); lab = ""
        tenji = next((l for l in c["lines"] if re.match(r"(進入)?[1-6]{3}\s*[/・]\s*[1-6]{3}", l)), "")
        comment = " ".join(l for l in c["lines"] if not re.search(rf"[{CIRC}]\s*[-=]", l) and not re.match(r"\[[23]連[単複]\]", l) and l != tenji and l not in ("2連単", "3連単", "2連複", "3連複"))
        res[r] = {"marks": c["marks"], "entry": tenji.replace("進入", ""), "comment": comment, "buys": " / ".join(buys)}
    sen = {}
    for r, c in senmon.items():
        if r == "_note": continue
        buys = [l for l in c["lines"] if re.search(r"\d\s*[-=]\s*\d", l)]
        text = [l for l in c["lines"] if l not in buys]
        sen[r] = {"race": c["race"], "headline": text[0] if text else "", "comment": " ".join(text[1:]), "buys": " ".join(buys)}
    return {"title": title, "races": res, "senmon": sen, "senmon_note": " ".join(senmon.get("_note", [])), "outlook": " ".join(outlook)}

def wyosou(hd):
    """若松予想サイト(マクール運営・無料)。各レースのコメントのみ(買い目は画像のため未取得)."""
    W = "https://wyosou.macour.jp"
    res = {"title": "", "races": {}, "senmon": {}, "senmon_note": "", "outlook": "", "date_ok": False}
    h = bhttp.get(f"{W}/seriesindex/index/day/{hd}", max_age=3600)
    if h:
        s = S(h); [x.decompose() for x in s(["script", "style"])]
        L = [l.strip() for l in s.get_text("\n").split("\n") if l.strip()]
        res["title"] = next((l for l in L if "年" in l and "月" in l and "日" in l), "")
        d = dt.datetime.strptime(hd, "%Y%m%d"); res["date_ok"] = f"{d.year}年{d.month}月{d.day}日" in res["title"]
        i = next((k for k, l in enumerate(L) if l.startswith(("最終日", "初日")) or "日目" in l[:4]), 1)
        res["outlook"] = " ".join(L[i + 2:i + 8])[:400] if len(L) > i + 2 else ""
    for rno in range(1, 13):
        h = bhttp.get(f"{W}/index/list/day/{hd}/no/{rno}", max_age=3600)
        if not h: continue
        s = S(h); [x.decompose() for x in s(["script", "style"])]
        L = [l.strip() for l in s.get_text("\n").split("\n") if l.strip()]
        k = next((k for k, l in enumerate(L) if "締切予定時刻" in l), None)
        if k is not None and k + 1 < len(L) and L[k + 1] not in ("2連単", "3連単"):
            res["races"][rno] = {"marks": [], "entry": "", "comment": L[k + 1], "buys": "", "race": L[k - 1] if k else ""}
    res["source_url"] = f"{W}/seriesindex/"
    return res

def news(hd, venues_today, per_venue=2, max_days=2):
    h = bhttp.get(f"{M}/news/", max_age=1800)
    items = {}
    if not h: return items
    s = S(h); limit = dt.datetime.strptime(hd, "%Y%m%d") - dt.timedelta(days=max_days)
    seen = set()
    for a in s.select('a[href*="/news/"]'):
        href = a.get("href", ""); 
        if not re.search(r"/news/\d+/", href) or href in seen: continue
        seen.add(href)
        name = T(a.select_one(".tag-ol.is-jo")); jcd = NAME2JCD.get(name)
        tm = a.select_one("time"); when = tm.get("datetime") if tm else ""
        if not jcd or jcd not in venues_today or not when: continue
        if dt.datetime.strptime(when[:10], "%Y-%m-%d") < limit: continue
        if len(items.get(jcd, [])) >= per_venue: continue
        title = a.get("title") or T(a.select_one("._title"))
        items.setdefault(jcd, []).append({"headline": title, "time": when[:16], "url": href, "source": "マクール ニュース", "summary": ""})
    for jcd, lst in items.items():
        for it in lst:
            hh = bhttp.get(it["url"], max_age=None)
            if not hh: continue
            body = S(hh).select_one("div._text, p._text, ._text")
            t = T(body) if body else ""
            t = t.split("続きは")[0].strip()
            it["summary"] = (t[:140] + "…") if len(t) > 140 else t
            it["paywalled_rest"] = "続きは" in (T(body) if body else "") or "入会" in hh[:0]
    return items

def collect(hd, venues_today):
    out = {"hd": hd, "collected_at": dt.datetime.now(JST).isoformat(timespec="seconds"), "venues": {}, "featured": [], "status": []}
    pp = predictions_page(hd)
    out["featured"] = pp["featured"]
    out["status"].append(f"マクール予想ページ: 注目レース{len(pp['featured'])}件, 無料予想リンク{len(pp['free_links'])}場, 有料(イチオシ)リンク{sum(len(v) for v in pp['paid_links'].values())}件(本文は会員限定のため未取得)")
    nw = news(hd, venues_today)
    out["status"].append(f"マクールニュース: {sum(len(v) for v in nw.values())}件 (見出し+無料冒頭のみ。続きはスタンダードコース会員限定)")
    for jcd in venues_today:
        v = {"free_yosou_url": pp["free_links"].get(jcd), "free_yosou": None, "paid": pp["paid_links"].get(jcd, []), "news": nw.get(jcd, [])}
        url = v["free_yosou_url"]
        if url and url.startswith(M + "/c/"):
            h = bhttp.get(url, max_age=1800)
            if h:
                fy = parse_free_yosou(h)
                # 日付チェック (例: "10月18日予想")
                d = dt.datetime.strptime(hd, "%Y%m%d"); want = f"{d.month}月{d.day}日"
                fy["date_ok"] = want in fy["title"]
                v["free_yosou"] = fy
        elif url and "wyosou.macour.jp" in url:
            v["free_yosou"] = wyosou(hd)
        elif url:
            v["free_yosou_note"] = "外部サイト(各場公式/提携サイト)の無料予想。形式が場ごとに異なるため未解析、リンクのみ。"
        out["venues"][jcd] = v
    ok = sum(1 for v in out["venues"].values() if v["free_yosou"] and v["free_yosou"]["races"])
    out["status"].append(f"無料予想(マクール掲載分)を解析できた場: {ok}")
    return out

if __name__ == "__main__":
    hd = sys.argv[1] if len(sys.argv) > 1 else dt.datetime.now(JST).strftime("%Y%m%d")
    jcds = sys.argv[2].split(",") if len(sys.argv) > 2 else list(NAME2JCD.values())
    r = collect(hd, sorted(set(jcds)))
    os.makedirs(os.path.join(ROOT, "cache", "json", hd), exist_ok=True)
    json.dump(r, open(os.path.join(ROOT, "cache", "json", hd, "_media.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n".join(r["status"]))
