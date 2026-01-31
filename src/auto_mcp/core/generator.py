"""MCP server code generator."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import FastMCP

from auto_mcp.cache import PromptCache
from auto_mcp.core.analyzer import MethodMetadata, ModuleAnalyzer
from auto_mcp.core.package import PackageAnalyzer, PackageMetadata
from auto_mcp.prompts.templates import (
    get_fallback_prompt_description,
    get_fallback_resource_description,
    get_fallback_tool_description,
)
from auto_mcp.types import (
    FunctionWrapper,
    ObjectStore,
    TypeRegistry,
    get_default_registry,
    get_default_store,
    register_stdlib_adapters,
)

if TYPE_CHECKING:
    from auto_mcp.llm.base import LLMProvider
    from auto_mcp.session.manager import SessionManager


@dataclass
class GeneratorConfig:
    """Configuration for MCP generation.

    Attributes:
        server_name: Name for the generated MCP server
        server_description: Description for the server
        include_private: Whether to include private methods
        generate_resources: Whether to generate MCP resources
        generate_prompts: Whether to generate MCP prompts
        use_cache: Whether to use caching for LLM descriptions
        use_llm: Whether to use LLM for description generation
        max_depth: Maximum depth for recursive package analysis
        public_api_only: Only expose functions in __all__ (public API)
        include_patterns: Glob patterns for modules to include
        exclude_patterns: Glob patterns for modules to exclude
        enable_type_transforms: Enable automatic type transformations
        register_stdlib_adapters: Auto-register standard library adapters
        include_reexports: Include functions re-exported in __all__ from submodules
        enable_sessions: Enable session lifecycle support
        session_ttl: Default session TTL in seconds
        max_sessions: Maximum number of concurrent sessions
    """

    server_name: str = "auto-mcp-server"
    server_description: str = "Auto-generated MCP server"
    include_private: bool = False
    generate_resources: bool = True
    generate_prompts: bool = True
    use_cache: bool = True
    use_llm: bool = True
    max_depth: int | None = None
    public_api_only: bool = False
    include_patterns: list[str] | None = None
    exclude_patterns: list[str] | None = None
    enable_type_transforms: bool = False
    register_stdlib_adapters: bool = True
    include_reexports: bool = False
    enable_sessions: bool = False
    session_ttl: int = 3600
    max_sessions: int = 100


@dataclass
class GeneratedTool:
    """Represents a generated MCP tool.

    Attributes:
        name: Tool name
        description: Tool description
        function: The original function
        metadata: The method metadata
        parameter_descriptions: Descriptions for parameters
    """

    name: str
    description: str
    function: Any
    metadata: MethodMetadata
    parameter_descriptions: dict[str, str] = field(default_factory=dict)


@dataclass
class GeneratedResource:
    """Represents a generated MCP resource.

    Attributes:
        name: Resource name
        uri: URI template
        description: Resource description
        function: The original function
        metadata: The method metadata
    """

    name: str
    uri: str
    description: str
    function: Any
    metadata: MethodMetadata
    mime_type: str | None = None


@dataclass
class GeneratedPrompt:
    """Represents a generated MCP prompt.

    Attributes:
        name: Prompt name
        description: Prompt description
        function: The original function
        metadata: The method metadata
    """

    name: str
    description: str
    function: Any
    metadata: MethodMetadata


class MCPGenerator:
    """Generates MCP servers from Python modules.

    This class analyzes Python modules and generates MCP-compatible
    servers with tools, resources, and prompts.
    """

    def __init__(
        self,
        llm: LLMProvider | None = None,
        cache: PromptCache | None = None,
        config: GeneratorConfig | None = None,
        type_registry: TypeRegistry | None = None,
        object_store: ObjectStore | None = None,
        session_manager: "SessionManager | None" = None,
    ) -> None:
        """Initialize the generator.

        Args:
            llm: LLM provider for description generation (optional)
            cache: Cache for storing generated descriptions (optional)
            config: Generator configuration (uses defaults if not provided)
            type_registry: Registry for type adapters (optional)
            object_store: Store for stateful objects (optional)
            session_manager: Session manager for session lifecycle (optional)
        """
        self.llm = llm
        self.cache = cache or PromptCache()
        self.config = config or GeneratorConfig()
        self.analyzer = ModuleAnalyzer(
            include_private=self.config.include_private,
            include_reexports=self.config.include_reexports,
        )
        self.package_analyzer = PackageAnalyzer(
            include_private=self.config.include_private,
            max_depth=self.config.max_depth,
            include_reexports=self.config.include_reexports,
        )

        # Initialize type system
        self.type_registry = type_registry or get_default_registry()
        self.object_store = object_store or get_default_store()

        # Register stdlib adapters if configured
        if self.config.register_stdlib_adapters:
            register_stdlib_adapters(self.type_registry)

        # Initialize session manager if sessions are enabled
        self.session_manager: "SessionManager | None" = None
        if self.config.enable_sessions:
            if session_manager:
                self.session_manager = session_manager
            else:
                from auto_mcp.session.manager import SessionConfig, SessionManager

                self.session_manager = SessionManager(
                    config=SessionConfig(
                        default_ttl=self.config.session_ttl,
                        max_sessions=self.config.max_sessions,
                    )
                )

    async def analyze_and_generate(
        self,
        modules: list[ModuleType],
        context: str | None = None,
    ) -> tuple[list[GeneratedTool], list[GeneratedResource], list[GeneratedPrompt]]:
        """Analyze modules and generate MCP components.

        Args:
            modules: List of Python modules to analyze
            context: Optional context for LLM description generation

        Returns:
            Tuple of (tools, resources, prompts)
        """
        tools: list[GeneratedTool] = []
        resources: list[GeneratedResource] = []
        prompts: list[GeneratedPrompt] = []

        for module in modules:
            methods = self.analyzer.analyze_module(module)

            for method in methods:
                # Check what type of MCP component this should be
                if method.is_resource:
                    resource = await self._generate_resource(method, module, context)
                    if resource:
                        resources.append(resource)
                elif method.is_prompt:
                    prompt = await self._generate_prompt(method, module, context)
                    if prompt:
                        prompts.append(prompt)
                else:
                    # Default to tool
                    tool = await self._generate_tool(method, module, context)
                    if tool:
                        tools.append(tool)

        return tools, resources, prompts

    async def analyze_and_generate_from_package(
        self,
        package: str | ModuleType,
        context: str | None = None,
    ) -> tuple[list[GeneratedTool], list[GeneratedResource], list[GeneratedPrompt]]:
        """Analyze a package recursively and generate MCP components.

        Args:
            package: Package name (string) or module object
            context: Optional context for LLM description generation

        Returns:
            Tuple of (tools, resources, prompts)
        """
        # Analyze the package
        pkg_metadata = self.package_analyzer.analyze_package(
            package,
            include_patterns=self.config.include_patterns,
            exclude_patterns=self.config.exclude_patterns,
        )

        # Get methods to process
        if self.config.public_api_only:
            methods = self.package_analyzer.get_public_methods(pkg_metadata)
        else:
            methods = pkg_metadata.methods

        tools: list[GeneratedTool] = []
        resources: list[GeneratedResource] = []
        prompts: list[GeneratedPrompt] = []

        # Process each method
        for method in methods:
            # Get the module containing this method
            module_info = pkg_metadata.modules.get(method.module_name)
            if not module_info:
                continue
            module = module_info.module

            # Check what type of MCP component this should be
            if method.is_resource:
                resource = await self._generate_resource(method, module, context)
                if resource:
                    resources.append(resource)
            elif method.is_prompt:
                prompt = await self._generate_prompt(method, module, context)
                if prompt:
                    prompts.append(prompt)
            else:
                # Default to tool
                tool = await self._generate_tool(method, module, context)
                if tool:
                    tools.append(tool)

        return tools, resources, prompts

    def analyze_package(
        self,
        package: str | ModuleType,
    ) -> PackageMetadata:
        """Analyze a package and return its metadata.

        Args:
            package: Package name (string) or module object

        Returns:
            PackageMetadata with all discovered modules and methods
        """
        return self.package_analyzer.analyze_package(
            package,
            include_patterns=self.config.include_patterns,
            exclude_patterns=self.config.exclude_patterns,
        )

    def create_server_from_package(
        self,
        package: str | ModuleType,
        context: str | None = None,
    ) -> FastMCP:
        """Create an in-memory FastMCP server from a package.

        Args:
            package: Package name (string) or module object
            context: Optional context for LLM description generation

        Returns:
            Configured FastMCP server instance
        """
        # Analyze the package to get modules
        pkg_metadata = self.package_analyzer.analyze_package(
            package,
            include_patterns=self.config.include_patterns,
            exclude_patterns=self.config.exclude_patterns,
        )

        # Run async analysis synchronously
        tools, resources, prompts = asyncio.run(
            self.analyze_and_generate_from_package(package, context)
        )

        # Create FastMCP server
        mcp = FastMCP(
            name=self.config.server_name,
        )

        # Register session hooks and tools if sessions are enabled
        if self.config.enable_sessions and self.session_manager:
            # Extract modules from package metadata
            pkg_modules = [
                info.module for info in pkg_metadata.modules.values() if info.module
            ]
            self._register_session_hooks(pkg_modules)
            self._register_session_tools(mcp)

        # Register tools
        for tool in tools:
            self._register_tool(mcp, tool)

        # Register resources
        if self.config.generate_resources:
            for resource in resources:
                self._register_resource(mcp, resource)

        # Register prompts
        if self.config.generate_prompts:
            for prompt in prompts:
                self._register_prompt(mcp, prompt)

        return mcp

    def generate_standalone_from_package(
        self,
        package: str | ModuleType,
        output_path: Path | str,
        context: str | None = None,
    ) -> Path:
        """Generate a standalone MCP server file from a package.

        Args:
            package: Package name (string) or module object
            output_path: Path for the generated file
            context: Optional context for LLM description generation

        Returns:
            Path to the generated file
        """
        output_path = Path(output_path)

        # Analyze the package
        pkg_metadata = self.package_analyzer.analyze_package(
            package,
            include_patterns=self.config.include_patterns,
            exclude_patterns=self.config.exclude_patterns,
        )

        # Run async generation
        tools, resources, prompts = asyncio.run(
            self.analyze_and_generate_from_package(package, context)
        )

        # Generate code
        code = self._generate_standalone_code_from_package(
            pkg_metadata, tools, resources, prompts
        )

        # Write file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(code)

        return output_path

    def _escape_docstring(self, docstring: str) -> str:
        """Escape a docstring for safe inclusion in generated triple-quoted strings.

        Handles backslashes (which could form unintended escape sequences)
        and triple-quote sequences that would terminate the docstring.

        Args:
            docstring: The raw docstring text

        Returns:
            Escaped string safe for use inside triple-quoted strings
        """
        result = docstring.replace("\\", "\\\\")
        result = result.replace('"""', '\\"\\"\\"')
        return result

    def _sanitize_type_str(self, type_str: str | None) -> str | None:
        """Sanitize a type string for use in generated code.

        Replaces complex types that would require additional imports with 'Any'.

        Args:
            type_str: The type string from parameter analysis

        Returns:
            Sanitized type string or None
        """
        if not type_str:
            return None

        # List of safe builtin types and typing constructs
        safe_types = {
            "str", "int", "float", "bool", "bytes", "None",
            "list", "dict", "tuple", "set", "frozenset",
            "Any", "Optional", "Union", "List", "Dict", "Tuple", "Set",
            "Callable", "Sequence", "Mapping", "Iterable", "Iterator",
            "Type", "Literal",
        }

        # Bare Union/Optional without brackets is invalid - replace with Any
        # e.g., "Union" should be "Any", but "Union[str, int]" is fine
        if type_str in ("Union", "Optional"):
            return "Any"

        # Check if type string contains potentially problematic types
        # These are types that would need to be imported from the original module
        problematic_patterns = [
            "DataFrame", "Series", "Index", "Timestamp", "Timedelta",
            "DatetimeIndex", "TimedeltaIndex", "PeriodIndex",
            "Categorical", "CategoricalDtype",
            "collections.abc.", "typing.",
            "numpy.", "np.",
            "Hashable", "Iterable[", "Sequence[", "Mapping[",
        ]

        for pattern in problematic_patterns:
            if pattern in type_str:
                return "Any"

        # Check for complex nested types that might cause issues
        # If type_str contains class names that aren't in safe_types
        # and isn't a simple generic like list[str]
        import re
        # Find all word tokens that look like type names (start with capital)
        type_names = re.findall(r'\b([A-Z][a-zA-Z0-9_]*)\b', type_str)
        for type_name in type_names:
            if type_name not in safe_types:
                return "Any"

        return type_str

    def _generate_function_signature(
        self,
        metadata: MethodMetadata,
    ) -> tuple[str, str]:
        """Generate a proper function signature and call site from metadata.

        Args:
            metadata: The method metadata containing parameter info

        Returns:
            Tuple of (signature_params, call_args):
            - signature_params: e.g., "name: str, count: int = 5"
            - call_args: e.g., "name=name, count=count"
        """
        params = []
        call_args = []
        has_var_positional = False
        has_var_keyword = False

        for param in metadata.parameters:
            name = param["name"]
            kind = param["kind"]
            type_str = self._sanitize_type_str(param.get("type_str"))
            has_default = param.get("has_default", False)
            default = param.get("default")

            # Handle *args
            if kind == "VAR_POSITIONAL":
                has_var_positional = True
                if type_str:
                    params.append(f"*args: {type_str}")
                else:
                    params.append("*args")
                call_args.append("*args")
                continue

            # Handle **kwargs
            if kind == "VAR_KEYWORD":
                has_var_keyword = True
                if type_str:
                    params.append(f"**kwargs: {type_str}")
                else:
                    params.append("**kwargs")
                call_args.append("**kwargs")
                continue

            # Build parameter definition
            param_def = name
            if type_str:
                param_def += f": {type_str}"

            if has_default:
                # Format the default value properly
                default_repr = self._format_default_value(default)
                if type_str:
                    param_def += f" = {default_repr}"
                else:
                    param_def += f"={default_repr}"

            params.append(param_def)

            # Build call argument
            call_args.append(f"{name}={name}")

        signature_params = ", ".join(params)
        call_args_str = ", ".join(call_args)

        return signature_params, call_args_str

    def _format_default_value(self, value: Any) -> str:
        """Format a default value for code generation.

        Args:
            value: The default value

        Returns:
            String representation suitable for code
        """
        import enum

        if value is None:
            return "None"
        elif isinstance(value, str):
            # Escape quotes and use repr for proper string formatting
            return repr(value)
        elif isinstance(value, bool):
            return "True" if value else "False"
        elif isinstance(value, (int, float)):
            # Handle special float values that need special representation
            import math
            if isinstance(value, float):
                if math.isnan(value):
                    return "None"  # Can't represent nan without import
                elif math.isinf(value):
                    return "None"  # Can't represent inf without import
            return str(value)
        elif isinstance(value, (list, tuple)):
            return repr(value)
        elif isinstance(value, dict):
            return repr(value)
        elif isinstance(value, enum.Enum):
            # Special enum values like pandas._libs.lib._NoDefault
            # These are sentinel values that should be treated as None
            return "None"
        else:
            # For complex objects, try repr
            try:
                value_repr = repr(value)
                # Check for special sentinel values that can't be used in code
                # e.g., <no_default>, <class 'inspect._empty'>, <object ...>
                if value_repr.startswith("<") and value_repr.endswith(">"):
                    return "None"
                return value_repr
            except Exception:
                return "None"

    def _collect_typing_imports(
        self,
        tools: list[GeneratedTool],
        resources: list[GeneratedResource],
        prompts: list[GeneratedPrompt],
    ) -> set[str]:
        """Collect typing imports needed for generated signatures.

        Args:
            tools: Generated tools
            resources: Generated resources
            prompts: Generated prompts

        Returns:
            Set of typing module names to import (e.g., {"Any", "Optional"})
        """
        typing_imports: set[str] = set()

        # Common typing constructs to look for in type strings
        typing_names = ["Any", "Optional", "Union", "List", "Dict", "Tuple", "Set",
                        "Callable", "Sequence", "Mapping", "Iterable", "Iterator"]

        all_items = list(tools) + list(resources) + list(prompts)

        for item in all_items:
            for param in item.metadata.parameters:
                type_str = param.get("type_str", "")
                if type_str:
                    for name in typing_names:
                        if name in type_str:
                            typing_imports.add(name)

        return typing_imports

    def _generate_standalone_code_from_package(
        self,
        pkg_metadata: PackageMetadata,
        tools: list[GeneratedTool],
        resources: list[GeneratedResource],
        prompts: list[GeneratedPrompt],
    ) -> str:
        """Generate standalone server code from package analysis.

        Args:
            pkg_metadata: The analyzed package metadata
            tools: Generated tools
            resources: Generated resources
            prompts: Generated prompts

        Returns:
            The generated Python code
        """
        # Collect unique modules that need to be imported
        modules_to_import: set[str] = set()
        for tool in tools:
            modules_to_import.add(tool.metadata.module_name)
        for resource in resources:
            modules_to_import.add(resource.metadata.module_name)
        for prompt in prompts:
            modules_to_import.add(prompt.metadata.module_name)

        # Build imports
        imports_code = "\n".join(
            f"import {mod}" for mod in sorted(modules_to_import)
        )

        # Build tool registrations
        tool_code = []
        for tool in tools:
            module_name = tool.metadata.module_name
            func_name = tool.metadata.qualified_name
            desc = self._escape_docstring(tool.description)
            safe_name = tool.name.replace(".", "_")

            # Generate proper signature with named parameters
            sig_params, call_args = self._generate_function_signature(tool.metadata)

            tool_code.append(f'''
@mcp.tool(name="{tool.name}")
def {safe_name}({sig_params}):
    """{desc}"""
    return {module_name}.{func_name}({call_args})
''')

        tools_code = "\n".join(tool_code)

        # Build resource registrations
        resource_code = []
        for resource in resources:
            module_name = resource.metadata.module_name
            func_name = resource.metadata.qualified_name
            desc = self._escape_docstring(resource.description)
            safe_name = resource.name.replace(".", "_")

            # Generate proper signature
            sig_params, call_args = self._generate_function_signature(resource.metadata)

            resource_code.append(f'''
@mcp.resource(uri="{resource.uri}", name="{resource.name}")
def resource_{safe_name}({sig_params}):
    """{desc}"""
    return {module_name}.{func_name}({call_args})
''')

        resources_code = "\n".join(resource_code) if resources else ""

        # Build prompt registrations
        prompt_code = []
        for prompt in prompts:
            module_name = prompt.metadata.module_name
            func_name = prompt.metadata.qualified_name
            desc = self._escape_docstring(prompt.description)
            safe_name = prompt.name.replace(".", "_")

            # Generate proper signature
            sig_params, call_args = self._generate_function_signature(prompt.metadata)

            prompt_code.append(f'''
@mcp.prompt(name="{prompt.name}")
def prompt_{safe_name}({sig_params}):
    """{desc}"""
    return {module_name}.{func_name}({call_args})
''')

        prompts_code = "\n".join(prompt_code) if prompts else ""

        # Collect typing imports needed from signatures
        typing_imports = self._collect_typing_imports(tools, resources, prompts)
        typing_import_line = ""
        if typing_imports:
            typing_import_line = f"from typing import {', '.join(sorted(typing_imports))}\n"

        # Combine all code
        code = f'''"""Auto-generated MCP server from package '{pkg_metadata.name}'.

Generated by auto-mcp.
Modules analyzed: {pkg_metadata.module_count}
Methods exposed: {len(tools)} tools, {len(resources)} resources, {len(prompts)} prompts
"""

{typing_import_line}from mcp.server.fastmcp import FastMCP

{imports_code}

# Create MCP server
mcp = FastMCP(name="{self.config.server_name}")

# Tools
{tools_code}
{resources_code}
{prompts_code}

if __name__ == "__main__":
    mcp.run()
'''

        return code

    async def _generate_tool(
        self,
        method: MethodMetadata,
        module: ModuleType,
        context: str | None,
    ) -> GeneratedTool | None:
        """Generate a tool from method metadata.

        Args:
            method: The method metadata
            module: The source module
            context: Optional context for LLM

        Returns:
            Generated tool or None if generation failed
        """
        # Get the actual function
        func = self._get_function(method, module)
        if func is None:
            return None

        # Determine tool name
        tool_meta = method.mcp_metadata.get("tool_name")
        name = tool_meta if tool_meta else method.name

        # Get description
        description = await self._get_tool_description(method, context)

        # Get parameter descriptions
        param_descriptions = await self._get_parameter_descriptions(method)

        return GeneratedTool(
            name=name,
            description=description,
            function=func,
            metadata=method,
            parameter_descriptions=param_descriptions,
        )

    async def _generate_resource(
        self,
        method: MethodMetadata,
        module: ModuleType,
        context: str | None,
    ) -> GeneratedResource | None:
        """Generate a resource from method metadata.

        Args:
            method: The method metadata
            module: The source module
            context: Optional context for LLM

        Returns:
            Generated resource or None if generation failed
        """
        func = self._get_function(method, module)
        if func is None:
            return None

        # Get resource metadata
        resource_meta = method.mcp_metadata
        uri = resource_meta.get("resource_uri", f"auto://{method.name}")
        name = resource_meta.get("resource_name") or method.name
        mime_type = resource_meta.get("resource_mime_type")

        # Get description
        custom_desc = resource_meta.get("resource_description")
        if custom_desc:
            description = custom_desc
        else:
            description = await self._get_resource_description(method, uri, context)

        return GeneratedResource(
            name=name,
            uri=uri,
            description=description,
            function=func,
            metadata=method,
            mime_type=mime_type,
        )

    async def _generate_prompt(
        self,
        method: MethodMetadata,
        module: ModuleType,
        context: str | None,
    ) -> GeneratedPrompt | None:
        """Generate a prompt from method metadata.

        Args:
            method: The method metadata
            module: The source module
            context: Optional context for LLM

        Returns:
            Generated prompt or None if generation failed
        """
        func = self._get_function(method, module)
        if func is None:
            return None

        # Get prompt metadata
        prompt_meta = method.mcp_metadata
        name = prompt_meta.get("prompt_name") or method.name

        # Get description
        custom_desc = prompt_meta.get("prompt_description")
        if custom_desc:
            description = custom_desc
        else:
            description = await self._get_prompt_description(method, context)

        return GeneratedPrompt(
            name=name,
            description=description,
            function=func,
            metadata=method,
        )

    def _get_function(
        self, method: MethodMetadata, module: ModuleType
    ) -> Any | None:
        """Get the actual function from a module.

        Args:
            method: The method metadata
            module: The source module

        Returns:
            The function or None if not found
        """
        if method.is_method:
            # For class methods, we need to get the class first
            parts = method.qualified_name.split(".")
            if len(parts) >= 2:
                class_name = parts[0]
                method_name = parts[1]
                cls = getattr(module, class_name, None)
                if cls:
                    return getattr(cls, method_name, None)
            return None
        else:
            return getattr(module, method.name, None)

    async def _get_tool_description(
        self,
        method: MethodMetadata,
        context: str | None,
    ) -> str:
        """Get description for a tool.

        Args:
            method: The method metadata
            context: Optional context for LLM

        Returns:
            The tool description
        """
        # Check for custom description in decorator
        custom_desc = method.mcp_metadata.get("tool_description")
        if custom_desc:
            return str(custom_desc)

        # Check cache
        if self.config.use_cache:
            cached = self.cache.get(method, cache_type="tool")
            if cached:
                return cached

        # Generate with LLM if available
        if self.config.use_llm and self.llm:
            try:
                description: str = await self.llm.generate_tool_description(method, context)
                if self.config.use_cache:
                    self.cache.set(method, description, cache_type="tool")
                return description
            except Exception:
                pass

        # Fallback to docstring-based description
        return get_fallback_tool_description(method.name, method.docstring)

    async def _get_resource_description(
        self,
        method: MethodMetadata,
        uri: str,
        context: str | None,
    ) -> str:
        """Get description for a resource.

        Args:
            method: The method metadata
            uri: The resource URI template
            context: Optional context for LLM

        Returns:
            The resource description
        """
        # Check cache
        if self.config.use_cache:
            cached = self.cache.get(method, cache_type="resource")
            if cached:
                return cached

        # Generate with LLM if available
        if self.config.use_llm and self.llm:
            try:
                description: str = await self.llm.generate_resource_description(method, uri)
                if self.config.use_cache:
                    self.cache.set(method, description, cache_type="resource")
                return description
            except Exception:
                pass

        return get_fallback_resource_description(method.name, method.docstring)

    async def _get_prompt_description(
        self,
        method: MethodMetadata,
        context: str | None,
    ) -> str:
        """Get description for a prompt.

        Args:
            method: The method metadata
            context: Optional context for LLM

        Returns:
            The prompt description
        """
        # Check cache
        if self.config.use_cache:
            cached = self.cache.get(method, cache_type="prompt")
            if cached:
                return cached

        # Generate with LLM if available
        if self.config.use_llm and self.llm:
            try:
                description: str = await self.llm.generate_prompt_template(method)
                if self.config.use_cache:
                    self.cache.set(method, description, cache_type="prompt")
                return description
            except Exception:
                pass

        return get_fallback_prompt_description(method.name, method.docstring)

    async def _get_parameter_descriptions(
        self,
        method: MethodMetadata,
    ) -> dict[str, str]:
        """Get descriptions for method parameters.

        Args:
            method: The method metadata

        Returns:
            Dictionary of parameter names to descriptions
        """
        if not method.parameters:
            return {}

        # Check cache
        if self.config.use_cache:
            cached = self.cache.get_parameter_descriptions(method)
            if cached:
                return cached

        # Generate with LLM if available
        if self.config.use_llm and self.llm:
            try:
                descriptions: dict[str, str] = await self.llm.generate_parameter_descriptions(
                    method
                )
                if self.config.use_cache:
                    self.cache.set_parameter_descriptions(method, descriptions)
                return descriptions
            except Exception:
                pass

        # Fallback to empty descriptions
        return {}

    def create_server(
        self,
        modules: list[ModuleType],
        context: str | None = None,
    ) -> FastMCP:
        """Create an in-memory FastMCP server from modules.

        Args:
            modules: List of Python modules to expose
            context: Optional context for LLM description generation

        Returns:
            Configured FastMCP server instance
        """
        # Run async analysis synchronously
        tools, resources, prompts = asyncio.run(
            self.analyze_and_generate(modules, context)
        )

        # Create FastMCP server
        mcp = FastMCP(
            name=self.config.server_name,
        )

        # Register session hooks and tools if sessions are enabled
        if self.config.enable_sessions and self.session_manager:
            self._register_session_hooks(modules)
            self._register_session_tools(mcp)

        # Register tools
        for tool in tools:
            self._register_tool(mcp, tool)

        # Register resources
        if self.config.generate_resources:
            for resource in resources:
                self._register_resource(mcp, resource)

        # Register prompts
        if self.config.generate_prompts:
            for prompt in prompts:
                self._register_prompt(mcp, prompt)

        return mcp

    def _register_session_hooks(self, modules: list[ModuleType]) -> None:
        """Register session init/cleanup hooks from modules.

        Args:
            modules: List of modules to scan for hooks
        """
        if not self.session_manager:
            return

        from auto_mcp.decorators import MCP_SESSION_CLEANUP_MARKER, MCP_SESSION_INIT_MARKER

        for module in modules:
            # Scan module for hook functions
            for name in dir(module):
                if name.startswith("_"):
                    continue

                obj = getattr(module, name, None)
                if not callable(obj):
                    continue

                # Check for init hook
                if hasattr(obj, MCP_SESSION_INIT_MARKER):
                    meta = getattr(obj, MCP_SESSION_INIT_MARKER, {})
                    order = meta.get("order", 0)
                    self.session_manager.register_init_hook(obj, order=order)

                # Check for cleanup hook
                if hasattr(obj, MCP_SESSION_CLEANUP_MARKER):
                    meta = getattr(obj, MCP_SESSION_CLEANUP_MARKER, {})
                    order = meta.get("order", 0)
                    self.session_manager.register_cleanup_hook(obj, order=order)

    def _register_session_tools(self, mcp: FastMCP) -> None:
        """Register create_session and close_session tools.

        Args:
            mcp: The FastMCP server
        """
        if not self.session_manager:
            return

        session_manager = self.session_manager

        @mcp.tool(
            name="create_session",
            description="Create a new session. Returns session_id to use in subsequent calls.",
        )
        async def create_session(
            metadata: dict[str, Any] | None = None,
            ttl: int | None = None,
        ) -> dict[str, Any]:
            """Create a new session.

            Args:
                metadata: Optional metadata to store with the session
                ttl: Optional TTL override in seconds

            Returns:
                Dictionary with session_id and creation info
            """
            session = await session_manager.create_session(metadata=metadata, ttl=ttl)
            return {
                "session_id": session.session_id,
                "created_at": session.created_at,
                "expires_in": ttl or session_manager.config.default_ttl,
            }

        @mcp.tool(
            name="close_session",
            description="Close an existing session and run cleanup hooks.",
        )
        async def close_session(session_id: str) -> dict[str, Any]:
            """Close an existing session.

            Args:
                session_id: The session ID to close

            Returns:
                Dictionary with success status
            """
            success = await session_manager.close_session(session_id)
            return {"success": success, "session_id": session_id}

    def _register_tool(self, mcp: FastMCP, tool: GeneratedTool) -> None:
        """Register a tool with the MCP server.

        Args:
            mcp: The FastMCP server
            tool: The generated tool
        """
        func = tool.function

        # Check if this tool needs session injection
        needs_session = tool.metadata.needs_session
        session_param = tool.metadata.session_param_name

        # Optionally wrap with type transformations or session injection
        if self.config.enable_type_transforms or (needs_session and self.session_manager):
            wrapper = FunctionWrapper(
                func,
                registry=self.type_registry,
                store=self.object_store,
                session_manager=self.session_manager if needs_session else None,
                session_param_name=session_param if needs_session else None,
            )
            # Use the wrapper's call method for MCP
            func = wrapper.call

        # Use the decorator to register the tool
        mcp.tool(name=tool.name, description=tool.description)(func)

    def _register_resource(self, mcp: FastMCP, resource: GeneratedResource) -> None:
        """Register a resource with the MCP server.

        Args:
            mcp: The FastMCP server
            resource: The generated resource
        """
        mcp.resource(uri=resource.uri, name=resource.name, description=resource.description)(
            resource.function
        )

    def _register_prompt(self, mcp: FastMCP, prompt: GeneratedPrompt) -> None:
        """Register a prompt with the MCP server.

        Args:
            mcp: The FastMCP server
            prompt: The generated prompt
        """
        mcp.prompt(name=prompt.name, description=prompt.description)(prompt.function)

    def generate_standalone(
        self,
        modules: list[ModuleType],
        output_path: Path | str,
        context: str | None = None,
    ) -> Path:
        """Generate a standalone MCP server Python file.

        Args:
            modules: List of Python modules to expose
            output_path: Path for the generated file
            context: Optional context for LLM description generation

        Returns:
            Path to the generated file
        """
        output_path = Path(output_path)

        # Run async analysis
        tools, resources, prompts = asyncio.run(
            self.analyze_and_generate(modules, context)
        )

        # Generate code
        code = self._generate_standalone_code(modules, tools, resources, prompts)

        # Write file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(code)

        return output_path

    def _generate_standalone_code(
        self,
        modules: list[ModuleType],
        tools: list[GeneratedTool],
        resources: list[GeneratedResource],
        prompts: list[GeneratedPrompt],
    ) -> str:
        """Generate standalone server code.

        Args:
            modules: Source modules
            tools: Generated tools
            resources: Generated resources
            prompts: Generated prompts

        Returns:
            The generated Python code
        """
        # Build imports
        module_imports = []
        for module in modules:
            module_imports.append(f"import {module.__name__}")

        imports_code = "\n".join(module_imports)

        # Build tool registrations
        tool_code = []
        for tool in tools:
            module_name = tool.metadata.module_name
            func_name = tool.metadata.qualified_name
            safe_name = tool.name.replace(".", "_").replace("-", "_")

            # Escape description for string
            desc = self._escape_docstring(tool.description)

            # Generate proper signature with named parameters
            sig_params, call_args = self._generate_function_signature(tool.metadata)

            tool_code.append(f'''
@mcp.tool(name="{tool.name}")
def {safe_name}({sig_params}):
    """{desc}"""
    return {module_name}.{func_name}({call_args})
''')

        tools_code = "\n".join(tool_code)

        # Build resource registrations
        resource_code = []
        for resource in resources:
            module_name = resource.metadata.module_name
            func_name = resource.metadata.qualified_name
            desc = self._escape_docstring(resource.description)
            safe_name = resource.name.replace(".", "_").replace("-", "_")

            # Generate proper signature
            sig_params, call_args = self._generate_function_signature(resource.metadata)

            resource_code.append(f'''
@mcp.resource(uri="{resource.uri}", name="{resource.name}")
def resource_{safe_name}({sig_params}):
    """{desc}"""
    return {module_name}.{func_name}({call_args})
''')

        resources_code = "\n".join(resource_code) if resources else ""

        # Build prompt registrations
        prompt_code = []
        for prompt in prompts:
            module_name = prompt.metadata.module_name
            func_name = prompt.metadata.qualified_name
            desc = self._escape_docstring(prompt.description)
            safe_name = prompt.name.replace(".", "_").replace("-", "_")

            # Generate proper signature
            sig_params, call_args = self._generate_function_signature(prompt.metadata)

            prompt_code.append(f'''
@mcp.prompt(name="{prompt.name}")
def prompt_{safe_name}({sig_params}):
    """{desc}"""
    return {module_name}.{func_name}({call_args})
''')

        prompts_code = "\n".join(prompt_code) if prompts else ""

        # Collect typing imports needed from signatures
        typing_imports = self._collect_typing_imports(tools, resources, prompts)
        typing_import_line = ""
        if typing_imports:
            typing_import_line = f"from typing import {', '.join(sorted(typing_imports))}\n"

        # Combine all code
        code = f'''"""Auto-generated MCP server.

Generated by auto-mcp.
"""

{typing_import_line}from mcp.server.fastmcp import FastMCP

{imports_code}

# Create MCP server
mcp = FastMCP(name="{self.config.server_name}")

# Tools
{tools_code}
{resources_code}
{prompts_code}

if __name__ == "__main__":
    mcp.run()
'''

        return code

    def generate_package(
        self,
        modules: list[ModuleType],
        output_dir: Path | str,
        package_name: str,
        context: str | None = None,
    ) -> Path:
        """Generate a complete MCP server package.

        Args:
            modules: List of Python modules to expose
            output_dir: Directory for the generated package
            package_name: Name for the package
            context: Optional context for LLM description generation

        Returns:
            Path to the generated package directory
        """
        output_dir = Path(output_dir)
        package_dir = output_dir / package_name

        # Create package structure
        package_dir.mkdir(parents=True, exist_ok=True)
        src_dir = package_dir / "src" / package_name.replace("-", "_")
        src_dir.mkdir(parents=True, exist_ok=True)

        # Generate server code
        tools, resources, prompts = asyncio.run(
            self.analyze_and_generate(modules, context)
        )

        server_code = self._generate_standalone_code(modules, tools, resources, prompts)
        (src_dir / "server.py").write_text(server_code)

        # Generate __init__.py
        init_code = f'''"""Auto-generated MCP server package."""

from {package_name.replace("-", "_")}.server import mcp

__all__ = ["mcp"]
'''
        (src_dir / "__init__.py").write_text(init_code)

        # Generate pyproject.toml
        pyproject = self._generate_pyproject(package_name, modules)
        (package_dir / "pyproject.toml").write_text(pyproject)

        return package_dir

    def _generate_pyproject(
        self,
        package_name: str,
        modules: list[ModuleType],
    ) -> str:
        """Generate pyproject.toml for the package.

        Args:
            package_name: The package name
            modules: Source modules (for metadata)

        Returns:
            The pyproject.toml content
        """
        pkg_name_safe = package_name.replace("-", "_")

        return f'''[project]
name = "{package_name}"
version = "0.1.0"
description = "{self.config.server_description}"
requires-python = ">=3.10"
dependencies = [
    "mcp>=1.0",
]

[project.scripts]
{package_name} = "{pkg_name_safe}.server:mcp.run"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/{pkg_name_safe}"]
'''
