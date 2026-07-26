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
import requests
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

# Buroflow-Datenbank (Supabase). Verbindungsstring: Supabase → Settings → Database → URI
SUPABASE_URL = os.getenv("SUPABASE_DB_URL", "")
BF_T_WAITLIST = os.getenv("BF_TABLE_WAITLIST", "waitlist")
BF_T_USERS    = os.getenv("BF_TABLE_USERS", "user_profiles")
BF_T_SUBS     = os.getenv("BF_TABLE_SUBS", "subscriptions")
BF_T_GEN      = os.getenv("BF_TABLE_GENERATIONS", "generations")
BF_T_USAGE    = os.getenv("BF_TABLE_USAGE", "ai_usage")

# Umami (Besucherstatistik). Cloud: https://api.umami.is | Self-hosted: eigene URL
UMAMI_URL = os.getenv("UMAMI_URL", "https://api.umami.is").rstrip("/")
UMAMI_KEY = os.getenv("UMAMI_API_KEY", "")
UMAMI_SITE = os.getenv("UMAMI_WEBSITE_ID", "")
# Kostenlose Alternative zur API: oeffentlicher Share-Link (Umami Cloud, kein Pro noetig)
UMAMI_SHARE = os.getenv("UMAMI_SHARE_URL", "").strip().rstrip("/")
TEXT_EXT = (".md", ".txt", ".json", ".yml", ".yaml", ".csv")
IMG_EXT  = (".png", ".jpg", ".jpeg", ".webp", ".gif")

# Bot-Registry: Queue-Namen + Hierarchie fuers Frontend
BOTS = {
    "jarvis":       {"label": "JARVIS",        "inbox": "jarvis:inbox",        "reply": "jarvis:reply:{id}",        "parent": None,           "desc": "orchestrator",              "history": "jarvis:history"},
    "buroflow-ceo": {"label": "CEO",           "inbox": "bot:ceo:inbox",       "reply": "bot:ceo:reply:{id}",       "parent": "jarvis",       "desc": "strategie & entscheidungen", "history": "bot:ceo:history"},
    "marketing":    {"label": "MARKETING",     "inbox": "bot:marketing:inbox", "reply": "bot:marketing:reply:{id}", "parent": "buroflow-ceo", "desc": "content, creatives, skills", "history": "bot:marketing:history"},
    "immo":         {"label": "IMMO",          "inbox": "bot:immo:inbox",      "reply": "bot:immo:reply:{id}",      "parent": "jarvis",       "desc": "rendite-analysen, telegram", "history": "bot:immo:history"},
    "seo":          {"label": "SEO",           "inbox": "bot:seo:inbox",       "reply": "bot:seo:reply:{id}",       "parent": "buroflow-ceo", "desc": "gutefrage + quora, entwuerfe", "history": "bot:seo:history"},
}

app = FastAPI()


def pg():
    return psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER,
                            password=PG_PASS, dbname=PG_DB, connect_timeout=5)


def rds(socket_timeout=15):
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True,
                       socket_connect_timeout=5, socket_timeout=socket_timeout,
                       socket_keepalive=True, health_check_interval=20,
                       retry_on_timeout=True)


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
                SELECT bot, COALESCE(SUM(cost_usd),0) AS cost, COUNT(*) AS requests, MAX(created_at) AS last_seen,
                       MAX(created_at) > now() - interval '10 minutes' AS recent
                FROM cost_ledger GROUP BY bot""")
            for b in cur.fetchall():
                known[b["bot"]] = {"cost": float(b["cost"]), "requests": int(b["requests"]),
                                   "recent": bool(b["recent"]),
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
    spark = {}
    try:
        conn2 = pg()
        with conn2, conn2.cursor() as cur2:
            cur2.execute("SELECT bot, EXTRACT(EPOCH FROM (now() - created_at)) / 3600.0 AS hrs_ago, "
                        "cost_usd FROM cost_ledger WHERE created_at > now() - interval '6 hours'")
            for bot_name, hrs_ago, cost_usd in cur2.fetchall():
                idx = 5 - min(int(hrs_ago), 5)
                arr = spark.setdefault(bot_name, [0.0] * 6)
                arr[idx] += float(cost_usd)
        conn2.close()
    except Exception:
        pass

    online_all = listeners >= len(BOTS)
    for key, meta in BOTS.items():
        k = known.get(key, {"cost": 0.0, "requests": 0, "last_seen": "-", "recent": False})
        out["bots"].append({"id": key, "label": meta["label"], "parent": meta["parent"],
                            "desc": meta.get("desc", "agent"),
                            "cost": k["cost"], "requests": k["requests"], "last_seen": k["last_seen"],
                            "spark": spark.get(key, [0.0] * 6),
                            "online": online_all or k.get("recent", False) or (key == "jarvis" and listeners > 0)})
    for name, k in known.items():
        if name not in BOTS:
            out["bots"].append({"id": name, "label": name.upper(), "parent": "jarvis", "desc": "agent",
                                "cost": k["cost"], "requests": k["requests"],
                                "last_seen": k["last_seen"], "spark": spark.get(name, [0.0] * 6), "online": False})
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
        return JSONResponse({"id": req_id, "target": target})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/chat/history")
def chat_history(target: str = "jarvis", n: int = 20):
    """Liest den Gespraechsverlauf des Bots aus Redis (das, woran er sich erinnert)."""
    target = (target or "").strip().lower()
    if target not in BOTS:
        return JSONResponse({"messages": []})
    key = BOTS[target].get("history")
    if not key:
        return JSONResponse({"messages": []})
    try:
        r = rds()
        raw = r.get(key)
        if not raw:
            return JSONResponse({"messages": []})
        verlauf = json.loads(raw)
    except Exception as e:
        return JSONResponse({"messages": [], "error": str(e)[:120]})
    out = []
    for m in verlauf[-min(max(n, 1), 60):]:
        inhalt = m.get("content")
        if isinstance(inhalt, list):
            inhalt = " ".join(b.get("text", "") for b in inhalt if isinstance(b, dict) and b.get("type") == "text")
        if not isinstance(inhalt, str) or not inhalt.strip():
            continue
        # Auto-Recall-Anhaenge nicht anzeigen
        inhalt = inhalt.split("\n\n[AUTO-RECALL")[0].strip()
        out.append({"role": m.get("role", "user"), "text": inhalt})
    return JSONResponse({"messages": out, "target": target})


@app.get("/api/chat/poll")
def chat_poll(target: str = "jarvis", id: str = ""):
    """Holt die Antwort ab, sobald sie da ist. Blockiert nur kurz — nie minutenlang."""
    target = (target or "").strip().lower()
    if target not in BOTS or not id:
        return JSONResponse({"status": "error", "error": "Ziel oder ID fehlt"}, status_code=400)
    key = BOTS[target]["reply"].format(id=id)
    try:
        r = rds(socket_timeout=20)
        resp = r.blpop(key, timeout=8)
        if resp is None:
            return JSONResponse({"status": "pending"})
        return JSONResponse({"status": "done", "answer": resp[1]})
    except Exception as e:
        # Verbindungsproblem heisst nicht, dass der Bot fertig ist -> weiter pollen
        return JSONResponse({"status": "pending", "hinweis": str(e)[:120]})


def _safe_vault_path(rel: str) -> str:
    rel = (rel or "").strip().lstrip("/")
    full = os.path.realpath(os.path.join(VAULT_DIR, rel))
    root = os.path.realpath(VAULT_DIR)
    if not (full == root or full.startswith(root + os.sep)):
        return ""
    return full


def bf_conn():
    if not SUPABASE_URL:
        raise RuntimeError("SUPABASE_DB_URL fehlt")
    return psycopg2.connect(SUPABASE_URL, connect_timeout=8)


def _one(cur, sql, default=0):
    """Einzelwert holen; bei fehlender Tabelle/Spalte sauber default zurueckgeben."""
    try:
        cur.execute(sql)
        row = cur.fetchone()
        if not row or row[0] is None:
            return default
        return row[0]
    except Exception:
        cur.connection.rollback()
        return default


def _rows(cur, sql):
    try:
        cur.execute(sql)
        return cur.fetchall()
    except Exception:
        cur.connection.rollback()
        return []


@app.get("/api/buroflow")
def buroflow():
    out = {"ok": False, "tables": [], "error": None}
    try:
        conn = bf_conn()
    except Exception as e:
        out["error"] = str(e)
        return JSONResponse(out)
    try:
        with conn, conn.cursor() as cur:
            out["tables"] = [r[0] for r in _rows(cur,
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' ORDER BY table_name")]

            out["waitlist"] = int(_one(cur, f"SELECT COUNT(*) FROM {BF_T_WAITLIST}"))
            out["waitlist_7d"] = int(_one(cur,
                f"SELECT COUNT(*) FROM {BF_T_WAITLIST} WHERE created_at > now() - interval '7 days'"))
            out["users"] = int(_one(cur, f"SELECT COUNT(*) FROM {BF_T_USERS}"))
            if not out["users"]:
                out["users"] = int(_one(cur, "SELECT COUNT(*) FROM users"))
            out["users_7d"] = int(_one(cur,
                f"SELECT COUNT(*) FROM {BF_T_USERS} WHERE created_at > now() - interval '7 days'"))
            out["subs"] = int(_one(cur, f"SELECT COUNT(*) FROM {BF_T_SUBS} WHERE status = 'active'"))
            out["generations"] = int(_one(cur, f"SELECT COUNT(*) FROM {BF_T_GEN}"))
            out["gen_ok"] = None  # wird unten gesetzt
            out["gen_7d"] = int(_one(cur,
                f"SELECT COUNT(*) FROM {BF_T_GEN} WHERE created_at > now() - interval '7 days'"))
            def _first(*sqls):
                """Erste Query, die einen Wert liefert (Tabellen-/Spaltennamen unsicher)."""
                for s in sqls:
                    v = _one(cur, s, None)
                    if v is not None:
                        return v
                return 0

            out["tokens_in"] = int(_first(
                f"SELECT SUM(input_tokens) FROM {BF_T_USAGE}",
                f"SELECT SUM(tokens_in) FROM {BF_T_USAGE}",
                f"SELECT SUM(input_tokens) FROM {BF_T_GEN}"))
            out["tokens_out"] = int(_first(
                f"SELECT SUM(output_tokens) FROM {BF_T_USAGE}",
                f"SELECT SUM(tokens_out) FROM {BF_T_USAGE}",
                f"SELECT SUM(output_tokens) FROM {BF_T_GEN}"))
            out["cost_total"] = float(_first(
                f"SELECT SUM(cost_usd) FROM {BF_T_USAGE}",
                f"SELECT SUM(cost) FROM {BF_T_USAGE}",
                f"SELECT SUM(cost_usd) FROM {BF_T_GEN}"))
            out["cost_7d"] = float(_first(
                f"SELECT SUM(cost_usd) FROM {BF_T_USAGE} WHERE created_at > now() - interval '7 days'",
                f"SELECT SUM(cost) FROM {BF_T_USAGE} WHERE created_at > now() - interval '7 days'",
                f"SELECT SUM(cost_usd) FROM {BF_T_GEN} WHERE created_at > now() - interval '7 days'"))
            out["ki_calls"] = int(_first(f"SELECT COUNT(*) FROM {BF_T_USAGE}"))
            gok = _first(f"SELECT COUNT(*) FROM {BF_T_GEN} WHERE success = true",
                         f"SELECT COUNT(*) FROM {BF_T_GEN} WHERE status = 'success'",
                         f"SELECT COUNT(*) FROM {BF_T_GEN} WHERE error IS NULL")
            out["gen_ok"] = int(gok) if gok else out.get("generations", 0)
            out["active_users_7d"] = int(_one(cur,
                f"SELECT COUNT(DISTINCT user_id) FROM {BF_T_GEN} WHERE created_at > now() - interval '7 days'"))

            out["per_tool"] = [{"tool": r[0] or "?", "n": int(r[1])} for r in _rows(cur,
                f"SELECT tool, COUNT(*) FROM {BF_T_GEN} GROUP BY tool ORDER BY COUNT(*) DESC LIMIT 8")]
            out["per_day"] = [{"d": r[0].strftime("%d.%m."), "n": int(r[1])} for r in _rows(cur,
                f"SELECT created_at::date AS d, COUNT(*) FROM {BF_T_GEN} "
                f"WHERE created_at > now() - interval '14 days' GROUP BY d ORDER BY d")]
            out["per_plan"] = [{"plan": r[0] or "?", "n": int(r[1])} for r in _rows(cur,
                f"SELECT plan, COUNT(*) FROM {BF_T_SUBS} WHERE status='active' GROUP BY plan ORDER BY plan")]
        conn.close()
        out["ok"] = True
    except Exception as e:
        out["error"] = str(e)
        try:
            conn.close()
        except Exception:
            pass
    return JSONResponse(out)


@app.get("/api/umami")
def umami(tage: int = 7):
    out = {"ok": False, "error": None, "share": UMAMI_SHARE}
    if not UMAMI_KEY or not UMAMI_SITE:
        out["error"] = ("Kein API-Zugang (Umami Cloud erlaubt das nur im Pro-Plan)."
                        if not UMAMI_SHARE else "share")
        return JSONResponse(out)
    import time as _t
    end = int(_t.time() * 1000)
    start = end - tage * 86400 * 1000
    headers = {"x-umami-api-key": UMAMI_KEY, "Authorization": f"Bearer {UMAMI_KEY}",
               "Accept": "application/json"}
    base = f"{UMAMI_URL}/v1/websites/{UMAMI_SITE}"

    def _get(path, params):
        try:
            r = requests.get(base + path, params=params, headers=headers, timeout=15)
            if r.status_code >= 400:
                return None, f"HTTP {r.status_code}: {r.text[:120]}"
            return r.json(), None
        except Exception as e:
            return None, f"{type(e).__name__}: {e}"

    stats, err = _get("/stats", {"startAt": start, "endAt": end})
    if err:
        out["error"] = err
        return JSONResponse(out)

    def _v(key):
        d = (stats or {}).get(key) or {}
        if isinstance(d, dict):
            return float(d.get("value") or 0), float(d.get("prev") or 0)
        return float(d or 0), 0.0

    pv, pv_p = _v("pageviews")
    vis, vis_p = _v("visitors")
    ses, ses_p = _v("visits")
    bounces, _ = _v("bounces")
    tt, _ = _v("totaltime")

    out.update({
        "tage": tage,
        "visitors": int(vis), "visitors_prev": int(vis_p),
        "pageviews": int(pv), "pageviews_prev": int(pv_p),
        "visits": int(ses), "visits_prev": int(ses_p),
        "bounce_pct": round(bounces / ses * 100) if ses else 0,
        "avg_sec": round(tt / ses) if ses else 0,
    })

    pages, _e1 = _get("/metrics", {"startAt": start, "endAt": end, "type": "url", "limit": 6})
    refs, _e2 = _get("/metrics", {"startAt": start, "endAt": end, "type": "referrer", "limit": 6})
    out["pages"] = [{"x": p.get("x") or "/", "y": int(p.get("y") or 0)} for p in (pages or [])][:6]
    out["refs"] = [{"x": p.get("x") or "direkt", "y": int(p.get("y") or 0)} for p in (refs or [])][:6]
    out["ok"] = True
    return JSONResponse(out)


@app.get("/api/jobs")
def jobs():
    try:
        conn = pg()
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, titel, schritte, aktueller_schritt, status, "
                        "to_char(updated_at,'HH24:MI') AS zeit FROM jobs "
                        "WHERE status IN ('offen','laeuft') OR updated_at > now() - interval '2 hours' "
                        "ORDER BY id DESC LIMIT 6")
            rows = cur.fetchall()
        conn.close()
        out = []
        for r in rows:
            n = len(r["schritte"] or [])
            i = r["aktueller_schritt"] or 0
            out.append({"id": r["id"], "titel": r["titel"], "status": r["status"],
                        "schritt": min(i + 1, n) if r["status"] == "laeuft" else i,
                        "gesamt": n, "zeit": r["zeit"],
                        "aktuell": (r["schritte"] or [""])[i] if (r["status"] == "laeuft" and i < n) else ""})
        return JSONResponse({"jobs": out})
    except Exception as e:
        return JSONResponse({"jobs": [], "error": str(e)})


@app.get("/api/memory")
def memory_graph():
    try:
        conn = pg()
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, project, title, source, LEFT(content, 400) AS content, "
                        "to_char(created_at, 'DD.MM.YYYY') AS created FROM memory "
                        "ORDER BY id DESC LIMIT 400")
            rows = cur.fetchall()
        conn.close()
        return JSONResponse({"nodes": [dict(r) for r in rows]})
    except Exception as e:
        return JSONResponse({"error": str(e), "nodes": []}, status_code=500)


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
  #space, #brain { position: fixed; inset: 0; z-index: 0; }

  .hud { position: fixed; inset: 0; z-index: 2; pointer-events: none; }
  .hud > * { pointer-events: auto; }

  header {
    position: absolute; top: 0; left: 0; right: 0;
    display: flex; align-items: center; justify-content: space-between;
    padding: 18px 28px; z-index: 6;
  }
  .brand { font-size: 22px; font-weight: 700; letter-spacing: .45em; color: #eaf9ff;
           text-shadow: 0 0 18px var(--cyan-dim); }
  .viewtabs { position: absolute; left: 50%; transform: translateX(-50%); display: flex; gap: 4px;
              border: 1px solid var(--glass-line); border-radius: 20px; padding: 4px;
              background: var(--glass); backdrop-filter: blur(10px); }
  .vt { font-size: 10px; letter-spacing: .35em; padding: 6px 16px 6px 19px; border-radius: 16px;
        color: var(--dim); cursor: pointer; user-select: none; transition: all .25s; }
  .vt.active { color: #eaf9ff; background: rgba(89, 215, 255, .12);
               text-shadow: 0 0 10px rgba(89, 215, 255, .5); }
  .vt:hover { color: var(--cyan); }
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

  .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--red); flex: none; }
  .dot.on { background: var(--green); box-shadow: 0 0 9px rgba(93, 202, 165, .8); }

  /* Bueroflow-Reiter */
  .bfView { position: absolute; inset: 0; overflow-y: auto; overflow-x: hidden;
            scrollbar-width: thin; padding: 88px 26px 34px; z-index: 1; }
  .bfInner { max-width: 1080px; margin: 0 auto; }
  .bfHero { backdrop-filter: blur(16px); border: 0.5px solid rgba(93, 202, 165, .32);
            border-radius: 16px; padding: 20px 24px; margin-bottom: 14px; position: relative; overflow: hidden;
            background: linear-gradient(150deg, rgba(93, 202, 165, .16), rgba(9, 22, 33, .6));
            box-shadow: 0 6px 28px rgba(0, 0, 0, .32), inset 0 1px 0 rgba(255, 255, 255, .06);
            display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; flex-wrap: wrap; }
  .bfHero .lbl { font-size: 9.5px; letter-spacing: .22em; color: var(--dim); margin-bottom: 8px; }
  .bfHero .big { font-size: 34px; font-weight: 600; color: #f2fbff; letter-spacing: -.01em;
                 text-shadow: 0 0 22px rgba(93, 202, 165, .28); }
  .bfHero .sub { font-size: 10px; color: var(--dim); margin-top: 6px; }
  .bfHero .big.green { color: var(--green); }
  .bfGrid { display: grid; grid-template-columns: repeat(auto-fit, minmax(168px, 1fr)); gap: 12px; margin-bottom: 16px; }
  .bfCard { backdrop-filter: blur(14px); background: linear-gradient(160deg, rgba(89, 215, 255, .09), rgba(9, 22, 33, .58));
            border: 0.5px solid rgba(89, 215, 255, .2); border-radius: 13px; padding: 14px 16px;
            box-shadow: 0 4px 18px rgba(0, 0, 0, .28), inset 0 1px 0 rgba(255, 255, 255, .05); }
  .bfCard .k { font-size: 9px; letter-spacing: .2em; color: var(--dim); margin-bottom: 9px; }
  .bfCard .v { font-size: 24px; font-weight: 600; color: #f2fbff; font-variant-numeric: tabular-nums; }
  .bfCard .s { font-size: 9.5px; color: var(--dim); margin-top: 5px; }
  .bfSection { font-size: 9.5px; letter-spacing: .3em; color: var(--green); margin: 22px 0 12px; }
  .bfWide { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 12px; }
  .bfPanel { backdrop-filter: blur(14px); background: rgba(9, 22, 33, .5);
             border: 0.5px solid rgba(89, 215, 255, .15); border-radius: 13px; padding: 16px 18px; }
  .bfPanel .t { font-size: 10px; letter-spacing: .18em; color: var(--dim); margin-bottom: 14px; }
  .bfBar { display: flex; align-items: center; gap: 10px; margin-bottom: 9px; font-size: 10.5px; }
  .bfBar .n { width: 108px; color: var(--txt); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .bfBar .track { flex: 1; height: 9px; background: rgba(255, 255, 255, .05); border-radius: 5px; overflow: hidden; }
  .bfBar .fill { height: 100%; border-radius: 5px; transition: width .6s cubic-bezier(.2,.8,.2,1); }
  .bfBar .val { width: 34px; text-align: right; color: var(--dim); font-variant-numeric: tabular-nums; }
  .bfSpark { display: flex; gap: 3px; align-items: flex-end; height: 74px; margin-top: 6px; }
  .bfSpark span { flex: 1; background: linear-gradient(180deg, rgba(93,202,165,.85), rgba(93,202,165,.25));
                  border-radius: 3px 3px 0 0; min-height: 2px; }
  .bfSpark .lbls { display: flex; }
  .bfDays { display: flex; justify-content: space-between; font-size: 8px; color: var(--dim); margin-top: 6px; }
  .bfRing { display: flex; align-items: center; justify-content: center; gap: 20px; }
  .bfRing .txt { text-align: center; }
  .bfRing .pct { font-size: 26px; font-weight: 600; color: var(--green); }
  .bfRing .cap { font-size: 9px; letter-spacing: .2em; color: var(--dim); margin-top: 4px; }
  .bfFunnel .step { margin-bottom: 13px; }
  .bfFunnel .head { display: flex; justify-content: space-between; font-size: 10.5px; margin-bottom: 5px; }
  .bfFunnel .head b { color: var(--txt); font-weight: 400; }
  .bfFunnel .head span { color: var(--dim); font-size: 9.5px; }
  .bfErr { border: 0.5px solid rgba(255, 95, 107, .4); background: rgba(60, 10, 16, .5);
           border-radius: 12px; padding: 16px 18px; color: #ffd6da; font-size: 11px; line-height: 1.7; }
  .bfErr b { color: #ff9aa4; font-weight: 400; }

  /* Agenten-Reiter: Org-Chart auf eigenem, blickdichtem Grund (keine Kugel im Hintergrund) */
  .agentsView { position: absolute; inset: 0; overflow: hidden;
                display: flex; padding: 90px 26px 30px; z-index: 1; }
  #agChart { transform-origin: 0 0; }
  .agAurora { position: fixed; inset: 0; pointer-events: none; z-index: 0; }
  .agAurora i { position: absolute; border-radius: 50%; filter: blur(70px); opacity: .16; }
  .agAurora i:nth-child(1) { width: 560px; height: 560px; left: 8%; top: 12%;
    background: radial-gradient(circle, #1b5f7a, transparent 65%); animation: adrift1 26s ease-in-out infinite alternate; }
  .agAurora i:nth-child(2) { width: 480px; height: 480px; right: 6%; top: 34%;
    background: radial-gradient(circle, #1d6b52, transparent 65%); animation: adrift2 31s ease-in-out infinite alternate; }
  .agAurora i:nth-child(3) { width: 420px; height: 420px; left: 38%; bottom: 4%;
    background: radial-gradient(circle, #4a3a70, transparent 65%); animation: adrift1 37s ease-in-out infinite alternate-reverse; }
  @keyframes adrift1 { from { transform: translate(0, 0) scale(1); } to { transform: translate(70px, -50px) scale(1.15); } }
  @keyframes adrift2 { from { transform: translate(0, 0) scale(1.1); } to { transform: translate(-80px, 60px) scale(.95); } }
  .agInner { max-width: 1040px; width: 100%; margin: auto; }
  .agSvg { position: absolute; top: 0; left: 0; pointer-events: none; }
  .agNode { position: absolute; backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
            border-radius: 15px; padding: 15px 17px; cursor: grab; overflow: hidden;
            box-shadow: 0 6px 26px rgba(0, 0, 0, .35), inset 0 1px 0 rgba(255, 255, 255, .06);
            transition: transform .25s, box-shadow .3s; }
  .agNode::after { content: ""; position: absolute; inset: -60% -20%; pointer-events: none;
    background: linear-gradient(115deg, transparent 42%, rgba(255, 255, 255, .045) 50%, transparent 58%);
    animation: agsweep 7s linear infinite; }
  @keyframes agsweep { from { transform: translateX(-55%); } to { transform: translateX(55%); } }
  .agNode:hover { transform: translateY(-3px) scale(1.015); }
  .agNode.enter { animation: agenter .5s cubic-bezier(.2, .8, .25, 1) both; }
  @keyframes agenter { from { opacity: 0; transform: translateY(16px) scale(.96); } to { opacity: 1; transform: none; } }
  .agNode::before { content: ""; position: absolute; top: 0; left: 8%; right: 8%; height: 1px;
                     background: linear-gradient(90deg, transparent, rgba(255, 255, 255, .16), transparent); }
  .agNode:hover { transform: translateY(-2px); }
  .agNode.busy { animation: agcardpulse 1.4s ease-in-out infinite; }
  @keyframes agcardpulse {
    0%, 100% { filter: brightness(1); }
    50% { filter: brightness(1.3); }
  }
  .agLayer { font-size: 8px; letter-spacing: .26em; color: var(--dim); margin-bottom: 10px; opacity: .8; }
  .agLayer b { color: inherit; }
  .agTop { display: flex; align-items: center; gap: 9px; }
  .agMono { width: 26px; height: 26px; border-radius: 50%; flex: none; display: flex;
            align-items: center; justify-content: center; font-size: 9.5px; font-weight: 500;
            letter-spacing: 0; }
  .agName { font-size: 13px; letter-spacing: .12em; font-weight: 600; color: #f6fcff; }
  .agDesc { font-size: 9.5px; color: var(--dim); margin: 9px 0 11px; line-height: 1.55; }
  .agDiv { border-top: 0.5px solid rgba(255, 255, 255, .09); margin: 0 0 8px; }
  .agRow { display: flex; align-items: center; justify-content: space-between; font-size: 9.5px;
           color: var(--dim); margin-bottom: 4px; font-variant-numeric: tabular-nums; }
  .agRow .l { display: flex; align-items: center; gap: 7px; letter-spacing: .12em; }
  .agRow .cost { font-size: 15px; color: var(--green); font-weight: 600; letter-spacing: 0;
                 text-shadow: 0 0 12px rgba(93, 202, 165, .35); }
  .agPing { position: relative; width: 7px; height: 7px; border-radius: 50%; display: inline-block; flex: none; }
  .agPing.on::after { content: ""; position: absolute; inset: -4px; border-radius: 50%;
    border: 1px solid currentColor; animation: agping 2s ease-out infinite; }
  @keyframes agping { 0% { transform: scale(.4); opacity: .9; } 100% { transform: scale(1.5); opacity: 0; } }
  .agSpark { display: flex; gap: 3px; align-items: flex-end; height: 16px; margin: 10px 0 2px; }
  .agSpark span { flex: 1; border-radius: 2px 2px 0 0; min-height: 2px; }
  .agCoreNode { text-align: center; }
  .agCoreNode .agTop { justify-content: center; }
  .agCoreWrap { position: relative; width: 40px; height: 40px; flex: none; }
  .agCoreWrap::before { content: ""; position: absolute; inset: -4px; border-radius: 50%;
    background: conic-gradient(from 0deg, rgba(89, 215, 255, .0), rgba(89, 215, 255, .75), rgba(93, 202, 165, .4), rgba(89, 215, 255, 0));
    animation: agspin 5s linear infinite; filter: blur(1.5px); }
  @keyframes agspin { to { transform: rotate(360deg); } }
  .agCoreRing { position: absolute; inset: 3px; border-radius: 50%;
                background: radial-gradient(circle at 35% 30%, #ffffff, #9fe3ff 45%, #59d7ff 100%);
                box-shadow: 0 0 22px rgba(89, 215, 255, .55); animation: agcorepulse 2.2s ease-in-out infinite; }
  @keyframes agcorepulse {
    0%, 100% { box-shadow: 0 0 18px rgba(89, 215, 255, .45); }
    50% { box-shadow: 0 0 30px rgba(89, 215, 255, .8); }
  }

  .logbox { font-size: 10.5px; display: flex; flex-direction: column; gap: 5px;
            max-height: 130px; overflow: hidden; }
  .logbox div { color: var(--dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .logbox b { color: var(--cyan); font-weight: 400; }
  .jobitem { margin-bottom: 10px; }
  .jobitem:last-child { margin-bottom: 0; }
  .jobtop { display: flex; justify-content: space-between; font-size: 10.5px; margin-bottom: 4px; }
  .jobtop b { color: var(--txt); font-weight: 400; overflow: hidden; text-overflow: ellipsis;
              white-space: nowrap; max-width: 165px; }
  .jobtop span { color: var(--dim); font-size: 9px; flex: none; }
  .jobbar { height: 5px; background: rgba(255,255,255,.06); border-radius: 3px; overflow: hidden; }
  .jobbar i { display: block; height: 100%; background: var(--cyan); border-radius: 3px;
              transition: width .6s cubic-bezier(.2,.8,.2,1); }
  .jobbar.fertig i { background: var(--green); }
  .jobbar.fehler i { background: var(--red); }
  .jobstep { font-size: 9px; color: var(--dim); margin-top: 4px; overflow: hidden;
             text-overflow: ellipsis; white-space: nowrap; }

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
  .verlaufmark { text-align: center; font-size: 8.5px; letter-spacing: .25em; color: var(--dim);
                 margin: 6px 0 2px; opacity: .55; }

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

  .braindetail { position: absolute; right: 24px; top: 84px; width: 320px; max-height: 60vh;
                 overflow: auto; z-index: 4; }
  .braindetail h3 { display: flex; justify-content: space-between; }
  .bdbody { font-size: 12px; line-height: 1.6; }
  .bdbody .bt { color: var(--cyan); font-size: 12.5px; margin-bottom: 6px; }
  .bdbody .bm { color: var(--dim); font-size: 10px; margin-bottom: 10px; letter-spacing: .15em; }
  .brainlegend { position: absolute; left: 24px; bottom: 46px; display: flex; flex-wrap: wrap;
                 gap: 10px; font-size: 10px; color: var(--dim); letter-spacing: .15em; z-index: 4;
                 max-width: 50vw; }
  .brainlegend span { display: flex; align-items: center; gap: 5px; }
  .brainlegend i { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
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
<canvas id="brain" style="display:none"></canvas>

<div class="hud">
  <header>
    <div class="brand">J.A.R.V.I.S</div>
    <div class="viewtabs">
      <span class="vt active" data-view="0">CORE</span>
      <span class="vt" data-view="2">AGENTEN</span>
      <span class="vt" data-view="3">BÜROFLOW</span>
      <span class="vt" data-view="1">GEHIRN</span>
    </div>
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

    <div class="panel" id="jobPanel" style="display:none">
      <h3>AUFTRÄGE <span class="chev"></span></h3>
      <div id="joblist"></div>
    </div>

    <div class="panel">
      <h3>AKTIVITÄT <span class="chev"></span></h3>
      <div class="logbox" id="log"><div class="empty">-</div></div>
    </div>
  </div>

  <div class="bfView" id="bfView" style="display:none">
    <div class="bfInner" id="bfInner"><div class="empty">Lade Kennzahlen …</div></div>
  </div>

  <div class="agentsView" id="agentsView" style="display:none">
    <div class="agAurora"><i></i><i></i><i></i></div>
    <div class="agInner">
      <div id="agChart" style="position:relative;"></div>
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
        <option value="immo">IMMO</option>
        <option value="seo">SEO</option>
      </select>
      <input id="input" placeholder="Nachricht..." autocomplete="off">
    </div>
  </div>

  <div class="braindetail panel" id="braindetail" style="display:none">
    <h3>ERINNERUNG <span class="vclose" id="bdclose">\u2715</span></h3>
    <div id="bdbody" class="bdbody"></div>
  </div>
  <div class="brainlegend" id="brainlegend" style="display:none"></div>

  <footer>
    <span>SESSION <b id="f-session">00:00</b></span>
  </footer>
</div>

<script>
window.onerror = function(msg, srcf, line, col) {
  var el = document.getElementById('errbox') || (function() {
    var d = document.createElement('div');
    d.id = 'errbox';
    d.style.cssText = 'position:fixed;bottom:8px;left:50%;transform:translateX(-50%);z-index:99;' +
      'background:rgba(60,10,16,.92);border:1px solid #ff5f6b;color:#ffd6da;font:11px Consolas,monospace;' +
      'padding:8px 14px;border-radius:8px;max-width:80vw;';
    document.body.appendChild(d);
    return d;
  })();
  el.textContent = 'JS-FEHLER: ' + msg + ' (Zeile ' + line + ')';
  return false;
};
/* ── Plasma-Kern ── */
var canvas = document.getElementById('space');
var ctx = canvas.getContext('2d');
var W, H, CX, CY, R;
function resize() {
  W = canvas.width = window.innerWidth;
  H = canvas.height = window.innerHeight;
  CX = W / 2; CY = H * 0.5;
  R = Math.min(W, H) * 0.46;
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

/* ── Bueroflow-Ansicht ── */
var bfTimer = null;
var BF_COLORS = ['#5DCAA5', '#59d7ff', '#c792ea', '#ffd479', '#ff8fa3'];

function bfNum(n) { return (n || 0).toLocaleString('de-DE'); }
function bfEur(n) { return (n || 0).toLocaleString('de-DE', {minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' \u20ac'; }
function bfUsd(n) { return '$' + (n || 0).toFixed(4); }

function bfTrend(now, prev) {
  if (!prev) return '';
  var diff = Math.round((now - prev) / prev * 100);
  if (!isFinite(diff) || diff === 0) return '';
  var up = diff > 0;
  return '<span style="font-size:9px;margin-left:7px;color:' + (up ? 'var(--green)' : '#ff8fa3') + '">' +
         (up ? '\u2191' : '\u2193') + ' ' + Math.abs(diff) + ' %</span>';
}

async function loadUmami() {
  var box = document.getElementById('bfUmami');
  if (!box) return;
  try {
    var u = await (await fetch('/api/umami?tage=7')).json();
    if (!u.ok) {
      if (u.share) {
        box.innerHTML =
          '<div class="bfPanel" style="padding:0;overflow:hidden">' +
          '<iframe src="' + esc(u.share) + '" title="Umami" ' +
          'style="width:100%;height:720px;border:0;border-radius:12px;background:#0b1620" ' +
          'loading="lazy" referrerpolicy="no-referrer"></iframe></div>' +
          '<div style="font-size:9px;color:var(--dim);margin-top:8px">' +
          'Live aus Umami \u00b7 <a href="' + esc(u.share) + '" target="_blank" rel="noreferrer" ' +
          'style="color:var(--cyan);text-decoration:none">in neuem Tab \u00f6ffnen</a></div>';
      } else {
        box.innerHTML = '<div class="bfPanel"><div class="t">BESUCHER</div>' +
          '<div class="empty" style="line-height:1.7">Nicht verbunden.<br>' + esc(u.error || '') + '</div></div>';
      }
      return;
    }
    var mins = Math.floor((u.avg_sec || 0) / 60), secs = (u.avg_sec || 0) % 60;
    var h = '<div class="bfGrid">' +
      '<div class="bfCard"><div class="k">BESUCHER 7T</div><div class="v">' + bfNum(u.visitors) +
      bfTrend(u.visitors, u.visitors_prev) + '</div><div class="s">eindeutige Personen</div></div>' +
      '<div class="bfCard"><div class="k">SITZUNGEN</div><div class="v">' + bfNum(u.visits) +
      bfTrend(u.visits, u.visits_prev) + '</div><div class="s">Besuche gesamt</div></div>' +
      '<div class="bfCard"><div class="k">SEITENAUFRUFE</div><div class="v">' + bfNum(u.pageviews) +
      bfTrend(u.pageviews, u.pageviews_prev) + '</div><div class="s">Views</div></div>' +
      '<div class="bfCard"><div class="k">ABSPRUNGRATE</div><div class="v">' + (u.bounce_pct || 0) + ' %</div>' +
      '<div class="s">\u00d8 Dauer ' + mins + 'm ' + secs + 's</div></div>' +
      '</div>';

    function liste(titel, arr, farbe) {
      var max = Math.max.apply(null, (arr || []).map(function(x) { return x.y; }).concat([1]));
      var inner = (arr || []).length ? arr.map(function(x) {
        var name = String(x.x || '/').replace(/^https?:\\/\\//, '');
        if (name.length > 24) name = name.substring(0, 23) + '\u2026';
        return '<div class="bfBar"><span class="n" title="' + esc(String(x.x)) + '">' + esc(name) + '</span>' +
          '<span class="track"><span class="fill" style="width:' + Math.round(x.y / max * 100) +
          '%;background:' + farbe + '"></span></span><span class="val">' + x.y + '</span></div>';
      }).join('') : '<div class="empty">Noch keine Daten.</div>';
      return '<div class="bfPanel"><div class="t">' + titel + '</div>' + inner + '</div>';
    }
    h += '<div class="bfWide">' + liste('MEISTBESUCHTE SEITEN', u.pages, '#5DCAA5') +
         liste('WOHER DIE BESUCHER KOMMEN', u.refs, '#59d7ff') + '</div>';
    box.innerHTML = h;
  } catch (e) {
    box.innerHTML = '<div class="bfPanel"><div class="empty">Umami nicht erreichbar.</div></div>';
  }
}

async function loadBuroflow() {
  var box = document.getElementById('bfInner');
  try {
    var d = await (await fetch('/api/buroflow')).json();
    if (!d.ok) {
      box.innerHTML = '<div class="bfErr"><b>Keine Verbindung zur Bueroflow-Datenbank.</b><br>' +
        esc(d.error || 'unbekannter Fehler') +
        '<br><br>Pruefe SUPABASE_DB_URL in der .env auf dem Server.</div>';
      return;
    }
    var gen = d.generations || 0;
    var ok = d.gen_ok || 0;
    var quote = gen ? Math.round(ok / gen * 100) : 0;
    var proGen = ok ? (d.cost_total || 0) / ok : 0;
    var eurKurs = 0.92;

    var html = '';
    // Hero
    html += '<div class="bfHero">' +
      '<div><div class="lbl">CLAUDE-KOSTEN GESAMT</div>' +
      '<div class="big green">' + bfUsd(d.cost_total) + '</div>' +
      '<div class="sub">\u2248 ' + bfEur((d.cost_total || 0) * eurKurs) + ' \u00b7 7 Tage: ' + bfUsd(d.cost_7d) + '</div></div>' +
      '<div style="text-align:right"><div class="lbl">GENERIERUNGEN</div>' +
      '<div class="big">' + bfNum(gen) + '</div>' +
      '<div class="sub">' + bfNum(d.gen_7d) + ' in 7 Tagen \u00b7 \u00d8 ' + bfUsd(proGen) + ' pro Stueck</div></div></div>';

    // KPI-Karten
    html += '<div class="bfGrid">' +
      '<div class="bfCard"><div class="k">WARTELISTE</div><div class="v">' + bfNum(d.waitlist) + '</div>' +
      '<div class="s">+' + bfNum(d.waitlist_7d) + ' in 7 Tagen</div></div>' +
      '<div class="bfCard"><div class="k">REGISTRIERTE NUTZER</div><div class="v">' + bfNum(d.users) + '</div>' +
      '<div class="s">+' + bfNum(d.users_7d) + ' in 7 Tagen</div></div>' +
      '<div class="bfCard"><div class="k">AKTIVE ABOS</div><div class="v">' + bfNum(d.subs) + '</div>' +
      '<div class="s">zahlende Kunden</div></div>' +
      '<div class="bfCard"><div class="k">AKTIVE NUTZER 7T</div><div class="v">' + bfNum(d.active_users_7d) + '</div>' +
      '<div class="s">mit mind. 1 Generierung</div></div>' +
      '</div>';

    // Nutzung
    html += '<div class="bfSection">NUTZUNG &amp; KI</div><div class="bfWide">';
    var pt = d.per_tool || [];
    var maxT = Math.max.apply(null, pt.map(function(x) { return x.n; }).concat([1]));
    html += '<div class="bfPanel"><div class="t">GENERIERUNGEN PRO TOOL</div>';
    html += pt.length ? pt.map(function(x, i) {
      return '<div class="bfBar"><span class="n">' + esc(x.tool) + '</span>' +
        '<span class="track"><span class="fill" style="width:' + Math.round(x.n / maxT * 100) + '%;background:' +
        BF_COLORS[i % BF_COLORS.length] + '"></span></span><span class="val">' + x.n + '</span></div>';
    }).join('') : '<div class="empty">Noch keine Daten.</div>';
    html += '</div>';

    html += '<div class="bfPanel"><div class="t">KI-ERFOLGSQUOTE</div><div class="bfRing">' +
      '<svg width="112" height="112" viewBox="0 0 112 112">' +
      '<circle cx="56" cy="56" r="46" fill="none" stroke="rgba(255,255,255,.07)" stroke-width="11"/>' +
      '<circle cx="56" cy="56" r="46" fill="none" stroke="#5DCAA5" stroke-width="11" stroke-linecap="round" ' +
      'stroke-dasharray="' + (quote / 100 * 289).toFixed(1) + ' 289" transform="rotate(-90 56 56)"/></svg>' +
      '<div class="txt"><div class="pct">' + quote + ' %</div><div class="cap">' + bfNum(ok) + ' OK \u00b7 ' +
      bfNum(gen - ok) + ' FEHLER</div></div></div></div>';
    html += '</div>';

    // Verlauf + Token
    html += '<div class="bfWide" style="margin-top:12px">';
    var pd = d.per_day || [];
    var maxD = Math.max.apply(null, pd.map(function(x) { return x.n; }).concat([1]));
    html += '<div class="bfPanel"><div class="t">GENERIERUNGEN PRO TAG (14 TAGE)</div>';
    if (pd.length) {
      html += '<div class="bfSpark">' + pd.map(function(x) {
        return '<span style="height:' + Math.max(2, Math.round(x.n / maxD * 70)) + 'px" title="' + x.d + ': ' + x.n + '"></span>';
      }).join('') + '</div><div class="bfDays"><span>' + esc(pd[0].d) + '</span><span>' +
        esc(pd[pd.length - 1].d) + '</span></div>';
    } else { html += '<div class="empty">Noch keine Daten.</div>'; }
    html += '</div>';

    html += '<div class="bfPanel"><div class="t">TOKEN GESAMT</div>' +
      '<div class="bfBar"><span class="n">Input</span><span class="track"><span class="fill" style="width:100%;background:#59d7ff"></span></span>' +
      '<span class="val" style="width:auto">' + bfNum(d.tokens_in) + '</span></div>' +
      '<div class="bfBar"><span class="n">Output</span><span class="track"><span class="fill" style="width:' +
      Math.round((d.tokens_out || 0) / Math.max(d.tokens_in || 1, 1) * 100) + '%;background:#c792ea"></span></span>' +
      '<span class="val" style="width:auto">' + bfNum(d.tokens_out) + '</span></div>' +
      '<div class="s" style="font-size:9.5px;color:var(--dim);margin-top:12px">Kosten 7 Tage: ' + bfUsd(d.cost_7d) +
      ' \u00b7 gesamt: ' + bfUsd(d.cost_total) + '</div></div>';
    html += '</div>';

    // Funnel + Plaene
    html += '<div class="bfSection">WACHSTUM</div><div class="bfWide">';
    var wl = d.waitlist || 0, us = d.users || 0, sb = d.subs || 0;
    var base = Math.max(wl, us, sb, 1);
    function step(name, val, ref, refName) {
      var pct = ref ? Math.round(val / ref * 1000) / 10 : 0;
      return '<div class="step"><div class="head"><b>' + name + '</b><span>' + bfNum(val) +
        (refName ? ' \u00b7 ' + pct + ' % der ' + refName : '') + '</span></div>' +
        '<div class="bfBar" style="margin:0"><span class="track"><span class="fill" style="width:' +
        Math.round(val / base * 100) + '%;background:#5DCAA5"></span></span></div></div>';
    }
    html += '<div class="bfPanel bfFunnel"><div class="t">CONVERSION-FUNNEL</div>' +
      step('Warteliste', wl, 0, '') + step('Registriert', us, wl, 'Warteliste') +
      step('Zahlend', sb, us, 'Registrierten') + '</div>';

    var pp = d.per_plan || [];
    html += '<div class="bfPanel"><div class="t">AKTIVE ABOS NACH PLAN</div>';
    html += pp.length ? pp.map(function(x, i) {
      return '<div class="bfBar"><span class="n">' + esc(x.plan) + '</span>' +
        '<span class="track"><span class="fill" style="width:' + Math.round(x.n / Math.max(sb, 1) * 100) +
        '%;background:' + BF_COLORS[i % BF_COLORS.length] + '"></span></span><span class="val">' + x.n + '</span></div>';
    }).join('') : '<div class="empty">Noch keine aktiven Abos.</div>';
    html += '</div></div>';

    html += '<div class="bfSection">BESUCHER (UMAMI)</div><div id="bfUmami">' +
      '<div class="bfPanel"><div class="empty">Lade Besucherdaten...</div></div></div>';

    html += '<div style="font-size:9px;color:var(--dim);margin-top:18px;line-height:1.7">' +
      'Direkt aus Supabase \u00b7 Stand ' + new Date().toLocaleString('de-DE') +
      ' \u00b7 Tabellen: ' + esc((d.tables || []).join(', ') || '-') + '</div>';

    box.innerHTML = html;
    loadUmami();
  } catch (e) {
    box.innerHTML = '<div class="bfErr"><b>Fehler beim Laden.</b><br>' + esc(String(e)) + '</div>';
  }
}

/* ── Gehirn-View (Memory-Graph, Obsidian-Style) ── */
var brainCanvas = document.getElementById('brain');
var bctx = brainCanvas.getContext('2d');
var currentView = 0;
var brainNodes = [], brainEdges = [], brainHubs = {}, brainFolders = [], brainLoaded = false, brainAnim = null;
var PALETTE = ['#59d7ff', '#5DCAA5', '#c792ea', '#ffd479', '#ff8fa3', '#7ee0d0', '#9fb5ff', '#f4a988'];
var brainHover = null, brainSelected = null;
var brainCore = { x: 0, y: 0, color: '#59d7ff' };
var brainNodesById = {};
var brainFolderStore = {};
var brainPollTimer = null;
var brainGrowToast = { text: '', until: 0 };
var bview = { x: 0, y: 0, zoom: 1 };
var brainAlpha = 0;
var stars = [];
var pulses = [];
var lastPulse = 0;

function resizeBrain() {
  brainCanvas.width = window.innerWidth;
  brainCanvas.height = window.innerHeight;
  stars = [];
  for (var i = 0; i < 160; i++) {
    stars.push({ x: Math.random() * brainCanvas.width, y: Math.random() * brainCanvas.height,
                 r: Math.random() * 1.1 + 0.2, a: 0.04 + Math.random() * 0.10,
                 tw: Math.random() * 6.28 });
  }
}
window.addEventListener('resize', resizeBrain);
resizeBrain();

var STOP = new Set(['jarvis','buroflow','privat','sonstiges','einer','eines','nicht','wurde','haben','sowie','ueber','aktuell','status']);

function tokenize(n) {
  return (n.title + ' ' + (n.content || '').substring(0, 80)).toLowerCase()
    .replace(/[^a-zäöüß0-9 ]/g, ' ').split(/\\s+/).filter(function(w) { return w.length > 4 && !STOP.has(w); });
}

function stem(w) { return w.replace(/(ungen|ung|en|er|n|s)$/, ''); }

function buildStructure() {
  // ORDNER-BILDUNG pro Projekt (persistente Objekte -> stabile Positionen ueber Reloads):
  // 1) Titel-Praefix "Xyz: ..." wird direkt zum Ordner
  // 2) danach: gemeinsame Wortstaemme (>=2 Titel)
  // 3) Rest -> Ordner "ALLGEMEIN"
  var seenFolderKeys = {};
  var allFolders = [];
  var byProject = {};
  brainNodes.forEach(function(n, i) { (byProject[n.project] = byProject[n.project] || []).push(i); });

  Object.keys(byProject).forEach(function(p) {
    var idx = byProject[p];
    var assigned = new Set();
    var localFolders = [];

    function addFolder(label, members) {
      if (!members.length) return;
      var lbl = label.toUpperCase().substring(0, 14);
      var key = p + '/' + lbl;
      seenFolderKeys[key] = true;
      var f = brainFolderStore[key];
      if (!f) { f = {}; brainFolderStore[key] = f; }
      f.project = p; f.label = lbl; f.members = members;
      localFolders.push(f);
      members.forEach(function(i) { assigned.add(i); });
    }

    // 1) Praefix-Ordner
    var prefixGroups = {};
    idx.forEach(function(i) {
      var m = brainNodes[i].title.match(/^([A-Za-zÄÖÜäöüß\\-]{4,16}):/);
      if (m) (prefixGroups[m[1].toLowerCase()] = prefixGroups[m[1].toLowerCase()] || []).push(i);
    });
    Object.keys(prefixGroups).forEach(function(pref) {
      var mem = prefixGroups[pref];
      // Praefix zieht auch Titel-Treffer per Stamm an
      var ps = stem(pref);
      idx.forEach(function(i) {
        if (assigned.has(i) || mem.indexOf(i) >= 0) return;
        var hit = tokenize(brainNodes[i]).some(function(w) { return w.indexOf(ps) >= 0 || ps.indexOf(stem(w)) >= 0; });
        if (hit) mem.push(i);
      });
      addFolder(pref, mem.filter(function(i) { return !assigned.has(i); }));
    });

    // 2) Stamm-Gruppen
    var freq = {};
    idx.forEach(function(i) {
      if (assigned.has(i)) return;
      var seen = new Set();
      tokenize(brainNodes[i]).forEach(function(w) {
        var s = stem(w);
        if (s.length < 5 || s === p || seen.has(s)) return;
        seen.add(s);
        (freq[s] = freq[s] || { word: w, members: [] }).members.push(i);
      });
    });
    Object.keys(freq)
      .sort(function(a, b) { return freq[b].members.length - freq[a].members.length; })
      .forEach(function(s) {
        var free = freq[s].members.filter(function(i) { return !assigned.has(i); });
        if (free.length >= 2) addFolder(freq[s].word, free);
      });

    // 3) Rest
    addFolder('allgemein', idx.filter(function(i) { return !assigned.has(i); }));

    localFolders.forEach(function(f) {
      var fi = allFolders.length;
      allFolders.push(f);
      f.members.forEach(function(i) { brainNodes[i].folder = fi; });
    });
  });

  Object.keys(brainFolderStore).forEach(function(k) { if (!seenFolderKeys[k]) delete brainFolderStore[k]; });
  brainFolders = allFolders;

  // Wenige semantische Querlinks (projektuebergreifend)
  brainEdges = [];
  var toks = brainNodes.map(function(n) { return new Set(tokenize(n)); });
  var cross = brainNodes.map(function() { return 0; });
  for (var i = 0; i < brainNodes.length; i++) {
    for (var j = i + 1; j < brainNodes.length; j++) {
      if (brainNodes[i].project === brainNodes[j].project) continue;
      if (cross[i] > 0 || cross[j] > 0) continue;
      var shared = 0;
      toks[i].forEach(function(w) { if (toks[j].has(w)) shared++; });
      if (shared >= 2) { brainEdges.push({ a: i, b: j }); cross[i]++; cross[j]++; }
    }
  }
}

function layoutBrain() {
  var W2 = brainCanvas.width, H2 = brainCanvas.height;
  brainCore.x = W2 / 2; brainCore.y = H2 / 2;
  var base = Math.min(W2, H2);
  var R1 = base * 0.20, R2 = base * 0.335, R3 = base * 0.435, ROW = base * 0.062;

  var projects = [];
  brainNodes.forEach(function(n) { if (projects.indexOf(n.project) < 0 && n.project !== 'jarvis') projects.push(n.project); });
  projects.sort();
  var hasJarvis = brainNodes.some(function(n) { return n.project === 'jarvis'; });
  var all = hasJarvis ? projects.concat(['jarvis']) : projects;
  var sectorW = 6.283 / Math.max(all.length, 1);

  var seenHubs = {};
  all.forEach(function(p, i) {
    var ang = i * sectorW - 1.5708;
    var h = brainHubs[p];
    if (!h) { h = { x: brainCore.x, y: brainCore.y }; brainHubs[p] = h; }
    h.tx = brainCore.x + Math.cos(ang) * R1;
    h.ty = brainCore.y + Math.sin(ang) * R1;
    h.ang = ang;
    h.color = (p === 'jarvis') ? '#59d7ff' : PALETTE[(i + 1) % PALETTE.length];
    h.label = p;
    seenHubs[p] = true;
  });
  Object.keys(brainHubs).forEach(function(k) { if (!seenHubs[k]) delete brainHubs[k]; });

  // Ordner: Faecher im Sektor ihres Projekts (persistente Positionen -> weiches Nachruecken)
  var foldersByP = {};
  brainFolders.forEach(function(f, fi) { (foldersByP[f.project] = foldersByP[f.project] || []).push(fi); });
  Object.keys(foldersByP).forEach(function(p) {
    var hub = brainHubs[p];
    var fis = foldersByP[p];
    var spread = sectorW * 0.72;
    fis.forEach(function(fi, k) {
      var off = fis.length > 1 ? (k / (fis.length - 1) - 0.5) * spread : 0;
      var ang = hub.ang + off;
      var f = brainFolders[fi];
      if (f.x === undefined) { f.x = hub.x; f.y = hub.y; }
      f.tx = brainCore.x + Math.cos(ang) * R2;
      f.ty = brainCore.y + Math.sin(ang) * R2;
      f.ang = ang;
      f.color = hub.color;
      // Erinnerungen: Faecher um den Ordner, ggf. zweite Reihe
      var perRow = 5;
      f.members.forEach(function(ni, m) {
        var row = Math.floor(m / perRow);
        var inRow = f.members.length - row * perRow > perRow ? perRow : f.members.length - row * perRow;
        var pos = m % perRow;
        var nSpread = Math.min(0.16 * inRow, sectorW * 0.62);
        var nOff = inRow > 1 ? (pos / (inRow - 1) - 0.5) * nSpread : 0;
        var na = ang + nOff;
        var nr = R3 + row * ROW;
        var node = brainNodes[ni];
        if (node.x === undefined) { node.x = f.x; node.y = f.y; }
        node.tx = brainCore.x + Math.cos(na) * nr;
        node.ty = brainCore.y + Math.sin(na) * nr;
      });
    });
  });
}

async function loadBrain(isPoll) {
  try {
    var d = await (await fetch('/api/memory')).json();
    var incoming = d.nodes || [];
    var newCount = 0;
    var nextById = {};
    brainNodes = incoming.map(function(n) {
      var node = brainNodesById[n.id];
      if (!node) {
        node = { id: n.id, r: 3.5 + Math.min((n.content || '').length / 120, 3.5), ph: Math.random() * 6.28 };
        if (isPoll) { node.bornAt = Date.now(); newCount++; }
      }
      node.title = n.title; node.content = n.content; node.project = n.project;
      node.source = n.source; node.created = n.created;
      nextById[n.id] = node;
      return node;
    });
    brainNodesById = nextById;

    buildStructure();
    layoutBrain();

    if (isPoll && newCount > 0) {
      brainGrowToast = { text: '+' + newCount + ' neue Erinnerung' + (newCount > 1 ? 'en' : ''), until: Date.now() + 4500 };
    }

    var lg = Object.keys(brainHubs).filter(function(p) { return p !== 'jarvis'; }).map(function(p) {
      return '<span><i style="background:' + brainHubs[p].color + '"></i>' + esc(p) + '</span>';
    }).join('');
    document.getElementById('brainlegend').innerHTML =
      lg + '<span>' + brainNodes.length + ' Erinnerungen | ' + brainFolders.length + ' Ordner</span>';
    brainLoaded = true;
  } catch (e) {}
}

function drawCurve(x1, y1, x2, y2, style, width, dash) {
  bctx.beginPath();
  if (dash) bctx.setLineDash(dash);
  bctx.moveTo(x1, y1);
  var mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
  var cx2 = mx + (brainCore.x - mx) * -0.12, cy2 = my + (brainCore.y - my) * -0.12;
  bctx.quadraticCurveTo(cx2, cy2, x2, y2);
  bctx.strokeStyle = style;
  bctx.lineWidth = width;
  bctx.stroke();
  bctx.setLineDash([]);
}

var labelBoxes = [];
function drawLabel(text, x, y, opts) {
  opts = opts || {};
  bctx.font = (opts.bold ? 'bold ' : '') + (opts.size || 9.5) + 'px Consolas, monospace';
  bctx.textAlign = 'center';
  var w = bctx.measureText(text).width + 10;
  var h = (opts.size || 9.5) + 5;
  var candidates = [y, opts.alt || (y - 22), y + 15, (opts.alt || (y - 22)) - 15];
  var fy = candidates[0];
  for (var c = 0; c < candidates.length; c++) {
    var box = { x: x - w / 2, y: candidates[c] - h + 3, w: w, h: h };
    var hit = labelBoxes.some(function(b) {
      return box.x < b.x + b.w && box.x + box.w > b.x && box.y < b.y + b.h && box.y + box.h > b.y;
    });
    if (!hit) { fy = candidates[c]; break; }
  }
  labelBoxes.push({ x: x - w / 2, y: fy - h + 3, w: w, h: h });
  bctx.fillStyle = 'rgba(4, 11, 18, .8)';
  bctx.fillRect(x - w / 2, fy - h + 3, w, h);
  bctx.fillStyle = opts.color || 'rgba(205, 231, 247, .82)';
  bctx.fillText(text, x, fy);
}

var EASE_K = 0.09;
function easeAll() {
  brainNodes.forEach(function(n) { n.x += (n.tx - n.x) * EASE_K; n.y += (n.ty - n.y) * EASE_K; });
  brainFolders.forEach(function(f) { f.x += (f.tx - f.x) * EASE_K; f.y += (f.ty - f.y) * EASE_K; });
  Object.keys(brainHubs).forEach(function(k) {
    var h = brainHubs[k]; h.x += (h.tx - h.x) * EASE_K; h.y += (h.ty - h.y) * EASE_K;
  });
}

function drawBrain() {
  if (currentView === 0) { brainAnim = null; return; }
  var t = Date.now() / 1000;
  bctx.clearRect(0, 0, brainCanvas.width, brainCanvas.height);
  labelBoxes = [];

  stars.forEach(function(s) {
    bctx.beginPath();
    bctx.arc(s.x, s.y, s.r, 0, 6.283);
    bctx.fillStyle = 'rgba(140, 210, 255,' + (s.a * (0.6 + 0.4 * Math.sin(t * 1.3 + s.tw))) + ')';
    bctx.fill();
  });

  if (currentView === 2) {   // Agenten-Tab: nur Sternenfeld als Hintergrund
    brainAnim = requestAnimationFrame(drawBrain);
    return;
  }

  if (!brainNodes.length) {
    bctx.font = '11px Consolas, monospace';
    bctx.textAlign = 'center';
    bctx.fillStyle = 'rgba(120, 170, 200, .6)';
    bctx.fillText('LADE GEDÄCHTNIS …', brainCanvas.width / 2, brainCanvas.height / 2);
    brainAnim = requestAnimationFrame(drawBrain);
    return;
  }

  bctx.save();
  bctx.translate(bview.x, bview.y);
  bctx.scale(bview.zoom, bview.zoom);
  easeAll();

  // 1) Kanten (hinten): Kern->Hub, Hub->Ordner, Ordner->Erinnerung, Querlinks
  Object.keys(brainHubs).forEach(function(p) {
    var h = brainHubs[p];
    var g = bctx.createLinearGradient(brainCore.x, brainCore.y, h.x, h.y);
    g.addColorStop(0, 'rgba(89, 215, 255, .30)');
    g.addColorStop(1, h.color + '55');
    drawCurve(brainCore.x, brainCore.y, h.x, h.y, g, 1.6);
  });
  brainFolders.forEach(function(f) {
    var hub = brainHubs[f.project];
    drawCurve(hub.x, hub.y, f.x, f.y, f.color + '40', 1.1);
    f.members.forEach(function(ni) {
      var n = brainNodes[ni];
      drawCurve(f.x, f.y, n.x, n.y, f.color + '2a', 0.8);
    });
  });
  brainEdges.forEach(function(e) {
    var a = brainNodes[e.a], b = brainNodes[e.b];
    drawCurve(a.x, a.y, b.x, b.y, 'rgba(160, 200, 230, .12)', 0.7, [3, 4]);
  });

  // Synapsen-Pulse auf Ordner-Kanten
  if (brainFolders.length && Date.now() - lastPulse > 380) {
    var rf = brainFolders[Math.floor(Math.random() * brainFolders.length)];
    if (rf.members.length) {
      pulses.push({ fx: rf.x, fy: rf.y, n: brainNodes[rf.members[Math.floor(Math.random() * rf.members.length)]],
                    col: rf.color, t: 0 });
    }
    lastPulse = Date.now();
  }
  for (var pi = pulses.length - 1; pi >= 0; pi--) {
    var pu = pulses[pi];
    pu.t += 0.02;
    if (pu.t >= 1) { pulses.splice(pi, 1); continue; }
    var px2 = pu.fx + (pu.n.x - pu.fx) * pu.t;
    var py2 = pu.fy + (pu.n.y - pu.fy) * pu.t;
    bctx.beginPath();
    bctx.arc(px2, py2, 1.9, 0, 6.283);
    bctx.shadowColor = pu.col; bctx.shadowBlur = 8;
    bctx.fillStyle = pu.col;
    bctx.fill();
    bctx.shadowBlur = 0;
  }

  // 2) Punkte: Erinnerungen -> Ordner -> Hubs -> Kern
  brainNodes.forEach(function(n) {
    var col = brainFolders[n.folder] ? brainFolders[n.folder].color : '#59d7ff';
    var hot = (n === brainHover || n === brainSelected);
    var isNew = n.bornAt && (Date.now() - n.bornAt < 4500);
    if (n.bornAt && !isNew) n.bornAt = 0;
    var rr = n.r + (hot ? 2.5 : 0) + (isNew ? 1.5 : 0);
    bctx.beginPath();
    bctx.arc(n.x, n.y, rr, 0, 6.283);
    bctx.fillStyle = hot ? col : col + 'c8';
    if (hot || isNew) { bctx.shadowColor = col; bctx.shadowBlur = isNew ? 20 : 16; }
    bctx.fill();
    bctx.shadowBlur = 0;
    if (isNew) {
      bctx.beginPath();
      bctx.arc(n.x, n.y, rr + 5 + 3 * Math.sin(Date.now() / 150), 0, 6.283);
      bctx.strokeStyle = col + '90';
      bctx.lineWidth = 1.2;
      bctx.stroke();
    }
  });
  brainFolders.forEach(function(f) {
    bctx.beginPath();
    bctx.arc(f.x, f.y, 8, 0, 6.283);
    bctx.strokeStyle = f.color + 'aa';
    bctx.lineWidth = 1.6;
    bctx.stroke();
    bctx.beginPath();
    bctx.arc(f.x, f.y, 3.2, 0, 6.283);
    bctx.fillStyle = f.color;
    bctx.fill();
  });
  Object.keys(brainHubs).forEach(function(p) {
    var h = brainHubs[p];
    var halo = bctx.createRadialGradient(h.x, h.y, 0, h.x, h.y, 30);
    halo.addColorStop(0, h.color + '30');
    halo.addColorStop(1, h.color + '00');
    bctx.fillStyle = halo;
    bctx.fillRect(h.x - 30, h.y - 30, 60, 60);
    bctx.beginPath();
    bctx.arc(h.x, h.y, 7, 0, 6.283);
    bctx.fillStyle = h.color;
    bctx.shadowColor = h.color; bctx.shadowBlur = 12;
    bctx.fill();
    bctx.shadowBlur = 0;
  });
  var corePulse = 1 + 0.08 * Math.sin(t * 2.1);
  var chalo = bctx.createRadialGradient(brainCore.x, brainCore.y, 0, brainCore.x, brainCore.y, 60 * corePulse);
  chalo.addColorStop(0, 'rgba(89, 215, 255, .25)');
  chalo.addColorStop(1, 'rgba(89, 215, 255, 0)');
  bctx.fillStyle = chalo;
  bctx.fillRect(brainCore.x - 60, brainCore.y - 60, 120, 120);
  bctx.beginPath();
  bctx.arc(brainCore.x, brainCore.y, 10 * corePulse, 0, 6.283);
  bctx.fillStyle = '#bfeeff';
  bctx.shadowColor = '#59d7ff'; bctx.shadowBlur = 22;
  bctx.fill();
  bctx.shadowBlur = 0;

  // 3) Labels zuletzt, nach Prioritaet: Kern -> Hubs -> Ordner -> Erinnerungen
  drawLabel('J A R V I S', brainCore.x, brainCore.y - 22, { size: 11, bold: true, color: 'rgba(234,249,255,.96)', alt: brainCore.y + 30 });
  Object.keys(brainHubs).forEach(function(p) {
    if (p === 'jarvis') return;
    var h = brainHubs[p];
    drawLabel(p.toUpperCase(), h.x, h.y - 15, { size: 10.5, bold: true, color: 'rgba(224,246,255,.95)', alt: h.y + 22 });
  });
  brainFolders.forEach(function(f) {
    drawLabel('\u25C8 ' + f.label, f.x, f.y - 14, { size: 9.5, color: 'rgba(226,244,255,.9)', alt: f.y + 22 });
  });
  if (bview.zoom > 0.5) {
    brainNodes.forEach(function(n) {
      var label = n.title.length > 24 ? n.title.substring(0, 23) + '\u2026' : n.title;
      var hot = (n === brainHover || n === brainSelected);
      drawLabel(label, n.x, n.y + n.r + 13, {
        size: hot ? 10.5 : 9,
        color: hot ? 'rgba(234,249,255,.98)' : 'rgba(195,222,240,.72)',
        alt: n.y - n.r - 6,
      });
    });
  }

  bctx.restore();

  if (brainGrowToast.text && Date.now() < brainGrowToast.until) {
    var remain = brainGrowToast.until - Date.now();
    var alpha = Math.min(1, remain / 500);
    bctx.font = '11px Consolas, monospace';
    bctx.textAlign = 'center';
    var ttxt = brainGrowToast.text;
    var tw3 = bctx.measureText(ttxt).width;
    var tcx = brainCanvas.width / 2, tcy = 94;
    bctx.fillStyle = 'rgba(93, 202, 165,' + (0.16 * alpha) + ')';
    bctx.fillRect(tcx - tw3 / 2 - 14, tcy - 15, tw3 + 28, 23);
    bctx.strokeStyle = 'rgba(93, 202, 165,' + (0.55 * alpha) + ')';
    bctx.lineWidth = 1;
    bctx.strokeRect(tcx - tw3 / 2 - 14, tcy - 15, tw3 + 28, 23);
    bctx.fillStyle = 'rgba(200, 250, 225,' + alpha + ')';
    bctx.fillText(ttxt, tcx, tcy);
  }

  brainAnim = requestAnimationFrame(drawBrain);
}

function brainHit(mx, my) {
  var x = (mx - bview.x) / bview.zoom, y = (my - bview.y) / bview.zoom;
  for (var i = 0; i < brainNodes.length; i++) {
    var n = brainNodes[i];
    var dx = n.x - x, dy = n.y - y;
    if (dx * dx + dy * dy < (n.r + 6) * (n.r + 6)) return n;
  }
  return null;
}
var dragging = false, dragMoved = false, dragSX = 0, dragSY = 0;
brainCanvas.addEventListener('mousedown', function(ev) {
  dragging = true; dragMoved = false; dragSX = ev.clientX - bview.x; dragSY = ev.clientY - bview.y;
});
window.addEventListener('mouseup', function() { dragging = false; });
brainCanvas.addEventListener('mousemove', function(ev) {
  if (dragging) {
    bview.x = ev.clientX - dragSX; bview.y = ev.clientY - dragSY;
    dragMoved = true;
    return;
  }
  brainHover = brainHit(ev.clientX, ev.clientY);
  brainCanvas.style.cursor = brainHover ? 'pointer' : 'grab';
});
brainCanvas.addEventListener('click', function(ev) {
  if (dragMoved) return;
  var n = brainHit(ev.clientX, ev.clientY);
  brainSelected = n;
  var panel = document.getElementById('braindetail');
  if (n) {
    document.getElementById('bdbody').innerHTML =
      '<div class="bt">' + esc(n.title) + '</div>' +
      '<div class="bm">' + esc(n.project.toUpperCase()) + ' | ' + esc(n.source) + ' | ' + esc(n.created) + '</div>' +
      '<div>' + esc(n.content) + '</div>';
    panel.style.display = 'block';
  } else { panel.style.display = 'none'; }
});
brainCanvas.addEventListener('wheel', function(ev) {
  ev.preventDefault();
  var z = ev.deltaY < 0 ? 1.1 : 0.9;
  bview.zoom = Math.max(0.4, Math.min(2.5, bview.zoom * z));
}, { passive: false });
document.getElementById('bdclose').addEventListener('click', function() {
  brainSelected = null;
  document.getElementById('braindetail').style.display = 'none';
});

var VIEW_ORDER = [0, 2, 3, 1];
function setView(v) {
  currentView = v;
  document.querySelectorAll('.vt').forEach(function(t) {
    t.classList.toggle('active', parseInt(t.getAttribute('data-view')) === v);
  });
  var brainMode = (v === 1);
  var agentMode = (v === 2);
  var bfMode = (v === 3);
  var overlay = (brainMode || agentMode || bfMode);
  brainCanvas.style.display = (brainMode || agentMode) ? 'block' : 'none';
  canvas.style.display = overlay ? 'none' : 'block';
  document.querySelector('.col-left').style.display = overlay ? 'none' : 'flex';
  document.querySelector('.chat').style.display = overlay ? 'none' : 'flex';
  document.getElementById('vtab').style.display = overlay ? 'none' : 'block';
  document.getElementById('bfView').style.display = bfMode ? 'block' : 'none';
  document.getElementById('agentsView').style.display = agentMode ? 'block' : 'none';
  if (agentMode) { document.getElementById('agChart').innerHTML = ''; agLastHash = ''; renderAgents(lastBots); }
  document.getElementById('brainlegend').style.display = brainMode ? 'flex' : 'none';
  if (!brainMode) document.getElementById('braindetail').style.display = 'none';
  if (bfMode) {
    loadBuroflow();
    if (bfTimer) clearInterval(bfTimer);
    bfTimer = setInterval(loadBuroflow, 60000);
  } else if (bfTimer) {
    clearInterval(bfTimer);
    bfTimer = null;
  }
  if (brainMode || agentMode) {
    if (brainMode) loadBrain(false);
    if (brainAnim) cancelAnimationFrame(brainAnim);
    brainAnim = null;
    drawBrain();
  }
  if (brainMode) {
    if (brainPollTimer) clearInterval(brainPollTimer);
    brainPollTimer = setInterval(function() { loadBrain(true); }, 20000);
  } else if (brainPollTimer) {
    clearInterval(brainPollTimer);
    brainPollTimer = null;
  }
}
document.querySelectorAll('.vt').forEach(function(t) {
  t.addEventListener('click', function() { setView(parseInt(t.getAttribute('data-view'))); });
});
document.addEventListener('keydown', function(ev) {
  if (ev.key !== 'ArrowRight' && ev.key !== 'ArrowLeft') return;
  var i = VIEW_ORDER.indexOf(currentView);
  var ni = ev.key === 'ArrowRight' ? Math.min(i + 1, VIEW_ORDER.length - 1) : Math.max(i - 1, 0);
  setView(VIEW_ORDER[ni]);
});

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

/* ── Stats + Agenten-Ansicht ── */
var AG_PALETTE = ['#59d7ff', '#5DCAA5', '#c792ea', '#ffd479', '#ff8fa3', '#7ee0d0', '#9fb5ff', '#f4a988'];
var lastLog = [];
var lastBots = [];

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

    document.getElementById('log').innerHTML = (s.log || []).map(function(e) {
      return '<div>' + e.t + ' <b>' + esc(e.bot) + '</b> ' + fmt(e.cost) + '</div>';
    }).join('') || '<div class="empty">-</div>';
    lastLog = s.log || [];
    lastBots = s.bots || [];

    renderAgents(s.bots);
  } catch (e) {}
}

var agView = { x: 0, y: 0, zoom: 1 };
function agApplyView() {
  document.getElementById('agChart').style.transform =
    'translate(' + agView.x + 'px,' + agView.y + 'px) scale(' + agView.zoom + ')';
}
function agZoomAt(mx, my, factor) {
  var nz = Math.max(0.4, Math.min(2.5, agView.zoom * factor));
  var k = nz / agView.zoom;
  agView.x = mx - (mx - agView.x) * k;
  agView.y = my - (my - agView.y) * k;
  agView.zoom = nz;
  agApplyView();
}
var agPan = null;

var agCustomPos = {};
try { agCustomPos = JSON.parse(localStorage.getItem('jarvis_agpos') || '{}'); } catch (e) {}
var agMeta = null;
var agDrag = null;
var agDragMoved = false;

function buildAgSvg(pos) {
  var defs = '<defs>';
  var paths = '';
  agMeta.bots.forEach(function(b, bi) {
    if (!b.parent || !pos[b.parent] || !pos[b.id]) return;
    var a = pos[b.parent], c = pos[b.id];
    var colP = agMeta.colorOf[b.parent] || '#59d7ff';
    var col = agMeta.colorOf[b.id] || '#59d7ff';
    var x1 = a.x + agMeta.CW / 2, y1 = a.y + agMeta.CH - 4;
    var x2 = c.x + agMeta.CW / 2, y2 = c.y + 6;
    var gid = 'agg' + bi;
    defs += '<linearGradient id="' + gid + '" x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 +
            '" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="' + colP + '"/><stop offset="1" stop-color="' + col + '"/></linearGradient>';
    var path = 'M ' + x1 + ' ' + y1 + ' C ' + x1 + ' ' + (y1 + 38) + ', ' + x2 + ' ' + (y2 - 38) + ', ' + x2 + ' ' + y2;
    paths += '<path d="' + path + '" fill="none" stroke="url(#' + gid + ')" stroke-width="5" stroke-opacity=".07"/>';
    paths += '<path d="' + path + '" fill="none" stroke="url(#' + gid + ')" stroke-width="1.2" stroke-opacity=".55"/>';
    paths += '<circle r="2.2" fill="' + col + '"><animateMotion dur="3.2s" repeatCount="indefinite" path="' + path + '"/></circle>';
    paths += '<circle r="1.5" fill="' + colP + '" opacity=".7"><animateMotion dur="3.2s" begin="1.6s" repeatCount="indefinite" path="' + path + '"/></circle>';
  });
  return '<svg class="agSvg" width="' + agMeta.W + '" height="' + agMeta.totalH + '" viewBox="0 0 ' + agMeta.W + ' ' + agMeta.totalH + '">' + defs + '</defs>' + paths + '</svg>';
}

function agDomPositions() {
  var pos = {};
  document.querySelectorAll('#agChart .agNode').forEach(function(n) {
    pos[n.getAttribute('data-bot')] = { x: parseFloat(n.style.left) || 0, y: parseFloat(n.style.top) || 0 };
  });
  return pos;
}

function agUpdateSvgLive() {
  if (!agMeta) return;
  var chart = document.getElementById('agChart');
  var old = chart.querySelector('.agSvg');
  var pos = agDomPositions();
  var maxY = 0;
  Object.keys(pos).forEach(function(id) { maxY = Math.max(maxY, pos[id].y); });
  agMeta.totalH = Math.max(agMeta.totalH, maxY + agMeta.CH + 10);
  chart.style.height = agMeta.totalH + 'px';
  var tmp = document.createElement('div');
  tmp.innerHTML = buildAgSvg(pos);
  if (old) old.replaceWith(tmp.firstChild);
}

var agLastHash = '';
function renderAgents(bots) {
  var chart = document.getElementById('agChart');
  var W = chart.clientWidth;
  if (!W) return;

  var busyIds = [];
  document.querySelectorAll('.agNode.busy').forEach(function(n) { busyIds.push(n.getAttribute('data-bot')); });
  var hash = W + '|' + busyIds.join(',') + '|' + JSON.stringify(bots.map(function(b) {
    return [b.id, b.parent, b.online, b.cost, b.requests, b.spark];
  }));
  var firstRender = chart.innerHTML === '';
  if (hash === agLastHash && !firstRender) return;
  agLastHash = hash;

  var byId = {};
  bots.forEach(function(b) { byId[b.id] = b; });
  var children = {};
  bots.forEach(function(b) {
    var p = (b.parent && byId[b.parent]) ? b.parent : 'root';
    (children[p] = children[p] || []).push(b);
  });
  var levels = [];
  var colorOf = {};
  var depthOf = {};
  function walk(list, depth, branchColor) {
    if (!list || !list.length) return;
    levels[depth] = (levels[depth] || []).concat(list);
    list.forEach(function(b, i) {
      var col = depth === 0 ? AG_PALETTE[i % AG_PALETTE.length] : branchColor;
      colorOf[b.id] = col;
      depthOf[b.id] = depth;
      walk(children[b.id], depth + 1, col);
    });
  }
  walk(children['root'], 0, '#59d7ff');

  var CW = 216, CH = 168, GAPX = 26, GAPY = 78;
  var pos = {};
  levels.forEach(function(lv, d) {
    var n = lv.length;
    var rowW = n * CW + (n - 1) * GAPX;
    var startX = Math.max(0, (W - rowW) / 2);
    lv.forEach(function(b, i) {
      pos[b.id] = { x: startX + i * (CW + GAPX), y: d * (CH + GAPY), w: CW };
    });
  });
  Object.keys(agCustomPos).forEach(function(id) {
    if (pos[id]) { pos[id].x = agCustomPos[id].x; pos[id].y = agCustomPos[id].y; }
  });
  var maxY = 0;
  Object.keys(pos).forEach(function(id) { maxY = Math.max(maxY, pos[id].y); });
  var totalH = Math.max(levels.length * (CH + GAPY) - GAPY, maxY + CH) + 10;
  agMeta = { bots: bots, colorOf: colorOf, CW: CW, CH: CH, W: W, totalH: totalH };

  var svg = buildAgSvg(pos);

  var html = svg;
  bots.forEach(function(b) {
    var p = pos[b.id];
    if (!p) return;
    var col = colorOf[b.id] || '#59d7ff';
    var isRoot = !b.parent;
    var depth = depthOf[b.id] || 0;
    var isBusy = busyIds.indexOf(b.id) >= 0;
    var maxSpark = Math.max.apply(null, (b.spark || [0]).concat([0.0001]));
    var bars = (b.spark || [0, 0, 0, 0, 0, 0]).map(function(v) {
      var h = Math.max(2, Math.round((v / maxSpark) * 15));
      return '<span style="height:' + h + 'px;background:' + col + (v > 0 ? '88' : '26') + '"></span>';
    }).join('');
    var mono = esc(b.label.substring(0, 2).toUpperCase());
    var enterDelay = firstRender ? (' style-delay') : '';
    html += '<div class="agNode' + (isBusy ? ' busy' : '') + (isRoot ? ' agCoreNode' : '') + (firstRender ? ' enter' : '') +
      '" data-bot="' + esc(b.id) + '" style="' +
      'left:' + p.x + 'px; top:' + p.y + 'px; width:' + p.w + 'px; min-height:' + CH + 'px; ' +
      (firstRender ? 'animation-delay:' + (depth * 130) + 'ms; ' : '') +
      'background:linear-gradient(160deg, ' + col + (isRoot ? '26' : '1c') + ', rgba(9,22,33,.62)); border:0.5px solid ' + col + (b.online ? (isRoot ? '77' : '55') : '22') +
      (isRoot ? '; box-shadow: 0 0 30px rgba(89,215,255,.14), 0 6px 26px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.08)' : '') + '">' +
      '<div class="agLayer">LAYER ' + depth + ' \u00b7 ' + (isRoot ? 'ORCHESTRATOR' : 'AGENT') + '</div>' +
      '<div class="agTop">' +
      (isRoot ? '<div class="agCoreWrap"><div class="agCoreRing"></div></div>' :
        '<div class="agMono" style="background:' + col + '22; color:' + col + '; border:1px solid ' + col + '55">' + mono + '</div>') +
      '<div class="agName">' + esc(b.label) + '</div></div>' +
      '<div class="agDesc">' + esc(b.desc || 'agent') + '</div>' +
      '<div class="agDiv"></div>' +
      '<div class="agRow"><span class="l"><span class="agPing' + (b.online ? ' on' : '') + '" style="background:' +
      (b.online ? col : 'var(--dim)') + '; color:' + col + '"></span>' +
      (isBusy ? 'DENKT ...' : (b.online ? 'ONLINE' : 'STANDBY')) + '</span><span class="cost">' + fmt(b.cost) + '</span></div>' +
      '<div class="agRow"><span>requests</span><span>' + b.requests + '</span></div>' +
      '<div class="agSpark">' + bars + '</div>' +
      '</div>';
  });

  chart.style.height = totalH + 'px';
  chart.innerHTML = html;
}

async function loadJobs() {
  try {
    var d = await (await fetch('/api/jobs')).json();
    var js = d.jobs || [];
    var panel = document.getElementById('jobPanel');
    if (!js.length) { panel.style.display = 'none'; return; }
    panel.style.display = 'block';
    document.getElementById('joblist').innerHTML = js.map(function(j) {
      var pct = j.gesamt ? Math.round(j.schritt / j.gesamt * 100) : 0;
      var kl = j.status === 'fertig' ? ' fertig' : (j.status === 'fehler' ? ' fehler' : '');
      return '<div class="jobitem"><div class="jobtop"><b>' + esc(j.titel) + '</b>' +
        '<span>' + (j.status === 'laeuft' ? j.schritt + '/' + j.gesamt : j.status.toUpperCase()) + '</span></div>' +
        '<div class="jobbar' + kl + '"><i style="width:' + pct + '%"></i></div>' +
        (j.aktuell ? '<div class="jobstep">' + esc(j.aktuell) + '</div>' : '') + '</div>';
    }).join('');
  } catch (e) {}
}
setInterval(loadJobs, 8000); loadJobs();

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

var verlaufLaeuft = false;
async function ladeVerlauf(target) {
  if (verlaufLaeuft) return;
  verlaufLaeuft = true;
  var box = document.getElementById('msgs');
  try {
    var d = await (await fetch('/api/chat/history?target=' + encodeURIComponent(target) + '&n=20')).json();
    box.innerHTML = '';
    var msgs = d.messages || [];
    if (!msgs.length) {
      box.innerHTML = '<div class="empty" style="margin:auto;text-align:center;font-size:10.5px">' +
        'Noch kein Verlauf mit ' + esc(target.toUpperCase()) + '.</div>';
    } else {
      msgs.forEach(function(m) {
        if (m.role === 'user') addMsg('me', '', m.text);
        else addMsg('bot', target.toUpperCase(), m.text);
      });
      var hinweis = document.createElement('div');
      hinweis.className = 'verlaufmark';
      hinweis.textContent = '\u2014 frühere Unterhaltung \u2014';
      box.appendChild(hinweis);
    }
    box.scrollTop = box.scrollHeight;
  } catch (e) {
    box.innerHTML = '<div class="empty" style="margin:auto;font-size:10.5px">Verlauf nicht ladbar.</div>';
  }
  verlaufLaeuft = false;
}

document.getElementById('target').addEventListener('change', function() {
  ladeVerlauf(this.value);
});
ladeVerlauf(document.getElementById('target').value);

input.addEventListener('keydown', async function(ev) {
  if (ev.key !== 'Enter' || busy) return;
  var text = input.value.trim();
  if (!text) return;
  var target = document.getElementById('target').value;
  input.value = '';
  var leer = msgs.querySelector('.empty');
  if (leer) leer.remove();
  addMsg('me', '', text);
  busy = true;
  setEnergy(1);
  document.body.classList.add('thinking');
  var bn = document.querySelector('.agNode[data-bot="' + target + '"]');
  if (bn) { bn.classList.add('busy'); var st = bn.querySelector('.agState'); if (st) st.textContent = 'DENKT ...'; }
  var t0 = Date.now();
  function laufzeit() {
    var s = Math.floor((Date.now() - t0) / 1000);
    return String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
  }
  var ticker = setInterval(function() {
    document.getElementById('typing').textContent =
      target.toUpperCase() + ' ARBEITET ... ' + laufzeit();
  }, 1000);
  document.getElementById('typing').textContent = target.toUpperCase() + ' ARBEITET ... 00:00';

  try {
    var r = await fetch('/api/chat', { method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ target: target, text: text }) });
    var d = await r.json();
    if (d.error) {
      addMsg('bot', 'SYSTEM', 'Fehler: ' + d.error);
    } else {
      // Antwort abholen, bis sie da ist (max. 20 Minuten)
      var antwort = null, fehler = null;
      var grenze = Date.now() + 20 * 60 * 1000;
      while (Date.now() < grenze) {
        var p;
        try {
          p = await (await fetch('/api/chat/poll?target=' + encodeURIComponent(d.target) +
                                 '&id=' + encodeURIComponent(d.id))).json();
        } catch (e) {
          await new Promise(function(res) { setTimeout(res, 3000); });
          continue;
        }
        if (p.status === 'done') { antwort = p.answer; break; }
        if (p.status === 'error') { fehler = p.error; break; }
        await new Promise(function(res) { setTimeout(res, 1200); });
      }
      if (antwort !== null) {
        addMsg('bot', target.toUpperCase(), antwort);
      } else if (fehler) {
        addMsg('bot', 'SYSTEM', 'Fehler: ' + fehler);
      } else {
        addMsg('bot', 'SYSTEM', 'Nach 20 Minuten keine Antwort. Im Server-Log nachsehen: ' +
               'docker compose logs ' + (d.target === 'jarvis' ? 'jarvis-core' : 'jarvis-' + d.target) + ' --tail 30');
      }
    }
  } catch (e) {
    addMsg('bot', 'SYSTEM', 'Fehler: ' + e);
  }
  clearInterval(ticker);
  if (/^(reset|vergiss alles|speicher leeren)$/i.test(text)) {
    setTimeout(function() { ladeVerlauf(target); }, 400);
  }
  busy = false;
  setEnergy(0);
  document.body.classList.remove('thinking');
  document.querySelectorAll('.agNode.busy').forEach(function(n) {
    n.classList.remove('busy');
    var st = n.querySelector('.agState'); if (st) st.textContent = st.getAttribute('data-default');
  });
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
    view.innerHTML = head + '<div class="empty">Binärdatei – per Download öffnen.</div>';
  }
}

document.getElementById('agChart').addEventListener('mousedown', function(ev) {
  var card = ev.target.closest('.agNode');
  if (!card || ev.button !== 0) return;
  ev.preventDefault();
  agDragMoved = false;
  agDrag = { card: card, startX: ev.clientX, startY: ev.clientY,
             origX: parseFloat(card.style.left) || 0, origY: parseFloat(card.style.top) || 0 };
  card.style.zIndex = 5;
  card.style.transition = 'none';
});
document.addEventListener('mousemove', function(ev) {
  if (!agDrag) return;
  var dx = (ev.clientX - agDrag.startX) / agView.zoom, dy = (ev.clientY - agDrag.startY) / agView.zoom;
  if (Math.abs(dx) + Math.abs(dy) > 4) agDragMoved = true;
  if (!agDragMoved) return;
  var nx = Math.max(-300, agDrag.origX + dx);
  var ny = Math.max(-300, agDrag.origY + dy);
  agDrag.card.style.left = nx + 'px';
  agDrag.card.style.top = ny + 'px';
  agUpdateSvgLive();
});
document.addEventListener('mouseup', function() {
  if (!agDrag) return;
  var card = agDrag.card;
  card.style.zIndex = '';
  card.style.transition = '';
  if (agDragMoved) {
    agCustomPos[card.getAttribute('data-bot')] = {
      x: parseFloat(card.style.left) || 0, y: parseFloat(card.style.top) || 0 };
    try { localStorage.setItem('jarvis_agpos', JSON.stringify(agCustomPos)); } catch (e) {}
    agLastHash = '';
  }
  agDrag = null;
});
document.getElementById('agChart').addEventListener('click', function(ev) {
  if (agDragMoved) { agDragMoved = false; return; }
  var card = ev.target.closest('.agNode');
  if (!card) return;
  var id = card.getAttribute('data-bot');
  document.getElementById('target').value = id;
  document.getElementById('input').focus();
});
document.getElementById('agentsView').addEventListener('wheel', function(ev) {
  ev.preventDefault();
  var rect = document.getElementById('agentsView').getBoundingClientRect();
  agZoomAt(ev.clientX - rect.left, ev.clientY - rect.top, ev.deltaY < 0 ? 1.12 : 0.89);
}, { passive: false });
document.getElementById('agentsView').addEventListener('mousedown', function(ev) {
  if (ev.target.closest('.agNode') || ev.button !== 0) return;
  agPan = { sx: ev.clientX - agView.x, sy: ev.clientY - agView.y };
  document.getElementById('agentsView').style.cursor = 'grabbing';
});
document.addEventListener('mousemove', function(ev) {
  if (!agPan) return;
  agView.x = ev.clientX - agPan.sx;
  agView.y = ev.clientY - agPan.sy;
  agApplyView();
});
document.addEventListener('mouseup', function() {
  if (agPan) { agPan = null; document.getElementById('agentsView').style.cursor = ''; }
});
document.getElementById('agentsView').addEventListener('dblclick', function(ev) {
  if (ev.target.closest('.agNode')) return;
  agView = { x: 0, y: 0, zoom: 1 };
  agApplyView();
});
document.getElementById('agChart').addEventListener('dblclick', function(ev) {
  var card = ev.target.closest('.agNode');
  if (!card) return;
  delete agCustomPos[card.getAttribute('data-bot')];
  try { localStorage.setItem('jarvis_agpos', JSON.stringify(agCustomPos)); } catch (e) {}
  agLastHash = '';
  document.getElementById('agChart').innerHTML = '';
  renderAgents(lastBots);
});

document.getElementById('vsearch').addEventListener('input', function() { vrender(); });

document.querySelectorAll('.col-left .panel h3').forEach(function(h) {
  h.addEventListener('click', function() { h.parentElement.classList.toggle('collapsed'); });
});

document.addEventListener('click', async function(ev) {
  var del = ev.target.closest('[data-del]');
  if (del) {
    ev.stopPropagation();
    var p = del.getAttribute('data-del');
    if (!confirm('Wirklich löschen? ' + p)) return;
    try {
      var r = await fetch('/api/vault/delete', { method: 'POST',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ path: p }) });
      if (r.ok) { vload(vpath); document.getElementById('vview').innerHTML = '<div class="empty">Gelöscht.</div>'; }
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
