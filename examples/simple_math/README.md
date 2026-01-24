# Simple Math Example

A basic example demonstrating how to expose Python functions as MCP tools.

## Files

- `math_utils.py` - Module containing math functions (add, subtract, multiply, etc.)
- `run_server.py` - Script to run the MCP server programmatically

## Usage

### Option 1: CLI (Recommended)

```bash
# Generate a standalone server file
auto-mcp-tool generate examples/simple_math/math_utils.py -o math_server.py --no-llm

# Run the server
python math_server.py

# Or serve directly without generating a file
auto-mcp-tool serve examples/simple_math/math_utils.py --name math-server
```

### Option 2: Python API

```bash
python examples/simple_math/run_server.py
```

### Option 3: Claude Desktop Integration

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "math-server": {
      "command": "auto-mcp-tool",
      "args": ["serve", "examples/simple_math/math_utils.py", "--no-llm"]
    }
  }
}
```

## Available Tools

| Tool | Description |
|------|-------------|
| `add` | Add two numbers together |
| `subtract` | Subtract the second number from the first |
| `multiply` | Multiply two numbers together |
| `divide` | Divide the first number by the second |
| `power` | Raise a number to a power |
| `factorial` | Calculate the factorial of a non-negative integer |
| `is_prime` | Check if a number is prime |
| `gcd` | Calculate the greatest common divisor of two integers |

## Example Interactions

```
User: What is 15 factorial?
Assistant: [calls factorial(15)] -> 1307674368000

User: Is 97 a prime number?
Assistant: [calls is_prime(97)] -> True

User: What's the GCD of 48 and 18?
Assistant: [calls gcd(48, 18)] -> 6
```
