"""Integration tests for cache behaviour with real LLM responses."""

from __future__ import annotations

import pytest

from auto_mcp.cache.file_cache import PromptCache
from auto_mcp.core.analyzer import MethodMetadata
from auto_mcp.llm.ollama import OllamaProvider

pytestmark = pytest.mark.integration


class TestCacheStoresLLMResponse:
    """Verify that cache correctly stores and serves LLM-generated descriptions."""

    @pytest.mark.asyncio
    async def test_cache_hit_after_generation(
        self,
        ollama_provider: OllamaProvider,
        sample_method_metadata: MethodMetadata,
    ) -> None:
        """After generating a description, the cache returns it on next lookup."""
        cache = PromptCache()

        # Initially empty
        assert cache.get(sample_method_metadata, cache_type="tool") is None

        # Generate with LLM and store
        description = await ollama_provider.generate_tool_description(
            sample_method_metadata,
        )
        cache.set(sample_method_metadata, description, cache_type="tool")

        # Cache should now return the same description
        cached = cache.get(sample_method_metadata, cache_type="tool")
        assert cached == description

    @pytest.mark.asyncio
    async def test_cache_stats_reflect_hits_and_misses(
        self,
        ollama_provider: OllamaProvider,
        sample_method_metadata: MethodMetadata,
    ) -> None:
        """Cache stats correctly track hits and misses."""
        cache = PromptCache()

        # Miss
        cache.get(sample_method_metadata, cache_type="tool")
        stats = cache.get_stats()
        assert stats.misses == 1
        assert stats.hits == 0

        # Generate and store
        description = await ollama_provider.generate_tool_description(
            sample_method_metadata,
        )
        cache.set(sample_method_metadata, description, cache_type="tool")

        # Hit
        cache.get(sample_method_metadata, cache_type="tool")
        stats = cache.get_stats()
        assert stats.hits == 1
        assert stats.misses == 1

    @pytest.mark.asyncio
    async def test_parameter_descriptions_cached(
        self,
        ollama_provider: OllamaProvider,
        complex_method_metadata: MethodMetadata,
    ) -> None:
        """Parameter descriptions can be cached and retrieved."""
        cache = PromptCache()

        descriptions = await ollama_provider.generate_parameter_descriptions(
            complex_method_metadata,
        )
        cache.set_parameter_descriptions(complex_method_metadata, descriptions)

        cached = cache.get_parameter_descriptions(complex_method_metadata)
        assert cached is not None
        assert cached == descriptions


class TestCacheInvalidation:
    """Verify that cache invalidation causes new LLM calls."""

    @pytest.mark.asyncio
    async def test_invalidation_clears_entry(
        self,
        ollama_provider: OllamaProvider,
        sample_method_metadata: MethodMetadata,
    ) -> None:
        """After invalidation, the cache returns None for the entry."""
        cache = PromptCache()

        # Store
        description = await ollama_provider.generate_tool_description(
            sample_method_metadata,
        )
        cache.set(sample_method_metadata, description, cache_type="tool")
        assert cache.get(sample_method_metadata, cache_type="tool") is not None

        # Invalidate
        count = cache.invalidate_method(sample_method_metadata)
        assert count >= 1

        # Should be gone
        assert cache.get(sample_method_metadata, cache_type="tool") is None

    @pytest.mark.asyncio
    async def test_module_level_invalidation(
        self,
        ollama_provider: OllamaProvider,
        sample_method_metadata: MethodMetadata,
        complex_method_metadata: MethodMetadata,
    ) -> None:
        """Invalidating an entire module clears all its entries."""
        cache = PromptCache()

        # Store entries for sample (module_name="sample")
        desc = await ollama_provider.generate_tool_description(sample_method_metadata)
        cache.set(sample_method_metadata, desc, cache_type="tool")

        count = cache.invalidate(sample_method_metadata.module_name)
        assert count >= 1

        # Entry should be gone
        assert cache.get(sample_method_metadata, cache_type="tool") is None


class TestCachePersistence:
    """Verify cache persistence to and loading from disk with real data."""

    @pytest.mark.asyncio
    async def test_save_and_load(
        self,
        ollama_provider: OllamaProvider,
        sample_method_metadata: MethodMetadata,
        tmp_path: MethodMetadata,
    ) -> None:
        """Cached descriptions survive save/load cycle."""
        cache = PromptCache(cache_dir=tmp_path)

        description = await ollama_provider.generate_tool_description(
            sample_method_metadata,
        )
        cache.set(sample_method_metadata, description, cache_type="tool")
        cache.save(sample_method_metadata.module_name)

        # Create a fresh cache and load from disk
        cache2 = PromptCache(cache_dir=tmp_path)
        cache2.load(sample_method_metadata.module_name)

        cached = cache2.get(sample_method_metadata, cache_type="tool")
        assert cached == description
