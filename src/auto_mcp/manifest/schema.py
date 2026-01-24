"""Pydantic models for manifest schema.

This module defines the structure for manifest YAML files that specify
which tools to expose in the generated MCP server.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator


class ToolEntry(BaseModel):
    """A tool entry in the manifest with optional customization."""

    function: str = Field(..., description="Function or method path (e.g., 'read_csv', 'DataFrame.to_csv')")
    name: str | None = Field(default=None, description="Optional rename for the tool")
    description: str | None = Field(default=None, description="Optional custom description")

    model_config = {"extra": "forbid"}


class Manifest(BaseModel):
    """MCP manifest schema for selective tool exposure.

    Example manifest:
        ```yaml
        package: pandas
        module: pandas
        server_name: pandas-mcp-server
        auto_include_dependencies: true

        tools:
          - read_csv
          - read_excel
          - DataFrame
          - DataFrame.to_*
          - function: read_json
            name: load_json
            description: "Load JSON file into DataFrame"
        ```
    """

    package: str | None = Field(
        default=None, description="PyPI package name (optional if inferred from CLI)"
    )
    module: str | None = Field(
        default=None, description="Import name (defaults to package name)"
    )
    version: str | None = Field(default=None, description="Version constraint (optional)")
    server_name: str | None = Field(
        default=None, description="MCP server name (defaults to 'auto-mcp-server')"
    )
    auto_include_dependencies: bool = Field(
        default=True,
        description="Auto-include functions that produce types needed by listed tools",
    )
    tools: list[str | ToolEntry] = Field(
        default_factory=list,
        description="List of tools to expose (patterns, class names, or ToolEntry objects)",
    )

    model_config = {"extra": "forbid"}

    def get_module_name(self, fallback: str | None = None) -> str:
        """Get the module import name.

        Args:
            fallback: Fallback module name if not specified in manifest

        Returns:
            Module name for import
        """
        if self.module:
            return self.module
        if self.package:
            return self.package
        if fallback:
            return fallback
        raise ValueError("No module name available - specify in manifest or provide fallback")

    def get_server_name(self, fallback: str = "auto-mcp-server") -> str:
        """Get the server name.

        Args:
            fallback: Fallback server name if not specified

        Returns:
            Server name for the MCP server
        """
        return self.server_name or fallback

    def get_tool_entries(self) -> list[ToolEntry]:
        """Convert all tool specifications to ToolEntry objects.

        Returns:
            List of ToolEntry objects with normalized patterns
        """
        entries = []
        for tool in self.tools:
            if isinstance(tool, str):
                entries.append(ToolEntry(function=tool))
            else:
                entries.append(tool)
        return entries

    @classmethod
    def from_yaml(cls, path: Path) -> Manifest:
        """Load a manifest from a YAML file.

        Args:
            path: Path to the YAML manifest file

        Returns:
            Parsed Manifest object

        Raises:
            FileNotFoundError: If the manifest file doesn't exist
            yaml.YAMLError: If the YAML is invalid
            ValidationError: If the manifest structure is invalid
        """
        if not path.exists():
            raise FileNotFoundError(f"Manifest file not found: {path}")

        with open(path) as f:
            data = yaml.safe_load(f)

        if data is None:
            data = {}

        return cls.model_validate(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Manifest:
        """Create a manifest from a dictionary.

        Args:
            data: Dictionary containing manifest data

        Returns:
            Parsed Manifest object
        """
        return cls.model_validate(data)

    def to_yaml(self, path: Path) -> None:
        """Write the manifest to a YAML file.

        Args:
            path: Path to write the YAML file
        """
        data = self.model_dump(exclude_none=True)
        # Convert ToolEntry objects back to dicts
        tools = []
        for tool in data.get("tools", []):
            if isinstance(tool, dict) and "function" in tool:
                # If only function is set, convert to string
                if tool.get("name") is None and tool.get("description") is None:
                    tools.append(tool["function"])
                else:
                    tools.append(tool)
            else:
                tools.append(tool)
        data["tools"] = tools

        with open(path, "w") as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)

    @model_validator(mode="after")
    def validate_tools_present(self) -> Manifest:
        """Validate that tools list is not empty when provided."""
        # Empty tools list is allowed - means generate all tools from package
        return self
