#!/usr/bin/env python3
"""
ARBEITSPROTOKOLL — gemeinsames Gedaechtnis fuer Taetigkeiten
Jeder Bot traegt ein, was er produziert hat. JARVIS (und jeder andere Bot)
kann nachsehen, statt zu behaupten, er wisse nichts davon.

Einbinden:
    from protokoll import protokoll_init, protokoll_melden
    protokoll_init()                                   # einmal beim Start
    protokoll_melden("marketing", "Creative erstellt",
                     "LinkedIn Mahnflow", "assets/xy.png")

Fuer JARVIS zusaetzlich:
    from protokoll import PROTOKOLL_TOOLS, protokoll_tool_ausfuehren
"""

import os
import threading
from datetime import datetime

import psycopg2
import psycopg2.extras

_PG = dict(host=os.getenv("POSTGRES_HOST", "postgres"),
           port=int(os.getenv("POSTGRES_PORT", "5432")),
           user=os.getenv("POSTGRES_USER", "jarvis"),
           password=os.getenv("POSTGRES_PASSWORD", ""),
           dbname=os.getenv("POSTGRES_DB", "jarvis_brain"),
           connect_timeout=5)


def _conn():
    return psycopg2.connect(**_PG)


def protokoll_init():
    try:
        conn = _conn()
        with conn, conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS arbeit_log (
                id SERIAL PRIMARY KEY,
                bot TEXT,
                aktion TEXT,
                ergebnis TEXT,
                datei TEXT,
                created_at TIMESTAMPTZ DEFAULT now())""")
            cur.execute("CREATE INDEX IF NOT EXISTS arbeit_log_zeit ON arbeit_log (created_at DESC)")
        conn.close()
        return True
    except Exception as e:
        print(f"  [protokoll] {e}", flush=True)
        return False


def protokoll_melden(bot, aktion, ergebnis="", datei=""):
    """Traegt eine erledigte Arbeit ein. Laeuft im Hintergrund, blockiert nie."""
    def _work():
        try:
            conn = _conn()
            with conn, conn.cursor() as cur:
                cur.execute("INSERT INTO arbeit_log (bot, aktion, ergebnis, datei) "
                            "VALUES (%s, %s, %s, %s)",
                            (bot[:40], (aktion or "")[:120], (ergebnis or "")[:600], (datei or "")[:250]))
            conn.close()
        except Exception as e:
            print(f"  [protokoll] {type(e).__name__}: {e}", flush=True)
    threading.Thread(target=_work, daemon=True).start()


def protokoll_lesen(stunden=24, bot=None, limit=25):
    try:
        conn = _conn()
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if bot:
                cur.execute("SELECT * FROM arbeit_log WHERE created_at > now() - make_interval(hours => %s) "
                            "AND bot = %s ORDER BY id DESC LIMIT %s", (int(stunden), bot, int(limit)))
            else:
                cur.execute("SELECT * FROM arbeit_log WHERE created_at > now() - make_interval(hours => %s) "
                            "ORDER BY id DESC LIMIT %s", (int(stunden), int(limit)))
            rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        return [{"bot": "system", "aktion": f"Protokoll nicht lesbar: {type(e).__name__}",
                 "ergebnis": "", "datei": "", "created_at": datetime.now()}]


def tool_was_lief(inp):
    stunden = min(max(int(inp.get("stunden") or 24), 1), 336)
    bot = (inp.get("bot") or "").strip().lower() or None
    eintraege = protokoll_lesen(stunden, bot)
    if not eintraege:
        wer = f" von {bot}" if bot else ""
        return f"In den letzten {stunden} Stunden wurde nichts{wer} protokolliert."
    zeilen = [f"Arbeiten der letzten {stunden} Stunden:"]
    for e in eintraege:
        zeit = e["created_at"].strftime("%d.%m. %H:%M") if hasattr(e["created_at"], "strftime") else ""
        zeile = f"- [{zeit}] {e['bot']}: {e['aktion']}"
        if e.get("ergebnis"):
            zeile += f" — {e['ergebnis'][:180]}"
        if e.get("datei"):
            zeile += f"  (vault/{e['datei']})"
        zeilen.append(zeile)
    return "\n".join(zeilen)


PROTOKOLL_TOOLS = [
    {
        "name": "was_lief",
        "description": ("Zeigt, was die Bots zuletzt tatsaechlich getan haben — welche Creatives, "
                        "Entwuerfe, Analysen und Berichte entstanden sind. Nutze das IMMER, bevor du "
                        "sagst, du wuesstest nichts von einer Arbeit: die anderen Bots tragen hier ein, "
                        "was sie produziert haben."),
        "input_schema": {"type": "object", "properties": {
            "stunden": {"type": "integer", "description": "Zeitraum (Standard 24, max 336)"},
            "bot": {"type": "string", "description": "auf einen Bot begrenzen: ceo, marketing, immo, seo"}}},
    },
]

PROTOKOLL_PROMPT = """- WAS DIE ANDEREN TUN: Alle Bots tragen ihre Ergebnisse in ein gemeinsames Arbeitsprotokoll ein.
  Fragt Rui nach etwas, das ein Bot erstellt hat ("wo ist das Creative?", "was habt ihr gemacht?"),
  rufst du was_lief auf — nicht behaupten, du wuesstest davon nichts."""


def protokoll_tool_ausfuehren(name, inp):
    if name == "was_lief":
        return tool_was_lief(inp)
    return None
