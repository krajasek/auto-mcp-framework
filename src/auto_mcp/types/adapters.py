"""Built-in type adapters for common Python types.

This module provides ready-to-use adapters for frequently used types
that aren't natively JSON-serializable.
"""

from __future__ import annotations

import base64
import logging
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path, PurePath
from typing import Any
from uuid import UUID

from auto_mcp.types.base import JsonValue, TypeAdapter

logger = logging.getLogger(__name__)


# ============================================================================
# Standard Library Adapters
# ============================================================================


class DateTimeAdapter(TypeAdapter[datetime]):
    """Adapter for datetime objects using ISO 8601 format."""

    target_type = datetime

    def serialize(self, obj: datetime) -> str:
        """Convert datetime to ISO 8601 string."""
        return obj.isoformat()

    def deserialize(self, data: JsonValue) -> datetime:
        """Parse ISO 8601 string to datetime."""
        if not isinstance(data, str):
            raise TypeError(f"Expected string, got {type(data).__name__}")
        return datetime.fromisoformat(data)

    def json_schema(self) -> dict[str, Any]:
        """Return JSON Schema for datetime."""
        return {
            "type": "string",
            "format": "date-time",
            "description": "ISO 8601 datetime (e.g., 2024-01-15T10:30:00)",
        }


class DateAdapter(TypeAdapter[date]):
    """Adapter for date objects using ISO 8601 format."""

    target_type = date

    def serialize(self, obj: date) -> str:
        """Convert date to ISO 8601 string."""
        return obj.isoformat()

    def deserialize(self, data: JsonValue) -> date:
        """Parse ISO 8601 string to date."""
        if not isinstance(data, str):
            raise TypeError(f"Expected string, got {type(data).__name__}")
        return date.fromisoformat(data)

    def json_schema(self) -> dict[str, Any]:
        """Return JSON Schema for date."""
        return {
            "type": "string",
            "format": "date",
            "description": "ISO 8601 date (e.g., 2024-01-15)",
        }


class TimeAdapter(TypeAdapter[time]):
    """Adapter for time objects using ISO 8601 format."""

    target_type = time

    def serialize(self, obj: time) -> str:
        """Convert time to ISO 8601 string."""
        return obj.isoformat()

    def deserialize(self, data: JsonValue) -> time:
        """Parse ISO 8601 string to time."""
        if not isinstance(data, str):
            raise TypeError(f"Expected string, got {type(data).__name__}")
        return time.fromisoformat(data)

    def json_schema(self) -> dict[str, Any]:
        """Return JSON Schema for time."""
        return {
            "type": "string",
            "format": "time",
            "description": "ISO 8601 time (e.g., 10:30:00)",
        }


class TimeDeltaAdapter(TypeAdapter[timedelta]):
    """Adapter for timedelta objects using total seconds."""

    target_type = timedelta

    def serialize(self, obj: timedelta) -> float:
        """Convert timedelta to total seconds."""
        return obj.total_seconds()

    def deserialize(self, data: JsonValue) -> timedelta:
        """Create timedelta from seconds."""
        if not isinstance(data, (int, float)):
            raise TypeError(f"Expected number, got {type(data).__name__}")
        return timedelta(seconds=float(data))

    def json_schema(self) -> dict[str, Any]:
        """Return JSON Schema for timedelta."""
        return {
            "type": "number",
            "description": "Duration in seconds",
        }


class PathAdapter(TypeAdapter[Path]):
    """Adapter for pathlib.Path objects."""

    target_type = Path

    def serialize(self, obj: Path) -> str:
        """Convert Path to string."""
        return str(obj)

    def deserialize(self, data: JsonValue) -> Path:
        """Parse string to Path."""
        if not isinstance(data, str):
            raise TypeError(f"Expected string, got {type(data).__name__}")
        return Path(data)

    def json_schema(self) -> dict[str, Any]:
        """Return JSON Schema for Path."""
        return {
            "type": "string",
            "description": "File system path",
        }


class PurePathAdapter(TypeAdapter[PurePath]):
    """Adapter for pathlib.PurePath objects."""

    target_type = PurePath

    def serialize(self, obj: PurePath) -> str:
        """Convert PurePath to string."""
        return str(obj)

    def deserialize(self, data: JsonValue) -> PurePath:
        """Parse string to PurePath."""
        if not isinstance(data, str):
            raise TypeError(f"Expected string, got {type(data).__name__}")
        return PurePath(data)

    def json_schema(self) -> dict[str, Any]:
        """Return JSON Schema for PurePath."""
        return {
            "type": "string",
            "description": "Platform-independent file path",
        }


class UUIDAdapter(TypeAdapter[UUID]):
    """Adapter for UUID objects."""

    target_type = UUID

    def serialize(self, obj: UUID) -> str:
        """Convert UUID to string."""
        return str(obj)

    def deserialize(self, data: JsonValue) -> UUID:
        """Parse string to UUID."""
        if not isinstance(data, str):
            raise TypeError(f"Expected string, got {type(data).__name__}")
        return UUID(data)

    def json_schema(self) -> dict[str, Any]:
        """Return JSON Schema for UUID."""
        return {
            "type": "string",
            "format": "uuid",
            "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            "description": "UUID in standard format",
        }


class DecimalAdapter(TypeAdapter[Decimal]):
    """Adapter for Decimal objects."""

    target_type = Decimal

    def serialize(self, obj: Decimal) -> str:
        """Convert Decimal to string (preserves precision)."""
        return str(obj)

    def deserialize(self, data: JsonValue) -> Decimal:
        """Parse string to Decimal."""
        if isinstance(data, str):
            return Decimal(data)
        if isinstance(data, (int, float)):
            return Decimal(str(data))
        raise TypeError(f"Expected string or number, got {type(data).__name__}")

    def json_schema(self) -> dict[str, Any]:
        """Return JSON Schema for Decimal."""
        return {
            "type": "string",
            "pattern": r"^-?\d+(\.\d+)?$",
            "description": "Decimal number as string (preserves precision)",
        }


class BytesAdapter(TypeAdapter[bytes]):
    """Adapter for bytes objects using base64 encoding."""

    target_type = bytes

    def __init__(self, max_size: int | None = None) -> None:
        """Initialize with optional size limit.

        Args:
            max_size: Maximum bytes size to serialize (None for no limit)
        """
        self._max_size = max_size

    def serialize(self, obj: bytes) -> str:
        """Encode bytes as base64 string."""
        return base64.b64encode(obj).decode("ascii")

    def deserialize(self, data: JsonValue) -> bytes:
        """Decode base64 string to bytes."""
        if not isinstance(data, str):
            raise TypeError(f"Expected string, got {type(data).__name__}")
        return base64.b64decode(data)

    def json_schema(self) -> dict[str, Any]:
        """Return JSON Schema for bytes."""
        return {
            "type": "string",
            "contentEncoding": "base64",
            "description": "Base64-encoded binary data",
        }

    def can_serialize(self, obj: bytes) -> bool:
        """Check if bytes can be serialized (respecting size limit)."""
        if not isinstance(obj, bytes):
            return False
        return not (self._max_size is not None and len(obj) > self._max_size)


class ByteArrayAdapter(TypeAdapter[bytearray]):
    """Adapter for bytearray objects using base64 encoding."""

    target_type = bytearray

    def __init__(self, max_size: int | None = None) -> None:
        """Initialize with optional size limit.

        Args:
            max_size: Maximum bytes size to serialize (None for no limit)
        """
        self._max_size = max_size

    def serialize(self, obj: bytearray) -> str:
        """Encode bytearray as base64 string."""
        return base64.b64encode(obj).decode("ascii")

    def deserialize(self, data: JsonValue) -> bytearray:
        """Decode base64 string to bytearray."""
        if not isinstance(data, str):
            raise TypeError(f"Expected string, got {type(data).__name__}")
        return bytearray(base64.b64decode(data))

    def json_schema(self) -> dict[str, Any]:
        """Return JSON Schema for bytearray."""
        return {
            "type": "string",
            "contentEncoding": "base64",
            "description": "Base64-encoded binary data",
        }

    def can_serialize(self, obj: bytearray) -> bool:
        """Check if bytearray can be serialized (respecting size limit)."""
        if not isinstance(obj, bytearray):
            return False
        return not (self._max_size is not None and len(obj) > self._max_size)


class SetAdapter(TypeAdapter["set[Any]"]):
    """Adapter for set objects (converts to/from list)."""

    target_type: type[set[Any]] = set

    def serialize(self, obj: set[Any]) -> list[Any]:
        """Convert set to sorted list."""
        try:
            return sorted(obj)
        except TypeError:
            # Elements not comparable, just convert to list
            return list(obj)

    def deserialize(self, data: JsonValue) -> set[Any]:
        """Convert list to set."""
        if not isinstance(data, list):
            raise TypeError(f"Expected list, got {type(data).__name__}")
        return set(data)

    def json_schema(self) -> dict[str, Any]:
        """Return JSON Schema for set."""
        return {
            "type": "array",
            "uniqueItems": True,
            "description": "Set represented as array with unique items",
        }


class FrozenSetAdapter(TypeAdapter["frozenset[Any]"]):
    """Adapter for frozenset objects (converts to/from list)."""

    target_type: type[frozenset[Any]] = frozenset

    def serialize(self, obj: frozenset[Any]) -> list[Any]:
        """Convert frozenset to sorted list."""
        try:
            return sorted(obj)
        except TypeError:
            return list(obj)

    def deserialize(self, data: JsonValue) -> frozenset[Any]:
        """Convert list to frozenset."""
        if not isinstance(data, list):
            raise TypeError(f"Expected list, got {type(data).__name__}")
        return frozenset(data)

    def json_schema(self) -> dict[str, Any]:
        """Return JSON Schema for frozenset."""
        return {
            "type": "array",
            "uniqueItems": True,
            "description": "Frozenset represented as array with unique items",
        }


class ComplexAdapter(TypeAdapter[complex]):
    """Adapter for complex numbers."""

    target_type = complex

    def serialize(self, obj: complex) -> dict[str, float]:
        """Convert complex to dict with real and imag parts."""
        return {"real": obj.real, "imag": obj.imag}

    def deserialize(self, data: JsonValue) -> complex:
        """Convert dict to complex number."""
        if isinstance(data, dict):
            return complex(data.get("real", 0), data.get("imag", 0))
        if isinstance(data, str):
            return complex(data)
        raise TypeError(f"Expected dict or string, got {type(data).__name__}")

    def json_schema(self) -> dict[str, Any]:
        """Return JSON Schema for complex."""
        return {
            "type": "object",
            "properties": {
                "real": {"type": "number", "description": "Real part"},
                "imag": {"type": "number", "description": "Imaginary part"},
            },
            "required": ["real", "imag"],
            "description": "Complex number with real and imaginary parts",
        }


# ============================================================================
# Optional Third-Party Adapters
# ============================================================================


def create_pandas_dataframe_adapter() -> TypeAdapter[Any] | None:
    """Create adapter for pandas DataFrame if pandas is available.

    Returns:
        DataFrameAdapter instance or None if pandas not installed
    """
    try:
        import pandas as pd
    except ImportError:
        logger.debug("pandas not installed, DataFrame adapter not available")
        return None

    class DataFrameAdapter(TypeAdapter[pd.DataFrame]):
        """Adapter for pandas DataFrame objects."""

        target_type = pd.DataFrame

        def __init__(self, max_rows: int = 10000) -> None:
            """Initialize with optional row limit.

            Args:
                max_rows: Maximum rows to serialize (prevents memory issues)
            """
            self._max_rows = max_rows

        def serialize(self, obj: pd.DataFrame) -> dict[str, Any]:
            """Convert DataFrame to dict format."""
            return {
                "columns": obj.columns.tolist(),
                "data": obj.head(self._max_rows).values.tolist(),
                "dtypes": {col: str(dtype) for col, dtype in obj.dtypes.items()},
                "shape": list(obj.shape),
                "truncated": len(obj) > self._max_rows,
            }

        def deserialize(self, data: JsonValue) -> pd.DataFrame:
            """Reconstruct DataFrame from dict."""
            if not isinstance(data, dict):
                raise TypeError(f"Expected dict, got {type(data).__name__}")
            return pd.DataFrame(
                data=data.get("data", []),
                columns=data.get("columns", []),
            )

        def json_schema(self) -> dict[str, Any]:
            """Return JSON Schema for DataFrame."""
            return {
                "type": "object",
                "properties": {
                    "columns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Column names",
                    },
                    "data": {
                        "type": "array",
                        "items": {"type": "array"},
                        "description": "Row data as nested arrays",
                    },
                    "dtypes": {
                        "type": "object",
                        "description": "Column data types",
                    },
                    "shape": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "[rows, columns]",
                    },
                    "truncated": {
                        "type": "boolean",
                        "description": "Whether data was truncated",
                    },
                },
                "required": ["columns", "data"],
                "description": "Pandas DataFrame",
            }

        def can_serialize(self, obj: pd.DataFrame) -> bool:
            """Check if DataFrame can be serialized."""
            return isinstance(obj, pd.DataFrame)

    return DataFrameAdapter()


def create_pil_image_adapter() -> TypeAdapter[Any] | None:
    """Create adapter for PIL Image if Pillow is available.

    Returns:
        ImageAdapter instance or None if Pillow not installed
    """
    try:
        from PIL import Image
    except ImportError:
        logger.debug("Pillow not installed, Image adapter not available")
        return None

    import io

    class PILImageAdapter(TypeAdapter[Image.Image]):
        """Adapter for PIL Image objects."""

        target_type = Image.Image

        def __init__(
            self,
            format: str = "PNG",
            max_size: tuple[int, int] | None = None,
        ) -> None:
            """Initialize with format and size options.

            Args:
                format: Image format for serialization (PNG, JPEG, etc.)
                max_size: Maximum (width, height) before resizing
            """
            self._format = format
            self._max_size = max_size

        def serialize(self, obj: Image.Image) -> dict[str, Any]:
            """Convert Image to base64-encoded dict."""
            img = obj

            # Resize if needed
            if self._max_size and (
                img.width > self._max_size[0] or img.height > self._max_size[1]
            ):
                img = img.copy()
                img.thumbnail(self._max_size, Image.Resampling.LANCZOS)

            # Convert to bytes
            buffer = io.BytesIO()
            img.save(buffer, format=self._format)
            image_bytes = buffer.getvalue()

            return {
                "data": base64.b64encode(image_bytes).decode("ascii"),
                "format": self._format.lower(),
                "width": img.width,
                "height": img.height,
                "mode": img.mode,
            }

        def deserialize(self, data: JsonValue) -> Image.Image:
            """Reconstruct Image from dict."""
            if not isinstance(data, dict):
                raise TypeError(f"Expected dict, got {type(data).__name__}")

            image_bytes = base64.b64decode(data["data"])
            buffer = io.BytesIO(image_bytes)
            return Image.open(buffer)

        def json_schema(self) -> dict[str, Any]:
            """Return JSON Schema for Image."""
            return {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "string",
                        "contentEncoding": "base64",
                        "description": "Base64-encoded image data",
                    },
                    "format": {
                        "type": "string",
                        "description": "Image format (png, jpeg, etc.)",
                    },
                    "width": {"type": "integer", "description": "Image width"},
                    "height": {"type": "integer", "description": "Image height"},
                    "mode": {"type": "string", "description": "PIL image mode"},
                },
                "required": ["data", "format"],
                "description": "PIL Image",
            }

        def can_serialize(self, obj: Image.Image) -> bool:
            """Check if Image can be serialized."""
            return isinstance(obj, Image.Image)

    return PILImageAdapter()


def create_numpy_array_adapter() -> TypeAdapter[Any] | None:
    """Create adapter for numpy ndarray if numpy is available.

    Returns:
        NumpyArrayAdapter instance or None if numpy not installed
    """
    try:
        import numpy as np
    except ImportError:
        logger.debug("numpy not installed, ndarray adapter not available")
        return None

    class NumpyArrayAdapter(TypeAdapter[np.ndarray]):
        """Adapter for numpy ndarray objects."""

        target_type = np.ndarray

        def __init__(self, max_elements: int = 100000) -> None:
            """Initialize with element limit.

            Args:
                max_elements: Maximum elements to serialize
            """
            self._max_elements = max_elements

        def serialize(self, obj: np.ndarray) -> dict[str, Any]:
            """Convert ndarray to dict format."""
            flat = obj.flatten()
            truncated = len(flat) > self._max_elements

            return {
                "data": flat[: self._max_elements].tolist(),
                "shape": list(obj.shape),
                "dtype": str(obj.dtype),
                "truncated": truncated,
            }

        def deserialize(self, data: JsonValue) -> np.ndarray:
            """Reconstruct ndarray from dict."""
            if not isinstance(data, dict):
                raise TypeError(f"Expected dict, got {type(data).__name__}")

            arr = np.array(data["data"], dtype=data.get("dtype"))
            shape = data.get("shape")
            if shape and not data.get("truncated"):
                arr = arr.reshape(shape)
            return arr

        def json_schema(self) -> dict[str, Any]:
            """Return JSON Schema for ndarray."""
            return {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "array",
                        "description": "Flattened array data",
                    },
                    "shape": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Array dimensions",
                    },
                    "dtype": {
                        "type": "string",
                        "description": "NumPy data type",
                    },
                    "truncated": {
                        "type": "boolean",
                        "description": "Whether data was truncated",
                    },
                },
                "required": ["data", "shape", "dtype"],
                "description": "NumPy ndarray",
            }

        def can_serialize(self, obj: np.ndarray) -> bool:
            """Check if ndarray can be serialized."""
            return isinstance(obj, np.ndarray)

    return NumpyArrayAdapter()


# ============================================================================
# Registry Helper Functions
# ============================================================================


def get_stdlib_adapters() -> list[TypeAdapter[Any]]:
    """Get all standard library type adapters.

    Returns:
        List of adapter instances for stdlib types
    """
    return [
        DateTimeAdapter(),
        DateAdapter(),
        TimeAdapter(),
        TimeDeltaAdapter(),
        PathAdapter(),
        PurePathAdapter(),
        UUIDAdapter(),
        DecimalAdapter(),
        BytesAdapter(),
        ByteArrayAdapter(),
        SetAdapter(),
        FrozenSetAdapter(),
        ComplexAdapter(),
    ]


def get_optional_adapters() -> list[TypeAdapter[Any]]:
    """Get adapters for optional third-party libraries.

    Only returns adapters for libraries that are installed.

    Returns:
        List of adapter instances for available libraries
    """
    adapters: list[TypeAdapter[Any]] = []

    pandas_adapter = create_pandas_dataframe_adapter()
    if pandas_adapter:
        adapters.append(pandas_adapter)

    pil_adapter = create_pil_image_adapter()
    if pil_adapter:
        adapters.append(pil_adapter)

    numpy_adapter = create_numpy_array_adapter()
    if numpy_adapter:
        adapters.append(numpy_adapter)

    return adapters


def get_all_adapters() -> list[TypeAdapter[Any]]:
    """Get all available adapters (stdlib + optional).

    Returns:
        List of all available adapter instances
    """
    return get_stdlib_adapters() + get_optional_adapters()


def register_stdlib_adapters(registry: Any) -> None:
    """Register all standard library adapters with a registry.

    Args:
        registry: TypeRegistry instance
    """
    for adapter in get_stdlib_adapters():
        registry.register_adapter(adapter)


def register_all_adapters(registry: Any) -> None:
    """Register all available adapters with a registry.

    Args:
        registry: TypeRegistry instance
    """
    for adapter in get_all_adapters():
        registry.register_adapter(adapter)
