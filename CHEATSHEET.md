# Cheatsheet

Stand: 09.08.2026 07:01 — automatisch erzeugt.

## Verbindung
```
ssh -i %USERPROFILE%\.ssh\jarvis_key jarvis@195.201.7.109
ssh -i %USERPROFILE%\.ssh\jarvis_key -L 8090:127.0.0.1:8090 jarvis@195.201.7.109
```
Dashboard danach: http://127.0.0.1:8090

## Datei einspielen
```
scp -i %USERPROFILE%\.ssh\jarvis_key "C:\Users\rlope\Downloads\DATEI" jarvis@195.201.7.109:/opt/jarvis-brain/PFAD
cd /opt/jarvis-brain && wc -l PFAD && docker compose up -d --build SERVICE
```

## Dateien und Dienste
| Datei | Dienst |
|---|---|
| orchestrator/core.py | jarvis-core |
| dashboard/dashboard.py | dashboard |
| bots/ceo/bot.py | jarvis-ceo |
| bots/marketing/bot.py | jarvis-marketing |
| bots/seo/bot.py | jarvis-seo |
| bots/immo/bot.py | jarvis-immo |
| bots/telegram/bridge.py | jarvis-telegram |

## Aktuelle Zeilenzahlen
| Datei | Zeilen |
|---|---|
| orchestrator/core.py | 3434 |
| dashboard/dashboard.py | 4123 |
| bots/ceo/bot.py | 777 |
| bots/marketing/bot.py | 1261 |
| bots/seo/bot.py | 1563 |
| bots/immo/bot.py | 1092 |
| bots/telegram/bridge.py | 350 |

## Haeufige Befehle
```
docker compose ps
docker compose logs -f DIENST
docker compose logs --tail=100 DIENST | grep -iE "muster"
docker compose exec postgres psql -U jarvis -d jarvis_brain -c "\d TABELLE"
```

## Handbefehle an JARVIS
- `morgenlauf` — Mails beider Konten + Kalender durchgehen, Aufgaben anlegen
- `changelog` — Doku neu erzeugen
- `konsolidiere` — Gedaechtnis verdichten
- `reset` — Kurzzeitgedaechtnis leeren

## Geplante Laeufe
- Morgen-Durchgang: 07:00 (danach automatisch die Doku)
- Gedaechtnis-Konsolidierung: 03:00
- SEO-Tagesrecherche: siehe SEO_DAILY_TIME in der .env
