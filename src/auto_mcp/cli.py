"""Command-line interface for auto-mcp."""

from __future__ import annotations

import fnmatch
import importlib
import importlib.util
import inspect as inspect_module
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Literal

import click
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.tree import Tree

from auto_mcp.cache import PromptCache
from auto_mcp.config import Settings, get_settings
from auto_mcp.core.analyzer import MethodMetadata, ModuleAnalyzer
from auto_mcp.core.generator import GeneratorConfig, MCPGenerator
from auto_mcp.core.package import PackageAnalyzer
from auto_mcp.llm import LLMProvider, create_provider
from auto_mcp.types import FunctionWrapper, get_default_registry
from auto_mcp.watcher import HotReloadServer

console = Console()
error_console = Console(stderr=True)


def load_module_from_path(module_path: Path) -> ModuleType:
    """Load a Python module from a file path.

    Args:
        module_path: Path to the Python file

    Returns:
        The loaded module

    Raises:
        click.ClickException: If the module cannot be loaded
    """
    if not module_path.exists():
        raise click.ClickException(f"Module not found: {module_path}")

    if not module_path.suffix == ".py":
        raise click.ClickException(f"Not a Python file: {module_path}")

    module_name = module_path.stem

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise click.ClickException(f"Cannot load module: {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)
    except Exception as e:
        raise click.ClickException(f"Error loading module: {e}") from e

    return module


def load_modules(module_paths: tuple[str, ...]) -> list[ModuleType]:
    """Load multiple modules from paths.

    Args:
        module_paths: Tuple of module path strings

    Returns:
        List of loaded modules
    """
    modules = []
    for path_str in module_paths:
        path = Path(path_str).resolve()
        module = load_module_from_path(path)
        modules.append(module)
    return modules


def get_llm_provider(
    provider: str | None,
    model: str | None,
    settings: Settings,
) -> LLMProvider | None:
    """Get an LLM provider based on settings.

    Args:
        provider: Provider name override
        model: Model name override
        settings: Application settings

    Returns:
        LLM provider instance or None
    """
    provider_name = provider or settings.llm_provider
    model_name = model or settings.llm_model

    # Get API keys from settings
    api_key = None
    if provider_name == "openai":
        api_key = settings.openai_api_key
    elif provider_name == "anthropic":
        api_key = settings.anthropic_api_key

    try:
        return create_provider(
            provider_name,  # type: ignore[arg-type]
            model=model_name,
            api_key=api_key,
        )
    except Exception as e:
        error_console.print(f"[yellow]Warning: Could not create LLM provider: {e}[/yellow]")
        return None


@click.group()
@click.version_option(package_name="auto-mcp-tool")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """auto-mcp-tool: Automatically generate MCP servers from Python modules.

    Use this tool to analyze Python modules and generate MCP-compatible
    servers with tools, resources, and prompts.
    """
    ctx.ensure_object(dict)
    ctx.obj["settings"] = get_settings()


@cli.command()
@click.argument("source", required=True)
@click.option(
    "-o",
    "--output",
    type=click.Path(),
    required=True,
    help="Output path for generated server file",
)
@click.option(
    "--manifest",
    type=click.Path(exists=True),
    help="YAML manifest for selective tool exposure. If not provided, exposes entire module/package.",
)
@click.option(
    "--name",
    type=str,
    default=None,
    help="Name for the generated server (defaults to 'auto-mcp-server' or package name)",
)
@click.option(
    "--version",
    "pkg_version",
    type=str,
    default=None,
    help="Package version to use with uvx isolation (e.g., '2.28.0')",
)
@click.option(
    "--no-isolated",
    is_flag=True,
    help="Disable uvx isolation (fail if package not installed locally)",
)
@click.option(
    "--llm-provider",
    type=click.Choice(["ollama", "openai", "anthropic"]),
    help="LLM provider for description generation",
)
@click.option(
    "--llm-model",
    type=str,
    help="Model name for description generation",
)
@click.option(
    "--no-llm",
    is_flag=True,
    help="Disable LLM description generation (use docstrings only)",
)
@click.option(
    "--no-cache",
    is_flag=True,
    help="Disable caching of generated descriptions",
)
@click.option(
    "--include-private",
    is_flag=True,
    help="Include private methods (starting with _)",
)
@click.option(
    "--no-resources",
    is_flag=True,
    help="Don't generate MCP resources",
)
@click.option(
    "--no-prompts",
    is_flag=True,
    help="Don't generate MCP prompts",
)
@click.option(
    "--context",
    type=str,
    help="Additional context for LLM description generation",
)
@click.option(
    "--enable-sessions",
    is_flag=True,
    help="Enable session lifecycle support (create_session/close_session tools)",
)
@click.option(
    "--session-ttl",
    type=int,
    default=3600,
    help="Session TTL in seconds (default: 3600)",
)
@click.option(
    "--max-sessions",
    type=int,
    default=100,
    help="Maximum number of concurrent sessions (default: 100)",
)
@click.option(
    "--max-depth",
    type=int,
    default=None,
    help="Maximum recursion depth for package submodule discovery",
)
@click.option(
    "--public-api-only",
    is_flag=True,
    help="Only expose functions in __all__ (public API) - for packages",
)
@click.option(
    "--include-reexports",
    is_flag=True,
    help="Include functions re-exported in __all__ from submodules",
)
@click.option(
    "--wrapper",
    is_flag=True,
    help="Use wrapper generator for C extension modules (enables handle-based storage)",
)
@click.pass_context
def generate(
    ctx: click.Context,
    source: str,
    output: str,
    manifest: str | None,
    name: str | None,
    pkg_version: str | None,
    no_isolated: bool,
    llm_provider: str | None,
    llm_model: str | None,
    no_llm: bool,
    no_cache: bool,
    include_private: bool,
    no_resources: bool,
    no_prompts: bool,
    context: str | None,
    enable_sessions: bool,
    session_ttl: int,
    max_sessions: int,
    max_depth: int | None,
    public_api_only: bool,
    include_reexports: bool,
    wrapper: bool,
) -> None:
    """Generate an MCP server from a Python file or installed package.

    SOURCE can be:
    \b
    - A Python file: mymodule.py, src/lib.py
    - A package name: pandas, requests, sqlite3

    Examples:

    \b
        # From a Python file
        auto-mcp-tool generate mymodule.py -o server.py

    \b
        # From an installed package
        auto-mcp-tool generate requests -o requests_server.py

    \b
        # With manifest for selective tool exposure
        auto-mcp-tool generate pandas --manifest pandas_tools.yaml -o server.py

    \b
        # Specific package version (uses uvx isolation)
        auto-mcp-tool generate requests --version 2.28.0 -o server.py

    \b
        # Generate with custom server name
        auto-mcp-tool generate mymodule.py -o server.py --name "My Server"

    \b
        # Generate without LLM (use docstrings only)
        auto-mcp-tool generate json -o json_server.py --no-llm
    """
    settings: Settings = ctx.obj["settings"]
    output_path = Path(output).resolve()

    # Detect source type: file or package
    source_path = Path(source)
    is_file = source.endswith(".py") or source_path.exists()

    if is_file:
        # File-based generation
        _generate_from_file(
            ctx=ctx,
            source_path=source_path,
            output_path=output_path,
            manifest_path=Path(manifest) if manifest else None,
            name=name or "auto-mcp-server",
            llm_provider=llm_provider,
            llm_model=llm_model,
            no_llm=no_llm,
            no_cache=no_cache,
            include_private=include_private,
            no_resources=no_resources,
            no_prompts=no_prompts,
            context=context,
            enable_sessions=enable_sessions,
            session_ttl=session_ttl,
            max_sessions=max_sessions,
            settings=settings,
        )
    else:
        # Package-based generation
        _generate_from_package(
            ctx=ctx,
            package_name=source,
            output_path=output_path,
            manifest_path=Path(manifest) if manifest else None,
            name=name,
            pkg_version=pkg_version,
            no_isolated=no_isolated,
            llm_provider=llm_provider,
            llm_model=llm_model,
            no_llm=no_llm,
            no_cache=no_cache,
            include_private=include_private,
            no_resources=no_resources,
            no_prompts=no_prompts,
            context=context,
            enable_sessions=enable_sessions,
            session_ttl=session_ttl,
            max_sessions=max_sessions,
            max_depth=max_depth,
            public_api_only=public_api_only,
            include_reexports=include_reexports,
            use_wrapper=wrapper,
            settings=settings,
        )


def _generate_with_wrapper(
    package_name: str,
    output_path: Path,
    server_name: str,
    include_private: bool = False,
) -> None:
    """Generate MCP server using wrapper generator for C extensions.

    This uses the wrapper generator to properly handle C extension modules,
    including:
    - Parsing signatures from __text_signature__ and docstrings
    - Handle-based storage for non-serializable types (Connection, Cursor, etc.)
    - Proper method wrapping for classes

    Args:
        package_name: Name of the package to generate from
        output_path: Path to write the generated server
        server_name: Name for the MCP server
        include_private: Whether to include private methods
    """
    from auto_mcp.wrapper.generator import WrapperGenerator

    try:
        module = importlib.import_module(package_name)
    except ImportError as e:
        raise click.ClickException(f"Cannot import package '{package_name}': {e}") from None

    console.print(f"[green]✓[/green] Loaded module: {package_name}")

    # Create wrapper generator
    wrapper_gen = WrapperGenerator(
        include_private=include_private,
        include_dunder=False,
    )

    # Check if it's a C extension
    is_c_ext = wrapper_gen.is_c_extension_module(module)
    if is_c_ext:
        console.print("[dim]Detected C extension module, using wrapper generator[/dim]")

    # Analyze module
    with console.status("[bold blue]Analyzing module..."):
        functions, classes = wrapper_gen.analyze_module(module)

    console.print(f"[green]✓[/green] Found {len(functions)} functions and {len(classes)} classes")

    # Generate MCP server code
    with console.status("[bold blue]Generating MCP server..."):
        code = _generate_wrapper_mcp_server(
            module_name=package_name,
            server_name=server_name,
            functions=functions,
            classes=classes,
            wrapper_gen=wrapper_gen,
        )

    # Write to file
    output_path.write_text(code)

    console.print(f"[green]✓[/green] Generated server at: {output_path}")
    console.print(f"\n[dim]To run: python {output_path}[/dim]")


def _generate_wrapper_mcp_server(
    module_name: str,
    server_name: str,
    functions: list,
    classes: list,
    wrapper_gen: Any,
) -> str:
    """Generate MCP server code from wrapper analysis.

    Args:
        module_name: Name of the module
        server_name: Name for the MCP server
        functions: List of CallableInfo for functions
        classes: List of ClassInfo for classes
        wrapper_gen: WrapperGenerator instance

    Returns:
        Generated MCP server code
    """
    lines = [
        '"""Auto-generated MCP server with wrapper support.',
        "",
        f"Module: {module_name}",
        f"Server: {server_name}",
        '"""',
        "",
        "from typing import Any",
        "",
        "from mcp.server.fastmcp import FastMCP",
        "",
        f"import {module_name}",
        "",
        "# Object store for handle-based types",
        "_object_store: dict[str, Any] = {}",
        "_handle_counter: int = 0",
        "",
        "",
        "def _store_object(obj: Any, type_name: str) -> str:",
        '    """Store an object and return a handle string."""',
        "    global _handle_counter",
        "    _handle_counter += 1",
        '    handle = f"{type_name}_{_handle_counter}"',
        "    _object_store[handle] = obj",
        "    return handle",
        "",
        "",
        "def _get_object(handle: str) -> Any:",
        '    """Retrieve an object by its handle."""',
        "    obj = _object_store.get(handle)",
        "    if obj is None:",
        '        raise ValueError(f"Invalid or expired handle: {handle}")',
        "    return obj",
        "",
        "",
        f'mcp = FastMCP(name="{server_name}")',
        "",
    ]

    # Collect all class names for handle type detection
    class_names = {cls.name for cls in classes}

    # Build factory inference map (e.g., connect -> Connection)
    factory_map = _build_factory_map(class_names)

    # Build method return type map (e.g., execute -> Cursor)
    method_return_map = _build_method_return_map(class_names)

    # Generate function wrappers
    for func in functions:
        func_lines = _generate_wrapper_tool(
            func, module_name, class_names, factory_map, is_method=False
        )
        lines.extend(func_lines)
        lines.append("")

    # Generate class method wrappers
    for cls in classes:
        for method in cls.methods:
            # Skip dunder methods except __init__
            if method.name.startswith("__") and method.name != "__init__":
                continue

            method_lines = _generate_wrapper_tool(
                method, module_name, class_names, method_return_map,
                is_method=True, class_name=cls.name
            )
            lines.extend(method_lines)
            lines.append("")

    # Generate main entry point
    lines.extend([
        "",
        'if __name__ == "__main__":',
        "    mcp.run()",
    ])

    return "\n".join(lines)


def _build_factory_map(class_names: set[str]) -> dict[str, str]:
    """Build map of function names to class names they likely return."""
    factory_map = {}
    for class_name in class_names:
        lower = class_name.lower()
        # connect -> Connection
        if lower.endswith("ion"):
            factory_map[lower[:-3]] = class_name
        # cursor -> Cursor
        factory_map[lower] = class_name
    return factory_map


def _build_method_return_map(class_names: set[str]) -> dict[str, str]:
    """Build map of method names to class names they likely return."""
    method_map = {}
    class_names_lower = {c.lower(): c for c in class_names}

    known_methods = {
        "execute": "Cursor",
        "executemany": "Cursor",
        "executescript": "Cursor",
        "cursor": "Cursor",
    }

    for method, ret_type in known_methods.items():
        if ret_type.lower() in class_names_lower:
            method_map[method] = class_names_lower[ret_type.lower()]

    return method_map


def _generate_wrapper_tool(
    callable_info: Any,
    module_name: str,
    class_names: set[str],
    return_type_map: dict[str, str],
    is_method: bool = False,
    class_name: str | None = None,
) -> list[str]:
    """Generate a single tool wrapper."""
    lines = []
    sig = callable_info.signature

    # Determine tool name
    if is_method and class_name:
        tool_name = f"{class_name.lower()}_{callable_info.name}"
    else:
        tool_name = callable_info.name

    # Build parameters
    params = []
    call_args = []

    # Add instance parameter for methods
    if is_method and class_name:
        params.append(f"{class_name.lower()}: str")

    # Add other parameters from signature
    if sig:
        for param in sig.parameters:
            type_str = param.type_str if param.type_str != "Any" else "Any"
            if param.has_default:
                params.append(f"{param.name}: {type_str} = {param.default_repr}")
            else:
                params.append(f"{param.name}: {type_str}")
            call_args.append(f"{param.name}={param.name}")

    params_str = ", ".join(params)
    call_args_str = ", ".join(call_args)

    # Determine return type
    returns_handle = False
    handle_type = None

    if sig and sig.return_is_handle:
        returns_handle = True
        handle_type = sig.return_handle_type
    elif callable_info.name.lower() in return_type_map:
        returns_handle = True
        handle_type = return_type_map[callable_info.name.lower()]

    return_type = "str" if returns_handle else "Any"

    # Generate decorator and function
    lines.append(f'@mcp.tool(name="{tool_name}")')
    lines.append(f"def {tool_name}({params_str}) -> {return_type}:")

    # Docstring
    doc = callable_info.docstring or f"Tool: {tool_name}"
    doc_first_line = doc.split("\n")[0] if doc else f"Tool: {tool_name}"
    lines.append(f'    """{doc_first_line}"""')

    # Function body
    if is_method and class_name:
        lines.append(f"    _instance = _get_object({class_name.lower()})")
        if returns_handle and handle_type:
            lines.append(f"    result = _instance.{callable_info.name}({call_args_str})")
            lines.append(f'    return _store_object(result, "{handle_type}")')
        else:
            lines.append(f"    return _instance.{callable_info.name}({call_args_str})")
    else:
        call_target = f"{module_name}.{callable_info.name}"
        if returns_handle and handle_type:
            lines.append(f"    result = {call_target}({call_args_str})")
            lines.append(f'    return _store_object(result, "{handle_type}")')
        else:
            lines.append(f"    return {call_target}({call_args_str})")

    return lines


def _generate_from_file(
    ctx: click.Context,
    source_path: Path,
    output_path: Path,
    manifest_path: Path | None,
    name: str,
    llm_provider: str | None,
    llm_model: str | None,
    no_llm: bool,
    no_cache: bool,
    include_private: bool,
    no_resources: bool,
    no_prompts: bool,
    context: str | None,
    enable_sessions: bool,
    session_ttl: int,
    max_sessions: int,
    settings: Settings,
) -> None:
    """Generate MCP server from a Python file."""
    # Load module
    with console.status("[bold blue]Loading module..."):
        module = load_module_from_path(source_path.resolve())
    console.print(f"[green]✓[/green] Loaded module: {module.__name__}")

    if manifest_path:
        # Manifest-based generation
        from auto_mcp.manifest import Manifest, ManifestGenerator

        with console.status("[bold blue]Loading manifest..."):
            manifest = Manifest.from_yaml(manifest_path)
        console.print(f"[green]✓[/green] Loaded manifest with {len(manifest.tools)} tool patterns")

        with console.status("[bold blue]Generating MCP server from manifest..."):
            generator = ManifestGenerator()
            generator.generate(module, manifest, output_path, module.__name__)

        console.print(f"[green]✓[/green] Generated server at: {output_path}")
        console.print(f"\n[dim]To run: python {output_path}[/dim]")
    else:
        # Full module generation (existing behavior)
        # Create LLM provider if enabled
        llm = None
        if not no_llm:
            with console.status("[bold blue]Initializing LLM provider..."):
                llm = get_llm_provider(llm_provider, llm_model, settings)
            if llm:
                console.print(f"[green]✓[/green] Using LLM: {llm.model_name}")
            else:
                console.print("[yellow]![/yellow] LLM disabled, using docstrings only")

        # Create cache
        cache = PromptCache() if not no_cache else PromptCache(cache_dir=None)

        # Create generator config
        config = GeneratorConfig(
            server_name=name,
            include_private=include_private,
            generate_resources=not no_resources,
            generate_prompts=not no_prompts,
            use_cache=not no_cache,
            use_llm=not no_llm and llm is not None,
            enable_sessions=enable_sessions,
            session_ttl=session_ttl,
            max_sessions=max_sessions,
        )

        # Create generator
        generator = MCPGenerator(llm=llm, cache=cache, config=config)

        if enable_sessions:
            console.print("[green]✓[/green] Session lifecycle enabled")

        # Generate standalone file
        with console.status("[bold blue]Generating standalone server..."):
            result = generator.generate_standalone(
                [module],
                output_path,
                context=context,
            )
        console.print(f"[green]✓[/green] Generated server at: {result}")
        console.print(f"\n[dim]To run: python {result}[/dim]")

        # Save cache if enabled
        if not no_cache:
            cache.save(module.__name__)


def _generate_from_package(
    ctx: click.Context,
    package_name: str,
    output_path: Path,
    manifest_path: Path | None,
    name: str | None,
    pkg_version: str | None,
    no_isolated: bool,
    llm_provider: str | None,
    llm_model: str | None,
    no_llm: bool,
    no_cache: bool,
    include_private: bool,
    no_resources: bool,
    no_prompts: bool,
    context: str | None,
    enable_sessions: bool,
    session_ttl: int,
    max_sessions: int,
    max_depth: int | None,
    public_api_only: bool,
    include_reexports: bool,
    use_wrapper: bool,
    settings: Settings,
) -> None:
    """Generate MCP server from an installed package."""
    from auto_mcp.isolation import IsolationManager, check_uvx_available
    from auto_mcp.isolation.manager import IsolationConfig, IsolationError, PackageNotFoundError

    # Create isolation manager
    isolation = IsolationManager(
        package_name=package_name,
        version=pkg_version,
        force_local=no_isolated,
    )

    # Determine if we need isolation
    use_isolation = isolation.should_use_isolation()

    # If version specified, always use isolation
    if pkg_version:
        use_isolation = True

    server_name = name or f"{isolation.package_name}-mcp-server"

    if manifest_path:
        # Manifest-based generation
        if use_isolation and not no_isolated:
            # Need to run in isolation
            if not check_uvx_available():
                raise click.ClickException(
                    f"Package '{package_name}' is not installed locally and uvx is not available.\n"
                    "Either install the package or install uv: https://docs.astral.sh/uv/"
                )

            console.print(f"[dim]Package not installed locally, using uvx isolation...[/dim]")

            # For manifest mode with isolation, we need a different approach
            # Run manifest generation in the isolated environment
            import subprocess

            from auto_mcp.isolation.manager import get_auto_mcp_source_dir

            source_dir = get_auto_mcp_source_dir()
            auto_mcp_source = str(source_dir) if source_dir else "auto-mcp-tool"

            # Build package spec
            pkg_spec = f"{isolation.package_name}=={pkg_version}" if pkg_version else isolation.package_name

            uvx_cmd = [
                "uvx",
                "--from", auto_mcp_source,
                "--with", pkg_spec,
                "auto-mcp-tool",
                "internal-worker", "manifest-generate",
                "--package", isolation.package_name,
                "--manifest", str(manifest_path),
                "--output", str(output_path),
                "--server-name", server_name,
            ]

            with console.status(f"[bold blue]Generating from '{pkg_spec}' via uvx with manifest..."):
                try:
                    result = subprocess.run(
                        uvx_cmd,
                        capture_output=True,
                        text=True,
                        timeout=300,
                    )
                except subprocess.TimeoutExpired:
                    raise click.ClickException("Generation timed out.") from None

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout or "Unknown error"
                raise click.ClickException(f"Failed to generate: {error_msg}")

            console.print(f"[green]✓[/green] Generated server at: {output_path}")
            console.print(f"\n[dim]To run: python {output_path}[/dim]")
        else:
            # Local manifest generation
            from auto_mcp.manifest import Manifest, ManifestGenerator

            try:
                module = importlib.import_module(package_name)
            except ImportError as e:
                raise click.ClickException(f"Cannot import package '{package_name}': {e}") from None

            with console.status("[bold blue]Loading manifest..."):
                manifest = Manifest.from_yaml(manifest_path)
            console.print(f"[green]✓[/green] Loaded manifest with {len(manifest.tools)} tool patterns")

            with console.status("[bold blue]Generating MCP server from manifest..."):
                generator = ManifestGenerator()
                generator.generate(module, manifest, output_path, package_name)

            console.print(f"[green]✓[/green] Generated server at: {output_path}")
            console.print(f"\n[dim]To run: python {output_path}[/dim]")
    else:
        # Full package generation (existing behavior)
        if use_isolation:
            # Check if uvx is available
            if not check_uvx_available():
                raise click.ClickException(
                    f"Package '{package_name}' is not installed locally and uvx is not available.\n"
                    "Either install the package or install uv: https://docs.astral.sh/uv/"
                )

            # Warn about LLM being disabled in isolation
            if not no_llm:
                console.print("[yellow]![/yellow] LLM disabled in isolation mode (using docstrings only)")

            console.print(f"[dim]Package not installed locally, using uvx isolation...[/dim]")

            iso_config = IsolationConfig(
                package_name=isolation.package_name,
                version=isolation.version,
                max_depth=max_depth,
                include_private=include_private,
                include_reexports=include_reexports,
                public_api_only=public_api_only,
                server_name=server_name,
                enable_sessions=enable_sessions,
                session_ttl=session_ttl,
                max_sessions=max_sessions,
            )

            if enable_sessions:
                console.print("[green]✓[/green] Session lifecycle enabled")

            with console.status(f"[bold blue]Generating from '{isolation.get_package_spec()}' via uvx..."):
                try:
                    result = isolation.run_generate(iso_config, output_path)
                except PackageNotFoundError as e:
                    raise click.ClickException(str(e)) from None
                except IsolationError as e:
                    raise click.ClickException(str(e)) from None

            console.print(f"[green]✓[/green] Generated server at: {result}")
            console.print(f"\n[dim]To run: python {result}[/dim]")
        else:
            # Local execution
            # First, check if this is a C extension module (auto-detect)
            try:
                module = importlib.import_module(package_name)
            except ImportError as e:
                raise click.ClickException(f"Cannot import package '{package_name}': {e}") from None

            # Auto-detect C extension modules and use wrapper generator
            from auto_mcp.wrapper.generator import WrapperGenerator
            wrapper_gen = WrapperGenerator()
            is_c_ext = wrapper_gen.is_c_extension_module(module)

            if use_wrapper or is_c_ext:
                if is_c_ext and not use_wrapper:
                    console.print("[dim]Auto-detected C extension module, using wrapper generator[/dim]")
                # Wrapper-based generation for C extensions
                _generate_with_wrapper(
                    package_name=package_name,
                    output_path=output_path,
                    server_name=server_name,
                    include_private=include_private,
                )
                return

            # Standard generation (original flow)
            # Create LLM provider if enabled
            llm = None
            if not no_llm:
                with console.status("[bold blue]Initializing LLM provider..."):
                    llm = get_llm_provider(llm_provider, llm_model, settings)
                if llm:
                    console.print(f"[green]✓[/green] Using LLM: {llm.model_name}")
                else:
                    console.print("[yellow]![/yellow] LLM disabled, using docstrings only")

            # Create cache
            cache = PromptCache() if not no_cache else PromptCache(cache_dir=None)

            # Create generator config
            config = GeneratorConfig(
                server_name=server_name,
                include_private=include_private,
                use_cache=not no_cache,
                use_llm=not no_llm and llm is not None,
                max_depth=max_depth,
                public_api_only=public_api_only,
                include_reexports=include_reexports,
                enable_sessions=enable_sessions,
                session_ttl=session_ttl,
                max_sessions=max_sessions,
            )

            # Create generator
            mcp_generator = MCPGenerator(llm=llm, cache=cache, config=config)

            if enable_sessions:
                console.print("[green]✓[/green] Session lifecycle enabled")

            # Generate
            with console.status(f"[bold blue]Analyzing and generating from '{package_name}'..."):
                try:
                    result = mcp_generator.generate_standalone_from_package(
                        package_name,
                        output_path,
                        context=context,
                    )
                except ImportError as e:
                    raise click.ClickException(f"Cannot import package '{package_name}': {e}") from None
                except ValueError as e:
                    raise click.ClickException(str(e)) from None

            console.print(f"[green]✓[/green] Generated server at: {result}")
            console.print(f"\n[dim]To run: python {result}[/dim]")

            # Save cache if enabled
            if not no_cache:
                cache.save(package_name)


@cli.command()
@click.argument("modules", nargs=-1, required=True, type=click.Path(exists=True))
@click.option(
    "--name",
    type=str,
    default="auto-mcp-server",
    help="Name for the server",
)
@click.option(
    "--llm-provider",
    type=click.Choice(["ollama", "openai", "anthropic"]),
    help="LLM provider for description generation",
)
@click.option(
    "--llm-model",
    type=str,
    help="Model name for description generation",
)
@click.option(
    "--no-llm",
    is_flag=True,
    help="Disable LLM description generation",
)
@click.option(
    "--no-cache",
    is_flag=True,
    help="Disable caching of generated descriptions",
)
@click.option(
    "--include-private",
    is_flag=True,
    help="Include private methods",
)
@click.option(
    "--transport",
    type=click.Choice(["stdio", "sse"]),
    default="stdio",
    help="MCP transport to use",
)
@click.option(
    "--watch",
    is_flag=True,
    help="Enable hot-reload on source file changes",
)
@click.option(
    "--enable-sessions",
    is_flag=True,
    help="Enable session lifecycle support (create_session/close_session tools)",
)
@click.option(
    "--session-ttl",
    type=int,
    default=3600,
    help="Session TTL in seconds (default: 3600)",
)
@click.option(
    "--max-sessions",
    type=int,
    default=100,
    help="Maximum number of concurrent sessions (default: 100)",
)
@click.pass_context
def serve(
    ctx: click.Context,
    modules: tuple[str, ...],
    name: str,
    llm_provider: str | None,
    llm_model: str | None,
    no_llm: bool,
    no_cache: bool,
    include_private: bool,
    transport: Literal["stdio", "sse"],
    watch: bool,
    enable_sessions: bool,
    session_ttl: int,
    max_sessions: int,
) -> None:
    """Run an MCP server from Python modules.

    MODULES: One or more Python files to expose as MCP tools.

    Examples:

        # Run server with stdio transport
        auto-mcp-tool serve mymodule.py

        # Run with custom name
        auto-mcp-tool serve mymodule.py --name "My Server"

        # Run with SSE transport
        auto-mcp-tool serve mymodule.py --transport sse

        # Run with hot-reload enabled
        auto-mcp-tool serve mymodule.py --watch

        # Run with session lifecycle support
        auto-mcp-tool serve mymodule.py --enable-sessions

        # Run with custom session settings
        auto-mcp-tool serve mymodule.py --enable-sessions --session-ttl 7200 --max-sessions 50
    """
    settings: Settings = ctx.obj["settings"]

    # Load modules
    console.print("[bold blue]Loading modules...[/bold blue]")
    loaded_modules = load_modules(modules)
    console.print(f"[green]✓[/green] Loaded {len(loaded_modules)} module(s)")

    # Create LLM provider if enabled
    llm = None
    if not no_llm:
        llm = get_llm_provider(llm_provider, llm_model, settings)
        if llm:
            console.print(f"[green]✓[/green] Using LLM: {llm.model_name}")

    # Create cache
    cache = PromptCache() if not no_cache else PromptCache(cache_dir=None)

    # Create generator config
    config = GeneratorConfig(
        server_name=name,
        include_private=include_private,
        use_cache=not no_cache,
        use_llm=not no_llm and llm is not None,
        enable_sessions=enable_sessions,
        session_ttl=session_ttl,
        max_sessions=max_sessions,
    )

    # Create generator and server
    generator = MCPGenerator(llm=llm, cache=cache, config=config)

    console.print("[bold blue]Creating MCP server...[/bold blue]")

    if enable_sessions:
        console.print("[green]✓[/green] Session lifecycle enabled")

    if watch:
        # Hot-reload mode
        from auto_mcp.api import AutoMCP

        auto = AutoMCP(
            llm_provider=llm_provider or "ollama" if not no_llm else None,  # type: ignore[arg-type]
            llm_model=llm_model,
            use_llm=not no_llm,
            use_cache=not no_cache,
            server_name=name,
            include_private=include_private,
            enable_sessions=enable_sessions,
            session_ttl=session_ttl,
            max_sessions=max_sessions,
        )
        hot_server = HotReloadServer(auto, loaded_modules)

        console.print(f"[green]✓[/green] Server '{name}' ready")
        console.print(f"[dim]Transport: {transport}[/dim]")
        console.print("[yellow]Hot-reload enabled - watching for file changes[/yellow]\n")

        hot_server.run(transport=transport)
    else:
        # Normal mode
        server = generator.create_server(loaded_modules)

        console.print(f"[green]✓[/green] Server '{name}' ready")
        console.print(f"[dim]Transport: {transport}[/dim]\n")

        # Run server
        server.run(transport=transport)


@cli.command()
@click.argument("modules", nargs=-1, required=True, type=click.Path(exists=True))
@click.option(
    "--include-private",
    is_flag=True,
    help="Include private methods",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed information about each method",
)
@click.pass_context
def check(
    ctx: click.Context,
    modules: tuple[str, ...],
    include_private: bool,
    verbose: bool,
) -> None:
    """Check modules and show what would be exposed as MCP tools.

    This is a dry-run mode that analyzes modules without generating anything.

    MODULES: One or more Python files to analyze.

    Examples:

        # Check what would be exposed
        auto-mcp-tool check mymodule.py

        # Include private methods in check
        auto-mcp-tool check mymodule.py --include-private

        # Show detailed information
        auto-mcp-tool check mymodule.py -v
    """
    # Load modules
    with console.status("[bold blue]Loading modules..."):
        loaded_modules = load_modules(modules)

    # Create analyzer
    analyzer = ModuleAnalyzer(include_private=include_private)

    total_tools = 0
    total_resources = 0
    total_prompts = 0

    for module in loaded_modules:
        console.print(f"\n[bold]Module: {module.__name__}[/bold]")

        methods = analyzer.analyze_module(module)

        # Categorize methods
        tools = []
        resources = []
        prompts = []

        for method in methods:
            if method.is_resource:
                resources.append(method)
            elif method.is_prompt:
                prompts.append(method)
            else:
                tools.append(method)

        # Display tools
        if tools:
            table = Table(title="Tools", show_header=True)
            table.add_column("Name", style="cyan")
            table.add_column("Async", style="yellow")
            table.add_column("Parameters")
            if verbose:
                table.add_column("Docstring")

            for tool in tools:
                params = ", ".join(p["name"] for p in tool.parameters)
                row = [
                    tool.mcp_metadata.get("tool_name") or tool.name,
                    "✓" if tool.is_async else "",
                    params or "(none)",
                ]
                if verbose:
                    doc = tool.docstring or ""
                    doc_display = doc[:50] + "..." if len(doc) > 50 else doc
                    row.append(doc_display)
                table.add_row(*row)

            console.print(table)
            total_tools += len(tools)

        # Display resources
        if resources:
            table = Table(title="Resources", show_header=True)
            table.add_column("Name", style="cyan")
            table.add_column("URI", style="green")
            if verbose:
                table.add_column("Docstring")

            for resource in resources:
                uri = resource.mcp_metadata.get("resource_uri", f"auto://{resource.name}")
                row = [
                    resource.mcp_metadata.get("resource_name") or resource.name,
                    uri,
                ]
                if verbose:
                    doc = resource.docstring or ""
                    doc_display = doc[:50] + "..." if len(doc) > 50 else doc
                    row.append(doc_display)
                table.add_row(*row)

            console.print(table)
            total_resources += len(resources)

        # Display prompts
        if prompts:
            table = Table(title="Prompts", show_header=True)
            table.add_column("Name", style="cyan")
            table.add_column("Parameters")
            if verbose:
                table.add_column("Docstring")

            for prompt in prompts:
                params = ", ".join(p["name"] for p in prompt.parameters)
                row = [
                    prompt.mcp_metadata.get("prompt_name") or prompt.name,
                    params or "(none)",
                ]
                if verbose:
                    doc = prompt.docstring or ""
                    doc_display = doc[:50] + "..." if len(doc) > 50 else doc
                    row.append(doc_display)
                table.add_row(*row)

            console.print(table)
            total_prompts += len(prompts)

        if not tools and not resources and not prompts:
            console.print("[yellow]No public methods found[/yellow]")

    # Summary
    console.print("\n" + "─" * 40)
    console.print(
        f"[bold]Summary:[/bold] {total_tools} tool(s), "
        f"{total_resources} resource(s), {total_prompts} prompt(s)"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Inspect command helper functions
# ─────────────────────────────────────────────────────────────────────────────

# Description truncation constants for consistent display
_DESC_MAX_WIDTH = 40  # Maximum display width for descriptions
_DESC_TRUNCATE_AT = 37  # Where to truncate (leaves room for "...")
_DESC_TREE_MAX_WIDTH = 60  # Wider limit for tree format


def _format_type_str(type_hint: Any) -> str:
    """Convert a type hint to a readable string."""
    if type_hint is None:
        return "Any"
    if hasattr(type_hint, "__name__"):
        return str(type_hint.__name__)
    return str(type_hint).replace("typing.", "")


def _match_filter(name: str, pattern: str) -> bool:
    """Match name against a glob pattern."""
    return fnmatch.fnmatch(name, pattern)


def _get_schema_for_type(type_hint: Any) -> dict[str, Any]:
    """Get JSON schema for a type hint."""
    if type_hint is None:
        return {"type": "any"}
    try:
        registry = get_default_registry()
        return registry.get_json_schema(type_hint)
    except Exception:
        # Fallback for unsupported types
        return {"type": _format_type_str(type_hint)}


def _build_input_schema_from_metadata(metadata: MethodMetadata) -> dict[str, Any]:
    """Build a fallback input schema from metadata when FunctionWrapper fails.

    Args:
        metadata: MethodMetadata object with parameter information

    Returns:
        JSON schema dictionary for the function's parameters
    """
    properties: dict[str, Any] = {}
    required: list[str] = []

    for param in metadata.parameters:
        param_name = param.get("name", "unknown")
        properties[param_name] = _get_schema_for_type(param.get("type"))
        if not param.get("has_default", False):
            required.append(param_name)

    return {"type": "object", "properties": properties, "required": required}


def _build_inspection_data(
    metadata: MethodMetadata,
    func: Any,
    show_schema: bool = False,
    show_source: bool = False,
) -> dict[str, Any]:
    """Build inspection dictionary from method metadata.

    Args:
        metadata: MethodMetadata object with function information
        func: The actual function/method object (may be None if not found)
        show_schema: Whether to generate JSON schemas for parameters/return
        show_source: Whether to include function source code

    Returns:
        Dictionary with keys: name, qualified_name, description, is_async,
        parameters, return_type, and optionally schemas and source code.
    """
    data: dict[str, Any] = {
        "name": metadata.mcp_metadata.get("tool_name") or metadata.name,
        "qualified_name": metadata.qualified_name,
        "description": metadata.docstring or "",
        "is_async": metadata.is_async,
        "is_tool": metadata.is_tool,
        "is_resource": metadata.is_resource,
        "is_prompt": metadata.is_prompt,
        "decorators": metadata.decorators,
        "parameters": [],
        "return_type": _format_type_str(metadata.return_type),
    }

    # Add MCP-specific metadata
    if metadata.mcp_metadata:
        data["mcp_metadata"] = {
            k: v for k, v in metadata.mcp_metadata.items() if not k.startswith("is_")
        }

    # Build parameter info
    for param in metadata.parameters:
        if "name" not in param:
            continue  # Skip malformed parameters
        param_data: dict[str, Any] = {
            "name": param["name"],
            "type": param.get("type_str", "Any"),
            "required": not param.get("has_default", False),
            "default": param.get("default"),
        }
        if show_schema:
            param_data["schema"] = _get_schema_for_type(param.get("type"))
        data["parameters"].append(param_data)

    # Add schemas if requested
    if show_schema:
        if func is not None:
            try:
                wrapper = FunctionWrapper(func)
                data["input_schema"] = wrapper.get_json_schema()
                data["return_schema"] = wrapper.get_return_schema()
            except Exception:
                # Fall back to metadata-based schema generation
                data["input_schema"] = _build_input_schema_from_metadata(metadata)
                data["return_schema"] = _get_schema_for_type(metadata.return_type)
        else:
            # func not available, use metadata-based schema
            data["input_schema"] = _build_input_schema_from_metadata(metadata)
            data["return_schema"] = _get_schema_for_type(metadata.return_type)

    # Add source if requested
    if show_source:
        data["source"] = metadata.source_code

    return data


def _display_table_format(
    module_name: str,
    tools: list[dict[str, Any]],
    resources: list[dict[str, Any]],
    prompts: list[dict[str, Any]],
    show_schema: bool,
    show_source: bool = False,
) -> None:
    """Display inspection results in table format.

    Args:
        module_name: Name of the module being displayed
        tools: List of tool inspection data dictionaries
        resources: List of resource inspection data dictionaries
        prompts: List of prompt inspection data dictionaries
        show_schema: Whether to show detailed schemas (triggers verbose display)
        show_source: Whether to show source code in detailed view
    """
    console.print(f"\n[bold cyan]Module: {module_name}[/bold cyan]")
    console.print("─" * 50)

    # Display tools
    if tools:
        console.print(f"\n[bold]Tools[/bold] ({len(tools)})")
        if not show_schema:
            # Compact table
            table = Table(show_header=True, header_style="bold")
            table.add_column("Name", style="cyan")
            table.add_column("Description", max_width=40)
            table.add_column("Async", justify="center")
            table.add_column("Parameters")

            for tool in tools:
                params = ", ".join(p["name"] for p in tool["parameters"])
                desc = tool["description"]
                desc_display = (
                    desc[:_DESC_TRUNCATE_AT] + "..." if len(desc) > _DESC_MAX_WIDTH else desc
                )
                table.add_row(
                    tool["name"],
                    desc_display,
                    "[yellow]*[/yellow]" if tool["is_async"] else "",
                    params or "(none)",
                )
            console.print(table)
        else:
            # Detailed view with schemas
            for tool in tools:
                _display_tool_detail(tool, show_source)

    # Display resources
    if resources:
        console.print(f"\n[bold]Resources[/bold] ({len(resources)})")
        table = Table(show_header=True, header_style="bold")
        table.add_column("Name", style="cyan")
        table.add_column("URI", style="green")
        table.add_column("Description", max_width=40)

        for res in resources:
            uri = res.get("mcp_metadata", {}).get("resource_uri", f"auto://{res['name']}")
            desc = res["description"]
            desc_display = desc[:_DESC_TRUNCATE_AT] + "..." if len(desc) > _DESC_MAX_WIDTH else desc
            table.add_row(res["name"], uri, desc_display)
        console.print(table)

    # Display prompts
    if prompts:
        console.print(f"\n[bold]Prompts[/bold] ({len(prompts)})")
        table = Table(show_header=True, header_style="bold")
        table.add_column("Name", style="cyan")
        table.add_column("Parameters")
        table.add_column("Description", max_width=40)

        for prompt in prompts:
            params = ", ".join(p["name"] for p in prompt["parameters"])
            desc = prompt["description"]
            desc_display = desc[:_DESC_TRUNCATE_AT] + "..." if len(desc) > _DESC_MAX_WIDTH else desc
            table.add_row(prompt["name"], params or "(none)", desc_display)
        console.print(table)

    if not tools and not resources and not prompts:
        console.print("[yellow]No components found[/yellow]")


def _display_tool_detail(tool: dict[str, Any], show_source: bool) -> None:
    """Display detailed information for a single tool."""
    console.print()
    console.print(
        Panel(
            f"[bold]{tool['name']}[/bold]",
            subtitle=f"{'async ' if tool['is_async'] else ''}function",
            style="cyan",
        )
    )

    if tool["description"]:
        console.print(f"[dim]{tool['description']}[/dim]")

    # Parameters table
    if tool["parameters"]:
        console.print("\n[bold]Parameters:[/bold]")
        param_table = Table(show_header=True, header_style="bold", box=None)
        param_table.add_column("Name")
        param_table.add_column("Type")
        param_table.add_column("Required")
        param_table.add_column("Default")
        if "schema" in tool["parameters"][0]:
            param_table.add_column("Schema")

        for param in tool["parameters"]:
            row = [
                f"[cyan]{param['name']}[/cyan]",
                param["type"],
                "[green]yes[/green]" if param["required"] else "[dim]no[/dim]",
                str(param["default"]) if param["default"] is not None else "[dim]-[/dim]",
            ]
            if "schema" in param:
                schema_str = json.dumps(param["schema"], separators=(",", ":"))
                if len(schema_str) > 30:
                    schema_str = schema_str[:27] + "..."
                row.append(f"[dim]{schema_str}[/dim]")
            param_table.add_row(*row)
        console.print(param_table)
    else:
        console.print("\n[dim]No parameters[/dim]")

    # Return type
    console.print(f"\n[bold]Returns:[/bold] {tool['return_type']}")
    if "return_schema" in tool and tool["return_schema"]:
        schema_str = json.dumps(tool["return_schema"], indent=2)
        console.print(Syntax(schema_str, "json", theme="monokai", line_numbers=False))

    # Source code
    if show_source and "source" in tool and tool["source"]:
        console.print("\n[bold]Source:[/bold]")
        console.print(Syntax(tool["source"], "python", theme="monokai", line_numbers=True))


def _display_json_format(
    module_name: str,
    tools: list[dict[str, Any]],
    resources: list[dict[str, Any]],
    prompts: list[dict[str, Any]],
) -> None:
    """Display inspection results in JSON format."""
    output = {
        "module": module_name,
        "tools": tools,
        "resources": resources,
        "prompts": prompts,
    }
    console.print(Syntax(json.dumps(output, indent=2, default=str), "json", theme="monokai"))


def _display_tree_format(
    module_name: str,
    tools: list[dict[str, Any]],
    resources: list[dict[str, Any]],
    prompts: list[dict[str, Any]],
) -> None:
    """Display inspection results in tree format."""
    tree = Tree(f"[bold cyan]{module_name}[/bold cyan]")

    # Tools branch
    if tools:
        tools_branch = tree.add(f"[bold]Tools[/bold] ({len(tools)})")
        for tool in tools:
            params = ", ".join(f"{p['name']}: {p['type']}" for p in tool["parameters"])
            sig = f"[cyan]{tool['name']}[/cyan]({params}) -> {tool['return_type']}"
            if tool["is_async"]:
                sig = f"[yellow]async[/yellow] {sig}"
            tool_branch = tools_branch.add(sig)
            if tool["description"]:
                desc = tool["description"]
                desc_display = (
                    desc[: _DESC_TREE_MAX_WIDTH - 3] + "..."
                    if len(desc) > _DESC_TREE_MAX_WIDTH
                    else desc
                )
                tool_branch.add(f"[dim]{desc_display}[/dim]")

    # Resources branch
    if resources:
        res_branch = tree.add(f"[bold]Resources[/bold] ({len(resources)})")
        for res in resources:
            uri = res.get("mcp_metadata", {}).get("resource_uri", f"auto://{res['name']}")
            res_item = res_branch.add(f"[green]{uri}[/green]")
            res_item.add(f"[cyan]{res['name']}[/cyan]")
            if res["description"]:
                desc = res["description"]
                desc_display = (
                    desc[: _DESC_TREE_MAX_WIDTH - 10] + "..."
                    if len(desc) > _DESC_TREE_MAX_WIDTH - 10
                    else desc
                )
                res_item.add(f"[dim]{desc_display}[/dim]")

    # Prompts branch
    if prompts:
        prompts_branch = tree.add(f"[bold]Prompts[/bold] ({len(prompts)})")
        for prompt in prompts:
            params = ", ".join(p["name"] for p in prompt["parameters"])
            prompt_item = prompts_branch.add(f"[magenta]{prompt['name']}[/magenta]({params})")
            if prompt["description"]:
                desc = prompt["description"]
                desc_display = (
                    desc[: _DESC_TREE_MAX_WIDTH - 10] + "..."
                    if len(desc) > _DESC_TREE_MAX_WIDTH - 10
                    else desc
                )
                prompt_item.add(f"[dim]{desc_display}[/dim]")

    if not tools and not resources and not prompts:
        tree.add("[yellow]No components found[/yellow]")

    console.print(tree)


@cli.command()
@click.argument("modules", nargs=-1, required=True, type=click.Path(exists=True))
@click.option(
    "-f",
    "--format",
    "output_format",
    type=click.Choice(["table", "json", "tree"]),
    default="table",
    help="Output format",
)
@click.option(
    "--filter",
    "name_filter",
    type=str,
    help="Filter by name (glob pattern, e.g. 'get_*')",
)
@click.option(
    "-t",
    "--type",
    "component_type",
    type=click.Choice(["tools", "resources", "prompts", "all"]),
    default="all",
    help="Component type to show",
)
@click.option(
    "-s",
    "--show-schema",
    is_flag=True,
    help="Show JSON schemas for parameters and return types",
)
@click.option(
    "--show-source",
    is_flag=True,
    help="Show function source code",
)
@click.option(
    "--include-private",
    is_flag=True,
    help="Include private methods (starting with _)",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Verbose output (implies --show-schema)",
)
@click.pass_context
def inspect(
    ctx: click.Context,
    modules: tuple[str, ...],
    output_format: str,
    name_filter: str | None,
    component_type: str,
    show_schema: bool,
    show_source: bool,
    include_private: bool,
    verbose: bool,
) -> None:
    """Inspect modules and display detailed MCP component information.

    This command provides deep visibility into MCP servers - view tools,
    schemas, parameter types, and metadata without running the server.

    MODULES: One or more Python files to inspect.

    Examples:

        # Basic inspection
        auto-mcp-tool inspect mymodule.py

        # Verbose with schemas
        auto-mcp-tool inspect mymodule.py -v

        # JSON output
        auto-mcp-tool inspect mymodule.py -f json

        # Tree view
        auto-mcp-tool inspect mymodule.py -f tree

        # Filter by name
        auto-mcp-tool inspect mymodule.py --filter "get_*"

        # Show only tools
        auto-mcp-tool inspect mymodule.py -t tools
    """
    # Verbose implies show_schema
    if verbose:
        show_schema = True

    # Load modules
    with console.status("[bold blue]Loading modules..."):
        loaded_modules = load_modules(modules)

    # Create analyzer
    analyzer = ModuleAnalyzer(include_private=include_private)

    # Accumulate totals across all modules
    total_tools = 0
    total_resources = 0
    total_prompts = 0

    for module in loaded_modules:
        methods = analyzer.analyze_module(module)

        # Get function references for schema generation (only actual functions/methods)
        func_map: dict[str, Any] = {}
        for name in dir(module):
            obj = getattr(module, name, None)
            if inspect_module.isfunction(obj) or inspect_module.ismethod(obj):
                func_map[name] = obj

        # Categorize and build inspection data
        tools: list[dict[str, Any]] = []
        resources: list[dict[str, Any]] = []
        prompts: list[dict[str, Any]] = []

        for method in methods:
            # Get the actual function
            func = func_map.get(method.name)

            # Build inspection data
            data = _build_inspection_data(
                method,
                func,
                show_schema=show_schema,
                show_source=show_source,
            )

            # Apply name filter
            if name_filter and not _match_filter(data["name"], name_filter):
                continue

            # Categorize
            if method.is_resource:
                resources.append(data)
            elif method.is_prompt:
                prompts.append(data)
            else:
                tools.append(data)

        # Apply component type filter
        if component_type == "tools":
            resources, prompts = [], []
        elif component_type == "resources":
            tools, prompts = [], []
        elif component_type == "prompts":
            tools, resources = [], []

        # Accumulate totals
        total_tools += len(tools)
        total_resources += len(resources)
        total_prompts += len(prompts)

        # Display based on format
        if output_format == "json":
            _display_json_format(module.__name__, tools, resources, prompts)
        elif output_format == "tree":
            _display_tree_format(module.__name__, tools, resources, prompts)
        else:
            _display_table_format(
                module.__name__,
                tools,
                resources,
                prompts,
                show_schema,
                show_source,
            )

    # Summary for table format
    if output_format == "table":
        console.print("\n" + "─" * 50)
        console.print(
            f"[bold]Total:[/bold] {total_tools} tool(s), "
            f"{total_resources} resource(s), {total_prompts} prompt(s)"
        )


@cli.group()
def cache() -> None:
    """Manage the description cache."""
    pass


@cache.command(name="clear")
@click.argument("modules", nargs=-1, type=click.Path(exists=True))
@click.option(
    "--all",
    "clear_all",
    is_flag=True,
    help="Clear all cached entries",
)
@click.pass_context
def cache_clear(
    ctx: click.Context,
    modules: tuple[str, ...],
    clear_all: bool,
) -> None:
    """Clear cached descriptions.

    MODULES: Optional module files to clear cache for.

    Examples:

        # Clear cache for specific modules
        auto-mcp-tool cache clear mymodule.py

        # Clear all cache
        auto-mcp-tool cache clear --all
    """
    cache_instance = PromptCache()

    if clear_all:
        count = cache_instance.clear()
        console.print(f"[green]✓[/green] Cleared {count} cached entries")
    elif modules:
        total = 0
        for module_path in modules:
            path = Path(module_path)
            module_name = path.stem
            count = cache_instance.invalidate(module_name)
            total += count
            console.print(f"[green]✓[/green] Cleared {count} entries for {module_name}")
        console.print(f"\n[bold]Total:[/bold] {total} entries cleared")
    else:
        raise click.ClickException("Specify modules to clear or use --all")


@cache.command(name="stats")
@click.pass_context
def cache_stats(ctx: click.Context) -> None:
    """Show cache statistics.

    Examples:

        auto-mcp-tool cache stats
    """
    cache_instance = PromptCache()
    stats = cache_instance.get_stats()

    panel = Panel(
        f"""[cyan]Hits:[/cyan] {stats.hits}
[cyan]Misses:[/cyan] {stats.misses}
[cyan]Hit Rate:[/cyan] {stats.hit_rate:.1%}
[cyan]Total Entries:[/cyan] {stats.total_entries}
[cyan]Invalidations:[/cyan] {stats.invalidations}""",
        title="Cache Statistics",
    )
    console.print(panel)


@cli.group()
def config() -> None:
    """View and manage configuration."""
    pass


@config.command(name="show")
@click.pass_context
def config_show(ctx: click.Context) -> None:
    """Show current configuration.

    Examples:

        auto-mcp-tool config show
    """
    settings: Settings = ctx.obj["settings"]

    table = Table(title="Current Configuration", show_header=True)
    table.add_column("Setting", style="cyan")
    table.add_column("Value")

    table.add_row("LLM Provider", settings.llm_provider)
    table.add_row("LLM Model", settings.llm_model)
    table.add_row("LLM Base URL", settings.llm_base_url or "(default)")
    table.add_row("OpenAI API Key", "***" if settings.openai_api_key else "(not set)")
    table.add_row("Anthropic API Key", "***" if settings.anthropic_api_key else "(not set)")
    table.add_row("Cache Enabled", str(settings.cache_enabled))
    table.add_row("Cache Directory", settings.cache_dir or "(default)")
    table.add_row("Server Name", settings.server_name)
    table.add_row("Transport", settings.transport)
    table.add_row("Include Private", str(settings.include_private))
    table.add_row("Generate Resources", str(settings.generate_resources))
    table.add_row("Generate Prompts", str(settings.generate_prompts))
    table.add_row("Enable Sessions", str(settings.enable_sessions))
    table.add_row("Session TTL", f"{settings.session_ttl}s")
    table.add_row("Max Sessions", str(settings.max_sessions))

    console.print(table)

    console.print(
        "\n[dim]Configuration is loaded from environment variables with AUTO_MCP_ prefix.[/dim]"
    )
    console.print("[dim]Example: AUTO_MCP_LLM_PROVIDER=openai[/dim]")


@config.command(name="env")
@click.pass_context
def config_env(ctx: click.Context) -> None:
    """Show environment variable names for configuration.

    Examples:

        auto-mcp-tool config env
    """
    env_vars = [
        ("AUTO_MCP_LLM_PROVIDER", "LLM provider (ollama, openai, anthropic)"),
        ("AUTO_MCP_LLM_MODEL", "Model name"),
        ("AUTO_MCP_LLM_BASE_URL", "Custom LLM endpoint URL"),
        ("AUTO_MCP_OPENAI_API_KEY", "OpenAI API key"),
        ("AUTO_MCP_ANTHROPIC_API_KEY", "Anthropic API key"),
        ("AUTO_MCP_CACHE_ENABLED", "Enable caching (true/false)"),
        ("AUTO_MCP_CACHE_DIR", "Cache directory path"),
        ("AUTO_MCP_SERVER_NAME", "Default server name"),
        ("AUTO_MCP_TRANSPORT", "MCP transport (stdio, sse)"),
        ("AUTO_MCP_INCLUDE_PRIVATE", "Include private methods (true/false)"),
        ("AUTO_MCP_GENERATE_RESOURCES", "Generate resources (true/false)"),
        ("AUTO_MCP_GENERATE_PROMPTS", "Generate prompts (true/false)"),
        ("AUTO_MCP_ENABLE_SESSIONS", "Enable session lifecycle (true/false)"),
        ("AUTO_MCP_SESSION_TTL", "Session TTL in seconds (default: 3600)"),
        ("AUTO_MCP_MAX_SESSIONS", "Maximum concurrent sessions (default: 100)"),
    ]

    table = Table(title="Environment Variables", show_header=True)
    table.add_column("Variable", style="cyan")
    table.add_column("Description")

    for var, desc in env_vars:
        table.add_row(var, desc)

    console.print(table)


# Package commands for analyzing installed packages
@cli.group()
def package() -> None:
    """Analyze and generate servers from installed Python packages.

    These commands work with installed packages (e.g., requests, json)
    rather than local Python files.
    """
    pass


@package.command(name="check")
@click.argument("package_name", required=True)
@click.option(
    "--max-depth",
    type=int,
    default=None,
    help="Maximum recursion depth for submodule discovery",
)
@click.option(
    "--include-private",
    is_flag=True,
    help="Include private modules and methods",
)
@click.option(
    "--public-api-only",
    is_flag=True,
    help="Only show functions in __all__ (public API)",
)
@click.option(
    "--include",
    "include_patterns",
    multiple=True,
    help="Glob patterns for modules to include (e.g., 'requests.api.*')",
)
@click.option(
    "--exclude",
    "exclude_patterns",
    multiple=True,
    help="Glob patterns for modules to exclude (e.g., 'requests.compat.*')",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed information about each method",
)
@click.option(
    "--include-reexports",
    is_flag=True,
    help="Include functions re-exported in __all__ from submodules (e.g., pandas, numpy)",
)
@click.option(
    "--no-isolated",
    is_flag=True,
    help="Force local execution only (fail if package not installed)",
)
@click.option(
    "--version",
    "pkg_version",
    type=str,
    default=None,
    help="Package version to use with uvx (e.g., '2.28.0')",
)
@click.pass_context
def package_check(
    ctx: click.Context,
    package_name: str,
    max_depth: int | None,
    include_private: bool,
    public_api_only: bool,
    include_patterns: tuple[str, ...],
    exclude_patterns: tuple[str, ...],
    verbose: bool,
    include_reexports: bool,
    no_isolated: bool,
    pkg_version: str | None,
) -> None:
    """Analyze an installed package and show what would be exposed.

    PACKAGE_NAME: Name of the installed package (e.g., 'requests', 'json')

    If the package is not installed locally, it will automatically be analyzed
    in an isolated uvx environment. Use --no-isolated to disable this behavior.

    Examples:

        # Check requests package
        auto-mcp-tool package check requests

        # Check with depth limit
        auto-mcp-tool package check boto3 --max-depth 2

        # Check only public API
        auto-mcp-tool package check requests --public-api-only

        # Check with module filtering
        auto-mcp-tool package check requests --include 'requests.api.*'

        # Verbose output
        auto-mcp-tool package check requests -v

        # Check a specific version (uses uvx)
        auto-mcp-tool package check requests --version 2.28.0
        auto-mcp-tool package check requests==2.28.0
    """
    from auto_mcp.isolation import IsolationManager, check_uvx_available
    from auto_mcp.isolation.manager import IsolationConfig, IsolationError, PackageNotFoundError

    # Create isolation manager
    isolation = IsolationManager(
        package_name=package_name,
        version=pkg_version,
        force_local=no_isolated,
    )

    # Determine execution mode
    use_isolation = isolation.should_use_isolation()

    # If version specified, always use isolation
    if pkg_version:
        use_isolation = True

    if use_isolation:
        # Check if uvx is available
        if not check_uvx_available():
            raise click.ClickException(
                f"Package '{package_name}' is not installed locally and uvx is not available.\n"
                "Either install the package or install uv: https://docs.astral.sh/uv/"
            )

        # Run in isolation
        console.print(f"[dim]Package not installed locally, using uvx isolation...[/dim]")

        config = IsolationConfig(
            package_name=isolation.package_name,
            version=isolation.version,
            max_depth=max_depth,
            include_private=include_private,
            include_reexports=include_reexports,
            include_patterns=list(include_patterns) if include_patterns else None,
            exclude_patterns=list(exclude_patterns) if exclude_patterns else None,
            public_api_only=public_api_only,
        )

        with console.status(f"[bold blue]Analyzing package '{isolation.get_package_spec()}' via uvx..."):
            try:
                metadata = isolation.run_check(config)
            except PackageNotFoundError as e:
                raise click.ClickException(str(e)) from None
            except IsolationError as e:
                raise click.ClickException(str(e)) from None

        # For isolated execution, methods are already in metadata
        methods = metadata.methods
    else:
        # Local execution (original flow)
        with console.status(f"[bold blue]Analyzing package '{package_name}'..."):
            try:
                analyzer = PackageAnalyzer(
                    include_private=include_private,
                    max_depth=max_depth,
                    include_reexports=include_reexports,
                )
                metadata = analyzer.analyze_package(
                    package_name,
                    include_patterns=list(include_patterns) if include_patterns else None,
                    exclude_patterns=list(exclude_patterns) if exclude_patterns else None,
                )
            except ImportError as e:
                raise click.ClickException(f"Cannot import package '{package_name}': {e}") from None
            except ValueError as e:
                raise click.ClickException(str(e)) from None

        # Get methods to display (local execution can filter)
        methods = analyzer.get_public_methods(metadata) if public_api_only else metadata.methods

    # Display package overview
    console.print(f"\n[bold]Package: {metadata.name}[/bold]")
    console.print(f"[dim]Modules discovered: {metadata.module_count}[/dim]")
    console.print(f"[dim]Public modules: {metadata.public_module_count}[/dim]")

    # Show module tree
    if verbose:
        console.print("\n[bold]Module Structure:[/bold]")
        tree = Tree(f"[cyan]{metadata.name}[/cyan]")
        _build_module_tree(tree, metadata.name, metadata.module_graph, set())
        console.print(tree)

    # Categorize methods (methods variable already set above)
    tools = []
    resources = []
    prompts = []

    for method in methods:
        if method.is_resource:
            resources.append(method)
        elif method.is_prompt:
            prompts.append(method)
        else:
            tools.append(method)

    # Display tools
    if tools:
        table = Table(title=f"Tools ({len(tools)})", show_header=True)
        table.add_column("Name", style="cyan")
        table.add_column("Module", style="dim")
        table.add_column("Async", style="yellow")
        table.add_column("Parameters")
        if verbose:
            table.add_column("Docstring")

        for tool in tools[:50]:  # Limit display to 50
            params = ", ".join(p["name"] for p in tool.parameters)
            row = [
                tool.name,
                tool.module_name.replace(f"{metadata.name}.", ""),
                "✓" if tool.is_async else "",
                params[:30] + "..." if len(params) > 30 else params or "(none)",
            ]
            if verbose:
                doc = tool.docstring or ""
                doc_display = doc[:40] + "..." if len(doc) > 40 else doc
                row.append(doc_display)
            table.add_row(*row)

        if len(tools) > 50:
            table.add_row("[dim]...[/dim]", f"[dim]+{len(tools) - 50} more[/dim]", "", "")

        console.print(table)

    # Display resources
    if resources:
        table = Table(title=f"Resources ({len(resources)})", show_header=True)
        table.add_column("Name", style="cyan")
        table.add_column("Module", style="dim")
        table.add_column("URI", style="green")

        for resource in resources[:20]:
            uri = resource.mcp_metadata.get("resource_uri", f"auto://{resource.name}")
            table.add_row(
                resource.name,
                resource.module_name.replace(f"{metadata.name}.", ""),
                uri,
            )

        console.print(table)

    # Display prompts
    if prompts:
        table = Table(title=f"Prompts ({len(prompts)})", show_header=True)
        table.add_column("Name", style="cyan")
        table.add_column("Module", style="dim")
        table.add_column("Parameters")

        for prompt in prompts[:20]:
            params = ", ".join(p["name"] for p in prompt.parameters)
            table.add_row(
                prompt.name,
                prompt.module_name.replace(f"{metadata.name}.", ""),
                params or "(none)",
            )

        console.print(table)

    if not tools and not resources and not prompts:
        console.print("[yellow]No public methods found[/yellow]")

    # Summary
    console.print("\n" + "─" * 50)
    console.print(
        f"[bold]Summary:[/bold] {len(tools)} tool(s), "
        f"{len(resources)} resource(s), {len(prompts)} prompt(s)"
    )

    if metadata.public_api:
        console.print(f"[dim]Public API symbols (__all__): {len(metadata.public_api)}[/dim]")


def _build_module_tree(
    tree: Tree,
    module_name: str,
    graph: dict[str, list[str]],
    visited: set[str],
) -> None:
    """Build a rich Tree from the module graph."""
    if module_name in visited:
        return
    visited.add(module_name)

    submodules = graph.get(module_name, [])
    for submodule in sorted(submodules):
        sub_name = submodule.split(".")[-1]
        is_private = sub_name.startswith("_")
        style = "dim" if is_private else "cyan"
        branch = tree.add(f"[{style}]{sub_name}[/{style}]")
        _build_module_tree(branch, submodule, graph, visited)


@package.command(name="generate")
@click.argument("package_name", required=True)
@click.option(
    "-o",
    "--output",
    type=click.Path(),
    required=True,
    help="Output path for generated file",
)
@click.option(
    "--name",
    type=str,
    default=None,
    help="Name for the generated server (defaults to package name)",
)
@click.option(
    "--max-depth",
    type=int,
    default=None,
    help="Maximum recursion depth for submodule discovery",
)
@click.option(
    "--include-private",
    is_flag=True,
    help="Include private modules and methods",
)
@click.option(
    "--public-api-only",
    is_flag=True,
    help="Only expose functions in __all__ (public API)",
)
@click.option(
    "--include",
    "include_patterns",
    multiple=True,
    help="Glob patterns for modules to include",
)
@click.option(
    "--exclude",
    "exclude_patterns",
    multiple=True,
    help="Glob patterns for modules to exclude",
)
@click.option(
    "--llm-provider",
    type=click.Choice(["ollama", "openai", "anthropic"]),
    help="LLM provider for description generation",
)
@click.option(
    "--llm-model",
    type=str,
    help="Model name for description generation",
)
@click.option(
    "--no-llm",
    is_flag=True,
    help="Disable LLM description generation (use docstrings only)",
)
@click.option(
    "--no-cache",
    is_flag=True,
    help="Disable caching of generated descriptions",
)
@click.option(
    "--context",
    type=str,
    help="Additional context for LLM description generation",
)
@click.option(
    "--include-reexports",
    is_flag=True,
    help="Include functions re-exported in __all__ from submodules (e.g., pandas, numpy)",
)
@click.option(
    "--enable-sessions",
    is_flag=True,
    help="Enable session lifecycle support (create_session/close_session tools)",
)
@click.option(
    "--session-ttl",
    type=int,
    default=3600,
    help="Session TTL in seconds (default: 3600)",
)
@click.option(
    "--max-sessions",
    type=int,
    default=100,
    help="Maximum number of concurrent sessions (default: 100)",
)
@click.option(
    "--no-isolated",
    is_flag=True,
    help="Force local execution only (fail if package not installed)",
)
@click.option(
    "--version",
    "pkg_version",
    type=str,
    default=None,
    help="Package version to use with uvx (e.g., '2.28.0')",
)
@click.pass_context
def package_generate(
    ctx: click.Context,
    package_name: str,
    output: str,
    name: str | None,
    max_depth: int | None,
    include_private: bool,
    public_api_only: bool,
    include_patterns: tuple[str, ...],
    exclude_patterns: tuple[str, ...],
    llm_provider: str | None,
    llm_model: str | None,
    no_llm: bool,
    no_cache: bool,
    context: str | None,
    include_reexports: bool,
    enable_sessions: bool,
    session_ttl: int,
    max_sessions: int,
    no_isolated: bool,
    pkg_version: str | None,
) -> None:
    """[DEPRECATED] Generate an MCP server from an installed package.

    NOTE: This command is deprecated. Use 'auto-mcp-tool generate' instead,
    which now accepts both Python files and package names.

    PACKAGE_NAME: Name of the installed package (e.g., 'requests', 'json')

    If the package is not installed locally, it will automatically be generated
    in an isolated uvx environment. Note: LLM description generation is disabled
    in isolation mode.

    Examples:

        # New unified command (recommended):
        auto-mcp-tool generate requests -o requests_server.py

        # Old command (deprecated):
        auto-mcp-tool package generate requests -o requests_server.py
    """
    # Deprecation warning
    console.print(
        "[yellow]Warning:[/yellow] 'package generate' is deprecated. "
        "Use 'auto-mcp-tool generate <package> -o <output>' instead."
    )

    from auto_mcp.isolation import IsolationManager, check_uvx_available
    from auto_mcp.isolation.manager import IsolationConfig, IsolationError, PackageNotFoundError

    settings: Settings = ctx.obj["settings"]

    # Create isolation manager
    isolation = IsolationManager(
        package_name=package_name,
        version=pkg_version,
        force_local=no_isolated,
    )

    # Determine execution mode
    use_isolation = isolation.should_use_isolation()

    # If version specified, always use isolation
    if pkg_version:
        use_isolation = True

    server_name = name or f"{isolation.package_name}-mcp-server"
    output_path = Path(output)

    if use_isolation:
        # Check if uvx is available
        if not check_uvx_available():
            raise click.ClickException(
                f"Package '{package_name}' is not installed locally and uvx is not available.\n"
                "Either install the package or install uv: https://docs.astral.sh/uv/"
            )

        # Warn about LLM being disabled in isolation
        if not no_llm:
            console.print("[yellow]![/yellow] LLM disabled in isolation mode (using docstrings only)")

        console.print(f"[dim]Package not installed locally, using uvx isolation...[/dim]")

        iso_config = IsolationConfig(
            package_name=isolation.package_name,
            version=isolation.version,
            max_depth=max_depth,
            include_private=include_private,
            include_reexports=include_reexports,
            include_patterns=list(include_patterns) if include_patterns else None,
            exclude_patterns=list(exclude_patterns) if exclude_patterns else None,
            public_api_only=public_api_only,
            server_name=server_name,
            enable_sessions=enable_sessions,
            session_ttl=session_ttl,
            max_sessions=max_sessions,
        )

        if enable_sessions:
            console.print("[green]✓[/green] Session lifecycle enabled")

        with console.status(f"[bold blue]Generating from '{isolation.get_package_spec()}' via uvx..."):
            try:
                result = isolation.run_generate(iso_config, output_path)
            except PackageNotFoundError as e:
                raise click.ClickException(str(e)) from None
            except IsolationError as e:
                raise click.ClickException(str(e)) from None

        console.print(f"[green]✓[/green] Generated server at: {result}")
        console.print(f"\n[dim]To run: python {result}[/dim]")
    else:
        # Local execution (original flow)
        # Create LLM provider if enabled
        llm = None
        if not no_llm:
            with console.status("[bold blue]Initializing LLM provider..."):
                llm = get_llm_provider(llm_provider, llm_model, settings)
            if llm:
                console.print(f"[green]✓[/green] Using LLM: {llm.model_name}")
            else:
                console.print("[yellow]![/yellow] LLM disabled, using docstrings only")

        # Create cache
        cache = PromptCache() if not no_cache else PromptCache(cache_dir=None)

        # Create generator config
        config = GeneratorConfig(
            server_name=server_name,
            include_private=include_private,
            use_cache=not no_cache,
            use_llm=not no_llm and llm is not None,
            max_depth=max_depth,
            public_api_only=public_api_only,
            include_patterns=list(include_patterns) if include_patterns else None,
            exclude_patterns=list(exclude_patterns) if exclude_patterns else None,
            include_reexports=include_reexports,
            enable_sessions=enable_sessions,
            session_ttl=session_ttl,
            max_sessions=max_sessions,
        )

        # Create generator
        generator = MCPGenerator(llm=llm, cache=cache, config=config)

        if enable_sessions:
            console.print("[green]✓[/green] Session lifecycle enabled")

        # Generate
        with console.status(f"[bold blue]Analyzing and generating from '{package_name}'..."):
            try:
                result = generator.generate_standalone_from_package(
                    package_name,
                    output_path,
                    context=context,
                )
            except ImportError as e:
                raise click.ClickException(f"Cannot import package '{package_name}': {e}") from None
            except ValueError as e:
                raise click.ClickException(str(e)) from None

        console.print(f"[green]✓[/green] Generated server at: {result}")
        console.print(f"\n[dim]To run: python {result}[/dim]")

        # Save cache if enabled
        if not no_cache:
            cache.save(package_name)


@package.command(name="serve")
@click.argument("package_name", required=True)
@click.option(
    "--name",
    type=str,
    default=None,
    help="Name for the server (defaults to package name)",
)
@click.option(
    "--max-depth",
    type=int,
    default=None,
    help="Maximum recursion depth for submodule discovery",
)
@click.option(
    "--include-private",
    is_flag=True,
    help="Include private modules and methods",
)
@click.option(
    "--public-api-only",
    is_flag=True,
    default=True,
    help="Only expose functions in __all__ (public API) [default: True]",
)
@click.option(
    "--include",
    "include_patterns",
    multiple=True,
    help="Glob patterns for modules to include",
)
@click.option(
    "--exclude",
    "exclude_patterns",
    multiple=True,
    help="Glob patterns for modules to exclude",
)
@click.option(
    "--llm-provider",
    type=click.Choice(["ollama", "openai", "anthropic"]),
    help="LLM provider for description generation",
)
@click.option(
    "--llm-model",
    type=str,
    help="Model name for description generation",
)
@click.option(
    "--no-llm",
    is_flag=True,
    help="Disable LLM description generation",
)
@click.option(
    "--no-cache",
    is_flag=True,
    help="Disable caching of generated descriptions",
)
@click.option(
    "--transport",
    type=click.Choice(["stdio", "sse"]),
    default="stdio",
    help="MCP transport to use",
)
@click.option(
    "--include-reexports",
    is_flag=True,
    help="Include functions re-exported in __all__ from submodules (e.g., pandas, numpy)",
)
@click.option(
    "--enable-sessions",
    is_flag=True,
    help="Enable session lifecycle support (create_session/close_session tools)",
)
@click.option(
    "--session-ttl",
    type=int,
    default=3600,
    help="Session TTL in seconds (default: 3600)",
)
@click.option(
    "--max-sessions",
    type=int,
    default=100,
    help="Maximum number of concurrent sessions (default: 100)",
)
@click.option(
    "--no-isolated",
    is_flag=True,
    help="Force local execution only (fail if package not installed)",
)
@click.option(
    "--version",
    "pkg_version",
    type=str,
    default=None,
    help="Package version to use with uvx (e.g., '2.28.0')",
)
@click.pass_context
def package_serve(
    ctx: click.Context,
    package_name: str,
    name: str | None,
    max_depth: int | None,
    include_private: bool,
    public_api_only: bool,
    include_patterns: tuple[str, ...],
    exclude_patterns: tuple[str, ...],
    llm_provider: str | None,
    llm_model: str | None,
    no_llm: bool,
    no_cache: bool,
    transport: Literal["stdio", "sse"],
    include_reexports: bool,
    enable_sessions: bool,
    session_ttl: int,
    max_sessions: int,
    no_isolated: bool,
    pkg_version: str | None,
) -> None:
    """Run an MCP server from an installed package.

    PACKAGE_NAME: Name of the installed package (e.g., 'requests', 'json')

    If the package is not installed locally, it will automatically be served
    in an isolated uvx environment.

    Examples:

        # Serve requests package
        auto-mcp-tool package serve requests

        # Serve with custom name
        auto-mcp-tool package serve requests --name "HTTP Server"

        # Serve with filtering
        auto-mcp-tool package serve boto3 --include 'boto3.s3.*' --max-depth 2

        # Serve a specific version (uses uvx)
        auto-mcp-tool package serve requests==2.28.0
    """
    from auto_mcp.isolation import IsolationManager, check_uvx_available
    from auto_mcp.isolation.manager import IsolationConfig, IsolationError

    settings: Settings = ctx.obj["settings"]

    # Create isolation manager
    isolation = IsolationManager(
        package_name=package_name,
        version=pkg_version,
        force_local=no_isolated,
    )

    # Determine execution mode
    use_isolation = isolation.should_use_isolation()

    # If version specified, always use isolation
    if pkg_version:
        use_isolation = True

    server_name = name or f"{isolation.package_name}-mcp-server"

    if use_isolation:
        # Check if uvx is available
        if not check_uvx_available():
            raise click.ClickException(
                f"Package '{package_name}' is not installed locally and uvx is not available.\n"
                "Either install the package or install uv: https://docs.astral.sh/uv/"
            )

        console.print(f"[dim]Package not installed locally, using uvx isolation...[/dim]")
        console.print(f"[bold blue]Starting server for '{isolation.get_package_spec()}'...[/bold blue]")

        if enable_sessions:
            console.print("[green]✓[/green] Session lifecycle enabled")

        console.print(f"[green]✓[/green] Server '{server_name}' ready")
        console.print(f"[dim]Transport: {transport}[/dim]\n")

        iso_config = IsolationConfig(
            package_name=isolation.package_name,
            version=isolation.version,
            max_depth=max_depth,
            include_private=include_private,
            include_reexports=include_reexports,
            include_patterns=list(include_patterns) if include_patterns else None,
            exclude_patterns=list(exclude_patterns) if exclude_patterns else None,
            public_api_only=public_api_only,
            server_name=server_name,
            enable_sessions=enable_sessions,
            session_ttl=session_ttl,
            max_sessions=max_sessions,
            transport=transport,
        )

        # This replaces the current process with uvx
        # Note: run_serve does not return - it exec's into the subprocess
        try:
            isolation.run_serve(iso_config)
        except IsolationError as e:
            raise click.ClickException(str(e)) from None
    else:
        # Local execution (original flow)
        console.print(f"[bold blue]Loading package '{package_name}'...[/bold blue]")

        # Create LLM provider if enabled
        llm = None
        if not no_llm:
            llm = get_llm_provider(llm_provider, llm_model, settings)
            if llm:
                console.print(f"[green]✓[/green] Using LLM: {llm.model_name}")

        # Create cache
        cache = PromptCache() if not no_cache else PromptCache(cache_dir=None)

        # Create generator config
        config = GeneratorConfig(
            server_name=server_name,
            include_private=include_private,
            use_cache=not no_cache,
            use_llm=not no_llm and llm is not None,
            max_depth=max_depth,
            public_api_only=public_api_only,
            include_patterns=list(include_patterns) if include_patterns else None,
            exclude_patterns=list(exclude_patterns) if exclude_patterns else None,
            include_reexports=include_reexports,
            enable_sessions=enable_sessions,
            session_ttl=session_ttl,
            max_sessions=max_sessions,
        )

        # Create generator
        generator = MCPGenerator(llm=llm, cache=cache, config=config)

        console.print("[bold blue]Creating MCP server...[/bold blue]")

        if enable_sessions:
            console.print("[green]✓[/green] Session lifecycle enabled")

        try:
            server = generator.create_server_from_package(package_name)
        except ImportError as e:
            raise click.ClickException(f"Cannot import package '{package_name}': {e}") from None
        except ValueError as e:
            raise click.ClickException(str(e)) from None

        console.print(f"[green]✓[/green] Server '{server_name}' ready")
        console.print(f"[dim]Transport: {transport}[/dim]\n")

        # Run server
        server.run(transport=transport)


# =============================================================================
# Wrapper Commands (for C extension modules)
# =============================================================================


@cli.group()
def wrapper() -> None:
    """Generate Python wrappers for C extension modules.

    C extension modules (like sqlite3, _json, etc.) cannot be directly
    introspected by Python. These commands generate pure Python wrappers
    that delegate to the original module, making them analyzable.
    """
    pass


@wrapper.command(name="generate")
@click.argument("module_name", required=True)
@click.option(
    "-o",
    "--output",
    type=click.Path(),
    required=True,
    help="Output path for generated wrapper file",
)
@click.option(
    "--with",
    "with_package",
    type=str,
    default=None,
    help="Package name to install (if different from module name, e.g., --with Pillow for PIL module)",
)
@click.option(
    "--version",
    "pkg_version",
    type=str,
    default=None,
    help="Package version to use with uvx (e.g., '2.28.0')",
)
@click.option(
    "--no-isolated",
    is_flag=True,
    help="Disable automatic uvx isolation (fail if module not installed locally)",
)
@click.option(
    "--include-private",
    is_flag=True,
    help="Include private methods (starting with _)",
)
@click.option(
    "--include-dunder",
    is_flag=True,
    help="Include dunder methods (__init__, etc.)",
)
@click.pass_context
def wrapper_generate(
    ctx: click.Context,
    module_name: str,
    output: str,
    with_package: str | None,
    pkg_version: str | None,
    no_isolated: bool,
    include_private: bool,
    include_dunder: bool,
) -> None:
    """Generate a Python wrapper for a C extension module.

    MODULE_NAME: Name of the module to wrap (e.g., 'sqlite3', '_json')

    This creates a pure Python file that wraps the C extension functions,
    making them introspectable for MCP server generation.

    If the module is not installed locally, it will automatically be generated
    in an isolated uvx environment.

    Examples:

        # Generate wrapper for sqlite3 (stdlib)
        auto-mcp-tool wrapper generate sqlite3 -o sqlite3_wrapper.py

        # Generate wrapper for third-party package (auto-installs via uvx)
        auto-mcp-tool wrapper generate requests -o requests_wrapper.py

        # Package name differs from module name
        auto-mcp-tool wrapper generate PIL --with Pillow -o pil_wrapper.py

        # Specific version
        auto-mcp-tool wrapper generate requests --version 2.28.0 -o wrapper.py

        # Then generate MCP server from the wrapper
        auto-mcp-tool generate sqlite3_wrapper.py -o sqlite_server.py

        # Include private methods
        auto-mcp-tool wrapper generate sqlite3 -o wrapper.py --include-private
    """
    import subprocess

    from auto_mcp.isolation import check_uvx_available
    from auto_mcp.isolation.manager import is_package_installed
    from auto_mcp.wrapper import WrapperGenerator

    output_path = Path(output).resolve()

    # Determine package name (module name unless --with overrides)
    package_name = with_package or module_name

    # Build version spec
    package_spec = package_name
    if pkg_version:
        package_spec = f"{package_name}=={pkg_version}"

    # Check if module is available locally
    module_available = False
    try:
        module = importlib.import_module(module_name)
        module_available = True
    except ImportError:
        pass

    # Determine if we need isolation
    use_isolation = not module_available and not no_isolated

    # If version specified, always use isolation to get that specific version
    if pkg_version:
        use_isolation = True

    if use_isolation:
        # Check if uvx is available
        if not check_uvx_available():
            raise click.ClickException(
                f"Module '{module_name}' is not installed locally and uvx is not available.\n"
                "Either install the module or install uv: https://docs.astral.sh/uv/\n\n"
                f"Or try: pip install {package_name}"
            ) from None

        console.print(f"[dim]Module not installed locally, using uvx isolation...[/dim]")

        # Build uvx command
        # Use --from to get auto-mcp-tool, --with to add the target package
        from auto_mcp.isolation.manager import get_auto_mcp_source_dir

        source_dir = get_auto_mcp_source_dir()
        auto_mcp_source = str(source_dir) if source_dir else "auto-mcp-tool"

        uvx_cmd = [
            "uvx",
            "--from", auto_mcp_source,
            "--with", package_spec,
            "auto-mcp-tool",
            "internal-worker", "wrapper",
            "--module", module_name,
            "--output", str(output_path),
        ]
        if include_private:
            uvx_cmd.append("--include-private")
        if include_dunder:
            uvx_cmd.append("--include-dunder")

        with console.status(f"[bold blue]Generating wrapper via uvx..."):
            try:
                result = subprocess.run(
                    uvx_cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
            except subprocess.TimeoutExpired:
                raise click.ClickException(
                    "Wrapper generation timed out. The package may be too large."
                ) from None
            except FileNotFoundError:
                raise click.ClickException(
                    "uvx not found. Please install uv: https://docs.astral.sh/uv/"
                ) from None

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            # Check for common errors
            if "not found" in error_msg.lower() or "No matching" in error_msg:
                raise click.ClickException(
                    f"Package '{package_spec}' not found on PyPI.\n"
                    f"If the package name differs from the module name, use --with:\n"
                    f"  auto-mcp-tool wrapper generate {module_name} --with <package-name> -o {output}"
                )
            raise click.ClickException(f"Failed to generate wrapper: {error_msg}")

        # Parse JSON output from worker
        try:
            import json
            output_data = json.loads(result.stdout)
            if not output_data.get("success"):
                raise click.ClickException(output_data.get("error", "Unknown error"))
            generated_count = output_data.get("function_count", 0)
        except json.JSONDecodeError:
            # Fallback if not JSON (shouldn't happen with worker)
            generated_count = 0

        console.print(f"[green]✓[/green] Generated wrapper at: {output_path}")
        if generated_count:
            console.print(f"[dim]Generated {generated_count} wrapper functions[/dim]")
        console.print("\n[bold]Next steps:[/bold]")
        console.print(f"  1. Review and customize the wrapper: {output_path}")
        console.print(
            f"  2. Generate MCP server: auto-mcp-tool generate {output_path} -o server.py"
        )
        return

    # Local execution - module already imported above or --no-isolated specified
    if not module_available:
        raise click.ClickException(
            f"Cannot import module '{module_name}'.\n\n"
            f"If this is a third-party package, either:\n"
            f"  1. Remove --no-isolated to use automatic uvx isolation\n"
            f"  2. Install the package: pip install {package_name}"
        ) from None

    # Create generator
    generator = WrapperGenerator(
        include_private=include_private,
        include_dunder=include_dunder,
    )

    # Check if it's a C extension
    is_c_ext = generator.is_c_extension_module(module)

    with console.status(f"[bold blue]Analyzing '{module_name}'..."):
        functions, classes = generator.analyze_module(module)

    # Count callables
    total_funcs = len(functions)
    total_methods = sum(len(c.methods) for c in classes)
    c_ext_funcs = sum(1 for f in functions if f.is_c_extension)
    c_ext_methods = sum(1 for c in classes for m in c.methods if m.is_c_extension)

    if is_c_ext:
        console.print("[yellow]![/yellow] Detected C extension module")
    console.print(
        f"[dim]Found {total_funcs} functions, {len(classes)} classes "
        f"with {total_methods} methods[/dim]"
    )
    console.print(
        f"[dim]C extension callables: {c_ext_funcs} functions, "
        f"{c_ext_methods} methods[/dim]"
    )

    if total_funcs == 0 and total_methods == 0:
        raise click.ClickException(f"No callable objects found in '{module_name}'")

    # Generate wrapper
    with console.status("[bold blue]Generating wrapper..."):
        code = generator.generate_wrapper(module, output_path)

    # Count generated functions
    generated_count = code.count("\ndef ")

    console.print(f"[green]✓[/green] Generated wrapper at: {output_path}")
    console.print(f"[dim]Generated {generated_count} wrapper functions[/dim]")
    console.print("\n[bold]Next steps:[/bold]")
    console.print(f"  1. Review and customize the wrapper: {output_path}")
    console.print(f"  2. Generate MCP server: auto-mcp-tool generate {output_path} -o server.py")


@wrapper.command(name="check")
@click.argument("module_name", required=True)
@click.option(
    "--include-private",
    is_flag=True,
    help="Include private methods (starting with _)",
)
@click.pass_context
def wrapper_check(
    ctx: click.Context,
    module_name: str,
    include_private: bool,
) -> None:
    """Check a module for C extension callables.

    MODULE_NAME: Name of the module to check (e.g., 'sqlite3')

    This analyzes the module and reports which callables are C extensions
    that would benefit from wrapper generation.

    Examples:

        auto-mcp-tool wrapper check sqlite3
        auto-mcp-tool wrapper check json
    """
    from auto_mcp.wrapper import WrapperGenerator

    # Try to import the module
    try:
        module = importlib.import_module(module_name)
    except ImportError as e:
        raise click.ClickException(f"Cannot import module '{module_name}': {e}") from None

    generator = WrapperGenerator(include_private=include_private)

    is_c_ext = generator.is_c_extension_module(module)
    functions, classes = generator.analyze_module(module)

    # Display results
    panel_content = []
    panel_content.append(f"[cyan]Module:[/cyan] {module_name}")
    panel_content.append(f"[cyan]C Extension:[/cyan] {'Yes' if is_c_ext else 'No'}")
    panel_content.append(f"[cyan]Module File:[/cyan] {getattr(module, '__file__', 'built-in')}")

    console.print(Panel("\n".join(panel_content), title="Module Info"))

    # Functions table
    if functions:
        table = Table(title="Functions", show_header=True)
        table.add_column("Name", style="cyan")
        table.add_column("C Extension", style="yellow")
        table.add_column("Has Docstring")
        table.add_column("Parsed Params")

        for func in functions:
            param_count = len(func.signature.parameters) if func.signature else 0
            table.add_row(
                func.name,
                "Yes" if func.is_c_extension else "No",
                "Yes" if func.docstring else "No",
                str(param_count),
            )

        console.print(table)

    # Classes table
    for cls_info in classes:
        if cls_info.methods:
            table = Table(title=f"Class: {cls_info.name}", show_header=True)
            table.add_column("Method", style="cyan")
            table.add_column("C Extension", style="yellow")
            table.add_column("Has Docstring")

            for method in cls_info.methods:
                table.add_row(
                    method.name,
                    "Yes" if method.is_c_extension else "No",
                    "Yes" if method.docstring else "No",
                )

            console.print(table)

    # Summary
    total_funcs = len(functions)
    total_methods = sum(len(c.methods) for c in classes)
    c_ext_funcs = sum(1 for f in functions if f.is_c_extension)
    c_ext_methods = sum(1 for c in classes for m in c.methods if m.is_c_extension)

    console.print("\n" + "─" * 50)
    console.print("[bold]Summary:[/bold]")
    console.print(f"  Functions: {total_funcs} total, {c_ext_funcs} C extension")
    console.print(f"  Methods: {total_methods} total, {c_ext_methods} C extension")

    if c_ext_funcs > 0 or c_ext_methods > 0:
        console.print("\n[yellow]Recommendation:[/yellow] Generate a wrapper with:")
        console.print(
            f"  auto-mcp-tool wrapper generate {module_name} -o {module_name}_wrapper.py"
        )


# =============================================================================
# Internal Worker Commands (hidden, for uvx subprocess execution)
# =============================================================================


@cli.group(hidden=True)
def internal_worker() -> None:
    """Internal commands for subprocess workers (hidden from help).

    These commands are used by the isolation manager when running
    package analysis in a uvx subprocess.
    """
    pass


@internal_worker.command(name="check")
@click.option("--config", "config_json", required=True, help="JSON configuration")
def internal_worker_check(config_json: str) -> None:
    """Internal: Run package check as worker."""
    from auto_mcp.isolation.worker import worker_check

    worker_check(config_json)


@internal_worker.command(name="generate")
@click.option("--config", "config_json", required=True, help="JSON configuration")
def internal_worker_generate(config_json: str) -> None:
    """Internal: Run package generate as worker."""
    from auto_mcp.isolation.worker import worker_generate

    worker_generate(config_json)


@internal_worker.command(name="serve")
@click.option("--config", "config_json", required=True, help="JSON configuration")
def internal_worker_serve(config_json: str) -> None:
    """Internal: Run package serve as worker."""
    from auto_mcp.isolation.worker import worker_serve

    worker_serve(config_json)


@internal_worker.command(name="manifest-generate")
@click.option("--package", "package_name", required=True, help="Package name to generate from")
@click.option("--manifest", "manifest_path", required=True, help="Path to YAML manifest")
@click.option("--output", "output_path", required=True, help="Output file path")
@click.option("--server-name", default="auto-mcp-server", help="Server name")
def internal_worker_manifest_generate(
    package_name: str,
    manifest_path: str,
    output_path: str,
    server_name: str,
) -> None:
    """Internal: Generate MCP server from manifest as worker."""
    import json

    try:
        module = importlib.import_module(package_name)

        from auto_mcp.manifest import Manifest, ManifestGenerator

        manifest = Manifest.from_yaml(Path(manifest_path))
        # Override server name if provided
        if server_name:
            manifest = Manifest(
                package=manifest.package,
                module=manifest.module,
                version=manifest.version,
                server_name=server_name,
                auto_include_dependencies=manifest.auto_include_dependencies,
                tools=manifest.tools,
            )

        generator = ManifestGenerator()
        generator.generate(module, manifest, Path(output_path), package_name)

        # Output JSON result
        result = {
            "success": True,
            "output_path": output_path,
        }
        print(json.dumps(result))

    except Exception as e:
        result = {
            "success": False,
            "error": str(e),
        }
        print(json.dumps(result))
        raise SystemExit(1) from None


@internal_worker.command(name="wrapper")
@click.option("--module", "module_name", required=True, help="Module name to wrap")
@click.option("--output", "output_path", required=True, help="Output file path")
@click.option("--include-private", is_flag=True, help="Include private methods")
@click.option("--include-dunder", is_flag=True, help="Include dunder methods")
def internal_worker_wrapper(
    module_name: str,
    output_path: str,
    include_private: bool,
    include_dunder: bool,
) -> None:
    """Internal: Generate wrapper as worker."""
    import json

    try:
        module = importlib.import_module(module_name)

        from auto_mcp.wrapper import WrapperGenerator

        generator = WrapperGenerator(
            include_private=include_private,
            include_dunder=include_dunder,
        )

        code = generator.generate_wrapper(module, Path(output_path))
        function_count = code.count("\ndef ")

        # Output JSON result
        result = {
            "success": True,
            "output_path": output_path,
            "function_count": function_count,
        }
        print(json.dumps(result))

    except Exception as e:
        result = {
            "success": False,
            "error": str(e),
        }
        print(json.dumps(result))
        raise SystemExit(1) from None


def main() -> None:
    """Main entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
