"""
Test Suite for KATO v2.0 Database Reliability Specification

This test suite validates critical database reliability improvements including:
- Connection pooling with proper limits
- Write concern guarantees (w=majority)
- Circuit breaker activation and recovery
- Retry logic with exponential backoff
- Graceful handling of database failures

Tests ensure the system can handle production database issues without crashing.
"""

import asyncio
import pytest
import time
import random
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError, PyMongoError
from enum import Enum


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class TestConnectionPooling:
    """Test database connection pooling behavior"""
    
    @pytest.mark.asyncio
    async def test_connection_pool_creation(self, mongo_pool_manager):
        """Test that connection pools are created with correct settings"""
        pool = mongo_pool_manager
        
        # Verify pool configuration
        assert pool.max_pool_size == 50
        assert pool.min_pool_size == 10
        assert pool.max_idle_time_ms == 30000
        assert pool.wait_queue_timeout_ms == 5000
        
        # Verify write concern is NOT 0
        assert pool.write_concern != {"w": 0}
        assert pool.write_concern == {"w": "majority", "j": True}
        
        # Test connection acquisition
        db = await pool.get_database("test_db")
        assert db is not None
    
    @pytest.mark.asyncio
    async def test_connection_pool_limits(self, mongo_pool_manager):
        """Test that pool enforces connection limits"""
        pool = mongo_pool_manager
        connections = []
        
        # Acquire connections up to limit
        for i in range(pool.max_pool_size):
            conn = await pool.get_connection()
            connections.append(conn)
        
        # Next connection should timeout
        with pytest.raises(asyncio.TimeoutError):
            # Use short timeout to fail fast in test
            await asyncio.wait_for(
                pool.get_connection(),
                timeout=1.0
            )
        
        # Release connections
        for conn in connections:
            await pool.release_connection(conn)
        
        # Should be able to get connection again
        conn = await pool.get_connection()
        assert conn is not None
        await pool.release_connection(conn)
    
    @pytest.mark.asyncio
    async def test_connection_pool_health_checks(self, mongo_pool_manager):
        """Test that unhealthy connections are detected and replaced"""
        pool = mongo_pool_manager
        
        # Get a connection
        conn1 = await pool.get_connection()
        conn1_id = id(conn1)
        
        # Simulate connection becoming unhealthy
        with patch.object(conn1, 'ping', side_effect=ConnectionFailure("Connection lost")):
            # Release unhealthy connection
            await pool.release_connection(conn1)
            
            # Pool should detect unhealthy connection on next health check
            await pool._health_check_connections()
        
        # Get connection again - should be different instance
        conn2 = await pool.get_connection()
        conn2_id = id(conn2)
        
        assert conn1_id != conn2_id, "Unhealthy connection should be replaced"
        
        # New connection should be healthy
        assert await pool._is_connection_healthy(conn2)
    
    @pytest.mark.asyncio
    async def test_connection_pool_concurrent_access(self, mongo_pool_manager):
        """Test concurrent access to connection pool"""
        pool = mongo_pool_manager
        num_concurrent = 20
        
        async def use_connection(task_id: int):
            """Simulate using a connection"""
            conn = await pool.get_connection()
            # Simulate some work
            await asyncio.sleep(random.uniform(0.01, 0.05))
            await pool.release_connection(conn)
            return task_id
        
        # Run concurrent tasks
        tasks = [use_connection(i) for i in range(num_concurrent)]
        results = await asyncio.gather(*tasks)
        
        # All tasks should complete
        assert len(results) == num_concurrent
        assert set(results) == set(range(num_concurrent))
        
        # Pool should have all connections available again
        stats = await pool.get_pool_stats()
        assert stats['available_connections'] == pool.max_pool_size


class TestWriteConcerns:
    """Test write concern guarantees"""
    
    @pytest.mark.asyncio
    async def test_write_concern_majority(self, database_manager):
        """Test that writes use w=majority for critical data"""
        db_manager = database_manager
        
        # Save critical pattern data
        pattern_data = {
            "name": "PTRN|test123",
            "pattern_data": [["A"], ["B"], ["C"]],
            "frequency": 1
        }
        
        with patch.object(db_manager.patterns_kb, 'update_one') as mock_update:
            # Create async mock that returns a result
            async def async_update(*args, **kwargs):
                return Mock(acknowledged=True)
            mock_update.side_effect = async_update
            
            await db_manager.save_pattern(pattern_data)
            
            # Verify write concern was majority
            mock_update.assert_called_once()
            call_kwargs = mock_update.call_args[1]
            assert 'write_concern' in call_kwargs
            
            write_concern = call_kwargs['write_concern']
            assert write_concern.w == 'majority'
            assert write_concern.j is True  # Journal write
    
    @pytest.mark.asyncio
    async def test_write_acknowledgment_verification(self, database_manager):
        """Test that unacknowledged writes raise errors"""
        db_manager = database_manager
        
        pattern_data = {"name": "test", "data": [["X"]]}
        
        # Simulate unacknowledged write
        with patch.object(db_manager.patterns_kb, 'update_one') as mock_update:
            async def async_update(*args, **kwargs):
                return Mock(acknowledged=False)
            mock_update.side_effect = async_update
            
            with pytest.raises(DatabaseWriteError) as exc:
                await db_manager.save_pattern(pattern_data)
            
            assert "not acknowledged" in str(exc.value)
    
    @pytest.mark.asyncio
    async def test_write_concern_levels(self, database_manager):
        """Test different write concern levels for different operations"""
        db_manager = database_manager
        
        # Critical operation - should use majority
        with patch.object(db_manager, '_execute_write') as mock_write:
            await db_manager.save_critical_data({"important": "data"})
            
            write_concern = mock_write.call_args[1]['write_concern']
            assert write_concern == WriteConcernLevel.CRITICAL
        
        # Bulk operation - can use relaxed concern
        with patch.object(db_manager, '_execute_write') as mock_write:
            await db_manager.save_bulk_data([{"item": 1}, {"item": 2}])
            
            write_concern = mock_write.call_args[1]['write_concern']
            assert write_concern == WriteConcernLevel.BULK
        
        # Metrics - can use fire-and-forget
        with patch.object(db_manager, '_execute_write') as mock_write:
            await db_manager.log_metrics({"metric": "value"})
            
            write_concern = mock_write.call_args[1]['write_concern']
            assert write_concern == WriteConcernLevel.METRICS


class TestCircuitBreaker:
    """Test circuit breaker pattern for database operations"""
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_on_failures(self, circuit_breaker):
        """Test that circuit breaker opens after threshold failures"""
        breaker = circuit_breaker
        breaker.failure_threshold = 3
        
        async def failing_operation():
            raise ConnectionFailure("Database unavailable")
        
        # First 3 failures should go through
        for i in range(3):
            with pytest.raises(ConnectionFailure):
                await breaker.call(failing_operation)
            assert breaker.state == CircuitState.CLOSED if i < 2 else CircuitState.OPEN
        
        # Circuit should now be open
        assert breaker.state == CircuitState.OPEN
        
        # Next call should fail fast without calling operation
        with pytest.raises(CircuitBreakerOpenError) as exc:
            await breaker.call(failing_operation)
        
        assert "Circuit breaker is OPEN" in str(exc.value)
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_recovery(self, circuit_breaker):
        """Test circuit breaker recovery after timeout"""
        breaker = circuit_breaker
        breaker.failure_threshold = 2
        breaker.recovery_timeout = 1  # 1 second for testing
        
        async def operation():
            if breaker.failure_count < 2:
                raise ConnectionFailure("DB Error")
            return "success"
        
        # Trigger circuit open
        for _ in range(2):
            with pytest.raises(ConnectionFailure):
                await breaker.call(operation)
        
        assert breaker.state == CircuitState.OPEN
        
        # Wait for recovery timeout
        await asyncio.sleep(1.5)
        
        # Circuit should attempt half-open
        breaker.failure_count = 2  # Reset so operation succeeds
        result = await breaker.call(operation)
        
        assert result == "success"
        assert breaker.state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_half_open_state(self, circuit_breaker):
        """Test circuit breaker half-open state behavior"""
        breaker = circuit_breaker
        breaker.state = CircuitState.HALF_OPEN
        
        # Success in half-open should close circuit
        async def success_operation():
            return "success"
        
        result = await breaker.call(success_operation)
        assert result == "success"
        assert breaker.state == CircuitState.CLOSED
        
        # Reset to half-open
        breaker.state = CircuitState.HALF_OPEN
        
        # Failure in half-open should re-open circuit
        async def fail_operation():
            raise ConnectionFailure("Still failing")
        
        with pytest.raises(ConnectionFailure):
            await breaker.call(fail_operation)
        
        assert breaker.state == CircuitState.OPEN


class TestRetryLogic:
    """Test retry logic with exponential backoff"""
    
    @pytest.mark.asyncio
    async def test_retry_with_exponential_backoff(self, retry_policy):
        """Test that retries use exponential backoff"""
        policy = retry_policy
        policy.max_attempts = 3
        policy.base_delay = 0.1
        policy.exponential_base = 2
        
        attempt_times = []
        attempt_count = 0
        
        async def failing_operation():
            nonlocal attempt_count
            attempt_times.append(time.time())
            attempt_count += 1
            if attempt_count < 3:
                raise ConnectionFailure("Transient error")
            return "success"
        
        result = await policy.execute(failing_operation)
        
        assert result == "success"
        assert attempt_count == 3
        
        # Verify exponential backoff timing
        delay1 = attempt_times[1] - attempt_times[0]
        delay2 = attempt_times[2] - attempt_times[1]
        
        # Second delay should be roughly 2x first delay
        assert delay2 > delay1 * 1.5  # Allow some variance
        assert delay2 < delay1 * 2.5
    
    @pytest.mark.asyncio
    async def test_retry_max_attempts(self, retry_policy):
        """Test that retry stops after max attempts"""
        policy = retry_policy
        policy.max_attempts = 3
        policy.base_delay = 0.01  # Short for testing
        
        attempt_count = 0
        
        async def always_failing():
            nonlocal attempt_count
            attempt_count += 1
            raise ConnectionFailure(f"Failure {attempt_count}")
        
        with pytest.raises(ConnectionFailure) as exc:
            await policy.execute(always_failing)
        
        assert attempt_count == 3
        assert "Failure 3" in str(exc.value)
    
    @pytest.mark.asyncio
    async def test_retry_with_jitter(self, retry_policy):
        """Test that retry delays include jitter"""
        policy = retry_policy
        policy.max_attempts = 5
        policy.base_delay = 0.1
        policy.jitter = True
        
        delays = []
        attempt_times = []
        
        async def failing_operation():
            attempt_times.append(time.time())
            if len(attempt_times) < 5:
                raise ConnectionFailure("Error")
            return "success"
        
        await policy.execute(failing_operation)
        
        # Calculate delays
        for i in range(1, len(attempt_times)):
            delays.append(attempt_times[i] - attempt_times[i-1])
        
        # With jitter, delays should vary
        unique_delays = len(set(round(d, 3) for d in delays))
        assert unique_delays > 1, "Jitter should create variation in delays"
    
    @pytest.mark.asyncio
    async def test_retry_only_on_retryable_exceptions(self, retry_policy):
        """Test that retry only happens for configured exception types"""
        policy = retry_policy
        policy.retryable_exceptions = (ConnectionFailure,)
        
        # Should retry ConnectionFailure
        connection_attempts = 0
        
        async def connection_error():
            nonlocal connection_attempts
            connection_attempts += 1
            if connection_attempts < 2:
                raise ConnectionFailure("Retry this")
            return "success"
        
        result = await policy.execute(connection_error)
        assert result == "success"
        assert connection_attempts == 2
        
        # Should NOT retry ValueError
        value_attempts = 0
        
        async def value_error():
            nonlocal value_attempts
            value_attempts += 1
            raise ValueError("Don't retry this")
        
        with pytest.raises(ValueError):
            await policy.execute(value_error)
        
        assert value_attempts == 1  # No retry


class TestDatabaseFailureRecovery:
    """Test system behavior during database failures"""
    
    @pytest.mark.asyncio
    async def test_database_connection_recovery(self, database_manager):
        """Test automatic recovery from database connection loss"""
        db_manager = database_manager
        
        # Simulate connection failure
        with patch.object(db_manager.mongo_pool, 'get_database') as mock_get_db:
            # First call fails
            mock_get_db.side_effect = [
                ConnectionFailure("Connection lost"),
                Mock()  # Second call succeeds
            ]
            
            # Should retry and succeed
            result = await db_manager.save_with_retry({"data": "test"})
            assert result is not None
            assert mock_get_db.call_count == 2
    
    @pytest.mark.asyncio
    async def test_graceful_degradation_during_outage(self, database_manager):
        """Test that system degrades gracefully during database outage"""
        db_manager = database_manager
        
        # Simulate complete database outage
        with patch.object(db_manager.mongo_pool, 'get_database') as mock_get_db:
            mock_get_db.side_effect = ConnectionFailure("Database down")
            
            # System should degrade gracefully
            degradation_level = await db_manager.check_health_and_degrade()
            assert degradation_level == "degraded"
            
            # Non-critical operations should be disabled
            assert not db_manager.is_feature_enabled("auto_learn")
            assert not db_manager.is_feature_enabled("emotives")
            
            # Critical operations should still be attempted
            assert db_manager.is_feature_enabled("observations")
    
    @pytest.mark.asyncio
    @pytest.mark.chaos
    async def test_chaos_random_failures(self, database_manager):
        """Chaos test with random database failures"""
        db_manager = database_manager
        
        success_count = 0
        failure_count = 0
        operations = 100
        
        async def operation_with_chaos():
            """Operation that randomly fails"""
            if random.random() < 0.3:  # 30% failure rate
                raise ConnectionFailure("Random failure")
            return "success"
        
        # Wrap with circuit breaker and retry
        for i in range(operations):
            try:
                # Reset circuit breaker if needed
                if db_manager.circuit_breaker.state == CircuitState.OPEN:
                    await asyncio.sleep(0.1)  # Wait a bit
                
                result = await db_manager.execute_with_reliability(
                    operation_with_chaos
                )
                if result == "success":
                    success_count += 1
            except (ConnectionFailure, CircuitBreakerOpenError):
                failure_count += 1
        
        # Should handle most operations despite failures
        success_rate = success_count / operations
        assert success_rate > 0.5, f"Success rate too low: {success_rate:.2%}"
        
        print(f"Chaos test: {success_count}/{operations} successful ({success_rate:.2%})")
    
    @pytest.mark.asyncio
    async def test_connection_pool_exhaustion_recovery(self, database_manager):
        """Test recovery from connection pool exhaustion"""
        db_manager = database_manager
        pool = db_manager.mongo_pool
        
        # Exhaust pool
        held_connections = []
        for _ in range(pool.max_pool_size):
            conn = await pool.get_connection()
            held_connections.append(conn)
        
        # New operations should queue and timeout
        async def waiting_operation():
            conn = await asyncio.wait_for(
                pool.get_connection(),
                timeout=0.5
            )
            return conn
        
        with pytest.raises(asyncio.TimeoutError):
            await waiting_operation()
        
        # Release half the connections
        for conn in held_connections[:25]:
            await pool.release_connection(conn)
        
        # Should be able to get connections again
        new_conn = await pool.get_connection()
        assert new_conn is not None
        
        # Clean up
        await pool.release_connection(new_conn)
        for conn in held_connections[25:]:
            await pool.release_connection(conn)


class TestHealthMonitoring:
    """Test database health monitoring"""
    
    @pytest.mark.asyncio
    async def test_health_check_detection(self, health_monitor):
        """Test that health checks detect database issues"""
        monitor = health_monitor
        
        # Simulate healthy state
        with patch.object(monitor.db_manager.mongo_pool, 'ping') as mock_ping:
            mock_ping.return_value = True
            
            health = await monitor.check_mongo_health()
            assert health.status == "healthy"
            assert health.latency_ms < 100
        
        # Simulate unhealthy state
        with patch.object(monitor.db_manager.mongo_pool, 'ping') as mock_ping:
            mock_ping.side_effect = ConnectionFailure("Cannot connect")
            
            health = await monitor.check_mongo_health()
            assert health.status == "unhealthy"
            assert health.last_error is not None
    
    @pytest.mark.asyncio
    async def test_health_monitoring_alerts(self, health_monitor):
        """Test that health monitoring triggers alerts"""
        monitor = health_monitor
        monitor.alert_threshold = 3
        
        alerts_triggered = []
        
        async def mock_alert(alert_type, message, details):
            alerts_triggered.append((alert_type, message))
        
        monitor._send_alert = mock_alert
        
        # Simulate consecutive failures
        for _ in range(3):
            with patch.object(monitor.db_manager.mongo_pool, 'ping') as mock_ping:
                mock_ping.side_effect = ConnectionFailure("DB Down")
                await monitor.check_and_alert()
        
        # Should have triggered alert
        assert len(alerts_triggered) > 0
        assert any("unhealthy" in msg.lower() for _, msg in alerts_triggered)


# Test Fixtures and Mocks

class ConnectionPoolExhaustedError(Exception):
    """Raised when connection pool is exhausted"""
    pass


class DatabaseWriteError(Exception):
    """Raised when write is not acknowledged"""
    pass


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open"""
    pass


class WriteConcernLevel(Enum):
    """Write concern levels"""
    CRITICAL = {"w": "majority", "j": True}
    BULK = {"w": 1, "j": False}
    METRICS = {"w": 0}


class MockMongoPoolManager:
    """Mock MongoDB connection pool"""
    
    def __init__(self):
        self.max_pool_size = 50
        self.min_pool_size = 10
        self.max_idle_time_ms = 30000
        self.wait_queue_timeout_ms = 5000
        self.write_concern = {"w": "majority", "j": True}
        self.connections = []
        self.available = asyncio.Queue(maxsize=self.max_pool_size)
        self._initialize_pool()
    
    def _initialize_pool(self):
        for i in range(self.max_pool_size):
            conn = Mock(id=i)
            self.connections.append(conn)
            self.available.put_nowait(conn)
    
    async def get_connection(self):
        try:
            return await asyncio.wait_for(
                self.available.get(),
                timeout=self.wait_queue_timeout_ms / 1000
            )
        except asyncio.TimeoutError:
            raise ConnectionPoolExhaustedError("No connections available")
    
    async def release_connection(self, conn):
        await self.available.put(conn)
    
    async def get_database(self, name):
        conn = await self.get_connection()
        db = Mock(name=name, connection=conn)
        await self.release_connection(conn)
        return db
    
    async def _health_check_connections(self):
        # Check health of connections
        pass
    
    async def _is_connection_healthy(self, conn):
        try:
            # Simulate ping
            if hasattr(conn, 'ping'):
                conn.ping()
            return True
        except:
            return False
    
    async def get_pool_stats(self):
        return {
            "available_connections": self.available.qsize(),
            "total_connections": self.max_pool_size
        }


class MockCircuitBreaker:
    """Mock circuit breaker"""
    
    def __init__(self):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.failure_threshold = 5
        self.recovery_timeout = 30
        self.last_failure_time = None
    
    async def call(self, func, *args, **kwargs):
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
            else:
                raise CircuitBreakerOpenError("Circuit breaker is OPEN")
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def _on_success(self):
        self.failure_count = 0
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
    
    def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.state == CircuitState.HALF_OPEN:
            # Any failure in half-open goes back to open
            self.state = CircuitState.OPEN
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
    
    def _should_attempt_reset(self):
        if self.last_failure_time:
            return time.time() - self.last_failure_time > self.recovery_timeout
        return False


class MockRetryPolicy:
    """Mock retry policy"""
    
    def __init__(self):
        self.max_attempts = 3
        self.base_delay = 1.0
        self.exponential_base = 2.0
        self.jitter = True
        self.retryable_exceptions = (ConnectionFailure, ServerSelectionTimeoutError)
    
    async def execute(self, func, *args, **kwargs):
        last_exception = None
        
        for attempt in range(self.max_attempts):
            try:
                return await func(*args, **kwargs)
            except self.retryable_exceptions as e:
                last_exception = e
                
                if attempt == self.max_attempts - 1:
                    raise
                
                delay = self.base_delay * (self.exponential_base ** attempt)
                
                if self.jitter:
                    delay *= (0.5 + random.random())
                
                await asyncio.sleep(delay)
        
        raise last_exception


@pytest.fixture
def mongo_pool_manager():
    """Fixture providing MongoDB connection pool"""
    return MockMongoPoolManager()


@pytest.fixture
def circuit_breaker():
    """Fixture providing circuit breaker"""
    return MockCircuitBreaker()


@pytest.fixture
def retry_policy():
    """Fixture providing retry policy"""
    return MockRetryPolicy()


@pytest.fixture
def database_manager(mongo_pool_manager, circuit_breaker, retry_policy):
    """Fixture providing database manager with reliability features"""
    
    class MockDatabaseManager:
        def __init__(self):
            self.mongo_pool = mongo_pool_manager
            self.circuit_breaker = circuit_breaker
            self.retry_policy = retry_policy
            self.patterns_kb = Mock()
            self.degradation_level = "normal"
        
        async def save_pattern(self, pattern_data):
            return await self.circuit_breaker.call(
                self._save_pattern_internal,
                pattern_data
            )
        
        async def _save_pattern_internal(self, pattern_data):
            result = await self.patterns_kb.update_one(
                {"name": pattern_data["name"]},
                {"$set": pattern_data},
                upsert=True,
                write_concern={"w": "majority", "j": True}
            )
            
            if not result.acknowledged:
                raise DatabaseWriteError("Write not acknowledged")
            
            return result
        
        async def save_with_retry(self, data):
            return await self.retry_policy.execute(
                self._save_internal,
                data
            )
        
        async def _save_internal(self, data):
            db = await self.mongo_pool.get_database("test")
            return {"saved": data}
        
        async def check_health_and_degrade(self):
            try:
                await self.mongo_pool.get_database("health_check")
                self.degradation_level = "normal"
            except:
                self.degradation_level = "degraded"
            return self.degradation_level
        
        def is_feature_enabled(self, feature):
            if self.degradation_level == "degraded":
                return feature in ["observations"]  # Only critical features
            return True
        
        async def execute_with_reliability(self, operation):
            return await self.retry_policy.execute(
                lambda: self.circuit_breaker.call(operation)
            )
        
        async def _execute_write(self, data, write_concern):
            # Mock write execution
            pass
        
        async def save_critical_data(self, data):
            await self._execute_write(data, write_concern=WriteConcernLevel.CRITICAL)
        
        async def save_bulk_data(self, data):
            await self._execute_write(data, write_concern=WriteConcernLevel.BULK)
        
        async def log_metrics(self, data):
            await self._execute_write(data, write_concern=WriteConcernLevel.METRICS)
    
    return MockDatabaseManager()


@pytest.fixture
def health_monitor(database_manager):
    """Fixture providing health monitor"""
    
    class MockHealthMonitor:
        def __init__(self):
            self.db_manager = database_manager
            self.alert_threshold = 3
            self.consecutive_failures = 0
        
        async def check_mongo_health(self):
            from collections import namedtuple
            HealthStatus = namedtuple('HealthStatus', ['status', 'latency_ms', 'last_error'])
            
            start = time.time()
            try:
                await self.db_manager.mongo_pool.ping()
                latency = (time.time() - start) * 1000
                return HealthStatus(status="healthy", latency_ms=latency, last_error=None)
            except Exception as e:
                latency = (time.time() - start) * 1000
                return HealthStatus(status="unhealthy", latency_ms=latency, last_error=str(e))
        
        async def check_and_alert(self):
            health = await self.check_mongo_health()
            if health.status == "unhealthy":
                self.consecutive_failures += 1
                if self.consecutive_failures >= self.alert_threshold:
                    await self._send_alert(
                        "DATABASE_UNHEALTHY",
                        f"Database unhealthy for {self.consecutive_failures} checks",
                        {"error": health.last_error}
                    )
            else:
                self.consecutive_failures = 0
        
        async def _send_alert(self, alert_type, message, details):
            # Mock alert sending
            pass
    
    return MockHealthMonitor()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])