"""Ergaenzt tool_remember im Core um Verschluesselung — analog zum CEO-Bot.
Ohne diesen Schritt setzt das Sicherheitsnetz zwar geheim=true, die Funktion
ignoriert es aber und speichert weiter im Klartext."""
import re, shutil, ast

PFAD = "/opt/jarvis-brain/orchestrator/core.py"
shutil.copy(PFAD, PFAD + ".bak2")
src = open(PFAD, encoding="utf-8").read()

# ── 1. memory_crypto importieren ─────────────────────────────────
if "import memory_crypto" not in src:
    m = list(re.finditer(r'^(import |from )\S+.*$', src, re.M))
    pos = m[-1].end()
    src = (src[:pos] +
           "\n\n# Verschluesselung fuer sensible Gedaechtnis-Eintraege\n"
           "try:\n"
           "    import memory_crypto as _mc\n"
           "except Exception:\n"
           "    _mc = None" +
           src[pos:])
    print("1/3 Import ergaenzt")

# ── 2. tool_remember um geheim erweitern ─────────────────────────
alt = '''def tool_remember(inp: dict) -> str:
    content = inp.get("content", "").strip()
    project = inp.get("project", "sonstiges").strip().lower()
    title   = inp.get("title", "").strip()
    if not content:
        return "Fehler: leerer Inhalt."
    v = embed(f"{title}\\n{content}")'''

neu = '''def tool_remember(inp: dict) -> str:
    content = inp.get("content", "").strip()
    project = inp.get("project", "sonstiges").strip().lower()
    title   = inp.get("title", "").strip()
    geheim  = bool(inp.get("geheim"))
    if not content:
        return "Fehler: leerer Inhalt."

    # GEHEIME EINTRAEGE: verschluesselt und OHNE Embedding. Ohne Embedding
    # kann kein anderer Bot per Aehnlichkeitssuche erkennen, dass es einen
    # Eintrag zu diesem Thema ueberhaupt gibt.
    if geheim:
        if _mc is None or not _mc.hat_schluessel():
            return ("Fehler: Kein Verschluesselungs-Schluessel (MEMORY_KEY fehlt). "
                    "Sensible Daten werden NICHT im Klartext gespeichert. "
                    "Nichts wurde abgelegt.")
        content = _mc.verschluesseln(content)
        if content is None:
            return "Fehler: Verschluesselung fehlgeschlagen. Nichts gespeichert."
        v = None
    else:
        v = embed(f"{title}\\n{content}")'''

if alt in src:
    src = src.replace(alt, neu)
    print("2/3 tool_remember erweitert")
else:
    print("WARNUNG: tool_remember nicht im erwarteten Format — bitte pruefen")

# ── 3. Tool-Definition um geheim ergaenzen ───────────────────────
m = re.search(r'\{"name":\s*"remember",.*?\}\},', src, re.S)
if m and '"geheim"' not in m.group(0):
    block = m.group(0)
    neu_block = block.replace(
        '"title": {"type": "string"}',
        '"title": {"type": "string"},\n'
        '         "geheim": {"type": "boolean", "description": '
        '"true = verschluesselt speichern (nur JARVIS und CEO koennen lesen). '
        'PFLICHT bei Bankverbindungen, Kartennummern, IBAN, Zugangsdaten, Passwoertern, '
        'Ausweis- und Steuernummern. Lehne solche Daten NICHT ab — speichere sie geheim."}',
        1)
    src = src.replace(block, neu_block)
    print("3/3 Tool-Definition erweitert")
else:
    print("3/3 Tool-Definition schon erweitert oder nicht gefunden")

open(PFAD, "w", encoding="utf-8").write(src)
ast.parse(src)
print("\ncore.py syntaktisch OK — Sicherung: core.py.bak2")
