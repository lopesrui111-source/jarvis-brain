<!-- automatisch erzeugt am 29.07.2026 15:46 — nicht von Hand bearbeiten -->

# STATUS

## Was das System ist

Multi-Bot-System auf einem Hetzner-Server. JARVIS (orchestrator/core.py) ist der zentrale Orchestrator mit Langzeitgedächtnis (pgvector), Mail-Lesen, Kalender-Lesen, Web-Recherche und Aufgabenverwaltung — er delegiert an spezialisierte Bots. Derzeit laufen: CEO (Strategie), Marketing (Creatives), SEO (Antwort-Entwürfe), IMMO (Rendite-Analysen), Telegram (Durchreiche-Schicht) sowie Infrastruktur-Dienste (Redis, Postgres, Adminer, Watchtower, Dashboard, Camofox).

## Infrastruktur

- **Server:** Hetzner CX23, 195.201.7.109, Ubuntu, Docker Compose
- **Repo-Wurzel:** `/opt/jarvis-brain/` (nicht /opt/jarvis/)
- **Datenbank:** PostgreSQL 16 mit pgvector, Datenbankname `jarvis_brain`, Benutzer `jarvis`
- **Zeitzone:** `Europe/Berlin` in allen Bot-Dockerfiles
- **Laufende Container:** redis, postgres, adminer, watchtower, dashboard, jarvis-core, jarvis-ceo, jarvis-marketing, camofox, jarvis-immo, jarvis-seo, jarvis-telegram, jarvis-net
- **Deploy-Muster:** Datei ersetzen → `docker compose up -d --build <dienst>` → `wc -l` zur Prüfung

## Aktueller Stand je Komponente

| Datei | Zeilen | Was sie macht | Zuletzt geändert |
|---|---|---|---|
| `orchestrator/core.py` | 2932 | Orchestrator: Gedächtnis (pgvector), Mail lesen (IMAP IONOS + Gmail), Kalender lesen (Google iCal, read-only), Web-Recherche, GitHub lesen, Auftrags-System, Aufgabenverwaltung, Morgen-Durchgang (07:00), Gedächtnis-Konsolidierung (03:00), Lagebild-Tool, Doku-System, Delegation an alle Bots | Doku-System, Morgen-Durchgang, Lagebild, Aufgaben aus Mails |
| `dashboard/dashboard.py` | 3122 | Web-HUD: Vault-Browser, Wochenansicht mit Gruppen, HEUTE-Panel, Bot-Detailfenster, Aufgaben abhaken, Mobile-Ansicht, Zoom-Buttons, Typografie-Korrekturen | Dashboard-Typografie, Abhak-Funktion, Wochenansicht |
| `bots/ceo/bot.py` | 763 | Strategie und Entscheidungen für Büroflow, CEO-Review von Marketing-Entwürfen, Zugriff auf Skill-Bibliothek (345 Anleitungen) | Skill-Modul integriert |
| `bots/marketing/bot.py` | 1194 | 48 Marketing-Skills, Creatives und Post-Texte, Bildgenerierung über MuAPI, CEO-Review-Schleife, Bild-Rhythmus, Notbremse. Postet NICHTS selbst — legt Dateien im Vault ab. | CEO-Review, Bild-Rhythmus, Notbremse |
| `bots/seo/bot.py` | 1113 | Recherchiert Fragen auf gutefrage.net, schreibt Antwort-Entwürfe in den Vault. Postet NIEMALS selbst. Tageslauf mit Nachholen, Cookie-Consent automatisch wegklicken. Quora derzeit ABGESCHALTET (Cloudflare-Schutz). | SEO-Tageslauf, Quellen-Fix, Nachholen |
| `bots/immo/bot.py` | 901 | Rendite-Analysen von Immobilien-Inseraten, Plausibilitätsprüfung, Telegram-Hinweise | Plausibilitätsprüfung |
| `bots/telegram/bridge.py` | 289 | Durchreiche-Schicht zwischen Telegram und den Bots. Kein eigenes Gedächtnis. | Initiale Implementierung |

**Geplante Läufe:**
- 07:00 — Morgen-Durchgang: Mails beider Konten + Kalender, legt Aufgaben an; danach automatisch Doku-Lauf
- 03:00 — Gedächtnis-Konsolidierung (Tages-Log, Fakten-Extraktion, Dedup, Vault-Tagesnotiz)
- Täglich — SEO-Tagesrecherche zur Zeit aus `SEO_DAILY_TIME`

## Zuletzt gebaut

**Doku-System, Morgen-Durchgang, Lagebild (neueste Arbeit)**
JARVIS hat ein Doku-System bekommen. Der Morgen-Durchgang läuft um 07:00 automatisch und legt aus Mails Aufgaben an. Das Lagebild-Tool zeigt den aktuellen Systemzustand. Dashboard: Typografie-Korrekturen, Aufgaben lassen sich abhaken. SEO-Quellen wurden gefixt.

**Wochenansicht, Bot-Detailfenster, Marketing-Workflow**
Dashboard erhielt Wochenansicht mit Gruppen und Bot-Detailfenster. Marketing-Bot: CEO-Review-Schleife, Bild-Rhythmus, Notbremse. SEO-Tageslauf mit Nachholen-Logik. Zeitzone-Handling bereinigt.

**Skill-Bibliothek**
Wiederverwendbares Skill-Modul mit 345 Anleitungen. CEO hat Zugriff darauf; Architektur erlaubt Erweiterung auf weitere Bots.

**Immo, Dashboard-Panels, Mobile**
Immo-Bot: Plausibilitätsprüfung für Inserate. Dashboard: HEUTE-Panel, Mobile-Ansicht, Zoom-Buttons.

**Telegram-Brücke**
Initiale Durchreiche-Schicht als eigenem Container.

**Google-Kalender-Migration**
Von iCloud auf Google iCal umgestellt (read-only).

**Multi-Agent-Grundstack**
Marketing-Bot (48 Skills, render_creative, Brand-Kit, MuAPI-Bildgenerierung), CEO v3, Camofox Web-Zugriff, Prompt-Caching, Kosten-Tracking, Dashboard Vault-Browser.

**JARVIS-Kernfunktionen**
Langzeitgedächtnis mit pgvector und Embeddings, Nightly-Konsolidierung, Stilprofil aus gesendeten Mails (IONOS + Gmail), DB-Schema (init.sql) versioniert, Auftrags-System, GitHub-Lesen, Büroflow-Zahlen, Umami-Integration.

## Offene Punkte

- **2 offene Aufgaben** im System (Details über Dashboard oder Lagebild abrufen)
- **3 SEO-Entwürfe** warten auf Prüfung und manuelles Posting durch Rui
- **4 Immo-Treffer** ungepüft
- **Quora abgeschaltet** — Cloudflare-Schutz blockiert SEO-Bot; kein Workaround aktiv
- **Kosten 30 Tage:** jarvis $7.00 · marketing $4.25 · buroflow-ceo $0.56 · immo $0.28 · seo $0.20

## Arbeitsweise mit Rui

- **Komplette Ersetzungsdateien** liefern, keine Patches oder Diffs
- **CMD-Syntax**, nicht PowerShell
- **Deutsch** antworten, kurz und direkt
- **Schritt für Schritt** vorgehen — nach jedem Deploy `wc -l <datei>` zur Kontrolle
- Nur eine Sache auf einmal ändern, nicht mehrere Baustellen gleichzeitig aufmachen
- Bei Unklarheiten kurz nachfragen statt vermuten

## Kritische Regeln

- **`.env` wird NIE angefasst** — keine Anweisungen, die `.env` lesen, schreiben oder überschreiben
- **`docker-compose.yml`**: fertige Blöcke zum manuellen Einfügen liefern, keine Skripte die die Datei automatisch verändern
- **Ausgeliefertes JavaScript** vor Auslieferung prüfen — kein unkontrolliertes JS in Dashboard-Ausgaben
- JARVIS kann Kalender nur **lesen**, nicht schreiben
- Mail-Zugriff ist nur **lesend** (IMAP IONOS + Gmail)
- SEO-Bot und Marketing-Bot posten **niemals selbst** — alle Entwürfe landen im Vault, Rui postet manuell