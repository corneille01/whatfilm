# storage/cache_engine/lock_manager.py

import secrets
from typing import Optional

from .redis_client import get_redis
from .ttl import TTL_LOCK


_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


def acquire_lock(key: str, ttl: int = TTL_LOCK) -> Optional[str]:
    """
    Essaie de créer un verrou Redis.

    Retourne un token si le verrou est obtenu.
    Retourne None si Redis est indisponible ou si le verrou existe déjà.
    """
    redis_client = get_redis()

    if not redis_client:
        return None

    token = secrets.token_hex(16)
    lock_key = "lock:" + key

    try:
        acquired = redis_client.set(
            lock_key,
            token,
            nx=True,
            ex=ttl,
        )

        if acquired:
            return token

        return None

    except Exception as e:
        print(f"⚠️ Redis lock error: {e}", flush=True)
        return None


def release_lock(key: str, token: str) -> bool:
    """
    Libère le verrou uniquement si le token correspond.
    Cela évite de supprimer le lock d'un autre worker.
    """
    redis_client = get_redis()

    if not redis_client:
        return False

    lock_key = "lock:" + key

    try:
        result = redis_client.eval(
            _RELEASE_SCRIPT,
            1,
            lock_key,
            token,
        )

        return result == 1

    except Exception as e:
        print(f"⚠️ Redis unlock error: {e}", flush=True)
        return False