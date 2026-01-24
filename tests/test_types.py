"""Tests for the type serialization system."""

from __future__ import annotations

import time
from datetime import date, datetime, time as dt_time, timedelta
from decimal import Decimal
from pathlib import Path, PurePath
from typing import Any
from uuid import UUID

import pytest

from auto_mcp.types import (
    AutoCompressRegistry,
    ByteArrayAdapter,
    BytesAdapter,
    CompressedAdapter,
    CompressedData,
    CompressionAlgorithm,
    CompressionConfig,
    ComplexAdapter,
    DateAdapter,
    DateTimeAdapter,
    DecimalAdapter,
    FrozenSetAdapter,
    FunctionAdapter,
    FunctionWrapper,
    ObjectStore,
    ObjectStoreConfig,
    PathAdapter,
    PurePathAdapter,
    SetAdapter,
    StoredObject,
    StoreStats,
    TimeAdapter,
    TimeDeltaAdapter,
    TypeAdapter,
    TypeInfo,
    TypeRegistry,
    TypeStrategy,
    TypeTransformError,
    UUIDAdapter,
    compress_bytes,
    decompress_bytes,
    get_all_adapters,
    get_default_registry,
    get_default_store,
    get_stdlib_adapters,
    is_json_compatible,
    register_all_adapters,
    register_stdlib_adapters,
    set_default_registry,
    set_default_store,
    type_adapter,
    with_compression,
    wrap_function,
)


class TestTypeStrategy:
    """Tests for TypeStrategy enum."""

    def test_strategy_values(self) -> None:
        """Test strategy enum values."""
        assert TypeStrategy.ADAPTER.value == "adapter"
        assert TypeStrategy.OBJECT_STORE.value == "object_store"
        assert TypeStrategy.PASSTHROUGH.value == "passthrough"
        assert TypeStrategy.UNSUPPORTED.value == "unsupported"


class TestTypeInfo:
    """Tests for TypeInfo dataclass."""

    def test_type_info_creation(self) -> None:
        """Test creating TypeInfo."""
        info = TypeInfo(
            type_=int,
            strategy=TypeStrategy.PASSTHROUGH,
            json_schema={"type": "integer"},
        )
        assert info.type_ is int
        assert info.strategy == TypeStrategy.PASSTHROUGH
        assert info.json_schema == {"type": "integer"}

    def test_type_name_property(self) -> None:
        """Test type_name property."""
        info = TypeInfo(type_=datetime, strategy=TypeStrategy.ADAPTER)
        assert "datetime" in info.type_name


class TestObjectStoreConfig:
    """Tests for ObjectStoreConfig dataclass."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = ObjectStoreConfig()
        assert config.ttl == 3600
        assert config.max_instances == 100
        assert config.singleton is False
        assert config.auto_create_tool is True
        assert config.auto_cleanup_tool is True
        assert config.factory is None

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = ObjectStoreConfig(
            ttl=7200,
            max_instances=50,
            singleton=True,
        )
        assert config.ttl == 7200
        assert config.max_instances == 50
        assert config.singleton is True


class TestFunctionAdapter:
    """Tests for FunctionAdapter class."""

    def test_basic_adapter(self) -> None:
        """Test basic function adapter."""
        adapter = FunctionAdapter(
            target_type=datetime,
            serializer=lambda dt: dt.isoformat(),
            deserializer=lambda s: datetime.fromisoformat(s),
            schema={"type": "string", "format": "date-time"},
        )

        now = datetime.now()
        serialized = adapter.serialize(now)
        assert isinstance(serialized, str)

        deserialized = adapter.deserialize(serialized)
        assert isinstance(deserialized, datetime)

    def test_json_schema(self) -> None:
        """Test JSON schema generation."""
        adapter = FunctionAdapter(
            target_type=int,
            serializer=lambda x: x,
            deserializer=lambda x: x,
            schema={"type": "integer"},
        )
        schema = adapter.json_schema()
        assert schema == {"type": "integer"}

    def test_can_serialize(self) -> None:
        """Test can_serialize with custom function."""
        adapter = FunctionAdapter(
            target_type=str,
            serializer=lambda s: s,
            deserializer=lambda s: s,
            can_serialize_fn=lambda s: len(s) < 100,
        )

        assert adapter.can_serialize("short") is True
        assert adapter.can_serialize("x" * 200) is False


class TestTypeAdapterDecorator:
    """Tests for the @type_adapter decorator."""

    def test_decorator(self) -> None:
        """Test creating adapter with decorator."""

        @type_adapter(datetime)
        class CustomDateTimeAdapter:
            def serialize(self, obj: datetime) -> str:
                return obj.isoformat()

            def deserialize(self, data: str) -> datetime:
                return datetime.fromisoformat(data)

            def json_schema(self) -> dict[str, Any]:
                return {"type": "string"}

        adapter = CustomDateTimeAdapter()
        assert adapter.target_type is datetime


class TestIsJsonCompatible:
    """Tests for is_json_compatible function."""

    def test_primitives(self) -> None:
        """Test primitive types."""
        assert is_json_compatible(str) is True
        assert is_json_compatible(int) is True
        assert is_json_compatible(float) is True
        assert is_json_compatible(bool) is True
        assert is_json_compatible(type(None)) is True
        assert is_json_compatible(list) is True
        assert is_json_compatible(dict) is True

    def test_non_compatible(self) -> None:
        """Test non-compatible types."""
        assert is_json_compatible(datetime) is False
        assert is_json_compatible(Path) is False


# ============================================================================
# Type Registry Tests
# ============================================================================


class TestTypeRegistry:
    """Tests for TypeRegistry class."""

    def test_empty_registry(self) -> None:
        """Test empty registry initialization."""
        registry = TypeRegistry()
        assert registry.list_adapters() == []
        assert registry.list_stored_types() == []

    def test_register_adapter(self) -> None:
        """Test registering an adapter."""
        registry = TypeRegistry()
        adapter = DateTimeAdapter()
        registry.register_adapter(adapter)

        assert registry.has_adapter(datetime)
        assert registry.get_adapter(datetime) is adapter

    def test_register_function(self) -> None:
        """Test quick registration with functions."""
        registry = TypeRegistry()
        registry.register(
            Path,
            serialize=lambda p: str(p),
            deserialize=lambda s: Path(s),
            schema={"type": "string"},
        )

        assert registry.has_adapter(Path)

    def test_register_stored_type(self) -> None:
        """Test registering a stored type."""
        registry = TypeRegistry()

        class MyService:
            pass

        registry.register_stored_type(
            MyService,
            ttl=7200,
            max_instances=10,
            singleton=True,
        )

        assert registry.has_store_config(MyService)
        config = registry.get_store_config(MyService)
        assert config is not None
        assert config.ttl == 7200
        assert config.singleton is True

    def test_get_type_info_passthrough(self) -> None:
        """Test getting info for passthrough types."""
        registry = TypeRegistry()
        info = registry.get_type_info(int)

        assert info.strategy == TypeStrategy.PASSTHROUGH
        assert info.json_schema == {"type": "integer"}

    def test_get_type_info_adapter(self) -> None:
        """Test getting info for adapter types."""
        registry = TypeRegistry()
        registry.register_adapter(DateTimeAdapter())

        info = registry.get_type_info(datetime)
        assert info.strategy == TypeStrategy.ADAPTER
        assert info.adapter is not None

    def test_get_type_info_object_store(self) -> None:
        """Test getting info for stored types."""
        registry = TypeRegistry()

        class Session:
            pass

        registry.register_stored_type(Session)

        info = registry.get_type_info(Session)
        assert info.strategy == TypeStrategy.OBJECT_STORE
        assert info.store_config is not None

    def test_serialize(self) -> None:
        """Test serialization via registry."""
        registry = TypeRegistry()
        registry.register_adapter(DateTimeAdapter())

        now = datetime.now()
        serialized = registry.serialize(now)
        assert isinstance(serialized, str)

    def test_deserialize(self) -> None:
        """Test deserialization via registry."""
        registry = TypeRegistry()
        registry.register_adapter(DateTimeAdapter())

        iso_str = "2024-01-15T10:30:00"
        dt = registry.deserialize(iso_str, datetime)
        assert isinstance(dt, datetime)

    def test_get_json_schema(self) -> None:
        """Test getting JSON schema."""
        registry = TypeRegistry()
        registry.register_adapter(DateTimeAdapter())

        schema = registry.get_json_schema(datetime)
        assert "type" in schema

    def test_clear(self) -> None:
        """Test clearing the registry."""
        registry = TypeRegistry()
        registry.register_adapter(DateTimeAdapter())
        registry.clear()

        assert registry.list_adapters() == []

    def test_overwrite_stored_type_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that overwriting stored type config logs a warning (line 141)."""
        import logging

        registry = TypeRegistry()

        class TestStoredType:
            pass

        # Register once
        registry.register_stored_type(TestStoredType)

        # Register again - should warn
        with caplog.at_level(logging.WARNING):
            registry.register_stored_type(TestStoredType)

        # Check for warning message
        assert any("Overwriting" in record.message for record in caplog.records)


class TestDefaultRegistry:
    """Tests for default registry functions."""

    def test_get_default_registry(self) -> None:
        """Test getting default registry."""
        registry = get_default_registry()
        assert isinstance(registry, TypeRegistry)

    def test_set_default_registry(self) -> None:
        """Test setting default registry."""
        new_registry = TypeRegistry()
        set_default_registry(new_registry)
        assert get_default_registry() is new_registry


# ============================================================================
# Object Store Tests
# ============================================================================


class TestStoredObject:
    """Tests for StoredObject dataclass."""

    def test_stored_object_creation(self) -> None:
        """Test creating a stored object."""
        obj = StoredObject(
            obj="test",
            type_name="str",
            created_at=time.time(),
            expires_at=time.time() + 3600,
        )
        assert obj.obj == "test"
        assert obj.access_count == 0

    def test_is_expired(self) -> None:
        """Test expiration check."""
        # Not expired
        obj = StoredObject(
            obj="test",
            type_name="str",
            created_at=time.time(),
            expires_at=time.time() + 3600,
        )
        assert obj.is_expired is False

        # Expired
        obj_expired = StoredObject(
            obj="test",
            type_name="str",
            created_at=time.time() - 7200,
            expires_at=time.time() - 3600,
        )
        assert obj_expired.is_expired is True

        # Never expires
        obj_never = StoredObject(
            obj="test",
            type_name="str",
            created_at=time.time(),
            expires_at=0,
        )
        assert obj_never.is_expired is False

    def test_touch(self) -> None:
        """Test updating access stats."""
        obj = StoredObject(
            obj="test",
            type_name="str",
            created_at=time.time(),
            expires_at=0,
        )
        obj.touch()
        assert obj.access_count == 1
        assert obj.last_accessed > 0


class TestStoreStats:
    """Tests for StoreStats dataclass."""

    def test_default_stats(self) -> None:
        """Test default stats."""
        stats = StoreStats()
        assert stats.total_objects == 0
        assert stats.by_type == {}
        assert stats.expired_count == 0


class TestObjectStore:
    """Tests for ObjectStore class."""

    def test_store_and_get(self) -> None:
        """Test storing and retrieving objects."""
        store = ObjectStore()
        handle = store.store("test_value")

        assert store.exists(handle)
        assert store.get(handle) == "test_value"

    def test_store_with_ttl(self) -> None:
        """Test storing with TTL."""
        store = ObjectStore()
        handle = store.store("test", ttl=3600)

        info = store.get_info(handle)
        assert info["ttl_remaining"] is not None
        assert info["ttl_remaining"] > 0

    def test_store_custom_handle(self) -> None:
        """Test storing with custom handle."""
        store = ObjectStore()
        handle = store.store("test", handle="custom:handle")

        assert handle == "custom:handle"
        assert store.get(handle) == "test"

    def test_get_typed(self) -> None:
        """Test typed retrieval."""
        store = ObjectStore()
        handle = store.store("test")

        value = store.get_typed(handle, str)
        assert value == "test"

        with pytest.raises(TypeError):
            store.get_typed(handle, int)

    def test_release(self) -> None:
        """Test releasing objects."""
        store = ObjectStore()
        handle = store.store("test")

        assert store.release(handle) is True
        assert store.exists(handle) is False
        assert store.release(handle) is False

    def test_list_handles(self) -> None:
        """Test listing handles."""
        store = ObjectStore()
        h1 = store.store("test1")
        h2 = store.store("test2")

        handles = store.list_handles()
        assert h1 in handles
        assert h2 in handles

    def test_count(self) -> None:
        """Test counting objects."""
        store = ObjectStore()
        store.store("test1")
        store.store("test2")

        assert store.count() == 2

    def test_get_stats(self) -> None:
        """Test getting statistics."""
        store = ObjectStore()
        store.store("test1")
        store.store("test2")

        stats = store.get_stats()
        assert stats.total_objects == 2

    def test_cleanup(self) -> None:
        """Test cleanup of expired objects."""
        store = ObjectStore(auto_cleanup=False)
        handle = store.store("test", ttl=0)  # Expires immediately

        # Manually expire the object
        store._objects[handle].expires_at = time.time() - 1

        removed = store.cleanup()
        assert removed == 1

    def test_clear(self) -> None:
        """Test clearing all objects."""
        store = ObjectStore()
        store.store("test1")
        store.store("test2")

        count = store.clear()
        assert count == 2
        assert store.count() == 0

    def test_singleton_type(self) -> None:
        """Test singleton type constraint."""
        store = ObjectStore()
        config = ObjectStoreConfig(singleton=True)
        store.configure_type(str, config)

        h1 = store.store("first")
        h2 = store.store("second")

        # Should return same handle for singleton
        assert h1 == h2

    def test_max_instances(self) -> None:
        """Test max instances constraint."""
        store = ObjectStore()
        config = ObjectStoreConfig(max_instances=2)
        store.configure_type(str, config)

        store.store("first")
        store.store("second")

        with pytest.raises(ValueError, match="Maximum instances"):
            store.store("third")

    def test_key_not_found(self) -> None:
        """Test KeyError for missing handle."""
        store = ObjectStore()

        with pytest.raises(KeyError):
            store.get("nonexistent")

    def test_expired_object_access(self) -> None:
        """Test accessing expired objects."""
        store = ObjectStore(auto_cleanup=False)
        handle = store.store("test", ttl=1)

        # Manually expire
        store._objects[handle].expires_at = time.time() - 1

        with pytest.raises(ValueError, match="expired"):
            store.get(handle)

    def test_exists_with_expired_object(self) -> None:
        """Test exists() removes expired objects (lines 278-279)."""
        store = ObjectStore(auto_cleanup=False)
        handle = store.store("test", ttl=1)

        # Verify it exists
        assert store.exists(handle) is True

        # Manually expire
        store._objects[handle].expires_at = time.time() - 1

        # exists() should return False and remove the expired object
        assert store.exists(handle) is False
        # The handle should now be gone
        assert handle not in store._objects


class TestDefaultStore:
    """Tests for default store functions."""

    def test_get_default_store(self) -> None:
        """Test getting default store."""
        store = get_default_store()
        assert isinstance(store, ObjectStore)

    def test_set_default_store(self) -> None:
        """Test setting default store."""
        new_store = ObjectStore()
        set_default_store(new_store)
        assert get_default_store() is new_store


# ============================================================================
# Built-in Adapter Tests
# ============================================================================


class TestDateTimeAdapter:
    """Tests for DateTimeAdapter."""

    def test_serialize(self) -> None:
        """Test serialization."""
        adapter = DateTimeAdapter()
        dt = datetime(2024, 1, 15, 10, 30, 0)
        serialized = adapter.serialize(dt)
        assert serialized == "2024-01-15T10:30:00"

    def test_deserialize(self) -> None:
        """Test deserialization."""
        adapter = DateTimeAdapter()
        dt = adapter.deserialize("2024-01-15T10:30:00")
        assert dt == datetime(2024, 1, 15, 10, 30, 0)

    def test_json_schema(self) -> None:
        """Test JSON schema."""
        adapter = DateTimeAdapter()
        schema = adapter.json_schema()
        assert schema["type"] == "string"
        assert schema["format"] == "date-time"


class TestDateAdapter:
    """Tests for DateAdapter."""

    def test_roundtrip(self) -> None:
        """Test serialize/deserialize roundtrip."""
        adapter = DateAdapter()
        d = date(2024, 1, 15)
        serialized = adapter.serialize(d)
        deserialized = adapter.deserialize(serialized)
        assert deserialized == d


class TestTimeAdapter:
    """Tests for TimeAdapter."""

    def test_roundtrip(self) -> None:
        """Test serialize/deserialize roundtrip."""
        adapter = TimeAdapter()
        t = dt_time(10, 30, 0)
        serialized = adapter.serialize(t)
        deserialized = adapter.deserialize(serialized)
        assert deserialized == t


class TestTimeDeltaAdapter:
    """Tests for TimeDeltaAdapter."""

    def test_roundtrip(self) -> None:
        """Test serialize/deserialize roundtrip."""
        adapter = TimeDeltaAdapter()
        td = timedelta(hours=2, minutes=30)
        serialized = adapter.serialize(td)
        assert serialized == td.total_seconds()
        deserialized = adapter.deserialize(serialized)
        assert deserialized == td


class TestPathAdapter:
    """Tests for PathAdapter."""

    def test_roundtrip(self) -> None:
        """Test serialize/deserialize roundtrip."""
        adapter = PathAdapter()
        p = Path("/home/user/file.txt")
        serialized = adapter.serialize(p)
        assert serialized == "/home/user/file.txt"
        deserialized = adapter.deserialize(serialized)
        assert deserialized == p


class TestPurePathAdapter:
    """Tests for PurePathAdapter."""

    def test_roundtrip(self) -> None:
        """Test serialize/deserialize roundtrip."""
        adapter = PurePathAdapter()
        p = PurePath("/home/user/file.txt")
        serialized = adapter.serialize(p)
        deserialized = adapter.deserialize(serialized)
        assert str(deserialized) == str(p)


class TestUUIDAdapter:
    """Tests for UUIDAdapter."""

    def test_roundtrip(self) -> None:
        """Test serialize/deserialize roundtrip."""
        adapter = UUIDAdapter()
        u = UUID("12345678-1234-5678-1234-567812345678")
        serialized = adapter.serialize(u)
        assert serialized == "12345678-1234-5678-1234-567812345678"
        deserialized = adapter.deserialize(serialized)
        assert deserialized == u


class TestDecimalAdapter:
    """Tests for DecimalAdapter."""

    def test_roundtrip(self) -> None:
        """Test serialize/deserialize roundtrip."""
        adapter = DecimalAdapter()
        d = Decimal("123.456")
        serialized = adapter.serialize(d)
        assert serialized == "123.456"
        deserialized = adapter.deserialize(serialized)
        assert deserialized == d


class TestBytesAdapter:
    """Tests for BytesAdapter."""

    def test_roundtrip(self) -> None:
        """Test serialize/deserialize roundtrip."""
        adapter = BytesAdapter()
        b = b"hello world"
        serialized = adapter.serialize(b)
        assert isinstance(serialized, str)
        deserialized = adapter.deserialize(serialized)
        assert deserialized == b

    def test_max_size(self) -> None:
        """Test max size constraint."""
        adapter = BytesAdapter(max_size=10)
        assert adapter.can_serialize(b"short") is True
        assert adapter.can_serialize(b"x" * 20) is False


class TestByteArrayAdapter:
    """Tests for ByteArrayAdapter."""

    def test_roundtrip(self) -> None:
        """Test serialize/deserialize roundtrip."""
        adapter = ByteArrayAdapter()
        ba = bytearray(b"hello world")
        serialized = adapter.serialize(ba)
        deserialized = adapter.deserialize(serialized)
        assert deserialized == ba


class TestSetAdapter:
    """Tests for SetAdapter."""

    def test_roundtrip(self) -> None:
        """Test serialize/deserialize roundtrip."""
        adapter = SetAdapter()
        s = {1, 2, 3}
        serialized = adapter.serialize(s)
        assert isinstance(serialized, list)
        deserialized = adapter.deserialize(serialized)
        assert deserialized == s


class TestFrozenSetAdapter:
    """Tests for FrozenSetAdapter."""

    def test_roundtrip(self) -> None:
        """Test serialize/deserialize roundtrip."""
        adapter = FrozenSetAdapter()
        fs = frozenset({1, 2, 3})
        serialized = adapter.serialize(fs)
        deserialized = adapter.deserialize(serialized)
        assert deserialized == fs


class TestComplexAdapter:
    """Tests for ComplexAdapter."""

    def test_roundtrip(self) -> None:
        """Test serialize/deserialize roundtrip."""
        adapter = ComplexAdapter()
        c = complex(3, 4)
        serialized = adapter.serialize(c)
        assert serialized == {"real": 3.0, "imag": 4.0}
        deserialized = adapter.deserialize(serialized)
        assert deserialized == c


class TestAdapterHelpers:
    """Tests for adapter helper functions."""

    def test_get_stdlib_adapters(self) -> None:
        """Test getting stdlib adapters."""
        adapters = get_stdlib_adapters()
        assert len(adapters) > 0
        assert any(isinstance(a, DateTimeAdapter) for a in adapters)

    def test_get_all_adapters(self) -> None:
        """Test getting all adapters."""
        adapters = get_all_adapters()
        assert len(adapters) >= len(get_stdlib_adapters())

    def test_register_stdlib_adapters(self) -> None:
        """Test registering stdlib adapters."""
        registry = TypeRegistry()
        register_stdlib_adapters(registry)
        assert registry.has_adapter(datetime)
        assert registry.has_adapter(Path)

    def test_register_all_adapters(self) -> None:
        """Test registering all adapters."""
        registry = TypeRegistry()
        register_all_adapters(registry)
        assert registry.has_adapter(datetime)


# ============================================================================
# Function Wrapper Tests
# ============================================================================


class TestFunctionWrapper:
    """Tests for FunctionWrapper class."""

    def test_basic_wrapping(self) -> None:
        """Test basic function wrapping."""

        def add(a: int, b: int) -> int:
            return a + b

        wrapper = FunctionWrapper(add)
        result = wrapper.call({"a": 1, "b": 2})
        assert result == 3

    def test_type_transformation(self) -> None:
        """Test type transformation with adapters."""
        registry = TypeRegistry()
        register_stdlib_adapters(registry)

        def get_date_str(d: datetime) -> str:
            return d.strftime("%Y-%m-%d")

        wrapper = FunctionWrapper(get_date_str, registry=registry)

        # Call with serialized datetime
        result = wrapper.call({"d": "2024-01-15T10:30:00"})
        assert result == "2024-01-15"

    def test_get_json_schema(self) -> None:
        """Test getting JSON schema for parameters."""

        def func(name: str, count: int) -> dict:
            return {"name": name, "count": count}

        wrapper = FunctionWrapper(func)
        schema = wrapper.get_json_schema()

        assert "properties" in schema
        assert "name" in schema["properties"]
        assert "count" in schema["properties"]
        assert "required" in schema

    def test_wrap_function_helper(self) -> None:
        """Test wrap_function convenience function."""

        def greet(name: str) -> str:
            return f"Hello, {name}!"

        wrapper = wrap_function(greet)
        result = wrapper.call({"name": "World"})
        assert result == "Hello, World!"

    def test_transform_error(self) -> None:
        """Test TypeTransformError."""
        error = TypeTransformError("Test error", param_name="test")
        assert str(error) == "Test error"
        assert error.param_name == "test"


class TestTypeTransformError:
    """Tests for TypeTransformError."""

    def test_error_creation(self) -> None:
        """Test creating transform error."""
        error = TypeTransformError(
            "Failed to transform",
            param_name="data",
            original_error=ValueError("invalid"),
        )
        assert "Failed to transform" in str(error)
        assert error.param_name == "data"
        assert isinstance(error.original_error, ValueError)


# ============================================================================
# Compression Tests
# ============================================================================


class TestCompressionAlgorithm:
    """Tests for CompressionAlgorithm enum."""

    def test_algorithm_values(self) -> None:
        """Test algorithm enum values."""
        assert CompressionAlgorithm.GZIP.value == "gzip"
        assert CompressionAlgorithm.ZLIB.value == "zlib"
        assert CompressionAlgorithm.LZ4.value == "lz4"
        assert CompressionAlgorithm.NONE.value == "none"


class TestCompressionConfig:
    """Tests for CompressionConfig dataclass."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = CompressionConfig()
        assert config.enabled is True
        assert config.algorithm == CompressionAlgorithm.GZIP
        assert config.threshold == 1024
        assert config.level == 6

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = CompressionConfig(
            enabled=True,
            algorithm=CompressionAlgorithm.ZLIB,
            threshold=2048,
            level=9,
        )
        assert config.algorithm == CompressionAlgorithm.ZLIB
        assert config.threshold == 2048
        assert config.level == 9


class TestCompressedData:
    """Tests for CompressedData dataclass."""

    def test_to_dict(self) -> None:
        """Test converting to dict."""
        data = CompressedData(
            compressed=True,
            algorithm="gzip",
            original_size=1000,
            compressed_size=500,
            data="SGVsbG8=",
        )
        d = data.to_dict()
        assert d["compressed"] is True
        assert d["algorithm"] == "gzip"
        assert d["original_size"] == 1000
        assert d["compressed_size"] == 500
        assert d["compression_ratio"] == 0.5

    def test_from_dict(self) -> None:
        """Test creating from dict."""
        d = {
            "compressed": True,
            "algorithm": "gzip",
            "original_size": 1000,
            "compressed_size": 500,
            "data": "SGVsbG8=",
        }
        data = CompressedData.from_dict(d)
        assert data.compressed is True
        assert data.algorithm == "gzip"


class TestCompressionFunctions:
    """Tests for compression utility functions."""

    def test_compress_decompress_gzip(self) -> None:
        """Test gzip compression roundtrip."""
        original = b"Hello, World! " * 100
        compressed = compress_bytes(original, CompressionAlgorithm.GZIP)
        decompressed = decompress_bytes(compressed, CompressionAlgorithm.GZIP)
        assert decompressed == original
        assert len(compressed) < len(original)

    def test_compress_decompress_zlib(self) -> None:
        """Test zlib compression roundtrip."""
        original = b"Test data " * 100
        compressed = compress_bytes(original, CompressionAlgorithm.ZLIB)
        decompressed = decompress_bytes(compressed, CompressionAlgorithm.ZLIB)
        assert decompressed == original
        assert len(compressed) < len(original)

    def test_compress_none(self) -> None:
        """Test no compression."""
        original = b"Hello"
        result = compress_bytes(original, CompressionAlgorithm.NONE)
        assert result == original


class TestCompressedAdapter:
    """Tests for CompressedAdapter."""

    def test_small_data_not_compressed(self) -> None:
        """Test that small data is not compressed."""
        adapter = DateTimeAdapter()
        config = CompressionConfig(threshold=10000)  # High threshold
        compressed = CompressedAdapter(adapter, config)

        dt = datetime(2024, 1, 15, 10, 30, 0)
        result = compressed.serialize(dt)

        assert isinstance(result, dict)
        assert result["compressed"] is False

    def test_large_data_compressed(self) -> None:
        """Test that large data is compressed."""
        # Create a simple adapter for strings
        adapter = FunctionAdapter(
            target_type=str,
            serializer=lambda s: s,
            deserializer=lambda s: s,
            schema={"type": "string"},
        )
        config = CompressionConfig(threshold=100)  # Low threshold
        compressed = CompressedAdapter(adapter, config)

        # Create a large string
        large_string = "x" * 1000
        result = compressed.serialize(large_string)

        assert isinstance(result, dict)
        assert result["compressed"] is True
        assert result["compressed_size"] < result["original_size"]

    def test_roundtrip(self) -> None:
        """Test serialize/deserialize roundtrip."""
        adapter = DateTimeAdapter()
        config = CompressionConfig(threshold=1)  # Force compression
        compressed = CompressedAdapter(adapter, config)

        dt = datetime(2024, 1, 15, 10, 30, 0)
        serialized = compressed.serialize(dt)
        deserialized = compressed.deserialize(serialized)

        assert deserialized == dt

    def test_deserialize_uncompressed(self) -> None:
        """Test deserializing uncompressed data."""
        adapter = DateTimeAdapter()
        compressed = CompressedAdapter(adapter)

        # Pass through non-compressed data
        result = compressed.deserialize("2024-01-15T10:30:00")
        assert result == datetime(2024, 1, 15, 10, 30, 0)

    def test_json_schema(self) -> None:
        """Test JSON schema generation."""
        adapter = DateTimeAdapter()
        compressed = CompressedAdapter(adapter)

        schema = compressed.json_schema()
        assert "properties" in schema
        assert "compressed" in schema["properties"]
        assert "algorithm" in schema["properties"]
        assert "data" in schema["properties"]

    def test_can_serialize(self) -> None:
        """Test can_serialize delegation."""
        adapter = DateTimeAdapter()
        compressed = CompressedAdapter(adapter)

        assert compressed.can_serialize(datetime.now()) is True


class TestWithCompression:
    """Tests for with_compression helper function."""

    def test_with_compression(self) -> None:
        """Test convenience wrapper function."""
        adapter = DateTimeAdapter()
        compressed = with_compression(adapter, threshold=100)

        assert isinstance(compressed, CompressedAdapter)
        assert compressed.config.threshold == 100


class TestAutoCompressRegistry:
    """Tests for AutoCompressRegistry."""

    def test_register_large_type(self) -> None:
        """Test registering large types."""
        registry = AutoCompressRegistry()

        class LargeData:
            pass

        registry.register_large_type(LargeData)

    def test_wrap_adapter(self) -> None:
        """Test wrapping adapters."""
        registry = AutoCompressRegistry()
        adapter = DateTimeAdapter()

        # Not registered as large, should return as-is
        wrapped = registry.wrap_adapter(adapter)
        assert wrapped is adapter

    def test_wrap_if_large(self) -> None:
        """Test explicitly wrapping with compression."""
        registry = AutoCompressRegistry()
        adapter = DateTimeAdapter()

        wrapped = registry.wrap_if_large(adapter, threshold=500)
        assert isinstance(wrapped, CompressedAdapter)
        assert wrapped.config.threshold == 500

    def test_wrap_adapter_for_registered_large_type(self) -> None:
        """Test wrapping adapters for registered large types."""
        registry = AutoCompressRegistry()
        adapter = DateTimeAdapter()

        # Register datetime as a large type
        registry.register_large_type(datetime)

        wrapped = registry.wrap_adapter(adapter)
        assert isinstance(wrapped, CompressedAdapter)

    def test_wrap_adapter_disabled(self) -> None:
        """Test wrapping when compression is disabled."""
        config = CompressionConfig(enabled=False)
        registry = AutoCompressRegistry(config=config)
        adapter = DateTimeAdapter()

        # Register datetime as large but compression disabled
        registry.register_large_type(datetime)

        wrapped = registry.wrap_adapter(adapter)
        assert wrapped is adapter  # Should return as-is


# ============================================================================
# Extended FunctionWrapper Tests
# ============================================================================


class TestFunctionWrapperExtended:
    """Extended tests for FunctionWrapper to improve coverage."""

    def test_function_with_no_type_hints(self) -> None:
        """Test wrapping function without type hints."""

        def no_hints(x, y):
            return x + y

        wrapper = FunctionWrapper(no_hints)
        result = wrapper.call({"x": 1, "y": 2})
        assert result == 3

    def test_function_with_defaults(self) -> None:
        """Test wrapping function with default parameters."""

        def with_defaults(name: str, count: int = 5) -> str:
            return name * count

        wrapper = FunctionWrapper(with_defaults)
        schema = wrapper.get_json_schema()

        # name should be required, count should not
        assert "name" in schema["required"]
        assert "count" not in schema["required"]

    def test_get_return_schema_no_return_type(self) -> None:
        """Test getting return schema when no return type."""

        def no_return(x: int) -> None:
            pass

        wrapper = FunctionWrapper(no_return)
        schema = wrapper.get_return_schema()
        assert schema == {}

    def test_get_return_schema_with_return_type(self) -> None:
        """Test getting return schema with return type."""

        def with_return(x: int) -> str:
            return str(x)

        wrapper = FunctionWrapper(with_return)
        schema = wrapper.get_return_schema()
        assert "type" in schema

    def test_transform_input_no_info(self) -> None:
        """Test transform_input when parameter has no type info."""

        def func(x):
            return x

        wrapper = FunctionWrapper(func)
        result = wrapper.transform_input("x", 42)
        assert result == 42

    def test_transform_input_with_error(self) -> None:
        """Test transform_input raises TypeTransformError on failure."""
        registry = TypeRegistry()

        # Create a broken adapter
        adapter = FunctionAdapter(
            target_type=datetime,
            serializer=lambda dt: dt.isoformat(),
            deserializer=lambda s: datetime.fromisoformat(s),
            schema={"type": "string"},
        )
        registry.register_adapter(adapter)

        def func(d: datetime) -> str:
            return str(d)

        wrapper = FunctionWrapper(func, registry=registry)

        with pytest.raises(TypeTransformError):
            wrapper.transform_input("d", "not-a-date")

    def test_transform_output_none(self) -> None:
        """Test transform_output with None value."""

        def returns_none() -> None:
            return None

        wrapper = FunctionWrapper(returns_none)
        result = wrapper.transform_output(None)
        assert result is None

    def test_transform_output_with_adapter(self) -> None:
        """Test transform_output with adapter type."""
        registry = TypeRegistry()
        register_stdlib_adapters(registry)

        def get_date() -> datetime:
            return datetime(2024, 1, 15, 10, 30, 0)

        wrapper = FunctionWrapper(get_date, registry=registry)
        result = wrapper.transform_output(datetime(2024, 1, 15, 10, 30, 0))
        assert result == "2024-01-15T10:30:00"

    def test_transform_output_passthrough(self) -> None:
        """Test transform_output with passthrough type."""

        def get_dict() -> dict:
            return {"a": 1}

        wrapper = FunctionWrapper(get_dict)
        result = wrapper.transform_output({"a": 1})
        assert result == {"a": 1}

    def test_transform_output_object_store(self) -> None:
        """Test transform_output with object store type."""
        registry = TypeRegistry()
        store = ObjectStore()

        class Session:
            pass

        registry.register_stored_type(Session, ttl=3600)

        # Use wrapper's call method which handles the full flow
        def create_session() -> dict:
            return {"created": True}

        wrapper = FunctionWrapper(create_session, registry=registry, store=store)

        # Test _apply_output_transform directly with OBJECT_STORE strategy
        info = registry.get_type_info(Session)
        assert info.strategy == TypeStrategy.OBJECT_STORE

        session = Session()
        result = wrapper._apply_output_transform(info, session)

        # Should return a handle string
        assert isinstance(result, str)
        assert store.exists(result)

    def test_auto_serialize_output_list(self) -> None:
        """Test auto-serialization of lists."""

        def get_list():
            return [datetime(2024, 1, 15), datetime(2024, 1, 16)]

        registry = TypeRegistry()
        register_stdlib_adapters(registry)
        wrapper = FunctionWrapper(get_list, registry=registry)

        result = wrapper._auto_serialize_output([datetime(2024, 1, 15)])
        assert isinstance(result, list)
        # Should serialize datetime to string
        assert result[0] == "2024-01-15T00:00:00"

    def test_auto_serialize_output_dict(self) -> None:
        """Test auto-serialization of dicts."""
        registry = TypeRegistry()
        register_stdlib_adapters(registry)
        wrapper = FunctionWrapper(lambda: None, registry=registry)

        result = wrapper._auto_serialize_output({"date": datetime(2024, 1, 15)})
        assert result == {"date": "2024-01-15T00:00:00"}

    def test_auto_serialize_output_unknown_type(self) -> None:
        """Test auto-serialization of unknown types falls back to str."""

        class CustomType:
            def __str__(self) -> str:
                return "custom"

        wrapper = FunctionWrapper(lambda: None)
        result = wrapper._auto_serialize_output(CustomType())
        assert result == "custom"

    def test_call_with_transform_disabled(self) -> None:
        """Test call with input/output transforms disabled."""

        def add(a: int, b: int) -> int:
            return a + b

        wrapper = FunctionWrapper(add, transform_inputs=False, transform_output=False)
        result = wrapper.call({"a": 1, "b": 2})
        assert result == 3

    def test_direct_call(self) -> None:
        """Test direct __call__ method."""

        def multiply(a: int, b: int) -> int:
            return a * b

        wrapper = FunctionWrapper(multiply)
        result = wrapper(3, 4)
        assert result == 12

    def test_direct_call_with_type_transform(self) -> None:
        """Test direct __call__ with type transformation."""
        registry = TypeRegistry()
        register_stdlib_adapters(registry)

        def get_day(d: datetime) -> int:
            return d.day

        wrapper = FunctionWrapper(get_day, registry=registry)
        # Pass actual datetime object
        result = wrapper(datetime(2024, 1, 15))
        assert result == 15

    def test_maybe_serialize_input_json_types(self) -> None:
        """Test _maybe_serialize_input with JSON-compatible types."""

        def func(x: str) -> str:
            return x

        wrapper = FunctionWrapper(func)

        # All these should pass through
        assert wrapper._maybe_serialize_input("x", None) is None
        assert wrapper._maybe_serialize_input("x", True) is True
        assert wrapper._maybe_serialize_input("x", 42) == 42
        assert wrapper._maybe_serialize_input("x", 3.14) == 3.14
        assert wrapper._maybe_serialize_input("x", "hello") == "hello"
        assert wrapper._maybe_serialize_input("x", [1, 2]) == [1, 2]
        assert wrapper._maybe_serialize_input("x", {"a": 1}) == {"a": 1}

    def test_maybe_serialize_input_with_adapter(self) -> None:
        """Test _maybe_serialize_input with adapter types."""
        registry = TypeRegistry()
        register_stdlib_adapters(registry)

        def func(d: datetime) -> str:
            return str(d)

        wrapper = FunctionWrapper(func, registry=registry)

        # Pass actual datetime - should serialize it
        dt = datetime(2024, 1, 15)
        result = wrapper._maybe_serialize_input("d", dt)
        assert result == "2024-01-15T00:00:00"

    def test_maybe_serialize_input_no_info(self) -> None:
        """Test _maybe_serialize_input with no param info."""

        class CustomType:
            pass

        def func(x):
            return x

        wrapper = FunctionWrapper(func)
        obj = CustomType()
        result = wrapper._maybe_serialize_input("x", obj)
        assert result is obj


class TestAsyncFunctionWrapper:
    """Tests for async function wrapping."""

    @pytest.mark.asyncio
    async def test_call_async(self) -> None:
        """Test call_async method."""

        async def async_add(a: int, b: int) -> int:
            return a + b

        wrapper = FunctionWrapper(async_add)
        result = await wrapper.call_async({"a": 1, "b": 2})
        assert result == 3

    @pytest.mark.asyncio
    async def test_call_async_with_transforms(self) -> None:
        """Test call_async with type transforms."""
        registry = TypeRegistry()
        register_stdlib_adapters(registry)

        async def async_get_day(d: datetime) -> int:
            return d.day

        wrapper = FunctionWrapper(async_get_day, registry=registry)
        result = await wrapper.call_async({"d": "2024-01-15T10:30:00"})
        assert result == 15

    @pytest.mark.asyncio
    async def test_call_async_no_transform(self) -> None:
        """Test call_async with transforms disabled."""

        async def async_double(x: int) -> int:
            return x * 2

        wrapper = FunctionWrapper(
            async_double, transform_inputs=False, transform_output=False
        )
        result = await wrapper.call_async({"x": 5})
        assert result == 10


class TestAutoTransformDecorator:
    """Tests for the auto_transform decorator."""

    def test_auto_transform_basic(self) -> None:
        """Test basic auto_transform decorator usage."""
        from auto_mcp.types import auto_transform

        @auto_transform()
        def greet(name: str) -> str:
            return f"Hello, {name}!"

        result = greet.call({"name": "World"})
        assert result == "Hello, World!"

    def test_auto_transform_with_registry(self) -> None:
        """Test auto_transform with custom registry."""
        from auto_mcp.types import auto_transform

        registry = TypeRegistry()
        register_stdlib_adapters(registry)

        @auto_transform(registry=registry)
        def get_day(d: datetime) -> int:
            return d.day

        result = get_day.call({"d": "2024-01-15T10:30:00"})
        assert result == 15


# ============================================================================
# MethodWrapper and ClassWrapper Tests
# ============================================================================


class TestMethodWrapper:
    """Tests for MethodWrapper class."""

    def test_method_wrapper_basic(self) -> None:
        """Test basic method wrapping."""
        from auto_mcp.types.wrapper import MethodWrapper

        class Calculator:
            def add(self, a: int, b: int) -> int:
                return a + b

        calc = Calculator()
        wrapper = MethodWrapper(Calculator.add, calc)
        result = wrapper.call({"a": 1, "b": 2})
        assert result == 3

    def test_method_wrapper_with_registry(self) -> None:
        """Test method wrapper with type registry."""
        from auto_mcp.types.wrapper import MethodWrapper

        registry = TypeRegistry()
        register_stdlib_adapters(registry)

        class DateFormatter:
            def format_date(self, d: datetime) -> str:
                return d.strftime("%Y-%m-%d")

        formatter = DateFormatter()
        wrapper = MethodWrapper(DateFormatter.format_date, formatter, registry=registry)
        result = wrapper.call({"d": "2024-01-15T10:30:00"})
        assert result == "2024-01-15"


class TestClassWrapper:
    """Tests for ClassWrapper class."""

    def test_class_wrapper_basic(self) -> None:
        """Test basic class wrapping."""
        from auto_mcp.types.wrapper import ClassWrapper

        class Calculator:
            def add(self, a: int, b: int) -> int:
                return a + b

            def multiply(self, a: int, b: int) -> int:
                return a * b

        wrapper = ClassWrapper(Calculator)
        instance = wrapper.create()

        result = wrapper.call_method(instance, "add", {"a": 3, "b": 4})
        assert result == 7

        result = wrapper.call_method(instance, "multiply", {"a": 3, "b": 4})
        assert result == 12

    def test_class_wrapper_get_method_names(self) -> None:
        """Test getting method names from class wrapper."""
        from auto_mcp.types.wrapper import ClassWrapper

        class MyClass:
            def public_method(self) -> str:
                return "public"

            def _private_method(self) -> str:
                return "private"

        wrapper = ClassWrapper(MyClass)
        names = wrapper.get_method_names()

        assert "public_method" in names
        assert "_private_method" not in names

    def test_class_wrapper_get_method_schema(self) -> None:
        """Test getting method schema from class wrapper."""
        from auto_mcp.types.wrapper import ClassWrapper

        class MyClass:
            def process(self, name: str, count: int) -> dict:
                return {"name": name, "count": count}

        wrapper = ClassWrapper(MyClass)
        schema = wrapper.get_method_schema("process")

        assert "properties" in schema
        assert "name" in schema["properties"]
        assert "count" in schema["properties"]

    def test_class_wrapper_method_not_found(self) -> None:
        """Test error when method not found."""
        from auto_mcp.types.wrapper import ClassWrapper

        class MyClass:
            def exists(self) -> str:
                return "yes"

        wrapper = ClassWrapper(MyClass)

        with pytest.raises(KeyError, match="Method not found"):
            wrapper.get_method_schema("nonexistent")

        with pytest.raises(KeyError, match="Method not found"):
            wrapper.call_method(wrapper.create(), "nonexistent", {})

    def test_class_wrapper_create_with_init_kwargs(self) -> None:
        """Test creating instance with init kwargs."""
        from auto_mcp.types.wrapper import ClassWrapper

        class Greeter:
            def __init__(self, prefix: str) -> None:
                self.prefix = prefix

            def greet(self, name: str) -> str:
                return f"{self.prefix} {name}"

        wrapper = ClassWrapper(Greeter)
        instance = wrapper.create({"prefix": "Hello"})

        result = wrapper.call_method(instance, "greet", {"name": "World"})
        assert result == "Hello World"

    def test_class_wrapper_with_type_transforms(self) -> None:
        """Test class wrapper with type transformations."""
        from auto_mcp.types.wrapper import ClassWrapper

        registry = TypeRegistry()
        register_stdlib_adapters(registry)

        class DateProcessor:
            def get_year(self, d: datetime) -> int:
                return d.year

        wrapper = ClassWrapper(DateProcessor, registry=registry)
        instance = wrapper.create()

        result = wrapper.call_method(instance, "get_year", {"d": "2024-01-15T10:30:00"})
        assert result == 2024


class TestFunctionWrapperSessionInjection:
    """Tests for FunctionWrapper session injection."""

    @pytest.mark.asyncio
    async def test_call_with_session_injection(self) -> None:
        """Test FunctionWrapper.call() with session injection."""
        from auto_mcp.session.context import SessionContext
        from auto_mcp.session.manager import SessionManager
        from auto_mcp.types.wrapper import FunctionWrapper

        manager = SessionManager()
        session = await manager.create_session()

        def session_aware_func(session: SessionContext, x: int) -> str:
            return f"session:{session.session_id}, x:{x}"

        wrapper = FunctionWrapper(
            session_aware_func,
            session_manager=manager,
            session_param_name="session",
        )

        result = wrapper.call({"session_id": session.session_id, "x": 42})
        assert f"session:{session.session_id}" in result
        assert "x:42" in result

    @pytest.mark.asyncio
    async def test_call_with_session_missing_session_id(self) -> None:
        """Test FunctionWrapper.call() raises error when session_id is missing."""
        from auto_mcp.session.context import SessionContext
        from auto_mcp.session.manager import SessionManager
        from auto_mcp.types.wrapper import FunctionWrapper

        manager = SessionManager()

        def session_aware_func(session: SessionContext, x: int) -> str:
            return "result"

        wrapper = FunctionWrapper(
            session_aware_func,
            session_manager=manager,
            session_param_name="session",
        )

        with pytest.raises(ValueError, match="session_id is required"):
            wrapper.call({"x": 42})

    @pytest.mark.asyncio
    async def test_call_with_session_invalid_session_id_type(self) -> None:
        """Test FunctionWrapper.call() raises error for non-string session_id."""
        from auto_mcp.session.context import SessionContext
        from auto_mcp.session.manager import SessionManager
        from auto_mcp.types.wrapper import FunctionWrapper

        manager = SessionManager()

        def session_aware_func(session: SessionContext, x: int) -> str:
            return "result"

        wrapper = FunctionWrapper(
            session_aware_func,
            session_manager=manager,
            session_param_name="session",
        )

        with pytest.raises(TypeError, match="session_id must be a string"):
            wrapper.call({"session_id": 123, "x": 42})

    @pytest.mark.asyncio
    async def test_call_async_with_session_injection(self) -> None:
        """Test FunctionWrapper.call_async() with session injection."""
        from auto_mcp.session.context import SessionContext
        from auto_mcp.session.manager import SessionManager
        from auto_mcp.types.wrapper import FunctionWrapper

        manager = SessionManager()
        session = await manager.create_session()

        async def async_session_func(session: SessionContext, x: int) -> str:
            return f"async session:{session.session_id}, x:{x}"

        wrapper = FunctionWrapper(
            async_session_func,
            session_manager=manager,
            session_param_name="session",
        )

        result = await wrapper.call_async({"session_id": session.session_id, "x": 99})
        assert f"session:{session.session_id}" in result
        assert "x:99" in result

    @pytest.mark.asyncio
    async def test_call_async_missing_session_id(self) -> None:
        """Test FunctionWrapper.call_async() raises error when session_id is missing."""
        from auto_mcp.session.context import SessionContext
        from auto_mcp.session.manager import SessionManager
        from auto_mcp.types.wrapper import FunctionWrapper

        manager = SessionManager()

        async def async_session_func(session: SessionContext, x: int) -> str:
            return "result"

        wrapper = FunctionWrapper(
            async_session_func,
            session_manager=manager,
            session_param_name="session",
        )

        with pytest.raises(ValueError, match="session_id is required"):
            await wrapper.call_async({"x": 42})

    @pytest.mark.asyncio
    async def test_call_async_invalid_session_id_type(self) -> None:
        """Test FunctionWrapper.call_async() raises error for non-string session_id."""
        from auto_mcp.session.context import SessionContext
        from auto_mcp.session.manager import SessionManager
        from auto_mcp.types.wrapper import FunctionWrapper

        manager = SessionManager()

        async def async_session_func(session: SessionContext, x: int) -> str:
            return "result"

        wrapper = FunctionWrapper(
            async_session_func,
            session_manager=manager,
            session_param_name="session",
        )

        with pytest.raises(TypeError, match="session_id must be a string"):
            await wrapper.call_async({"session_id": 123, "x": 42})


class TestFunctionWrapperObjectStore:
    """Tests for FunctionWrapper with object store strategy."""

    def test_object_store_handle_type_error(self) -> None:
        """Test object store raises TypeError for non-string handle."""
        from auto_mcp.types.base import TypeInfo, TypeStrategy
        from auto_mcp.types.wrapper import FunctionWrapper

        def func_with_object(obj: dict) -> str:
            return str(obj)

        wrapper = FunctionWrapper(func_with_object)

        # Create a TypeInfo with OBJECT_STORE strategy
        info = TypeInfo(
            type_=dict,
            strategy=TypeStrategy.OBJECT_STORE,
        )

        # This should raise TypeError for non-string handle
        with pytest.raises(TypeError, match="Expected handle string"):
            wrapper._apply_input_transform(info, 123)


class TestFunctionWrapperOutputTransform:
    """Tests for FunctionWrapper output transformation edge cases."""

    def test_output_transform_failure_fallback(self) -> None:
        """Test output transformation fallback on failure."""
        from auto_mcp.types.base import TypeInfo, TypeStrategy
        from auto_mcp.types.wrapper import FunctionWrapper

        # A function that returns a custom type
        class CustomType:
            def __init__(self, value: int) -> None:
                self.value = value

            def __str__(self) -> str:
                return f"CustomType({self.value})"

        def func_with_custom_return() -> CustomType:
            return CustomType(42)

        # Wrapper without adapter for CustomType
        wrapper = FunctionWrapper(func_with_custom_return)

        # Should fall back to auto-serialization
        result = wrapper.call({})
        # The auto-serialization should have converted it somehow
        assert result is not None


# ============================================================================
# Extended Adapter Tests
# ============================================================================


class TestAdapterErrorHandling:
    """Tests for adapter error handling."""

    def test_datetime_adapter_type_error(self) -> None:
        """Test DateTimeAdapter raises TypeError for non-string input."""
        adapter = DateTimeAdapter()
        with pytest.raises(TypeError, match="Expected string"):
            adapter.deserialize(123)

    def test_date_adapter_type_error(self) -> None:
        """Test DateAdapter raises TypeError for non-string input."""
        adapter = DateAdapter()
        with pytest.raises(TypeError, match="Expected string"):
            adapter.deserialize(123)

    def test_time_adapter_type_error(self) -> None:
        """Test TimeAdapter raises TypeError for non-string input."""
        adapter = TimeAdapter()
        with pytest.raises(TypeError, match="Expected string"):
            adapter.deserialize(123)

    def test_timedelta_adapter_type_error(self) -> None:
        """Test TimeDeltaAdapter raises TypeError for non-number input."""
        adapter = TimeDeltaAdapter()
        with pytest.raises(TypeError, match="Expected number"):
            adapter.deserialize("not a number")

    def test_path_adapter_type_error(self) -> None:
        """Test PathAdapter raises TypeError for non-string input."""
        adapter = PathAdapter()
        with pytest.raises(TypeError, match="Expected string"):
            adapter.deserialize(123)

    def test_purepath_adapter_type_error(self) -> None:
        """Test PurePathAdapter raises TypeError for non-string input."""
        adapter = PurePathAdapter()
        with pytest.raises(TypeError, match="Expected string"):
            adapter.deserialize(123)

    def test_uuid_adapter_type_error(self) -> None:
        """Test UUIDAdapter raises TypeError for non-string input."""
        adapter = UUIDAdapter()
        with pytest.raises(TypeError, match="Expected string"):
            adapter.deserialize(123)

    def test_decimal_adapter_type_error(self) -> None:
        """Test DecimalAdapter raises TypeError for unsupported input."""
        adapter = DecimalAdapter()
        with pytest.raises(TypeError, match="Expected string or number"):
            adapter.deserialize([1, 2, 3])

    def test_decimal_adapter_from_int(self) -> None:
        """Test DecimalAdapter deserializes from int."""
        adapter = DecimalAdapter()
        result = adapter.deserialize(42)
        assert result == Decimal("42")

    def test_decimal_adapter_from_float(self) -> None:
        """Test DecimalAdapter deserializes from float."""
        adapter = DecimalAdapter()
        result = adapter.deserialize(3.14)
        assert result == Decimal("3.14")

    def test_bytes_adapter_type_error(self) -> None:
        """Test BytesAdapter raises TypeError for non-string input."""
        adapter = BytesAdapter()
        with pytest.raises(TypeError, match="Expected string"):
            adapter.deserialize(123)

    def test_bytearray_adapter_type_error(self) -> None:
        """Test ByteArrayAdapter raises TypeError for non-string input."""
        adapter = ByteArrayAdapter()
        with pytest.raises(TypeError, match="Expected string"):
            adapter.deserialize(123)

    def test_set_adapter_type_error(self) -> None:
        """Test SetAdapter raises TypeError for non-list input."""
        adapter = SetAdapter()
        with pytest.raises(TypeError, match="Expected list"):
            adapter.deserialize("not a list")

    def test_frozenset_adapter_type_error(self) -> None:
        """Test FrozenSetAdapter raises TypeError for non-list input."""
        adapter = FrozenSetAdapter()
        with pytest.raises(TypeError, match="Expected list"):
            adapter.deserialize("not a list")

    def test_complex_adapter_type_error(self) -> None:
        """Test ComplexAdapter raises TypeError for unsupported input."""
        adapter = ComplexAdapter()
        with pytest.raises(TypeError, match="Expected dict or string"):
            adapter.deserialize(123)

    def test_complex_adapter_from_string(self) -> None:
        """Test ComplexAdapter deserializes from string."""
        adapter = ComplexAdapter()
        result = adapter.deserialize("3+4j")
        assert result == complex(3, 4)


class TestSetAdapterUncomparable:
    """Tests for set adapters with uncomparable elements."""

    def test_set_adapter_uncomparable(self) -> None:
        """Test SetAdapter with uncomparable elements."""
        adapter = SetAdapter()
        # Dict items are uncomparable
        s = {frozenset([1]), frozenset([2])}
        serialized = adapter.serialize(s)
        # Should fallback to list conversion
        assert isinstance(serialized, list)

    def test_frozenset_adapter_uncomparable(self) -> None:
        """Test FrozenSetAdapter with uncomparable elements."""
        adapter = FrozenSetAdapter()
        fs = frozenset([frozenset([1]), frozenset([2])])
        serialized = adapter.serialize(fs)
        assert isinstance(serialized, list)


class TestBytesAdapterConstraints:
    """Tests for bytes adapter constraints."""

    def test_bytes_adapter_can_serialize_wrong_type(self) -> None:
        """Test BytesAdapter can_serialize with wrong type."""
        adapter = BytesAdapter()
        assert adapter.can_serialize("not bytes") is False  # type: ignore

    def test_bytes_adapter_no_limit(self) -> None:
        """Test BytesAdapter with no size limit."""
        adapter = BytesAdapter()
        large_bytes = b"x" * 10000
        assert adapter.can_serialize(large_bytes) is True

    def test_bytearray_adapter_can_serialize_wrong_type(self) -> None:
        """Test ByteArrayAdapter can_serialize with wrong type."""
        adapter = ByteArrayAdapter()
        assert adapter.can_serialize("not bytearray") is False  # type: ignore

    def test_bytearray_adapter_max_size(self) -> None:
        """Test ByteArrayAdapter max size constraint."""
        adapter = ByteArrayAdapter(max_size=10)
        assert adapter.can_serialize(bytearray(b"short")) is True
        assert adapter.can_serialize(bytearray(b"x" * 20)) is False


# ============================================================================
# Extended Registry Tests
# ============================================================================


class TestTypeRegistryExtended:
    """Extended tests for TypeRegistry."""

    def test_get_strategy(self) -> None:
        """Test get_strategy method."""
        registry = TypeRegistry()
        registry.register_adapter(DateTimeAdapter())

        assert registry.get_strategy(int) == TypeStrategy.PASSTHROUGH
        assert registry.get_strategy(datetime) == TypeStrategy.ADAPTER

    def test_serialize_passthrough(self) -> None:
        """Test serializing passthrough types."""
        registry = TypeRegistry()
        result = registry.serialize("hello")
        assert result == "hello"

    def test_serialize_object_store_error(self) -> None:
        """Test serialize raises error for object store types."""
        registry = TypeRegistry()

        class Session:
            pass

        registry.register_stored_type(Session)

        with pytest.raises(TypeError, match="uses object store strategy"):
            registry.serialize(Session())

    def test_serialize_unsupported_error(self) -> None:
        """Test serialize raises error for unsupported types."""
        registry = TypeRegistry()

        class Unsupported:
            pass

        with pytest.raises(TypeError, match="No serialization strategy"):
            registry.serialize(Unsupported())

    def test_serialize_adapter_cannot_serialize(self) -> None:
        """Test serialize raises error when adapter can't serialize."""
        registry = TypeRegistry()
        adapter = BytesAdapter(max_size=10)
        registry.register_adapter(adapter)

        with pytest.raises(ValueError, match="cannot serialize"):
            registry.serialize(b"x" * 100)

    def test_deserialize_passthrough(self) -> None:
        """Test deserializing passthrough types."""
        registry = TypeRegistry()
        result = registry.deserialize("hello", str)
        assert result == "hello"

    def test_deserialize_object_store_error(self) -> None:
        """Test deserialize raises error for object store types."""
        registry = TypeRegistry()

        class Session:
            pass

        registry.register_stored_type(Session)

        with pytest.raises(TypeError, match="uses object store strategy"):
            registry.deserialize("handle:123", Session)

    def test_deserialize_unsupported_error(self) -> None:
        """Test deserialize raises error for unsupported types."""
        registry = TypeRegistry()

        class Unsupported:
            pass

        with pytest.raises(TypeError, match="No deserialization strategy"):
            registry.deserialize({}, Unsupported)

    def test_parent_class_adapter_lookup(self) -> None:
        """Test adapter lookup for parent classes."""
        registry = TypeRegistry()

        class Base:
            pass

        class Derived(Base):
            pass

        adapter = FunctionAdapter(
            target_type=Base,
            serializer=lambda x: "base",
            deserializer=lambda s: Base(),
            schema={"type": "string"},
        )
        registry.register_adapter(adapter)

        # Should find adapter via parent class
        found = registry.get_adapter(Derived)
        assert found is adapter

    def test_parent_class_store_config_lookup(self) -> None:
        """Test store config lookup for parent classes."""
        registry = TypeRegistry()

        class BaseSession:
            pass

        class DerivedSession(BaseSession):
            pass

        registry.register_stored_type(BaseSession, ttl=7200)

        # Should find config via parent class
        config = registry.get_store_config(DerivedSession)
        assert config is not None
        assert config.ttl == 7200

    def test_overwrite_warning(self) -> None:
        """Test that overwriting adapter logs warning."""
        registry = TypeRegistry()
        registry.register_adapter(DateTimeAdapter())
        # Second registration should overwrite without error
        registry.register_adapter(DateTimeAdapter())
        # Should still work
        assert registry.has_adapter(datetime)

    def test_get_type_info_unsupported(self) -> None:
        """Test get_type_info for unsupported types."""
        registry = TypeRegistry()

        class Unsupported:
            pass

        info = registry.get_type_info(Unsupported)
        assert info.strategy == TypeStrategy.UNSUPPORTED
        assert info.json_schema == {}

    def test_primitive_schema_all_types(self) -> None:
        """Test _get_primitive_schema for all primitive types."""
        registry = TypeRegistry()

        assert registry._get_primitive_schema(type(None)) == {"type": "null"}
        assert registry._get_primitive_schema(bool) == {"type": "boolean"}
        assert registry._get_primitive_schema(int) == {"type": "integer"}
        assert registry._get_primitive_schema(float) == {"type": "number"}
        assert registry._get_primitive_schema(str) == {"type": "string"}
        assert registry._get_primitive_schema(list) == {"type": "array"}
        assert registry._get_primitive_schema(dict) == {"type": "object"}

    def test_primitive_schema_unknown(self) -> None:
        """Test _get_primitive_schema for unknown types."""
        registry = TypeRegistry()

        class Unknown:
            pass

        assert registry._get_primitive_schema(Unknown) == {}


# ============================================================================
# Extended Base Types Tests
# ============================================================================


class TestBaseTypesExtended:
    """Extended tests for base types."""

    def test_type_info_type_name_builtin(self) -> None:
        """Test type_name for builtin types."""
        info = TypeInfo(type_=int, strategy=TypeStrategy.PASSTHROUGH)
        assert info.type_name == "int"

    def test_type_info_type_name_module(self) -> None:
        """Test type_name for module types."""
        info = TypeInfo(type_=datetime, strategy=TypeStrategy.ADAPTER)
        assert "datetime" in info.type_name

    def test_is_json_compatible_generic_list(self) -> None:
        """Test is_json_compatible with generic list."""
        from typing import List

        assert is_json_compatible(List[int]) is True  # type: ignore

    def test_is_json_compatible_generic_dict(self) -> None:
        """Test is_json_compatible with generic dict."""
        from typing import Dict

        assert is_json_compatible(Dict[str, Any]) is True  # type: ignore

    def test_is_json_compatible_other_generic(self) -> None:
        """Test is_json_compatible with non-list/dict generic."""
        from typing import Optional

        assert is_json_compatible(Optional[int]) is False

    def test_get_type_origin(self) -> None:
        """Test get_type_origin utility function."""
        from typing import List

        from auto_mcp.types.base import get_type_origin

        assert get_type_origin(List[int]) is list  # type: ignore
        assert get_type_origin(int) is None

    def test_get_type_args(self) -> None:
        """Test get_type_args utility function."""
        from typing import Dict

        from auto_mcp.types.base import get_type_args

        args = get_type_args(Dict[str, int])  # type: ignore
        assert str in args
        assert int in args

        # No args for non-generic
        assert get_type_args(int) == ()


class TestTypeAdapterDecorator:
    """Tests for the type_adapter decorator edge cases."""

    def test_type_adapter_missing_serialize(self) -> None:
        """Test type_adapter raises error for missing serialize."""
        from auto_mcp.types.base import type_adapter

        with pytest.raises(TypeError, match="must implement serialize"):

            @type_adapter(datetime)
            class MissingSerialize:
                def deserialize(self, data: str) -> datetime:
                    return datetime.fromisoformat(data)

                def json_schema(self) -> dict:
                    return {}

    def test_type_adapter_missing_deserialize(self) -> None:
        """Test type_adapter raises error for missing deserialize."""
        from auto_mcp.types.base import type_adapter

        with pytest.raises(TypeError, match="must implement deserialize"):

            @type_adapter(datetime)
            class MissingDeserialize:
                def serialize(self, obj: datetime) -> str:
                    return obj.isoformat()

                def json_schema(self) -> dict:
                    return {}

    def test_type_adapter_missing_json_schema(self) -> None:
        """Test type_adapter raises error for missing json_schema."""
        from auto_mcp.types.base import type_adapter

        with pytest.raises(TypeError, match="must implement json_schema"):

            @type_adapter(datetime)
            class MissingSchema:
                def serialize(self, obj: datetime) -> str:
                    return obj.isoformat()

                def deserialize(self, data: str) -> datetime:
                    return datetime.fromisoformat(data)


class TestTypeAdapterValidate:
    """Tests for TypeAdapter validate method."""

    def test_validate_default(self) -> None:
        """Test default validate always returns True."""
        adapter = DateTimeAdapter()
        assert adapter.validate("2024-01-15T10:30:00") is True
        assert adapter.validate(123) is True  # Default doesn't validate


# ============================================================================
# Extended Compression Tests
# ============================================================================


class TestCompressionExtended:
    """Extended tests for compression module."""

    def test_compressed_data_zero_original_size(self) -> None:
        """Test CompressedData with zero original size."""
        data = CompressedData(
            compressed=False,
            algorithm="none",
            original_size=0,
            compressed_size=0,
            data="",
        )
        d = data.to_dict()
        assert d["compression_ratio"] == 1.0

    def test_decompress_none(self) -> None:
        """Test decompression with NONE algorithm."""
        original = b"Hello"
        result = decompress_bytes(original, CompressionAlgorithm.NONE)
        assert result == original

    def test_compressed_adapter_compression_not_worth_it(self) -> None:
        """Test CompressedAdapter when compression doesn't save space."""
        # Create adapter for small incompressible data
        adapter = FunctionAdapter(
            target_type=str,
            serializer=lambda s: s,
            deserializer=lambda s: s,
            schema={"type": "string"},
        )
        config = CompressionConfig(threshold=1)  # Force compression attempt
        compressed = CompressedAdapter(adapter, config)

        # Very small string - compression may not help
        result = compressed.serialize("x")
        assert isinstance(result, dict)
        # Either compressed or not, it should work
        assert "compressed" in result

    def test_compressed_adapter_disabled(self) -> None:
        """Test CompressedAdapter when compression is disabled."""
        adapter = DateTimeAdapter()
        config = CompressionConfig(enabled=False)
        compressed = CompressedAdapter(adapter, config)

        dt = datetime(2024, 1, 15, 10, 30, 0)
        result = compressed.serialize(dt)

        assert isinstance(result, dict)
        assert result["compressed"] is False

    def test_compress_zlib_different_level(self) -> None:
        """Test zlib compression with different levels."""
        data = b"Hello World! " * 100

        # Level 1 (fast)
        compressed_fast = compress_bytes(data, CompressionAlgorithm.ZLIB, level=1)
        # Level 9 (best)
        compressed_best = compress_bytes(data, CompressionAlgorithm.ZLIB, level=9)

        # Both should decompress correctly
        assert decompress_bytes(compressed_fast, CompressionAlgorithm.ZLIB) == data
        assert decompress_bytes(compressed_best, CompressionAlgorithm.ZLIB) == data

    def test_with_compression_all_params(self) -> None:
        """Test with_compression with all parameters."""
        adapter = DateTimeAdapter()
        compressed = with_compression(
            adapter,
            threshold=2048,
            algorithm=CompressionAlgorithm.ZLIB,
            level=9,
        )

        assert isinstance(compressed, CompressedAdapter)
        assert compressed.config.threshold == 2048
        assert compressed.config.algorithm == CompressionAlgorithm.ZLIB
        assert compressed.config.level == 9


# ============================================================================
# Object Store Extended Tests
# ============================================================================


# ============================================================================
# Optional Third-Party Adapter Tests
# ============================================================================


class TestPandasDataFrameAdapter:
    """Tests for pandas DataFrame adapter."""

    def test_create_adapter(self) -> None:
        """Test creating pandas DataFrame adapter."""
        from auto_mcp.types.adapters import create_pandas_dataframe_adapter

        adapter = create_pandas_dataframe_adapter()
        assert adapter is not None

    def test_serialize_dataframe(self) -> None:
        """Test serializing a DataFrame."""
        import pandas as pd

        from auto_mcp.types.adapters import create_pandas_dataframe_adapter

        adapter = create_pandas_dataframe_adapter()
        assert adapter is not None

        df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        result = adapter.serialize(df)

        assert isinstance(result, dict)
        assert result["columns"] == ["a", "b"]
        assert result["shape"] == [3, 2]
        assert result["truncated"] is False

    def test_deserialize_dataframe(self) -> None:
        """Test deserializing a DataFrame."""
        import pandas as pd

        from auto_mcp.types.adapters import create_pandas_dataframe_adapter

        adapter = create_pandas_dataframe_adapter()
        assert adapter is not None

        data = {
            "columns": ["a", "b"],
            "data": [[1, 4], [2, 5], [3, 6]],
        }
        df = adapter.deserialize(data)

        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["a", "b"]
        assert len(df) == 3

    def test_dataframe_truncation(self) -> None:
        """Test DataFrame truncation for large data."""
        import pandas as pd

        from auto_mcp.types.adapters import create_pandas_dataframe_adapter

        # Create adapter with low max_rows
        adapter = create_pandas_dataframe_adapter()
        assert adapter is not None

        # Manually set max_rows lower for testing
        adapter._max_rows = 2

        df = pd.DataFrame({"a": range(10)})
        result = adapter.serialize(df)

        assert result["truncated"] is True
        assert len(result["data"]) == 2

    def test_dataframe_json_schema(self) -> None:
        """Test DataFrame JSON schema."""
        from auto_mcp.types.adapters import create_pandas_dataframe_adapter

        adapter = create_pandas_dataframe_adapter()
        assert adapter is not None

        schema = adapter.json_schema()
        assert schema["type"] == "object"
        assert "columns" in schema["properties"]
        assert "data" in schema["properties"]

    def test_dataframe_can_serialize(self) -> None:
        """Test DataFrame can_serialize."""
        import pandas as pd

        from auto_mcp.types.adapters import create_pandas_dataframe_adapter

        adapter = create_pandas_dataframe_adapter()
        assert adapter is not None

        df = pd.DataFrame({"a": [1]})
        assert adapter.can_serialize(df) is True
        assert adapter.can_serialize("not a dataframe") is False

    def test_deserialize_type_error(self) -> None:
        """Test DataFrame deserialize with wrong type."""
        from auto_mcp.types.adapters import create_pandas_dataframe_adapter

        adapter = create_pandas_dataframe_adapter()
        assert adapter is not None

        with pytest.raises(TypeError, match="Expected dict"):
            adapter.deserialize("not a dict")


class TestPILImageAdapter:
    """Tests for PIL Image adapter."""

    def test_create_adapter(self) -> None:
        """Test creating PIL Image adapter."""
        from auto_mcp.types.adapters import create_pil_image_adapter

        adapter = create_pil_image_adapter()
        assert adapter is not None

    def test_serialize_image(self) -> None:
        """Test serializing an image."""
        from PIL import Image

        from auto_mcp.types.adapters import create_pil_image_adapter

        adapter = create_pil_image_adapter()
        assert adapter is not None

        # Create a simple test image
        img = Image.new("RGB", (100, 100), color="red")
        result = adapter.serialize(img)

        assert isinstance(result, dict)
        assert "data" in result
        assert result["format"] == "png"
        assert result["width"] == 100
        assert result["height"] == 100
        assert result["mode"] == "RGB"

    def test_deserialize_image(self) -> None:
        """Test deserializing an image."""
        from PIL import Image

        from auto_mcp.types.adapters import create_pil_image_adapter

        adapter = create_pil_image_adapter()
        assert adapter is not None

        # Create and serialize an image first
        original = Image.new("RGB", (50, 50), color="blue")
        serialized = adapter.serialize(original)

        # Deserialize
        restored = adapter.deserialize(serialized)

        assert isinstance(restored, Image.Image)
        assert restored.size == (50, 50)

    def test_image_with_max_size(self) -> None:
        """Test image resizing with max_size."""
        from PIL import Image

        from auto_mcp.types.adapters import create_pil_image_adapter

        # Create adapter with max_size (we need to create it directly)
        adapter = create_pil_image_adapter()
        assert adapter is not None

        # Set max_size
        adapter._max_size = (50, 50)

        # Create large image
        img = Image.new("RGB", (200, 200), color="green")
        result = adapter.serialize(img)

        # Should be resized
        assert result["width"] <= 50
        assert result["height"] <= 50

    def test_image_json_schema(self) -> None:
        """Test Image JSON schema."""
        from auto_mcp.types.adapters import create_pil_image_adapter

        adapter = create_pil_image_adapter()
        assert adapter is not None

        schema = adapter.json_schema()
        assert schema["type"] == "object"
        assert "data" in schema["properties"]
        assert "format" in schema["properties"]

    def test_image_can_serialize(self) -> None:
        """Test Image can_serialize."""
        from PIL import Image

        from auto_mcp.types.adapters import create_pil_image_adapter

        adapter = create_pil_image_adapter()
        assert adapter is not None

        img = Image.new("RGB", (10, 10))
        assert adapter.can_serialize(img) is True
        assert adapter.can_serialize("not an image") is False

    def test_deserialize_type_error(self) -> None:
        """Test Image deserialize with wrong type."""
        from auto_mcp.types.adapters import create_pil_image_adapter

        adapter = create_pil_image_adapter()
        assert adapter is not None

        with pytest.raises(TypeError, match="Expected dict"):
            adapter.deserialize("not a dict")


class TestNumpyArrayAdapter:
    """Tests for numpy ndarray adapter."""

    def test_create_adapter(self) -> None:
        """Test creating numpy ndarray adapter."""
        from auto_mcp.types.adapters import create_numpy_array_adapter

        adapter = create_numpy_array_adapter()
        assert adapter is not None

    def test_serialize_array(self) -> None:
        """Test serializing a numpy array."""
        import numpy as np

        from auto_mcp.types.adapters import create_numpy_array_adapter

        adapter = create_numpy_array_adapter()
        assert adapter is not None

        arr = np.array([[1, 2, 3], [4, 5, 6]])
        result = adapter.serialize(arr)

        assert isinstance(result, dict)
        assert result["shape"] == [2, 3]
        assert result["dtype"] == "int64"
        assert result["truncated"] is False
        assert len(result["data"]) == 6

    def test_deserialize_array(self) -> None:
        """Test deserializing a numpy array."""
        import numpy as np

        from auto_mcp.types.adapters import create_numpy_array_adapter

        adapter = create_numpy_array_adapter()
        assert adapter is not None

        data = {
            "data": [1, 2, 3, 4, 5, 6],
            "shape": [2, 3],
            "dtype": "int64",
            "truncated": False,
        }
        arr = adapter.deserialize(data)

        assert isinstance(arr, np.ndarray)
        assert arr.shape == (2, 3)

    def test_array_truncation(self) -> None:
        """Test array truncation for large data."""
        import numpy as np

        from auto_mcp.types.adapters import create_numpy_array_adapter

        adapter = create_numpy_array_adapter()
        assert adapter is not None

        # Set low max_elements
        adapter._max_elements = 5

        arr = np.arange(100)
        result = adapter.serialize(arr)

        assert result["truncated"] is True
        assert len(result["data"]) == 5

    def test_deserialize_truncated_array(self) -> None:
        """Test deserializing truncated array doesn't reshape."""
        import numpy as np

        from auto_mcp.types.adapters import create_numpy_array_adapter

        adapter = create_numpy_array_adapter()
        assert adapter is not None

        data = {
            "data": [1, 2, 3, 4, 5],  # Only 5 elements
            "shape": [10, 10],  # Original was 100 elements
            "dtype": "int64",
            "truncated": True,  # Was truncated
        }
        arr = adapter.deserialize(data)

        # Should not reshape since truncated
        assert arr.shape == (5,)

    def test_array_json_schema(self) -> None:
        """Test ndarray JSON schema."""
        from auto_mcp.types.adapters import create_numpy_array_adapter

        adapter = create_numpy_array_adapter()
        assert adapter is not None

        schema = adapter.json_schema()
        assert schema["type"] == "object"
        assert "data" in schema["properties"]
        assert "shape" in schema["properties"]
        assert "dtype" in schema["properties"]

    def test_array_can_serialize(self) -> None:
        """Test ndarray can_serialize."""
        import numpy as np

        from auto_mcp.types.adapters import create_numpy_array_adapter

        adapter = create_numpy_array_adapter()
        assert adapter is not None

        arr = np.array([1, 2, 3])
        assert adapter.can_serialize(arr) is True
        assert adapter.can_serialize([1, 2, 3]) is False

    def test_deserialize_type_error(self) -> None:
        """Test ndarray deserialize with wrong type."""
        from auto_mcp.types.adapters import create_numpy_array_adapter

        adapter = create_numpy_array_adapter()
        assert adapter is not None

        with pytest.raises(TypeError, match="Expected dict"):
            adapter.deserialize("not a dict")


class TestOptionalAdaptersHelpers:
    """Tests for optional adapter helper functions."""

    def test_get_optional_adapters(self) -> None:
        """Test getting optional adapters."""
        from auto_mcp.types.adapters import get_optional_adapters

        adapters = get_optional_adapters()
        # Should have at least pandas, PIL, numpy adapters
        assert len(adapters) >= 3


# ============================================================================
# Object Store Extended Tests
# ============================================================================


class TestObjectStoreExtended:
    """Extended tests for ObjectStore."""

    def test_get_info_nonexistent(self) -> None:
        """Test get_info for non-existent handle."""
        store = ObjectStore()
        with pytest.raises(KeyError):
            store.get_info("nonexistent")

    def test_store_with_no_expiration(self) -> None:
        """Test storing with no expiration (ttl=0)."""
        store = ObjectStore()
        handle = store.store("test", ttl=0)

        info = store.get_info(handle)
        assert info["ttl_remaining"] is None

    def test_list_handles_by_type(self) -> None:
        """Test listing handles filtered by type."""
        store = ObjectStore()
        store.store("string1")
        store.store("string2")
        store.store(123)

        str_handles = store.list_handles(type_filter=str)
        int_handles = store.list_handles(type_filter=int)

        assert len(str_handles) == 2
        assert len(int_handles) == 1

    def test_count_by_type(self) -> None:
        """Test counting objects by type."""
        store = ObjectStore()
        store.store("string1")
        store.store("string2")
        store.store(123)

        assert store.count(type_filter=str) == 2
        assert store.count(type_filter=int) == 1

    def test_cleanup_with_auto_cleanup_disabled(self) -> None:
        """Test manual cleanup when auto_cleanup is disabled."""
        store = ObjectStore(auto_cleanup=False)

        # Store objects that will expire
        h1 = store.store("test1", ttl=3600)
        h2 = store.store("test2", ttl=3600)

        # Manually set one as expired
        store._objects[h1].expires_at = time.time() - 1

        # Cleanup should remove only expired
        removed = store.cleanup()
        assert removed == 1
        assert not store.exists(h1)
        assert store.exists(h2)
