"""Unit tests for Slack API client wrapper.

Tests:
- Retry logic with exponential backoff
- _should_retry() for 429/5xx errors
- _get_retry_delay() with Retry-After header support
- API methods: get_permalink, get_user_info, get_channel_info, post_message
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from slack_sdk.errors import SlackApiError

from integritykit.slack.api import SlackAPIClient
from integritykit.utils.retry import RetryConfig


# ============================================================================
# Test Fixtures
# ============================================================================


def make_slack_error(
    status_code: int | None = None,
    error_message: str = "test_error",
    retry_after: str | None = None,
) -> SlackApiError:
    """Create a mock SlackApiError with configurable status and headers."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.get.return_value = error_message

    if retry_after:
        mock_response.headers = {"Retry-After": retry_after}
    else:
        mock_response.headers = {}

    error = SlackApiError(
        message=error_message,
        response=mock_response,
    )
    return error


def make_mock_async_web_client():
    """Create a mock AsyncWebClient with async methods."""
    mock_client = MagicMock()
    mock_client.chat_getPermalink = AsyncMock()
    mock_client.users_info = AsyncMock()
    mock_client.conversations_info = AsyncMock()
    mock_client.chat_postMessage = AsyncMock()
    return mock_client


# ============================================================================
# SlackAPIClient Initialization Tests
# ============================================================================


@pytest.mark.unit
class TestSlackAPIClientInit:
    """Test SlackAPIClient initialization and configuration."""

    def test_client_initialization_with_defaults(self) -> None:
        """Client initializes with default retry config."""
        client = SlackAPIClient(token="xoxb-test-token")

        assert client.client is not None
        assert client.retry_config.max_retries == 3
        assert client.retry_config.initial_delay == 1.0
        assert client.retry_config.max_delay == 60.0
        assert client.retry_config.exponential_base == 2.0
        assert client.retry_config.jitter is True

    def test_client_initialization_with_custom_retry_config(self) -> None:
        """Client accepts custom retry configuration."""
        custom_config = RetryConfig(
            max_retries=5,
            initial_delay=2.0,
            max_delay=120.0,
            exponential_base=3.0,
            jitter=False,
        )

        client = SlackAPIClient(
            token="xoxb-test-token",
            retry_config=custom_config,
        )

        assert client.retry_config.max_retries == 5
        assert client.retry_config.initial_delay == 2.0
        assert client.retry_config.max_delay == 120.0
        assert client.retry_config.exponential_base == 3.0
        assert client.retry_config.jitter is False


# ============================================================================
# _should_retry() Logic Tests
# ============================================================================


@pytest.mark.unit
class TestShouldRetry:
    """Test _should_retry() decision logic for different error types."""

    def test_should_retry_on_429_rate_limit(self) -> None:
        """Rate limit errors (429) should be retried."""
        client = SlackAPIClient(token="xoxb-test-token")
        error = make_slack_error(status_code=429)

        assert client._should_retry(error) is True

    def test_should_retry_on_500_server_error(self) -> None:
        """Server errors (500) should be retried."""
        client = SlackAPIClient(token="xoxb-test-token")
        error = make_slack_error(status_code=500)

        assert client._should_retry(error) is True

    def test_should_retry_on_502_bad_gateway(self) -> None:
        """Bad gateway errors (502) should be retried."""
        client = SlackAPIClient(token="xoxb-test-token")
        error = make_slack_error(status_code=502)

        assert client._should_retry(error) is True

    def test_should_retry_on_503_service_unavailable(self) -> None:
        """Service unavailable errors (503) should be retried."""
        client = SlackAPIClient(token="xoxb-test-token")
        error = make_slack_error(status_code=503)

        assert client._should_retry(error) is True

    def test_should_retry_on_504_gateway_timeout(self) -> None:
        """Gateway timeout errors (504) should be retried."""
        client = SlackAPIClient(token="xoxb-test-token")
        error = make_slack_error(status_code=504)

        assert client._should_retry(error) is True

    def test_should_not_retry_on_400_bad_request(self) -> None:
        """Bad request errors (400) should not be retried."""
        client = SlackAPIClient(token="xoxb-test-token")
        error = make_slack_error(status_code=400)

        assert client._should_retry(error) is False

    def test_should_not_retry_on_401_unauthorized(self) -> None:
        """Unauthorized errors (401) should not be retried."""
        client = SlackAPIClient(token="xoxb-test-token")
        error = make_slack_error(status_code=401)

        assert client._should_retry(error) is False

    def test_should_not_retry_on_403_forbidden(self) -> None:
        """Forbidden errors (403) should not be retried."""
        client = SlackAPIClient(token="xoxb-test-token")
        error = make_slack_error(status_code=403)

        assert client._should_retry(error) is False

    def test_should_not_retry_on_404_not_found(self) -> None:
        """Not found errors (404) should not be retried."""
        client = SlackAPIClient(token="xoxb-test-token")
        error = make_slack_error(status_code=404)

        assert client._should_retry(error) is False

    def test_should_retry_on_network_error_without_status(self) -> None:
        """Network errors without status code should be retried."""
        client = SlackAPIClient(token="xoxb-test-token")

        # Create error without status code
        mock_response = MagicMock()
        mock_response.status_code = None
        error = SlackApiError(message="Network error", response=mock_response)

        assert client._should_retry(error) is True

    def test_should_retry_on_error_with_no_response(self) -> None:
        """Errors without response object should be retried."""
        client = SlackAPIClient(token="xoxb-test-token")

        # Create error without response
        error = SlackApiError(message="Connection error", response=None)

        assert client._should_retry(error) is True


# ============================================================================
# _get_retry_delay() Logic Tests
# ============================================================================


@pytest.mark.unit
class TestGetRetryDelay:
    """Test _get_retry_delay() calculation with Retry-After header support."""

    def test_uses_retry_after_header_when_present(self) -> None:
        """Retry-After header value should be used when available."""
        client = SlackAPIClient(token="xoxb-test-token")
        error = make_slack_error(status_code=429, retry_after="30")

        delay = client._get_retry_delay(error, attempt=0)

        assert delay == 30.0

    def test_fallback_to_exponential_backoff_without_retry_after(self) -> None:
        """Should use exponential backoff when Retry-After is not present."""
        config = RetryConfig(
            initial_delay=2.0,
            exponential_base=2.0,
            jitter=False,
        )
        client = SlackAPIClient(token="xoxb-test-token", retry_config=config)
        error = make_slack_error(status_code=500)

        # Attempt 0: 2.0 * (2^0) = 2.0
        delay_0 = client._get_retry_delay(error, attempt=0)
        assert delay_0 == 2.0

        # Attempt 1: 2.0 * (2^1) = 4.0
        delay_1 = client._get_retry_delay(error, attempt=1)
        assert delay_1 == 4.0

        # Attempt 2: 2.0 * (2^2) = 8.0
        delay_2 = client._get_retry_delay(error, attempt=2)
        assert delay_2 == 8.0

    def test_fallback_on_invalid_retry_after_value(self) -> None:
        """Should fallback to exponential backoff if Retry-After is invalid."""
        config = RetryConfig(
            initial_delay=1.0,
            exponential_base=2.0,
            jitter=False,
        )
        client = SlackAPIClient(token="xoxb-test-token", retry_config=config)
        error = make_slack_error(status_code=429, retry_after="invalid")

        delay = client._get_retry_delay(error, attempt=0)

        # Should fallback to exponential calculation
        assert delay == 1.0

    def test_respects_max_delay_cap(self) -> None:
        """Delay should not exceed max_delay configuration."""
        config = RetryConfig(
            initial_delay=10.0,
            max_delay=30.0,
            exponential_base=10.0,
            jitter=False,
        )
        client = SlackAPIClient(token="xoxb-test-token", retry_config=config)
        error = make_slack_error(status_code=500)

        # Would be 10 * (10^3) = 10000, but should cap at 30
        delay = client._get_retry_delay(error, attempt=3)
        assert delay == 30.0

    def test_retry_after_as_float(self) -> None:
        """Retry-After header can be a decimal value."""
        client = SlackAPIClient(token="xoxb-test-token")
        error = make_slack_error(status_code=429, retry_after="2.5")

        delay = client._get_retry_delay(error, attempt=0)

        assert delay == 2.5


# ============================================================================
# get_permalink() Tests
# ============================================================================


@pytest.mark.unit
class TestGetPermalink:
    """Test get_permalink() API method."""

    @pytest.mark.asyncio
    async def test_get_permalink_success(self) -> None:
        """Successfully retrieves permalink on first attempt."""
        client = SlackAPIClient(token="xoxb-test-token")
        mock_web_client = make_mock_async_web_client()
        client.client = mock_web_client

        mock_web_client.chat_getPermalink.return_value = {
            "ok": True,
            "permalink": "https://example.slack.com/archives/C123/p1234567890123456",
        }

        result = await client.get_permalink(
            channel="C123456",
            message_ts="1234567890.123456",
        )

        assert result == "https://example.slack.com/archives/C123/p1234567890123456"
        mock_web_client.chat_getPermalink.assert_called_once_with(
            channel="C123456",
            message_ts="1234567890.123456",
        )

    @pytest.mark.asyncio
    async def test_get_permalink_retries_on_rate_limit(self) -> None:
        """Retries when rate limited and eventually succeeds."""
        config = RetryConfig(max_retries=2, initial_delay=0.01, jitter=False)
        client = SlackAPIClient(token="xoxb-test-token", retry_config=config)
        mock_web_client = make_mock_async_web_client()
        client.client = mock_web_client

        # Fail twice with rate limit, then succeed
        mock_web_client.chat_getPermalink.side_effect = [
            make_slack_error(status_code=429),
            make_slack_error(status_code=429),
            {"ok": True, "permalink": "https://example.slack.com/archives/C123/p1234"},
        ]

        result = await client.get_permalink(
            channel="C123456",
            message_ts="1234567890.123456",
        )

        assert result == "https://example.slack.com/archives/C123/p1234"
        assert mock_web_client.chat_getPermalink.call_count == 3

    @pytest.mark.asyncio
    async def test_get_permalink_raises_on_non_retryable_error(self) -> None:
        """Raises immediately on non-retryable errors like 404."""
        client = SlackAPIClient(token="xoxb-test-token")
        mock_web_client = make_mock_async_web_client()
        client.client = mock_web_client

        mock_web_client.chat_getPermalink.side_effect = make_slack_error(
            status_code=404,
            error_message="message_not_found",
        )

        with pytest.raises(SlackApiError) as exc_info:
            await client.get_permalink(
                channel="C123456",
                message_ts="1234567890.123456",
            )

        assert exc_info.value.response.status_code == 404
        # Should not retry on 404
        mock_web_client.chat_getPermalink.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_permalink_exhausts_retries(self) -> None:
        """Raises after exhausting all retry attempts."""
        config = RetryConfig(max_retries=2, initial_delay=0.01, jitter=False)
        client = SlackAPIClient(token="xoxb-test-token", retry_config=config)
        mock_web_client = make_mock_async_web_client()
        client.client = mock_web_client

        # Always fail with server error
        mock_web_client.chat_getPermalink.side_effect = make_slack_error(
            status_code=500
        )

        with pytest.raises(SlackApiError) as exc_info:
            await client.get_permalink(
                channel="C123456",
                message_ts="1234567890.123456",
            )

        assert exc_info.value.response.status_code == 500
        # Should be called 3 times (initial + 2 retries)
        assert mock_web_client.chat_getPermalink.call_count == 3


# ============================================================================
# get_user_info() Tests
# ============================================================================


@pytest.mark.unit
class TestGetUserInfo:
    """Test get_user_info() API method."""

    @pytest.mark.asyncio
    async def test_get_user_info_success(self) -> None:
        """Successfully retrieves user info."""
        client = SlackAPIClient(token="xoxb-test-token")
        mock_web_client = make_mock_async_web_client()
        client.client = mock_web_client

        mock_web_client.users_info.return_value = {
            "ok": True,
            "user": {
                "id": "U123456",
                "name": "testuser",
                "real_name": "Test User",
            },
        }

        result = await client.get_user_info(user_id="U123456")

        assert result["id"] == "U123456"
        assert result["name"] == "testuser"
        mock_web_client.users_info.assert_called_once_with(user="U123456")

    @pytest.mark.asyncio
    async def test_get_user_info_retries_on_server_error(self) -> None:
        """Retries on server errors."""
        config = RetryConfig(max_retries=1, initial_delay=0.01, jitter=False)
        client = SlackAPIClient(token="xoxb-test-token", retry_config=config)
        mock_web_client = make_mock_async_web_client()
        client.client = mock_web_client

        # Fail once, then succeed
        mock_web_client.users_info.side_effect = [
            make_slack_error(status_code=503),
            {
                "ok": True,
                "user": {"id": "U123456", "name": "testuser"},
            },
        ]

        result = await client.get_user_info(user_id="U123456")

        assert result["id"] == "U123456"
        assert mock_web_client.users_info.call_count == 2


# ============================================================================
# get_channel_info() Tests
# ============================================================================


@pytest.mark.unit
class TestGetChannelInfo:
    """Test get_channel_info() API method."""

    @pytest.mark.asyncio
    async def test_get_channel_info_success(self) -> None:
        """Successfully retrieves channel info."""
        client = SlackAPIClient(token="xoxb-test-token")
        mock_web_client = make_mock_async_web_client()
        client.client = mock_web_client

        mock_web_client.conversations_info.return_value = {
            "ok": True,
            "channel": {
                "id": "C123456",
                "name": "general",
                "is_channel": True,
            },
        }

        result = await client.get_channel_info(channel_id="C123456")

        assert result["id"] == "C123456"
        assert result["name"] == "general"
        mock_web_client.conversations_info.assert_called_once_with(
            channel="C123456"
        )

    @pytest.mark.asyncio
    async def test_get_channel_info_raises_on_not_found(self) -> None:
        """Raises immediately on channel not found."""
        client = SlackAPIClient(token="xoxb-test-token")
        mock_web_client = make_mock_async_web_client()
        client.client = mock_web_client

        mock_web_client.conversations_info.side_effect = make_slack_error(
            status_code=404,
            error_message="channel_not_found",
        )

        with pytest.raises(SlackApiError) as exc_info:
            await client.get_channel_info(channel_id="C999999")

        assert exc_info.value.response.status_code == 404
        mock_web_client.conversations_info.assert_called_once()


# ============================================================================
# post_message() Tests
# ============================================================================


@pytest.mark.unit
class TestPostMessage:
    """Test post_message() API method."""

    @pytest.mark.asyncio
    async def test_post_message_with_text(self) -> None:
        """Successfully posts message with text."""
        client = SlackAPIClient(token="xoxb-test-token")
        mock_web_client = make_mock_async_web_client()
        client.client = mock_web_client

        mock_web_client.chat_postMessage.return_value = {
            "ok": True,
            "ts": "1234567890.123456",
            "channel": "C123456",
        }

        result = await client.post_message(
            channel="C123456",
            text="Test message",
        )

        assert result["ok"] is True
        assert result["ts"] == "1234567890.123456"
        mock_web_client.chat_postMessage.assert_called_once_with(
            channel="C123456",
            text="Test message",
        )

    @pytest.mark.asyncio
    async def test_post_message_with_blocks(self) -> None:
        """Successfully posts message with blocks."""
        client = SlackAPIClient(token="xoxb-test-token")
        mock_web_client = make_mock_async_web_client()
        client.client = mock_web_client

        mock_web_client.chat_postMessage.return_value = {
            "ok": True,
            "ts": "1234567890.123456",
        }

        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "Hello *world*"},
            }
        ]

        result = await client.post_message(
            channel="C123456",
            blocks=blocks,
        )

        assert result["ok"] is True
        mock_web_client.chat_postMessage.assert_called_once_with(
            channel="C123456",
            blocks=blocks,
        )

    @pytest.mark.asyncio
    async def test_post_message_with_thread_ts(self) -> None:
        """Successfully posts message in thread."""
        client = SlackAPIClient(token="xoxb-test-token")
        mock_web_client = make_mock_async_web_client()
        client.client = mock_web_client

        mock_web_client.chat_postMessage.return_value = {
            "ok": True,
            "ts": "1234567890.123457",
        }

        result = await client.post_message(
            channel="C123456",
            text="Reply in thread",
            thread_ts="1234567890.123456",
        )

        assert result["ok"] is True
        mock_web_client.chat_postMessage.assert_called_once_with(
            channel="C123456",
            text="Reply in thread",
            thread_ts="1234567890.123456",
        )

    @pytest.mark.asyncio
    async def test_post_message_with_text_and_blocks(self) -> None:
        """Posts message with both text and blocks."""
        client = SlackAPIClient(token="xoxb-test-token")
        mock_web_client = make_mock_async_web_client()
        client.client = mock_web_client

        mock_web_client.chat_postMessage.return_value = {
            "ok": True,
            "ts": "1234567890.123456",
        }

        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "Block"}}]

        result = await client.post_message(
            channel="C123456",
            text="Fallback text",
            blocks=blocks,
        )

        assert result["ok"] is True
        mock_web_client.chat_postMessage.assert_called_once_with(
            channel="C123456",
            text="Fallback text",
            blocks=blocks,
        )

    @pytest.mark.asyncio
    async def test_post_message_retries_on_rate_limit_with_retry_after(self) -> None:
        """Respects Retry-After header when rate limited."""
        config = RetryConfig(max_retries=1, initial_delay=1.0, jitter=False)
        client = SlackAPIClient(token="xoxb-test-token", retry_config=config)
        mock_web_client = make_mock_async_web_client()
        client.client = mock_web_client

        # Fail with rate limit that has Retry-After, then succeed
        mock_web_client.chat_postMessage.side_effect = [
            make_slack_error(status_code=429, retry_after="0.01"),
            {"ok": True, "ts": "1234567890.123456"},
        ]

        result = await client.post_message(
            channel="C123456",
            text="Test message",
        )

        assert result["ok"] is True
        assert mock_web_client.chat_postMessage.call_count == 2

    @pytest.mark.asyncio
    async def test_post_message_raises_on_invalid_channel(self) -> None:
        """Raises immediately on invalid channel error."""
        client = SlackAPIClient(token="xoxb-test-token")
        mock_web_client = make_mock_async_web_client()
        client.client = mock_web_client

        mock_web_client.chat_postMessage.side_effect = make_slack_error(
            status_code=400,
            error_message="channel_not_found",
        )

        with pytest.raises(SlackApiError) as exc_info:
            await client.post_message(
                channel="INVALID",
                text="Test message",
            )

        assert exc_info.value.response.status_code == 400
        # Should not retry on 400
        mock_web_client.chat_postMessage.assert_called_once()
