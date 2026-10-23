"use strict";
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const pct = (p, d = 0) => p == null ? "-" : (p * 100).toFixed(d) + "%";
const fx = (v, d = 2) => v == null || v === "" ? "-" : Number(v).toFixed(d);
const fmtDate = hd => `${hd.slice(0,4)}/${+hd.slice(4,6)}/${+hd.slice(6)}(${"日月火水木金土"[new Date(+hd.slice(0,4), +hd.slice(4,6)-1, +hd.slice(6)).getDay()]})`;
const W = n => `<span class="waku w${n}">${n}</span>`;
const combo = c => `<span class="combo">${String(c).split("-").map(W).join('<span class="sep">-</span>')}</span>`;
const CONF = {"鉄板":"b-teppan","混戦":"b-konsen","荒れそう":"b-are"};
const confB = l => l ? `<span class="badge ${CONF[l]||""}">${l}</span>` : "";
let DATES = [], DATA = {}, CUR = null;

function jstToday(){ const d = new Date(Date.now() + 9*3600e3); return d.toISOString().slice(0,10).replace(/-/g,""); }
/* ---- 公開版: data/key.json があれば暗号化モード (AES-GCM, PBKDF2-SHA256) ---- */
let ENC = null, KEY = null;
const b64d = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
async function deriveKey(pw){
  const base = await crypto.subtle.importKey("raw", new TextEncoder().encode(pw), "PBKDF2", false, ["deriveKey"]);
  return crypto.subtle.deriveKey({name:"PBKDF2", salt:b64d(ENC.salt), iterations:ENC.iter, hash:"SHA-256"}, base, {name:"AES-GCM", length:256}, true, ["decrypt"]);
}
async function decBytes(buf){
  const u = new Uint8Array(buf);
  return new TextDecoder().decode(await crypto.subtle.decrypt({name:"AES-GCM", iv:u.slice(0,12)}, KEY, u.slice(12)));
}
async function tryKey(k){ KEY = k; try { return (await decBytes(b64d(ENC.check))) === "ok"; } catch(e){ KEY = null; return false; } }
function login(){
  return new Promise(resolve => {
    $("#app").innerHTML = `<div class="card" style="margin-top:30px"><h2 class="sec" style="margin-top:0">🔒 パスワード</h2>
      <form id="lf"><input id="pw" type="password" autocomplete="current-password" autocapitalize="off" autocorrect="off" spellcheck="false" placeholder="パスワード"
        style="width:100%;font-size:16px;padding:10px;border:1px solid var(--line);border-radius:10px">
      <label class="small" style="display:block;margin:8px 0"><input type="checkbox" id="rem" checked> この端末に保存する</label>
      <button style="width:100%;padding:11px;border:0;border-radius:10px;background:var(--navy2);color:#fff;font-size:16px;font-weight:700">開く</button>
      <div id="lerr" class="small" style="color:var(--bad);margin-top:6px"></div></form></div>`;
    $("#lf").onsubmit = async e => {
      e.preventDefault(); $("#lerr").textContent = "確認中…";
      const k = await deriveKey($("#pw").value.trim());
      if (await tryKey(k)) {
        if ($("#rem").checked) { const raw = new Uint8Array(await crypto.subtle.exportKey("raw", k)); localStorage.setItem("kn_key", btoa(String.fromCharCode(...raw)) + "|" + ENC.salt); }
        resolve();
      } else $("#lerr").textContent = "パスワードが違います";
    };
  });
}
async function ensureKey(){
  if (KEY) return;
  const saved = (localStorage.getItem("kn_key") || "").split("|");
  if (saved[0] && saved[1] === ENC.salt) {
    const k = await crypto.subtle.importKey("raw", b64d(saved[0]), {name:"AES-GCM"}, true, ["decrypt"]);
    if (await tryKey(k)) return;
  }
  await login();
}
async function getJSON(u){
  if (ENC === null) { try { const r = await fetch("data/key.json", {cache:"no-cache"}); ENC = r.ok ? await r.json() : false; } catch(e){ ENC = false; } }
  if (!ENC) { const r = await fetch(u, {cache:"no-cache"}); if(!r.ok) throw new Error(r.status); return r.json(); }
  await ensureKey();
  const r = await fetch(u.replace(/\.json$/, ".bin"), {cache:"no-cache"}); if(!r.ok) throw new Error(r.status);
  return JSON.parse(await decBytes(await r.arrayBuffer()));
}
function logout(){ localStorage.removeItem("kn_key"); location.reload(); }
async function loadDay(hd){
  if (!DATA[hd]) DATA[hd] = await getJSON(`data/${hd}.json`);
  return DATA[hd];
}
function parseHash(){
  const p = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  let hd = /^\d{8}$/.test(p[0]) ? p.shift() : null;
  return {hd, view: p[0] || "picks", a: p[1], b: p[2]};
}
function go(hd, view, a, b){ location.hash = "#/" + [hd, view, a, b].filter(x => x != null).join("/"); }
function venue(d, jcd){ return d.venues.find(v => v.jcd === jcd); }
function race(d, jcd, rno){ const v = venue(d, jcd); return v && v.races.find(r => r.rno == rno); }

function setChrome(hd, view, crumbs){
  const sel = $("#dateSel");
  sel.innerHTML = DATES.map(x => `<option value="${x}" ${x===hd?"selected":""}>${fmtDate(x)}</option>`).join("");
  if (!DATES.includes(hd)) sel.insertAdjacentHTML("afterbegin", `<option selected>${fmtDate(hd)}</option>`);
  ["picks","venues","about"].forEach(t => $("#tab-"+t).classList.toggle("on", t === view || (t==="venues" && (view==="v"||view==="r"))));
  ["picks","venues","about"].forEach(t => $("#tab-"+t).href = `#/${hd}/${t}`);
  $("#brand").href = `#/${hd}/picks`;
  $("#crumbs").innerHTML = crumbs || "";
}

function statusBadge(r){
  if (r.status === "finished") return `<span class="badge b-fin">確定</span>`;
  if (r.status === "closed") return `<span class="badge b-fin">締切</span>`;
  if (r.status === "nodata") return `<span class="badge b-fin">データなし</span>`;
  return `<span class="badge b-up">発売中</span>`;
}
function exBadge(r){
  if (!r.analysis || r.status === "finished" || r.status === "nodata") return "";
  return r.ex_reflected ? `<span class="badge b-ex">展示反映済み</span>` : `<span class="badge b-pre">展示前</span>`;
}
function exBlock(r){
  const an = r.analysis, t = r.before_checked_at ? String(r.before_checked_at).slice(11,16) : "";
  const hasOri = r.boats.some(b => b.original);
  if (!r.ex_reflected) return `<h2 class="sec">展示タイム <span class="badge b-pre">展示前</span></h2><div class="card">
    <div class="small">⏳ 展示タイムはまだ発表されていません（締切の約20〜30分前に発表）。いまの予想は<b>展示なし</b>で計算しています。発表後の自動更新で予想に反映されます。</div>
    ${t?`<div class="muted" style="margin-top:4px">直前情報の最終確認 ${esc(t)}</div>`:""}</div>`;
  const pre = an.pre || null, fav = r.boats.reduce((a, b) => (b.p_win > a.p_win ? b : a));
  const cells = [...r.boats].map(b => { const bf = b.before || {}, o = b.original || {};
    return `<div class="exc ${b.ex_rank===1?"top":""}">${W(b.waku)}<b>${bf.ex_time?fx(bf.ex_time):"-"}</b><span class="lo">${b.ex_rank?b.ex_rank+"位":""}</span>
      ${(b.parts||{}).ex_time!=null||(b.parts||{}).ex_rank!=null?`<span class="exp ${((b.parts.ex_time||0)+(b.parts.ex_rank||0))>=0?"pl":"mi"}">${((b.parts.ex_time||0)+(b.parts.ex_rank||0))>=0?"+":""}${((b.parts.ex_time||0)+(b.parts.ex_rank||0)).toFixed(2)}</span>`:""}
      ${hasOri?`<span class="lo ori">${o.half!=null?"半周"+fx(o.half):""}<br>${o.mawari!=null?"回り"+fx(o.mawari):""}<br>${o.straight!=null?"直線"+fx(o.straight):""}</span>`:""}</div>`; }).join("");
  let cmp = "";
  if (pre) {
    const same = pre.fav === fav.waku, hon = an.rec.honmei.map(x => x.combo);
    cmp = `<div class="small" style="margin-top:8px"><b>展示前→展示後</b>：本命艇 ${W(pre.fav)}${pct(pre.fav_p)} → ${W(fav.waku)}${pct(fav.p_win)} ${same?'<span class="muted">（変わらず）</span>':'<span class="badge b-are">本命変更</span>'}</div>
      <div class="small">本命3連単 展示前 ${pre.honmei.map(esc).join(" / ")}${pre.honmei.join()===hon.join()?' <span class="muted">（同じ）</span>':` → 展示後 <b>${hon.map(esc).join(" / ")}</b>`}</div>`;
  }
  return `<h2 class="sec">展示タイム <span class="badge b-ex">展示反映済み</span></h2><div class="card">
    <div class="exg">${cells}</div>${cmp}
    <div class="muted" style="margin-top:6px">数字の下の±＝展示による能力スコア補正（レース平均より0.05秒速いごと+0.12・±0.10秒で頭打ち、順位1位+0.08〜6位-0.08）。${hasOri?"半周・回り足・直線は場の独自計測値で、表示のみ（予想には未使用）。":""}${t?"最終確認 "+esc(t):""}</div></div>`;
}
function betRow(lab, x){
  const v = x.ev != null && x.ev >= 1;
  return `<div class="betrow ${v?"value":""}">${combo(x.combo)}
    <span class="nums">推定 <b>${pct(x.prob,1)}</b>${x.pb!=null?` <span class="lo">補正${pct(x.pb,1)}</span>`:""}<br>${x.odds?`${x.odds}倍`:"オッズ未取得"}${x.ev!=null?` ・ EV <b>${x.ev.toFixed(2)}</b>`:""}</span>${v?`<span class="badge b-value">妙味</span>`:""}</div>`;
}
function betsBlock(an, compact){
  const rc = an.rec;
  const g = (cls, t, arr, lab) => arr.length ? `<div class="grp"><div class="grp-t ${cls}">${t}</div>${arr.map(x => betRow(lab, x)).join("")}</div>` : "";
  if (compact) return `<div class="grp-t h">本命 3連単</div><div class="chips">${rc.honmei.map(x=>combo(x.combo)).join("")}</div>
     <div class="grp-t n">2連単</div><div class="chips">${rc.nitan.slice(0,2).map(x=>combo(x.combo)).join("")}</div>`;
  return g("h","◎ 本命（3連単）", rc.honmei, "本命") + g("o","○ 押え（3連単）", rc.osae, "押え") +
    g("a",`☆ 穴（3連単）<span class="muted">${esc(rc.ana_basis)}</span>`, rc.ana, "穴") + g("n","2連単", rc.nitan, "2単");
}

/* ---------- views ---------- */
function anaTk(x){ return `<span class="atk">${combo(x.combo)}<span class="nums"><b>${x.odds}倍</b><br>補正${pct(x.pb,1)}・EV <b>${x.ev.toFixed(2)}</b></span></span>`; }
function anaSection(d){
  const ap = d.ana_picks, ar = d.ana_rules; if (!ap || !ar) return "";
  const tl = t => { const [lo,hi] = ar.tiers[t]; return hi ? `${lo}〜${hi}倍未満` : `${lo}倍以上`; };
  let h = `<h2 class="sec">🎯 穴狙い <span class="badge b-risk">高リスク</span></h2>
    <div class="card small risk-note">荒れ度${ar.threshold}以上の未発走レースから、3連単オッズ帯別に補正期待値の高い目を表示。<b>的中率は低く、外れが続く前提の少額向け</b>です。</div>`;
  for (const t of ["中穴","大穴"]) {
    const L = ap[t] || [];
    h += `<div class="ana-t">${t}（3連単 ${tl(t)}）</div>`;
    if (!L.length) { h += `<div class="card empty">該当レースなし</div>`; continue; }
    h += L.map(x => `<a class="card ana" href="#/${d.hd}/r/${x.jcd}/${x.rno}">
      <div class="head"><span class="vn">${esc(x.venue)}</span><span class="rn">${x.rno}R</span><span class="badge b-are">荒れ度 ${x.score}</span><span class="time">締切 ${esc(x.deadline)}</span></div>
      <div class="why">${x.reasons.slice(0,4).map(esc).join(" / ")}</div>
      <div class="atks">${x.tickets.map(anaTk).join("")}</div>
      <div class="muted">この帯で決まる推定確率 ${pct(x.p_tier,0)} ・ オッズ ${esc((x.odds_updated||"").replace(/^.*?(\d+:\d+).*$/,"$1")||"取得時点")}</div></a>`).join("");
  }
  const bt = d.ana_backtest;
  if (bt && bt["候補"]) { const c = bt["候補"], o = bt["その他"], r = (a,b)=> b?Math.round(a/b*100)+"%":"-";
    h += `<div class="card small muted">本日の検証（確定レース）: 候補${c.races}Rの配当 中穴${r(c.chuana,c.races)}・万舟${r(c.oana,c.races)} ／ 候補外${o.races}R 中穴${r(o.chuana,o.races)}・万舟${r(o.oana,o.races)}。穴買い目の回収率 中穴${r(bt["tickets_中穴"].return_yen,bt["tickets_中穴"].stake_yen)}・大穴${r(bt["tickets_大穴"].return_yen,bt["tickets_大穴"].stake_yen)}（${bt["tickets_中穴"].hits+bt["tickets_大穴"].hits}本的中）。${esc(bt.note)}</div>`; }
  return h;
}
function anaRace(d, r){
  const a = r.analysis && r.analysis.ana; if (!a) return "";
  const flag = a.score >= d.ana_rules.threshold;
  let h = `<h2 class="sec">荒れ度・穴狙い ${flag?'<span class="badge b-risk">穴狙い候補</span>':""}</h2><div class="card">
    <div class="row"><span class="badge b-are" style="font-size:14px">荒れ度 ${a.score}</span><span class="muted" style="margin-left:8px">候補基準 ${d.ana_rules.threshold}以上${a.has_odds?` ・ 20〜100倍で決着 ${pct(a.p_tier["中穴"],0)} / 100倍以上 ${pct(a.p_tier["大穴"],0)}`:""}</span></div>
    <div class="why">${a.reasons.length?a.reasons.map(esc).join(" / "):"荒れる要素は少なめ"}</div>`;
  if (a.has_odds) for (const t of ["中穴","大穴"]) h += `<div class="grp-t">${t}${(a.tickets[t]||[]).length?"":"：条件を満たす目なし"}</div><div class="atks">${(a.tickets[t]||[]).map(anaTk).join("")}</div>`;
  else h += `<div class="muted">オッズ未取得のため穴の買い目は計算できません。</div>`;
  return h + `<div class="muted" style="margin-top:6px">⚠ 高リスク: 中穴=3連単20〜100倍、大穴=100倍以上。補正確率${Math.round(d.ana_rules.min_pb["中穴"]*100)}%/${(d.ana_rules.min_pb["大穴"]*100).toFixed(1)}%未満の目は除外。荒れ度の算出基準は「使い方」参照。</div></div>`;
}
function viewPicks(d){
  const s = d.day_stats;
  let h = `<div class="hero"><h1>${fmtDate(d.hd)} 今日のおすすめ</h1>
    <div class="small" style="opacity:.85">開催 ${d.venues.length}場 ・ データ取得 ${esc((d.fetched_at||"").slice(11,16))}</div>
    <div class="stats"><div><b>${s.upcoming}</b><span>発売中レース</span></div><div><b>${s.finished?Math.round(s.fav_win/s.finished*100)+"%":"-"}</b><span>本命艇1着率(確定${s.finished}R)</span></div><div><b>${s.honmei_hit}/${s.finished}</b><span>本命3連単的中</span></div></div>
    ${s.upcoming?`<div class="small" style="opacity:.85;margin-top:6px">発売中${s.upcoming}Rのうち 展示反映済み ${s.upcoming_ex??0}R（展示発表ごとに自動で予想を更新）</div>`:""}</div>`;
  h += `<h2 class="sec">自信度の高いレース TOP${d.picks.length}</h2>`;
  if (!d.picks.length) h += `<div class="card empty">対象レースがありません</div>`;
  d.picks.forEach((p, i) => {
    const r = race(d, p.jcd, p.rno), an = r.analysis;
    h += `<a class="card pick" href="#/${d.hd}/r/${p.jcd}/${p.rno}">
      <div class="head"><span class="badge b-grade">#${i+1}</span><span class="vn">${esc(p.venue)}</span><span class="rn">${p.rno}R</span>${confB(an.confidence)}${statusBadge(r)}${exBadge(r)}<span class="time">締切 ${esc(r.deadline)}</span></div>
      <div class="muted">${esc(r.race_title)} ${esc(r.distance)}</div>
      <div class="comment">${esc(an.comment)}</div>${betsBlock(an, true)}</a>`;
  });
  h += `<h2 class="sec">妙味あり（補正確率×オッズ ≥ 1.0）</h2>`;
  if (!d.values.length) h += `<div class="card empty">現時点で該当なし（オッズ未発売/取得前を含む）</div>`;
  else h += `<div class="card">${d.values.map(x => `<a class="betrow value" href="#/${d.hd}/r/${x.jcd}/${x.rno}"><span class="lab">${esc(x.venue)}<br>${x.rno}R</span>
      <span class="badge b-kind">${x.bet}</span>${combo(x.combo)}<span class="nums">補正 <b>${pct(x.pb,1)}</b> ・ ${x.odds}倍<br>EV <b>${x.ev.toFixed(2)}</b> ・ 締切${esc(x.deadline)}</span></a>`).join("")}
      <div class="muted" style="margin-top:6px">※ 補正確率＝モデルと市場オッズのブレンド。オッズは取得時点（${esc(d.fetched_at?.slice(11,16))}頃）のもので締切まで変動します。</div></div>`;
  h += anaSection(d);
  const feat = d.venues.flatMap(v => v.races.flatMap(r => (r.media||[]).filter(m => /注目/.test(m.source)).map(m => ({v, r, m}))));
  if (feat.length) {
    h += `<h2 class="sec">メディア注目レース</h2>`;
    feat.forEach(({v, r, m}) => h += `<a class="card media" href="#/${d.hd}/r/${v.jcd}/${r.rno}"><div class="mi" style="border:0"><span class="src">${esc(m.source)}</span>
      <div class="hl">${esc(v.name)} ${r.rno}R ${esc(m.headline)}</div><div class="sm">${esc(m.summary)}</div></div></a>`);
  }
  h += `<div class="disc">${esc(d.disclaimer)}</div>`;
  return h;
}

function viewVenues(d){
  let h = `<h2 class="sec">${fmtDate(d.hd)} 開催場（${d.venues.length}場）</h2><div class="vlist">`;
  d.venues.forEach(v => {
    const up = v.races.filter(r => r.status === "upcoming");
    const nx = up[0];
    const cnt = {"鉄板":0,"混戦":0,"荒れそう":0}; v.races.forEach(r => r.analysis && cnt[r.analysis.confidence]++);
    h += `<a class="card venue" href="#/${d.hd}/v/${v.jcd}"><div style="min-width:0;flex:1">
      <div class="row"><span class="vname">${esc(v.name)}</span><span class="badge b-grade b-${esc(v.grade.slice(0,2))}">${esc(v.grade)}</span><span class="badge b-kind">${esc(v.kind)}</span><span class="badge b-kind">${esc((v.period_day.split(" ")[1]||""))}</span></div>
      <div class="vtitle">${esc(v.title)}</div>
      <div class="small" style="margin-top:3px">${nx ? `次: <b>${nx.rno}R ${esc(nx.deadline)}</b>` : `<span class="muted">本日の発売終了</span>`}
        <span class="muted"> ・ 鉄板${cnt["鉄板"]} 混戦${cnt["混戦"]} 荒${cnt["荒れそう"]}</span></div></div><span class="chev">›</span></a>`;
  });
  return h + `</div>`;
}

function viewVenue(d, jcd){
  const v = venue(d, jcd); if (!v) return `<div class="card empty">場が見つかりません</div>`;
  let h = `<div class="card"><div class="row wrap"><span class="vname">${esc(v.name)}</span><span class="badge b-grade b-${esc(v.grade.slice(0,2))}">${esc(v.grade)}</span><span class="badge b-kind">${esc(v.kind)}</span></div>
    <div class="small">${esc(v.title)}</div><div class="muted">${esc(v.period_day)}</div>
    <details><summary>コース別1着率（${esc(v.course_src)}）</summary><div class="prob">${[1,2,3,4,5,6].map(c => `<div class="pr"><span class="nm">${c}コース</span><span class="bar"><i style="width:${v.course_stats[c].r1}%"></i></span><span class="pv">${v.course_stats[c].r1}%</span></div>`).join("")}</div></details></div>`;
  h += `<div class="card rlist">` + v.races.map(r => {
    const an = r.analysis;
    const fav = an ? r.boats.reduce((a, b) => (b.p_win > a.p_win ? b : a)) : null;
    const ck = r.check;
    return `<a class="race" href="#/${d.hd}/r/${jcd}/${r.rno}"><span class="rno">${r.rno}R</span><div class="rmeta">
      <div class="row"><b style="font-variant-numeric:tabular-nums">${esc(r.deadline)}</b>${confB(an&&an.confidence)}${statusBadge(r)}${exBadge(r)}</div>
      <div class="t">${esc(r.race_title)} ${esc(r.distance)}${fav?` ・ 本命 ${fav.waku}号艇 ${esc(fav.name)} ${pct(fav.p_win)}`:""}</div>
      ${ck ? `<div class="t">結果 ${combo(ck.trifecta||"")} ${ck.trifecta_yen?ck.trifecta_yen.toLocaleString()+"円":""} ${ck.hits.length?`<span class="badge b-teppan">${esc(ck.hits.join("・"))}</span>`:""}</div>` : (an?`<div class="t">本命 ${an.rec.honmei.map(x=>esc(x.combo)).join(" / ")}</div>`:"")}
      </div><span class="chev">›</span></a>`;
  }).join("") + `</div>`;
  const m = v.media;
  h += `<h2 class="sec">メディア情報（${esc(v.name)}）</h2><div class="card media">`;
  if (m.outlook) h += `<div class="mi"><span class="src">今節の展望（無料予想ページ）</span><div class="sm">${esc(m.outlook)}</div>${m.free_yosou_url?`<a class="link" href="${esc(m.free_yosou_url)}" target="_blank" rel="noopener">出典を開く ↗</a>`:""}</div>`;
  (m.news||[]).forEach(n => h += `<div class="mi"><span class="src">${esc(n.source)}</span> <span class="muted">${esc(n.time)}</span><div class="hl">${esc(n.headline)}</div><div class="sm">${esc(n.summary)}</div><a class="link" href="${esc(n.url)}" target="_blank" rel="noopener">記事を開く ↗</a>${n.paywalled_rest?` <span class="muted">（続きは会員限定）</span>`:""}</div>`);
  if (m.free_yosou_url && !m.free_yosou_title) h += `<div class="mi"><span class="src">無料予想（外部サイト）</span><div class="sm">${esc(m.free_yosou_note||"")}</div><a class="link" href="${esc(m.free_yosou_url)}" target="_blank" rel="noopener">${esc(m.free_yosou_url)} ↗</a></div>`;
  if (!m.outlook && !(m.news||[]).length && !m.free_yosou_url) h += `<div class="empty">取得できた無料メディア情報はありません</div>`;
  return h + `</div>`;
}

function cmEval(b){ const c = b.comment || {}; return (c.chokuzen && c.chokuzen.eval) || (c.zenjitsu && c.zenjitsu.eval) || null; }
function cmLabel(b){ const e = cmEval(b); if (!e) return '<span class="lo">-</span>';
  const cls = e.total >= 0.5 ? "b-teppan" : e.total <= -0.5 ? "b-are" : "b-kind"; return `<span class="badge ${cls}">${esc(e.label.slice(0,1))}</span>`; }
function commentBlock(r, v){
  const bs = r.boats.filter(b => b.comment);
  if (!bs.length) { const cs = (v && v.comment_status) || {status:"none", message:"この場は公式サイトで無料のコメントが公開されていません"};
    const t = cs.checked_at ? String(cs.checked_at).slice(11,16) : "";
    return `<h2 class="sec">選手コメント・足色</h2><div class="card"><div class="empty" style="padding:6px 0">${cs.status==="pending"?"⏳ ":"ー "}${esc(cs.message)}</div>
      ${cs.detail?`<div class="muted">${esc(cs.detail)}</div>`:""}<div class="muted">最終確認 ${esc(t||"-")}${cs.site?` ・ <a class="link" href="${esc(cs.site)}/sp/" target="_blank" rel="noopener">公式サイト ↗</a>`:""}</div></div>`; }
  const asp = e => Object.entries(e.aspects||{}).map(([a,x]) => `<span class="badge ${x>0?"b-teppan":x<0?"b-are":"b-kind"}">${a==="総合"?"舟足":a}${x>0?"↑":x<0?"↓":"→"}</span>`).join(" ");
  return `<h2 class="sec">選手コメント・足色</h2><div class="card media">${bs.map(b => { const c = b.comment, e = cmEval(b);
    return `<div class="mi"><div class="row">${W(b.waku)}<b>${esc(b.name)}</b><span class="badge ${e.total>=0.5?"b-teppan":e.total<=-0.5?"b-are":"b-kind"}">${esc(e.label)}</span>${b.parts&&b.parts.comment!=null?`<span class="muted">補正 ${b.parts.comment>=0?"+":""}${b.parts.comment.toFixed(2)}</span>`:""}</div>
      ${c.chokuzen?`<div class="sm"><span class="src">直前${c.chokuzen.time?" "+esc(c.chokuzen.time):""}</span> ${esc(c.chokuzen.text)}</div>`:""}
      ${c.zenjitsu?`<div class="sm" style="margin-top:2px"><span class="src paid">前日</span> ${esc(c.zenjitsu.text)}</div>`:""}
      <div style="margin-top:3px">${asp((c.chokuzen||{}).eval||{})} ${asp((c.zenjitsu||{}).eval||{})}</div>
      <details><summary>判定根拠</summary><div class="muted">${[...((c.chokuzen||{}).eval||{evidence:[]}).evidence, ...((c.zenjitsu||{}).eval||{evidence:[]}).evidence].map(esc).join("<br>")||"該当語なし"}</div></details></div>`; }).join("")}
    <div class="muted">出典: 各場公式サイトの選手コメント（<a class="link" href="${esc(bs[0].comment.source||"")}" target="_blank" rel="noopener">開く ↗</a>）。足色はキーワード辞書による自動判定で、モデルには最大±0.2の小さな補正として反映。</div></div>`;
}
function memoBlock(d, v, r){
  const k = `${d.hd}:${v.jcd}:${r.rno}`;
  return `<h2 class="sec">情報誌メモ・自分メモ</h2><div class="card">
    <div class="small" style="font-weight:700">📰 情報誌・新聞の予想を貼り付け</div>
    <textarea data-k="mag:${k}" placeholder="例）マクール本誌: ◎1 ○3 ▲4 「1号艇の出足◎」">${esc(localStorage.getItem("mag:"+k)||"")}</textarea>
    <div class="small" style="font-weight:700;margin-top:8px">✏️ 自分のメモ</div>
    <textarea data-k="memo:${k}" placeholder="展示の気配、買い目メモなど">${esc(localStorage.getItem("memo:"+k)||"")}</textarea>
    <div class="saved" id="savedMsg"></div><div class="muted">この端末のブラウザ(localStorage)に自動保存されます。</div></div>`;
}

function viewRace(d, jcd, rno){
  const v = venue(d, jcd), r = race(d, jcd, rno);
  if (!r) return `<div class="card empty">レースが見つかりません</div>`;
  const an = r.analysis;
  const idx = v.races.indexOf(r);
  const nav = `<div class="tabs2">${v.races.map(x => `<a href="#/${d.hd}/r/${jcd}/${x.rno}" class="${x.rno==r.rno?"on":""}">${x.rno}R</a>`).join("")}</div>`;
  let h = nav + `<div class="card"><div class="row wrap"><span class="vname">${esc(v.name)} ${r.rno}R</span>${confB(an&&an.confidence)}${statusBadge(r)}${exBadge(r)}<span style="margin-left:auto;font-weight:800">締切 ${esc(r.deadline)}</span></div>
    <div class="muted">${esc(r.race_title)} ${esc(r.distance)} ・ ${esc(v.title)}</div></div>`;
  if (!an) return h + `<div class="card empty">出走表データを取得できませんでした ${esc((r.errors||[]).join(" "))}</div>`;
  if (r.check) {
    const ck = r.check;
    h += `<div class="card ${ck.hits.length?"result":"result miss"}"><div class="row between"><b>レース結果</b><span class="badge b-kind">${esc(ck.kimarite)}</span></div>
      <div class="row" style="margin-top:4px">3連単 ${combo(ck.trifecta||"")} <b>${(ck.trifecta_yen||0).toLocaleString()}円</b> ・ 2連単 ${combo(ck.exacta||"")} <b>${(ck.exacta_yen||0).toLocaleString()}円</b></div>
      <div class="small" style="margin-top:4px">${ck.hits.length?`🎯 ${esc(ck.hits.join("・"))}`:"モデルの買い目は不的中"}（本命艇${ck.fav_won?"1着":"敗退"}）</div></div>`;
  }
  h += `<h2 class="sec">攻略コメント</h2><div class="card"><div class="comment" style="margin:0">${esc(an.comment)}</div>
     <div class="muted" style="margin-top:6px">進入: ${esc(an.entry_src)} ・ 展示: ${r.ex_reflected?"反映済み":"発表前（展示なしで算出）"} ・ オッズ: ${an.has_odds?esc(r.odds_updated||"取得済"):"未取得"}</div></div>`;
  if (r.status !== "finished" || r.ex_reflected) h += exBlock(r);
  h += `<h2 class="sec">推定1着率</h2><div class="card prob">${[...r.boats].sort((a,b)=>b.p_win-a.p_win).map(b => `<div class="pr">${W(b.waku)}<span class="nm">${esc(b.name)}</span><span class="bar"><i style="width:${Math.min(100,b.p_win*100/0.8*0.8*1.25)}%"></i></span><span class="pv">${pct(b.p_win)}</span></div>`).join("")}
    <div class="muted">2連対率/3連対率(推定): ${r.boats.map(b => `${b.waku}:${pct(b.p_top2)}/${pct(b.p_top3)}`).join(" ")}</div></div>`;
  h += `<h2 class="sec">買い目（参考）</h2><div class="card bets">${betsBlock(an)}
    ${an.rec.value.length?`<div class="grp-t" style="color:#c25400">💰 妙味（補正確率×オッズ≥1）: ${an.rec.value.map(x=>`${x.bet} ${esc(x.combo)} (EV${x.ev.toFixed(2)})`).join("、")}</div>`:""}
    <div class="muted">推定＝モデル確率、補正＝モデル${Math.round((d.model.blend_w||0.3)*100)}%・市場オッズ${100-Math.round((d.model.blend_w||0.3)*100)}%の対数ブレンド、EV＝補正確率×オッズ（1.0超で妙味）。締切から遠い時間帯のオッズは票数が少なく変動が大きい点に注意。${an.has_odds?"":"オッズ未取得のため期待値は計算できません。"}</div></div>`;
  h += anaRace(d, r);
  // 出走表
  const best = (k, low) => { const xs = r.boats.map(b => b[k]).filter(x => x != null && x !== 0); return xs.length ? (low ? Math.min(...xs) : Math.max(...xs)) : null; };
  const bx = {nat: best("nat_win"), loc: best("loc_win"), st: best("avg_st", true), mot: best("motor_2r")};
  const hi = (v, b) => v != null && v === b ? "hi" : "";
  h += `<h2 class="sec">出走表 <span class="muted" style="font-weight:400">横スクロールで展示・PC印・スコア ›</span></h2><div class="card"><div class="tblwrap"><table class="st"><thead><tr>
    <th>枠</th><th class="nm">選手</th><th>全国<br>勝率/2連</th><th>当地<br>勝率/2連</th><th>平均ST<br>F/L</th><th>モーター<br>No/2連</th><th>ボート<br>No/2連</th><th>展示<br>(順位)</th><th>チルト</th><th>進入</th><th>気配<br>(ｺﾒﾝﾄ)</th><th>公式<br>PC印</th><th>スコア</th><th>今節</th></tr></thead><tbody>
    ${r.boats.map(b => { const bf = b.before || {}; return `<tr><td class="wk wk${b.waku}">${b.waku}</td>
      <td class="nm"><div class="rname">${esc(b.name)}<span class="cls c${esc(b.class)}">${esc(b.class)}</span></div><div class="muted">${esc(b.toban)} ${esc(b.branch)} ${b.age||""}歳</div></td>
      <td class="${hi(b.nat_win,bx.nat)}">${fx(b.nat_win)}<br><span class="lo">${fx(b.nat_2r,1)}%</span></td>
      <td class="${hi(b.loc_win,bx.loc)}">${b.loc_win?fx(b.loc_win):"-"}<br><span class="lo">${b.loc_win?fx(b.loc_2r,1)+"%":""}</span></td>
      <td class="${hi(b.avg_st,bx.st)}">${fx(b.avg_st)}<br>${b.F?`<span class="flag">F${b.F}</span>`:'<span class="lo">F0</span>'} <span class="lo">L${b.L}</span></td>
      <td class="${hi(b.motor_2r,bx.mot)}">${b.motor_no??"-"}<br>${fx(b.motor_2r,1)}%</td>
      <td>${b.boat_no??"-"}<br><span class="lo">${fx(b.boat_2r,1)}%</span></td>
      <td class="${b.ex_rank===1?"hi":""}">${bf.ex_time?fx(bf.ex_time):"-"}<br><span class="lo">${b.ex_rank?`(${b.ex_rank})`:""}</span></td>
      <td>${bf.ex_time!=null&&bf.tilt!=null?fx(bf.tilt,1):"-"}</td><td>${b.course??"-"}</td><td>${cmLabel(b)}</td><td style="font-size:15px">${esc(r.pc.marks[b.waku]||"")}</td>
      <td><b>${b.score>=0?"+":""}${fx(b.score)}</b></td><td class="small">${(b.series||[]).map(s=>esc(s.rank)).join(" ")||"-"}</td></tr>`; }).join("")}
    </tbody></table></div><div class="muted" style="margin-top:6px">赤字＝メンバー内トップ。スコア＝能力スコア(レース内平均との差)。公式PC印は boatrace.jp コンピューター予想。</div>
    <details><summary>スコア内訳を見る</summary><div class="parts">${r.boats.map(b => `<span>${W(b.waku)}</span><span>${Object.entries(b.parts||{}).map(([k,x]) => `${({nat_win:"全国",loc_win:"当地",avg_st:"ST",motor_2r:"モーター",boat_2r:"ボート",ex_time:"展示",ex_rank:"展示順位",class:"級別",F:"F",comment:"ｺﾒﾝﾄ"})[k]} ${x>=0?"+":""}${x.toFixed(2)}`).join(" / ")} ・ ${b.course}コース1着率${b.r1}%</span>`).join("")}</div></details></div>`;
  h += commentBlock(r, v);
  // 直前情報
  const w = r.weather || {};
  const wOK = r.before_available || w.wind_mps != null || w.wave_cm != null || (w.weather||"") !== "";
  h += `<h2 class="sec">直前情報</h2><div class="card">${wOK ? `
    <div class="kv"><div><b>${esc(w.weather||"-")}</b><span>天候</span></div><div><b>${w.wind_mps!=null?w.wind_mps+"m":"-"}</b><span>風速</span></div><div><b>${w.wave_cm!=null?w.wave_cm+"cm":"-"}</b><span>波高</span></div>
    <div><b>${esc(w.air_temp||"-")}</b><span>気温</span></div><div><b>${esc(w.water_temp||"-")}</b><span>水温</span></div><div><b class="small">${esc((w.title||"").replace("水面気象情報",""))}</b><span>観測</span></div></div>
    ${!r.before_available?`<div class="small" style="margin-top:6px">⏳ このレースの展示・スタート展示は発表前（締切の約30分前ごろ発表）。水面気象は${esc((w.title||"").replace("水面気象情報","").trim()||"直近")}の値。</div>`:""}
    ${(r.start_exhibition||[]).length?`<div class="small" style="margin-top:8px;font-weight:700">スタート展示（コース順）</div><div class="se">${r.start_exhibition.map(x=>`<div>${W(x.waku)}<br>${esc(x.st)}</div>`).join("")}</div>`:""}`
    : `<div class="empty">⏳ 発表前（締切の約30分前ごろ発表）</div><div class="muted">展示タイム・スタート展示・水面気象は発表後の更新で反映されます。データ取得 ${esc((d.fetched_at||"").slice(11,16))}</div>`}
    <div class="muted" style="margin-top:6px">風向は公式ページでご確認ください。</div></div>`;
  // 公式PC予想
  if ((r.pc.focus||[]).length) h += `<h2 class="sec">公式コンピューター予想</h2><div class="card"><div class="chips">${r.pc.focus.map(f => `<span class="badge b-kind" style="font-size:12px">${esc(f)}</span>`).join("")}</div><a class="link" href="${esc(r.links.pcexpect)}" target="_blank" rel="noopener">boatrace.jp で見る ↗</a></div>`;
  // メディア
  h += `<h2 class="sec">メディア情報</h2><div class="card media">`;
  const ms = r.media || [];
  ms.forEach(m => h += `<div class="mi"><span class="src ${m.paywalled?"paid":""}">${esc(m.source)}</span><div class="hl">${esc(m.headline)}</div>${m.summary?`<div class="sm">${esc(m.summary)}</div>`:""}${m.buys?`<div class="by">買い目: ${esc(m.buys)}</div>`:""}${m.url?`<a class="link" href="${esc(m.url)}" target="_blank" rel="noopener">出典を開く ↗</a>`:""}</div>`);
  (v.media.news||[]).slice(0,2).forEach(n => h += `<div class="mi"><span class="src">${esc(n.source)}（${esc(v.name)}）</span><div class="hl">${esc(n.headline)}</div><div class="sm">${esc(n.summary)}</div><a class="link" href="${esc(n.url)}" target="_blank" rel="noopener">記事を開く ↗</a></div>`);
  if (!ms.length && !(v.media.news||[]).length) h += `<div class="empty">このレースの無料メディア情報は取得できませんでした${v.media.free_yosou_url?`<br><a class="link" href="${esc(v.media.free_yosou_url)}" target="_blank">場の無料予想ページ ↗</a>`:""}</div>`;
  h += `</div>` + memoBlock(d, v, r);
  h += `<div class="card small"><b>公式ページ</b><div class="row wrap" style="margin-top:4px;gap:12px">${[["出走表","racelist"],["直前情報","beforeinfo"],["オッズ","odds"],["結果","result"]].map(([t,k])=>`<a class="link" href="${esc(r.links[k])}" target="_blank" rel="noopener">${t} ↗</a>`).join("")}</div></div>`;
  h += `<div class="row between" style="margin:8px 2px">${idx>0?`<a class="link" href="#/${d.hd}/r/${jcd}/${v.races[idx-1].rno}">‹ ${v.races[idx-1].rno}R</a>`:"<span></span>"}${idx<v.races.length-1?`<a class="link" href="#/${d.hd}/r/${jcd}/${v.races[idx+1].rno}">${v.races[idx+1].rno}R ›</a>`:""}</div>`;
  return h + `<div class="disc">${esc(d.disclaimer)}</div>`;
}

function viewAbout(d){
  return `<h2 class="sec">このツールについて</h2><div class="card small">
   <p><b>データ</b>: ボートレース公式サイト boatrace.jp の公開ページ（出走表・直前情報・オッズ・結果・場別データ）を約1秒間隔で取得・キャッシュしています。</p>
   <p><b>メディア</b>: マクール(sp.macour.jp)の<b>無料公開部分のみ</b>（無料予想ページ、注目レースコメント、ニュース見出しと冒頭）。イチオシ予想・超抜モード・記事の続き等の会員限定部分は取得していません。</p>
   <p><b>自信度</b>: 鉄板＝本命艇の推定1着率60%以上 / 荒れそう＝38%未満 または 風5m・波5cm以上 / その他＝混戦。</p>
   <p><b>妙味</b>: 推定確率 × オッズ ≥ 1.0 の買い目（推定確率は概算のため過信禁物）。</p></div>
   <h2 class="sec">モデル</h2><div class="card small"><pre style="white-space:pre-wrap;font-size:11.5px;margin:0">${esc(d.model.formula)}</pre>
   <div style="margin-top:6px">${Object.entries(d.model.weights).map(([k,v])=>`<div>・${esc(v)}</div>`).join("")}<div>・K = ${d.model.K}</div></div></div>
   ${d.ana_rules?`<h2 class="sec">荒れ度・穴狙いの基準</h2><div class="card small"><div>中穴＝3連単${d.ana_rules.tiers["中穴"][0]}〜${d.ana_rules.tiers["中穴"][1]}倍未満、大穴＝${d.ana_rules.tiers["大穴"][0]}倍以上。荒れ度${d.ana_rules.threshold}以上を穴狙い候補とし、帯ごとに補正確率×オッズの高い順に3点。</div>${d.ana_rules.rules.map(([k,v])=>`<div>・<b>${esc(k)}</b>: ${esc(v)}</div>`).join("")}<div style="margin-top:4px">合計(上限100)。高リスク・参考情報です。</div></div>`:""}
   <h2 class="sec">選手コメント足色辞書</h2><div class="card small">${d.model.comment_dict?Object.entries({"観点":Object.entries(d.model.comment_dict.aspects).map(([a,k])=>a+"："+k.join("・")).join(" / "),"好評価":d.model.comment_dict.good.join("・"),"やや好評価(+0.5)":d.model.comment_dict.mild_good.join("・"),"悪評価":d.model.comment_dict.bad.join("・"),"普通(0)":d.model.comment_dict.neutral.join("・"),"要望(−0.3/0)":d.model.comment_dict.hope.join("・"),"条件付き(無視)":d.model.comment_dict.conditional.join("・")}).map(([k,v])=>`<div><b>${k}</b>: ${esc(v)}</div>`).join(""):""}
   <div style="margin-top:6px">対応場: ${Object.entries(d.comments_status?.venues||{}).filter(([j,v])=>v.races_with_comments||v.racers_by_toban).map(([j,v])=>esc((d.venues.find(x=>x.jcd===j)||{}).name)+(v.races_with_comments?` ${v.races_with_comments}R`:"")+(v.racers_by_toban?` ${v.racers_by_toban}名`:"")).join("、")||"なし"}</div></div>
   <h2 class="sec">取得状況</h2><div class="card small">${(d.media_status||[]).map(s=>`<div>・${esc(s)}</div>`).join("")}<div>・生成: ${esc(d.generated_at)}</div>${ENC?`<div style="margin-top:6px"><a class="link" href="javascript:logout()">この端末のパスワード保存を解除</a></div>`:""}</div>
   <div class="disc">${esc(d.disclaimer)}</div>`;
}

async function render(){
  const {hd: h0, view, a, b} = parseHash();
  const hd = h0 || CUR || (DATES.includes(jstToday()) ? jstToday() : DATES[0]);
  CUR = hd;
  const app = $("#app");
  let d;
  try { d = await loadDay(hd); }
  catch(e){ setChrome(hd, view, ""); app.innerHTML = `<div class="card empty">${fmtDate(hd)} のデータがありません。<br><span class="muted">fetch.py / build.py を実行してください。</span></div>`; return; }
  let html, cr = "";
  if (view === "venues") html = viewVenues(d);
  else if (view === "v") { const v = venue(d, a); cr = `<a href="#/${hd}/venues">開催場</a> › ${esc(v?.name)}`; html = viewVenue(d, a); }
  else if (view === "r") { const v = venue(d, a); cr = `<a href="#/${hd}/venues">開催場</a> › <a href="#/${hd}/v/${a}">${esc(v?.name)}</a> › ${b}R`; html = viewRace(d, a, b); }
  else if (view === "about") html = viewAbout(d);
  else html = viewPicks(d);
  setChrome(hd, view, cr);
  app.innerHTML = html;
  (document.getElementById('app')||window).scrollTo(0, 0);
  app.querySelectorAll("textarea[data-k]").forEach(t => t.addEventListener("input", () => {
    localStorage.setItem(t.dataset.k, t.value); const m = $("#savedMsg"); if (m){ m.textContent = "保存しました"; clearTimeout(m._t); m._t = setTimeout(()=>m.textContent="", 1200);} }));
}

async function init(){
  try { DATES = (await getJSON("data/dates.json")).dates; } catch(e){ DATES = []; }
  $("#dateSel").addEventListener("change", e => { const {view, a, b} = parseHash(); go(e.target.value, view === "r" || view === "v" ? "venues" : view); });
  const shift = n => { const i = DATES.indexOf(CUR); const j = i - n; if (j >= 0 && j < DATES.length) { const {view} = parseHash(); go(DATES[j], view === "r" || view === "v" ? "venues" : view); } };
  $("#prevDay").onclick = () => shift(-1); $("#nextDay").onclick = () => shift(1);
  window.addEventListener("hashchange", render);
  render();
}
init();
