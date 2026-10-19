#!/bin/bash
# Refresh 競艇ナビ every 15 min between 09:00 and 22:59 JST
while true; do
  H=$(TZ=Asia/Tokyo date +%H)
  if [ "$H" -ge 9 ] && [ "$H" -le 22 ]; then
    /workspace/boatrace/refresh.sh >> /workspace/boatrace/refresh.log 2>&1
  fi
  sleep 900
done
