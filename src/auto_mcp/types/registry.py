"""Type registry for managing type adapters and strategies."""

from __future__ import annotations

import logging
from typing import Any, TypeVar, cast

from auto_mcp.types.base import (
    FunctionAdapter,
    JsonValue,
    ObjectStoreConfig,
    TypeAdapter,
    TypeInfo,
    TypeStrategy,
    is_json_compatible,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class TypeRegistry:
    """Central registry for type handling strategies.

    The registry manages type adapters and object store configurations,
    providing a unified interface for type transformations.

    Example:
        >>> registry = TypeRegistry()
        >>>
        >>> # Register an adapter
        >>> registry.register_adapter(DateTimeAdapter())
        >>>
        >>> # Or use the quick registration
        >>> registry.register(
        ...     datetime,
        ...     serialize=lambda dt: dt.isoformat(),
        ...     deserialize=lambda s: datetime.fromisoformat(s),
        ...     schema={"type": "string", "format": "date-time"},
        ... )
        >>>
        >>> # Register a stored type
        >>> registry.register_stored_type(
        ...     requests.Session,
        ...     ttl=3600,
        ...     auto_create_tool=True,
        ... )
        >>>
        >>> # Get type info
        >>> info = registry.get_type_info(datetime)
        >>> print(info.strategy)  # TypeStrategy.ADAPTER
    """

    def __init__(self) -> None:
        """Initialize an empty type registry."""
        self._adapters: dict[type, TypeAdapter[Any]] = {}
        self._store_configs: dict[type, ObjectStoreConfig] = {}
        self._type_cache: dict[type, TypeInfo] = {}

    def register_adapter(self, adapter: TypeAdapter[T]) -> None:
        """Register a type adapter.

        Args:
            adapter: The adapter instance to register

        Raises:
            ValueError: If an adapter for this type is already registered
        """
        target_type = adapter.target_type

        if target_type in self._adapters:
            logger.warning(
                f"Overwriting existing adapter for {target_type.__name__}"
            )

        self._adapters[target_type] = adapter
        self._invalidate_cache(target_type)

        logger.debug(f"Registered adapter for {target_type.__name__}")

    def register(
        self,
        target_type: type[T],
        *,
        serialize: Any,  # Callable[[T], JsonValue]
        deserialize: Any,  # Callable[[JsonValue], T]
        schema: dict[str, Any] | None = None,
        can_serialize: Any | None = None,  # Callable[[T], bool]
    ) -> None:
        """Quick registration of a type adapter using functions.

        Args:
            target_type: The type to register an adapter for
            serialize: Function to convert object to JSON
            deserialize: Function to convert JSON to object
            schema: JSON Schema for the serialized form
            can_serialize: Optional function to check if object can be serialized
        """
        adapter = FunctionAdapter(
            target_type=target_type,
            serializer=serialize,
            deserializer=deserialize,
            schema=schema,
            can_serialize_fn=can_serialize,
        )
        self.register_adapter(adapter)

    def register_stored_type(
        self,
        target_type: type,
        *,
        ttl: int = 3600,
        max_instances: int = 100,
        singleton: bool = False,
        auto_create_tool: bool = True,
        auto_cleanup_tool: bool = True,
        factory: Any | None = None,
    ) -> None:
        """Register a type to be stored server-side with handles.

        Args:
            target_type: The type to register
            ttl: Time-to-live in seconds (0 for no expiration)
            max_instances: Maximum number of instances to store
            singleton: Only allow one instance of this type
            auto_create_tool: Auto-generate a creation tool
            auto_cleanup_tool: Auto-generate a cleanup tool
            factory: Optional factory function to create instances
        """
        config = ObjectStoreConfig(
            ttl=ttl,
            max_instances=max_instances,
            singleton=singleton,
            auto_create_tool=auto_create_tool,
            auto_cleanup_tool=auto_cleanup_tool,
            factory=factory,
        )

        if target_type in self._store_configs:
            logger.warning(
                f"Overwriting existing store config for {target_type.__name__}"
            )

        self._store_configs[target_type] = config
        self._invalidate_cache(target_type)

        logger.debug(f"Registered stored type {target_type.__name__}")

    def get_adapter(self, type_: type) -> TypeAdapter[Any] | None:
        """Get the adapter for a type.

        Args:
            type_: The type to get an adapter for

        Returns:
            The adapter instance or None if not registered
        """
        # Direct lookup
        if type_ in self._adapters:
            return self._adapters[type_]

        # Check for parent class adapters
        for registered_type, adapter in self._adapters.items():
            if isinstance(type_, type) and issubclass(type_, registered_type):
                return adapter

        return None

    def get_store_config(self, type_: type) -> ObjectStoreConfig | None:
        """Get the object store config for a type.

        Args:
            type_: The type to get config for

        Returns:
            The config or None if not registered
        """
        # Direct lookup
        if type_ in self._store_configs:
            return self._store_configs[type_]

        # Check for parent class configs
        for registered_type, config in self._store_configs.items():
            if isinstance(type_, type) and issubclass(type_, registered_type):
                return config

        return None

    def get_type_info(self, type_: type) -> TypeInfo:
        """Get complete type information including strategy.

        Args:
            type_: The type to get info for

        Returns:
            TypeInfo with strategy and handler details
        """
        # Check cache
        if type_ in self._type_cache:
            return self._type_cache[type_]

        # Determine strategy
        info = self._compute_type_info(type_)
        self._type_cache[type_] = info

        return info

    def get_strategy(self, type_: type) -> TypeStrategy:
        """Get the handling strategy for a type.

        Args:
            type_: The type to get strategy for

        Returns:
            The TypeStrategy enum value
        """
        return self.get_type_info(type_).strategy

    def serialize(self, obj: Any) -> JsonValue:
        """Serialize an object using the appropriate adapter.

        Args:
            obj: The object to serialize

        Returns:
            JSON-compatible value

        Raises:
            TypeError: If no adapter is registered for the type
            ValueError: If the object cannot be serialized
        """
        obj_type = type(obj)
        info = self.get_type_info(obj_type)

        if info.strategy == TypeStrategy.PASSTHROUGH:
            return cast(JsonValue, obj)

        if info.strategy == TypeStrategy.ADAPTER and info.adapter:
            if not info.adapter.can_serialize(obj):
                raise ValueError(f"Adapter cannot serialize this {obj_type.__name__}")
            return info.adapter.serialize(obj)

        if info.strategy == TypeStrategy.OBJECT_STORE:
            raise TypeError(
                f"Type {obj_type.__name__} uses object store strategy. "
                "Use ObjectStore.store() instead of serialize()."
            )

        raise TypeError(f"No serialization strategy for type {obj_type.__name__}")

    def deserialize(self, data: JsonValue, target_type: type[T]) -> T:
        """Deserialize data to the target type.

        Args:
            data: The JSON-compatible data
            target_type: The type to deserialize to

        Returns:
            The deserialized object

        Raises:
            TypeError: If no adapter is registered for the type
        """
        info = self.get_type_info(target_type)

        if info.strategy == TypeStrategy.PASSTHROUGH:
            return data  # type: ignore[return-value]

        if info.strategy == TypeStrategy.ADAPTER and info.adapter:
            return cast(T, info.adapter.deserialize(data))

        if info.strategy == TypeStrategy.OBJECT_STORE:
            raise TypeError(
                f"Type {target_type.__name__} uses object store strategy. "
                "Use ObjectStore.get() instead of deserialize()."
            )

        raise TypeError(f"No deserialization strategy for type {target_type.__name__}")

    def get_json_schema(self, type_: type) -> dict[str, Any]:
        """Get JSON Schema for a type's serialized form.

        Args:
            type_: The type to get schema for

        Returns:
            JSON Schema dictionary
        """
        info = self.get_type_info(type_)
        return info.json_schema.copy()

    def has_adapter(self, type_: type) -> bool:
        """Check if an adapter is registered for a type.

        Args:
            type_: The type to check

        Returns:
            True if an adapter exists
        """
        return self.get_adapter(type_) is not None

    def has_store_config(self, type_: type) -> bool:
        """Check if a store config is registered for a type.

        Args:
            type_: The type to check

        Returns:
            True if a store config exists
        """
        return self.get_store_config(type_) is not None

    def list_adapters(self) -> list[type]:
        """List all types with registered adapters.

        Returns:
            List of type objects
        """
        return list(self._adapters.keys())

    def list_stored_types(self) -> list[type]:
        """List all types configured for object store.

        Returns:
            List of type objects
        """
        return list(self._store_configs.keys())

    def clear(self) -> None:
        """Clear all registered adapters and configs."""
        self._adapters.clear()
        self._store_configs.clear()
        self._type_cache.clear()

    def _compute_type_info(self, type_: type) -> TypeInfo:
        """Compute TypeInfo for a type.

        Args:
            type_: The type to compute info for

        Returns:
            Computed TypeInfo
        """
        # Check if JSON-compatible (passthrough)
        if is_json_compatible(type_):
            return TypeInfo(
                type_=type_,
                strategy=TypeStrategy.PASSTHROUGH,
                json_schema=self._get_primitive_schema(type_),
            )

        # Check for registered adapter
        adapter = self.get_adapter(type_)
        if adapter:
            return TypeInfo(
                type_=type_,
                strategy=TypeStrategy.ADAPTER,
                adapter=adapter,
                json_schema=adapter.json_schema(),
            )

        # Check for object store config
        store_config = self.get_store_config(type_)
        if store_config:
            return TypeInfo(
                type_=type_,
                strategy=TypeStrategy.OBJECT_STORE,
                store_config=store_config,
                json_schema={"type": "string", "description": f"Handle to {type_.__name__}"},
            )

        # No handler registered
        return TypeInfo(
            type_=type_,
            strategy=TypeStrategy.UNSUPPORTED,
            json_schema={},
        )

    def _get_primitive_schema(self, type_: type) -> dict[str, Any]:
        """Get JSON Schema for primitive types.

        Args:
            type_: The primitive type

        Returns:
            JSON Schema dictionary
        """
        if type_ is type(None) or type_ is None:
            return {"type": "null"}
        if type_ is bool:
            return {"type": "boolean"}
        if type_ is int:
            return {"type": "integer"}
        if type_ is float:
            return {"type": "number"}
        if type_ is str:
            return {"type": "string"}
        if type_ is list:
            return {"type": "array"}
        if type_ is dict:
            return {"type": "object"}
        return {}

    def _invalidate_cache(self, type_: type) -> None:
        """Invalidate the cache for a type.

        Args:
            type_: The type to invalidate
        """
        self._type_cache.pop(type_, None)


# Global default registry
_default_registry: TypeRegistry | None = None


def get_default_registry() -> TypeRegistry:
    """Get the default global type registry.

    Returns:
        The default TypeRegistry instance
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = TypeRegistry()
    return _default_registry


def set_default_registry(registry: TypeRegistry) -> None:
    """Set the default global type registry.

    Args:
        registry: The registry to use as default
    """
    global _default_registry
    _default_registry = registry
