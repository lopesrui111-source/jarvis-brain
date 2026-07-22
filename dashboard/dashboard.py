#!/usr/bin/env python3
"""
JARVIS Dashboard v3 — Cinematic HUD
- Partikel-Sphaere (Canvas), Glassmorphism-Panels
- Agenten-Struktur (JARVIS -> CEO -> Marketing) mit Kosten/Status
- Vault-Drawer (aufklappbar): Ordner, Notizen, Bilder, Download
- Chat mit JARVIS / CEO / Marketing ueber den Redis-Bus
Port nur lokal gebunden — Zugriff per SSH-Tunnel.
"""

import os
import json
import uuid
from datetime import datetime

import redis
import psycopg2
import psycopg2.extras
from fastapi import FastAPI, Body
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, PlainTextResponse
import uvicorn

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
PG_HOST = os.getenv("POSTGRES_HOST", "postgres")
PG_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
PG_USER = os.getenv("POSTGRES_USER", "jarvis")
PG_PASS = os.getenv("POSTGRES_PASSWORD", "")
PG_DB   = os.getenv("POSTGRES_DB", "jarvis_brain")

VAULT_DIR = "/app/vault"
TEXT_EXT = (".md", ".txt", ".json", ".yml", ".yaml", ".csv")
IMG_EXT  = (".png", ".jpg", ".jpeg", ".webp", ".gif")

# Bot-Registry: Queue-Namen + Hierarchie fuers Frontend
BOTS = {
    "jarvis":       {"label": "JARVIS",        "inbox": "jarvis:inbox",        "reply": "jarvis:reply:{id}",        "parent": None},
    "buroflow-ceo": {"label": "BUEROFLOW-CEO", "inbox": "bot:ceo:inbox",       "reply": "bot:ceo:reply:{id}",       "parent": "jarvis"},
    "marketing":    {"label": "MARKETING",     "inbox": "bot:marketing:inbox", "reply": "bot:marketing:reply:{id}", "parent": "buroflow-ceo"},
}

app = FastAPI()


def pg():
    return psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER,
                            password=PG_PASS, dbname=PG_DB, connect_timeout=5)


def rds():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True,
                       socket_connect_timeout=3)


def count_listeners():
    try:
        r = rds()
        return sum(1 for c in r.client_list() if c.get("cmd", "").lower().startswith("blpop"))
    except Exception:
        return 0


@app.get("/api/stats")
def stats():
    listeners = count_listeners()
    out = {"listeners": listeners, "expected": len(BOTS),
           "today": 0.0, "month": 0.0, "total": 0.0,
           "requests": 0, "queue": 0, "bots": [], "log": []}
    try:
        r = rds()
        out["queue"] = sum(r.llen(b["inbox"]) for b in BOTS.values())
    except Exception:
        pass
    known = {}
    try:
        conn = pg()
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                  COALESCE(SUM(cost_usd) FILTER (WHERE created_at::date = CURRENT_DATE), 0) AS today,
                  COALESCE(SUM(cost_usd) FILTER (WHERE date_trunc('month', created_at) = date_trunc('month', now())), 0) AS month,
                  COALESCE(SUM(cost_usd), 0) AS total,
                  COUNT(*) AS requests
                FROM cost_ledger""")
            row = cur.fetchone()
            out.update({"today": float(row["today"]), "month": float(row["month"]),
                        "total": float(row["total"]), "requests": int(row["requests"])})
            cur.execute("""
                SELECT bot, COALESCE(SUM(cost_usd),0) AS cost, COUNT(*) AS requests, MAX(created_at) AS last_seen
                FROM cost_ledger GROUP BY bot""")
            for b in cur.fetchall():
                known[b["bot"]] = {"cost": float(b["cost"]), "requests": int(b["requests"]),
                                   "last_seen": b["last_seen"].strftime("%d.%m. %H:%M") if b["last_seen"] else "-"}
            cur.execute("""
                SELECT bot, model, cost_usd, created_at FROM cost_ledger
                ORDER BY created_at DESC LIMIT 8""")
            for e in cur.fetchall():
                out["log"].append({"t": e["created_at"].strftime("%H:%M:%S"), "bot": e["bot"],
                                   "cost": float(e["cost_usd"])})
        conn.close()
    except Exception as e:
        out["error"] = str(e)
    online_all = listeners >= len(BOTS)
    for key, meta in BOTS.items():
        k = known.get(key, {"cost": 0.0, "requests": 0, "last_seen": "-"})
        out["bots"].append({"id": key, "label": meta["label"], "parent": meta["parent"],
                            "cost": k["cost"], "requests": k["requests"], "last_seen": k["last_seen"],
                            "online": online_all or (key == "jarvis" and listeners > 0)})
    for name, k in known.items():
        if name not in BOTS:
            out["bots"].append({"id": name, "label": name.upper(), "parent": "jarvis",
                                "cost": k["cost"], "requests": k["requests"],
                                "last_seen": k["last_seen"], "online": False})
    return JSONResponse(out)


@app.post("/api/chat")
def chat(payload: dict = Body(...)):
    target = (payload.get("target") or "jarvis").strip().lower()
    text = (payload.get("text") or "").strip()
    if target not in BOTS:
        return JSONResponse({"error": f"Unbekanntes Ziel: {target}"}, status_code=400)
    if not text:
        return JSONResponse({"error": "Leere Nachricht"}, status_code=400)
    meta = BOTS[target]
    try:
        r = rds()
        req_id = str(uuid.uuid4())
        r.rpush(meta["inbox"], json.dumps({"id": req_id, "text": text}, ensure_ascii=False))
        resp = r.blpop(meta["reply"].format(id=req_id), timeout=240)
        if resp is None:
            return JSONResponse({"answer": "(Timeout — antwortet der Bot-Container?)"})
        return JSONResponse({"answer": resp[1]})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


def _safe_vault_path(rel: str) -> str:
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
                              "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%d.%m.%Y %H:%M"),
                              "kind": "image" if name.lower().endswith(IMG_EXT) else ("text" if name.lower().endswith(TEXT_EXT) else "file")})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    return JSONResponse({"path": path, "dirs": dirs, "files": files})


@app.get("/api/vault/file")
def vault_file(path: str = "", download: int = 0):
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


@app.post("/api/vault/delete")
def vault_delete(payload: dict = Body(...)):
    path = (payload.get("path") or "").strip()
    full = _safe_vault_path(path)
    if not full or not os.path.isfile(full):
        return JSONResponse({"error": "Datei nicht gefunden"}, status_code=404)
    try:
        os.remove(full)
        return JSONResponse({"deleted": path})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML


HTML = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>J.A.R.V.I.S</title>
<style>
  :root {
    --cyan: #59d7ff;
    --cyan-dim: rgba(89, 215, 255, .45);
    --green: #5DCAA5;
    --red: #ff5f6b;
    --txt: #d6f2ff;
    --dim: #5f8ba3;
    --glass: rgba(16, 32, 46, .38);
    --glass-line: rgba(89, 215, 255, .18);
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    background: radial-gradient(ellipse at 50% 42%, #0a1d2b 0%, #050d15 55%, #02070c 100%);
    color: var(--txt); overflow: hidden;
    font-family: 'Cascadia Code', 'Consolas', 'Segoe UI', monospace;
    letter-spacing: .06em;
  }
  #space { position: fixed; inset: 0; z-index: 0; }

  .hud { position: fixed; inset: 0; z-index: 2; pointer-events: none; }
  .hud > * { pointer-events: auto; }

  header {
    position: absolute; top: 0; left: 0; right: 0;
    display: flex; align-items: center; justify-content: space-between;
    padding: 18px 28px;
  }
  .brand { font-size: 22px; font-weight: 700; letter-spacing: .45em; color: #eaf9ff;
           text-shadow: 0 0 18px var(--cyan-dim); }
  .sub { position: absolute; left: 50%; transform: translateX(-50%);
         font-size: 11px; color: var(--cyan); letter-spacing: .5em; opacity: .85; }
  .sub::after { content: ""; display: block; height: 1px; margin-top: 6px;
                background: linear-gradient(90deg, transparent, var(--cyan), transparent); }
  body.thinking .sub { animation: subpulse 1s ease-in-out infinite; }
  @keyframes subpulse {
    0%, 100% { opacity: .85; text-shadow: 0 0 8px rgba(89, 215, 255, .3); }
    50% { opacity: 1; text-shadow: 0 0 22px rgba(93, 255, 210, .9); }
  }
  .clock { font-size: 26px; color: #eaf9ff; text-shadow: 0 0 14px var(--cyan-dim);
           font-variant-numeric: tabular-nums; text-align: right; }
  .clock small { display: block; font-size: 10px; color: var(--dim); letter-spacing: .4em; }

  .panel {
    background: var(--glass);
    border: 1px solid var(--glass-line);
    border-radius: 12px;
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    box-shadow: 0 0 30px rgba(0, 0, 0, .35), inset 0 0 22px rgba(89, 215, 255, .04);
    padding: 14px 16px;
  }
  .panel h3 { font-size: 10px; color: var(--cyan); letter-spacing: .35em; margin-bottom: 12px;
              display: flex; justify-content: space-between; align-items: center; }
  .panel h3::before { content: "// "; color: var(--dim); }
  .col-left .panel h3 { cursor: pointer; user-select: none; }
  .col-left .panel h3 .chev { width: 7px; height: 7px; border-right: 1.5px solid var(--cyan);
    border-bottom: 1.5px solid var(--cyan); transform: rotate(45deg); transition: transform .25s;
    opacity: .7; margin-right: 2px; }
  .col-left .panel.collapsed h3 .chev { transform: rotate(-45deg); }
  .col-left .panel.collapsed h3 { margin-bottom: 0; }
  .col-left .panel.collapsed > *:not(h3) { display: none; }

  .col-left { position: absolute; top: 84px; left: 24px; width: 265px;
              display: flex; flex-direction: column; gap: 14px; max-height: calc(100% - 110px);
              transition: opacity .3s, transform .3s; }
  .kv { display: flex; justify-content: space-between; font-size: 11.5px; padding: 4px 0;
        border-bottom: 1px solid rgba(89, 215, 255, .07); }
  .kv:last-child { border-bottom: none; }
  .kv .k { color: var(--dim); }
  .kv .v { font-variant-numeric: tabular-nums; }
  .kv .v.green { color: var(--green); }
  .kv .v.cyan { color: var(--cyan); }

  .tree { position: relative; }
  .treewrap { position: relative; }
  .treewrap svg { display: block; }
  .bnode { position: absolute; border: 1px solid rgba(89, 215, 255, .22); border-radius: 9px;
           background: rgba(9, 22, 33, .72); backdrop-filter: blur(6px);
           padding: 6px 10px; display: flex; flex-direction: column; justify-content: center; gap: 3px;
           transition: box-shadow .3s, border-color .3s; }
  .bnode.on { border-color: rgba(93, 202, 165, .4); box-shadow: 0 0 14px rgba(93, 202, 165, .12); }
  .bnode.busy { animation: nodepulse 1.1s ease-in-out infinite; }
  @keyframes nodepulse {
    0%, 100% { box-shadow: 0 0 10px rgba(89, 215, 255, .15); border-color: rgba(89, 215, 255, .3); }
    50% { box-shadow: 0 0 26px rgba(89, 215, 255, .55); border-color: rgba(89, 215, 255, .85); }
  }
  .bnode .bl { display: flex; align-items: center; gap: 7px; font-size: 11px; letter-spacing: .12em; }
  .bnode .bm { display: flex; justify-content: space-between; font-size: 9.5px; color: var(--dim);
               font-variant-numeric: tabular-nums; }
  .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--red); flex: none; }
  .dot.on { background: var(--green); box-shadow: 0 0 9px rgba(93, 202, 165, .8); }

  .logbox { font-size: 10.5px; display: flex; flex-direction: column; gap: 5px;
            max-height: 130px; overflow: hidden; }
  .logbox div { color: var(--dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .logbox b { color: var(--cyan); font-weight: 400; }

  /* Chat rechts */
  .chat { position: absolute; top: 84px; right: 24px; bottom: 24px; width: 340px;
          display: flex; flex-direction: column; }
  .chat .msgs { flex: 1; overflow-y: auto; display: flex; flex-direction: column;
                gap: 10px; padding: 4px 2px; scrollbar-width: thin; }
  .msg { max-width: 92%; padding: 9px 12px; border-radius: 10px; font-size: 12px;
         line-height: 1.55; white-space: pre-wrap; word-break: break-word; }
  .msg.me { align-self: flex-end; background: rgba(89, 215, 255, .12);
            border: 1px solid rgba(89, 215, 255, .25); }
  .msg.bot { align-self: flex-start; background: rgba(9, 22, 33, .6);
             border: 1px solid rgba(89, 215, 255, .1); }
  .msg.bot b { color: var(--cyan); font-weight: 400; font-size: 10px; letter-spacing: .2em;
               display: block; margin-bottom: 4px; }
  .chatbar { display: flex; gap: 8px; margin-top: 10px; }
  .chatbar select, .chatbar input {
    background: rgba(9, 22, 33, .7); border: 1px solid var(--glass-line); color: var(--txt);
    border-radius: 8px; padding: 10px; font-family: inherit; font-size: 12px; outline: none;
  }
  .chatbar select { width: 92px; }
  .chatbar input { flex: 1; }
  .chatbar input:focus { border-color: var(--cyan-dim); box-shadow: 0 0 12px rgba(89, 215, 255, .15); }
  .typing { font-size: 10px; color: var(--dim); letter-spacing: .3em; height: 14px; margin-top: 4px; }

  /* Vault-Modal */
  .vtab { position: absolute; left: 0; top: 50%; transform: translateY(-50%);
          writing-mode: vertical-rl;
          background: var(--glass); border: 1px solid var(--glass-line); border-left: none;
          border-radius: 0 10px 10px 0; padding: 16px 7px; font-size: 11px; letter-spacing: .4em;
          color: var(--cyan); cursor: pointer; backdrop-filter: blur(10px); user-select: none; }
  .vtab:hover { box-shadow: 0 0 18px rgba(89, 215, 255, .25); }
  .vbackdrop { position: fixed; inset: 0; background: rgba(2, 8, 14, .55);
               backdrop-filter: blur(6px); opacity: 0; pointer-events: none;
               transition: opacity .25s; z-index: 8; }
  .vbackdrop.open { opacity: 1; pointer-events: auto; }
  .vmodal { position: fixed; top: 50%; left: 50%; width: min(1040px, 92vw); height: min(680px, 86vh);
            transform: translate(-50%, -50%) scale(.97); opacity: 0; pointer-events: none;
            transition: opacity .25s, transform .25s; z-index: 9;
            display: flex; flex-direction: column; background: rgba(7, 16, 25, .97) !important; }
  .vmodal.open { opacity: 1; transform: translate(-50%, -50%) scale(1); pointer-events: auto; }
  .vmhead { display: flex; align-items: center; gap: 14px; padding-bottom: 12px;
            border-bottom: 1px solid var(--glass-line); margin-bottom: 12px; }
  .vmhead .title { font-size: 12px; color: var(--cyan); letter-spacing: .35em; }
  .vmhead .vcrumbs { margin: 0; flex: 1; }
  .vmhead .vsearch { margin: 0; width: 200px; }
  .vclose { cursor: pointer; color: var(--dim); font-size: 16px; padding: 2px 8px;
            border: 1px solid transparent; border-radius: 8px; }
  .vclose:hover { color: var(--red); border-color: rgba(255, 95, 107, .35);
                  text-shadow: 0 0 10px rgba(255, 95, 107, .6); }
  .vbody { flex: 1; display: flex; gap: 14px; min-height: 0; }
  .vbody .vlistwrap { width: 340px; display: flex; flex-direction: column; min-height: 0; }
  .vsearch { background: rgba(9, 22, 33, .7); border: 1px solid var(--glass-line); color: var(--txt);
             border-radius: 8px; padding: 8px 10px; font-family: inherit; font-size: 11px;
             outline: none; }
  .vsearch:focus { border-color: var(--cyan-dim); box-shadow: 0 0 12px rgba(89, 215, 255, .12); }
  .vcrumbs { font-size: 11px; color: var(--dim); word-break: break-all; }
  .vcrumbs a { color: var(--cyan); cursor: pointer; text-decoration: none; }
  .vcrumbs a:hover { text-shadow: 0 0 8px rgba(89, 215, 255, .5); }
  .vlist { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 4px;
           scrollbar-width: thin; padding-right: 4px; }
  .vgrid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 9px; margin-bottom: 10px; }
  .vcard { position: relative; border: 1px solid rgba(89, 215, 255, .14); border-radius: 10px;
           overflow: hidden; cursor: pointer; aspect-ratio: 1; background: rgba(9, 22, 33, .55);
           display: flex; align-items: center; justify-content: center;
           animation: fadeUp .3s ease both; transition: border-color .2s, box-shadow .2s, transform .2s; }
  .vcard:hover { border-color: rgba(89, 215, 255, .6); box-shadow: 0 0 18px rgba(89, 215, 255, .25);
                 transform: translateY(-2px); }
  .vcard img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .vcard .cap { position: absolute; left: 0; right: 0; bottom: 0; font-size: 8.5px; padding: 4px 7px;
                background: linear-gradient(transparent, rgba(2, 10, 16, .92)); color: var(--txt);
                white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .vcard.folder { font-size: 11px; color: var(--cyan); flex-direction: column; gap: 6px;
                  letter-spacing: .08em; text-align: center; padding: 8px; aspect-ratio: auto;
                  min-height: 60px; }
  .vcard.folder .fic { font-size: 20px; text-shadow: 0 0 12px rgba(89, 215, 255, .5); }
  .vcard .del { position: absolute; top: 5px; right: 5px; z-index: 2; color: var(--dim);
                background: rgba(2, 10, 16, .75); border-radius: 6px; padding: 1px 6px; font-size: 11px; }
  .vcard .del:hover { color: var(--red); text-shadow: 0 0 8px rgba(255, 95, 107, .7); }
  .vitem { display: flex; align-items: center; justify-content: space-between; gap: 8px;
           padding: 8px 10px; border-radius: 8px; font-size: 11.5px; cursor: pointer;
           border: 1px solid transparent; animation: fadeUp .3s ease both; }
  .vitem:hover { background: rgba(89, 215, 255, .07); border-color: rgba(89, 215, 255, .18); }
  .vitem .n { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .vitem .m { color: var(--dim); font-size: 9.5px; flex: none; }
  .vitem .del { flex: none; color: var(--dim); padding: 0 4px; border-radius: 5px; }
  .vitem .del:hover { color: var(--red); text-shadow: 0 0 8px rgba(255, 95, 107, .6); }
  .vview { flex: 1; overflow: auto; scrollbar-width: thin; border: 1px solid rgba(89, 215, 255, .1);
           border-radius: 10px; padding: 14px; background: rgba(5, 13, 21, .5); min-width: 0; }
  .vview pre { white-space: pre-wrap; word-break: break-word; font-size: 11.5px; line-height: 1.65; }
  .vview img { max-width: 100%; max-height: 520px; object-fit: contain; display: block;
               margin: 0 auto; border-radius: 8px; border: 1px solid var(--glass-line); }
  .vhead { display: flex; justify-content: space-between; gap: 12px; align-items: center;
           margin-bottom: 12px; }
  .vhead .t { font-size: 11px; word-break: break-all; color: var(--cyan); }
  .vhead a { color: var(--green); font-size: 10.5px; text-decoration: none; flex: none;
             letter-spacing: .2em; }
  .vhead a:hover { text-shadow: 0 0 10px rgba(93, 202, 165, .6); }
  @keyframes fadeUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }

  footer { position: absolute; bottom: 0; left: 0; right: 0; display: flex;
           justify-content: space-between; padding: 12px 28px; font-size: 10px;
           color: var(--dim); letter-spacing: .3em; }
  footer b { color: var(--cyan); font-weight: 400; }

  ::-webkit-scrollbar { width: 5px; }
  ::-webkit-scrollbar-thumb { background: rgba(89, 215, 255, .2); border-radius: 3px; }
</style>
</head>
<body>
<canvas id="space"></canvas>

<div class="hud">
  <header>
    <div class="brand">J.A.R.V.I.S</div>
    <div class="sub">NEURAL CORE AKTIV</div>
    <div class="clock"><span id="time">--:--:--</span><small id="date"></small></div>
  </header>

  <div class="col-left">
    <div class="panel">
      <h3>SYSTEMSTATUS <span style="display:flex;align-items:center;gap:10px"><span class="dot on" id="sysdot"></span><span class="chev"></span></span></h3>
      <div class="kv"><span class="k">LISTENER</span><span class="v cyan" id="s-listen">-/-</span></div>
      <div class="kv"><span class="k">KOSTEN HEUTE</span><span class="v green" id="s-today">$0.0000</span></div>
      <div class="kv"><span class="k">KOSTEN MONAT</span><span class="v" id="s-month">$0.0000</span></div>
      <div class="kv"><span class="k">KOSTEN GESAMT</span><span class="v" id="s-total">$0.0000</span></div>
      <div class="kv"><span class="k">REQUESTS</span><span class="v" id="s-req">0</span></div>
      <div class="kv"><span class="k">QUEUE</span><span class="v" id="s-queue">0</span></div>
    </div>

    <div class="panel">
      <h3>AGENTEN-STRUKTUR <span class="chev"></span></h3>
      <div class="tree" id="tree"><div class="empty">Lade...</div></div>
    </div>

    <div class="panel">
      <h3>AKTIVITAET <span class="chev"></span></h3>
      <div class="logbox" id="log"><div class="empty">-</div></div>
    </div>
  </div>

  <div class="vtab" id="vtab">VAULT</div>
  <div class="vbackdrop" id="vbackdrop"></div>
  <div class="vmodal panel" id="vmodal">
    <div class="vmhead">
      <span class="title">VAULT</span>
      <div class="vcrumbs" id="vcrumbs"></div>
      <input class="vsearch" id="vsearch" placeholder="Suchen..." autocomplete="off">
      <span class="vclose" id="vclose">\u2715</span>
    </div>
    <div class="vbody">
      <div class="vlistwrap"><div class="vlist" id="vlist"></div></div>
      <div class="vview" id="vview"><div class="empty">Datei anklicken.</div></div>
    </div>
  </div>

  <div class="chat panel">
    <h3>KOMMUNIKATION</h3>
    <div class="msgs" id="msgs"></div>
    <div class="typing" id="typing"></div>
    <div class="chatbar">
      <select id="target">
        <option value="jarvis">JARVIS</option>
        <option value="buroflow-ceo">CEO</option>
        <option value="marketing">MARKETING</option>
      </select>
      <input id="input" placeholder="Nachricht..." autocomplete="off">
    </div>
  </div>

  <footer>
    <span>SESSION <b id="f-session">00:00</b></span>
    <span>STATUS <b>NOMINAL</b></span>
    <span>SYSTEM <b id="f-online">ONLINE</b></span>
  </footer>
</div>

<script>
/* ── Plasma-Kern ── */
var canvas = document.getElementById('space');
var ctx = canvas.getContext('2d');
var W, H, CX, CY, R;
function resize() {
  W = canvas.width = window.innerWidth;
  H = canvas.height = window.innerHeight;
  CX = W / 2; CY = H * 0.47;
  R = Math.min(W, H) * 0.33;
}
window.addEventListener('resize', resize);
resize();

var N = 340;
var pts = [];
for (var i = 0; i < N; i++) {
  var phi = Math.acos(1 - 2 * (i + 0.5) / N);
  var theta = Math.PI * (1 + Math.sqrt(5)) * i;
  pts.push({
    x: Math.sin(phi) * Math.cos(theta), y: Math.cos(phi), z: Math.sin(phi) * Math.sin(theta),
    o1: Math.random() * 6.28, o2: Math.random() * 6.28,
    f1: 0.6 + Math.random() * 0.9, f2: 1.2 + Math.random() * 1.6,
    sx: 0, sy: 0, sz: 0, sa: 0
  });
}

var rot = 0;
var energy = 0;
var energyTarget = 0;
var bolts = [];
var lastBolt = 0;
function setEnergy(v) { energyTarget = v; }

function spawnBolt() {
  var start = Math.floor(Math.random() * N);
  var erupt = Math.random() < 0.45;
  var chain = [start];
  var cur = start;
  var len = 5 + Math.floor(Math.random() * 5);
  for (var s = 0; s < len; s++) {
    var best = -1, bestD = 1e9;
    for (var t = 0; t < 14; t++) {
      var cand = Math.floor(Math.random() * N);
      if (chain.indexOf(cand) >= 0) continue;
      var a = pts[cur], b = pts[cand];
      var d = (a.x - b.x) * (a.x - b.x) + (a.y - b.y) * (a.y - b.y) + (a.z - b.z) * (a.z - b.z);
      if (d < bestD) { bestD = d; best = cand; }
    }
    if (best < 0) break;
    chain.push(best);
    cur = best;
  }
  bolts.push({ chain: chain, life: 1, erupt: erupt, out: 0.25 + Math.random() * 0.45 });
}

function draw() {
  ctx.clearRect(0, 0, W, H);
  energy += (energyTarget - energy) * 0.06;
  rot += 0.0015 + energy * 0.010;
  var t = Date.now() / 1000;

  var beat = 1 + energy * 0.10 * (0.5 + 0.5 * Math.sin(Date.now() / 170)) * Math.abs(Math.sin(Date.now() / 540));
  var Rb = R * beat;

  if (energy > 0.03) {
    var glow = ctx.createRadialGradient(CX, CY, 0, CX, CY, Rb * 0.9);
    glow.addColorStop(0, 'rgba(93, 255, 200,' + (0.11 * energy) + ')');
    glow.addColorStop(0.5, 'rgba(89, 215, 255,' + (0.05 * energy) + ')');
    glow.addColorStop(1, 'rgba(89, 215, 255, 0)');
    ctx.fillStyle = glow;
    ctx.fillRect(CX - Rb, CY - Rb, Rb * 2, Rb * 2);
  }


  var cosR = Math.cos(rot), sinR = Math.sin(rot);
  var wob = Math.sin(t / 3.8) * 0.14;
  var cosW = Math.cos(wob), sinW = Math.sin(wob);

  // Punkte projizieren (mit organischem Noise-Wabern)
  for (var i = 0; i < N; i++) {
    var p = pts[i];
    var wobble = 1 + (0.07 + energy * 0.09) * Math.sin(t * p.f1 + p.o1) +
                     (0.04 + energy * 0.06) * Math.sin(t * p.f2 + p.o2);
    var x = p.x * cosR - p.z * sinR;
    var z = p.x * sinR + p.z * cosR;
    var y = p.y * cosW - z * sinW;
    z = p.y * sinW + z * cosW;
    var scale = 1 / (1.65 - z * 0.62);
    p.sx = CX + x * Rb * wobble * scale;
    p.sy = CY + y * Rb * wobble * scale;
    p.sz = z;
    p.sa = Math.max(0, (z + 1) / 2);
  }

  // Plexus-Linien zwischen nahen Punkten
  var linkDist = Rb * (0.155 + energy * 0.03);
  var flicker = 0.75 + 0.25 * Math.sin(t * 9);
  for (var a1 = 0; a1 < N; a1++) {
    var pa = pts[a1];
    for (var b1 = a1 + 1; b1 < N; b1++) {
      var pb = pts[b1];
      var dx = pa.sx - pb.sx, dy = pa.sy - pb.sy;
      if (dx > linkDist || dx < -linkDist || dy > linkDist || dy < -linkDist) continue;
      var d = Math.sqrt(dx * dx + dy * dy);
      if (d > linkDist) continue;
      var depth = (pa.sa + pb.sa) / 2;
      var alpha = (1 - d / linkDist) * (0.10 + depth * (0.22 + energy * 0.22)) * flicker;
      ctx.beginPath();
      ctx.moveTo(pa.sx, pa.sy); ctx.lineTo(pb.sx, pb.sy);
      ctx.strokeStyle = 'rgba(' + Math.floor(100 - energy * 10) + ',' + Math.floor(215 + energy * 40) + ',' +
                        Math.floor(255 - energy * 55) + ',' + alpha + ')';
      ctx.lineWidth = 0.6 + depth * 0.5;
      ctx.stroke();
    }
  }

  // Punkte
  for (var i2 = 0; i2 < N; i2++) {
    var p2 = pts[i2];
    var tw = 0.6 + 0.4 * Math.sin(t * 2.2 + p2.o1);
    ctx.beginPath();
    ctx.arc(p2.sx, p2.sy, Math.max(0.5, (1.5 + energy * 1.1) * (0.6 + p2.sa * 0.8) * tw), 0, 6.283);
    ctx.fillStyle = 'rgba(' + Math.floor(120 - energy * 15) + ',' + Math.floor(225 + energy * 30) + ',' +
                    Math.floor(255 - energy * 60) + ',' + (0.10 + p2.sa * (0.6 + energy * 0.3) * tw) + ')';
    ctx.fill();
  }

  // Energie-Blitze
  var boltEvery = 560 - energy * 380;
  if (Date.now() - lastBolt > boltEvery) { spawnBolt(); if (energy > 0.5) { spawnBolt(); spawnBolt(); } lastBolt = Date.now(); }
  ctx.save();
  ctx.shadowColor = 'rgba(150, 255, 240, .9)';
  for (var bi = bolts.length - 1; bi >= 0; bi--) {
    var bolt = bolts[bi];
    bolt.life *= 0.86;
    if (bolt.life < 0.05) { bolts.splice(bi, 1); continue; }
    ctx.shadowBlur = 10 * bolt.life;
    ctx.beginPath();
    var cl = bolt.chain.length;
    for (var ci = 0; ci < cl; ci++) {
      var bp = pts[bolt.chain[ci]];
      var bx = bp.sx, by = bp.sy;
      if (bolt.erupt) {
        var f = 1 + bolt.out * (ci / cl) * (0.6 + bolt.life);
        bx = CX + (bp.sx - CX) * f;
        by = CY + (bp.sy - CY) * f;
      }
      if (ci === 0) ctx.moveTo(bx, by); else ctx.lineTo(bx, by);
    }
    ctx.strokeStyle = 'rgba(180, 255, 245,' + (bolt.life * (0.5 + energy * 0.4)) + ')';
    ctx.lineWidth = 1.1 + bolt.life * 0.9;
    ctx.stroke();
  }
  ctx.restore();

  requestAnimationFrame(draw);
}
draw();

/* ── Helpers ── */
function esc(s) { return String(s).replace(/[&<>"]/g, function(c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
function fmt(n) { return '$' + n.toFixed(4); }

/* ── Uhr + Session ── */
var t0 = Date.now();
function tick() {
  var n = new Date();
  document.getElementById('time').textContent = n.toLocaleTimeString('de-DE');
  document.getElementById('date').textContent = n.toLocaleDateString('de-DE', {day:'2-digit', month:'short'}).toUpperCase();
  var s = Math.floor((Date.now() - t0) / 1000);
  document.getElementById('f-session').textContent =
    String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
}
setInterval(tick, 1000); tick();

/* ── Stats ── */
async function load() {
  try {
    var s = await (await fetch('/api/stats')).json();
    document.getElementById('s-listen').textContent = s.listeners + '/' + s.expected;
    document.getElementById('s-today').textContent = fmt(s.today);
    document.getElementById('s-month').textContent = fmt(s.month);
    document.getElementById('s-total').textContent = fmt(s.total);
    document.getElementById('s-req').textContent = s.requests;
    document.getElementById('s-queue').textContent = s.queue;
    document.getElementById('sysdot').className = 'dot ' + (s.listeners > 0 ? 'on' : '');
    document.getElementById('f-online').textContent = s.listeners > 0 ? 'ONLINE' : 'OFFLINE';

    renderTree(s.bots);

    document.getElementById('log').innerHTML = (s.log || []).map(function(e) {
      return '<div>' + e.t + ' <b>' + esc(e.bot) + '</b> ' + fmt(e.cost) + '</div>';
    }).join('') || '<div class="empty">-</div>';
  } catch (e) {}
}
function renderTree(bots) {
  var byId = {}, children = {};
  bots.forEach(function(b) { byId[b.id] = b; });
  bots.forEach(function(b) {
    var p = (b.parent && byId[b.parent]) ? b.parent : (b.parent ? 'root' : 'root');
    if (b.parent && byId[b.parent]) { (children[b.parent] = children[b.parent] || []).push(b); }
    else { (children['root'] = children['root'] || []).push(b); }
  });
  var levels = [];
  function walk(list, depth) {
    if (!list || !list.length) return;
    levels[depth] = (levels[depth] || []).concat(list);
    list.forEach(function(b) { walk(children[b.id], depth + 1); });
  }
  walk(children['root'], 0);

  var Wp = 233, NH = 46, GAP = 30, PADT = 8;
  var Hp = PADT + levels.length * (NH + GAP) - GAP + 8;
  var pos = {};
  var svg = '<svg width="' + Wp + '" height="' + Hp + '" viewBox="0 0 ' + Wp + ' ' + Hp + '">';
  levels.forEach(function(lv, d) {
    var slice = Wp / lv.length;
    lv.forEach(function(b, i) {
      pos[b.id] = { x: slice * i + slice / 2, y: PADT + d * (NH + GAP) + NH / 2, w: Math.min(slice - 8, 210) };
    });
  });
  // Verbindungen + Fluss-Partikel
  bots.forEach(function(b) {
    if (!b.parent || !pos[b.parent] || !pos[b.id]) return;
    var a = pos[b.parent], c = pos[b.id];
    var y1 = a.y + NH / 2, y2 = c.y - NH / 2;
    var path = 'M ' + a.x + ' ' + y1 + ' C ' + a.x + ' ' + (y1 + 16) + ', ' + c.x + ' ' + (y2 - 16) + ', ' + c.x + ' ' + y2;
    svg += '<path d="' + path + '" fill="none" stroke="rgba(89,215,255,.35)" stroke-width="1"/>';
    svg += '<circle r="2" fill="#59d7ff"><animateMotion dur="2.6s" repeatCount="indefinite" path="' + path + '"/></circle>';
  });
  svg += '</svg>';

  var html = '<div class="treewrap">' + svg;
  bots.forEach(function(b) {
    var p = pos[b.id];
    if (!p) return;
    html += '<div class="bnode' + (b.online ? ' on' : '') + '" data-bot="' + esc(b.id) + '" style="left:' +
      (p.x - p.w / 2) + 'px;top:' + (p.y - NH / 2) + 'px;width:' + p.w + 'px;height:' + NH + 'px">' +
      '<div class="bl"><span class="dot ' + (b.online ? 'on' : '') + '"></span>' + esc(b.label) + '</div>' +
      '<div class="bm"><span>' + fmt(b.cost) + '</span><span>' + b.requests + ' req</span></div></div>';
  });
  html += '</div>';
  var wrap = document.getElementById('tree');
  wrap.style.height = Hp + 'px';
  wrap.innerHTML = html;
}

setInterval(load, 5000); load();

/* ── Chat ── */
var msgs = document.getElementById('msgs');
var input = document.getElementById('input');
var busy = false;

function addMsg(cls, who, text) {
  var d = document.createElement('div');
  d.className = 'msg ' + cls;
  d.innerHTML = (who ? '<b>' + esc(who) + '</b>' : '') + esc(text);
  msgs.appendChild(d);
  msgs.scrollTop = msgs.scrollHeight;
}

input.addEventListener('keydown', async function(ev) {
  if (ev.key !== 'Enter' || busy) return;
  var text = input.value.trim();
  if (!text) return;
  var target = document.getElementById('target').value;
  input.value = '';
  addMsg('me', '', text);
  busy = true;
  setEnergy(1);
  document.body.classList.add('thinking');
  var bn = document.querySelector('[data-bot="' + target + '"]');
  if (bn) bn.classList.add('busy');
  document.getElementById('typing').textContent = target.toUpperCase() + ' DENKT...';
  try {
    var r = await fetch('/api/chat', { method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ target: target, text: text }) });
    var d = await r.json();
    addMsg('bot', target.toUpperCase(), d.answer || d.error || '(keine Antwort)');
  } catch (e) {
    addMsg('bot', 'SYSTEM', 'Fehler: ' + e);
  }
  busy = false;
  setEnergy(0);
  document.body.classList.remove('thinking');
  document.querySelectorAll('.bnode.busy').forEach(function(n) { n.classList.remove('busy'); });
  document.getElementById('typing').textContent = '';
});

/* ── Vault-Modal ── */
var vmodal = document.getElementById('vmodal');
var vbackdrop = document.getElementById('vbackdrop');
function vaultOpen() { vmodal.classList.add('open'); vbackdrop.classList.add('open'); vload(vpath); }
function vaultClose() { vmodal.classList.remove('open'); vbackdrop.classList.remove('open'); }
document.getElementById('vtab').addEventListener('click', vaultOpen);
document.getElementById('vclose').addEventListener('click', vaultClose);
vbackdrop.addEventListener('click', vaultClose);
document.addEventListener('keydown', function(ev) { if (ev.key === 'Escape') vaultClose(); });

var vpath = '';
var vdata = null;
async function vload(path) {
  vpath = path || '';
  try {
    vdata = await (await fetch('/api/vault?path=' + encodeURIComponent(vpath))).json();
    vrender();
  } catch (e) {
    document.getElementById('vlist').innerHTML = '<div class="empty">Vault nicht erreichbar.</div>';
  }
}

function vrender() {
  var d = vdata || {};
  var q = (document.getElementById('vsearch').value || '').toLowerCase();
  var crumbHtml = '<a data-nav="">vault</a>';
  var acc = '';
  vpath.split('/').filter(Boolean).forEach(function(part) {
    acc = acc ? acc + '/' + part : part;
    crumbHtml += ' / <a data-nav="' + esc(acc) + '">' + esc(part) + '</a>';
  });
  var nf = (d.dirs || []).length + (d.files || []).length;
  document.getElementById('vcrumbs').innerHTML = crumbHtml + ' <span style="color:var(--dim)">(' + nf + ')</span>';

  var i = 0;
  function delay() { return ' style="animation-delay:' + (Math.min(i++, 20) * 28) + 'ms"'; }
  var dirsHtml = '';
  (d.dirs || []).filter(function(x) { return x.name.toLowerCase().includes(q); }).forEach(function(dir) {
    dirsHtml += '<div class="vcard folder" data-nav="' + esc(dir.path) + '"' + delay() + '>' +
                '<span class="fic">\u25C8</span><span>' + esc(dir.name) + '</span></div>';
  });
  var imgsHtml = '';
  var rowsHtml = '';
  (d.files || []).filter(function(x) { return x.name.toLowerCase().includes(q); }).forEach(function(f) {
    var enc = encodeURIComponent(f.path);
    if (f.kind === 'image') {
      imgsHtml += '<div class="vcard" data-open="' + esc(f.path) + '" data-kind="image"' + delay() + '>' +
                  '<img loading="lazy" src="/api/vault/file?path=' + enc + '">' +
                  '<span class="del" data-del="' + esc(f.path) + '">\u2715</span>' +
                  '<span class="cap">' + esc(f.name) + '</span></div>';
    } else {
      rowsHtml += '<div class="vitem" data-open="' + esc(f.path) + '" data-kind="' + f.kind + '"' + delay() + '>' +
                  '<span class="n">' + esc(f.name) + '</span><span class="m">' + f.mtime + '</span>' +
                  '<span class="del" data-del="' + esc(f.path) + '">\u2715</span></div>';
    }
  });
  var html = '';
  if (dirsHtml) html += '<div class="vgrid">' + dirsHtml + '</div>';
  if (imgsHtml) html += '<div class="vgrid">' + imgsHtml + '</div>';
  html += rowsHtml;
  document.getElementById('vlist').innerHTML = html || '<div class="empty">Leer.</div>';
}

async function vopen(path, kind) {
  var view = document.getElementById('vview');
  var enc = encodeURIComponent(path);
  var head = '<div class="vhead"><span class="t">' + esc(path) + '</span>' +
             '<a href="/api/vault/file?download=1&path=' + enc + '">DOWNLOAD</a></div>';
  if (kind === 'image') {
    view.innerHTML = head + '<img src="/api/vault/file?path=' + enc + '">';
  } else if (kind === 'text') {
    var txt = await (await fetch('/api/vault/file?path=' + enc)).text();
    view.innerHTML = head + '<pre>' + esc(txt) + '</pre>';
  } else {
    view.innerHTML = head + '<div class="empty">Binaerdatei - per Download oeffnen.</div>';
  }
}

document.getElementById('vsearch').addEventListener('input', function() { vrender(); });

document.querySelectorAll('.col-left .panel h3').forEach(function(h) {
  h.addEventListener('click', function() { h.parentElement.classList.toggle('collapsed'); });
});

document.addEventListener('click', async function(ev) {
  var del = ev.target.closest('[data-del]');
  if (del) {
    ev.stopPropagation();
    var p = del.getAttribute('data-del');
    if (!confirm('Wirklich loeschen? ' + p)) return;
    try {
      var r = await fetch('/api/vault/delete', { method: 'POST',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ path: p }) });
      if (r.ok) { vload(vpath); document.getElementById('vview').innerHTML = '<div class="empty">Geloescht.</div>'; }
    } catch (e) {}
    return;
  }
  var el = ev.target.closest('[data-nav],[data-open]');
  if (!el) return;
  if (el.hasAttribute('data-nav')) { vload(el.getAttribute('data-nav')); }
  else { vopen(el.getAttribute('data-open'), el.getAttribute('data-kind')); }
});
</script>
</body>
</html>"""


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8090, log_level="warning")
