# storage/cache_engine/redis_client.py

from typing import Optional

import redis

from config.config import REDIS_URL


# storage/cache_engine/redis_client.py — remplace la fonction get_redis

_client: Optional[redis.Redis] = None
_last_attempt: float = 0
_RETRY_INTERVAL = 30  # retente toutes les 30s après échec

def get_redis() -> Optional[redis.Redis]:
    global _client, _available, _last_attempt
    
    if _available and _client is not None:
        return _client
    
    # Ne retente pas trop souvent
    now = __import__("time").time()
    if not _available and (now - _last_attempt) < _RETRY_INTERVAL:
        return None
    
    _last_attempt = now
    
    if not REDIS_URL:
        return None
    
    try:
        _client = redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            retry_on_timeout=False,
        )
        _client.ping()
        _available = True
        print("✅ Redis connecté", flush=True)
        return _client
    except Exception as e:
        _client = None
        _available = False
        print(f"⚠️ Redis indisponible → fallback RAM ({e})", flush=True)
        return None

def redis_is_available() -> bool:
    return get_redis() is not None