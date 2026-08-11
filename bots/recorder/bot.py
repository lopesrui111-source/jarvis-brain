# -*- coding: utf-8 -*-
"""
JARVIS Aufnahme-Bot (Recorder)
- Queue: bot:recorder:inbox / bot:recorder:reply:<id>
- Nimmt buroflow.de auf: oeffentliche Seiten ohne Login, Dashboard mit Login.
- Ersetzt vor jedem Screenshot ALLE echten Namen/Zahlen durch Fake-Werte (DSGVO).
- Legt Screenshots/Recordings im Vault ab (vault/recordings/).

Steuerung per Text-Auftrag, z.B.:
  "nimm die landing page auf"
  "nimm das dashboard auf"          -> Login + Hauptansichten
  "nimm mahnflow auf"
  "recording dashboard uebersicht"  -> bewegtes Video (webm) statt Standbild

Der Bot entscheidet selbst, welche Seiten sinnvoll sind, wenn der Auftrag vage ist.
"""
import os
import re
import sys
import csv
import json
import time
import uuid
import redis
import datetime as dt

# ── Konfiguration ────────────────────────────────────────────────
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

INBOX_KEY = "bot:recorder:inbox"
REPLY_KEY = "bot:recorder:reply:{id}"

BASE_URL   = os.getenv("BUROFLOW_BASE_URL", "https://buroflow.de")
SIGNIN_URL = os.getenv("BUROFLOW_LOGIN_URL", "https://buroflow.de/sign-in")
BF_USER    = os.getenv("BUROFLOW_USER", "")
BF_PASS    = os.getenv("BUROFLOW_PASS", "")

VAULT_DIR = "/app/vault"
OUT_DIR   = os.path.join(VAULT_DIR, "recordings")
SESSION_FILE = os.path.join(VAULT_DIR, "buroflow_session.json")

# Aufnahme-Groesse: Full-HD, gut fuers Video
VIEWPORT = {"width": 1920, "height": 1080}
VIEWPORT_HOCH = {"width": 1080, "height": 1920}  # fuer TikTok/Reels
# Desktop-Kontext erzwingen (sonst rendert die Seite mobil)
DESKTOP_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
CTX_ARGS = dict(viewport=VIEWPORT, screen=VIEWPORT, device_scale_factor=3,
                is_mobile=False, has_touch=False, user_agent=DESKTOP_UA,
                locale="de-DE")

# Wunsch-Betraege fuers aktuelle Video (leer = Zufallszahlen wie bisher)
AKTUELLE_ZAHLEN = []
# Kennzahl-Kacheln nach Label (z.B. {"bezahlt": 12, "kunden": 47})
AKTUELLE_KACHELN = {}

# ── Fake-Daten: echte Werte werden im DOM ueberschrieben ─────────
# Namen (echte Kundennamen -> Fake). Wird als Textersetzung angewandt.
FAKE_NAMEN = [
    "Max Mustermann", "Erika Musterfrau", "Thomas Beispiel", "Julia Schmidt",
    "Michael Wagner", "Sandra Hoffmann", "Andreas Becker", "Nicole Fischer",
    "Stefan Weber", "Laura Meyer", "Daniel Koch", "Christina Bauer",
]
FAKE_FIRMEN = [
    "Musterbau GmbH", "Beispiel & Partner", "Nordwind Handels UG",
    "Sonnenhof Dienstleistungen", "TechnikPro GmbH", "GartenGlueck e.K.",
]

# Muster fuer sensible Daten
RE_EMAIL = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
RE_IBAN  = r"\bDE\d{2}[\s\d]{18,22}\b"
RE_TEL   = r"\b(?:\+49|0)[\s\d/()-]{7,}\b"


def log(msg):
    print(f"  {msg}", flush=True)


def _antwort_senden(r, reply_q, text):
    try:
        r.rpush(reply_q, json.dumps({"text": text}, ensure_ascii=False))
        r.expire(reply_q, 300)
    except Exception as e:
        log(f"[reply] Fehler: {e}")


def arbeit_log(r, aktion, ergebnis, datei=""):
    """Schreibt einen Eintrag ins gemeinsame Arbeitsprotokoll (fuer Dashboard-Live-Strom)."""
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv("PGHOST", "postgres"),
            dbname=os.getenv("PGDATABASE", "jarvis_brain"),
            user=os.getenv("PGUSER", "jarvis"),
            password=os.getenv("PGPASSWORD", ""))
        with conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO arbeit_log (bot, aktion, ergebnis, datei) VALUES (%s,%s,%s,%s)",
                ("recorder", aktion[:80], ergebnis[:400], datei[:200]))
        conn.close()
    except Exception:
        pass


# ── Fake-Daten-Skript: wird im Browser ausgefuehrt vor dem Screenshot ──
def _fake_js():
    """Liefert JavaScript, das im Seiten-DOM echte Daten durch Fake ersetzt."""
    return """
    (function(fakeNamen, fakeFirmen, fakeZahlen, fakeKacheln) {
      // Sammelt alle Textknoten und ersetzt sensible Muster.
      var reEmail = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/g;
      var reIban  = /DE\\d{2}[\\s\\d]{18,22}/g;
      var reTel   = /(?:\\+49|0)[\\s\\d\\/()-]{7,}/g;
      var reGeld  = /\\d{1,3}(?:\\.\\d{3})*(?:,\\d{2})?\\s?(?:€|EUR)/g;

      var namenIdx = 0, firmenIdx = 0, zahlIdx = 0;
      function naechsterName(){ var n = fakeNamen[namenIdx % fakeNamen.length]; namenIdx++; return n; }
      function naechsteFirma(){ var f = fakeFirmen[firmenIdx % fakeFirmen.length]; firmenIdx++; return f; }
      function naechsterBetrag(){
        if (fakeZahlen && fakeZahlen.length > 0) {
          var z = fakeZahlen[zahlIdx % fakeZahlen.length]; zahlIdx++;
          if (/\u20ac|EUR/.test(z)) return z;
          var n = parseFloat(String(z).replace(/\\./g,'').replace(',','.'));
          if (!isNaN(n)) return n.toLocaleString('de-DE', {minimumFractionDigits: 2}) + " \u20ac";
          return z + " \u20ac";
        }
        var base = 1000 + Math.floor(Math.random()*8000);
        return base.toLocaleString('de-DE') + ",00 \u20ac";
      }

      // 1) Bekannte Namensfelder ueber data-Attribute / Klassen (heuristisch)
      var namensSel = '[class*="name"],[class*="kunde"],[class*="customer"],[class*="empfaenger"],[class*="client"],[data-name]';
      document.querySelectorAll(namensSel).forEach(function(el){
        if (el.children.length === 0 && el.textContent.trim().length > 2 && el.textContent.trim().length < 40) {
          // sieht aus wie ein Name (zwei Woerter, Grossbuchstaben)
          if (/^[A-ZÄÖÜ][a-zäöüß]+ [A-ZÄÖÜ]/.test(el.textContent.trim())) {
            el.textContent = naechsterName();
          }
        }
      });

      // 1b) Begruessung mit Vornamen: "Guten Morgen/Tag/Abend, X" / "Hallo X" / "Willkommen X"
      document.querySelectorAll('h1,h2,h3,p,span,div').forEach(function(el){
        if (el.children.length !== 0) return;
        var t = el.textContent;
        if (!t) return;
        var neu = t
          .replace(/(Guten\\s+(?:Morgen|Tag|Abend),?\\s+)([A-ZÄÖÜ][\\wäöüß-]+)/,        "$1Max")
          .replace(/(Hallo,?\\s+)([A-ZÄÖÜ][\\wäöüß-]+)/,                                  "$1Max")
          .replace(/(Willkommen(?:\\s+zurück)?,?\\s+)([A-ZÄÖÜ][\\wäöüß-]+)/,             "$1Max")
          .replace(/(Hi,?\\s+)([A-ZÄÖÜ][\\wäöüß-]+)/,                                     "$1Max");
        if (neu !== t) el.textContent = neu;
      });

      // 1c) Kennzahl-Kacheln nach LABEL setzen: {labelteil: wert}
      // HTML-Muster: <div>ZAHL</div> gefolgt von <div>Label</div> im selben Container.
      if (fakeKacheln && Object.keys(fakeKacheln).length > 0) {
        document.querySelectorAll('div,span,h1,h2,h3').forEach(function(el){
          if (el.children.length !== 0) return;
          var t = (el.textContent || '').trim();
          // grosse, fette, reine Zahl?
          if (!/^[€\s]*\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?\s*€?$/.test(t)) return;
          var st = window.getComputedStyle(el);
          if ((parseFloat(st.fontSize)||0) < 24) return;
          if ((parseInt(st.fontWeight)||0) < 600) return;
          // Label = naechstes Geschwister-Element mit Text
          var lbl = el.nextElementSibling;
          var labelText = lbl ? (lbl.textContent || '').toLowerCase() : '';
          if (!labelText) return;
          // gegen die vorgegebenen Kachel-Keys matchen
          for (var key in fakeKacheln) {
            if (labelText.indexOf(key.toLowerCase()) !== -1) {
              var wert = String(fakeKacheln[key]);
              // €-Betrag? dann deutsch formatieren, sonst reine Zahl
              if (/€|EUR/.test(t)) {
                var n = parseFloat(wert.replace(/\./g,'').replace(',','.'));
                el.textContent = isNaN(n) ? wert : n.toLocaleString('de-DE') + " \u20ac";
              } else {
                el.textContent = wert;
              }
              break;
            }
          }
        });
      }

      // 2) Alle Textknoten durchgehen und Muster ersetzen
      var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
      var nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);
      nodes.forEach(function(node){
        var t = node.nodeValue;
        if (!t || !t.trim()) return;
        t = t.replace(reEmail, "kontakt@beispiel.de");
        t = t.replace(reIban,  "DE00 0000 0000 0000 0000 00");
        t = t.replace(reTel,   "+49 000 0000000");
        // Geldbetraege: Wunsch-Zahlen (falls vorgegeben) oder Zufall
        t = t.replace(reGeld, function(m){
          return naechsterBetrag();
        });
        if (t !== node.nodeValue) node.nodeValue = t;
      });

      // 3) Eingabefelder mit echten Werten leeren/faken
      document.querySelectorAll('input[type="email"]').forEach(function(i){ if(i.value) i.value = "kontakt@beispiel.de"; });
      document.querySelectorAll('input[type="tel"]').forEach(function(i){ if(i.value) i.value = "+49 000 0000000"; });

      return true;
    })
    """


def _apply_fake(page):
    """Fuehrt das Fake-Skript auf der aktuellen Seite aus."""
    try:
        # Argumente sauber uebergeben statt in den JS-String zu formatieren
        # (der JS-Code enthaelt % und ] -> %-Formatting wuerde crashen).
        page.evaluate(
            "(args) => (" + _fake_js() + ")(args[0], args[1], args[2], args[3])",
            [FAKE_NAMEN, FAKE_FIRMEN, AKTUELLE_ZAHLEN, AKTUELLE_KACHELN])
        page.wait_for_timeout(300)
    except Exception as e:
        log(f"[fake] Warnung: {e}")


# ── Login ────────────────────────────────────────────────────────
def _login(page):
    """Loggt ein. Bei vorhandener Session-Datei ist man schon eingeloggt."""
    if os.path.exists(SESSION_FILE):
        # Session-Cookies sind im Context geladen -> pruefen ob Dashboard erreichbar
        try:
            page.goto(BASE_URL + "/dashboard", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)
            if "sign-in" not in page.url:
                log(f"[login] via Session eingeloggt -> {page.url}")
                return True
            log("[login] Session abgelaufen — bitte neu exportieren")
        except Exception as e:
            log(f"[login] Session-Check Fehler: {e}")
        return False
    if not BF_USER or not BF_PASS:
        log("[login] keine Session und BUROFLOW_USER/PASS fehlen")
        return False
    try:
        page.goto(SIGNIN_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1500)
        # buroflow.de: input[type=email], input[type=password], Button "Anmelden"
        page.fill('input[type="email"]', BF_USER, timeout=10000)
        page.fill('input[type="password"]', BF_PASS, timeout=8000)
        # Nur den E-Mail/Passwort-Anmelden-Button klicken, NICHT "Mit Google anmelden"
        try:
            page.click('button:has-text("Anmelden"):not(:has-text("Google"))', timeout=4000)
        except Exception:
            # Fallback: Enter im Passwortfeld
            page.focus('input[type="password"]')
            page.keyboard.press("Enter")
        page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_timeout(2500)
        # Erfolg pruefen: nicht mehr auf /sign-in
        if "sign-in" in page.url or "login" in page.url.lower():
            log(f"[login] steckt noch auf {page.url}")
            return False
        log(f"[login] erfolgreich -> {page.url}")
        return True
    except Exception as e:
        log(f"[login] Fehler: {e}")
        return False


# ── Aufnahme einer Seite ─────────────────────────────────────────
def _screenshot(page, url, name, fake=True, full_page=False):
    """Oeffnet URL, faked Daten, macht Screenshot. Gibt Dateipfad zurueck."""
    page.goto(url, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(1500)
    # tatsaechliche Fenster-/Render-Breite loggen (Diagnose)
    try:
        iw = page.evaluate("window.innerWidth")
        dw = page.evaluate("document.documentElement.clientWidth")
        log(f"[maße] innerWidth={iw} clientWidth={dw} viewport={page.viewport_size}")
    except Exception:
        pass
    if fake:
        _apply_fake(page)
    os.makedirs(OUT_DIR, exist_ok=True)
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    pfad = os.path.join(OUT_DIR, f"{ts}_{name}.png")
    page.screenshot(path=pfad, full_page=full_page)
    log(f"[shot] {name} -> {pfad}")
    return pfad


# ── Seiten-Kataloge ──────────────────────────────────────────────
OEFFENTLICHE_SEITEN = {
    "landing":      (BASE_URL + "/",               "landing"),
    "tools":        (BASE_URL + "/tools",          "tools"),
    "mahnflow":     (BASE_URL + "/tools/mahnflow",     "tool_mahnflow"),
    "mailflow":     (BASE_URL + "/tools/mailflow",     "tool_mailflow"),
    "angebotsflow": (BASE_URL + "/tools/angebotsflow", "tool_angebotsflow"),
    "erechnungsflow": (BASE_URL + "/tools/erechnungsflow", "tool_erechnungsflow"),
    "pricing":      (BASE_URL + "/pricing",         "pricing"),
}

# Dashboard-Ansichten (nach Login). Pfade heuristisch — der Bot probiert sie.
DASHBOARD_SEITEN = {
    "uebersicht":  (BASE_URL + "/dashboard",              "dash_uebersicht"),
    "mahnflow":    (BASE_URL + "/dashboard/mahnflow",     "dash_mahnflow"),
    "mailflow":    (BASE_URL + "/dashboard/mailflow",     "dash_mailflow"),
    "angebotsflow":(BASE_URL + "/dashboard/angebotsflow", "dash_angebotsflow"),
    "erechnung":   (BASE_URL + "/dashboard/erechnungsflow","dash_erechnungsflow"),
}


def nimm_oeffentlich(page, welche=None):
    """Nimmt oeffentliche Seiten auf (kein Login, kein Fake noetig)."""
    ergebnisse = []
    ziel = OEFFENTLICHE_SEITEN if not welche else {k: v for k, v in OEFFENTLICHE_SEITEN.items() if k in welche}
    for key, (url, name) in ziel.items():
        try:
            p = _screenshot(page, url, name, fake=False)
            ergebnisse.append((name, p))
        except Exception as e:
            log(f"[shot] {key} fehlgeschlagen: {e}")
    return ergebnisse


def nimm_dashboard(page, welche=None):
    """Nimmt Dashboard-Ansichten auf (Login noetig, Fake-Daten an)."""
    ergebnisse = []
    ziel = DASHBOARD_SEITEN if not welche else {k: v for k, v in DASHBOARD_SEITEN.items() if k in welche}
    for key, (url, name) in ziel.items():
        try:
            p = _screenshot(page, url, name, fake=True)
            ergebnisse.append((name, p))
        except Exception as e:
            log(f"[shot] {key} fehlgeschlagen: {e}")
    return ergebnisse


def recording_dashboard(context, page, name="dash_walk"):
    """Bewegtes Recording: klickt durch die Dashboard-Tabs, nimmt als Video auf."""
    # Video wird ueber den BrowserContext aufgezeichnet (record_video_dir).
    os.makedirs(OUT_DIR, exist_ok=True)
    page.goto(BASE_URL + "/dashboard", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(1500)
    _apply_fake(page)
    # Durch die Tabs klicken, jeweils kurz warten (ergibt eine fluessige Tour)
    for key, (url, _n) in DASHBOARD_SEITEN.items():
        try:
            page.goto(url, wait_until="networkidle", timeout=20000)
            page.wait_for_timeout(1200)
            _apply_fake(page)
            page.wait_for_timeout(1500)
        except Exception:
            continue
    # Video wird beim context.close() gespeichert
    return True


# ── Auftrags-Interpretation ──────────────────────────────────────
def interpretiere(text):
    """Entscheidet aus dem Auftrag, was aufgenommen wird.
    Rueckgabe: dict mit modus ('oeffentlich'|'dashboard'|'recording'|'alles'), welche (Liste|None)."""
    t = text.lower()
    welche = []
    for key in ["landing", "tools", "mahnflow", "mailflow", "angebotsflow",
                "erechnungsflow", "erechnung", "pricing", "uebersicht", "übersicht"]:
        if key in t:
            welche.append(key.replace("übersicht", "uebersicht").replace("erechnungsflow", "erechnung"))
    if "recording" in t or "video" in t or "tour" in t or "bewegt" in t:
        return {"modus": "recording", "welche": welche or None}
    if "dashboard" in t or "eingeloggt" in t or "app" in t:
        return {"modus": "dashboard", "welche": welche or None}
    if "landing" in t or "oeffentlich" in t or "öffentlich" in t or "tool" in t or "pricing" in t:
        return {"modus": "oeffentlich", "welche": welche or None}
    if "alles" in t or "komplett" in t:
        return {"modus": "alles", "welche": None}
    # Default: oeffentliche Seiten (sicher, kein Login noetig)
    return {"modus": "oeffentlich", "welche": welche or None}


# ── Hauptverarbeitung eines Auftrags ─────────────────────────────
def bearbeite(r, text, zahlen=None, welche_override=None, kacheln=None, fmt="desktop"):
    from playwright.sync_api import sync_playwright
    global AKTUELLE_ZAHLEN, AKTUELLE_KACHELN
    AKTUELLE_ZAHLEN = [str(z) for z in (zahlen or [])]
    AKTUELLE_KACHELN = dict(kacheln or {})
    plan = interpretiere(text)
    modus = plan["modus"]
    welche = welche_override or plan["welche"]
    # Viewport nach Format waehlen (hoch = TikTok/Reels)
    vp = VIEWPORT_HOCH if fmt in ("hoch", "hochformat", "tiktok", "vertical") else VIEWPORT
    ctx_args = dict(CTX_ARGS)
    ctx_args["viewport"] = vp
    ctx_args["screen"] = vp
    log(f"[plan] modus={modus} welche={welche} zahlen={len(AKTUELLE_ZAHLEN)} format={fmt}")

    zusammenfassung = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])

        if modus == "recording":
            _cargs = dict(ctx_args)
            if os.path.exists(SESSION_FILE):
                _cargs["storage_state"] = SESSION_FILE
            context = browser.new_context(
                record_video_dir=OUT_DIR, record_video_size=vp, **_cargs)
            page = context.new_page()
            if not _login(page):
                context.close(); browser.close()
                return "Login fehlgeschlagen — pruefe BUROFLOW_USER/PASS in .env."
            recording_dashboard(context, page, "dash_walk")
            context.close()  # speichert das Video
            browser.close()
            # Video-Datei finden (Playwright vergibt zufaelligen Namen)
            vids = [f for f in os.listdir(OUT_DIR) if f.endswith(".webm")]
            vids.sort(key=lambda f: os.path.getmtime(os.path.join(OUT_DIR, f)))
            neu = vids[-1] if vids else None
            if neu:
                ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
                ziel = f"{ts}_dash_walk.webm"
                os.rename(os.path.join(OUT_DIR, neu), os.path.join(OUT_DIR, ziel))
                arbeit_log(r, "Dashboard-Recording", "Bewegte Tour aufgenommen", f"recordings/{ziel}")
                return f"Recording fertig: vault/recordings/{ziel}\n(bewegte Dashboard-Tour, Fake-Daten aktiv)"
            return "Recording lief, aber keine Video-Datei gefunden."

        # Screenshot-Modi
        _cargs2 = dict(ctx_args)
        if os.path.exists(SESSION_FILE):
            _cargs2["storage_state"] = SESSION_FILE
        context = browser.new_context(**_cargs2)
        page = context.new_page()

        if modus in ("oeffentlich", "alles"):
            res = nimm_oeffentlich(page, welche)
            zusammenfassung += res

        if modus in ("dashboard", "alles"):
            if _login(page):
                res = nimm_dashboard(page, welche)
                zusammenfassung += res
            else:
                zusammenfassung.append(("LOGIN", "fehlgeschlagen — .env pruefen"))

        context.close()
        browser.close()

    if not zusammenfassung:
        return "Nichts aufgenommen. Sag z.B. 'nimm landing page auf' oder 'nimm dashboard auf'."

    zeilen = [f"- {name}: vault/recordings/{os.path.basename(p)}" if p.endswith(".png") else f"- {name}: {p}"
              for name, p in zusammenfassung]
    for name, p in zusammenfassung:
        if p.endswith(".png"):
            arbeit_log(r, "Seite aufgenommen", name, f"recordings/{os.path.basename(p)}")
    return "Aufnahmen fertig (Fake-Daten aktiv wo noetig):\n" + "\n".join(zeilen)


def main():
    print("=" * 58, flush=True)
    print("  AUFNAHME-BOT (Recorder) — Playwright fuer buroflow.de", flush=True)
    print(f"  Queue: {INBOX_KEY}", flush=True)
    print(f"  Login: {'konfiguriert' if BF_USER and BF_PASS else 'FEHLT (BUROFLOW_USER/PASS)'}", flush=True)
    print(f"  Ausgabe: {OUT_DIR}", flush=True)
    print("=" * 58, flush=True)

    r = None
    for _ in range(30):
        try:
            r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT,
                            decode_responses=True, socket_keepalive=True,
                            health_check_interval=20, socket_timeout=30)
            r.ping()
            log("[redis] verbunden")
            break
        except Exception:
            time.sleep(2)
    if r is None:
        sys.exit(1)
    log("Recorder bereit.\n")

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
            zahlen = msg.get("zahlen") or []   # optionale Wunsch-Betraege fuers Video
            welche = msg.get("welche") or None  # optional: nur bestimmte Seiten, z.B. ["uebersicht"]
            kacheln = msg.get("kacheln") or {}  # optional: Kennzahl-Kacheln nach Label
            fmt = msg.get("format") or "desktop"  # "desktop" oder "hoch" (TikTok)
            reply_q = REPLY_KEY.format(id=req_id)
            if not text:
                _antwort_senden(r, reply_q, "Leere Anfrage. Sag z.B. 'nimm dashboard auf'.")
                continue
            log(f"Auftrag: {text[:80]}")
            try:
                antwort = bearbeite(r, text, zahlen, welche, kacheln, fmt)
            except Exception as e:
                antwort = f"Fehler bei der Aufnahme: {type(e).__name__}: {e}"
                log(f"[bearbeite] {antwort}")
            _antwort_senden(r, reply_q, antwort)
        except Exception as e:
            log(f"[loop] {e}")
            time.sleep(3)


if __name__ == "__main__":
    main()
