#!/usr/bin/env python3
"""CLI fuer den Marketing-Bot."""
import os, json, uuid
import redis

r = redis.Redis(host=os.getenv("REDIS_HOST", "redis"),
                port=int(os.getenv("REDIS_PORT", "6379")), decode_responses=True)

print("=" * 50)
print("  MARKETING-BOT CLI — 'exit' beendet, 'skills' listet Skills")
print("=" * 50)
while True:
    try:
        text = input("\nDu: ").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if not text:
        continue
    if text.lower() in ("exit", "quit"):
        print("Tschau. (Bot laeuft weiter)")
        break
    req_id = str(uuid.uuid4())
    r.rpush("bot:marketing:inbox", json.dumps({"id": req_id, "text": text}, ensure_ascii=False))
    resp = r.blpop(f"bot:marketing:reply:{req_id}", timeout=300)
    print(f"\nMarketing: {resp[1] if resp else '(Timeout — laeuft der Marketing-Container?)'}")
