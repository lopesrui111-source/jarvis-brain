#!/usr/bin/env python3
"""
JARVIS Core v8 — v7.9 + AUFTRAGS-SYSTEM (mehrstufige Aufgaben im Hintergrund)
Neu gegenueber v4:
- Stil-Analyse: 'stil ionos' / 'stil gmail' liest die letzten gesendeten
  Mails (read-only), erstellt ein Schreibstil-Profil und speichert es
  ins Langzeitgedaechtnis + Vault (skills/)
- Gesendet-Ordner wird automatisch erkannt (\\Sent Flag, Fallback-Namen)
- ask_ceo: delegiert Auftraege an den Bueroflow-CEO-Bot am Bus
- ask_immo: dein Immobilien-Analyst (Rendite-Bewertungen, Scans, Telegram-Alerts an Rui).
- BUEROFLOW-ZAHLEN: Bei Fragen zum Stand von Bueroflow (Warteliste, Nutzer, Abos, Umsatz, Nutzung,
  Kosten, Wachstum) rufst du buroflow_zahlen auf und antwortest mit den echten Werten — nie schaetzen.
- FACHWISSEN NUTZEN: Du hast eine Bibliothek mit 362 erprobten Fachanleitungen und 7 Experten-Personas.
  Bevor du eine fachliche Aufgabe angehst (Preisgestaltung, SEO, Sicherheitsaudit, Vertragspruefung,
  Produktstrategie, Finanzplanung ...), suche mit skill_suchen nach einer passenden Anleitung und lade
  sie mit skill_laden. Das ist besser als aus dem Bauch zu antworten. Bei Bedarf persona_laden.
- GROSSE AUFGABEN: Wenn ein Auftrag mehrere Arbeitsschritte braucht (ganzes Repo/Projekt analysieren,
  Recherche ueber mehrere Quellen, etwas erarbeiten und dann sichern), lege mit job_anlegen einen
  Auftrag an, statt alles in einem Zug zu versuchen. Zerlege in 2-8 Schritte; der letzte Schritt ist
  meist das Sichern per remember. Du arbeitest ihn dann im Hintergrund ab — Rui muss nicht warten
  und nichts geht verloren, auch nicht bei einem Neustart. Kleine Fragen beantwortest du weiter direkt.
- AUFTRAEGE ZU ENDE BRINGEN: Wenn Rui sagt "merk dir das", "speichere das" oder "lerne daraus",
  dann rufst du remember AUF (ein oder mehrere Male, thematisch getrennt) — ein Satz wie
  "Jetzt alles merken" ohne Tool-Aufruf ist ein Fehler und speichert nichts.
  Bei Recherche-Auftraegen gilt: erst sammeln, dann die Erkenntnisse per remember sichern,
  dann Rui zusammenfassen.
- HANDELN STATT ANKUENDIGEN: Kuendige niemals an, was du gleich tust ("Lass mich...", "Ich schaue...",
  "Starte jetzt", "Einen Moment"). Rufe die noetigen Tools SOFORT im selben Zug auf und antworte erst,
  wenn du das Ergebnis hast. Eine Antwort ohne Tool-Aufruf, die eine Handlung ankuendigt, ist ein Fehler.
  Bei mehrstufigen Auftraegen arbeitest du die Schritte nacheinander ab, ohne zwischendurch zu fragen.
- github_repos/github_browse/github_read/github_search/github_commits: Du kannst Ruis GitHub-Code
  lesen — z.B. das Buroflow-Projekt (Repo 'Buroflow') oder dein eigenes Repo 'jarvis-brain'.
  Nutze das, um Ruis Architektur, Konventionen und Stand wirklich zu kennen, statt zu raten.
  STRIKT read-only: du kannst nichts committen, pushen oder aendern.
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
MAX_TOOL_ROUNDS = 14

VAULT_DIR = "/app/vault"
BOT_USER_ID = "jarvis"

# Bueroflow-Datenbank (Supabase, read-only)
SUPABASE_URL = os.getenv("SUPABASE_DB_URL", "")
BF_T_WAITLIST = os.getenv("BF_TABLE_WAITLIST", "waitlist")
BF_T_USERS    = os.getenv("BF_TABLE_USERS", "user_profiles")
BF_T_SUBS     = os.getenv("BF_TABLE_SUBS", "subscriptions")
BF_T_GEN      = os.getenv("BF_TABLE_GENERATIONS", "generations")
BF_T_USAGE    = os.getenv("BF_TABLE_USAGE", "ai_usage")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_USER = os.getenv("GITHUB_USER", "lopesrui111-source")
GH_API = "https://api.github.com"

# Google-Kalender: private iCal-Adressen (kommagetrennt), read-only
GOOGLE_ICS = [u.strip() for u in os.getenv("GOOGLE_ICS_URLS", "").split(",") if u.strip()]

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
- github_repos/github_browse/github_read/github_search/github_commits: Du kannst Ruis GitHub-Code
  lesen — z.B. das Buroflow-Projekt (Repo 'Buroflow') oder dein eigenes Repo 'jarvis-brain'.
  Nutze das, um Ruis Architektur, Konventionen und Stand wirklich zu kennen, statt zu raten.
  STRIKT read-only: du kannst nichts committen, pushen oder aendern.
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
        "name": "buroflow_zahlen",
        "description": ("Liest die aktuellen Bueroflow-Kennzahlen direkt aus Supabase: Warteliste, "
                        "registrierte Nutzer, aktive Abos und Plaene, Generierungen je Tool, KI-Kosten, "
                        "aktive Nutzer und Conversion-Funnel. Read-only. Nutze das bei allen Fragen zum "
                        "Stand von Bueroflow, statt zu schaetzen."),
        "input_schema": {"type": "object", "properties": {
            "tage": {"type": "integer", "description": "Vergleichszeitraum in Tagen (Standard 7, max 90)"}}},
    },
    {
        "name": "skill_suchen",
        "description": ("Durchsucht die Skill-Bibliothek (362 Fachanleitungen: Engineering, Marketing, Finanzen, "
                        "Recht/Compliance, Produkt, Research, C-Level-Beratung u.a.). Ohne query bekommst du die "
                        "Bereichsuebersicht. Nutze das, BEVOR du eine Fachaufgabe angehst — die Anleitungen "
                        "enthalten erprobte Vorgehensweisen, Checklisten und Frameworks."),
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
    },
    {
        "name": "skill_laden",
        "description": "Laedt eine Fachanleitung vollstaendig (Name aus skill_suchen).",
        "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    },
    {
        "name": "persona_laden",
        "description": ("Laedt eine Experten-Persona (z.B. startup-cto, finance-lead, growth-marketer, "
                        "solo-founder, product-manager, devops-engineer, content-strategist) und denkt "
                        "anschliessend aus deren Blickwinkel. Ohne name bekommst du die Liste."),
        "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}},
    },
    {
        "name": "job_anlegen",
        "description": ("Legt einen mehrstufigen Auftrag an, den du im Hintergrund Schritt fuer Schritt abarbeitest. "
                        "Nutze das IMMER fuer groessere Aufgaben (Repo/Projekt analysieren, mehrstufige Recherche, "
                        "Konzept erarbeiten und sichern) statt zu versuchen, alles in einem Zug zu erledigen. "
                        "Zerlege die Aufgabe in 2-8 konkrete, aufeinander aufbauende Schritte. "
                        "Der letzte Schritt sollte typischerweise das Sichern der Erkenntnisse (remember) sein."),
        "input_schema": {"type": "object", "properties": {
            "titel": {"type": "string", "description": "kurzer Name des Auftrags"},
            "auftrag": {"type": "string", "description": "das Gesamtziel in 1-3 Saetzen"},
            "schritte": {"type": "array", "items": {"type": "string"},
                         "description": "2-8 konkrete Arbeitsschritte in sinnvoller Reihenfolge"}},
            "required": ["titel", "auftrag", "schritte"]},
    },
    {
        "name": "job_status",
        "description": "Zeigt den Stand der Auftraege (ohne id: die letzten 8; mit id: einen bestimmten samt Ergebnis).",
        "input_schema": {"type": "object", "properties": {"id": {"type": "integer"}}},
    },
    {
        "name": "job_abbrechen",
        "description": "Bricht einen laufenden Auftrag ab.",
        "input_schema": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
    },
    {
        "name": "github_repos",
        "description": "Listet Ruis GitHub-Repositories (Name, Sprache, letzte Aenderung). Read-only.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "github_browse",
        "description": "Zeigt den Inhalt eines Ordners in einem Repo (Ordner + Dateien). repo z.B. 'Buroflow', path z.B. 'src/app'. Read-only.",
        "input_schema": {"type": "object", "properties": {
            "repo": {"type": "string"}, "path": {"type": "string"}}, "required": ["repo"]},
    },
    {
        "name": "github_read",
        "description": "Liest eine Datei aus einem Repo im Klartext. Damit kannst du Ruis Code studieren und daraus lernen. Read-only.",
        "input_schema": {"type": "object", "properties": {
            "repo": {"type": "string"}, "path": {"type": "string"},
            "max_zeichen": {"type": "integer"}}, "required": ["repo", "path"]},
    },
    {
        "name": "github_search",
        "description": "Durchsucht den Code (optional auf ein Repo begrenzt) und liefert Fundstellen als Dateipfade. Read-only.",
        "input_schema": {"type": "object", "properties": {
            "query": {"type": "string"}, "repo": {"type": "string"}}, "required": ["query"]},
    },
    {
        "name": "github_commits",
        "description": "Zeigt die letzten Commits eines Repos (optional zu einem bestimmten Pfad). Read-only.",
        "input_schema": {"type": "object", "properties": {
            "repo": {"type": "string"}, "pfad": {"type": "string"},
            "anzahl": {"type": "integer"}}, "required": ["repo"]},
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


# ── BUEROFLOW-ZAHLEN (Supabase, strikt read-only) ────────────
def tool_buroflow_zahlen(inp):
    if not SUPABASE_URL:
        return "Bueroflow-Datenbank nicht konfiguriert (SUPABASE_DB_URL fehlt)."
    tage = min(max(int(inp.get("tage") or 7), 1), 90)
    try:
        conn = psycopg2.connect(SUPABASE_URL, connect_timeout=10)
    except Exception as e:
        return f"Keine Verbindung zur Bueroflow-DB: {type(e).__name__}: {str(e)[:120]}"

    def eins(cur, *sqls):
        """Erste Abfrage, die einen Wert liefert (Spaltennamen koennen abweichen)."""
        for s in sqls:
            try:
                cur.execute(s)
                row = cur.fetchone()
                if row and row[0] is not None:
                    return row[0]
            except Exception:
                cur.connection.rollback()
        return 0

    def viele(cur, sql):
        try:
            cur.execute(sql)
            return cur.fetchall()
        except Exception:
            cur.connection.rollback()
            return []

    z = {}
    try:
        with conn, conn.cursor() as cur:
            iv = f"interval '{tage} days'"
            z["warteliste"] = int(eins(cur, f"SELECT COUNT(*) FROM {BF_T_WAITLIST}"))
            z["warteliste_neu"] = int(eins(cur, f"SELECT COUNT(*) FROM {BF_T_WAITLIST} WHERE created_at > now() - {iv}"))
            z["nutzer"] = int(eins(cur, f"SELECT COUNT(*) FROM {BF_T_USERS}", "SELECT COUNT(*) FROM users"))
            z["nutzer_neu"] = int(eins(cur, f"SELECT COUNT(*) FROM {BF_T_USERS} WHERE created_at > now() - {iv}"))
            z["abos"] = int(eins(cur, f"SELECT COUNT(*) FROM {BF_T_SUBS} WHERE status = 'active'"))
            z["generierungen"] = int(eins(cur, f"SELECT COUNT(*) FROM {BF_T_GEN}"))
            z["gen_neu"] = int(eins(cur, f"SELECT COUNT(*) FROM {BF_T_GEN} WHERE created_at > now() - {iv}"))
            z["kosten"] = float(eins(cur, f"SELECT SUM(cost_usd) FROM {BF_T_USAGE}",
                                          f"SELECT SUM(cost) FROM {BF_T_USAGE}",
                                          f"SELECT SUM(cost_usd) FROM {BF_T_GEN}"))
            z["kosten_zeitraum"] = float(eins(cur,
                f"SELECT SUM(cost_usd) FROM {BF_T_USAGE} WHERE created_at > now() - {iv}",
                f"SELECT SUM(cost) FROM {BF_T_USAGE} WHERE created_at > now() - {iv}"))
            z["aktive_nutzer"] = int(eins(cur,
                f"SELECT COUNT(DISTINCT user_id) FROM {BF_T_GEN} WHERE created_at > now() - {iv}"))
            z["tools"] = [(r[0] or "?", int(r[1])) for r in viele(cur,
                f"SELECT tool, COUNT(*) FROM {BF_T_GEN} GROUP BY tool ORDER BY COUNT(*) DESC LIMIT 6")]
            z["plaene"] = [(r[0] or "?", int(r[1])) for r in viele(cur,
                f"SELECT plan, COUNT(*) FROM {BF_T_SUBS} WHERE status='active' GROUP BY plan")]
        conn.close()
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return f"Fehler beim Lesen: {type(e).__name__}: {str(e)[:150]}"

    wl, nu, ab = z["warteliste"], z["nutzer"], z["abos"]
    zeilen = [
        f"BUEROFLOW-ZAHLEN (Zeitraum: letzte {tage} Tage)",
        f"- Warteliste: {wl} (+{z['warteliste_neu']})",
        f"- Registrierte Nutzer: {nu} (+{z['nutzer_neu']})",
        f"- Aktive Abos: {ab}" + (f" — {', '.join(f'{p}: {n}' for p, n in z['plaene'])}" if z["plaene"] else ""),
        f"- Aktive Nutzer im Zeitraum: {z['aktive_nutzer']}",
        f"- Generierungen: {z['generierungen']} gesamt, {z['gen_neu']} im Zeitraum",
        f"- KI-Kosten: ${z['kosten']:.4f} gesamt, ${z['kosten_zeitraum']:.4f} im Zeitraum",
    ]
    if z["tools"]:
        zeilen.append("- Nutzung je Tool: " + ", ".join(f"{t} {n}x" for t, n in z["tools"]))
    if wl:
        zeilen.append(f"- Funnel: Warteliste {wl} -> registriert {nu} ({nu/wl*100:.0f}%) -> zahlend {ab}"
                      + (f" ({ab/nu*100:.0f}% der Registrierten)" if nu else ""))
    return "\n".join(zeilen)


# ── SKILL-BIBLIOTHEK (claude-skills, read-only) ──────────────
SKILLS_DIR = os.getenv("SKILLS_DIR", "/app/skills-lib")
SKILL_INDEX = []          # [{name, beschreibung, kategorie, pfad}]
PERSONA_INDEX = []        # [{name, pfad}]
SKILL_MAX_ZEICHEN = 14000


def _frontmatter(pfad):
    """Liest name/description/category aus dem YAML-Kopf einer SKILL.md."""
    name = beschreibung = kategorie = ""
    try:
        with open(pfad, encoding="utf-8", errors="replace") as f:
            if f.readline().strip() != "---":
                return None
            for _ in range(40):
                zeile = f.readline()
                if not zeile or zeile.strip() == "---":
                    break
                z = zeile.strip()
                if z.startswith("name:"):
                    name = z.split(":", 1)[1].strip().strip('"\'')
                elif z.startswith("description:"):
                    beschreibung = z.split(":", 1)[1].strip().strip('"\'')
                elif z.startswith("category:"):
                    kategorie = z.split(":", 1)[1].strip().strip('"\'')
    except Exception:
        return None
    if not name:
        name = os.path.basename(os.path.dirname(pfad))
    return {"name": name, "beschreibung": beschreibung[:400],
            "kategorie": kategorie or pfad.replace(SKILLS_DIR, "").strip("/").split("/")[0],
            "pfad": pfad}


def skills_indexieren():
    """Baut den Index einmalig beim Start. Duplikate (.gemini) werden uebersprungen."""
    global SKILL_INDEX, PERSONA_INDEX
    SKILL_INDEX, PERSONA_INDEX = [], []
    if not os.path.isdir(SKILLS_DIR):
        print("  [skills] Bibliothek nicht gemountet", flush=True)
        return
    gesehen = set()
    for wurzel, dirs, dateien in os.walk(SKILLS_DIR):
        dirs[:] = [d for d in dirs if d not in (".gemini", ".hermes", ".vibe", ".git", "node_modules")]
        if "SKILL.md" in dateien:
            eintrag = _frontmatter(os.path.join(wurzel, "SKILL.md"))
            if eintrag and eintrag["name"].lower() not in gesehen:
                gesehen.add(eintrag["name"].lower())
                SKILL_INDEX.append(eintrag)
    pdir = os.path.join(SKILLS_DIR, "agents", "personas")
    if os.path.isdir(pdir):
        for f in sorted(os.listdir(pdir)):
            if f.endswith(".md") and f not in ("README.md", "TEMPLATE.md"):
                PERSONA_INDEX.append({"name": f[:-3], "pfad": os.path.join(pdir, f)})
    print(f"  [skills] {len(SKILL_INDEX)} Skills, {len(PERSONA_INDEX)} Personas indexiert", flush=True)


def tool_skill_suchen(inp):
    query = (inp.get("query") or "").strip().lower()
    if not SKILL_INDEX:
        return "Skill-Bibliothek nicht verfuegbar."
    if not query:
        kats = {}
        for s in SKILL_INDEX:
            kats[s["kategorie"]] = kats.get(s["kategorie"], 0) + 1
        return (f"{len(SKILL_INDEX)} Skills in diesen Bereichen:\n" +
                "\n".join(f"  {k} ({v})" for k, v in sorted(kats.items(), key=lambda x: -x[1])) +
                "\n\nSuche mit einem Stichwort, z.B. 'pricing', 'seo', 'security'.")
    woerter = [w for w in re.split(r"[^a-z0-9aeoeueaeoeuess]+", query) if len(w) > 2]
    treffer = []
    for s in SKILL_INDEX:
        heu = f"{s['name']} {s['beschreibung']} {s['kategorie']}".lower()
        punkte = sum(3 if w in s["name"].lower() else (1 if w in heu else 0) for w in woerter)
        if punkte:
            treffer.append((punkte, s))
    if not treffer:
        return f"Keine Skills zu '{query}' gefunden."
    treffer.sort(key=lambda t: -t[0])
    zeilen = [f"- {s['name']} [{s['kategorie']}]: {s['beschreibung'][:180]}" for _, s in treffer[:12]]
    return (f"{len(treffer)} Treffer (max 12 gezeigt):\n" + "\n".join(zeilen) +
            "\n\nMit skill_laden(name) holst du die vollstaendige Anleitung.")


def tool_skill_laden(inp):
    name = (inp.get("name") or "").strip().lower()
    if not name:
        return "Fehler: name noetig."
    if not SKILL_INDEX:
        return "Skill-Bibliothek nicht verfuegbar."
    treffer = [s for s in SKILL_INDEX if s["name"].lower() == name] or \
              [s for s in SKILL_INDEX if name in s["name"].lower()]
    if not treffer:
        return f"Skill '{name}' nicht gefunden — nutze skill_suchen."
    s = treffer[0]
    try:
        with open(s["pfad"], encoding="utf-8", errors="replace") as f:
            inhalt = f.read()
    except Exception as e:
        return f"Fehler beim Lesen: {e}"
    if len(inhalt) > SKILL_MAX_ZEICHEN:
        inhalt = inhalt[:SKILL_MAX_ZEICHEN] + "\n\n[... gekuerzt]"
    return f"=== SKILL: {s['name']} [{s['kategorie']}] ===\n{inhalt}"


def tool_persona_laden(inp):
    name = (inp.get("name") or "").strip().lower()
    if not PERSONA_INDEX:
        return "Keine Personas verfuegbar."
    if not name:
        return "Verfuegbare Personas:\n" + "\n".join(f"  - {p['name']}" for p in PERSONA_INDEX)
    treffer = [p for p in PERSONA_INDEX if name in p["name"].lower()]
    if not treffer:
        return ("Persona nicht gefunden. Verfuegbar:\n" +
                "\n".join(f"  - {p['name']}" for p in PERSONA_INDEX))
    try:
        with open(treffer[0]["pfad"], encoding="utf-8", errors="replace") as f:
            inhalt = f.read()[:SKILL_MAX_ZEICHEN]
    except Exception as e:
        return f"Fehler: {e}"
    return f"=== PERSONA: {treffer[0]['name']} ===\n{inhalt}"


# ── AUFTRAGS-SYSTEM (mehrstufige Aufgaben) ───────────────────
JOB_MAX_SCHRITTE = int(os.getenv("JOB_MAX_SCHRITTE", "8"))
JOB_RUNDEN = int(os.getenv("JOB_RUNDEN_PRO_SCHRITT", "12"))
JOB_NOTIZ_LIMIT = 7000


def init_jobs():
    try:
        conn = pg_conn()
        with conn, conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id SERIAL PRIMARY KEY,
                titel TEXT,
                auftrag TEXT,
                schritte JSONB,
                aktueller_schritt INT DEFAULT 0,
                notizen TEXT DEFAULT '',
                status TEXT DEFAULT 'offen',
                ergebnis TEXT,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now())""")
        conn.close()
        print("  [jobs] Tabelle bereit", flush=True)
    except Exception as e:
        print(f"  [jobs] {e}", flush=True)


def _job_update(job_id, **felder):
    if not felder:
        return
    sets = ", ".join(f"{k} = %s" for k in felder)
    werte = list(felder.values()) + [job_id]
    try:
        conn = pg_conn()
        with conn, conn.cursor() as cur:
            cur.execute(f"UPDATE jobs SET {sets}, updated_at = now() WHERE id = %s", werte)
        conn.close()
    except Exception as e:
        print(f"  [jobs] update: {e}", flush=True)


def _job_holen(job_id=None):
    """Naechsten offenen Job holen, oder einen bestimmten."""
    try:
        conn = pg_conn()
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if job_id:
                cur.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
            else:
                cur.execute("SELECT * FROM jobs WHERE status IN ('offen','laeuft') "
                            "ORDER BY id ASC LIMIT 1")
            row = cur.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        print(f"  [jobs] holen: {e}", flush=True)
        return None


def tool_job_anlegen(inp):
    titel = (inp.get("titel") or "").strip()
    auftrag = (inp.get("auftrag") or "").strip()
    schritte = inp.get("schritte") or []
    if not titel or not auftrag:
        return "Fehler: titel und auftrag noetig."
    if not isinstance(schritte, list) or not schritte:
        return "Fehler: schritte muss eine Liste mit mindestens einem Schritt sein."
    schritte = [str(s).strip() for s in schritte if str(s).strip()][:JOB_MAX_SCHRITTE]
    try:
        conn = pg_conn()
        with conn, conn.cursor() as cur:
            cur.execute("INSERT INTO jobs (titel, auftrag, schritte) VALUES (%s, %s, %s) RETURNING id",
                        (titel[:200], auftrag, json.dumps(schritte, ensure_ascii=False)))
            jid = cur.fetchone()[0]
        conn.close()
        print(f"  [jobs] #{jid} angelegt: {titel} ({len(schritte)} Schritte)", flush=True)
        return (f"Auftrag #{jid} angelegt: {titel}\n"
                f"Schritte: {len(schritte)}\n" +
                "\n".join(f"  {i+1}. {s}" for i, s in enumerate(schritte)) +
                "\n\nIch arbeite ihn im Hintergrund ab. Frag mit job_status nach dem Stand.")
    except Exception as e:
        return f"Fehler: {e}"


def tool_job_status(inp):
    jid = inp.get("id")
    try:
        conn = pg_conn()
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if jid:
                cur.execute("SELECT * FROM jobs WHERE id = %s", (int(jid),))
                rows = cur.fetchall()
            else:
                cur.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT 8")
                rows = cur.fetchall()
        conn.close()
    except Exception as e:
        return f"Fehler: {e}"
    if not rows:
        return "Keine Auftraege vorhanden."
    out = []
    for r in rows:
        schritte = r["schritte"] or []
        n = len(schritte)
        i = r["aktueller_schritt"] or 0
        zeile = f"#{r['id']} [{r['status']}] {r['titel']} — Schritt {min(i+1, n)}/{n}"
        if r["status"] == "fertig" and r.get("ergebnis"):
            zeile += f"\n   Ergebnis: {r['ergebnis'][:400]}"
        elif r["status"] == "laeuft" and i < n:
            zeile += f"\n   Laeuft gerade: {schritte[i]}"
        elif r["status"] == "fehler":
            zeile += f"\n   Abgebrochen: {(r.get('ergebnis') or '')[:200]}"
        out.append(zeile)
    return "\n".join(out)


def tool_job_abbrechen(inp):
    jid = inp.get("id")
    if not jid:
        return "Fehler: id noetig."
    _job_update(int(jid), status="abgebrochen")
    return f"Auftrag #{jid} abgebrochen."


JOB_SYS = """Du bist JARVIS und arbeitest EINEN Schritt eines groesseren Auftrags ab.
Nutze die Tools, um den Schritt wirklich auszufuehren — nicht ankuendigen, sondern tun.
Antworte am Ende KURZ und faktisch: was hast du herausgefunden oder erledigt.
Diese Antwort wird als Arbeitsnotiz gespeichert und ist die Grundlage fuer die naechsten Schritte.
Keine Floskeln, keine Wiederholung des Auftrags — nur die Substanz."""


def _job_schritt_ausfuehren(job, schritt):
    """Ein Schritt = eigener, begrenzter Agent-Lauf mit frischem Kontext."""
    notizen = (job.get("notizen") or "")[-JOB_NOTIZ_LIMIT:]
    prompt = (f"GESAMT-AUFTRAG: {job['auftrag']}\n\n"
              f"BISHERIGE ARBEITSNOTIZEN:\n{notizen or '(noch keine)'}\n\n"
              f"DEIN SCHRITT JETZT: {schritt}")
    messages = [{"role": "user", "content": prompt}]
    final = ""
    for _ in range(JOB_RUNDEN):
        resp = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS,
                                      system=JOB_SYS, tools=TOOLS_CACHED, messages=messages)
        try:
            track_cost(MODEL, resp.usage.input_tokens, resp.usage.output_tokens,
                       getattr(resp.usage, 'cache_read_input_tokens', 0) or 0,
                       getattr(resp.usage, 'cache_creation_input_tokens', 0) or 0)
        except Exception:
            pass
        txt = "".join(b.text for b in resp.content if b.type == "text").strip()
        if txt:
            final = txt
        if resp.stop_reason != "tool_use":
            break
        a_content, t_results = [], []
        for block in resp.content:
            if block.type == "text":
                a_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                a_content.append({"type": "tool_use", "id": block.id,
                                  "name": block.name, "input": block.input})
                res = run_tool(block.name, block.input or {})
                print(f"    [job-tool] {block.name} -> {str(res)[:70]}", flush=True)
                t_results.append({"type": "tool_result", "tool_use_id": block.id, "content": res})
        messages.append({"role": "assistant", "content": a_content})
        messages.append({"role": "user", "content": t_results})
    return final or "(kein Ergebnis)"


def job_worker():
    """Arbeitet offene Auftraege Schritt fuer Schritt ab. Fortschritt wird persistiert."""
    while True:
        try:
            job = _job_holen()
            if not job:
                time.sleep(15)
                continue
            jid = job["id"]
            schritte = job["schritte"] or []
            i = job["aktueller_schritt"] or 0
            if i >= len(schritte):
                _job_update(jid, status="fertig")
                continue
            if job["status"] == "offen":
                _job_update(jid, status="laeuft")
            schritt = schritte[i]
            print(f"  [jobs] #{jid} Schritt {i+1}/{len(schritte)}: {schritt}", flush=True)
            try:
                ergebnis = _job_schritt_ausfuehren(job, schritt)
            except Exception as e:
                print(f"  [jobs] #{jid} Fehler: {type(e).__name__}: {e}", flush=True)
                _job_update(jid, status="fehler", ergebnis=f"{type(e).__name__}: {e}")
                continue
            notizen = (job.get("notizen") or "") + f"\n\n### Schritt {i+1}: {schritt}\n{ergebnis}"
            notizen = notizen[-JOB_NOTIZ_LIMIT:]
            neuer_index = i + 1
            if neuer_index >= len(schritte):
                _job_update(jid, notizen=notizen, aktueller_schritt=neuer_index,
                            status="fertig", ergebnis=ergebnis[:4000])
                print(f"  [jobs] #{jid} FERTIG", flush=True)
                try:
                    tool_remember({"title": f"Auftrag: {job['titel']}",
                                   "content": f"{job['auftrag']}\n\nErgebnis:\n{notizen[-3000:]}"})
                except Exception:
                    pass
            else:
                _job_update(jid, notizen=notizen, aktueller_schritt=neuer_index)
        except Exception as e:
            print(f"  [jobs] Worker: {type(e).__name__}: {e}", flush=True)
            time.sleep(10)


# ── GITHUB (read-only: lesen, nie schreiben) ─────────────────
def _gh(path, params=None):
    if not GITHUB_TOKEN:
        return None, "GitHub nicht konfiguriert (GITHUB_TOKEN fehlt)."
    try:
        r = requests.get(f"{GH_API}{path}", params=params or {}, timeout=30,
                         headers={"Authorization": f"Bearer {GITHUB_TOKEN}",
                                  "Accept": "application/vnd.github+json",
                                  "X-GitHub-Api-Version": "2022-11-28"})
        if r.status_code == 404:
            return None, "Nicht gefunden (Pfad/Repo pruefen)."
        if r.status_code == 401:
            return None, "GitHub-Token ungueltig oder abgelaufen."
        if r.status_code >= 400:
            return None, f"GitHub-Fehler {r.status_code}: {r.text[:150]}"
        return r.json(), None
    except Exception as e:
        return None, f"GitHub nicht erreichbar: {type(e).__name__}"


def _repo_full(repo):
    repo = (repo or "").strip()
    return repo if "/" in repo else f"{GITHUB_USER}/{repo}"


def tool_github_repos(inp):
    data, err = _gh("/user/repos", {"sort": "updated", "per_page": 30, "affiliation": "owner,collaborator"})
    if err:
        return err
    if not data:
        return "Keine Repos gefunden."
    lines = []
    for r in data[:30]:
        upd = (r.get("updated_at") or "")[:10]
        priv = "privat" if r.get("private") else "oeffentlich"
        lang = r.get("language") or "-"
        lines.append(f"- {r.get('full_name')} ({priv}, {lang}, aktualisiert {upd})")
    return f"{len(data)} Repositories:\n" + "\n".join(lines)


def tool_github_browse(inp):
    repo = _repo_full(inp.get("repo"))
    path = (inp.get("path") or "").strip().strip("/")
    data, err = _gh(f"/repos/{repo}/contents/{path}")
    if err:
        return err
    if isinstance(data, dict):
        return f"'{path}' ist eine Datei — nutze github_read."
    dirs = [d for d in data if d.get("type") == "dir"]
    files = [d for d in data if d.get("type") == "file"]
    out = [f"{repo}/{path or ''} — {len(dirs)} Ordner, {len(files)} Dateien"]
    for d in sorted(dirs, key=lambda x: x["name"]):
        out.append(f"  [DIR ] {d['name']}/")
    for f in sorted(files, key=lambda x: x["name"]):
        kb = round((f.get("size") or 0) / 1024, 1)
        out.append(f"  [FILE] {f['name']} ({kb} KB)")
    return "\n".join(out[:80])


def tool_github_read(inp):
    repo = _repo_full(inp.get("repo"))
    path = (inp.get("path") or "").strip().strip("/")
    if not path:
        return "Fehler: Dateipfad fehlt."
    data, err = _gh(f"/repos/{repo}/contents/{path}")
    if err:
        return err
    if isinstance(data, list):
        return f"'{path}' ist ein Ordner — nutze github_browse."
    if (data.get("size") or 0) > 400000:
        return f"Datei zu gross ({round(data['size']/1024)} KB)."
    try:
        import base64
        content = base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
    except Exception as e:
        return f"Konnte Datei nicht dekodieren ({type(e).__name__}) — evtl. Binaerdatei."
    limit = min(int(inp.get("max_zeichen") or 12000), 20000)
    if len(content) > limit:
        content = content[:limit] + f"\n\n[... gekuerzt, insgesamt {len(content)} Zeichen]"
    return f"=== {repo}/{path} ===\n{content}"


def tool_github_search(inp):
    query = (inp.get("query") or "").strip()
    if not query:
        return "Fehler: leere Suche."
    repo = inp.get("repo")
    q = query + (f" repo:{_repo_full(repo)}" if repo else f" user:{GITHUB_USER}")
    data, err = _gh("/search/code", {"q": q, "per_page": 20})
    if err:
        return err
    items = data.get("items", []) if isinstance(data, dict) else []
    if not items:
        return "Keine Treffer."
    lines = [f"{data.get('total_count', len(items))} Treffer (max 20 gezeigt):"]
    for it in items[:20]:
        lines.append(f"- {it.get('repository', {}).get('full_name')}/{it.get('path')}")
    return "\n".join(lines)


def tool_github_commits(inp):
    repo = _repo_full(inp.get("repo"))
    params = {"per_page": min(int(inp.get("anzahl") or 10), 30)}
    if inp.get("pfad"):
        params["path"] = inp["pfad"]
    data, err = _gh(f"/repos/{repo}/commits", params)
    if err:
        return err
    if not data:
        return "Keine Commits gefunden."
    lines = [f"Letzte Commits in {repo}:"]
    for c in data:
        commit = c.get("commit", {})
        datum = (commit.get("author", {}).get("date") or "")[:10]
        msg = (commit.get("message") or "").split("\n")[0][:80]
        lines.append(f"- {datum} {msg}")
    return "\n".join(lines)


# ── iCLOUD-KALENDER (CalDAV, strikt read-only) ───────────────
def _google_termine(days):
    """Liest Termine aus den privaten iCal-Adressen (Google Kalender). Read-only."""
    from datetime import timedelta, date as _date
    import icalendar
    try:
        import recurring_ical_events
        wiederholungen = True
    except Exception:
        wiederholungen = False

    start = datetime.now()
    ende = start + timedelta(days=days)
    events = []
    fehler = []

    for url in GOOGLE_ICS[:5]:
        try:
            r = requests.get(url, timeout=30)
            if r.status_code >= 400:
                fehler.append(f"HTTP {r.status_code}")
                continue
            cal = icalendar.Calendar.from_ical(r.text)
        except Exception as e:
            fehler.append(f"{type(e).__name__}")
            continue

        name = str(cal.get("X-WR-CALNAME") or "Kalender")

        if wiederholungen:
            try:
                treffer = recurring_ical_events.of(cal).between(start, ende)
            except Exception:
                treffer = [c for c in cal.walk("VEVENT")]
        else:
            treffer = [c for c in cal.walk("VEVENT")]

        for ev in treffer:
            try:
                dt = ev.get("DTSTART").dt
                summ = str(ev.get("SUMMARY") or "(ohne Titel)")
                ort = str(ev.get("LOCATION") or "").strip()
                if isinstance(dt, datetime):
                    naiv = dt.replace(tzinfo=None) if dt.tzinfo else dt
                    if not (start <= naiv <= ende):
                        continue
                    label = naiv.strftime("%a %d.%m. %H:%M")
                    dte = ev.get("DTEND")
                    if dte is not None and isinstance(dte.dt, datetime):
                        e2 = dte.dt.replace(tzinfo=None) if dte.dt.tzinfo else dte.dt
                        label += e2.strftime("-%H:%M")
                    sortier = naiv
                else:
                    tag = datetime.combine(dt, datetime.min.time())
                    if not (start.replace(hour=0, minute=0) <= tag <= ende):
                        continue
                    label = tag.strftime("%a %d.%m.") + " ganztaegig"
                    sortier = tag
                zeile = f"{label} | {summ}"
                if ort:
                    zeile += f" ({ort[:40]})"
                zeile += f" [{name}]"
                events.append((sortier, zeile))
            except Exception:
                continue

    if not events:
        if fehler:
            return f"Kalender nicht lesbar: {', '.join(fehler[:3])}"
        return f"Keine Termine in den naechsten {days} Tagen."
    events.sort(key=lambda x: x[0])
    kopf = f"Termine der naechsten {days} Tage:"
    if not wiederholungen:
        kopf += " (Serientermine evtl. unvollstaendig)"
    return kopf + "\n" + "\n".join(z for _, z in events[:40])


def tool_check_calendar(inp):
    days = min(max(int(inp.get("days") or 7), 1), 30)
    if GOOGLE_ICS:
        return _google_termine(days)
    if not ICLOUD_USER or not ICLOUD_PASS:
        return ("Kein Kalender konfiguriert — GOOGLE_ICS_URLS (Google) oder "
                "ICLOUD_USER/ICLOUD_PASS (iCloud) in der .env setzen.")
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
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True,
                            socket_keepalive=True, health_check_interval=20,
                            retry_on_timeout=True, socket_timeout=30)
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
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True,
                            socket_keepalive=True, health_check_interval=20,
                            retry_on_timeout=True, socket_timeout=30)
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
    if name == "buroflow_zahlen":
        return tool_buroflow_zahlen(inp)
    if name == "skill_suchen":
        return tool_skill_suchen(inp)
    if name == "skill_laden":
        return tool_skill_laden(inp)
    if name == "persona_laden":
        return tool_persona_laden(inp)
    if name == "job_anlegen":
        return tool_job_anlegen(inp)
    if name == "job_status":
        return tool_job_status(inp)
    if name == "job_abbrechen":
        return tool_job_abbrechen(inp)
    if name == "github_repos":
        return tool_github_repos(inp)
    if name == "github_browse":
        return tool_github_browse(inp)
    if name == "github_read":
        return tool_github_read(inp)
    if name == "github_search":
        return tool_github_search(inp)
    if name == "github_commits":
        return tool_github_commits(inp)
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


MEMORY_TRIGGER = re.compile(
    r"(merk(e|en)?\s+(dir|es|das|alles)|merk\s+dir|speicher(e|n|st)?\b|behalte?\b"
    r"|lern(e|en)?\s+(daraus|davon)|ins\s+ged(ae|\u00e4)chtnis|praeg|pr\u00e4g"
    r"|halt(e)?\s+.{0,12}fest|schreib(e)?\s+.{0,12}auf|notier)", re.I)


def _verlangt_speichern(text):
    return bool(MEMORY_TRIGGER.search(text or ""))


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
    tool_benutzt = False
    nachfass_zahl = 0
    genutzte_tools = set()
    braucht_remember = _verlangt_speichern(user_text)
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
        _txt = "".join(text_parts).strip()
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
                genutzte_tools.add(block.name)
                result = run_tool(block.name, block.input or {})
                print(f"  [tool] {block.name} -> {result[:100]}", flush=True)
                tool_results.append({
                    "type": "tool_result", "tool_use_id": block.id,
                    "content": result,
                })
        messages.append({"role": "assistant", "content": assistant_content})
        messages.append({"role": "user", "content": tool_results})

    # Auftrag verlangte Speichern, aber remember wurde nicht aufgerufen -> ERZWINGEN
    if braucht_remember and "remember" not in genutzte_tools:
        print("  [zwang] Auftrag verlangte Speichern — erzwinge remember", flush=True)
        try:
            messages.append({"role": "assistant", "content": final_text or "..."})
            messages.append({"role": "user", "content":
                "Du hast noch nichts gespeichert. Rufe JETZT remember auf und sichere die "
                "wichtigsten Erkenntnisse (aussagekraeftiger Titel, substanzieller Inhalt). "
                "Bei mehreren Themen mehrere Aufrufe."})
            for versuch in range(3):
                rz = client.messages.create(
                    model=MODEL, max_tokens=MAX_TOKENS, system=SYS_CACHED,
                    tools=TOOLS_CACHED, messages=messages,
                    tool_choice={"type": "tool", "name": "remember"})
                try:
                    track_cost(MODEL, rz.usage.input_tokens, rz.usage.output_tokens,
                               getattr(rz.usage, 'cache_read_input_tokens', 0) or 0,
                               getattr(rz.usage, 'cache_creation_input_tokens', 0) or 0)
                except Exception:
                    pass
                a_content, t_results, gespeichert = [], [], []
                for block in rz.content:
                    if block.type == "text":
                        a_content.append({"type": "text", "text": block.text})
                    elif block.type == "tool_use":
                        a_content.append({"type": "tool_use", "id": block.id,
                                          "name": block.name, "input": block.input})
                        res = run_tool(block.name, block.input or {})
                        print(f"  [zwang-tool] {block.name} -> {str(res)[:80]}", flush=True)
                        if block.name == "remember":
                            gespeichert.append((block.input or {}).get("title", "?"))
                            genutzte_tools.add("remember")
                        t_results.append({"type": "tool_result", "tool_use_id": block.id, "content": res})
                if not t_results:
                    break
                messages.append({"role": "assistant", "content": a_content})
                messages.append({"role": "user", "content": t_results})
                if gespeichert:
                    titel = ", ".join(gespeichert)
                    if final_text and "gespeichert" not in final_text.lower():
                        final_text = final_text.rstrip(".") + f"\n\nGespeichert: {titel}"
                    elif not final_text:
                        final_text = f"Gespeichert: {titel}"
                    break
        except Exception as e:
            print(f"  [zwang] {type(e).__name__}: {e}", flush=True)

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
    # Ins Kurzzeitgedaechtnis nur die saubere Antwort (ohne Tool-Zwischenschritte)
    history.append({"role": "assistant", "content": final_text})
    return final_text


# ── HAUPTSCHLEIFE ────────────────────────────────────────────
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
    print("=" * 58, flush=True)
    print("  JARVIS CORE v7.9 — GEDAECHTNIS, MAIL, WEB, KALENDER, GITHUB, BOTS", flush=True)
    print(f"  Modell    : {MODEL}", flush=True)
    print(f"  Extraktion: {EXTRACT_MODEL}", flush=True)
    print(f"  Embeddings: {EMBED_MODEL if oai else 'DEAKTIVIERT (kein Key)'}", flush=True)
    print(f"  Nightly   : taeglich {NIGHTLY_HOUR:02d}:00", flush=True)
    _kal = f"Google ({len(GOOGLE_ICS)} Kalender)" if GOOGLE_ICS else ("iCloud" if (ICLOUD_USER and ICLOUD_PASS) else "nicht konfiguriert")
    print(f"  Kalender  : {_kal}", flush=True)
    print(f"  GitHub    : {'aktiv (' + GITHUB_USER + ')' if GITHUB_TOKEN else 'nicht konfiguriert'}", flush=True)
    print(f"  Bueroflow : {'DB verbunden' if SUPABASE_URL else 'nicht konfiguriert'}", flush=True)
    print(f"  Auftraege : max {JOB_MAX_SCHRITTE} Schritte, {JOB_RUNDEN} Runden je Schritt", flush=True)
    print(f"  Skills    : {len(SKILL_INDEX)} Anleitungen, {len(PERSONA_INDEX)} Personas", flush=True)
    for k, acc in MAIL_ACCOUNTS.items():
        status = "aktiv" if (acc["user"] and acc["pass"]) else "nicht konfiguriert"
        print(f"  Mail {k:<6}: {status}", flush=True)
    print("=" * 58, flush=True)

    skills_indexieren()
    init_jobs()
    threading.Thread(target=job_worker, daemon=True).start()

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
                _antwort_senden(r, reply_q, "Leere Anfrage.")
                continue

            low = text.lower()
            if low in ("reset", "vergiss alles", "speicher leeren"):
                r.delete(HISTORY_KEY)
                _antwort_senden(r, reply_q, "Kurzzeitgedaechtnis geleert. (Langzeitgedaechtnis bleibt.)")
                continue

            if low in ("konsolidiere", "konsolidieren", "nightly"):
                result = consolidate(r)
                _antwort_senden(r, reply_q, result)
                continue

            if low.startswith("stil "):
                acct = low.split(None, 1)[1].strip()
                _antwort_senden(r, reply_q, analyze_style(acct))
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

            _antwort_senden(r, reply_q, answer)

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"  [loop] {type(e).__name__}: {e}", flush=True)
            time.sleep(1)


if __name__ == "__main__":
    main()
