#!/bin/bash
# 状態(取得キャッシュ・本日分の解析JSON・site/data・展示署名)を暗号化して保存/復元する。
# 公開リポジトリの Actions cache は第三者のPR等から読める可能性があるため、必ず STATE_KEY (Actions secret) で AES-256 暗号化する。
#   ci/state.sh pack   → state.enc を作成 (古いキャッシュは削除してから)
#   ci/state.sh unpack → state.enc があれば展開。無ければ/失敗したら何もしない (後段で公開サイトから復元・full実行)
set -u
cd "$(dirname "$0")/.."
: "${STATE_KEY:?STATE_KEY not set}"
case "${1:-}" in
  pack)
    HD=$(TZ=Asia/Tokyo date +%Y%m%d); YD=$(TZ=Asia/Tokyo date -d yesterday +%Y%m%d)
    mkdir -p cache/html cache/json site/data publish
    for d in cache/json/*/; do b=$(basename "$d"); [ "$b" = "$HD" ] || [ "$b" = "$YD" ] || rm -rf "$d"; done
    find cache/html -type f -mmin +1800 -delete            # 30時間より古いHTMLキャッシュは捨てる
    ls site/data/2*.json 2>/dev/null | sort -r | tail -n +15 | xargs -r rm -f   # 公開は直近14日分
    find publish -maxdepth 1 -name '.ex_sig_*' -mtime +2 -delete
    tar -czf - cache/html cache/json site/data $(ls publish/.ex_sig_* 2>/dev/null) \
      | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass env:STATE_KEY -out state.enc
    echo "state packed: $(du -h state.enc | cut -f1)" ;;
  unpack)
    if [ -f state.enc ]; then
      if openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:STATE_KEY -in state.enc | tar -xzf -; then
        echo "state restored ($(ls cache/html | wc -l) html, json days: $(ls cache/json | tr '\n' ' '))"
      else echo "state decrypt/extract failed (続行)"; fi
      rm -f state.enc
    else echo "no saved state (初回またはキャッシュ消失)"; fi ;;
  *) echo "usage: $0 pack|unpack"; exit 2 ;;
esac
