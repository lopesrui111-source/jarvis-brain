# -*- coding: utf-8 -*-
"""
Higgsfield-API-Client fuer das JARVIS Studio-Team.
- Text -> Bild (fuer Vibe-Motion-Startframes)
- Bild -> Video (animiert das Bild zu einem Clip)
- Asynchron: Request absenden, Status pollen bis 'completed'

WICHTIG: Gibt nur URLs zurueck, laedt Medien NIE in den Kontext (Kostenfalle).
Auth ueber HIGGSFIELD_KEY + HIGGSFIELD_SECRET aus der Umgebung (.env).
"""
import os
import time
import json
import requests

BASE = "https://platform.higgsfield.ai"
KEY = os.getenv("HIGGSFIELD_KEY", "")
SECRET = os.getenv("HIGGSFIELD_SECRET", "")

# Standard-Modelle (ueber .env ueberschreibbar)
BILD_MODELL  = os.getenv("HF_BILD_MODELL", "higgsfield-ai/soul/standard")
VIDEO_MODELL = os.getenv("HF_VIDEO_MODELL", "kling-video/v2.1/pro/image-to-video")

POLL_INTERVALL = 6      # Sekunden zwischen Status-Abfragen
POLL_MAX = 60           # max. Versuche (~6 Min)


def _headers():
    return {
        "Authorization": f"Key {KEY}:{SECRET}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def verfuegbar():
    """True, wenn API-Zugangsdaten gesetzt sind."""
    return bool(KEY and SECRET)


def _absenden(model_id, payload):
    """Sendet einen Generierungs-Request, gibt request_id + status_url zurueck."""
    url = f"{BASE}/{model_id}"
    r = requests.post(url, headers=_headers(), data=json.dumps(payload), timeout=30)
    if r.status_code not in (200, 201, 202):
        raise RuntimeError(f"Higgsfield {r.status_code}: {r.text[:200]}")
    d = r.json()
    return d.get("request_id"), d.get("status_url")


def _warten(request_id, status_url=None):
    """Pollt den Status bis completed/failed. Gibt das Ergebnis-JSON zurueck."""
    url = status_url or f"{BASE}/requests/{request_id}/status"
    for _ in range(POLL_MAX):
        r = requests.get(url, headers=_headers(), timeout=30)
        if r.status_code != 200:
            time.sleep(POLL_INTERVALL); continue
        d = r.json()
        st = d.get("status")
        if st == "completed":
            return d
        if st in ("failed", "nsfw"):
            raise RuntimeError(f"Generierung {st}: {d}")
        time.sleep(POLL_INTERVALL)
    raise TimeoutError(f"Timeout bei request {request_id}")


def bild_erzeugen(prompt, aspect_ratio="16:9", resolution="720p", modell=None):
    """Text -> Bild. Gibt die Bild-URL zurueck."""
    if not verfuegbar():
        raise RuntimeError("HIGGSFIELD_KEY/SECRET fehlen in .env")
    model_id = modell or BILD_MODELL
    rid, surl = _absenden(model_id, {
        "prompt": prompt, "aspect_ratio": aspect_ratio, "resolution": resolution})
    d = _warten(rid, surl)
    imgs = d.get("images") or []
    if not imgs:
        raise RuntimeError(f"Kein Bild im Ergebnis: {d}")
    return imgs[0].get("url")


def video_erzeugen(image_url, prompt, duration=5, modell=None):
    """Bild -> Video. Gibt die Video-URL zurueck."""
    if not verfuegbar():
        raise RuntimeError("HIGGSFIELD_KEY/SECRET fehlen in .env")
    model_id = modell or VIDEO_MODELL
    payload = {"image_url": image_url, "prompt": prompt}
    if duration:
        payload["duration"] = duration
    rid, surl = _absenden(model_id, payload)
    d = _warten(rid, surl)
    vid = d.get("video") or {}
    if not vid.get("url"):
        raise RuntimeError(f"Kein Video im Ergebnis: {d}")
    return vid.get("url")


def clip_aus_prompt(bild_prompt, motion_prompt, aspect_ratio="16:9",
                    duration=5, bild_modell=None, video_modell=None):
    """Kompletter Vibe-Clip: erst Bild aus Text, dann Bild animieren.
    Gibt dict mit bild_url + video_url zurueck."""
    b = bild_erzeugen(bild_prompt, aspect_ratio=aspect_ratio, modell=bild_modell)
    v = video_erzeugen(b, motion_prompt, duration=duration, modell=video_modell)
    return {"bild_url": b, "video_url": v}


if __name__ == "__main__":
    # Schneller Selbsttest (nur wenn Keys gesetzt)
    if not verfuegbar():
        print("HIGGSFIELD_KEY/SECRET fehlen — .env pruefen")
    else:
        print("Test: Bild erzeugen ...")
        try:
            url = bild_erzeugen("abstract flowing blue liquid motion, dark background, premium tech aesthetic")
            print("Bild-URL:", url)
        except Exception as e:
            print("Fehler:", e)
