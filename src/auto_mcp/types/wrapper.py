"""Function wrapper for automatic type transformation.

This module provides wrappers that automatically handle type
serialization/deserialization for function parameters and return values.
"""

from __future__ import annotations

import functools
import inspect
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar, cast, get_type_hints

from auto_mcp.types.base import JsonValue, TypeInfo, TypeStrategy
from auto_mcp.types.registry import TypeRegistry, get_default_registry
from auto_mcp.types.store import ObjectStore, get_default_store

if TYPE_CHECKING:
    from auto_mcp.session.manager import SessionManager

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class TypeTransformError(Exception):
    """Error during type transformation."""

    def __init__(
        self,
        message: str,
        param_name: str | None = None,
        original_error: Exception | None = None,
    ) -> None:
        """Initialize transformation error.

        Args:
            message: Error description
            param_name: Name of the parameter that failed
            original_error: The underlying exception
        """
        super().__init__(message)
        self.param_name = param_name
        self.original_error = original_error


class FunctionWrapper:
    """Wraps a function to handle type transformations.

    The wrapper inspects the function signature and applies appropriate
    transformations for parameters and return values based on their types.

    Example:
        >>> def process_data(df: pd.DataFrame, path: Path) -> dict:
        ...     return {"rows": len(df), "path": str(path)}
        >>>
        >>> wrapper = FunctionWrapper(process_data)
        >>> # Now accepts JSON-serialized inputs
        >>> result = wrapper.call({
        ...     "df": {"columns": ["a"], "data": [[1]]},
        ...     "path": "/tmp/data.csv"
        ... })
    """

    def __init__(
        self,
        func: Callable[..., Any],
        registry: TypeRegistry | None = None,
        store: ObjectStore | None = None,
        transform_inputs: bool = True,
        transform_output: bool = True,
        session_manager: SessionManager | None = None,
        session_param_name: str | None = None,
    ) -> None:
        """Initialize function wrapper.

        Args:
            func: The function to wrap
            registry: Type registry for adapters (uses default if None)
            store: Object store for handles (uses default if None)
            transform_inputs: Whether to transform input parameters
            transform_output: Whether to transform return value
            session_manager: Session manager for session injection
            session_param_name: Name of the SessionContext parameter to inject
        """
        self.func = func
        self.registry = registry or get_default_registry()
        self.store = store or get_default_store()
        self._transform_inputs = transform_inputs
        self._transform_output = transform_output
        self._session_manager = session_manager
        self._session_param_name = session_param_name

        # Analyze function signature
        self._sig = inspect.signature(func)
        self._type_hints = self._get_type_hints()

        # Validate session param name exists in signature if specified
        if (
            self._session_param_name
            and self._session_manager
            and self._session_param_name not in self._sig.parameters
        ):
            raise ValueError(
                f"Session parameter '{self._session_param_name}' not found in "
                f"function '{func.__name__}' signature. "
                f"Available parameters: {list(self._sig.parameters.keys())}"
            )

        self._param_info = self._analyze_parameters()
        self._return_info = self._analyze_return()

        # Preserve function metadata
        functools.update_wrapper(self, func)

    def _get_type_hints(self) -> dict[str, Any]:
        """Get type hints for the function.

        Returns:
            Dictionary of parameter names to types
        """
        try:
            return get_type_hints(self.func)
        except Exception:
            # Type hints may fail for various reasons
            return {}

    def _analyze_parameters(self) -> dict[str, TypeInfo]:
        """Analyze parameter types and get their TypeInfo.

        Returns:
            Dictionary of parameter names to TypeInfo
        """
        # Import here to avoid circular imports
        from auto_mcp.session.context import SessionContext

        param_info: dict[str, TypeInfo] = {}

        for name, param in self._sig.parameters.items():
            if name in ("self", "cls"):
                continue

            # Skip SessionContext parameter - it's injected, not passed by caller
            if name == self._session_param_name:
                continue

            # Get type annotation
            type_hint = self._type_hints.get(name)
            if type_hint is None and param.annotation is not inspect.Parameter.empty:
                type_hint = param.annotation

            # Skip SessionContext type even if not specified by name
            if type_hint is SessionContext:
                continue

            if type_hint is not None:
                param_info[name] = self.registry.get_type_info(type_hint)

        return param_info

    def _analyze_return(self) -> TypeInfo | None:
        """Analyze return type and get TypeInfo.

        Returns:
            TypeInfo for return type or None
        """
        return_type = self._type_hints.get("return")
        if return_type is None or return_type is type(None):
            return None

        # At this point, return_type is a valid type
        return self.registry.get_type_info(return_type)

    def get_json_schema(self) -> dict[str, Any]:
        """Get JSON Schema for the function's parameters.

        Returns:
            JSON Schema dictionary for the input parameters
        """
        # Import here to avoid circular imports
        from auto_mcp.session.context import SessionContext

        properties: dict[str, Any] = {}
        required: list[str] = []

        # Add session_id if session injection is enabled
        if self._session_manager and self._session_param_name:
            properties["session_id"] = {
                "type": "string",
                "description": "Active session ID from create_session",
            }
            required.append("session_id")

        for name, param in self._sig.parameters.items():
            if name in ("self", "cls"):
                continue

            # Skip SessionContext parameter
            if name == self._session_param_name:
                continue

            # Get type hint to check for SessionContext
            type_hint = self._type_hints.get(name)
            if type_hint is SessionContext:
                continue

            # Get parameter info
            info = self._param_info.get(name)
            if info:
                properties[name] = info.json_schema.copy()
            else:
                # No type info, allow any value
                properties[name] = {}

            # Check if required (no default value)
            if param.default is inspect.Parameter.empty:
                required.append(name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    def get_return_schema(self) -> dict[str, Any]:
        """Get JSON Schema for the function's return value.

        Returns:
            JSON Schema dictionary for the return type
        """
        if self._return_info:
            return self._return_info.json_schema.copy()
        return {}

    def transform_input(self, name: str, value: JsonValue) -> Any:
        """Transform a single input value based on parameter type.

        Args:
            name: Parameter name
            value: JSON-compatible input value

        Returns:
            Transformed Python object
        """
        info = self._param_info.get(name)
        if info is None:
            return value

        try:
            return self._apply_input_transform(info, value)
        except Exception as e:
            raise TypeTransformError(
                f"Failed to transform parameter '{name}': {e}",
                param_name=name,
                original_error=e,
            ) from e

    def _apply_input_transform(self, info: TypeInfo, value: JsonValue) -> Any:
        """Apply input transformation based on strategy.

        Args:
            info: TypeInfo for the parameter
            value: JSON-compatible input value

        Returns:
            Transformed Python object
        """
        if info.strategy == TypeStrategy.PASSTHROUGH:
            return value

        if info.strategy == TypeStrategy.ADAPTER and info.adapter:
            return info.adapter.deserialize(value)

        if info.strategy == TypeStrategy.OBJECT_STORE:
            # Value should be a handle string
            if not isinstance(value, str):
                raise TypeError(f"Expected handle string, got {type(value).__name__}")
            return self.store.get_typed(value, info.type_)

        # Unsupported type - pass through and let the function handle it
        return value

    def transform_output(self, value: Any) -> JsonValue:
        """Transform the return value to JSON-compatible format.

        Args:
            value: Function return value

        Returns:
            JSON-compatible value
        """
        if value is None:
            return None

        if self._return_info is None:
            # No return type annotation - try to serialize if not JSON-compatible
            return self._auto_serialize_output(value)

        try:
            return self._apply_output_transform(self._return_info, value)
        except Exception as e:
            logger.warning(f"Failed to transform return value: {e}")
            # Fall back to auto-serialization
            return self._auto_serialize_output(value)

    def _apply_output_transform(self, info: TypeInfo, value: Any) -> JsonValue:
        """Apply output transformation based on strategy.

        Args:
            info: TypeInfo for the return type
            value: The return value

        Returns:
            JSON-compatible value
        """
        if info.strategy == TypeStrategy.PASSTHROUGH:
            return cast(JsonValue, value)

        if info.strategy == TypeStrategy.ADAPTER and info.adapter:
            if info.adapter.can_serialize(value):
                return info.adapter.serialize(value)
            # Can't serialize, try auto-serialization
            return self._auto_serialize_output(value)

        if info.strategy == TypeStrategy.OBJECT_STORE:
            # Store the object and return the handle
            config = info.store_config
            ttl = config.ttl if config else 3600
            return self.store.store(value, ttl=ttl)

        # Unsupported - try auto-serialization
        return self._auto_serialize_output(value)

    def _auto_serialize_output(self, value: Any) -> JsonValue:
        """Attempt to auto-serialize a value.

        Args:
            value: The value to serialize

        Returns:
            JSON-compatible value
        """
        # Already JSON-compatible
        if isinstance(value, (type(None), bool, int, float, str)):
            return value

        if isinstance(value, (list, tuple)):
            return [self._auto_serialize_output(item) for item in value]

        if isinstance(value, dict):
            return {
                str(k): self._auto_serialize_output(v)
                for k, v in value.items()
            }

        # Try to find an adapter for the actual type
        actual_type = type(value)
        info = self.registry.get_type_info(actual_type)

        if (
            info.strategy == TypeStrategy.ADAPTER
            and info.adapter
            and info.adapter.can_serialize(value)
        ):
            return info.adapter.serialize(value)

        # Last resort - convert to string
        return str(value)

    def call(self, kwargs: dict[str, JsonValue]) -> JsonValue:
        """Call the wrapped function with type transformations.

        Args:
            kwargs: JSON-compatible keyword arguments

        Returns:
            JSON-compatible return value
        """
        # Make a copy to avoid modifying the original
        kwargs = dict(kwargs)

        # Handle session injection
        if self._session_manager and self._session_param_name:
            session_id = kwargs.pop("session_id", None)
            if session_id is None:
                raise ValueError("session_id is required for session-aware tools")
            if not isinstance(session_id, str):
                raise TypeError(f"session_id must be a string, got {type(session_id).__name__}")
            session = self._session_manager.get_session(session_id)
            kwargs[self._session_param_name] = session

        # Transform inputs
        if self._transform_inputs:
            transformed_kwargs: dict[str, Any] = {}
            for name, value in kwargs.items():
                # Skip session - it's already the right type
                if name == self._session_param_name:
                    transformed_kwargs[name] = value
                else:
                    transformed_kwargs[name] = self.transform_input(name, value)
        else:
            transformed_kwargs = kwargs

        # Call the function
        result = self.func(**transformed_kwargs)

        # Transform output
        if self._transform_output:
            return self.transform_output(result)
        return cast(JsonValue, result)

    async def call_async(self, kwargs: dict[str, JsonValue]) -> JsonValue:
        """Call the wrapped async function with type transformations.

        Args:
            kwargs: JSON-compatible keyword arguments

        Returns:
            JSON-compatible return value
        """
        # Make a copy to avoid modifying the original
        kwargs = dict(kwargs)

        # Handle session injection
        if self._session_manager and self._session_param_name:
            session_id = kwargs.pop("session_id", None)
            if session_id is None:
                raise ValueError("session_id is required for session-aware tools")
            if not isinstance(session_id, str):
                raise TypeError(f"session_id must be a string, got {type(session_id).__name__}")
            session = self._session_manager.get_session(session_id)
            kwargs[self._session_param_name] = session

        # Transform inputs
        if self._transform_inputs:
            transformed_kwargs: dict[str, Any] = {}
            for name, value in kwargs.items():
                # Skip session - it's already the right type
                if name == self._session_param_name:
                    transformed_kwargs[name] = value
                else:
                    transformed_kwargs[name] = self.transform_input(name, value)
        else:
            transformed_kwargs = kwargs

        # Call the async function
        result = await self.func(**transformed_kwargs)

        # Transform output
        if self._transform_output:
            return self.transform_output(result)
        return cast(JsonValue, result)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Call the function with positional and keyword arguments.

        This is the direct call interface that transforms inputs/outputs.
        """
        # Bind arguments to parameters
        bound = self._sig.bind(*args, **kwargs)
        bound.apply_defaults()

        # Convert to JSON kwargs for transformation
        json_kwargs = {}
        for name, value in bound.arguments.items():
            if name in ("self", "cls"):
                continue
            # For direct calls, we need to serialize first if applicable
            json_kwargs[name] = self._maybe_serialize_input(name, value)

        return self.call(json_kwargs)

    def _maybe_serialize_input(self, name: str, value: Any) -> JsonValue:
        """Serialize input if it's already the target type.

        This handles the case where the user passes an already-typed
        object in a direct function call.

        Args:
            name: Parameter name
            value: Input value

        Returns:
            JSON-compatible value (or the value itself if already compatible)
        """
        if isinstance(value, (type(None), bool, int, float, str, list, dict)):
            return value

        info = self._param_info.get(name)
        if info is None:
            return cast(JsonValue, value)

        if (
            info.strategy == TypeStrategy.ADAPTER
            and info.adapter
            and info.adapter.can_serialize(value)
        ):
            return info.adapter.serialize(value)

        # Return as-is (may need to be passed through)
        return cast(JsonValue, value)


def wrap_function(
    func: F,
    registry: TypeRegistry | None = None,
    store: ObjectStore | None = None,
    transform_inputs: bool = True,
    transform_output: bool = True,
    session_manager: SessionManager | None = None,
    session_param_name: str | None = None,
) -> FunctionWrapper:
    """Wrap a function with type transformations.

    Args:
        func: The function to wrap
        registry: Type registry for adapters
        store: Object store for handles
        transform_inputs: Whether to transform inputs
        transform_output: Whether to transform outputs
        session_manager: Session manager for session injection
        session_param_name: Name of the SessionContext parameter to inject

    Returns:
        FunctionWrapper instance
    """
    return FunctionWrapper(
        func,
        registry=registry,
        store=store,
        transform_inputs=transform_inputs,
        transform_output=transform_output,
        session_manager=session_manager,
        session_param_name=session_param_name,
    )


def auto_transform(
    registry: TypeRegistry | None = None,
    store: ObjectStore | None = None,
    transform_inputs: bool = True,
    transform_output: bool = True,
) -> Callable[[F], FunctionWrapper]:
    """Decorator to automatically transform function types.

    Example:
        >>> @auto_transform()
        ... def process(data: pd.DataFrame) -> Path:
        ...     # Works with JSON inputs, returns serialized Path
        ...     return Path("/output/result.csv")

    Args:
        registry: Type registry for adapters
        store: Object store for handles
        transform_inputs: Whether to transform inputs
        transform_output: Whether to transform outputs

    Returns:
        Decorator function
    """

    def decorator(func: F) -> FunctionWrapper:
        return FunctionWrapper(
            func,
            registry=registry,
            store=store,
            transform_inputs=transform_inputs,
            transform_output=transform_output,
        )

    return decorator


class MethodWrapper:
    """Wraps class methods for type transformations.

    Handles the special case of bound methods where 'self' needs
    to be preserved.
    """

    def __init__(
        self,
        method: Callable[..., Any],
        instance: Any,
        registry: TypeRegistry | None = None,
        store: ObjectStore | None = None,
    ) -> None:
        """Initialize method wrapper.

        Args:
            method: The unbound method
            instance: The class instance
            registry: Type registry for adapters
            store: Object store for handles
        """
        self.method = method
        self.instance = instance
        self.registry = registry or get_default_registry()
        self.store = store or get_default_store()

        # Create wrapper for the underlying function
        self._func_wrapper = FunctionWrapper(
            method,
            registry=registry,
            store=store,
        )

    def call(self, kwargs: dict[str, JsonValue]) -> JsonValue:
        """Call the wrapped method with type transformations.

        Args:
            kwargs: JSON-compatible keyword arguments (excluding self)

        Returns:
            JSON-compatible return value
        """
        # Transform inputs
        transformed_kwargs = {}
        for name, value in kwargs.items():
            transformed_kwargs[name] = self._func_wrapper.transform_input(name, value)

        # Call the method with self
        result = self.method(self.instance, **transformed_kwargs)

        # Transform output
        return self._func_wrapper.transform_output(result)


class ClassWrapper:
    """Wraps a class to handle type transformations for all methods.

    Example:
        >>> class DataProcessor:
        ...     def process(self, df: pd.DataFrame) -> dict:
        ...         return {"rows": len(df)}
        >>>
        >>> wrapper = ClassWrapper(DataProcessor)
        >>> instance = wrapper.create()
        >>> result = wrapper.call_method(instance, "process", {
        ...     "df": {"columns": ["a"], "data": [[1]]}
        ... })
    """

    def __init__(
        self,
        cls: type,
        registry: TypeRegistry | None = None,
        store: ObjectStore | None = None,
    ) -> None:
        """Initialize class wrapper.

        Args:
            cls: The class to wrap
            registry: Type registry for adapters
            store: Object store for handles
        """
        self.cls = cls
        self.registry = registry or get_default_registry()
        self.store = store or get_default_store()

        # Analyze class methods
        self._method_wrappers: dict[str, FunctionWrapper] = {}
        self._analyze_methods()

    def _analyze_methods(self) -> None:
        """Analyze and wrap all public methods."""
        for name, method in inspect.getmembers(self.cls, predicate=inspect.isfunction):
            if name.startswith("_"):
                continue

            self._method_wrappers[name] = FunctionWrapper(
                method,
                registry=self.registry,
                store=self.store,
            )

    def create(self, init_kwargs: dict[str, JsonValue] | None = None) -> Any:
        """Create an instance of the wrapped class.

        Args:
            init_kwargs: JSON-compatible kwargs for __init__

        Returns:
            Class instance
        """
        if init_kwargs is None:
            return self.cls()

        # Transform init kwargs if we have a wrapper for __init__
        if "__init__" in self._method_wrappers:
            wrapper = self._method_wrappers["__init__"]
            transformed = {}
            for name, value in init_kwargs.items():
                transformed[name] = wrapper.transform_input(name, value)
            return self.cls(**transformed)

        return self.cls(**init_kwargs)

    def get_method_names(self) -> list[str]:
        """Get list of wrapped method names.

        Returns:
            List of public method names
        """
        return list(self._method_wrappers.keys())

    def get_method_schema(self, method_name: str) -> dict[str, Any]:
        """Get JSON Schema for a method's parameters.

        Args:
            method_name: Name of the method

        Returns:
            JSON Schema dictionary
        """
        if method_name not in self._method_wrappers:
            raise KeyError(f"Method not found: {method_name}")
        return self._method_wrappers[method_name].get_json_schema()

    def call_method(
        self,
        instance: Any,
        method_name: str,
        kwargs: dict[str, JsonValue],
    ) -> JsonValue:
        """Call a method on an instance with type transformations.

        Args:
            instance: The class instance
            method_name: Name of the method to call
            kwargs: JSON-compatible keyword arguments

        Returns:
            JSON-compatible return value
        """
        if method_name not in self._method_wrappers:
            raise KeyError(f"Method not found: {method_name}")

        wrapper = self._method_wrappers[method_name]

        # Transform inputs
        transformed_kwargs = {}
        for name, value in kwargs.items():
            transformed_kwargs[name] = wrapper.transform_input(name, value)

        # Get the actual method from the instance
        method = getattr(instance, method_name)
        result = method(**transformed_kwargs)

        # Transform output
        return wrapper.transform_output(result)
