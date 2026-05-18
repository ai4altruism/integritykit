"""Unit tests for URL-safety / SSRF-prevention utility.

Covers ticket S9-4 (acceptance criteria) and seeds the broader SSRF test
suite specified in S9-7 (DNS rebinding, redirect-chain depth).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from integritykit.utils.url_safety import UnsafeURLError, validate_external_url

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_head_response(
    *,
    status_code: int = 200,
    location: str | None = None,
) -> MagicMock:
    """Build a fake httpx.Response sufficient for the utility's logic."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.is_redirect = 300 <= status_code < 400 and location is not None
    response.headers = {"Location": location} if location else {}
    return response


def _patch_head(response_sequence: list[MagicMock]) -> AsyncMock:
    """Return an AsyncMock that yields successive HEAD responses in order."""
    head_mock = AsyncMock()
    head_mock.side_effect = response_sequence
    return head_mock


# ---------------------------------------------------------------------------
# Blocked IP literals — no DNS needed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,fragment",
    [
        ("http://127.0.0.1/secret", "loopback"),
        ("http://127.255.0.1/secret", "loopback"),
        ("http://10.0.0.1/internal", "private"),
        ("http://10.255.255.255/internal", "private"),
        ("http://172.16.0.1/internal", "private"),
        ("http://172.31.0.1/internal", "private"),
        ("http://192.168.0.1/router", "private"),
        ("http://192.168.255.255/router", "private"),
        ("http://169.254.169.254/latest/meta-data", "cloud metadata"),
        ("http://169.254.0.1/", "link-local"),
        ("http://[::1]/secret", "loopback"),
        ("http://[fd00::1]/internal", "private"),
        ("http://[fc00::1]/internal", "private"),
    ],
)
@pytest.mark.asyncio
async def test_blocked_ip_literal_raises(url: str, fragment: str) -> None:
    """Each blocked range must raise UnsafeURLError with a descriptive reason."""
    with pytest.raises(UnsafeURLError) as exc_info:
        await validate_external_url(url)
    assert fragment in str(exc_info.value)


# ---------------------------------------------------------------------------
# Scheme / hostname validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unsupported_scheme_raises() -> None:
    with pytest.raises(UnsafeURLError, match="Unsupported URL scheme"):
        await validate_external_url("ftp://example.com/payload")


@pytest.mark.asyncio
async def test_file_scheme_raises() -> None:
    with pytest.raises(UnsafeURLError, match="Unsupported URL scheme"):
        await validate_external_url("file:///etc/passwd")


@pytest.mark.asyncio
async def test_missing_hostname_raises() -> None:
    with pytest.raises(UnsafeURLError, match="has no hostname"):
        await validate_external_url("http:///just-a-path")


# ---------------------------------------------------------------------------
# DNS resolution behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unresolvable_hostname_raises() -> None:
    with (
        patch(
            "integritykit.utils.url_safety._resolve_hostname",
            new=AsyncMock(side_effect=UnsafeURLError("did not resolve")),
        ),
        pytest.raises(UnsafeURLError, match="did not resolve"),
    ):
        await validate_external_url("http://nonexistent.invalid/")


@pytest.mark.asyncio
async def test_hostname_resolving_to_private_ip_raises() -> None:
    """Hostname looks public but DNS returns a private address."""
    with (
        patch(
            "integritykit.utils.url_safety._resolve_hostname",
            new=AsyncMock(return_value=["10.0.0.1"]),
        ),
        pytest.raises(UnsafeURLError, match="private address"),
    ):
        await validate_external_url("http://sneaky.example.com/")


@pytest.mark.asyncio
async def test_public_hostname_passes() -> None:
    """A hostname resolving to a single public IP must not raise."""
    with (
        patch(
            "integritykit.utils.url_safety._resolve_hostname",
            new=AsyncMock(return_value=["93.184.216.34"]),  # example.com
        ),
        patch.object(
            httpx.AsyncClient,
            "head",
            new=_patch_head([_make_head_response(status_code=200)]),
        ),
    ):
        # Should complete without raising
        await validate_external_url("http://example.com/")


@pytest.mark.asyncio
async def test_one_private_ip_in_multi_resolution_raises() -> None:
    """If any resolved address is private, the URL is unsafe."""
    with (
        patch(
            "integritykit.utils.url_safety._resolve_hostname",
            new=AsyncMock(return_value=["93.184.216.34", "10.0.0.1"]),
        ),
        pytest.raises(UnsafeURLError, match="private address"),
    ):
        await validate_external_url("http://mixed.example.com/")


# ---------------------------------------------------------------------------
# Redirect handling — S9-4 AC + S9-7 coverage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redirect_to_private_ip_raises() -> None:
    """Redirect chain that terminates at a private IP must raise."""
    head_responses = [
        # First hop: public URL returns 302 → http://10.0.0.1/leak
        _make_head_response(status_code=302, location="http://10.0.0.1/leak"),
    ]
    with (
        patch(
            "integritykit.utils.url_safety._resolve_hostname",
            new=AsyncMock(return_value=["93.184.216.34"]),
        ),
        patch.object(
            httpx.AsyncClient,
            "head",
            new=_patch_head(head_responses),
        ),
        pytest.raises(UnsafeURLError, match="private address"),
    ):
        await validate_external_url("http://public.example.com/")


@pytest.mark.asyncio
async def test_redirect_chain_re_validates_each_hop() -> None:
    """A two-hop redirect chain where the final hostname resolves private."""
    head_responses = [
        _make_head_response(status_code=302, location="http://hop2.example.com/next"),
        _make_head_response(status_code=200),  # terminal
    ]
    resolve_calls: list[str] = []

    async def fake_resolve(hostname: str) -> list[str]:
        resolve_calls.append(hostname)
        if hostname == "hop2.example.com":
            return ["10.0.0.5"]
        return ["93.184.216.34"]

    with (
        patch(
            "integritykit.utils.url_safety._resolve_hostname",
            new=AsyncMock(side_effect=fake_resolve),
        ),
        patch.object(
            httpx.AsyncClient,
            "head",
            new=_patch_head(head_responses),
        ),
        pytest.raises(UnsafeURLError, match="private address"),
    ):
        await validate_external_url("http://hop1.example.com/start")

    # Both hostnames were re-resolved — confirms per-hop re-validation
    assert resolve_calls == ["hop1.example.com", "hop2.example.com"]


@pytest.mark.asyncio
async def test_redirect_loop_detected() -> None:
    """A redirect that loops back must raise rather than infinite-loop."""
    head_responses = [
        _make_head_response(status_code=302, location="http://example.com/start"),
    ]
    with (
        patch(
            "integritykit.utils.url_safety._resolve_hostname",
            new=AsyncMock(return_value=["93.184.216.34"]),
        ),
        patch.object(
            httpx.AsyncClient,
            "head",
            new=_patch_head(head_responses),
        ),
        pytest.raises(UnsafeURLError, match="Redirect loop"),
    ):
        await validate_external_url("http://example.com/start")


@pytest.mark.asyncio
async def test_redirect_chain_depth_enforced() -> None:
    """Chains longer than max_redirects raise (S9-7 depth coverage)."""
    head_responses = [
        _make_head_response(status_code=302, location=f"http://hop{i}.example/")
        for i in range(1, 10)
    ]
    with (
        patch(
            "integritykit.utils.url_safety._resolve_hostname",
            new=AsyncMock(return_value=["93.184.216.34"]),
        ),
        patch.object(
            httpx.AsyncClient,
            "head",
            new=_patch_head(head_responses),
        ),
        pytest.raises(UnsafeURLError, match="Too many redirects"),
    ):
        await validate_external_url(
            "http://hop0.example/",
            max_redirects=3,
        )


@pytest.mark.asyncio
async def test_dns_rebinding_caught_by_per_hop_revalidation() -> None:
    """DNS rebinding: first lookup returns public IP, second returns private.

    Each redirect hop triggers a fresh DNS resolution, so a hostname whose
    resolution changes between calls is caught on the second lookup.
    """
    resolutions = iter([["93.184.216.34"], ["10.0.0.99"]])

    async def rebinding_resolve(_hostname: str) -> list[str]:
        return next(resolutions)

    head_responses = [
        _make_head_response(status_code=302, location="http://rebind.example.com/again"),
    ]
    with (
        patch(
            "integritykit.utils.url_safety._resolve_hostname",
            new=AsyncMock(side_effect=rebinding_resolve),
        ),
        patch.object(
            httpx.AsyncClient,
            "head",
            new=_patch_head(head_responses),
        ),
        pytest.raises(UnsafeURLError, match="private address"),
    ):
        await validate_external_url("http://rebind.example.com/start")


@pytest.mark.asyncio
async def test_head_probe_network_error_allows_validation_to_pass() -> None:
    """If HEAD probe fails for network reasons, validation does not raise."""

    async def fail_head(*_args, **_kwargs):
        raise httpx.ConnectError("simulated network failure")

    with (
        patch(
            "integritykit.utils.url_safety._resolve_hostname",
            new=AsyncMock(return_value=["93.184.216.34"]),
        ),
        patch.object(httpx.AsyncClient, "head", new=fail_head),
    ):
        # Must not raise — the caller's real request will surface this
        await validate_external_url("http://example.com/")
