"""Unit tests for retry utilities with exponential backoff."""

import asyncio
import time
import pytest
from unittest.mock import Mock, patch

from integritykit.utils.retry import (
    RetryConfig,
    RetryableError,
    retry_with_backoff,
    async_retry_with_backoff,
)


@pytest.mark.unit
class TestRetryConfig:
    """Test RetryConfig dataclass."""

    def test_default_config(self):
        """Test RetryConfig with default values."""
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.initial_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0
        assert config.jitter is True
        assert config.retryable_exceptions == (Exception,)

    def test_custom_config(self):
        """Test RetryConfig with custom values."""
        config = RetryConfig(
            max_retries=5,
            initial_delay=2.0,
            max_delay=120.0,
            exponential_base=3.0,
            jitter=False,
            retryable_exceptions=(ValueError, ConnectionError),
        )
        assert config.max_retries == 5
        assert config.initial_delay == 2.0
        assert config.max_delay == 120.0
        assert config.exponential_base == 3.0
        assert config.jitter is False
        assert config.retryable_exceptions == (ValueError, ConnectionError)

    def test_calculate_delay_no_jitter(self):
        """Test delay calculation without jitter."""
        config = RetryConfig(
            initial_delay=1.0,
            exponential_base=2.0,
            max_delay=60.0,
            jitter=False,
        )

        # Attempt 0: 1 * (2^0) = 1
        assert config.calculate_delay(0) == 1.0

        # Attempt 1: 1 * (2^1) = 2
        assert config.calculate_delay(1) == 2.0

        # Attempt 2: 1 * (2^2) = 4
        assert config.calculate_delay(2) == 4.0

        # Attempt 3: 1 * (2^3) = 8
        assert config.calculate_delay(3) == 8.0

    def test_calculate_delay_with_max(self):
        """Test delay calculation respects max_delay."""
        config = RetryConfig(
            initial_delay=10.0,
            exponential_base=2.0,
            max_delay=30.0,
            jitter=False,
        )

        # Attempt 5: 10 * (2^5) = 320, but capped at 30
        assert config.calculate_delay(5) == 30.0

    def test_calculate_delay_with_jitter(self):
        """Test delay calculation with jitter adds randomness."""
        config = RetryConfig(
            initial_delay=10.0,
            exponential_base=2.0,
            max_delay=100.0,
            jitter=True,
        )

        # With jitter, delay should be between 50% and 100% of base delay
        delay = config.calculate_delay(0)
        assert 5.0 <= delay <= 10.0

        # Run multiple times to ensure randomness
        delays = [config.calculate_delay(1) for _ in range(10)]
        assert len(set(delays)) > 1  # Should produce different values


@pytest.mark.unit
class TestRetryWithBackoff:
    """Test synchronous retry_with_backoff decorator."""

    def test_successful_first_attempt(self):
        """Test function succeeds on first attempt."""
        mock_func = Mock(return_value="success")
        decorated = retry_with_backoff()(mock_func)

        result = decorated()
        assert result == "success"
        assert mock_func.call_count == 1

    def test_retry_on_retryable_exception(self):
        """Test function retries on retryable exception."""
        mock_func = Mock(side_effect=[ValueError("error 1"), ValueError("error 2"), "success"], __name__="mock_func")
        config = RetryConfig(max_retries=3, initial_delay=0.01, jitter=False)
        decorated = retry_with_backoff(config)(mock_func)

        result = decorated()
        assert result == "success"
        assert mock_func.call_count == 3

    def test_max_retries_exhausted(self):
        """Test function raises after max retries exhausted."""
        mock_func = Mock(side_effect=ValueError("persistent error"), __name__="mock_func")
        config = RetryConfig(max_retries=2, initial_delay=0.01, jitter=False)
        decorated = retry_with_backoff(config)(mock_func)

        with pytest.raises(ValueError, match="persistent error"):
            decorated()

        # Should be called max_retries + 1 times (initial + 2 retries)
        assert mock_func.call_count == 3

    def test_non_retryable_exception_not_retried(self):
        """Test non-retryable exceptions are raised immediately."""
        mock_func = Mock(side_effect=TypeError("non-retryable"))
        config = RetryConfig(
            max_retries=3,
            initial_delay=0.01,
            retryable_exceptions=(ValueError,),
        )
        decorated = retry_with_backoff(config)(mock_func)

        with pytest.raises(TypeError, match="non-retryable"):
            decorated()

        # Should only be called once
        assert mock_func.call_count == 1

    def test_custom_retryable_exceptions(self):
        """Test custom retryable exceptions override config."""
        mock_func = Mock(side_effect=[ConnectionError("error"), "success"], __name__="mock_func")
        decorated = retry_with_backoff(
            retryable_exceptions=(ConnectionError,)
        )(mock_func)

        result = decorated()
        assert result == "success"
        assert mock_func.call_count == 2

    @patch("time.sleep")
    def test_exponential_backoff_delay(self, mock_sleep):
        """Test exponential backoff delays are applied."""
        mock_func = Mock(side_effect=[ValueError(), ValueError(), "success"], __name__="mock_func")
        config = RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            exponential_base=2.0,
            jitter=False,
        )
        decorated = retry_with_backoff(config)(mock_func)

        result = decorated()
        assert result == "success"

        # Should sleep twice (between attempts)
        assert mock_sleep.call_count == 2
        # First retry: 1 * (2^0) = 1.0
        assert mock_sleep.call_args_list[0][0][0] == 1.0
        # Second retry: 1 * (2^1) = 2.0
        assert mock_sleep.call_args_list[1][0][0] == 2.0


@pytest.mark.unit
@pytest.mark.asyncio
class TestAsyncRetryWithBackoff:
    """Test async retry_with_backoff decorator."""

    async def test_async_successful_first_attempt(self):
        """Test async function succeeds on first attempt."""
        async def async_func():
            return "success"

        decorated = async_retry_with_backoff()(async_func)
        result = await decorated()
        assert result == "success"

    async def test_async_retry_on_retryable_exception(self):
        """Test async function retries on retryable exception."""
        call_count = 0

        async def async_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError(f"error {call_count}")
            return "success"

        config = RetryConfig(max_retries=3, initial_delay=0.01, jitter=False)
        decorated = async_retry_with_backoff(config)(async_func)

        result = await decorated()
        assert result == "success"
        assert call_count == 3

    async def test_async_max_retries_exhausted(self):
        """Test async function raises after max retries exhausted."""
        async def async_func():
            raise ValueError("persistent error")

        config = RetryConfig(max_retries=2, initial_delay=0.01, jitter=False)
        decorated = async_retry_with_backoff(config)(async_func)

        with pytest.raises(ValueError, match="persistent error"):
            await decorated()

    async def test_async_non_retryable_exception_not_retried(self):
        """Test async non-retryable exceptions are raised immediately."""
        call_count = 0

        async def async_func():
            nonlocal call_count
            call_count += 1
            raise TypeError("non-retryable")

        config = RetryConfig(
            max_retries=3,
            initial_delay=0.01,
            retryable_exceptions=(ValueError,),
        )
        decorated = async_retry_with_backoff(config)(async_func)

        with pytest.raises(TypeError, match="non-retryable"):
            await decorated()

        assert call_count == 1

    @patch("asyncio.sleep")
    async def test_async_exponential_backoff_delay(self, mock_sleep):
        """Test async exponential backoff delays are applied."""
        call_count = 0

        async def async_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError(f"error {call_count}")
            return "success"

        # Make mock_sleep async coroutine
        async def mock_async_sleep(delay):
            pass

        mock_sleep.side_effect = mock_async_sleep

        config = RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            exponential_base=2.0,
            jitter=False,
        )
        decorated = async_retry_with_backoff(config)(async_func)

        result = await decorated()
        assert result == "success"

        # Should sleep twice (between attempts)
        assert mock_sleep.call_count == 2
        # First retry: 1 * (2^0) = 1.0
        assert mock_sleep.call_args_list[0][0][0] == 1.0
        # Second retry: 1 * (2^1) = 2.0
        assert mock_sleep.call_args_list[1][0][0] == 2.0

    async def test_async_custom_retryable_exceptions(self):
        """Test async custom retryable exceptions override config."""
        call_count = 0

        async def async_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("error")
            return "success"

        decorated = async_retry_with_backoff(
            retryable_exceptions=(ConnectionError,)
        )(async_func)

        result = await decorated()
        assert result == "success"
        assert call_count == 2


@pytest.mark.unit
class TestRetryableError:
    """Test RetryableError exception."""

    def test_retryable_error_is_exception(self):
        """Test RetryableError is an Exception."""
        error = RetryableError("test error")
        assert isinstance(error, Exception)
        assert str(error) == "test error"

    def test_retry_on_retryable_error(self):
        """Test retry works with RetryableError."""
        mock_func = Mock(side_effect=[RetryableError("error"), "success"], __name__="mock_func")
        config = RetryConfig(
            max_retries=2,
            initial_delay=0.01,
            retryable_exceptions=(RetryableError,),
        )
        decorated = retry_with_backoff(config)(mock_func)

        result = decorated()
        assert result == "success"
        assert mock_func.call_count == 2
