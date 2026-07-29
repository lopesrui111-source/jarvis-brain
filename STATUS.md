<!-- automatisch erzeugt am 29.07.2026 15:42 — nicht von Hand bearbeiten -->

# STATUS

## Was das System ist

Multi-Bot-System auf einem Hetzner-Server. JARVIS (orchestrator/core.py) ist der Orchestrator: er liest Mails und Kalender, pflegt das Langzeitgedächtnis (pgvector), verwaltet Aufgaben und Aufträge und delegiert an spezialisierte Bots. Die weiteren Bots sind CEO, MARKETING, SEO, IMMO und TELEGRAM. Ein Dashboard (dashboard/dashboard.py) zeigt den Systemzustand, den Vault und alle Bot-Ausgaben.

## Infrastruktur

- **Server:** Hetzner CX23, 195.201.7.109, Ubuntu, Docker Compose
- **Repo-Wurzel:** `/opt/jarvis-brain/`
- **Datenbank:** PostgreSQL 16 mit pgvector, Datenbankname `jarvis_brain`, Benutzer `jarvis`
- **Laufende Container:** redis, postgres, adminer, watchtower, dashboard, jarvis-core, jarvis-ceo, jarvis-marketing, camofox, jarvis-immo, jarvis-seo, jarvis-telegram, jarvis-net
- **Zeitzone:** Europe/Berlin in allen Bot-Dockerfiles
- **Deploy-Muster:** Datei auf Server übertragen, `docker compose up -d --build <service>`, danach Zeilenzahl mit `wc -l` prüfen

## Aktueller Stand je Komponente

**orchestrator/core.py** (2932 Zeilen)
Orchestrator-Kern. Gedächtnis via pgvector und Embeddings, Nightly-Konsolidierung (Tages-Log, Fakten-Extraktion, Dedup, Vault-Tagesnotiz täglich 03:00), Morgen-Durchgang 07:00 (Mails beider Konten + Kalender, Aufgaben anlegen, danach Doku-Lauf), Lagebild-Tool, Auftrags-System, Doku-System, Web-Recherche via camofox, GitHub lesen, Stilprofil aus gesendeten Mails (IONOS + Gmail). Mail: IMAP auf IONOS und Gmail, nur lesend. Kalender: Google iCal, read-only.

**dashboard/dashboard.py** (3122 Zeilen)
Web-Dashboard. Zeigt Systemzustand, Vault-Browser, HEUTE-Panel, Wochenansicht mit Gruppen, Aufgaben aus Mails, Bot-Detailfenster, Mobile-Ansicht, Zoom-Buttons. Umami-Integration. Bueroflow-Zahlen sichtbar.

**bots/ceo/bot.py** (763 Zeilen)
Strategie und Entscheidungen für Bueroflow. Prüft Marketing-Entwürfe (CEO-Review). Hat Zugriff auf die Skill-Bibliothek (wiederverwendbares Skill-Modul, das auch für weitere Bots nutzbar ist).

**bots/marketing/bot.py** (1194 Zeilen)
Erstellt Creatives und Post-Texte. 48 Marketing-Skills plus die große Skill-Bibliothek (345 Anleitungen). Bildgenerierung über MuAPI. CEO-Review-Schritt integriert, Bild-Rhythmus, Notbremse. Postet **nichts selbst** — legt alle Ausgaben im Vault ab.

**bots/seo/bot.py** (1113 Zeilen)
Recherchiert Fragen auf gutefrage.net, schreibt Antwort-Entwürfe in den Vault. Cookie-Consent wird automatisch weggeklickt. Tageslauf mit Nachholen (Uhrzeit aus `SEO_DAILY_TIME`). Postet **niemals** selbst — das macht Rui von Hand. Quora ist derzeit **abgeschaltet** (Cloudflare-Schutz).

**bots/immo/bot.py** (901 Zeilen)
Rendite-Analysen von Immobilien-Inseraten, Plausibilitätsprüfung, Telegram-Hinweise.

**bots/telegram/bridge.py** (289 Zeilen)
Durchreiche-Schicht zwischen Telegram und den Bots. Kein eigenes Gedächtnis.

## Zuletzt gebaut

- **Dashboard-Ausbau:** Wochenansicht mit Gruppen, HEUTE-Panel, Bot-Detailfenster, Mobile-Ansicht, Zoom-Buttons, Aufgaben aus Mails, Bueroflow-Zahlen
- **Marketing-Workflow:** CEO-Review-Schritt, Bild-Rhythmus, Notbremse
- **SEO-Tageslauf:** Nachholen verpasster Läufe, Zeitzone-Fix, Cookie-Consent automatisch wegklicken
- **Skill-Modul:** Zentrales, wiederverwendbares Modul; CEO hat Zugriff, weitere Bots können folgen
- **Immo:** Plausibilitätsprüfung für Inserate
- **Telegram-Brücke:** Initiale Implementierung
- **Kalender-Migration:** Von iCloud auf Google iCal umgestellt
- **Auftrags-System, GitHub-Zugriff, Umami** in Core und Dashboard integriert
- **SEO-Bot Grundaufbau:** gutefrage + Quora (Quora jetzt abgeschaltet), Vault-only-Prinzip
- **Multi-Agent-Stack:** Marketing-Bot (48 Skills, Brand-Kit, MuAPI), CEO v3, camofox Web-Zugriff, Prompt-Caching, Kosten-Tracking
- **Langzeitgedächtnis:** pgvector + Embeddings, Nightly-Konsolidierung, DB-Schema (init.sql) versioniert

## Offene Punkte

- 2 offene Aufgaben im System
- 3 SEO-Entwürfe warten auf Ruis Durchsicht und manuelles Posten
- 4 Immo-Treffer ungepüft
- Quora abgeschaltet (Cloudflare-Schutz), kein Ersatz bislang definiert

## Arbeitsweise mit Rui

- **Komplette Ersetzungsdateien** liefern, keine Patches oder Diffs
- **CMD**, nicht PowerShell
- **Deutsch**, kurz und direkt
- **Schritt für Schritt** vorgehen; nach jedem Deploy Zeilenzahl mit `wc -l <datei>` prüfen und bestätigen lassen, bevor der nächste Schritt folgt

## Kritische Regeln

- `.env` wird **niemals** angefasst — keine Lesevorschläge, keine Schreibvorschläge, keine Umstrukturierungen
- `docker-compose.yml`: fertige Blöcke zum **manuellen Einfügen** liefern, keine Skripte, die die Datei automatisch verändern
- Ausgeliefertes JavaScript vor der Auslieferung auf Korrektheit prüfen — fehlerhafte Skripte blockieren das Dashboard