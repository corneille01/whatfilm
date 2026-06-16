"""
core/redis_client.py — Client Redis async partagé pour le cache serveur.
Tout est tolérant aux pannes : si Redis tombe, l'app continue (juste sans cache).
"""
import os
import json
import redis.asyncio as redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

_client: redis.Redis | None = None


def get_redis() -> redis.Redis | None:
    global _client
    if _client is None:
        try:
            _client = redis.from_url(
                REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
                health_check_interval=30,
            )
        except Exception as e:
            print(f"⚠️ Redis init KO: {e}", flush=True)
            return None
    return _client


async def cache_get(key: str):
    """Retourne l'objet déjà désérialisé, ou None."""
    r = get_redis()
    if not r:
        return None
    try:
        raw = await r.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None  # Redis down → on fait comme s'il n'y avait pas de cache


async def cache_set(key: str, value, ttl: int | None = None):
    """Stocke un objet JSON-sérialisable. ttl en secondes (None = permanent)."""
    r = get_redis()
    if not r:
        return
    try:
        payload = json.dumps(value, ensure_ascii=False)
        if ttl:
            await r.set(key, payload, ex=ttl)
        else:
            await r.set(key, payload)
    except Exception:
        pass  # échec silencieux, on ne casse jamais la requête