#!/usr/bin/env python3
"""
REGIE-BOT — Kopf des JARVIS Studio-Teams
- Queue: bot:regie:inbox / bot:regie:reply:<id>
- Entwickelt Video-Konzepte im Vibe-Motion-Stil (Hook, Story-Arc, Plattform)
- Wertet Trends aus (Websuche), schlaegt Hooks vor
- Generiert die Vibe-Motion-Clips SELBST ueber die Higgsfield-API
- WICHTIG: KI-Clips zeigen NIE echtes Produkt/Logo/UI (das kommt vom Recorder).
  KI macht nur atmosphaerische Vibe-Teile (Motion, Uebergaenge, Stimmung).

Ablauf eines Clips: Text -> Bild (Higgsfield) -> Bild animieren -> Video-URL.
Video-URLs werden nur als Text gespeichert, nie ins Kontextfenster geladen.
"""
import os
import sys
import json
import time
import uuid
from datetime import datetime, date

import redis
import requests
from anthropic import Anthropic

import higgsfield_client as hf

BOT_NAME = "regie"
AKTUELLES_JAHR = date.today().year

CLAUDE_KEY = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY", "")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
PG_HOST = os.getenv("POSTGRES_HOST", "postgres")
PG_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
PG_USER = os.getenv("POSTGRES_USER", "jarvis")
PG_PASS = os.getenv("POSTGRES_PASSWORD", "")
PG_DB   = os.getenv("POSTGRES_DB", "jarvis_brain")

MODEL      = os.getenv("ORCHESTRATOR_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = 3000
MAX_HISTORY = 8
MAX_TOOL_ROUNDS = 14
VAULT_DIR = "/app/vault"
CLIP_DIR  = os.path.join(VAULT_DIR, "clips")   # hier landen Clip-Infos (JSON)

INBOX_KEY = "bot:regie:inbox"
REPLY_KEY = "bot:regie:reply:{id}"

# Tages-Budget fuer Higgsfield-Generierungen (Schutz vor Credit-Verbrennung)
MAX_CLIPS_PRO_LAUF = int(os.getenv("REGIE_MAX_CLIPS", "6"))

client = Anthropic(api_key=CLAUDE_KEY)

# Laufzeit-Zaehler pro Anfrage
CLIP_ZAEHLER = {"n": 0}
TOOL_LOG = []


def log(m): print(f"  {m}", flush=True)


def pg():
    import psycopg2
    return psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER,
                            password=PG_PASS, dbname=PG_DB, connect_timeout=5)


def arbeit_log(aktion, ergebnis, datei=""):
    try:
        conn = pg()
        with conn, conn.cursor() as cur:
            cur.execute("INSERT INTO arbeit_log (bot, aktion, ergebnis, datei) "
                        "VALUES (%s,%s,%s,%s)", (BOT_NAME, aktion[:80], ergebnis[:400], datei[:200]))
        conn.close()
    except Exception:
        pass


# ── SYSTEM-PROMPT ────────────────────────────────────────────
def build_system():
    return f"""Du bist der REGIE-BOT im JARVIS Studio-Team von Rui. Heute ist {datetime.now():%d.%m.%Y}, Jahr {AKTUELLES_JAHR}.

DEINE ROLLE: Du bist der kreative Kopf fuer Video-Content von Bueroflow (buroflow.de) — einem deutschen KI-SaaS mit vier Tools (Mahnflow, Mailflow, Angebotsflow, E-Rechnungsflow). Zielgruppe: Selbststaendige, Freelancer, kleine Unternehmen.

STIL: Rui liebt VIBE-MOTION-Videos — cineastisch, atmosphaerisch, moderne Bewegung, hochwertiger Look. Denk an fluessige Kamerafahrten, sanfte Uebergaenge, premium Tech-Aesthetik, dunkle elegante Toene mit dem Bueroflow-Gruen (#5DCAA5) als Akzent.

PLATTFORMEN: Primaer LinkedIn (professionell, B2B, Nutzen im Fokus), sekundaer Instagram (visueller, kuerzer, emotionaler). Passe Konzept und Ton an die Plattform an.

═══ DEINE AUFGABE ═══
1. KONZEPT entwickeln: Hook (die ersten 2 Sekunden entscheiden!), Story-Arc, Kernbotschaft, Call-to-Action.
2. TRENDS auswerten: Nutze die Websuche, um aktuelle Video-Trends, Hooks und Formate auf LinkedIn/Reels zu verstehen.
3. VIBE-CLIPS generieren: Erstelle die atmosphaerischen Motion-Teile ueber Higgsfield (Tool 'vibe_clip').

═══ EISERNE REGEL — ECHTES PRODUKT ═══
KI-generierte Clips zeigen NIEMALS das echte Bueroflow-Produkt, Logo, Dashboard oder UI. KI kann das nicht echt darstellen — es wuerde Fake-Logos/Fake-Screens erfinden. Das ist VERBOTEN.
KI macht NUR: abstrakte Vibe-Motion, Atmosphaere, Stimmungsbilder, Uebergaenge, Texturen, Kamerafahrten durch abstrakte Szenen.
Das ECHTE Produkt (Dashboard, Logo) kommt als echte Aufnahme vom Recorder-Bot und wird spaeter im Schnitt eingefuegt. Du planst NUR, wo es hinkommt — du generierst es nicht.

═══ VIBE-CLIP GENERIEREN ═══
Tool 'vibe_clip' macht: Text->Bild->Video. Du gibst:
- bild_prompt: beschreibt das Startbild (abstrakt, atmosphaerisch, KEIN Produkt/Logo/Text)
- motion_prompt: beschreibt die Bewegung (Kamera, Fluss, Tempo)
- aspect_ratio: "16:9" (LinkedIn/YouTube) oder "9:16" (Reels/Stories) oder "1:1"
- duration: 5 (Standard, kurz halten zum Iterieren)

Beispiel guter Prompts:
- bild_prompt: "abstract flowing liquid data streams, dark teal and black, premium tech aesthetic, soft glow, cinematic depth of field"
- motion_prompt: "slow cinematic camera push forward, liquid flows gently upward, particles drift, smooth premium motion"

Generiere pro Anfrage hoechstens {MAX_CLIPS_PRO_LAUF} Clips (Credit-Schutz). Nach der Generierung nennst du dem Nutzer die Video-URLs — lade Videos NIE selbst herunter oder betrachte sie.

═══ ABLAUF ═══
Bei einem Auftrag ("mach ein LinkedIn-Video ueber E-Rechnungspflicht"):
1. Recherchiere kurz aktuelle Trends/Hooks (Websuche), wenn hilfreich.
2. Entwirf das KONZEPT: Hook, 3-5 Szenen, Kernbotschaft, CTA, welche Szenen KI-Vibe sind und wo echtes Produkt-Material hin soll.
3. Zeig Rui das Konzept ZUERST. Generiere Clips erst, wenn er zustimmt ODER wenn er direkt "generier die Clips" sagt.
4. Nach Generierung: liste die Clip-URLs und was jede zeigt.

Antworte auf Deutsch, konkret, mit Gespuer fuer den Vibe-Motion-Stil. Sei ein echter Kreativ-Regisseur, kein Aufzaehler."""


SYSTEM = build_system()
SYS_CACHED = [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}]


# ── TOOLS ────────────────────────────────────────────────────
TOOLS = [
    {
        "name": "websuche",
        "description": "Sucht aktuelle Infos im Web (Video-Trends, Hooks, Formate, Themen). Gibt Textausschnitte zurueck.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Suchbegriff, kurz"}},
            "required": ["query"],
        },
    },
    {
        "name": "vibe_clip",
        "description": ("Generiert einen Vibe-Motion-Clip ueber Higgsfield (Text->Bild->Video). "
                        "NUR abstrakte Atmosphaere, KEIN Produkt/Logo/Text im Bild. Gibt Video-URL zurueck."),
        "input_schema": {
            "type": "object",
            "properties": {
                "bild_prompt": {"type": "string", "description": "Startbild, abstrakt/atmosphaerisch, englisch"},
                "motion_prompt": {"type": "string", "description": "Bewegung/Kamera, englisch"},
                "aspect_ratio": {"type": "string", "enum": ["16:9", "9:16", "1:1"], "description": "Seitenverhaeltnis"},
                "duration": {"type": "integer", "description": "Sekunden (Standard 5)"},
                "beschreibung": {"type": "string", "description": "Kurz auf Deutsch: was zeigt dieser Clip / wofuer"},
            },
            "required": ["bild_prompt", "motion_prompt", "beschreibung"],
        },
    },
]
TOOLS_CACHED = [{**TOOLS[0]}, {**TOOLS[-1], "cache_control": {"type": "ephemeral"}}]


def tool_websuche(query):
    """Einfache Websuche ueber die Anthropic-Web-Search waere ideal; hier per DuckDuckGo-HTML als Fallback."""
    try:
        # leichte, abhaengigkeitsarme Suche
        r = requests.get("https://duckduckgo.com/html/",
                         params={"q": query}, timeout=15,
                         headers={"User-Agent": "Mozilla/5.0"})
        import re as _re
        treffer = _re.findall(r'result__snippet[^>]*>(.*?)</a>', r.text)[:5]
        sauber = [_re.sub(r"<[^>]+>", "", t).strip() for t in treffer]
        sauber = [s for s in sauber if s]
        if not sauber:
            return "Keine verwertbaren Treffer gefunden."
        return "Aktuelle Treffer:\n" + "\n".join(f"- {s}" for s in sauber[:5])
    except Exception as e:
        return f"Websuche fehlgeschlagen: {e}"


def tool_vibe_clip(inp):
    """Generiert einen Clip ueber Higgsfield. Speichert Clip-Info als JSON, gibt URL-Text zurueck."""
    if CLIP_ZAEHLER["n"] >= MAX_CLIPS_PRO_LAUF:
        return (f"Clip-Limit ({MAX_CLIPS_PRO_LAUF}) fuer diese Anfrage erreicht — "
                "Credit-Schutz. Fasse zusammen, was du hast.")
    if not hf.verfuegbar():
        return "Higgsfield nicht konfiguriert (HIGGSFIELD_KEY/SECRET fehlen in .env)."
    bild_prompt = inp.get("bild_prompt", "").strip()
    motion_prompt = inp.get("motion_prompt", "").strip()
    aspect = inp.get("aspect_ratio", "16:9")
    duration = int(inp.get("duration", 5) or 5)
    beschreibung = inp.get("beschreibung", "Vibe-Clip")
    if not bild_prompt or not motion_prompt:
        return "bild_prompt und motion_prompt sind noetig."
    try:
        log(f"[higgsfield] generiere Clip: {beschreibung[:50]} ...")
        res = hf.clip_aus_prompt(bild_prompt, motion_prompt,
                                 aspect_ratio=aspect, duration=duration)
        CLIP_ZAEHLER["n"] += 1
        # Clip-Info speichern (nur Text/URLs, kein Medien-Download)
        os.makedirs(CLIP_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        info = {"beschreibung": beschreibung, "aspect_ratio": aspect,
                "duration": duration, "bild_prompt": bild_prompt,
                "motion_prompt": motion_prompt, "bild_url": res["bild_url"],
                "video_url": res["video_url"], "erstellt": ts}
        pfad = os.path.join(CLIP_DIR, f"{ts}_clip.json")
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
        arbeit_log("Vibe-Clip generiert", beschreibung, f"clips/{ts}_clip.json")
        return (f"Clip fertig ({CLIP_ZAEHLER['n']}/{MAX_CLIPS_PRO_LAUF}): {beschreibung}\n"
                f"Video: {res['video_url']}\n(gespeichert: vault/clips/{ts}_clip.json)")
    except Exception as e:
        return f"Clip-Generierung fehlgeschlagen: {type(e).__name__}: {e}"


def run_tool(name, inp):
    if name == "websuche":
        return tool_websuche(inp.get("query", ""))
    if name == "vibe_clip":
        return tool_vibe_clip(inp)
    return f"Unbekanntes Tool: {name}"


# ── DENKEN ───────────────────────────────────────────────────
def think(history, user_text, bilder=None):
    CLIP_ZAEHLER["n"] = 0
    TOOL_LOG.clear()
    merk_text = user_text + (f"\n[{len(bilder)} Bild(er) mitgeschickt]" if bilder else "")
    history.append({"role": "user", "content": merk_text})
    messages = list(history[:-1])
    if bilder:
        inhalt = [{"type": "text", "text": user_text}]
        for b in bilder[:5]:
            inhalt.append({"type": "image", "source": {
                "type": "base64", "media_type": b.get("media_type", "image/png"),
                "data": b.get("data", "")}})
        messages.append({"role": "user", "content": inhalt})
    else:
        messages.append({"role": "user", "content": user_text})

    final_text = ""
    tool_benutzt = False
    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS,
                                      system=SYS_CACHED, tools=TOOLS_CACHED, messages=messages)
        parts = [b.text for b in resp.content if b.type == "text"]
        t = "".join(parts).strip()
        if t:
            final_text = t
        if resp.stop_reason != "tool_use":
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
                log(f"[tool] {block.name} -> {str(result)[:80]}")
                t_results.append({"type": "tool_result", "tool_use_id": block.id,
                                  "content": result})
        messages.append({"role": "assistant", "content": a_content})
        messages.append({"role": "user", "content": t_results})

    if tool_benutzt and (not final_text or resp.stop_reason == "tool_use"):
        try:
            messages.append({"role": "user", "content":
                "Fasse jetzt zusammen: das Konzept und die generierten Clips (mit URLs). Keine weiteren Tools."})
            resp2 = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS,
                                           system=SYS_CACHED, messages=messages)
            t2 = "".join(b.text for b in resp2.content if b.type == "text").strip()
            if t2:
                final_text = t2
        except Exception as e:
            log(f"[abschluss] {e}")

    if not final_text:
        final_text = "Ich konnte das Konzept nicht abschliessen — bitte in kleineren Schritten anfragen."
    history.append({"role": "assistant", "content": final_text})
    return final_text


def _antwort_senden(r, queue, text):
    for _ in range(3):
        try:
            r.rpush(queue, text); r.expire(queue, 300); return True
        except Exception:
            time.sleep(1)
    return False


def main():
    print("=" * 58, flush=True)
    print("  REGIE-BOT — Studio-Team (Vibe-Motion + Higgsfield)", flush=True)
    print(f"  Queue: {INBOX_KEY}", flush=True)
    print(f"  Higgsfield: {'konfiguriert' if hf.verfuegbar() else 'FEHLT (HIGGSFIELD_KEY/SECRET)'}", flush=True)
    print("=" * 58, flush=True)

    r = None
    for _ in range(30):
        try:
            r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True,
                            socket_keepalive=True, health_check_interval=20, socket_timeout=30)
            r.ping(); log("[redis] verbunden"); break
        except Exception:
            time.sleep(2)
    if r is None:
        sys.exit(1)
    log("Regie-Bot bereit.\n")

    history = []
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
            bilder = msg.get("bilder")
            reply_q = REPLY_KEY.format(id=req_id)
            if not text and not bilder:
                _antwort_senden(r, reply_q, "Leere Anfrage.")
                continue
            log(f"Auftrag: {text[:80]}")
            if len(history) > MAX_HISTORY * 2:
                history = history[-MAX_HISTORY * 2:]
            try:
                antwort = think(history, text, bilder=bilder)
            except Exception as e:
                antwort = f"Fehler: {type(e).__name__}: {e}"
                log(f"[think] {antwort}")
            _antwort_senden(r, reply_q, antwort)
        except Exception as e:
            log(f"[loop] {e}")
            time.sleep(3)


if __name__ == "__main__":
    main()
