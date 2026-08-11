<!-- automatisch erzeugt am 11.08.2026 07:01 — nicht von Hand bearbeiten -->

# STATUS

## Was das System ist

Multi-Bot-System auf Hetzner CX23 (195.201.7.109), orchestriert durch JARVIS als zentralen Hub. Sieben spezialisierte Bots (CEO, Marketing, SEO, Immo, Telegram, Recorder, Render) führen Aufgaben parallel aus. PostgreSQL 16 mit pgvector als Gedächtnis, Redis für Queuing. Docker Compose, alle Services laufen in Containern.

## Infrastruktur

- **Server:** Hetzner CX23, Ubuntu, Docker Compose
- **Repo-Wurzel:** `/opt/jarvis-brain/` (nicht `/opt/jarvis/`)
- **Datenbank:** PostgreSQL 16 mit pgvector, DB `jarvis_brain`, User `jarvis`
- **Laufende Services:** redis, postgres, adminer, watchtower, dashboard, jarvis-core, jarvis-ceo, jarvis-marketing, jarvis-recorder, jarvis-regie, jarvis-render, camofox, jarvis-immo, jarvis-seo, jarvis-telegram
- **Externe Quellen:** Google iCal (read-only), IMAP auf IONOS und Gmail (lesend), MuAPI für Bildgenerierung, ElevenLabs für Audio
- **Zeitzone:** Europe/Berlin in allen Bot-Dockerfiles

## Aktueller Stand je Komponente

| Datei | Zeilen | Funktion | Zuletzt |
|-------|--------|----------|---------|
| `orchestrator/core.py` | 3434 | Orchestrator, Gedächtnis (pgvector), Mail/Kalender-Lesen, Web-Recherche, GitHub-Lesen, Auftrags- und Aufgabenverwaltung, Morgen-Durchgang, Lagebild-Tool, Doku-System | Audio via ElevenLabs, Story-Übergänge |
| `dashboard/dashboard.py` | 4123 | Web-UI für Aufgaben, Mails, Kalender, Vault, Logs, Echtzeit-Telemetrie | Audio via ElevenLabs |
| `bots/ceo/bot.py` | 777 | Strategie, Entscheidungen für Büroflow, CEO-Review für Marketing-Entwürfe | Audio via ElevenLabs |
| `bots/marketing/bot.py` | 1261 | 48 Marketing-Skills + 345 Anleitungen-Bibliothek, Creative-Texte, Post-Entwürfe, Bildgenerierung via MuAPI, legt ab (postet nicht selbst) | Audio via ElevenLabs |
| `bots/seo/bot.py` | 1563 | Recherche auf gutefrage.net, Antwort-Entwürfe in Vault (postet NIE selbst), Quora abgeschaltet (Cloudflare-Schutz) | Audio via ElevenLabs |
| `bots/immo/bot.py` | 1092 | Rendite-Analysen, Plausibilitätsprüfung, Telegram-Hinweise | Audio via ElevenLabs |
| `bots/telegram/bridge.py` | 350 | Durchreiche-Schicht, kein eigenes Gedächtnis | Audio via ElevenLabs |

## Zuletzt gebaut

**Audio-System (ElevenLabs):** On-demand SFX-Generierung über Pro-Prompts, fliessende Story-Übergänge mit SFX-Timing, Tempo-Regeln verschärft. Betrifft core.py, dashboard.py, CEO, Marketing, SEO, Immo, Telegram.

## Offene Punkte

- Quora derzeit inaktiv (Cloudflare-Blockade) — Fallback auf gutefrage.net
- SEO-Entwürfe: 0 wartend
- Immo-Treffer ungeprueft: 1
- Geplante automatisierte Laeufe: Morgen-Durchgang (07:00, Mails + Kalender), Gedächtnis-Konsolidierung (03:00), SEO-Tagesrecherche (Zeit aus `SEO_DAILY_TIME`)

## Arbeitsweise mit Rui

- **Lieferformat:** Komplette Ersetzungsdateien, nie Patches oder sed-Befehle
- **Shell:** CMD statt PowerShell
- **Sprache:** Deutsch, sachlich, kurz und direkt
- **Deploy-Prozess:** Schritt für Schritt, nach jedem Deploy `wc -l` auf alle geänderten Dateien (sichert Vollständigkeit)
- **Kontrolle vor Auslieferung:** Alle JavaScript-Dateien müssen reviewed sein, bevor sie live gehen

## Kritische Regeln

- **`.env` wird NIEMALS angefasst** — Umgebungsvariablen nur über Ruis Änderungen an Dockerfiles oder Compose
- **`docker-compose.yml`:** Fertige Service-Blöcke zum manuellen Einfügen, keine Automatisierungs-Skripte
- **Ausgeliefertes JavaScript:** Vor Deployment vollständig prüfen (Syntax, Abhängigkeiten, Sicherheit)
- **Gedächtnis (pgvector):** Keine direkten SQL-Updates — über JARVIS-API oder orchestrator/core.py schreiben
- **Externe APIs:** Mail/Kalender sind read-only; SEO und Immo schreiben NUR in Vault/Telegram, nicht direkt ins Web