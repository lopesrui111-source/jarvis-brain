#!/usr/bin/env python3
"""
TELEGRAM-BRUECKE
- Empfaengt Nachrichten per Long-Polling (kein oeffentlicher Endpunkt noetig)
- Leitet sie ueber den Redis-Bus an JARVIS oder einen der Bots
- Schickt die Antwort zurueck, lange Texte automatisch geteilt
- Nimmt AUSSCHLIESSLICH Nachrichten von Ruis Chat-ID an
"""

import os
import re
import sys
import json
import time
import uuid
import html

import redis
import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = str(os.getenv("TELEGRAM_CHAT_ID", "")).strip()
API = f"https://api.telegram.org/bot{TOKEN}"

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

ANTWORT_MAX_SEK = int(os.getenv("TELEGRAM_TIMEOUT", "900"))   # 15 Minuten
TG_LIMIT = 3900

ZIELE = {
    "jarvis":    {"label": "JARVIS",    "inbox": "jarvis:inbox",        "reply": "jarvis:reply:{id}"},
    "ceo":       {"label": "CEO",       "inbox": "bot:ceo:inbox",       "reply": "bot:ceo:reply:{id}"},
    "marketing": {"label": "MARKETING", "inbox": "bot:marketing:inbox", "reply": "bot:marketing:reply:{id}"},
    "immo":      {"label": "IMMO",      "inbox": "bot:immo:inbox",      "reply": "bot:immo:reply:{id}"},
    "seo":       {"label": "SEO",       "inbox": "bot:seo:inbox",       "reply": "bot:seo:reply:{id}"},
}
ZIEL_KEY = "telegram:ziel"

HILFE = """JARVIS am Handy

Einfach schreiben — die Frage geht an JARVIS.

Gezielt an einen Bot (einmalig):
/ceo Wie steht Bueroflow da?
/immo check meine immoscout mails
/seo recherche
/marketing render ein creative

Dauerhaft umstellen:
/ziel ceo      (zurueck mit /ziel jarvis)

Weitere Befehle:
/status    Systemstatus und Kosten
/jobs      laufende Auftraege
/reset     Kurzzeitgedaechtnis des aktuellen Ziels leeren
/hilfe     diese Uebersicht"""


def rds():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True,
                       socket_connect_timeout=5, socket_timeout=30,
                       socket_keepalive=True, health_check_interval=20)


def tg(methode, **daten):
    try:
        r = requests.post(f"{API}/{methode}", json=daten, timeout=40)
        if r.status_code >= 400:
            print(f"  [tg] {methode}: HTTP {r.status_code} {r.text[:120]}", flush=True)
            return None
        return r.json().get("result")
    except Exception as e:
        print(f"  [tg] {methode}: {type(e).__name__}", flush=True)
        return None


def senden(text, chat=None):
    """Verschickt Text, teilt lange Antworten an Zeilengrenzen."""
    chat = chat or CHAT_ID
    text = (text or "").strip() or "(leer)"
    teile, aktuell = [], ""
    for zeile in text.split("\n"):
        if len(aktuell) + len(zeile) + 1 > TG_LIMIT:
            if aktuell:
                teile.append(aktuell)
            while len(zeile) > TG_LIMIT:
                teile.append(zeile[:TG_LIMIT])
                zeile = zeile[TG_LIMIT:]
            aktuell = zeile
        else:
            aktuell = (aktuell + "\n" + zeile) if aktuell else zeile
    if aktuell:
        teile.append(aktuell)
    for i, t in enumerate(teile):
        kopf = "" if i == 0 else f"(Teil {i + 1}/{len(teile)})\n"
        tg("sendMessage", chat_id=chat, text=kopf + t, disable_web_page_preview=True)
        if len(teile) > 1:
            time.sleep(0.4)


def tippt(chat=None):
    tg("sendChatAction", chat_id=chat or CHAT_ID, action="typing")


def ziel_holen(r):
    try:
        z = r.get(ZIEL_KEY)
        return z if z in ZIELE else "jarvis"
    except Exception:
        return "jarvis"


def ziel_setzen(r, ziel):
    try:
        r.set(ZIEL_KEY, ziel)
    except Exception:
        pass


def frage_bot(r, ziel, text):
    """Auftrag auf den Bus legen und auf die Antwort warten (mit Tipp-Anzeige)."""
    meta = ZIELE[ziel]
    req_id = str(uuid.uuid4())
    try:
        r.rpush(meta["inbox"], json.dumps({"id": req_id, "text": text}, ensure_ascii=False))
    except Exception as e:
        return f"Konnte den Auftrag nicht absetzen: {type(e).__name__}"

    key = meta["reply"].format(id=req_id)
    ende = time.time() + ANTWORT_MAX_SEK
    verbindung = r
    while time.time() < ende:
        try:
            res = verbindung.blpop(key, timeout=5)
            if res:
                return res[1]
        except Exception:
            try:
                verbindung = rds()
            except Exception:
                pass
        tippt()
    return (f"{meta['label']} antwortet seit {ANTWORT_MAX_SEK // 60} Minuten nicht. "
            f"Läuft der Container? (docker compose logs jarvis-{'core' if ziel == 'jarvis' else ziel} --tail 20)")


def status_text(r):
    zeilen = ["SYSTEMSTATUS"]
    try:
        listener = sum(1 for c in r.client_list() if c.get("cmd", "").lower().startswith("blpop"))
        zeilen.append(f"Aktive Bots: {listener}/{len(ZIELE)}")
        offen = sum(r.llen(z["inbox"]) for z in ZIELE.values())
        zeilen.append(f"Offene Auftraege in der Warteschlange: {offen}")
    except Exception as e:
        zeilen.append(f"Redis: {type(e).__name__}")
    try:
        import psycopg2
        conn = psycopg2.connect(host=os.getenv("POSTGRES_HOST", "postgres"),
                                port=int(os.getenv("POSTGRES_PORT", "5432")),
                                user=os.getenv("POSTGRES_USER", "jarvis"),
                                password=os.getenv("POSTGRES_PASSWORD", ""),
                                dbname=os.getenv("POSTGRES_DB", "jarvis_brain"),
                                connect_timeout=5)
        with conn, conn.cursor() as cur:
            cur.execute("SELECT COALESCE(SUM(cost_usd),0) FROM cost_ledger WHERE created_at::date = CURRENT_DATE")
            heute = float(cur.fetchone()[0])
            cur.execute("SELECT COALESCE(SUM(cost_usd),0) FROM cost_ledger "
                        "WHERE date_trunc('month', created_at) = date_trunc('month', now())")
            monat = float(cur.fetchone()[0])
        conn.close()
        zeilen.append(f"Kosten heute: ${heute:.4f}")
        zeilen.append(f"Kosten Monat: ${monat:.4f}")
    except Exception as e:
        zeilen.append(f"Datenbank: {type(e).__name__}")
    return "\n".join(zeilen)


def verarbeite(r, text, chat):
    text = (text or "").strip()
    if not text:
        return

    # ── Befehle ──
    if text.startswith("/"):
        befehl = text.split()[0].lower().lstrip("/").split("@")[0]
        rest = text[len(text.split()[0]):].strip()

        if befehl in ("start", "hilfe", "help"):
            senden(HILFE, chat)
            return
        if befehl == "status":
            senden(status_text(r), chat)
            return
        if befehl == "jobs":
            tippt(chat)
            senden(frage_bot(r, "jarvis", "job status"), chat)
            return
        if befehl == "ziel":
            neu = rest.strip().lower()
            if neu in ZIELE:
                ziel_setzen(r, neu)
                senden(f"Ziel umgestellt auf {ZIELE[neu]['label']}.", chat)
            else:
                senden("Moegliche Ziele: " + ", ".join(ZIELE), chat)
            return
        if befehl == "reset":
            ziel = ziel_holen(r)
            senden(frage_bot(r, ziel, "reset"), chat)
            return
        if befehl in ZIELE:
            if not rest:
                ziel_setzen(r, befehl)
                senden(f"Ziel umgestellt auf {ZIELE[befehl]['label']}. Schreib einfach los.", chat)
                return
            tippt(chat)
            antwort = frage_bot(r, befehl, rest)
            senden(f"[{ZIELE[befehl]['label']}]\n{antwort}", chat)
            return
        senden(f"Unbekannter Befehl. {HILFE}", chat)
        return

    # ── normale Nachricht ans aktuelle Ziel ──
    ziel = ziel_holen(r)
    tippt(chat)
    antwort = frage_bot(r, ziel, text)
    kopf = "" if ziel == "jarvis" else f"[{ZIELE[ziel]['label']}]\n"
    senden(kopf + antwort, chat)


def main():
    print("=" * 58, flush=True)
    print("  TELEGRAM-BRUECKE", flush=True)
    if not TOKEN or not CHAT_ID:
        print("  FEHLER: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID fehlen", flush=True)
        sys.exit(1)
    print(f"  Erlaubte Chat-ID: {CHAT_ID}", flush=True)
    print(f"  Ziele: {', '.join(ZIELE)}", flush=True)
    print("=" * 58, flush=True)

    ich = tg("getMe") or {}
    if ich:
        print(f"  Bot: @{ich.get('username')} ({ich.get('first_name')})", flush=True)

    r = None
    for _ in range(30):
        try:
            r = rds()
            r.ping()
            print("  [redis] verbunden", flush=True)
            break
        except Exception:
            time.sleep(2)
    if r is None:
        sys.exit(1)

    senden("JARVIS ist erreichbar. /hilfe zeigt, was geht.")
    offset = 0
    print("  Warte auf Nachrichten.\n", flush=True)

    while True:
        try:
            updates = tg("getUpdates", offset=offset, timeout=30,
                         allowed_updates=["message"]) or []
            for u in updates:
                offset = u.get("update_id", 0) + 1
                msg = u.get("message") or {}
                chat = str((msg.get("chat") or {}).get("id", ""))
                text = msg.get("text") or ""
                if not text:
                    continue
                if chat != CHAT_ID:
                    print(f"  [tg] Fremde Chat-ID {chat} ignoriert", flush=True)
                    continue
                print(f"  Du: {text[:80]}", flush=True)
                try:
                    verarbeite(r, text, chat)
                except Exception as e:
                    print(f"  [fehler] {type(e).__name__}: {e}", flush=True)
                    senden(f"Fehler: {type(e).__name__}: {str(e)[:200]}", chat)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"  [loop] {type(e).__name__}: {e}", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
