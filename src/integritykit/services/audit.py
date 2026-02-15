"""Audit logging service for immutable action history.

Implements:
- FR-AUD-001: Immutable audit log
- FR-ROLE-003: Role-change audit logging
- NFR-ABUSE-001: Abuse detection signals
"""

from datetime import datetime
from typing import Any, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection

from integritykit.models.audit import (
    AuditActionType,
    AuditChanges,
    AuditLogCreate,
    AuditLogEntry,
    AuditTargetType,
)
from integritykit.models.user import User, UserRole
from integritykit.services.database import get_collection


class AuditRepository:
    """Repository for audit log operations.

    Audit log entries are immutable - only insert and read operations are supported.
    """

    def __init__(self, collection: Optional[AsyncIOMotorCollection] = None):
        """Initialize audit repository.

        Args:
            collection: Motor collection instance (optional, uses default if not provided)
        """
        self.collection = collection or get_collection("audit_log")

    async def create(self, entry_data: AuditLogCreate) -> AuditLogEntry:
        """Create a new audit log entry.

        Args:
            entry_data: Audit entry creation data

        Returns:
            Created AuditLogEntry instance with ID
        """
        now = datetime.utcnow()
        entry = AuditLogEntry(
            timestamp=now,
            created_at=now,
            **entry_data.model_dump(),
        )

        # Convert to dict for MongoDB insertion
        entry_dict = entry.model_dump(by_alias=True, exclude={"id"})

        result = await self.collection.insert_one(entry_dict)
        entry.id = result.inserted_id

        return entry

    async def get_by_id(self, entry_id: ObjectId) -> Optional[AuditLogEntry]:
        """Get audit entry by ID.

        Args:
            entry_id: Entry ObjectId

        Returns:
            AuditLogEntry or None if not found
        """
        doc = await self.collection.find_one({"_id": entry_id})
        if doc:
            return AuditLogEntry(**doc)
        return None

    async def list_by_actor(
        self,
        actor_id: ObjectId,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLogEntry]:
        """List audit entries by actor.

        Args:
            actor_id: Actor user ID
            limit: Maximum entries to return
            offset: Number of entries to skip

        Returns:
            List of AuditLogEntry instances
        """
        cursor = (
            self.collection.find({"actor_id": actor_id})
            .sort("timestamp", -1)
            .skip(offset)
            .limit(limit)
        )

        entries = []
        async for doc in cursor:
            entries.append(AuditLogEntry(**doc))

        return entries

    async def list_by_entity(
        self,
        entity_type: AuditTargetType,
        entity_id: ObjectId,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLogEntry]:
        """List audit entries for a specific entity.

        Args:
            entity_type: Type of entity
            entity_id: Entity ObjectId
            limit: Maximum entries to return
            offset: Number of entries to skip

        Returns:
            List of AuditLogEntry instances
        """
        cursor = (
            self.collection.find(
                {
                    "target_entity_type": entity_type.value,
                    "target_entity_id": entity_id,
                }
            )
            .sort("timestamp", -1)
            .skip(offset)
            .limit(limit)
        )

        entries = []
        async for doc in cursor:
            entries.append(AuditLogEntry(**doc))

        return entries

    async def list_by_action_type(
        self,
        action_type: AuditActionType,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLogEntry]:
        """List audit entries by action type.

        Args:
            action_type: Type of action
            limit: Maximum entries to return
            offset: Number of entries to skip

        Returns:
            List of AuditLogEntry instances
        """
        cursor = (
            self.collection.find({"action_type": action_type.value})
            .sort("timestamp", -1)
            .skip(offset)
            .limit(limit)
        )

        entries = []
        async for doc in cursor:
            entries.append(AuditLogEntry(**doc))

        return entries

    async def list_flagged(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLogEntry]:
        """List flagged audit entries for abuse detection.

        Args:
            limit: Maximum entries to return
            offset: Number of entries to skip

        Returns:
            List of flagged AuditLogEntry instances
        """
        cursor = (
            self.collection.find({"is_flagged": True})
            .sort("timestamp", -1)
            .skip(offset)
            .limit(limit)
        )

        entries = []
        async for doc in cursor:
            entries.append(AuditLogEntry(**doc))

        return entries

    async def list_role_changes(
        self,
        target_user_id: Optional[ObjectId] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLogEntry]:
        """List role change audit entries (FR-ROLE-003).

        Args:
            target_user_id: Filter by target user (optional)
            limit: Maximum entries to return
            offset: Number of entries to skip

        Returns:
            List of role change AuditLogEntry instances
        """
        query = {"action_type": AuditActionType.USER_ROLE_CHANGE.value}

        if target_user_id:
            query["target_entity_id"] = target_user_id

        cursor = (
            self.collection.find(query)
            .sort("timestamp", -1)
            .skip(offset)
            .limit(limit)
        )

        entries = []
        async for doc in cursor:
            entries.append(AuditLogEntry(**doc))

        return entries

    async def list_all(
        self,
        action_type: Optional[AuditActionType] = None,
        target_entity_type: Optional[AuditTargetType] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLogEntry]:
        """List audit entries with filters.

        Args:
            action_type: Filter by action type (optional)
            target_entity_type: Filter by entity type (optional)
            start_time: Filter entries after this time (optional)
            end_time: Filter entries before this time (optional)
            limit: Maximum entries to return
            offset: Number of entries to skip

        Returns:
            List of AuditLogEntry instances
        """
        query: dict[str, Any] = {}

        if action_type:
            query["action_type"] = action_type.value

        if target_entity_type:
            query["target_entity_type"] = target_entity_type.value

        if start_time or end_time:
            query["timestamp"] = {}
            if start_time:
                query["timestamp"]["$gte"] = start_time
            if end_time:
                query["timestamp"]["$lte"] = end_time

        cursor = (
            self.collection.find(query)
            .sort("timestamp", -1)
            .skip(offset)
            .limit(limit)
        )

        entries = []
        async for doc in cursor:
            entries.append(AuditLogEntry(**doc))

        return entries

    async def count(
        self,
        action_type: Optional[AuditActionType] = None,
        target_entity_type: Optional[AuditTargetType] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        """Count audit entries with filters.

        Args:
            action_type: Filter by action type (optional)
            target_entity_type: Filter by entity type (optional)
            start_time: Filter entries after this time (optional)
            end_time: Filter entries before this time (optional)

        Returns:
            Count of matching entries
        """
        query: dict[str, Any] = {}

        if action_type:
            query["action_type"] = action_type.value

        if target_entity_type:
            query["target_entity_type"] = target_entity_type.value

        if start_time or end_time:
            query["timestamp"] = {}
            if start_time:
                query["timestamp"]["$gte"] = start_time
            if end_time:
                query["timestamp"]["$lte"] = end_time

        return await self.collection.count_documents(query)


class AuditService:
    """Service for creating audit log entries.

    Provides high-level methods for logging various actions.
    """

    def __init__(self, repository: Optional[AuditRepository] = None):
        """Initialize audit service.

        Args:
            repository: AuditRepository instance (optional)
        """
        self.repository = repository or AuditRepository()

    async def log_role_change(
        self,
        actor: User,
        target_user: User,
        old_roles: list[str],
        new_roles: list[str],
        justification: Optional[str] = None,
        actor_ip: Optional[str] = None,
    ) -> AuditLogEntry:
        """Log a role change event (FR-ROLE-003).

        Args:
            actor: User who performed the action
            target_user: User whose roles changed
            old_roles: Roles before change
            new_roles: Roles after change
            justification: Reason for change
            actor_ip: IP address of actor

        Returns:
            Created AuditLogEntry
        """
        # Determine actor's highest role for logging
        actor_role = self._get_highest_role(actor)

        entry_data = AuditLogCreate(
            actor_id=actor.id,
            actor_role=actor_role,
            actor_ip=actor_ip,
            action_type=AuditActionType.USER_ROLE_CHANGE,
            target_entity_type=AuditTargetType.USER,
            target_entity_id=target_user.id,
            changes=AuditChanges(
                before={"roles": old_roles},
                after={"roles": new_roles},
            ),
            justification=justification,
            system_context={
                "target_slack_user_id": target_user.slack_user_id,
                "target_display_name": target_user.slack_display_name,
            },
        )

        return await self.repository.create(entry_data)

    async def log_user_suspend(
        self,
        actor: User,
        target_user: User,
        reason: str,
        actor_ip: Optional[str] = None,
    ) -> AuditLogEntry:
        """Log a user suspension event (NFR-ABUSE-002).

        Args:
            actor: Admin who performed the suspension
            target_user: User who was suspended
            reason: Reason for suspension
            actor_ip: IP address of actor

        Returns:
            Created AuditLogEntry
        """
        actor_role = self._get_highest_role(actor)

        entry_data = AuditLogCreate(
            actor_id=actor.id,
            actor_role=actor_role,
            actor_ip=actor_ip,
            action_type=AuditActionType.USER_SUSPEND,
            target_entity_type=AuditTargetType.USER,
            target_entity_id=target_user.id,
            changes=AuditChanges(
                before={"is_suspended": False},
                after={"is_suspended": True},
            ),
            justification=reason,
            system_context={
                "target_slack_user_id": target_user.slack_user_id,
                "target_display_name": target_user.slack_display_name,
                "target_roles": [
                    r.value if isinstance(r, UserRole) else r for r in target_user.roles
                ],
            },
        )

        return await self.repository.create(entry_data)

    async def log_user_reinstate(
        self,
        actor: User,
        target_user: User,
        reason: Optional[str] = None,
        actor_ip: Optional[str] = None,
    ) -> AuditLogEntry:
        """Log a user reinstatement event.

        Args:
            actor: Admin who performed the reinstatement
            target_user: User who was reinstated
            reason: Reason for reinstatement
            actor_ip: IP address of actor

        Returns:
            Created AuditLogEntry
        """
        actor_role = self._get_highest_role(actor)

        entry_data = AuditLogCreate(
            actor_id=actor.id,
            actor_role=actor_role,
            actor_ip=actor_ip,
            action_type=AuditActionType.USER_REINSTATE,
            target_entity_type=AuditTargetType.USER,
            target_entity_id=target_user.id,
            changes=AuditChanges(
                before={"is_suspended": True},
                after={"is_suspended": False},
            ),
            justification=reason,
            system_context={
                "target_slack_user_id": target_user.slack_user_id,
                "target_display_name": target_user.slack_display_name,
            },
        )

        return await self.repository.create(entry_data)

    async def log_access_denied(
        self,
        actor: User,
        resource_type: AuditTargetType,
        resource_id: ObjectId,
        required_permission: Optional[str] = None,
        required_role: Optional[str] = None,
        actor_ip: Optional[str] = None,
    ) -> AuditLogEntry:
        """Log an access denied event (FR-ROLE-002).

        Args:
            actor: User who was denied access
            resource_type: Type of resource accessed
            resource_id: ID of resource accessed
            required_permission: Permission that was required
            required_role: Role that was required
            actor_ip: IP address of actor

        Returns:
            Created AuditLogEntry
        """
        actor_role = self._get_highest_role(actor)

        entry_data = AuditLogCreate(
            actor_id=actor.id,
            actor_role=actor_role,
            actor_ip=actor_ip,
            action_type=AuditActionType.ACCESS_DENIED,
            target_entity_type=resource_type,
            target_entity_id=resource_id,
            changes=AuditChanges(),
            system_context={
                "required_permission": required_permission,
                "required_role": required_role,
                "actor_roles": [
                    r.value if isinstance(r, UserRole) else r for r in actor.roles
                ],
            },
        )

        return await self.repository.create(entry_data)

    def _get_highest_role(self, user: User) -> str:
        """Get the highest role for a user.

        Args:
            user: User to check

        Returns:
            String name of highest role
        """
        role_priority = [
            UserRole.WORKSPACE_ADMIN,
            UserRole.FACILITATOR,
            UserRole.VERIFIER,
            UserRole.GENERAL_PARTICIPANT,
        ]

        for role in role_priority:
            if user.has_role(role):
                return role.value

        return UserRole.GENERAL_PARTICIPANT.value


# Global service instance
_audit_service: Optional[AuditService] = None


def get_audit_service() -> AuditService:
    """Get the global audit service instance.

    Returns:
        AuditService singleton
    """
    global _audit_service
    if _audit_service is None:
        _audit_service = AuditService()
    return _audit_service


async def get_audit_repository() -> AuditRepository:
    """Get audit repository instance (for FastAPI dependency injection).

    Returns:
        AuditRepository instance
    """
    return AuditRepository(get_collection("audit_log"))
