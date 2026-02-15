"""Retry utilities with exponential backoff."""

import asyncio
import random
import time
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Optional, Type, TypeVar, Union

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class RetryableError(Exception):
    """Custom exception to signal retryable failures."""

    pass


@dataclass
class RetryConfig:
    """Configuration for retry behavior with exponential backoff.

    Attributes:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds before first retry
        max_delay: Maximum delay in seconds between retries
        exponential_base: Base for exponential backoff calculation
        jitter: Whether to add randomness to prevent thundering herd
        retryable_exceptions: Tuple of exception types to retry on
    """

    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_exceptions: tuple[Type[Exception], ...] = (Exception,)

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number with exponential backoff.

        Args:
            attempt: Current attempt number (0-indexed)

        Returns:
            Delay in seconds to wait before retry
        """
        # Calculate exponential delay: initial_delay * (base ^ attempt)
        delay = min(
            self.initial_delay * (self.exponential_base**attempt),
            self.max_delay,
        )

        # Add jitter if enabled (randomize between 50% and 100% of delay)
        if self.jitter:
            delay = delay * (0.5 + random.random() * 0.5)

        return delay


def retry_with_backoff(
    config: Optional[RetryConfig] = None,
    retryable_exceptions: Optional[tuple[Type[Exception], ...]] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator for retrying synchronous functions with exponential backoff.

    Args:
        config: Retry configuration (uses defaults if None)
        retryable_exceptions: Tuple of exception types to retry on (overrides config)

    Returns:
        Decorated function with retry logic

    Example:
        @retry_with_backoff(RetryConfig(max_retries=5))
        def api_call():
            return requests.get("https://api.example.com")
    """
    if config is None:
        config = RetryConfig()

    if retryable_exceptions is not None:
        config = RetryConfig(
            max_retries=config.max_retries,
            initial_delay=config.initial_delay,
            max_delay=config.max_delay,
            exponential_base=config.exponential_base,
            jitter=config.jitter,
            retryable_exceptions=retryable_exceptions,
        )

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Optional[Exception] = None

            for attempt in range(config.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except config.retryable_exceptions as e:
                    last_exception = e

                    if attempt >= config.max_retries:
                        logger.error(
                            "Max retries exhausted",
                            function=func.__name__,
                            attempt=attempt + 1,
                            max_retries=config.max_retries,
                            error=str(e),
                        )
                        raise

                    delay = config.calculate_delay(attempt)
                    logger.warning(
                        "Retrying after failure",
                        function=func.__name__,
                        attempt=attempt + 1,
                        max_retries=config.max_retries,
                        delay_seconds=round(delay, 2),
                        error=str(e),
                    )
                    time.sleep(delay)

            # This should never be reached, but keeps type checker happy
            if last_exception:
                raise last_exception
            raise RuntimeError("Unexpected retry loop exit")

        return wrapper

    return decorator


def async_retry_with_backoff(
    config: Optional[RetryConfig] = None,
    retryable_exceptions: Optional[tuple[Type[Exception], ...]] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator for retrying async functions with exponential backoff.

    Args:
        config: Retry configuration (uses defaults if None)
        retryable_exceptions: Tuple of exception types to retry on (overrides config)

    Returns:
        Decorated async function with retry logic

    Example:
        @async_retry_with_backoff(RetryConfig(max_retries=5))
        async def api_call():
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.example.com") as resp:
                    return await resp.json()
    """
    if config is None:
        config = RetryConfig()

    if retryable_exceptions is not None:
        config = RetryConfig(
            max_retries=config.max_retries,
            initial_delay=config.initial_delay,
            max_delay=config.max_delay,
            exponential_base=config.exponential_base,
            jitter=config.jitter,
            retryable_exceptions=retryable_exceptions,
        )

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Optional[Exception] = None

            for attempt in range(config.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except config.retryable_exceptions as e:
                    last_exception = e

                    if attempt >= config.max_retries:
                        logger.error(
                            "Max retries exhausted",
                            function=func.__name__,
                            attempt=attempt + 1,
                            max_retries=config.max_retries,
                            error=str(e),
                        )
                        raise

                    delay = config.calculate_delay(attempt)
                    logger.warning(
                        "Retrying after failure",
                        function=func.__name__,
                        attempt=attempt + 1,
                        max_retries=config.max_retries,
                        delay_seconds=round(delay, 2),
                        error=str(e),
                    )
                    await asyncio.sleep(delay)

            # This should never be reached, but keeps type checker happy
            if last_exception:
                raise last_exception
            raise RuntimeError("Unexpected retry loop exit")

        return wrapper

    return decorator
