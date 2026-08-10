<!-- automatisch erzeugt am 10.08.2026 07:00 — nicht von Hand bearbeiten -->

# STATUS

## Was das System ist

Multi-Bot-System auf Hetzner CX23 mit Docker Compose. JARVIS ist der Orchestrator (Gedächtnis, Mail, Kalender, Web-Recherche, Aufgaben). Spezialisierte Bots: CEO (Strategie/Review), MARKETING (Creatives/Skills), SEO (Recherche-Entwürfe), IMMO (Immobilien-Analysen), TELEGRAM (Durchreiche), REGIE (Motion-Design-Rendering), RECORDER (Datenerfassung), weitere Dienste (Redis, PostgreSQL, Dashboard, Watchtower).

## Infrastruktur

- **Server:** Hetzner CX23, 195.201.7.109, Ubuntu, Docker Compose
- **Repo-Wurzel:** /opt/jarvis-brain/ (nicht /opt/jarvis/)
- **Datenbank:** PostgreSQL 16 mit pgvector, Datenbankname `jarvis_brain`, Benutzer `jarvis`
- **Laufende Dienste:** redis, postgres, adminer, watchtower, dashboard, jarvis-core, jarvis-ceo, jarvis-marketing, jarvis-recorder, jarvis-regie, jarvis-render, camofox, jarvis-immo, jarvis-seo, jarvis-telegram
- **Zeitzone:** Europe/Berlin in allen Bot-Dockerfiles

## Aktueller Stand je Komponente

| Datei | Zeilen | Aufgabe | Zuletzt geändert |
|-------|--------|---------|------------------|
| orchestrator/core.py | 3434 | Orchestrator: Gedächtnis (pgvector), Mail-Lesen (IMAP), Kalender-Lesen (Google iCal), Web-Recherche, GitHub-Lesen, Auftrags-System, Aufgabenverwaltung, Morgen-Durchgang (07:00), Lagebild-Tool, Doku-System | Studio-Anbauerungen (Motion-Skills, MAX_TOKENS 8000) |
| dashboard/dashboard.py | 4123 | Zentrale Web-UI für alle Bot-Ausgaben, Aufgabenverwaltung, Status-Übersicht | – |
| bots/ceo/bot.py | 777 | Strategie/Entscheidungen für Büroflow, prueft Marketing-Entwürfe (CEO-Review), delegiert | – |
| bots/marketing/bot.py | 1261 | Creatives, Post-Texte, 48 Marketing-Skills + 345 Anleitungen, Bildgenerierung via MuAPI. Postet nichts selbst — legt Dateien im Vault ab | Motion-DNA aus Referenzen, Komponenten-Schmiede, MAX_TOKENS 8000 |
| bots/seo/bot.py | 1563 | Recherche auf gutefrage.net, schreibt Antwort-Entwürfe in Vault (postet NIEMALS selbst). Quora abgeschaltet (Cloudflare) | – |
| bots/immo/bot.py | 1092 | Rendite-Analysen, Plausibilitätsprüfung, Telegram-Hinweise | – |
| bots/telegram/bridge.py | 350 | Durchreiche-Schicht zu Telegram, kein eigenes Gedächtnis | – |
| bots/regie/bot.py | – | Rendert Motion-Design autonom via Render-Server | Higgsfield-Client bereit, wartet auf API-Guthaben |

## Zuletzt gebaut

- **Studio-Integration:** Motion-Skills (Disney easing, anti-slop), Grafik-Bausteine, custom Segmente in Story-Workflow
- **Motion-DNA:** Automatische Referenz-Analyse (easeOutExpo, Glasmorphismus, Cuts), Referenz-Analyse-Tool
- **Komponenten-Schmiede:** Bot baut eigenständig visuelle Komponenten, Regie-Bot rendert Motion-Design autonom
- **Render-Server:** Higgsfield-Client integriert, warten auf API-Guthaben zur Aktivierung

## Offene Punkte

- Regie-Bot: API-Guthaben für Higgsfield einrichten
- SEO-Quora: Cloudflare-Bypass oder Alternative evaluieren
- Kosten-Monitoring: Täglich abfragen (Budgets: JARVIS $9.91, MARKETING $7.43, CEO $1.54, SEO $1.31, IMMO $0.80 in letzten 30 Tagen)

## Arbeitsweise mit Rui

- **Datei-Übergabe:** Komplette Ersetzungsdateien statt Patches (git apply/patch vermeiden)
- **Shell:** Immer `bash`/`sh` und CMD, niemals PowerShell
- **Sprache:** Deutsch, kurz und direkt
- **Deploy-Workflow:** Schritt für Schritt mit `wc -l` nach jedem Daten-Push zur Kontrolle
- **Feedback:** Fehlermeldungen vollständig aus Logs zitieren, nicht paraphrasieren

## Kritische Regeln

- **.env:** Wird NIEMALS angefasst (API-Keys, DB-Credentials, Secrets)
- **docker-compose.yml:** Änderungen als fertige, manuelle Code-Blöcke (zum Copy-Paste), keine automatischen Skripte
- **Ausgeliefertes JavaScript:** Vor Deployment prüfen (Syntax, externe Dependencies, console.log-Reste)
- **Kalender & Mail:** Read-only. JARVIS liest, ändert nichts.
- **SEO & IMMO:** Schreiben Entwürfe in Vault, posten NICHTS selbst — Rui entscheidet manuell
- **TELEGRAM:** Nur Durchreiche, kein Speicher