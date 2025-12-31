"""Todo list service demonstrating class-based tool exposure.

This module shows how to use the @mcp_tool decorator on class methods
and how auto-mcp can expose class instances as MCP tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import uuid4

from auto_mcp import mcp_exclude, mcp_tool


@dataclass
class TodoItem:
    """A single todo item."""

    id: str
    title: str
    description: str
    status: Literal["pending", "in_progress", "completed"]
    priority: Literal["low", "medium", "high"]
    created_at: datetime
    completed_at: datetime | None = None
    tags: list[str] = field(default_factory=list)


class TodoService:
    """A simple todo list service.

    This service manages a collection of todo items and provides
    methods for CRUD operations that will be exposed as MCP tools.
    """

    def __init__(self) -> None:
        """Initialize the todo service with an empty list."""
        self._todos: dict[str, TodoItem] = {}

    @mcp_tool(name="create_todo", description="Create a new todo item")
    def create(
        self,
        title: str,
        description: str = "",
        priority: Literal["low", "medium", "high"] = "medium",
        tags: list[str] | None = None,
    ) -> dict:
        """Create a new todo item.

        Args:
            title: Title of the todo item
            description: Detailed description (optional)
            priority: Priority level (low, medium, high)
            tags: List of tags for categorization

        Returns:
            The created todo item as a dictionary
        """
        todo_id = str(uuid4())[:8]
        todo = TodoItem(
            id=todo_id,
            title=title,
            description=description,
            status="pending",
            priority=priority,
            created_at=datetime.now(),
            tags=tags or [],
        )
        self._todos[todo_id] = todo
        return self._todo_to_dict(todo)

    @mcp_tool(name="get_todo")
    def get(self, todo_id: str) -> dict | None:
        """Get a todo item by ID.

        Args:
            todo_id: The unique identifier of the todo

        Returns:
            The todo item or None if not found
        """
        todo = self._todos.get(todo_id)
        if todo:
            return self._todo_to_dict(todo)
        return None

    @mcp_tool(name="list_todos")
    def list_all(
        self,
        status: Literal["pending", "in_progress", "completed", "all"] = "all",
        priority: Literal["low", "medium", "high", "all"] = "all",
    ) -> list[dict]:
        """List all todo items with optional filtering.

        Args:
            status: Filter by status (or 'all' for no filter)
            priority: Filter by priority (or 'all' for no filter)

        Returns:
            List of todo items matching the filters
        """
        todos = list(self._todos.values())

        if status != "all":
            todos = [t for t in todos if t.status == status]

        if priority != "all":
            todos = [t for t in todos if t.priority == priority]

        return [self._todo_to_dict(t) for t in todos]

    @mcp_tool(name="update_todo_status")
    def update_status(
        self,
        todo_id: str,
        status: Literal["pending", "in_progress", "completed"],
    ) -> dict | None:
        """Update the status of a todo item.

        Args:
            todo_id: The unique identifier of the todo
            status: New status value

        Returns:
            The updated todo item or None if not found
        """
        todo = self._todos.get(todo_id)
        if not todo:
            return None

        todo.status = status
        if status == "completed":
            todo.completed_at = datetime.now()
        else:
            todo.completed_at = None

        return self._todo_to_dict(todo)

    @mcp_tool(name="delete_todo")
    def delete(self, todo_id: str) -> bool:
        """Delete a todo item.

        Args:
            todo_id: The unique identifier of the todo

        Returns:
            True if deleted, False if not found
        """
        if todo_id in self._todos:
            del self._todos[todo_id]
            return True
        return False

    @mcp_tool(name="search_todos")
    def search(self, query: str) -> list[dict]:
        """Search todos by title or description.

        Args:
            query: Search query string

        Returns:
            List of matching todo items
        """
        query_lower = query.lower()
        matches = [
            t
            for t in self._todos.values()
            if query_lower in t.title.lower() or query_lower in t.description.lower()
        ]
        return [self._todo_to_dict(t) for t in matches]

    @mcp_tool(name="get_stats")
    def get_statistics(self) -> dict:
        """Get statistics about the todo list.

        Returns:
            Dictionary with counts by status and priority
        """
        todos = list(self._todos.values())

        status_counts = {"pending": 0, "in_progress": 0, "completed": 0}
        priority_counts = {"low": 0, "medium": 0, "high": 0}

        for todo in todos:
            status_counts[todo.status] += 1
            priority_counts[todo.priority] += 1

        return {
            "total": len(todos),
            "by_status": status_counts,
            "by_priority": priority_counts,
        }

    @mcp_exclude
    def _todo_to_dict(self, todo: TodoItem) -> dict:
        """Convert a TodoItem to a dictionary.

        This is an internal helper and should not be exposed as a tool.
        """
        return {
            "id": todo.id,
            "title": todo.title,
            "description": todo.description,
            "status": todo.status,
            "priority": todo.priority,
            "created_at": todo.created_at.isoformat(),
            "completed_at": todo.completed_at.isoformat() if todo.completed_at else None,
            "tags": todo.tags,
        }


# Create a singleton instance for use
todo_service = TodoService()

# Expose instance methods as module-level functions
create_todo = todo_service.create
get_todo = todo_service.get
list_todos = todo_service.list_all
update_todo_status = todo_service.update_status
delete_todo = todo_service.delete
search_todos = todo_service.search
get_stats = todo_service.get_statistics
