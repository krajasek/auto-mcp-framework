"""Prompt templates for LLM-based description generation."""

# System prompt for all description generation tasks
SYSTEM_PROMPT = """You are a technical documentation expert. Your task is to generate \
clear, concise descriptions for Python functions that will be exposed as MCP (Model \
Context Protocol) tools.

Guidelines:
- Be concise but informative (1-2 sentences max)
- Focus on what the function does, not how it does it
- Use active voice (e.g., "Adds two numbers" not "Two numbers are added")
- Don't include implementation details
- Don't mention the function name in the description
- Avoid phrases like "This function..." or "This method..."
"""

# Template for generating tool descriptions
TOOL_DESCRIPTION_PROMPT = """Generate a concise description for this Python function \
that will be exposed as an MCP tool.

Function: {function_name}
Signature: {signature}
Docstring: {docstring}
Source code (truncated):
```python
{source_code}
```

Additional context: {context}

Respond with ONLY the description text, nothing else. Keep it under 100 words."""

# Template for generating parameter descriptions
PARAMETER_DESCRIPTION_PROMPT = """Generate brief descriptions for each parameter of \
this function.

Function: {function_name}
Docstring: {docstring}
Parameters:
{parameters}

Respond with one line per parameter in this exact format:
- parameter_name: Brief description of what this parameter is for

Only include the parameters listed above, nothing else."""

# Template for generating resource descriptions
RESOURCE_DESCRIPTION_PROMPT = """Generate a description for this MCP resource.

Function: {function_name}
URI Template: {uri_template}
Docstring: {docstring}
Returns: {return_type}

This function serves as an MCP resource that provides data via the URI template shown.

Respond with ONLY the description text (1-2 sentences), nothing else."""

# Template for generating MCP prompt descriptions
PROMPT_TEMPLATE_PROMPT = """Generate a description for this MCP prompt template.

Function: {function_name}
Docstring: {docstring}
Arguments: {parameters}

This function generates a prompt template for use with language models.

Respond with ONLY the description text (1-2 sentences), nothing else."""

# Fallback descriptions when LLM is unavailable
FALLBACK_DESCRIPTIONS = {
    "tool": "Executes the {name} operation.",
    "resource": "Provides access to {name} data.",
    "prompt": "Generates a prompt for {name}.",
    "parameter": "The {name} parameter.",
}


def get_fallback_tool_description(name: str, docstring: str | None) -> str:
    """Get a fallback tool description when LLM is unavailable.

    Args:
        name: The function name
        docstring: The function's docstring, if any

    Returns:
        A basic description string
    """
    if docstring:
        # Use first sentence of docstring
        first_sentence = docstring.split(".")[0].strip()
        if first_sentence:
            return first_sentence + "."

    return FALLBACK_DESCRIPTIONS["tool"].format(name=name)


def get_fallback_resource_description(name: str, docstring: str | None) -> str:
    """Get a fallback resource description when LLM is unavailable.

    Args:
        name: The function name
        docstring: The function's docstring, if any

    Returns:
        A basic description string
    """
    if docstring:
        first_sentence = docstring.split(".")[0].strip()
        if first_sentence:
            return first_sentence + "."

    return FALLBACK_DESCRIPTIONS["resource"].format(name=name)


def get_fallback_prompt_description(name: str, docstring: str | None) -> str:
    """Get a fallback prompt description when LLM is unavailable.

    Args:
        name: The function name
        docstring: The function's docstring, if any

    Returns:
        A basic description string
    """
    if docstring:
        first_sentence = docstring.split(".")[0].strip()
        if first_sentence:
            return first_sentence + "."

    return FALLBACK_DESCRIPTIONS["prompt"].format(name=name)


def get_fallback_parameter_description(name: str) -> str:
    """Get a fallback parameter description when LLM is unavailable.

    Args:
        name: The parameter name

    Returns:
        A basic description string
    """
    # Try to make something readable from the parameter name
    readable = name.replace("_", " ").strip()
    return f"The {readable} value."
