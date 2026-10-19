#!/usr/bin/env python3
"""site/data に過去日のデータが無い時(状態キャッシュ消失時)、公開サイトの暗号化データを KYOTEI_PW で復号して site/data/*.json を復元する。"""
import os, sys, json, base64, urllib.request
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = json.load(open(os.path.join(ROOT, "publish", "publish.json")))["url"]
SD = os.path.join(ROOT, "site", "data"); os.makedirs(SD, exist_ok=True)
def get(p): return urllib.request.urlopen(urllib.request.Request(URL + p, headers={"Cache-Control": "no-cache"}), timeout=30).read()
k = json.loads(get("data/key.json"))
aes = AESGCM(PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=base64.b64decode(k["salt"]), iterations=k["iter"]).derive(os.environ["KYOTEI_PW"].encode()))
dec = lambda b: aes.decrypt(b[:12], b[12:], None)
dates = json.loads(dec(get("data/dates.bin")))["dates"]
n = 0
for d in dates:
    fn = os.path.join(SD, f"{d}.json")
    if os.path.exists(fn): continue
    try: open(fn, "wb").write(dec(get(f"data/{d}.bin"))); n += 1
    except Exception as e: print(f"{d}: restore failed {e!r}")
print(f"restored {n} day(s) from live site (live dates: {len(dates)})")
