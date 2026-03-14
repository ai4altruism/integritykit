"""
Tests for verifying the demo scripts function.
This ensures the mock ingestion syntax doesn't break if internal models change.
"""

import pytest
import asyncio
from httpx import AsyncClient

from integritykit.models.signal import Signal, SourceQuality, SourceQualityType
from integritykit.api.main import app

@pytest.mark.asyncio
async def test_signal_model_instantiation():
    """Verify that the Signal model instantiation used in the demo is valid."""
    text = "Test flood warning"
    channel_id = "C01OPS"
    user_id = "U01USER1"
    message_ts = "123456.7890"

    signal = Signal(
        slack_workspace_id="T01DEMO",
        slack_channel_id=channel_id,
        slack_message_ts=message_ts,
        slack_user_id=user_id,
        slack_permalink=f"https://demo.slack.com/archives/{channel_id}/p{message_ts.replace('.', '')}",
        content=text,
        source_quality=SourceQuality(
            type=SourceQualityType.PRIMARY,
            is_firsthand=True,
            has_external_link=False,
            external_links=[]
        )
    )

    assert signal.slack_workspace_id == "T01DEMO"
    assert signal.content == text
    assert signal.source_quality.is_firsthand is True

@pytest.mark.asyncio
async def test_api_health_endpoint():
    """Verify the API is accessible and healthy."""
    from httpx import ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
