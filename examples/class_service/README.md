# Class Service Example

Demonstrates how to use decorators (`@mcp_tool`, `@mcp_exclude`) with class-based services.

## Files

- `todo_service.py` - A todo list service using decorators
- `run_server.py` - Script to run the MCP server programmatically

## Usage

### Option 1: CLI (Recommended)

```bash
# Generate a standalone server file
auto-mcp-tool generate examples/class_service/todo_service.py -o todo_server.py --no-llm

# Run the server
python todo_server.py

# Or serve directly without generating a file
auto-mcp-tool serve examples/class_service/todo_service.py --name todo-server
```

### Option 2: Python API

```bash
python examples/class_service/run_server.py
```

### Option 3: Claude Desktop Integration

Add to your Claude Desktop config:

```json
{
  "mcpServers": {
    "todo-server": {
      "command": "auto-mcp-tool",
      "args": ["serve", "examples/class_service/todo_service.py", "--no-llm"]
    }
  }
}
```

## Available Tools

| Tool | Description |
|------|-------------|
| `create_todo` | Create a new todo item |
| `get_todo` | Get a todo item by ID |
| `list_todos` | List all todo items with optional filtering |
| `update_todo_status` | Update the status of a todo item |
| `delete_todo` | Delete a todo item |
| `search_todos` | Search todos by title or description |
| `get_stats` | Get statistics about the todo list |

## Key Features Demonstrated

- **`@mcp_tool` decorator**: Explicitly mark methods as MCP tools with custom names/descriptions
- **`@mcp_exclude` decorator**: Exclude helper methods from exposure
- **Class instances**: Service methods work with shared state
- **Literal types**: Constrained parameter values (priority: low/medium/high)

## Decorator Usage

```python
from auto_mcp import mcp_tool, mcp_exclude

class TodoService:
    @mcp_tool(name="create_todo", description="Create a new todo item")
    def create(self, title: str, priority: Literal["low", "medium", "high"] = "medium"):
        ...

    @mcp_exclude  # This helper won't be exposed
    def _todo_to_dict(self, todo):
        ...
```

## Example Interactions

```
User: Create a todo to buy groceries with high priority
Assistant: [calls create_todo("Buy groceries", priority="high")]
-> Created todo with ID: abc123

User: List all pending high priority todos
Assistant: [calls list_todos(status="pending", priority="high")]
-> [{ id: "abc123", title: "Buy groceries", status: "pending", priority: "high" }]

User: Mark todo abc123 as completed
Assistant: [calls update_todo_status("abc123", "completed")]
-> Updated successfully
```
