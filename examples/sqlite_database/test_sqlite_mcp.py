#!/usr/bin/env python3
"""Test script for SQLite MCP server.

This script demonstrates:
1. Database connection and management
2. CRUD operations through the MCP tools
3. Query execution and aggregations
4. Join operations

Run directly to test the sqlite_tools module:
    python test_sqlite_mcp.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add the module directory to path
sys.path.insert(0, str(Path(__file__).parent))

import sqlite_tools


def test_connection():
    """Test database connection."""
    print("\n=== Connection Test ===\n")

    # Connect to in-memory database
    result = sqlite_tools.connect_database(":memory:", "test_db")
    print(f"1. {result}")

    # Get database info (should be empty)
    info = sqlite_tools.get_database_info("test_db")
    print(f"2. Database info: {info}")

    print("\n[OK] Connection test passed!")


def test_create_tables():
    """Test table creation."""
    print("\n=== Table Creation Test ===\n")

    # Create a simple table
    result = sqlite_tools.create_table(
        "employees",
        {
            "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
            "name": "TEXT NOT NULL",
            "department": "TEXT",
            "salary": "REAL",
        },
        connection="test_db",
    )
    print(f"1. {result}")

    # List tables
    tables = sqlite_tools.list_tables("test_db")
    print(f"2. Tables: {tables}")

    # Describe table
    schema = sqlite_tools.describe_table("employees", "test_db")
    print("3. Schema:")
    for col in schema:
        print(f"   - {col['column']}: {col['type']} (nullable={col['nullable']}, pk={col['primary_key']})")

    print("\n[OK] Table creation test passed!")


def test_insert_operations():
    """Test insert operations."""
    print("\n=== Insert Operations Test ===\n")

    # Insert single row
    row_id = sqlite_tools.insert_row(
        "employees",
        {"name": "Alice", "department": "Engineering", "salary": 85000},
        connection="test_db",
    )
    print(f"1. Inserted row with ID: {row_id}")

    # Insert multiple rows
    employees = [
        {"name": "Bob", "department": "Engineering", "salary": 90000},
        {"name": "Charlie", "department": "Sales", "salary": 75000},
        {"name": "Diana", "department": "Engineering", "salary": 95000},
        {"name": "Eve", "department": "Marketing", "salary": 70000},
    ]
    count = sqlite_tools.insert_many("employees", employees, connection="test_db")
    print(f"2. Inserted {count} rows")

    # Count rows
    total = sqlite_tools.count_rows("employees", connection="test_db")
    print(f"3. Total employees: {total}")

    print("\n[OK] Insert operations test passed!")


def test_select_operations():
    """Test select operations."""
    print("\n=== Select Operations Test ===\n")

    # Select all
    all_rows = sqlite_tools.select_all("employees", connection="test_db")
    print(f"1. All employees ({len(all_rows)} rows):")
    for row in all_rows:
        print(f"   {row['id']}: {row['name']} - {row['department']} (${row['salary']:,.0f})")

    # Select with limit
    limited = sqlite_tools.select_all("employees", limit=2, connection="test_db")
    print(f"\n2. First 2 employees: {[r['name'] for r in limited]}")

    # Select where
    engineers = sqlite_tools.select_where(
        "employees",
        {"department": "Engineering"},
        connection="test_db",
    )
    print(f"\n3. Engineers ({len(engineers)} rows):")
    for row in engineers:
        print(f"   {row['name']} - ${row['salary']:,.0f}")

    print("\n[OK] Select operations test passed!")


def test_update_delete():
    """Test update and delete operations."""
    print("\n=== Update/Delete Test ===\n")

    # Update salary
    updated = sqlite_tools.update_rows(
        "employees",
        {"salary": 100000},
        {"name": "Diana"},
        connection="test_db",
    )
    print(f"1. Updated {updated} row(s)")

    # Verify update
    diana = sqlite_tools.select_where("employees", {"name": "Diana"}, connection="test_db")
    print(f"2. Diana's new salary: ${diana[0]['salary']:,.0f}")

    # Delete row
    deleted = sqlite_tools.delete_rows(
        "employees",
        {"name": "Eve"},
        connection="test_db",
    )
    print(f"3. Deleted {deleted} row(s)")

    # Count remaining
    remaining = sqlite_tools.count_rows("employees", connection="test_db")
    print(f"4. Remaining employees: {remaining}")

    print("\n[OK] Update/Delete test passed!")


def test_aggregations():
    """Test aggregation queries."""
    print("\n=== Aggregation Test ===\n")

    # Total salary
    total = sqlite_tools.aggregate_query(
        "employees", "salary", "SUM", connection="test_db"
    )
    print(f"1. Total salary: ${total[0]['result']:,.0f}")

    # Average salary
    avg = sqlite_tools.aggregate_query(
        "employees", "salary", "AVG", connection="test_db"
    )
    print(f"2. Average salary: ${avg[0]['result']:,.0f}")

    # Count by department
    by_dept = sqlite_tools.aggregate_query(
        "employees", "id", "COUNT", group_by="department", connection="test_db"
    )
    print("3. Employees by department:")
    for row in by_dept:
        print(f"   {row['department']}: {row['result']}")

    # Max salary by department
    max_by_dept = sqlite_tools.aggregate_query(
        "employees", "salary", "MAX", group_by="department", connection="test_db"
    )
    print("4. Max salary by department:")
    for row in max_by_dept:
        print(f"   {row['department']}: ${row['result']:,.0f}")

    print("\n[OK] Aggregation test passed!")


def test_raw_queries():
    """Test raw SQL query execution."""
    print("\n=== Raw Query Test ===\n")

    # Complex query
    result = sqlite_tools.execute_query(
        """
        SELECT department, COUNT(*) as count, AVG(salary) as avg_salary
        FROM employees
        GROUP BY department
        ORDER BY avg_salary DESC
        """,
        connection="test_db",
    )
    print("1. Department statistics:")
    for row in result:
        print(f"   {row['department']}: {row['count']} employees, avg ${row['avg_salary']:,.0f}")

    # Parameterized query
    result = sqlite_tools.execute_query(
        "SELECT * FROM employees WHERE salary > ?",
        [80000],
        connection="test_db",
    )
    print(f"\n2. High earners (>$80k): {[r['name'] for r in result]}")

    print("\n[OK] Raw query test passed!")


def test_sample_data():
    """Test sample data creation."""
    print("\n=== Sample Data Test ===\n")

    # Create new connection for sample data
    sqlite_tools.connect_database(":memory:", "sample_db")

    # Create sample data
    result = sqlite_tools.create_sample_data(connection="sample_db")
    print(f"1. {result}")

    # Get database info
    info = sqlite_tools.get_database_info(connection="sample_db")
    print("2. Database structure:")
    for table, details in info["tables"].items():
        print(f"   {table}: {details['row_count']} rows, columns: {details['columns']}")

    # Test join query
    print("\n3. Orders with user and product info:")
    orders = sqlite_tools.execute_query(
        """
        SELECT u.name as customer, p.name as product, o.quantity, o.total
        FROM orders o
        JOIN users u ON o.user_id = u.id
        JOIN products p ON o.product_id = p.id
        ORDER BY o.total DESC
        """,
        connection="sample_db",
    )
    for order in orders[:5]:
        print(f"   {order['customer']} bought {order['quantity']}x {order['product']} (${order['total']:.2f})")

    # Test join_query function
    print("\n4. Using join_query function:")
    user_orders = sqlite_tools.join_query(
        "users", "orders",
        "id", "user_id",
        select_columns=["users.name", "orders.total"],
        connection="sample_db",
    )
    for row in user_orders[:3]:
        print(f"   {row}")

    print("\n[OK] Sample data test passed!")


def test_cleanup():
    """Test cleanup operations."""
    print("\n=== Cleanup Test ===\n")

    # Drop table
    result = sqlite_tools.drop_table("employees", connection="test_db")
    print(f"1. {result}")

    # Disconnect
    result = sqlite_tools.disconnect_database("test_db")
    print(f"2. {result}")

    result = sqlite_tools.disconnect_database("sample_db")
    print(f"3. {result}")

    print("\n[OK] Cleanup test passed!")


def main():
    """Run all tests."""
    print("=" * 60)
    print("SQLite MCP Server - Test Suite")
    print("=" * 60)

    test_connection()
    test_create_tables()
    test_insert_operations()
    test_select_operations()
    test_update_delete()
    test_aggregations()
    test_raw_queries()
    test_sample_data()
    test_cleanup()

    print("\n" + "=" * 60)
    print("All tests completed successfully!")
    print("=" * 60)
    print("\nAvailable MCP tools (18):")
    tools = [
        "connect_database", "disconnect_database", "execute_query", "execute_script",
        "create_table", "drop_table", "list_tables", "describe_table",
        "insert_row", "insert_many", "select_all", "select_where",
        "update_rows", "delete_rows", "count_rows", "aggregate_query",
        "join_query", "create_sample_data", "get_database_info",
    ]
    for i, tool in enumerate(tools, 1):
        print(f"  {i:2}. {tool}")


if __name__ == "__main__":
    main()
