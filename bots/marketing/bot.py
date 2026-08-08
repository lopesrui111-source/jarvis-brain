#!/usr/bin/env python3
"""
MARKETING-BOT — Arbeiter unter dem Bueroflow-CEO
- Queue: bot:marketing:inbox / bot:marketing:reply:<id>
- Skill-Bibliothek: /app/skills/<name>/SKILL.md (marketingskills-Repo),
  Index im System-Prompt, voller Skill wird per Tool bei Bedarf geladen
- Creatives: render_creative (HTML/CSS -> PNG via Chromium, pixelgenauer Text/Brand)
- Illustrationen: MuAPI (api.muapi.ai) — nur fuer Bilder OHNE Text
- Gemeinsames Langzeitgedaechtnis mit JARVIS + CEO (pgvector)
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
from datetime import date as _d

AKTUELLES_JAHR = _d.today().year
from skills import (skills_indexieren, SKILL_TOOLS, skill_tool_ausfuehren, skill_banner)
from openai import OpenAI

BOT_NAME = "marketing"

CLAUDE_KEY = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY", "")
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
MUAPI_KEY  = os.getenv("MUAPI_KEY", "")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
PG_HOST = os.getenv("POSTGRES_HOST", "postgres")
PG_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
PG_USER = os.getenv("POSTGRES_USER", "jarvis")
PG_PASS = os.getenv("POSTGRES_PASSWORD", "")
PG_DB   = os.getenv("POSTGRES_DB", "jarvis_brain")

MODEL       = os.getenv("ORCHESTRATOR_MODEL", "claude-sonnet-4-6")
EMBED_MODEL = "text-embedding-3-small"
MAX_HISTORY = 10
MAX_TOKENS  = 3000
MAX_TOOL_ROUNDS = 12
VAULT_DIR  = "/app/vault"
SKILLS_DIR = "/app/skills"

MUAPI_BASE = "https://api.muapi.ai/api/v1"
DEFAULT_IMAGE_MODEL = os.getenv("MUAPI_IMAGE_MODEL", "gpt-image-2-text-to-image")

# Modellwahl nach Zweck — Qualitaet dort, wo sie sichtbar wird
BILD_MODELLE = {
    "motiv":       ("gpt-image-2-text-to-image", 0.090,
                    "Hauptmotiv eines Creatives — beste Prompt-Treue, klare Komposition"),
    "premium":     ("nano-banana-pro", 0.120,
                    "wenn es richtig gut werden muss (Kampagnen-Visual, Titelbild)"),
    "hintergrund": ("flux-2-pro", 0.032,
                    "Hintergruende und Verlaeufe hinter Text — hohe Qualitaet, guenstiger"),
    "textur":      ("flux-2-klein-9b", 0.013,
                    "dezente Texturen, die ohnehin gedaempft werden"),
    "entwurf":     ("flux-2-klein-9b-turbo", 0.006,
                    "schnelle Vorschau, um eine Bildidee zu pruefen"),
}

INBOX_KEY   = "bot:marketing:inbox"
HISTORY_KEY = "bot:marketing:history"
REPLY_KEY   = "bot:marketing:reply:{id}"

if not CLAUDE_KEY:
    print("FEHLER: ANTHROPIC_API_KEY fehlt", flush=True)
    sys.exit(1)


# ── SKILL-BIBLIOTHEK ─────────────────────────────────────────
def build_skill_index():
    """Scannt /app/skills und baut einen kompakten Index aus den Frontmatter-Daten."""
    index = {}
    if not os.path.isdir(SKILLS_DIR):
        return index
    for name in sorted(os.listdir(SKILLS_DIR)):
        path = os.path.join(SKILLS_DIR, name, "SKILL.md")
        if not os.path.isfile(path):
            continue
        desc = ""
        try:
            with open(path, encoding="utf-8") as f:
                head = f.read(3000)
            m = re.search(r'description:\s*"?(.*?)("|\n[a-z_]+:|\n---)', head, re.S)
            if m:
                desc = " ".join(m.group(1).split())
            # Nur der erste Satz-Teil ("When the user wants ...") reicht fuer den Index
            desc = desc.split(" Also use")[0].split(" Use this")[0][:220]
        except Exception:
            pass
        index[name] = desc or "(keine Beschreibung)"
    return index


SKILL_INDEX = build_skill_index()


def tool_load_skill(inp):
    name = (inp.get("name") or "").strip().lower()
    if name not in SKILL_INDEX:
        return f"Skill '{name}' unbekannt. Verfuegbar: {', '.join(SKILL_INDEX)}"
    path = os.path.join(SKILLS_DIR, name, "SKILL.md")
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        return content[:12000]
    except Exception as e:
        return f"Fehler beim Laden: {e}"


# ── MUAPI BILDGENERIERUNG ────────────────────────────────────
def tool_generate_image(inp):
    if not MUAPI_KEY:
        return "MuAPI nicht konfiguriert — MUAPI_KEY fehlt in .env."
    prompt = (inp.get("prompt") or "").strip()
    if not prompt:
        return "Fehler: leerer Prompt."
    zweck = (inp.get("zweck") or "").strip().lower()
    # Reihenfolge: ausdrueckliches model > zweck > Standard "motiv".
    # Frueher fiel der Bot ohne zweck auf DEFAULT_IMAGE_MODEL zurueck und
    # erzeugte Hauptmotive versehentlich mit dem Hintergrund-Modell.
    if inp.get("model"):
        model = str(inp["model"]).strip()
    elif zweck in BILD_MODELLE:
        model = BILD_MODELLE[zweck][0]
    else:
        model = BILD_MODELLE["motiv"][0]
    print(f"  [bild] zweck={zweck or '(keiner -> motiv)'} modell={model}", flush=True)
    payload = {"prompt": prompt}
    for k in ("num_images", "aspect_ratio", "image_url"):
        if inp.get(k):
            payload[k] = inp[k]
    headers = {"x-api-key": MUAPI_KEY, "Content-Type": "application/json"}
    try:
        r = requests.post(f"{MUAPI_BASE}/{model}", json=payload, headers=headers, timeout=60)
        if r.status_code >= 400:
            return f"MuAPI-Fehler ({r.status_code}): {r.text[:300]}"
        data = r.json()
        req_id = data.get("request_id") or data.get("id")
        if not req_id:
            return f"Keine request_id erhalten: {str(data)[:300]}"
        # Pollen bis fertig (max 3 Minuten).
        # Kurz nach dem Start liefert der Endpunkt teils 404 — das ist normal, weiter warten.
        poll_url = f"{MUAPI_BASE}/predictions/{req_id}/result"
        deadline = time.time() + 180
        result = None
        letzter_fehler = ""
        while time.time() < deadline:
            time.sleep(3)
            try:
                rr = requests.get(poll_url, headers=headers, timeout=30)
            except Exception as e:
                letzter_fehler = f"Netzwerk: {type(e).__name__}"
                continue
            if rr.status_code in (404, 202, 425):
                letzter_fehler = f"{rr.status_code} (Job noch nicht bereit)"
                continue          # Ergebnis-Endpunkt existiert noch nicht -> weiter warten
            if rr.status_code >= 400:
                # MuAPI liefert waehrend der Generierung teils 400 mit dem
                # Status im JSON ("processing"/"queued"). Das ist KEIN Abbruch.
                warte = False
                try:
                    d = rr.json()
                    det = d.get("detail") if isinstance(d.get("detail"), dict) else d
                    st = str((det or {}).get("status", "")).lower()
                    if st in ("processing", "starting", "queued", "pending",
                              "in_progress", "running", "not_ready"):
                        warte = True
                        letzter_fehler = f"{rr.status_code} ({st})"
                except Exception:
                    pass
                if warte:
                    continue
                return f"MuAPI-Poll-Fehler ({rr.status_code}): {rr.text[:600]}"
            try:
                result = rr.json()
            except Exception:
                continue
            status = result.get("status", "")
            if status == "completed":
                break
            if status == "failed":
                return f"Generierung fehlgeschlagen: {result.get('error') or result.get('detail') or 'unbekannt'}"
            # sonst 'processing' -> weiter
        else:
            return f"Timeout nach 3 Minuten (zuletzt: {letzter_fehler or 'processing'})."

        roh = (result.get("outputs") or result.get("output")
               or result.get("images") or result.get("urls") or [])
        if isinstance(roh, str):
            roh = [roh]
        outputs = []
        for o in roh:
            if isinstance(o, str):
                outputs.append(o)
            elif isinstance(o, dict):
                u = o.get("url") or o.get("image_url") or o.get("uri")
                if u:
                    outputs.append(u)
        if not outputs:
            return f"Fertig, aber keine Bild-URL gefunden: {str(result)[:250]}"

        # In den Vault herunterladen
        saved = []
        adir = os.path.join(VAULT_DIR, "bilder")
        os.makedirs(adir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        for i, url in enumerate(outputs[:4]):
            try:
                ext = ".png" if ".png" in url.lower() else ".jpg"
                fname = f"{stamp}_{model}_{i}{ext}"
                img = requests.get(url, timeout=60)
                with open(os.path.join(adir, fname), "wb") as f:
                    f.write(img.content)
                saved.append(f"vault/bilder/{fname}")
                protokoll_melden("marketing", "Rohbild generiert",
                                 (inp.get("prompt") or "")[:150], f"bilder/{fname}")
            except Exception:
                saved.append(f"(Download fehlgeschlagen: {url})")
        lines = [f"Bild(er) generiert mit {model}:"]
        for u, s in zip(outputs, saved):
            lines.append(f"- URL: {u}\n  Lokal: {s}")
        return "\n".join(lines)
    except Exception as e:
        return f"MuAPI-Fehler: {type(e).__name__}: {e}"


# ── BRAND-ASSETS (echtes Brand-Kit einbetten) ────────────────
BRAND_DIR = "/app/brand"

def brand_assets_list():
    try:
        return sorted(f for f in os.listdir(BRAND_DIR) if not f.startswith("."))
    except Exception:
        return []


def _asset_data_uri(fname):
    """Sucht in brand/, vault/bilder/ (generierte Rohbilder) und vault/assets/ (Creatives)."""
    import base64, mimetypes
    name = os.path.basename(fname)
    kandidaten = [os.path.join(BRAND_DIR, name),
                  os.path.join(VAULT_DIR, "bilder", name),
                  os.path.join(VAULT_DIR, "assets", name),
                  os.path.join(VAULT_DIR, name)]
    path = next((p for p in kandidaten if os.path.isfile(p)), None)
    if not path:
        return None
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


def apply_brand_placeholders(html):
    """{{LOGO_SVG}} -> Inline-SVG; {{ASSET:datei}} -> data-URI."""
    # Logo inline (erste .svg mit 'logo' im Namen, sonst erste .svg)
    if "{{LOGO_SVG}}" in html:
        svgs = [f for f in brand_assets_list() if f.lower().endswith(".svg")]
        logos = [f for f in svgs if "logo" in f.lower()]
        pick = (next((f for f in logos if "white" in f.lower()), None)
                or (logos[0] if logos else (svgs[0] if svgs else None)))
        inline = ""
        if pick:
            try:
                with open(os.path.join(BRAND_DIR, pick), encoding="utf-8", errors="replace") as f:
                    inline = f.read()
            except Exception:
                inline = ""
        html = html.replace("{{LOGO_SVG}}", inline)
    # Beliebige Assets als data-URI
    for m in set(re.findall(r"\{\{ASSET:([^}]+)\}\}", html)):
        uri = _asset_data_uri(m.strip())
        html = html.replace("{{ASSET:" + m + "}}", uri or "")
    return html


# ── CREATIVE-RENDERING (HTML/CSS -> PNG, pixelgenau) ─────────
# ── LAYOUT-VIELFALT (verhindert das immer gleiche Schema) ────
LAYOUTS = {
    "statement": "Nur ein Satz, riesig (120-180px), randabfallend gesetzt. Kein Label, kein Button, "
                 "keine Erklaerung. Logo klein in einer Ecke. Maximale Reduktion.",
    "vollflaeche": "Gruene Vollflaeche (#5DCAA5) als Hintergrund, Text in Anthrazit. Invertiert zum "
                   "ueblichen Look. Logo in der dunklen Variante.",
    "split": "Zweigeteilt: eine Haelfte Farbflaeche oder Bild, andere Haelfte Text. Harte Kante "
             "zwischen beiden, kein Verlauf.",
    "vergleich": "Gegenueberstellung: links das Problem (durchgestrichen/ausgegraut), rechts die "
                 "Loesung (gruen). Zwei Spalten, klare Achse.",
    "liste": "Drei bis vier kurze Zeilen untereinander, jede mit gruenem Marker. Viel Zeilenabstand, "
             "kein Fliesstext.",
    "zitat": "Grosses Zitat in Anfuehrungszeichen, kursiv, mittig. Darunter klein die Quelle. "
             "Sonst leer.",
    "zahl": "Eine dominante Zahl (200px+) mit kurzem Kontext darunter.",
    "typo_collage": "Mehrere Textgroessen ineinander verschachtelt, Woerter unterschiedlich gross, "
                    "ein Wort in Gruen hervorgehoben. Asymmetrisch.",
    "diagonal": "Diagonale Komposition, Text schraeg gesetzt oder diagonale Trennlinie. "
                "Bewusst aus der Achse.",
    "rahmen": "Duenner gruener Rahmen um die gesamte Flaeche, Text zentriert darin, "
              "viel Weissraum innen.",
    "showcase": "PRODUKT-SHOWCASE im Bueroflow-Markenstil (wie die offiziellen Ads). Aufbau: "
                "Bueroflow-Logo klein oben links. Oben rechts ein Badge/Button mit abgerundeten "
                "Ecken und duennem gruenem Rand ('Jetzt testen', 'Vorab-Zugang', 'Jetzt starten'). "
                "Grosse fette Headline (80-140px, weiss oder anthrazit) ueber 1-2 Zeilen im oberen "
                "Drittel, darunter eine kurze Subline (28-36px, gedaempft). Untere zwei Drittel: "
                "mehrere Dashboard-Screenshots schraeg/perspektivisch gestaffelt, ueberlappend, "
                "mit gruenem Glow (#5DCAA5) an den Kanten (box-shadow, drop-shadow). Optional kleine "
                "schwebende UI-Karten (Aufgaben, Credits, Kontakt) mit gruenem Rand um die Screenshots. "
                "Hintergrund: dunkles Anthrazit (#12161C-#1A1D24), oft mit dezentem radial-gradient-Glow "
                "in Gruen hinter den Screenshots, ODER ein stark gedaempftes generiertes Motiv "
                "(Buerogebaeude, Atrium) als Hintergrund. Screenshots per {{ASSET:datei.png}} einbetten "
                "(echte Dashboard-Bilder wirken am besten) — alternativ mit CSS gebaute Fake-Dashboards "
                "(dunkle Karten, gruene Balken, Platzhalter-Text). Viel Tiefe durch Staffelung und Glow.",
    # ── Mit Bildmaterial (erst generate_image, dann per {{ASSET:datei}} einbetten) ──
    "foto_vollflaeche": "Generiertes Bild fuellt die ganze Flaeche. Darueber ein dunkler Verlauf "
                        "(linear-gradient von transparent zu #1A1D24), Text unten drauf. "
                        "Logo klein oben. Wirkt wie ein Filmplakat.",
    "foto_split": "Obere oder linke Haelfte generiertes Bild, andere Haelfte Anthrazit mit Text. "
                  "Harte Kante dazwischen, kein Verlauf.",
    "foto_freisteller": "Generiertes Bild in einer Form (Kreis, Blob oder abgerundetes Rechteck), "
                        "versetzt platziert. Text daneben oder darunter. Viel Leerraum.",
    "textur": "Abstrakte generierte Textur als Hintergrund, stark gedaempft "
              "(opacity .25-.4 oder mix-blend-mode), Text klar darueber. Subtil, nicht plakativ.",
}

BILD_LAYOUTS = ("foto_vollflaeche", "foto_split", "foto_freisteller", "textur")


def _letzte_layouts(anzahl=4):
    """Die zuletzt genutzten Layouts, neueste zuerst (aus dem Arbeitsprotokoll)."""
    gefunden = []
    try:
        from protokoll import protokoll_lesen
        for e in protokoll_lesen(stunden=720, bot="marketing", limit=30):
            erg = (e.get("ergebnis") or "")
            for name in LAYOUTS:
                if f"[{name}]" in erg:
                    gefunden.append(name)
                    break
            if len(gefunden) >= anzahl:
                break
    except Exception:
        pass
    return gefunden


def _letztes_layout():
    letzte = _letzte_layouts(1)
    return letzte[0] if letzte else None


BRAND_CSS = """
<style>
:root {
  --anthrazit: #1A1D24;
  --anthrazit-tief: #12151b;
  --gruen: #5DCAA5;
  --gruen-hell: #7fd9bb;
  --weiss: #ffffff;
  --grau: rgba(255,255,255,.62);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Inter', 'Helvetica Neue', Arial, sans-serif;
  background: radial-gradient(ellipse at 30% 20%, #24303a 0%, var(--anthrazit) 62%, var(--anthrazit-tief) 100%);
  color: var(--weiss);
  -webkit-font-smoothing: antialiased;
}
.akzent { color: var(--gruen); }
.kursiv { font-style: italic; }
</style>
"""

BRAND_FARBEN = ("5dcaa5", "1a1d24", "var(--gruen)", "var(--anthrazit)")


CSS_BILD_MERKMALE = ("radial-gradient", "conic-gradient", "repeating-linear-gradient",
                     "repeating-radial-gradient", "mix-blend-mode", "filter: blur",
                     "backdrop-filter", "<svg", "clip-path", "mask-image")


def _hat_bildmaterial(html):
    """Echtes Bild ODER eine ernsthafte CSS-Textur zaehlt als visuelles Material."""
    h = (html or "").lower()
    if "{{asset:" in h:
        return True
    # mehrere Gestaltungstechniken = bewusst gebaute Textur, kein Farbverlauf-Alibi
    treffer = sum(1 for m in CSS_BILD_MERKMALE if m in h)
    return treffer >= 2


def _hat_logo(html):
    """Das echte Logo muss drin sein — Schriftzug oder Farbe reichen nicht."""
    h = (html or "").lower()
    if "{{logo_svg}}" in h:
        return True
    # oder ein Logo-Asset aus dem Brand-Ordner
    import re as _re
    for m in _re.findall(r"\{\{asset:([^}]+)\}\}", h):
        if "logo" in m:
            return True
    return False


def _brand_pruefen(html):
    """Pflicht: echtes Logo UND Brandfarben."""
    h = (html or "").lower()
    return _hat_logo(html) and any(f in h for f in BRAND_FARBEN)


def _brand_einsetzen(html):
    """Fuegt das Brand-Grundgeruest ein, damit Farben und Schrift immer stimmen."""
    if "--gruen" in html:
        return html
    if "<head>" in html:
        return html.replace("<head>", "<head>" + BRAND_CSS, 1)
    if "<body" in html:
        i = html.index("<body")
        return html[:i] + BRAND_CSS + html[i:]
    return BRAND_CSS + html


def tool_render_creative(inp):
    html = (inp.get("html") or "").strip()
    if not SKILL_GELADEN["ja"] and not _notbremse():
        _ablehnung()
        return ("ABGELEHNT: Du hast noch keinen Skill geladen. Hol dir erst Fachwissen — "
                "skill_suchen (z.B. 'social media creative', 'copywriting hooks', 'ad design') "
                "und dann skill_laden. Danach baust du das Creative. "
                "Ohne Anleitung kommt nur Baukasten-Ware raus.")
    layout = (inp.get("layout") or "").strip().lower()
    if layout not in LAYOUTS and not _notbremse():
        _ablehnung()
        return ("ABGELEHNT: Bitte ein Layout waehlen. Moeglich sind:\n" +
                "\n".join(f"  {k}: {v}" for k, v in LAYOUTS.items()) +
                "\n\nWaehle eines, das zum Inhalt passt — und ein anderes als beim letzten Mal.")
    if _notbremse():
        print("  [notbremse] zwei Ablehnungen — Creative wird jetzt durchgelassen", flush=True)
        if layout not in LAYOUTS:
            layout = "statement"
    letzte = _letzte_layouts(3)
    # Nach zwei reinen Typo-Creatives ist ein Bild-Layout faellig
    if (not _notbremse() and len(letzte) >= 2
            and not any(l in BILD_LAYOUTS for l in letzte[:2])
            and layout not in BILD_LAYOUTS and not _hat_bildmaterial(html)):
        _ablehnung()
        return (f"ABGELEHNT: Die letzten beiden Creatives waren reine Typo-Kacheln "
                f"({', '.join(letzte[:2])}). Jetzt ist ein Creative MIT BILD faellig — "
                f"reine Textkacheln fallen im Feed durch.\n"
                f"So gehts: 1) generate_image mit einem textfreien, abstrakten Motiv in der "
                f"Bueroflow-Farbwelt  2) render_creative mit layout=foto_vollflaeche, foto_split, "
                f"foto_freisteller oder textur und dem Bild per {{{{ASSET:dateiname.png}}}}.")
    vorher = letzte[0] if letzte else None
    if vorher and vorher == layout and not _notbremse():
        andere = [k for k in LAYOUTS if k != layout]
        _ablehnung()
        return (f"ABGELEHNT: '{layout}' war schon das letzte Creative. Nimm ein anderes Layout, "
                f"z.B. {', '.join(andere[:4])}. Creatives duerfen sich nicht wiederholen.")
    if BILD_VERLANGT["ja"] and "{{ASSET:" not in html and not _notbremse():
        _ablehnung()
        return ("ABGELEHNT: Rui hat ausdruecklich ein GENERIERTES Motiv verlangt — eine "
                "CSS-Textur ersetzt das nicht. Ablauf: 1) generate_image mit zweck='motiv' "
                "und einem textfreien Prompt in der Bueroflow-Farbwelt  2) die gemeldete "
                "Datei per {{ASSET:dateiname.png}} einbetten  3) render_creative mit einem "
                "foto_*-Layout. Der Dateiname steht in der Antwort von generate_image.")
    if layout in BILD_LAYOUTS and not _hat_bildmaterial(html) and not _notbremse():
        _ablehnung()
        return (f"ABGELEHNT: Layout '{layout}' braucht visuelles Material. Zwei Wege:\n"
                f"a) generate_image (textfreies Motiv, Bueroflow-Farbwelt) und per "
                f"{{{{ASSET:datei.png}}}} einbetten\n"
                f"b) eine ernsthafte CSS-Textur bauen — mindestens zwei Techniken kombiniert "
                f"(radial-gradient, conic-gradient, repeating-*, mix-blend-mode, SVG-Pattern, "
                f"clip-path). Ein einfacher Farbverlauf reicht nicht.")
    if not _hat_logo(html) and not _notbremse():
        _ablehnung()
        return ("ABGELEHNT: Das Bueroflow-LOGO fehlt. Jedes Creative braucht {{LOGO_SVG}} "
                "(fuegt das echte Logo als Inline-SVG ein) — ein Schriftzug oder 'buroflow.de' "
                "als Text reicht NICHT. Platziere es dezent: oben links oder unten, "
                "etwa 8-12 % der Bildbreite, nicht dominant. Baue neu.")
    if not _brand_pruefen(html) and not _notbremse():
        _ablehnung()
        return ("ABGELEHNT: Brandfarben fehlen. Nutze --gruen (#5DCAA5) und --anthrazit "
                "(#1A1D24), sie stehen als CSS-Variablen bereit.")
    html = _brand_einsetzen(html)
    if not html:
        return "Fehler: leeres HTML."
    html = apply_brand_placeholders(html)
    width  = int(inp.get("width") or 1080)
    height = int(inp.get("height") or 1080)
    width, height = max(200, min(width, 3000)), max(200, min(height, 3000))
    name = re.sub(r"[^a-zA-Z0-9_\-]", "-", (inp.get("filename") or "creative"))[:50].strip("-") or "creative"
    fname = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{name}.png"
    adir = os.path.join(VAULT_DIR, "assets")
    os.makedirs(adir, exist_ok=True)
    path = os.path.join(adir, fname)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            pg = b.new_page(viewport={"width": width, "height": height})
            pg.set_content(html, wait_until="networkidle")
            pg.screenshot(path=path)
            b.close()
        protokoll_melden("marketing", "Creative gerendert",
                         f"[{layout}] " + ((inp.get("titel") or inp.get("beschreibung") or "")[:130]
                                           or f"{width}x{height}"),
                         f"assets/{fname}")
        CREATIVE_INFO["datei"] = fname
        CREATIVE_INFO["layout"] = layout
        return f"Creative gerendert ({width}x{height}): vault/assets/{fname}"
    except Exception as e:
        return f"Render-Fehler: {type(e).__name__}: {e}"


# ── KOSTEN / DB / GEDAECHTNIS (wie CEO) ──────────────────────
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
                cur.execute("INSERT INTO cost_ledger (bot, model, tokens_in, tokens_out, cost_usd) "
                            "VALUES (%s, %s, %s, %s, %s)",
                            (BOT_NAME, model, tok_in, tok_out, round(cost, 6)))
            conn.close()
        except Exception as e:
            print(f"  [cost] {e}", flush=True)
    threading.Thread(target=_work, daemon=True).start()


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


TOOLS = [
    {"name": "load_skill",
     "description": "Laedt einen Marketing-Skill (volle Anleitung) aus der Bibliothek. Immer den passenden Skill laden BEVOR du die Aufgabe bearbeitest.",
     "input_schema": {"type": "object", "properties": {
         "name": {"type": "string", "description": "Skill-Name aus dem Index, z.B. social, copywriting, ai-seo"}},
         "required": ["name"]}},
    {"name": "render_creative",
     "description": "Rendert ein Marketing-Creative aus HTML/CSS pixelgenau als PNG. PFLICHT: Parameter layout (statement, vollflaeche, split, vergleich, liste, zitat, zahl, typo_collage, diagonal, rahmen) — und nie dasselbe wie zuletzt (headless Chromium). ERSTE WAHL fuer alle Creatives mit Text, Logo, Zahlen oder UI-Elementen — Text wird exakt gerendert, Brandfarben stimmen garantiert. FORMATE: 1200x1200 oder 1080x1080 = Feed-Post (LinkedIn/Instagram), STANDARD. 1080x1350 = Hochformat, belegt im Feed mehr Flaeche. 1080x1920 = Story. 1200x628 NUR fuer Link-Vorschauen, NICHT fuer Feed-Posts — geht dort unter. BRAND-KIT: {{LOGO_SVG}} fuegt das echte Bueroflow-Logo als Inline-SVG ein; {{ASSET:dateiname}} bettet eine Datei aus dem Brand-Ordner als data-URI ein (fuer <img src=...>).",
     "input_schema": {"type": "object", "properties": {
         "layout": {"type": "string", "enum": ["statement", "vollflaeche", "split", "vergleich", "liste", "zitat", "zahl", "typo_collage", "diagonal", "rahmen"], "description": "Bildaufbau — Pflicht, und anders als beim letzten Creative"},
         "html": {"type": "string", "description": "Komplettes HTML-Dokument mit Inline-CSS. Body exakt auf width/height dimensionieren (margin:0, box-sizing:border-box)."},
         "width": {"type": "integer", "description": "Breite in px, Standard 1080"},
         "height": {"type": "integer", "description": "Hoehe in px, Standard 1080"},
         "filename": {"type": "string", "description": "Dateiname-Basis, z.B. e-rechnung-feed"}},
         "required": ["html"]}},
    {"name": "generate_image",
     "description": "Generiert KI-Bilder ueber MuAPI — NUR fuer fotografische/illustrative Motive OHNE Text (Hintergruende, Stimmungsbilder). NIEMALS fuer Creatives mit Text/Logo/Zahlen — dafuer render_creative nutzen (KI-Modelle verhunzen deutschen Text). Prompt auf Englisch.",
     "input_schema": {"type": "object", "properties": {
         "zweck": {"type": "string", "enum": ["motiv","premium","hintergrund","textur","entwurf"], "description": "waehlt automatisch das passende Modell: motiv (Hauptmotiv), premium (Kampagne), hintergrund (hinter Text), textur (gedaempft), entwurf (schnelle Vorschau)"},
         "prompt": {"type": "string", "description": "Bildbeschreibung auf Englisch"},
         "model": {"type": "string", "description": f"nur wenn du ein bestimmtes Modell brauchst; sonst zweck nutzen. Standard: {DEFAULT_IMAGE_MODEL}"},
         "num_images": {"type": "integer", "description": "Optional, 1-4"},
         "aspect_ratio": {"type": "string", "description": "Optional, z.B. 1:1, 16:9, 9:16"}},
         "required": ["prompt"]}},
    {"name": "remember",
     "description": "Speichert wichtige Fakten/Entscheidungen dauerhaft im gemeinsamen Gedaechtnis.",
     "input_schema": {"type": "object", "properties": {
         "content": {"type": "string"}, "project": {"type": "string", "description": "Standard: buroflow"},
         "title": {"type": "string"}}, "required": ["content", "title"]}},
    {"name": "recall",
     "description": "Durchsucht das gemeinsame Langzeitgedaechtnis (auch 'Schreibstil buroflow', Brand-Infos, CEO-Entscheidungen).",
     "input_schema": {"type": "object", "properties": {
         "query": {"type": "string"}, "project": {"type": "string"}}, "required": ["query"]}},
    {"name": "ceo_review",
     "description": ("Legt einen fertigen Entwurf (Post-Text und/oder Creative-Beschreibung) dem "
                     "Bueroflow-CEO zur Bewertung vor. Er antwortet mit PASST oder UEBERARBEITEN "
                     "plus maximal 3 konkreten Aenderungen. Hole dieses Review IMMER, bevor du "
                     "einen Post oder ein Creative endgueltig ablieferst — aber nur EINMAL."),
     "input_schema": {"type": "object", "properties": {
         "entwurf": {"type": "string", "description": "der komplette Entwurf zur Bewertung"}},
         "required": ["entwurf"]}},
    {"name": "vault_note",
     "description": ("Legt eigenstaendige Dokumente als Markdown im Vault ab: Kampagnenplaene, "
                     "Strategien, Analysen, Themensammlungen. NICHT fuer Post-Texte zu einem "
                     "Creative — die werden automatisch nach vault/posts/ gesichert."),
     "input_schema": {"type": "object", "properties": {
         "folder": {"type": "string"}, "title": {"type": "string"}, "content": {"type": "string"}},
         "required": ["title", "content"]}},
]


TOOLS = TOOLS + SKILL_TOOLS

REVIEW_AKTIV = os.getenv("MARKETING_REVIEW", "1") == "1"
REVIEW_TIMEOUT = int(os.getenv("MARKETING_REVIEW_TIMEOUT", "180"))
# Merker: kam der Auftrag vom CEO? Dann kein Rueckfrage-Review (Deadlock!)
VOM_CEO = {"ja": False}
BILD_VERLANGT = {"ja": False}
_BILD_MUSTER = re.compile(r"(generiert|generier|ki.?bild|echtes?\s+(bild|motiv|foto)"
                          r"|bild.?layout|mit\s+(bild|motiv|foto)|muapi|nano.?banana|gpt.?image)", re.I)
REVIEW_STAND = {"geholt": False}


def tool_ceo_review(inp):
    """Legt den Entwurf dem CEO zur Bewertung vor."""
    if not REVIEW_AKTIV:
        return "Review ist abgeschaltet (MARKETING_REVIEW=0). Liefere direkt ab."
    if VOM_CEO["ja"]:
        return ("Dieser Auftrag kam vom CEO selbst — kein Review noetig, sonst warten wir "
                "gegenseitig aufeinander. Liefere direkt ab.")
    entwurf = (inp.get("entwurf") or "").strip()
    if len(entwurf) < 80:
        return "Fehler: Bitte den vollstaendigen Entwurf uebergeben (Text und ggf. Creative-Beschreibung)."

    frage = ("[REVIEW] Bewerte diesen Marketing-Entwurf fuer Bueroflow. "
             "Antworte KURZ und konkret:\n"
             "1. Urteil: PASST oder UEBERARBEITEN\n"
             "2. Bei UEBERARBEITEN: maximal 3 konkrete Aenderungen (keine Grundsatzdebatte)\n"
             "Achte auf: Klarheit der Aussage, Zielgruppe Kleinunternehmer/Freelancer, "
             "fachliche Richtigkeit, Ruis Ton (direkt, keine Werbefloskeln), Pre-Launch-Kontext.\n\n"
             "--- ENTWURF ---\n" + entwurf[:5000])

    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True,
                        socket_keepalive=True, health_check_interval=20, socket_timeout=30)
        req_id = str(uuid.uuid4())
        r.rpush("bot:ceo:inbox", json.dumps({"id": req_id, "text": frage}, ensure_ascii=False))
        ende = time.time() + REVIEW_TIMEOUT
        while time.time() < ende:
            try:
                res = r.blpop(f"bot:ceo:reply:{req_id}", timeout=5)
                if res:
                    REVIEW_STAND["geholt"] = True
                    protokoll_melden("marketing", "CEO-Review eingeholt", res[1][:200], "")
                    return f"CEO-REVIEW:\n{res[1]}"
            except Exception:
                try:
                    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True,
                                    socket_keepalive=True, socket_timeout=30)
                except Exception:
                    pass
        return ("CEO antwortet nicht rechtzeitig — liefere deinen Entwurf ohne Review ab "
                "und weise Rui kurz darauf hin.")
    except Exception as e:
        return f"Review nicht moeglich ({type(e).__name__}) — liefere direkt ab."


SKILL_GELADEN = {"ja": False}
CREATIVE_INFO = {"datei": "", "layout": ""}
ABLEHNUNGEN = {"n": 0}


def _ablehnung():
    ABLEHNUNGEN["n"] += 1


def _notbremse():
    """Nach zwei Ablehnungen nicht weiter blockieren — sonst dreht sich der Bot im Kreis."""
    return ABLEHNUNGEN["n"] >= 2


def _post_ablegen(text, creative="", layout=""):
    """Legt den Begleittext automatisch neben dem Creative ab (vault/posts/)."""
    if not text or len(text.strip()) < 120:
        return ""
    pdir = os.path.join(VAULT_DIR, "posts")
    try:
        os.makedirs(pdir, exist_ok=True)
        basis = os.path.splitext(os.path.basename(creative))[0] if creative else "post"
        fname = f"{basis}.md" if creative else f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_post.md"
        with open(os.path.join(pdir, fname), "w", encoding="utf-8") as f:
            f.write(f"# Post — {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n")
            if creative:
                f.write(f"- **Creative:** vault/assets/{os.path.basename(creative)}\n")
            if layout:
                f.write(f"- **Layout:** {layout}\n")
            f.write("\n---\n\n" + text.strip() + "\n")
        return f"posts/{fname}"
    except Exception as e:
        print(f"  [posts] {e}", flush=True)
        return ""


# ── FORTSCHRITT ──────────────────────────────────────────────
# Ein Creative durchlaeuft leicht acht Tool-Runden plus Bildgenerierung.
# Ohne Zwischenstand wirkt das im Dashboard wie ein Haenger.
FORTSCHRITT = {"r": None, "id": ""}

_TOOL_KLARTEXT = {
    "recall": "sucht im Gedaechtnis",
    "remember": "merkt sich etwas",
    "skill_suchen": "sucht passenden Skill",
    "load_skill": "laedt Skill",
    "skill_laden": "laedt Skill",
    "generate_image": "generiert Bild (kann 1-3 Min dauern)",
    "render_creative": "rendert Creative",
    "ceo_review": "holt CEO-Freigabe",
    "vault_note": "legt Notiz ab",
    "web_search": "recherchiert im Web",
}


def fortschritt(text):
    if not (FORTSCHRITT["r"] and FORTSCHRITT["id"]):
        return
    try:
        FORTSCHRITT["r"].setex(f"bot:marketing:fortschritt:{FORTSCHRITT['id']}", 900, text)
    except Exception:
        pass


# ── TATSACHEN-PROTOKOLL ──────────────────────────────────────
# Der Bot hat frueher am Ende einer Anfrage geraten, was er getan hat:
# mal erfundene Pfade, mal eine falsche "ich habe gar nichts gemacht"-Beichte.
# Hier wird pro Anfrage mitgeschrieben, was WIRKLICH lief.
TOOL_LOG = []          # [(toolname, ergebnis-kurz), ...]
ECHTE_DATEIEN = []     # nachweislich geschriebene Vault-Pfade

_PFAD_RE = re.compile(r"vault/[A-Za-z0-9_\-./]+\.(?:png|jpg|jpeg|md|txt|html|svg)")
_LEUGNUNG_RE = re.compile(
    r"(kann das nicht liefern|habe (?:in dieser session |)(?:so getan|nicht tats)|"
    r"erfunden(?:e|en)? (?:pfade|dateinamen)|es gibt (?:keinen echten|keine echten)|"
    r"nichts gespeichert|war(?:en|) (?:alles |)erfunden)", re.I)


def _protokoll_merken(name, ergebnis):
    txt = str(ergebnis)
    TOOL_LOG.append((name, txt[:120]))
    for p in _PFAD_RE.findall(txt):
        if p not in ECHTE_DATEIEN:
            ECHTE_DATEIEN.append(p)


def _tatsachen_block():
    """Faktenblock aus dem Protokoll — vom Code erzeugt, nicht vom Modell."""
    if not ECHTE_DATEIEN:
        return ""
    zeilen = ["", "— Tatsaechlich erzeugt:"]
    for p in ECHTE_DATEIEN:
        zeilen.append(f"  {p}")
    return "\n".join(zeilen)


def _antwort_bereinigen(text):
    """Entfernt erfundene Pfade und korrigiert falsche Selbst-Beichten."""
    if not text:
        return text
    # 1) Pfade, die in keinem Tool-Ergebnis vorkamen -> markieren
    erfunden = [p for p in set(_PFAD_RE.findall(text)) if p not in ECHTE_DATEIEN]
    for p in erfunden:
        text = text.replace(p, "(Pfad nicht belegt)")
        print(f"  [pruefung] erfundener Pfad entfernt: {p}", flush=True)
    # 2) Falsche Leugnung, obwohl Dateien entstanden sind
    if ECHTE_DATEIEN and _LEUGNUNG_RE.search(text):
        print("  [pruefung] falsche Selbst-Beichte erkannt — korrigiert", flush=True)
        namen = ", ".join(n for n, _ in TOOL_LOG) or "-"
        text = ("(Hinweis vom System: die folgende Selbsteinschaetzung war falsch — "
                f"es liefen tatsaechlich diese Tools: {namen})\n\n" + text)
    return text


def run_tool(name, inp):
    if name in ("skill_laden", "load_skill"):
        SKILL_GELADEN["ja"] = True
    _skill = skill_tool_ausfuehren(name, inp)
    if _skill is not None:
        return _skill
    if name == "load_skill":
        return tool_load_skill(inp)
    if name == "render_creative":
        return tool_render_creative(inp)
    if name == "generate_image":
        return tool_generate_image(inp)
    if name == "remember":
        return tool_remember(inp)
    if name == "recall":
        return tool_recall(inp)
    if name == "ceo_review":
        return tool_ceo_review(inp)
    if name == "vault_note":
        return tool_vault_note(inp)
    return f"Unbekanntes Tool: {name}"


# ── SYSTEM-PROMPT ────────────────────────────────────────────
def build_system():
    brand_files = ", ".join(brand_assets_list()) or "(keine — Brand-Ordner leer)"
    idx = "\n".join(f"- {n}: {d}" for n, d in SKILL_INDEX.items())
    return f"""Du bist der MARKETING-BOT von Bueroflow — Arbeiter unter dem Bueroflow-CEO.

PERSOENLICHKEIT:
- Du duzt. Direkt, kreativ, handwerklich sauber. Kein Marketing-Blabla ueber Marketing.
- Du LIEFERST: fertige Entwuerfe, konkrete Plaene — kein "man koennte".

BUEROFLOW-KONTEXT:
- Deutsches SaaS fuer Kleinunternehmer/Solopreneure: Mahnflow, Briefflow, Angebotsflow, E-Rechnungsflow.
- Pre-Launch auf buroflow.de: Waitlist offen, Verkauf gesperrt. Ziel: Warteliste fuellen.
- Brand: Anthrazit #1A1D24, Weiss, Gruen #5DCAA5, kursive Akzent-Woerter, radikaler Minimalismus, Anti-KI-Aesthetik.
- Tagline: "Weniger Buerokram. Mehr Feierabend." Zielgruppe: deutsche Solo-Selbststaendige, KMU.
- Kanaele: LinkedIn (Unternehmensseite), gutefrage.net + Quora (VORSICHT: nur menschlich-lockere Entwuerfe,
  Rui wurde wegen KI-Texten verwarnt — "is", "nich", "wuerd ich", keine Listen, kein Werbesprech), SEO-Blog geplant.

DEINE SKILL-BIBLIOTHEK (per load_skill laden, IMMER bevor du eine Aufgabe bearbeitest):
{idx}

ARBEITSWEISE:
1. IMMER ZUERST FACHWISSEN HOLEN — nie aus dem Bauch texten. Du hast ZWEI Bibliotheken:

   a) GROSSE BIBLIOTHEK (skill_suchen / skill_laden) — ueber 340 Anleitungen aus Engineering,
      Marketing, Produkt, C-Level-Beratung. Hier steckt die Tiefe: Positionierung, Messaging-
      Frameworks, Ad-Strukturen, Design-Prinzipien, Conversion. NUTZE DIESE ZUERST.
      Beispiele: skill_suchen("social media creative"), skill_suchen("copywriting hooks"),
      skill_suchen("visual design"), skill_suchen("positioning").

   b) MARKETING-SPEZIALSKILLS (load_skill) — 48 kompakte Praxis-Skills. Ergaenzend, nicht ersatzweise.

   Fuer ein gutes Creative laedst du mindestens EINEN Skill aus der grossen Bibliothek —
   idealerweise einen zum Text und einen zur visuellen Gestaltung.
   Dazu recall fuer Schreibstil, Brand und frueher Erstelltes (nichts wiederholen!).
2. Entwurf/Plan erstellen nach Skill-Anleitung, angepasst auf Bueroflow und deutschen Markt.
3. BRAND IST PFLICHT, NICHT OPTIONAL:
   - Jedes Creative enthaelt {{{{LOGO_SVG}}}} — das ECHTE Logo als Inline-SVG. Ein getippter
     Schriftzug oder "buroflow.de" als Text ist KEIN Logo und wird abgelehnt.
     Platzierung: dezent, oben links oder unten, 8-12 % der Bildbreite. Nicht dominant.
   - Dazu die Brandfarben.
     Verfuegbar als CSS-Variablen: var(--gruen) #5DCAA5, var(--anthrazit) #1A1D24,
     var(--weiss), var(--grau). Das Grundgeruest wird automatisch eingefuegt.
   - Creatives ohne Brand-Element werden technisch abgelehnt — dann baust du neu.
   - Bildmaterial aus dem Brand-Ordner per {{{{ASSET:dateiname}}}}.

4. BILDMATERIAL — so entstehen die staerksten Creatives:
   - generate_image erzeugt textfreie Motive (MuAPI). NIE Text ins Bild, den setzt render_creative.
   - Modellwahl ueber den Parameter zweck — nicht ueber model:
     zweck="motiv" fuers Hauptmotiv (0,09 $, beste Qualitaet)
     zweck="hintergrund" fuer Flaechen hinter Text (0,03 $)
     zweck="textur" fuer gedaempfte Muster (0,013 $)
     zweck="premium" nur fuer wirklich wichtige Visuals (0,12 $)
     Nimm nicht immer das teuerste — hinter Text reicht 'hintergrund' vollkommen.
   - Gute Prompts: abstrakt, ruhig, zur Marke passend. Z.B. "abstract dark teal gradient mesh,
     soft depth of field, minimal, editorial", "flowing paper texture in charcoal and mint,
     macro, soft light", "geometric shapes floating, dark background, subtle green accent".
   - Vermeide: Menschen mit Gesichtern, Buerostockfotos, Text, Logos, ueberladene Szenen.
   - Ablage: Rohbilder in vault/bilder/, fertige Creatives in vault/assets/,
     die Post-Texte werden automatisch in vault/posts/ gesichert (musst du nicht selbst tun).
     Einbetten mit {{{{ASSET:dateiname.png}}}} — der Ordner wird automatisch gefunden. Layouts dafuer:
     foto_vollflaeche, foto_split, foto_freisteller, textur.
   - Sagt Rui "generiertes Motiv", "KI-Bild" oder "Bild-Layout": IMMER generate_image
     aufrufen und per {{{{ASSET:datei}}}} einbetten — CSS-Effekte gelten dann NICHT.
   - PFLICHT-RHYTHMUS: Nach zwei reinen Typo-Creatives ist das naechste MIT BILD.
     Das wird technisch geprueft — du bekommst sonst eine Ablehnung. Plane es also ein:
     erst generate_image, dann render_creative mit einem foto_*- oder textur-Layout.

5. ANSPRUCH — kein Baukasten-Look:
   - Keine generischen Stockfloskeln ("Effizienz steigern", "Zeit sparen", "revolutionaer").
   - Ein Creative = EINE Aussage. Grosse Typo, viel Leerraum, ein Akzent in Gruen.
   - Jedes Creative anders als das letzte (recall nutzen, um Wiederholung zu vermeiden).
   - Deutsche Sprache, Ruis Ton: direkt, konkret, keine Werbefloskeln.

AKTUELLES JAHR: {AKTUELLES_JAHR} — nutze nie eine aeltere Jahreszahl in Creatives.

6. QUALITAETSKONTROLLE — Ablauf bei Posts und Creatives:
   a) Skills laden, Entwurf bauen (Text + Creative)
   b) ceo_review aufrufen mit dem kompletten Entwurf
   c) Sagt der CEO UEBERARBEITEN: die genannten Punkte umsetzen — Text neu schreiben,
      Creative neu rendern (anderes Layout ist erlaubt). NUR EINE Ueberarbeitungsrunde,
      danach lieferst du ab, auch wenn nicht alles perfekt ist.
   d) Sagt er PASST: direkt abliefern.
   e) In deiner Antwort an Rui nennst du kurz, was der CEO angemerkt hat und was du geaendert hast.
   Kommt der Auftrag vom CEO selbst, entfaellt das Review.

7. FORMAT: Fuer LinkedIn- und Instagram-Posts immer quadratisch (1200x1200) oder
   hochkant (1080x1350). Querformat 1200x628 ist ausschliesslich fuer Link-Vorschauen —
   im Feed wird es klein dargestellt und faellt durch. Frag im Zweifel nicht, nimm 1200x1200.

8. CREATIVES (Social-Grafiken, Ads, Banner): IMMER render_creative (HTML/CSS) — Text pixelgenau, Umlaute korrekt, Brand exakt. NIEMALS generate_image fuer Text-Creatives (KI-Modelle verhunzen deutschen Text, falsche Logos). generate_image nur fuer textfreie Illustrationen/Hintergruende.
   - Fuer hochwertige PRODUKT-ADS im offiziellen Bueroflow-Look (grosse Headline oben, Badge oben rechts, gestaffelte Dashboard-Screenshots mit gruenem Glow) das Layout 'showcase' nutzen. Das ist der Marken-Stil fuer starke Werbe-Grafiken — greif oefter darauf zurueck, wenn es um das Produkt selbst geht (nicht bei reinen Statement-/Zitat-Posts).
   ECHTES BRAND-KIT: Nutze IMMER {{{{LOGO_SVG}}}} fuer das Logo (nimmt automatisch die weisse Variante — richtig fuer dunkle Creatives; nie selbst nachbauen!). Andere Varianten gezielt per {{{{ASSET:dateiname}}}} (z.B. <img src="{{{{ASSET:logo_dark_transparent.png}}}}"> auf hellem Grund). Verfuegbare Brand-Dateien: {brand_files}
   Brand-Bauplan fuer Creatives: body margin:0 exakt auf Format; Hintergrund radial-gradient(circle at 50% 30%, #24303a 0%, #1A1D24 60%); Schrift 'Segoe UI',system-ui; Headline GROSS fett weiss (90-130px), Subline #5DCAA5 mit letter-spacing; Fliesstext #c9cdd6; Logo-Wordmark "Büroflow" oben links (B in #5DCAA5); optional CTA-Pill (Rand #5DCAA5, transparent); dezente Glow-Punkte via box-shadow. Radikal minimalistisch, viel Negativraum, KEINE Stockfoto-Optik.
4. POST-TEXTE NICHT SELBST ABLEGEN: Der Begleittext zu einem Creative wird automatisch
   nach vault/posts/ gesichert — gleicher Dateiname wie das Creative, ohne dein Zutun.
   Rufe dafuer KEIN vault_note auf, sonst liegt derselbe Text doppelt im Vault.
   vault_note (folder: projects) nutzt du nur fuer eigenstaendige Sachen:
   Kampagnenplaene, Strategien, Analysen, Themensammlungen.
5. Wichtige Learnings/Entscheidungen via remember speichern (project: buroflow).

EISERNE REGELN:
- ALLES ist ENTWURF zur Freigabe. Du postest, sendest, veroeffentlichst NICHTS selbst.
- Deutsch fuer Content (ausser Bild-Prompts). Ruis Stil anwenden (recall "Schreibstil buroflow").
- Keine erfundenen Zahlen/Features. Wenn Info fehlt: recall, dann fragen.
- Max 2-3 Skills pro Aufgabe laden — fokussiert bleiben."""


SYSTEM = build_system()

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


def think(history, user_text, bilder=None):
    SKILL_GELADEN["ja"] = False
    VOM_CEO["ja"] = "[REVIEW]" in user_text or "[von-ceo]" in user_text.lower()
    BILD_VERLANGT["ja"] = bool(_BILD_MUSTER.search(user_text))
    REVIEW_STAND["geholt"] = False
    CREATIVE_INFO["datei"] = ""
    CREATIVE_INFO["layout"] = ""
    ABLEHNUNGEN["n"] = 0
    TOOL_LOG.clear()
    ECHTE_DATEIEN.clear()
    # Ins Gedaechtnis nur ein Textvermerk (base64 wuerde die Historie sprengen);
    # die eigentlichen Bilder gehen nur in die aktuelle Anfrage.
    merk_text = user_text + (f"\n[{len(bilder)} Bild(er) mitgeschickt]" if bilder else "")
    history.append({"role": "user", "content": merk_text})
    messages = list(history[:-1])
    if bilder:
        print(f"  [bild] {len(bilder)} Bild(er) empfangen", flush=True)
        inhalt = [{"type": "text", "text": user_text}]
        for b in bilder[:5]:
            inhalt.append({"type": "image", "source": {
                "type": "base64",
                "media_type": b.get("media_type", "image/png"),
                "data": b.get("data", "")}})
        messages.append({"role": "user", "content": inhalt})
    else:
        messages.append({"role": "user", "content": user_text})
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
                fortschritt(_TOOL_KLARTEXT.get(block.name, block.name))
                result = run_tool(block.name, block.input or {})
                _protokoll_merken(block.name, result)
                print(f"  [tool] {block.name} -> {str(result)[:90]}", flush=True)
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
    # Selbstauskunft gegen das Tatsachen-Protokoll pruefen
    final_text = _antwort_bereinigen(final_text)
    final_text += _tatsachen_block()
    # Begleittext automatisch sichern (kostet nichts, passiert immer)
    if CREATIVE_INFO["datei"] or len(final_text) > 400:
        ablage = _post_ablegen(final_text, CREATIVE_INFO["datei"], CREATIVE_INFO["layout"])
        if ablage:
            print(f"  [posts] abgelegt: {ablage}", flush=True)
            protokoll_melden("marketing", "Post-Text abgelegt",
                             final_text.strip().splitlines()[0][:120], ablage)
            final_text += f"\n\n(Text gesichert: vault/{ablage})"

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
    print("  MARKETING-BOT — Arbeiter unter dem Bueroflow-CEO", flush=True)
    print(f"  Modell : {MODEL} | Queue: {INBOX_KEY}", flush=True)
    print(f"  Skills : {len(SKILL_INDEX)} geladen", flush=True)
    print(f"  Bibliothek: {skill_banner()}", flush=True)
    print(f"  MuAPI  : {'aktiv' if MUAPI_KEY else 'nicht konfiguriert (MUAPI_KEY fehlt)'}", flush=True)
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
    print("  Marketing-Bot bereit.\n", flush=True)

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
            bilder = msg.get("bilder") or msg.get("images") or []
            reply_q = REPLY_KEY.format(id=req_id)
            if not text and not bilder:
                _antwort_senden(r, reply_q, "Leere Anfrage.")
                continue
            if bilder and not text:
                text = "Schau dir die mitgeschickten Bilder an."
            if text.lower() in ("reset", "vergiss alles"):
                r.delete(HISTORY_KEY)
                _antwort_senden(r, reply_q, "Marketing-Kurzzeitgedaechtnis geleert.")
                continue
            if text.lower() == "skills":
                _antwort_senden(r, reply_q, "Skills:\n" + "\n".join(f"- {n}" for n in SKILL_INDEX))
                continue
            print(f"  Auftrag: {text[:80]}", flush=True)
            FORTSCHRITT["r"], FORTSCHRITT["id"] = r, req_id
            fortschritt("denkt nach")
            history = load_history(r)
            try:
                answer = think(history, text, bilder=bilder)
            except Exception as e:
                answer = f"Fehler: {type(e).__name__}: {e}"
                print(f"  [think] {answer}", flush=True)
            save_history(r, history)
            print(f"  Marketing: {answer[:100]}\n", flush=True)
            try:
                r.delete(f"bot:marketing:fortschritt:{req_id}")
            except Exception:
                pass
            FORTSCHRITT["id"] = ""
            _antwort_senden(r, reply_q, answer)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"  [loop] {type(e).__name__}: {e}", flush=True)
            time.sleep(1)


if __name__ == "__main__":
    main()
