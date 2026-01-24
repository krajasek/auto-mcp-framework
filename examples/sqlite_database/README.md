# SQLite Database Example

Demonstrates creating an MCP server for SQLite database operations using a manifest file.

## Files

- `manifest.yaml` - YAML manifest defining which sqlite3 functions to expose
- `server.py` - Generated MCP server (created from manifest)
- `run_server.py` - Helper script to run the server

## User Workflow

This example shows the typical workflow for creating an MCP server:

### Step 1: Create a Manifest

The `manifest.yaml` file defines which functions to expose:

```yaml
server_name: sqlite-server
auto_include_dependencies: true

tools:
  - function: connect
    description: "Open a connection to an SQLite database."

  - function: Connection.execute
    name: connection_execute
    description: "Execute a single SQL statement."

  - function: Cursor.fetchall
    name: cursor_fetchall
    description: "Fetch all remaining rows."
  # ... more tools
```

### Step 2: Generate the Server

```bash
auto-mcp-tool generate sqlite3 --manifest manifest.yaml -o server.py
```

This creates `server.py` with all the selected tools.

### Step 3: Run the Server

```bash
python server.py
```

Or use the helper script:

```bash
python run_server.py
```

## Claude Desktop Integration

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "sqlite": {
      "command": "python",
      "args": ["/path/to/examples/sqlite_database/server.py"]
    }
  }
}
```

## Available Tools

| Tool | Description |
|------|-------------|
| `connect` | Open a connection to an SQLite database |
| `connection_close` | Close the database connection |
| `connection_commit` | Commit the current transaction |
| `connection_rollback` | Roll back changes since last commit |
| `connection_execute` | Execute a single SQL statement |
| `connection_executemany` | Execute SQL for each item in a sequence |
| `connection_executescript` | Execute multiple SQL statements |
| `connection_cursor` | Create a new Cursor object |
| `cursor_execute` | Execute SQL on a cursor |
| `cursor_executemany` | Execute SQL for each item in a sequence |
| `cursor_fetchone` | Fetch the next row |
| `cursor_fetchall` | Fetch all remaining rows |
| `cursor_fetchmany` | Fetch up to n rows |
| `cursor_close` | Close the cursor |

## How Handle-Based Storage Works

Since sqlite3 returns non-serializable objects (Connection, Cursor), the generated server uses handles:

```python
# 1. Connect returns a handle (string reference)
handle = connect(":memory:")  # Returns "Connection_1"

# 2. Use handle for subsequent operations
cursor = connection_execute(handle, "CREATE TABLE users (id INTEGER, name TEXT)")
# Returns "Cursor_1"

# 3. Fetch results using cursor handle
rows = cursor_fetchall(cursor)  # Returns actual data: [(1, "Alice"), (2, "Bob")]

# 4. Clean up
connection_close(handle)
```

## Example Interactions

```
User: Create an in-memory database and make a users table
Assistant: [calls connect(":memory:")]
-> "Connection_1"
Assistant: [calls connection_execute("Connection_1", "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")]
-> "Cursor_1"

User: Add a user named Alice
Assistant: [calls connection_execute("Connection_1", "INSERT INTO users (name, email) VALUES (?, ?)", ["Alice", "alice@example.com"])]
-> "Cursor_2"
Assistant: [calls connection_commit("Connection_1")]
-> null

User: Show all users
Assistant: [calls connection_execute("Connection_1", "SELECT * FROM users")]
-> "Cursor_3"
Assistant: [calls cursor_fetchall("Cursor_3")]
-> [[1, "Alice", "alice@example.com"]]
```

## Regenerating the Server

If you modify `manifest.yaml`, regenerate the server:

```bash
auto-mcp-tool generate sqlite3 --manifest manifest.yaml -o server.py
```

## Deployment Notes

The handle-based storage requires a **single-process server**. See the main README's "Deployment Considerations for Handle-Based Storage" section for details.
