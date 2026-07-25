#!/usr/bin/env python3
"""
JARVIS Core v7.5 — v7.4 + IMMO-BOT-DELEGATION
Neu gegenueber v4:
- Stil-Analyse: 'stil ionos' / 'stil gmail' liest die letzten gesendeten
  Mails (read-only), erstellt ein Schreibstil-Profil und speichert es
  ins Langzeitgedaechtnis + Vault (skills/)
- Gesendet-Ordner wird automatisch erkannt (\\Sent Flag, Fallback-Namen)
- ask_ceo: delegiert Auftraege an den Bueroflow-CEO-Bot am Bus
- ask_immo: dein Immobilien-Analyst (Rendite-Bewertungen, Scans, Telegram-Alerts an Rui).
- check_calendar: Ruis iCloud-Kalender lesen (Termine der naechsten Tage). Read-only — du kannst nichts eintragen oder aendern.
- web_search/web_open/web_click: echtes Browsen via camofox
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
from openai import OpenAI

# ── KONFIGURATION ────────────────────────────────────────────
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
EMBED_MODEL = "text-embedding-3-small"   # 1536 Dimensionen, passt zur DB
MAX_HISTORY = 16
MAX_TOKENS  = 1024
MAX_TOOL_ROUNDS = 5

VAULT_DIR = "/app/vault"
BOT_USER_ID = "jarvis"

ICLOUD_USER = os.getenv("ICLOUD_USER", "")
ICLOUD_PASS = os.getenv("ICLOUD_PASS", "")

# Mail-Konten (read-only). Nur Konten mit gesetztem User+Pass sind aktiv.
MAIL_ACCOUNTS = {
    "ionos": {
        "host": os.getenv("MAIL_IONOS_HOST", "imap.ionos.de"),
        "user": os.getenv("MAIL_IONOS_USER", ""),
        "pass": os.getenv("MAIL_IONOS_PASS", ""),
        "label": "Bueroflow (IONOS)",
    },
    "gmail": {
        "host": os.getenv("MAIL_GMAIL_HOST", "imap.gmail.com"),
        "user": os.getenv("MAIL_GMAIL_USER", ""),
        "pass": os.getenv("MAIL_GMAIL_PASS", ""),
        "label": "Privat (Gmail)",
    },
}

INBOX_KEY   = "jarvis:inbox"
HISTORY_KEY = "jarvis:history"
REPLY_KEY   = "jarvis:reply:{id}"
DAYLOG_KEY  = "jarvis:daylog:{date}"      # Tages-Mitschnitt
NIGHTLY_MARK = "jarvis:nightly:last"      # Datum des letzten Laufs
NIGHTLY_HOUR = 3                          # 03:00 Europe/Berlin (TZ aus .env)
DEDUP_DIST  = 0.15                        # Vektor-Distanz: darunter = Duplikat

if not CLAUDE_KEY:
    print("FEHLER: ANTHROPIC_API_KEY fehlt in .env", flush=True)
    sys.exit(1)
if not OPENAI_KEY:
    print("WARNUNG: OPENAI_API_KEY fehlt — Gedaechtnis (Embeddings) deaktiviert", flush=True)

# ── SYSTEM-PROMPT ────────────────────────────────────────────
SYSTEM = """Du bist JARVIS, der persoenliche KI-Sparringspartner von Rui — 24/7-Server-Instanz mit Langzeitgedaechtnis.

PERSOENLICHKEIT:
- Du duzt Rui. Kein Sir, kein Sie.
- Direkt, ehrlich, kurz und knackig. Mitdenkend, nicht unterwuerfig.
- Kein Markdown, keine Emojis, keine Sternchen in Antworten.
- Standard: 1-3 kurze Saetze. Nur ausfuehrlich wenn Rui es explizit will.

DEIN GEDAECHTNIS (Tools):
- remember: Speichere wichtige Fakten, Entscheidungen, Vorlieben dauerhaft. Nutze es proaktiv, wenn Rui dir etwas Wichtiges erzaehlt (Projekte, Zahlen, Entscheidungen, Deadlines).
- recall: Durchsuche dein Langzeitgedaechtnis. Nutze es, wenn Rui nach frueheren Themen fragt oder dir Kontext fehlt.
- vault_note: Lege eine Markdown-Notiz im Wissens-Vault ab (fuer laengere Inhalte: Zusammenfassungen, Plaene, Recherchen).
- check_mail / read_mail: Lies Ruis Postfaecher (ionos = Bueroflow-Business, gmail = privat). STRIKT read-only. Du kannst Mails zusammenfassen und Antwort-ENTWUERFE vorschlagen, aber nie senden.
- ask_immo: dein Immobilien-Analyst (Rendite-Bewertungen, Scans, Telegram-Alerts an Rui).
- check_calendar: Ruis iCloud-Kalender lesen (Termine der naechsten Tage). Read-only — du kannst nichts eintragen oder aendern.
- web_search/web_open/web_click: Du kannst echt im Web browsen (Stealth-Browser). Nutze es fuer aktuelle Infos, Recherche, Preise, News. REGELN: nur lesen und recherchieren — nie einloggen, nie kaufen, nie posten, nie Formulare absenden.
- Bevor du Texte/Mails/Posts fuer Rui entwirfst: recall nach "Schreibstil" und wende das Profil an (buroflow = geschaeftlich, privat = persoenlich).
- Vor jeder Antwort bekommst du automatisch relevante Gedaechtnis-Treffer als Kontext (AUTO-RECALL). Nutze sie, erwaehne sie nur wenn relevant.

DEINE ROLLE:
- Orchestrator eines Multi-Agent-Systems auf einem Hetzner-Server. Erster Bot am Bus: der BUEROFLOW-CEO (ask_ceo) fuer Strategie, Marketing-Entwuerfe und Bueroflow-Analysen. Delegiere Bueroflow-Detailarbeit an ihn; einfache Fragen beantworte selbst.
- Ruis Denk-Partner: Ideen challengen, Optionen abwaegen, Klartext reden.
- Sag nie "ich bin nur eine KI". Wenn du etwas nicht kannst, sag konkret was fehlt.

WAS DU UEBER RUI WEISST:
- Recruiting-Berater (Bau/Immobilien, BW+Hessen) bei Elements Personalberatung, Stuttgart.
- Baut Bueroflow (SaaS, Pre-Launch auf buroflow.de) — Waitlist laeuft.
- Immo-Investor im Rems-Murr-Kreis, Ziel >=4% Bruttomietrendite.
- Weitere Projekte: Frozen Memory (Shopify), Stille Minuten (YouTube), lokales JARVIS v5.
- Windows-User (rlope), mag CMD, komplette Dateien, kurze Antworten.

WICHTIG:
- Wenn du etwas nicht sicher weisst, sag es ehrlich. recall nutzen statt raten.
- Speichere nichts Belangloses — Qualitaet vor Quantitaet im Gedaechtnis.
"""

# ── TOOLS (Claude Tool-Use Definitionen) ─────────────────────
TOOLS = [
    {
        "name": "remember",
        "description": "Speichert einen wichtigen Fakt dauerhaft im Langzeitgedaechtnis (mit Embedding fuer spaetere Suche). Fuer kurze, wichtige Infos: Entscheidungen, Zahlen, Vorlieben, Projektstaende.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Der zu merkende Fakt, praezise formuliert"},
                "project": {"type": "string", "description": "Projekt-Tag: elements|buroflow|immo|frozen|stille|jarvis|privat|sonstiges"},
                "title": {"type": "string", "description": "Kurzer Titel (3-6 Woerter)"},
            },
            "required": ["content", "project", "title"],
        },
    },
    {
        "name": "recall",
        "description": "Durchsucht das Langzeitgedaechtnis semantisch (Vektor-Suche). Nutzen wenn Kontext zu frueheren Themen fehlt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Wonach suchen (natuerliche Sprache)"},
                "project": {"type": "string", "description": "Optional: nur dieses Projekt durchsuchen"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "vault_note",
        "description": "Legt eine Markdown-Notiz im Wissens-Vault ab (Git-Ordner). Fuer laengere Inhalte: Zusammenfassungen, Plaene, Analysen.",
        "input_schema": {
            "type": "object",
            "properties": {
                "folder": {"type": "string", "description": "Zielordner: daily|notes|projects|inbox"},
                "title": {"type": "string", "description": "Dateititel ohne .md"},
                "content": {"type": "string", "description": "Markdown-Inhalt der Notiz"},
            },
            "required": ["folder", "title", "content"],
        },
    },
    {
        "name": "check_mail",
        "description": "Listet die neuesten Mails eines Postfachs (read-only, nichts wird als gelesen markiert). Konten: 'ionos' (Bueroflow) oder 'gmail' (privat).",
        "input_schema": {
            "type": "object",
            "properties": {
                "account": {"type": "string", "description": "ionos oder gmail"},
                "limit": {"type": "integer", "description": "Wieviele Mails (Standard 10, max 25)"},
                "unread_only": {"type": "boolean", "description": "Nur ungelesene (Standard: true)"},
            },
            "required": ["account"],
        },
    },
    {
        "name": "read_mail",
        "description": "Liest den Textinhalt einer Mail (read-only). uid stammt aus check_mail.",
        "input_schema": {
            "type": "object",
            "properties": {
                "account": {"type": "string", "description": "ionos oder gmail"},
                "uid": {"type": "string", "description": "Mail-UID aus check_mail"},
            },
            "required": ["account", "uid"],
        },
    },
    {
        "name": "ask_ceo",
        "description": "Delegiert einen Auftrag an den Bueroflow-CEO-Bot (Strategie, Marketing-Entwuerfe, Bueroflow-Analysen). Der CEO hat eigenes Fachwissen, Zugriff aufs gemeinsame Gedaechtnis und das Bueroflow-Postfach. Dauert bis zu 2 Minuten.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Der Auftrag an den CEO, praezise formuliert"},
            },
            "required": ["task"],
        },
    },
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
        "name": "web_click",
        "description": "Klickt ein Element (ref aus Snapshot, z.B. e3) im offenen Tab und liefert den neuen Snapshot.",
        "input_schema": {"type": "object", "properties": {"tab_id": {"type": "string"}, "ref": {"type": "string"}}, "required": ["tab_id", "ref"]},
    },
    {
        "name": "ask_immo",
        "description": "Delegiert an den IMMO-BOT (Immobilien-Investment-Analyst): Angebote bewerten (URL), ImmoScout-Mails scannen, Kleinanzeigen-Suchen pruefen, fruehere Objekte nachschlagen. Kann bis zu 4 Minuten dauern.",
        "input_schema": {"type": "object", "properties": {"task": {"type": "string"}}, "required": ["task"]},
    },
    {
        "name": "check_calendar",
        "description": "Liest Ruis iCloud-Kalender (read-only): kommende Termine der naechsten Tage, sortiert.",
        "input_schema": {"type": "object", "properties": {
            "days": {"type": "integer", "description": "Zeitraum in Tagen (Standard 7, max 30)"}},
        },
    },
]


# ── MAIL (READ-ONLY) ─────────────────────────────────────────
def _dec(s):
    """Mail-Header dekodieren (=?utf-8?...)."""
    if not s:
        return ""
    parts = decode_header(s)
    out = ""
    for txt, enc in parts:
        if isinstance(txt, bytes):
            try:
                out += txt.decode(enc or "utf-8", errors="replace")
            except Exception:
                out += txt.decode("utf-8", errors="replace")
        else:
            out += txt
    return out.strip()


def _imap_connect(account: str, mailbox: str = "INBOX"):
    acc = MAIL_ACCOUNTS.get(account)
    if not acc:
        return None, f"Unbekanntes Konto '{account}'. Verfuegbar: ionos, gmail."
    if not acc["user"] or not acc["pass"]:
        return None, f"Konto '{account}' ist nicht konfiguriert (MAIL_{account.upper()}_USER/_PASS in .env fehlen)."
    try:
        M = imaplib.IMAP4_SSL(acc["host"], 993)
        M.login(acc["user"], acc["pass"])
        if mailbox == "SENT":
            mailbox = _find_sent_folder(M)
            if not mailbox:
                try:
                    M.logout()
                except Exception:
                    pass
                return None, f"Gesendet-Ordner bei {acc['label']} nicht gefunden."
        ok, _ = M.select(f'"{mailbox}"', readonly=True)   # readonly: doppelte Absicherung
        if ok != "OK":
            return None, f"Ordner '{mailbox}' liess sich nicht oeffnen ({acc['label']})."
        return M, None
    except Exception as e:
        return None, f"IMAP-Fehler ({acc['label']}): {e}"


def _find_sent_folder(M) -> str:
    """Findet den Gesendet-Ordner: erst per \\Sent-Flag, dann ueber bekannte Namen."""
    try:
        ok, boxes = M.list()
        if ok == "OK":
            for raw in boxes:
                line = raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw)
                if "\\Sent" in line:
                    return line.rsplit('"', 2)[-2] if '"' in line else line.split()[-1]
    except Exception:
        pass
    for name in ("[Gmail]/Gesendet", "[Gmail]/Sent Mail", "Gesendete Objekte", "Sent", "Sent Items", "INBOX.Sent"):
        try:
            ok, _ = M.select(f'"{name}"', readonly=True)
            if ok == "OK":
                return name
        except Exception:
            continue
    return ""


def _extract_body(msg) -> str:
    """Textkoerper einer Mail extrahieren (plain bevorzugt, HTML gestrippt)."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                    break
        if not body:
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload:
                        html = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                        body = re.sub(r"<[^>]+>", " ", html)
                        body = re.sub(r"\s+", " ", body)
                        break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            raw = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
            if msg.get_content_type() == "text/html":
                raw = re.sub(r"<[^>]+>", " ", raw)
                raw = re.sub(r"\s+", " ", raw)
            body = raw
    return (body or "").strip()


def tool_check_mail(inp: dict) -> str:
    account = (inp.get("account") or "").strip().lower()
    limit = min(int(inp.get("limit") or 10), 25)
    unread_only = inp.get("unread_only", True)
    M, err = _imap_connect(account)
    if err:
        return err
    try:
        crit = "UNSEEN" if unread_only else "ALL"
        ok, data = M.uid("search", None, crit)
        if ok != "OK":
            return "Suche fehlgeschlagen."
        uids = data[0].split()
        total = len(uids)
        uids = uids[-limit:][::-1]  # neueste zuerst
        if not uids:
            return f"Keine {'ungelesenen ' if unread_only else ''}Mails im Posteingang ({MAIL_ACCOUNTS[account]['label']})."
        lines = [f"{MAIL_ACCOUNTS[account]['label']} — {total} {'ungelesen' if unread_only else 'gesamt'}, zeige {len(uids)}:"]
        for uid in uids:
            ok, msg_data = M.uid("fetch", uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if ok != "OK" or not msg_data or msg_data[0] is None:
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            frm = _dec(msg.get("From"))[:60]
            sub = _dec(msg.get("Subject"))[:80] or "(kein Betreff)"
            dat = _dec(msg.get("Date"))[:31]
            lines.append(f"[uid {uid.decode()}] {dat} | {frm} | {sub}")
        return "\n".join(lines)
    except Exception as e:
        return f"Fehler beim Abrufen: {e}"
    finally:
        try:
            M.logout()
        except Exception:
            pass


def tool_read_mail(inp: dict) -> str:
    account = (inp.get("account") or "").strip().lower()
    uid = (inp.get("uid") or "").strip()
    if not uid:
        return "Fehler: uid fehlt."
    M, err = _imap_connect(account)
    if err:
        return err
    try:
        ok, msg_data = M.uid("fetch", uid.encode(), "(BODY.PEEK[])")
        if ok != "OK" or not msg_data or msg_data[0] is None:
            return f"Mail uid {uid} nicht gefunden."
        msg = email.message_from_bytes(msg_data[0][1])
        frm = _dec(msg.get("From"))
        sub = _dec(msg.get("Subject"))
        dat = _dec(msg.get("Date"))
        body = (_extract_body(msg) or "(kein Textinhalt)")[:4000]
        return f"Von: {frm}\nDatum: {dat}\nBetreff: {sub}\n\n{body}"
    except Exception as e:
        return f"Fehler beim Lesen: {e}"
    finally:
        try:
            M.logout()
        except Exception:
            pass

# ── KOSTEN ───────────────────────────────────────────────────
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
                    "VALUES ('jarvis', %s, %s, %s, %s)",
                    (model, tok_in, tok_out, round(cost, 6)))
            conn.close()
        except Exception as e:
            print(f"  [cost] {e}", flush=True)
    threading.Thread(target=_work, daemon=True).start()


# ── EMBEDDINGS + GEDAECHTNIS ─────────────────────────────────
oai = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None


def embed(text: str):
    """Text -> 1536er Vektor. None wenn kein OpenAI-Key."""
    if oai is None:
        return None
    try:
        resp = oai.embeddings.create(model=EMBED_MODEL, input=text[:8000])
        return resp.data[0].embedding
    except Exception as e:
        print(f"  [embed] {e}", flush=True)
        return None


def vec_literal(v) -> str:
    return "[" + ",".join(f"{x:.7f}" for x in v) + "]"


def tool_remember(inp: dict) -> str:
    content = inp.get("content", "").strip()
    project = inp.get("project", "sonstiges").strip().lower()
    title   = inp.get("title", "").strip()
    if not content:
        return "Fehler: leerer Inhalt."
    v = embed(f"{title}\n{content}")
    try:
        conn = pg_conn()
        with conn, conn.cursor() as cur:
            if v is not None:
                cur.execute(
                    "INSERT INTO memory (source, project, title, content, embedding) "
                    "VALUES ('jarvis', %s, %s, %s, %s::vector) RETURNING id",
                    (project, title, content, vec_literal(v)))
            else:
                cur.execute(
                    "INSERT INTO memory (source, project, title, content) "
                    "VALUES ('jarvis', %s, %s, %s) RETURNING id",
                    (project, title, content))
            mid = cur.fetchone()[0]
        conn.close()
        return f"Gespeichert (#{mid}, {project}): {title}"
    except Exception as e:
        return f"Fehler beim Speichern: {e}"


def tool_recall(inp: dict, k: int = 5) -> str:
    query   = inp.get("query", "").strip()
    project = (inp.get("project") or "").strip().lower()
    if not query:
        return "Fehler: leere Suchanfrage."
    v = embed(query)
    try:
        conn = pg_conn()
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if v is not None:
                sql = ("SELECT id, project, title, content, created_at, "
                       "embedding <=> %s::vector AS dist FROM memory "
                       "WHERE embedding IS NOT NULL ")
                params = [vec_literal(v)]
                if project:
                    sql += "AND project = %s "
                    params.append(project)
                sql += "ORDER BY dist ASC LIMIT %s"
                params.append(k)
                cur.execute(sql, params)
            else:
                sql = "SELECT id, project, title, content, created_at, 0 AS dist FROM memory "
                params = []
                if project:
                    sql += "WHERE project = %s "
                    params.append(project)
                sql += "ORDER BY created_at DESC LIMIT %s"
                params.append(k)
                cur.execute(sql, params)
            rows = cur.fetchall()
        conn.close()
        if not rows:
            return "Keine Treffer im Gedaechtnis."
        out = []
        for r_ in rows:
            d = r_["created_at"].strftime("%d.%m.%Y")
            out.append(f"[#{r_['id']} | {r_['project']} | {d}] {r_['title']}: {r_['content']}")
        return "\n".join(out)
    except Exception as e:
        return f"Fehler bei der Suche: {e}"


def tool_vault_note(inp: dict) -> str:
    folder  = inp.get("folder", "inbox").strip().lower()
    if folder not in ("daily", "notes", "projects", "inbox", "skills"):
        folder = "inbox"
    title   = inp.get("title", "notiz").strip()
    content = inp.get("content", "").strip()
    if not content:
        return "Fehler: leerer Inhalt."
    safe = re.sub(r"[^a-zA-Z0-9aeoeueAeOeUess_\-]", "-", title.replace(" ", "-"))[:60].strip("-") or "notiz"
    fname = f"{datetime.now().strftime('%Y-%m-%d')}_{safe}.md"
    path = os.path.join(VAULT_DIR, folder, fname)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n{content}\n\n---\n*JARVIS, {datetime.now().strftime('%d.%m.%Y %H:%M')}*\n")
        return f"Notiz abgelegt: vault/{folder}/{fname}"
    except Exception as e:
        return f"Fehler beim Schreiben: {e}"



# ── WEB-ZUGRIFF (camofox, anti-detect Browser) ───────────────
CAMOFOX_URL = os.getenv("CAMOFOX_URL", "http://camofox:9377")


# ── iCLOUD-KALENDER (CalDAV, strikt read-only) ───────────────
def tool_check_calendar(inp):
    if not ICLOUD_USER or not ICLOUD_PASS:
        return "iCloud nicht konfiguriert — ICLOUD_USER/ICLOUD_PASS in .env fehlen."
    days = min(max(int(inp.get("days") or 7), 1), 30)
    try:
        import caldav
        from datetime import timedelta, date as _date
        client = caldav.DAVClient(url="https://caldav.icloud.com/",
                                  username=ICLOUD_USER, password=ICLOUD_PASS)
        principal = client.principal()
        cals = principal.calendars()
        start = datetime.now()
        end = start + timedelta(days=days)
        events = []
        for cal in cals:
            try:
                name = cal.name or "Kalender"
            except Exception:
                name = "Kalender"
            try:
                found = cal.search(start=start, end=end, event=True, expand=True)
            except Exception:
                try:
                    found = cal.date_search(start, end)
                except Exception:
                    continue
            for ev in found:
                try:
                    comp = ev.icalendar_component
                    summ = str(comp.get("summary", "(ohne Titel)"))
                    dt = comp.get("dtstart").dt
                    if isinstance(dt, datetime):
                        key = dt.replace(tzinfo=None) if dt.tzinfo else dt
                        label = dt.strftime("%a %d.%m. %H:%M")
                        dte = comp.get("dtend")
                        if dte is not None and isinstance(dte.dt, datetime):
                            label += dte.dt.strftime("-%H:%M")
                    else:
                        key = datetime.combine(dt, datetime.min.time())
                        label = dt.strftime("%a %d.%m.") + " ganztaegig"
                    events.append((key, f"{label} | {summ} ({name})"))
                except Exception:
                    continue
        if not events:
            return f"Keine Termine in den naechsten {days} Tagen."
        events.sort(key=lambda x: x[0])
        lines = [e[1] for e in events[:40]]
        return f"Termine der naechsten {days} Tage:\n" + "\n".join(lines)
    except Exception as e:
        return f"Kalender-Fehler: {type(e).__name__}: {e}"


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


def tool_web_search(inp: dict) -> str:
    q = (inp.get("query") or "").strip()
    if not q:
        return "Fehler: leere Suche."
    return _camofox_open("@google_search " + q, BOT_USER_ID)


def tool_web_open(inp: dict) -> str:
    url = (inp.get("url") or "").strip()
    if not url:
        return "Fehler: leere URL."
    return _camofox_open(url, BOT_USER_ID)


def tool_web_click(inp: dict) -> str:
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


def tool_ask_immo(inp):
    task = (inp.get("task") or "").strip()
    if not task:
        return "Fehler: leerer Auftrag."
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        req_id = str(uuid.uuid4())
        r.rpush("bot:immo:inbox", json.dumps({"id": req_id, "text": task}, ensure_ascii=False))
        resp = r.blpop(f"bot:immo:reply:{req_id}", timeout=280)
        if resp is None:
            return "Immo-Bot antwortet nicht (Timeout) — laeuft der Container?"
        return f"IMMO-BOT:\n{resp[1]}"
    except Exception as e:
        return f"Fehler: {type(e).__name__}: {e}"


def tool_ask_ceo(inp: dict) -> str:
    task = (inp.get("task") or "").strip()
    if not task:
        return "Fehler: leerer Auftrag."
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        req_id = str(uuid.uuid4())
        r.rpush("bot:ceo:inbox", json.dumps({"id": req_id, "text": task}, ensure_ascii=False))
        resp = r.blpop(f"bot:ceo:reply:{req_id}", timeout=150)
        if resp is None:
            return "CEO antwortet nicht (Timeout) — laeuft der jarvis-ceo Container?"
        return f"CEO-Antwort:\n{resp[1]}"
    except Exception as e:
        return f"Fehler bei der Delegation: {e}"


def run_tool(name: str, inp: dict) -> str:
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
    if name == "ask_ceo":
        return tool_ask_ceo(inp)
    if name == "web_search":
        return tool_web_search(inp)
    if name == "web_open":
        return tool_web_open(inp)
    if name == "web_click":
        return tool_web_click(inp)
    if name == "check_calendar":
        return tool_check_calendar(inp)
    if name == "ask_immo":
        return tool_ask_immo(inp)
    return f"Unbekanntes Tool: {name}"


# ── STIL-ANALYSE (aus gesendeten Mails) ──────────────────────
STYLE_PROMPT = """Du bekommst von Rui selbst geschriebene, gesendete E-Mails.
Erstelle ein kompaktes SCHREIBSTIL-PROFIL, damit eine KI kuenftig Texte in exakt seinem Stil entwerfen kann.

Analysiere: Tonalitaet (formell/locker), Anrede und Grussformeln (Du/Sie, typische Floskeln),
Satzlaenge und -bau, Wortwahl und typische Formulierungen, Emojis/Sonderzeichen,
Struktur (Absaetze, Listen), Unterschiede je Empfaengertyp falls erkennbar.

Antworte NUR mit dem Profil als kompakter Fliesstext mit kurzen Stichpunkten, max 300 Woerter.
Zitiere 3-5 typische Original-Formulierungen als Beispiele."""


def _strip_quotes_sig(body: str) -> str:
    """Zitierte Zeilen, Weiterleitungs-Header und Signatur entfernen."""
    lines = []
    for ln in body.splitlines():
        s = ln.strip()
        if s.startswith(">"):
            continue
        if re.match(r"^(Am .{5,60} schrieb|On .{5,60} wrote|Von: |From: |-{2,}\s*Original|_{5,})", s):
            break
        if s == "--":
            break
        lines.append(ln)
    return "\n".join(lines).strip()


def analyze_style(account: str, limit: int = 30) -> str:
    """Liest gesendete Mails, erstellt Stilprofil, speichert es in Gedaechtnis + Vault."""
    M, err = _imap_connect(account, mailbox="SENT")
    if err:
        return err
    samples = []
    try:
        ok, data = M.uid("search", None, "ALL")
        if ok != "OK":
            return "Suche im Gesendet-Ordner fehlgeschlagen."
        uids = data[0].split()[-limit:][::-1]
        if not uids:
            return f"Keine gesendeten Mails bei '{account}' gefunden."
        for uid in uids:
            ok, msg_data = M.uid("fetch", uid, "(BODY.PEEK[])")
            if ok != "OK" or not msg_data or msg_data[0] is None:
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            body = _strip_quotes_sig(_extract_body(msg))
            if len(body) < 40:          # leere/auto-Mails ueberspringen
                continue
            sub = _dec(msg.get("Subject"))[:60]
            samples.append(f"--- Betreff: {sub} ---\n{body[:1500]}")
            if sum(len(s) for s in samples) > 24000:
                break
    except Exception as e:
        return f"Fehler beim Lesen der gesendeten Mails: {e}"
    finally:
        try:
            M.logout()
        except Exception:
            pass

    if not samples:
        return f"Keine brauchbaren Text-Mails im Gesendet-Ordner von '{account}'."

    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=1500, system=STYLE_PROMPT,
            messages=[{"role": "user", "content": "\n\n".join(samples)}])
        track_cost(MODEL, resp.usage.input_tokens, resp.usage.output_tokens, getattr(resp.usage, 'cache_read_input_tokens', 0) or 0, getattr(resp.usage, 'cache_creation_input_tokens', 0) or 0)
        profile = "".join(b.text for b in resp.content if b.type == "text").strip()
    except Exception as e:
        return f"Fehler bei der Stil-Analyse: {e}"

    label = "buroflow" if account == "ionos" else "privat"
    tool_remember({
        "content": f"SCHREIBSTIL-PROFIL ({label}, aus {len(samples)} gesendeten Mails): {profile}",
        "project": label,
        "title": f"Schreibstil {label}",
    })
    tool_vault_note({
        "folder": "skills",
        "title": f"Stilprofil {label}",
        "content": f"Basis: {len(samples)} gesendete Mails ({account}).\n\n{profile}",
    })
    return f"Stilprofil '{label}' erstellt aus {len(samples)} Mails und gespeichert.\n\n{profile}"


# ── TAGES-LOG + NIGHTLY-KONSOLIDIERUNG ───────────────────────
EXTRACT_MODEL = os.getenv("BOT_MODEL", "claude-haiku-4-5-20251001")

EXTRACT_PROMPT = """Du bekommst den Gespraechsmitschnitt eines Tages zwischen Rui und JARVIS.
Extrahiere NUR dauerhaft merkwuerdige Fakten ueber Rui und seine Projekte:
Entscheidungen, Zahlen, Deadlines, Projektstaende, Vorlieben, wichtige Ereignisse.
KEIN Smalltalk, KEINE Fragen, KEINE technischen Zwischenschritte, nichts Redundantes.

Antworte NUR mit einem JSON-Array, ohne Markdown, ohne Erklaerung:
[{"content": "praeziser Fakt", "project": "elements|buroflow|immo|frozen|stille|jarvis|privat|sonstiges", "title": "3-6 Woerter"}]

Wenn nichts Merkwuerdiges dabei ist: []"""


def log_exchange(r, user_text, answer):
    """Schneidet jeden Austausch ins Tages-Log mit (7 Tage TTL)."""
    try:
        key = DAYLOG_KEY.format(date=datetime.now().strftime("%Y-%m-%d"))
        r.rpush(key, json.dumps({"t": datetime.now().strftime("%H:%M"),
                                 "du": user_text, "jarvis": answer}, ensure_ascii=False))
        r.expire(key, 7 * 24 * 3600)
    except Exception as e:
        print(f"  [daylog] {e}", flush=True)


def memory_is_duplicate(v) -> bool:
    """True, wenn ein sehr aehnlicher Eintrag schon existiert."""
    if v is None:
        return False
    try:
        conn = pg_conn()
        with conn, conn.cursor() as cur:
            cur.execute(
                "SELECT embedding <=> %s::vector AS dist FROM memory "
                "WHERE embedding IS NOT NULL ORDER BY dist ASC LIMIT 1",
                (vec_literal(v),))
            row = cur.fetchone()
        conn.close()
        return row is not None and row[0] < DEDUP_DIST
    except Exception as e:
        print(f"  [dedup] {e}", flush=True)
        return False


def consolidate(r, date_str=None) -> str:
    """Extrahiert Fakten aus dem Tages-Log und speichert Neues ins Gedaechtnis."""
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    key = DAYLOG_KEY.format(date=date_str)
    try:
        raw_items = r.lrange(key, 0, -1)
    except Exception as e:
        return f"Fehler beim Lesen des Tages-Logs: {e}"
    if not raw_items:
        return f"Kein Tages-Log fuer {date_str} — nichts zu konsolidieren."

    lines = []
    for raw in raw_items:
        try:
            d = json.loads(raw)
            lines.append(f"[{d.get('t','')}] Rui: {d.get('du','')}")
            lines.append(f"[{d.get('t','')}] JARVIS: {d.get('jarvis','')}")
        except Exception:
            continue
    transcript = "\n".join(lines)[-30000:]

    try:
        resp = client.messages.create(
            model=EXTRACT_MODEL, max_tokens=2000, system=EXTRACT_PROMPT,
            messages=[{"role": "user", "content": transcript}])
        track_cost(EXTRACT_MODEL, resp.usage.input_tokens, resp.usage.output_tokens)
        text = "".join(b.text for b in resp.content if b.type == "text")
        text = re.sub(r"```json|```", "", text).strip()
        facts = json.loads(text)
        if not isinstance(facts, list):
            facts = []
    except Exception as e:
        return f"Fehler bei der Extraktion: {e}"

    saved, skipped = [], 0
    for f_ in facts[:20]:
        content = (f_.get("content") or "").strip()
        if not content:
            continue
        v = embed(f"{f_.get('title','')}\n{content}")
        if memory_is_duplicate(v):
            skipped += 1
            continue
        res = tool_remember({"content": content,
                             "project": f_.get("project", "sonstiges"),
                             "title": f_.get("title", content[:40])})
        if res.startswith("Gespeichert"):
            saved.append(f_.get("title", content[:40]))

    if saved:
        tool_vault_note({
            "folder": "daily",
            "title": f"Konsolidierung {date_str}",
            "content": "Neu gemerkt:\n" + "\n".join(f"- {t}" for t in saved) +
                       (f"\n\nUebersprungen (schon bekannt): {skipped}" if skipped else ""),
        })
    summary = f"Konsolidierung {date_str}: {len(saved)} neu gespeichert, {skipped} Duplikate uebersprungen."
    print(f"  [nightly] {summary}", flush=True)
    return summary


def nightly_thread(r):
    """Laeuft im Hintergrund, stoesst die Konsolidierung taeglich um NIGHTLY_HOUR an."""
    while True:
        try:
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            last = r.get(NIGHTLY_MARK)
            if now.hour >= NIGHTLY_HOUR and last != today:
                from datetime import timedelta
                yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
                consolidate(r, yesterday)
                r.set(NIGHTLY_MARK, today)
        except Exception as e:
            print(f"  [nightly] {e}", flush=True)
        time.sleep(60)


# ── GEDAECHTNIS-VERWALTUNG (Redis Kurzzeitgedaechtnis) ───────
def load_history(r):
    try:
        raw = r.get(HISTORY_KEY)
        return json.loads(raw) if raw else []
    except Exception:
        return []


def save_history(r, history):
    try:
        r.set(HISTORY_KEY, json.dumps(history[-MAX_HISTORY:], ensure_ascii=False))
    except Exception as e:
        print(f"  [history] {e}", flush=True)


# ── CLAUDE MIT TOOL-LOOP ─────────────────────────────────────
client = Anthropic(api_key=CLAUDE_KEY)

# Prompt-Caching: System-Prompt + Tools werden serverseitig gecacht (90% billiger ab 2. Aufruf)
import copy as _copy
SYS_CACHED = [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}]
TOOLS_CACHED = _copy.deepcopy(TOOLS)
if TOOLS_CACHED:
    TOOLS_CACHED[-1]["cache_control"] = {"type": "ephemeral"}


def think(history, user_text):
    """Agent-Loop wie im lokalen v5: Claude darf Tools nutzen, bis end_turn."""
    # AUTO-RECALL: relevantes Langzeitwissen als Kontext mitgeben
    context = ""
    if oai is not None:
        hits = tool_recall({"query": user_text}, k=3)
        if hits and not hits.startswith("Keine Treffer") and not hits.startswith("Fehler"):
            context = f"\n\n[AUTO-RECALL — relevantes Langzeitgedaechtnis:\n{hits}]"

    history.append({"role": "user", "content": user_text})
    messages = list(history)
    if context:
        messages[-1] = {"role": "user", "content": user_text + context}

    final_text = ""
    for _round in range(MAX_TOOL_ROUNDS):
        resp = client.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS, system=SYS_CACHED,
            tools=TOOLS_CACHED, messages=messages,
        )
        try:
            track_cost(MODEL, resp.usage.input_tokens, resp.usage.output_tokens, getattr(resp.usage, 'cache_read_input_tokens', 0) or 0, getattr(resp.usage, 'cache_creation_input_tokens', 0) or 0)
        except Exception:
            pass

        text_parts = [b.text for b in resp.content if b.type == "text"]
        if text_parts:
            final_text = "".join(text_parts).strip()

        if resp.stop_reason != "tool_use":
            break

        # Tool-Aufrufe ausfuehren
        assistant_content = []
        tool_results = []
        for block in resp.content:
            if block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_content.append({
                    "type": "tool_use", "id": block.id,
                    "name": block.name, "input": block.input,
                })
                result = run_tool(block.name, block.input or {})
                print(f"  [tool] {block.name} -> {result[:100]}", flush=True)
                tool_results.append({
                    "type": "tool_result", "tool_use_id": block.id,
                    "content": result,
                })
        messages.append({"role": "assistant", "content": assistant_content})
        messages.append({"role": "user", "content": tool_results})

    if not final_text:
        final_text = "..."
    # Ins Kurzzeitgedaechtnis nur die saubere Antwort (ohne Tool-Zwischenschritte)
    history.append({"role": "assistant", "content": final_text})
    return final_text


# ── HAUPTSCHLEIFE ────────────────────────────────────────────
def main():
    print("=" * 58, flush=True)
    print("  JARVIS CORE v6 — GEDAECHTNIS + NIGHTLY + MAIL + STIL + CEO", flush=True)
    print(f"  Modell    : {MODEL}", flush=True)
    print(f"  Extraktion: {EXTRACT_MODEL}", flush=True)
    print(f"  Embeddings: {EMBED_MODEL if oai else 'DEAKTIVIERT (kein Key)'}", flush=True)
    print(f"  Nightly   : taeglich {NIGHTLY_HOUR:02d}:00", flush=True)
    print(f"  Kalender  : {'aktiv' if (ICLOUD_USER and ICLOUD_PASS) else 'nicht konfiguriert'}", flush=True)
    for k, acc in MAIL_ACCOUNTS.items():
        status = "aktiv" if (acc["user"] and acc["pass"]) else "nicht konfiguriert"
        print(f"  Mail {k:<6}: {status}", flush=True)
    print("=" * 58, flush=True)

    r = None
    for attempt in range(30):
        try:
            r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
            r.ping()
            print("  [redis] verbunden", flush=True)
            break
        except Exception:
            print(f"  [redis] warte... ({attempt+1}/30)", flush=True)
            time.sleep(2)
    if r is None:
        sys.exit(1)

    threading.Thread(target=nightly_thread, args=(r,), daemon=True).start()
    print("  JARVIS laeuft. Warte auf Anfragen ueber den Bus.\n", flush=True)

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
            text   = (msg.get("text") or "").strip()
            reply_q = REPLY_KEY.format(id=req_id)

            if not text:
                r.rpush(reply_q, "Leere Anfrage.")
                r.expire(reply_q, 120)
                continue

            low = text.lower()
            if low in ("reset", "vergiss alles", "speicher leeren"):
                r.delete(HISTORY_KEY)
                r.rpush(reply_q, "Kurzzeitgedaechtnis geleert. (Langzeitgedaechtnis bleibt.)")
                r.expire(reply_q, 120)
                continue

            if low in ("konsolidiere", "konsolidieren", "nightly"):
                result = consolidate(r)
                r.rpush(reply_q, result)
                r.expire(reply_q, 120)
                continue

            if low.startswith("stil "):
                acct = low.split(None, 1)[1].strip()
                r.rpush(reply_q, analyze_style(acct))
                r.expire(reply_q, 120)
                continue

            print(f"  Du: {text}", flush=True)
            history = load_history(r)
            try:
                answer = think(history, text)
            except Exception as e:
                answer = f"Fehler beim Denken: {type(e).__name__}: {e}"
                print(f"  [think] {answer}", flush=True)
            save_history(r, history)
            log_exchange(r, text, answer)
            print(f"  JARVIS: {answer}\n", flush=True)

            r.rpush(reply_q, answer)
            r.expire(reply_q, 120)

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"  [loop] {type(e).__name__}: {e}", flush=True)
            time.sleep(1)


if __name__ == "__main__":
    main()
