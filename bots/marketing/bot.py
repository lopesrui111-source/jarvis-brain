#!/usr/bin/env python3
"""
MARKETING-BOT — Arbeiter unter dem Bueroflow-CEO
- Queue: bot:marketing:inbox / bot:marketing:reply:<id>
- Skill-Bibliothek: /app/skills/<name>/SKILL.md (marketingskills-Repo),
  Index im System-Prompt, voller Skill wird per Tool bei Bedarf geladen
- Creatives: render_creative (HTML/CSS -> PNG via Chromium, pixelgenauer Text/Brand)
- Illustrationen: MuAPI (api.muapi.ai) — nur fuer Bilder OHNE Text
- Gemeinsames Langzeitgedaechtnis mit JARVIS + CEO (pgvector)
"""

import os
import re
import sys
import json
import time
import uuid
import threading
from datetime import datetime

import redis
import requests
import psycopg2
import psycopg2.extras
from anthropic import Anthropic
from openai import OpenAI

BOT_NAME = "marketing"

CLAUDE_KEY = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY", "")
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
MUAPI_KEY  = os.getenv("MUAPI_KEY", "")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
PG_HOST = os.getenv("POSTGRES_HOST", "postgres")
PG_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
PG_USER = os.getenv("POSTGRES_USER", "jarvis")
PG_PASS = os.getenv("POSTGRES_PASSWORD", "")
PG_DB   = os.getenv("POSTGRES_DB", "jarvis_brain")

MODEL       = os.getenv("ORCHESTRATOR_MODEL", "claude-sonnet-4-6")
EMBED_MODEL = "text-embedding-3-small"
MAX_HISTORY = 24
MAX_TOKENS  = 3000
MAX_TOOL_ROUNDS = 8
VAULT_DIR  = "/app/vault"
SKILLS_DIR = "/app/skills"

MUAPI_BASE = "https://api.muapi.ai/api/v1"
DEFAULT_IMAGE_MODEL = os.getenv("MUAPI_IMAGE_MODEL", "flux-dev-image")

INBOX_KEY   = "bot:marketing:inbox"
HISTORY_KEY = "bot:marketing:history"
REPLY_KEY   = "bot:marketing:reply:{id}"

if not CLAUDE_KEY:
    print("FEHLER: ANTHROPIC_API_KEY fehlt", flush=True)
    sys.exit(1)


# ── SKILL-BIBLIOTHEK ─────────────────────────────────────────
def build_skill_index():
    """Scannt /app/skills und baut einen kompakten Index aus den Frontmatter-Daten."""
    index = {}
    if not os.path.isdir(SKILLS_DIR):
        return index
    for name in sorted(os.listdir(SKILLS_DIR)):
        path = os.path.join(SKILLS_DIR, name, "SKILL.md")
        if not os.path.isfile(path):
            continue
        desc = ""
        try:
            with open(path, encoding="utf-8") as f:
                head = f.read(3000)
            m = re.search(r'description:\s*"?(.*?)("|\n[a-z_]+:|\n---)', head, re.S)
            if m:
                desc = " ".join(m.group(1).split())
            # Nur der erste Satz-Teil ("When the user wants ...") reicht fuer den Index
            desc = desc.split(" Also use")[0].split(" Use this")[0][:220]
        except Exception:
            pass
        index[name] = desc or "(keine Beschreibung)"
    return index


SKILL_INDEX = build_skill_index()


def tool_load_skill(inp):
    name = (inp.get("name") or "").strip().lower()
    if name not in SKILL_INDEX:
        return f"Skill '{name}' unbekannt. Verfuegbar: {', '.join(SKILL_INDEX)}"
    path = os.path.join(SKILLS_DIR, name, "SKILL.md")
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        return content[:22000]
    except Exception as e:
        return f"Fehler beim Laden: {e}"


# ── MUAPI BILDGENERIERUNG ────────────────────────────────────
def tool_generate_image(inp):
    if not MUAPI_KEY:
        return "MuAPI nicht konfiguriert — MUAPI_KEY fehlt in .env."
    prompt = (inp.get("prompt") or "").strip()
    if not prompt:
        return "Fehler: leerer Prompt."
    model = (inp.get("model") or DEFAULT_IMAGE_MODEL).strip()
    payload = {"prompt": prompt}
    for k in ("num_images", "aspect_ratio", "image_url"):
        if inp.get(k):
            payload[k] = inp[k]
    headers = {"x-api-key": MUAPI_KEY, "Content-Type": "application/json"}
    try:
        r = requests.post(f"{MUAPI_BASE}/{model}", json=payload, headers=headers, timeout=60)
        if r.status_code >= 400:
            return f"MuAPI-Fehler ({r.status_code}): {r.text[:300]}"
        data = r.json()
        req_id = data.get("request_id") or data.get("id")
        if not req_id:
            return f"Keine request_id erhalten: {str(data)[:300]}"
        # Pollen bis fertig (max 3 Minuten)
        deadline = time.time() + 180
        result = None
        while time.time() < deadline:
            rr = requests.get(f"{MUAPI_BASE}/predictions/{req_id}/result", headers=headers, timeout=30)
            if rr.status_code >= 400:
                return f"MuAPI-Poll-Fehler ({rr.status_code}): {rr.text[:300]}"
            result = rr.json()
            status = result.get("status", "")
            if status == "completed":
                break
            if status == "failed":
                return f"Generierung fehlgeschlagen: {result.get('error', 'unbekannt')}"
            time.sleep(4)
        else:
            return "Timeout: Generierung nicht fertig nach 3 Minuten."

        outputs = result.get("outputs") or []
        if not outputs:
            return f"Fertig, aber keine Outputs: {str(result)[:300]}"

        # In den Vault herunterladen
        saved = []
        adir = os.path.join(VAULT_DIR, "assets")
        os.makedirs(adir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        for i, url in enumerate(outputs[:4]):
            try:
                ext = ".png" if ".png" in url.lower() else ".jpg"
                fname = f"{stamp}_{model}_{i}{ext}"
                img = requests.get(url, timeout=60)
                with open(os.path.join(adir, fname), "wb") as f:
                    f.write(img.content)
                saved.append(f"vault/assets/{fname}")
            except Exception:
                saved.append(f"(Download fehlgeschlagen: {url})")
        lines = [f"Bild(er) generiert mit {model}:"]
        for u, s in zip(outputs, saved):
            lines.append(f"- URL: {u}\n  Lokal: {s}")
        return "\n".join(lines)
    except Exception as e:
        return f"MuAPI-Fehler: {type(e).__name__}: {e}"


# ── BRAND-ASSETS (echtes Brand-Kit einbetten) ────────────────
BRAND_DIR = "/app/brand"

def brand_assets_list():
    try:
        return sorted(f for f in os.listdir(BRAND_DIR) if not f.startswith("."))
    except Exception:
        return []


def _asset_data_uri(fname):
    import base64, mimetypes
    path = os.path.join(BRAND_DIR, os.path.basename(fname))
    if not os.path.isfile(path):
        return None
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


def apply_brand_placeholders(html):
    """{{LOGO_SVG}} -> Inline-SVG; {{ASSET:datei}} -> data-URI."""
    # Logo inline (erste .svg mit 'logo' im Namen, sonst erste .svg)
    if "{{LOGO_SVG}}" in html:
        svgs = [f for f in brand_assets_list() if f.lower().endswith(".svg")]
        logos = [f for f in svgs if "logo" in f.lower()]
        pick = (next((f for f in logos if "white" in f.lower()), None)
                or (logos[0] if logos else (svgs[0] if svgs else None)))
        inline = ""
        if pick:
            try:
                with open(os.path.join(BRAND_DIR, pick), encoding="utf-8", errors="replace") as f:
                    inline = f.read()
            except Exception:
                inline = ""
        html = html.replace("{{LOGO_SVG}}", inline)
    # Beliebige Assets als data-URI
    for m in set(re.findall(r"\{\{ASSET:([^}]+)\}\}", html)):
        uri = _asset_data_uri(m.strip())
        html = html.replace("{{ASSET:" + m + "}}", uri or "")
    return html


# ── CREATIVE-RENDERING (HTML/CSS -> PNG, pixelgenau) ─────────
def tool_render_creative(inp):
    html = (inp.get("html") or "").strip()
    if not html:
        return "Fehler: leeres HTML."
    html = apply_brand_placeholders(html)
    width  = int(inp.get("width") or 1080)
    height = int(inp.get("height") or 1080)
    width, height = max(200, min(width, 3000)), max(200, min(height, 3000))
    name = re.sub(r"[^a-zA-Z0-9_\-]", "-", (inp.get("filename") or "creative"))[:50].strip("-") or "creative"
    fname = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{name}.png"
    adir = os.path.join(VAULT_DIR, "assets")
    os.makedirs(adir, exist_ok=True)
    path = os.path.join(adir, fname)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            pg = b.new_page(viewport={"width": width, "height": height})
            pg.set_content(html, wait_until="networkidle")
            pg.screenshot(path=path)
            b.close()
        return f"Creative gerendert ({width}x{height}): vault/assets/{fname}"
    except Exception as e:
        return f"Render-Fehler: {type(e).__name__}: {e}"


# ── KOSTEN / DB / GEDAECHTNIS (wie CEO) ──────────────────────
PRICING = {
    "claude-haiku-4-5-20251001": {"in": 1.00, "out": 5.00},
    "claude-sonnet-4-5":         {"in": 3.00, "out": 15.00},
    "claude-sonnet-4-6":         {"in": 3.00, "out": 15.00},
    "claude-opus-4-8":           {"in": 15.00, "out": 75.00},
}
DEFAULT_PRICE = {"in": 3.00, "out": 15.00}


def pg_conn():
    return psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER,
                            password=PG_PASS, dbname=PG_DB, connect_timeout=5)


def track_cost(model, tok_in, tok_out):
    def _work():
        try:
            p = PRICING.get(model, DEFAULT_PRICE)
            cost = (tok_in * p["in"] + tok_out * p["out"]) / 1_000_000
            conn = pg_conn()
            with conn, conn.cursor() as cur:
                cur.execute("INSERT INTO cost_ledger (bot, model, tokens_in, tokens_out, cost_usd) "
                            "VALUES (%s, %s, %s, %s, %s)",
                            (BOT_NAME, model, tok_in, tok_out, round(cost, 6)))
            conn.close()
        except Exception as e:
            print(f"  [cost] {e}", flush=True)
    threading.Thread(target=_work, daemon=True).start()


oai = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None


def embed(text):
    if oai is None:
        return None
    try:
        return oai.embeddings.create(model=EMBED_MODEL, input=text[:8000]).data[0].embedding
    except Exception as e:
        print(f"  [embed] {e}", flush=True)
        return None


def vec_literal(v):
    return "[" + ",".join(f"{x:.7f}" for x in v) + "]"


def tool_remember(inp):
    content = (inp.get("content") or "").strip()
    project = (inp.get("project") or "buroflow").strip().lower()
    title   = (inp.get("title") or "").strip()
    if not content:
        return "Fehler: leerer Inhalt."
    v = embed(f"{title}\n{content}")
    try:
        conn = pg_conn()
        with conn, conn.cursor() as cur:
            if v is not None:
                cur.execute("INSERT INTO memory (source, project, title, content, embedding) "
                            "VALUES (%s, %s, %s, %s, %s::vector) RETURNING id",
                            (BOT_NAME, project, title, content, vec_literal(v)))
            else:
                cur.execute("INSERT INTO memory (source, project, title, content) "
                            "VALUES (%s, %s, %s, %s) RETURNING id",
                            (BOT_NAME, project, title, content))
            mid = cur.fetchone()[0]
        conn.close()
        return f"Gespeichert (#{mid}, {project}): {title}"
    except Exception as e:
        return f"Fehler beim Speichern: {e}"


def tool_recall(inp, k=5):
    query = (inp.get("query") or "").strip()
    project = (inp.get("project") or "").strip().lower()
    if not query:
        return "Fehler: leere Suchanfrage."
    v = embed(query)
    try:
        conn = pg_conn()
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if v is not None:
                sql = ("SELECT id, project, title, content, created_at, "
                       "embedding <=> %s::vector AS dist FROM memory WHERE embedding IS NOT NULL ")
                params = [vec_literal(v)]
                if project:
                    sql += "AND project = %s "
                    params.append(project)
                sql += "ORDER BY dist ASC LIMIT %s"
                params.append(k)
                cur.execute(sql, params)
            else:
                cur.execute("SELECT id, project, title, content, created_at, 0 AS dist "
                            "FROM memory ORDER BY created_at DESC LIMIT %s", (k,))
            rows = cur.fetchall()
        conn.close()
        if not rows:
            return "Keine Treffer im Gedaechtnis."
        return "\n".join(f"[#{r['id']} | {r['project']} | {r['created_at'].strftime('%d.%m.%Y')}] "
                         f"{r['title']}: {r['content']}" for r in rows)
    except Exception as e:
        return f"Fehler bei der Suche: {e}"


def tool_vault_note(inp):
    folder = (inp.get("folder") or "projects").strip().lower()
    if folder not in ("daily", "notes", "projects", "inbox", "skills"):
        folder = "projects"
    title = (inp.get("title") or "notiz").strip()
    content = (inp.get("content") or "").strip()
    if not content:
        return "Fehler: leerer Inhalt."
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "-", title.replace(" ", "-"))[:60].strip("-") or "notiz"
    fname = f"{datetime.now().strftime('%Y-%m-%d')}_{safe}.md"
    path = os.path.join(VAULT_DIR, folder, fname)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n{content}\n\n---\n*{BOT_NAME}, {datetime.now().strftime('%d.%m.%Y %H:%M')}*\n")
        return f"Notiz abgelegt: vault/{folder}/{fname}"
    except Exception as e:
        return f"Fehler beim Schreiben: {e}"


TOOLS = [
    {"name": "load_skill",
     "description": "Laedt einen Marketing-Skill (volle Anleitung) aus der Bibliothek. Immer den passenden Skill laden BEVOR du die Aufgabe bearbeitest.",
     "input_schema": {"type": "object", "properties": {
         "name": {"type": "string", "description": "Skill-Name aus dem Index, z.B. social, copywriting, ai-seo"}},
         "required": ["name"]}},
    {"name": "render_creative",
     "description": "Rendert ein Marketing-Creative aus HTML/CSS pixelgenau als PNG (headless Chromium). ERSTE WAHL fuer alle Creatives mit Text, Logo, Zahlen oder UI-Elementen — Text wird exakt gerendert, Brandfarben stimmen garantiert. Formate: 1080x1080 (Feed), 1080x1350 (Portrait), 1200x628 (LinkedIn-Link), 1080x1920 (Story). BRAND-KIT: {{LOGO_SVG}} fuegt das echte Bueroflow-Logo als Inline-SVG ein; {{ASSET:dateiname}} bettet eine Datei aus dem Brand-Ordner als data-URI ein (fuer <img src=...>).",
     "input_schema": {"type": "object", "properties": {
         "html": {"type": "string", "description": "Komplettes HTML-Dokument mit Inline-CSS. Body exakt auf width/height dimensionieren (margin:0, box-sizing:border-box)."},
         "width": {"type": "integer", "description": "Breite in px, Standard 1080"},
         "height": {"type": "integer", "description": "Hoehe in px, Standard 1080"},
         "filename": {"type": "string", "description": "Dateiname-Basis, z.B. e-rechnung-feed"}},
         "required": ["html"]}},
    {"name": "generate_image",
     "description": "Generiert KI-Bilder ueber MuAPI — NUR fuer fotografische/illustrative Motive OHNE Text (Hintergruende, Stimmungsbilder). NIEMALS fuer Creatives mit Text/Logo/Zahlen — dafuer render_creative nutzen (KI-Modelle verhunzen deutschen Text). Prompt auf Englisch.",
     "input_schema": {"type": "object", "properties": {
         "prompt": {"type": "string", "description": "Bildbeschreibung auf Englisch"},
         "model": {"type": "string", "description": f"Optional, Standard: {DEFAULT_IMAGE_MODEL}"},
         "num_images": {"type": "integer", "description": "Optional, 1-4"},
         "aspect_ratio": {"type": "string", "description": "Optional, z.B. 1:1, 16:9, 9:16"}},
         "required": ["prompt"]}},
    {"name": "remember",
     "description": "Speichert wichtige Fakten/Entscheidungen dauerhaft im gemeinsamen Gedaechtnis.",
     "input_schema": {"type": "object", "properties": {
         "content": {"type": "string"}, "project": {"type": "string", "description": "Standard: buroflow"},
         "title": {"type": "string"}}, "required": ["content", "title"]}},
    {"name": "recall",
     "description": "Durchsucht das gemeinsame Langzeitgedaechtnis (auch 'Schreibstil buroflow', Brand-Infos, CEO-Entscheidungen).",
     "input_schema": {"type": "object", "properties": {
         "query": {"type": "string"}, "project": {"type": "string"}}, "required": ["query"]}},
    {"name": "vault_note",
     "description": "Legt Content-Plaene/Entwuerfe als Markdown im Vault ab.",
     "input_schema": {"type": "object", "properties": {
         "folder": {"type": "string"}, "title": {"type": "string"}, "content": {"type": "string"}},
         "required": ["title", "content"]}},
]


def run_tool(name, inp):
    if name == "load_skill":
        return tool_load_skill(inp)
    if name == "render_creative":
        return tool_render_creative(inp)
    if name == "generate_image":
        return tool_generate_image(inp)
    if name == "remember":
        return tool_remember(inp)
    if name == "recall":
        return tool_recall(inp)
    if name == "vault_note":
        return tool_vault_note(inp)
    return f"Unbekanntes Tool: {name}"


# ── SYSTEM-PROMPT ────────────────────────────────────────────
def build_system():
    brand_files = ", ".join(brand_assets_list()) or "(keine — Brand-Ordner leer)"
    idx = "\n".join(f"- {n}: {d}" for n, d in SKILL_INDEX.items())
    return f"""Du bist der MARKETING-BOT von Bueroflow — Arbeiter unter dem Bueroflow-CEO.

PERSOENLICHKEIT:
- Du duzt. Direkt, kreativ, handwerklich sauber. Kein Marketing-Blabla ueber Marketing.
- Du LIEFERST: fertige Entwuerfe, konkrete Plaene — kein "man koennte".

BUEROFLOW-KONTEXT:
- Deutsches SaaS fuer Kleinunternehmer/Solopreneure: Mahnflow, Briefflow, Angebotsflow, E-Rechnungsflow.
- Pre-Launch auf buroflow.de: Waitlist offen, Verkauf gesperrt. Ziel: Warteliste fuellen.
- Brand: Anthrazit #1A1D24, Weiss, Gruen #5DCAA5, kursive Akzent-Woerter, radikaler Minimalismus, Anti-KI-Aesthetik.
- Tagline: "Weniger Buerokram. Mehr Feierabend." Zielgruppe: deutsche Solo-Selbststaendige, KMU.
- Kanaele: LinkedIn (Unternehmensseite), gutefrage.net + Quora (VORSICHT: nur menschlich-lockere Entwuerfe,
  Rui wurde wegen KI-Texten verwarnt — "is", "nich", "wuerd ich", keine Listen, kein Werbesprech), SEO-Blog geplant.

DEINE SKILL-BIBLIOTHEK (per load_skill laden, IMMER bevor du eine Aufgabe bearbeitest):
{idx}

ARBEITSWEISE:
1. Aufgabe verstehen -> passenden Skill laden (load_skill) -> ggf. recall (Schreibstil, Brand, fruehere Posts).
2. Entwurf/Plan erstellen nach Skill-Anleitung, angepasst auf Bueroflow und deutschen Markt.
3. CREATIVES (Social-Grafiken, Ads, Banner): IMMER render_creative (HTML/CSS) — Text pixelgenau, Umlaute korrekt, Brand exakt. NIEMALS generate_image fuer Text-Creatives (KI-Modelle verhunzen deutschen Text, falsche Logos). generate_image nur fuer textfreie Illustrationen/Hintergruende.
   ECHTES BRAND-KIT: Nutze IMMER {{LOGO_SVG}} fuer das Logo (nimmt automatisch die weisse Variante — richtig fuer dunkle Creatives; nie selbst nachbauen!). Andere Varianten gezielt per {{ASSET:dateiname}} (z.B. <img src="{{ASSET:logo_dark_transparent.png}}"> auf hellem Grund). Verfuegbare Brand-Dateien: {brand_files}
   Brand-Bauplan fuer Creatives: body margin:0 exakt auf Format; Hintergrund radial-gradient(circle at 50% 30%, #24303a 0%, #1A1D24 60%); Schrift 'Segoe UI',system-ui; Headline GROSS fett weiss (90-130px), Subline #5DCAA5 mit letter-spacing; Fliesstext #c9cdd6; Logo-Wordmark "Büroflow" oben links (B in #5DCAA5); optional CTA-Pill (Rand #5DCAA5, transparent); dezente Glow-Punkte via box-shadow. Radikal minimalistisch, viel Negativraum, KEINE Stockfoto-Optik.
4. Laengere Ergebnisse zusaetzlich als vault_note ablegen (folder: projects).
5. Wichtige Learnings/Entscheidungen via remember speichern (project: buroflow).

EISERNE REGELN:
- ALLES ist ENTWURF zur Freigabe. Du postest, sendest, veroeffentlichst NICHTS selbst.
- Deutsch fuer Content (ausser Bild-Prompts). Ruis Stil anwenden (recall "Schreibstil buroflow").
- Keine erfundenen Zahlen/Features. Wenn Info fehlt: recall, dann fragen.
- Max 2-3 Skills pro Aufgabe laden — fokussiert bleiben."""


SYSTEM = build_system()

client = Anthropic(api_key=CLAUDE_KEY)


def load_history(r):
    try:
        raw = r.get(HISTORY_KEY)
        return json.loads(raw) if raw else []
    except Exception:
        return []


def save_history(r, h):
    try:
        r.set(HISTORY_KEY, json.dumps(h[-MAX_HISTORY:], ensure_ascii=False))
    except Exception as e:
        print(f"  [history] {e}", flush=True)


def think(history, user_text):
    history.append({"role": "user", "content": user_text})
    messages = list(history)
    final_text = ""
    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS,
                                      system=SYSTEM, tools=TOOLS, messages=messages)
        try:
            track_cost(MODEL, resp.usage.input_tokens, resp.usage.output_tokens)
        except Exception:
            pass
        parts = [b.text for b in resp.content if b.type == "text"]
        if parts:
            final_text = "".join(parts).strip()
        if resp.stop_reason != "tool_use":
            break
        a_content, t_results = [], []
        for block in resp.content:
            if block.type == "text":
                a_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                a_content.append({"type": "tool_use", "id": block.id,
                                  "name": block.name, "input": block.input})
                result = run_tool(block.name, block.input or {})
                print(f"  [tool] {block.name} -> {str(result)[:90]}", flush=True)
                t_results.append({"type": "tool_result", "tool_use_id": block.id,
                                  "content": result})
        messages.append({"role": "assistant", "content": a_content})
        messages.append({"role": "user", "content": t_results})
    if not final_text:
        final_text = "..."
    history.append({"role": "assistant", "content": final_text})
    return final_text


def main():
    print("=" * 58, flush=True)
    print("  MARKETING-BOT — Arbeiter unter dem Bueroflow-CEO", flush=True)
    print(f"  Modell : {MODEL} | Queue: {INBOX_KEY}", flush=True)
    print(f"  Skills : {len(SKILL_INDEX)} geladen", flush=True)
    print(f"  MuAPI  : {'aktiv' if MUAPI_KEY else 'nicht konfiguriert (MUAPI_KEY fehlt)'}", flush=True)
    print("=" * 58, flush=True)

    r = None
    for attempt in range(30):
        try:
            r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
            r.ping()
            print("  [redis] verbunden", flush=True)
            break
        except Exception:
            time.sleep(2)
    if r is None:
        sys.exit(1)
    print("  Marketing-Bot bereit.\n", flush=True)

    while True:
        try:
            item = r.blpop(INBOX_KEY, timeout=5)
            if item is None:
                continue
            _, raw = item
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            req_id = msg.get("id", str(uuid.uuid4()))
            text = (msg.get("text") or "").strip()
            reply_q = REPLY_KEY.format(id=req_id)
            if not text:
                r.rpush(reply_q, "Leere Anfrage.")
                r.expire(reply_q, 300)
                continue
            if text.lower() in ("reset", "vergiss alles"):
                r.delete(HISTORY_KEY)
                r.rpush(reply_q, "Marketing-Kurzzeitgedaechtnis geleert.")
                r.expire(reply_q, 300)
                continue
            if text.lower() == "skills":
                r.rpush(reply_q, "Skills:\n" + "\n".join(f"- {n}" for n in SKILL_INDEX))
                r.expire(reply_q, 300)
                continue
            print(f"  Auftrag: {text[:80]}", flush=True)
            history = load_history(r)
            try:
                answer = think(history, text)
            except Exception as e:
                answer = f"Fehler: {type(e).__name__}: {e}"
                print(f"  [think] {answer}", flush=True)
            save_history(r, history)
            print(f"  Marketing: {answer[:100]}\n", flush=True)
            r.rpush(reply_q, answer)
            r.expire(reply_q, 300)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"  [loop] {type(e).__name__}: {e}", flush=True)
            time.sleep(1)


if __name__ == "__main__":
    main()
