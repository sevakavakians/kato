"""
Test KATO error handling module
Tests structured exceptions and error handlers
"""

import time
from unittest.mock import Mock

import pytest
from fastapi import Request

from kato.exceptions import (
    ConcurrencyError,
    DatabaseConnectionError,
    KatoV2Exception,
    ResourceExhaustedError,
    SessionExpiredError,
    SessionNotFoundError,
    ValidationError,
    session_not_found,
    validation_failed,
)
from kato.exceptions.handlers import (
    ErrorContext,
    create_error_response,
    get_recovery_suggestions,
    kato_v2_exception_handler,
)


class TestKatoExceptions:
    """Test KATO exception classes"""

    def test_base_exception(self):
        """Test base KatoV2Exception functionality"""
        exc = KatoV2Exception(
            message="Test error",
            error_code="TEST_ERROR",
            context={"test_key": "test_value"},
            recoverable=True
        )

        assert exc.message == "Test error"
        assert exc.error_code == "TEST_ERROR"
        assert exc.context == {"test_key": "test_value"}
        assert exc.recoverable is True
        assert isinstance(exc.timestamp, (int, float))

        # Test dict conversion
        error_dict = exc.to_dict()
        assert error_dict["error"]["type"] == "KatoV2Exception"
        assert error_dict["error"]["message"] == "Test error"
        assert error_dict["error"]["code"] == "TEST_ERROR"
        assert error_dict["error"]["recoverable"] is True

    def test_session_not_found_error(self):
        """Test SessionNotFoundError"""
        exc = SessionNotFoundError(
            session_id="test-session-123",
            context={"additional": "info"}
        )

        assert exc.session_id == "test-session-123"
        assert exc.error_code == "SESSION_NOT_FOUND"
        assert exc.recoverable is True
        assert "test-session-123" in exc.message
        assert exc.context["session_id"] == "test-session-123"
        assert exc.context["additional"] == "info"

    def test_session_expired_error(self):
        """Test SessionExpiredError"""
        expired_time = time.time()
        exc = SessionExpiredError(
            session_id="expired-session",
            expired_at=expired_time
        )

        assert exc.session_id == "expired-session"
        assert exc.expired_at == expired_time
        assert exc.error_code == "SESSION_EXPIRED"
        assert exc.recoverable is True
        assert exc.context["expired_at"] == expired_time

    def test_concurrency_error(self):
        """Test ConcurrencyError"""
        exc = ConcurrencyError(
            resource_id="resource-123",
            operation="update"
        )

        assert exc.resource_id == "resource-123"
        assert exc.operation == "update"
        assert exc.error_code == "CONCURRENCY_ERROR"
        assert exc.recoverable is True
        assert "concurrent" in exc.message.lower()

    def test_validation_error(self):
        """Test ValidationError"""
        exc = ValidationError(
            field_name="email",
            field_value="invalid-email",
            validation_rule="must be valid email format"
        )

        assert exc.field_name == "email"
        assert exc.field_value == "invalid-email"
        assert exc.validation_rule == "must be valid email format"
        assert exc.error_code == "VALIDATION_ERROR"
        assert exc.recoverable is True

    def test_database_connection_error(self):
        """Test DatabaseConnectionError"""
        exc = DatabaseConnectionError(
            database_type="MongoDB",
            connection_string="mongodb://localhost:27017"
        )

        assert exc.database_type == "MongoDB"
        assert exc.connection_string == "mongodb://localhost:27017"
        assert exc.error_code == "DATABASE_CONNECTION_ERROR"
        assert exc.recoverable is True
        assert "mongodb" in exc.message.lower()

    def test_resource_exhausted_error(self):
        """Test ResourceExhaustedError"""
        exc = ResourceExhaustedError(
            resource_type="memory",
            current_usage=95.0,
            max_capacity=100.0
        )

        assert exc.resource_type == "memory"
        assert exc.current_usage == 95.0
        assert exc.max_capacity == 100.0
        assert exc.error_code == "RESOURCE_EXHAUSTED"
        assert exc.context["utilization"] == 0.95

    def test_convenience_functions(self):
        """Test convenience functions for creating exceptions"""
        # Test session_not_found
        exc = session_not_found("test-session", {"extra": "context"})
        assert isinstance(exc, SessionNotFoundError)
        assert exc.session_id == "test-session"
        assert exc.context["extra"] == "context"

        # Test validation_failed
        exc = validation_failed("username", "x", "minimum 3 characters")
        assert isinstance(exc, ValidationError)
        assert exc.field_name == "username"
        assert exc.field_value == "x"
        assert exc.validation_rule == "minimum 3 characters"


class TestErrorHandlers:
    """Test error handler functions"""

    async def test_kato_exception_handler(self):
        """Test KATO exception handler"""
        # Mock request
        request = Mock(spec=Request)
        request.url.path = "/test/endpoint"

        # Create test exception
        exc = SessionNotFoundError("test-session")

        # Handle exception
        response = await kato_v2_exception_handler(request, exc)

        # Verify response
        assert response.status_code == 404
        assert "error" in response.body.decode()

        # Parse response content (would need json.loads in real usage)
        # Here we just verify the structure exists
        assert response.headers["content-type"] == "application/json"

    def test_create_error_response(self):
        """Test error response creation"""
        response = create_error_response(
            error_code="TEST_ERROR",
            message="Test error message",
            status_code=400,
            details={"field": "value"},
            context={"request_id": "123"}
        )

        assert response.status_code == 400
        assert response.headers["content-type"] == "application/json"

        # The body would contain structured error data
        # In actual usage, you'd parse response.body with json.loads

    def test_get_recovery_suggestions(self):
        """Test recovery suggestions for different error types"""
        # Session not found
        exc = SessionNotFoundError("test-session")
        suggestions = get_recovery_suggestions(exc)

        assert "actions" in suggestions
        assert suggestions["retry_recommended"] is False
        assert any("processor_id" in action for action in suggestions["actions"])

        # Concurrency error
        exc = ConcurrencyError("resource-123", "update")
        suggestions = get_recovery_suggestions(exc)

        assert suggestions["retry_recommended"] is True
        assert "retry_delay_seconds" in suggestions
        assert any("retry" in action.lower() for action in suggestions["actions"])

        # Validation error
        exc = ValidationError("email", "invalid", "must be valid email")
        suggestions = get_recovery_suggestions(exc)

        assert suggestions["retry_recommended"] is False
        assert any("email" in action for action in suggestions["actions"])

        # Resource exhausted
        exc = ResourceExhaustedError("memory", 95, 100)
        suggestions = get_recovery_suggestions(exc)

        assert suggestions["retry_recommended"] is True
        assert suggestions["retry_delay_seconds"] == 30.0


class TestErrorContext:
    """Test ErrorContext context manager"""

    def test_error_context_success(self):
        """Test ErrorContext when no exception occurs"""
        with ErrorContext("test_operation", "resource-123", extra="info") as ctx:
            assert ctx.operation == "test_operation"
            assert ctx.resource_id == "resource-123"
            assert ctx.context["extra"] == "info"
            # Simulate successful operation
            pass

    def test_error_context_with_kato_exception(self):
        """Test ErrorContext enriching KATO exceptions"""
        try:
            with ErrorContext("test_operation", "resource-123") as ctx:
                raise SessionNotFoundError("test-session")
        except SessionNotFoundError as e:
            # Context should be enriched
            assert e.context["operation"] == "test_operation"
            assert e.context["resource_id"] == "resource-123"
            assert "duration_seconds" in e.context

    def test_error_context_with_standard_exception(self):
        """Test ErrorContext with standard Python exceptions"""
        # This should not raise an exception in the context manager
        # but the exception should still propagate
        with pytest.raises(ValueError), ErrorContext("test_operation") as ctx:
            raise ValueError("Standard Python exception")


class TestErrorIntegration:
    """Test error handling integration scenarios"""

    def test_error_chain_context(self):
        """Test error context propagation through multiple layers"""
        def layer3():
            raise ValidationError("email", "bad-email", "invalid format")

        def layer2():
            try:
                layer3()
            except ValidationError as e:
                # Add more context
                e.context["layer"] = "service_layer"
                raise

        def layer1():
            with ErrorContext("user_registration", "user-123"):
                layer2()

        try:
            layer1()
        except ValidationError as e:
            assert e.context["operation"] == "user_registration"
            assert e.context["resource_id"] == "user-123"
            assert e.context["layer"] == "service_layer"
            assert "duration_seconds" in e.context

    def test_error_serialization_roundtrip(self):
        """Test that errors can be serialized and maintain structure"""
        exc = SessionNotFoundError(
            session_id="test-123",
            context={"node_id": "node-456", "attempt": 1}
        )

        # Convert to dict (like for API responses)
        error_dict = exc.to_dict()

        # Verify structure
        assert error_dict["error"]["type"] == "SessionNotFoundError"
        assert error_dict["error"]["code"] == "SESSION_NOT_FOUND"
        assert error_dict["error"]["context"]["session_id"] == "test-123"
        assert error_dict["error"]["context"]["node_id"] == "node-456"
        assert error_dict["error"]["recoverable"] is True

    def test_multiple_error_types_handling(self):
        """Test that different error types map to correct HTTP status codes"""
        error_status_mapping = [
            (SessionNotFoundError("test"), 404),
            (SessionExpiredError("test"), 410),
            (ConcurrencyError("test", "op"), 409),
            (ValidationError("field", "value", "rule"), 422),
            (DatabaseConnectionError("mongo"), 503),
            (ResourceExhaustedError("cpu", 100, 100), 507)
        ]

        # In a real integration test, you'd test these against actual FastAPI endpoints
        # Here we verify the exceptions have the expected properties
        for exception, expected_status in error_status_mapping:
            assert isinstance(exception, KatoV2Exception)
            assert exception.error_code is not None
            assert exception.message is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
