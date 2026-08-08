<!-- automatisch erzeugt am 06.08.2026 07:00 — nicht von Hand bearbeiten -->

# STATUS

## Was das System ist

Multi-Bot-System auf Hetzner CX23 (195.201.7.109), Docker Compose, Ubuntu. JARVIS ist der Orchestrator mit Gedächtnis (PostgreSQL 16 + pgvector), liest Mail (IMAP IONOS/Gmail) und Google-Kalender (read-only), delegiert Aufgaben an spezialisierte Bots: CEO (Strategie/Review), MARKETING (Creatives, 48 Skills + 345 Anleitungen), SEO (Recherche gutefrage.net), IMMO (Rendite-Analyse), TELEGRAM (Durchreiche). Alles läuft in Redis-Cache, PostgreSQL-Speicher, mit Watchtower als Auto-Update und Dashboard zur Übersicht.

## Infrastruktur

- **Server**: Hetzner CX23, 195.201.7.109, Ubuntu, Docker Compose
- **Repo-Root**: `/opt/jarvis-brain/` (nicht `/opt/jarvis/`)
- **Datenbank**: PostgreSQL 16 mit pgvector Extension, DB `jarvis_brain`, User `jarvis`
- **Cache**: Redis
- **Zeitzone**: Europe/Berlin (in allen Bot-Dockerfiles)
- **Laufende Services**: redis, postgres, adminer, watchtower, dashboard, jarvis-core, jarvis-ceo, jarvis-marketing, camofox, jarvis-immo, jarvis-seo, jarvis-telegram
- **Daten**: Mail read-only (IMAP), Kalender read-only (Google iCal), GitHub-Lesezugriff, kein Schreiben nach außen außer über Bot-spezifische Ausgabe-Pfade (Vault, Telegram, Logs)

## Aktueller Stand je Komponente

| Datei | Zeilen | Was sie macht | Zuletzt geändert |
|-------|--------|---------------|------------------|
| `orchestrator/core.py` | 3434 | Orchestrator: Mail/Kalender-Lesen, Gedächtnis (pgvector), Auftrags-Dispatch, Morgen-Durchgang 07:00, Lagebild, Doku-System | HEALTH-Reiter, 3D-Figur, Foto-Kalorientracking, lebendiger Agenten-Baum mit Live-Stream |
| `dashboard/dashboard.py` | 4117 | Web-UI: Agent-Status, Aufgabenliste, Kosten-Tracking, Entwurf-Inbox, Immo-Queue, Bildempfang | Aufgaben-Box, Kostenoptim, Bildempfang für alle Bots |
| `bots/ceo/bot.py` | 777 | Strategie/Entscheidungen für Büroflow, CEO-Review (prueft Marketing-Entwürfe) | Stabil |
| `bots/marketing/bot.py` | 1261 | 48 Marketing-Skills, 345 Skill-Anleitungen, Bildgenerierung (MuAPI), legt Dateien im Vault ab (postet NICHT selbst) | Bildgenerierung, MuAPI-Integration |
| `bots/seo/bot.py` | 1563 | Recherche gutefrage.net, schreibt Antwort-ENTWÜRFE in Vault, postet NIEMALS selbst. Quora abgeschaltet (Cloudflare). Tagesrecherche gemäß SEO_DAILY_TIME | Quora-Abschaltung, Vault-Integration |
| `bots/immo/bot.py` | 1092 | Rendite-Analysen von Immobilien-Inseraten, Plausibilitätsprüfung, Telegram-Hinweise | Telegram-Integration |
| `bots/telegram/bridge.py` | 350 | Durchreiche-Schicht zu Telegram, kein eigenes Gedächtnis | Stabil |

## Zuletzt gebaut

- **Dashboard**: HEALTH-Reiter mit 3D-Agent-Figur und Foto-Kalorientracking, Bildempfang für alle Bots
- **Agenten-Ansicht**: Lebendiger Baum mit Live-Stream, Aufgaben-Kasten, Kostenoptimierung
- **SEO**: Quora-Plattform deaktiviert (Cloudflare-Schutz macht Scraping unmöglich)
- **Marketing**: MuAPI-Bildgenerierung integriert
- **Immo**: Telegram-Benachrichtigungen bei neuen Treffern

## Offene Punkte

- Quora-Recherche ist blockiert (Cloudflare); Alternative (Google News, Medium, Reddit) noch nicht implementiert
- SEO-Entwürfe: 1 wartend (müssen manuell freigegeben werden)
- Immo-Treffer: 0 ungeprueft (System läuft stabil)

## Arbeitsweise mit Rui

- **Dateien**: Komplette Ersetzungsdateien liefern, NICHT Patches oder Diff-Snippets
- **Shell**: CMD (Windows) oder Bash (Linux), NICHT PowerShell
- **Sprache**: Deutsch, sachlich, kurz und direkt
- **Deployment-Prozess**: Schrittweise, nach jedem Deploy Zeilenzahl prüfen (`wc -l DATEI`)
- **Konfiguration**: `.env` wird NIEMALS angefasst — neue Werte gehören in `.env.local` oder Docker-Secrets
- **docker-compose.yml**: Keine Deploy-Skripte, sondern fertige Blöcke zum manuellen Einfuegen
- **JavaScript**: Vor Auslieferung prüfen (Syntax, Console-Fehler, Performance)
- **Git**: Commits sollten ein Thema pro Commit haben, nicht 20 kleine Commits für eine Datei

## Kritische Regeln

- `.env` wird niemals verändert oder commitet; Geheimnisse gehen in `.env.local` (nicht im Repo)
- Bei Änderungen an `docker-compose.yml`: Fertige `services`-Blöcke bereitstellen zum Copy-Paste, keine Automatisierungsskripte
- JavaScript vor Auslieferung prüfen: `console.log` entfernen, `eval()` vermeiden, Abhängigkeiten lockern
- Postgres-Dump vor größeren Migrationen: `pg_dump -U jarvis jarvis_brain > backup_DATUM.sql`
- pgvector-Queries: Immer `LIMIT` setzen; `ORDER BY ... <-> ... LIMIT 5` für Similarity-Search
- JARVIS-Mail-Abruf lädt IMMER zuerst, DANN delegiert; keine parallelen Mail-Reads auf demselben IMAP-Account
- SEO/IMMO: Daten landen IMMER zuerst im Vault oder in der Datenbank, NIEMALS direkt auf fremden Plattformen