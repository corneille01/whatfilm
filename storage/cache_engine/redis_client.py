# storage/cache_engine/redis_client.py

from typing import Optional

import redis

from config.config import REDIS_URL


_client: Optional[redis.Redis] = None
_available = False


def get_redis() -> Optional[redis.Redis]:
    global _client, _available

    if _available and _client is not None:
        return _client

    if not REDIS_URL:
        print("ℹ️ REDIS_URL absent → cache RAM uniquement", flush=True)
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