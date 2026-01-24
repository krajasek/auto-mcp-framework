"""Example modules for auto-mcp.

Two approaches are demonstrated:

1. Direct Serve (simple modules):
   - simple_math: Basic math functions
   - async_api: Async weather API
   - class_service: Todo service with decorators

2. Manifest-Based (large packages):
   - sqlite_database: SQLite operations via manifest
   - pandas_analytics: Pandas data analysis via manifest

Each manifest-based example includes:
- manifest.yaml: Defines which functions to expose
- server.py: Pre-generated MCP server
- run_server.py: Helper script to run the server
"""
