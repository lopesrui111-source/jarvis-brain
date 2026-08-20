"""Ergaenzt die remember-Tool-Definition um den geheim-Parameter."""
import shutil, ast

PFAD = "/opt/jarvis-brain/bots/ceo/bot.py"
shutil.copy(PFAD, PFAD + ".bak2")
src = open(PFAD, encoding="utf-8").read()

alt = '''    {"name": "remember",
     "description": "Speichert wichtige Fakten/Entscheidungen dauerhaft im gemeinsamen Gedaechtnis.",
     "input_schema": {"type": "object", "properties": {
         "content": {"type": "string"}, "project": {"type": "string", "description": "Standard: buroflow"},
         "title": {"type": "string"}}, "required": ["content", "title"]}},'''

neu = '''    {"name": "remember",
     "description": ("Speichert wichtige Fakten/Entscheidungen dauerhaft im gemeinsamen Gedaechtnis. "
                     "Setze 'geheim': true bei SENSIBLEN Daten — Bankverbindungen, Kartennummern, IBAN, "
                     "Zugangsdaten, Passwoerter, Ausweis- und Steuernummern, Gesundheitsdaten. Solche "
                     "Eintraege werden verschluesselt abgelegt und sind nur fuer JARVIS und den CEO-Bot "
                     "lesbar; alle anderen Bots sehen nur einen Platzhalter. Im Zweifel lieber geheim "
                     "setzen — das kostet nichts ausser der semantischen Suche."),
     "input_schema": {"type": "object", "properties": {
         "content": {"type": "string"}, "project": {"type": "string", "description": "Standard: buroflow"},
         "title": {"type": "string"},
         "geheim": {"type": "boolean", "description": ("true = verschluesselt speichern, nur fuer JARVIS "
                    "und CEO lesbar. Pflicht bei Bank-/Karten-/Zugangsdaten. Hinweis: geheime Eintraege "
                    "haben kein Embedding, sind also nur ueber die Zeitsortierung auffindbar, nicht "
                    "ueber die semantische Suche — nenne den Titel deshalb praezise.")}},
         "required": ["content", "title"]}},'''

assert alt in src, "Tool-Definition nicht gefunden"
src = src.replace(alt, neu)
open(PFAD, "w", encoding="utf-8").write(src)
ast.parse(src)
print("remember-Tool um 'geheim' erweitert — Sicherung: bot.py.bak2")
