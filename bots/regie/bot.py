#!/usr/bin/env python3
"""
REGIE-BOT — Kopf des JARVIS Studio-Teams
- Queue: bot:regie:inbox / bot:regie:reply:<id>
- Entwickelt Video-Konzepte im Vibe-Motion-Stil (Hook, Story-Arc, Plattform)
- Wertet Trends aus (Websuche), schlaegt Hooks vor
- Generiert die Vibe-Motion-Clips SELBST ueber die Higgsfield-API
- WICHTIG: KI-Clips (Higgsfield) zeigen NIE echtes Produkt/Logo/UI — nur atmosphaerische Vibe-Teile (Motion, Textur, Stimmung).
  Echtes Büroflow-UI baust du als CODE-NACHBAU nach (ui_aus_github + komponente_bauen), NICHT als Screenshot.

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
VIDEOS_DIR = os.path.join(VAULT_DIR, "videos") # fertige Renders (fuer Selbst-Review)
HF_DIR    = os.path.join(VAULT_DIR, "higgsfield")  # heruntergeladene Higgsfield-Clips
POSTS_DIR = os.path.join(VAULT_DIR, "posts")   # Publishing-Entwuerfe (Markdown)

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
MUSIK_DIR = os.getenv("MUSIK_DIR", "/app/vault/musik")
# ── GITHUB (Büroflow-Repo lesen, fuer 1:1-UI-Nachbau) ───────
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "lopesrui111-source/Buroflow")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
GITHUB_MAX_ZEICHEN = 60000
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

DEINE ROLLE: Du bist der kreative Kopf fuer Video-Content von Büroflow (buroflow.de) — einem deutschen KI-SaaS mit vier Tools (Mahnflow, Mailflow, Angebotsflow, E-Rechnungsflow). Zielgruppe: Selbststaendige, Freelancer, kleine Unternehmen.

DEIN HAUPTWERKZEUG: MOTION-DESIGN. Du erstellst hochwertige Motion-Graphics-Videos (animierter Text, Glasoptik, bewegte Formen, Kinetic Typography) ueber den Render-Server (Tool 'motion_video'). Das ist praezises, marken-konformes Motion-Design im Büroflow-Look — KEIN fotorealistisches KI-Video.

STIL: Modern, premium, mit Punch. Büroflow-Brandkit ist fest eingebaut (Farben, Geist-Schrift, Logo). Standard-Look: dunkel mit Limette-Akzent (#C8FF47). Weitere Paletten je nach Stimmung verfuegbar.

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

═══ HINTERGRUND-MUSIK (Tool 'musik_generieren') ═══
Ein Musik-Track unter dem Video traegt den Rhythmus — das macht Motion-Videos erst "fertig". Generiere einen passenden Track (Stil/Mood auf Englisch) in Video-Laenge, dann gib ihn im story_video mit: musik: "name", musik_lautstaerke: 0.25 (leise unter den SFX). Fuer Büroflow passt: modern, clean, upbeat-corporate, optimistisch, treibend, ohne Gesang. Generiere pro Vibe EINEN Track, dann wiederverwendbar.
LIZENZ-REGELN (ElevenLabs Music Terms, VERBINDLICH — sonst Lizenzbruch): Im Musik-Prompt NIEMALS verwenden: echte Kuenstler-/Bandnamen, Songwriter-Namen, Songtitel, Albumtitel, Plattenlabel- oder Musikverlag-Namen, oder erkennbare Songtext-Zeilen. Beschreibe NUR Genre, Stimmung, Tempo, Instrumente (z.B. "upbeat corporate, driving synth, optimistic, no vocals, 120bpm"). Formulierungen wie "im Stil von [Kuenstler]" oder "klingt wie [Song]" sind verboten. So bleibt der Track sauber kommerziell nutzbar.
WICHTIG: Musik gehoert IMMER in den 'musik'-Parameter, NIE in die sfx-Liste. Sie laeuft automatisch ab Sekunde 0 durchgehend — gib ihr kein bei_sek. SFX sind kurze Einzeleffekte (Whoosh, Impact, Tick), Musik ist der durchgehende Track darunter.

═══ KOMPLETTE VIDEOS BAUEN (Tool 'story_video') ═══
Fuer volle Videos (20-30 Sek) mit Story-Arc verkettest du mehrere Segmente zu EINEM Clip. Jedes Segment ist entweder ein Grundstil ODER eine deiner selbstgebauten custom-Komponenten (stil: "custom-NAME").

Verfuegbare custom-Komponenten: {custom_komponenten_liste()}

TEMPO & RHYTHMUS (WICHTIG — sonst wirkt es langsam/langweilig):
- Grundstil-Segmente (wortpop/szenen/zahl/formen/kinetic): KURZ halten, 1.5-2.5 Sek pro Segment. Schneller Schnitt = dynamisch.
- Reiche custom-Komponenten (problem-karten, erfolg-moment) sind LANG (7-8s Mini-Videos). Nutze sie SPARSAM als "Hero-Moment" (max 1-2 pro Video), NICHT als schnelle Schnittfolge.
- Ein gutes 25-30s-Video: viele kurze Segmente + 1-2 reiche Hero-Momente.
- UEBERGAENGE: Nutze fliessende Uebergaenge (slide-hoch/links, wipe, fade) fuer Dynamik — NICHT nur "cut". Mische sie. Ein "flash" am dramatischsten Moment.

ECHTES BUEROFLOW-UI (immer als CODE-NACHBAU, nicht als Screenshot):
Als "Beweis"-Moment (nach dem Problem, als Loesung: "so sieht's in Büroflow aus") ist echtes UI der staerkste Vertrauensbeweis. Baue es IMMER als Code-Nachbau ein — nutze eine fertige custom-Komponente (custom-dashboard-hero, custom-tool-karten) oder baue mit ui_aus_github + komponente_bauen eine neue nach dem echten Repo-Code. Das ist vektorscharf, animierbar (Zahlen zaehlen hoch, Karten staffeln rein) und laeuft in jedem Format — einem statischen Screenshot in jeder Hinsicht ueberlegen.
(Der alte Segment-Stil "ui-clip" fuer statische Screenshots existiert technisch noch, wird aber NICHT mehr genutzt — echtes UI kommt als Code-Nachbau.)

So baust du ein starkes Video:
- HOOK (Segment 1): custom-Komponente oder wortpop — stark, stoppt den Scroll
- PROBLEM: z.B. custom-problem-karten (reiche UI-Elemente)
- LOESUNG/BEWEIS: custom-erfolg-moment, zahl, oder eine passende custom-Komponente
- CTA (letztes Segment): kurz, klar
Uebergaenge: "cut" (harter Schnitt, Standard), fliessende Motion-Uebergaenge "slide-links/rechts/hoch/runter", "wipe", "fade" (die reiche Szene gleitet/wischt rein!), "flash" (Limette-Blitz). Mische bewusst: nicht nur cuts — nutze slide/wipe fuer Dynamik zwischen den Szenen, flash am dramatischsten Moment. Dauer je Segment passend zur Komponente (bei custom >= deren dauerSek).

WICHTIG: Wenn dir fuer ein Segment eine passende Komponente fehlt, BAU SIE ZUERST mit 'komponente_bauen' und nutze sie dann im story_video. So entstehen mit der Zeit immer bessere Videos.

═══ ECHTES BUEROFLOW-UI 1:1 NACHBAUEN (Tool 'ui_aus_github') ═══
Das staerkste Material sind nicht Screenshots, sondern das UI als CODE-NACHBAU: vektorscharf, in jedem Format, und vor allem ANIMIERBAR (Zahlen zaehlen hoch, Karten staffeln rein, Charts bauen sich auf, Donut fuellt sich). Genau so ist 'custom-dashboard-hero' entstanden.

Mit 'ui_aus_github' liest du den echten Quellcode aus dem privaten Repo {GITHUB_REPO}. Vorgehen:
1. Ordner listen, um dich zu orientieren (z.B. pfad "components/dashboard" oder "app/dashboard").
2. Die 1-3 relevanten Dateien lesen (z.B. "components/dashboard/dash-sidebar.tsx").
3. Mit 'komponente_bauen' als Remotion-Komponente nachbauen.

UEBERSETZUNGS-REGELN Next.js -> Remotion (wichtig, sonst schlaegt der Render fehl):
- useState/useEffect/Hover -> WEG. Alles frame-basiert ueber useCurrentFrame(), Hover-Zustaende statisch (nicht-gehoverte Variante).
- CountUp/Timer -> Fortschritt aus dem Frame rechnen, Kurve easeOutExpo.
- fetch/API-Daten -> plausible Fake-Daten als Props (DSGVO: NIE echte Kundendaten).
- next/link, next/navigation, Clerk -> raus; Link wird ein div.
- next/image -> <Img src={{staticFile("...")}} /> aus remotion.
- Feste Design-Groesse definieren (z.B. 1600x1000) und per Math.min(width/DESIGN_W, height/DESIGN_H) in den Frame skalieren — dann laeuft es in allen Formaten.
- Tailwind-Klassen -> inline styles (das Dashboard nutzt ohnehin fast nur inline styles).
- Fonts: Bricolage Grotesque (Display) + DM Sans (Text) via @remotion/google-fonts laden, nicht raten.

LAYOUT-REGELN (VERBINDLICH — hier ist beim ersten Versuch am meisten schiefgegangen):
- Lege eine feste Design-Flaeche fest (UI-Nachbau: 1600x900) und skaliere sie per Math.min(width/DESIGN_W, height/DESIGN_H) in den Frame.
- RECHNE die Hoehen aus, schaetze sie nicht: Kartenhoehe = Kopfbereich + Inhalt + Fussbereich, und dieser Wert MUSS exakt aufgehen. Schreib die Rechnung als Kommentar in den Code.
- Pruefe vor dem Rendern: Rand + Zeilen*Hoehe + Gaps <= DESIGN_H minus mindestens 80px Sicherheitsrand. Nichts darf am Bildrand kleben.
- BALANCE: Der Inhalt muss die Design-Flaeche AUSFUELLEN oder vertikal zentriert sein. Bleiben unten mehr als ~120px leer, waehrend oben alles klebt, ist das ein FEHLER — dann den ganzen Block vertikal zentrieren (justifyContent center) oder Elemente grosszuegiger dimensionieren. Rechne nach: oberer Abstand und unterer Abstand sollen ungefaehr gleich sein. Grosse Leerflaechen am unteren Rand sind kein Stilmittel.
- ABER: "Flaeche fuellen" heisst NICHT Elemente strecken. Bloecke behalten ihre inhaltsgerechte Groesse (z.B. Preis-Karte 380-450px hoch). Bleibt Platz uebrig: Block vertikal zentrieren, Abstaende zwischen Bloecken erhoehen ODER echten Inhalt ergaenzen (z.B. Feature-Liste als Bullet-Points) — niemals ein einzelnes Element auf Flaeche aufblasen. Ein Loch >80px zwischen zwei Elementen INNERHALB eines Blocks ist ein Fehler.
- Elemente, die ueber den Blockrand hinausragen (Badges wie "Beliebt", Ecken-Labels), brauchen oben/seitlich Platz im Grid — sonst werden sie abgeschnitten.
- Kein Element darf abgeschnitten werden — besonders Titel und Beschreibungstexte muessen VOLLSTAENDIG sichtbar sein. Wenn Text nicht passt: Schrift/Karte anpassen, nicht abschneiden.
- Kein toter Raum: wenn unter dem Text grosse Leerflaechen bleiben, sind die Karten zu hoch — Hoehe reduzieren, nicht Text aufblaehen.
- Typische Groessen, die funktionieren: Titel 21px, Beschreibung 13.5px (line-height 1.6), Tag/Mono 10-11px, Karten-Radius 16, Innenabstand 26px.
- Motion ueber blosses Reinstaffeln hinaus: Elemente innerhalb der Karte gestaffelt (Icon-Pop, Tag, Titel, Text, Footer), danach EIN wanderndes Spotlight-Licht als Hover-Ersatz. Das macht den Unterschied zwischen "Standbild mit Einblendung" und lebendigem UI.

═══ MOTION-QUALITAET: AFTER-EFFECTS-DICHTE (das Wichtigste fuer gute Videos) ═══
Der Unterschied zwischen "basic" und "professionell" ist DICHTE: mehrere Bewegungs-Ebenen laufen GLEICHZEITIG, nicht nur ein Element blendet ein und friert dann ein. Ein starkes Motion-Segment hat 4-5 Ebenen parallel:
1. HINTERGRUND: driftende Partikel (10-30 kleine Punkte, deterministisch geseedet, NIE Math.random pro Frame) mit Parallax — ferne langsam, nahe schnell. Dazu 1-2 langsam wandernde Radial-Glows.
2. MITTELGRUND: EIN durchlaufendes Element, das sich staendig bewegt — ein schraeger Licht-Balken, der zyklisch durchs Bild sweept, oder eine Linie/Form.
3. VORDERGRUND: Text WORT FUER WORT (oder Zeile fuer Zeile) mit gestaffeltem Overshoot — spring() mit damping ~10-13, sichtbarer Y-Drop + leichte Rotation/Scale. NICHT alles gleichzeitig, NICHT zu frueh: Start ~Frame 8, Abstand 11-13 Frames pro Wort, damit man JEDES einzeln aufploppen sieht.
4. AKZENT: das betonte Wort/Zahl bekommt SEKUNDAERBEWEGUNG waehrend der Haltezeit (Scale-Puls + Glow-Puls per Math.sin(leben/20)), plus optional Unterstrich/Ring/Rahmen.
5. FEINSCHLIFF: HUD-Ecken-Ticks, Kamera-Push (langsamer Scale 1.0->1.05 ueber die Szene).
Wichtig: nichts darf nach dem Eintritt EINFRIEREN. Immer laeuft etwas weiter (Partikel, Balken-Sweep, Puls). Timing-Regel: Eintritt ~erste Sekunde, danach traegt die Sekundaerbewegung. Bei weichem Uebergang (weich=true) die harten Eintritts-Bewegungen abschalten, nur kurzer Fade.

FERTIGE REFERENZ-KOMPONENTEN (im Vault, nutze sie ODER lerne von ihrem Code): custom-kinetic-pro, custom-wortpop-pro, custom-zahl-pro, custom-formen-pro — das sind die alten Grundstile auf AE-Niveau. Bevorzuge sie gegenueber den alten kinetic/wortpop/zahl/formen. Wenn du etwas NEUES baust (mit komponente_bauen), orientiere dich an ihrem Aufbau: lies bei Bedarf ihren Code und uebertrage das Ebenen-Prinzip auf dein neues Motiv. Du bist NICHT auf diese Bausteine beschraenkt — du kannst jederzeit eigene Motion-Szenen erfinden. Das Ebenen-Prinzip ist der Massstab, nicht die konkrete Komponente.

SCHREIBWEISE (KRITISCH, NIE falsch): Der Markenname ist IMMER "Büroflow" — mit ü, gross B. NIEMALS "Bueroflow", "bueroflow" oder "Buroflow" im sichtbaren Text/Video. (Die Domain buroflow.de bleibt klein; nur der Repo-Name im Code heisst 'Buroflow'.) Genauso korrekt: "Mahnflow", "Mailflow", "Angebotsflow", "E-Rechnungsflow". Umlaute (ä/ö/ü) gehoeren normal in den Text — der Renderer kann sie, hab keine Angst davor.

KOMPOSITION (gilt auch fuer FREI gebaute Motion-Szenen, nicht nur UI-Nachbau): Der Inhalt muss zentriert und ausgewogen im Bild sitzen. Ein kleines Element oben-mittig mit Text unten-links und viel totem Raum rechts ist ein FEHLER. Fuelle die Flaeche: Hauptmotiv gross und mittig, Text darunter/darum zentriert, oberer und unterer Rand ungefaehr gleich. Nutze mindestens 70% der Bildbreite. Pruefe vor dem Rendern: wirkt das Bild leer oder unausgewogen, ist es noch nicht fertig.

HALTEZEIT ZUERST PLANEN: Die laengste Phase eines Segments ist NICHT der Eintritt, sondern die Zeit DANACH. Ein 3-Sekunden-Segment hat ~0,8s Eintritt und ~2,2s Haltezeit. Wenn in der Haltezeit nichts passiert, wirkt das Video tot — genau der haeufigste Fehler. Regel: In JEDER Szene muessen nach dem Eintritt MINDESTENS 3 Dinge DURCHGEHEND in Bewegung sein (z.B. driftende Partikel + wanderndes Licht-Element + Puls/Atmen auf dem Hauptmotiv). Plane die Haltezeit-Bewegung, bevor du den Eintritt baust.

SELBST-REVIEW (PFLICHT-ARBEITSSCHRITT): Nach JEDEM fertigen Render (story_video ODER komponente_bauen) rufst du 'video_pruefen' auf, BEVOR du Rui das Ergebnis meldest. Das Tool schaut dein Video mit Bild-KI an und findet tote Haltezeit, leere Komposition, falsche Marken-Schreibweise. Bei Urteil NACHBESSERN: setz die genannten Fixes um (Komponente/Segmente anpassen, neu rendern), dann pruefe erneut — wiederhole bis FREIGABE (max. 2-3 Runden, dann melde ehrlich den Restzustand). Erst bei FREIGABE meldest du Rui das fertige Video. So faengst du Fehler selbst, statt dass Rui sie findet.

PUBLISHING-ENTWURF: Wenn Rui ein Video zum Posten/Veroeffentlichen will (oder du ein komplettes Video als fertiges Paket lieferst), rufe nach der FREIGABE 'post_entwurf' auf. Das schreibt fertige, plattformspezifische Captions (LinkedIn/Instagram/TikTok) + Hashtags + Format-Empfehlung nach vault/posts/. Es POSTET NICHT — Rui gibt frei und veroeffentlicht selbst. Nenne ihm den Pfad zum Entwurf.

FORMAT BEWUSST WAEHLEN: Waehle das Format aktiv passend zum Zweck und NENNE es Rui, nimm nicht still den Default. tiktok (9:16) fuer Instagram Reels / TikTok / Shorts — Hochformat, mobil. linkedin (16:9) fuer LinkedIn, YouTube, Praesentation, und fuer UI-lastige Inhalte (Dashboards, breite Layouts). quadrat (1:1) fuer Feed-Posts. Im Zweifel bei Marketing-Kurzvideos tiktok, bei UI/Business-Inhalten linkedin. Wenn Rui ein Format nennt oder vorher eins genutzt wurde, dieses beibehalten.


Erfinde nie UI, die es nicht gibt — bau echtes Büroflow-UI immer nach dem echten Code aus dem Repo (ui_aus_github + komponente_bauen), nie geraten oder als Screenshot.

═══ HIGGSFIELD-HINTERGRUND (Tool 'vibe_clip' + story_video hintergrund_video) ═══
Fuer atmosphaerische, cineastische HINTERGRUND-Clips (fliessende Texturen, Licht, Stimmung) kannst du Higgsfield nutzen — NUR abstrakt, kein Produkt/Logo/Text/Menschen. Der Clip liegt HINTER dem Motion-Design.
ABLAUF (End-zu-End): 1) 'vibe_clip' generiert den Clip UND laedt ihn nach vault/higgsfield/ — es gibt dir den lokalen Pfad zurueck (z.B. 'higgsfield/hf_...mp4'). 2) Diesen Pfad gibst du im 'story_video' als 'hintergrund_video' an. Dann laeuft der Clip geloopt unter ALLEN Segmenten, automatisch mit dunklem Overlay (hintergrund_dim, Standard 0.55) fuer Text-Lesbarkeit. Der sonst uebliche Glow-Blob wird dadurch ersetzt.
WANN: Sparsam einsetzen (kostet Credits), nur wenn ein cineastischer Hintergrund den Look wirklich hebt — z.B. fuer ein Hero/Marken-Video. Standardmaessig reicht das Motion-Design allein. Bild-/Motion-Prompt abstrakt halten (z.B. bild_prompt "dark abstract flowing liquid, subtle lime green light, premium, minimal", motion_prompt "slow drifting, gentle waves"). Ein Clip ist ~5s und wird automatisch geloopt. Fuer mehr/anderen Bewegungscharakter den motion_prompt anpassen (z.B. "swirling", "turbulent", "rotating flow" statt "gentle").
WICHTIG — nur mit EINFACHEN Segmenten kombinieren: Der Higgsfield-Hintergrund wirkt NUR hinter den transparenten Grundstil-Segmenten (szenen/wortpop/zahl/formen/kinetic und den -pro-Varianten). custom-Komponenten (Dashboard, tool-karten, eigene Motion-Szenen) bringen IMMER ihren eigenen deckenden Hintergrund mit und VERDECKEN den Higgsfield-Clip komplett — das ist gewollt, kein Fehler. Wenn video_pruefen bei einem Segment mit custom-Komponente ueber Higgsfield "Hintergrund nicht sichtbar / keine Bewegung vom Hintergrund" meldet, ist das ERWARTET — baue NICHT die Komponente um, um den Clip durchscheinen zu lassen. Fuer einen sichtbaren Higgsfield-Hintergrund nutze einfache Segmente.

═══ EIGENE KOMPONENTEN BAUEN (Komponenten-Schmiede) ═══
Du bist nicht auf die festen Stile beschraenkt. Mit dem Tool 'komponente_bauen' kannst du EIGENE Motion-Komponenten in Remotion (JSX) schreiben — fuer Effekte, die es noch nicht gibt. So wird das Studio mit der Zeit besser: du kombinierst Vorhandenes und erfindest Neues.

TIPP: Bevor du eine neue Komponente baust, lies bei Bedarf einen Motion-Skill ('motion-design' fuer Timing/Easing/Disney-Prinzipien/Choreografie, 'motion-principles' um AI-Slop zu vermeiden, 'ui-animation' fuer konkrete Easing-Kurven/Reveals). Das hebt die Qualitaet deutlich.

REGELN fuer den JSX-Code:
- MUSS zwei Exports haben: `export const meta = {{ dauerSek: N, defaultProps: {{...}} }};` und `export const Komponente = (props) => {{ ... }};`
- Importiere Bausteine relativ: `import {{ EXPO, TextBlock, Surface, FlashOverlay, StoryHintergrund, useKameraPush }} from "../motion_helpers.jsx";` und `import {{ BRAND, logoFuer }} from "../brand.js";`
- Nutze `useVideoConfig()` fuer width/height (damit es in allen Formaten laeuft) und `useCurrentFrame()`.
- HALTE DICH AN DIE MOTION-DNA: easeOutExpo (EXPO) als Kurve, KEIN Bounce/Elastic. Text auf Surface (Glas/Card), nie nackt. Metronomisch. Max 2 Dekor-Elemente. Subtile Bewegung statt Zappeln.
- EASING-FALLE (haeufiger Crash!): `easing:` in interpolate() MUSS eine FUNKTION sein. Richtig: `easing: EXPO` (importiert aus motion_helpers) oder `easing: Easing.out(Easing.exp)`. FALSCH und crasht mit "easing is not a function": `easing: Easing.exp` (ohne .out()), `easing: "expo"` (String), `easing: EXPO()` (aufgerufen). Wenn du Easing aus remotion direkt nutzt: `import {{ Easing }} from "remotion"` und dann `Easing.out(Easing.ease)` o.ae. Im Zweifel EXPO aus motion_helpers importieren und nur diesen nutzen.
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
Ein starkes Video hat einen Bogen: HOOK (Aufmerksamkeit) -> PROBLEM (Schmerzpunkt) -> LOESUNG (Büroflow) -> BEWEIS/NUTZEN -> CTA.
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
        "description": ("Erstellt ein Motion-Design-Video ueber den Render-Server (Büroflow-Brandkit, 60fps). "
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
        "name": "video_pruefen",
        "description": ("SELBST-REVIEW deines eigenen gerenderten Videos. Extrahiert gleichmaessig ueber die "
                        "ganze Dauer verteilte Frames und prueft mit Bild-KI kritisch: Bewegt sich ueber die "
                        "GESAMTE Dauer genug (oder steht es nach dem Eintritt still?), ist die Komposition "
                        "zentriert/gefuellt, stimmt der Markenname 'Büroflow' und alle Texte, ist es dicht genug. "
                        "Gibt ein Urteil (FREIGABE / NACHBESSERN) mit konkreten Fixes. "
                        "WICHTIG: Rufe das nach JEDEM story_video und komponente_bauen auf, BEVOR du Rui das "
                        "Ergebnis meldest. Bei 'NACHBESSERN' die Fixes umsetzen (Komponente/Segmente anpassen, neu "
                        "rendern) und erneut pruefen — erst bei FREIGABE melden. So lieferst du nur gute Videos."),
        "input_schema": {
            "type": "object",
            "properties": {
                "datei": {"type": "string", "description": "Optional: Dateiname in vault/videos/. Ohne Angabe wird das ZULETZT gerenderte Video geprueft."},
                "erwartung": {"type": "string", "description": "Optional: was das Video zeigen/sein sollte (hilft der Bewertung, z.B. 'Chaos wird zu Ordnung, Markenname Büroflow')."},
            },
        },
    },
    {
        "name": "post_entwurf",
        "description": ("Erstellt einen PUBLISHING-ENTWURF (Markdown) fuer ein fertiges, freigegebenes Video. "
                        "Schreibt plattformspezifische Post-Captions (LinkedIn foermlich/Business, Instagram "
                        "lockerer, TikTok sehr direkt) + passende Hashtags + Format-Empfehlung nach vault/posts/. "
                        "Postet NICHT automatisch — Rui gibt frei und postet selbst. "
                        "Rufe das NACH FREIGABE (video_pruefen) auf, wenn Rui einen Post-Entwurf will, oder am Ende "
                        "eines kompletten Video-Auftrags als fertiges Paket."),
        "input_schema": {
            "type": "object",
            "properties": {
                "datei": {"type": "string", "description": "Optional: Video in vault/videos/. Ohne Angabe das zuletzt gerenderte."},
                "thema": {"type": "string", "description": "Worum geht's im Video (z.B. 'Mahnungen automatisieren mit Mahnflow')."},
                "kernbotschaft": {"type": "string", "description": "Die eine Kernaussage/der Nutzen, den der Post transportieren soll."},
                "plattformen": {"type": "array", "items": {"type": "string", "enum": ["linkedin", "instagram", "tiktok"]},
                                "description": "Fuer welche Plattformen Captions erzeugt werden (Standard: alle drei)."},
            },
        },
    },
    {
        "name": "ui_aus_github",
        "description": ("Liest den ECHTEN Quellcode von Büroflow aus dem privaten GitHub-Repo. "
                        "Damit baust du eine Seite/Komponente 1:1 als Remotion-Komponente nach (vektorscharf + animierbar), "
                        "statt sie zu raten oder unscharfe Screenshots zu nutzen. "
                        "Gib einen ORDNER an, um den Inhalt zu listen (z.B. 'components/dashboard'), "
                        "oder eine DATEI, um ihren Code zu lesen (z.B. 'components/dashboard/dash-sidebar.tsx'). "
                        "Vorgehen: erst Ordner listen, dann die 1-3 relevanten Dateien lesen, dann mit 'komponente_bauen' nachbauen."),
        "input_schema": {
            "type": "object",
            "properties": {
                "pfad": {"type": "string", "description": "Pfad im Repo, ohne fuehrenden Slash (z.B. 'components/dashboard' oder 'app/dashboard/mahnflow/page.tsx')"},
                "max_zeichen": {"type": "integer", "description": "Optional: Kuerzungslimit fuer Dateiinhalt (Standard 60000)"},
            },
            "required": ["pfad"],
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
                "musik": {"type": "string", "description": "Optional: Name/Pfad des Hintergrund-Tracks (z.B. 'upbeat-clean' oder 'musik/upbeat-clean.mp3'). Laeuft leise durchgehend."},
                "musik_lautstaerke": {"type": "number", "description": "Lautstaerke der Musik 0-1, Standard 0.25 (leise unter den SFX)."},
                "hintergrund_video": {"type": "string", "description": "Optional: Higgsfield-Clip als cineastischer Hintergrund HINTER dem Motion-Design (z.B. 'higgsfield/hf_20260812-201500.mp4' oder nur der Dateiname). Zuerst mit vibe_clip erzeugen — der gibt den Pfad zurueck. Laeuft geloopt unter allen Segmenten mit dunklem Overlay fuer Text-Lesbarkeit."},
                "hintergrund_dim": {"type": "number", "description": "Verdunkelung des Hintergrundvideos 0-1 (Standard 0.55). Hoeher = dunkler = besser lesbar, aber Clip weniger sichtbar."},
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
    {
        "name": "musik_generieren",
        "description": ("Generiert einen Hintergrund-Musik-Track via ElevenLabs Music aus einer Stil-/Mood-Beschreibung. "
                        "KEINE Kuenstler-/Band-/Songwriter-Namen, Songtitel, Albumtitel, Label- oder Verlagsnamen, keine Songtext-Zeilen (Lizenzbruch laut ElevenLabs Music Terms). Nur Genre/Stimmung/Tempo/Instrumente. Der Track laeuft leise unter dem ganzen Video und traegt den Rhythmus."),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Dateiname (z.B. 'upbeat-clean')"},
                "beschreibung": {"type": "string", "description": "Stil/Mood auf Englisch (z.B. 'modern upbeat corporate electronic, clean driving beat, optimistic, minimal, no vocals')"},
                "dauer_sek": {"type": "number", "description": "Laenge in Sekunden (passend zum Video, z.B. 25)"},
            },
            "required": ["name", "beschreibung", "dauer_sek"],
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


def _hf_download(url, ziel_pfad, timeout=120):
    """Laedt ein Higgsfield-Video von der URL nach ziel_pfad. Gibt True/False."""
    try:
        with requests.get(url, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            with open(ziel_pfad, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    if chunk:
                        f.write(chunk)
        return os.path.getsize(ziel_pfad) > 1024
    except Exception as e:
        log(f"[higgsfield] Download-Fehler: {e}")
        return False


def tool_vibe_clip(inp):
    """Generiert einen Clip ueber Higgsfield, LAEDT ihn nach vault/higgsfield/ und
    gibt lokalen Pfad + URL zurueck. Der lokale Pfad ist als Story-Hintergrund
    nutzbar (hintergrund_video in story_video)."""
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
        os.makedirs(CLIP_DIR, exist_ok=True)
        os.makedirs(HF_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        # Video herunterladen (fuer Nutzung als Hintergrundlayer)
        datei_name = f"hf_{ts}.mp4"
        lokal = os.path.join(HF_DIR, datei_name)
        geladen = _hf_download(res["video_url"], lokal)
        rel_pfad = f"higgsfield/{datei_name}" if geladen else ""
        info = {"beschreibung": beschreibung, "aspect_ratio": aspect,
                "duration": duration, "bild_prompt": bild_prompt,
                "motion_prompt": motion_prompt, "bild_url": res["bild_url"],
                "video_url": res["video_url"], "lokal": rel_pfad, "erstellt": ts}
        pfad = os.path.join(CLIP_DIR, f"{ts}_clip.json")
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
        arbeit_log("Vibe-Clip generiert", beschreibung, f"higgsfield/{datei_name}")
        if geladen:
            return (f"Clip fertig ({CLIP_ZAEHLER['n']}/{MAX_CLIPS_PRO_LAUF}): {beschreibung}\n"
                    f"Lokal gespeichert als: {rel_pfad}\n"
                    f"NUTZUNG: Gib diesen Pfad im story_video als 'hintergrund_video' an, dann liegt der "
                    f"cineastische Clip HINTER dem Motion-Design (mit dunklem Overlay fuer Lesbarkeit).")
        return (f"Clip generiert, aber Download fehlgeschlagen. Nur als URL verfuegbar: {res['video_url']}")
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

    # ── Echte Zeitachse rechnen (fuer SFX-Timing-Korrektur) ──
    # Der Bot plant SFX in "geplanten" Sekunden (Segmentgrenzen ohne
    # Ueberlappung). Fliessende Uebergaenge ziehen aber je 13 Frames Overlap
    # ab -> die reale Zeitachse verschiebt sich nach vorne, und die SFX
    # kaemen sonst zu SPAET. Wir bauen eine Umrechnung geplant->real.
    FPS = 60
    UEBERGANG_FRAMES = 13
    def _fliessend(u): return bool(u) and u not in ("cut", "flash")
    # geplante und reale Startframes je Segment
    geplant_start = []  # geplanter Startframe (ohne Overlap-Abzug)
    real_start = []     # realer Startframe (mit Overlap-Abzug)
    gp, rp = 0, 0
    for idx, seg in enumerate(aufbereitet):
        f = max(24, int(round(float(seg.get("dauer", 3)) * FPS)))
        if idx > 0 and _fliessend(seg.get("uebergang")):
            rp -= UEBERGANG_FRAMES  # Overlap: reales Segment startet frueher
        geplant_start.append(gp)
        real_start.append(rp)
        gp += f
        rp += f
    def _geplant_zu_real(frame_geplant):
        # finde das Segment, in dem der geplante Frame liegt, und verschiebe
        # um denselben Versatz auf die reale Achse
        versatz = 0
        for i in range(len(geplant_start)):
            if frame_geplant >= geplant_start[i]:
                versatz = real_start[i] - geplant_start[i]
            else:
                break
        return max(0, frame_geplant + versatz)

    # SFX aufbereiten: bei_sek -> Frame (60fps) -> Overlap-Korrektur.
    # Ausserdem: faelschlich als SFX eingetragene MUSIK erkennen und
    # stattdessen als durchgehende Hintergrundmusik behandeln.
    sfx_liste = []
    musik_aus_sfx = ""
    for s_ in (inp.get("sfx") or []):
        datei = s_.get("datei", "")
        if not datei:
            continue
        # Musik-Fehleintrag abfangen (liegt im musik-Ordner oder heisst so)
        low = datei.lower()
        if low.startswith("musik/") or "musik" in low or "music" in low or "track" in low:
            musik_aus_sfx = datei
            continue
        if not datei.startswith("sfx/"):
            datei = f"sfx/{datei}"
        if not datei.endswith(".mp3"):
            datei = datei + ".mp3"
        frame_geplant = int(round(float(s_.get("bei_sek", 0)) * FPS))
        sfx_liste.append({
            "datei": datei,
            "frame": _geplant_zu_real(frame_geplant),
            "lautstaerke": float(s_.get("lautstaerke", 0.7)),
        })

    # Musik aufbereiten (bevorzugt der explizite musik-Parameter, sonst der
    # aus einem SFX-Fehleintrag geborgene Track). Musik laeuft IMMER ab
    # Frame 0 durchgehend, nie mit Offset.
    musik = inp.get("musik", "") or musik_aus_sfx
    if musik:
        if not musik.startswith("musik/"):
            musik = f"musik/{musik}"
        if not musik.endswith(".mp3"):
            musik = musik + ".mp3"
    musik_vol = float(inp.get("musik_lautstaerke", 0.25))

    # Higgsfield-Hintergrundvideo (optional). Pfad relativ zu public/ oder vault.
    # Der Render nutzt public-dir, daher muss der Clip fuer OffthreadVideo per
    # staticFile erreichbar sein -> wir referenzieren ihn ueber den vault-Pfad,
    # den der Render-Container ebenfalls gemountet hat.
    hg_video = (inp.get("hintergrund_video") or "").strip()
    if hg_video:
        # normalisieren: nackten Namen -> higgsfield/<name>
        if not hg_video.startswith("higgsfield/") and "/" not in hg_video:
            hg_video = f"higgsfield/{hg_video}"
    hg_dim = float(inp.get("hintergrund_dim", 0.55))  # 0=hell .. 1=ganz dunkel

    props = {"palette": palette, "logo": True, "segmente": aufbereitet,
             "sfx": sfx_liste, "musik": musik, "musik_lautstaerke": musik_vol,
             "hintergrund_video": hg_video, "hintergrund_dim": hg_dim}
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

def _neuestes_video():
    """Findet das zuletzt geaenderte .mp4 in vault/videos/."""
    try:
        mp4s = glob.glob(os.path.join(VIDEOS_DIR, "*.mp4"))
        if not mp4s:
            return ""
        return max(mp4s, key=os.path.getmtime)
    except Exception:
        return ""

def tool_video_pruefen(inp):
    """SELBST-REVIEW: extrahiert gleichverteilte Frames aus einem fertigen Video
    und laesst Claude Vision es ehrlich gegen die Qualitaetskriterien pruefen —
    besonders 'passiert ueber die ganze Dauer genug' und 'Komposition/Marke'."""
    datei = inp.get("datei", "")
    erwartung = inp.get("erwartung", "")
    if datei:
        pfad = datei if os.path.isabs(datei) else os.path.join(VIDEOS_DIR, datei)
    else:
        pfad = _neuestes_video()  # ohne Angabe: das zuletzt gerenderte
    if not pfad or not os.path.exists(pfad):
        vorhanden = ", ".join(sorted(os.listdir(VIDEOS_DIR))[-8:]) if os.path.isdir(VIDEOS_DIR) else "(Ordner fehlt)"
        return f"Video nicht gefunden. Zuletzt in vault/videos/: {vorhanden}"

    dauer = _video_dauer(pfad)
    if dauer <= 0:
        return "Konnte Videodauer nicht lesen — gueltiges Video?"

    # GLEICHMAESSIG ueber die ganze Dauer verteilte Frames — entscheidend, um
    # 'ab Sekunde 2 passiert nichts' ueberhaupt sehen zu koennen.
    n = 8
    fps = max(0.3, min(4.0, n / dauer))
    tmp = tempfile.mkdtemp(prefix="pruefframes_")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", pfad, "-vf", f"fps={fps:.3f},scale=640:-1",
             "-frames:v", str(n), os.path.join(tmp, "f_%03d.jpg")],
            capture_output=True, text=True, timeout=120)
        frames = sorted(glob.glob(os.path.join(tmp, "f_*.jpg")))[:n]
        if not frames:
            return "Konnte keine Frames extrahieren (ffmpeg-Problem)."

        content = []
        for i, fr in enumerate(frames):
            with open(fr, "rb") as fh:
                b64 = base64.standard_b64encode(fh.read()).decode()
            t = (i / fps)
            content.append({"type": "text", "text": f"Frame {i+1}/{len(frames)} (t~{t:.1f}s von {dauer:.1f}s):"})
            content.append({"type": "image", "source": {"type": "base64",
                            "media_type": "image/jpeg", "data": b64}})
        anweisung = (
            "Du bist ein strenger, ehrlicher Motion-Design-Reviewer und pruefst DEIN EIGENES gerendertes Video "
            "(diese Frames sind zeitlich gleichmaessig ueber die gesamte Dauer verteilt). Sei kritisch, nicht nett — "
            "das Ziel ist, Schwaechen zu finden, bevor Rui sie sieht. Pruefe konkret:\n"
            "1. BEWEGUNG UEBER DIE ZEIT (wichtigster Punkt): Veraendert sich von Frame zu Frame genug, ODER "
            "steht das Bild nach dem Eintritt still? Vergleiche spaete Frames miteinander — wenn Frame 4-8 fast "
            "identisch aussehen, ist die Haltezeit TOT. Das ist ein schwerer Fehler.\n"
            "2. KOMPOSITION: Ist der Inhalt zentriert und fuellt die Flaeche (mind. ~70% Breite), oder klebt etwas "
            "in einer Ecke mit viel totem Raum? Oberer/unterer Rand ausgewogen?\n"
            "3. MARKE/TEXT: Steht der Markenname KORREKT als 'Büroflow' (mit ü)? Falsche Schreibweisen "
            "(Bueroflow/Buroflow) oder Tippfehler in sichtbarem Text? Toolnamen korrekt (Mahnflow/Mailflow/Angebotsflow/E-Rechnungsflow)?\n"
            "4. LESBARKEIT: Text gross genug, guter Kontrast, nicht abgeschnitten?\n"
            "5. DICHTE: Wirkt es 'basic' (nur ein Element blendet ein) oder reich (mehrere Ebenen: Partikel, "
            "durchlaufendes Element, Sekundaerbewegung)?\n\n"
            "Gib am Ende ein klares URTEIL: 'FREIGABE' wenn es gut genug ist, oder 'NACHBESSERN' mit einer "
            "nummerierten Liste der konkreten Fixes (was genau, in welchem Zeitbereich). Antworte auf Deutsch, kurz und konkret."
        )
        if erwartung:
            anweisung += f"\n\nWas das Video zeigen/sein sollte: {erwartung}"
        content.append({"type": "text", "text": anweisung})

        log(f"[pruefen] Selbst-Review {os.path.basename(pfad)} ({dauer:.1f}s, {len(frames)} Frames)")
        resp = client.messages.create(model=MODEL, max_tokens=1400,
                                      messages=[{"role": "user", "content": content}])
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        arbeit_log("Video geprueft", os.path.basename(pfad), text[:200])
        urteil = "NACHBESSERN" if "NACHBESSERN" in text.upper() else ("FREIGABE" if "FREIGABE" in text.upper() else "?")
        return f"Selbst-Review von '{os.path.basename(pfad)}' ({dauer:.0f}s) — Urteil: {urteil}\n\n{text}"
    finally:
        for fr in glob.glob(os.path.join(tmp, "*")):
            try: os.remove(fr)
            except Exception: pass
        try: os.rmdir(tmp)
        except Exception: pass


def tool_ui_aus_github(inp):
    """Liest Dateien/Ordner aus dem privaten Büroflow-Repo (GitHub Contents API).
    Ordner -> Liste der Eintraege. Datei -> Quellcode (gekuerzt)."""
    pfad = (inp.get("pfad") or "").strip().lstrip("/")
    limit = inp.get("max_zeichen") or GITHUB_MAX_ZEICHEN
    try:
        limit = max(2000, min(120000, int(limit)))
    except Exception:
        limit = GITHUB_MAX_ZEICHEN

    if not GITHUB_TOKEN:
        return "GITHUB_TOKEN fehlt in der .env — ohne Token kein Zugriff auf das private Repo."
    if not pfad:
        return "Bitte 'pfad' angeben (z.B. 'components/dashboard')."
    if ".." in pfad:
        return "Ungueltiger Pfad."

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{pfad}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        resp = requests.get(url, headers=headers, params={"ref": GITHUB_BRANCH}, timeout=25)
    except Exception as e:
        return f"GitHub nicht erreichbar: {e}"

    if resp.status_code == 404:
        return (f"Nicht gefunden: '{pfad}' (Branch {GITHUB_BRANCH}). "
                f"Tipp: erst einen Ordner listen, z.B. 'components/dashboard' oder 'app/dashboard'.")
    if resp.status_code in (401, 403):
        return f"Kein Zugriff ({resp.status_code}). Token pruefen (Repo-Scope) oder Rate-Limit abwarten."
    if resp.status_code != 200:
        return f"GitHub-Fehler {resp.status_code}: {resp.text[:200]}"

    try:
        daten = resp.json()
    except Exception:
        return "Antwort von GitHub konnte nicht gelesen werden."

    # Ordner -> Liste
    if isinstance(daten, list):
        ordner = sorted(e["name"] for e in daten if e.get("type") == "dir")
        dateien = sorted(f"{e['name']} ({e.get('size', 0)} B)" for e in daten if e.get("type") == "file")
        zeilen = [f"Inhalt von '{pfad}' im Repo {GITHUB_REPO}:"]
        if ordner:
            zeilen.append("\nORDNER:\n" + "\n".join(f"  {o}/" for o in ordner))
        if dateien:
            zeilen.append("\nDATEIEN:\n" + "\n".join(f"  {d}" for d in dateien))
        if not ordner and not dateien:
            zeilen.append("(leer)")
        arbeit_log("GitHub gelistet", pfad, f"{len(ordner)} Ordner, {len(dateien)} Dateien")
        return "\n".join(zeilen)

    # Datei -> Inhalt
    if daten.get("type") != "file":
        return f"'{pfad}' ist weder Datei noch Ordner (Typ: {daten.get('type')})."
    if daten.get("encoding") != "base64" or not daten.get("content"):
        groesse = daten.get("size", 0)
        return f"Datei '{pfad}' konnte nicht dekodiert werden (Groesse {groesse} B, evtl. zu gross oder binaer)."
    try:
        code = base64.b64decode(daten["content"]).decode("utf-8", errors="replace")
    except Exception as e:
        return f"Datei '{pfad}' konnte nicht dekodiert werden: {e}"

    gekuerzt = ""
    if len(code) > limit:
        code = code[:limit]
        gekuerzt = f"\n\n[... gekuerzt bei {limit} Zeichen — bei Bedarf gezielt weitere Datei lesen ...]"
    arbeit_log("GitHub gelesen", pfad, f"{len(code)} Zeichen")
    log(f"[github] {pfad} gelesen ({len(code)} Zeichen)")
    return f"Quellcode aus {GITHUB_REPO}/{pfad} (Branch {GITHUB_BRANCH}):\n\n```\n{code}\n```{gekuerzt}"


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
            # E-17-Fix: aktuelle custom-Liste mitgeben, damit der Bot die frisch
            # gebaute Komponente SOFORT kennt (der System-Prompt wird erst bei
            # Bot-Neustart neu gerendert — diese Liste ueberbrueckt das).
            liste = ", ".join(custom_komponenten_liste())
            return (f"Komponente '{name}' gebaut & getestet. Verfuegbar als Stil 'custom-{name}' "
                    f"in allen Formaten. Test-Video: {antwort}\n"
                    f"Aktuell verfuegbare custom-Komponenten (nutze sie direkt, ohne Neustart): {liste}")
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


def tool_musik_generieren(inp):
    """Generiert einen Hintergrund-Track via ElevenLabs Music und speichert ihn nach vault/musik/."""
    beschreibung = inp.get("beschreibung", "").strip()
    name = inp.get("name", "").strip().lower()
    dauer_sek = inp.get("dauer_sek", 20)
    if not beschreibung or not name:
        return "Bitte 'beschreibung' (Stil/Mood, KEINE Band-/Kuenstlernamen) und 'name' angeben."
    if not ELEVENLABS_KEY:
        return "ELEVENLABS_API_KEY fehlt in der .env."
    import re as _re
    if not _re.fullmatch(r"[a-z0-9][a-z0-9\-]{1,40}", name):
        return "Ungueltiger Name. Erlaubt: kleinbuchstaben, zahlen, bindestrich."

    os.makedirs(MUSIK_DIR, exist_ok=True)
    try:
        ms = int(max(3000, min(600000, float(dauer_sek) * 1000)))
    except Exception:
        ms = 20000
    payload = {"prompt": beschreibung, "music_length_ms": ms, "model_id": "music_v2"}

    try:
        resp = requests.post(
            "https://api.elevenlabs.io/v1/music",
            headers={"xi-api-key": ELEVENLABS_KEY, "Content-Type": "application/json"},
            data=json.dumps(payload), timeout=300)
    except Exception as e:
        return f"ElevenLabs-Music-Anfrage fehlgeschlagen: {e}"
    if resp.status_code != 200:
        return f"ElevenLabs-Music-Fehler {resp.status_code}: {resp.text[:250]}"

    pfad = os.path.join(MUSIK_DIR, f"{name}.mp3")
    try:
        with open(pfad, "wb") as f:
            f.write(resp.content)
    except Exception as e:
        return f"Konnte Musik nicht speichern: {e}"
    kb = len(resp.content) // 1024
    arbeit_log("Musik generiert", name, beschreibung[:80])
    log(f"[musik] {name}.mp3 gespeichert ({kb} KB, {dauer_sek}s)")
    return f"Musik '{name}' erstellt ({kb} KB, ~{dauer_sek}s). In Videos als musik-Datei 'musik/{name}.mp3'."


def tool_post_entwurf(inp):
    """Erstellt einen Publishing-Entwurf (Markdown) fuer ein fertiges Video:
    plattformspezifische Captions (LinkedIn foermlicher, Insta/TikTok lockerer),
    Hashtags, Format-Empfehlung. Postet NICHT — legt nur den Entwurf in vault/posts/ ab."""
    datei = inp.get("datei", "")
    thema = inp.get("thema", "")
    kern = inp.get("kernbotschaft", "")
    plattformen = inp.get("plattformen") or ["linkedin", "instagram", "tiktok"]
    if datei:
        pfad = datei if os.path.isabs(datei) else os.path.join(VIDEOS_DIR, datei)
    else:
        pfad = _neuestes_video()
    if not pfad or not os.path.exists(pfad):
        return "Kein Video gefunden. Gib 'datei' an oder rendere zuerst ein Video."
    video_name = os.path.basename(pfad)

    # Claude schreibt die plattformspezifischen Texte
    anweisung = (
        "Du bist Social-Media-Redakteur fuer Büroflow (deutsches KI-SaaS fuer Buerokram-Automatisierung: "
        "Mahnflow, Mailflow, Angebotsflow, E-Rechnungsflow; Zielgruppe Selbststaendige, Freelancer, kleine "
        "Unternehmen; Marken-CTA: buroflow.de). Schreibe fertige Post-Captions fuer ein Marketing-Video.\n"
        f"Video-Thema: {thema or '(aus Kernbotschaft ableiten)'}\n"
        f"Kernbotschaft: {kern or '(nicht angegeben — allgemein Büroflow-Nutzen)'}\n"
        f"Plattformen: {', '.join(plattformen)}\n\n"
        "Regeln:\n"
        "- Markenname IMMER 'Büroflow' (mit ü). Deutsch.\n"
        "- LinkedIn: professionell, Mehrwert-orientiert, 3-5 Saetze, ein konkreter Business-Nutzen, dezente "
        "Hashtags (3-5, branchig: #Buchhaltung #Selbststaendigkeit #KI etc.).\n"
        "- Instagram: lockerer, emotional, kurze Zeilen, Emojis sparsam ok, CTA klar, 8-12 Hashtags (Mix "
        "Reichweite + Nische).\n"
        "- TikTok: sehr direkt, Hook in Zeile 1, jung/frisch, kurz, 4-6 Hashtags (#fyp + thematisch).\n"
        "- Jede Caption endet mit klarem CTA zu buroflow.de.\n"
        "- KEINE erfundenen Features — nur die 4 echten Tools.\n\n"
        "Gib fuer JEDE gewuenschte Plattform aus:\n"
        "### <Plattform>\n<Caption-Text>\n\nHashtags: <hashtags durch Leerzeichen>\n\n"
        "Danach eine Zeile: 'Format-Empfehlung: <tiktok 9:16 / linkedin 16:9 / quadrat 1:1> — <kurzer Grund>'."
    )
    try:
        resp = client.messages.create(model=MODEL, max_tokens=1600,
                                      messages=[{"role": "user", "content": anweisung}])
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
    except Exception as e:
        return f"Caption-Generierung fehlgeschlagen: {type(e).__name__}: {e}"

    os.makedirs(POSTS_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    md_name = f"{ts}_post.md"
    md_pfad = os.path.join(POSTS_DIR, md_name)
    kopf = (f"# Publishing-Entwurf — {thema or video_name}\n\n"
            f"**Video:** `vault/videos/{video_name}`\n"
            f"**Erstellt:** {ts}\n"
            f"**Status:** ENTWURF (noch nicht gepostet)\n\n---\n\n")
    try:
        with open(md_pfad, "w", encoding="utf-8") as f:
            f.write(kopf + text + "\n")
    except Exception as e:
        return f"Konnte Entwurf nicht speichern: {e}"
    arbeit_log("Post-Entwurf erstellt", thema or video_name, f"posts/{md_name}")
    log(f"[post] Entwurf gespeichert: posts/{md_name}")
    return (f"Publishing-Entwurf erstellt: vault/posts/{md_name}\n"
            f"Enthaelt plattformspezifische Captions ({', '.join(plattformen)}) + Hashtags + Format-Empfehlung.\n"
            f"NICHT gepostet — Rui gibt frei und postet selbst.\n\n{text[:600]}...")


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
    if name == "video_pruefen":
        return tool_video_pruefen(inp)
    if name == "post_entwurf":
        return tool_post_entwurf(inp)
    if name == "ui_aus_github":
        return tool_ui_aus_github(inp)
    if name == "komponente_bauen":
        return tool_komponente_bauen(inp, r)
    if name == "sfx_generieren":
        return tool_sfx_generieren(inp)
    if name == "musik_generieren":
        return tool_musik_generieren(inp)
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
    pruef_zaehler = {"n": 0}  # Notbremse gegen endlose Review-Schleifen
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
                # NOTBREMSE: video_pruefen hoechstens 3x pro Auftrag. Danach
                # Zwangs-Freigabe, damit der Loop nicht endlos dreht und Code
                # kaputt-iteriert (siehe easing-Crash in Runde 4+).
                if block.name == "video_pruefen":
                    pruef_zaehler["n"] += 1
                    if pruef_zaehler["n"] > 3:
                        result = ("STOPP: Du hast bereits 3 Review-Runden gemacht. Keine weitere "
                                  "Nachbesserung — das Ergebnis ist gut genug. Melde Rui JETZT das "
                                  "aktuelle Video mit einem kurzen ehrlichen Fazit (was gut ist, was "
                                  "in einer spaeteren Runde noch besser werden koennte). Keine Tools mehr.")
                        log(f"[notbremse] video_pruefen #{pruef_zaehler['n']} -> Zwangs-Freigabe")
                        t_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
                        continue
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
