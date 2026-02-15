"""Slack App Home view for facilitators.

Implements:
- NFR-PRIVACY-001: Private facilitator views
- Backlog list, search entry, role indicator
"""

from typing import Any, Optional

import structlog
from slack_bolt.async_app import AsyncApp
from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from integritykit.models.user import Permission, User
from integritykit.services.backlog import BacklogService
from integritykit.services.database import UserRepository
from integritykit.services.rbac import RBACService

logger = structlog.get_logger(__name__)


class SlackAppHomeHandler:
    """Handler for Slack App Home tab events (NFR-PRIVACY-001).

    Displays different views based on user role:
    - Facilitators/Verifiers: Backlog list, search, role indicator
    - General participants: Welcome message and role info
    """

    def __init__(
        self,
        app: AsyncApp,
        user_repository: UserRepository,
        backlog_service: BacklogService,
        rbac_service: RBACService,
    ):
        """Initialize App Home handler.

        Args:
            app: Slack Bolt async app instance
            user_repository: User repository
            backlog_service: Backlog service for facilitators
            rbac_service: RBAC service for permission checks
        """
        self.app = app
        self.user_repo = user_repository
        self.backlog_service = backlog_service
        self.rbac_service = rbac_service
        self.client: AsyncWebClient = app.client

        # Register event listener
        self._register_listeners()

    def _register_listeners(self) -> None:
        """Register Slack event listeners."""
        self.app.event("app_home_opened")(self.handle_app_home_opened)

    async def handle_app_home_opened(
        self,
        event: dict[str, Any],
        client: AsyncWebClient,
    ) -> None:
        """Handle app_home_opened event.

        Args:
            event: Slack app_home_opened event
            client: Slack web client
        """
        user_id = event["user"]
        team_id = event.get("view", {}).get("team_id") or event.get("team_id")

        if not team_id:
            logger.warning(
                "App home opened without team_id",
                user_id=user_id,
                event=event,
            )
            return

        logger.info(
            "App home opened",
            user_id=user_id,
            team_id=team_id,
        )

        # Get or create user
        user, created = await self.user_repo.get_or_create_by_slack_id(
            slack_user_id=user_id,
            slack_team_id=team_id,
        )

        if created:
            logger.info("Created new user from app home", user_id=user_id)

        # Build and publish view based on role
        try:
            if self.rbac_service.check_permission(user, Permission.VIEW_BACKLOG):
                view = await self._build_facilitator_view(user, team_id)
            else:
                view = self._build_participant_view(user)

            await client.views_publish(
                user_id=user_id,
                view=view,
            )

            logger.info(
                "Published app home view",
                user_id=user_id,
                is_facilitator=self.rbac_service.check_permission(
                    user, Permission.VIEW_BACKLOG
                ),
            )
        except SlackApiError as e:
            logger.error(
                "Failed to publish app home view",
                user_id=user_id,
                error=str(e),
            )

    async def _build_facilitator_view(
        self,
        user: User,
        team_id: str,
    ) -> dict[str, Any]:
        """Build App Home view for facilitators.

        Args:
            user: User model
            team_id: Slack team ID

        Returns:
            Slack view object
        """
        # Get backlog stats
        try:
            stats = await self.backlog_service.get_backlog_stats(
                workspace_id=team_id,
            )
        except Exception as e:
            logger.error("Failed to get backlog stats", error=str(e))
            stats = {"total_items": 0, "items_with_conflicts": 0, "high_priority_items": 0}

        # Get top backlog items
        try:
            backlog_items = await self.backlog_service.get_backlog(
                workspace_id=team_id,
                limit=5,
                include_signals=False,
            )
        except Exception as e:
            logger.error("Failed to get backlog items", error=str(e))
            backlog_items = []

        # Get role display name
        role_display = self._get_role_display(user)

        # Build blocks
        blocks = [
            # Header with role indicator
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🛡️ IntegrityKit Facilitator Dashboard",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Your role:* {role_display}",
                },
            },
            {"type": "divider"},
            # Search section
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*🔍 Search Signals & Clusters*\nSearch across all ingested messages and clusters.",
                },
                "accessory": {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Open Search",
                        "emoji": True,
                    },
                    "action_id": "open_search_modal",
                },
            },
            {"type": "divider"},
            # Backlog stats
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*📋 Backlog Overview*",
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Total Items:*\n{stats['total_items']}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*High Priority:*\n{stats['high_priority_items']}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*With Conflicts:*\n{stats['items_with_conflicts']}",
                    },
                ],
            },
        ]

        # Add top backlog items
        if backlog_items:
            blocks.append({"type": "divider"})
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Top Priority Items*",
                    },
                }
            )

            for item in backlog_items[:5]:
                urgency_emoji = "🔴" if item.priority_scores.urgency >= 70 else "🟡" if item.priority_scores.urgency >= 40 else "🟢"
                conflict_indicator = " ⚠️" if item.has_unresolved_conflicts else ""

                blocks.append(
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"{urgency_emoji} *{item.topic}*{conflict_indicator}\n{item.summary[:100]}{'...' if len(item.summary or '') > 100 else ''}\n_Signals: {item.signal_count} | Score: {item.composite_score:.1f}_",
                        },
                        "accessory": {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "View",
                                "emoji": True,
                            },
                            "action_id": f"view_backlog_item_{item.id}",
                            "value": str(item.id),
                        },
                    }
                )
        else:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "_No items in backlog yet._",
                    },
                }
            )

        # View all button
        blocks.append({"type": "divider"})
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View Full Backlog",
                            "emoji": True,
                        },
                        "style": "primary",
                        "action_id": "view_full_backlog",
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Refresh",
                            "emoji": True,
                        },
                        "action_id": "refresh_home",
                    },
                ],
            }
        )

        # Help section
        blocks.append({"type": "divider"})
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "💡 *Tip:* Use the backlog to triage incoming signals and promote high-priority items to COP candidates.",
                    },
                ],
            }
        )

        return {
            "type": "home",
            "blocks": blocks,
        }

    def _build_participant_view(self, user: User) -> dict[str, Any]:
        """Build App Home view for general participants.

        Args:
            user: User model

        Returns:
            Slack view object
        """
        role_display = self._get_role_display(user)

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🛡️ IntegrityKit",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Your role:* {role_display}",
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Welcome to IntegrityKit! 👋\n\nYour messages in monitored channels are being processed to help generate accurate Common Operating Picture (COP) updates during crisis response.",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*How you can help:*\n• Share accurate, firsthand information\n• Include sources when possible\n• Report any errors you notice in published updates",
                },
            },
            {"type": "divider"},
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "📊 Your messages contribute to verified, trusted situation updates.",
                    },
                ],
            },
        ]

        return {
            "type": "home",
            "blocks": blocks,
        }

    def _get_role_display(self, user: User) -> str:
        """Get display string for user's roles.

        Args:
            user: User model

        Returns:
            Formatted role string
        """
        role_emojis = {
            "workspace_admin": "👑 Workspace Admin",
            "facilitator": "🎯 Facilitator",
            "verifier": "✅ Verifier",
            "general_participant": "👤 Participant",
        }

        if not user.roles:
            return role_emojis["general_participant"]

        role_displays = []
        for role in user.roles:
            role_str = role.value if hasattr(role, "value") else str(role)
            if role_str in role_emojis:
                role_displays.append(role_emojis[role_str])

        return ", ".join(role_displays) if role_displays else role_emojis["general_participant"]

    async def refresh_home(self, user_id: str, team_id: str) -> None:
        """Refresh App Home for a user.

        Args:
            user_id: Slack user ID
            team_id: Slack team ID
        """
        # Get user
        user = await self.user_repo.get_by_slack_id(
            slack_user_id=user_id,
            slack_team_id=team_id,
        )

        if not user:
            logger.warning(
                "User not found for home refresh",
                user_id=user_id,
                team_id=team_id,
            )
            return

        # Build and publish view
        try:
            if self.rbac_service.check_permission(user, Permission.VIEW_BACKLOG):
                view = await self._build_facilitator_view(user, team_id)
            else:
                view = self._build_participant_view(user)

            await self.client.views_publish(
                user_id=user_id,
                view=view,
            )

            logger.info("Refreshed app home view", user_id=user_id)
        except SlackApiError as e:
            logger.error(
                "Failed to refresh app home view",
                user_id=user_id,
                error=str(e),
            )
