"""Unit tests for redaction service.

Tests:
- NFR-PRIVACY-002: Configurable redaction rules with facilitator override
- Regex pattern matching (email, phone, address, SSN, credit cards)
- Keyword matching (case-insensitive, multiple occurrences)
- Invalid regex handling
- Text redaction application
- Multi-field suggestion generation
- Apply redaction with audit logging
- Override redaction with justification
- Redaction status retrieval
- RedactionRuleRepository CRUD operations
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from bson import ObjectId

from integritykit.models.audit import AuditActionType, AuditTargetType
from integritykit.models.redaction import (
    DEFAULT_PATTERNS,
    AppliedRedaction,
    RedactionMatch,
    RedactionOverride,
    RedactionRule,
    RedactionRuleCreate,
    RedactionRuleType,
    RedactionStatus,
    RedactionSuggestion,
    SensitiveCategory,
)
from integritykit.models.user import User, UserRole
from integritykit.services.redaction import (
    RedactionRuleRepository,
    RedactionService,
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


def make_rule(
    *,
    rule_id: ObjectId | None = None,
    workspace_id: str = "T123456",
    name: str = "Test Rule",
    category: SensitiveCategory = SensitiveCategory.PII_EMAIL,
    rule_type: RedactionRuleType = RedactionRuleType.REGEX,
    pattern: str = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    replacement: str = "[EMAIL REDACTED]",
    is_enabled: bool = True,
    priority: int = 100,
) -> RedactionRule:
    """Create a test redaction rule."""
    return RedactionRule(
        id=rule_id or ObjectId(),
        workspace_id=workspace_id,
        name=name,
        description=f"Test rule for {category.value}",
        category=category,
        rule_type=rule_type,
        pattern=pattern,
        replacement=replacement,
        is_enabled=is_enabled,
        priority=priority,
        created_by=ObjectId(),
        created_at=datetime.now(timezone.utc),
    )


def make_match(
    *,
    rule_id: str | None = None,
    rule_name: str = "Test Rule",
    category: SensitiveCategory = SensitiveCategory.PII_EMAIL,
    matched_text: str = "test@example.com",
    start_position: int = 0,
    end_position: int | None = None,
    suggested_replacement: str = "[EMAIL REDACTED]",
    field_path: str = "text",
) -> RedactionMatch:
    """Create a test redaction match."""
    if end_position is None:
        end_position = start_position + len(matched_text)

    return RedactionMatch(
        rule_id=rule_id or str(ObjectId()),
        rule_name=rule_name,
        category=category,
        matched_text=matched_text,
        start_position=start_position,
        end_position=end_position,
        suggested_replacement=suggested_replacement,
        field_path=field_path,
    )


def make_mock_collection():
    """Create a mock MongoDB collection."""
    collection = MagicMock()
    collection.insert_one = AsyncMock()
    collection.find_one = AsyncMock()
    collection.find_one_and_update = AsyncMock()
    collection.delete_one = AsyncMock()
    collection.update_one = AsyncMock()
    collection.find = MagicMock()
    return collection


def make_mock_audit_service():
    """Create a mock audit service."""
    service = MagicMock()
    service.log_action = AsyncMock()
    return service


# ============================================================================
# RedactionMatch Tests
# ============================================================================


@pytest.mark.unit
class TestRedactionMatch:
    """Test RedactionMatch data model."""

    def test_redaction_match_creation(self) -> None:
        """RedactionMatch stores all necessary match data."""
        rule_id = str(ObjectId())

        match = RedactionMatch(
            rule_id=rule_id,
            rule_name="Email Detector",
            category=SensitiveCategory.PII_EMAIL,
            matched_text="user@example.com",
            start_position=10,
            end_position=27,
            suggested_replacement="[EMAIL REDACTED]",
            field_path="message.text",
        )

        assert match.rule_id == rule_id
        assert match.rule_name == "Email Detector"
        assert match.category == SensitiveCategory.PII_EMAIL
        assert match.matched_text == "user@example.com"
        assert match.start_position == 10
        assert match.end_position == 27
        assert match.suggested_replacement == "[EMAIL REDACTED]"
        assert match.field_path == "message.text"


# ============================================================================
# RedactionService Pattern Matching Tests
# ============================================================================


@pytest.mark.unit
class TestRedactionServicePatternMatching:
    """Test pattern matching functionality."""

    @pytest.mark.asyncio
    async def test_scan_text_no_matches(self) -> None:
        """Scanning text with no sensitive information returns empty list."""
        mock_repo = MagicMock()
        mock_repo.list_by_workspace = AsyncMock(return_value=[])

        service = RedactionService(rule_repo=mock_repo, audit_service=make_mock_audit_service())

        matches = await service.scan_text(
            text="This is a clean text with no sensitive data",
            workspace_id="T123456",
        )

        assert matches == []

    @pytest.mark.asyncio
    async def test_scan_text_regex_email_match(self) -> None:
        """Regex rule correctly detects email addresses."""
        email_rule = make_rule(
            pattern=r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            replacement="[EMAIL REDACTED]",
        )

        mock_repo = MagicMock()
        mock_repo.list_by_workspace = AsyncMock(return_value=[email_rule])

        service = RedactionService(rule_repo=mock_repo, audit_service=make_mock_audit_service())

        text = "Contact me at john.doe@example.com for more info"
        matches = await service.scan_text(text, workspace_id="T123456")

        assert len(matches) == 1
        assert matches[0].matched_text == "john.doe@example.com"
        assert matches[0].start_position == 14
        assert matches[0].end_position == 34
        assert matches[0].suggested_replacement == "[EMAIL REDACTED]"

    @pytest.mark.asyncio
    async def test_scan_text_regex_phone_match(self) -> None:
        """Regex rule correctly detects phone numbers."""
        phone_rule = make_rule(
            category=SensitiveCategory.PII_PHONE,
            pattern=r"\b(?:\+1[-.\s]?)?\(?[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
            replacement="[PHONE REDACTED]",
        )

        mock_repo = MagicMock()
        mock_repo.list_by_workspace = AsyncMock(return_value=[phone_rule])

        service = RedactionService(rule_repo=mock_repo, audit_service=make_mock_audit_service())

        text = "Call me at 555-123-4567 or 555-987-6543"
        matches = await service.scan_text(text, workspace_id="T123456")

        assert len(matches) == 2
        assert matches[0].matched_text == "555-123-4567"
        assert matches[1].matched_text == "555-987-6543"

    @pytest.mark.asyncio
    async def test_scan_text_regex_ssn_match(self) -> None:
        """Regex rule correctly detects SSN patterns."""
        ssn_rule = make_rule(
            category=SensitiveCategory.MEDICAL,
            pattern=r"\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b",
            replacement="[SSN REDACTED]",
        )

        mock_repo = MagicMock()
        mock_repo.list_by_workspace = AsyncMock(return_value=[ssn_rule])

        service = RedactionService(rule_repo=mock_repo, audit_service=make_mock_audit_service())

        text = "My SSN is 123-45-6789 for verification"
        matches = await service.scan_text(text, workspace_id="T123456")

        assert len(matches) == 1
        assert matches[0].matched_text == "123-45-6789"
        assert matches[0].category == SensitiveCategory.MEDICAL

    @pytest.mark.asyncio
    async def test_scan_text_keyword_match_case_insensitive(self) -> None:
        """Keyword rule matches case-insensitively."""
        keyword_rule = make_rule(
            rule_type=RedactionRuleType.KEYWORD,
            pattern="sensitive, confidential, secret",
            category=SensitiveCategory.CUSTOM,
            replacement="[REDACTED]",
        )

        mock_repo = MagicMock()
        mock_repo.list_by_workspace = AsyncMock(return_value=[keyword_rule])

        service = RedactionService(rule_repo=mock_repo, audit_service=make_mock_audit_service())

        text = "This is SENSITIVE information and Confidential data"
        matches = await service.scan_text(text, workspace_id="T123456")

        assert len(matches) == 2
        assert matches[0].matched_text == "SENSITIVE"
        assert matches[1].matched_text == "Confidential"

    @pytest.mark.asyncio
    async def test_scan_text_keyword_multiple_occurrences(self) -> None:
        """Keyword rule finds all occurrences of a keyword."""
        keyword_rule = make_rule(
            rule_type=RedactionRuleType.KEYWORD,
            pattern="password",
            category=SensitiveCategory.CUSTOM,
            replacement="[REDACTED]",
        )

        mock_repo = MagicMock()
        mock_repo.list_by_workspace = AsyncMock(return_value=[keyword_rule])

        service = RedactionService(rule_repo=mock_repo, audit_service=make_mock_audit_service())

        text = "My password is secret and the old password was gone"
        matches = await service.scan_text(text, workspace_id="T123456")

        assert len(matches) == 2
        assert all(m.matched_text == "password" for m in matches)

    @pytest.mark.asyncio
    async def test_scan_text_invalid_regex_skipped(self) -> None:
        """Invalid regex patterns are silently skipped."""
        invalid_rule = make_rule(
            pattern="[invalid(regex",  # Invalid regex
        )

        valid_rule = make_rule(
            pattern=r"\b\d{3}-\d{3}-\d{4}\b",
            category=SensitiveCategory.PII_PHONE,
        )

        mock_repo = MagicMock()
        mock_repo.list_by_workspace = AsyncMock(
            return_value=[invalid_rule, valid_rule]
        )

        service = RedactionService(rule_repo=mock_repo, audit_service=make_mock_audit_service())

        text = "Call 555-123-4567 for help"
        matches = await service.scan_text(text, workspace_id="T123456")

        # Only valid rule matches
        assert len(matches) == 1
        assert matches[0].matched_text == "555-123-4567"

    @pytest.mark.asyncio
    async def test_scan_text_multiple_rules_different_categories(self) -> None:
        """Multiple rules from different categories all match."""
        email_rule = make_rule(
            category=SensitiveCategory.PII_EMAIL,
            pattern=r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            replacement="[EMAIL REDACTED]",
        )

        phone_rule = make_rule(
            category=SensitiveCategory.PII_PHONE,
            pattern=r"\b\d{3}-\d{3}-\d{4}\b",
            replacement="[PHONE REDACTED]",
        )

        mock_repo = MagicMock()
        mock_repo.list_by_workspace = AsyncMock(
            return_value=[email_rule, phone_rule]
        )

        service = RedactionService(rule_repo=mock_repo, audit_service=make_mock_audit_service())

        text = "Contact john@example.com at 555-123-4567"
        matches = await service.scan_text(text, workspace_id="T123456")

        assert len(matches) == 2
        # Matches are sorted by position
        assert matches[0].matched_text == "john@example.com"
        assert matches[0].category == SensitiveCategory.PII_EMAIL
        assert matches[1].matched_text == "555-123-4567"
        assert matches[1].category == SensitiveCategory.PII_PHONE

    @pytest.mark.asyncio
    async def test_scan_text_disabled_rule_ignored(self) -> None:
        """Disabled rules are not applied during scanning."""
        disabled_rule = make_rule(
            is_enabled=False,
            pattern=r"test@example\.com",
        )

        mock_repo = MagicMock()
        # list_by_workspace with enabled_only=True won't return disabled rules
        mock_repo.list_by_workspace = AsyncMock(return_value=[])

        service = RedactionService(rule_repo=mock_repo, audit_service=make_mock_audit_service())

        text = "Send to test@example.com"
        matches = await service.scan_text(text, workspace_id="T123456")

        assert matches == []
        mock_repo.list_by_workspace.assert_called_once_with(
            "T123456", enabled_only=True
        )


# ============================================================================
# RedactionService Text Application Tests
# ============================================================================


@pytest.mark.unit
class TestApplyRedactionsToText:
    """Test applying redactions to text strings."""

    def test_apply_redactions_to_text_single_match(self) -> None:
        """Single redaction is correctly applied to text."""
        mock_repo = MagicMock()
        service = RedactionService(rule_repo=mock_repo, audit_service=make_mock_audit_service())

        text = "Contact me at john@example.com for details"
        match = make_match(
            matched_text="john@example.com",
            start_position=14,
            end_position=30,
            suggested_replacement="[EMAIL REDACTED]",
        )

        result = service.apply_redactions_to_text(text, [match])

        assert result == "Contact me at [EMAIL REDACTED] for details"

    def test_apply_redactions_to_text_multiple_matches(self) -> None:
        """Multiple redactions are applied correctly in reverse order."""
        mock_repo = MagicMock()
        service = RedactionService(rule_repo=mock_repo, audit_service=make_mock_audit_service())

        text = "Call 555-1234 or email test@example.com for help"
        matches = [
            make_match(
                matched_text="555-1234",
                start_position=5,
                end_position=13,
                suggested_replacement="[PHONE]",
            ),
            make_match(
                matched_text="test@example.com",
                start_position=23,
                end_position=39,
                suggested_replacement="[EMAIL]",
            ),
        ]

        result = service.apply_redactions_to_text(text, matches)

        assert result == "Call [PHONE] or email [EMAIL] for help"

    def test_apply_redactions_to_text_overlapping_positions(self) -> None:
        """Overlapping matches are handled correctly."""
        mock_repo = MagicMock()
        service = RedactionService(rule_repo=mock_repo, audit_service=make_mock_audit_service())

        text = "password123password"
        matches = [
            make_match(
                matched_text="password",
                start_position=0,
                end_position=8,
                suggested_replacement="[REDACTED]",
            ),
            make_match(
                matched_text="password",
                start_position=11,
                end_position=19,
                suggested_replacement="[REDACTED]",
            ),
        ]

        result = service.apply_redactions_to_text(text, matches)

        assert result == "[REDACTED]123[REDACTED]"

    def test_apply_redactions_to_text_empty_matches(self) -> None:
        """Empty match list returns original text."""
        mock_repo = MagicMock()
        service = RedactionService(rule_repo=mock_repo, audit_service=make_mock_audit_service())

        text = "No redactions needed"
        result = service.apply_redactions_to_text(text, [])

        assert result == text

    def test_apply_redactions_to_text_different_replacements(self) -> None:
        """Different replacement strings are used correctly."""
        mock_repo = MagicMock()
        service = RedactionService(rule_repo=mock_repo, audit_service=make_mock_audit_service())

        text = "SSN: 123-45-6789, CC: 4111111111111111"
        matches = [
            make_match(
                matched_text="123-45-6789",
                start_position=5,
                end_position=16,
                suggested_replacement="[SSN REDACTED]",
            ),
            make_match(
                matched_text="4111111111111111",
                start_position=22,
                end_position=38,
                suggested_replacement="[CARD REDACTED]",
            ),
        ]

        result = service.apply_redactions_to_text(text, matches)

        assert result == "SSN: [SSN REDACTED], CC: [CARD REDACTED]"


# ============================================================================
# RedactionService Suggestion Generation Tests
# ============================================================================


@pytest.mark.unit
class TestGenerateSuggestions:
    """Test redaction suggestion generation."""

    @pytest.mark.asyncio
    async def test_generate_suggestions_single_field(self) -> None:
        """Suggestions are generated for a single text field."""
        email_rule = make_rule()

        mock_repo = MagicMock()
        mock_repo.list_by_workspace = AsyncMock(return_value=[email_rule])

        service = RedactionService(rule_repo=mock_repo, audit_service=make_mock_audit_service())

        suggestion = await service.generate_suggestions(
            content_id="signal123",
            content_type="signal",
            text_fields={"text": "Email me at user@example.com"},
            workspace_id="T123456",
        )

        assert suggestion.content_id == "signal123"
        assert suggestion.content_type == "signal"
        assert suggestion.total_matches == 1
        assert len(suggestion.matches) == 1
        assert suggestion.matches[0].matched_text == "user@example.com"
        assert suggestion.matches[0].field_path == "text"
        assert SensitiveCategory.PII_EMAIL.value in suggestion.categories_detected

    @pytest.mark.asyncio
    async def test_generate_suggestions_multiple_fields(self) -> None:
        """Suggestions are generated across multiple fields."""
        email_rule = make_rule(
            category=SensitiveCategory.PII_EMAIL,
            pattern=r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        )
        phone_rule = make_rule(
            category=SensitiveCategory.PII_PHONE,
            pattern=r"\b\d{3}-\d{3}-\d{4}\b",
        )

        mock_repo = MagicMock()
        mock_repo.list_by_workspace = AsyncMock(
            return_value=[email_rule, phone_rule]
        )

        service = RedactionService(rule_repo=mock_repo, audit_service=make_mock_audit_service())

        suggestion = await service.generate_suggestions(
            content_id="signal123",
            content_type="signal",
            text_fields={
                "text": "Contact user@example.com",
                "description": "Phone: 555-123-4567",
            },
            workspace_id="T123456",
        )

        assert suggestion.total_matches == 2
        assert len(suggestion.matches) == 2

        # Check both categories detected
        assert SensitiveCategory.PII_EMAIL.value in suggestion.categories_detected
        assert SensitiveCategory.PII_PHONE.value in suggestion.categories_detected

    @pytest.mark.asyncio
    async def test_generate_suggestions_no_matches(self) -> None:
        """Suggestions with no matches return empty result."""
        mock_repo = MagicMock()
        mock_repo.list_by_workspace = AsyncMock(return_value=[])

        service = RedactionService(rule_repo=mock_repo, audit_service=make_mock_audit_service())

        suggestion = await service.generate_suggestions(
            content_id="signal123",
            content_type="signal",
            text_fields={"text": "Clean text with no issues"},
            workspace_id="T123456",
        )

        assert suggestion.total_matches == 0
        assert len(suggestion.matches) == 0
        assert len(suggestion.categories_detected) == 0

    @pytest.mark.asyncio
    async def test_generate_suggestions_empty_field_ignored(self) -> None:
        """Empty or None text fields are skipped."""
        email_rule = make_rule()

        mock_repo = MagicMock()
        mock_repo.list_by_workspace = AsyncMock(return_value=[email_rule])

        service = RedactionService(rule_repo=mock_repo, audit_service=make_mock_audit_service())

        suggestion = await service.generate_suggestions(
            content_id="signal123",
            content_type="signal",
            text_fields={
                "text": "user@example.com",
                "empty": "",
                "none": None,
            },
            workspace_id="T123456",
        )

        assert suggestion.total_matches == 1
        assert len(suggestion.matches) == 1


# ============================================================================
# RedactionService Apply Redaction Tests
# ============================================================================


@pytest.mark.unit
class TestApplyRedaction:
    """Test applying redactions to database content."""

    @pytest.mark.asyncio
    async def test_apply_redaction_updates_document(self) -> None:
        """Applying redaction updates document in database."""
        user = make_user()
        content_id = ObjectId()
        match = make_match(
            rule_id=str(ObjectId()),
            matched_text="test@example.com",
            suggested_replacement="[EMAIL REDACTED]",
            field_path="text",
        )

        mock_collection = make_mock_collection()
        mock_audit = make_mock_audit_service()

        service = RedactionService(rule_repo=MagicMock(), audit_service=mock_audit)

        applied = await service.apply_redaction(
            actor=user,
            content_id=content_id,
            content_type="signal",
            match=match,
            collection=mock_collection,
        )

        # Verify document update
        mock_collection.update_one.assert_called_once()
        call_args = mock_collection.update_one.call_args
        assert call_args[0][0] == {"_id": content_id}

        update_doc = call_args[0][1]
        assert update_doc["$set"]["redaction.is_redacted"] is True
        assert "redaction.last_scanned_at" in update_doc["$set"]
        assert update_doc["$addToSet"]["redaction.redacted_fields"] == "text"

        # Verify applied redaction details
        assert applied.rule_id == ObjectId(match.rule_id)
        assert applied.original_text == "test@example.com"
        assert applied.redacted_text == "[EMAIL REDACTED]"
        assert applied.applied_by == user.id

    @pytest.mark.asyncio
    async def test_apply_redaction_logs_to_audit(self) -> None:
        """Applying redaction logs action to audit service."""
        user = make_user()
        content_id = ObjectId()
        rule_id = ObjectId()
        match = make_match(
            rule_id=str(rule_id),
            rule_name="Email Rule",
            category=SensitiveCategory.PII_EMAIL,
            matched_text="sensitive@example.com",
            field_path="description",
        )

        mock_collection = make_mock_collection()
        mock_audit = make_mock_audit_service()

        service = RedactionService(rule_repo=MagicMock(), audit_service=mock_audit)

        await service.apply_redaction(
            actor=user,
            content_id=content_id,
            content_type="cop_candidate",
            match=match,
            collection=mock_collection,
        )

        # Verify audit log
        mock_audit.log_action.assert_called_once()
        call_kwargs = mock_audit.log_action.call_args.kwargs

        assert call_kwargs["actor"] == user
        assert call_kwargs["action_type"] == AuditActionType.REDACTION_APPLIED
        assert call_kwargs["target_type"] == AuditTargetType("cop_candidate")
        assert call_kwargs["target_id"] == content_id
        assert call_kwargs["changes_before"]["text"] == "sensitive@example.com"
        assert call_kwargs["changes_after"]["text"] == "[EMAIL REDACTED]"
        assert call_kwargs["system_context"]["rule_id"] == str(rule_id)
        assert call_kwargs["system_context"]["category"] == SensitiveCategory.PII_EMAIL.value


# ============================================================================
# RedactionService Override Tests
# ============================================================================


@pytest.mark.unit
class TestOverrideRedaction:
    """Test overriding redaction suggestions."""

    @pytest.mark.asyncio
    async def test_override_redaction_updates_document(self) -> None:
        """Overriding redaction records override in document."""
        user = make_user()
        content_id = ObjectId()
        match = make_match()

        mock_collection = make_mock_collection()
        mock_audit = make_mock_audit_service()

        service = RedactionService(rule_repo=MagicMock(), audit_service=mock_audit)

        override = await service.override_redaction(
            actor=user,
            content_id=content_id,
            content_type="signal",
            match=match,
            justification="This email is from a public official statement",
            collection=mock_collection,
        )

        # Verify document update
        mock_collection.update_one.assert_called_once()
        call_args = mock_collection.update_one.call_args
        assert call_args[0][0] == {"_id": content_id}

        update_doc = call_args[0][1]
        assert "redaction.overrides" in update_doc["$addToSet"]
        assert "redaction.last_scanned_at" in update_doc["$set"]

        # Verify override details
        assert override.content_id == content_id
        assert override.match == match
        assert override.overridden_by == user.id
        assert override.justification == "This email is from a public official statement"

    @pytest.mark.asyncio
    async def test_override_redaction_logs_with_flag(self) -> None:
        """Overriding redaction logs flagged audit entry."""
        user = make_user()
        content_id = ObjectId()
        rule_id = ObjectId()
        match = make_match(
            rule_id=str(rule_id),
            rule_name="Phone Rule",
            category=SensitiveCategory.PII_PHONE,
            matched_text="555-1234",
            suggested_replacement="[PHONE REDACTED]",
        )

        mock_collection = make_mock_collection()
        mock_audit = make_mock_audit_service()

        service = RedactionService(rule_repo=MagicMock(), audit_service=mock_audit)

        await service.override_redaction(
            actor=user,
            content_id=content_id,
            content_type="cop_update",
            match=match,
            justification="Public hotline number, not personal",
            collection=mock_collection,
        )

        # Verify audit log with flag
        mock_audit.log_action.assert_called_once()
        call_kwargs = mock_audit.log_action.call_args.kwargs

        assert call_kwargs["action_type"] == AuditActionType.REDACTION_OVERRIDE
        assert call_kwargs["is_flagged"] is True
        assert "Redaction override requires review" in call_kwargs["flag_reason"]
        assert call_kwargs["justification"] == "Public hotline number, not personal"
        assert call_kwargs["changes_before"]["suggested_redaction"] == "[PHONE REDACTED]"
        assert call_kwargs["changes_after"]["kept_original"] == "555-1234"


# ============================================================================
# RedactionService Status Tests
# ============================================================================


@pytest.mark.unit
class TestGetRedactionStatus:
    """Test retrieving redaction status."""

    @pytest.mark.asyncio
    async def test_get_redaction_status_no_redaction(self) -> None:
        """Content with no redaction returns default status."""
        content_id = ObjectId()

        mock_collection = make_mock_collection()
        mock_collection.find_one.return_value = None

        mock_repo = MagicMock()
        service = RedactionService(rule_repo=mock_repo, audit_service=make_mock_audit_service())

        status = await service.get_redaction_status(content_id, mock_collection)

        assert status.is_redacted is False
        assert len(status.redacted_fields) == 0
        assert len(status.applied_redactions) == 0
        assert len(status.overrides) == 0

    @pytest.mark.asyncio
    async def test_get_redaction_status_with_redactions(self) -> None:
        """Content with redactions returns correct status."""
        content_id = ObjectId()
        now = datetime.utcnow()

        mock_collection = make_mock_collection()
        mock_collection.find_one.return_value = {
            "_id": content_id,
            "redaction": {
                "is_redacted": True,
                "redacted_fields": ["text", "description"],
                "applied_redactions": [
                    {
                        "rule_id": ObjectId(),
                        "rule_name": "Email Rule",
                        "category": SensitiveCategory.PII_EMAIL.value,
                        "field_path": "text",
                        "original_text": "test@example.com",
                        "redacted_text": "[EMAIL REDACTED]",
                        "applied_by": ObjectId(),
                        "applied_at": now,
                    }
                ],
                "overrides": [],
                "pending_suggestions": 0,
                "last_scanned_at": now,
            },
        }

        mock_repo = MagicMock()
        service = RedactionService(rule_repo=mock_repo, audit_service=make_mock_audit_service())

        status = await service.get_redaction_status(content_id, mock_collection)

        assert status.is_redacted is True
        assert len(status.redacted_fields) == 2
        assert "text" in status.redacted_fields
        assert "description" in status.redacted_fields
        assert len(status.applied_redactions) == 1
        assert status.applied_redactions[0].original_text == "test@example.com"
        assert status.last_scanned_at == now

    @pytest.mark.asyncio
    async def test_get_redaction_status_with_overrides(self) -> None:
        """Content with overrides returns override records."""
        content_id = ObjectId()
        match_data = make_match().model_dump()

        mock_collection = make_mock_collection()
        mock_collection.find_one.return_value = {
            "_id": content_id,
            "redaction": {
                "is_redacted": False,
                "redacted_fields": [],
                "applied_redactions": [],
                "overrides": [
                    {
                        "content_id": content_id,
                        "content_type": "signal",
                        "match": match_data,
                        "overridden_by": ObjectId(),
                        "justification": "Test justification",
                        "overridden_at": datetime.utcnow(),
                    }
                ],
                "pending_suggestions": 2,
                "last_scanned_at": datetime.utcnow(),
            },
        }

        mock_repo = MagicMock()
        service = RedactionService(rule_repo=mock_repo, audit_service=make_mock_audit_service())

        status = await service.get_redaction_status(content_id, mock_collection)

        assert status.is_redacted is False
        assert len(status.overrides) == 1
        assert status.overrides[0].justification == "Test justification"
        assert status.pending_suggestions == 2


# ============================================================================
# RedactionRuleRepository CRUD Tests
# ============================================================================


@pytest.mark.unit
class TestRedactionRuleRepository:
    """Test RedactionRuleRepository CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_rule(self) -> None:
        """Creating a rule inserts into database."""
        rule_data = RedactionRuleCreate(
            workspace_id="T123456",
            name="Test Email Rule",
            description="Detects email addresses",
            category=SensitiveCategory.PII_EMAIL,
            rule_type=RedactionRuleType.REGEX,
            pattern=r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            replacement="[EMAIL REDACTED]",
            created_by=ObjectId(),
        )

        mock_collection = make_mock_collection()
        inserted_id = ObjectId()
        mock_collection.insert_one.return_value = MagicMock(inserted_id=inserted_id)

        repo = RedactionRuleRepository(collection=mock_collection)

        rule = await repo.create(rule_data)

        assert rule.id == inserted_id
        assert rule.name == "Test Email Rule"
        assert rule.workspace_id == "T123456"
        mock_collection.insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_id_found(self) -> None:
        """Getting rule by ID returns rule when found."""
        rule_id = ObjectId()

        mock_collection = make_mock_collection()
        mock_collection.find_one.return_value = {
            "_id": rule_id,
            "workspace_id": "T123456",
            "name": "Test Rule",
            "category": SensitiveCategory.PII_EMAIL.value,
            "rule_type": RedactionRuleType.REGEX.value,
            "pattern": r"test",
            "replacement": "[REDACTED]",
            "is_enabled": True,
            "priority": 100,
            "created_by": ObjectId(),
            "created_at": datetime.utcnow(),
        }

        repo = RedactionRuleRepository(collection=mock_collection)

        rule = await repo.get_by_id(rule_id)

        assert rule is not None
        assert rule.id == rule_id
        assert rule.name == "Test Rule"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self) -> None:
        """Getting rule by ID returns None when not found."""
        rule_id = ObjectId()

        mock_collection = make_mock_collection()
        mock_collection.find_one.return_value = None

        repo = RedactionRuleRepository(collection=mock_collection)

        rule = await repo.get_by_id(rule_id)

        assert rule is None

    @pytest.mark.asyncio
    async def test_list_by_workspace_enabled_only(self) -> None:
        """Listing rules filters by workspace and enabled status."""
        rule_id = ObjectId()

        mock_cursor = MagicMock()
        mock_cursor.__aiter__.return_value = iter([
            {
                "_id": rule_id,
                "workspace_id": "T123456",
                "name": "Rule 1",
                "category": SensitiveCategory.PII_EMAIL.value,
                "rule_type": RedactionRuleType.REGEX.value,
                "pattern": r"test",
                "replacement": "[REDACTED]",
                "is_enabled": True,
                "priority": 100,
                "created_by": ObjectId(),
                "created_at": datetime.utcnow(),
            }
        ])

        mock_collection = make_mock_collection()
        mock_collection.find.return_value.sort.return_value = mock_cursor

        repo = RedactionRuleRepository(collection=mock_collection)

        rules = await repo.list_by_workspace("T123456", enabled_only=True)

        assert len(rules) == 1
        assert rules[0].name == "Rule 1"

        # Verify query
        call_args = mock_collection.find.call_args[0][0]
        assert call_args["workspace_id"] == "T123456"
        assert call_args["is_enabled"] is True

    @pytest.mark.asyncio
    async def test_list_by_workspace_with_category_filter(self) -> None:
        """Listing rules can filter by category."""
        mock_cursor = MagicMock()
        mock_cursor.__aiter__.return_value = iter([])

        mock_collection = make_mock_collection()
        mock_collection.find.return_value.sort.return_value = mock_cursor

        repo = RedactionRuleRepository(collection=mock_collection)

        await repo.list_by_workspace(
            "T123456",
            enabled_only=True,
            category=SensitiveCategory.PII_PHONE,
        )

        # Verify query includes category
        call_args = mock_collection.find.call_args[0][0]
        assert call_args["category"] == SensitiveCategory.PII_PHONE.value

    @pytest.mark.asyncio
    async def test_update_rule(self) -> None:
        """Updating rule modifies document and sets updated_at."""
        rule_id = ObjectId()

        mock_collection = make_mock_collection()
        mock_collection.find_one_and_update.return_value = {
            "_id": rule_id,
            "workspace_id": "T123456",
            "name": "Updated Rule",
            "category": SensitiveCategory.PII_EMAIL.value,
            "rule_type": RedactionRuleType.REGEX.value,
            "pattern": r"updated",
            "replacement": "[UPDATED]",
            "is_enabled": False,
            "priority": 200,
            "created_by": ObjectId(),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        repo = RedactionRuleRepository(collection=mock_collection)

        updated_rule = await repo.update(
            rule_id,
            {"is_enabled": False, "priority": 200},
        )

        assert updated_rule is not None
        assert updated_rule.is_enabled is False
        assert updated_rule.priority == 200

        # Verify updated_at was set
        call_args = mock_collection.find_one_and_update.call_args[0]
        assert "updated_at" in call_args[1]["$set"]

    @pytest.mark.asyncio
    async def test_delete_rule(self) -> None:
        """Deleting rule removes from database."""
        rule_id = ObjectId()

        mock_collection = make_mock_collection()
        mock_collection.delete_one.return_value = MagicMock(deleted_count=1)

        repo = RedactionRuleRepository(collection=mock_collection)

        result = await repo.delete(rule_id)

        assert result is True
        mock_collection.delete_one.assert_called_once_with({"_id": rule_id})

    @pytest.mark.asyncio
    async def test_delete_rule_not_found(self) -> None:
        """Deleting non-existent rule returns False."""
        rule_id = ObjectId()

        mock_collection = make_mock_collection()
        mock_collection.delete_one.return_value = MagicMock(deleted_count=0)

        repo = RedactionRuleRepository(collection=mock_collection)

        result = await repo.delete(rule_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_seed_default_rules(self) -> None:
        """Seeding creates default rules from DEFAULT_PATTERNS."""
        workspace_id = "T123456"
        created_by = ObjectId()

        mock_collection = make_mock_collection()

        # Mock insert_one to return different IDs
        call_count = 0
        def mock_insert_one(doc):
            nonlocal call_count
            call_count += 1
            return MagicMock(inserted_id=ObjectId())

        mock_collection.insert_one = AsyncMock(side_effect=mock_insert_one)

        repo = RedactionRuleRepository(collection=mock_collection)

        rules = await repo.seed_default_rules(workspace_id, created_by)

        # Verify rules were created for all default patterns
        total_expected = sum(len(patterns) for patterns in DEFAULT_PATTERNS.values())
        assert len(rules) == total_expected

        # Verify all rules have correct workspace
        assert all(r.workspace_id == workspace_id for r in rules)
        assert all(r.created_by == created_by for r in rules)

        # Verify categories are represented
        categories = {r.category for r in rules}
        assert SensitiveCategory.PII_EMAIL in categories
        assert SensitiveCategory.PII_PHONE in categories
        assert SensitiveCategory.FINANCIAL in categories
