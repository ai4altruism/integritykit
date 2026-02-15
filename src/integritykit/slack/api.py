"""Slack API client wrapper with retry logic."""

from typing import Any, Optional

import structlog
from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from integritykit.utils.retry import RetryConfig, RetryableError, async_retry_with_backoff

logger = structlog.get_logger(__name__)


class SlackAPIClient:
    """Slack API client with built-in retry logic and error handling.

    This wrapper provides resilient API calls with exponential backoff for:
    - 5xx server errors
    - Rate limiting (429 errors)
    - Transient network failures

    4xx client errors (except 429) are not retried as they indicate
    invalid requests that won't succeed on retry.
    """

    def __init__(
        self,
        token: str,
        retry_config: Optional[RetryConfig] = None,
    ):
        """Initialize Slack API client with retry configuration.

        Args:
            token: Slack bot token (xoxb-...)
            retry_config: Retry configuration (uses defaults if None)
        """
        self.client = AsyncWebClient(token=token)
        self.retry_config = retry_config or RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            max_delay=60.0,
            exponential_base=2.0,
            jitter=True,
        )

    def _should_retry(self, error: SlackApiError) -> bool:
        """Determine if a Slack API error should be retried.

        Args:
            error: Slack API error

        Returns:
            True if error is retryable, False otherwise
        """
        # Get status code from error
        status_code = error.response.status_code if error.response else None

        if status_code is None:
            # Network errors without status code - retry
            logger.debug(
                "Network error without status code, will retry",
                error=str(error),
            )
            return True

        # Retry on rate limiting (429)
        if status_code == 429:
            logger.debug(
                "Rate limit error, will retry",
                status_code=status_code,
                retry_after=error.response.headers.get("Retry-After"),
            )
            return True

        # Retry on 5xx server errors
        if 500 <= status_code < 600:
            logger.debug(
                "Server error, will retry",
                status_code=status_code,
            )
            return True

        # Don't retry 4xx client errors (except 429)
        if 400 <= status_code < 500:
            logger.debug(
                "Client error, will not retry",
                status_code=status_code,
                error=error.response.get("error"),
            )
            return False

        # Retry other errors
        return True

    def _get_retry_delay(self, error: SlackApiError, attempt: int) -> float:
        """Calculate retry delay, respecting Retry-After header if present.

        Args:
            error: Slack API error
            attempt: Current retry attempt (0-indexed)

        Returns:
            Delay in seconds before retry
        """
        # Check for Retry-After header (from rate limiting)
        if error.response and error.response.headers:
            retry_after = error.response.headers.get("Retry-After")
            if retry_after:
                try:
                    # Retry-After is in seconds
                    delay = float(retry_after)
                    logger.info(
                        "Using Retry-After header for delay",
                        retry_after_seconds=delay,
                    )
                    return delay
                except (ValueError, TypeError):
                    logger.warning(
                        "Invalid Retry-After header value",
                        retry_after=retry_after,
                    )

        # Fall back to exponential backoff
        return self.retry_config.calculate_delay(attempt)

    async def _retry_api_call(
        self,
        func: Any,
        operation_name: str,
        **kwargs: Any,
    ) -> Any:
        """Execute Slack API call with retry logic.

        Args:
            func: Slack client method to call
            operation_name: Name of operation for logging
            **kwargs: Arguments to pass to Slack API method

        Returns:
            Response from Slack API

        Raises:
            SlackApiError: If all retries exhausted or non-retryable error
        """
        last_exception: Optional[SlackApiError] = None

        for attempt in range(self.retry_config.max_retries + 1):
            try:
                logger.debug(
                    "Calling Slack API",
                    operation=operation_name,
                    attempt=attempt + 1,
                    **kwargs,
                )
                result = await func(**kwargs)
                logger.debug(
                    "Slack API call succeeded",
                    operation=operation_name,
                    attempt=attempt + 1,
                )
                return result

            except SlackApiError as e:
                last_exception = e

                # Check if error is retryable
                if not self._should_retry(e):
                    logger.error(
                        "Non-retryable Slack API error",
                        operation=operation_name,
                        error=str(e),
                        status_code=e.response.status_code if e.response else None,
                    )
                    raise

                # Check if we've exhausted retries
                if attempt >= self.retry_config.max_retries:
                    logger.error(
                        "Max retries exhausted for Slack API call",
                        operation=operation_name,
                        attempt=attempt + 1,
                        max_retries=self.retry_config.max_retries,
                        error=str(e),
                    )
                    raise

                # Calculate delay and retry
                delay = self._get_retry_delay(e, attempt)
                logger.warning(
                    "Retrying Slack API call after failure",
                    operation=operation_name,
                    attempt=attempt + 1,
                    max_retries=self.retry_config.max_retries,
                    delay_seconds=round(delay, 2),
                    error=str(e),
                    status_code=e.response.status_code if e.response else None,
                )

                # Import asyncio here to avoid circular imports
                import asyncio

                await asyncio.sleep(delay)

        # This should never be reached, but keeps type checker happy
        if last_exception:
            raise last_exception
        raise RuntimeError("Unexpected retry loop exit")

    async def get_permalink(
        self,
        channel: str,
        message_ts: str,
    ) -> str:
        """Get permalink for a Slack message with retry logic.

        Args:
            channel: Slack channel ID
            message_ts: Slack message timestamp

        Returns:
            Permalink URL

        Raises:
            SlackApiError: If API call fails after retries
        """
        result = await self._retry_api_call(
            self.client.chat_getPermalink,
            "get_permalink",
            channel=channel,
            message_ts=message_ts,
        )
        return result["permalink"]

    async def get_user_info(self, user_id: str) -> dict[str, Any]:
        """Get Slack user information with retry logic.

        Args:
            user_id: Slack user ID

        Returns:
            User information dictionary

        Raises:
            SlackApiError: If API call fails after retries
        """
        result = await self._retry_api_call(
            self.client.users_info,
            "get_user_info",
            user=user_id,
        )
        return result["user"]

    async def get_channel_info(self, channel_id: str) -> dict[str, Any]:
        """Get Slack channel information with retry logic.

        Args:
            channel_id: Slack channel ID

        Returns:
            Channel information dictionary

        Raises:
            SlackApiError: If API call fails after retries
        """
        result = await self._retry_api_call(
            self.client.conversations_info,
            "get_channel_info",
            channel=channel_id,
        )
        return result["channel"]

    async def post_message(
        self,
        channel: str,
        text: Optional[str] = None,
        blocks: Optional[list[dict[str, Any]]] = None,
        thread_ts: Optional[str] = None,
    ) -> dict[str, Any]:
        """Post a message to Slack with retry logic.

        Args:
            channel: Slack channel ID
            text: Message text (required if blocks not provided)
            blocks: Message blocks (required if text not provided)
            thread_ts: Thread timestamp to reply in thread

        Returns:
            Message response dictionary

        Raises:
            SlackApiError: If API call fails after retries
        """
        kwargs: dict[str, Any] = {"channel": channel}

        if text is not None:
            kwargs["text"] = text
        if blocks is not None:
            kwargs["blocks"] = blocks
        if thread_ts is not None:
            kwargs["thread_ts"] = thread_ts

        result = await self._retry_api_call(
            self.client.chat_postMessage,
            "post_message",
            **kwargs,
        )
        return result
