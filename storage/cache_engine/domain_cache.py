# storage/cache_engine/domain_cache.py

from typing import Optional

from .cache_manager import (
    cache_get,
    cache_set,
    cache_delete,
    cache_stats as manager_cache_stats,
    purge_expired_ram,
    ram_items,
    redis_scan,
)

from .hash_utils import (
    key_url,
    legacy_key_url,
    key_film,
    key_content,
    key_title,
)

from .ttl import TTL_URL, TTL_CONTENT


def get_cache(url: str) -> Optional[dict]:
    data = cache_get(key_url(url))

    if data:
        print("✅ Cache URL hit", flush=True)
        return data

    data = cache_get(legacy_key_url(url))

    if data:
        print("✅ Cache URL legacy hit", flush=True)
        return data

    return None


def get_cache_by_content(
    transcript: str,
    ocr_text: str,
    lang: str = "fr",
) -> Optional[dict]:
    content_key = key_content(transcript, ocr_text)

    if not content_key:
        return None

    tmdb_id = cache_get(content_key)

    if not tmdb_id:
        return None

    return get_cache_by_film(tmdb_id, lang)


def get_cache_by_film(tmdb_id, lang: str) -> Optional[dict]:
    data = cache_get(key_film(tmdb_id, lang))

    if data:
        print(f"✅ Cache film hit: {tmdb_id}:{lang}", flush=True)

    return data


def get_cache_by_title(title: str, lang: str) -> Optional[dict]:
    title_key = key_title(title)

    if not title_key:
        return None

    tmdb_id = cache_get(title_key)

    if not tmdb_id:
        return None

    return get_cache_by_film(tmdb_id, lang)


def set_cache(
    url: str,
    data: dict,
    transcript: str = "",
    ocr_text: str = "",
) -> None:
    confidence = data.get("confidence", 0)
    tmdb_id = data.get("tmdb_id")
    lang = data.get("lang", "fr")
    title = data.get("title", "")
    original_title = data.get("original_title", "")

    cache_set(key_url(url), data, TTL_URL)
    cache_set(legacy_key_url(url), data, TTL_URL)

    if confidence >= 50 and tmdb_id:
        film_key = key_film(tmdb_id, lang)

        cache_set(film_key, data, ttl=None)

        print(f"💾 Cache film permanent: {tmdb_id}:{lang}", flush=True)

        content_key = key_content(transcript, ocr_text)

        if content_key:
            cache_set(content_key, tmdb_id, TTL_CONTENT)

        if title:
            set_cache_title(title, tmdb_id)

        if original_title and original_title != title:
            set_cache_title(original_title, tmdb_id)


def set_cache_title(title: str, tmdb_id: int) -> None:
    title_key = key_title(title)

    if not title_key:
        return

    cache_set(title_key, tmdb_id, ttl=None)


def delete_cache(url: str) -> bool:
    deleted_new = cache_delete(key_url(url))
    deleted_old = cache_delete(legacy_key_url(url))

    return deleted_new or deleted_old


def purge_expired() -> int:
    return purge_expired_ram()


def purge_by_code(code: str) -> int:
    count = 0

    for key, value in ram_items():
        data = value.get("data")

        if isinstance(data, dict):
            if data.get("code") == code or data.get("status") == code:
                cache_delete(key)
                count += 1

    for key in redis_scan("url:*"):
        data = cache_get(key)

        if isinstance(data, dict):
            if data.get("code") == code or data.get("status") == code:
                cache_delete(key)
                count += 1

    return count


def cache_get_generic(key: str):
    return cache_get(key)


def cache_set_generic(key: str, data, ttl: int) -> None:
    cache_set(key, data, ttl)


def cache_stats() -> dict:
    return manager_cache_stats()