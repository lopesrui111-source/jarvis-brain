#!/usr/bin/env python3
"""JARVIS CLI — duenner Client zum Reden mit dem 24/7-Core."""

import os
import sys
import json
import uuid

import redis

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

INBOX_KEY = "jarvis:inbox"
REPLY_KEY = "jarvis:reply:{id}"
TIMEOUT   = 90


def main():
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        r.ping()
    except Exception as e:
        print(f"Keine Redis-Verbindung: {e}")
        sys.exit(1)

    print("=" * 50)
    print("  JARVIS CLI  —  'exit' zum Beenden, 'reset' leert Gedaechtnis")
    print("=" * 50)

    while True:
        try:
            text = input("\nDu: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nTschau.")
            break

        if not text:
            continue
        if text.lower() in ("exit", "quit", "beenden"):
            print("Tschau. (Core laeuft weiter)")
            break

        req_id = str(uuid.uuid4())
        reply_q = REPLY_KEY.format(id=req_id)
        r.rpush(INBOX_KEY, json.dumps({"id": req_id, "text": text}, ensure_ascii=False))

        item = r.blpop(reply_q, timeout=TIMEOUT)
        if item is None:
            print("JARVIS: (keine Antwort — laeuft der Core? 'docker compose logs jarvis-core')")
            continue
        _, answer = item
        print(f"JARVIS: {answer}")


if __name__ == "__main__":
    main()
