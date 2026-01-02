"""Type serialization system for MCP tool parameters.

This module provides a unified system for handling complex Python types
in MCP contexts, including serialization adapters and server-side object storage.

Example:
    >>> from auto_mcp.types import TypeRegistry, ObjectStore
    >>>
    >>> # Set up registry with adapters
    >>> registry = TypeRegistry()
    >>> registry.register(
    ...     datetime,
    ...     serialize=lambda dt: dt.isoformat(),
    ...     deserialize=lambda s: datetime.fromisoformat(s),
    ...     schema={"type": "string", "format": "date-time"},
    ... )
    >>>
    >>> # Or use object store for stateful objects
    >>> store = ObjectStore()
    >>> handle = store.store(my_session, ttl=3600)
    >>> session = store.get(handle)
"""

from auto_mcp.types.adapters import (
    # Stdlib adapters
    ByteArrayAdapter,
    BytesAdapter,
    ComplexAdapter,
    DateAdapter,
    DateTimeAdapter,
    DecimalAdapter,
    FrozenSetAdapter,
    PathAdapter,
    PurePathAdapter,
    SetAdapter,
    TimeAdapter,
    TimeDeltaAdapter,
    UUIDAdapter,
    # Factory functions
    create_numpy_array_adapter,
    create_pandas_dataframe_adapter,
    create_pil_image_adapter,
    get_all_adapters,
    get_optional_adapters,
    get_stdlib_adapters,
    register_all_adapters,
    register_stdlib_adapters,
)
from auto_mcp.types.base import (
    JSON_COMPATIBLE_TYPES,
    FunctionAdapter,
    JsonValue,
    ObjectStoreConfig,
    TypeAdapter,
    TypeInfo,
    TypeStrategy,
    get_type_args,
    get_type_origin,
    is_json_compatible,
    type_adapter,
)
from auto_mcp.types.registry import (
    TypeRegistry,
    get_default_registry,
    set_default_registry,
)
from auto_mcp.types.store import (
    ObjectStore,
    StoredObject,
    StoreStats,
    get_default_store,
    set_default_store,
)
from auto_mcp.types.wrapper import (
    ClassWrapper,
    FunctionWrapper,
    MethodWrapper,
    TypeTransformError,
    auto_transform,
    wrap_function,
)
from auto_mcp.types.compression import (
    AutoCompressRegistry,
    CompressedAdapter,
    CompressedData,
    CompressionAlgorithm,
    CompressionConfig,
    compress_bytes,
    decompress_bytes,
    with_compression,
)

__all__ = [
    # Base types
    "JsonValue",
    "TypeStrategy",
    "TypeInfo",
    "ObjectStoreConfig",
    "TypeAdapter",
    "FunctionAdapter",
    "type_adapter",
    "JSON_COMPATIBLE_TYPES",
    "is_json_compatible",
    "get_type_origin",
    "get_type_args",
    # Registry
    "TypeRegistry",
    "get_default_registry",
    "set_default_registry",
    # Object store
    "ObjectStore",
    "StoredObject",
    "StoreStats",
    "get_default_store",
    "set_default_store",
    # Stdlib adapters
    "DateTimeAdapter",
    "DateAdapter",
    "TimeAdapter",
    "TimeDeltaAdapter",
    "PathAdapter",
    "PurePathAdapter",
    "UUIDAdapter",
    "DecimalAdapter",
    "BytesAdapter",
    "ByteArrayAdapter",
    "SetAdapter",
    "FrozenSetAdapter",
    "ComplexAdapter",
    # Adapter factories
    "create_pandas_dataframe_adapter",
    "create_pil_image_adapter",
    "create_numpy_array_adapter",
    "get_stdlib_adapters",
    "get_optional_adapters",
    "get_all_adapters",
    "register_stdlib_adapters",
    "register_all_adapters",
    # Wrappers
    "FunctionWrapper",
    "MethodWrapper",
    "ClassWrapper",
    "TypeTransformError",
    "wrap_function",
    "auto_transform",
    # Compression
    "CompressionAlgorithm",
    "CompressionConfig",
    "CompressedData",
    "CompressedAdapter",
    "AutoCompressRegistry",
    "compress_bytes",
    "decompress_bytes",
    "with_compression",
]
