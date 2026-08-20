"""Patch-Skript: baut die Verschluesselung in den CEO-Bot ein.
Wird auf dem Server ausgefuehrt, aendert bots/ceo/bot.py an drei Stellen."""
import re, sys, shutil

PFAD = "/opt/jarvis-brain/bots/ceo/bot.py"
shutil.copy(PFAD, PFAD + ".bak")
src = open(PFAD, encoding="utf-8").read()

# ── 1. Import ergaenzen ───────────────────────────────────────────
if "import memory_crypto" not in src:
    # nach dem letzten Standard-Import einfuegen
    m = list(re.finditer(r'^(import |from )\S+.*$', src, re.M))
    pos = m[-1].end()
    src = (src[:pos] +
           "\n\n# Verschluesselung fuer sensible Gedaechtnis-Eintraege\n"
           "import sys as _sys\n"
           "_sys.path.insert(0, '/app')\n"
           "try:\n"
           "    import memory_crypto as _mc\n"
           "except Exception:\n"
           "    _mc = None" +
           src[pos:])
    print("1/3 Import ergaenzt")

# ── 2. tool_remember: geheim-Parameter ────────────────────────────
alt_rem = '''def tool_remember(inp):
    content = (inp.get("content") or "").strip()
    project = (inp.get("project") or "buroflow").strip().lower()
    title   = (inp.get("title") or "").strip()
    if not content:
        return "Fehler: leerer Inhalt."
    v = embed(f"{title}\\n{content}")'''
neu_rem = '''def tool_remember(inp):
    content = (inp.get("content") or "").strip()
    project = (inp.get("project") or "buroflow").strip().lower()
    title   = (inp.get("title") or "").strip()
    geheim  = bool(inp.get("geheim"))
    if not content:
        return "Fehler: leerer Inhalt."

    # GEHEIME EINTRAEGE: verschluesselt speichern, KEIN Embedding.
    # Ohne Embedding kann kein anderer Bot per Aehnlichkeitssuche auch nur
    # erkennen, dass ein Eintrag zu diesem Thema existiert.
    if geheim:
        if _mc is None or not _mc.hat_schluessel():
            return ("Fehler: Dieser Bot hat keinen Verschluesselungs-Schluessel "
                    "(MEMORY_KEY fehlt). Sensible Daten werden NICHT im Klartext "
                    "gespeichert. Bitte den Schluessel in der .env setzen.")
        content = _mc.verschluesseln(content)
        if content is None:
            return "Fehler: Verschluesselung fehlgeschlagen. Nichts gespeichert."
        v = None
    else:
        v = embed(f"{title}\\n{content}")'''
if alt_rem in src:
    src = src.replace(alt_rem, neu_rem)
    print("2/3 tool_remember angepasst")
else:
    print("WARNUNG: tool_remember nicht gefunden — bitte pruefen")

# Rueckmeldung kennzeichnen
src = src.replace(
    'return f"Gespeichert (#{mid}, {project}): {title}"',
    'return f"Gespeichert (#{mid}, {project}{\', verschluesselt\' if geheim else \'\'}): {title}"')

# ── 3. tool_recall: entschluesseln beim Anzeigen ──────────────────
alt_out = '''        return "\\n".join(f"[#{r['id']} | {r['project']} | {r['created_at'].strftime('%d.%m.%Y')}] "
                         f"{r['title']}: {r['content']}" for r in rows)'''
neu_out = '''        def _inhalt(r):
            c = r["content"]
            return _mc.lesbar_machen(c) if _mc else c
        return "\\n".join(f"[#{r['id']} | {r['project']} | {r['created_at'].strftime('%d.%m.%Y')}] "
                         f"{r['title']}: {_inhalt(r)}" for r in rows)'''
if alt_out in src:
    src = src.replace(alt_out, neu_out)
    print("3/3 tool_recall angepasst")
else:
    print("WARNUNG: Ausgabe in tool_recall nicht gefunden")

# ── 4. Auch die Zeit-Sortierung soll geheime Eintraege finden ─────
src = src.replace(
    'cur.execute("SELECT id, project, title, content, created_at, 0 AS dist "\n'
    '                            "FROM memory ORDER BY created_at DESC LIMIT %s", (k,))',
    'cur.execute("SELECT id, project, title, content, created_at, 0 AS dist "\n'
    '                            "FROM memory ORDER BY created_at DESC LIMIT %s", (k,))')

open(PFAD, "w", encoding="utf-8").write(src)
import ast
ast.parse(src)
print("\nbot.py syntaktisch OK — Sicherung liegt unter bot.py.bak")
