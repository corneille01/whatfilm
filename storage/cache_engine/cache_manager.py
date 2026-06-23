# storage/cache_engine/cache_manager.py

import json
import time
from typing import Any, Optional

from .redis_client import get_redis, redis_is_available


EXPIRES_NEVER = float("inf")

_ram: dict[str, dict[str, Any]] = {}

_stats = {
    "redis_hits": 0,
    "ram_hits": 0,
    "misses": 0,
    "sets": 0,
    "deletes": 0,
}


def cache_get(key: str) -> Any:
    redis_client = get_redis()

    if redis_client:
        try:
            raw = redis_client.get(key)

            if raw is not None:
                _stats["redis_hits"] += 1
                return json.loads(raw)

        except Exception as e:
            print(f"⚠️ Redis read error: {e}", flush=True)

    entry = _ram.get(key)

    if entry:
        expires = entry.get("expires", 0)

        if expires == EXPIRES_NEVER or time.time() < expires:
            _stats["ram_hits"] += 1
            return entry["data"]

        del _ram[key]

    _stats["misses"] += 1
    return None


def cache_set(key: str, data: Any, ttl: Optional[int] = None) -> None:
    redis_client = get_redis()

    if redis_client:
        try:
            raw = json.dumps(data, ensure_ascii=False, default=str)

            if ttl is None:
                redis_client.set(key, raw)
            else:
                redis_client.setex(key, ttl, raw)

        except Exception as e:
            print(f"⚠️ Redis write error: {e}", flush=True)

    expires = EXPIRES_NEVER if ttl is None else time.time() + ttl

    _ram[key] = {
        "data": data,
        "expires": expires,
    }

    _stats["sets"] += 1


def cache_delete(key: str) -> bool:
    deleted = False

    if key in _ram:
        del _ram[key]
        deleted = True

    redis_client = get_redis()

    if redis_client:
        try:
            if redis_client.delete(key):
                deleted = True

        except Exception as e:
            print(f"⚠️ Redis delete error: {e}", flush=True)

    if deleted:
        _stats["deletes"] += 1

    return deleted


def purge_expired_ram() -> int:
    now = time.time()

    expired = []

    for key, value in _ram.items():
        expires = value.get("expires")

        if expires != EXPIRES_NEVER and now >= expires:
            expired.append(key)

    for key in expired:
        del _ram[key]

    return len(expired)


def ram_items():
    return list(_ram.items())


def redis_scan(pattern: str):
    redis_client = get_redis()

    if not redis_client:
        return []

    try:
        return list(redis_client.scan_iter(pattern, count=200))

    except Exception as e:
        print(f"⚠️ Redis scan error: {e}", flush=True)
        return []


def cache_stats() -> dict:
    stats = {
        "redis": redis_is_available(),
        "ram_entries": len(_ram),
        **_stats,
    }

    redis_client = get_redis()

    if redis_client:
        try:
            info = redis_client.info("memory")

            stats["redis_memory_mb"] = round(
                info.get("used_memory", 0) / 1024 / 1024,
                2
            )

            stats["redis_keys"] = redis_client.dbsize()

        except Exception:
            pass

    return stats