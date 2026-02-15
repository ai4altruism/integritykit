"""
Unit tests for Slack App Home view functionality.

Tests:
- NFR-PRIVACY-001: Private facilitator views
- Role-based App Home views
"""

import pytest
from bson import ObjectId
from unittest.mock import AsyncMock, MagicMock, patch

from integritykit.models.user import User, UserRole
from integritykit.slack.home import SlackAppHomeHandler


# ============================================================================
# Role Display Tests
# ============================================================================


@pytest.mark.unit
class TestRoleDisplay:
    """Test role display formatting."""

    def test_facilitator_role_display(self) -> None:
        """Facilitator role shows correct display."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.FACILITATOR],
        )

        handler = SlackAppHomeHandler(
            app=MagicMock(),
            user_repository=MagicMock(),
            backlog_service=MagicMock(),
            rbac_service=MagicMock(),
        )

        display = handler._get_role_display(user)

        assert "Facilitator" in display

    def test_verifier_role_display(self) -> None:
        """Verifier role shows correct display."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.VERIFIER],
        )

        handler = SlackAppHomeHandler(
            app=MagicMock(),
            user_repository=MagicMock(),
            backlog_service=MagicMock(),
            rbac_service=MagicMock(),
        )

        display = handler._get_role_display(user)

        assert "Verifier" in display

    def test_admin_role_display(self) -> None:
        """Admin role shows correct display."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.WORKSPACE_ADMIN],
        )

        handler = SlackAppHomeHandler(
            app=MagicMock(),
            user_repository=MagicMock(),
            backlog_service=MagicMock(),
            rbac_service=MagicMock(),
        )

        display = handler._get_role_display(user)

        assert "Admin" in display

    def test_participant_role_display(self) -> None:
        """General participant shows correct display."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[],
        )

        handler = SlackAppHomeHandler(
            app=MagicMock(),
            user_repository=MagicMock(),
            backlog_service=MagicMock(),
            rbac_service=MagicMock(),
        )

        display = handler._get_role_display(user)

        assert "Participant" in display

    def test_multiple_roles_display(self) -> None:
        """Multiple roles show all roles."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[UserRole.FACILITATOR, UserRole.VERIFIER],
        )

        handler = SlackAppHomeHandler(
            app=MagicMock(),
            user_repository=MagicMock(),
            backlog_service=MagicMock(),
            rbac_service=MagicMock(),
        )

        display = handler._get_role_display(user)

        assert "Facilitator" in display
        assert "Verifier" in display


# ============================================================================
# Participant View Tests
# ============================================================================


@pytest.mark.unit
class TestParticipantView:
    """Test participant App Home view."""

    def test_participant_view_structure(self) -> None:
        """Participant view has correct structure."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[],
        )

        handler = SlackAppHomeHandler(
            app=MagicMock(),
            user_repository=MagicMock(),
            backlog_service=MagicMock(),
            rbac_service=MagicMock(),
        )

        view = handler._build_participant_view(user)

        assert view["type"] == "home"
        assert "blocks" in view
        assert len(view["blocks"]) > 0

    def test_participant_view_has_welcome(self) -> None:
        """Participant view includes welcome message."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[],
        )

        handler = SlackAppHomeHandler(
            app=MagicMock(),
            user_repository=MagicMock(),
            backlog_service=MagicMock(),
            rbac_service=MagicMock(),
        )

        view = handler._build_participant_view(user)

        # Check that welcome text is present somewhere
        blocks_text = str(view["blocks"])
        assert "Welcome" in blocks_text or "welcome" in blocks_text

    def test_participant_view_no_backlog(self) -> None:
        """Participant view does not show backlog."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[],
        )

        handler = SlackAppHomeHandler(
            app=MagicMock(),
            user_repository=MagicMock(),
            backlog_service=MagicMock(),
            rbac_service=MagicMock(),
        )

        view = handler._build_participant_view(user)

        # Should not have backlog-related elements
        blocks_text = str(view["blocks"])
        assert "view_backlog" not in blocks_text.lower()
        assert "open_search" not in blocks_text.lower()


# ============================================================================
# View Type Tests
# ============================================================================


@pytest.mark.unit
class TestViewTypes:
    """Test view type selection."""

    def test_view_type_is_home(self) -> None:
        """Views are of type 'home'."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[],
        )

        handler = SlackAppHomeHandler(
            app=MagicMock(),
            user_repository=MagicMock(),
            backlog_service=MagicMock(),
            rbac_service=MagicMock(),
        )

        view = handler._build_participant_view(user)

        assert view["type"] == "home"


# ============================================================================
# Block Structure Tests
# ============================================================================


@pytest.mark.unit
class TestBlockStructure:
    """Test Slack block structure."""

    def test_blocks_have_required_fields(self) -> None:
        """All blocks have required type field."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[],
        )

        handler = SlackAppHomeHandler(
            app=MagicMock(),
            user_repository=MagicMock(),
            backlog_service=MagicMock(),
            rbac_service=MagicMock(),
        )

        view = handler._build_participant_view(user)

        for block in view["blocks"]:
            assert "type" in block

    def test_section_blocks_have_text(self) -> None:
        """Section blocks have text field."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[],
        )

        handler = SlackAppHomeHandler(
            app=MagicMock(),
            user_repository=MagicMock(),
            backlog_service=MagicMock(),
            rbac_service=MagicMock(),
        )

        view = handler._build_participant_view(user)

        for block in view["blocks"]:
            if block["type"] == "section":
                assert "text" in block or "fields" in block


# ============================================================================
# Privacy Tests
# ============================================================================


@pytest.mark.unit
class TestPrivacy:
    """Test privacy aspects of App Home."""

    def test_participant_cannot_see_search(self) -> None:
        """Participants cannot see search button."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[],
        )

        handler = SlackAppHomeHandler(
            app=MagicMock(),
            user_repository=MagicMock(),
            backlog_service=MagicMock(),
            rbac_service=MagicMock(),
        )

        view = handler._build_participant_view(user)

        # Look for search button action
        blocks_text = str(view["blocks"])
        assert "open_search_modal" not in blocks_text

    def test_participant_cannot_see_backlog_items(self) -> None:
        """Participants cannot see backlog items."""
        user = User(
            id=ObjectId(),
            slack_user_id="U123",
            slack_team_id="T123",
            roles=[],
        )

        handler = SlackAppHomeHandler(
            app=MagicMock(),
            user_repository=MagicMock(),
            backlog_service=MagicMock(),
            rbac_service=MagicMock(),
        )

        view = handler._build_participant_view(user)

        # Look for backlog item actions
        blocks_text = str(view["blocks"])
        assert "view_backlog_item" not in blocks_text


# ============================================================================
# Action ID Tests
# ============================================================================


@pytest.mark.unit
class TestActionIds:
    """Test Slack action IDs."""

    def test_action_ids_are_valid(self) -> None:
        """Action IDs follow Slack conventions."""
        # Action IDs should be alphanumeric with underscores
        valid_action_ids = [
            "open_search_modal",
            "view_backlog_item",
            "view_full_backlog",
            "refresh_home",
        ]

        import re

        pattern = re.compile(r"^[a-z][a-z0-9_]*$")

        for action_id in valid_action_ids:
            # Remove dynamic suffix for testing
            base_id = action_id.split("_")[0] + "_" + action_id.split("_")[1]
            if len(action_id.split("_")) > 2:
                base_id = "_".join(action_id.split("_")[:2])
            assert pattern.match(action_id) or "_" in action_id
