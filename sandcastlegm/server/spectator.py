"""Self-contained spectator/play web UI served by the session server.

Two pages, no build step and no external assets:

* the index (``/``) creates or joins a room,
* the watch page (``/watch/{room_id}``) connects to the room's WebSocket and
  renders the live narration feed plus a state panel (scene, characters with HP,
  initiative, tactical map). It also has an action bar so a watcher can act as a
  player, which makes it a usable lightweight client as well as a spectator view.

The HTML uses a ``__ROOM_ID__`` placeholder filled by ``str.replace`` (not
``.format``) so the inline CSS/JS braces need no escaping.
"""

from __future__ import annotations

INDEX_HTML = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SandcastleGM</title>
<style>
  body { font-family: system-ui, sans-serif; background:#15171c; color:#e6e6e6;
         max-width:640px; margin:40px auto; padding:0 16px; }
  h1 { font-size:1.4rem; } input,select,button { font-size:1rem; padding:6px 8px; }
  .card { background:#1e2128; border:1px solid #2c313c; border-radius:8px;
          padding:16px; margin:16px 0; }
  button { background:#3a6ea5; color:#fff; border:0; border-radius:6px; cursor:pointer; }
  label { display:block; margin:8px 0 4px; color:#9aa4b2; font-size:.9rem; }
  a { color:#7fb2e6; }
</style></head><body>
<h1>🏰 SandcastleGM</h1>
<div class="card">
  <h2 style="font-size:1.1rem">新しい卓を作る</h2>
  <label>タイトル</label>
  <input id="title" value="灰隅の冒険" style="width:100%">
  <label>ルールセット</label>
  <input id="ruleset" value="sandcastle" style="width:100%">
  <p><button onclick="create()">作成して入室</button></p>
</div>
<div class="card">
  <h2 style="font-size:1.1rem">既存の卓に入る</h2>
  <input id="rid" placeholder="game_xxxxxxxx" style="width:70%">
  <button onclick="join()">入室</button>
</div>
<div class="card">
  <h2 style="font-size:1.1rem">稼働中の卓</h2>
  <ul id="rooms" style="list-style:none;padding:0;margin:0"><li style="color:#6b7280">読み込み中…</li></ul>
</div>
<script>
async function create() {
  const r = await fetch('/sessions', {method:'POST', headers:{'content-type':'application/json'},
    body: JSON.stringify({title: document.getElementById('title').value,
                          ruleset_id: document.getElementById('ruleset').value})});
  const j = await r.json();
  location.href = '/watch/' + j.id;
}
function join() {
  const id = document.getElementById('rid').value.trim();
  if (id) location.href = '/watch/' + id;
}
async function loadRooms() {
  try {
    const rooms = await (await fetch('/sessions')).json();
    const ul = document.getElementById('rooms');
    ul.innerHTML = rooms.length ? rooms.map(r =>
      '<li style="padding:6px 0;border-top:1px solid #2c313c">' +
      '<a href="/watch/' + r.id + '">' + esc(r.title) + '</a>' +
      ' <small style="color:#9aa4b2">' + esc(r.ruleset) + ' · ' + r.players + '人 · ' + r.id + '</small></li>'
    ).join('') : '<li style="color:#6b7280">まだありません</li>';
  } catch (e) { /* server may be momentarily unavailable */ }
}
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
loadRooms();
setInterval(loadRooms, 5000);
</script>
</body></html>"""


WATCH_HTML = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SandcastleGM — __ROOM_ID__</title>
<style>
  * { box-sizing:border-box; }
  body { font-family: system-ui, sans-serif; background:#15171c; color:#e6e6e6;
         margin:0; height:100vh; display:flex; flex-direction:column; }
  header { padding:8px 14px; background:#1b1e25; border-bottom:1px solid #2c313c;
           display:flex; gap:12px; align-items:baseline; }
  header b { color:#7fb2e6; } header .rid { color:#6b7280; font-size:.8rem; }
  #status { margin-left:auto; font-size:.8rem; color:#9aa4b2; }
  main { flex:1; display:flex; min-height:0; }
  #panel { width:340px; border-right:1px solid #2c313c; overflow:auto; padding:12px; }
  #feedwrap { flex:1; display:flex; flex-direction:column; min-width:0; }
  #feed { flex:1; overflow:auto; padding:14px; }
  .ev { margin:0 0 12px; line-height:1.5; }
  .ev .who { font-size:.75rem; color:#6b7280; text-transform:uppercase; }
  .narration { font-size:1.02rem; white-space:pre-wrap; }
  .player_action { color:#cdb87f; } .player_action::before { content:"▶ "; }
  .roll { color:#8fce8f; font-family:ui-monospace, monospace; font-size:.88rem; }
  .scene { color:#c79be0; } .map,.turn,.system { color:#7fb2e6; font-size:.9rem; }
  h3 { font-size:.8rem; color:#9aa4b2; text-transform:uppercase; margin:14px 0 6px; }
  .ch { margin:4px 0; font-size:.92rem; }
  .bar { height:6px; background:#3a2d2d; border-radius:3px; overflow:hidden; margin-top:2px; }
  .bar > i { display:block; height:100%; background:#5fae5f; }
  .down { opacity:.5; text-decoration:line-through; }
  #map { overflow:auto; }
  .board { display:grid; gap:1px; background:#2c313c; padding:1px; width:max-content; }
  .cell { width:18px; height:18px; background:#0e1014; position:relative; }
  .cell.wall { background:#3a3f4b; } .cell.water { background:#1d3a5a; }
  .cell.difficult { background:#2a241a; }
  .tok { position:absolute; inset:1px; border-radius:3px; display:flex;
         align-items:center; justify-content:center; font-size:11px; font-weight:bold;
         color:#fff; cursor:default; }
  .tok.downed { opacity:.4; }
  form { display:flex; gap:8px; padding:10px; border-top:1px solid #2c313c; background:#1b1e25; }
  form select, form input { padding:8px; background:#0e1014; color:#e6e6e6;
            border:1px solid #2c313c; border-radius:6px; }
  form input[type=text] { flex:1; } form button { background:#3a6ea5; color:#fff;
            border:0; border-radius:6px; padding:0 16px; cursor:pointer; }
  .active { color:#ffd479; font-weight:bold; }
</style></head><body>
<header><b>🏰 SandcastleGM</b><span id="scene">—</span>
  <span class="rid">__ROOM_ID__</span><span id="status">接続中…</span></header>
<main>
  <div id="panel">
    <h3>キャラクター</h3><div id="chars"></div>
    <h3>イニシアチブ</h3><div id="init">—</div>
    <h3>マップ</h3><div id="map">（なし）</div>
  </div>
  <div id="feedwrap">
    <div id="feed"></div>
    <form onsubmit="act(event)">
      <select id="actor"><option value="">（ナレーション/GM宛）</option></select>
      <input type="text" id="msg" placeholder="行動やセリフを入力…" autocomplete="off">
      <button>送信</button>
    </form>
  </div>
</main>
<script>
const ROOM = "__ROOM_ID__";
const feed = document.getElementById('feed');

function addEvent(e) {
  const div = document.createElement('div');
  div.className = 'ev';
  const who = e.actor ? ('<div class="who">' + e.actor + '</div>') : '';
  div.innerHTML = who + '<div class="' + e.type + '">' +
      escapeHtml(e.text) + '</div>';
  feed.appendChild(div);
  feed.scrollTop = feed.scrollHeight;
}
function escapeHtml(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}

async function refreshState() {
  const st = await (await fetch('/sessions/' + ROOM)).json();
  const scene = (st.scenes || []).find(s => s.id === st.current_scene_id);
  document.getElementById('scene').textContent = scene ? scene.title : '—';
  const active = (st.turn_order && st.turn_order.order || [])[st.turn_order.index];
  const chars = Object.values(st.characters || {});
  document.getElementById('chars').innerHTML = chars.map(c => {
    const pct = c.max_hp ? Math.max(0, 100 * c.hp / c.max_hp) : 0;
    const down = c.hp <= 0 ? ' down' : '';
    const star = c.id === active ? ' <span class="active">◀手番</span>' : '';
    return '<div class="ch' + down + '">' + escapeHtml(c.name) +
      ' <small>' + c.hp + '/' + c.max_hp + '</small>' + star +
      '<div class="bar"><i style="width:' + pct + '%"></i></div></div>';
  }).join('') || '—';
  const order = (st.turn_order && st.turn_order.order) || [];
  document.getElementById('init').innerHTML = order.length
    ? ('R' + st.turn_order.round + ': ' + order.map(id => {
        const c = st.characters[id]; const nm = c ? c.name : id;
        return id === active ? '<span class="active">' + escapeHtml(nm) + '</span>' : escapeHtml(nm);
      }).join(' → ')) : '—';
  // actor dropdown (PCs)
  const sel = document.getElementById('actor');
  const cur = sel.value;
  sel.innerHTML = '<option value="">（ナレーション/GM宛）</option>' +
    chars.filter(c => c.is_pc).map(c => '<option value="' + c.id + '">' + escapeHtml(c.name) + '</option>').join('');
  sel.value = cur;
  const board = await (await fetch('/sessions/' + ROOM + '/board')).json();
  renderBoard(board.grid);
}

function renderBoard(grid) {
  const el = document.getElementById('map');
  if (!grid) { el.textContent = '（マップなし）'; return; }
  const terr = grid.terrain || {};
  const cells = [];
  for (let y = 0; y < grid.height; y++)
    for (let x = 0; x < grid.width; x++) {
      const tag = terr[x + ',' + y];
      cells.push('<div class="cell' + (tag ? ' ' + tag : '') + '"></div>');
    }
  el.innerHTML = '<div class="board" style="grid-template-columns:repeat(' +
    grid.width + ',18px)">' + cells.join('') + '</div>';
  const board = el.querySelector('.board');
  (grid.tokens || []).forEach(t => {
    const cell = board.children[t.y * grid.width + t.x];
    if (!cell) return;
    const tok = document.createElement('div');
    tok.className = 'tok' + (t.downed ? ' downed' : '');
    tok.style.background = t.color || '#888';
    tok.textContent = (t.glyph || t.name || '?').slice(0, 1);
    const hp = (t.hp != null) ? ' ' + t.hp + '/' + t.max_hp : '';
    tok.title = (t.name || '') + hp + (t.downed ? ' (戦闘不能)' : '');
    cell.appendChild(tok);
  });
}

let ws;
function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(proto + '://' + location.host + '/sessions/' + ROOM + '/ws');
  ws.onopen = () => document.getElementById('status').textContent = '接続済み';
  ws.onclose = () => { document.getElementById('status').textContent = '切断（再接続中…）'; setTimeout(connect, 1500); };
  ws.onmessage = (m) => {
    const d = JSON.parse(m.data);
    if (d.kind === 'backlog') { d.events.forEach(addEvent); refreshState(); }
    else if (d.kind === 'event') {
      addEvent(d.event);
      if (['scene','map','turn','system'].includes(d.event.type)) refreshState();
    }
  };
}
function act(e) {
  e.preventDefault();
  const msg = document.getElementById('msg');
  if (!msg.value.trim() || !ws || ws.readyState !== 1) return;
  ws.send(JSON.stringify({type:'action', text: msg.value, actor_id: document.getElementById('actor').value || null}));
  msg.value = '';
}
connect();
refreshState();
</script>
</body></html>"""


def index_page() -> str:
    return INDEX_HTML


def watch_page(room_id: str) -> str:
    return WATCH_HTML.replace("__ROOM_ID__", room_id)
