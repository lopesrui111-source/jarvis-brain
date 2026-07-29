#!/usr/bin/env python3
"""
SEO/Q&A-BOT — Arbeiter unter dem Bueroflow-CEO
- Queue: bot:seo:inbox / bot:seo:reply:<id>
- Recherchiert gutefrage.net + Quora via camofox (STRIKT read-only)
- Priorisiert frische Fragen mit 0 Antworten (bester Sichtbarkeits-Hebel)
- Schreibt Antwort-ENTWUERFE in Ruis echtem Stil (Stilprofil aus dem Gedaechtnis)
- Speichert Entwuerfe in vault/seo/, meldet per Telegram (Link + Text)
- Postet NICHTS und veraendert nichts auf den Seiten. Rui postet selbst.
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
import psycopg2
import psycopg2.extras
from anthropic import Anthropic
from protokoll import protokoll_init, protokoll_melden
from openai import OpenAI

BOT_NAME = "seo"
BOT_USER_ID = "seo"

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
MAX_TOKENS  = 2500
MAX_TOOL_ROUNDS = 12

CAMOFOX_URL = os.getenv("CAMOFOX_URL", "http://camofox:9377")
VAULT_DIR = "/app/vault"
VAULT_SUB = "seo"

DAILY_TIME = os.getenv("SEO_DAILY_TIME", "08:00").strip().split()[0] if os.getenv("SEO_DAILY_TIME", "08:00").strip() else ""
DAILY_ENTWUERFE = int(os.getenv("SEO_DAILY_ENTWUERFE", "3"))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")

INBOX_KEY   = "bot:seo:inbox"
HISTORY_KEY = "bot:seo:history"
REPLY_KEY   = "bot:seo:reply:{id}"

# ── Recherche-Quellen (aus Ruis Original-Workflow) ────────────
# WICHTIG: /home/... erfordert Login -> nur oeffentliche Pfade verwenden
# Alle Slugs am 28.07.2026 gegen gutefrage geprueft (Format: /tag/<slug>/1).
# "e-rechnung" existiert dort NICHT — genau das erzeugte frueher die 404-Fehler.
GF_TAGS = ["rechnung", "selbstaendigkeit", "steuererklaerung", "umsatzsteuer",
           "gewerbe", "steuerrecht", "freiberufler", "mahnung",
           "unternehmen", "kleinunternehmer", "finanzamt", "gruendung",
           "handwerk", "buchhaltung", "steuern", "selbststaendigkeit",
           "existenzgruendung"]
GF_KEYWORDS = ["E-Rechnung", "Rechnung schreiben", "Kleinunternehmer",
               "Angebot erstellen", "Mahnung"]
GF_NEUE = "https://www.gutefrage.net/fragen/neue"
# Wie viele Tag-Seiten pro Lauf durchgesehen werden (Default 8 von 17).
GF_TAG_ANZAHL = int(os.getenv("SEO_GF_TAGS", "8"))
# Zusaetzlich der allgemeine Fragen-Strom (wenig ergiebig, daher nur 1 Seite).
GF_SEITEN = int(os.getenv("SEO_GF_SEITEN", "1"))
# Suchseiten liefern 404 — nur zuschalten, falls gutefrage sie zurueckbringt.
GF_ALT_QUELLEN = os.getenv("SEO_ALT_QUELLEN", "0") == "1"

# Quora wird von Cloudflare geblockt -> standardmaessig aus
QUORA_AKTIV = os.getenv("SEO_QUORA", "0") == "1"
QUORA_KEYWORDS = ["Kleinunternehmer Rechnung", "E-Rechnung Pflicht",
                  "Rechnung schreiben Selbststaendige", "Mahnung schreiben"]

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
            cur.execute("""CREATE TABLE IF NOT EXISTS qa_seen (
                id SERIAL PRIMARY KEY,
                url TEXT UNIQUE,
                plattform TEXT,
                titel TEXT,
                antworten INT,
                entwurf_datei TEXT,
                erledigt BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT now())""")
        conn.close()
        print("  [db] qa_seen bereit", flush=True)
    except Exception as e:
        print(f"  [db] {e}", flush=True)


def already_seen(url):
    try:
        conn = pg_conn()
        with conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM qa_seen WHERE url = %s", (url,))
            row = cur.fetchone()
        conn.close()
        return row is not None
    except Exception:
        return False


def mark_seen(url, plattform, titel, antworten, datei=""):
    try:
        conn = pg_conn()
        with conn, conn.cursor() as cur:
            cur.execute("INSERT INTO qa_seen (url, plattform, titel, antworten, entwurf_datei) "
                        "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (url) DO NOTHING",
                        (url, plattform, titel[:250], antworten, datei))
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
                            "VALUES (%s, 'buroflow', %s, %s, %s::vector) RETURNING id",
                            (BOT_NAME, title, content, vec_literal(v)))
            else:
                cur.execute("INSERT INTO memory (source, project, title, content) "
                            "VALUES (%s, 'buroflow', %s, %s) RETURNING id",
                            (BOT_NAME, title, content))
            mid = cur.fetchone()[0]
        conn.close()
        return f"Gespeichert (#{mid}): {title}"
    except Exception as e:
        return f"Fehler: {e}"


def recall_text(query, k=4):
    v = embed(query)
    try:
        conn = pg_conn()
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if v is not None:
                cur.execute("SELECT title, content FROM memory WHERE embedding IS NOT NULL "
                            "ORDER BY embedding <=> %s::vector ASC LIMIT %s", (vec_literal(v), k))
            else:
                cur.execute("SELECT title, content FROM memory ORDER BY created_at DESC LIMIT %s", (k,))
            rows = cur.fetchall()
        conn.close()
        return "\n".join(f"{r['title']}: {r['content']}" for r in rows)
    except Exception:
        return ""


def tool_recall(inp):
    q = (inp.get("query") or "").strip()
    if not q:
        return "Fehler: leere Suche."
    return recall_text(q, 5) or "Keine Treffer."


# ── CAMOFOX (nur lesen) ──────────────────────────────────────
LOGIN_MARKER = ("einloggen", "anmelden mit", "passwort vergessen", "registrieren",
                "__cf_chl", "just a moment", "cf-challenge")


def _ist_blockiert(url, snapshot):
    """Erkennt Login-Weiterleitungen und Bot-Schutz, damit wir nicht still scheitern."""
    u = (url or "").lower()
    s = (snapshot or "").lower()
    if "/einloggen" in u or "/login" in u or "__cf_chl" in u:
        return True
    if len(s) < 900 and any(m in s for m in LOGIN_MARKER):
        return True
    treffer = sum(1 for m in LOGIN_MARKER if m in s)
    return treffer >= 3 and len(s) < 5000


CONSENT_HINWEIS = ("consent to cookies", "cookie", "datenschutz-einstellung",
                   "privatsphaere", "privatsph\u00e4re", "einwilligung")
# Reihenfolge = Prioritaet: erst ablehnen, nur zur Not akzeptieren
CONSENT_ABLEHNEN = ("ablehnen", "reject", "nur notwendige", "nur essenzielle", "necessary only",
                    "decline", "weiter ohne", "nicht akzeptieren", "alle ablehnen")
CONSENT_ANNEHMEN = ("akzeptieren", "zustimmen", "einverstanden", "accept", "agree", "alle erlauben")


def _ist_consent(snapshot):
    kopf = " ".join((snapshot or "").split())[:600].lower()
    return any(w in kopf for w in CONSENT_HINWEIS)


_404_MARKER = ("fehler 404", "error 404", "gibt's nicht mehr", "gibt es nicht mehr",
               "seite nicht gefunden", "page not found")


def _ist_404(snapshot):
    """Gutefrage liefert bei toten Tag-/Suchseiten eine 404-Seite mit Status 200."""
    s = " ".join((snapshot or "").split()).lower()
    return any(m in s for m in _404_MARKER)


def _consent_ref(snapshot):
    """Sucht den Consent-Button. Datenschutzfreundlich: Ablehnen vor Akzeptieren.

    Camofox liefert die Referenz als [e1] (nicht [ref=e1]) und der Consent-Dialog
    besteht teils aus Links statt Buttons — beides wird hier beruecksichtigt.
    """
    zeilen = [z for z in (snapshot or "").splitlines()
              if ("button" in z.lower() or "link" in z.lower())]
    for begriffe in (CONSENT_ABLEHNEN, CONSENT_ANNEHMEN):
        for z in zeilen:
            zl = z.lower()
            if not any(w in zl for w in begriffe):
                continue
            # Bezahlangebote nie anklicken (contentpass o.ae.)
            if any(w in zl for w in ("contentpass", "€", "eur", "monat", "month", "login")):
                continue
            m = re.search(r"\[(?:ref=)?([A-Za-z]?\d+[A-Za-z0-9_-]*)\]", z)
            if m:
                return m.group(1), z.strip()[:70]
    return None, None


def _klick(tab, ref):
    try:
        r = requests.post(f"{CAMOFOX_URL}/tabs/{tab}/click",
                          json={"userId": BOT_USER_ID, "sessionKey": "main", "ref": ref}, timeout=40)
        return r.status_code < 400
    except Exception:
        return False


def _snapshot(tab):
    try:
        s = requests.get(f"{CAMOFOX_URL}/tabs/{tab}/snapshot",
                         params={"userId": BOT_USER_ID}, timeout=70)
        if s.status_code >= 400:
            return None, None
        d = s.json()
        return (d.get("snapshot") or ""), (d.get("url") or "")
    except Exception:
        return None, None


def _tab_schliessen(tab):
    """Tab freigeben. Ohne das laeuft camofox nach wenigen Abrufen voll."""
    if not tab:
        return
    try:
        requests.delete(f"{CAMOFOX_URL}/tabs/{tab}",
                        params={"userId": BOT_USER_ID}, timeout=20)
    except Exception:
        pass


def fetch_page(url):
    tab = None
    try:
        r = requests.post(f"{CAMOFOX_URL}/tabs",
                          json={"userId": BOT_USER_ID, "sessionKey": "main", "url": url}, timeout=70)
        if r.status_code >= 400:
            return None, f"Browser-Fehler ({r.status_code})"
        tab = r.json().get("tabId") or r.json().get("id")
        s = requests.get(f"{CAMOFOX_URL}/tabs/{tab}/snapshot",
                         params={"userId": BOT_USER_ID}, timeout=70)
        if s.status_code >= 400:
            return None, f"Snapshot-Fehler ({s.status_code})"
        daten = s.json()
        snap = daten.get("snapshot") or ""
        end_url = daten.get("url") or url

        # Cookie-Dialog wegklicken (bis zu 2 Versuche, sonst wird nichts bedient)
        for _versuch in range(2):
            if not _ist_consent(snap):
                break
            ref, beschriftung = _consent_ref(snap)
            if not ref:
                print("  [consent] Dialog erkannt, aber kein Button gefunden", flush=True)
                break
            if not _klick(tab, ref):
                print(f"  [consent] Klick fehlgeschlagen: {beschriftung}", flush=True)
                break
            print(f"  [consent] weggeklickt: {beschriftung}", flush=True)
            time.sleep(1.5)
            neu, neue_url = _snapshot(tab)
            if neu:
                snap, end_url = neu, (neue_url or end_url)

        if _ist_404(snap):
            return None, f"SEITE-404 (Quelle existiert nicht mehr) bei {end_url[:90]}"
        if _ist_blockiert(end_url, snap):
            return None, f"BLOCKIERT (Login/Bot-Schutz) bei {end_url[:90]}"
        if _ist_consent(snap) and len(snap) < 8000:
            return None, "BLOCKIERT (Cookie-Dialog liess sich nicht schliessen)"
        return snap[:9000], None
    except Exception as e:
        return None, f"Browser nicht erreichbar ({type(e).__name__})"
    finally:
        _tab_schliessen(tab)


def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return False
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      json={"chat_id": TELEGRAM_CHAT, "text": text[:4000],
                            "disable_web_page_preview": True}, timeout=20)
        return True
    except Exception as e:
        print(f"  [telegram] {e}", flush=True)
        return False


# ── FRAGEN-EXTRAKTION ────────────────────────────────────────
EXTRACT_SYS = """Du extrahierst Fragen aus einem Q&A-Seiten-Snapshot.
Antworte NUR mit JSON, keine Erklaerung:
{"fragen":[{"titel":"...","url":"https://...","alter":"vor 3 Stunden","antworten":0,"relevant":true}]}

RELEVANZ (relevant=true NUR wenn fachlich passend):
Rechnungen schreiben, Kleinunternehmer/§19 UStG, Angebote, Mahnwesen, E-Rechnung/ZUGFeRD,
Buchhaltung, Umsatzsteuer, Gruendung/Gewerbe, Selbststaendigkeit-Buerokratie.
NICHT relevant: E-Scooter, PayPal, eBay-Kaeuferschutz, Handyvertraege, Privatstreit,
Arbeitsrecht ohne Selbststaendigkeit, alles Themenfremde.

antworten = Anzahl vorhandener Antworten (0 wenn "Noch keine Antworten").
alter = wie auf der Seite angegeben. Nichts erfinden: nur was im Snapshot steht.
Max 12 Fragen."""


def _extract_fragen(snapshot, quelle):
    try:
        resp = client.messages.create(
            model=FAST_MODEL, max_tokens=1400, system=EXTRACT_SYS,
            messages=[{"role": "user", "content": f"QUELLE: {quelle}\n\n{snapshot[:8000]}"}])
        track_cost(FAST_MODEL, resp.usage.input_tokens, resp.usage.output_tokens)
        raw = re.sub(r"```json|```", "", "".join(b.text for b in resp.content if b.type == "text")).strip()
        data = json.loads(raw)
        out = []
        for f in data.get("fragen", []):
            if not f.get("relevant"):
                continue
            url = (f.get("url") or "").strip()
            if not url.startswith("http"):
                continue
            f["quelle"] = quelle
            f["antworten"] = int(f.get("antworten") or 0)
            out.append(f)
        return out
    except Exception as e:
        print(f"  [extract] {type(e).__name__}: {e}", flush=True)
        return []


# "vor 2 Tagen, 9 Stunden" enthielt frueher "stunde" und galt damit faelschlich
# als frisch. Jetzt zaehlen Stunden nur, wenn KEINE Tagesangabe davorsteht.
FRISCH = re.compile(
    r"(vor \d+ (?:sekunde|minute)"
    r"|vor (?:1|2|3|4|5|6|7|8|9|1\d|2[0-3]) stunde"
    r"|heute|gerade|soeben|vor 1 tag|vor einem tag|gestern)", re.I)
_ALT = re.compile(r"vor \d+\s*(tag|tagen|woche|monat|jahr)", re.I)


def _ist_frisch(alter):
    t = (alter or "").strip()
    if not t:
        return False
    # "vor 2 Tagen, 9 Stunden" -> alt, egal was dahinter steht
    m = _ALT.search(t)
    if m:
        zahl = re.match(r"vor (\d+)", t[m.start():])
        if zahl and int(zahl.group(1)) > 1:
            return False
        if "woche" in m.group(0).lower() or "monat" in m.group(0).lower() \
           or "jahr" in m.group(0).lower():
            return False
    return bool(FRISCH.search(t))


def scan_gutefrage(max_quellen=12):
    """Oeffentliche Quellen ohne Login.

    Hauptquelle sind die Themenseiten /tag/<slug>/1 — dort stehen fachlich
    passende Fragen. Der allgemeine Strom /fragen/neue kommt ergaenzend dazu,
    liefert aber selten Relevantes (Anime, Urlaub, Beziehungsfragen).
    Die Tags rotieren taeglich, damit ueber die Zeit alle drankommen.
    """
    from urllib.parse import quote
    gefunden, blockiert, tot = [], [], []

    # Taegliche Rotation: Startpunkt haengt am Tag des Jahres
    versatz = datetime.now().timetuple().tm_yday % max(1, len(GF_TAGS))
    tags = (GF_TAGS + GF_TAGS)[versatz:versatz + GF_TAG_ANZAHL]

    quellen = [(f"https://www.gutefrage.net/tag/{t}/1", f"Tag: {t}") for t in tags]
    quellen += [(f"{GF_NEUE}/{s}", f"Neueste Fragen S.{s}")
                for s in range(1, GF_SEITEN + 1)]
    if GF_ALT_QUELLEN:
        for k in GF_KEYWORDS[:3]:
            quellen.append((f"https://www.gutefrage.net/suche?q={quote(k)}", f"Suche: {k}"))

    for url, label in quellen[:max_quellen]:
        snap, err = fetch_page(url)
        if err:
            print(f"  [gf] {label}: {err}", flush=True)
            if "SEITE-404" in err:
                tot.append(label)
            elif "BLOCKIERT" in err:
                blockiert.append(label)
            continue
        gefunden += _extract_fragen(snap, f"gutefrage / {label}")
        time.sleep(1)

    if tot:
        print(f"  [gf] {len(tot)} Quellen existieren nicht mehr (404): "
              f"{', '.join(tot[:4])} — GF_TAGS pruefen!", flush=True)
    if blockiert:
        print(f"  [gf] {len(blockiert)} Quellen blockiert: {', '.join(blockiert[:4])}", flush=True)
    print(f"  [gf] {len(quellen[:max_quellen])} Quellen abgefragt, "
          f"{len(gefunden)} relevante Fragen", flush=True)
    return gefunden


def scan_quora(max_quellen=3):
    """Quora-Suche. Achtung: Cloudflare blockt haeufig — daher standardmaessig aus."""
    from urllib.parse import quote
    if not QUORA_AKTIV:
        print("  [quora] deaktiviert (Cloudflare-Schutz) — SEO_QUORA=1 zum Aktivieren", flush=True)
        return []
    gefunden = []
    for k in QUORA_KEYWORDS[:max_quellen]:
        url = f"https://www.quora.com/search?q={quote(k)}&type=question&time=week"
        snap, err = fetch_page(url)
        if err:
            print(f"  [quora] {k}: {err}", flush=True)
            continue
        gefunden += _extract_fragen(snap, f"quora / Suche: {k}")
        time.sleep(1)
    return gefunden


# ── ENTWURF SCHREIBEN ────────────────────────────────────────
DRAFT_SYS = """Du schreibst einen ANTWORT-ENTWURF fuer Rui auf eine oeffentliche Q&A-Frage.
Rui postet ihn selbst — du postest nichts.

STIL (verbindlich):
- Ruis echter Stil: locker, Umgangssprache, du-Form, kurze Saetze, kleine Unschaerfen erlaubt
  ("meist", "in der Regel", "so wie ich das kenne"). Kein Marketing-Sprech.
- KEINE Aufzaehlungszeichen-Listen, keine Zwischenueberschriften, keine Emojis.
  Fliesstext, 3-8 Saetze. So wie man das einem Kollegen erklaeren wuerde.
- Nicht mit "Gerne!" / "Klar!" / "Super Frage" anfangen. Direkt in die Sache.
- Keine Floskeln wie "Ich hoffe, das hilft dir weiter" am Ende.

INHALT:
- Fachlich korrekt und konkret. Wenn du bei einem Detail unsicher bist: allgemein bleiben
  oder ehrlich schreiben, dass es auf den Einzelfall ankommt. NICHTS erfinden.
- Keine Rechts- oder Steuerberatung im engeren Sinn — bei sowas auf Steuerberater verweisen.

BUEROFLOW-REGEL (streng):
- Bueroflow NUR erwaehnen, wenn die Frage aktiv nach einem Tool/Programm/Software fragt.
- Bei reinen Rechts-, Steuer- oder Verfahrensfragen: NIE erwaehnen.
- Wenn erwaehnt: beilaeufig, ein Halbsatz, kein Link-Spam, als eine Option unter mehreren.

Antworte NUR mit JSON:
{"antwort":"...","tool_frage":true/false,"unsicher":"was ggf. geprueft werden sollte, sonst leer"}"""


def _slug(text):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "frage").lower())
    return s.strip("-")[:60] or "frage"


def _vault_pfad():
    p = os.path.join(VAULT_DIR, VAULT_SUB)
    os.makedirs(p, exist_ok=True)
    return p


def entwurf_schreiben(frage, stil_kontext=""):
    titel = frage.get("titel", "")
    url = frage.get("url", "")
    snap, err = fetch_page(url)
    kontext = (snap or "")[:4000]
    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=1200, system=DRAFT_SYS,
            messages=[{"role": "user", "content":
                       f"FRAGE: {titel}\nURL: {url}\n\nSEITENINHALT:\n{kontext}\n\n"
                       f"RUIS STILPROFIL (aus frueheren Texten):\n{stil_kontext[:1500]}"}])
        track_cost(MODEL, resp.usage.input_tokens, resp.usage.output_tokens)
        raw = re.sub(r"```json|```", "", "".join(b.text for b in resp.content if b.type == "text")).strip()
        d = json.loads(raw)
    except Exception as e:
        return None, f"Entwurf fehlgeschlagen: {type(e).__name__}"

    antwort = (d.get("antwort") or "").strip()
    if not antwort:
        return None, "Leerer Entwurf."

    datei = f"{datetime.now().strftime('%Y-%m-%d')}_{_slug(titel)}.md"
    pfad = os.path.join(_vault_pfad(), datei)
    try:
        with open(pfad, "w", encoding="utf-8") as f:
            f.write(f"# {titel}\n\n")
            f.write(f"- **Link:** {url}\n")
            f.write(f"- **Quelle:** {frage.get('quelle', '-')}\n")
            f.write(f"- **Alter:** {frage.get('alter', '-')} | **Antworten:** {frage.get('antworten', 0)}\n")
            f.write(f"- **Erstellt:** {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n")
            if d.get("unsicher"):
                f.write(f"> ⚠️ Vor dem Posten pruefen: {d['unsicher']}\n\n")
            f.write("## Entwurf\n\n")
            f.write(antwort + "\n")
    except Exception as e:
        return None, f"Vault-Fehler: {e}"
    protokoll_melden("seo", "Antwort-Entwurf geschrieben", titel[:150], f"seo/{datei}")
    return {"antwort": antwort, "datei": datei, "unsicher": d.get("unsicher", "")}, None


def _bericht_zeile(f):
    marker = "🟢" if f.get("antworten", 0) == 0 else "🔵"
    return (f"{marker} {f.get('titel', '?')}\n"
            f"   {f.get('alter', '-')} | {f.get('antworten', 0)} Antworten | {f.get('quelle', '-')}\n"
            f"   {f.get('url', '')}")


def recherche(plattform="beide", mit_entwuerfen=True, max_entwuerfe=3, telegram=False):
    """Sucht frische Fragen, priorisiert 0-Antworten, schreibt Entwuerfe in den Vault.
    telegram=False (Standard): nichts wird verschickt — alles landet nur im Vault."""
    fragen = []
    if plattform in ("beide", "gutefrage"):
        fragen += scan_gutefrage()
    if plattform in ("beide", "quora"):
        fragen += scan_quora()

    # dedup + nur frische + nur unbekannte
    neu, gesehen_urls = [], set()
    for f in fragen:
        u = f.get("url", "")
        if not u or u in gesehen_urls:
            continue
        gesehen_urls.add(u)
        if not _ist_frisch(f.get("alter", "")):
            continue
        if already_seen(u):
            continue
        neu.append(f)

    if not neu:
        msg = ("Heute keine neuen passenden Fragen."
               if fragen else
               "Keine passenden Fragen gefunden. Moegliche Gruende: nichts Frisches "
               "zum Thema, oder Quellen nicht erreichbar — im Server-Log steht, welche.")
        if telegram:
            send_telegram("🔍 Q&A-Recherche: " + msg)
        return msg

    # Priorisierung: 0 Antworten zuerst, dann wenige Antworten
    neu.sort(key=lambda f: (f.get("antworten", 99), f.get("titel", "")))

    zeilen = [_bericht_zeile(f) for f in neu[:12]]
    kopf = f"🔍 Q&A-Recherche {datetime.now().strftime('%d.%m.%Y')} — {len(neu)} neue Fragen"
    bericht = kopf + "\n\n" + "\n\n".join(zeilen)

    entwuerfe = []
    if mit_entwuerfen:
        stil = recall_text("Schreibstil Rui gutefrage locker Umgangssprache", 3)
        for f in neu[:max_entwuerfe]:
            res, err = entwurf_schreiben(f, stil)
            if err:
                mark_seen(f["url"], f.get("quelle", ""), f.get("titel", ""), f.get("antworten", 0))
                entwuerfe.append(f"❌ {f.get('titel', '?')}: {err}")
                continue
            mark_seen(f["url"], f.get("quelle", ""), f.get("titel", ""), f.get("antworten", 0), res["datei"])
            if telegram:
                send_telegram(_entwurf_block(f.get("titel", "?"), f.get("url", ""), res))
            entwuerfe.append(f"✅ Entwurf: {f.get('titel', '?')} → seo/{res['datei']}")
            time.sleep(1)
    else:
        for f in neu[:12]:
            mark_seen(f["url"], f.get("quelle", ""), f.get("titel", ""), f.get("antworten", 0))

    if telegram:
        send_telegram(bericht)
    if entwuerfe:
        bericht += "\n\n" + "\n".join(entwuerfe)
    bericht += "\n\nEntwuerfe liegen im Vault unter seo/ — bitte pruefen und selbst posten."
    return bericht


def _entwurf_block(titel, url, res):
    return (f"📝 {titel}\n{url}\n"
            + (f"⚠️ Pruefen: {res['unsicher']}\n" if res.get("unsicher") else "")
            + f"\n{res['antwort']}\n\n(Vault: seo/{res['datei']})")


def entwuerfe_senden(limit=5, nur_offene=True):
    """Schickt vorhandene Entwuerfe aus dem Vault per Telegram — nur auf Nachfrage."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return "Telegram nicht konfiguriert."
    try:
        conn = pg_conn()
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT titel, url, entwurf_datei FROM qa_seen "
                        "WHERE entwurf_datei <> ''" + (" AND NOT erledigt" if nur_offene else "") +
                        " ORDER BY id DESC LIMIT %s", (limit,))
            rows = cur.fetchall()
        conn.close()
    except Exception as e:
        return f"Fehler: {e}"
    if not rows:
        return "Keine Entwuerfe zum Senden."
    gesendet = 0
    for r in rows:
        pfad = os.path.join(_vault_pfad(), r["entwurf_datei"])
        try:
            with open(pfad, encoding="utf-8") as f:
                inhalt = f.read()
        except Exception:
            continue
        teil = inhalt.split("## Entwurf", 1)
        antwort = teil[1].strip() if len(teil) > 1 else inhalt
        send_telegram(f"📝 {r['titel']}\n{r['url']}\n\n{antwort}\n\n(Vault: seo/{r['entwurf_datei']})")
        gesendet += 1
        time.sleep(1)
    return f"{gesendet} Entwurf/Entwuerfe per Telegram geschickt."


def entwurf_fuer_url(url):
    """Einzelne Frage: Entwurf schreiben."""
    if not url.startswith("http"):
        return "Bitte eine vollstaendige URL angeben."
    snap, err = fetch_page(url)
    if err:
        return err
    titel = ""
    m = re.search(r"^#?\s*(.{10,140}\?)", snap or "", re.M)
    if m:
        titel = m.group(1).strip()
    frage = {"titel": titel or url, "url": url, "quelle": "manuell", "alter": "-", "antworten": 0}
    stil = recall_text("Schreibstil Rui gutefrage locker Umgangssprache", 3)
    res, err = entwurf_schreiben(frage, stil)
    if err:
        return err
    mark_seen(url, "manuell", frage["titel"], 0, res["datei"])
    return _entwurf_block(frage["titel"], url, res)


def offene_entwuerfe():
    try:
        conn = pg_conn()
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT titel, url, entwurf_datei, to_char(created_at,'DD.MM.') AS d "
                        "FROM qa_seen WHERE entwurf_datei <> '' AND NOT erledigt "
                        "ORDER BY id DESC LIMIT 15")
            rows = cur.fetchall()
        conn.close()
        if not rows:
            return "Keine offenen Entwuerfe."
        return "Offene Entwuerfe:\n" + "\n".join(
            f"- [{r['d']}] {r['titel']}\n  seo/{r['entwurf_datei']}\n  {r['url']}" for r in rows)
    except Exception as e:
        return f"Fehler: {e}"


def als_erledigt(url):
    try:
        conn = pg_conn()
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE qa_seen SET erledigt = TRUE WHERE url = %s", (url,))
            n = cur.rowcount
        conn.close()
        return "Als erledigt markiert." if n else "URL nicht gefunden."
    except Exception as e:
        return f"Fehler: {e}"


# ── TOOLS ────────────────────────────────────────────────────
TOOLS = [
    {"name": "recherche",
     "description": "Sucht auf gutefrage.net und/oder Quora frische, fachlich passende Fragen (Prioritaet: 0 Antworten). Schreibt zu den besten Treffern Antwort-Entwuerfe in Ruis Stil, legt sie im Vault unter seo/ ab und schickt sie per Telegram. Postet nichts.",
     "input_schema": {"type": "object", "properties": {
         "plattform": {"type": "string", "enum": ["beide", "gutefrage", "quora"]},
         "mit_entwuerfen": {"type": "boolean", "description": "false = nur Liste, keine Entwuerfe"},
         "max_entwuerfe": {"type": "integer", "description": "wie viele Entwuerfe (Standard 3)"},
         "telegram": {"type": "boolean", "description": "true = Ergebnis zusaetzlich per Telegram schicken (Standard false, nur Vault)"}}}},
    {"name": "entwurf",
     "description": "Schreibt einen Antwort-Entwurf zu EINER konkreten Frage-URL (gutefrage oder Quora).",
     "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
    {"name": "tagesrecherche",
     "description": ("Startet die Tagesrecherche sofort — dieselbe, die automatisch laeuft. "
                     "Ergebnis landet im Vault unter seo/, kein Telegram."),
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "senden",
     "description": "Schickt vorhandene Entwuerfe aus dem Vault per Telegram — nur wenn Rui aktiv danach fragt.",
     "input_schema": {"type": "object", "properties": {
         "limit": {"type": "integer", "description": "wie viele (Standard 5)"}}}},
    {"name": "offene_entwuerfe",
     "description": "Listet Entwuerfe, die noch nicht als gepostet markiert wurden.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "erledigt",
     "description": "Markiert eine Frage als erledigt (von Rui beantwortet).",
     "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
    {"name": "remember",
     "description": "Speichert SEO-/Q&A-Erkenntnisse dauerhaft (project: buroflow).",
     "input_schema": {"type": "object", "properties": {
         "content": {"type": "string"}, "title": {"type": "string"}}, "required": ["content", "title"]}},
    {"name": "recall",
     "description": "Durchsucht das gemeinsame Gedaechtnis (Stilprofil, fruehere Themen, Regeln).",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
]


def run_tool(name, inp):
    if name == "recherche":
        return recherche(plattform=(inp.get("plattform") or "beide"),
                         mit_entwuerfen=inp.get("mit_entwuerfen", True),
                         max_entwuerfe=min(int(inp.get("max_entwuerfe") or 3), 5),
                         telegram=bool(inp.get("telegram", False)))
    if name == "tagesrecherche":
        return tagesrecherche("manuell angestossen")
    if name == "senden":
        return entwuerfe_senden(limit=min(int(inp.get("limit") or 5), 10))
    if name == "entwurf":
        return entwurf_fuer_url((inp.get("url") or "").strip())
    if name == "offene_entwuerfe":
        return offene_entwuerfe()
    if name == "erledigt":
        return als_erledigt((inp.get("url") or "").strip())
    if name == "remember":
        return tool_remember(inp)
    if name == "recall":
        return tool_recall(inp)
    return f"Unbekanntes Tool: {name}"


SYSTEM = """Du bist der SEO/Q&A-BOT von Bueroflow, Arbeiter unter dem Bueroflow-CEO.

DEINE AUFGABE: Auf gutefrage.net und Quora frische Fragen finden, bei denen Rui mit einer
guten Antwort sichtbar wird — und ihm fertige Entwuerfe liefern.

PRIORITAET (wichtigster Hebel zuerst):
1. Fragen mit 0 Antworten aus den letzten ~24h (dort ist man Erster)
2. Fragen mit 1-2 Antworten
Alles aeltere oder themenfremde ignorierst du. Du erfindest NIE Fragen, um eine Liste zu fuellen.
Wenn nichts Passendes da ist, sagst du genau das in einem Satz.

THEMEN: Rechnungen schreiben, Kleinunternehmer/§19 UStG, Angebote, Mahnwesen,
E-Rechnung/ZUGFeRD, Buchhaltung, Umsatzsteuer, Gruendung/Gewerbe.

EISERNE REGELN:
- Du POSTEST NICHTS und veraenderst nichts auf den Plattformen. Nur lesen.
  Alle Antworten sind ENTWUERFE — Rui prueft und postet selbst.
- Entwuerfe klingen wie Rui: locker, du-Form, Fliesstext, kurze Saetze, keine Listen,
  keine Emojis, kein Marketing-Sprech, keine KI-Floskeln.
- Bueroflow nur erwaehnen, wenn aktiv nach einem Tool gefragt wird. Nie bei Rechts- oder
  Steuerfragen. Und dann beilaeufig, nicht als Werbung.
- Fachlich ehrlich: lieber "kommt auf den Einzelfall an" als eine erfundene Detailangabe.

ABLAUF:
- Du laeufst automatisch einmal taeglich und legst die Entwuerfe im Vault unter seo/ ab.
- Telegram schickst du NUR, wenn Rui aktiv danach fragt (Tool: senden, oder telegram=true).
  Von selbst verschickst du nichts.
Antworte Rui knapp und direkt auf Deutsch."""

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
    # Absichts-Saetze pruefen (auch wenn sie nicht am Anfang stehen)
    saetze = [s.strip() for s in re.split(r"[.!?]+", t) if s.strip()]
    if len(t) <= 160:
        for s in saetze:
            if len(s) <= 90 and INTENT_RE.match(s):
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


def _lauf_marker():
    return os.path.join(VAULT_DIR, VAULT_SUB, ".letzter_lauf")


def _letzter_lauf():
    """Wann lief die Tagesrecherche zuletzt? (ueberlebt Neustarts)"""
    try:
        with open(_lauf_marker(), encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def _lauf_vermerken(tag):
    try:
        os.makedirs(os.path.dirname(_lauf_marker()), exist_ok=True)
        with open(_lauf_marker(), "w", encoding="utf-8") as f:
            f.write(tag)
    except Exception as e:
        print(f"  [auto] Marker: {e}", flush=True)


def tagesrecherche(grund="automatisch"):
    now = datetime.now()
    print(f"  [auto] Tagesrecherche startet ({grund})", flush=True)
    res = recherche(plattform="beide", mit_entwuerfen=True,
                    max_entwuerfe=DAILY_ENTWUERFE, telegram=False)
    print(f"  [auto] fertig: {str(res)[:140]}", flush=True)
    try:
        with open(os.path.join(_vault_pfad(), "_tagesbericht.md"), "a", encoding="utf-8") as f:
            f.write(f"\n\n## {now.strftime('%d.%m.%Y %H:%M')}\n\n{res}\n")
    except Exception:
        pass
    _lauf_vermerken(now.strftime("%Y-%m-%d"))
    try:
        protokoll_melden("seo", "Tagesrecherche", str(res)[:200], "seo/_tagesbericht.md")
    except Exception:
        pass
    return res


def daily_thread():
    """Taeglicher Lauf. Holt nach, wenn der Bot zur eigentlichen Zeit nicht lief."""
    if not DAILY_TIME or ":" not in DAILY_TIME:
        print("  [auto] kein Tageslauf konfiguriert", flush=True)
        return
    try:
        hh, mm = [int(x) for x in DAILY_TIME.split(":")[:2]]
    except Exception:
        print(f"  [auto] SEO_DAILY_TIME ungueltig: {DAILY_TIME}", flush=True)
        return

    letzter = _letzter_lauf()
    print(f"  [auto] Tageslauf {DAILY_TIME} aktiv (zuletzt: {letzter or 'noch nie'})", flush=True)
    versuche = {"tag": "", "n": 0}
    time.sleep(30)   # erst hochfahren lassen

    while True:
        try:
            now = datetime.now()
            heute = now.strftime("%Y-%m-%d")
            faellig_ab = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            # Nachholen: Zeitpunkt vorbei UND heute noch nicht gelaufen
            if now >= faellig_ab and _letzter_lauf() != heute:
                if versuche.get("tag") != heute:
                    versuche.clear()
                    versuche["tag"] = heute
                    versuche["n"] = 0
                if versuche["n"] >= 3:
                    time.sleep(300)
                    continue
                versuche["n"] += 1
                grund = "planmaessig" if now.hour == hh else f"nachgeholt, geplant war {DAILY_TIME}"
                try:
                    tagesrecherche(grund)
                except Exception as e:
                    # Frueher wurde der Tag hier als erledigt vermerkt — dadurch
                    # verschwand ein gescheiterter Lauf lautlos. Jetzt: melden
                    # und bis zu 3x am Tag erneut versuchen.
                    print(f"  [auto] Lauf fehlgeschlagen ({versuche['n']}/3): "
                          f"{type(e).__name__}: {e}", flush=True)
                    if versuche["n"] >= 3:
                        _lauf_vermerken(heute)
                        send_telegram(f"SEO-Bot: Tagesrecherche heute 3x fehlgeschlagen "
                                      f"({type(e).__name__}: {str(e)[:200]})")
                    else:
                        time.sleep(300)   # kurz warten, dann neuer Versuch
        except Exception as e:
            print(f"  [auto] {type(e).__name__}: {e}", flush=True)
        time.sleep(60)


def main():
    protokoll_init()
    print("=" * 58, flush=True)
    print("  SEO/Q&A-BOT — gutefrage + Quora (read-only)", flush=True)
    print(f"  Telegram  : {'aktiv' if (TELEGRAM_TOKEN and TELEGRAM_CHAT) else 'nicht konfiguriert'}", flush=True)
    print(f"  Vault     : {VAULT_DIR}/{VAULT_SUB}/", flush=True)
    print(f"  Tageslauf : {DAILY_TIME or 'aus'} ({DAILY_ENTWUERFE} Entwuerfe, ohne Telegram)", flush=True)
    print("  Postet nichts — nur Entwuerfe fuer Rui.", flush=True)
    print("=" * 58, flush=True)
    init_db()
    try:
        _vault_pfad()
    except Exception as e:
        print(f"  [vault] {e}", flush=True)

    r = None
    for _ in range(30):
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
    threading.Thread(target=daily_thread, daemon=True).start()
    print("  SEO-Bot bereit.\n", flush=True)

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
                _antwort_senden(r, reply_q, "SEO-Kurzzeitgedaechtnis geleert.")
                continue
            print(f"  Auftrag: {text[:80]}", flush=True)
            history = load_history(r)
            try:
                answer = think(history, text)
            except Exception as e:
                answer = f"Fehler: {type(e).__name__}: {e}"
            save_history(r, history)
            print(f"  SEO: {answer[:100]}\n", flush=True)
            _antwort_senden(r, reply_q, answer)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"  [loop] {type(e).__name__}: {e}", flush=True)
            time.sleep(1)


if __name__ == "__main__":
    main()
