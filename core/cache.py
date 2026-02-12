"""Cache Management Module

Handles caching of OSM data and other resources.
"""

import os
import pickle
import time
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


def _metadata_path(key: str) -> Path:
    """Generate the metadata file path for a cache entry."""
    safe = key.replace(os.sep, "_").replace("/", "_").replace("\\", "_")
    return get_cache_dir() / f"{safe}.meta"


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


def cache_get_with_metadata(key: str) -> tuple[Any | None, dict[str, Any]]:
    """
    Retrieve a cached object along with its metadata.

    Args:
        key: Cache key identifier

    Returns:
        Tuple of (cached object or None, metadata dict with 'age_seconds', 'created_at')
    """
    try:
        path = _cache_path(key)
        metadata_path = _metadata_path(key)
        
        if not path.exists():
            return None, {}
        
        with open(path, "rb") as f:
            value = pickle.load(f)
        
        metadata = {
            "age_seconds": 0,
            "created_at": 0,
        }
        
        if metadata_path.exists():
            with open(metadata_path, "rb") as f:
                metadata = pickle.load(f)
        
        if metadata.get("created_at"):
            metadata["age_seconds"] = time.time() - metadata["created_at"]
        
        return value, metadata
    except Exception:
        return None, {}


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
        
        metadata_path = _metadata_path(key)
        metadata = {
            "created_at": time.time(),
            "key": key,
        }
        with open(metadata_path, "wb") as f:
            pickle.dump(metadata, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        pass


def cache_set_with_ttl(key: str, value: Any, ttl_hours: int = 24) -> None:
    """
    Store an object in the cache with a time-to-live.

    Args:
        key: Cache key identifier
        value: Object to cache (must be picklable)
        ttl_hours: Time-to-live in hours
    """
    try:
        cache_dir = get_cache_dir()
        if not cache_dir.exists():
            cache_dir.mkdir(parents=True, exist_ok=True)

        path = _cache_path(key)
        with open(path, "wb") as f:
            pickle.dump(value, f, protocol=pickle.HIGHEST_PROTOCOL)
        
        metadata_path = _metadata_path(key)
        metadata = {
            "created_at": time.time(),
            "ttl_seconds": ttl_hours * 3600,
            "expires_at": time.time() + (ttl_hours * 3600),
            "key": key,
        }
        with open(metadata_path, "wb") as f:
            pickle.dump(metadata, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        pass


def cache_clear() -> None:
    """Clear all cached files."""
    cache_dir = get_cache_dir()
    if cache_dir.exists():
        for file in cache_dir.glob("*.pkl"):
            file.unlink()
        for file in cache_dir.glob("*.meta"):
            file.unlink()


def cache_size() -> int:
    """Get the total size of the cache in bytes."""
    cache_dir = get_cache_dir()
    if not cache_dir.exists():
        return 0

    total_size = 0
    for file in cache_dir.glob("*.pkl"):
        total_size += file.stat().st_size
    for file in cache_dir.glob("*.meta"):
        total_size += file.stat().st_size

    return total_size


def cache_count() -> int:
    """Get the number of cached files."""
    cache_dir = get_cache_dir()
    if not cache_dir.exists():
        return 0

    return len(list(cache_dir.glob("*.pkl")))


def cache_is_expired(key: str) -> bool:
    """
    Check if a cached entry has expired based on its TTL.

    Args:
        key: Cache key identifier

    Returns:
        True if expired or doesn't exist, False otherwise
    """
    try:
        metadata_path = _metadata_path(key)
        if not metadata_path.exists():
            return True
        
        with open(metadata_path, "rb") as f:
            metadata = pickle.load(f)
        
        expires_at = metadata.get("expires_at")
        if expires_at:
            return time.time() > expires_at
        
        return False
    except Exception:
        return True


def cache_get_stats() -> dict[str, Any]:
    """
    Get statistics about the cache.

    Returns:
        Dictionary with cache statistics
    """
    cache_dir = get_cache_dir()
    if not cache_dir.exists():
        return {"count": 0, "size_bytes": 0, "expired": 0, "valid": 0}
    
    count = 0
    size_bytes = 0
    expired = 0
    valid = 0
    
    for file in cache_dir.glob("*.pkl"):
        count += 1
        size_bytes += file.stat().st_size
        key = file.stem
        if cache_is_expired(key):
            expired += 1
        else:
            valid += 1
    
    return {
        "count": count,
        "size_bytes": size_bytes,
        "size_mb": size_bytes / (1024 * 1024),
        "expired": expired,
        "valid": valid,
    }

