"""Slack event handlers for message ingestion."""

import re
from datetime import datetime
from typing import Any, Optional

import structlog
from slack_bolt.async_app import AsyncApp
from slack_sdk.errors import SlackApiError

from integritykit.models.signal import SignalCreate, SourceQuality, SourceQualityType
from integritykit.services.clustering import ClusteringService
from integritykit.services.database import SignalRepository

logger = structlog.get_logger(__name__)

# URL pattern for detecting external links
URL_PATTERN = re.compile(
    r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
)


class SlackEventHandler:
    """Handler for Slack events using slack-bolt."""

    def __init__(
        self,
        app: AsyncApp,
        signal_repository: SignalRepository,
        workspace_id: str,
        monitored_channels: Optional[list[str]] = None,
        filter_bot_messages: bool = True,
        clustering_service: Optional[ClusteringService] = None,
    ):
        """Initialize Slack event handler.

        Args:
            app: Slack Bolt async app instance
            signal_repository: Repository for signal storage
            workspace_id: Slack workspace/team ID
            monitored_channels: List of channel IDs to monitor (None = all channels)
            filter_bot_messages: Whether to filter out bot messages
            clustering_service: Optional clustering service for signal processing
        """
        self.app = app
        self.signal_repository = signal_repository
        self.workspace_id = workspace_id
        self.monitored_channels = monitored_channels
        self.filter_bot_messages = filter_bot_messages
        self.clustering_service = clustering_service

        # Register event listeners
        self._register_listeners()

    def _register_listeners(self) -> None:
        """Register Slack event listeners."""
        self.app.event("message")(self.handle_message)
        self.app.event("message_changed")(self.handle_message_changed)
        self.app.event("message_deleted")(self.handle_message_deleted)

    def _should_process_message(self, event: dict[str, Any]) -> bool:
        """Check if message should be processed based on filters.

        Args:
            event: Slack message event

        Returns:
            True if message should be processed
        """
        # Filter bot messages if configured
        if self.filter_bot_messages and event.get("bot_id"):
            logger.debug(
                "Skipping bot message",
                bot_id=event.get("bot_id"),
                channel=event.get("channel"),
            )
            return False

        # Filter by channel allowlist if configured
        channel_id = event.get("channel")
        if self.monitored_channels and channel_id not in self.monitored_channels:
            logger.debug(
                "Skipping message from unmonitored channel",
                channel=channel_id,
            )
            return False

        # Skip message subtypes we don't want to process
        subtype = event.get("subtype")
        if subtype in ["channel_join", "channel_leave", "channel_topic", "channel_purpose"]:
            logger.debug(
                "Skipping system message",
                subtype=subtype,
                channel=channel_id,
            )
            return False

        return True

    async def _get_permalink(
        self,
        channel_id: str,
        message_ts: str,
    ) -> Optional[str]:
        """Get permalink for a Slack message.

        Args:
            channel_id: Slack channel ID
            message_ts: Slack message timestamp

        Returns:
            Permalink URL or None if failed
        """
        try:
            result = await self.app.client.chat_getPermalink(
                channel=channel_id,
                message_ts=message_ts,
            )
            return result["permalink"]
        except SlackApiError as e:
            logger.error(
                "Failed to get Slack permalink",
                error=str(e),
                channel=channel_id,
                message_ts=message_ts,
            )
            return None

    def _extract_source_quality(self, text: str) -> SourceQuality:
        """Extract source quality indicators from message text.

        Args:
            text: Message text content

        Returns:
            SourceQuality instance with extracted indicators
        """
        # Find external links
        external_links = URL_PATTERN.findall(text)

        # Check for firsthand observation indicators
        firsthand_keywords = [
            "i saw",
            "i witnessed",
            "i observed",
            "we saw",
            "we witnessed",
            "we observed",
            "personally",
            "firsthand",
        ]
        is_firsthand = any(keyword in text.lower() for keyword in firsthand_keywords)

        # Determine source type based on presence of external links
        if external_links:
            source_type = SourceQualityType.EXTERNAL
            confidence = 0.8
        elif is_firsthand:
            source_type = SourceQualityType.PRIMARY
            confidence = 0.7
        else:
            source_type = SourceQualityType.SECONDARY
            confidence = 0.5

        return SourceQuality(
            type=source_type,
            confidence=confidence,
            is_firsthand=is_firsthand,
            has_external_link=bool(external_links),
            external_links=external_links,
        )

    async def handle_message(self, event: dict[str, Any], say: Any) -> None:
        """Handle new message events.

        Args:
            event: Slack message event
            say: Slack say function (unused but required by slack-bolt)
        """
        if not self._should_process_message(event):
            return

        channel_id = event["channel"]
        message_ts = event["ts"]
        user_id = event.get("user", "UNKNOWN")
        text = event.get("text", "")
        thread_ts = event.get("thread_ts")

        logger.info(
            "Processing new Slack message",
            channel=channel_id,
            message_ts=message_ts,
            user=user_id,
            is_thread_reply=bool(thread_ts),
        )

        # Get permalink
        permalink = await self._get_permalink(channel_id, message_ts)
        if not permalink:
            logger.warning(
                "Skipping message without permalink",
                channel=channel_id,
                message_ts=message_ts,
            )
            return

        # Extract source quality indicators
        source_quality = self._extract_source_quality(text)

        # Check if signal already exists (idempotency)
        existing = await self.signal_repository.get_by_slack_ts(
            workspace_id=self.workspace_id,
            channel_id=channel_id,
            message_ts=message_ts,
        )

        if existing:
            logger.debug(
                "Signal already exists, skipping",
                signal_id=str(existing.id),
                channel=channel_id,
                message_ts=message_ts,
            )
            return

        # Create signal
        signal_data = SignalCreate(
            slack_workspace_id=self.workspace_id,
            slack_channel_id=channel_id,
            slack_thread_ts=thread_ts,
            slack_message_ts=message_ts,
            slack_user_id=user_id,
            slack_permalink=permalink,
            content=text,
            attachments=event.get("attachments", []),
            source_quality=source_quality,
        )

        try:
            signal = await self.signal_repository.create(signal_data)
            logger.info(
                "Signal created",
                signal_id=str(signal.id),
                channel=channel_id,
                message_ts=message_ts,
                source_type=source_quality.type,
                is_firsthand=source_quality.is_firsthand,
                has_external_links=source_quality.has_external_link,
            )

            # Process signal through clustering service
            if self.clustering_service:
                try:
                    cluster = await self.clustering_service.process_new_signal(signal)
                    logger.info(
                        "Signal clustered successfully",
                        signal_id=str(signal.id),
                        cluster_id=str(cluster.id),
                        cluster_topic=cluster.topic,
                    )
                except Exception as e:
                    # Don't fail ingestion if clustering fails
                    logger.error(
                        "Failed to cluster signal, continuing without clustering",
                        signal_id=str(signal.id),
                        error=str(e),
                    )
                    # Mark as pending clustering for retry
                    await self.signal_repository.update(
                        signal.id,
                        {
                            "ai_generated_metadata": {
                                "pending_clustering": True,
                                "clustering_error": str(e),
                                "ingested_at": datetime.utcnow().isoformat(),
                            }
                        },
                    )
            else:
                # No clustering service configured, mark as pending
                await self.signal_repository.update(
                    signal.id,
                    {
                        "ai_generated_metadata": {
                            "pending_embedding": True,
                            "pending_clustering": True,
                            "ingested_at": datetime.utcnow().isoformat(),
                        }
                    },
                )

        except Exception as e:
            logger.error(
                "Failed to create signal",
                error=str(e),
                channel=channel_id,
                message_ts=message_ts,
            )
            raise

    async def handle_message_changed(self, event: dict[str, Any], say: Any) -> None:
        """Handle message edit events.

        Args:
            event: Slack message_changed event
            say: Slack say function (unused but required by slack-bolt)
        """
        message = event.get("message", {})
        channel_id = event["channel"]
        message_ts = message.get("ts")
        text = message.get("text", "")

        if not message_ts:
            logger.warning("Message changed event missing timestamp", event=event)
            return

        logger.info(
            "Processing message edit",
            channel=channel_id,
            message_ts=message_ts,
        )

        # Find existing signal
        existing = await self.signal_repository.get_by_slack_ts(
            workspace_id=self.workspace_id,
            channel_id=channel_id,
            message_ts=message_ts,
        )

        if not existing:
            logger.warning(
                "Signal not found for edited message",
                channel=channel_id,
                message_ts=message_ts,
            )
            return

        # Extract new source quality
        source_quality = self._extract_source_quality(text)

        # Update signal content
        await self.signal_repository.update(
            existing.id,
            {
                "content": text,
                "attachments": message.get("attachments", []),
                "source_quality": source_quality.model_dump(),
                "updated_at": datetime.utcnow(),
                "ai_generated_metadata": {
                    **(existing.ai_generated_metadata or {}),
                    "edited_at": datetime.utcnow().isoformat(),
                    "pending_re_clustering": True,  # Re-cluster after edit
                },
            },
        )

        logger.info(
            "Signal updated after message edit",
            signal_id=str(existing.id),
            channel=channel_id,
            message_ts=message_ts,
        )

    async def handle_message_deleted(self, event: dict[str, Any], say: Any) -> None:
        """Handle message deletion events.

        Args:
            event: Slack message_deleted event
            say: Slack say function (unused but required by slack-bolt)
        """
        channel_id = event["channel"]
        deleted_ts = event.get("deleted_ts")

        if not deleted_ts:
            logger.warning("Message deleted event missing timestamp", event=event)
            return

        logger.info(
            "Processing message deletion",
            channel=channel_id,
            deleted_ts=deleted_ts,
        )

        # Find existing signal
        existing = await self.signal_repository.get_by_slack_ts(
            workspace_id=self.workspace_id,
            channel_id=channel_id,
            message_ts=deleted_ts,
        )

        if not existing:
            logger.warning(
                "Signal not found for deleted message",
                channel=channel_id,
                deleted_ts=deleted_ts,
            )
            return

        # Mark signal as redacted (don't delete for audit trail)
        await self.signal_repository.update(
            existing.id,
            {
                "redacted": True,
                "updated_at": datetime.utcnow(),
                "ai_generated_metadata": {
                    **(existing.ai_generated_metadata or {}),
                    "deleted_at": datetime.utcnow().isoformat(),
                    "deletion_reason": "message_deleted_in_slack",
                },
            },
        )

        logger.info(
            "Signal marked as redacted after message deletion",
            signal_id=str(existing.id),
            channel=channel_id,
            deleted_ts=deleted_ts,
        )
