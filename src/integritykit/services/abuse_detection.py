"""Anti-abuse detection service for rapid-fire override alerts.

Implements:
- S7-3: Anti-abuse detection for rapid-fire overrides
- NFR-ABUSE-001: Abuse detection signals
"""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Optional

import structlog
from bson import ObjectId
from slack_sdk.web.async_client import AsyncWebClient

from integritykit.models.audit import AuditActionType, AuditTargetType
from integritykit.models.user import User
from integritykit.services.audit import AuditService, get_audit_service

logger = structlog.get_logger(__name__)


def _get_settings():
    """Lazy import of settings to avoid validation errors in tests."""
    from integritykit.config import settings
    return settings


class OverrideRecord:
    """Record of an override action for tracking."""

    def __init__(
        self,
        user_id: ObjectId,
        action_type: str,
        target_id: ObjectId,
        timestamp: datetime,
    ):
        self.user_id = user_id
        self.action_type = action_type
        self.target_id = target_id
        self.timestamp = timestamp


class AbuseAlert:
    """Alert for detected abuse pattern."""

    def __init__(
        self,
        user_id: ObjectId,
        alert_type: str,
        override_count: int,
        window_minutes: int,
        timestamp: datetime,
        override_records: list[OverrideRecord],
    ):
        self.user_id = user_id
        self.alert_type = alert_type
        self.override_count = override_count
        self.window_minutes = window_minutes
        self.timestamp = timestamp
        self.override_records = override_records

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "user_id": str(self.user_id),
            "alert_type": self.alert_type,
            "override_count": self.override_count,
            "window_minutes": self.window_minutes,
            "timestamp": self.timestamp.isoformat(),
            "target_ids": [str(r.target_id) for r in self.override_records],
        }


class AbuseDetectionService:
    """Service for detecting and alerting on abuse patterns (S7-3).

    Monitors override actions and flags suspicious rapid-fire patterns
    that may indicate abuse or compromised accounts.
    """

    def __init__(
        self,
        audit_service: Optional[AuditService] = None,
        slack_client: Optional[AsyncWebClient] = None,
    ):
        """Initialize AbuseDetectionService.

        Args:
            audit_service: Audit logging service
            slack_client: Slack client for sending alerts
        """
        self.audit_service = audit_service or get_audit_service()
        self.slack_client = slack_client

        # In-memory tracking (in production, use Redis or database)
        # Maps user_id -> list of recent override records
        self._override_history: dict[str, list[OverrideRecord]] = defaultdict(list)

        # Recent alerts to prevent alert flooding
        self._recent_alerts: dict[str, datetime] = {}

    def is_enabled(self) -> bool:
        """Check if abuse detection is enabled.

        Returns:
            True if abuse detection is enabled in settings
        """
        return _get_settings().abuse_detection_enabled

    def _get_threshold(self) -> int:
        """Get override threshold from settings."""
        return _get_settings().abuse_override_threshold

    def _get_window_minutes(self) -> int:
        """Get detection window from settings."""
        return _get_settings().abuse_override_window_minutes

    def _get_alert_channel(self) -> Optional[str]:
        """Get Slack alert channel from settings."""
        return _get_settings().abuse_alert_slack_channel

    def _cleanup_old_records(self, user_id: str) -> None:
        """Remove override records outside the detection window.

        Args:
            user_id: User ID to clean up
        """
        if user_id not in self._override_history:
            return

        window = timedelta(minutes=self._get_window_minutes())
        cutoff = datetime.utcnow() - window

        self._override_history[user_id] = [
            r for r in self._override_history[user_id]
            if r.timestamp > cutoff
        ]

    async def record_override(
        self,
        user: User,
        action_type: str,
        target_id: ObjectId,
    ) -> Optional[AbuseAlert]:
        """Record an override action and check for abuse patterns.

        Args:
            user: User performing the override
            action_type: Type of override action
            target_id: ID of target being overridden

        Returns:
            AbuseAlert if threshold exceeded, None otherwise
        """
        if not self.is_enabled():
            return None

        user_id = str(user.id)
        now = datetime.utcnow()

        # Record the override
        record = OverrideRecord(
            user_id=user.id,
            action_type=action_type,
            target_id=target_id,
            timestamp=now,
        )
        self._override_history[user_id].append(record)

        # Clean up old records
        self._cleanup_old_records(user_id)

        # Check if threshold exceeded
        recent_overrides = self._override_history[user_id]
        threshold = self._get_threshold()

        if len(recent_overrides) >= threshold:
            # Check for recent alert to prevent flooding
            last_alert = self._recent_alerts.get(user_id)
            if last_alert and (now - last_alert) < timedelta(minutes=15):
                # Already alerted recently
                logger.debug(
                    "Skipping duplicate abuse alert",
                    user_id=user_id,
                    last_alert=last_alert.isoformat(),
                )
                return None

            # Create alert
            alert = AbuseAlert(
                user_id=user.id,
                alert_type="rapid_fire_overrides",
                override_count=len(recent_overrides),
                window_minutes=self._get_window_minutes(),
                timestamp=now,
                override_records=recent_overrides.copy(),
            )

            # Record alert time
            self._recent_alerts[user_id] = now

            # Log and notify
            await self._handle_alert(alert, user)

            return alert

        return None

    async def _handle_alert(
        self,
        alert: AbuseAlert,
        user: User,
    ) -> None:
        """Handle an abuse alert by logging and notifying.

        Args:
            alert: The abuse alert to handle
            user: The user who triggered the alert
        """
        # Log to audit with is_flagged=True
        await self.audit_service.log_action(
            actor=user,
            action_type=AuditActionType.ACCESS_DENIED,
            target_type=AuditTargetType.USER,
            target_id=user.id,
            changes_after={
                "alert_type": alert.alert_type,
                "override_count": alert.override_count,
                "window_minutes": alert.window_minutes,
            },
            system_context={
                "action": "abuse_detection_alert",
                "target_ids": [str(r.target_id) for r in alert.override_records],
            },
            is_flagged=True,
            flag_reason=f"Rapid-fire overrides: {alert.override_count} overrides in {alert.window_minutes} minutes",
        )

        logger.warning(
            "Abuse pattern detected: rapid-fire overrides",
            user_id=str(alert.user_id),
            override_count=alert.override_count,
            window_minutes=alert.window_minutes,
            target_ids=[str(r.target_id) for r in alert.override_records],
        )

        # Send Slack alert if configured
        await self._send_slack_alert(alert, user)

    async def _send_slack_alert(
        self,
        alert: AbuseAlert,
        user: User,
    ) -> None:
        """Send abuse alert to Slack channel.

        Args:
            alert: The abuse alert
            user: The user who triggered the alert
        """
        channel = self._get_alert_channel()
        if not channel or not self.slack_client:
            return

        try:
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": ":warning: Abuse Pattern Detected",
                        "emoji": True,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*User:*\n<@{user.slack_user_id}>",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Alert Type:*\n{alert.alert_type}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Override Count:*\n{alert.override_count}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Time Window:*\n{alert.window_minutes} minutes",
                        },
                    ],
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Detected at <!date^{int(alert.timestamp.timestamp())}^{{date_short}} at {{time}}|{alert.timestamp.isoformat()}>",
                        },
                    ],
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Review Audit Log",
                            },
                            "action_id": "review_audit_log",
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Suspend User",
                            },
                            "style": "danger",
                            "action_id": "suspend_user",
                            "value": str(user.id),
                        },
                    ],
                },
            ]

            await self.slack_client.chat_postMessage(
                channel=channel,
                text=f"Abuse pattern detected: {alert.override_count} overrides by <@{user.slack_user_id}> in {alert.window_minutes} minutes",
                blocks=blocks,
            )

            logger.info(
                "Sent abuse alert to Slack",
                channel=channel,
                user_id=str(user.id),
            )

        except Exception as e:
            logger.error(
                "Failed to send Slack abuse alert",
                error=str(e),
                channel=channel,
            )

    def get_user_override_count(
        self,
        user_id: ObjectId,
    ) -> int:
        """Get current override count for a user in the detection window.

        Args:
            user_id: User ID to check

        Returns:
            Number of recent overrides
        """
        user_id_str = str(user_id)
        self._cleanup_old_records(user_id_str)
        return len(self._override_history.get(user_id_str, []))

    def clear_user_history(
        self,
        user_id: ObjectId,
    ) -> None:
        """Clear override history for a user.

        Used when a user is suspended or their history should be reset.

        Args:
            user_id: User ID to clear
        """
        user_id_str = str(user_id)
        self._override_history.pop(user_id_str, None)
        self._recent_alerts.pop(user_id_str, None)

        logger.info(
            "Cleared abuse detection history for user",
            user_id=user_id_str,
        )


# Singleton instance
_abuse_detection_service: Optional[AbuseDetectionService] = None


def get_abuse_detection_service() -> AbuseDetectionService:
    """Get the abuse detection service singleton.

    Returns:
        AbuseDetectionService instance
    """
    global _abuse_detection_service
    if _abuse_detection_service is None:
        _abuse_detection_service = AbuseDetectionService()
    return _abuse_detection_service
