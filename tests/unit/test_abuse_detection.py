"""Unit tests for anti-abuse detection service.

Tests:
- S7-3: Anti-abuse detection for rapid-fire overrides
- NFR-ABUSE-001: Abuse detection signals
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

from integritykit.models.user import User, UserRole
from integritykit.services.abuse_detection import (
    AbuseAlert,
    AbuseDetectionService,
    OverrideRecord,
)


# ============================================================================
# Test Fixtures
# ============================================================================


def make_user(
    *,
    user_id: ObjectId | None = None,
    roles: list[UserRole] | None = None,
) -> User:
    """Create a test user."""
    return User(
        id=user_id or ObjectId(),
        slack_user_id="U123456",
        slack_team_id="T123456",
        slack_display_name="Test User",
        roles=roles or [UserRole.FACILITATOR],
        created_at=datetime.now(timezone.utc),
    )


def make_mock_settings(
    enabled: bool = True,
    threshold: int = 5,
    window_minutes: int = 30,
    alert_channel: str | None = None,
):
    """Create mock settings for abuse detection tests."""
    mock = MagicMock()
    mock.abuse_detection_enabled = enabled
    mock.abuse_override_threshold = threshold
    mock.abuse_override_window_minutes = window_minutes
    mock.abuse_alert_slack_channel = alert_channel
    return mock


def make_mock_audit_service():
    """Create mock audit service."""
    service = MagicMock()
    service.log_action = AsyncMock()
    return service


# ============================================================================
# OverrideRecord Tests
# ============================================================================


@pytest.mark.unit
class TestOverrideRecord:
    """Test OverrideRecord data class."""

    def test_override_record_creation(self) -> None:
        """Override records store all necessary data."""
        user_id = ObjectId()
        target_id = ObjectId()
        now = datetime.utcnow()

        record = OverrideRecord(
            user_id=user_id,
            action_type="high_stakes_override",
            target_id=target_id,
            timestamp=now,
        )

        assert record.user_id == user_id
        assert record.action_type == "high_stakes_override"
        assert record.target_id == target_id
        assert record.timestamp == now


# ============================================================================
# AbuseAlert Tests
# ============================================================================


@pytest.mark.unit
class TestAbuseAlert:
    """Test AbuseAlert data class."""

    def test_abuse_alert_creation(self) -> None:
        """Abuse alerts contain all relevant information."""
        user_id = ObjectId()
        now = datetime.utcnow()

        alert = AbuseAlert(
            user_id=user_id,
            alert_type="rapid_fire_overrides",
            override_count=5,
            window_minutes=30,
            timestamp=now,
            override_records=[],
        )

        assert alert.user_id == user_id
        assert alert.alert_type == "rapid_fire_overrides"
        assert alert.override_count == 5
        assert alert.window_minutes == 30

    def test_abuse_alert_to_dict(self) -> None:
        """Abuse alert can be serialized to dictionary."""
        user_id = ObjectId()
        target_id = ObjectId()
        now = datetime.utcnow()

        record = OverrideRecord(
            user_id=user_id,
            action_type="high_stakes_override",
            target_id=target_id,
            timestamp=now,
        )

        alert = AbuseAlert(
            user_id=user_id,
            alert_type="rapid_fire_overrides",
            override_count=1,
            window_minutes=30,
            timestamp=now,
            override_records=[record],
        )

        alert_dict = alert.to_dict()

        assert alert_dict["user_id"] == str(user_id)
        assert alert_dict["alert_type"] == "rapid_fire_overrides"
        assert len(alert_dict["target_ids"]) == 1


# ============================================================================
# AbuseDetectionService Tests
# ============================================================================


@pytest.mark.unit
class TestAbuseDetectionService:
    """Test AbuseDetectionService functionality."""

    def test_is_enabled_respects_settings(self) -> None:
        """Service respects enabled setting."""
        with patch(
            "integritykit.services.abuse_detection._get_settings",
            return_value=make_mock_settings(enabled=True)
        ):
            service = AbuseDetectionService(
                audit_service=make_mock_audit_service()
            )

            assert service.is_enabled() is True

        with patch(
            "integritykit.services.abuse_detection._get_settings",
            return_value=make_mock_settings(enabled=False)
        ):
            service = AbuseDetectionService(
                audit_service=make_mock_audit_service()
            )

            assert service.is_enabled() is False

    @pytest.mark.asyncio
    async def test_record_override_no_alert_below_threshold(self) -> None:
        """No alert when override count is below threshold."""
        with patch(
            "integritykit.services.abuse_detection._get_settings",
            return_value=make_mock_settings(threshold=5)
        ):
            service = AbuseDetectionService(
                audit_service=make_mock_audit_service()
            )
            user = make_user()

            # Record 4 overrides (below threshold of 5)
            for i in range(4):
                alert = await service.record_override(
                    user=user,
                    action_type="high_stakes_override",
                    target_id=ObjectId(),
                )
                assert alert is None

    @pytest.mark.asyncio
    async def test_record_override_alert_at_threshold(self) -> None:
        """Alert triggered when override count reaches threshold."""
        with patch(
            "integritykit.services.abuse_detection._get_settings",
            return_value=make_mock_settings(threshold=5, window_minutes=30)
        ):
            service = AbuseDetectionService(
                audit_service=make_mock_audit_service()
            )
            user = make_user()

            # Record 5 overrides (at threshold)
            alert = None
            for i in range(5):
                alert = await service.record_override(
                    user=user,
                    action_type="high_stakes_override",
                    target_id=ObjectId(),
                )

            assert alert is not None
            assert alert.override_count == 5
            assert alert.alert_type == "rapid_fire_overrides"

    @pytest.mark.asyncio
    async def test_record_override_disabled(self) -> None:
        """No tracking when abuse detection is disabled."""
        with patch(
            "integritykit.services.abuse_detection._get_settings",
            return_value=make_mock_settings(enabled=False)
        ):
            service = AbuseDetectionService(
                audit_service=make_mock_audit_service()
            )
            user = make_user()

            # Record many overrides - should not trigger alert
            for i in range(10):
                alert = await service.record_override(
                    user=user,
                    action_type="high_stakes_override",
                    target_id=ObjectId(),
                )
                assert alert is None

    def test_get_user_override_count(self) -> None:
        """Can query current override count for a user."""
        with patch(
            "integritykit.services.abuse_detection._get_settings",
            return_value=make_mock_settings(threshold=10, window_minutes=30)
        ):
            service = AbuseDetectionService(
                audit_service=make_mock_audit_service()
            )
            user_id = ObjectId()

            # Add some records directly
            for i in range(3):
                record = OverrideRecord(
                    user_id=user_id,
                    action_type="high_stakes_override",
                    target_id=ObjectId(),
                    timestamp=datetime.utcnow(),
                )
                service._override_history[str(user_id)].append(record)

            count = service.get_user_override_count(user_id)
            assert count == 3

    def test_clear_user_history(self) -> None:
        """Can clear override history for a user."""
        with patch(
            "integritykit.services.abuse_detection._get_settings",
            return_value=make_mock_settings()
        ):
            service = AbuseDetectionService(
                audit_service=make_mock_audit_service()
            )
            user_id = ObjectId()

            # Add some records
            service._override_history[str(user_id)].append(
                OverrideRecord(
                    user_id=user_id,
                    action_type="test",
                    target_id=ObjectId(),
                    timestamp=datetime.utcnow(),
                )
            )

            # Clear
            service.clear_user_history(user_id)

            assert service.get_user_override_count(user_id) == 0

    @pytest.mark.asyncio
    async def test_old_records_cleaned_up(self) -> None:
        """Records outside detection window are cleaned up."""
        with patch(
            "integritykit.services.abuse_detection._get_settings",
            return_value=make_mock_settings(threshold=5, window_minutes=30)
        ):
            service = AbuseDetectionService(
                audit_service=make_mock_audit_service()
            )
            user = make_user()
            user_id = str(user.id)

            # Add old records (outside window)
            old_time = datetime.utcnow() - timedelta(hours=1)
            for i in range(3):
                record = OverrideRecord(
                    user_id=user.id,
                    action_type="high_stakes_override",
                    target_id=ObjectId(),
                    timestamp=old_time,
                )
                service._override_history[user_id].append(record)

            # Add new records
            for i in range(2):
                await service.record_override(
                    user=user,
                    action_type="high_stakes_override",
                    target_id=ObjectId(),
                )

            # Old records should be cleaned up
            count = service.get_user_override_count(user.id)
            assert count == 2  # Only the 2 new records


@pytest.mark.unit
class TestAbuseAlertLogging:
    """Test that abuse alerts are properly logged."""

    @pytest.mark.asyncio
    async def test_alert_is_flagged_in_audit_log(self) -> None:
        """Abuse alerts are logged with is_flagged=True."""
        mock_audit = make_mock_audit_service()

        with patch(
            "integritykit.services.abuse_detection._get_settings",
            return_value=make_mock_settings(threshold=1)
        ):
            service = AbuseDetectionService(audit_service=mock_audit)
            user = make_user()

            # Trigger alert
            await service.record_override(
                user=user,
                action_type="high_stakes_override",
                target_id=ObjectId(),
            )

            # Verify audit was called with is_flagged=True
            mock_audit.log_action.assert_called_once()
            call_kwargs = mock_audit.log_action.call_args.kwargs
            assert call_kwargs["is_flagged"] is True
            assert "Rapid-fire overrides" in call_kwargs["flag_reason"]

    @pytest.mark.asyncio
    async def test_alert_flood_prevention(self) -> None:
        """Multiple alerts from same user within 15 minutes are suppressed."""
        mock_audit = make_mock_audit_service()

        with patch(
            "integritykit.services.abuse_detection._get_settings",
            return_value=make_mock_settings(threshold=2, window_minutes=60)
        ):
            service = AbuseDetectionService(audit_service=mock_audit)
            user = make_user()

            # First batch - triggers alert
            for i in range(2):
                await service.record_override(
                    user=user,
                    action_type="high_stakes_override",
                    target_id=ObjectId(),
                )

            # Second batch - should not trigger new alert (flood prevention)
            for i in range(2):
                alert = await service.record_override(
                    user=user,
                    action_type="high_stakes_override",
                    target_id=ObjectId(),
                )
                assert alert is None  # Suppressed

            # Only one audit log call
            assert mock_audit.log_action.call_count == 1
