#!/usr/bin/env python3
"""site/ を暗号化して GitHub Pages リポジトリへデプロイする。
- HTML/CSS/JS はそのまま、data/*.json は AES-256-GCM で暗号化して data/*.bin に (鍵 = PBKDF2-SHA256(パスワード, salt, ITER))
- パスワードは ../.publish_pw、salt は publish/.salt (固定: 変えると端末保存の鍵が無効になる)
- 履歴肥大を避けるため毎回 orphan 1コミットで force-push (このツール専用リポジトリのみ)
usage: deploy.py [--no-push] [--keep-days 14]"""
import os, sys, json, glob, shutil, base64, subprocess, argparse, datetime as dt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
P = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(P)
SITE = os.path.join(ROOT, "site"); REPO = os.path.join(P, "repo")
CONF = json.load(open(os.path.join(P, "publish.json")))
ITER = 310000

def key():
    # GitHub Actions では環境変数 KYOTEI_PW / KYOTEI_SALT_B64 (Actions secrets) を使う。無ければ従来どおりファイル
    if os.environ.get("KYOTEI_SALT_B64"): salt = base64.b64decode(os.environ["KYOTEI_SALT_B64"])
    else:
        sp = os.path.join(P, ".salt")
        if not os.path.exists(sp): open(sp, "wb").write(os.urandom(16))
        salt = open(sp, "rb").read()
    pw = os.environ.get("KYOTEI_PW") or open(os.path.join(ROOT, ".publish_pw")).read().strip()
    k = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(pw.encode())
    return AESGCM(k), salt

def enc(aes, b):
    iv = os.urandom(12); return iv + aes.encrypt(iv, b, None)

def sh(*a, check=True): return subprocess.run(a, cwd=REPO, check=check, capture_output=True, text=True)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--no-push", action="store_true"); ap.add_argument("--keep-days", type=int, default=14)
    a = ap.parse_args()
    aes, salt = key()
    if not os.path.isdir(os.path.join(REPO, ".git")):
        os.makedirs(REPO, exist_ok=True); sh("git", "init", "-q", "-b", "main")
        sh("git", "remote", "add", "origin", f"https://github.com/{CONF['repo']}.git")
    sh("git", "config", "user.name", CONF["git_name"]); sh("git", "config", "user.email", CONF["git_email"])
    for f in os.listdir(REPO):
        if f != ".git": (shutil.rmtree if os.path.isdir(os.path.join(REPO, f)) else os.remove)(os.path.join(REPO, f))
    for f in ("index.html", "app.js", "style.css"): shutil.copy(os.path.join(SITE, f), REPO)
    open(os.path.join(REPO, ".nojekyll"), "w").close()
    open(os.path.join(REPO, "robots.txt"), "w").write("User-agent: *\nDisallow: /\n")
    os.makedirs(os.path.join(REPO, "data"))
    days = sorted((os.path.basename(p)[:8] for p in glob.glob(os.path.join(SITE, "data", "2*.json"))), reverse=True)[:a.keep_days]
    for d in days:
        open(os.path.join(REPO, "data", f"{d}.bin"), "wb").write(enc(aes, open(os.path.join(SITE, "data", f"{d}.json"), "rb").read()))
    open(os.path.join(REPO, "data", "dates.bin"), "wb").write(enc(aes, json.dumps({"dates": days, "latest": days[0] if days else None}).encode()))
    json.dump({"v": 1, "salt": base64.b64encode(salt).decode(), "iter": ITER, "check": base64.b64encode(enc(aes, b"ok")).decode(),
               "deployed_at": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec="seconds")},
              open(os.path.join(REPO, "data", "key.json"), "w"))
    print(f"built {len(days)} day(s): {', '.join(days)}")
    if a.no_push: return
    sh("git", "checkout", "-q", "--orphan", "deploy-tmp")
    sh("git", "add", "-A"); sh("git", "commit", "-q", "-m", f"deploy {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')}Z")
    sh("git", "branch", "-D", "main", check=False); sh("git", "branch", "-m", "main")
    r = subprocess.run(["git", "-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential", "push", "-q", "-f", "origin", "main"], cwd=REPO, capture_output=True, text=True)
    if r.returncode: sys.exit("push failed: " + r.stderr[-500:])
    print("pushed to", CONF["repo"], "->", CONF["url"])

if __name__ == "__main__":
    main()
