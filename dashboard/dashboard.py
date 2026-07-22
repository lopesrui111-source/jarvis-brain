#!/usr/bin/env python3
"""
JARVIS Dashboard — liest Postgres (cost_ledger, tasks) + Redis (Status)
und zeigt Kopfzeile (Kosten/Requests) + eine Kachel pro Bot.
Nur lesen, nie handeln. Port nur lokal gebunden — Zugriff per SSH-Tunnel.
"""

import os
import json
from datetime import date

import redis
import psycopg2
import psycopg2.extras
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

PG_HOST = os.getenv("POSTGRES_HOST", "postgres")
PG_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
PG_USER = os.getenv("POSTGRES_USER", "jarvis")
PG_PASS = os.getenv("POSTGRES_PASSWORD", "")
PG_DB   = os.getenv("POSTGRES_DB", "jarvis_brain")

app = FastAPI()


def pg():
    return psycopg2.connect(
        host=PG_HOST, port=PG_PORT, user=PG_USER,
        password=PG_PASS, dbname=PG_DB, connect_timeout=5
    )


def jarvis_online() -> bool:
    """Core wartet praktisch immer in BLPOP auf jarvis:inbox —
    wenn ein Redis-Client gerade blpop ausfuehrt, lebt der Core."""
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True,
                        socket_connect_timeout=3)
        for c in r.client_list():
            if c.get("cmd", "").lower().startswith("blpop"):
                return True
        return False
    except Exception:
        return False


@app.get("/api/stats")
def stats():
    out = {
        "online": jarvis_online(),
        "today": 0.0, "month": 0.0, "total": 0.0,
        "requests": 0, "tokens_in": 0, "tokens_out": 0,
        "bots": [],
        "queue": 0,
    }
    # Redis-Queue-Laenge
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True,
                        socket_connect_timeout=3)
        out["queue"] = r.llen("jarvis:inbox")
    except Exception:
        pass
    # Postgres-Aggregationen
    try:
        conn = pg()
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                  COALESCE(SUM(cost_usd) FILTER (WHERE created_at::date = CURRENT_DATE), 0)  AS today,
                  COALESCE(SUM(cost_usd) FILTER (WHERE date_trunc('month', created_at) = date_trunc('month', now())), 0) AS month,
                  COALESCE(SUM(cost_usd), 0)   AS total,
                  COUNT(*)                     AS requests,
                  COALESCE(SUM(tokens_in), 0)  AS tokens_in,
                  COALESCE(SUM(tokens_out), 0) AS tokens_out
                FROM cost_ledger
            """)
            row = cur.fetchone()
            out.update({
                "today": float(row["today"]), "month": float(row["month"]),
                "total": float(row["total"]), "requests": int(row["requests"]),
                "tokens_in": int(row["tokens_in"]), "tokens_out": int(row["tokens_out"]),
            })
            # pro Bot: Kosten, Requests, letzte Aktivitaet
            cur.execute("""
                SELECT bot,
                       COALESCE(SUM(cost_usd), 0) AS cost,
                       COUNT(*)                   AS requests,
                       MAX(created_at)            AS last_seen
                FROM cost_ledger
                GROUP BY bot
                ORDER BY bot
            """)
            for b in cur.fetchall():
                out["bots"].append({
                    "name": b["bot"],
                    "cost": float(b["cost"]),
                    "requests": int(b["requests"]),
                    "last_seen": b["last_seen"].strftime("%d.%m. %H:%M") if b["last_seen"] else "-",
                    "online": out["online"] if b["bot"] == "jarvis" else False,
                })
        conn.close()
    except Exception as e:
        out["error"] = str(e)
    return JSONResponse(out)


VAULT_DIR = "/app/vault"
TEXT_EXT = (".md", ".txt", ".json", ".yml", ".yaml", ".csv")
IMG_EXT  = (".png", ".jpg", ".jpeg", ".webp", ".gif")


def _safe_vault_path(rel: str) -> str:
    """Pfad-Traversal verhindern: Ergebnis muss unter VAULT_DIR liegen."""
    rel = (rel or "").strip().lstrip("/")
    full = os.path.realpath(os.path.join(VAULT_DIR, rel))
    root = os.path.realpath(VAULT_DIR)
    if not (full == root or full.startswith(root + os.sep)):
        return ""
    return full


@app.get("/api/vault")
def vault_list(path: str = ""):
    full = _safe_vault_path(path)
    if not full or not os.path.isdir(full):
        return JSONResponse({"error": "Ordner nicht gefunden", "path": path}, status_code=404)
    dirs, files = [], []
    try:
        for name in sorted(os.listdir(full)):
            if name.startswith("."):
                continue
            p = os.path.join(full, name)
            rel = os.path.relpath(p, os.path.realpath(VAULT_DIR)).replace(os.sep, "/")
            if os.path.isdir(p):
                dirs.append({"name": name, "path": rel})
            else:
                st = os.stat(p)
                files.append({"name": name, "path": rel, "size": st.st_size,
                              "mtime": __import__("datetime").datetime.fromtimestamp(st.st_mtime).strftime("%d.%m.%Y %H:%M"),
                              "kind": "image" if name.lower().endswith(IMG_EXT) else ("text" if name.lower().endswith(TEXT_EXT) else "file")})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    return JSONResponse({"path": path, "dirs": dirs, "files": files})


@app.get("/api/vault/file")
def vault_file(path: str = "", download: int = 0):
    from fastapi.responses import FileResponse, PlainTextResponse
    full = _safe_vault_path(path)
    if not full or not os.path.isfile(full):
        return JSONResponse({"error": "Datei nicht gefunden"}, status_code=404)
    name = os.path.basename(full)
    if download:
        return FileResponse(full, filename=name)
    if name.lower().endswith(IMG_EXT):
        return FileResponse(full)
    if name.lower().endswith(TEXT_EXT):
        try:
            with open(full, encoding="utf-8", errors="replace") as f:
                return PlainTextResponse(f.read(200000))
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
    return FileResponse(full, filename=name)


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML


HTML = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JARVIS Brain</title>
<style>
  :root {
    --bg: #1A1D24;
    --bg2: #22262f;
    --card: #232833;
    --line: #2e3440;
    --txt: #e8eaee;
    --dim: #8b93a3;
    --green: #5DCAA5;
    --red: #e06c75;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: var(--bg); color: var(--txt);
    font-family: 'Segoe UI', system-ui, sans-serif;
    min-height: 100vh; padding: 32px 24px;
  }
  .wrap { max-width: 1080px; margin: 0 auto; }
  header { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 28px; }
  h1 { font-size: 22px; font-weight: 600; letter-spacing: .5px; }
  h1 em { color: var(--green); font-style: italic; }
  .clock { color: var(--dim); font-size: 14px; font-variant-numeric: tabular-nums; }

  .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 28px; }
  .kpi {
    background: var(--card); border: 1px solid var(--line); border-radius: 10px;
    padding: 16px 18px;
  }
  .kpi .label { color: var(--dim); font-size: 11px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; }
  .kpi .value { font-size: 22px; font-weight: 600; font-variant-numeric: tabular-nums; }
  .kpi .value.green { color: var(--green); }

  h2 { font-size: 13px; color: var(--dim); text-transform: uppercase; letter-spacing: 1.2px; margin: 0 0 14px 2px; }
  .bots { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 14px; }
  .bot {
    background: var(--card); border: 1px solid var(--line); border-radius: 12px;
    padding: 18px;
  }
  .bot .head { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
  .dot { width: 9px; height: 9px; border-radius: 50%; background: var(--red); flex: none; }
  .dot.on { background: var(--green); box-shadow: 0 0 8px rgba(93,202,165,.55); }
  .bot .name { font-size: 15px; font-weight: 600; text-transform: capitalize; }
  .bot .state { margin-left: auto; font-size: 11px; color: var(--dim); text-transform: uppercase; letter-spacing: .8px; }
  .bot .rows { display: grid; gap: 7px; font-size: 13px; }
  .bot .row { display: flex; justify-content: space-between; }
  .bot .row .k { color: var(--dim); }
  .bot .row .v { font-variant-numeric: tabular-nums; }

  .empty { color: var(--dim); font-size: 13px; padding: 8px 2px; }
  .vault { display: grid; grid-template-columns: minmax(260px, 1fr) 2fr; gap: 14px; }
  @media (max-width: 800px) { .vault { grid-template-columns: 1fr; } }
  .vpanel { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 14px; min-height: 120px; }
  .vcrumbs { font-size: 12px; color: var(--dim); margin-bottom: 10px; word-break: break-all; }
  .vcrumbs a { color: var(--green); text-decoration: none; cursor: pointer; }
  .vlist { display: grid; gap: 4px; max-height: 420px; overflow-y: auto; }
  .vitem { display: flex; justify-content: space-between; gap: 8px; padding: 7px 9px; border-radius: 8px;
           font-size: 13px; cursor: pointer; border: 1px solid transparent; }
  .vitem:hover { background: var(--bg2); border-color: var(--line); }
  .vitem .n { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .vitem .m { color: var(--dim); font-size: 11px; flex: none; }
  .vitem.dir .n::before { content: "📁 "; }
  .vitem.text .n::before { content: "📄 "; }
  .vitem.image .n::before { content: "🖼️ "; }
  .vitem.file .n::before { content: "📦 "; }
  .vview { max-height: 480px; overflow: auto; }
  .vview pre { white-space: pre-wrap; word-break: break-word; font-size: 13px; line-height: 1.55;
               font-family: 'Cascadia Code', Consolas, monospace; }
  .vview img { max-width: 100%; border-radius: 8px; }
  .vhead { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; gap: 10px; }
  .vhead .t { font-size: 13px; font-weight: 600; word-break: break-all; }
  .vhead a { color: var(--green); font-size: 12px; text-decoration: none; flex: none; }
  footer { margin-top: 34px; color: var(--dim); font-size: 11px; text-align: center; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>JARVIS <em>Brain</em></h1>
    <div class="clock" id="clock">--:--:--</div>
  </header>

  <div class="kpis">
    <div class="kpi"><div class="label">Kosten heute</div><div class="value green" id="k-today">$0.0000</div></div>
    <div class="kpi"><div class="label">Kosten Monat</div><div class="value" id="k-month">$0.0000</div></div>
    <div class="kpi"><div class="label">Kosten gesamt</div><div class="value" id="k-total">$0.0000</div></div>
    <div class="kpi"><div class="label">Requests</div><div class="value" id="k-req">0</div></div>
    <div class="kpi"><div class="label">Queue</div><div class="value" id="k-queue">0</div></div>
  </div>

  <h2>Agenten</h2>
  <div class="bots" id="bots"><div class="empty">Lade...</div></div>

  <h2 style="margin-top:32px">Vault</h2>
  <div class="vault">
    <div class="vpanel">
      <div class="vcrumbs" id="vcrumbs"></div>
      <div class="vlist" id="vlist"><div class="empty">Lade...</div></div>
    </div>
    <div class="vpanel vview" id="vview">
      <div class="empty">Datei anklicken zum Ansehen.</div>
    </div>
  </div>

  <footer>JARVIS Brain · Hetzner nbg1 · nur lesend</footer>
</div>

<script>
function fmt(n, d) { return '$' + n.toFixed(d === undefined ? 4 : d); }
function esc(s) { return String(s).replace(/[&<>"]/g, function(c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }

async function load() {
  try {
    const s = await (await fetch('/api/stats')).json();
    document.getElementById('k-today').textContent = fmt(s.today);
    document.getElementById('k-month').textContent = fmt(s.month);
    document.getElementById('k-total').textContent = fmt(s.total);
    document.getElementById('k-req').textContent   = s.requests;
    document.getElementById('k-queue').textContent = s.queue;
    const wrap = document.getElementById('bots');
    if (!s.bots.length) { wrap.innerHTML = '<div class="empty">Noch keine Agenten aktiv.</div>'; return; }
    wrap.innerHTML = s.bots.map(function(b) {
      return '<div class="bot"><div class="head">' +
        '<span class="dot ' + (b.online ? 'on' : '') + '"></span>' +
        '<span class="name">' + esc(b.name) + '</span>' +
        '<span class="state">' + (b.online ? 'online' : 'offline') + '</span></div>' +
        '<div class="rows">' +
        '<div class="row"><span class="k">Kosten</span><span class="v">' + fmt(b.cost) + '</span></div>' +
        '<div class="row"><span class="k">Requests</span><span class="v">' + b.requests + '</span></div>' +
        '<div class="row"><span class="k">Zuletzt aktiv</span><span class="v">' + b.last_seen + '</span></div>' +
        '</div></div>';
    }).join('');
  } catch (e) {}
}

function tick() {
  const n = new Date();
  document.getElementById('clock').textContent =
    n.toLocaleTimeString('de-DE') + ' | ' + n.toLocaleDateString('de-DE', {weekday:'short', day:'2-digit', month:'short'});
}

var vpath = '';

async function vload(path) {
  vpath = path || '';
  try {
    const d = await (await fetch('/api/vault?path=' + encodeURIComponent(vpath))).json();
    var crumbHtml = '<a data-nav="">vault</a>';
    var acc = '';
    vpath.split('/').filter(Boolean).forEach(function(part) {
      acc = acc ? acc + '/' + part : part;
      crumbHtml += ' / <a data-nav="' + esc(acc) + '">' + esc(part) + '</a>';
    });
    document.getElementById('vcrumbs').innerHTML = crumbHtml;
    var items = '';
    (d.dirs || []).forEach(function(dir) {
      items += '<div class="vitem dir" data-nav="' + esc(dir.path) + '"><span class="n">' + esc(dir.name) + '</span></div>';
    });
    (d.files || []).forEach(function(f) {
      items += '<div class="vitem ' + f.kind + '" data-open="' + esc(f.path) + '" data-kind="' + f.kind + '">' +
               '<span class="n">' + esc(f.name) + '</span><span class="m">' + f.mtime + '</span></div>';
    });
    document.getElementById('vlist').innerHTML = items || '<div class="empty">Leer.</div>';
  } catch (e) {
    document.getElementById('vlist').innerHTML = '<div class="empty">Vault nicht erreichbar.</div>';
  }
}

async function vopen(path, kind) {
  const view = document.getElementById('vview');
  const enc = encodeURIComponent(path);
  const head = '<div class="vhead"><span class="t">' + esc(path) + '</span>' +
               '<a href="/api/vault/file?download=1&path=' + enc + '">Download</a></div>';
  if (kind === 'image') {
    view.innerHTML = head + '<img src="/api/vault/file?path=' + enc + '">';
  } else if (kind === 'text') {
    const txt = await (await fetch('/api/vault/file?path=' + enc)).text();
    view.innerHTML = head + '<pre>' + esc(txt) + '</pre>';
  } else {
    view.innerHTML = head + '<div class="empty">Binaerdatei - per Download oeffnen.</div>';
  }
}

document.addEventListener('click', function(ev) {
  var el = ev.target.closest('[data-nav],[data-open]');
  if (!el) return;
  if (el.hasAttribute('data-nav')) { vload(el.getAttribute('data-nav')); }
  else { vopen(el.getAttribute('data-open'), el.getAttribute('data-kind')); }
});

load(); tick(); vload('');
setInterval(load, 5000);
setInterval(tick, 1000);
</script>
</body>
</html>"""


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8090, log_level="warning")
