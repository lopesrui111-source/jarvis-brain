<!-- automatisch erzeugt am 18.08.2026 07:01 — nicht von Hand bearbeiten -->

# STATUS

## Was das System ist

Multi-Bot-System auf Hetzner CX23 (195.201.7.109) mit JARVIS als Orchestrator. JARVIS delegiert spezialisierte Aufgaben an CEO (Strategie), MARKETING (Creatives), SEO (Recherche), IMMO (Immobilien-Analyse) und TELEGRAM (Messaging-Bridge). Alle Bots laufen in Docker Compose, speichern Gedächtnis in PostgreSQL 16 mit pgvector, Zwischenergebnisse im Vault.

## Infrastruktur

- **Server**: Hetzner CX23, Ubuntu, Docker Compose
- **Repo-Wurzel**: `/opt/jarvis-brain/` (nicht `/opt/jarvis/`)
- **Datenbank**: PostgreSQL 16, pgvector-Extension, DB `jarvis_brain`, User `jarvis`
- **Cache/Queue**: Redis
- **Dienste**: postgres, redis, adminer, watchtower, dashboard, jarvis-core, jarvis-ceo, jarvis-marketing, jarvis-recorder, jarvis-regie, jarvis-render, camofox, jarvis-immo, jarvis-seo, jarvis-telegram
- **Zeitzone**: Europe/Berlin (in allen Dockerfiles gesetzt)
- **Deploy**: docker-compose.yml mit manuellen Block-Einfügungen, keine Skripte

## Aktueller Stand je Komponente

| Datei | Zeilen | Letzte Änderung |
|-------|--------|-----------------|
| orchestrator/core.py | 3434 | Morgen-Durchgang, Lagebild-Tool, Auftrags-System |
| dashboard/dashboard.py | 4959 | Web-UI für Aufgaben, Mails, Kalender, Gedächtnis |
| bots/ceo/bot.py | 777 | CEO-Review für Marketing-Entwürfe |
| bots/marketing/bot.py | 1261 | 48 Skills + 345 Anleitungen, MuAPI-Bildgen |
| bots/seo/bot.py | 1563 | gutefrage.net-Recherche, Entwürfe im Vault (Quora deaktiviert) |
| bots/immo/bot.py | 1092 | Rendite-Analysen, Plausibilität, Telegram-Hinweise |
| bots/telegram/bridge.py | 350 | Durchreiche-Schicht, kein Gedächtnis |

**JARVIS-Fähigkeiten**: Gedächtnis (pgvector), Mail lesen (IMAP IONOS + Gmail), Kalender lesen (Google iCal, read-only), Web-Recherche, GitHub lesen, Auftrags-System, Aufgabenverwaltung, Morgen-Durchgang (07:00), Lagebild-Tool, Doku-System. Delegiert spezialisierte Arbeiten.

## Zuletzt gebaut

- **Motion-Referenzbibliothek**: 10 Komponenten dokumentiert (Vorschau-Renders, Bewegungsprüfung, Typografie, Anti-Abbruch), README mit Verwendungsanleitung

## Systemlage (Momentaufnahme)

- Offene Aufgaben: 9
- SEO-Entwürfe wartend: 0
- Immo-Treffer ungeprueft: 18
- Kosten 30 Tage: regie $12.34, jarvis $11.42, marketing $7.75, seo $1.83, buroflow-ceo $1.65, immo $1.07

## Offene Punkte

Keine kritischen Blockaden dokumentiert.

## Arbeitsweise mit Rui

- **Dateiaustausch**: Vollständige Ersetzungsdateien, nicht Patches
- **Shell**: `CMD` (Bash), nie PowerShell
- **Sprache**: Deutsche Antworten, sachlich, kurz und direkt
- **Deployment**: Nach jedem Deploy `wc -l` auf geänderte Dateien prüfen
- **Schrittweise**: Ein Änderungsschritt pro Request, dann warten

## Kritische Regeln

- **`.env` unantastbar**: Wird nie angefasst, nie im Repo commitet
- **`docker-compose.yml`**: Nur fertige Blöcke zum manuellen Einfügen liefern, keine Automatisierungs-Skripte
- **JavaScript vor Auslieferung**: Prüfung auf Syntax und Kompatibilität
- **Mail/Kalender**: JARVIS liest nur; Änderungen von Hand durch Rui
- **SEO-Posts**: Keine automatische Veröffentlichung; Entwürfe gehen in den Vault, Rui postet von Hand
- **pgvector-Queries**: Achte auf embedding_model und similarity-Schwellenwerte