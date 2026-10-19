"""Polite HTTP helper: disk cache + per-host rate limit (>=1.0s between request starts)."""
import os, time, hashlib, threading, requests
from urllib.parse import urlparse
UA = "Mozilla/5.0 (compatible; personal-boatrace-notes/0.1; low-rate, cached)"
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "html")
os.makedirs(CACHE, exist_ok=True)
_lock = threading.Lock()
_next = {}
_local = threading.local()
STATS = {"net": 0, "cache": 0, "fail": 0}

def _session():
    if not hasattr(_local, "s"):
        _local.s = requests.Session(); _local.s.headers["User-Agent"] = UA
    return _local.s

def cache_path(url):
    return os.path.join(CACHE, hashlib.md5(url.encode()).hexdigest() + ".html")

def get(url, max_age=None, interval=1.0):
    """GET with disk cache. max_age: seconds a cached copy stays fresh (None=forever, 0=always refetch)."""
    fn = cache_path(url)
    if os.path.exists(fn) and (max_age is None or time.time() - os.path.getmtime(fn) < max_age):
        STATS["cache"] += 1
        return open(fn, encoding="utf-8").read()
    host = urlparse(url).netloc
    for i in range(3):
        with _lock:  # reserve a start slot for this host
            now = time.time(); t = max(now, _next.get(host, 0)); _next[host] = t + interval
        if t > now: time.sleep(t - now)
        try:
            r = _session().get(url, timeout=40)
            if r.encoding in (None, "ISO-8859-1"): r.encoding = r.apparent_encoding
            STATS["net"] += 1
            if r.status_code == 200:
                with open(fn, "w", encoding="utf-8") as f: f.write(r.text)
                return r.text
            if r.status_code in (403, 404, 410): break
        except requests.RequestException:
            pass
        time.sleep(3 + 3 * i)
    STATS["fail"] += 1
    if os.path.exists(fn):  # stale cache better than nothing
        return open(fn, encoding="utf-8").read()
    return None
