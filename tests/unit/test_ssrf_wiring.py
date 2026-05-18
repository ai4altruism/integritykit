"""SSRF wiring tests — S9-7.

Confirms that `validate_external_url` is invoked from the webhook delivery
path and the external-source ingestion path, and that failures surface as
the documented status / error.

The autouse fixture in `tests/conftest.py` mocks `validate_external_url`
to a no-op so other tests don't depend on real DNS. These tests re-patch
it to raise `UnsafeURLError` to verify the wiring.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from integritykit.models.external_source import (
    AuthType as SourceAuthType,
)
from integritykit.models.external_source import (
    ExternalSource,
    ExternalSourceCreate,
    ImportRequest,
    SourceType,
    TrustLevel,
)
from integritykit.models.webhook import (
    AuthType as WebhookAuthType,
)
from integritykit.models.webhook import (
    Webhook,
    WebhookCreate,
    WebhookEvent,
    WebhookPayload,
    WebhookStatus,
)
from integritykit.services import external_sources as external_sources_module
from integritykit.services import webhooks as webhooks_module
from integritykit.services.external_sources import ExternalSourceService
from integritykit.services.webhooks import WebhookService
from integritykit.utils.url_safety import UnsafeURLError


def _raise_ssrf_async() -> AsyncMock:
    return AsyncMock(side_effect=UnsafeURLError("private address 10.0.0.1"))


# ---------------------------------------------------------------------------
# Webhook wiring
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_webhook_rejects_ssrf_url(test_db, monkeypatch) -> None:
    """create_webhook surfaces SSRF failures as ValueError (→ 400 at the API)."""
    monkeypatch.setattr(webhooks_module, "validate_external_url", _raise_ssrf_async())
    monkeypatch.setattr(webhooks_module.settings, "debug", False)

    service = WebhookService(
        webhooks_collection=test_db.webhooks,
        deliveries_collection=test_db.webhook_deliveries,
    )
    webhook_data = WebhookCreate(
        name="bad-webhook",
        url="https://attacker.example.com/webhook",
        events=[WebhookEvent.COP_UPDATE_PUBLISHED],
        auth_type=WebhookAuthType.NONE,
        enabled=True,
    )
    with pytest.raises(ValueError, match="SSRF check"):
        await service.create_webhook(
            webhook_data=webhook_data,
            workspace_id="T1",
            created_by="U1",
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_attempt_delivery_returns_blocked_ssrf_status(monkeypatch) -> None:
    """_attempt_delivery returns BLOCKED_SSRF when the URL resolves unsafe."""
    monkeypatch.setattr(webhooks_module, "validate_external_url", _raise_ssrf_async())
    monkeypatch.setattr(webhooks_module.settings, "debug", False)

    service = WebhookService(
        webhooks_collection=MagicMock(),
        deliveries_collection=MagicMock(),
    )
    webhook = Webhook(
        workspace_id="T1",
        name="bad-webhook",
        url="http://10.0.0.1/webhook",
        events=[WebhookEvent.COP_UPDATE_PUBLISHED],
        auth_type=WebhookAuthType.NONE,
        enabled=True,
        created_by="U1",
    )
    payload = WebhookPayload(
        event_id="evt-1",
        event_type=WebhookEvent.COP_UPDATE_PUBLISHED,
        timestamp=datetime.utcnow(),
        workspace_id="T1",
        data={},
    )

    status, status_code, _, body, error = await service._attempt_delivery(webhook, payload)

    assert status == WebhookStatus.BLOCKED_SSRF
    assert status_code is None
    assert body is None
    assert error is not None and error.startswith("SSRF:")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_test_webhook_reports_ssrf_when_url_unsafe(test_db, monkeypatch) -> None:
    """test_webhook returns success=False with error mentioning SSRF."""
    monkeypatch.setattr(webhooks_module.settings, "debug", False)

    service = WebhookService(
        webhooks_collection=test_db.webhooks,
        deliveries_collection=test_db.webhook_deliveries,
    )

    # Insert directly to bypass create_webhook's own SSRF check
    webhook = Webhook(
        workspace_id="T1",
        name="seeded-webhook",
        url="http://10.0.0.1/webhook",
        events=[WebhookEvent.COP_UPDATE_PUBLISHED],
        auth_type=WebhookAuthType.NONE,
        enabled=True,
        created_by="U1",
    )
    inserted = await test_db.webhooks.insert_one(webhook.model_dump(by_alias=True, exclude={"id"}))

    # Now arm the SSRF mock to raise on the test_webhook re-check
    monkeypatch.setattr(webhooks_module, "validate_external_url", _raise_ssrf_async())

    result = await service.test_webhook(
        webhook_id=inserted.inserted_id,
        workspace_id="T1",
    )

    assert result.success is False
    assert result.error is not None and "SSRF" in result.error


@pytest.mark.unit
@pytest.mark.asyncio
async def test_debug_mode_bypasses_webhook_ssrf_check(test_db, monkeypatch) -> None:
    """Debug mode preserves the historical localhost-allowed behavior."""
    monkeypatch.setattr(webhooks_module.settings, "debug", True)
    # Re-arm to raise so we can prove it isn't called in debug mode
    raising_mock = _raise_ssrf_async()
    monkeypatch.setattr(webhooks_module, "validate_external_url", raising_mock)

    service = WebhookService(
        webhooks_collection=test_db.webhooks,
        deliveries_collection=test_db.webhook_deliveries,
    )
    webhook_data = WebhookCreate(
        name="local-webhook",
        url="http://localhost:8000/webhook",
        events=[WebhookEvent.COP_UPDATE_PUBLISHED],
        auth_type=WebhookAuthType.NONE,
        enabled=True,
    )
    # Must not raise — the SSRF check is gated off in debug mode
    webhook = await service.create_webhook(
        webhook_data=webhook_data,
        workspace_id="T1",
        created_by="U1",
    )
    assert webhook.id is not None
    raising_mock.assert_not_called()


# ---------------------------------------------------------------------------
# External-source wiring
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_source_rejects_ssrf_url(test_db, monkeypatch) -> None:
    """create_source surfaces SSRF failures as ValueError (→ 400 at the API)."""
    monkeypatch.setattr(external_sources_module, "validate_external_url", _raise_ssrf_async())
    monkeypatch.setattr(external_sources_module.settings, "debug", False)

    service = ExternalSourceService(
        sources_collection=test_db.external_sources,
        imports_collection=test_db.external_source_imports,
        candidates_collection=test_db.cop_candidates,
    )
    source_data = ExternalSourceCreate(
        source_id="bad-source",
        name="Bad",
        source_type=SourceType.GOVERNMENT_API,
        api_endpoint="https://attacker.example.com/data",
        auth_type=SourceAuthType.NONE,
        trust_level=TrustLevel.MEDIUM,
    )
    with pytest.raises(ValueError, match="SSRF check"):
        await service.create_source(
            source_data=source_data,
            workspace_id="T1",
            created_by="U1",
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_from_external_api_raises_ssrf_on_unsafe(monkeypatch) -> None:
    """_fetch_from_external_api raises ValueError prefixed with 'SSRF:' on unsafe URL."""
    monkeypatch.setattr(external_sources_module, "validate_external_url", _raise_ssrf_async())
    monkeypatch.setattr(external_sources_module.settings, "debug", False)

    service = ExternalSourceService(
        sources_collection=MagicMock(),
        imports_collection=MagicMock(),
        candidates_collection=MagicMock(),
    )

    source = ExternalSource(
        workspace_id="T1",
        source_id="src",
        name="Src",
        source_type=SourceType.GOVERNMENT_API,
        api_endpoint="https://attacker.example.com/data",
        auth_type=SourceAuthType.NONE,
        trust_level=TrustLevel.MEDIUM,
        created_by="U1",
    )
    import_request = ImportRequest()

    with pytest.raises(ValueError, match="^SSRF:"):
        await service._fetch_from_external_api(source, import_request)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_debug_mode_bypasses_external_source_ssrf_check(test_db, monkeypatch) -> None:
    """Debug mode preserves localhost allowance for external sources."""
    monkeypatch.setattr(external_sources_module.settings, "debug", True)
    raising_mock = _raise_ssrf_async()
    monkeypatch.setattr(external_sources_module, "validate_external_url", raising_mock)

    service = ExternalSourceService(
        sources_collection=test_db.external_sources,
        imports_collection=test_db.external_source_imports,
        candidates_collection=test_db.cop_candidates,
    )
    source_data = ExternalSourceCreate(
        source_id="local-source",
        name="Local",
        source_type=SourceType.GOVERNMENT_API,
        api_endpoint="http://localhost:8001/data",
        auth_type=SourceAuthType.NONE,
        trust_level=TrustLevel.MEDIUM,
    )
    # Must not raise
    source = await service.create_source(
        source_data=source_data,
        workspace_id="T1",
        created_by="U1",
    )
    assert source.id is not None
    raising_mock.assert_not_called()
