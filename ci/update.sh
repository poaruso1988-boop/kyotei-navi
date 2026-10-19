#!/bin/bash
# GitHub Actions 用の更新処理。 usage: ci/update.sh refresh|tenji|full
#   refresh … 直前情報・オッズ・結果・コメント (box の refresh.sh 相当, 15分ごと)
#   tenji   … 締切50分以内の展示タイムのみ。展示データが変化した時だけ公開 (box の tenji_refresh.sh 相当, 5分ごと)
#   full    … 1日分を最初から (本日の取得データが無い時は自動でこれになる)
# 公開(暗号化)は publish/deploy.py --no-push で publish/repo/ に生成し、ワークフローが actions/deploy-pages で配信する。
# 結果 deploy=true|false を $GITHUB_OUTPUT に書く。予想内容はログに出さない(公開リポジトリのログは誰でも見られる)。
set -u
cd "$(dirname "$0")/.."
MODE=${1:-refresh}
HD=$(TZ=Asia/Tokyo date +%Y%m%d)
OUT=${GITHUB_OUTPUT:-/dev/null}
log(){ echo "$(TZ=Asia/Tokyo date '+%F %T JST') $*"; }
T0=$(date +%s)
[ -f "cache/json/$HD/_all.json" ] || { [ "$MODE" != full ] && log "本日($HD)の取得データが無いため full で実行"; MODE=full; }
DEPLOY=0
case "$MODE" in
  full)
    python3 fetch.py "$HD" --workers 8 || exit 1
    python3 media.py "$HD" >/dev/null || echo "media.py failed (続行)"
    python3 comments.py "$HD" || echo "comments.py failed (続行)"
    DEPLOY=1 ;;
  refresh)
    python3 fetch.py "$HD" --workers 8 --intraday --window "${WINDOW:-3}" || exit 1
    COMMENTS_MAX_AGE=600 python3 comments.py "$HD" || echo "comments.py failed (続行)"
    DEPLOY=1 ;;
  tenji)
    python3 fetch.py "$HD" --workers 8 --ex-only --ex-window "${EX_WINDOW:-50}" || exit 1 ;;
  *) echo "unknown mode $MODE"; exit 2 ;;
esac
python3 build.py "$HD" || exit 1
SIG=$(python3 ex_sig.py "$HD"); OLD=$(cat "publish/.ex_sig_$HD" 2>/dev/null || true)
if [ "$MODE" = tenji ]; then
  if [ "$SIG" != "$OLD" ] || [ -n "${FORCE_DEPLOY:-}" ]; then DEPLOY=1; else log "展示データに変化なし: 公開スキップ"; fi
fi
if [ $DEPLOY = 1 ]; then
  python3 publish/deploy.py --no-push || exit 1
  rm -rf publish/repo/.git
  echo "$SIG" > "publish/.ex_sig_$HD"
  echo "deploy=true" >> "$OUT"
else
  echo "deploy=false" >> "$OUT"
fi
log "$MODE done in $(( $(date +%s) - T0 ))s (deploy=$DEPLOY)"
