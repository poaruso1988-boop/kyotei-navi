#!/bin/sh
# 1日分を更新して公開: ./run.sh [YYYYMMDD]   (省略時は今日 JST)。 NO_DEPLOY=1 で公開をスキップ
cd "$(dirname "$0")"
HD=${1:-$(TZ=Asia/Tokyo date +%Y%m%d)}
python3 fetch.py "$HD" --workers 8 || exit 1
python3 media.py "$HD" || echo "media.py failed (続行)"
python3 comments.py "$HD" || echo "comments.py failed (続行)"
python3 build.py "$HD" || exit 1
[ -z "$NO_DEPLOY" ] && { python3 publish/deploy.py || echo "deploy failed"; }
python3 daily_summary.py "$HD"
