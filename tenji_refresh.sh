#!/bin/sh
# 展示タイム専用の高速更新: 締切まで EX_WINDOW 分以内の未確定レースだけ直前情報(展示タイム・スタート展示・水面気象)を再取得し、
# 予想を再計算。展示データが新たに出た/変わった時だけ公開(GitHub Pages)する。5分間隔での定期実行向け（1回 約20〜60秒）。
#   ./tenji_refresh.sh [YYYYMMDD]   省略時は今日(JST)
#   EX_WINDOW=50 (分) / NO_DEPLOY=1 / FORCE_DEPLOY=1 (変化が無くても公開)
# オッズ・結果・コメントは refresh.sh(15分間隔)側で更新。同じロックを使うので両方が同時に走ることはない。
cd "$(dirname "$0")"
HD=${1:-$(TZ=Asia/Tokyo date +%Y%m%d)}
exec 9>/tmp/kyotei-navi-refresh.lock
flock -n 9 || { echo "$(TZ=Asia/Tokyo date '+%F %T JST') 別の更新が実行中のためスキップ"; exit 0; }
T0=$(date +%s)
if [ ! -f "cache/json/$HD/_all.json" ]; then echo "$(TZ=Asia/Tokyo date '+%F %T JST') 本日の出走表が未取得のためスキップ（先に refresh.sh / run.sh を実行）"; exit 0; fi
python3 fetch.py "$HD" --workers 8 --ex-only --ex-window "${EX_WINDOW:-50}" || exit 1
python3 build.py "$HD" || exit 1
SIG=$(python3 ex_sig.py "$HD")
OLD=$(cat "publish/.ex_sig_$HD" 2>/dev/null)
if [ -n "$NO_DEPLOY" ]; then echo "NO_DEPLOY: 公開スキップ";
elif [ "$SIG" != "$OLD" ] || [ -n "$FORCE_DEPLOY" ]; then
  python3 publish/deploy.py && echo "$SIG" > "publish/.ex_sig_$HD" || echo "deploy failed"
else echo "展示データに変化なし: 公開スキップ"; fi
echo "$(TZ=Asia/Tokyo date '+%F %T JST') tenji refresh done in $(( $(date +%s) - T0 ))s"
