"""memory_crypto.py — Verschluesselung fuer sensible Gedaechtnis-Eintraege.

WARUM: Die memory-Tabelle liegt im Klartext in Postgres. Jeder Bot mit
Datenbankzugriff kann sie lesen — auch Marketing-, SEO- und Immo-Bot, die
ihre Inhalte an externe APIs schicken. Sensible Daten (Bankverbindungen,
Zugaenge, Ausweisnummern) duerfen dort nicht offen liegen.

WIE: Eintraege koennen als 'geheim' markiert werden. Ihr Inhalt wird dann
mit Fernet (AES-128 im CBC-Modus, HMAC-authentifiziert) verschluesselt.
Den Schluessel haben nur die Bots, die ihn in ihrer Umgebung finden —
vorgesehen sind jarvis-core und jarvis-ceo.

WICHTIG: Fuer geheime Eintraege wird KEIN Embedding gespeichert. Sonst
koennte ein anderer Bot per Aehnlichkeitssuche zumindest erkennen, DASS
ein Eintrag zu 'Bankdaten' existiert — auch ohne den Inhalt zu sehen.

Einrichtung:
    1. Schluessel erzeugen:  python3 memory_crypto.py --neuer-schluessel
    2. In die .env eintragen: MEMORY_KEY=<ausgabe>
    3. Nur bei jarvis-core und jarvis-ceo in docker-compose.yml durchreichen
"""

import os
import base64

_PREFIX = "enc:v1:"          # kennzeichnet verschluesselte Inhalte


def _fernet():
    """Liefert das Fernet-Objekt oder None, wenn kein Schluessel gesetzt ist."""
    key = os.getenv("MEMORY_KEY", "").strip()
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
        return Fernet(key.encode())
    except Exception:
        return None


def hat_schluessel():
    """True, wenn dieser Bot geheime Eintraege lesen/schreiben darf."""
    return _fernet() is not None


def verschluesseln(text):
    """Verschluesselt einen Text. Ohne Schluessel wird None zurueckgegeben —
    der Aufrufer MUSS das behandeln und darf nichts im Klartext speichern."""
    f = _fernet()
    if f is None:
        return None
    return _PREFIX + f.encrypt(text.encode("utf-8")).decode("ascii")


def ist_verschluesselt(text):
    return isinstance(text, str) and text.startswith(_PREFIX)


def entschluesseln(text):
    """Entschluesselt einen Eintrag. Ohne Schluessel oder bei Fehler wird ein
    Platzhalter geliefert — nie der Rohwert."""
    if not ist_verschluesselt(text):
        return text
    f = _fernet()
    if f is None:
        return "[verschluesselt — dieser Bot hat keinen Zugriff]"
    try:
        return f.decrypt(text[len(_PREFIX):].encode("ascii")).decode("utf-8")
    except Exception:
        return "[verschluesselt — Entschluesselung fehlgeschlagen]"


def lesbar_machen(text):
    """Bequemer Wrapper fuer die Anzeige: entschluesselt wenn moeglich,
    sonst Platzhalter."""
    return entschluesseln(text) if ist_verschluesselt(text) else text


if __name__ == "__main__":
    import sys
    if "--neuer-schluessel" in sys.argv:
        from cryptography.fernet import Fernet
        print(Fernet.generate_key().decode())
    else:
        print(__doc__)
