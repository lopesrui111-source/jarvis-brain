# JARVIS BRAIN — Cheat-Sheet
*Server: Hetzner CX23 · 195.201.7.109 · /opt/jarvis-brain/ · Stand: Juli 2026*

---

## 1. Verbinden & Starten

| Zweck | Befehl (PC-CMD) |
|---|---|
| SSH auf den Server | `ssh -i %USERPROFILE%\.ssh\jarvis_key jarvis@195.201.7.109` |
| Dashboard-Tunnel (Fenster offen lassen) | `ssh -i %USERPROFILE%\.ssh\jarvis_key -L 8090:127.0.0.1:8090 jarvis@195.201.7.109` |
| Dashboard im Browser | `http://localhost:8090` |
| Datei hochladen (scp-Muster) | `scp -i %USERPROFILE%\.ssh\jarvis_key "C:\Users\rlope\Downloads\DATEI" jarvis@195.201.7.109:/opt/jarvis-brain/ZIEL` |

**Auf dem Server** (`cd /opt/jarvis-brain` zuerst):

| Zweck | Befehl |
|---|---|
| Alles starten | `docker compose up -d` |
| Status aller Container | `docker compose ps` |
| Einen Bot neu bauen | `docker compose up -d --build jarvis-core` *(oder jarvis-ceo, jarvis-marketing, jarvis-immo, dashboard, camofox)* |
| Logs ansehen | `docker compose logs jarvis-core --tail 20` |
| Live-Logs | `docker compose logs -f jarvis-immo` |
| Alles neustarten | `docker compose restart` |
| CLI direkt zu JARVIS | `docker exec -it jarvis-core python cli.py` |
| CLI zum Immo-Bot | `docker exec -it jarvis-immo python cli.py` |
| Sichern (nach Änderungen) | `git add -A && git commit -m "..." && git push` |
| Datei-Vollständigkeit prüfen | `wc -l dashboard/dashboard.py` *(Zeilenzahl gegen Angabe im Chat abgleichen)* |

---

## 2. Chat mit JARVIS — Keywords & Prompts

*(Dashboard-Chat, Ziel „JARVIS", oder CLI)*

### Gedächtnis
| Prompt | Wirkung |
|---|---|
| `Merke dir: ...` | Speichert dauerhaft ins Langzeitgedächtnis (pgvector) |
| `Was weißt du über ...?` | Semantische Suche im Gedächtnis |
| `konsolidiere` | Nightly-Konsolidierung sofort ausführen (Tages-Log → Erinnerungen) |
| `reset` / `vergiss alles` | Kurzzeit-Verlauf leeren (Langzeitgedächtnis bleibt!) |

### Mail (read-only)
| Prompt | Wirkung |
|---|---|
| `Check meine Mails` / `Was ist im Büroflow-Postfach?` | IONOS-Posteingang lesen |
| `Ungelesene Gmail-Mails?` | Gmail-Posteingang lesen |
| `Lies mir die Mail von ... vor` | Einzelne Mail komplett anzeigen |

### Kalender (read-only, iCloud)
| Prompt | Wirkung |
|---|---|
| `Was steht diese Woche im Kalender?` | Nächste 7 Tage |
| `Termine der nächsten 14 Tage?` | Beliebiger Zeitraum (max 30 Tage) |
| `Hab ich morgen was?` | Kurzcheck |

### Web (camofox Stealth-Browser, nur lesen)
| Prompt | Wirkung |
|---|---|
| `Such im Web: ...` | Google-Suche + Zusammenfassung |
| `Öffne https://...` | Seite lesen |
| `Such auf YouTube/Reddit/Wikipedia/LinkedIn nach ...` | Platform-Suche |

### Stilprofile
| Prompt (CLI) | Wirkung |
|---|---|
| `stil ionos` | Schreibstil aus IONOS-Gesendet lernen |
| `stil gmail` | Schreibstil aus Gmail-Gesendet lernen |
| `Schreib die Mail in meinem Stil` | Wendet gelerntes Profil an |

### Delegation (JARVIS reicht weiter)
| Prompt | Geht an |
|---|---|
| `Frag den CEO, ...` / `Was sagt der CEO zu ...?` | Büroflow-CEO |
| `Lass Marketing ein Creative bauen: ...` | CEO → Marketing |
| `Lass den Immo-Bot meine Mails checken` | Immo-Bot |
| `Immo-Bot soll diese Anzeige bewerten: URL` | Immo-Bot |

---

## 3. Chat mit dem CEO (Ziel „CEO")

| Prompt | Wirkung |
|---|---|
| `Status Büroflow?` | Lagebericht mit CEO-Framework |
| `Entscheidung: ... — was tun?` | Entscheidungs-Framework (Kill-Kriterien, Runway) |
| `Marketing soll ...` | Delegiert an Marketing-Bot |
| `Recherchier den Wettbewerber ...` | Web-Recherche |
| `Entwurf für gutefrage-Antwort zu ...` | Lockerer Q&A-Text (nur Entwurf!) |
| `reset` | Verlauf leeren |

**Eiserne Regel:** Alles Externe (Posts, Mails) liefert er nur als ENTWURF — nichts geht automatisch raus.

---

## 4. Chat mit Marketing (Ziel „MARKETING")

| Prompt | Wirkung |
|---|---|
| `Welche Skills hast du?` | Liste der 48 Marketing-Skills |
| `Nutze den Skill ... für ...` | Lädt Skill on-demand |
| `Render ein Creative: FEIERABEND-Motiv, quadratisch` | HTML→PNG mit echtem Büroflow-Logo (beste Wahl für Text!) |
| `Generier eine Illustration ohne Text: ...` | KI-Bild via MuAPI (nie für deutschen Text nutzen) |
| `Content-Plan für nächste Woche` | Nutzt Skills + Brand |

Ergebnisse landen im **Vault** (`vault/assets/`) → Dashboard VAULT-Tab.

---

## 5. Chat mit Immo-Bot (Ziel „IMMO")

| Prompt | Wirkung |
|---|---|
| `Check meine ImmoScout-Mails` | Mails der letzten 24h bewerten (läuft im Hintergrund → Telegram) |
| `Mails der letzten 48 Stunden checken` | Eigenes Zeitfenster (max 7 Tage) |
| `Scan die Kleinanzeigen-Suchen` | IMMO_SEARCH_URLS abklappern → Telegram |
| `Bewerte: https://www.kleinanzeigen.de/s-anzeige/...` | Einzelbewertung mit beiden Szenarien |
| `Bewerte nochmal (force): URL` | Auch wenn schon bekannt |
| `Was war mein Favorit?` / `Was weißt du über Pleidelsheim?` | Gedächtnis-Abfrage |
| `reset` | Verlauf leeren |

**Feste Kriterien:** ≥ 4% Bruttorendite · 5,5% Zins · 11% NK (BW) · Szenario A (NK aus EK) + B (Vollfinanzierung). Qualifizierte Angebote → automatisch Telegram.

---

## 6. Dashboard-Bedienung

| Aktion | Wie |
|---|---|
| Ansicht wechseln | Tabs **CORE / AGENTEN / GEHIRN** oder Pfeiltasten ← → |
| Chat | rechts unten: Ziel wählen (JARVIS/CEO/MARKETING/IMMO), Enter sendet |
| Vault öffnen | **VAULT**-Tab links → Modal (Suche, Thumbnails, Download, ✕ löscht, ESC schließt) |
| Panels ein-/ausklappen | Klick auf Panel-Titel (Chevron) |
| **AGENTEN:** Karte verschieben | Ziehen (Position wird gespeichert) |
| Karte zurück ins Raster | Doppelklick auf die Karte |
| Zoomen / Verschieben | Mausrad / freie Fläche ziehen |
| Ansicht zurücksetzen | Doppelklick auf freie Fläche |
| Bot als Chat-Ziel wählen | Kurzer Klick auf seine Karte |
| **GEHIRN:** Erinnerung öffnen | Klick auf Knoten (Panel rechts) |
| Zoomen / Pan | Mausrad / Ziehen |
| Live-Wachstum | Tab offen lassen — pollt alle 20s, neue Knoten wachsen sichtbar rein |

---

## 7. Wartung & Diagnose

```bash
# Kosten der letzten Anfragen
docker exec -it jarvis-postgres psql -U jarvis -d jarvis_brain -c \
  "SELECT bot, to_char(created_at,'DD.MM HH24:MI') zeit, tokens_in, tokens_out, cost_usd FROM cost_ledger ORDER BY id DESC LIMIT 15;"

# Kosten pro Bot heute
docker exec -it jarvis-postgres psql -U jarvis -d jarvis_brain -c \
  "SELECT bot, ROUND(SUM(cost_usd)::numeric,4) FROM cost_ledger WHERE created_at::date=CURRENT_DATE GROUP BY bot;"

# Alle Erinnerungen ansehen
docker exec -it jarvis-postgres psql -U jarvis -d jarvis_brain -c \
  "SELECT id, project, title, to_char(created_at,'DD.MM') FROM memory ORDER BY id DESC LIMIT 20;"

# Erinnerung löschen (ID aus obiger Liste)
docker exec -it jarvis-postgres psql -U jarvis -d jarvis_brain -c "DELETE FROM memory WHERE id=123;"

# Verläufe aller Bots leeren (bei Kosten-/Kontext-Problemen)
docker exec jarvis-redis redis-cli DEL jarvis:history bot:ceo:history bot:marketing:history bot:immo:history

# Bereits gesehene Immo-Angebote zurücksetzen
docker exec -it jarvis-postgres psql -U jarvis -d jarvis_brain -c "TRUNCATE immo_seen;"

# Adminer (DB-GUI): Tunnel -L 8080:127.0.0.1:8080 → http://localhost:8080
```

---

## 8. .env-Variablen (Übersicht)

| Variable | Zweck |
|---|---|
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | Claude + Embeddings |
| `MAIL_IONOS_*` / `MAIL_GMAIL_*` | IMAP read-only (Host/User/Pass) |
| `ICLOUD_USER` / `ICLOUD_PASS` | Kalender (App-spezifisches Passwort) |
| `MUAPI_KEY` | Bildgenerierung Marketing |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Immo-Benachrichtigungen |
| `IMMO_SEARCH_URLS` | Kleinanzeigen-Suchen, kommagetrennt |
| `IMMO_MIN_RENDITE` / `IMMO_ZINS` / `IMMO_NK_PROZENT` | Kriterien (Default 4.0 / 5.5 / 11.0) |
| `IMMO_INTERVAL_MIN` | Auto-Scan-Intervall (weglassen/0 = nur auf Anfrage) |

Nach .env-Änderung: `docker compose up -d --build <bot>` (env wird beim Start gelesen).

---

## 9. Deploy-Routine (bei Code-Updates aus dem Chat)

1. Datei aus dem Chat → `C:\Users\rlope\Downloads\`
2. **PC-CMD** (nicht Server!): scp-Befehl aus dem Chat kopieren
3. Server: `wc -l <datei>` — Zeilenzahl muss mit Angabe übereinstimmen
4. `docker compose up -d --build <service>`
5. Browser **Strg+F5** (bei Dashboard) bzw. Log prüfen
6. Wenn gut: `git add -A && git commit -m "..." && git push`

**Nie** große Dateien per nano-Paste einfügen — scp only.
