<!-- automatisch erzeugt am 12.08.2026 07:00 — nicht von Hand bearbeiten -->

# STATUS

## Was das System ist

Multi-Bot-Orchestrator auf Hetzner. JARVIS (core.py) ist der zentrale Koordinator mit Gedächtnis (PostgreSQL + pgvector), Mail- und Kalender-Zugriff, Web-Recherche. Sechs spezialisierte Bots (CEO, Marketing, SEO, Immo, Telegram, Recorder, Regie) führen delegierte Aufgaben aus. Dashboard zeigt Echtzeit-Lagebild. Alle Services laufen in Docker Compose.

## Infrastruktur

- **Server**: Hetzner CX23, 195.201.7.109, Ubuntu, Docker Compose
- **Repo**: `/opt/jarvis-brain/` (nicht `/opt/jarvis/`)
- **Datenbank**: PostgreSQL 16 mit pgvector, DB `jarvis_brain`, User `jarvis`
- **Backing-Services**: Redis, Adminer, Watchtower, pgAdmin
- **Laufende Bots**: jarvis-core, jarvis-ceo, jarvis-marketing, jarvis-seo, jarvis-immo, jarvis-telegram, jarvis-recorder, jarvis-regie, camofox
- **Zeitzone überall**: Europe/Berlin

## Aktueller Stand je Komponente

| Komponente | Zeilen | Funktion | Stand |
|---|---|---|---|
| `orchestrator/core.py` | 3434 | Orchestrator, Gedächtnis (pgvector), Mail/Kalender-Zugriff, Web-Recherche, GitHub-Zugriff, Auftrags-System, Morgen-Durchgang (07:00), Lagebild-Tool, Doku-System | Produktiv |
| `dashboard/dashboard.py` | 4123 | Echtzeit-Lagebild, Hero-Vollbild-Layout mit Original-Fonts und neuem Hintergrund | Aktualisiert |
| `bots/ceo/bot.py` | 777 | Strategische Entscheidungen, CEO-Review für Marketing-Entwürfe | Produktiv |
| `bots/marketing/bot.py` | 1261 | 48 Marketing-Skills + 345-Anleitungs-Bibliothek, Bildgenerierung via MuAPI, legt nur Dateien im Vault ab (postet nicht selbst) | Produktiv |
| `bots/seo/bot.py` | 1563 | Recherche auf gutefrage.net, schreibt Antwort-Entwürfe in Vault, postet nichts selbst. Quora abgeschaltet (Cloudflare). Tagesrecherche nach SEO_DAILY_TIME | Produktiv, Quora pausiert |
| `bots/immo/bot.py` | 1092 | Rendite-Analysen von Immobilien-Inseraten, Plausibilitätsprüfung, Telegram-Hinweise | Produktiv |
| `bots/telegram/bridge.py` | 350 | Durchreiche-Schicht, kein Gedächtnis | Produktiv |
| `bots/recorder/bot.py` | — | Clerk-Session-Login, Fake-Namen, Kachel-Werte per Label steuerbar, Seiten wählbar, 2x Schärfe | Fertig |
| `bots/regie/bot.py` | — | UI-Nachbau-Layout-Regeln, Tool-Karten final | In Arbeit |

## Zuletzt gebaut

- **Recorder komplett**: Clerk-Session-Login, Fake-Namen-Generator, Kachel-Werte labelgesteuert, Seiten auswählbar, 2x Schärfe-Filter
- **Dashboard-Hero**: Vollbild-Layout, Original-Fonts, neuer Hintergrund
- **Regie-Bot Layout**: UI-Nachbau-Regeln und Tool-Karten finalisiert

## Offene Punkte

- Regie-Bot: JavaScript vor Auslieferung prüfen
- SEO: Quora-Reintegration nach Cloudflare-Lösung
- Systemlage: 10 offene Aufgaben, 1 ungepruefter Immo-Treffer

## Arbeitsweise mit Rui

1. **Dateien**: Komplette Ersetzungsdateien liefern, nicht Patches
2. **Shell**: CMD (`cmd.exe`), nicht PowerShell
3. **Sprache**: Deutsche Antworten, kurz und direkt
4. **Deploy-Rhythmus**: Schritt für Schritt, nach jedem Deploy `wc -l` auf betroffene Dateien
5. **Feedback**: Status und Probleme sofort ansprechen
6. **.env**: NIEMALS anfassen
7. **docker-compose.yml**: Fertige Service-Blöcke zum manuellen Einfügen statt automatische Skripte

## Kritische Regeln

- `.env` ist heilig — bei Secrets nur über Umgebungsvariablen
- Alle JavaScript-Auslieferungen **vor Commit** prüfen (Syntax, Linting, Tests)
- `docker-compose.yml`-Änderungen: vollständige Service-Definition zum Copy-Paste, kein sed/awk
- Mail ist read-only (IMAP auf IONOS und Gmail)
- Kalender ist read-only (Google iCal)
- SEO und Immo postet **nichts selbst** — Entwürfe nur in den Vault
- Dashboard-Änderungen: nach Deploy Refresh und Screenshot kontrollieren
- pgvector-Index regelmäßig `REINDEX` vor großen Insertierten-Läufen