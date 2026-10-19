#!/bin/sh
# 日中の軽量更新: 直前情報・オッズ・結果・選手コメントを更新して再公開する（定期実行向け, 10〜15分間隔推奨）
#   ./refresh.sh [YYYYMMDD]      省略時は今日(JST)
#   NO_DEPLOY=1 で公開スキップ / WITH_MEDIA=1 でメディア(マクール無料部分)も更新 / WINDOW=3 で再取得対象(締切まで◯時間以内)
# 確定済みレースと締切まで WINDOW 時間より先のレースは前回取得分を再利用。各ホスト1秒以上間隔・キャッシュ有り。
cd "$(dirname "$0")"
HD=${1:-$(TZ=Asia/Tokyo date +%Y%m%d)}
exec 9>/tmp/kyotei-navi-refresh.lock
flock -n 9 || { echo "別の更新が実行中のためスキップ"; exit 0; }
T0=$(date +%s)
if [ ! -f "cache/json/$HD/_all.json" ]; then echo "本日初回のため通常更新(run.sh)を実行"; exec ./run.sh "$HD"; fi
python3 fetch.py "$HD" --workers 8 --intraday --window "${WINDOW:-3}" || exit 1
[ -n "$WITH_MEDIA" ] && { python3 media.py "$HD" || echo "media.py failed (続行)"; }
COMMENTS_MAX_AGE=600 python3 comments.py "$HD" || echo "comments.py failed (続行)"
python3 build.py "$HD" || exit 1
[ -z "$NO_DEPLOY" ] && { python3 publish/deploy.py && python3 ex_sig.py "$HD" > "publish/.ex_sig_$HD" || echo "deploy failed"; }
echo "refresh done in $(( $(date +%s) - T0 ))s"
