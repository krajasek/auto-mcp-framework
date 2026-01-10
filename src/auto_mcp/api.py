"""High-level Python API for auto-mcp."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Literal

from mcp.server.fastmcp import FastMCP

from auto_mcp.cache import PromptCache
from auto_mcp.core.generator import GeneratorConfig, MCPGenerator
from auto_mcp.core.package import PackageMetadata
from auto_mcp.llm import LLMProvider, create_provider

if TYPE_CHECKING:
    from auto_mcp.core.generator import (
        GeneratedPrompt,
        GeneratedResource,
        GeneratedTool,
    )


class AutoMCP:
    """High-level API for generating MCP servers from Python modules.

    This class provides a simple, user-friendly interface for:
    - Analyzing Python modules
    - Generating MCP servers (in-memory, standalone file, or package)
    - Configuring LLM providers and caching

    Example:
        >>> from auto_mcp import AutoMCP
        >>> import my_module
        >>>
        >>> # Create with default settings (Ollama)
        >>> auto = AutoMCP()
        >>>
        >>> # Or with custom LLM provider
        >>> auto = AutoMCP(llm_provider="openai", llm_model="gpt-4o-mini")
        >>>
        >>> # Generate and run a server
        >>> server = auto.create_server([my_module])
        >>> server.run()
        >>>
        >>> # Or generate a standalone file
        >>> auto.generate_file([my_module], "server.py")
    """

    def __init__(
        self,
        *,
        llm_provider: Literal["ollama", "openai", "anthropic"] | None = None,
        llm_model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        use_llm: bool = True,
        use_cache: bool = True,
        cache_dir: Path | str | None = None,
        server_name: str = "auto-mcp-server",
        include_private: bool = False,
        generate_resources: bool = True,
        generate_prompts: bool = True,
        max_depth: int | None = None,
        public_api_only: bool = False,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        include_reexports: bool = False,
        enable_sessions: bool = False,
        session_ttl: int = 3600,
        max_sessions: int = 100,
    ) -> None:
        """Initialize AutoMCP.

        Args:
            llm_provider: LLM provider to use (ollama, openai, anthropic).
                         Defaults to ollama if use_llm is True.
            llm_model: Model name. Uses provider default if not specified.
            api_key: API key for cloud providers (OpenAI, Anthropic).
            base_url: Custom base URL for the LLM provider.
            use_llm: Whether to use LLM for description generation.
                    If False, uses docstrings only.
            use_cache: Whether to cache generated descriptions.
            cache_dir: Directory for cache files. Uses default if not specified.
            server_name: Name for generated MCP servers.
            include_private: Whether to include private methods (starting with _).
            generate_resources: Whether to generate MCP resources.
            generate_prompts: Whether to generate MCP prompts.
            max_depth: Maximum recursion depth for package analysis.
            public_api_only: Only expose functions in __all__ (public API).
            include_patterns: Glob patterns for modules to include.
            exclude_patterns: Glob patterns for modules to exclude.
            include_reexports: Include functions re-exported in __all__ from
                              submodules (useful for packages like pandas, numpy).
            enable_sessions: Enable session lifecycle support.
            session_ttl: Default session TTL in seconds.
            max_sessions: Maximum number of concurrent sessions.
        """
        self._use_llm = use_llm
        self._use_cache = use_cache

        # Create LLM provider if enabled
        self._llm: LLMProvider | None = None
        if use_llm:
            provider = llm_provider or "ollama"
            self._llm = create_provider(
                provider,
                model=llm_model,
                api_key=api_key,
                base_url=base_url,
            )

        # Create cache
        cache_path = Path(cache_dir) if cache_dir else None
        self._cache = PromptCache(cache_dir=cache_path) if use_cache else PromptCache()

        # Store configuration
        self._config = GeneratorConfig(
            server_name=server_name,
            include_private=include_private,
            generate_resources=generate_resources,
            generate_prompts=generate_prompts,
            use_cache=use_cache,
            use_llm=use_llm and self._llm is not None,
            max_depth=max_depth,
            public_api_only=public_api_only,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            include_reexports=include_reexports,
            enable_sessions=enable_sessions,
            session_ttl=session_ttl,
            max_sessions=max_sessions,
        )

        # Create generator
        self._generator = MCPGenerator(
            llm=self._llm,
            cache=self._cache,
            config=self._config,
        )

    @property
    def llm_provider(self) -> LLMProvider | None:
        """Get the LLM provider instance."""
        return self._llm

    @property
    def config(self) -> GeneratorConfig:
        """Get the generator configuration."""
        return self._config

    def create_server(
        self,
        modules: list[ModuleType],
        *,
        name: str | None = None,
        context: str | None = None,
    ) -> FastMCP:
        """Create an in-memory MCP server from modules.

        Args:
            modules: List of Python modules to expose as MCP tools.
            name: Override the server name. Uses default from config if not specified.
            context: Additional context for LLM description generation.

        Returns:
            A configured FastMCP server instance ready to run.

        Example:
            >>> server = auto.create_server([my_module])
            >>> server.run()  # Runs with stdio transport
        """
        if name:
            # Temporarily update config for this generation
            original_name = self._config.server_name
            self._config.server_name = name
            try:
                return self._generator.create_server(modules, context=context)
            finally:
                self._config.server_name = original_name
        return self._generator.create_server(modules, context=context)

    def generate_file(
        self,
        modules: list[ModuleType],
        output: Path | str,
        *,
        name: str | None = None,
        context: str | None = None,
    ) -> Path:
        """Generate a standalone MCP server Python file.

        Args:
            modules: List of Python modules to expose as MCP tools.
            output: Output path for the generated file.
            name: Override the server name.
            context: Additional context for LLM description generation.

        Returns:
            Path to the generated file.

        Example:
            >>> auto.generate_file([my_module], "server.py")
            >>> # Run with: python server.py
        """
        if name:
            original_name = self._config.server_name
            self._config.server_name = name
            try:
                return self._generator.generate_standalone(
                    modules, Path(output), context=context
                )
            finally:
                self._config.server_name = original_name
        return self._generator.generate_standalone(modules, Path(output), context=context)

    def generate_package(
        self,
        modules: list[ModuleType],
        output_dir: Path | str,
        package_name: str,
        *,
        context: str | None = None,
    ) -> Path:
        """Generate a complete MCP server package.

        Args:
            modules: List of Python modules to expose as MCP tools.
            output_dir: Directory to create the package in.
            package_name: Name for the generated package.
            context: Additional context for LLM description generation.

        Returns:
            Path to the generated package directory.

        Example:
            >>> auto.generate_package([my_module], "./dist", "my-mcp-server")
            >>> # Install with: pip install ./dist/my-mcp-server
        """
        return self._generator.generate_package(
            modules, Path(output_dir), package_name, context=context
        )

    async def analyze(
        self,
        modules: list[ModuleType],
        *,
        context: str | None = None,
    ) -> tuple[list[GeneratedTool], list[GeneratedResource], list[GeneratedPrompt]]:
        """Analyze modules and generate MCP component metadata.

        This is useful for inspecting what would be generated without
        actually creating a server or file.

        Args:
            modules: List of Python modules to analyze.
            context: Additional context for LLM description generation.

        Returns:
            Tuple of (tools, resources, prompts) that would be generated.

        Example:
            >>> tools, resources, prompts = await auto.analyze([my_module])
            >>> for tool in tools:
            ...     print(f"{tool.name}: {tool.description}")
        """
        return await self._generator.analyze_and_generate(modules, context)

    def analyze_sync(
        self,
        modules: list[ModuleType],
        *,
        context: str | None = None,
    ) -> tuple[list[GeneratedTool], list[GeneratedResource], list[GeneratedPrompt]]:
        """Synchronous version of analyze().

        Args:
            modules: List of Python modules to analyze.
            context: Additional context for LLM description generation.

        Returns:
            Tuple of (tools, resources, prompts) that would be generated.
        """
        return asyncio.run(self.analyze(modules, context=context))

    # Package-based methods

    def create_server_from_package(
        self,
        package: str | ModuleType,
        *,
        name: str | None = None,
        context: str | None = None,
    ) -> FastMCP:
        """Create an in-memory MCP server from a package.

        This method recursively analyzes all submodules of a package
        and exposes their functions as MCP tools.

        Args:
            package: Package name (e.g., "requests") or module object.
            name: Override the server name.
            context: Additional context for LLM description generation.

        Returns:
            A configured FastMCP server instance ready to run.

        Example:
            >>> server = auto.create_server_from_package("requests")
            >>> server.run()

            >>> # With filtering
            >>> auto = AutoMCP(
            ...     include_patterns=["requests.api.*"],
            ...     exclude_patterns=["requests.compat.*"],
            ... )
            >>> server = auto.create_server_from_package("requests")
        """
        if name:
            original_name = self._config.server_name
            self._config.server_name = name
            try:
                return self._generator.create_server_from_package(package, context)
            finally:
                self._config.server_name = original_name
        return self._generator.create_server_from_package(package, context)

    def generate_file_from_package(
        self,
        package: str | ModuleType,
        output: Path | str,
        *,
        name: str | None = None,
        context: str | None = None,
    ) -> Path:
        """Generate a standalone MCP server file from a package.

        Args:
            package: Package name (e.g., "requests") or module object.
            output: Output path for the generated file.
            name: Override the server name.
            context: Additional context for LLM description generation.

        Returns:
            Path to the generated file.

        Example:
            >>> auto.generate_file_from_package("requests", "requests_server.py")
        """
        if name:
            original_name = self._config.server_name
            self._config.server_name = name
            try:
                return self._generator.generate_standalone_from_package(
                    package, Path(output), context
                )
            finally:
                self._config.server_name = original_name
        return self._generator.generate_standalone_from_package(
            package, Path(output), context
        )

    def analyze_package(
        self,
        package: str | ModuleType,
    ) -> PackageMetadata:
        """Analyze a package and return detailed metadata.

        This is useful for inspecting what would be exposed without
        actually creating a server.

        Args:
            package: Package name (e.g., "requests") or module object.

        Returns:
            PackageMetadata with all discovered modules and methods.

        Example:
            >>> metadata = auto.analyze_package("requests")
            >>> print(f"Found {metadata.module_count} modules")
            >>> print(f"Found {metadata.method_count} methods")
            >>> for mod_name, mod_info in metadata.modules.items():
            ...     print(f"  {mod_name}: {len(mod_info.submodules)} submodules")
        """
        return self._generator.analyze_package(package)

    async def analyze_package_async(
        self,
        package: str | ModuleType,
        *,
        context: str | None = None,
    ) -> tuple[list[GeneratedTool], list[GeneratedResource], list[GeneratedPrompt]]:
        """Analyze a package and generate MCP component metadata.

        This is useful for inspecting what tools/resources/prompts would
        be generated from a package.

        Args:
            package: Package name (e.g., "requests") or module object.
            context: Additional context for LLM description generation.

        Returns:
            Tuple of (tools, resources, prompts) that would be generated.
        """
        return await self._generator.analyze_and_generate_from_package(package, context)

    def analyze_package_sync(
        self,
        package: str | ModuleType,
        *,
        context: str | None = None,
    ) -> tuple[list[GeneratedTool], list[GeneratedResource], list[GeneratedPrompt]]:
        """Synchronous version of analyze_package_async().

        Args:
            package: Package name (e.g., "requests") or module object.
            context: Additional context for LLM description generation.

        Returns:
            Tuple of (tools, resources, prompts) that would be generated.
        """
        return asyncio.run(self.analyze_package_async(package, context=context))

    def save_cache(self, modules: list[ModuleType] | None = None) -> None:
        """Save cache to disk.

        Args:
            modules: Specific modules to save cache for.
                    If None, saves all cached modules.
        """
        if modules:
            for module in modules:
                self._cache.save(module.__name__)
        else:
            self._cache.save_all()

    def clear_cache(self, modules: list[ModuleType] | None = None) -> int:
        """Clear cached descriptions.

        Args:
            modules: Specific modules to clear cache for.
                    If None, clears all cached entries.

        Returns:
            Number of entries cleared.
        """
        if modules:
            total = 0
            for module in modules:
                total += self._cache.invalidate(module.__name__)
            return total
        return self._cache.clear()

    def shutdown(self) -> None:
        """Release resources and save cache.

        Call this when done using the AutoMCP instance.
        """
        self._cache.save_all()
        if self._llm:
            self._llm.shutdown()

    def __enter__(self) -> AutoMCP:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Context manager exit - ensures cleanup."""
        self.shutdown()


# Convenience function for quick server creation
def quick_server(
    *modules: ModuleType,
    name: str = "auto-mcp-server",
    use_llm: bool = False,
) -> FastMCP:
    """Quickly create an MCP server from modules.

    This is a convenience function for simple use cases where you
    don't need fine-grained control over the generation process.

    Args:
        *modules: One or more Python modules to expose.
        name: Name for the server.
        use_llm: Whether to use LLM for descriptions (default: False for speed).

    Returns:
        A configured FastMCP server.

    Example:
        >>> from auto_mcp import quick_server
        >>> import my_module
        >>>
        >>> server = quick_server(my_module, name="My Server")
        >>> server.run()
    """
    auto = AutoMCP(use_llm=use_llm, use_cache=False, server_name=name)
    return auto.create_server(list(modules))


def quick_server_from_package(
    package: str | ModuleType,
    *,
    name: str = "auto-mcp-server",
    use_llm: bool = False,
    public_api_only: bool = True,
    max_depth: int | None = None,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> FastMCP:
    """Quickly create an MCP server from an installed package.

    This is a convenience function for creating servers from packages
    like `requests`, `json`, etc. without fine-grained control.

    Args:
        package: Package name (e.g., "requests") or module object.
        name: Name for the server.
        use_llm: Whether to use LLM for descriptions (default: False for speed).
        public_api_only: Only expose functions in __all__ (recommended).
        max_depth: Maximum recursion depth for submodule discovery.
        include_patterns: Glob patterns for modules to include.
        exclude_patterns: Glob patterns for modules to exclude.

    Returns:
        A configured FastMCP server.

    Example:
        >>> from auto_mcp import quick_server_from_package
        >>>
        >>> # Create server from requests library
        >>> server = quick_server_from_package("requests", name="HTTP Server")
        >>> server.run()
        >>>
        >>> # Create server with filtering
        >>> server = quick_server_from_package(
        ...     "requests",
        ...     include_patterns=["requests.api.*"],
        ...     max_depth=2,
        ... )
    """
    auto = AutoMCP(
        use_llm=use_llm,
        use_cache=False,
        server_name=name,
        public_api_only=public_api_only,
        max_depth=max_depth,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
    )
    return auto.create_server_from_package(package)
