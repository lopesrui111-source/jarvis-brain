#!/usr/bin/env python3
"""CLI fuer den Bueroflow-CEO."""
import os, sys, json, uuid
import redis

r = redis.Redis(host=os.getenv("REDIS_HOST", "redis"),
                port=int(os.getenv("REDIS_PORT", "6379")), decode_responses=True)

print("=" * 50)
print("  BUEROFLOW-CEO CLI — 'exit' zum Beenden")
print("=" * 50)
while True:
    try:
        text = input("\nDu: ").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if not text:
        continue
    if text.lower() in ("exit", "quit"):
        print("Tschau. (CEO laeuft weiter)")
        break
    req_id = str(uuid.uuid4())
    r.rpush("bot:ceo:inbox", json.dumps({"id": req_id, "text": text}, ensure_ascii=False))
    resp = r.blpop(f"bot:ceo:reply:{req_id}", timeout=180)
    print(f"\nCEO: {resp[1] if resp else '(Timeout — laeuft der CEO-Container?)'}")
