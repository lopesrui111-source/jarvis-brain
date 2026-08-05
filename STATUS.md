<!-- automatisch erzeugt am 03.08.2026 07:01 — nicht von Hand bearbeiten -->

# STATUS

## Was das System ist

Multi-Bot-Orchestrator auf Hetzner (CX23). **JARVIS** (core.py) koordiniert spezialisierte Bots: CEO (Strategie), MARKETING (Content + 48 Skills), SEO (Recherche), IMMO (Rendite-Analysen), TELEGRAM (Chat-Bridge). Alle laufen in Docker Compose, teilen PostgreSQL 16 + pgvector für Gedächtnis und Redis für Queues.

## Infrastruktur

- **Server:** Hetzner CX23, 195.201.7.109, Ubuntu
- **Root-Pfad:** `/opt/jarvis-brain/`
- **Container:** docker-compose.yml mit redis, postgres, adminer, watchtower, dashboard, alle Bots
- **DB:** PostgreSQL 16, Datenbankname `jarvis_brain`, Benutzer `jarvis`
- **Secrets:** `.env` (NIE anfassen)
- **Zeitzone:** Europe/Berlin in allen Bot-Dockerfiles

## Aktueller Stand je Komponente

| Komponente | Zeilen | Funktion | Zuletzt geändert |
|---|---|---|---|
| **orchestrator/core.py** | 3434 | Orchestrator, Gedächtnis (pgvector), Mail (IMAP IONOS+Gmail), Kalender (Google iCal read-only), Web-Recherche, GitHub, Auftrags-System, Morgen-Durchgang 07:00, Lagebild-Tool, Doku-System | Quellenfehler-Tracking, Fortschrittsanzeige |
| **dashboard/dashboard.py** | 3274 | Web-UI, Aufgabenstatus, Logs, Systemmetriken, Manual Triggers | — |
| **bots/ceo/bot.py** | 763 | Strategie + Büroflow-Entscheidungen, CEO-Review für Marketing-Entwürfe | — |
| **bots/marketing/bot.py** | 1230 | Content-Generierung, 48 Marketing-Skills + 345 Skill-Bibliothek, Bildgen (MuAPI), legt Ergebnisse in Vault (postet NICHT selbst) | — |
| **bots/seo/bot.py** | 1548 | Recherche gutefrage.net, schreibt Antwort-Entwürfe in Vault (postet NICHT), Reddit (neu, read-only), Quora ABGESCHALTET (Cloudflare) | Reddit-Anbindung hinzugefügt, _antwort_senden ergänzt |
| **bots/immo/bot.py** | 1077 | Rendite-Analysen Immobilien-Inserate, Plausibilität, Telegram-Hinweise | — |
| **bots/telegram/bridge.py** | 350 | Chat-Durchreiche, kein Gedächtnis | — |

## Zuletzt gebaut

- **Reddit-Integration (SEO):** Read-only-Anbindung, Quellenfehler im Chat sichtbar, Fortschrittsbalken beim Recherchieren
- **SEO-Fehlerbehandlung:** `_antwort_senden()` ergänzt, robustere Fehlerquellen-Anzeige
- **Listener-Status:** LISTENER-Anzeige im Dashboard korrigiert

## Offene Punkte

- Quora: Cloudflare-Schutz blockiert Zugriff (derzeit deaktiviert)
- 1 SEO-Entwurf wartet auf Freigabe
- 3 Immo-Treffer ungeklärt
- 3 offene Aufgaben im System

## Arbeitsweise mit Rui

1. **Dateiaustausch:** Komplette Datei-Ersetzung statt Patches/Snippets (copy-paste-Sicherheit)
2. **Shell:** CMD (`cmd.exe`) statt PowerShell
3. **Sprache:** Deutsch, sachlich, direkt, kompakt
4. **Deployment-Schritte:** Schrittweise, nach jedem Block `wc -l <datei>` zur Verifikation
5. **docker-compose.yml:** Fertige Blöcke zum manuellen Einfügen, KEINE Automatisierungs-Skripte
6. **Secrets:** `.env` wird NIEMALS geändert oder angefasst
7. **JavaScript-Auslieferung:** Alle JS-Dateien vor Deployment prüfen (Syntax, Imports, API-Calls)

## Kritische Regeln

- `.env` ist unveränderlich — alle Änderungen gehen in Code, nicht in Konfiguration
- Neue Bot-Bots-Dockerfiles müssen `TZ=Europe/Berlin` haben
- Mail und Kalender sind **read-only** (JARVIS liest nur, schreibt NIE)
- MARKETING und SEO schreiben nur in den Vault, nicht ins Netz
- IMMO und CEO schreiben Hinweise an TELEGRAM, nicht direkt ins Internet
- pgvector-Queries müssen mit `similarity_threshold` tesseliert werden (bei >50k Einträgen)
- Redis-TTL für Aufgaben: 7 Tage Standard