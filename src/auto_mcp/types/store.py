"""Object store for managing stateful objects server-side."""

from __future__ import annotations

import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, TypeVar

from auto_mcp.types.base import ObjectStoreConfig

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class StoredObject:
    """Container for a stored object with metadata.

    Attributes:
        obj: The stored object
        type_name: Fully qualified type name
        created_at: Unix timestamp when created
        expires_at: Unix timestamp when it expires (0 for never)
        access_count: Number of times accessed
        last_accessed: Unix timestamp of last access
    """

    obj: Any
    type_name: str
    created_at: float
    expires_at: float
    access_count: int = 0
    last_accessed: float = 0

    @property
    def is_expired(self) -> bool:
        """Check if this object has expired."""
        if self.expires_at == 0:
            return False
        return time.time() > self.expires_at

    def touch(self) -> None:
        """Update access timestamp and count."""
        self.access_count += 1
        self.last_accessed = time.time()


@dataclass
class StoreStats:
    """Statistics about the object store.

    Attributes:
        total_objects: Total number of stored objects
        by_type: Count of objects by type name
        expired_count: Number of expired objects (not yet cleaned)
        total_accesses: Total number of object accesses
        oldest_object_age: Age of oldest object in seconds
    """

    total_objects: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    expired_count: int = 0
    total_accesses: int = 0
    oldest_object_age: float = 0


class ObjectStore:
    """Server-side storage for stateful objects.

    The ObjectStore manages object lifecycles, providing handles for
    clients to reference server-side objects without serialization.

    Example:
        >>> store = ObjectStore()
        >>>
        >>> # Store an object
        >>> session = requests.Session()
        >>> handle = store.store(session, ttl=3600)
        >>> print(handle)  # "Session:x7k9m2"
        >>>
        >>> # Retrieve the object
        >>> session = store.get(handle)
        >>>
        >>> # Release when done
        >>> store.release(handle)
    """

    def __init__(
        self,
        handle_prefix: str = "",
        handle_length: int = 8,
        cleanup_interval: int = 60,
        auto_cleanup: bool = True,
    ) -> None:
        """Initialize the object store.

        Args:
            handle_prefix: Prefix for all handles (e.g., "mcp_")
            handle_length: Length of the random part of handles
            cleanup_interval: Seconds between automatic cleanups
            auto_cleanup: Whether to run automatic cleanup
        """
        self._objects: dict[str, StoredObject] = {}
        self._type_counts: dict[str, int] = {}
        self._configs: dict[type, ObjectStoreConfig] = {}
        self._lock = threading.RLock()

        self._handle_prefix = handle_prefix
        self._handle_length = handle_length
        self._cleanup_interval = cleanup_interval
        self._auto_cleanup = auto_cleanup

        self._last_cleanup = time.time()
        self._total_stored = 0
        self._total_released = 0

    def configure_type(self, type_: type, config: ObjectStoreConfig) -> None:
        """Configure storage behavior for a type.

        Args:
            type_: The type to configure
            config: The storage configuration
        """
        with self._lock:
            self._configs[type_] = config

    def store(
        self,
        obj: T,
        *,
        ttl: int | None = None,
        handle: str | None = None,
    ) -> str:
        """Store an object and return its handle.

        Args:
            obj: The object to store
            ttl: Time-to-live in seconds (overrides type config)
            handle: Use specific handle (for restoring objects)

        Returns:
            The handle string for retrieving the object

        Raises:
            ValueError: If max instances exceeded or singleton exists
        """
        obj_type = type(obj)
        type_name = self._get_type_name(obj_type)
        config = self._get_config(obj_type)

        with self._lock:
            # Maybe cleanup expired objects
            self._maybe_cleanup()

            # Check singleton constraint
            if config.singleton:
                existing = self._find_by_type(obj_type)
                if existing:
                    # Return existing handle for singleton
                    return existing

            # Check max instances
            type_count = self._type_counts.get(type_name, 0)
            if type_count >= config.max_instances:
                raise ValueError(
                    f"Maximum instances ({config.max_instances}) reached for {type_name}"
                )

            # Generate handle
            if handle is None:
                handle = self._generate_handle(obj_type)

            # Calculate expiration
            effective_ttl = ttl if ttl is not None else config.ttl
            expires_at = time.time() + effective_ttl if effective_ttl > 0 else 0

            # Store the object
            stored = StoredObject(
                obj=obj,
                type_name=type_name,
                created_at=time.time(),
                expires_at=expires_at,
            )
            self._objects[handle] = stored

            # Update counts
            self._type_counts[type_name] = type_count + 1
            self._total_stored += 1

            logger.debug(f"Stored {type_name} with handle {handle}")
            return handle

    def get(self, handle: str) -> Any:
        """Retrieve an object by its handle.

        Args:
            handle: The handle string

        Returns:
            The stored object

        Raises:
            KeyError: If handle not found
            ValueError: If object has expired
        """
        with self._lock:
            if handle not in self._objects:
                raise KeyError(f"Handle not found: {handle}")

            stored = self._objects[handle]

            if stored.is_expired:
                # Clean up expired object
                self._remove(handle)
                raise ValueError(f"Object has expired: {handle}")

            stored.touch()
            return stored.obj

    def get_typed(self, handle: str, expected_type: type[T]) -> T:
        """Retrieve an object with type checking.

        Args:
            handle: The handle string
            expected_type: The expected type of the object

        Returns:
            The stored object

        Raises:
            KeyError: If handle not found
            TypeError: If object is not of expected type
            ValueError: If object has expired
        """
        obj = self.get(handle)
        if not isinstance(obj, expected_type):
            raise TypeError(
                f"Expected {expected_type.__name__}, got {type(obj).__name__}"
            )
        return obj

    def release(self, handle: str) -> bool:
        """Release an object, removing it from the store.

        Args:
            handle: The handle string

        Returns:
            True if object was released, False if not found
        """
        with self._lock:
            if handle not in self._objects:
                return False

            self._remove(handle)
            logger.debug(f"Released handle {handle}")
            return True

    def exists(self, handle: str) -> bool:
        """Check if a handle exists and is not expired.

        Args:
            handle: The handle string

        Returns:
            True if handle exists and is valid
        """
        with self._lock:
            if handle not in self._objects:
                return False

            stored = self._objects[handle]
            if stored.is_expired:
                self._remove(handle)
                return False

            return True

    def get_info(self, handle: str) -> dict[str, Any]:
        """Get metadata about a stored object.

        Args:
            handle: The handle string

        Returns:
            Dictionary with object metadata

        Raises:
            KeyError: If handle not found
        """
        with self._lock:
            if handle not in self._objects:
                raise KeyError(f"Handle not found: {handle}")

            stored = self._objects[handle]
            now = time.time()

            return {
                "handle": handle,
                "type": stored.type_name,
                "created_at": stored.created_at,
                "age_seconds": now - stored.created_at,
                "expires_at": stored.expires_at if stored.expires_at > 0 else None,
                "ttl_remaining": max(0, stored.expires_at - now) if stored.expires_at > 0 else None,
                "access_count": stored.access_count,
                "last_accessed": stored.last_accessed if stored.last_accessed > 0 else None,
                "is_expired": stored.is_expired,
            }

    def list_handles(self, type_filter: type | None = None) -> list[str]:
        """List all active handles.

        Args:
            type_filter: Optional type to filter by

        Returns:
            List of handle strings
        """
        with self._lock:
            self._maybe_cleanup()

            if type_filter is None:
                return list(self._objects.keys())

            type_name = self._get_type_name(type_filter)
            return [
                handle
                for handle, stored in self._objects.items()
                if stored.type_name == type_name and not stored.is_expired
            ]

    def count(self, type_filter: type | None = None) -> int:
        """Count stored objects.

        Args:
            type_filter: Optional type to filter by

        Returns:
            Number of stored objects
        """
        return len(self.list_handles(type_filter))

    def get_stats(self) -> StoreStats:
        """Get statistics about the store.

        Returns:
            StoreStats object
        """
        with self._lock:
            stats = StoreStats()
            now = time.time()
            oldest_age = 0.0

            for stored in self._objects.values():
                stats.total_objects += 1
                stats.by_type[stored.type_name] = (
                    stats.by_type.get(stored.type_name, 0) + 1
                )
                stats.total_accesses += stored.access_count

                if stored.is_expired:
                    stats.expired_count += 1

                age = now - stored.created_at
                if age > oldest_age:
                    oldest_age = age

            stats.oldest_object_age = oldest_age
            return stats

    def cleanup(self) -> int:
        """Remove all expired objects.

        Returns:
            Number of objects removed
        """
        with self._lock:
            expired_handles = [
                handle
                for handle, stored in self._objects.items()
                if stored.is_expired
            ]

            for handle in expired_handles:
                self._remove(handle)

            self._last_cleanup = time.time()

            if expired_handles:
                logger.debug(f"Cleaned up {len(expired_handles)} expired objects")

            return len(expired_handles)

    def clear(self) -> int:
        """Remove all objects from the store.

        Returns:
            Number of objects removed
        """
        with self._lock:
            count = len(self._objects)
            self._objects.clear()
            self._type_counts.clear()
            self._total_released += count
            return count

    def _generate_handle(self, type_: type) -> str:
        """Generate a unique handle for an object.

        Args:
            type_: The type of the object

        Returns:
            A unique handle string
        """
        type_prefix = type_.__name__
        random_part = secrets.token_urlsafe(self._handle_length)[:self._handle_length]

        handle = f"{self._handle_prefix}{type_prefix}:{random_part}"

        # Ensure uniqueness
        while handle in self._objects:
            random_part = secrets.token_urlsafe(self._handle_length)[:self._handle_length]
            handle = f"{self._handle_prefix}{type_prefix}:{random_part}"

        return handle

    def _get_type_name(self, type_: type) -> str:
        """Get the fully qualified type name.

        Args:
            type_: The type

        Returns:
            Fully qualified name
        """
        module = getattr(type_, "__module__", "")
        name = getattr(type_, "__qualname__", type_.__name__)
        if module and module != "builtins":
            return f"{module}.{name}"
        return name

    def _get_config(self, type_: type) -> ObjectStoreConfig:
        """Get configuration for a type.

        Args:
            type_: The type

        Returns:
            Configuration (default if not registered)
        """
        # Check for exact match
        if type_ in self._configs:
            return self._configs[type_]

        # Check for parent class
        for registered_type, config in self._configs.items():
            if issubclass(type_, registered_type):
                return config

        # Return default config
        return ObjectStoreConfig()

    def _find_by_type(self, type_: type) -> str | None:
        """Find an existing handle for a type (for singletons).

        Args:
            type_: The type to find

        Returns:
            Handle if found, None otherwise
        """
        type_name = self._get_type_name(type_)
        for handle, stored in self._objects.items():
            if stored.type_name == type_name and not stored.is_expired:
                return handle
        return None

    def _remove(self, handle: str) -> None:
        """Remove an object from the store.

        Args:
            handle: The handle to remove
        """
        if handle in self._objects:
            stored = self._objects[handle]
            type_name = stored.type_name

            del self._objects[handle]

            # Update type count
            if type_name in self._type_counts:
                self._type_counts[type_name] -= 1
                if self._type_counts[type_name] <= 0:
                    del self._type_counts[type_name]

            self._total_released += 1

    def _maybe_cleanup(self) -> None:
        """Run cleanup if enough time has passed."""
        if not self._auto_cleanup:
            return

        if time.time() - self._last_cleanup > self._cleanup_interval:
            self.cleanup()


# Global default store
_default_store: ObjectStore | None = None


def get_default_store() -> ObjectStore:
    """Get the default global object store.

    Returns:
        The default ObjectStore instance
    """
    global _default_store
    if _default_store is None:
        _default_store = ObjectStore()
    return _default_store


def set_default_store(store: ObjectStore) -> None:
    """Set the default global object store.

    Args:
        store: The store to use as default
    """
    global _default_store
    _default_store = store
