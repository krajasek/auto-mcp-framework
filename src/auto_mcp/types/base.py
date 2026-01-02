"""Base types and protocols for type serialization system."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, TypeVar

# Type variable for generic adapter
T = TypeVar("T")

# JSON-compatible types
JsonValue = None | bool | int | float | str | list[Any] | dict[str, Any]


class TypeStrategy(Enum):
    """Strategy for handling a type in MCP context."""

    ADAPTER = "adapter"  # Serialize/deserialize via adapter
    OBJECT_STORE = "object_store"  # Store server-side, use handles
    PASSTHROUGH = "passthrough"  # Already JSON-compatible, pass as-is
    UNSUPPORTED = "unsupported"  # Cannot be handled


@dataclass
class TypeInfo:
    """Information about a type for serialization purposes.

    Attributes:
        type_: The Python type
        strategy: How to handle this type
        adapter: Adapter instance (if strategy is ADAPTER)
        store_config: Object store config (if strategy is OBJECT_STORE)
        json_schema: JSON Schema for the serialized form
    """

    type_: type
    strategy: TypeStrategy
    adapter: TypeAdapter[Any] | None = None
    store_config: ObjectStoreConfig | None = None
    json_schema: dict[str, Any] = field(default_factory=dict)

    @property
    def type_name(self) -> str:
        """Get the fully qualified type name."""
        module = getattr(self.type_, "__module__", "")
        name = getattr(self.type_, "__qualname__", self.type_.__name__)
        if module and module != "builtins":
            return f"{module}.{name}"
        return name


@dataclass
class ObjectStoreConfig:
    """Configuration for storing objects server-side.

    Attributes:
        ttl: Time-to-live in seconds (0 for no expiration)
        max_instances: Maximum number of instances to store
        singleton: Only allow one instance of this type
        auto_create_tool: Auto-generate a creation tool
        auto_cleanup_tool: Auto-generate a cleanup tool
        factory: Optional factory function to create instances
    """

    ttl: int = 3600
    max_instances: int = 100
    singleton: bool = False
    auto_create_tool: bool = True
    auto_cleanup_tool: bool = True
    factory: Any | None = None  # Callable[..., T]


class TypeAdapter(ABC, Generic[T]):
    """Abstract base class for type adapters.

    A type adapter handles serialization and deserialization of a specific
    Python type to/from JSON-compatible values.

    Example:
        >>> class DateTimeAdapter(TypeAdapter[datetime]):
        ...     target_type = datetime
        ...
        ...     def serialize(self, obj: datetime) -> str:
        ...         return obj.isoformat()
        ...
        ...     def deserialize(self, data: str) -> datetime:
        ...         return datetime.fromisoformat(data)
        ...
        ...     def json_schema(self) -> dict:
        ...         return {"type": "string", "format": "date-time"}
    """

    # The type this adapter handles - must be set by subclasses
    target_type: type[T]

    @abstractmethod
    def serialize(self, obj: T) -> JsonValue:
        """Convert object to JSON-serializable value.

        Args:
            obj: The object to serialize

        Returns:
            A JSON-compatible value (dict, list, str, int, float, bool, None)
        """
        ...

    @abstractmethod
    def deserialize(self, data: JsonValue) -> T:
        """Reconstruct object from JSON value.

        Args:
            data: The JSON-compatible value

        Returns:
            The reconstructed object
        """
        ...

    @abstractmethod
    def json_schema(self) -> dict[str, Any]:
        """Return JSON Schema for the serialized form.

        Returns:
            A JSON Schema dictionary describing the serialized format
        """
        ...

    def can_serialize(self, obj: T) -> bool:
        """Check if this adapter can serialize the given object.

        Override this for conditional serialization (e.g., size limits).

        Args:
            obj: The object to check

        Returns:
            True if the object can be serialized
        """
        return isinstance(obj, self.target_type)

    def validate(self, data: JsonValue) -> bool:
        """Validate that data matches the expected schema.

        Args:
            data: The data to validate

        Returns:
            True if the data is valid
        """
        # Basic validation - subclasses can override for stricter checks
        return True


class FunctionAdapter(TypeAdapter[T]):
    """Type adapter defined by functions.

    Convenient for simple adapters without creating a full class.

    Example:
        >>> adapter = FunctionAdapter(
        ...     target_type=Path,
        ...     serializer=lambda p: str(p),
        ...     deserializer=lambda s: Path(s),
        ...     schema={"type": "string"},
        ... )
    """

    def __init__(
        self,
        target_type: type[T],
        serializer: Any,  # Callable[[T], JsonValue]
        deserializer: Any,  # Callable[[JsonValue], T]
        schema: dict[str, Any] | None = None,
        can_serialize_fn: Any | None = None,  # Callable[[T], bool]
    ) -> None:
        """Initialize function-based adapter.

        Args:
            target_type: The type this adapter handles
            serializer: Function to convert object to JSON
            deserializer: Function to convert JSON to object
            schema: JSON Schema for the serialized form
            can_serialize_fn: Optional function to check if object can be serialized
        """
        self.target_type = target_type
        self._serializer = serializer
        self._deserializer = deserializer
        self._schema = schema or {"type": "object"}
        self._can_serialize_fn = can_serialize_fn

    def serialize(self, obj: T) -> JsonValue:
        """Convert object to JSON-serializable value."""
        result: JsonValue = self._serializer(obj)
        return result

    def deserialize(self, data: JsonValue) -> T:
        """Reconstruct object from JSON value."""
        result: T = self._deserializer(data)
        return result

    def json_schema(self) -> dict[str, Any]:
        """Return JSON Schema for the serialized form."""
        return self._schema.copy()

    def can_serialize(self, obj: T) -> bool:
        """Check if this adapter can serialize the given object."""
        if self._can_serialize_fn is not None:
            result: bool = self._can_serialize_fn(obj)
            return result
        return super().can_serialize(obj)


# Decorator for creating adapters
def type_adapter(target_type: type[T]) -> Any:  # Returns Callable[[type], type]
    """Decorator to create a type adapter class.

    Example:
        >>> @type_adapter(datetime)
        ... class DateTimeAdapter:
        ...     def serialize(self, obj: datetime) -> str:
        ...         return obj.isoformat()
        ...
        ...     def deserialize(self, data: str) -> datetime:
        ...         return datetime.fromisoformat(data)
        ...
        ...     def json_schema(self) -> dict:
        ...         return {"type": "string", "format": "date-time"}
    """

    def decorator(cls: type) -> type[TypeAdapter[T]]:
        # Ensure required methods exist
        if not hasattr(cls, "serialize"):
            raise TypeError(f"{cls.__name__} must implement serialize()")
        if not hasattr(cls, "deserialize"):
            raise TypeError(f"{cls.__name__} must implement deserialize()")
        if not hasattr(cls, "json_schema"):
            raise TypeError(f"{cls.__name__} must implement json_schema()")

        # Add target_type as class attribute
        cls.target_type = target_type  # type: ignore[attr-defined]

        # Make it inherit from TypeAdapter if it doesn't already
        if not issubclass(cls, TypeAdapter):
            # Create a new class that inherits from both
            new_cls = type(
                cls.__name__,
                (cls, TypeAdapter),
                {"target_type": target_type},
            )
            return new_cls

        return cls

    return decorator


# Common JSON-compatible types that don't need adapters
JSON_COMPATIBLE_TYPES: tuple[type, ...] = (
    type(None),
    bool,
    int,
    float,
    str,
    list,
    dict,
)


def is_json_compatible(type_: type) -> bool:
    """Check if a type is natively JSON-compatible.

    Args:
        type_: The type to check

    Returns:
        True if the type can be serialized to JSON without an adapter
    """
    # Check direct compatibility
    if type_ in JSON_COMPATIBLE_TYPES:
        return True

    # Check for None type
    if type_ is type(None):
        return True

    # Check origin for generic types (list[int], dict[str, Any], etc.)
    origin = getattr(type_, "__origin__", None)
    if origin is not None:
        return origin in (list, dict)

    return False


def get_type_origin(type_: type) -> type | None:
    """Get the origin of a generic type.

    Args:
        type_: The type to inspect

    Returns:
        The origin type (e.g., list for list[int]) or None
    """
    return getattr(type_, "__origin__", None)


def get_type_args(type_: type) -> tuple[type, ...]:
    """Get the type arguments of a generic type.

    Args:
        type_: The type to inspect

    Returns:
        Tuple of type arguments (e.g., (int,) for list[int])
    """
    return getattr(type_, "__args__", ())
