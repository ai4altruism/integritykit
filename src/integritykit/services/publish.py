"""COP Update publishing service.

Implements:
- FR-COP-PUB-001: Human-approved publishing workflow
- NFR-TRANSPARENCY-001: Full audit trail
"""

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

import structlog
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection
from slack_sdk.web.async_client import AsyncWebClient

from integritykit.models.audit import AuditActionType, AuditTargetType
from integritykit.models.cop_candidate import COPCandidate
from integritykit.models.cop_update import (
    COPUpdate,
    COPUpdateCreate,
    COPUpdateStatus,
    EvidenceSnapshot,
    PublishedLineItem,
    VersionChange,
    VersionChangeType,
)
from integritykit.models.user import User
from integritykit.services.audit import AuditService, get_audit_service
from integritykit.services.database import COPCandidateRepository, get_collection
from integritykit.services.draft import COPDraft, DraftService

logger = structlog.get_logger(__name__)


class COPUpdateRepository:
    """Repository for COP Update operations."""

    def __init__(self, collection: Optional[AsyncIOMotorCollection] = None):
        """Initialize repository.

        Args:
            collection: Motor collection instance (optional)
        """
        self.collection = collection or get_collection("cop_updates")

    async def create(self, update_data: COPUpdateCreate) -> COPUpdate:
        """Create a new COP update.

        Args:
            update_data: Update creation data

        Returns:
            Created COPUpdate instance
        """
        # Get next update number for workspace
        last_update = await self.collection.find_one(
            {"workspace_id": update_data.workspace_id},
            sort=[("update_number", -1)],
        )
        next_number = (last_update.get("update_number", 0) if last_update else 0) + 1

        now = datetime.utcnow()
        update = COPUpdate(
            workspace_id=update_data.workspace_id,
            update_number=next_number,
            title=update_data.title,
            status=COPUpdateStatus.DRAFT,
            line_items=update_data.line_items,
            open_questions=update_data.open_questions,
            candidate_ids=[li.candidate_id for li in update_data.line_items],
            draft_generated_at=now,
            created_by=update_data.created_by,
            created_at=now,
        )

        update_dict = update.model_dump(by_alias=True, exclude={"id"})
        result = await self.collection.insert_one(update_dict)
        update.id = result.inserted_id

        return update

    async def get_by_id(self, update_id: ObjectId) -> Optional[COPUpdate]:
        """Get COP update by ID.

        Args:
            update_id: Update ObjectId

        Returns:
            COPUpdate or None
        """
        doc = await self.collection.find_one({"_id": update_id})
        if doc:
            return COPUpdate(**doc)
        return None

    async def update(
        self,
        update_id: ObjectId,
        updates: dict[str, Any],
    ) -> Optional[COPUpdate]:
        """Update a COP update.

        Args:
            update_id: Update ObjectId
            updates: Fields to update

        Returns:
            Updated COPUpdate or None
        """
        updates["updated_at"] = datetime.utcnow()

        result = await self.collection.find_one_and_update(
            {"_id": update_id},
            {"$set": updates},
            return_document=True,
        )

        if result:
            return COPUpdate(**result)
        return None

    async def list_by_workspace(
        self,
        workspace_id: str,
        status: Optional[COPUpdateStatus] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[COPUpdate]:
        """List COP updates for a workspace.

        Args:
            workspace_id: Workspace ID
            status: Filter by status (optional)
            limit: Maximum results
            offset: Number to skip

        Returns:
            List of COPUpdate instances
        """
        query: dict[str, Any] = {"workspace_id": workspace_id}
        if status:
            query["status"] = status.value

        cursor = (
            self.collection.find(query)
            .sort("created_at", -1)
            .skip(offset)
            .limit(limit)
        )

        updates = []
        async for doc in cursor:
            updates.append(COPUpdate(**doc))

        return updates

    async def get_latest_published(
        self,
        workspace_id: str,
    ) -> Optional[COPUpdate]:
        """Get the most recent published update for a workspace.

        Args:
            workspace_id: Workspace ID

        Returns:
            Latest published COPUpdate or None
        """
        doc = await self.collection.find_one(
            {
                "workspace_id": workspace_id,
                "status": COPUpdateStatus.PUBLISHED.value,
            },
            sort=[("published_at", -1)],
        )

        if doc:
            return COPUpdate(**doc)
        return None


class PublishService:
    """Service for COP update publishing workflow (FR-COP-PUB-001).

    Workflow:
    1. Generate draft from candidates
    2. Facilitator reviews and optionally edits
    3. Facilitator approves for publishing
    4. System posts to configured Slack channel
    5. All actions logged in audit trail
    """

    def __init__(
        self,
        update_repo: Optional[COPUpdateRepository] = None,
        candidate_repo: Optional[COPCandidateRepository] = None,
        draft_service: Optional[DraftService] = None,
        audit_service: Optional[AuditService] = None,
        slack_client: Optional[AsyncWebClient] = None,
    ):
        """Initialize publish service.

        Args:
            update_repo: COP update repository
            candidate_repo: COP candidate repository
            draft_service: Draft generation service
            audit_service: Audit logging service
            slack_client: Slack web client
        """
        self.update_repo = update_repo or COPUpdateRepository()
        self.candidate_repo = candidate_repo or COPCandidateRepository()
        self.draft_service = draft_service or DraftService(use_llm=False)
        self.audit_service = audit_service or get_audit_service()
        self.slack_client = slack_client

    async def create_draft_from_candidates(
        self,
        workspace_id: str,
        candidate_ids: list[ObjectId],
        user: User,
        title: Optional[str] = None,
    ) -> COPUpdate:
        """Create a COP update draft from selected candidates.

        Args:
            workspace_id: Slack workspace ID
            candidate_ids: List of candidate IDs to include
            user: User creating the draft
            title: Optional custom title

        Returns:
            Created COPUpdate in DRAFT status
        """
        # Load candidates
        candidates: list[COPCandidate] = []
        for cid in candidate_ids:
            candidate = await self.candidate_repo.get_by_id(cid)
            if candidate:
                candidates.append(candidate)

        if not candidates:
            raise ValueError("No valid candidates found")

        # Generate draft using draft service
        draft = await self.draft_service.generate_draft(
            workspace_id=workspace_id,
            candidates=candidates,
            title=title,
            include_open_questions=True,
        )

        # Convert to line items
        line_items = []
        for item in draft.verified_items + draft.in_review_items + draft.disproven_items:
            line_items.append(
                PublishedLineItem(
                    candidate_id=ObjectId(item.candidate_id),
                    section=item.section.value,
                    status_label=item.status_label,
                    text=item.line_item_text,
                    citations=item.citations,
                    was_edited=False,
                )
            )

        # Create update
        update_data = COPUpdateCreate(
            workspace_id=workspace_id,
            title=draft.title,
            line_items=line_items,
            open_questions=draft.open_questions,
            created_by=user.id,
        )

        update = await self.update_repo.create(update_data)

        # Log to audit
        await self.audit_service.log_action(
            actor=user,
            action_type=AuditActionType.COP_UPDATE_PUBLISH,
            target_type=AuditTargetType.COP_UPDATE,
            target_id=update.id,
            changes_after={
                "status": "draft",
                "candidate_count": len(candidates),
                "line_item_count": len(line_items),
            },
            system_context={
                "action": "create_draft",
                "workspace_id": workspace_id,
            },
        )

        logger.info(
            "Created COP update draft",
            update_id=str(update.id),
            workspace_id=workspace_id,
            candidate_count=len(candidates),
            line_item_count=len(line_items),
        )

        return update

    async def edit_line_item(
        self,
        update_id: ObjectId,
        item_index: int,
        new_text: str,
        user: User,
    ) -> COPUpdate:
        """Edit a line item in a draft.

        Args:
            update_id: Update ID
            item_index: Index of line item to edit
            new_text: New text for the line item
            user: User making the edit

        Returns:
            Updated COPUpdate
        """
        update = await self.update_repo.get_by_id(update_id)
        if not update:
            raise ValueError("Update not found")

        if update.status not in [COPUpdateStatus.DRAFT, COPUpdateStatus.PENDING_APPROVAL]:
            raise ValueError("Cannot edit a published update")

        if item_index >= len(update.line_items):
            raise ValueError("Invalid line item index")

        # Store original text if first edit
        line_item = update.line_items[item_index]
        original_text = line_item.original_text or line_item.text

        # Update the line item
        update.line_items[item_index].text = new_text
        update.line_items[item_index].was_edited = True
        update.line_items[item_index].original_text = original_text

        # Update metadata
        updated = await self.update_repo.update(
            update_id,
            {
                "line_items": [li.model_dump() for li in update.line_items],
                "edit_count": update.edit_count + 1,
                "last_edited_by": user.id,
                "last_edited_at": datetime.utcnow(),
            },
        )

        # Log to audit
        await self.audit_service.log_action(
            actor=user,
            action_type=AuditActionType.COP_UPDATE_OVERRIDE,
            target_type=AuditTargetType.COP_UPDATE,
            target_id=update_id,
            changes_before={"text": original_text},
            changes_after={"text": new_text},
            system_context={
                "action": "edit_line_item",
                "item_index": item_index,
            },
        )

        logger.info(
            "Edited COP update line item",
            update_id=str(update_id),
            item_index=item_index,
            user_id=str(user.id),
        )

        return updated

    async def approve(
        self,
        update_id: ObjectId,
        user: User,
        notes: Optional[str] = None,
    ) -> COPUpdate:
        """Approve a COP update for publishing (FR-COP-PUB-001).

        This is the required human approval step before publishing.

        Args:
            update_id: Update ID to approve
            user: Facilitator approving
            notes: Optional approval notes

        Returns:
            Updated COPUpdate with APPROVED status
        """
        update = await self.update_repo.get_by_id(update_id)
        if not update:
            raise ValueError("Update not found")

        if update.status == COPUpdateStatus.PUBLISHED:
            raise ValueError("Update is already published")

        if update.status == COPUpdateStatus.SUPERSEDED:
            raise ValueError("Update has been superseded")

        now = datetime.utcnow()
        updated = await self.update_repo.update(
            update_id,
            {
                "status": COPUpdateStatus.APPROVED.value,
                "approved_by": user.id,
                "approved_at": now,
                "approval_notes": notes,
            },
        )

        # Log to audit
        await self.audit_service.log_action(
            actor=user,
            action_type=AuditActionType.COP_UPDATE_PUBLISH,
            target_type=AuditTargetType.COP_UPDATE,
            target_id=update_id,
            changes_before={"status": update.status.value},
            changes_after={"status": "approved"},
            justification=notes,
            system_context={
                "action": "approve",
            },
        )

        logger.info(
            "Approved COP update for publishing",
            update_id=str(update_id),
            approved_by=str(user.id),
        )

        return updated

    async def publish_to_slack(
        self,
        update_id: ObjectId,
        channel_id: str,
        user: User,
    ) -> COPUpdate:
        """Publish an approved COP update to Slack (FR-COP-PUB-001).

        Requires prior human approval.

        Args:
            update_id: Update ID to publish
            channel_id: Slack channel to post to
            user: User triggering the publish

        Returns:
            Updated COPUpdate with PUBLISHED status
        """
        update = await self.update_repo.get_by_id(update_id)
        if not update:
            raise ValueError("Update not found")

        if update.status != COPUpdateStatus.APPROVED:
            raise ValueError(
                "Update must be approved before publishing. "
                "No automated publishing without human approval."
            )

        if not self.slack_client:
            raise ValueError("Slack client not configured")

        # Build Slack blocks
        blocks = self._build_slack_blocks(update)

        # Post to Slack
        try:
            response = await self.slack_client.chat_postMessage(
                channel=channel_id,
                text=f"COP Update #{update.update_number}: {update.title}",
                blocks=blocks,
            )

            message_ts = response["ts"]
            permalink_response = await self.slack_client.chat_getPermalink(
                channel=channel_id,
                message_ts=message_ts,
            )
            permalink = permalink_response.get("permalink")

        except Exception as e:
            logger.error(
                "Failed to post COP update to Slack",
                update_id=str(update_id),
                channel_id=channel_id,
                error=str(e),
            )
            raise ValueError(f"Failed to post to Slack: {e}")

        # Update record
        now = datetime.utcnow()
        updated = await self.update_repo.update(
            update_id,
            {
                "status": COPUpdateStatus.PUBLISHED.value,
                "published_at": now,
                "slack_channel_id": channel_id,
                "slack_message_ts": message_ts,
                "slack_permalink": permalink,
            },
        )

        # Mark candidates as published
        for candidate_id in update.candidate_ids:
            await self.candidate_repo.update(
                candidate_id,
                {
                    "$push": {"published_in_cop_update_ids": update.id},
                },
            )

        # Supersede previous published updates
        previous = await self.update_repo.get_latest_published(update.workspace_id)
        if previous and previous.id != update.id:
            await self.update_repo.update(
                previous.id,
                {
                    "status": COPUpdateStatus.SUPERSEDED.value,
                    "superseded_by": update.id,
                    "superseded_at": now,
                },
            )

        # Log to audit
        await self.audit_service.log_action(
            actor=user,
            action_type=AuditActionType.COP_UPDATE_PUBLISH,
            target_type=AuditTargetType.COP_UPDATE,
            target_id=update_id,
            changes_before={"status": "approved"},
            changes_after={
                "status": "published",
                "slack_channel_id": channel_id,
                "slack_permalink": permalink,
            },
            system_context={
                "action": "publish_to_slack",
                "message_ts": message_ts,
            },
        )

        logger.info(
            "Published COP update to Slack",
            update_id=str(update_id),
            channel_id=channel_id,
            permalink=permalink,
        )

        return updated

    def _build_slack_blocks(self, update: COPUpdate) -> list[dict]:
        """Build Slack Block Kit blocks for COP update.

        Args:
            update: COP update to format

        Returns:
            List of Slack blocks
        """
        blocks = []

        # Header
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"COP Update #{update.update_number}: {update.title}",
                "emoji": True,
            },
        })

        # Timestamp
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"*Published:* <!date^{int(datetime.utcnow().timestamp())}^{{date_short_pretty}} at {{time}}|{datetime.utcnow().isoformat()}>",
                },
            ],
        })

        blocks.append({"type": "divider"})

        # Group items by section
        verified = [li for li in update.line_items if li.section == "verified"]
        in_review = [li for li in update.line_items if li.section == "in_review"]
        disproven = [li for li in update.line_items if li.section == "disproven"]

        # Verified section
        if verified:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*:white_check_mark: Verified Updates*",
                },
            })

            for item in verified:
                citation_text = ""
                if item.citations:
                    citation_links = [f"<{url}|[{i+1}]>" for i, url in enumerate(item.citations)]
                    citation_text = f" {' '.join(citation_links)}"

                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{item.status_label}* {item.text}{citation_text}",
                    },
                })

            blocks.append({"type": "divider"})

        # In Review section
        if in_review:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*:hourglass_flowing_sand: In Review (Unconfirmed)*",
                },
            })

            for item in in_review:
                citation_text = ""
                if item.citations:
                    citation_links = [f"<{url}|[{i+1}]>" for i, url in enumerate(item.citations)]
                    citation_text = f" {' '.join(citation_links)}"

                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{item.status_label}* {item.text}{citation_text}",
                    },
                })

            blocks.append({"type": "divider"})

        # Disproven/Rumor Control section
        if disproven:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*:x: Rumor Control / Corrections*",
                },
            })

            for item in disproven:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{item.status_label}* {item.text}",
                    },
                })

            blocks.append({"type": "divider"})

        # Open Questions section
        if update.open_questions:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*:question: Open Questions / Gaps*",
                },
            })

            for question in update.open_questions:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"- {question}",
                    },
                })

        # Footer
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "_This update was generated by IntegrityKit and reviewed by a facilitator before publishing._",
                },
            ],
        })

        return blocks

    async def get_draft_preview(
        self,
        update_id: ObjectId,
    ) -> dict:
        """Get a preview of the update as it would appear.

        Args:
            update_id: Update ID

        Returns:
            Preview dict with blocks and markdown
        """
        update = await self.update_repo.get_by_id(update_id)
        if not update:
            raise ValueError("Update not found")

        blocks = self._build_slack_blocks(update)

        # Also generate markdown
        markdown = self._build_markdown(update)

        return {
            "blocks": blocks,
            "markdown": markdown,
            "update": update,
        }

    def _build_markdown(self, update: COPUpdate) -> str:
        """Build markdown representation of COP update.

        Args:
            update: COP update

        Returns:
            Markdown string
        """
        lines = [f"# COP Update #{update.update_number}: {update.title}"]
        lines.append(f"*Generated: {datetime.utcnow().isoformat()}*")
        lines.append("")

        verified = [li for li in update.line_items if li.section == "verified"]
        in_review = [li for li in update.line_items if li.section == "in_review"]
        disproven = [li for li in update.line_items if li.section == "disproven"]

        if verified:
            lines.append("## Verified Updates")
            for item in verified:
                lines.append(f"- **{item.status_label}** {item.text}")
            lines.append("")

        if in_review:
            lines.append("## In Review (Unconfirmed)")
            for item in in_review:
                lines.append(f"- **{item.status_label}** {item.text}")
            lines.append("")

        if disproven:
            lines.append("## Rumor Control / Corrections")
            for item in disproven:
                lines.append(f"- **{item.status_label}** {item.text}")
            lines.append("")

        if update.open_questions:
            lines.append("## Open Questions / Gaps")
            for q in update.open_questions:
                lines.append(f"- {q}")
            lines.append("")

        return "\n".join(lines)

    async def capture_evidence_snapshots(
        self,
        candidates: list[COPCandidate],
    ) -> list[EvidenceSnapshot]:
        """Capture evidence snapshots for all candidates at publication time (S7-2).

        Freezes the state of all evidence to ensure accountability.

        Args:
            candidates: List of candidates to snapshot

        Returns:
            List of EvidenceSnapshot objects
        """
        snapshots = []
        now = datetime.utcnow()

        for candidate in candidates:
            # Convert evidence to serializable dicts
            slack_permalinks = []
            for permalink in candidate.evidence.slack_permalinks:
                slack_permalinks.append({
                    "url": permalink.url,
                    "signal_id": str(permalink.signal_id) if permalink.signal_id else None,
                    "description": permalink.description,
                })

            external_sources = []
            for source in candidate.evidence.external_sources:
                external_sources.append({
                    "url": source.url,
                    "source_name": source.source_name,
                    "retrieved_at": source.retrieved_at.isoformat(),
                    "description": source.description,
                })

            verifications = []
            for verification in candidate.verifications:
                verifications.append({
                    "verified_by": str(verification.verified_by),
                    "verified_at": verification.verified_at.isoformat(),
                    "verification_method": verification.verification_method.value
                    if hasattr(verification.verification_method, "value")
                    else verification.verification_method,
                    "verification_notes": verification.verification_notes,
                    "confidence_level": verification.confidence_level.value
                    if hasattr(verification.confidence_level, "value")
                    else verification.confidence_level,
                })

            # Capture COP fields
            fields_snapshot = {
                "what": candidate.fields.what,
                "where": candidate.fields.where,
                "when": {
                    "timestamp": candidate.fields.when.timestamp.isoformat()
                    if candidate.fields.when.timestamp else None,
                    "timezone": candidate.fields.when.timezone,
                    "is_approximate": candidate.fields.when.is_approximate,
                    "description": candidate.fields.when.description,
                },
                "who": candidate.fields.who,
                "so_what": candidate.fields.so_what,
            }

            snapshot = EvidenceSnapshot(
                candidate_id=candidate.id,
                slack_permalinks=slack_permalinks,
                external_sources=external_sources,
                verifications=verifications,
                risk_tier=candidate.risk_tier
                if isinstance(candidate.risk_tier, str)
                else candidate.risk_tier.value,
                readiness_state=candidate.readiness_state
                if isinstance(candidate.readiness_state, str)
                else candidate.readiness_state.value,
                fields_snapshot=fields_snapshot,
                captured_at=now,
            )
            snapshots.append(snapshot)

        logger.info(
            "Captured evidence snapshots",
            candidate_count=len(candidates),
            snapshot_count=len(snapshots),
        )

        return snapshots

    def compute_version_changes(
        self,
        previous_update: COPUpdate,
        new_update: COPUpdate,
    ) -> tuple[list[VersionChange], str]:
        """Compute changes between two COP update versions (S7-2).

        Args:
            previous_update: The previous version
            new_update: The new version

        Returns:
            Tuple of (list of changes, human-readable summary)
        """
        changes = []

        # Build lookup maps
        prev_items = {str(li.candidate_id): li for li in previous_update.line_items}
        new_items = {str(li.candidate_id): li for li in new_update.line_items}

        # Find removed items
        for cid, item in prev_items.items():
            if cid not in new_items:
                changes.append(VersionChange(
                    change_type=VersionChangeType.REMOVED,
                    candidate_id=item.candidate_id,
                    old_value=item.text,
                    description=f"Removed: {item.text[:50]}...",
                ))

        # Find added and modified items
        for cid, new_item in new_items.items():
            if cid not in prev_items:
                changes.append(VersionChange(
                    change_type=VersionChangeType.ADDED,
                    candidate_id=new_item.candidate_id,
                    new_value=new_item.text,
                    description=f"Added: {new_item.text[:50]}...",
                ))
            else:
                prev_item = prev_items[cid]

                # Check for section change
                if prev_item.section != new_item.section:
                    if prev_item.section == "in_review" and new_item.section == "verified":
                        change_type = VersionChangeType.PROMOTED
                        desc = f"Promoted to verified: {new_item.text[:50]}..."
                    elif prev_item.section == "verified" and new_item.section == "in_review":
                        change_type = VersionChangeType.DEMOTED
                        desc = f"Demoted to in review: {new_item.text[:50]}..."
                    else:
                        change_type = VersionChangeType.STATUS_CHANGED
                        desc = f"Moved from {prev_item.section} to {new_item.section}"

                    changes.append(VersionChange(
                        change_type=change_type,
                        candidate_id=new_item.candidate_id,
                        field="section",
                        old_value=prev_item.section,
                        new_value=new_item.section,
                        description=desc,
                    ))

                # Check for text change
                if prev_item.text != new_item.text:
                    changes.append(VersionChange(
                        change_type=VersionChangeType.MODIFIED,
                        candidate_id=new_item.candidate_id,
                        field="text",
                        old_value=prev_item.text,
                        new_value=new_item.text,
                        description=f"Text updated: {new_item.text[:50]}...",
                    ))

        # Generate summary
        added = len([c for c in changes if c.change_type == VersionChangeType.ADDED])
        removed = len([c for c in changes if c.change_type == VersionChangeType.REMOVED])
        modified = len([c for c in changes if c.change_type == VersionChangeType.MODIFIED])
        promoted = len([c for c in changes if c.change_type == VersionChangeType.PROMOTED])

        summary_parts = []
        if added:
            summary_parts.append(f"{added} item(s) added")
        if removed:
            summary_parts.append(f"{removed} item(s) removed")
        if modified:
            summary_parts.append(f"{modified} item(s) modified")
        if promoted:
            summary_parts.append(f"{promoted} item(s) promoted to verified")

        summary = "; ".join(summary_parts) if summary_parts else "No changes"

        return changes, summary

    def increment_version(
        self,
        current_version: str,
        has_major_changes: bool = False,
    ) -> str:
        """Increment version number.

        Args:
            current_version: Current version string (e.g., "1.0")
            has_major_changes: True for major version bump (items removed/promoted)

        Returns:
            New version string
        """
        parts = current_version.split(".")
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0

        if has_major_changes:
            return f"{major + 1}.0"
        else:
            return f"{major}.{minor + 1}"

    async def create_new_version(
        self,
        previous_update: COPUpdate,
        candidate_ids: list[ObjectId],
        user: User,
        title: Optional[str] = None,
    ) -> COPUpdate:
        """Create a new version of a COP update (S7-2).

        Args:
            previous_update: Previous update to base new version on
            candidate_ids: Candidate IDs for the new version
            user: User creating the new version
            title: Optional new title

        Returns:
            New COPUpdate with version tracking
        """
        # Load candidates
        candidates: list[COPCandidate] = []
        for cid in candidate_ids:
            candidate = await self.candidate_repo.get_by_id(cid)
            if candidate:
                candidates.append(candidate)

        if not candidates:
            raise ValueError("No valid candidates found")

        # Generate new draft
        draft = await self.draft_service.generate_draft(
            workspace_id=previous_update.workspace_id,
            candidates=candidates,
            title=title or previous_update.title,
            include_open_questions=True,
        )

        # Convert to line items
        line_items = []
        for item in draft.verified_items + draft.in_review_items + draft.disproven_items:
            line_items.append(
                PublishedLineItem(
                    candidate_id=ObjectId(item.candidate_id),
                    section=item.section.value,
                    status_label=item.status_label,
                    text=item.line_item_text,
                    citations=item.citations,
                    was_edited=False,
                )
            )

        # Capture evidence snapshots
        evidence_snapshots = await self.capture_evidence_snapshots(candidates)

        # Compute version changes
        # Create temporary update for comparison
        temp_update = COPUpdate(
            workspace_id=previous_update.workspace_id,
            title=draft.title,
            line_items=line_items,
            open_questions=draft.open_questions,
            created_by=user.id,
        )

        changes, change_summary = self.compute_version_changes(previous_update, temp_update)

        # Determine if major version bump needed
        has_major = any(
            c.change_type in [
                VersionChangeType.REMOVED,
                VersionChangeType.PROMOTED,
                VersionChangeType.DEMOTED,
            ]
            for c in changes
        )
        new_version = self.increment_version(previous_update.version, has_major)

        # Get next update number
        last_update = await self.update_repo.collection.find_one(
            {"workspace_id": previous_update.workspace_id},
            sort=[("update_number", -1)],
        )
        next_number = (last_update.get("update_number", 0) if last_update else 0) + 1

        # Create the new update
        now = datetime.utcnow()
        new_update = COPUpdate(
            workspace_id=previous_update.workspace_id,
            update_number=next_number,
            title=draft.title,
            status=COPUpdateStatus.DRAFT,
            line_items=line_items,
            open_questions=draft.open_questions,
            version=new_version,
            previous_version_id=previous_update.id,
            version_changes=changes,
            change_summary=change_summary,
            evidence_snapshots=evidence_snapshots,
            candidate_ids=[c.id for c in candidates],
            draft_generated_at=now,
            created_by=user.id,
            created_at=now,
        )

        # Insert to database
        update_dict = new_update.model_dump(by_alias=True, exclude={"id"})
        # Convert version changes to dicts for MongoDB
        update_dict["version_changes"] = [vc.model_dump() for vc in changes]
        update_dict["evidence_snapshots"] = [es.model_dump() for es in evidence_snapshots]

        result = await self.update_repo.collection.insert_one(update_dict)
        new_update.id = result.inserted_id

        # Log to audit
        await self.audit_service.log_action(
            actor=user,
            action_type=AuditActionType.COP_UPDATE_PUBLISH,
            target_type=AuditTargetType.COP_UPDATE,
            target_id=new_update.id,
            changes_before={"version": previous_update.version},
            changes_after={
                "version": new_version,
                "change_count": len(changes),
            },
            system_context={
                "action": "create_new_version",
                "previous_version_id": str(previous_update.id),
                "change_summary": change_summary,
            },
        )

        logger.info(
            "Created new COP update version",
            update_id=str(new_update.id),
            version=new_version,
            previous_version_id=str(previous_update.id),
            change_count=len(changes),
        )

        return new_update

    async def get_version_history(
        self,
        update_id: ObjectId,
    ) -> list[COPUpdate]:
        """Get the version history for a COP update (S7-2).

        Args:
            update_id: ID of any update in the version chain

        Returns:
            List of all versions, oldest first
        """
        history = []
        current = await self.update_repo.get_by_id(update_id)

        if not current:
            return history

        # Traverse back to find all previous versions
        while current:
            history.insert(0, current)
            if current.previous_version_id:
                current = await self.update_repo.get_by_id(current.previous_version_id)
            else:
                break

        return history


# Clarification templates (S4-4)
CLARIFICATION_TEMPLATES = {
    "location": (
        "Hi! We're tracking an update about *{topic}*. "
        "Could you help clarify the specific location? "
        "Any details like street address, neighborhood, or nearby landmarks would be helpful."
    ),
    "time": (
        "Hi! Regarding *{topic}* - could you clarify when this occurred or is expected? "
        "Approximate times are fine (e.g., 'around 2pm', 'earlier today')."
    ),
    "source": (
        "Hi! We're working on verifying information about *{topic}*. "
        "Do you have a source for this info, or did you witness it firsthand?"
    ),
    "status": (
        "Hi! We're updating the COP on *{topic}*. "
        "Do you know the current status? Has the situation changed since you last reported?"
    ),
    "impact": (
        "Hi! Regarding *{topic}* - can you help us understand who or what is affected? "
        "This helps us prioritize and coordinate response."
    ),
    "general": (
        "Hi! We're working on a COP update and wanted to follow up on your message about *{topic}*. "
        "Any additional details you can share would be helpful."
    ),
}


def get_clarification_template(template_type: str, topic: str) -> str:
    """Get a clarification request template.

    Args:
        template_type: Type of clarification (location, time, source, status, impact, general)
        topic: Topic to insert into template

    Returns:
        Formatted template string
    """
    template = CLARIFICATION_TEMPLATES.get(template_type, CLARIFICATION_TEMPLATES["general"])
    return template.format(topic=topic)
