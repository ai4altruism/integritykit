"""Integration tests for Slack OAuth bearer-token validation.

Covers ticket S9-1 acceptance criteria:
- Valid token authenticates and returns a User
- Invalid / revoked token returns 401
- Cached token within TTL does not trigger a second auth.test call
- TokenPayload fields are populated from the auth.test response
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from slack_sdk.errors import SlackApiError

from integritykit.api import dependencies
from integritykit.api.dependencies import (
    TokenPayload,
    _clear_oauth_cache,
    _validate_slack_token,
    get_current_user_from_token,
)
from integritykit.services.database import UserRepository

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_oauth_cache() -> None:
    """Ensure each test starts with an empty token cache."""
    _clear_oauth_cache()


def _make_slack_client(*, auth_test_result) -> MagicMock:
    """Build a mock AsyncWebClient whose auth_test returns/raises as given."""
    mock_client = MagicMock()
    if isinstance(auth_test_result, Exception):
        mock_client.auth_test = AsyncMock(side_effect=auth_test_result)
    else:
        mock_client.auth_test = AsyncMock(return_value=auth_test_result)
    return mock_client


def _slack_api_error(error_code: str = "invalid_auth") -> SlackApiError:
    """Build a SlackApiError shaped like the real SDK produces."""
    response = MagicMock()
    response.get = lambda key, default=None: error_code if key == "error" else default
    response.status_code = 401
    return SlackApiError(message=error_code, response=response)


def _make_request(authorization: str | None = None) -> MagicMock:
    """Build a minimal Request stub with .headers and .state."""
    request = MagicMock()
    request.headers = {}
    if authorization is not None:
        request.headers["Authorization"] = authorization
    request.state = MagicMock(spec=[])  # no .user attribute
    return request


# ---------------------------------------------------------------------------
# _validate_slack_token — unit-level behavior under integration markers
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_valid_token_populates_token_payload() -> None:
    """auth.test response fields land on TokenPayload."""
    mock_client = _make_slack_client(
        auth_test_result={
            "ok": True,
            "user_id": "U01VALID",
            "team_id": "T01TEAM",
            "user": "validuser",
        }
    )
    with patch.object(dependencies, "AsyncWebClient", return_value=mock_client):
        payload = await _validate_slack_token("xoxp-valid-token")

    assert isinstance(payload, TokenPayload)
    assert payload.user_id == "U01VALID"
    assert payload.team_id == "T01TEAM"
    assert payload.name == "validuser"
    # auth.test does not return email; we leave it None
    assert payload.email is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_invalid_token_raises_401() -> None:
    """A Slack API rejection becomes an HTTP 401."""
    mock_client = _make_slack_client(auth_test_result=_slack_api_error("invalid_auth"))
    with (
        patch.object(dependencies, "AsyncWebClient", return_value=mock_client),
        pytest.raises(HTTPException) as exc_info,
    ):
        await _validate_slack_token("xoxp-bogus")
    assert exc_info.value.status_code == 401
    assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_response_missing_user_id_raises_401() -> None:
    """A malformed Slack response shouldn't crash — return 401."""
    mock_client = _make_slack_client(auth_test_result={"ok": True})  # no user_id
    with (
        patch.object(dependencies, "AsyncWebClient", return_value=mock_client),
        pytest.raises(HTTPException) as exc_info,
    ):
        await _validate_slack_token("xoxp-malformed")
    assert exc_info.value.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ok_false_raises_401() -> None:
    """If Slack returns ok=False without raising, we still 401."""
    mock_client = _make_slack_client(auth_test_result={"ok": False, "error": "x"})
    with (
        patch.object(dependencies, "AsyncWebClient", return_value=mock_client),
        pytest.raises(HTTPException) as exc_info,
    ):
        await _validate_slack_token("xoxp-okfalse")
    assert exc_info.value.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cached_token_does_not_re_call_slack() -> None:
    """A second call within TTL must hit the cache (zero extra API calls)."""
    auth_test_calls: list[None] = []

    async def counting_auth_test(*args, **kwargs):
        auth_test_calls.append(None)
        return {
            "ok": True,
            "user_id": "U01CACHE",
            "team_id": "T01TEAM",
            "user": "cacheduser",
        }

    mock_client = MagicMock()
    mock_client.auth_test = counting_auth_test

    with patch.object(dependencies, "AsyncWebClient", return_value=mock_client):
        first = await _validate_slack_token("xoxp-cached-token")
        second = await _validate_slack_token("xoxp-cached-token")

    assert first.user_id == "U01CACHE"
    assert second.user_id == "U01CACHE"
    assert len(auth_test_calls) == 1, (
        "auth.test must be called exactly once; cache should serve the second call"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_distinct_tokens_do_not_share_cache_entries() -> None:
    """Cache is keyed by token, so a different token re-calls Slack."""
    auth_test_calls: list[str] = []

    async def counting_auth_test(*args, **kwargs):
        # We can't easily see the token from inside the mock client, so
        # instead we observe that the function is invoked twice.
        auth_test_calls.append("called")
        return {
            "ok": True,
            "user_id": "U01TEAM",
            "team_id": "T01TEAM",
            "user": "u",
        }

    mock_client = MagicMock()
    mock_client.auth_test = counting_auth_test

    with patch.object(dependencies, "AsyncWebClient", return_value=mock_client):
        await _validate_slack_token("xoxp-token-A")
        await _validate_slack_token("xoxp-token-B")

    assert len(auth_test_calls) == 2


# ---------------------------------------------------------------------------
# get_current_user_from_token — end-to-end through UserRepository
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_valid_bearer_token_returns_user(test_db) -> None:
    """A valid Bearer token round-trips through UserRepository to a User."""
    user_repo = UserRepository(test_db.users)
    request = _make_request(authorization="Bearer xoxp-valid")

    mock_client = _make_slack_client(
        auth_test_result={
            "ok": True,
            "user_id": "U01OAUTH",
            "team_id": "T01OAUTH",
            "user": "oauthuser",
        }
    )
    with patch.object(dependencies, "AsyncWebClient", return_value=mock_client):
        user = await get_current_user_from_token(
            request=request,
            authorization="Bearer xoxp-valid",
            user_repo=user_repo,
        )

    assert user.slack_user_id == "U01OAUTH"
    assert user.slack_team_id == "T01OAUTH"

    # User must have been persisted
    persisted = await test_db.users.find_one({"slack_user_id": "U01OAUTH"})
    assert persisted is not None


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_invalid_bearer_token_returns_401(test_db) -> None:
    """An invalid Bearer token raises 401 from the endpoint dependency."""
    user_repo = UserRepository(test_db.users)
    request = _make_request(authorization="Bearer xoxp-bogus")

    mock_client = _make_slack_client(auth_test_result=_slack_api_error())
    with (
        patch.object(dependencies, "AsyncWebClient", return_value=mock_client),
        pytest.raises(HTTPException) as exc_info,
    ):
        await get_current_user_from_token(
            request=request,
            authorization="Bearer xoxp-bogus",
            user_repo=user_repo,
        )
    assert exc_info.value.status_code == 401
