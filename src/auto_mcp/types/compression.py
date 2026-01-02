"""Compression support for type adapters.

This module provides compression wrappers for handling large serialized data.
"""

from __future__ import annotations

import base64
import gzip
import json
import logging
import zlib
from dataclasses import dataclass
from enum import Enum
from typing import Any, Generic, TypeVar

from auto_mcp.types.base import JsonValue, TypeAdapter

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CompressionAlgorithm(Enum):
    """Supported compression algorithms."""

    GZIP = "gzip"
    ZLIB = "zlib"
    LZ4 = "lz4"  # Optional, requires lz4 package
    NONE = "none"


@dataclass
class CompressionConfig:
    """Configuration for data compression.

    Attributes:
        enabled: Whether compression is enabled
        algorithm: Compression algorithm to use
        threshold: Minimum size in bytes to trigger compression
        level: Compression level (1-9, higher = more compression)
    """

    enabled: bool = True
    algorithm: CompressionAlgorithm = CompressionAlgorithm.GZIP
    threshold: int = 1024  # 1KB default threshold
    level: int = 6  # Default compression level


@dataclass
class CompressedData:
    """Container for compressed data with metadata.

    Attributes:
        compressed: Whether the data is compressed
        algorithm: Algorithm used for compression
        original_size: Size before compression
        compressed_size: Size after compression
        data: The (possibly compressed) data as base64 string
    """

    compressed: bool
    algorithm: str
    original_size: int
    compressed_size: int
    data: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "compressed": self.compressed,
            "algorithm": self.algorithm,
            "original_size": self.original_size,
            "compressed_size": self.compressed_size,
            "compression_ratio": round(self.compressed_size / self.original_size, 3)
            if self.original_size > 0
            else 1.0,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompressedData:
        """Create from dict."""
        return cls(
            compressed=data["compressed"],
            algorithm=data["algorithm"],
            original_size=data["original_size"],
            compressed_size=data["compressed_size"],
            data=data["data"],
        )


def compress_bytes(
    data: bytes,
    algorithm: CompressionAlgorithm = CompressionAlgorithm.GZIP,
    level: int = 6,
) -> bytes:
    """Compress bytes using the specified algorithm.

    Args:
        data: Data to compress
        algorithm: Compression algorithm
        level: Compression level (1-9)

    Returns:
        Compressed bytes
    """
    if algorithm == CompressionAlgorithm.GZIP:
        return gzip.compress(data, compresslevel=level)

    if algorithm == CompressionAlgorithm.ZLIB:
        return zlib.compress(data, level=level)

    if algorithm == CompressionAlgorithm.LZ4:
        try:
            import lz4.frame

            return lz4.frame.compress(data, compression_level=level)
        except ImportError:
            logger.warning("lz4 not installed, falling back to gzip")
            return gzip.compress(data, compresslevel=level)

    # No compression
    return data


def decompress_bytes(
    data: bytes,
    algorithm: CompressionAlgorithm = CompressionAlgorithm.GZIP,
) -> bytes:
    """Decompress bytes using the specified algorithm.

    Args:
        data: Compressed data
        algorithm: Compression algorithm used

    Returns:
        Decompressed bytes
    """
    if algorithm == CompressionAlgorithm.GZIP:
        return gzip.decompress(data)

    if algorithm == CompressionAlgorithm.ZLIB:
        return zlib.decompress(data)

    if algorithm == CompressionAlgorithm.LZ4:
        try:
            import lz4.frame

            return lz4.frame.decompress(data)
        except ImportError as e:
            raise ImportError(
                "lz4 package required to decompress lz4 data"
            ) from e

    # No compression
    return data


class CompressedAdapter(TypeAdapter[T], Generic[T]):
    """Wrapper adapter that adds compression to any TypeAdapter.

    This adapter wraps another adapter and automatically compresses
    the serialized data if it exceeds the configured threshold.

    Example:
        >>> base_adapter = DataFrameAdapter()
        >>> compressed = CompressedAdapter(
        ...     base_adapter,
        ...     config=CompressionConfig(threshold=10240)  # 10KB
        ... )
        >>> # Large DataFrames will be automatically compressed
        >>> serialized = compressed.serialize(large_df)
    """

    def __init__(
        self,
        base_adapter: TypeAdapter[T],
        config: CompressionConfig | None = None,
    ) -> None:
        """Initialize compressed adapter.

        Args:
            base_adapter: The underlying adapter to wrap
            config: Compression configuration
        """
        self.base_adapter = base_adapter
        self.config = config or CompressionConfig()
        self.target_type = base_adapter.target_type

    def serialize(self, obj: T) -> JsonValue:
        """Serialize and optionally compress the object.

        Args:
            obj: Object to serialize

        Returns:
            JSON-compatible value (dict with compression metadata if compressed)
        """
        # First serialize with base adapter
        serialized = self.base_adapter.serialize(obj)

        # Convert to JSON bytes for size check
        json_bytes = json.dumps(serialized).encode("utf-8")
        original_size = len(json_bytes)

        # Check if compression should be applied
        if not self.config.enabled or original_size < self.config.threshold:
            # Return uncompressed with metadata
            return CompressedData(
                compressed=False,
                algorithm="none",
                original_size=original_size,
                compressed_size=original_size,
                data=base64.b64encode(json_bytes).decode("ascii"),
            ).to_dict()

        # Compress the data
        compressed_bytes = compress_bytes(
            json_bytes,
            algorithm=self.config.algorithm,
            level=self.config.level,
        )
        compressed_size = len(compressed_bytes)

        # Only use compression if it actually saves space
        if compressed_size >= original_size:
            return CompressedData(
                compressed=False,
                algorithm="none",
                original_size=original_size,
                compressed_size=original_size,
                data=base64.b64encode(json_bytes).decode("ascii"),
            ).to_dict()

        logger.debug(
            f"Compressed {original_size} bytes to {compressed_size} bytes "
            f"({100 * compressed_size / original_size:.1f}%)"
        )

        return CompressedData(
            compressed=True,
            algorithm=self.config.algorithm.value,
            original_size=original_size,
            compressed_size=compressed_size,
            data=base64.b64encode(compressed_bytes).decode("ascii"),
        ).to_dict()

    def deserialize(self, data: JsonValue) -> T:
        """Decompress and deserialize the data.

        Args:
            data: JSON-compatible value (possibly compressed)

        Returns:
            The deserialized object
        """
        if not isinstance(data, dict) or "compressed" not in data:
            # Not wrapped in compression metadata, pass through
            return self.base_adapter.deserialize(data)

        compressed_data = CompressedData.from_dict(data)
        raw_bytes = base64.b64decode(compressed_data.data)

        if compressed_data.compressed:
            # Decompress
            algorithm = CompressionAlgorithm(compressed_data.algorithm)
            raw_bytes = decompress_bytes(raw_bytes, algorithm)

        # Parse JSON and deserialize
        json_data = json.loads(raw_bytes.decode("utf-8"))
        return self.base_adapter.deserialize(json_data)

    def json_schema(self) -> dict[str, Any]:
        """Return JSON Schema for compressed data."""
        return {
            "type": "object",
            "properties": {
                "compressed": {
                    "type": "boolean",
                    "description": "Whether the data is compressed",
                },
                "algorithm": {
                    "type": "string",
                    "enum": ["gzip", "zlib", "lz4", "none"],
                    "description": "Compression algorithm used",
                },
                "original_size": {
                    "type": "integer",
                    "description": "Original data size in bytes",
                },
                "compressed_size": {
                    "type": "integer",
                    "description": "Compressed data size in bytes",
                },
                "compression_ratio": {
                    "type": "number",
                    "description": "Ratio of compressed to original size",
                },
                "data": {
                    "type": "string",
                    "contentEncoding": "base64",
                    "description": "Base64-encoded (possibly compressed) data",
                },
            },
            "required": ["compressed", "algorithm", "data"],
            "description": f"Compressed {self.base_adapter.target_type.__name__}",
        }

    def can_serialize(self, obj: T) -> bool:
        """Check if the base adapter can serialize this object."""
        return self.base_adapter.can_serialize(obj)


def with_compression(
    adapter: TypeAdapter[T],
    threshold: int = 1024,
    algorithm: CompressionAlgorithm = CompressionAlgorithm.GZIP,
    level: int = 6,
) -> CompressedAdapter[T]:
    """Convenience function to wrap an adapter with compression.

    Args:
        adapter: The adapter to wrap
        threshold: Minimum size to trigger compression (bytes)
        algorithm: Compression algorithm
        level: Compression level

    Returns:
        CompressedAdapter wrapping the original adapter
    """
    config = CompressionConfig(
        enabled=True,
        algorithm=algorithm,
        threshold=threshold,
        level=level,
    )
    return CompressedAdapter(adapter, config)


class AutoCompressRegistry:
    """Registry extension that automatically applies compression to large types.

    This is a helper that can wrap adapters in a TypeRegistry with compression
    based on configuration.
    """

    def __init__(
        self,
        config: CompressionConfig | None = None,
        large_type_threshold: int = 10240,  # 10KB
    ) -> None:
        """Initialize auto-compress registry.

        Args:
            config: Compression configuration
            large_type_threshold: Types that commonly produce large output
        """
        self.config = config or CompressionConfig()
        self.large_type_threshold = large_type_threshold

        # Types that typically produce large serialized output
        self._large_types: set[type] = set()

    def register_large_type(self, type_: type) -> None:
        """Register a type as typically producing large output.

        Args:
            type_: The type to register
        """
        self._large_types.add(type_)

    def wrap_adapter(self, adapter: TypeAdapter[T]) -> TypeAdapter[T]:
        """Wrap an adapter with compression if appropriate.

        Args:
            adapter: The adapter to potentially wrap

        Returns:
            The adapter, possibly wrapped with compression
        """
        if not self.config.enabled:
            return adapter

        # Always wrap types registered as large
        if adapter.target_type in self._large_types:
            return CompressedAdapter(adapter, self.config)

        # Otherwise return as-is (threshold will be checked at serialize time)
        return adapter

    def wrap_if_large(
        self,
        adapter: TypeAdapter[T],
        threshold: int | None = None,
    ) -> CompressedAdapter[T]:
        """Explicitly wrap an adapter with compression.

        Args:
            adapter: The adapter to wrap
            threshold: Override the default threshold

        Returns:
            CompressedAdapter wrapping the original
        """
        config = CompressionConfig(
            enabled=True,
            algorithm=self.config.algorithm,
            threshold=threshold or self.large_type_threshold,
            level=self.config.level,
        )
        return CompressedAdapter(adapter, config)
