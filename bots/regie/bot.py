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
import base64
import subprocess
import glob
import tempfile
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
MAX_TOKENS = 8000
MAX_HISTORY = 8
MAX_TOOL_ROUNDS = 14
VAULT_DIR = "/app/vault"
CLIP_DIR  = os.path.join(VAULT_DIR, "clips")   # hier landen Clip-Infos (JSON)

INBOX_KEY = "bot:regie:inbox"
REPLY_KEY = "bot:regie:reply:{id}"

# Tages-Budget fuer Higgsfield-Generierungen (Schutz vor Credit-Verbrennung)
MAX_CLIPS_PRO_LAUF = int(os.getenv("REGIE_MAX_CLIPS", "6"))

# ── SKILLS (Marketing-Wissen) ────────────────────────────────
SKILLS_DIR = os.getenv("SKILLS_DIR", "/app/skills")
MOTION_SKILLS_DIR = os.getenv("MOTION_SKILLS_DIR", "/app/motion-skills")
REFERENZ_DIR = os.getenv("REFERENZ_DIR", "/app/vault/referenzen")
CUSTOM_DIR = os.getenv("CUSTOM_DIR", "/app/vault/custom")
SFX_DIR = os.getenv("SFX_DIR", "/app/vault/sfx")
ELEVENLABS_KEY = os.getenv("ELEVENLABS_API_KEY", "")
# Kuratierte, video-relevante Skills (Name -> Ordner im skills-repo)
VERFUEGBARE_SKILLS = {
    "marketing-psychology": "Psychologische Trigger, warum Menschen klicken/kaufen, Hooks",
    "social":               "Social-Media-Mechaniken, Short-Form-Video, Plattform-Logik",
    "content-strategy":     "Content-Aufbau, Story-Arc, Themen, Serien",
    "ad-creative":          "Werbe-Kreation, Anzeigen-Konzepte, visuelle Hooks",
    "ads":                  "Ad-Prinzipien, Performance, Zielgruppen",
    "copy-editing":         "Knackige Texte, Kuerzen, Klarheit",
    "product-marketing":    "Nutzen kommunizieren, Positionierung, Messaging",
    "offers":               "Angebote, CTAs, Conversion",
    "motion-design":        "MOTION: Timing, Easing, Disney-Prinzipien, Choreografie fuer Animationen (fuer Komponenten-Bau!)",
    "motion-principles":    "MOTION: Anti-AI-Slop-Prinzipien (Emil Kowalski/Krehel), wann/wie animieren, was billig wirkt",
    "ui-animation":         "MOTION: Springs, Easing-Kurven, Clip-path-Reveals, Timing, Transition-Rezepte",
    "video-template":       "MOTION: Multi-Scene-Video-Aufbau, Szenen-Transitions",
}

def skill_liste_text():
    zeilen = [f"- {name}: {beschr}" for name, beschr in VERFUEGBARE_SKILLS.items()]
    return "\n".join(zeilen)

def lade_skill(name):
    """Liest eine SKILL.md aus dem skills-repo. Gibt Text (gekuerzt) zurueck."""
    if name not in VERFUEGBARE_SKILLS:
        return f"Skill '{name}' nicht verfuegbar. Verfuegbar: {', '.join(VERFUEGBARE_SKILLS)}"
    # Motion-Skills liegen in eigenem Ordner, Marketing-Skills im skills-repo
    motion_namen = {"motion-design", "motion-principles", "ui-animation", "video-template"}
    basis = MOTION_SKILLS_DIR if name in motion_namen else SKILLS_DIR
    pfad = os.path.join(basis, name, "SKILL.md")
    try:
        with open(pfad, encoding="utf-8") as f:
            txt = f.read()
    except Exception as e:
        return f"Skill '{name}' konnte nicht geladen werden: {e}"
    # Sicherheitslimit gegen Ueberlaenge
    if len(txt) > 12000:
        txt = txt[:12000] + "\n\n[... gekuerzt ...]"
    return txt

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
def custom_komponenten_liste():
    """Listet die aktuell verfuegbaren custom-Komponenten (Dateinamen ohne .jsx)."""
    try:
        namen = [f[:-4] for f in os.listdir(CUSTOM_DIR)
                 if f.endswith(".jsx") and not f.startswith("_") and f != "beispiel.jsx"]
        return sorted(namen)
    except Exception:
        return []

def build_system():
    return f"""Du bist der REGIE-BOT im JARVIS Studio-Team von Rui. Heute ist {datetime.now():%d.%m.%Y}, Jahr {AKTUELLES_JAHR}.

DEINE ROLLE: Du bist der kreative Kopf fuer Video-Content von Bueroflow (buroflow.de) — einem deutschen KI-SaaS mit vier Tools (Mahnflow, Mailflow, Angebotsflow, E-Rechnungsflow). Zielgruppe: Selbststaendige, Freelancer, kleine Unternehmen.

DEIN HAUPTWERKZEUG: MOTION-DESIGN. Du erstellst hochwertige Motion-Graphics-Videos (animierter Text, Glasoptik, bewegte Formen, Kinetic Typography) ueber den Render-Server (Tool 'motion_video'). Das ist praezises, marken-konformes Motion-Design im Bueroflow-Look — KEIN fotorealistisches KI-Video.

STIL: Modern, premium, mit Punch. Bueroflow-Brandkit ist fest eingebaut (Farben, Geist-Schrift, Logo). Standard-Look: dunkel mit Limette-Akzent (#C8FF47). Weitere Paletten je nach Stimmung verfuegbar.

PLATTFORMEN & FORMATE:
- TikTok/Reels/Shorts -> Format "tiktok" (9:16, hochkant)
- LinkedIn/YouTube -> Format "linkedin" (16:9, quer)
- Feed/Ads quadratisch -> Format "quadrat" (1:1)
Du entscheidest das Format passend zur Plattform. Ads koennen in mehreren Formaten sinnvoll sein.

═══ MOTION-VIDEO ERSTELLEN (Tool 'motion_video') ═══
Du waehlst einen von 5 STILEN + Palette + Format + die Texte:

STILE:
- "szenen"  (PREMIUM, Vorzeige-Look): Aussagen auf Glas-Panels, die mit Punch reingleiten. Ideal fuer Story (Problem -> Loesung -> CTA). props: {{szenen: ["Zeile1","Zeile2","Zeile3"]}}
- "wortpop" (ENERGETISCH): einzelne Woerter knallen rhythmisch rein. Fuer knackige Hooks/Slogans. props: {{worte: ["SCHLUSS","MIT","PAPIERKRAM"], akzentWort: -1}}
- "zahl"    (STATISTIK): grosse Zahl zaehlt hoch. Fuer Zahlen-Aussagen. props: {{zielZahl: 30, suffix: " Sek", vortext: "Mahnung in", nachtext: "statt 30 Minuten"}}
- "formen"  (PREMIUM): bewegte Linie + rotierender Ring-Akzent mit Text. props: {{zeilen: ["Weniger Aufwand","mehr fuers Wesentliche"]}}
- "kinetic" (BASIS): gestaffelter Text mit Akzent-Zeile. props: {{zeilen: [...], akzentZeile: 1}}

PALETTEN: "dunkel" (Standard, dunkel+Limette), "hell" (creme+dunkelgruen), "gruen" (Marken-Gruen+weiss), "limette" (Limette+dunkel).

Der beste Allrounder ist "szenen". Nutze "wortpop" fuer Hooks, "zahl" fuer Statistiken, "formen" fuer elegante Statements.

WICHTIG:
- Texte kurz und knackig (Social-Media-tauglich, keine langen Saetze).
- Ein Motion-Video pro Aufruf. Du kannst mehrere Videos fuer eine Kampagne machen (z.B. Hook-Video + Haupt-Video), aber pro Aufruf eins.
- Nach dem Rendern nennst du den Dateipfad (vault/videos/...). Lade Videos NIE herunter oder betrachte sie.

═══ SOUND-EFFEKTE (Tool 'sfx_generieren') ═══
Du kannst passende SFX generieren (ElevenLabs) und in Videos einsetzen. Typische SFX fuer Motion-Videos:
- Uebergangs-Whoosh (bei slide/wipe-Uebergaengen)
- Pop/Tick (wenn Text/Elemente reinkommen)
- Impact/Boom (bei einem flash-Pivot)
- Erfolgs-Chime (beim positiven Moment, z.B. "Bezahlt")
Beschreibe SFX wie ein PROFESSIONELLER SOUND-DESIGNER — detailliert, mit Textur/Charakter, nicht generisch. Schlechte Prompts geben billige Sounds. Beispiele:
- statt "whoosh" -> "punchy cinematic transition whoosh, fast air movement with a subtle low-end tail, crisp and modern, professional sound design"
- statt "success chime" -> "bright premium success chime, short glassy bell with a warm harmonic shimmer, satisfying and clean, UI reward sound"
- statt "pop" -> "tight snappy UI pop, subtle click with a soft body, modern app interaction"
- Impact -> "deep cinematic impact hit with tight punch and short reverb tail, trailer-style"
Nutze prompt_influence 0.6-0.8 fuer literalere Ergebnisse. Generiere jeden SFX EINMAL, dann wiederverwendbar.
Im story_video gibst du die SFX mit Timing an: sfx: [{{datei: "whoosh-up", bei_sek: 2.0, lautstaerke: 0.6}}, ...]. bei_sek = wann im Video der Sound startet (z.B. genau am Uebergang). Setze SFX gezielt und sparsam — je nachdem was die Szene braucht, nicht wahllos.

═══ KOMPLETTE VIDEOS BAUEN (Tool 'story_video') ═══
Fuer volle Videos (20-30 Sek) mit Story-Arc verkettest du mehrere Segmente zu EINEM Clip. Jedes Segment ist entweder ein Grundstil ODER eine deiner selbstgebauten custom-Komponenten (stil: "custom-NAME").

Verfuegbare custom-Komponenten: {custom_komponenten_liste()}

TEMPO & RHYTHMUS (WICHTIG — sonst wirkt es langsam/langweilig):
- Grundstil-Segmente (wortpop/szenen/zahl/formen/kinetic): KURZ halten, 1.5-2.5 Sek pro Segment. Schneller Schnitt = dynamisch.
- Reiche custom-Komponenten (problem-karten, erfolg-moment) sind LANG (7-8s Mini-Videos). Nutze sie SPARSAM als "Hero-Moment" (max 1-2 pro Video), NICHT als schnelle Schnittfolge.
- Ein gutes 25-30s-Video: viele kurze Segmente + 1-2 reiche Hero-Momente.
- UEBERGAENGE: Nutze fliessende Uebergaenge (slide-hoch/links, wipe, fade) fuer Dynamik — NICHT nur "cut". Mische sie. Ein "flash" am dramatischsten Moment.

So baust du ein starkes Video:
- HOOK (Segment 1): custom-Komponente oder wortpop — stark, stoppt den Scroll
- PROBLEM: z.B. custom-problem-karten (reiche UI-Elemente)
- LOESUNG/BEWEIS: custom-erfolg-moment, zahl, oder eine passende custom-Komponente
- CTA (letztes Segment): kurz, klar
Uebergaenge: "cut" (harter Schnitt, Standard), fliessende Motion-Uebergaenge "slide-links/rechts/hoch/runter", "wipe", "fade" (die reiche Szene gleitet/wischt rein!), "flash" (Limette-Blitz). Mische bewusst: nicht nur cuts — nutze slide/wipe fuer Dynamik zwischen den Szenen, flash am dramatischsten Moment. Dauer je Segment passend zur Komponente (bei custom >= deren dauerSek).

WICHTIG: Wenn dir fuer ein Segment eine passende Komponente fehlt, BAU SIE ZUERST mit 'komponente_bauen' und nutze sie dann im story_video. So entstehen mit der Zeit immer bessere Videos.

═══ ECHTES PRODUKT-MATERIAL ═══
Das echte Bueroflow-Dashboard/UI kommt als Aufnahme vom Recorder-Bot (nicht von dir). In deinem Konzept PLANST du, wo echtes UI-Material eingefuegt werden soll (z.B. "hier Dashboard-Clip zeigen"). Du generierst KEINE Fake-UIs.

═══ HIGGSFIELD-HINTERGRUND (Nebenwerkzeug, Tool 'vibe_clip') ═══
Fuer atmosphaerische, cineastische HINTERGRUND-Clips (fliessende Texturen, Stimmung) kannst du Higgsfield nutzen — NUR abstrakt, kein Produkt/Logo/Text. Das legt man spaeter HINTER das Motion-Design. Nutze das sparsam (kostet Credits), nur wenn ein cineastischer Hintergrund den Look hebt. Standardmaessig reicht Motion-Design allein.

═══ EIGENE KOMPONENTEN BAUEN (Komponenten-Schmiede) ═══
Du bist nicht auf die festen Stile beschraenkt. Mit dem Tool 'komponente_bauen' kannst du EIGENE Motion-Komponenten in Remotion (JSX) schreiben — fuer Effekte, die es noch nicht gibt. So wird das Studio mit der Zeit besser: du kombinierst Vorhandenes und erfindest Neues.

TIPP: Bevor du eine neue Komponente baust, lies bei Bedarf einen Motion-Skill ('motion-design' fuer Timing/Easing/Disney-Prinzipien/Choreografie, 'motion-principles' um AI-Slop zu vermeiden, 'ui-animation' fuer konkrete Easing-Kurven/Reveals). Das hebt die Qualitaet deutlich.

REGELN fuer den JSX-Code:
- MUSS zwei Exports haben: `export const meta = {{ dauerSek: N, defaultProps: {{...}} }};` und `export const Komponente = (props) => {{ ... }};`
- Importiere Bausteine relativ: `import {{ EXPO, TextBlock, Surface, FlashOverlay, StoryHintergrund, useKameraPush }} from "../motion_helpers.jsx";` und `import {{ BRAND, logoFuer }} from "../brand.js";`
- Nutze `useVideoConfig()` fuer width/height (damit es in allen Formaten laeuft) und `useCurrentFrame()`.
- HALTE DICH AN DIE MOTION-DNA: easeOutExpo (EXPO) als Kurve, KEIN Bounce/Elastic. Text auf Surface (Glas/Card), nie nackt. Metronomisch. Max 2 Dekor-Elemente. Subtile Bewegung statt Zappeln.
- Verfuegbare Bausteine: EXPO (Easing), TextBlock (Fade+Blur-Text), Surface (Glas/Card), FlashOverlay (Pivot-Blitz), StoryHintergrund (Blob-BG), useKameraPush (Scale-Push). BRAND.paletten.{{dunkel,hell,gruen,limette}} mit .hintergrund/.text/.akzent.

GRAFIK-BAUSTEINE fuer visuellen Reichtum (import aus "../grafik.jsx"):
- Icon: <Icon name="rechnung" groesse={{48}} farbe={{p.akzent}} delay={{10}} /> — verfuegbare Namen: rechnung, dokument, mail, uhr, sanduhr, check, euro, warnung, blitz, karte, glocke, kalender, prozent, pfeil, x, robot, stapel
- Pille: <Pille text="Rechtssicher" icon="check" akzent={{p.akzent}} hell={{hell}} farbe={{p.text}} delay={{12}} /> — kleines Badge mit Icon+Text
- MiniKarte: <MiniKarte titel="Zahlung offen" zeile="Seit 21 Tagen" statusIcon="warnung" statusFarbe="#ff5a5a" hell={{hell}} akzent={{p.akzent}} delay={{8}} /> — App-UI-Snippet (wie in Referenzen!)
- CheckZeichnen: <CheckZeichnen groesse={{90}} farbe={{p.akzent}} delay={{10}} /> — Haekchen das sich zeichnet
- Ring: <Ring groesse={{120}} farbe={{p.akzent}} prozent={{100}} delay={{6}} /> — Fortschritts-Ring der sich fuellt

WICHTIG fuer Reichtum: Deine Referenzen leben von UI-Elementen (Karten, Pillen, Icons, Status-Meldungen), NICHT nur Text auf Panel. Baue diese Grafik-Bausteine ein — z.B. eine MiniKarte "Payment failed"-Style, mehrere Pillen als Feature-Liste, ein Haekchen-Moment beim Erfolg. Das hebt den Look deutlich. Halte dich trotzdem an "max 2-3 Elemente gleichzeitig, clean".

VORLAGE (Beispiel-Template, an dem du dich orientierst):
```jsx
import React from "react";
import {{ AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, Easing }} from "remotion";
import {{ BRAND }} from "../brand.js";
import {{ EXPO, TextBlock, Surface, StoryHintergrund }} from "../motion_helpers.jsx";

export const meta = {{ dauerSek: 4, defaultProps: {{ text: "Beispiel", palette: "dunkel" }} }};

export const Komponente = ({{ text = "Text", palette = "dunkel" }}) => {{
  const frame = useCurrentFrame();
  const {{ width, height }} = useVideoConfig();
  const istHoch = height > width;
  const p = BRAND.paletten[palette] || BRAND.paletten.dunkel;
  const groesse = istHoch ? width * 0.07 : height * 0.09;
  return (
    <AbsoluteFill style={{{{ background: p.hintergrund, fontFamily: BRAND.fonts.display }}}}>
      <StoryHintergrund p={{p}} />
      <AbsoluteFill style={{{{ justifyContent: "center", alignItems: "center" }}}}>
        <Surface art="glas" akzent={{p.akzent}} hell={{p.text !== "#FFFFFF"}}
          breite={{istHoch ? "82%" : "62%"}} padding={{istHoch ? "9% 7%" : "6% 6%"}}>
          <TextBlock text={{text}} groesse={{groesse}} farbe={{p.text}} delay={{4}} />
        </Surface>
      </AbsoluteFill>
    </AbsoluteFill>
  );
}};
```

VORGEHEN: Schreib den Code, rufe 'komponente_bauen' auf. Bei Fehler bekommst du die Meldung — korrigiere und wiederhole. Wenn es klappt, ist der neue Stil 'custom-NAME' sofort nutzbar (auch in Story-Segmenten spaeter). Erfinde neue Komponenten sparsam und gezielt — wenn ein vorhandener Stil reicht, nutze den.

═══ REFERENZ-VIDEOS ANALYSIEREN ═══
Rui kann Referenz-Videos (Vorbilder fuer den Stil) nach vault/referenzen/ hochladen. Mit dem Tool 'referenz_analysieren' schaust du sie dir an (Bild-KI) und verstehst die Motion-Sprache: Kamerabewegung, Tempo, Text-Animation, Uebergaenge, Look. Wenn Rui einen bestimmten Look will oder eine Referenz erwaehnt, analysiere sie ZUERST — dann triffst du den Stil praezise statt zu raten.

═══ DEIN MARKETING-WISSEN (Skills) ═══
Du hast Zugriff auf Experten-Skill-Dokumente. Nutze das Tool 'skill_lesen' GEZIELT beim Konzipieren — nicht wahllos, sondern was zum Auftrag passt. Ein Profi schlaegt nach, statt zu raten.

Verfuegbare Skills:
{skill_liste_text()}

Faustregel: Bei einem neuen Video-Konzept lies 1-2 passende Skills (z.B. 'marketing-psychology' fuer den Hook + 'social' fuer Plattform-Mechanik), bevor du das Konzept entwirfst. Bei Ad-Kampagnen zusaetzlich 'ad-creative'/'ads'. So bringst du echtes Marketing-Handwerk ein statt Bauchgefuehl.

═══ VIDEO-LAENGE & STORY ═══
Fertige Videos sollen eine echte Story haben, nicht nur 5 Sekunden:
- TikTok/Reels: ca. 25-30 Sekunden, schneller Schnitt, starker Hook in den ersten 2 Sek.
- LinkedIn: kann laenger, ruhiger, nutzenorientierter sein.
Ein starkes Video hat einen Bogen: HOOK (Aufmerksamkeit) -> PROBLEM (Schmerzpunkt) -> LOESUNG (Bueroflow) -> BEWEIS/NUTZEN -> CTA.
Plane die Story in mehreren Segmenten und nutze passende Stile pro Segment (z.B. wortpop fuer den Hook, szenen fuer Problem/Loesung, zahl fuer Beweis).

═══ ABLAUF ═══
Bei einem Auftrag ("mach ein LinkedIn-Video ueber E-Rechnungspflicht"):
1. Optional: kurz Trends/Hooks recherchieren (Websuche).
2. KONZEPT entwerfen: Hook, Kernbotschaft, welcher Stil, welche Texte, welches Format, wo echtes UI-Material hin soll.
3. Zeig Rui das Konzept ZUERST — ausser er sagt direkt "mach das Video".
4. Bei Zustimmung: 'motion_video' aufrufen, dann Dateipfad nennen.

Antworte auf Deutsch, konkret, als echter Kreativ-Regisseur mit Gespuer fuer modernes Motion-Design. Keine Aufzaehlungen ohne Substanz."""


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
    {
        "name": "motion_video",
        "description": ("Erstellt ein Motion-Design-Video ueber den Render-Server (Bueroflow-Brandkit, 60fps). "
                        "Waehle Stil, Palette, Format und liefere die Texte. Gibt den Dateipfad zurueck."),
        "input_schema": {
            "type": "object",
            "properties": {
                "stil": {"type": "string", "enum": ["szenen", "wortpop", "zahl", "formen", "kinetic"],
                         "description": "Motion-Stil"},
                "format": {"type": "string", "enum": ["tiktok", "linkedin", "quadrat"],
                           "description": "tiktok=9:16, linkedin=16:9, quadrat=1:1"},
                "palette": {"type": "string", "enum": ["dunkel", "hell", "gruen", "limette"],
                            "description": "Farbwelt (Standard: dunkel)"},
                "props": {"type": "object",
                          "description": "Stil-spezifische Inhalte. szenen:{szenen:[...]}, wortpop:{worte:[...],akzentWort:-1}, zahl:{zielZahl,suffix,vortext,nachtext}, formen:{zeilen:[...]}, kinetic:{zeilen:[...],akzentZeile:1}"},
                "beschreibung": {"type": "string", "description": "Kurz auf Deutsch: was zeigt das Video / wofuer"},
            },
            "required": ["stil", "format", "props", "beschreibung"],
        },
    },
    {
        "name": "skill_lesen",
        "description": ("Liest ein Marketing-Skill-Dokument (Experten-Wissen) fuer besseren Video-Content. "
                        "Nutze das GEZIELT beim Konzipieren: z.B. 'marketing-psychology' fuer Hooks/Trigger, "
                        "'social' fuer Short-Form-Mechanik, 'content-strategy' fuer Story-Arc, 'ad-creative' fuer Werbe-Konzepte."),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Skill-Name aus der Liste im System-Prompt"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "referenz_analysieren",
        "description": ("Analysiert ein Referenz-Video (das Rui als Vorbild hochgeladen hat) mit Bild-KI. "
                        "Extrahiert Frames und beschreibt die Motion-Sprache konkret: Kamerabewegung, Schnitt-Rhythmus, "
                        "Text-Animation, Uebergaenge, Look. Nutze das, um Ruis gewuenschten Stil praezise zu verstehen."),
        "input_schema": {
            "type": "object",
            "properties": {
                "datei": {"type": "string", "description": "Dateiname im Ordner vault/referenzen/ (z.B. 'refined1.mp4')"},
                "fokus": {"type": "string", "description": "Optional: worauf besonders achten (z.B. 'die Kamerabewegung')"},
            },
            "required": ["datei"],
        },
    },
    {
        "name": "komponente_bauen",
        "description": ("Baut eine NEUE Motion-Komponente (Remotion JSX) und test-rendert sie sofort. "
                        "Nutze das, wenn die vorhandenen Stile fuer eine Idee nicht reichen und du einen neuen Effekt brauchst. "
                        "Die Komponente wird dauerhaft als Stil 'custom-NAME' verfuegbar. Bei Render-Fehler wird sie verworfen — "
                        "du bekommst die Fehlermeldung und kannst korrigieren."),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Kurzer Name, kleinbuchstaben/zahlen/bindestrich (z.B. 'split-reveal')"},
                "jsx_code": {"type": "string", "description": "Vollstaendiger JSX-Code. MUSS `export const meta` und `export const Komponente` enthalten. Nutze die Bausteine aus ../motion_helpers.jsx und ../brand.js."},
                "test_props": {"type": "object", "description": "Props zum Test-Rendern (sollten zu meta.defaultProps passen)"},
                "format": {"type": "string", "enum": ["tiktok", "linkedin", "quadrat"], "description": "Test-Format (Standard tiktok)"},
            },
            "required": ["name", "jsx_code"],
        },
    },
    {
        "name": "story_video",
        "description": ("Rendert ein KOMPLETTES Story-Video aus mehreren Segmenten zu einem zusammenhaengenden Clip. "
                        "Jedes Segment kann ein Grundstil (szenen/wortpop/zahl/formen/kinetic) ODER eine deiner "
                        "custom-Komponenten (stil: 'custom-NAME') sein. So baust du volle 20-30-Sek-Videos mit Story-Arc."),
        "input_schema": {
            "type": "object",
            "properties": {
                "format": {"type": "string", "enum": ["tiktok", "linkedin", "quadrat"]},
                "palette": {"type": "string", "enum": ["dunkel", "hell", "gruen", "limette"]},
                "segmente": {
                    "type": "array",
                    "description": "Liste der Segmente in Reihenfolge. Jedes: {stil, props, dauer (Sek), surface (glas/card), uebergang (cut/dissolve/flash)}. Bei custom-Komponenten dauer >= deren dauerSek waehlen.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "stil": {"type": "string", "description": "Grundstil oder 'custom-NAME'"},
                            "props": {"type": "object"},
                            "dauer": {"type": "number", "description": "Sekunden"},
                            "surface": {"type": "string", "enum": ["glas", "card"]},
                            "uebergang": {"type": "string", "enum": ["cut", "fade", "slide-links", "slide-rechts", "slide-hoch", "slide-runter", "wipe", "flash"], "description": "cut=harter Schnitt, fade/slide/wipe=fliessende Motion-Uebergaenge, flash=Limette-Blitz"},
                        },
                        "required": ["stil", "dauer"],
                    },
                },
                "sfx": {
                    "type": "array",
                    "description": "Optional: Sound-Effekte mit Timing. Jeder: {datei (Name ohne .mp3 oder 'sfx/name.mp3'), bei_sek (wann im Video), lautstaerke (0-1, Standard 0.7)}.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "datei": {"type": "string"},
                            "bei_sek": {"type": "number"},
                            "lautstaerke": {"type": "number"},
                        },
                        "required": ["datei", "bei_sek"],
                    },
                },
                "beschreibung": {"type": "string"},
            },
            "required": ["segmente"],
        },
    },
    {
        "name": "sfx_generieren",
        "description": ("Generiert einen Sound-Effekt (Whoosh, Pop, Impact, Chime, Ambience) via ElevenLabs aus einer "
                        "Textbeschreibung und speichert ihn. Nutze das, um passende SFX fuer deine Videos zu erzeugen — "
                        "z.B. ein Whoosh fuer Uebergaenge, ein Erfolgs-Chime beim Bezahlt-Moment."),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Dateiname, kleinbuchstaben/zahlen/bindestrich (z.B. 'whoosh-up')"},
                "beschreibung": {"type": "string", "description": "Was fuer ein Sound (englisch praeziser: 'short clean whoosh transition', 'success chime UI', 'deep impact hit')"},
                "dauer_sek": {"type": "number", "description": "Optional, 0.5-30. Weglassen fuer auto."},
                "loop": {"type": "boolean", "description": "true fuer Ambience/Beds die nahtlos loopen"},
            },
            "required": ["name", "beschreibung"],
        },
    },
]
TOOLS_CACHED = [*TOOLS[:-1], {**TOOLS[-1], "cache_control": {"type": "ephemeral"}}]


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


def tool_story_video(inp, r):
    """Rendert ein komplettes Story-Video aus mehreren Segmenten (Grundstile ODER custom-Komponenten)."""
    fmt = inp.get("format", "tiktok")
    palette = inp.get("palette", "dunkel")
    segmente = inp.get("segmente") or []
    beschreibung = inp.get("beschreibung", "Story-Video")
    if not segmente:
        return "Keine Segmente uebergeben. Gib eine Liste von Segmenten mit stil/props/dauer/uebergang an."

    # Segmente aufbereiten: custom-Stile beginnen mit 'custom-'
    aufbereitet = []
    for seg in segmente:
        aufbereitet.append({
            "stil": seg.get("stil", "szenen"),
            "props": seg.get("props") or {},
            "dauer": seg.get("dauer", 3),
            "surface": seg.get("surface", "glas"),
            "uebergang": seg.get("uebergang", "cut"),
        })

    # SFX aufbereiten: bei_sek -> Frame (60fps), Dateiname normalisieren
    sfx_liste = []
    for s_ in (inp.get("sfx") or []):
        datei = s_.get("datei", "")
        if not datei:
            continue
        if not datei.startswith("sfx/"):
            datei = f"sfx/{datei}"
        if not datei.endswith(".mp3"):
            datei = datei + ".mp3"
        sfx_liste.append({
            "datei": datei,
            "frame": int(round(float(s_.get("bei_sek", 0)) * 60)),
            "lautstaerke": float(s_.get("lautstaerke", 0.7)),
        })

    props = {"palette": palette, "logo": True, "segmente": aufbereitet, "sfx": sfx_liste}
    komposition = f"story-{fmt}"
    rid = f"story-{uuid.uuid4().hex[:8]}"
    auftrag = {"id": rid, "komposition": komposition, "props": props}
    try:
        r.rpush("bot:render:inbox", json.dumps(auftrag, ensure_ascii=False))
    except Exception as e:
        return f"Konnte Story-Auftrag nicht senden: {e}"
    gesamt = sum(seg["dauer"] for seg in aufbereitet)
    log(f"[render] Story {komposition} ({len(aufbereitet)} Segmente, ~{gesamt:.0f}s) gesendet ...")
    reply_q = f"bot:render:reply:{rid}"
    for _ in range(96):  # bis 8 Min (Story rendert laenger)
        try:
            res = r.blpop(reply_q, timeout=5)
        except Exception:
            time.sleep(2); continue
        if res:
            _, antwort = res
            if antwort.startswith("FEHLER") or "fehlgeschlagen" in antwort.lower():
                arbeit_log("Story fehlgeschlagen", beschreibung, antwort[:200])
                return f"Story-Render FEHLGESCHLAGEN:\n{antwort[:600]}"
            arbeit_log("Story-Video gerendert", beschreibung, antwort[:200])
            return f"{beschreibung} ({len(aufbereitet)} Segmente, ~{gesamt:.0f}s)\n{antwort}"
    return "Story-Render-Timeout — spaeter in vault/videos/ nachsehen."


def tool_motion_video(inp, r):
    """Schickt einen Render-Auftrag an den Render-Server und wartet auf das fertige MP4."""
    stil = inp.get("stil", "szenen")
    fmt = inp.get("format", "tiktok")
    palette = inp.get("palette", "dunkel")
    props = inp.get("props") or {}
    beschreibung = inp.get("beschreibung", "Motion-Video")
    # Palette + logo in die props (Kompositionen erwarten das dort)
    props.setdefault("palette", palette)
    props.setdefault("logo", True)
    komposition = f"{stil}-{fmt}"
    rid = f"regie-{uuid.uuid4().hex[:8]}"
    auftrag = {"id": rid, "komposition": komposition, "props": props}
    try:
        r.rpush("bot:render:inbox", json.dumps(auftrag, ensure_ascii=False))
    except Exception as e:
        return f"Konnte Render-Auftrag nicht senden: {e}"
    log(f"[render] Auftrag {komposition} gesendet, warte auf Ergebnis ...")
    # auf Antwort warten (Render dauert; grosszuegig pollen, bis ~6 Min)
    reply_q = f"bot:render:reply:{rid}"
    for _ in range(72):  # 72 x 5s = 6 Min
        try:
            res = r.blpop(reply_q, timeout=5)
        except Exception:
            time.sleep(2); continue
        if res:
            _, antwort = res
            arbeit_log("Motion-Video gerendert", beschreibung, antwort[:200])
            return f"{beschreibung}\n{antwort}"
    return "Render-Timeout — der Server braucht ungewoehnlich lange. Spaeter in vault/videos/ nachsehen."


MAX_FRAMES = int(os.getenv("REF_MAX_FRAMES", "12"))

def _video_dauer(pfad):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", pfad],
            capture_output=True, text=True, timeout=30)
        return float(out.stdout.strip())
    except Exception:
        return 0.0

def tool_referenz_analysieren(inp):
    """Extrahiert Frames aus einem Referenzvideo und laesst Claude Vision die Motion-Sprache analysieren."""
    datei = inp.get("datei", "")
    fokus = inp.get("fokus", "")
    if not datei:
        return "Bitte 'datei' angeben (Dateiname im Ordner vault/referenzen/)."
    pfad = datei if os.path.isabs(datei) else os.path.join(REFERENZ_DIR, datei)
    if not os.path.exists(pfad):
        vorhanden = ", ".join(os.listdir(REFERENZ_DIR)) if os.path.isdir(REFERENZ_DIR) else "(Ordner fehlt)"
        return f"Datei nicht gefunden: {pfad}. Vorhanden in vault/referenzen/: {vorhanden}"

    dauer = _video_dauer(pfad)
    if dauer <= 0:
        return "Konnte Videodauer nicht lesen — ist die Datei ein gueltiges Video?"
    # fps so waehlen, dass ~MAX_FRAMES gleichmaessig verteilte Frames rauskommen
    fps = max(0.5, min(3.0, MAX_FRAMES / dauer))

    tmp = tempfile.mkdtemp(prefix="refframes_")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", pfad, "-vf", f"fps={fps:.3f},scale=512:-1",
             "-frames:v", str(MAX_FRAMES), os.path.join(tmp, "f_%03d.jpg")],
            capture_output=True, text=True, timeout=120)
        frames = sorted(glob.glob(os.path.join(tmp, "f_*.jpg")))[:MAX_FRAMES]
        if not frames:
            return "Konnte keine Frames extrahieren (ffmpeg-Problem)."

        content = []
        for i, fr in enumerate(frames):
            with open(fr, "rb") as fh:
                b64 = base64.standard_b64encode(fh.read()).decode()
            content.append({"type": "text", "text": f"Frame {i+1}/{len(frames)} (t~{i/fps:.1f}s):"})
            content.append({"type": "image", "source": {"type": "base64",
                            "media_type": "image/jpeg", "data": b64}})
        anweisung = (
            "Du bist Motion-Design-Analyst. Diese Frames stammen (zeitlich geordnet) aus einem "
            "Referenz-Video, das Rui als Vorbild fuer seinen Video-Stil nutzt. Analysiere die MOTION-SPRACHE "
            "konkret und umsetzbar, damit ein Remotion-Motion-Designer sie nachbauen kann:\n"
            "1. KAMERA/BEWEGUNG: Zoom, Pan, Parallax, Perspektive? Ruhig oder dynamisch? Kontinuierlich?\n"
            "2. SCHNITT-RHYTHMUS: Wie schnell wechseln Szenen/Elemente? Grob in Sekunden.\n"
            "3. TEXT-ANIMATION: Wie kommen Texte rein (Wisch, Blur, Scale, Buchstaben)? Timing?\n"
            "4. UEBERGAENGE: Welche Art (Cut, Wipe, Slide, Morph, Masken)?\n"
            "5. LOOK: Farben, Kontrast, Glas/Blur, Textur, Tiefe.\n"
            "6. AUFBAU: Erkennbarer Story-Arc (Hook->...)?\n"
            "7. KONKRETE TIPPS: 3-5 Dinge, die man uebernehmen sollte, um DIESEN Look zu treffen.\n"
            "Antworte auf Deutsch, strukturiert, praezise. Keine Floskeln."
        )
        if fokus:
            anweisung += f"\n\nBesonderer Fokus von Rui: {fokus}"
        content.append({"type": "text", "text": anweisung})

        log(f"[referenz] analysiere {len(frames)} Frames aus {datei} (Dauer {dauer:.1f}s)")
        resp = client.messages.create(model=MODEL, max_tokens=1800,
                                      messages=[{"role": "user", "content": content}])
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        arbeit_log("Referenz analysiert", datei, text[:200])
        return f"Motion-Analyse von '{datei}' ({dauer:.0f}s, {len(frames)} Frames):\n\n{text}"
    finally:
        for fr in glob.glob(os.path.join(tmp, "*")):
            try: os.remove(fr)
            except Exception: pass
        try: os.rmdir(tmp)
        except Exception: pass


import re as _re

def tool_komponente_bauen(inp, r):
    """Schreibt eine neue Motion-Komponente (JSX) nach vault/custom/ und test-rendert sie.
    Bei Render-Fehler wird die Datei wieder entfernt (Sicherheitsnetz)."""
    name = inp.get("name", "").strip().lower()
    code = inp.get("jsx_code", "")
    test_props = inp.get("test_props") or {}
    fmt = inp.get("format", "tiktok")

    if not _re.fullmatch(r"[a-z0-9][a-z0-9\-]{1,40}", name or ""):
        return "Ungueltiger Name. Erlaubt: kleinbuchstaben, zahlen, bindestrich (2-41 Zeichen)."
    if "export const Komponente" not in code and "export const meta" not in code:
        return "Der Code muss `export const meta` UND `export const Komponente` enthalten. Nutze das Beispiel-Template als Vorlage."

    os.makedirs(CUSTOM_DIR, exist_ok=True)
    pfad = os.path.join(CUSTOM_DIR, f"{name}.jsx")
    neu = not os.path.exists(pfad)
    # Backup bei Ueberschreiben
    backup = None
    if not neu:
        with open(pfad, encoding="utf-8") as f:
            backup = f.read()
    with open(pfad, "w", encoding="utf-8") as f:
        f.write(code)
    log(f"[schmiede] {name}.jsx geschrieben, test-rendere ...")

    # Test-Render ueber den Render-Server
    rid = f"schmiede-{uuid.uuid4().hex[:8]}"
    komposition = f"custom-{name}-{fmt}"
    auftrag = {"id": rid, "komposition": komposition, "props": test_props}
    try:
        r.rpush("bot:render:inbox", json.dumps(auftrag, ensure_ascii=False))
    except Exception as e:
        return f"Datei geschrieben, aber Test-Render konnte nicht gesendet werden: {e}"

    reply_q = f"bot:render:reply:{rid}"
    for _ in range(72):  # bis 6 Min
        try:
            res = r.blpop(reply_q, timeout=5)
        except Exception:
            time.sleep(2); continue
        if res:
            _, antwort = res
            if antwort.startswith("FEHLER") or "fehlgeschlagen" in antwort.lower():
                # zuruecksetzen
                if backup is not None:
                    with open(pfad, "w", encoding="utf-8") as f:
                        f.write(backup)
                    hinweis = "(alte Version wiederhergestellt)"
                else:
                    try: os.remove(pfad)
                    except Exception: pass
                    hinweis = "(fehlerhafte Datei entfernt)"
                arbeit_log("Komponente fehlgeschlagen", name, antwort[:200])
                return f"Test-Render FEHLGESCHLAGEN {hinweis}. Fehler:\n{antwort[:600]}\n\nKorrigiere den Code und versuch es erneut."
            arbeit_log("Komponente gebaut", name, antwort[:200])
            return (f"Komponente '{name}' gebaut & getestet. Verfuegbar als Stil 'custom-{name}' "
                    f"in allen Formaten. Test-Video: {antwort}")
    return "Test-Render-Timeout — Status unklar. Spaeter pruefen."


def tool_sfx_generieren(inp):
    """Generiert einen Sound-Effekt via ElevenLabs Sound Effects API und speichert ihn nach vault/sfx/."""
    beschreibung = inp.get("beschreibung", "").strip()
    name = inp.get("name", "").strip().lower()
    dauer = inp.get("dauer_sek")
    loop = bool(inp.get("loop", False))
    if not beschreibung or not name:
        return "Bitte 'beschreibung' (was fuer ein Sound) und 'name' (Dateiname) angeben."
    if not ELEVENLABS_KEY:
        return "ELEVENLABS_API_KEY fehlt in der .env."
    import re as _re
    if not _re.fullmatch(r"[a-z0-9][a-z0-9\-]{1,40}", name):
        return "Ungueltiger Name. Erlaubt: kleinbuchstaben, zahlen, bindestrich."

    os.makedirs(SFX_DIR, exist_ok=True)
    payload = {"text": beschreibung, "prompt_influence": inp.get("prompt_influence", 0.5)}
    if dauer is not None:
        try:
            payload["duration_seconds"] = max(0.5, min(30.0, float(dauer)))
        except Exception:
            pass
    if loop:
        payload["loop"] = True

    try:
        resp = requests.post(
            "https://api.elevenlabs.io/v1/sound-generation",
            headers={"xi-api-key": ELEVENLABS_KEY, "Content-Type": "application/json"},
            data=json.dumps(payload), timeout=120)
    except Exception as e:
        return f"ElevenLabs-Anfrage fehlgeschlagen: {e}"
    if resp.status_code != 200:
        return f"ElevenLabs-Fehler {resp.status_code}: {resp.text[:200]}"

    pfad = os.path.join(SFX_DIR, f"{name}.mp3")
    try:
        with open(pfad, "wb") as f:
            f.write(resp.content)
    except Exception as e:
        return f"Konnte SFX nicht speichern: {e}"
    kb = len(resp.content) // 1024
    arbeit_log("SFX generiert", name, beschreibung[:80])
    log(f"[sfx] {name}.mp3 gespeichert ({kb} KB)")
    return f"SFX '{name}' erstellt ({kb} KB). In Videos einsetzbar als sfx-Datei 'sfx/{name}.mp3'."


def run_tool(name, inp, r=None):
    if name == "websuche":
        return tool_websuche(inp.get("query", ""))
    if name == "vibe_clip":
        return tool_vibe_clip(inp)
    if name == "motion_video":
        return tool_motion_video(inp, r)
    if name == "story_video":
        return tool_story_video(inp, r)
    if name == "skill_lesen":
        return lade_skill(inp.get("name", ""))
    if name == "referenz_analysieren":
        return tool_referenz_analysieren(inp)
    if name == "komponente_bauen":
        return tool_komponente_bauen(inp, r)
    if name == "sfx_generieren":
        return tool_sfx_generieren(inp)
    return f"Unbekanntes Tool: {name}"


# ── DENKEN ───────────────────────────────────────────────────
def think(history, user_text, bilder=None, r=None):
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
                result = run_tool(block.name, block.input or {}, r)
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
                antwort = think(history, text, bilder=bilder, r=r)
            except Exception as e:
                antwort = f"Fehler: {type(e).__name__}: {e}"
                log(f"[think] {antwort}")
            _antwort_senden(r, reply_q, antwort)
        except Exception as e:
            log(f"[loop] {e}")
            time.sleep(3)


if __name__ == "__main__":
    main()
