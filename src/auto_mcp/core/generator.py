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

if TYPE_CHECKING:
    from auto_mcp.llm.base import LLMProvider


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
    ) -> None:
        """Initialize the generator.

        Args:
            llm: LLM provider for description generation (optional)
            cache: Cache for storing generated descriptions (optional)
            config: Generator configuration (uses defaults if not provided)
        """
        self.llm = llm
        self.cache = cache or PromptCache()
        self.config = config or GeneratorConfig()
        self.analyzer = ModuleAnalyzer(include_private=self.config.include_private)
        self.package_analyzer = PackageAnalyzer(
            include_private=self.config.include_private,
            max_depth=self.config.max_depth,
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
        # Run async analysis synchronously
        tools, resources, prompts = asyncio.run(
            self.analyze_and_generate_from_package(package, context)
        )

        # Create FastMCP server
        mcp = FastMCP(
            name=self.config.server_name,
        )

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
            desc = tool.description.replace('"""', '\\"\\"\\"')

            tool_code.append(f'''
@mcp.tool(name="{tool.name}")
def {tool.name.replace(".", "_")}(*args, **kwargs):
    """{desc}"""
    return {module_name}.{func_name}(*args, **kwargs)
''')

        tools_code = "\n".join(tool_code)

        # Build resource registrations
        resource_code = []
        for resource in resources:
            module_name = resource.metadata.module_name
            func_name = resource.metadata.qualified_name
            desc = resource.description.replace('"""', '\\"\\"\\"')

            resource_code.append(f'''
@mcp.resource(uri="{resource.uri}", name="{resource.name}")
def resource_{resource.name.replace(".", "_")}(*args, **kwargs):
    """{desc}"""
    return {module_name}.{func_name}(*args, **kwargs)
''')

        resources_code = "\n".join(resource_code) if resources else ""

        # Build prompt registrations
        prompt_code = []
        for prompt in prompts:
            module_name = prompt.metadata.module_name
            func_name = prompt.metadata.qualified_name
            desc = prompt.description.replace('"""', '\\"\\"\\"')

            prompt_code.append(f'''
@mcp.prompt(name="{prompt.name}")
def prompt_{prompt.name.replace(".", "_")}(*args, **kwargs):
    """{desc}"""
    return {module_name}.{func_name}(*args, **kwargs)
''')

        prompts_code = "\n".join(prompt_code) if prompts else ""

        # Combine all code
        code = f'''"""Auto-generated MCP server from package '{pkg_metadata.name}'.

Generated by auto-mcp.
Modules analyzed: {pkg_metadata.module_count}
Methods exposed: {len(tools)} tools, {len(resources)} resources, {len(prompts)} prompts
"""

from mcp.server.fastmcp import FastMCP

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

    def _register_tool(self, mcp: FastMCP, tool: GeneratedTool) -> None:
        """Register a tool with the MCP server.

        Args:
            mcp: The FastMCP server
            tool: The generated tool
        """
        # Use the decorator to register the tool
        mcp.tool(name=tool.name, description=tool.description)(tool.function)

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

            # Escape description for string
            desc = tool.description.replace('"""', '\\"\\"\\"')

            tool_code.append(f'''
@mcp.tool(name="{tool.name}")
def {tool.name}(*args, **kwargs):
    """{desc}"""
    return {module_name}.{func_name}(*args, **kwargs)
''')

        tools_code = "\n".join(tool_code)

        # Build resource registrations
        resource_code = []
        for resource in resources:
            module_name = resource.metadata.module_name
            func_name = resource.metadata.qualified_name
            desc = resource.description.replace('"""', '\\"\\"\\"')

            resource_code.append(f'''
@mcp.resource(uri="{resource.uri}", name="{resource.name}")
def resource_{resource.name}(*args, **kwargs):
    """{desc}"""
    return {module_name}.{func_name}(*args, **kwargs)
''')

        resources_code = "\n".join(resource_code) if resources else ""

        # Build prompt registrations
        prompt_code = []
        for prompt in prompts:
            module_name = prompt.metadata.module_name
            func_name = prompt.metadata.qualified_name
            desc = prompt.description.replace('"""', '\\"\\"\\"')

            prompt_code.append(f'''
@mcp.prompt(name="{prompt.name}")
def prompt_{prompt.name}(*args, **kwargs):
    """{desc}"""
    return {module_name}.{func_name}(*args, **kwargs)
''')

        prompts_code = "\n".join(prompt_code) if prompts else ""

        # Combine all code
        code = f'''"""Auto-generated MCP server.

Generated by auto-mcp.
"""

from mcp.server.fastmcp import FastMCP

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
