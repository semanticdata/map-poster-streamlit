"""Cache Management Module

Handles caching of OSM data and other resources.
"""

import os
import pickle
from pathlib import Path
from typing import Any

CACHE_DIR = Path("cache")


class CacheError(Exception):
    """Raised when a cache operation fails."""


def get_cache_dir() -> Path:
    """Get the cache directory path, creating it if necessary."""
    if not CACHE_DIR.exists():
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR


def _cache_path(key: str) -> Path:
    """Generate a safe cache file path from a cache key."""
    safe = key.replace(os.sep, "_").replace("/", "_").replace("\\", "_")
    return get_cache_dir() / f"{safe}.pkl"


def cache_get(key: str) -> Any | None:
    """
    Retrieve a cached object by key.

    Args:
        key: Cache key identifier

    Returns:
        Cached object if found, None otherwise
    """
    try:
        path = _cache_path(key)
        if not path.exists():
            return None
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def cache_set(key: str, value: Any) -> None:
    """
    Store an object in the cache.

    Args:
        key: Cache key identifier
        value: Object to cache (must be picklable)
    """
    try:
        cache_dir = get_cache_dir()
        if not cache_dir.exists():
            cache_dir.mkdir(parents=True, exist_ok=True)

        path = _cache_path(key)
        with open(path, "wb") as f:
            pickle.dump(value, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        pass


def cache_clear() -> None:
    """Clear all cached files."""
    cache_dir = get_cache_dir()
    if cache_dir.exists():
        for file in cache_dir.glob("*.pkl"):
            file.unlink()


def cache_size() -> int:
    """Get the total size of the cache in bytes."""
    cache_dir = get_cache_dir()
    if not cache_dir.exists():
        return 0

    total_size = 0
    for file in cache_dir.glob("*.pkl"):
        total_size += file.stat().st_size

    return total_size


def cache_count() -> int:
    """Get the number of cached files."""
    cache_dir = get_cache_dir()
    if not cache_dir.exists():
        return 0

    return len(list(cache_dir.glob("*.pkl")))
