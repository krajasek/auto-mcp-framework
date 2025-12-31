"""File-based caching for LLM-generated descriptions."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from auto_mcp.core.analyzer import MethodMetadata


@dataclass
class CacheEntry:
    """A single cache entry with metadata.

    Attributes:
        description: The cached description text
        source_hash: Hash of the source code when cached
        signature_hash: Hash of the function signature
        created_at: Unix timestamp when entry was created
        expires_at: Optional Unix timestamp when entry expires
    """

    description: str
    source_hash: str
    signature_hash: str
    created_at: float
    expires_at: float | None = None

    def is_expired(self) -> bool:
        """Check if this cache entry has expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def is_valid(self, source_hash: str, signature_hash: str) -> bool:
        """Check if this cache entry is still valid.

        Args:
            source_hash: Current hash of the source code
            signature_hash: Current hash of the signature

        Returns:
            True if the entry is valid and not expired
        """
        if self.is_expired():
            return False
        return self.source_hash == source_hash and self.signature_hash == signature_hash

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "description": self.description,
            "source_hash": self.source_hash,
            "signature_hash": self.signature_hash,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CacheEntry:
        """Create from dictionary."""
        return cls(
            description=data["description"],
            source_hash=data["source_hash"],
            signature_hash=data["signature_hash"],
            created_at=data["created_at"],
            expires_at=data.get("expires_at"),
        )


@dataclass
class CacheStats:
    """Statistics about cache usage.

    Attributes:
        hits: Number of cache hits
        misses: Number of cache misses
        invalidations: Number of entries invalidated
        total_entries: Current number of entries in cache
    """

    hits: int = 0
    misses: int = 0
    invalidations: int = 0
    total_entries: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate the cache hit rate."""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total


@dataclass
class PromptCache:
    """File-based cache for LLM-generated descriptions.

    This cache stores generated descriptions in a JSON file to avoid
    redundant LLM calls. Each entry is keyed by a hash of the function's
    source code and signature.

    Attributes:
        cache_dir: Directory to store cache files (None = alongside module)
        ttl_seconds: Time-to-live for cache entries in seconds (None = no expiry)
        cache_file_name: Name of the cache file
    """

    cache_dir: Path | None = None
    ttl_seconds: float | None = None
    cache_file_name: str = ".auto_mcp_cache.json"
    _cache: dict[str, dict[str, CacheEntry]] = field(default_factory=dict)
    _stats: CacheStats = field(default_factory=CacheStats)

    def get(
        self,
        method: MethodMetadata,
        cache_type: str = "tool",
    ) -> str | None:
        """Get a cached description for a method.

        Args:
            method: The method metadata
            cache_type: Type of description (tool, resource, prompt, params)

        Returns:
            The cached description, or None if not found/invalid
        """
        cache_key = self._get_cache_key(method)
        source_hash = self._hash_source(method.source_code)
        signature_hash = self._hash_signature(method)

        # Load cache for this module if not already loaded
        module_cache = self._get_module_cache(method.module_name)

        # Check for entry
        full_key = f"{cache_key}:{cache_type}"
        entry = module_cache.get(full_key)

        if entry is None:
            self._stats.misses += 1
            return None

        if not entry.is_valid(source_hash, signature_hash):
            # Entry is stale, remove it
            del module_cache[full_key]
            self._stats.invalidations += 1
            self._stats.misses += 1
            return None

        self._stats.hits += 1
        return entry.description

    def set(
        self,
        method: MethodMetadata,
        description: str,
        cache_type: str = "tool",
    ) -> None:
        """Cache a description for a method.

        Args:
            method: The method metadata
            description: The description to cache
            cache_type: Type of description (tool, resource, prompt, params)
        """
        cache_key = self._get_cache_key(method)
        source_hash = self._hash_source(method.source_code)
        signature_hash = self._hash_signature(method)

        expires_at = None
        if self.ttl_seconds is not None:
            expires_at = time.time() + self.ttl_seconds

        entry = CacheEntry(
            description=description,
            source_hash=source_hash,
            signature_hash=signature_hash,
            created_at=time.time(),
            expires_at=expires_at,
        )

        module_cache = self._get_module_cache(method.module_name)
        full_key = f"{cache_key}:{cache_type}"
        module_cache[full_key] = entry
        self._stats.total_entries = sum(len(c) for c in self._cache.values())

    def get_parameter_descriptions(
        self,
        method: MethodMetadata,
    ) -> dict[str, str] | None:
        """Get cached parameter descriptions.

        Args:
            method: The method metadata

        Returns:
            Dictionary of parameter descriptions, or None if not cached
        """
        cached = self.get(method, cache_type="params")
        if cached is None:
            return None

        try:
            result: dict[str, str] = json.loads(cached)
            return result
        except json.JSONDecodeError:
            return None

    def set_parameter_descriptions(
        self,
        method: MethodMetadata,
        descriptions: dict[str, str],
    ) -> None:
        """Cache parameter descriptions.

        Args:
            method: The method metadata
            descriptions: Dictionary of parameter descriptions
        """
        self.set(method, json.dumps(descriptions), cache_type="params")

    def invalidate(self, module_name: str) -> int:
        """Invalidate all cache entries for a module.

        Args:
            module_name: Name of the module to invalidate

        Returns:
            Number of entries invalidated
        """
        if module_name in self._cache:
            count = len(self._cache[module_name])
            del self._cache[module_name]
            self._stats.invalidations += count
            self._stats.total_entries = sum(len(c) for c in self._cache.values())

            # Also remove the cache file
            cache_file = self._get_cache_file_path(module_name)
            if cache_file and cache_file.exists():
                cache_file.unlink()

            return count
        return 0

    def invalidate_method(self, method: MethodMetadata) -> int:
        """Invalidate cache entries for a specific method.

        Args:
            method: The method to invalidate

        Returns:
            Number of entries invalidated
        """
        cache_key = self._get_cache_key(method)
        module_cache = self._get_module_cache(method.module_name)

        count = 0
        keys_to_remove = [k for k in module_cache if k.startswith(f"{cache_key}:")]
        for key in keys_to_remove:
            del module_cache[key]
            count += 1
            self._stats.invalidations += 1

        self._stats.total_entries = sum(len(c) for c in self._cache.values())
        return count

    def clear(self) -> int:
        """Clear all cache entries.

        Returns:
            Number of entries cleared
        """
        total = sum(len(c) for c in self._cache.values())
        self._cache.clear()
        self._stats.total_entries = 0
        return total

    def save(self, module_name: str) -> None:
        """Save cache for a module to disk.

        Args:
            module_name: Name of the module to save
        """
        if module_name not in self._cache:
            return

        cache_file = self._get_cache_file_path(module_name)
        if cache_file is None:
            return

        # Ensure directory exists
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        # Convert entries to dictionaries
        data = {key: entry.to_dict() for key, entry in self._cache[module_name].items()}

        with open(cache_file, "w") as f:
            json.dump(data, f, indent=2)

    def save_all(self) -> None:
        """Save all cached modules to disk."""
        for module_name in self._cache:
            self.save(module_name)

    def load(self, module_name: str) -> None:
        """Load cache for a module from disk.

        Args:
            module_name: Name of the module to load
        """
        cache_file = self._get_cache_file_path(module_name)
        if cache_file is None or not cache_file.exists():
            return

        try:
            with open(cache_file) as f:
                data = json.load(f)

            self._cache[module_name] = {
                key: CacheEntry.from_dict(entry) for key, entry in data.items()
            }
            self._stats.total_entries = sum(len(c) for c in self._cache.values())
        except (json.JSONDecodeError, KeyError):
            # Invalid cache file, ignore it
            pass

    def get_stats(self) -> CacheStats:
        """Get cache statistics.

        Returns:
            Current cache statistics
        """
        return self._stats

    def _get_cache_key(self, method: MethodMetadata) -> str:
        """Generate a cache key for a method.

        Args:
            method: The method metadata

        Returns:
            A unique cache key string
        """
        return f"{method.module_name}:{method.qualified_name}"

    def _hash_source(self, source_code: str) -> str:
        """Generate a hash of source code.

        Args:
            source_code: The source code to hash

        Returns:
            SHA256 hash of the source code
        """
        return hashlib.sha256(source_code.encode()).hexdigest()[:16]

    def _hash_signature(self, method: MethodMetadata) -> str:
        """Generate a hash of a method signature.

        Args:
            method: The method metadata

        Returns:
            SHA256 hash of the signature string
        """
        sig_str = str(method.signature)
        return hashlib.sha256(sig_str.encode()).hexdigest()[:16]

    def _get_module_cache(self, module_name: str) -> dict[str, CacheEntry]:
        """Get or create cache dictionary for a module.

        Args:
            module_name: Name of the module

        Returns:
            The cache dictionary for the module
        """
        if module_name not in self._cache:
            self._cache[module_name] = {}
            # Try to load from disk
            self.load(module_name)

        return self._cache[module_name]

    def _get_cache_file_path(self, module_name: str) -> Path | None:
        """Get the cache file path for a module.

        Args:
            module_name: Name of the module

        Returns:
            Path to the cache file, or None if not determinable
        """
        if self.cache_dir is not None:
            return self.cache_dir / f"{module_name.replace('.', '_')}_cache.json"

        # Try to determine path from module
        try:
            import importlib

            module = importlib.import_module(module_name)
            if hasattr(module, "__file__") and module.__file__:
                module_path = Path(module.__file__)
                return module_path.parent / self.cache_file_name
        except (ImportError, AttributeError):
            pass

        # Fallback to current directory
        return Path.cwd() / self.cache_file_name
