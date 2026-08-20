"""core_patch.py — Sensible Daten im JARVIS-Core verschluesselt speichern.

PROBLEM, das behoben wird:
  JARVIS lehnte sensible Daten inhaltlich ab und rief remember nicht auf.
  Danach griff die Zwangs-Speicherung (tool_choice erzwingt remember) und
  legte die Daten IM KLARTEXT ab — mit Embedding, also fuer jeden Bot
  lesbar und auffindbar. Ergebnis: "Ich speichere nicht" gefolgt von
  "Gespeichert". Der Nutzer denkt, nichts sei passiert.

LOESUNG (zwei Ebenen):
  1. Ein Sicherheitsnetz in run_tool: Erkennt remember-Aufrufe mit
     sensiblen Mustern (IBAN, Kartennummer, CVC) und setzt geheim=true
     automatisch — auch wenn das Modell es vergisst.
  2. Prompt-Regel: sensible Daten werden VERSCHLUESSELT gespeichert
     statt abgelehnt.
"""
import re, shutil, ast

PFAD = "/opt/jarvis-brain/orchestrator/core.py"
shutil.copy(PFAD, PFAD + ".bak")
src = open(PFAD, encoding="utf-8").read()

# ── 1. Sicherheitsnetz vor run_tool ──────────────────────────────
if "_sensibel_pruefen" not in src:
    netz = '''

# ── Sicherheitsnetz: sensible Daten nie im Klartext speichern ──────
# Greift auch dann, wenn das Modell 'geheim' vergisst oder die
# Zwangs-Speicherung remember ohne Ruecksicht aufruft.
_SENSIBEL_MUSTER = [
    re.compile(r"\\b[A-Z]{2}\\d{2}[\\s]?[\\dA-Z]{4}[\\s]?[\\dA-Z]{4}", re.I),   # IBAN
    re.compile(r"\\b(?:\\d[ -]?){13,19}\\b"),                                  # Kartennummer
    re.compile(r"\\bcvc\\b|\\bcvv\\b|\\bprüfziffer\\b", re.I),
    re.compile(r"\\bpasswort\\b|\\bpassword\\b|\\bapi[_-]?key\\b", re.I),
    re.compile(r"\\bsteuer[- ]?id\\b|\\bsteuernummer\\b", re.I),
]

def _sensibel_pruefen(name, inp):
    """Setzt geheim=true, wenn ein remember-Aufruf sensible Muster enthaelt."""
    if name != "remember" or not isinstance(inp, dict):
        return inp
    if inp.get("geheim"):
        return inp
    text = f"{inp.get('title','')} {inp.get('content','')}"
    for muster in _SENSIBEL_MUSTER:
        if muster.search(text):
            inp = dict(inp)
            inp["geheim"] = True
            print("  [schutz] Sensible Daten erkannt -> verschluesselt speichern", flush=True)
            break
    return inp
'''
    # nach den Importen einfuegen
    m = list(re.finditer(r'^(import |from )\S+.*$', src, re.M))
    pos = m[-1].end()
    src = src[:pos] + netz + src[pos:]
    print("1/3 Sicherheitsnetz eingefuegt")

# ── 2. In run_tool einhaengen ────────────────────────────────────
m = re.search(r'^def run_tool\(name, inp[^)]*\):\s*\n', src, re.M)
if m and "_sensibel_pruefen(name, inp)" not in src:
    pos = m.end()
    src = src[:pos] + "    inp = _sensibel_pruefen(name, inp)\n" + src[pos:]
    print("2/3 run_tool abgesichert")
elif "_sensibel_pruefen(name, inp)" in src:
    print("2/3 run_tool bereits abgesichert")
else:
    print("WARNUNG: run_tool nicht gefunden — bitte manuell pruefen")

# ── 3. Prompt-Regel ──────────────────────────────────────────────
alt_regel = "- Speichere nichts Belangloses — Qualitaet vor Quantitaet im Gedaechtnis."
neu_regel = ('''- Speichere nichts Belangloses — Qualitaet vor Quantitaet im Gedaechtnis.
- SENSIBLE DATEN (Bankverbindungen, Kartennummern, IBAN, Zugaenge, Passwoerter, Ausweis-
  und Steuernummern): NICHT ablehnen, sondern mit 'geheim': true speichern. Solche
  Eintraege werden verschluesselt abgelegt und sind nur fuer dich und den CEO-Bot lesbar;
  andere Bots sehen nur einen Platzhalter. Sag Rui kurz, dass du verschluesselt gespeichert
  hast. Behaupte NIE, du wuerdest etwas nicht speichern, und speicherst es dann doch —
  das ist der schlimmste Fehler, weil er sich in falscher Sicherheit wiegt.''')
if alt_regel in src and "SENSIBLE DATEN" not in src:
    src = src.replace(alt_regel, neu_regel, 1)
    print("3/3 Prompt-Regel ergaenzt")
else:
    print("3/3 Prompt-Regel schon vorhanden oder Anker nicht gefunden")

open(PFAD, "w", encoding="utf-8").write(src)
ast.parse(src)
print("\ncore.py syntaktisch OK — Sicherung: core.py.bak")
