# storage/cache_engine/redis_client.py

from typing import Optional
import time
import redis
from config.config import REDIS_URL

_client: Optional[redis.Redis] = None
_available: bool = False
_last_attempt: float = 0.0
_RETRY_INTERVAL: int = 30


def get_redis() -> Optional[redis.Redis]:
    global _client, _available, _last_attempt

    # Si connexion active, on vérifie qu'elle est toujours vivante
    if _available and _client is not None:
        try:
            _client.ping()
            return _client
        except Exception:
            # Connexion morte → on remet à zéro
            _client = None
            _available = False
            print("⚠️ Redis connexion perdue → reconnexion...", flush=True)

    # Trop tôt pour retenter
    now = time.time()
    if (now - _last_attempt) < _RETRY_INTERVAL:
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
    return _available