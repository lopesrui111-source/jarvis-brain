#!/usr/bin/env python3
"""
BUEROFLOW-CEO — Bot am JARVIS-Bus
- Queue: bot:ceo:inbox / bot:ceo:reply:<id>
- Gemeinsames Langzeitgedaechtnis mit JARVIS (memory-Tabelle, pgvector)
- Mail: nur ionos (Bueroflow) read-only
- Skill: skill_ceo.md (CEO-Advisor, adaptiert)
"""

import os
import re
import sys
import json
import time
import uuid
import threading
from datetime import datetime

import redis
import requests
import imaplib
import email
from email.header import decode_header
import psycopg2
import psycopg2.extras
from anthropic import Anthropic
from protokoll import protokoll_init, protokoll_melden
from skills import (skills_indexieren, SKILL_TOOLS, SKILL_PROMPT,
                    skill_tool_ausfuehren, skill_banner)
from openai import OpenAI

BOT_NAME = "buroflow-ceo"
BOT_USER_ID = "ceo"

CLAUDE_KEY = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY", "")
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
PG_HOST = os.getenv("POSTGRES_HOST", "postgres")
PG_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
PG_USER = os.getenv("POSTGRES_USER", "jarvis")
PG_PASS = os.getenv("POSTGRES_PASSWORD", "")
PG_DB   = os.getenv("POSTGRES_DB", "jarvis_brain")

MODEL       = os.getenv("ORCHESTRATOR_MODEL", "claude-sonnet-4-6")
EMBED_MODEL = "text-embedding-3-small"
MAX_HISTORY = 12
MAX_TOKENS  = 2000
MAX_TOOL_ROUNDS = 10
VAULT_DIR = "/app/vault"

INBOX_KEY   = "bot:ceo:inbox"
HISTORY_KEY = "bot:ceo:history"
REPLY_KEY   = "bot:ceo:reply:{id}"

MAIL_IONOS = {
    "host": os.getenv("MAIL_IONOS_HOST", "imap.ionos.de"),
    "user": os.getenv("MAIL_IONOS_USER", ""),
    "pass": os.getenv("MAIL_IONOS_PASS", ""),
}

if not CLAUDE_KEY:
    print("FEHLER: ANTHROPIC_API_KEY fehlt", flush=True)
    sys.exit(1)

# Skill laden
SKILL = ""
try:
    with open(os.path.join(os.path.dirname(__file__), "skill_ceo.md"), encoding="utf-8") as f:
        SKILL = f.read()
except Exception:
    SKILL = "(Skill-Datei nicht gefunden — arbeite nach Grundprinzipien.)"

SYSTEM = f"""Du bist der BUEROFLOW-CEO — Ruis strategischer Co-Founder-Bot fuer Bueroflow.

PERSOENLICHKEIT:
- Du duzt Rui. Direkt, unternehmerisch, pragmatisch. Kein Corporate-Sprech.
- Kein Markdown in kurzen Antworten; bei Plaenen/Entwuerfen klare Struktur erlaubt.
- Du bist Mitgruender im Geiste: Du denkst in Warteliste, Conversion, MRR und Ruis Zeitbudget.

WAS DU UEBER BUEROFLOW WEISST:
- Deutsches SaaS fuer Kleinunternehmer/Solopreneure: Buerokratie-Tools (Mahnflow, Briefflow, Angebotsflow, E-Rechnungsflow).
- Stack: Next.js, Supabase, Clerk, Claude API. Live auf buroflow.de im PRE-LAUNCH: Waitlist + SEO offen, Dashboard/Verkauf gesperrt.
- Brand: Anthrazit #1A1D24, Weiss, Gruen-Akzent #5DCAA5, kursive Akzent-Woerter, radikaler Minimalismus, Anti-KI-Aesthetik.
- Tagline: "Weniger Buerokram. Mehr Feierabend."
- Marketing aktuell: manuelle Q&A-Praesenz auf gutefrage.net und Quora (ACHTUNG: gutefrage hat Rui wegen KI-Texten verwarnt — Entwuerfe muessen menschlich-locker klingen), LinkedIn-Unternehmensseite live.
- Rui macht das neben Vollzeitjob (Recruiting) — Zeit ist die knappste Ressource.

DEINE TOOLS:
- remember/recall: gemeinsames Langzeitgedaechtnis mit JARVIS. Speichere Entscheidungen/Staende (project: buroflow). recall nutzen bevor du raetst — auch fuer "Schreibstil buroflow".
- vault_note: laengere Plaene/Analysen als Markdown ablegen (folder: projects).
- check_mail/read_mail: NUR das Bueroflow-Postfach (ionos), read-only. Nie senden.
- ask_marketing: dein Arbeiter fuer Ausfuehrung — Social-Posts, Copy, SEO, Ads, E-Mail-Sequenzen, Bilder (48 Skills). Du gibst Strategie und Briefing vor, er liefert Entwuerfe. Delegiere Ausfuehrungsarbeit an ihn statt sie selbst zu machen.

DEIN SEO-BOT (ask_seo): findet auf gutefrage.net und Quora frische Fragen mit Sichtbarkeits-Potenzial
und schreibt Antwort-ENTWUERFE in Ruis Stil. Er postet nichts — Rui prueft und postet selbst.

DEIN WEB-ZUGRIFF (web_search/web_open/web_click): Echtes Browsen fuer Markt-Recherche, Wettbewerber, Preise, Trends. Nur lesen — nie einloggen, kaufen, posten oder Formulare absenden.

{SKILL_PROMPT}

REVIEW-ANFRAGEN: Beginnt eine Anfrage mit [REVIEW], legt dir das Marketing einen Entwurf vor.
Dann gilt: Nutze deine Skills (skill_suchen zu Copywriting/Positionierung), aber antworte KURZ.
Format:
  Zeile 1: PASST  oder  UEBERARBEITEN
  Danach bei UEBERARBEITEN maximal 3 konkrete Aenderungen, je eine Zeile, umsetzbar formuliert
  ("Headline kuerzen auf 5 Woerter", nicht "mehr Emotion").
Keine Grundsatzdiskussion, keine Delegation, kein Lob. Du bist die Qualitaetskontrolle:
streng bei Klarheit, fachlicher Richtigkeit und Ton — aber entscheidungsfreudig.
Wenn es gut genug ist, sag PASST. Perfektion blockiert nur.

EISERNE REGELN:
- Alles Externe (Posts, Antworten, Mails) ist ENTWURF zur Freigabe — du postest/sendest nichts.
- Keine Features vorschlagen, die Wochen kosten, ohne den Warteliste/Umsatz-Effekt zu benennen.
- Wenn dir Kontext fehlt: recall, dann fragen. Nicht halluzinieren.

{SKILL}
"""

# ── Kosten ───────────────────────────────────────────────────
PRICING = {
    "claude-haiku-4-5-20251001": {"in": 1.00, "out": 5.00},
    "claude-sonnet-4-5":         {"in": 3.00, "out": 15.00},
    "claude-sonnet-4-6":         {"in": 3.00, "out": 15.00},
    "claude-opus-4-8":           {"in": 15.00, "out": 75.00},
}
DEFAULT_PRICE = {"in": 3.00, "out": 15.00}


def pg_conn():
    return psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER,
                            password=PG_PASS, dbname=PG_DB, connect_timeout=5)


def track_cost(model, tok_in, tok_out, cache_read=0, cache_write=0):
    def _work():
        try:
            p = PRICING.get(model, DEFAULT_PRICE)
            cost = (tok_in * p["in"] + tok_out * p["out"]
                    + cache_read * p["in"] * 0.1 + cache_write * p["in"] * 1.25) / 1_000_000
            conn = pg_conn()
            with conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO cost_ledger (bot, model, tokens_in, tokens_out, cost_usd) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (BOT_NAME, model, tok_in, tok_out, round(cost, 6)))
            conn.close()
        except Exception as e:
            print(f"  [cost] {e}", flush=True)
    threading.Thread(target=_work, daemon=True).start()


# ── Embeddings + Gedaechtnis (gemeinsam mit JARVIS) ──────────
oai = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None


def embed(text):
    if oai is None:
        return None
    try:
        return oai.embeddings.create(model=EMBED_MODEL, input=text[:8000]).data[0].embedding
    except Exception as e:
        print(f"  [embed] {e}", flush=True)
        return None


def vec_literal(v):
    return "[" + ",".join(f"{x:.7f}" for x in v) + "]"


def tool_remember(inp):
    content = (inp.get("content") or "").strip()
    project = (inp.get("project") or "buroflow").strip().lower()
    title   = (inp.get("title") or "").strip()
    if not content:
        return "Fehler: leerer Inhalt."
    v = embed(f"{title}\n{content}")
    try:
        conn = pg_conn()
        with conn, conn.cursor() as cur:
            if v is not None:
                cur.execute("INSERT INTO memory (source, project, title, content, embedding) "
                            "VALUES (%s, %s, %s, %s, %s::vector) RETURNING id",
                            (BOT_NAME, project, title, content, vec_literal(v)))
            else:
                cur.execute("INSERT INTO memory (source, project, title, content) "
                            "VALUES (%s, %s, %s, %s) RETURNING id",
                            (BOT_NAME, project, title, content))
            mid = cur.fetchone()[0]
        conn.close()
        return f"Gespeichert (#{mid}, {project}): {title}"
    except Exception as e:
        return f"Fehler beim Speichern: {e}"


def tool_recall(inp, k=5):
    query = (inp.get("query") or "").strip()
    project = (inp.get("project") or "").strip().lower()
    if not query:
        return "Fehler: leere Suchanfrage."
    v = embed(query)
    try:
        conn = pg_conn()
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if v is not None:
                sql = ("SELECT id, project, title, content, created_at, "
                       "embedding <=> %s::vector AS dist FROM memory WHERE embedding IS NOT NULL ")
                params = [vec_literal(v)]
                if project:
                    sql += "AND project = %s "
                    params.append(project)
                sql += "ORDER BY dist ASC LIMIT %s"
                params.append(k)
                cur.execute(sql, params)
            else:
                cur.execute("SELECT id, project, title, content, created_at, 0 AS dist "
                            "FROM memory ORDER BY created_at DESC LIMIT %s", (k,))
            rows = cur.fetchall()
        conn.close()
        if not rows:
            return "Keine Treffer im Gedaechtnis."
        return "\n".join(f"[#{r['id']} | {r['project']} | {r['created_at'].strftime('%d.%m.%Y')}] "
                         f"{r['title']}: {r['content']}" for r in rows)
    except Exception as e:
        return f"Fehler bei der Suche: {e}"


def tool_vault_note(inp):
    folder = (inp.get("folder") or "projects").strip().lower()
    if folder not in ("daily", "notes", "projects", "inbox", "skills"):
        folder = "projects"
    title = (inp.get("title") or "notiz").strip()
    content = (inp.get("content") or "").strip()
    if not content:
        return "Fehler: leerer Inhalt."
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "-", title.replace(" ", "-"))[:60].strip("-") or "notiz"
    fname = f"{datetime.now().strftime('%Y-%m-%d')}_{safe}.md"
    path = os.path.join(VAULT_DIR, folder, fname)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n{content}\n\n---\n*{BOT_NAME}, {datetime.now().strftime('%d.%m.%Y %H:%M')}*\n")
        return f"Notiz abgelegt: vault/{folder}/{fname}"
    except Exception as e:
        return f"Fehler beim Schreiben: {e}"


# ── Mail (nur ionos, read-only) ──────────────────────────────
def _dec(s):
    if not s:
        return ""
    out = ""
    for txt, enc in decode_header(s):
        if isinstance(txt, bytes):
            out += txt.decode(enc or "utf-8", errors="replace")
        else:
            out += txt
    return out.strip()


def _imap():
    if not MAIL_IONOS["user"] or not MAIL_IONOS["pass"]:
        return None, "IONOS-Postfach nicht konfiguriert."
    try:
        M = imaplib.IMAP4_SSL(MAIL_IONOS["host"], 993)
        M.login(MAIL_IONOS["user"], MAIL_IONOS["pass"])
        M.select("INBOX", readonly=True)
        return M, None
    except Exception as e:
        return None, f"IMAP-Fehler: {e}"


def _extract_body(msg):
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                p = part.get_payload(decode=True)
                if p:
                    body = p.decode(part.get_content_charset() or "utf-8", errors="replace")
                    break
        if not body:
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    p = part.get_payload(decode=True)
                    if p:
                        h = p.decode(part.get_content_charset() or "utf-8", errors="replace")
                        body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))
                        break
    else:
        p = msg.get_payload(decode=True)
        if p:
            raw = p.decode(msg.get_content_charset() or "utf-8", errors="replace")
            if msg.get_content_type() == "text/html":
                raw = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw))
            body = raw
    return (body or "").strip()


def tool_check_mail(inp):
    limit = min(int(inp.get("limit") or 10), 25)
    unread_only = inp.get("unread_only", True)
    M, err = _imap()
    if err:
        return err
    try:
        ok, data = M.uid("search", None, "UNSEEN" if unread_only else "ALL")
        if ok != "OK":
            return "Suche fehlgeschlagen."
        uids = data[0].split()
        total = len(uids)
        uids = uids[-limit:][::-1]
        if not uids:
            return "Keine ungelesenen Mails im Bueroflow-Postfach." if unread_only else "Postfach leer."
        lines = [f"Bueroflow-Postfach — {total} {'ungelesen' if unread_only else 'gesamt'}:"]
        for uid in uids:
            ok, md = M.uid("fetch", uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if ok != "OK" or not md or md[0] is None:
                continue
            m = email.message_from_bytes(md[0][1])
            lines.append(f"[uid {uid.decode()}] {_dec(m.get('Date'))[:31]} | "
                         f"{_dec(m.get('From'))[:55]} | {_dec(m.get('Subject'))[:75] or '(kein Betreff)'}")
        return "\n".join(lines)
    except Exception as e:
        return f"Fehler beim Abrufen: {e}"
    finally:
        try:
            M.logout()
        except Exception:
            pass


def tool_read_mail(inp):
    uid = (inp.get("uid") or "").strip()
    if not uid:
        return "Fehler: uid fehlt."
    M, err = _imap()
    if err:
        return err
    try:
        ok, md = M.uid("fetch", uid.encode(), "(BODY.PEEK[])")
        if ok != "OK" or not md or md[0] is None:
            return f"Mail uid {uid} nicht gefunden."
        m = email.message_from_bytes(md[0][1])
        body = (_extract_body(m) or "(kein Textinhalt)")[:4000]
        return f"Von: {_dec(m.get('From'))}\nDatum: {_dec(m.get('Date'))}\nBetreff: {_dec(m.get('Subject'))}\n\n{body}"
    except Exception as e:
        return f"Fehler beim Lesen: {e}"
    finally:
        try:
            M.logout()
        except Exception:
            pass


TOOLS = [
    {"name": "remember",
     "description": "Speichert wichtige Fakten/Entscheidungen dauerhaft im gemeinsamen Gedaechtnis.",
     "input_schema": {"type": "object", "properties": {
         "content": {"type": "string"}, "project": {"type": "string", "description": "Standard: buroflow"},
         "title": {"type": "string"}}, "required": ["content", "title"]}},
    {"name": "recall",
     "description": "Durchsucht das gemeinsame Langzeitgedaechtnis semantisch (auch JARVIS-Eintraege und 'Schreibstil buroflow').",
     "input_schema": {"type": "object", "properties": {
         "query": {"type": "string"}, "project": {"type": "string"}}, "required": ["query"]}},
    {"name": "vault_note",
     "description": "Legt laengere Plaene/Analysen als Markdown im Vault ab.",
     "input_schema": {"type": "object", "properties": {
         "folder": {"type": "string", "description": "projects|notes|inbox"},
         "title": {"type": "string"}, "content": {"type": "string"}},
         "required": ["title", "content"]}},
    {"name": "check_mail",
     "description": "Listet Mails im Bueroflow-Postfach (ionos, read-only).",
     "input_schema": {"type": "object", "properties": {
         "limit": {"type": "integer"}, "unread_only": {"type": "boolean"}}}},
    {"name": "read_mail",
     "description": "Liest eine Mail aus dem Bueroflow-Postfach (uid aus check_mail).",
     "input_schema": {"type": "object", "properties": {"uid": {"type": "string"}}, "required": ["uid"]}},
    {"name": "ask_marketing",
     "description": "Delegiert eine Marketing-Aufgabe an den Marketing-Bot (48 Skills: Social, Copywriting, SEO, Ads, E-Mails, Bildgenerierung via MuAPI u.v.m.). Er liefert fertige Entwuerfe. Dauert bis zu 4 Minuten.",
     "input_schema": {"type": "object", "properties": {
         "task": {"type": "string", "description": "Der Auftrag, praezise mit Kontext (Kanal, Ziel, Thema)"}},
         "required": ["task"]}},
    {
        "name": "web_search",
        "description": "Google-Suche ueber den Stealth-Browser. Liefert Ergebnisliste als Text-Snapshot mit klickbaren refs (e1, e2...).",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },
    {
        "name": "web_open",
        "description": "Oeffnet eine URL im Stealth-Browser und liefert den Seiteninhalt als kompakten Text-Snapshot. Auch Macros: @youtube_search foo, @reddit_subreddit bar.",
        "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    },
    {
        "name": "ask_seo",
        "description": "Delegiert an den SEO/Q&A-BOT: frische Fragen auf gutefrage.net und Quora finden, Antwort-Entwuerfe in Ruis Stil schreiben (Vault seo/ + Telegram). Der Bot postet nichts. Kann bis zu 7 Minuten dauern.",
        "input_schema": {"type": "object", "properties": {"task": {"type": "string"}}, "required": ["task"]},
    },
    {
        "name": "web_click",
        "description": "Klickt ein Element (ref aus Snapshot, z.B. e3) im offenen Tab und liefert den neuen Snapshot.",
        "input_schema": {"type": "object", "properties": {"tab_id": {"type": "string"}, "ref": {"type": "string"}}, "required": ["tab_id", "ref"]},
    },
]



# ── WEB-ZUGRIFF (camofox, anti-detect Browser) ───────────────
CAMOFOX_URL = os.getenv("CAMOFOX_URL", "http://camofox:9377")


WEB_MACROS = {
    "@google_search":   "https://www.google.com/search?q={}",
    "@youtube_search":  "https://www.youtube.com/results?search_query={}",
    "@wikipedia_search": "https://de.wikipedia.org/wiki/Spezial:Suche?search={}",
    "@reddit_search":   "https://www.reddit.com/search/?q={}",
    "@linkedin_search": "https://www.linkedin.com/search/results/all/?keywords={}",
}


def _expand_macro(target):
    if not target.startswith("@"):
        return target
    parts = target.split(None, 1)
    tmpl = WEB_MACROS.get(parts[0])
    if not tmpl:
        return target
    from urllib.parse import quote
    return tmpl.format(quote(parts[1] if len(parts) > 1 else ""))


def _camofox_open(target: str, bot_user: str) -> str:
    try:
        r = requests.post(f"{CAMOFOX_URL}/tabs", json={"userId": bot_user, "sessionKey": "main", "url": _expand_macro(target)}, timeout=60)
        if r.status_code >= 400:
            return f"Browser-Fehler ({r.status_code}): {r.text[:200]}"
        tab = r.json().get("tabId") or r.json().get("id")
        if not tab:
            return f"Kein Tab erhalten: {str(r.json())[:200]}"
        s = requests.get(f"{CAMOFOX_URL}/tabs/{tab}/snapshot", params={"userId": bot_user}, timeout=60)
        if s.status_code >= 400:
            return f"Snapshot-Fehler ({s.status_code}): {s.text[:200]}"
        snap = s.json().get("snapshot", "")
        return f"[tab {tab}]\n{snap[:3500]}"
    except Exception as e:
        return f"Browser nicht erreichbar ({type(e).__name__}) — laeuft der camofox-Container?"


def tool_web_search(inp):
    q = (inp.get("query") or "").strip()
    if not q:
        return "Fehler: leere Suche."
    return _camofox_open("@google_search " + q, BOT_USER_ID)


def tool_web_open(inp):
    url = (inp.get("url") or "").strip()
    if not url:
        return "Fehler: leere URL."
    return _camofox_open(url, BOT_USER_ID)


def tool_web_click(inp):
    tab = (inp.get("tab_id") or "").strip()
    ref = (inp.get("ref") or "").strip()
    if not tab or not ref:
        return "Fehler: tab_id und ref noetig."
    try:
        r = requests.post(f"{CAMOFOX_URL}/tabs/{tab}/click", json={"userId": BOT_USER_ID, "sessionKey": "main", "ref": ref}, timeout=60)
        if r.status_code >= 400:
            return f"Click-Fehler ({r.status_code}): {r.text[:200]}"
        s = requests.get(f"{CAMOFOX_URL}/tabs/{tab}/snapshot", params={"userId": BOT_USER_ID}, timeout=60)
        snap = s.json().get("snapshot", "") if s.status_code < 400 else ""
        return f"[tab {tab}]\n{snap[:3500]}"
    except Exception as e:
        return f"Browser-Fehler: {type(e).__name__}: {e}"


def tool_ask_seo(inp):
    task = (inp.get("task") or "").strip()
    if not task:
        return "Fehler: leerer Auftrag."
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True,
                            socket_keepalive=True, health_check_interval=20,
                            retry_on_timeout=True, socket_timeout=30)
        req_id = str(uuid.uuid4())
        r.rpush("bot:seo:inbox", json.dumps({"id": req_id, "text": task}, ensure_ascii=False))
        resp = r.blpop(f"bot:seo:reply:{req_id}", timeout=420)
        if resp is None:
            return "SEO-Bot antwortet nicht (Timeout) — laeuft der Container?"
        return f"SEO-BOT:\n{resp[1]}"
    except Exception as e:
        return f"Fehler: {type(e).__name__}: {e}"


def tool_ask_marketing(inp):
    task = (inp.get("task") or "").strip()
    if not task:
        return "Fehler: leerer Auftrag."
    try:
        rr = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True,
                            socket_keepalive=True, health_check_interval=20,
                            retry_on_timeout=True, socket_timeout=30)
        req_id = str(uuid.uuid4())
        rr.rpush("bot:marketing:inbox", json.dumps({"id": req_id, "text": "[von-ceo] " + task}, ensure_ascii=False))
        resp = rr.blpop(f"bot:marketing:reply:{req_id}", timeout=240)
        if resp is None:
            return "Marketing-Bot antwortet nicht (Timeout) — laeuft der jarvis-marketing Container?"
        return f"Marketing-Antwort:\n{resp[1]}"
    except Exception as e:
        return f"Fehler bei der Delegation: {e}"


TOOLS = TOOLS + SKILL_TOOLS

def run_tool(name, inp):
    _skill = skill_tool_ausfuehren(name, inp)
    if _skill is not None:
        return _skill
    if name == "remember":
        return tool_remember(inp)
    if name == "recall":
        return tool_recall(inp)
    if name == "vault_note":
        return tool_vault_note(inp)
    if name == "check_mail":
        return tool_check_mail(inp)
    if name == "read_mail":
        return tool_read_mail(inp)
    if name == "ask_marketing":
        return tool_ask_marketing(inp)
    if name == "ask_seo":
        return tool_ask_seo(inp)
    if name == "web_search":
        return tool_web_search(inp)
    if name == "web_open":
        return tool_web_open(inp)
    if name == "web_click":
        return tool_web_click(inp)
    return f"Unbekanntes Tool: {name}"


# ── Claude Tool-Loop ─────────────────────────────────────────
client = Anthropic(api_key=CLAUDE_KEY)

# Prompt-Caching: System-Prompt + Tools werden serverseitig gecacht (90% billiger ab 2. Aufruf)
import copy as _copy
SYS_CACHED = [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}]
TOOLS_CACHED = _copy.deepcopy(TOOLS)
if TOOLS_CACHED:
    TOOLS_CACHED[-1]["cache_control"] = {"type": "ephemeral"}


def load_history(r):
    try:
        raw = r.get(HISTORY_KEY)
        return json.loads(raw) if raw else []
    except Exception:
        return []


def save_history(r, h):
    try:
        r.set(HISTORY_KEY, json.dumps(h[-MAX_HISTORY:], ensure_ascii=False))
    except Exception as e:
        print(f"  [history] {e}", flush=True)



# Erkennt Antworten, die nur eine Absicht ankuendigen, ohne sie auszufuehren
ANNOUNCE_RE = re.compile(
    r"(lass mich|ich (schaue|sehe|gehe|starte|pruefe|pr\u00fcfe|hole|lese|checke|melde|merke|speichere)"
    r"|starte (jetzt|gleich|mal)|einen? moment|moment mal|bin dran|noch dran"
    r"|mache mich (dran|ans)|fange (jetzt |gleich )?an|arbeite (das )?(jetzt|gleich)"
    r"|gebe dir gleich|sage dir gleich|dauert (einen|kurz)|gehe (das )?(jetzt |gleich )?durch)", re.I)

# Kurze Saetze im Stil "Jetzt alles merken." / "Dann weiter pruefen."
INTENT_RE = re.compile(
    r"^(jetzt|gleich|nun|dann|weiter|als n(ae|\u00e4)chstes|zuerst|noch)\b[^.!?]{0,70}\b\w{3,}(en|ern)\.?$",
    re.I)


def _ist_leere_ankuendigung(text):
    """True, wenn der Bot nur ankuendigt statt zu handeln."""
    if not text:
        return False
    t = " ".join(text.split())
    if len(t) > 260:
        return False
    if ANNOUNCE_RE.search(t):
        return True
    # Absichts-Saetze pruefen (auch wenn sie nicht am Anfang stehen)
    saetze = [s.strip() for s in re.split(r"[.!?]+", t) if s.strip()]
    if len(t) <= 160:
        for s in saetze:
            if len(s) <= 90 and INTENT_RE.match(s):
                return True
    return False


def think(history, user_text):
    context = ""
    if oai is not None:
        hits = tool_recall({"query": user_text, "project": "buroflow"}, k=3)
        if hits and not hits.startswith(("Keine", "Fehler")):
            context = f"\n\n[AUTO-RECALL buroflow:\n{hits}]"
    history.append({"role": "user", "content": user_text})
    messages = list(history)
    if context:
        messages[-1] = {"role": "user", "content": user_text + context}
    final_text = ""
    tool_benutzt = False
    nachfass_zahl = 0
    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS,
                                      system=SYS_CACHED, tools=TOOLS_CACHED, messages=messages)
        try:
            track_cost(MODEL, resp.usage.input_tokens, resp.usage.output_tokens, getattr(resp.usage, 'cache_read_input_tokens', 0) or 0, getattr(resp.usage, 'cache_creation_input_tokens', 0) or 0)
        except Exception:
            pass
        parts = [b.text for b in resp.content if b.type == "text"]
        _txt = "".join(parts).strip()
        if _txt:
            final_text = _txt
        if resp.stop_reason != "tool_use":
            if nachfass_zahl < 2 and _ist_leere_ankuendigung(final_text):
                nachfass_zahl += 1
                print("  [nudge] Ankuendigung ohne Ausfuehrung erkannt — fasse nach", flush=True)
                messages.append({"role": "assistant", "content": final_text})
                messages.append({"role": "user", "content": "Du hast nur angekuendigt, aber nichts getan. Fuehre den Auftrag JETZT aus: rufe die noetigen Tools auf und antworte erst, wenn du das Ergebnis hast. Keine weitere Ankuendigung."})
                continue
            break
        tool_benutzt = True
        a_content, t_results = [], []
        for block in resp.content:
            if block.type == "text":
                a_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                a_content.append({"type": "tool_use", "id": block.id,
                                  "name": block.name, "input": block.input})
                result = run_tool(block.name, block.input or {})
                print(f"  [tool] {block.name} -> {result[:90]}", flush=True)
                t_results.append({"type": "tool_result", "tool_use_id": block.id,
                                  "content": result})
        messages.append({"role": "assistant", "content": a_content})
        messages.append({"role": "user", "content": t_results})
    # Runden aufgebraucht, aber noch keine echte Antwort -> Abschluss ohne Tools erzwingen
    if tool_benutzt and (not final_text or resp.stop_reason == "tool_use"):
        try:
            messages.append({"role": "user", "content":
                "Die Werkzeug-Runden sind aufgebraucht. Fasse JETZT zusammen, was du "
                "herausgefunden hast, und nenne offene Punkte. Keine weiteren Tool-Aufrufe."})
            resp2 = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS,
                                           system=SYS_CACHED, messages=messages)
            try:
                track_cost(MODEL, resp2.usage.input_tokens, resp2.usage.output_tokens,
                           getattr(resp2.usage, 'cache_read_input_tokens', 0) or 0,
                           getattr(resp2.usage, 'cache_creation_input_tokens', 0) or 0)
            except Exception:
                pass
            t2 = "".join(b.text for b in resp2.content if b.type == "text").strip()
            if t2:
                final_text = t2
                print("  [abschluss] Zusammenfassung nach Rundenlimit erzwungen", flush=True)
        except Exception as e:
            print(f"  [abschluss] {type(e).__name__}: {e}", flush=True)

    if not final_text:
        final_text = ("Ich konnte den Auftrag nicht abschliessen — bitte in kleineren Schritten "
                      "anfragen (z.B. erst Ordnerstruktur, dann einzelne Dateien).")
    history.append({"role": "assistant", "content": final_text})
    return final_text


def _antwort_senden(r, queue, text):
    """Antwort zustellen — auch wenn die Verbindung waehrend langer Arbeit abgelaufen ist."""
    for versuch in range(3):
        try:
            r.rpush(queue, text)
            r.expire(queue, 300)
            return True
        except Exception as e:
            print(f"  [reply] Versuch {versuch + 1} fehlgeschlagen ({type(e).__name__}) — neue Verbindung", flush=True)
            try:
                r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True,
                                socket_keepalive=True, health_check_interval=20,
                                retry_on_timeout=True, socket_timeout=30)
            except Exception:
                pass
            time.sleep(1)
    print("  [reply] Antwort konnte NICHT zugestellt werden!", flush=True)
    return False


def main():
    protokoll_init()
    skills_indexieren()
    print("=" * 58, flush=True)
    print("  BUEROFLOW-CEO — Bot am JARVIS-Bus", flush=True)
    print(f"  Skills    : {skill_banner()}", flush=True)
    print(f"  Modell: {MODEL} | Queue: {INBOX_KEY}", flush=True)
    print(f"  Skill : {'geladen' if len(SKILL) > 100 else 'FEHLT'}", flush=True)
    print("=" * 58, flush=True)

    r = None
    for attempt in range(30):
        try:
            r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True,
                            socket_keepalive=True, health_check_interval=20,
                            retry_on_timeout=True, socket_timeout=30)
            r.ping()
            print("  [redis] verbunden", flush=True)
            break
        except Exception:
            time.sleep(2)
    if r is None:
        sys.exit(1)
    print("  CEO bereit.\n", flush=True)

    while True:
        try:
            item = r.blpop(INBOX_KEY, timeout=5)
            if item is None:
                continue
            _, raw = item
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            req_id = msg.get("id", str(uuid.uuid4()))
            text = (msg.get("text") or "").strip()
            reply_q = REPLY_KEY.format(id=req_id)
            if not text:
                _antwort_senden(r, reply_q, "Leere Anfrage.")
                continue
            if text.lower() in ("reset", "vergiss alles"):
                r.delete(HISTORY_KEY)
                _antwort_senden(r, reply_q, "CEO-Kurzzeitgedaechtnis geleert.")
                continue
            print(f"  Auftrag: {text[:80]}", flush=True)
            history = load_history(r)
            try:
                answer = think(history, text)
            except Exception as e:
                answer = f"Fehler: {type(e).__name__}: {e}"
                print(f"  [think] {answer}", flush=True)
            save_history(r, history)
            try:
                protokoll_melden("ceo", "Anfrage beantwortet", text[:120], "")
            except Exception:
                pass
            print(f"  CEO: {answer[:100]}\n", flush=True)
            _antwort_senden(r, reply_q, answer)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"  [loop] {type(e).__name__}: {e}", flush=True)
            time.sleep(1)


if __name__ == "__main__":
    main()
