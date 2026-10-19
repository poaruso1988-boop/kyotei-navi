#!/usr/bin/env python3
"""site/data/YYYYMMDD.json の「展示反映済みレースと展示タイム/スタート展示」のハッシュを出力 (tenji_refresh.sh の公開要否判定用)。"""
import json, sys, hashlib
d = json.load(open(f"site/data/{sys.argv[1]}.json", encoding="utf-8"))
k = [(v["jcd"], r["rno"], [(b.get("before") or {}).get("ex_time") for b in r.get("boats", [])], [x.get("st") for x in (r.get("start_exhibition") or [])])
     for v in d["venues"] for r in v["races"] if r.get("ex_reflected")]
print(hashlib.md5(json.dumps(k).encode()).hexdigest())
