# 競艇ナビ (boatrace tool)

- `fetch.py [YYYYMMDD]` … boatrace.jp 公開ページ取得 (開催一覧 / pcexpect=出走表+公式PC予想 / beforeinfo / odds3t / odds2tf / raceresult / 場別データ)。
  robots.txt は全許可。1ホストあたり開始間隔≥1秒、HTMLは cache/html/、パース結果は cache/json/YYYYMMDD/。
- `media.py [YYYYMMDD]` … マクール無料ページのみ (予想ページ注目レース, 無料予想(場提供/地元専門紙), 若松予想サイト, ニュース見出し+冒頭)。
- `model.py` … 透明スコアリングモデル。`calibrate.py YYYYMMDD` で確定レースの対数尤度を確認。
- `build.py [YYYYMMDD]` → `site/data/YYYYMMDD.json`, `site/data/dates.json`
- `daily_summary.py [YYYYMMDD] [--refresh]` … チャット送信用サマリー
- `run.sh [YYYYMMDD]` … 一括実行
- サイト: `cd site && python3 -m http.server 18790` → http://localhost:18790/
- スクショ: `node shots.js YYYYMMDD JCD RNO` → shots/
- `tenji_refresh.sh [YYYYMMDD]` … 展示タイム専用の高速更新(fetch.py --ex-only → build → 変化時のみ deploy)。5分間隔向け。
