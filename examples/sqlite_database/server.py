"""Auto-generated MCP server from manifest.

Module: sqlite3
Server: sqlite-server
"""

from typing import Any

from mcp.server.fastmcp import FastMCP

import sqlite3

# Object store for handle-based types
_object_store: dict[str, Any] = {}
_handle_counter: int = 0


def _store_object(obj: Any, type_name: str) -> str:
    """Store an object and return a handle string."""
    global _handle_counter
    _handle_counter += 1
    handle = f"{type_name}_{_handle_counter}"
    _object_store[handle] = obj
    return handle


def _get_object(handle: str) -> Any:
    """Retrieve an object by its handle."""
    obj = _object_store.get(handle)
    if obj is None:
        raise ValueError(f"Invalid or expired handle: {handle}")
    return obj


mcp = FastMCP(name="sqlite-server")

@mcp.tool(name="connect")
def connect(database: Any, timeout: Any = 5.0, detect_types: Any = 0, isolation_level: Any = '', check_same_thread: Any = True, factory: Any = None, cached_statements: Any = 128, uri: Any = False) -> str:
    """Open a connection to an SQLite database. Use ':memory:' for an in-memory database."""
    _kwargs = {}
    _kwargs['database'] = database
    _kwargs['timeout'] = timeout
    _kwargs['detect_types'] = detect_types
    _kwargs['isolation_level'] = isolation_level
    _kwargs['check_same_thread'] = check_same_thread
    if factory is not None:
        _kwargs['factory'] = factory
    _kwargs['cached_statements'] = cached_statements
    _kwargs['uri'] = uri
    result = sqlite3.connect(**_kwargs)
    return _store_object(result, "Connection")

@mcp.tool(name="connection_close")
def connection_close(connection: str) -> Any:
    """Close the database connection."""
    _instance = _get_object(connection)
    return _instance.close()

@mcp.tool(name="connection_commit")
def connection_commit(connection: str) -> Any:
    """Commit the current transaction to the database."""
    _instance = _get_object(connection)
    return _instance.commit()

@mcp.tool(name="connection_rollback")
def connection_rollback(connection: str) -> Any:
    """Roll back any changes since the last commit."""
    _instance = _get_object(connection)
    return _instance.rollback()

@mcp.tool(name="connection_execute")
def connection_execute(connection: str, sql: Any, parameters: Any = None) -> str:
    """Execute a single SQL statement. Returns a Cursor for fetching results."""
    _instance = _get_object(connection)
    _args = []
    _args.append(sql)
    if parameters is not None:
        _args.append(parameters)
    result = _instance.execute(*_args)
    return _store_object(result, "Cursor")

@mcp.tool(name="connection_executemany")
def connection_executemany(connection: str, sql: Any, parameters: Any) -> str:
    """Execute an SQL statement for each item in a sequence of parameters."""
    _instance = _get_object(connection)
    result = _instance.executemany(sql=sql, parameters=parameters)
    return _store_object(result, "Cursor")

@mcp.tool(name="connection_executescript")
def connection_executescript(connection: str, sql_script: Any) -> str:
    """Execute multiple SQL statements in a single call (for scripts)."""
    _instance = _get_object(connection)
    result = _instance.executescript(sql_script=sql_script)
    return _store_object(result, "Cursor")

@mcp.tool(name="connection_cursor")
def connection_cursor(connection: str, factory: Any = None) -> str:
    """Create a new Cursor object for executing queries."""
    _instance = _get_object(connection)
    _args = []
    if factory is not None:
        _args.append(factory)
    result = _instance.cursor(*_args)
    return _store_object(result, "Cursor")

@mcp.tool(name="cursor_execute")
def cursor_execute(cursor: str, sql: Any, parameters: Any = ()) -> str:
    """Execute an SQL statement on this cursor."""
    _instance = _get_object(cursor)
    result = _instance.execute(sql=sql, parameters=parameters)
    return _store_object(result, "Cursor")

@mcp.tool(name="cursor_executemany")
def cursor_executemany(cursor: str, sql: Any, seq_of_parameters: Any) -> str:
    """Execute an SQL statement for each item in a sequence."""
    _instance = _get_object(cursor)
    result = _instance.executemany(sql=sql, seq_of_parameters=seq_of_parameters)
    return _store_object(result, "Cursor")

@mcp.tool(name="cursor_fetchone")
def cursor_fetchone(cursor: str) -> Any:
    """Fetch the next row from the query result, or None if no more rows."""
    _instance = _get_object(cursor)
    return _instance.fetchone()

@mcp.tool(name="cursor_fetchall")
def cursor_fetchall(cursor: str) -> Any:
    """Fetch all remaining rows from the query result as a list."""
    _instance = _get_object(cursor)
    return _instance.fetchall()

@mcp.tool(name="cursor_fetchmany")
def cursor_fetchmany(cursor: str, size: Any = 1) -> Any:
    """Fetch up to n rows from the query result."""
    _instance = _get_object(cursor)
    return _instance.fetchmany(size=size)

@mcp.tool(name="cursor_close")
def cursor_close(cursor: str) -> Any:
    """Close the cursor."""
    _instance = _get_object(cursor)
    return _instance.close()

@mcp.tool(name="connection_iterdump")
def connection_iterdump(connection: str) -> Any:
    """Return an iterator of SQL statements to recreate the database."""
    _instance = _get_object(connection)
    return _instance.iterdump()

@mcp.tool(name="connection_backup")
def connection_backup(connection: str, target: Any, pages: Any = -1, progress: Any = None, name: Any = 'main', sleep: Any = 0.25) -> Any:
    """Create a backup of the database to another connection."""
    _instance = _get_object(connection)
    _args = []
    _args.append(target)
    _args.append(pages)
    if progress is not None:
        _args.append(progress)
    _args.append(name)
    _args.append(sleep)
    return _instance.backup(*_args)


if __name__ == "__main__":
    mcp.run()