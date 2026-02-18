"""Redaction service for sensitive information detection and removal.

Implements:
- NFR-PRIVACY-002: Configurable redaction rules with facilitator override
"""

import re
from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection

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
from integritykit.models.user import User
from integritykit.services.audit import AuditService, get_audit_service
from integritykit.services.database import get_collection


class RedactionRuleRepository:
    """Repository for redaction rule CRUD operations."""

    def __init__(self, collection: AsyncIOMotorCollection | None = None):
        """Initialize redaction rule repository.

        Args:
            collection: Motor collection (optional)
        """
        self.collection = collection or get_collection("redaction_rules")

    async def create(self, rule_data: RedactionRuleCreate) -> RedactionRule:
        """Create a new redaction rule.

        Args:
            rule_data: Rule creation data

        Returns:
            Created RedactionRule
        """
        rule = RedactionRule(**rule_data.model_dump())

        rule_dict = rule.model_dump(by_alias=True, exclude={"id"})
        result = await self.collection.insert_one(rule_dict)
        rule.id = result.inserted_id

        return rule

    async def get_by_id(self, rule_id: ObjectId) -> RedactionRule | None:
        """Get rule by ID.

        Args:
            rule_id: Rule ObjectId

        Returns:
            RedactionRule or None
        """
        doc = await self.collection.find_one({"_id": rule_id})
        if doc:
            return RedactionRule(**doc)
        return None

    async def list_by_workspace(
        self,
        workspace_id: str,
        enabled_only: bool = True,
        category: SensitiveCategory | None = None,
    ) -> list[RedactionRule]:
        """List rules for a workspace.

        Args:
            workspace_id: Slack workspace ID
            enabled_only: Only return enabled rules
            category: Filter by category

        Returns:
            List of RedactionRule instances
        """
        query: dict = {"workspace_id": workspace_id}

        if enabled_only:
            query["is_enabled"] = True

        if category:
            query["category"] = category.value

        cursor = self.collection.find(query).sort("priority", 1)

        rules = []
        async for doc in cursor:
            rules.append(RedactionRule(**doc))

        return rules

    async def update(
        self,
        rule_id: ObjectId,
        updates: dict,
    ) -> RedactionRule | None:
        """Update a rule.

        Args:
            rule_id: Rule ObjectId
            updates: Fields to update

        Returns:
            Updated rule or None
        """
        updates["updated_at"] = datetime.utcnow()

        result = await self.collection.find_one_and_update(
            {"_id": rule_id},
            {"$set": updates},
            return_document=True,
        )
        if result:
            return RedactionRule(**result)
        return None

    async def delete(self, rule_id: ObjectId) -> bool:
        """Delete a rule.

        Args:
            rule_id: Rule ObjectId

        Returns:
            True if deleted
        """
        result = await self.collection.delete_one({"_id": rule_id})
        return result.deleted_count > 0

    async def seed_default_rules(
        self,
        workspace_id: str,
        created_by: ObjectId,
    ) -> list[RedactionRule]:
        """Seed default redaction rules for a workspace.

        Args:
            workspace_id: Workspace ID
            created_by: Admin user ID

        Returns:
            List of created rules
        """
        created_rules = []

        for category, patterns in DEFAULT_PATTERNS.items():
            for pattern_info in patterns:
                rule_data = RedactionRuleCreate(
                    workspace_id=workspace_id,
                    name=pattern_info["name"],
                    description=f"Default rule for detecting {category.value}",
                    category=category,
                    rule_type=RedactionRuleType.REGEX,
                    pattern=pattern_info["pattern"],
                    replacement=pattern_info["replacement"],
                    created_by=created_by,
                )
                rule = await self.create(rule_data)
                created_rules.append(rule)

        return created_rules


class RedactionService:
    """Service for detecting and applying redactions (NFR-PRIVACY-002).

    Scans content for sensitive information using configurable rules
    and provides redaction suggestions. Facilitators can override
    suggestions with justification.
    """

    def __init__(
        self,
        rule_repo: RedactionRuleRepository | None = None,
        audit_service: AuditService | None = None,
    ):
        """Initialize redaction service.

        Args:
            rule_repo: Redaction rule repository
            audit_service: Audit service for logging overrides
        """
        self.rule_repo = rule_repo or RedactionRuleRepository()
        self.audit_service = audit_service or get_audit_service()

    async def scan_text(
        self,
        text: str,
        workspace_id: str,
        field_path: str = "text",
    ) -> list[RedactionMatch]:
        """Scan text for sensitive information.

        Args:
            text: Text to scan
            workspace_id: Workspace ID for rule lookup
            field_path: Path to the field being scanned

        Returns:
            List of RedactionMatch instances
        """
        rules = await self.rule_repo.list_by_workspace(workspace_id, enabled_only=True)
        matches: list[RedactionMatch] = []

        for rule in rules:
            rule_matches = self._find_matches(text, rule, field_path)
            matches.extend(rule_matches)

        # Sort by position
        matches.sort(key=lambda m: m.start_position)

        return matches

    def _find_matches(
        self,
        text: str,
        rule: RedactionRule,
        field_path: str,
    ) -> list[RedactionMatch]:
        """Find matches for a single rule.

        Args:
            text: Text to scan
            rule: Redaction rule to apply
            field_path: Field path for the match

        Returns:
            List of matches
        """
        matches = []

        if rule.rule_type == RedactionRuleType.REGEX:
            try:
                pattern = re.compile(rule.pattern, re.IGNORECASE)
                for match in pattern.finditer(text):
                    matches.append(
                        RedactionMatch(
                            rule_id=str(rule.id),
                            rule_name=rule.name,
                            category=rule.category,
                            matched_text=match.group(),
                            start_position=match.start(),
                            end_position=match.end(),
                            suggested_replacement=rule.replacement,
                            field_path=field_path,
                        )
                    )
            except re.error:
                # Invalid regex, skip this rule
                pass

        elif rule.rule_type == RedactionRuleType.KEYWORD:
            # Simple keyword matching
            keywords = [k.strip() for k in rule.pattern.split(",")]
            text_lower = text.lower()

            for keyword in keywords:
                keyword_lower = keyword.lower()
                start = 0
                while True:
                    pos = text_lower.find(keyword_lower, start)
                    if pos == -1:
                        break
                    matches.append(
                        RedactionMatch(
                            rule_id=str(rule.id),
                            rule_name=rule.name,
                            category=rule.category,
                            matched_text=text[pos : pos + len(keyword)],
                            start_position=pos,
                            end_position=pos + len(keyword),
                            suggested_replacement=rule.replacement,
                            field_path=field_path,
                        )
                    )
                    start = pos + 1

        return matches

    async def generate_suggestions(
        self,
        content_id: str,
        content_type: str,
        text_fields: dict[str, str],
        workspace_id: str,
    ) -> RedactionSuggestion:
        """Generate redaction suggestions for content.

        Args:
            content_id: ID of the content
            content_type: Type (signal, cop_candidate, cop_update)
            text_fields: Dict of field_path -> text content
            workspace_id: Workspace ID

        Returns:
            RedactionSuggestion with all matches
        """
        all_matches: list[RedactionMatch] = []
        categories_detected: set[str] = set()

        for field_path, text in text_fields.items():
            if text:
                matches = await self.scan_text(text, workspace_id, field_path)
                all_matches.extend(matches)
                categories_detected.update(m.category.value for m in matches)

        return RedactionSuggestion(
            content_id=content_id,
            content_type=content_type,
            matches=all_matches,
            total_matches=len(all_matches),
            categories_detected=list(categories_detected),
            generated_at=datetime.utcnow(),
        )

    def apply_redactions_to_text(
        self,
        text: str,
        matches: list[RedactionMatch],
    ) -> str:
        """Apply redactions to text.

        Args:
            text: Original text
            matches: Matches to redact

        Returns:
            Text with redactions applied
        """
        if not matches:
            return text

        # Sort matches by position in reverse order
        # so we can replace from end to start without offset issues
        sorted_matches = sorted(matches, key=lambda m: m.start_position, reverse=True)

        result = text
        for match in sorted_matches:
            result = (
                result[: match.start_position]
                + match.suggested_replacement
                + result[match.end_position :]
            )

        return result

    async def apply_redaction(
        self,
        actor: User,
        content_id: ObjectId,
        content_type: str,
        match: RedactionMatch,
        collection: AsyncIOMotorCollection,
    ) -> AppliedRedaction:
        """Apply a single redaction to content.

        Args:
            actor: User applying the redaction
            content_id: Content ObjectId
            content_type: Content type
            match: The match to redact
            collection: MongoDB collection for the content

        Returns:
            AppliedRedaction record
        """
        applied = AppliedRedaction(
            rule_id=ObjectId(match.rule_id),
            rule_name=match.rule_name,
            category=match.category,
            field_path=match.field_path,
            original_text=match.matched_text,
            redacted_text=match.suggested_replacement,
            applied_by=actor.id,
        )

        # Update the document
        await collection.update_one(
            {"_id": content_id},
            {
                "$set": {
                    "redaction.is_redacted": True,
                    "redaction.last_scanned_at": datetime.utcnow(),
                },
                "$addToSet": {
                    "redaction.redacted_fields": match.field_path,
                    "redaction.applied_redactions": applied.model_dump(),
                },
            },
        )

        # Log to audit
        await self.audit_service.log_action(
            actor=actor,
            action_type=AuditActionType.REDACTION_APPLIED,
            target_type=AuditTargetType(content_type),
            target_id=content_id,
            changes_before={"text": match.matched_text},
            changes_after={"text": match.suggested_replacement},
            system_context={
                "rule_id": match.rule_id,
                "rule_name": match.rule_name,
                "category": match.category.value,
                "field_path": match.field_path,
            },
        )

        return applied

    async def override_redaction(
        self,
        actor: User,
        content_id: ObjectId,
        content_type: str,
        match: RedactionMatch,
        justification: str,
        collection: AsyncIOMotorCollection,
    ) -> RedactionOverride:
        """Override a redaction suggestion (NFR-PRIVACY-002).

        Facilitators may override redactions with justification.
        The override is logged in the audit trail.

        Args:
            actor: User overriding the redaction
            content_id: Content ObjectId
            content_type: Content type
            match: The match being overridden
            justification: Required justification
            collection: MongoDB collection

        Returns:
            RedactionOverride record
        """
        override = RedactionOverride(
            content_id=content_id,
            content_type=content_type,
            match=match,
            overridden_by=actor.id,
            justification=justification,
        )

        # Record the override
        await collection.update_one(
            {"_id": content_id},
            {
                "$addToSet": {
                    "redaction.overrides": override.model_dump(),
                },
                "$set": {
                    "redaction.last_scanned_at": datetime.utcnow(),
                },
            },
        )

        # Log to audit with flag for review
        await self.audit_service.log_action(
            actor=actor,
            action_type=AuditActionType.REDACTION_OVERRIDE,
            target_type=AuditTargetType(content_type),
            target_id=content_id,
            changes_before={"suggested_redaction": match.suggested_replacement},
            changes_after={"kept_original": match.matched_text},
            justification=justification,
            system_context={
                "rule_id": match.rule_id,
                "rule_name": match.rule_name,
                "category": match.category.value,
                "field_path": match.field_path,
            },
            is_flagged=True,
            flag_reason="Redaction override requires review",
        )

        return override

    async def get_redaction_status(
        self,
        content_id: ObjectId,
        collection: AsyncIOMotorCollection,
    ) -> RedactionStatus:
        """Get redaction status for content.

        Args:
            content_id: Content ObjectId
            collection: MongoDB collection

        Returns:
            RedactionStatus
        """
        doc = await collection.find_one(
            {"_id": content_id},
            {"redaction": 1},
        )

        if not doc or "redaction" not in doc:
            return RedactionStatus()

        redaction_data = doc["redaction"]
        return RedactionStatus(
            is_redacted=redaction_data.get("is_redacted", False),
            redacted_fields=redaction_data.get("redacted_fields", []),
            applied_redactions=[
                AppliedRedaction(**r)
                for r in redaction_data.get("applied_redactions", [])
            ],
            overrides=[
                RedactionOverride(**o) for o in redaction_data.get("overrides", [])
            ],
            pending_suggestions=redaction_data.get("pending_suggestions", 0),
            last_scanned_at=redaction_data.get("last_scanned_at"),
        )


# Global service instance
_redaction_service: RedactionService | None = None


def get_redaction_service() -> RedactionService:
    """Get the global redaction service instance.

    Returns:
        RedactionService singleton
    """
    global _redaction_service
    if _redaction_service is None:
        _redaction_service = RedactionService()
    return _redaction_service


async def get_redaction_service_dependency() -> RedactionService:
    """Get redaction service (for FastAPI dependency injection).

    Returns:
        RedactionService instance
    """
    return RedactionService()
