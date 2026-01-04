"""Command-line interface for auto-mcp."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Literal

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from auto_mcp.cache import PromptCache
from auto_mcp.config import Settings, get_settings
from auto_mcp.core.analyzer import ModuleAnalyzer
from auto_mcp.core.generator import GeneratorConfig, MCPGenerator
from auto_mcp.core.package import PackageAnalyzer
from auto_mcp.llm import LLMProvider, create_provider
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
@click.version_option(package_name="auto-mcp")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """auto-mcp: Automatically generate MCP servers from Python modules.

    Use this tool to analyze Python modules and generate MCP-compatible
    servers with tools, resources, and prompts.
    """
    ctx.ensure_object(dict)
    ctx.obj["settings"] = get_settings()


@cli.command()
@click.argument("modules", nargs=-1, required=True, type=click.Path(exists=True))
@click.option(
    "-o",
    "--output",
    type=click.Path(),
    help="Output path for generated file or directory",
)
@click.option(
    "--package",
    type=str,
    help="Generate as a package with this name (instead of standalone file)",
)
@click.option(
    "--name",
    type=str,
    default="auto-mcp-server",
    help="Name for the generated server",
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
@click.pass_context
def generate(
    ctx: click.Context,
    modules: tuple[str, ...],
    output: str | None,
    package: str | None,
    name: str,
    llm_provider: str | None,
    llm_model: str | None,
    no_llm: bool,
    no_cache: bool,
    include_private: bool,
    no_resources: bool,
    no_prompts: bool,
    context: str | None,
) -> None:
    """Generate an MCP server from Python modules.

    MODULES: One or more Python files to analyze and expose as MCP tools.

    Examples:

        # Generate standalone server file
        auto-mcp generate mymodule.py -o server.py

        # Generate with custom server name
        auto-mcp generate mymodule.py -o server.py --name "My MCP Server"

        # Generate as a package
        auto-mcp generate mymodule.py --package my-server -o ./dist

        # Generate without LLM (use docstrings only)
        auto-mcp generate mymodule.py -o server.py --no-llm
    """
    settings: Settings = ctx.obj["settings"]

    # Load modules
    with console.status("[bold blue]Loading modules..."):
        loaded_modules = load_modules(modules)
    console.print(f"[green]✓[/green] Loaded {len(loaded_modules)} module(s)")

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
    )

    # Create generator
    generator = MCPGenerator(llm=llm, cache=cache, config=config)

    # Generate output
    if package:
        # Generate package
        output_dir = Path(output) if output else Path.cwd()
        with console.status(f"[bold blue]Generating package '{package}'..."):
            result = generator.generate_package(
                loaded_modules,
                output_dir,
                package,
                context=context,
            )
        console.print(f"[green]✓[/green] Generated package at: {result}")
        console.print(f"\n[dim]To install: pip install {result}[/dim]")
    else:
        # Generate standalone file
        output_path = Path(output) if output else Path("server.py")
        with console.status("[bold blue]Generating standalone server..."):
            result = generator.generate_standalone(
                loaded_modules,
                output_path,
                context=context,
            )
        console.print(f"[green]✓[/green] Generated server at: {result}")
        console.print(f"\n[dim]To run: python {result}[/dim]")

    # Save cache if enabled
    if not no_cache:
        for module in loaded_modules:
            cache.save(module.__name__)


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
) -> None:
    """Run an MCP server from Python modules.

    MODULES: One or more Python files to expose as MCP tools.

    Examples:

        # Run server with stdio transport
        auto-mcp serve mymodule.py

        # Run with custom name
        auto-mcp serve mymodule.py --name "My Server"

        # Run with SSE transport
        auto-mcp serve mymodule.py --transport sse

        # Run with hot-reload enabled
        auto-mcp serve mymodule.py --watch
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
    )

    # Create generator and server
    generator = MCPGenerator(llm=llm, cache=cache, config=config)

    console.print("[bold blue]Creating MCP server...[/bold blue]")

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
        auto-mcp check mymodule.py

        # Include private methods in check
        auto-mcp check mymodule.py --include-private

        # Show detailed information
        auto-mcp check mymodule.py -v
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
        auto-mcp cache clear mymodule.py

        # Clear all cache
        auto-mcp cache clear --all
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

        auto-mcp cache stats
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

        auto-mcp config show
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

    console.print(table)

    console.print(
        "\n[dim]Configuration is loaded from environment variables "
        "with AUTO_MCP_ prefix.[/dim]"
    )
    console.print("[dim]Example: AUTO_MCP_LLM_PROVIDER=openai[/dim]")


@config.command(name="env")
@click.pass_context
def config_env(ctx: click.Context) -> None:
    """Show environment variable names for configuration.

    Examples:

        auto-mcp config env
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
) -> None:
    """Analyze an installed package and show what would be exposed.

    PACKAGE_NAME: Name of the installed package (e.g., 'requests', 'json')

    Examples:

        # Check requests package
        auto-mcp package check requests

        # Check with depth limit
        auto-mcp package check boto3 --max-depth 2

        # Check only public API
        auto-mcp package check requests --public-api-only

        # Check with module filtering
        auto-mcp package check requests --include 'requests.api.*'

        # Verbose output
        auto-mcp package check requests -v
    """
    # Try to import the package
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

    # Get methods to display
    methods = analyzer.get_public_methods(metadata) if public_api_only else metadata.methods

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
) -> None:
    """Generate an MCP server from an installed package.

    PACKAGE_NAME: Name of the installed package (e.g., 'requests', 'json')

    Examples:

        # Generate server from requests
        auto-mcp package generate requests -o requests_server.py

        # Generate with custom name
        auto-mcp package generate requests -o server.py --name "HTTP Server"

        # Generate with filtering
        auto-mcp package generate requests -o server.py --public-api-only

        # Generate without LLM
        auto-mcp package generate json -o json_server.py --no-llm
    """
    settings: Settings = ctx.obj["settings"]
    server_name = name or f"{package_name}-mcp-server"

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
    )

    # Create generator
    generator = MCPGenerator(llm=llm, cache=cache, config=config)

    # Generate
    output_path = Path(output)
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
) -> None:
    """Run an MCP server from an installed package.

    PACKAGE_NAME: Name of the installed package (e.g., 'requests', 'json')

    Examples:

        # Serve requests package
        auto-mcp package serve requests

        # Serve with custom name
        auto-mcp package serve requests --name "HTTP Server"

        # Serve with filtering
        auto-mcp package serve boto3 --include 'boto3.s3.*' --max-depth 2
    """
    settings: Settings = ctx.obj["settings"]
    server_name = name or f"{package_name}-mcp-server"

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
    )

    # Create generator
    generator = MCPGenerator(llm=llm, cache=cache, config=config)

    console.print("[bold blue]Creating MCP server...[/bold blue]")

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


def main() -> None:
    """Main entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
