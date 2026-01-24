"""Tests for session lifecycle support."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from auto_mcp.session import (
    SessionConfig,
    SessionContext,
    SessionData,
    SessionManager,
    mcp_session_cleanup,
    mcp_session_init,
)
from auto_mcp.session.decorators import (
    MCP_SESSION_CLEANUP_MARKER,
    MCP_SESSION_INIT_MARKER,
)
from auto_mcp.session.injection import (
    get_non_session_parameters,
    get_session_param_name,
    needs_session_injection,
)


class TestSessionData:
    """Tests for SessionData class."""

    def test_get_set_basic(self) -> None:
        """Test basic get/set operations."""
        data = SessionData()
        data.set("key1", "value1")
        assert data.get("key1") == "value1"

    def test_get_default(self) -> None:
        """Test get with default value."""
        data = SessionData()
        assert data.get("missing") is None
        assert data.get("missing", "default") == "default"

    def test_delete(self) -> None:
        """Test delete operation."""
        data = SessionData()
        data.set("key1", "value1")
        assert data.delete("key1") is True
        assert data.get("key1") is None
        assert data.delete("key1") is False  # Already deleted

    def test_clear(self) -> None:
        """Test clear operation."""
        data = SessionData()
        data.set("key1", "value1")
        data.set("key2", "value2")
        data.clear()
        assert data.get("key1") is None
        assert data.get("key2") is None

    def test_keys(self) -> None:
        """Test keys method."""
        data = SessionData()
        data.set("key1", "value1")
        data.set("key2", "value2")
        assert set(data.keys()) == {"key1", "key2"}

    def test_contains(self) -> None:
        """Test contains method."""
        data = SessionData()
        data.set("key1", "value1")
        assert data.contains("key1") is True
        assert data.contains("missing") is False

    def test_len(self) -> None:
        """Test len method."""
        data = SessionData()
        assert len(data) == 0
        data.set("key1", "value1")
        assert len(data) == 1
        data.set("key2", "value2")
        assert len(data) == 2


class TestSessionContext:
    """Tests for SessionContext class."""

    def test_creation(self) -> None:
        """Test SessionContext creation."""
        ctx = SessionContext(
            session_id="session:abc123",
            created_at=time.time(),
        )
        assert ctx.session_id == "session:abc123"
        assert isinstance(ctx.data, SessionData)
        assert ctx.metadata == {}

    def test_age_seconds(self) -> None:
        """Test age_seconds property."""
        ctx = SessionContext(
            session_id="session:abc123",
            created_at=time.time() - 10,  # 10 seconds ago
        )
        assert ctx.age_seconds >= 10

    def test_with_metadata(self) -> None:
        """Test SessionContext with metadata."""
        ctx = SessionContext(
            session_id="session:abc123",
            created_at=time.time(),
            metadata={"user_id": "user123"},
        )
        assert ctx.metadata["user_id"] == "user123"

    def test_data_operations(self) -> None:
        """Test data operations via context."""
        ctx = SessionContext(
            session_id="session:abc123",
            created_at=time.time(),
        )
        ctx.data.set("key1", "value1")
        assert ctx.data.get("key1") == "value1"


class TestSessionConfig:
    """Tests for SessionConfig class."""

    def test_defaults(self) -> None:
        """Test default values."""
        config = SessionConfig()
        assert config.default_ttl == 3600
        assert config.max_sessions == 100
        assert config.session_id_prefix == "session:"
        assert config.handle_length == 12

    def test_custom_values(self) -> None:
        """Test custom values."""
        config = SessionConfig(
            default_ttl=7200,
            max_sessions=50,
            session_id_prefix="sess:",
        )
        assert config.default_ttl == 7200
        assert config.max_sessions == 50
        assert config.session_id_prefix == "sess:"


class TestSessionManager:
    """Tests for SessionManager class."""

    @pytest.fixture
    def manager(self) -> SessionManager:
        """Create a session manager for tests."""
        return SessionManager(SessionConfig(max_sessions=10))

    @pytest.mark.asyncio
    async def test_create_session(self, manager: SessionManager) -> None:
        """Test session creation."""
        session = await manager.create_session()
        assert session.session_id.startswith("session:")
        assert manager.get_session(session.session_id) is session

    @pytest.mark.asyncio
    async def test_create_session_with_metadata(self, manager: SessionManager) -> None:
        """Test session creation with metadata."""
        session = await manager.create_session(metadata={"user_id": "user123"})
        assert session.metadata["user_id"] == "user123"

    @pytest.mark.asyncio
    async def test_close_session(self, manager: SessionManager) -> None:
        """Test session closing."""
        session = await manager.create_session()
        session_id = session.session_id
        assert await manager.close_session(session_id) is True
        # get_session raises KeyError for closed sessions
        with pytest.raises(KeyError):
            manager.get_session(session_id)

    @pytest.mark.asyncio
    async def test_close_nonexistent_session(self, manager: SessionManager) -> None:
        """Test closing a non-existent session."""
        assert await manager.close_session("session:nonexistent") is False

    @pytest.mark.asyncio
    async def test_max_sessions_limit(self, manager: SessionManager) -> None:
        """Test max sessions limit."""
        # Create max sessions
        sessions = []
        for _ in range(10):
            session = await manager.create_session()
            sessions.append(session)

        # Try to create one more
        with pytest.raises(ValueError, match="Maximum sessions"):
            await manager.create_session()

    @pytest.mark.asyncio
    async def test_session_count(self, manager: SessionManager) -> None:
        """Test session counting."""
        assert manager.session_count == 0
        session1 = await manager.create_session()
        assert manager.session_count == 1
        session2 = await manager.create_session()
        assert manager.session_count == 2
        await manager.close_session(session1.session_id)
        assert manager.session_count == 1

    @pytest.mark.asyncio
    async def test_list_sessions(self, manager: SessionManager) -> None:
        """Test listing sessions."""
        session1 = await manager.create_session()
        session2 = await manager.create_session()
        sessions = manager.list_sessions()
        assert len(sessions) == 2
        assert session1.session_id in sessions
        assert session2.session_id in sessions

    @pytest.mark.asyncio
    async def test_init_hook(self, manager: SessionManager) -> None:
        """Test init hook execution."""
        hook_called = []

        async def init_hook(session: SessionContext) -> None:
            hook_called.append(session.session_id)
            session.data.set("initialized", True)

        manager.register_init_hook(init_hook)
        session = await manager.create_session()

        assert len(hook_called) == 1
        assert hook_called[0] == session.session_id
        assert session.data.get("initialized") is True

    @pytest.mark.asyncio
    async def test_cleanup_hook(self, manager: SessionManager) -> None:
        """Test cleanup hook execution."""
        hook_called = []

        async def cleanup_hook(session: SessionContext) -> None:
            hook_called.append(session.session_id)

        manager.register_cleanup_hook(cleanup_hook)
        session = await manager.create_session()
        session_id = session.session_id

        await manager.close_session(session_id)
        assert len(hook_called) == 1
        assert hook_called[0] == session_id

    @pytest.mark.asyncio
    async def test_init_hooks_order(self, manager: SessionManager) -> None:
        """Test init hooks are called in order."""
        call_order: list[int] = []

        async def hook1(session: SessionContext) -> None:
            call_order.append(1)

        async def hook2(session: SessionContext) -> None:
            call_order.append(2)

        async def hook3(session: SessionContext) -> None:
            call_order.append(3)

        manager.register_init_hook(hook2, order=1)
        manager.register_init_hook(hook1, order=0)
        manager.register_init_hook(hook3, order=2)

        await manager.create_session()
        assert call_order == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_cleanup_hooks_reverse_order(self, manager: SessionManager) -> None:
        """Test cleanup hooks are called in reverse order."""
        call_order: list[int] = []

        async def hook1(session: SessionContext) -> None:
            call_order.append(1)

        async def hook2(session: SessionContext) -> None:
            call_order.append(2)

        async def hook3(session: SessionContext) -> None:
            call_order.append(3)

        manager.register_cleanup_hook(hook1, order=0)
        manager.register_cleanup_hook(hook2, order=1)
        manager.register_cleanup_hook(hook3, order=2)

        session = await manager.create_session()
        await manager.close_session(session.session_id)
        assert call_order == [3, 2, 1]

    @pytest.mark.asyncio
    async def test_sync_hook_support(self, manager: SessionManager) -> None:
        """Test that sync hooks are also supported."""
        hook_called = []

        def sync_init_hook(session: SessionContext) -> None:
            hook_called.append("init")

        def sync_cleanup_hook(session: SessionContext) -> None:
            hook_called.append("cleanup")

        manager.register_init_hook(sync_init_hook)
        manager.register_cleanup_hook(sync_cleanup_hook)

        session = await manager.create_session()
        await manager.close_session(session.session_id)

        assert hook_called == ["init", "cleanup"]


class TestSessionDecorators:
    """Tests for session decorators."""

    def test_mcp_session_init_decorator(self) -> None:
        """Test mcp_session_init decorator."""

        @mcp_session_init(order=5)
        def init_handler(session: SessionContext) -> None:
            pass

        assert hasattr(init_handler, MCP_SESSION_INIT_MARKER)
        metadata = getattr(init_handler, MCP_SESSION_INIT_MARKER)
        assert metadata["order"] == 5

    def test_mcp_session_cleanup_decorator(self) -> None:
        """Test mcp_session_cleanup decorator."""

        @mcp_session_cleanup(order=3)
        def cleanup_handler(session: SessionContext) -> None:
            pass

        assert hasattr(cleanup_handler, MCP_SESSION_CLEANUP_MARKER)
        metadata = getattr(cleanup_handler, MCP_SESSION_CLEANUP_MARKER)
        assert metadata["order"] == 3

    def test_mcp_session_init_default_order(self) -> None:
        """Test mcp_session_init with default order."""

        @mcp_session_init()
        def init_handler(session: SessionContext) -> None:
            pass

        metadata = getattr(init_handler, MCP_SESSION_INIT_MARKER)
        assert metadata["order"] == 0

    def test_decorators_preserve_function(self) -> None:
        """Test that decorators preserve function behavior."""

        @mcp_session_init()
        def init_handler(session: SessionContext) -> str:
            return "initialized"

        # Create a mock context
        ctx = SessionContext(session_id="test", created_at=time.time())
        assert init_handler(ctx) == "initialized"


class TestSessionInjection:
    """Tests for session injection utilities."""

    def test_needs_session_injection_true(self) -> None:
        """Test detection of SessionContext parameter."""

        def func_with_session(session: SessionContext, x: int) -> int:
            return x

        assert needs_session_injection(func_with_session) is True

    def test_needs_session_injection_false(self) -> None:
        """Test functions without SessionContext."""

        def func_without_session(x: int, y: str) -> int:
            return x

        assert needs_session_injection(func_without_session) is False

    def test_get_session_param_name(self) -> None:
        """Test getting session parameter name."""

        def func_with_session(ctx: SessionContext, x: int) -> int:
            return x

        assert get_session_param_name(func_with_session) == "ctx"

    def test_get_session_param_name_none(self) -> None:
        """Test when there's no SessionContext parameter."""

        def func_without_session(x: int) -> int:
            return x

        assert get_session_param_name(func_without_session) is None

    def test_get_non_session_parameters(self) -> None:
        """Test getting non-session parameters."""

        def func_with_session(session: SessionContext, x: int, y: str) -> None:
            pass

        params = get_non_session_parameters(func_with_session)
        assert params == ["x", "y"]

    def test_get_non_session_parameters_no_session(self) -> None:
        """Test getting parameters when no session."""

        def func_without_session(x: int, y: str) -> None:
            pass

        params = get_non_session_parameters(func_without_session)
        assert params == ["x", "y"]

    def test_async_function_detection(self) -> None:
        """Test session injection detection for async functions."""

        async def async_func(session: SessionContext, x: int) -> int:
            return x

        assert needs_session_injection(async_func) is True
        assert get_session_param_name(async_func) == "session"

    def test_optional_session_context(self) -> None:
        """Test detection of Optional[SessionContext] parameter."""
        from typing import Optional

        def func_with_optional(ctx: Optional[SessionContext], x: int) -> int:
            return x

        assert needs_session_injection(func_with_optional) is True
        assert get_session_param_name(func_with_optional) == "ctx"

    def test_union_session_context(self) -> None:
        """Test detection of SessionContext | None parameter."""

        def func_with_union(ctx: SessionContext | None, x: int) -> int:
            return x

        assert needs_session_injection(func_with_union) is True
        assert get_session_param_name(func_with_union) == "ctx"

    def test_get_type_hints_failure(self) -> None:
        """Test handling when get_type_hints fails."""
        # Create a function with an annotation that can't be resolved
        def problematic_func(x: "NonExistentType") -> None:  # type: ignore
            pass

        # Should return None gracefully (no SessionContext)
        assert get_session_param_name(problematic_func) is None
        assert needs_session_injection(problematic_func) is False

    def test_string_annotation_session_context(self) -> None:
        """Test detection of string annotation containing SessionContext."""
        # Use exec to create function with string annotation at runtime
        func_code = '''
def func_with_string_annotation(session: "SessionContext", x: int) -> int:
    return x
'''
        local_ns: dict[str, Any] = {}
        exec(func_code, {"SessionContext": SessionContext}, local_ns)
        func = local_ns["func_with_string_annotation"]

        # Note: This may or may not work depending on how get_type_hints resolves it
        # The fallback path checks for string "SessionContext" in annotation
        result = get_session_param_name(func)
        # The string annotation should be resolved or detected
        assert result == "session"


class TestSessionIntegration:
    """Integration tests for session lifecycle."""

    @pytest.mark.asyncio
    async def test_full_session_lifecycle(self) -> None:
        """Test complete session lifecycle with hooks."""
        manager = SessionManager()
        lifecycle_events: list[str] = []

        @mcp_session_init()
        async def on_init(session: SessionContext) -> None:
            lifecycle_events.append(f"init:{session.session_id}")
            session.data.set("connection", "db_conn")

        @mcp_session_cleanup()
        async def on_cleanup(session: SessionContext) -> None:
            lifecycle_events.append(f"cleanup:{session.session_id}")
            session.data.delete("connection")

        manager.register_init_hook(on_init)
        manager.register_cleanup_hook(on_cleanup)

        # Create session
        session = await manager.create_session(metadata={"user": "test"})
        assert f"init:{session.session_id}" in lifecycle_events
        assert session.data.get("connection") == "db_conn"

        # Use session
        session.data.set("counter", 0)
        session.data.set("counter", session.data.get("counter") + 1)
        assert session.data.get("counter") == 1

        # Close session
        await manager.close_session(session.session_id)
        assert f"cleanup:{session.session_id}" in lifecycle_events

    @pytest.mark.asyncio
    async def test_multiple_sessions_isolation(self) -> None:
        """Test that multiple sessions are isolated."""
        manager = SessionManager()

        session1 = await manager.create_session()
        session2 = await manager.create_session()

        session1.data.set("value", "session1_value")
        session2.data.set("value", "session2_value")

        assert session1.data.get("value") == "session1_value"
        assert session2.data.get("value") == "session2_value"

        await manager.close_session(session1.session_id)
        assert session2.data.get("value") == "session2_value"

    @pytest.mark.asyncio
    async def test_session_with_custom_ttl(self) -> None:
        """Test session creation with custom TTL."""
        manager = SessionManager(SessionConfig(default_ttl=3600))

        session = await manager.create_session(ttl=7200)
        # The session should store the custom TTL
        # (Note: TTL enforcement is not tested here as it would require time manipulation)
        assert session is not None


class TestSessionDataExtended:
    """Extended tests for SessionData class."""

    def test_items(self) -> None:
        """Test items method returns key-value pairs."""
        data = SessionData()
        data.set("key1", "value1")
        data.set("key2", "value2")
        items = data.items()
        assert ("key1", "value1") in items
        assert ("key2", "value2") in items
        assert len(items) == 2

    def test_contains_dunder(self) -> None:
        """Test __contains__ dunder method."""
        data = SessionData()
        data.set("exists", "value")
        assert "exists" in data
        assert "missing" not in data


class TestSessionContextExtended:
    """Extended tests for SessionContext class."""

    def test_refresh_without_manager(self) -> None:
        """Test refresh returns False when no manager."""
        ctx = SessionContext(
            session_id="session:test",
            created_at=time.time(),
            _manager=None,
        )
        assert ctx.refresh() is False

    @pytest.mark.asyncio
    async def test_refresh_with_manager(self) -> None:
        """Test refresh works with manager."""
        manager = SessionManager()
        session = await manager.create_session()
        assert session.refresh() is True

    def test_invalidate_without_manager(self) -> None:
        """Test invalidate does nothing without manager."""
        ctx = SessionContext(
            session_id="session:test",
            created_at=time.time(),
            _manager=None,
        )
        # Should not raise
        ctx.invalidate()

    @pytest.mark.asyncio
    async def test_invalidate_with_manager(self) -> None:
        """Test invalidate schedules session closure."""
        manager = SessionManager()
        session = await manager.create_session()
        session_id = session.session_id

        # Invalidate schedules async closure
        session.invalidate()
        # Give async task time to run
        await asyncio.sleep(0.1)

        assert not manager.session_exists(session_id)

    @pytest.mark.asyncio
    async def test_invalidate_async_without_manager(self) -> None:
        """Test invalidate_async returns False without manager."""
        ctx = SessionContext(
            session_id="session:test",
            created_at=time.time(),
            _manager=None,
        )
        result = await ctx.invalidate_async()
        assert result is False

    @pytest.mark.asyncio
    async def test_invalidate_async_with_manager(self) -> None:
        """Test invalidate_async properly closes session."""
        manager = SessionManager()
        session = await manager.create_session()
        session_id = session.session_id

        result = await session.invalidate_async()
        assert result is True
        assert not manager.session_exists(session_id)

    def test_copy_raises_error(self) -> None:
        """Test that copying SessionContext raises RuntimeError."""
        import copy

        ctx = SessionContext(
            session_id="session:test",
            created_at=time.time(),
        )

        with pytest.raises(RuntimeError, match="cannot be copied"):
            copy.copy(ctx)

    def test_deepcopy_raises_error(self) -> None:
        """Test that deep copying SessionContext raises RuntimeError."""
        import copy

        ctx = SessionContext(
            session_id="session:test",
            created_at=time.time(),
        )

        with pytest.raises(RuntimeError, match="cannot be deep copied"):
            copy.deepcopy(ctx)


class TestStoredSession:
    """Tests for StoredSession class."""

    def test_is_expired_never_expires(self) -> None:
        """Test is_expired returns False when expires_at is 0."""
        from auto_mcp.session.manager import StoredSession

        ctx = SessionContext(
            session_id="session:test",
            created_at=time.time(),
        )
        stored = StoredSession(
            context=ctx,
            expires_at=0,  # Never expires
            created_at=time.time(),
        )
        assert stored.is_expired is False

    def test_is_expired_not_expired(self) -> None:
        """Test is_expired returns False when not expired."""
        from auto_mcp.session.manager import StoredSession

        ctx = SessionContext(
            session_id="session:test",
            created_at=time.time(),
        )
        stored = StoredSession(
            context=ctx,
            expires_at=time.time() + 3600,  # 1 hour from now
            created_at=time.time(),
        )
        assert stored.is_expired is False

    def test_is_expired_expired(self) -> None:
        """Test is_expired returns True when expired."""
        from auto_mcp.session.manager import StoredSession

        ctx = SessionContext(
            session_id="session:test",
            created_at=time.time(),
        )
        stored = StoredSession(
            context=ctx,
            expires_at=time.time() - 1,  # 1 second ago
            created_at=time.time(),
        )
        assert stored.is_expired is True


class TestSessionManagerExtended:
    """Extended tests for SessionManager class."""

    @pytest.fixture
    def manager(self) -> SessionManager:
        """Create a session manager for tests."""
        return SessionManager(SessionConfig(max_sessions=10))

    @pytest.mark.asyncio
    async def test_metadata_validation_not_dict(self, manager: SessionManager) -> None:
        """Test metadata validation rejects non-dict."""
        with pytest.raises(TypeError, match="must be a dict"):
            await manager.create_session(metadata="not a dict")  # type: ignore

    @pytest.mark.asyncio
    async def test_metadata_validation_too_many_keys(self) -> None:
        """Test metadata validation rejects too many keys."""
        manager = SessionManager(SessionConfig(max_metadata_keys=2))
        metadata = {"key1": "v1", "key2": "v2", "key3": "v3"}

        with pytest.raises(ValueError, match="exceeds maximum key count"):
            await manager.create_session(metadata=metadata)

    @pytest.mark.asyncio
    async def test_metadata_validation_non_string_key(self, manager: SessionManager) -> None:
        """Test metadata validation rejects non-string keys."""
        with pytest.raises(TypeError, match="keys must be strings"):
            await manager.create_session(metadata={123: "value"})  # type: ignore

    @pytest.mark.asyncio
    async def test_metadata_validation_value_too_large(self) -> None:
        """Test metadata validation rejects oversized values."""
        manager = SessionManager(SessionConfig(max_metadata_value_size=10))
        metadata = {"key": "x" * 100}  # Value too large

        with pytest.raises(ValueError, match="exceeds maximum size"):
            await manager.create_session(metadata=metadata)

    @pytest.mark.asyncio
    async def test_init_hook_error_handling(self, manager: SessionManager) -> None:
        """Test that init hook errors are logged but don't break session creation."""

        async def failing_hook(session: SessionContext) -> None:
            raise ValueError("Hook failed!")

        manager.register_init_hook(failing_hook)
        # Should not raise, session should still be created
        session = await manager.create_session()
        assert session is not None
        assert manager.session_exists(session.session_id)

    @pytest.mark.asyncio
    async def test_cleanup_hook_error_handling(self, manager: SessionManager) -> None:
        """Test that cleanup hook errors are logged but don't break session closure."""

        async def failing_hook(session: SessionContext) -> None:
            raise ValueError("Cleanup failed!")

        manager.register_cleanup_hook(failing_hook)
        session = await manager.create_session()
        session_id = session.session_id

        # Should not raise, session should still be closed
        result = await manager.close_session(session_id)
        assert result is True
        assert not manager.session_exists(session_id)

    @pytest.mark.asyncio
    async def test_get_session_expired(self, manager: SessionManager) -> None:
        """Test get_session raises ValueError for expired session."""
        # Create session with very short TTL
        session = await manager.create_session(ttl=1)
        session_id = session.session_id

        # Wait for expiration
        await asyncio.sleep(1.5)

        with pytest.raises(ValueError, match="has expired"):
            manager.get_session(session_id)

    @pytest.mark.asyncio
    async def test_session_exists_expired(self, manager: SessionManager) -> None:
        """Test session_exists returns False for expired session."""
        session = await manager.create_session(ttl=1)
        session_id = session.session_id

        await asyncio.sleep(1.5)
        assert manager.session_exists(session_id) is False

    @pytest.mark.asyncio
    async def test_refresh_session_not_found(self, manager: SessionManager) -> None:
        """Test refresh_session returns False for non-existent session."""
        result = manager.refresh_session("session:nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_refresh_session_expired(self, manager: SessionManager) -> None:
        """Test refresh_session returns False for expired session."""
        session = await manager.create_session(ttl=1)
        session_id = session.session_id

        await asyncio.sleep(1.5)
        result = manager.refresh_session(session_id)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_stats(self, manager: SessionManager) -> None:
        """Test get_stats returns correct statistics."""
        # Create some sessions
        session1 = await manager.create_session()
        session2 = await manager.create_session()

        stats = manager.get_stats()
        assert stats["active_sessions"] == 2
        assert stats["max_sessions"] == 10
        assert stats["total_created"] == 2
        assert stats["total_closed"] == 0

        # Close one session
        await manager.close_session(session1.session_id)
        stats = manager.get_stats()
        assert stats["active_sessions"] == 1
        assert stats["total_closed"] == 1

    @pytest.mark.asyncio
    async def test_cleanup_removes_expired(self, manager: SessionManager) -> None:
        """Test cleanup() removes expired sessions."""
        # Create session with short TTL
        session = await manager.create_session(ttl=1)
        assert manager.session_count == 1

        await asyncio.sleep(1.5)

        count = await manager.cleanup()
        assert count == 1
        assert manager.session_count == 0

    @pytest.mark.asyncio
    async def test_clear_closes_all_sessions(self, manager: SessionManager) -> None:
        """Test clear() closes all sessions."""
        await manager.create_session()
        await manager.create_session()
        await manager.create_session()
        assert manager.session_count == 3

        count = await manager.clear()
        assert count == 3
        assert manager.session_count == 0

    @pytest.mark.asyncio
    async def test_never_expiring_session(self, manager: SessionManager) -> None:
        """Test session with TTL=0 never expires."""
        session = await manager.create_session(ttl=0)
        session_id = session.session_id

        # Even after sleep, session should exist
        await asyncio.sleep(0.1)
        assert manager.session_exists(session_id)
        assert manager.get_session(session_id) is session

    @pytest.mark.asyncio
    async def test_count_method(self, manager: SessionManager) -> None:
        """Test count() method."""
        assert manager.count() == 0
        await manager.create_session()
        assert manager.count() == 1
        await manager.create_session()
        assert manager.count() == 2


class TestDefaultSessionManager:
    """Tests for global default session manager."""

    def test_get_default_session_manager(self) -> None:
        """Test getting default manager creates one if needed."""
        from auto_mcp.session.manager import (
            _default_manager,
            get_default_session_manager,
            set_default_session_manager,
        )

        # Save current default
        import auto_mcp.session.manager as manager_module
        original = manager_module._default_manager

        try:
            # Reset to None
            manager_module._default_manager = None

            # Get default should create new manager
            default = get_default_session_manager()
            assert default is not None
            assert isinstance(default, SessionManager)

            # Should return same instance
            assert get_default_session_manager() is default
        finally:
            # Restore original
            manager_module._default_manager = original

    def test_set_default_session_manager(self) -> None:
        """Test setting default manager."""
        from auto_mcp.session.manager import (
            get_default_session_manager,
            set_default_session_manager,
        )
        import auto_mcp.session.manager as manager_module
        original = manager_module._default_manager

        try:
            custom_manager = SessionManager(SessionConfig(max_sessions=5))
            set_default_session_manager(custom_manager)

            assert get_default_session_manager() is custom_manager
        finally:
            manager_module._default_manager = original


class TestSessionManagerSyncCleanup:
    """Tests for synchronous cleanup paths."""

    def test_sync_cleanup(self) -> None:
        """Test _sync_cleanup removes expired sessions without hooks."""
        from auto_mcp.session.manager import StoredSession

        manager = SessionManager()

        # Manually add an expired session
        ctx = SessionContext(
            session_id="session:expired",
            created_at=time.time() - 100,
            _manager=manager,
        )
        stored = StoredSession(
            context=ctx,
            expires_at=time.time() - 1,  # Already expired
            created_at=time.time() - 100,
        )
        manager._sessions["session:expired"] = stored

        # Run sync cleanup
        count = manager._sync_cleanup()
        assert count == 1
        assert "session:expired" not in manager._sessions


class TestSessionInjectionEdgeCases:
    """Test edge cases in session parameter injection."""

    def test_get_session_param_union_with_none(self) -> None:
        """Test finding SessionContext | None parameter (line 47)."""
        from typing import Union
        from auto_mcp.session.context import SessionContext
        from auto_mcp.session.injection import get_session_param_name

        # Use Union syntax to ensure __origin__ is checked
        def func_with_union(ctx: Union[SessionContext, None] = None) -> None:
            pass

        result = get_session_param_name(func_with_union)
        assert result == "ctx"

    def test_get_session_param_direct_annotation(self) -> None:
        """Test finding session param via direct annotation."""
        from auto_mcp.session.context import SessionContext
        from auto_mcp.session.injection import get_session_param_name

        def func_with_session(session: SessionContext) -> None:
            pass

        result = get_session_param_name(func_with_session)
        assert result == "session"

    def test_get_session_param_none(self) -> None:
        """Test no session parameter found."""
        from auto_mcp.session.injection import get_session_param_name

        def func_without_session(x: int, y: str) -> None:
            pass

        result = get_session_param_name(func_without_session)
        assert result is None

    def test_get_session_param_with_forward_ref(self) -> None:
        """Test handling forward reference annotations (line 53 fallback)."""
        from auto_mcp.session.injection import get_session_param_name
        import inspect

        # Create a function with a string annotation that won't resolve
        # This forces the fallback path
        def func_with_forward_ref(session: "SessionContext") -> None:
            pass

        result = get_session_param_name(func_with_forward_ref)
        # The string annotation check should find it
        assert result == "session"

    def test_needs_session_injection(self) -> None:
        """Test needs_session_injection function."""
        from auto_mcp.session.context import SessionContext
        from auto_mcp.session.injection import needs_session_injection

        def with_session(ctx: SessionContext) -> None:
            pass

        def without_session(x: int) -> None:
            pass

        assert needs_session_injection(with_session) is True
        assert needs_session_injection(without_session) is False

    def test_get_non_session_parameters(self) -> None:
        """Test get_non_session_parameters function."""
        from auto_mcp.session.context import SessionContext
        from auto_mcp.session.injection import get_non_session_parameters

        def func(x: int, ctx: SessionContext, y: str) -> None:
            pass

        result = get_non_session_parameters(func)
        assert "x" in result
        assert "y" in result
        assert "ctx" not in result

    def test_get_session_hook_metadata(self) -> None:
        """Test get_session_hook_metadata function (line 114)."""
        from auto_mcp.session.decorators import get_session_hook_metadata, mcp_session_init

        @mcp_session_init()
        def my_init_hook() -> None:
            pass

        def regular_func() -> None:
            pass

        hooks = get_session_hook_metadata(my_init_hook)
        assert hooks["is_session_init"] is True
        assert hooks["is_session_cleanup"] is False

        hooks = get_session_hook_metadata(regular_func)
        assert hooks["is_session_init"] is False
        assert hooks["is_session_cleanup"] is False
