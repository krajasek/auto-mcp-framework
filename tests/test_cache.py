"""Tests for the caching system."""

from __future__ import annotations

import inspect
import json
import time
from pathlib import Path

import pytest

from auto_mcp.cache import CacheEntry, CacheStats, PromptCache
from auto_mcp.core.analyzer import MethodMetadata


@pytest.fixture
def sample_method() -> MethodMetadata:
    """Create sample method metadata for testing."""

    def sample_func(name: str, count: int = 10) -> str:
        """Process the given name."""
        return f"{name}: {count}"

    return MethodMetadata(
        name="sample_func",
        qualified_name="sample_func",
        module_name="test_module",
        signature=inspect.signature(sample_func),
        docstring="Process the given name.",
        type_hints={"name": str, "count": int},
        return_type=str,
        is_async=False,
        is_method=False,
        is_classmethod=False,
        is_staticmethod=False,
        source_code="def sample_func(name: str, count: int = 10) -> str:\n    pass",
        decorators=[],
        parameters=[
            {"name": "name", "type_str": "str", "has_default": False, "default": None},
            {"name": "count", "type_str": "int", "has_default": True, "default": 10},
        ],
        mcp_metadata={},
    )


@pytest.fixture
def another_method() -> MethodMetadata:
    """Create another sample method metadata."""

    def another_func(x: int) -> int:
        """Double a number."""
        return x * 2

    return MethodMetadata(
        name="another_func",
        qualified_name="another_func",
        module_name="test_module",
        signature=inspect.signature(another_func),
        docstring="Double a number.",
        type_hints={"x": int},
        return_type=int,
        is_async=False,
        is_method=False,
        is_classmethod=False,
        is_staticmethod=False,
        source_code="def another_func(x: int) -> int:\n    return x * 2",
        decorators=[],
        parameters=[
            {"name": "x", "type_str": "int", "has_default": False, "default": None},
        ],
        mcp_metadata={},
    )


@pytest.fixture
def cache(tmp_path: Path) -> PromptCache:
    """Create a cache with temporary directory."""
    return PromptCache(cache_dir=tmp_path)


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_is_expired_no_expiry(self) -> None:
        """Test that entries without expiry never expire."""
        entry = CacheEntry(
            description="test",
            source_hash="abc123",
            signature_hash="def456",
            created_at=time.time(),
            expires_at=None,
        )
        assert entry.is_expired() is False

    def test_is_expired_future(self) -> None:
        """Test that entries with future expiry are not expired."""
        entry = CacheEntry(
            description="test",
            source_hash="abc123",
            signature_hash="def456",
            created_at=time.time(),
            expires_at=time.time() + 3600,
        )
        assert entry.is_expired() is False

    def test_is_expired_past(self) -> None:
        """Test that entries with past expiry are expired."""
        entry = CacheEntry(
            description="test",
            source_hash="abc123",
            signature_hash="def456",
            created_at=time.time() - 3600,
            expires_at=time.time() - 1,
        )
        assert entry.is_expired() is True

    def test_is_valid_matching_hashes(self) -> None:
        """Test that entry is valid when hashes match."""
        entry = CacheEntry(
            description="test",
            source_hash="abc123",
            signature_hash="def456",
            created_at=time.time(),
        )
        assert entry.is_valid("abc123", "def456") is True

    def test_is_valid_different_source(self) -> None:
        """Test that entry is invalid when source hash differs."""
        entry = CacheEntry(
            description="test",
            source_hash="abc123",
            signature_hash="def456",
            created_at=time.time(),
        )
        assert entry.is_valid("xyz789", "def456") is False

    def test_is_valid_different_signature(self) -> None:
        """Test that entry is invalid when signature hash differs."""
        entry = CacheEntry(
            description="test",
            source_hash="abc123",
            signature_hash="def456",
            created_at=time.time(),
        )
        assert entry.is_valid("abc123", "xyz789") is False

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        entry = CacheEntry(
            description="test description",
            source_hash="abc123",
            signature_hash="def456",
            created_at=1234567890.0,
            expires_at=1234571490.0,
        )
        data = entry.to_dict()

        assert data["description"] == "test description"
        assert data["source_hash"] == "abc123"
        assert data["signature_hash"] == "def456"
        assert data["created_at"] == 1234567890.0
        assert data["expires_at"] == 1234571490.0

    def test_from_dict(self) -> None:
        """Test deserialization from dictionary."""
        data = {
            "description": "test description",
            "source_hash": "abc123",
            "signature_hash": "def456",
            "created_at": 1234567890.0,
            "expires_at": 1234571490.0,
        }
        entry = CacheEntry.from_dict(data)

        assert entry.description == "test description"
        assert entry.source_hash == "abc123"
        assert entry.signature_hash == "def456"
        assert entry.created_at == 1234567890.0
        assert entry.expires_at == 1234571490.0


class TestCacheStats:
    """Tests for CacheStats dataclass."""

    def test_hit_rate_empty(self) -> None:
        """Test hit rate with no operations."""
        stats = CacheStats()
        assert stats.hit_rate == 0.0

    def test_hit_rate_all_hits(self) -> None:
        """Test hit rate with all hits."""
        stats = CacheStats(hits=10, misses=0)
        assert stats.hit_rate == 1.0

    def test_hit_rate_all_misses(self) -> None:
        """Test hit rate with all misses."""
        stats = CacheStats(hits=0, misses=10)
        assert stats.hit_rate == 0.0

    def test_hit_rate_mixed(self) -> None:
        """Test hit rate with mixed hits and misses."""
        stats = CacheStats(hits=3, misses=7)
        assert stats.hit_rate == 0.3


class TestPromptCache:
    """Tests for PromptCache class."""

    def test_get_miss(self, cache: PromptCache, sample_method: MethodMetadata) -> None:
        """Test cache miss returns None."""
        result = cache.get(sample_method)
        assert result is None
        assert cache.get_stats().misses == 1

    def test_set_and_get(self, cache: PromptCache, sample_method: MethodMetadata) -> None:
        """Test setting and getting a cached value."""
        cache.set(sample_method, "Test description")
        result = cache.get(sample_method)

        assert result == "Test description"
        assert cache.get_stats().hits == 1

    def test_different_cache_types(self, cache: PromptCache, sample_method: MethodMetadata) -> None:
        """Test different cache types are stored separately."""
        cache.set(sample_method, "Tool description", cache_type="tool")
        cache.set(sample_method, "Resource description", cache_type="resource")

        assert cache.get(sample_method, cache_type="tool") == "Tool description"
        assert cache.get(sample_method, cache_type="resource") == "Resource description"

    def test_invalidate_on_source_change(
        self, cache: PromptCache, sample_method: MethodMetadata
    ) -> None:
        """Test that cache invalidates when source code changes."""
        cache.set(sample_method, "Original description")

        # Modify source code
        sample_method.source_code = "def sample_func(): pass  # modified"

        result = cache.get(sample_method)
        assert result is None
        assert cache.get_stats().invalidations == 1

    def test_parameter_descriptions(
        self, cache: PromptCache, sample_method: MethodMetadata
    ) -> None:
        """Test caching parameter descriptions."""
        params = {"name": "The name to process", "count": "Number of repetitions"}
        cache.set_parameter_descriptions(sample_method, params)

        result = cache.get_parameter_descriptions(sample_method)
        assert result == params

    def test_parameter_descriptions_invalid_json(
        self, cache: PromptCache, sample_method: MethodMetadata
    ) -> None:
        """Test that invalid JSON in parameter descriptions returns None."""
        # Directly set an invalid JSON string as the cached value
        cache.set(sample_method, "not valid json", cache_type="params")

        result = cache.get_parameter_descriptions(sample_method)
        assert result is None

    def test_invalidate_module(
        self,
        cache: PromptCache,
        sample_method: MethodMetadata,
        another_method: MethodMetadata,
    ) -> None:
        """Test invalidating all entries for a module."""
        cache.set(sample_method, "Description 1")
        cache.set(another_method, "Description 2")

        count = cache.invalidate("test_module")

        assert count == 2
        assert cache.get(sample_method) is None
        assert cache.get(another_method) is None

    def test_invalidate_method(self, cache: PromptCache, sample_method: MethodMetadata) -> None:
        """Test invalidating entries for a specific method."""
        cache.set(sample_method, "Tool desc", cache_type="tool")
        cache.set(sample_method, "Resource desc", cache_type="resource")

        count = cache.invalidate_method(sample_method)

        assert count == 2
        assert cache.get(sample_method, cache_type="tool") is None
        assert cache.get(sample_method, cache_type="resource") is None

    def test_clear(
        self,
        cache: PromptCache,
        sample_method: MethodMetadata,
        another_method: MethodMetadata,
    ) -> None:
        """Test clearing all cache entries."""
        cache.set(sample_method, "Description 1")
        cache.set(another_method, "Description 2")

        count = cache.clear()

        assert count == 2
        assert cache.get_stats().total_entries == 0

    def test_ttl_expiration(self, tmp_path: Path, sample_method: MethodMetadata) -> None:
        """Test that entries expire after TTL."""
        # Create cache with very short TTL
        cache = PromptCache(cache_dir=tmp_path, ttl_seconds=0.1)
        cache.set(sample_method, "Will expire")

        # Should be available immediately
        assert cache.get(sample_method) == "Will expire"

        # Wait for expiration
        time.sleep(0.15)

        # Should be expired now
        assert cache.get(sample_method) is None


class TestPromptCachePersistence:
    """Tests for cache persistence to disk."""

    def test_save_and_load(self, tmp_path: Path, sample_method: MethodMetadata) -> None:
        """Test saving and loading cache from disk."""
        # Create and populate cache
        cache1 = PromptCache(cache_dir=tmp_path)
        cache1.set(sample_method, "Cached description")
        cache1.save("test_module")

        # Create new cache and load
        cache2 = PromptCache(cache_dir=tmp_path)
        cache2.load("test_module")

        result = cache2.get(sample_method)
        assert result == "Cached description"

    def test_save_creates_file(self, tmp_path: Path, sample_method: MethodMetadata) -> None:
        """Test that save creates cache file."""
        cache = PromptCache(cache_dir=tmp_path)
        cache.set(sample_method, "Description")
        cache.save("test_module")

        cache_file = tmp_path / "test_module_cache.json"
        assert cache_file.exists()

        # Verify contents
        with open(cache_file) as f:
            data = json.load(f)
        assert len(data) == 1

    def test_save_all(
        self,
        tmp_path: Path,
        sample_method: MethodMetadata,
        another_method: MethodMetadata,
    ) -> None:
        """Test saving all cached modules."""
        cache = PromptCache(cache_dir=tmp_path)

        # Modify another_method to be in different module
        another_method.module_name = "other_module"

        cache.set(sample_method, "Description 1")
        cache.set(another_method, "Description 2")
        cache.save_all()

        assert (tmp_path / "test_module_cache.json").exists()
        assert (tmp_path / "other_module_cache.json").exists()

    def test_invalidate_removes_file(self, tmp_path: Path, sample_method: MethodMetadata) -> None:
        """Test that invalidate removes cache file."""
        cache = PromptCache(cache_dir=tmp_path)
        cache.set(sample_method, "Description")
        cache.save("test_module")

        cache_file = tmp_path / "test_module_cache.json"
        assert cache_file.exists()

        cache.invalidate("test_module")
        assert not cache_file.exists()

    def test_save_nonexistent_module(self, tmp_path: Path) -> None:
        """Test that saving a non-existent module does nothing."""
        cache = PromptCache(cache_dir=tmp_path)
        # Save a module that was never added - should not raise
        cache.save("nonexistent_module")
        # No file should be created
        cache_file = tmp_path / "nonexistent_module_cache.json"
        assert not cache_file.exists()

    def test_load_invalid_json(self, tmp_path: Path) -> None:
        """Test that loading invalid JSON is handled gracefully."""
        cache_file = tmp_path / "bad_module_cache.json"
        cache_file.write_text("not valid json")

        cache = PromptCache(cache_dir=tmp_path)
        # Should not raise
        cache.load("bad_module")
        # Cache should be empty
        assert cache.get_stats().total_entries == 0


class TestPromptCacheHashing:
    """Tests for cache key and hash generation."""

    def test_hash_source_consistent(self, cache: PromptCache) -> None:
        """Test that source hash is consistent."""
        source = "def foo(): pass"
        hash1 = cache._hash_source(source)
        hash2 = cache._hash_source(source)
        assert hash1 == hash2

    def test_hash_source_different(self, cache: PromptCache) -> None:
        """Test that different source produces different hash."""
        hash1 = cache._hash_source("def foo(): pass")
        hash2 = cache._hash_source("def bar(): pass")
        assert hash1 != hash2

    def test_hash_signature_consistent(
        self, cache: PromptCache, sample_method: MethodMetadata
    ) -> None:
        """Test that signature hash is consistent."""
        hash1 = cache._hash_signature(sample_method)
        hash2 = cache._hash_signature(sample_method)
        assert hash1 == hash2

    def test_cache_key_format(self, cache: PromptCache, sample_method: MethodMetadata) -> None:
        """Test cache key format."""
        key = cache._get_cache_key(sample_method)
        assert key == "test_module:sample_func"

    def test_get_cache_file_path_module_import_failure(self) -> None:
        """Test cache file path when module cannot be imported."""
        # Create cache without explicit cache_dir
        cache = PromptCache(cache_dir=None)
        # Use a module name that cannot be imported
        path = cache._get_cache_file_path("nonexistent_module_xyz123")
        # Should fallback to current directory
        from pathlib import Path

        assert path == Path.cwd() / cache.cache_file_name
