#!/usr/bin/env python3
"""Direkter Draht zum SEO-Bot: docker exec -it jarvis-seo python cli.py"""
import json, os, uuid
import redis

r = redis.Redis(host=os.getenv("REDIS_HOST", "redis"),
                port=int(os.getenv("REDIS_PORT", "6379")), decode_responses=True)
print("SEO/Q&A-BOT CLI — 'exit' beendet. Beispiele: 'recherche', 'nur gutefrage, ohne entwuerfe', URL einwerfen")
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
    r.rpush("bot:seo:inbox", json.dumps({"id": req, "text": text}, ensure_ascii=False))
    resp = r.blpop(f"bot:seo:reply:{req}", timeout=600)
    print("\nSEO:", resp[1] if resp else "(Timeout)", "\n")
