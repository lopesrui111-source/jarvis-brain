#!/usr/bin/env python3
"""
SKILL-BIBLIOTHEK — gemeinsames Modul fuer alle JARVIS-Bots
Liest die Fachanleitungen aus dem gemounteten Repo (read-only) und stellt
drei Tools bereit: skill_suchen, skill_laden, persona_laden.

Einbinden in einem Bot:
    from skills import skills_indexieren, SKILL_TOOLS, skill_tool_ausfuehren, skill_banner
    skills_indexieren()                      # einmal beim Start
    TOOLS = TOOLS + SKILL_TOOLS              # Tools registrieren
    # in run_tool():  res = skill_tool_ausfuehren(name, inp)
    #                 if res is not None: return res

Dazu im Dockerfile `COPY skills.py ./` und in docker-compose.yml
`- ./skills-lib:/app/skills-lib:ro` als Volume.
"""

import os
import re

SKILLS_DIR = os.getenv("SKILLS_DIR", "/app/skills-lib")
SKILL_MAX_ZEICHEN = int(os.getenv("SKILL_MAX_ZEICHEN", "14000"))

SKILL_INDEX = []      # [{name, beschreibung, kategorie, pfad}]
PERSONA_INDEX = []    # [{name, pfad}]

_UEBERSPRINGEN = (".gemini", ".hermes", ".vibe", ".git", "node_modules", ".github")


def _frontmatter(pfad):
    """Liest name/description/category aus dem YAML-Kopf einer SKILL.md."""
    name = beschreibung = kategorie = ""
    try:
        with open(pfad, encoding="utf-8", errors="replace") as f:
            if f.readline().strip() != "---":
                return None
            for _ in range(40):
                zeile = f.readline()
                if not zeile or zeile.strip() == "---":
                    break
                z = zeile.strip()
                if z.startswith("name:"):
                    name = z.split(":", 1)[1].strip().strip('"\'')
                elif z.startswith("description:"):
                    beschreibung = z.split(":", 1)[1].strip().strip('"\'')
                elif z.startswith("category:"):
                    kategorie = z.split(":", 1)[1].strip().strip('"\'')
    except Exception:
        return None
    if not name:
        name = os.path.basename(os.path.dirname(pfad))
    return {"name": name, "beschreibung": beschreibung[:400],
            "kategorie": kategorie or pfad.replace(SKILLS_DIR, "").strip("/").split("/")[0],
            "pfad": pfad}


def skills_indexieren():
    """Baut den Index einmalig beim Start auf. Duplikate werden uebersprungen."""
    global SKILL_INDEX, PERSONA_INDEX
    SKILL_INDEX, PERSONA_INDEX = [], []
    if not os.path.isdir(SKILLS_DIR):
        return 0, 0
    gesehen = set()
    for wurzel, dirs, dateien in os.walk(SKILLS_DIR):
        dirs[:] = [d for d in dirs if d not in _UEBERSPRINGEN]
        if "SKILL.md" in dateien:
            eintrag = _frontmatter(os.path.join(wurzel, "SKILL.md"))
            if eintrag and eintrag["name"].lower() not in gesehen:
                gesehen.add(eintrag["name"].lower())
                SKILL_INDEX.append(eintrag)
    pdir = os.path.join(SKILLS_DIR, "agents", "personas")
    if os.path.isdir(pdir):
        for f in sorted(os.listdir(pdir)):
            if f.endswith(".md") and f not in ("README.md", "TEMPLATE.md"):
                PERSONA_INDEX.append({"name": f[:-3], "pfad": os.path.join(pdir, f)})
    return len(SKILL_INDEX), len(PERSONA_INDEX)


def skill_banner():
    return f"{len(SKILL_INDEX)} Anleitungen, {len(PERSONA_INDEX)} Personas"


def tool_skill_suchen(inp):
    query = (inp.get("query") or "").strip().lower()
    if not SKILL_INDEX:
        return "Skill-Bibliothek nicht verfuegbar (Mount pruefen)."
    if not query:
        kats = {}
        for s in SKILL_INDEX:
            kats[s["kategorie"]] = kats.get(s["kategorie"], 0) + 1
        return (f"{len(SKILL_INDEX)} Skills in diesen Bereichen:\n" +
                "\n".join(f"  {k} ({v})" for k, v in sorted(kats.items(), key=lambda x: -x[1])) +
                "\n\nSuche mit einem Stichwort, z.B. 'pricing', 'seo', 'security'.")
    woerter = [w for w in re.split(r"[^a-z0-9äöüß]+", query) if len(w) > 2]
    treffer = []
    for s in SKILL_INDEX:
        heu = f"{s['name']} {s['beschreibung']} {s['kategorie']}".lower()
        punkte = sum(3 if w in s["name"].lower() else (1 if w in heu else 0) for w in woerter)
        if punkte:
            treffer.append((punkte, s))
    if not treffer:
        return f"Keine Skills zu '{query}' gefunden."
    treffer.sort(key=lambda t: -t[0])
    zeilen = [f"- {s['name']} [{s['kategorie']}]: {s['beschreibung'][:180]}" for _, s in treffer[:12]]
    return (f"{len(treffer)} Treffer (max 12 gezeigt):\n" + "\n".join(zeilen) +
            "\n\nMit skill_laden(name) holst du die vollstaendige Anleitung.")


def tool_skill_laden(inp):
    name = (inp.get("name") or "").strip().lower()
    if not name:
        return "Fehler: name noetig."
    if not SKILL_INDEX:
        return "Skill-Bibliothek nicht verfuegbar."
    treffer = [s for s in SKILL_INDEX if s["name"].lower() == name] or \
              [s for s in SKILL_INDEX if name in s["name"].lower()]
    if not treffer:
        return f"Skill '{name}' nicht gefunden — nutze skill_suchen."
    s = treffer[0]
    try:
        with open(s["pfad"], encoding="utf-8", errors="replace") as f:
            inhalt = f.read()
    except Exception as e:
        return f"Fehler beim Lesen: {e}"
    if len(inhalt) > SKILL_MAX_ZEICHEN:
        inhalt = inhalt[:SKILL_MAX_ZEICHEN] + "\n\n[... gekuerzt]"
    return f"=== SKILL: {s['name']} [{s['kategorie']}] ===\n{inhalt}"


def tool_persona_laden(inp):
    name = (inp.get("name") or "").strip().lower()
    if not PERSONA_INDEX:
        return "Keine Personas verfuegbar."
    if not name:
        return "Verfuegbare Personas:\n" + "\n".join(f"  - {p['name']}" for p in PERSONA_INDEX)
    treffer = [p for p in PERSONA_INDEX if name in p["name"].lower()]
    if not treffer:
        return ("Persona nicht gefunden. Verfuegbar:\n" +
                "\n".join(f"  - {p['name']}" for p in PERSONA_INDEX))
    try:
        with open(treffer[0]["pfad"], encoding="utf-8", errors="replace") as f:
            inhalt = f.read()[:SKILL_MAX_ZEICHEN]
    except Exception as e:
        return f"Fehler: {e}"
    return f"=== PERSONA: {treffer[0]['name']} ===\n{inhalt}"


SKILL_TOOLS = [
    {
        "name": "skill_suchen",
        "description": ("Durchsucht die Skill-Bibliothek (ueber 340 Fachanleitungen: Engineering, "
                        "Marketing, Finanzen, Recht/Compliance, Produkt, Research, C-Level-Beratung). "
                        "Ohne query bekommst du die Bereichsuebersicht. Nutze das, BEVOR du eine "
                        "Fachaufgabe angehst — die Anleitungen enthalten erprobte Vorgehensweisen, "
                        "Checklisten und Frameworks."),
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
    },
    {
        "name": "skill_laden",
        "description": "Laedt eine Fachanleitung vollstaendig (Name aus skill_suchen).",
        "input_schema": {"type": "object", "properties": {"name": {"type": "string"}},
                         "required": ["name"]},
    },
    {
        "name": "persona_laden",
        "description": ("Laedt eine Experten-Persona (z.B. startup-cto, finance-lead, growth-marketer, "
                        "solo-founder, product-manager, devops-engineer, content-strategist) und denkt "
                        "anschliessend aus deren Blickwinkel. Ohne name bekommst du die Liste."),
        "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}},
    },
]

SKILL_PROMPT = """- FACHWISSEN NUTZEN: Du hast eine Bibliothek mit ueber 340 erprobten Fachanleitungen und
  7 Experten-Personas. Bevor du eine fachliche Aufgabe angehst (Preisgestaltung, SEO, Sicherheits-
  audit, Vertragspruefung, Produktstrategie, Finanzplanung ...), suche mit skill_suchen nach einer
  passenden Anleitung und lade sie mit skill_laden. Das ist besser als aus dem Bauch zu antworten.
  Bei Bedarf persona_laden."""


def skill_tool_ausfuehren(name, inp):
    """Gibt das Ergebnis zurueck — oder None, wenn das Tool nicht hierher gehoert."""
    if name == "skill_suchen":
        return tool_skill_suchen(inp)
    if name == "skill_laden":
        return tool_skill_laden(inp)
    if name == "persona_laden":
        return tool_persona_laden(inp)
    return None
