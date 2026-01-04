"""SQLite database tools for MCP server.

This module provides SQLite database operations as MCP tools,
demonstrating CRUD operations, queries, and schema management.

The module uses an in-memory database by default, but can also
work with file-based databases.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

# Global connection store for managing database connections
_connections: dict[str, sqlite3.Connection] = {}
_default_db = ":memory:"


def connect_database(database: str = ":memory:", name: str = "default") -> str:
    """Connect to a SQLite database.

    Args:
        database: Database path or ":memory:" for in-memory database
        name: Connection name for later reference

    Returns:
        Connection name that was created
    """
    global _connections
    conn = sqlite3.connect(database, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _connections[name] = conn
    return f"Connected to '{database}' as '{name}'"


def disconnect_database(name: str = "default") -> str:
    """Close a database connection.

    Args:
        name: Connection name to close

    Returns:
        Status message
    """
    global _connections
    if name in _connections:
        _connections[name].close()
        del _connections[name]
        return f"Disconnected '{name}'"
    return f"Connection '{name}' not found"


def _get_connection(name: str = "default") -> sqlite3.Connection:
    """Get a database connection by name."""
    global _connections
    if name not in _connections:
        # Auto-connect to memory database
        connect_database(_default_db, name)
    return _connections[name]


def execute_query(
    sql: str,
    parameters: list[Any] | None = None,
    connection: str = "default",
) -> list[dict[str, Any]]:
    """Execute a SQL query and return results.

    Args:
        sql: SQL query to execute
        parameters: Optional list of parameters for parameterized queries
        connection: Connection name to use

    Returns:
        List of result rows as dictionaries
    """
    conn = _get_connection(connection)
    cursor = conn.cursor()

    if parameters:
        cursor.execute(sql, parameters)
    else:
        cursor.execute(sql)

    if cursor.description:
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]

    conn.commit()
    return [{"rows_affected": cursor.rowcount}]


def execute_script(sql_script: str, connection: str = "default") -> str:
    """Execute a SQL script with multiple statements.

    Args:
        sql_script: SQL script with multiple statements
        connection: Connection name to use

    Returns:
        Status message
    """
    conn = _get_connection(connection)
    cursor = conn.cursor()
    cursor.executescript(sql_script)
    conn.commit()
    return "Script executed successfully"


def create_table(
    table_name: str,
    columns: dict[str, str],
    connection: str = "default",
) -> str:
    """Create a new table.

    Args:
        table_name: Name of the table to create
        columns: Dictionary of column names to SQL types
                Example: {"id": "INTEGER PRIMARY KEY", "name": "TEXT NOT NULL"}
        connection: Connection name to use

    Returns:
        Status message
    """
    cols = ", ".join(f"{name} {dtype}" for name, dtype in columns.items())
    sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({cols})"
    execute_query(sql, connection=connection)
    return f"Table '{table_name}' created"


def drop_table(table_name: str, connection: str = "default") -> str:
    """Drop a table.

    Args:
        table_name: Name of the table to drop
        connection: Connection name to use

    Returns:
        Status message
    """
    sql = f"DROP TABLE IF EXISTS {table_name}"
    execute_query(sql, connection=connection)
    return f"Table '{table_name}' dropped"


def list_tables(connection: str = "default") -> list[str]:
    """List all tables in the database.

    Args:
        connection: Connection name to use

    Returns:
        List of table names
    """
    sql = "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    results = execute_query(sql, connection=connection)
    return [row["name"] for row in results]


def describe_table(table_name: str, connection: str = "default") -> list[dict[str, Any]]:
    """Get the schema of a table.

    Args:
        table_name: Name of the table
        connection: Connection name to use

    Returns:
        List of column definitions
    """
    sql = f"PRAGMA table_info({table_name})"
    results = execute_query(sql, connection=connection)
    return [
        {
            "column": row["name"],
            "type": row["type"],
            "nullable": not row["notnull"],
            "default": row["dflt_value"],
            "primary_key": bool(row["pk"]),
        }
        for row in results
    ]


def insert_row(
    table_name: str,
    data: dict[str, Any],
    connection: str = "default",
) -> int:
    """Insert a row into a table.

    Args:
        table_name: Name of the table
        data: Dictionary of column names to values
        connection: Connection name to use

    Returns:
        ID of the inserted row
    """
    columns = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"

    conn = _get_connection(connection)
    cursor = conn.cursor()
    cursor.execute(sql, list(data.values()))
    conn.commit()
    return cursor.lastrowid


def insert_many(
    table_name: str,
    rows: list[dict[str, Any]],
    connection: str = "default",
) -> int:
    """Insert multiple rows into a table.

    Args:
        table_name: Name of the table
        rows: List of dictionaries with column names to values
        connection: Connection name to use

    Returns:
        Number of rows inserted
    """
    if not rows:
        return 0

    columns = ", ".join(rows[0].keys())
    placeholders = ", ".join("?" for _ in rows[0])
    sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"

    conn = _get_connection(connection)
    cursor = conn.cursor()
    cursor.executemany(sql, [list(row.values()) for row in rows])
    conn.commit()
    return cursor.rowcount


def select_all(
    table_name: str,
    limit: int | None = None,
    offset: int = 0,
    connection: str = "default",
) -> list[dict[str, Any]]:
    """Select all rows from a table.

    Args:
        table_name: Name of the table
        limit: Maximum number of rows to return
        offset: Number of rows to skip
        connection: Connection name to use

    Returns:
        List of rows as dictionaries
    """
    sql = f"SELECT * FROM {table_name}"
    if limit:
        sql += f" LIMIT {limit} OFFSET {offset}"
    return execute_query(sql, connection=connection)


def select_where(
    table_name: str,
    conditions: dict[str, Any],
    connection: str = "default",
) -> list[dict[str, Any]]:
    """Select rows matching conditions.

    Args:
        table_name: Name of the table
        conditions: Dictionary of column names to values for WHERE clause
        connection: Connection name to use

    Returns:
        List of matching rows as dictionaries
    """
    where_parts = [f"{col} = ?" for col in conditions.keys()]
    where_clause = " AND ".join(where_parts)
    sql = f"SELECT * FROM {table_name} WHERE {where_clause}"
    return execute_query(sql, list(conditions.values()), connection=connection)


def update_rows(
    table_name: str,
    data: dict[str, Any],
    conditions: dict[str, Any],
    connection: str = "default",
) -> int:
    """Update rows matching conditions.

    Args:
        table_name: Name of the table
        data: Dictionary of column names to new values
        conditions: Dictionary of column names to values for WHERE clause
        connection: Connection name to use

    Returns:
        Number of rows updated
    """
    set_parts = [f"{col} = ?" for col in data.keys()]
    set_clause = ", ".join(set_parts)

    where_parts = [f"{col} = ?" for col in conditions.keys()]
    where_clause = " AND ".join(where_parts)

    sql = f"UPDATE {table_name} SET {set_clause} WHERE {where_clause}"
    parameters = list(data.values()) + list(conditions.values())

    result = execute_query(sql, parameters, connection=connection)
    return result[0]["rows_affected"]


def delete_rows(
    table_name: str,
    conditions: dict[str, Any],
    connection: str = "default",
) -> int:
    """Delete rows matching conditions.

    Args:
        table_name: Name of the table
        conditions: Dictionary of column names to values for WHERE clause
        connection: Connection name to use

    Returns:
        Number of rows deleted
    """
    where_parts = [f"{col} = ?" for col in conditions.keys()]
    where_clause = " AND ".join(where_parts)

    sql = f"DELETE FROM {table_name} WHERE {where_clause}"
    result = execute_query(sql, list(conditions.values()), connection=connection)
    return result[0]["rows_affected"]


def count_rows(
    table_name: str,
    conditions: dict[str, Any] | None = None,
    connection: str = "default",
) -> int:
    """Count rows in a table.

    Args:
        table_name: Name of the table
        conditions: Optional conditions for WHERE clause
        connection: Connection name to use

    Returns:
        Number of rows
    """
    sql = f"SELECT COUNT(*) as count FROM {table_name}"
    params = None

    if conditions:
        where_parts = [f"{col} = ?" for col in conditions.keys()]
        where_clause = " AND ".join(where_parts)
        sql += f" WHERE {where_clause}"
        params = list(conditions.values())

    result = execute_query(sql, params, connection=connection)
    return result[0]["count"]


def aggregate_query(
    table_name: str,
    column: str,
    function: str = "SUM",
    group_by: str | None = None,
    connection: str = "default",
) -> list[dict[str, Any]]:
    """Run an aggregate query on a table.

    Args:
        table_name: Name of the table
        column: Column to aggregate
        function: Aggregate function (SUM, AVG, COUNT, MIN, MAX)
        group_by: Optional column to group by
        connection: Connection name to use

    Returns:
        Aggregation results
    """
    func_upper = function.upper()
    if func_upper not in ("SUM", "AVG", "COUNT", "MIN", "MAX"):
        raise ValueError(f"Invalid aggregate function: {function}")

    if group_by:
        sql = f"SELECT {group_by}, {func_upper}({column}) as result FROM {table_name} GROUP BY {group_by}"
    else:
        sql = f"SELECT {func_upper}({column}) as result FROM {table_name}"

    return execute_query(sql, connection=connection)


def create_sample_data(connection: str = "default") -> str:
    """Create sample tables with test data.

    Args:
        connection: Connection name to use

    Returns:
        Status message
    """
    # Create users table
    create_table(
        "users",
        {
            "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
            "name": "TEXT NOT NULL",
            "email": "TEXT UNIQUE",
            "age": "INTEGER",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        },
        connection=connection,
    )

    # Create products table
    create_table(
        "products",
        {
            "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
            "name": "TEXT NOT NULL",
            "price": "REAL NOT NULL",
            "category": "TEXT",
            "stock": "INTEGER DEFAULT 0",
        },
        connection=connection,
    )

    # Create orders table
    create_table(
        "orders",
        {
            "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
            "user_id": "INTEGER REFERENCES users(id)",
            "product_id": "INTEGER REFERENCES products(id)",
            "quantity": "INTEGER NOT NULL",
            "total": "REAL NOT NULL",
            "order_date": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        },
        connection=connection,
    )

    # Insert sample users
    users = [
        {"name": "Alice", "email": "alice@example.com", "age": 30},
        {"name": "Bob", "email": "bob@example.com", "age": 25},
        {"name": "Charlie", "email": "charlie@example.com", "age": 35},
    ]
    insert_many("users", users, connection=connection)

    # Insert sample products
    products = [
        {"name": "Laptop", "price": 1200.00, "category": "Electronics", "stock": 50},
        {"name": "Phone", "price": 800.00, "category": "Electronics", "stock": 100},
        {"name": "Tablet", "price": 500.00, "category": "Electronics", "stock": 75},
        {"name": "Headphones", "price": 150.00, "category": "Accessories", "stock": 200},
        {"name": "Keyboard", "price": 80.00, "category": "Accessories", "stock": 150},
    ]
    insert_many("products", products, connection=connection)

    # Insert sample orders
    orders = [
        {"user_id": 1, "product_id": 1, "quantity": 1, "total": 1200.00},
        {"user_id": 1, "product_id": 4, "quantity": 2, "total": 300.00},
        {"user_id": 2, "product_id": 2, "quantity": 1, "total": 800.00},
        {"user_id": 2, "product_id": 5, "quantity": 1, "total": 80.00},
        {"user_id": 3, "product_id": 3, "quantity": 2, "total": 1000.00},
        {"user_id": 3, "product_id": 4, "quantity": 1, "total": 150.00},
    ]
    insert_many("orders", orders, connection=connection)

    return "Sample data created: users (3), products (5), orders (6)"


def get_database_info(connection: str = "default") -> dict[str, Any]:
    """Get information about the database.

    Args:
        connection: Connection name to use

    Returns:
        Database information including tables and row counts
    """
    tables = list_tables(connection=connection)
    info = {
        "connection": connection,
        "tables": {},
    }

    for table in tables:
        info["tables"][table] = {
            "row_count": count_rows(table, connection=connection),
            "columns": [col["column"] for col in describe_table(table, connection=connection)],
        }

    return info


def join_query(
    table1: str,
    table2: str,
    join_column1: str,
    join_column2: str,
    select_columns: list[str] | None = None,
    join_type: str = "INNER",
    connection: str = "default",
) -> list[dict[str, Any]]:
    """Execute a JOIN query between two tables.

    Args:
        table1: First table name
        table2: Second table name
        join_column1: Column from first table to join on
        join_column2: Column from second table to join on
        select_columns: List of columns to select (defaults to all)
        join_type: Type of join (INNER, LEFT, RIGHT)
        connection: Connection name to use

    Returns:
        Join results as list of dictionaries
    """
    columns = ", ".join(select_columns) if select_columns else "*"
    join_type_upper = join_type.upper()

    if join_type_upper not in ("INNER", "LEFT", "RIGHT", "CROSS"):
        raise ValueError(f"Invalid join type: {join_type}")

    sql = f"""
        SELECT {columns}
        FROM {table1}
        {join_type_upper} JOIN {table2}
        ON {table1}.{join_column1} = {table2}.{join_column2}
    """

    return execute_query(sql, connection=connection)
