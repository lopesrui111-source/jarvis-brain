<!-- automatisch erzeugt am 13.08.2026 07:02 — nicht von Hand bearbeiten -->

# STATUS

## Was das System ist

Multi-Bot-System auf Hetzner CX23 (195.201.7.109), läuft in Docker Compose unter Ubuntu.
JARVIS (orchestrator/core.py) ist der zentrale Orchestrator mit Gedächtnis (PostgreSQL + pgvector), Mail- und Kalender-Lesezugriff, Web-Recherche und Aufgabenverwaltung.
Spezialisierte Bots: CEO (Strategie, Bueroflow), MARKETING (48 Skills + 345 Anleitungen, Bildgen), SEO (Gutefrage-Recherche, Entwürfe), IMMO (Rendite-Analysen), TELEGRAM (Durchreiche-Schicht), RENDER (Video-Produktion), REGIE (Automation), RECORDER (deprecated).

## Infrastruktur

**Server:** Hetzner CX23, Ubuntu, Docker Compose  
**Repo-Wurzel:** `/opt/jarvis-brain/`  
**Datenbank:** PostgreSQL 16 mit pgvector, DB `jarvis_brain`, User `jarvis`  
**Datenquellen (read-only):** Google iCal (Kalender), IMAP (IONOS + Gmail), gutefrage.net, GitHub  
**Laufende Container:** redis, postgres, adminer, watchtower, dashboard, jarvis-core, jarvis-ceo, jarvis-marketing, jarvis-recorder, jarvis-seo, jarvis-telegram, jarvis-immo, jarvis-regie, jarvis-render, camofox  
**Zeitzone (alle Dockerfiles):** Europe/Berlin  
**Bildgen:** MuAPI (MARKETING delegiert an Render/MuAPI)

## Aktueller Stand je Komponente

| Komponente | Zeilen | Funktion | Zuletzt geändert |
|---|---|---|---|
| **orchestrator/core.py** | 3434 | Orchestrator, Mail/Kalender, Gedächtnis, Aufgaben, Morgen-Durchgang, Doku-Lauf | Routing, Delegation, Aufgaben-Parsing |
| **dashboard/dashboard.py** | 4713 | Web-UI, Echtzeit-Log, Aufgaben-Panel, Kosten-Track, Vault-Browser | Dashboard-Erweiterungen |
| **bots/ceo/bot.py** | 777 | Strategie, Bueroflow, CEO-Review (Marketing-Entwürfe) | Review-Logik |
| **bots/marketing/bot.py** | 1261 | 48 Skills, 345 Anleitungen, Text/Bild-Creatives, MuAPI-Integration | Skill-Ausführung, Entwurf-Management |
| **bots/seo/bot.py** | 1563 | Gutefrage-Recherche, Entwurf-Ablage im Vault | Entwürfe (1 wartend) |
| **bots/immo/bot.py** | 1092 | Rendite-Analysen, Plausibilitätsprüfung, Telegram-Hinweise | Analyse-Logic (8 ungeprueft) |
| **bots/telegram/bridge.py** | 350 | Durchreiche-Schicht zu Telegram | Datenfluss |
| **bots/render** | — | Video-Produktion: Higgsfield-Layer, StorySequenz, Motion-Tuning | Motion-Fix, Easing, Notbremse, Selbst-Review (video_pruefen) |
| **bots/regie** | — | Automation | — |

**Kosten (30 Tage):** jarvis $10.21, marketing $7.43, ceo $1.54, seo $1.51, immo $0.96  
**Offene Aufgaben:** 10

## Zuletzt gebaut

- **Publishing-Entwürfe & Recorder-Stilllegung:** post_entwurf-Infrastruktur, E-17 custom-Liste-Fix, beispiel.jsx entfernt, Recorder retired
- **Higgsfield-Integration:** Download + Mount + OffthreadVideo-Loop in StorySequenz, Prompt-Regeln für Video-Stil
- **Video-QA & Notbremse:** Selbst-Review-Loop (video_pruefen), Notbremse, 4-Pro-Stile, Motion-Prinzipien, Marken-Schreibweise, Easing-Warnung, Format-Wahl
- **Motion & Szenen:** formen/kinetic angeschlossen, Uebergaenge entkoppelt + getuned, durchgehendes Leben in allen 5 Grundstilen, GlasPanel-Look in Szenen
- **Bug-Fixes:** 3 Bugs (Notbremse, Easing-Warnung, Format-Wahl), ElevenLabs Musik-Lizenzregeln

## Offene Punkte

- SEO: 1 Entwurf wartend auf Ueberprüfung/Publication
- IMMO: 8 Treffer ungeprueft
- Quora: derzeit ABGESCHALTET (Cloudflare-Schutz)
- MARKETING postet NICHTS selbst — legt Dateien im Vault ab
- SEO postet NIEMALS — Rui kuemmert sich um Publication von Hand
- RENDER: Motion-Tuning und ElevenLabs-Integration stabil, Selbst-Review in Produktion

## Arbeitsweise mit Rui

- **Dateien:** Komplette Ersetzungsdateien statt Patches
- **Shell:** CMD statt PowerShell
- **Sprache:** Deutsche Antworten, kurz und direkt
- **Deployment:** Schritt für Schritt, nach jedem Deploy `wc -l` auf betroffene Dateien prüfen
- **Konsistenz:** Alle Aenderungen gegen STATUS.md validieren

## Kritische Regeln

- **.env wird NIE angefasst** — Secrets und Credentials sind tabu
- **docker-compose.yml:** Nur komplette, fertige Bloecke zum manuellen Einfuegen; KEINE Skripte zum automatischen Patchen
- **JavaScript/Video-Output:** Ausgelieferter Code (Dashboard, Render-Prompts, Video-Ausgaben) VOR Auslieferung IMMER pruefen
- **Schreibweise:** Marken-Namen (ElevenLabs, MuAPI, Higgsfield) korrekt halten
- **API-Kosten:** Vor jedem Deploy aktuelle Kostenraten bestaetigen
- **Gedaechtnis (pgvector):** Taeglich um 03:00 konsolidiert, nicht manuell faeddeln
- **Morgen-Durchgang:** 07:00, Mails + Kalender → Aufgaben, dann automatisch Doku-Lauf