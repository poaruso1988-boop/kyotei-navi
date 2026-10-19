#!/usr/bin/env python3
"""今日のおすすめレースをチャット送信向けの短い日本語テキストで出力する。
usage: python3 daily_summary.py [YYYYMMDD] [--refresh] [--top 5]
  --refresh : fetch.py → media.py → build.py を先に実行して最新化する
"""
import os, sys, json, argparse, subprocess, datetime as dt
ROOT = os.path.dirname(os.path.abspath(__file__))
JST = dt.timezone(dt.timedelta(hours=9))
W = "日月火水木金土"

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("hd", nargs="?", default=dt.datetime.now(JST).strftime("%Y%m%d"))
    ap.add_argument("--refresh", action="store_true"); ap.add_argument("--top", type=int, default=5)
    a = ap.parse_args(); hd = a.hd
    if a.refresh:
        for cmd in (["fetch.py", hd], ["media.py", hd], ["build.py", hd]):
            subprocess.run([sys.executable, os.path.join(ROOT, cmd[0])] + cmd[1:], cwd=ROOT, check=False, stdout=subprocess.DEVNULL)
    p = os.path.join(ROOT, "site", "data", f"{hd}.json")
    if not os.path.exists(p): print(f"{hd} のデータがありません。build.py を実行してください。"); return
    d = json.load(open(p, encoding="utf-8"))
    day = dt.date(int(hd[:4]), int(hd[4:6]), int(hd[6:]))
    V = {v["jcd"]: v for v in d["venues"]}
    lines = [f"🚤 {day.month}/{day.day}({W[(day.weekday()+1)%7]}) 本日の注目レース（{len(d['venues'])}場開催）"]
    for i, pk in enumerate(d["picks"][:a.top], 1):
        v = V[pk["jcd"]]; r = next(x for x in v["races"] if x["rno"] == pk["rno"]); an = r["analysis"]
        hon = " / ".join(x["combo"] for x in an["rec"]["honmei"])
        ni = " / ".join(x["combo"] for x in an["rec"]["nitan"][:2])
        reason = an["comment"].split("。")[0] + "。"
        if len(reason) > 70: reason = reason[:68] + "…"
        fav = max(r["boats"], key=lambda b: b["p_win"])
        lines.append(f"{i}. {v['name']}{r['rno']}R {r['deadline']}締切【{an['confidence']}】")
        lines.append(f"   3連単 {hon}｜2連単 {ni}")
        lines.append(f"   {reason}")
        cm = [b for b in r["boats"] if b.get("comment") and abs((b.get("parts") or {}).get("comment") or 0) >= 0.08]
        cm.sort(key=lambda b: -b["p_win"])
        for b in cm[:1]:
            c = b["comment"].get("chokuzen") or b["comment"].get("zenjitsu")
            t = c["text"] if len(c["text"]) <= 34 else c["text"][:33] + "…"
            lines.append(f"   💬{b['waku']}号艇{b['name'].split(' ')[0]}「{t}」→{c['eval']['label']}")
    if d.get("values"):
        vs = "、".join(f"{x['venue']}{x['rno']}R {x['bet']}{x['combo']}({x['odds']}倍)" for x in d["values"][:3])
        lines.append(f"💰 妙味: {vs}  ※{(d.get('fetched_at') or '')[11:16]}取得時点のオッズ(締切まで変動)")
    ap = d.get("ana_picks") or {}
    if ap.get("中穴") or ap.get("大穴"):
        lines.append("🎯 穴狙い（高リスク・少額向け／中穴=3連単20〜100倍・大穴=100倍以上）")
        for t in ("中穴", "大穴"):
            for x in (ap.get(t) or [])[:3]:
                tk = " ".join(f"{k['combo']}({k['odds']:.0f}倍)" for k in x["tickets"][:3])
                lines.append(f"  {t} {x['venue']}{x['rno']}R {x['deadline']} 荒れ度{x['score']}: {tk}")
                lines.append(f"     {' / '.join(x['reasons'][:2])}")
        bt = d.get("ana_backtest") or {}
        if bt.get("候補", {}).get("races"):
            c, o = bt["候補"], bt["その他"]
            lines.append(f"   ※本日確定分: 候補{c['races']}Rの中穴以上決着 {(c['chuana']+c['oana'])*100//c['races']}% / 候補外 {(o['chuana']+o['oana'])*100//max(1,o['races'])}%（差は小さく参考程度）")
    s = d.get("day_stats", {})
    if s.get("finished"):
        lines.append(f"📊 本日確定{s['finished']}R: 本命艇1着 {s['fav_win']}R / 本命3連単的中 {s['honmei_hit']}R")
    lines.append("※公開データによる機械的な参考予想です。的中を保証しません。")
    print("\n".join(lines))

if __name__ == "__main__":
    main()
