<!-- automatisch erzeugt am 08.08.2026 07:00 — nicht von Hand bearbeiten -->

# STATUS

## Was das System ist

Multi-Bot-System auf Hetzner CX23 (195.201.7.109), Docker Compose basiert. JARVIS ist der zentrale Orchestrator (core.py): liest Mail, Kalender, Web, GitHub, verwaltet Aufträge und Gedächtnis (pgvector). Spezialisierte Bots delegieren: CEO für Strategie/Review, Marketing für Creatives (345 Skills), SEO für gutefrage.net-Recherche, IMMO für Rendite-Analyse, Telegram als Durchreiche-Layer.

## Infrastruktur

**Server:** Hetzner CX23, Ubuntu, Docker Compose  
**Repo:** `/opt/jarvis-brain/` (nicht `/opt/jarvis/`)  
**Datenbank:** PostgreSQL 16 mit pgvector, DB `jarvis_brain`, User `jarvis`  
**Laufende Services:** redis, postgres, adminer, watchtower, dashboard, jarvis-core, jarvis-ceo, jarvis-marketing, jarvis-recorder, camofox, jarvis-immo, jarvis-seo, jarvis-telegram  
**Zeitzone:** Europe/Berlin (in allen Dockerfiles hardcodiert)  

Externe Quellen (read-only):
- Google iCal (Termine lesen, nicht ändern)
- IMAP: IONOS + Gmail (lesend)
- GitHub API (lesend)
- gutefrage.net (SEO-Recherche)
- Quora (derzeit ABGESCHALTET, Cloudflare-Schutz)

## Aktueller Stand je Komponente

| Datei | Zeilen | Stand |
|-------|--------|-------|
| `orchestrator/core.py` | 3434 | Orchestrator mit Mail-Parsing, Kalender-Lesend, pgvector-Memory, Morgen-Durchgang 07:00, Lagebild-Tool, Doku-System. Delegiert an Spezialbots. |
| `dashboard/dashboard.py` | 4123 | Web-UI für Aufgabenübersicht, Vault-Zugriff, Kosten-Monitoring. Auth-Methode offen (bearb. 2026-08-08). |
| `bots/ceo/bot.py` | 777 | Strategie und Entscheidungsfällung für Büroflow. Prüft Marketing-Entwürfe (CEO-Review). |
| `bots/marketing/bot.py` | 1261 | 48 Marketing-Skills + 345-Anleitungs-Skill-Bibliothek. Bildgen. über MuAPI. Legt Dateien im Vault ab, postet nicht selbst. |
| `bots/seo/bot.py` | 1563 | Recherchiert gutefrage.net, schreibt Antwort-Entwürfe in Vault. Postet nichts selbst. Daily-Lauf nach SEO_DAILY_TIME. |
| `bots/immo/bot.py` | 1092 | Rendite-Analyse von Immobilien-Inseraten, Plausibilitätsprüfung, Telegram-Hinweise. |
| `bots/telegram/bridge.py` | 350 | Durchreiche-Schicht ohne eigenes Gedächtnis. |
| `bots/recorder/bot.py` | – | Oeffentliche Seiten fertig, Dashboard-Auth noch offen (Stand 2026-08-08). |

## Zuletzt gebaut

**Recorder-Bot** (2026-08-08): Für öffentliche Seiten fertiggestellt. Dashboard-Auth-Integration noch offen.

## Offene Punkte

- Dashboard-Auth (Recorder-Integration)
- SEO: Quora-Support durch Cloudflare-Schutz blockiert (Status: bekannt, nicht bearbeitbar)
- 14 offene Aufgaben (im System)
- 1 SEO-Entwurf wartend auf Review

## Arbeitsweise mit Rui

1. **Austausch:** Komplette Ersetzungsdateien per Paste, keine Patches.
2. **Shell:** Ausschließlich `bash` (CMD), nie PowerShell. Jedes Deploy mit `wc -l` auf betroffene Dateien prüfen.
3. **Sprache:** Deutsche Antworten, sachlich, direkt, knapp.
4. **Tempo:** Schritt für Schritt. Nach jedem Deploy kurze Bestätigung der Zeilenzahl und Status.
5. **Git:** Commit-Messages prägnant, Thema vor Details.

## Kritische Regeln

- **`.env` wird NICHT angefasst** — Umgebungsvariablen nur im Deployment-Prozess setzen.
- **`docker-compose.yml`:** Keine Skripte zum Einfügen. Fertige Blöcke zum manuellen Copy-Paste bereitstellen mit klaren Markierungen (`# --- START ---` / `# --- END ---`).
- **JavaScript vor Auslieferung prüfen:** Syntax validieren, keine ungetesteten Minifications.
- **pgvector-Schema:** Datentyp `vector(1536)` für OpenAI embeddings, nie ändern ohne Migration.
- **Geheimnisse:** Alle Tokens/Keys nur über env-Vars, niemals in Code oder Logs.