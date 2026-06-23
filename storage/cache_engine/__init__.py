# storage/cache_engine/__init__.py

from .domain_cache import (
    get_cache,
    get_cache_by_content,
    get_cache_by_film,
    get_cache_by_title,
    set_cache,
    set_cache_title,
    delete_cache,
    purge_expired,
    purge_by_code,
    cache_get_generic,
    cache_set_generic,
    cache_stats,
)

from .lock_manager import acquire_lock, release_lock