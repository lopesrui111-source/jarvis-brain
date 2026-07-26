#!/usr/bin/env python3
"""
IMMO-BOT — Arbeiter direkt unter JARVIS
- Queue: bot:immo:inbox / bot:immo:reply:<id>
- Bewertet Immobilien-Angebote nach Ruis Kriterien:
  Bruttorendite >= 4%, Finanzierung 5,5% Zins, NK 11% (BW),
  Szenario A (NK aus EK) + Szenario B (Vollfinanzierung)
- Quellen: URL-Analyse via camofox, ImmoScout-Mails via Gmail-IMAP,
  Kleinanzeigen-Suchen via camofox (IMMO_SEARCH_URLS)
- Telegram-Benachrichtigung bei qualifizierenden Angeboten
- Dedup ueber Postgres (immo_seen), gemeinsames Gedaechtnis (project: immo)
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

BOT_NAME = "immo"

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
FAST_MODEL  = os.getenv("BOT_MODEL", "claude-haiku-4-5-20251001")
EMBED_MODEL = "text-embedding-3-small"
MAX_HISTORY = 10
MAX_TOKENS  = 2000
MAX_TOOL_ROUNDS = 10

CAMOFOX_URL = os.getenv("CAMOFOX_URL", "http://camofox:9377")

# Investitions-Parameter (Ruis Kriterien, per .env anpassbar)
MIN_RENDITE = float(os.getenv("IMMO_MIN_RENDITE", "4.0"))
ZINS        = float(os.getenv("IMMO_ZINS", "5.5"))
NK_PROZENT  = float(os.getenv("IMMO_NK_PROZENT", "11.0"))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")

SEARCH_URLS = [u.strip() for u in os.getenv("IMMO_SEARCH_URLS", "").split(",") if u.strip()]
AUTO_INTERVAL_MIN = int(os.getenv("IMMO_INTERVAL_MIN", "0"))   # 0 = kein Auto-Scan

MAIL_HOST = os.getenv("MAIL_GMAIL_HOST", "imap.gmail.com")
MAIL_USER = os.getenv("MAIL_GMAIL_USER", "")
MAIL_PASS = os.getenv("MAIL_GMAIL_PASS", "")

INBOX_KEY   = "bot:immo:inbox"
HISTORY_KEY = "bot:immo:history"
REPLY_KEY   = "bot:immo:reply:{id}"

if not CLAUDE_KEY:
    print("FEHLER: ANTHROPIC_API_KEY fehlt", flush=True)
    sys.exit(1)


def pg_conn():
    return psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER,
                            password=PG_PASS, dbname=PG_DB, connect_timeout=5)


def init_db():
    try:
        conn = pg_conn()
        with conn, conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS immo_seen (
                id SERIAL PRIMARY KEY,
                url TEXT UNIQUE,
                titel TEXT,
                rendite NUMERIC,
                qualifiziert BOOLEAN,
                created_at TIMESTAMPTZ DEFAULT now())""")
        conn.close()
        print("  [db] immo_seen bereit", flush=True)
    except Exception as e:
        print(f"  [db] {e}", flush=True)


def already_seen(url):
    try:
        conn = pg_conn()
        with conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM immo_seen WHERE url = %s", (url,))
            row = cur.fetchone()
        conn.close()
        return row is not None
    except Exception:
        return False


def mark_seen(url, titel, rendite, qualifiziert):
    try:
        conn = pg_conn()
        with conn, conn.cursor() as cur:
            cur.execute("INSERT INTO immo_seen (url, titel, rendite, qualifiziert) "
                        "VALUES (%s, %s, %s, %s) ON CONFLICT (url) DO NOTHING",
                        (url, titel[:200], rendite, qualifiziert))
        conn.close()
    except Exception as e:
        print(f"  [seen] {e}", flush=True)


PRICING = {
    "claude-haiku-4-5-20251001": {"in": 1.00, "out": 5.00},
    "claude-sonnet-4-6":         {"in": 3.00, "out": 15.00},
}
DEFAULT_PRICE = {"in": 3.00, "out": 15.00}


def track_cost(model, tok_in, tok_out, cache_read=0, cache_write=0):
    def _work():
        try:
            p = PRICING.get(model, DEFAULT_PRICE)
            cost = (tok_in * p["in"] + tok_out * p["out"]
                    + cache_read * p["in"] * 0.1 + cache_write * p["in"] * 1.25) / 1_000_000
            conn = pg_conn()
            with conn, conn.cursor() as cur:
                cur.execute("INSERT INTO cost_ledger (bot, model, tokens_in, tokens_out, cost_usd) "
                            "VALUES (%s, %s, %s, %s, %s)",
                            (BOT_NAME, model, tok_in, tok_out, round(cost, 6)))
            conn.close()
        except Exception as e:
            print(f"  [cost] {e}", flush=True)
    threading.Thread(target=_work, daemon=True).start()


oai = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None
client = Anthropic(api_key=CLAUDE_KEY)


def embed(text):
    if oai is None:
        return None
    try:
        return oai.embeddings.create(model=EMBED_MODEL, input=text[:8000]).data[0].embedding
    except Exception:
        return None


def vec_literal(v):
    return "[" + ",".join(f"{x:.7f}" for x in v) + "]"


def tool_remember(inp):
    content = (inp.get("content") or "").strip()
    title = (inp.get("title") or "").strip()
    if not content:
        return "Fehler: leerer Inhalt."
    v = embed(f"{title}\n{content}")
    try:
        conn = pg_conn()
        with conn, conn.cursor() as cur:
            if v is not None:
                cur.execute("INSERT INTO memory (source, project, title, content, embedding) "
                            "VALUES (%s, 'immo', %s, %s, %s::vector) RETURNING id",
                            (BOT_NAME, title, content, vec_literal(v)))
            else:
                cur.execute("INSERT INTO memory (source, project, title, content) "
                            "VALUES (%s, 'immo', %s, %s) RETURNING id",
                            (BOT_NAME, title, content))
            mid = cur.fetchone()[0]
        conn.close()
        return f"Gespeichert (#{mid}, immo): {title}"
    except Exception as e:
        return f"Fehler: {e}"


def tool_recall(inp, k=5):
    query = (inp.get("query") or "").strip()
    if not query:
        return "Fehler: leere Suche."
    v = embed(query)
    try:
        conn = pg_conn()
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if v is not None:
                cur.execute("SELECT id, project, title, content, created_at, "
                            "embedding <=> %s::vector AS dist FROM memory "
                            "WHERE embedding IS NOT NULL ORDER BY dist ASC LIMIT %s",
                            (vec_literal(v), k))
            else:
                cur.execute("SELECT id, project, title, content, created_at, 0 AS dist "
                            "FROM memory WHERE project='immo' ORDER BY created_at DESC LIMIT %s", (k,))
            rows = cur.fetchall()
        conn.close()
        if not rows:
            return "Keine Treffer."
        return "\n".join(f"[#{r['id']} | {r['project']} | {r['created_at'].strftime('%d.%m.%Y')}] "
                         f"{r['title']}: {r['content']}" for r in rows)
    except Exception as e:
        return f"Fehler: {e}"


# ── CAMOFOX (Seiten lesen) ───────────────────────────────────
def fetch_page(url):
    try:
        r = requests.post(f"{CAMOFOX_URL}/tabs",
                          json={"userId": "immo", "sessionKey": "main", "url": url}, timeout=60)
        if r.status_code >= 400:
            return None, f"Browser-Fehler ({r.status_code})"
        tab = r.json().get("tabId") or r.json().get("id")
        s = requests.get(f"{CAMOFOX_URL}/tabs/{tab}/snapshot", params={"userId": "immo"}, timeout=60)
        if s.status_code >= 400:
            return None, f"Snapshot-Fehler ({s.status_code})"
        return s.json().get("snapshot", "")[:9000], None
    except Exception as e:
        return None, f"Browser nicht erreichbar ({type(e).__name__})"


# ── ANALYSE (deterministische Rechnung, Haiku nur fuer Extraktion) ──
EXTRACT_SYS = """Du extrahierst Immobiliendaten aus einem Seiten-Snapshot und einer Mietspiegel-Recherche.
Antworte NUR mit JSON, keine Erklaerung:
{"titel":"...","ort":"...","kaufpreis":123000,"qm":75,"zimmer":3,"miete_qm":9.5,"miete_quelle":"kurz","vermietbar":true,"anmerkung":"1 Satz Einschaetzung (Zustand, Lage, Risiken)"}
kaufpreis in Euro (Zahl), qm (Zahl), miete_qm = realistische Kaltmiete Euro/m2 aus der Recherche (konservativ).
Wenn ein Wert fehlt: null. vermietbar=false nur bei Abrisskandidat/unbewohnbar."""


def calc_szenarien(kaufpreis, qm, miete_qm):
    kaltmiete = round(qm * miete_qm)
    jahresmiete = kaltmiete * 12
    rendite = round(jahresmiete / kaufpreis * 100, 2)
    nk = round(kaufpreis * NK_PROZENT / 100)
    rate_a = round(kaufpreis * ZINS / 100 / 12)
    gesamt_b = round(kaufpreis * (1 + NK_PROZENT / 100))
    rate_b = round(gesamt_b * ZINS / 100 / 12)
    return {
        "kaltmiete": kaltmiete, "rendite": rendite,
        "a": {"ek": nk, "summe": kaufpreis, "rate": rate_a, "cashflow": kaltmiete - rate_a},
        "b": {"ek": 0, "summe": gesamt_b, "rate": rate_b, "cashflow": kaltmiete - rate_b},
    }


def format_angebot(d, calc, url, plattform):
    q = calc["rendite"] >= MIN_RENDITE
    lines = [
        f"{'✅' if q else '❌'} 📍 {d.get('titel', '(ohne Titel)')} — 🏷️ {plattform}",
        f"💶 {d.get('kaufpreis', 0):,.0f} € | {d.get('qm', '?')} m² | {d.get('zimmer', '?')} Zi | {d.get('ort', '?')}".replace(",", "."),
        f"📊 Bruttorendite: {calc['rendite']:.1f} % (Miete ca. {d.get('miete_qm', 0):.2f} €/m² — {d.get('miete_quelle', '')})",
        f"🔗 {url}",
        f"💬 {d.get('anmerkung', '')}",
        "",
        "💰 Szenario A — NK aus Eigenkapital:",
        f"├ Eigenkapital: {calc['a']['ek']:,.0f} €".replace(",", "."),
        f"├ Finanzierung: {calc['a']['summe']:,.0f} €".replace(",", "."),
        f"├ Rate ({ZINS} %): {calc['a']['rate']:,.0f} €/Mo".replace(",", "."),
        f"└ Cashflow: {calc['a']['cashflow']:+,.0f} €/Mo".replace(",", "."),
        "",
        "💰 Szenario B — Vollfinanzierung:",
        f"├ Eigenkapital: 0 €",
        f"├ Finanzierung: {calc['b']['summe']:,.0f} €".replace(",", "."),
        f"├ Rate ({ZINS} %): {calc['b']['rate']:,.0f} €/Mo".replace(",", "."),
        f"└ Cashflow: {calc['b']['cashflow']:+,.0f} €/Mo".replace(",", "."),
    ]
    return "\n".join(lines)


def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return False
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      json={"chat_id": TELEGRAM_CHAT, "text": text}, timeout=20)
        return True
    except Exception as e:
        print(f"  [telegram] {e}", flush=True)
        return False


def analyze_listing(url, notify=True, force=False):
    """Komplette Bewertung eines Kleinanzeigen-Angebots nach Ruis Kriterien."""
    if "immobilienscout24" in url:
        return "ImmoScout-Angebote laufen ueber den Mail-Scan (scan_mails) — direkte Exposé-Links werden nicht aufgerufen."
    if not force and already_seen(url):
        return "Schon bekannt (bereits bewertet)."
    snap, err = fetch_page(url)
    if err:
        return err
    # Ort grob rausziehen fuer die Mietspiegel-Suche
    plattform = "ImmoScout24" if "immobilienscout24" in url else ("Kleinanzeigen" if "kleinanzeigen" in url else "Web")
    ort_guess = ""
    m = re.search(r"\b(\d{5})\s+([A-ZÄÖÜ][a-zäöüß\-]{3,25})", snap or "")
    if m:
        ort_guess = m.group(2)
    miet_snap = ""
    if ort_guess:
        ms, _ = fetch_page(f"https://www.google.com/search?q=Mietspiegel+{ort_guess}+{datetime.now().year}+Kaltmiete+pro+m2")
        miet_snap = (ms or "")[:3500]
    try:
        resp = client.messages.create(
            model=FAST_MODEL, max_tokens=600, system=EXTRACT_SYS,
            messages=[{"role": "user", "content":
                       f"ANGEBOT:\n{snap[:6000]}\n\nMIETSPIEGEL-RECHERCHE ({ort_guess}):\n{miet_snap}"}])
        track_cost(FAST_MODEL, resp.usage.input_tokens, resp.usage.output_tokens)
        raw = "".join(b.text for b in resp.content if b.type == "text")
        raw = re.sub(r"```json|```", "", raw).strip()
        d = json.loads(raw)
    except Exception as e:
        return f"Extraktion fehlgeschlagen: {type(e).__name__}: {e}"

    if not d.get("kaufpreis") or not d.get("qm") or not d.get("miete_qm"):
        mark_seen(url, d.get("titel") or url, 0, False)
        return f"Unvollstaendige Daten (Preis/qm/Miete fehlen) — nicht bewertbar.\nTitel: {d.get('titel')}"

    calc = calc_szenarien(float(d["kaufpreis"]), float(d["qm"]), float(d["miete_qm"]))
    qualifiziert = calc["rendite"] >= MIN_RENDITE and d.get("vermietbar", True)
    text = format_angebot(d, calc, url, plattform)
    mark_seen(url, d.get("titel") or url, calc["rendite"], qualifiziert)
    if qualifiziert and notify:
        send_telegram(text)
    return text + ("\n\n📲 Telegram gesendet." if qualifiziert and notify and TELEGRAM_TOKEN else "")


# ── SCAN-QUELLEN ─────────────────────────────────────────────
def _dec(s):
    if not s:
        return ""
    out = ""
    for txt, enc in decode_header(s):
        out += txt.decode(enc or "utf-8", errors="replace") if isinstance(txt, bytes) else txt
    return out.strip()


MAIL_EXTRACT_SYS = """Du extrahierst Immobilien-Angebote aus einer ImmoScout24-Benachrichtigungsmail.
Antworte NUR mit JSON:
{"angebote":[{"titel":"...","ort":"...","kaufpreis":123000,"qm":75,"zimmer":3,"url":"https://..."}]}
kaufpreis/qm als Zahlen. url = Expose-Link des Angebots. Fehlende Werte: null. Max 8 Angebote."""

MIETE_SYS = """Du liest eine Mietspiegel-Recherche und nennst die realistische Kaltmiete pro m2 (konservativ).
Antworte NUR mit JSON: {"miete_qm":9.5,"quelle":"kurz"}"""


def _miete_fuer_ort(ort, qm):
    snap, _ = fetch_page(f"https://www.google.com/search?q=Mietspiegel+{ort}+{datetime.now().year}+Kaltmiete+pro+m2")
    if not snap:
        return None, "keine Recherche moeglich"
    try:
        resp = client.messages.create(model=FAST_MODEL, max_tokens=150, system=MIETE_SYS,
                                      messages=[{"role": "user", "content": f"Ort: {ort}, Wohnung {qm} m2\n\n{snap[:3200]}"}])
        track_cost(FAST_MODEL, resp.usage.input_tokens, resp.usage.output_tokens)
        raw = re.sub(r"```json|```", "", "".join(b.text for b in resp.content if b.type == "text")).strip()
        d = json.loads(raw)
        return float(d.get("miete_qm") or 0) or None, d.get("quelle", "")
    except Exception:
        return None, "Recherche fehlgeschlagen"


def _fetch_mail_bodies(hours, limit):
    from datetime import timedelta
    since = (datetime.now() - timedelta(hours=hours)).strftime("%d-%b-%Y")
    bodies = []
    M = imaplib.IMAP4_SSL(MAIL_HOST, 993)
    M.login(MAIL_USER, MAIL_PASS)
    M.select("INBOX", readonly=True)
    ok, data = M.uid("search", None, f'(FROM "immobilienscout24" SINCE {since})')
    if ok != "OK":
        M.logout()
        return []
    uids = data[0].split()[-limit:]
    for uid in uids:
        ok, md = M.uid("fetch", uid, "(BODY.PEEK[])")
        if ok != "OK" or not md or md[0] is None:
            continue
        msg = email.message_from_bytes(md[0][1])
        body = ""
        for part in msg.walk():
            if part.get_content_type() in ("text/plain", "text/html"):
                p = part.get_payload(decode=True)
                if p:
                    body += p.decode(part.get_content_charset() or "utf-8", errors="replace")
    
        body = re.sub(r"<[^>]+>", " ", body)
        body = re.sub(r"\s+", " ", body)
        if body.strip():
            bodies.append(body[:7000])
    M.logout()
    return bodies


def _bewerte_mail_bodies(bodies):
    results, gefunden = [], 0
    for body in bodies:
        try:
            resp = client.messages.create(model=FAST_MODEL, max_tokens=800, system=MAIL_EXTRACT_SYS,
                                          messages=[{"role": "user", "content": body}])
            track_cost(FAST_MODEL, resp.usage.input_tokens, resp.usage.output_tokens)
            raw = re.sub(r"```json|```", "", "".join(b.text for b in resp.content if b.type == "text")).strip()
            angebote = json.loads(raw).get("angebote", [])
        except Exception as e:
            results.append(f"Mail-Extraktion fehlgeschlagen: {type(e).__name__}")
            continue
        for a in angebote:
            url = (a.get("url") or "").strip() or f"is24-mail:{a.get('titel','')[:60]}"
            if already_seen(url):
                continue
            gefunden += 1
            if not a.get("kaufpreis") or not a.get("qm") or not a.get("ort"):
                mark_seen(url, a.get("titel") or url, 0, False)
                results.append(f"❌ {a.get('titel', '?')} — unvollstaendige Daten in der Mail.")
                continue
            miete_qm, quelle = _miete_fuer_ort(a["ort"], a["qm"])
            if not miete_qm:
                mark_seen(url, a.get("titel") or url, 0, False)
                results.append(f"❌ {a.get('titel', '?')} ({a['ort']}) — Mietspiegel nicht ermittelbar.")
                continue
            d = {"titel": a.get("titel"), "ort": a.get("ort"), "kaufpreis": a["kaufpreis"],
                 "qm": a["qm"], "zimmer": a.get("zimmer"), "miete_qm": miete_qm,
                 "miete_quelle": quelle, "anmerkung": "Aus ImmoScout-Mail bewertet."}
            calc = calc_szenarien(float(a["kaufpreis"]), float(a["qm"]), miete_qm)
            qualifiziert = calc["rendite"] >= MIN_RENDITE
            text = format_angebot(d, calc, url if url.startswith("http") else "(Link in der Mail)", "ImmoScout24")
            mark_seen(url, a.get("titel") or url, calc["rendite"], qualifiziert)
            if qualifiziert:
                send_telegram(text)
            results.append(text)
            time.sleep(1)
    qual = sum(1 for r in results if r.startswith("✅"))
    summary = f"📬 Mail-Scan fertig: {len(bodies)} Mail(s), {gefunden} neue Angebote, {qual} qualifiziert."
    send_telegram(summary)
    if not results:
        return summary
    return summary + "\n\n" + "\n\n---\n\n".join(results)


def scan_immoscout_mails(hours=24, background=True):
    """Startet den Mail-Scan. background=True: sofortige Antwort, Ergebnis via Telegram."""
    if not MAIL_USER or not MAIL_PASS:
        return "Gmail nicht konfiguriert."
    try:
        bodies = _fetch_mail_bodies(hours, limit=10)
    except Exception as e:
        return f"IMAP-Fehler: {e}"
    if not bodies:
        return f"Keine ImmoScout-Mails in den letzten {hours} Stunden."
    if background:
        threading.Thread(target=_bewerte_mail_bodies, args=(bodies,), daemon=True).start()
        return (f"{len(bodies)} ImmoScout-Mail(s) aus den letzten {hours} Stunden gefunden. "
                f"Bewertung laeuft im Hintergrund — qualifizierte Angebote und die Zusammenfassung kommen per Telegram.")
    return _bewerte_mail_bodies(bodies)


def scan_kleinanzeigen(background=True):
    """Scannt die konfigurierten Kleinanzeigen-Suchen (IMMO_SEARCH_URLS)."""
    if not SEARCH_URLS:
        return "Keine Such-URLs konfiguriert (IMMO_SEARCH_URLS in .env)."
    if background:
        def _job():
            res = scan_kleinanzeigen(background=False)
            qual = res.count("✅")
            send_telegram(f"🔎 Kleinanzeigen-Scan fertig — {qual} qualifizierte Angebote." if "neue Angebote" in res
                          else "🔎 Kleinanzeigen-Scan fertig — nichts Neues.")
        threading.Thread(target=_job, daemon=True).start()
        return f"Scanne {len(SEARCH_URLS)} Kleinanzeigen-Suche(n) im Hintergrund — Ergebnis kommt per Telegram."
    results = []
    total_new = 0
    for surl in SEARCH_URLS[:4]:
        snap, err = fetch_page(surl)
        if err:
            results.append(f"{surl}: {err}")
            continue
        links = re.findall(r"https://www\.kleinanzeigen\.de/s-anzeige/[^\s\"'<>\)]+", snap or "")
        seen_links = []
        for u in links:
            u = u.rstrip('.,;')
            if u not in seen_links:
                seen_links.append(u)
        new = [u for u in seen_links[:10] if not already_seen(u)]
        total_new += len(new)
        for u in new[:4]:
            results.append(analyze_listing(u))
            time.sleep(2)
    if not results:
        return "Keine neuen Angebote in den Suchen."
    return f"{total_new} neue Angebote gefunden.\n\n" + "\n\n---\n\n".join(results)


# ── TOOLS ────────────────────────────────────────────────────
TOOLS = [
    {"name": "analyze_listing",
     "description": "Bewertet EIN Kleinanzeigen-Angebot (URL) komplett nach Ruis Kriterien: Daten-Extraktion, Mietspiegel-Recherche, Rendite, beide Finanzierungsszenarien. Bei Qualifikation (>= " + str(MIN_RENDITE) + "% Rendite) geht automatisch eine Telegram-Nachricht raus.",
     "input_schema": {"type": "object", "properties": {
         "url": {"type": "string"},
         "force": {"type": "boolean", "description": "true = auch bewerten wenn schon bekannt"}},
         "required": ["url"]}},
    {"name": "scan_mails",
     "description": "Bewertet ImmoScout24-Mails der letzten X Stunden (Standard 24) direkt aus dem Mail-Inhalt. Antwortet sofort; Ergebnisse und Zusammenfassung kommen per Telegram.",
     "input_schema": {"type": "object", "properties": {
         "hours": {"type": "integer", "description": "Zeitfenster in Stunden (Standard 24, max 168)"}}}},
    {"name": "scan_kleinanzeigen",
     "description": "Scannt die hinterlegten Kleinanzeigen-Suchauftraege und bewertet neue Angebote.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "remember",
     "description": "Speichert Immo-Erkenntnisse dauerhaft (project: immo).",
     "input_schema": {"type": "object", "properties": {
         "content": {"type": "string"}, "title": {"type": "string"}}, "required": ["content", "title"]}},
    {"name": "recall",
     "description": "Durchsucht das gemeinsame Gedaechtnis (fruehere Objekte, Entscheidungen, Kriterien).",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
]


def run_tool(name, inp):
    if name == "analyze_listing":
        return analyze_listing((inp.get("url") or "").strip(), force=bool(inp.get("force")))
    if name == "scan_mails":
        return scan_immoscout_mails(hours=min(int(inp.get("hours") or 24), 168))
    if name == "scan_kleinanzeigen":
        return scan_kleinanzeigen()
    if name == "remember":
        return tool_remember(inp)
    if name == "recall":
        return tool_recall(inp)
    return f"Unbekanntes Tool: {name}"


SYSTEM = f"""Du bist der IMMO-BOT — Ruis Immobilien-Investment-Analyst, direkt unter JARVIS.

RUIS KRITERIEN (fest):
- Buy-and-Hold ETWs, Ziel-Bruttorendite >= {MIN_RENDITE}% (besser 5%+)
- Finanzierung: {ZINS}% Zins, Nebenkosten {NK_PROZENT}% (GrESt BW 5%, Notar 1,5%, Makler 3,57% + Reserve)
- Immer BEIDE Szenarien: A = NK aus Eigenkapital, B = Vollfinanzierung
- Region: Rems-Murr-Kreis und Umgebung (BW), grundsaetzlich vermietbar, kein Abrisskandidat
- Bekannte Referenzen im Gedaechtnis: Pleidelsheim (Favorit ~5,1-5,3%), Bad Wimpfen (abgelehnt: Energieklasse F), Welzheim (alte Gasheizung, Bad ohne Fenster)

PERSOENLICHKEIT:
- Du duzt. Nuechtern, zahlengetrieben, ehrlich — du redest kein Objekt schoen.
- Rechne NIE selbst im Kopf: analyze_listing macht die Berechnung deterministisch.
- recall nutzen fuer fruehere Objekte/Entscheidungen; wichtige Bewertungen per remember sichern.

DEINE QUELLEN:
- ImmoScout24: NUR ueber scan_mails (Angebote werden aus den Benachrichtigungs-Mails bewertet, Exposé-Seiten werden nicht aufgerufen)
- Kleinanzeigen: analyze_listing (einzelne URL) oder scan_kleinanzeigen (gespeicherte Suchen)
- Du laeufst NUR auf Anfrage — kein automatisches Scannen.
DEINE TOOLS: analyze_listing, scan_mails, scan_kleinanzeigen, remember/recall.
Alles read-only — du kontaktierst keine Makler, gibst keine Gebote ab, klickst nichts an.
Telegram-Meldungen gehen nur an Rui selbst."""


import copy as _copy
SYS_CACHED = [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}]
TOOLS_CACHED = _copy.deepcopy(TOOLS)
TOOLS_CACHED[-1]["cache_control"] = {"type": "ephemeral"}


def load_history(r):
    try:
        raw = r.get(HISTORY_KEY)
        return (json.loads(raw)[-MAX_HISTORY:]) if raw else []
    except Exception:
        return []


def save_history(r, h):
    try:
        r.set(HISTORY_KEY, json.dumps(h[-MAX_HISTORY:], ensure_ascii=False))
    except Exception:
        pass



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
    # Sehr kurze Absichts-Saetze ohne jedes Ergebnis
    if len(t) <= 90 and INTENT_RE.match(t):
        return True
    return False


def think(history, user_text):
    history.append({"role": "user", "content": user_text})
    messages = list(history)
    final_text = ""
    tool_benutzt = False
    nachfass_zahl = 0
    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS,
                                      system=SYS_CACHED, tools=TOOLS_CACHED, messages=messages)
        try:
            track_cost(MODEL, resp.usage.input_tokens, resp.usage.output_tokens,
                       getattr(resp.usage, 'cache_read_input_tokens', 0) or 0,
                       getattr(resp.usage, 'cache_creation_input_tokens', 0) or 0)
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
                print(f"  [tool] {block.name} -> {str(result)[:90]}", flush=True)
                t_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
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


def auto_scan_thread():
    if AUTO_INTERVAL_MIN <= 0:
        return
    while True:
        time.sleep(AUTO_INTERVAL_MIN * 60)
        try:
            print("  [auto] Scan startet", flush=True)
            scan_immoscout_mails(background=False)
            scan_kleinanzeigen(background=False)
        except Exception as e:
            print(f"  [auto] {e}", flush=True)


def main():
    print("=" * 58, flush=True)
    print("  IMMO-BOT — Investment-Analyst unter JARVIS", flush=True)
    print(f"  Kriterien : >= {MIN_RENDITE}% Rendite | {ZINS}% Zins | NK {NK_PROZENT}%", flush=True)
    print(f"  Telegram  : {'aktiv' if (TELEGRAM_TOKEN and TELEGRAM_CHAT) else 'nicht konfiguriert'}", flush=True)
    print(f"  Suchen    : {len(SEARCH_URLS)} URLs | Auto-Scan: {'alle ' + str(AUTO_INTERVAL_MIN) + ' Min' if AUTO_INTERVAL_MIN else 'aus'}", flush=True)
    print("=" * 58, flush=True)
    init_db()

    r = None
    for _ in range(30):
        try:
            r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
            r.ping()
            print("  [redis] verbunden", flush=True)
            break
        except Exception:
            time.sleep(2)
    if r is None:
        sys.exit(1)
    threading.Thread(target=auto_scan_thread, daemon=True).start()
    print("  Immo-Bot bereit.\n", flush=True)

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
                r.rpush(reply_q, "Leere Anfrage.")
                r.expire(reply_q, 300)
                continue
            if text.lower() in ("reset", "vergiss alles"):
                r.delete(HISTORY_KEY)
                r.rpush(reply_q, "Immo-Kurzzeitgedaechtnis geleert.")
                r.expire(reply_q, 300)
                continue
            print(f"  Auftrag: {text[:80]}", flush=True)
            history = load_history(r)
            try:
                answer = think(history, text)
            except Exception as e:
                answer = f"Fehler: {type(e).__name__}: {e}"
            save_history(r, history)
            print(f"  Immo: {answer[:100]}\n", flush=True)
            r.rpush(reply_q, answer)
            r.expire(reply_q, 300)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"  [loop] {type(e).__name__}: {e}", flush=True)
            time.sleep(1)


if __name__ == "__main__":
    main()
