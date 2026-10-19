#!/usr/bin/env python3
"""各場公式サイトの無料公開「選手コメント」を収集し、足色(出足/行き足/伸び/回り足/総合)を辞書ベースで評価する。

対象: JLC系共通CMSの場サイト (/sp/index.php?page=...)。robots.txt は管理系パスのみ Disallow (または無し) を確認。
  - 直前情報ページ  page=yosou-cyokuzen&race=N : 枠ごとの 前日コメント + 直前コメント(時刻付き)  (例: 唐津)
  - 全選手コメント  page=raceinfo-racers_comment / raceinfo-racer_comment : 登番ごとの前日コメント (例: 芦屋, 唐津)
1ホストあたり 1秒以上の間隔, 30分キャッシュ。
usage: python3 comments.py [YYYYMMDD]  → cache/json/YYYYMMDD/_comments.json
"""
import os, re, sys, json, datetime as dt, warnings
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import bhttp
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
ROOT = os.path.dirname(os.path.abspath(__file__))
JST = dt.timezone(dt.timedelta(hours=9))
SITES = {"01": "https://www.kiryu-kyotei.com", "03": "https://www.boatrace-edogawa.com", "08": "https://www.boatrace-tokoname.jp",
         "09": "https://www.boatrace-tsu.com", "10": "https://www.boatrace-mikuni.jp", "18": "https://www.boatrace-tokuyama.jp",
         "19": "https://www.boatrace-shimonoseki.jp", "20": "https://www.wmb.jp", "21": "https://www.boatrace-ashiya.com",
         "23": "https://www.boatrace-karatsu.jp"}
NOT_COVERED = {"02": "戸田: 公式サイト(boatrace-toda.jp)のメニューに選手コメントページなし(2026-10-18確認)",
               "04": "平和島: 公式サイト(heiwajima.gr.jp)のメニューに選手コメントページなし(2026-10-18確認)",
               "16": "児島: 公式サイト(kojimaboat.jp)は優勝戦インタビューのみで、レース毎の選手コメントなし(2026-10-18確認)"}
MAX_AGE = int(os.environ.get("COMMENTS_MAX_AGE", "1800"))
Z2H = str.maketrans("０１２３４５６７８９", "0123456789")

# ---------------- 足色 辞書 ----------------
ASPECTS = {  # 観点: キーワード
    "出足": ["出足", "起こし", "押し", "押して", "立ち上がり", "レース足", "下がらない"],
    "行き足": ["行き足", "スリット", "加速", "Ｓ", "スタート"],
    "伸び": ["伸び", "直線", "ストレート", "上がり"],
    "回り足": ["回り足", "ターン回り", "ターン", "旋回", "回った後", "まわり足", "グリップ", "回って", "１Ｍ", "1M"],
    "総合": ["足", "舟足", "エンジン", "モーター", "機", "仕上が", "全体", "バランス", "乗り心地", "乗りやす", "乗りにく", "乗りづら", "操縦性"],
}
GOOD = ["いい", "良い", "良く", "良かった", "強い", "強力", "しっかり", "上々", "トップ級", "節イチ", "抜群", "出ている", "出てる", "出ていく", "出て行く",
        "余裕", "上向", "問題ない", "気にならない", "十分", "エグイ", "エグい", "完璧", "文句な", "負けない", "勝って", "合ってい", "合ってき", "スムーズ",
        "力強", "上位", "良さそう", "いける", "戦える"]
MILD_GOOD = ["悪くない", "まずまず", "そこそこ", "まあまあ", "それなり", "下がることはない", "下がらない", "ましになった", "マシ", "小マシ"]
BAD = ["弱い", "甘い", "劣勢", "足りない", "物足りな", "悪い", "良くない", "下が", "負け", "鈍", "重た", "重い", "苦し", "ダメ", "だめ", "いまいち", "イマイチ",
       "不安", "合ってない", "合っていない", "合わない", "掛からない", "滑る", "キャビ", "乗りづら", "乗りにく", "スカ", "厳しい", "きつい", "ひどい", "落ち",
       "ない", "なかった", "やられ", "鳴く", "跳ね", "苦戦", "失敗"]
NEUTRAL = ["普通", "平凡", "特徴ない", "特徴はない", "変わらない", "変わりない", "可もなく"]
HOPE = ["したい", "求めたい", "欲しい", "もっと", "上積み", "合わせたい", "やり直", "調整する", "叩く"]
COND = ["れば", "たら", "なら", "合えば", "戻せれば"]

def _pol(clause):
    c = clause
    if any(w in c for w in COND): return 0.0, "条件付き"
    for w in MILD_GOOD:
        if w in c: return 0.5, w
    for w in NEUTRAL:
        if w in c: return 0.0, w
    b = next((w for w in BAD if w in c), None)
    if b in ("ない", "なかった") and re.search(r"(気にならない|問題ない|負けない|悪くない|下がらない|文句な)", c): b = None
    if b in ("ない", "なかった") and not re.search(r"(が|は|も)(ない|なかった)|(てい|て)(ない|なかった)", c): b = None  # 「出足がない」「届いていない」型のみ
    g = next((w for w in GOOD if w in (c.replace(b, "　") if b else c)), None)
    if b and g:
        return (-0.5, b) if c.rfind(b) > c.rfind(g) else (0.5, g)
    if b: return -1.0, b
    if g:
        if any(w in c for w in HOPE): return 0.0, "要望"
        return 1.0, g
    if any(w in c for w in HOPE): return -0.3, "要望"
    return None, None

def evaluate(text):
    """コメント文 → {観点: score(-1..1)}, 根拠リスト。透明なルール: 文節ごとに観点語と評価語を対応付ける。"""
    out, why = {}, []
    if not text: return {"aspects": {}, "total": 0.0, "label": "－", "evidence": []}
    t = text.translate(Z2H)
    clauses = [c for c in re.split(r"[。、！!？?\n]|けど|けれど|ですが|だが|ものの|(?<=[たいるだ])が|(?<=く)て|(?<=い)し(?=[^っか])", t) if c.strip()]
    for c in clauses:
        asp = [a for a, kws in ASPECTS.items() if a != "総合" and any(k in c for k in kws)]
        if not asp and any(k in c for k in ASPECTS["総合"]): asp = ["総合"]
        if not asp: continue
        p, w = _pol(c)
        if p is None: continue
        for a in asp:
            out[a] = max(-1.0, min(1.0, out.get(a, 0) + p))
        why.append(f"「{c.strip()[:24]}」→{'・'.join(asp)}{'+' if p > 0 else ('±' if p == 0 else '−')}({w})")
    total = round(sum(out.values()), 2)
    label = "◎好気配" if total >= 1.5 else "○良好" if total >= 0.5 else "▲不安" if total <= -1.0 else "△やや不安" if total <= -0.5 else "－普通"
    return {"aspects": out, "total": total, "label": label, "evidence": why}

# ---------------- 取得 ----------------
def S(h): return BeautifulSoup(h, "lxml")
def T(e): return re.sub(r"\s+", " ", e.get_text(" ", strip=True)).strip() if e else ""

def parse_cyokuzen(h):
    """直前情報ページの 選手コメント 表 → {枠: {"zenjitsu": str, "chokuzen": str, "chokuzen_time": str}}"""
    s = S(h); res = {}
    for t in s.select("table"):
        if "選手コメント" not in T(t.select_one("thead") or t)[:30]: continue
        for tr in t.select("tbody tr"):
            wk = tr.select_one("td.waku")
            if not wk: continue
            w = int(T(wk).translate(Z2H) or 0)
            item = tr.select_one(".history_item")  # 最新日
            zen, cho = T(tr.select_one(".zComment")), ""
            if item:
                ps = item.select(".item-comment p")
                zen = T(ps[0]) if ps else zen
                acc = item.select_one(".item-comment p.u-accent"); cho = T(acc) if acc else ""
                date = T(item.select_one(".item-date"))
            else: date = ""
            m = re.search(r"（(\d{1,2})[：:](\d{2})現在）", cho)
            res[w] = {"zenjitsu": zen if zen != cho else "", "chokuzen": re.sub(r"（[^）]*現在）", "", cho).strip(), "chokuzen_time": f"{m.group(1)}:{m.group(2)}" if m else "", "date": date}
    return res

def parse_allracers(h):
    s = S(h); res = {}
    for t in s.select("table"):
        th = T(t.select_one("thead") or t)[:40]
        if "登番" not in th or "コメント" not in th: continue
        for tr in t.select("tbody tr"):
            tds = tr.select("td"); 
            if len(tds) < 2: continue
            m = re.match(r"(\d{4})", T(tds[0]).translate(Z2H))
            if not m: continue
            txts = [T(td) for td in tds[1:] if T(td) and "出足 ：" not in T(td)]
            c = next((x for x in txts if len(x) > 4), "")
            if c and "帰郷" not in c: res[m.group(1)] = c
    return res

def page_date_ok(h, hd):
    d = dt.date(int(hd[:4]), int(hd[4:6]), int(hd[6:])); h = T(S(h))[:3000]
    return bool(re.search(rf"{d.month}\s*/\s*{d.day}\s*[（(]", h)) or f"{d.year}/{d.month:02d}/{d.day:02d}" in h

def collect_venue(jcd, hd, nraces=12):
    base = SITES[jcd]; out = {"jcd": jcd, "site": base, "robots": None, "races": {}, "by_toban": {}, "sources": [], "note": ""}
    rb = bhttp.get(base + "/robots.txt", max_age=86400)
    out["robots"] = re.sub(r"\s+", " ", rb)[:200] if rb else "robots.txt なし(404等)"
    if rb and re.search(r"Disallow:\s*/sp/?\s", rb + " "): out["note"] = "robots.txtで/sp/が禁止のため取得せず"; return out
    for pg in ("raceinfo-racers_comment", "raceinfo-racer_comment"):
        h = bhttp.get(f"{base}/sp/index.php?page={pg}", max_age=MAX_AGE)
        if h and page_date_ok(h, hd):
            d = parse_allracers(h)
            if d: out["by_toban"].update(d); out["sources"].append(f"{base}/sp/index.php?page={pg}"); break
    has = lambda p: any((x.get("zenjitsu") or x.get("chokuzen")) for x in p.values())
    probe = {}; section = False
    for r in (1, nraces):  # 1Rが空でも最終Rに載ることがあるため2本だけ確認
        h = bhttp.get(f"{base}/sp/index.php?page=yosou-cyokuzen&race={r}", max_age=MAX_AGE)
        if h and "選手コメント" in h: section = True
        probe[r] = parse_cyokuzen(h) if h else {}
        if has(probe[r]): break
    if any(has(p) for p in probe.values()):
        for r in range(1, nraces + 1):
            if r in probe: out["races"][r] = probe[r]; continue
            h = bhttp.get(f"{base}/sp/index.php?page=yosou-cyokuzen&race={r}", max_age=MAX_AGE)
            if h: out["races"][r] = parse_cyokuzen(h)
        out["sources"].append(f"{base}/sp/index.php?page=yosou-cyokuzen&race=N")
    elif section and "更新までしばらくお待ちください" in (h or ""):
        out["note"] = "直前情報ページに選手コメント欄はあるが未更新(更新までしばらくお待ちください)"
    n = sum(1 for r in out["races"].values() for x in r.values() if x.get("zenjitsu") or x.get("chokuzen"))
    out["status"] = "ok" if (n or out["by_toban"]) else ("pending" if out["note"] else "none")
    out["checked_at"] = dt.datetime.now(JST).isoformat(timespec="minutes")
    return out

def main(hd):
    vj = json.load(open(os.path.join(ROOT, "cache", "json", hd, "_venues.json"), encoding="utf-8"))
    today = {v["jcd"]: len(v.get("deadlines") or []) or 12 for v in vj["venues"]}
    targets = [j for j in today if j in SITES]
    with ThreadPoolExecutor(5) as ex:
        res = dict(zip(targets, ex.map(lambda j: collect_venue(j, hd, today[j]), targets)))
    out = {"hd": hd, "collected_at": dt.datetime.now(JST).isoformat(timespec="seconds"), "venues": res,
           "not_covered": {j: NOT_COVERED.get(j, "対応サイト未登録") for j in today if j not in SITES}}
    json.dump(out, open(os.path.join(ROOT, "cache", "json", hd, "_comments.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for j, v in res.items():
        n = sum(1 for r in v["races"].values() for x in r.values() if x.get("zenjitsu") or x.get("chokuzen"))
        print(f"{j}: レース別 {n}件 / 全選手 {len(v['by_toban'])}名 {v['note']}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else dt.datetime.now(JST).strftime("%Y%m%d"))
