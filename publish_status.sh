#!/bin/sh
# 公開URLを表示し、稼働とデータ鮮度を確認。落ちている/古い場合は再デプロイする。
cd "$(dirname "$0")"
URL=$(python3 -c "import json;print(json.load(open('publish/publish.json'))['url'])")
REPO=$(python3 -c "import json;print(json.load(open('publish/publish.json'))['repo'])")
echo "公開URL: $URL"
code=$(curl -s -o /dev/null -m 20 -w "%{http_code}" "$URL")
remote=$(curl -s -m 20 "${URL}data/key.json?t=$(date +%s)" | python3 -c "import sys,json;print(json.load(sys.stdin).get('deployed_at',''))" 2>/dev/null)
local_gen=$(ls -t site/data/2*.json 2>/dev/null | head -1)
echo "HTTP $code / 公開データのデプロイ時刻: ${remote:-不明} / ローカル最新: $(basename "$local_gen" 2>/dev/null)"
need=0
[ "$code" != "200" ] && need=1
if [ -n "$local_gen" ] && [ -n "$remote" ]; then
  python3 - "$local_gen" "$remote" <<'P' || need=1
import os, sys, datetime as dt
mt = dt.datetime.fromtimestamp(os.path.getmtime(sys.argv[1]), dt.timezone.utc)
sys.exit(1 if mt > dt.datetime.fromisoformat(sys.argv[2]) + dt.timedelta(seconds=60) else 0)
P
fi
if [ $need = 1 ]; then
  echo "→ 停止またはデータが古いため再デプロイします"
  python3 publish/deploy.py && gh api "repos/$REPO/pages" --jq '"Pages status: "+.status' 2>/dev/null
  sleep 60; echo "再確認: HTTP $(curl -s -o /dev/null -m 20 -w '%{http_code}' "$URL")"
else
  echo "OK: 稼働中・最新"
fi
