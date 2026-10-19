#!/bin/bash
# 展示タイム高速更新: 09:00-22:59 JST に5分ごと
while true; do
  H=$(TZ=Asia/Tokyo date +%H)
  if [ "$H" -ge 9 ] && [ "$H" -le 22 ]; then
    /workspace/boatrace/tenji_refresh.sh >> /workspace/boatrace/tenji.log 2>&1
  fi
  sleep 300
done
