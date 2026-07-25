#!/usr/bin/env python3
"""Direkter Draht zum Immo-Bot: docker exec -it jarvis-immo python cli.py"""
import json, os, sys, uuid
import redis

r = redis.Redis(host=os.getenv("REDIS_HOST", "redis"),
                port=int(os.getenv("REDIS_PORT", "6379")), decode_responses=True)
print("IMMO-BOT CLI — 'exit' zum Beenden. Beispiele: 'scan', URL einwerfen, 'was war mein Favorit?'")
while True:
    try:
        text = input("Du: ").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if not text:
        continue
    if text.lower() in ("exit", "quit"):
        break
    req = str(uuid.uuid4())
    r.rpush("bot:immo:inbox", json.dumps({"id": req, "text": text}, ensure_ascii=False))
    resp = r.blpop(f"bot:immo:reply:{req}", timeout=300)
    print("\nImmo:", resp[1] if resp else "(Timeout)", "\n")
