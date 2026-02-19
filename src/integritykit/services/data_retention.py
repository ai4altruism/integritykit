"""Data retention and purge service.

Implements:
- S7-5: Data-retention TTL and purge mechanism
- NFR-PRIVACY-001: Data retention policies
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

import structlog
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from integritykit.models.audit import AuditActionType, AuditTargetType
from integritykit.models.user import User
from integritykit.services.audit import AuditService, get_audit_service

logger = structlog.get_logger(__name__)


def _get_settings():
    """Lazy import of settings to avoid validation errors in tests."""
    from integritykit.config import settings
    return settings


class RetentionEntityType(str, Enum):
    """Entity types that support data retention."""

    SIGNAL = "signal"
    CLUSTER = "cluster"
    AUDIT_LOG = "audit_log"


class PurgeResult:
    """Result of a purge operation."""

    def __init__(
        self,
        entity_type: RetentionEntityType,
        deleted_count: int,
        errors: list[str] | None = None,
        cutoff_date: datetime | None = None,
    ):
        self.entity_type = entity_type
        self.deleted_count = deleted_count
        self.errors = errors or []
        self.cutoff_date = cutoff_date

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entity_type": self.entity_type.value,
            "deleted_count": self.deleted_count,
            "errors": self.errors,
            "cutoff_date": self.cutoff_date.isoformat() if self.cutoff_date else None,
        }


class DataRetentionService:
    """Service for managing data retention and purging expired records.

    Implements S7-5: Data-retention TTL and purge mechanism.
    """

    def __init__(
        self,
        db: Optional[AsyncIOMotorDatabase] = None,
        audit_service: Optional[AuditService] = None,
    ):
        """Initialize DataRetentionService.

        Args:
            db: MongoDB database instance
            audit_service: Audit service for logging
        """
        self._db = db
        self.audit_service = audit_service or get_audit_service()

    def _get_db(self) -> AsyncIOMotorDatabase:
        """Get database instance."""
        if self._db is None:
            from integritykit.services.database import get_database
            self._db = get_database()
        return self._db

    def get_default_retention_days(self) -> int:
        """Get default retention period in days."""
        return _get_settings().default_retention_days

    def calculate_expiration_date(
        self,
        retention_days: int | None = None,
        from_date: datetime | None = None,
    ) -> datetime:
        """Calculate expiration date based on retention period.

        Args:
            retention_days: Days to retain (defaults to config setting)
            from_date: Base date (defaults to now)

        Returns:
            Expiration datetime
        """
        days = retention_days or self.get_default_retention_days()
        base_date = from_date or datetime.utcnow()
        return base_date + timedelta(days=days)

    async def set_signal_expiration(
        self,
        signal_id: ObjectId,
        retention_days: int | None = None,
    ) -> datetime:
        """Set expiration date for a signal.

        Args:
            signal_id: Signal to update
            retention_days: Custom retention period (optional)

        Returns:
            Expiration date that was set
        """
        db = self._get_db()
        expires_at = self.calculate_expiration_date(retention_days)

        await db.signals.update_one(
            {"_id": signal_id},
            {"$set": {"expires_at": expires_at, "updated_at": datetime.utcnow()}},
        )

        logger.debug(
            "Set signal expiration",
            signal_id=str(signal_id),
            expires_at=expires_at.isoformat(),
        )

        return expires_at

    async def extend_retention(
        self,
        entity_type: RetentionEntityType,
        entity_id: ObjectId,
        additional_days: int,
        reason: str,
        actor: User,
    ) -> datetime:
        """Extend retention period for an entity.

        Used when data needs to be kept longer for ongoing investigations.

        Args:
            entity_type: Type of entity
            entity_id: Entity ID
            additional_days: Days to add to current expiration
            reason: Justification for extension
            actor: User requesting extension

        Returns:
            New expiration date
        """
        db = self._get_db()
        collection_name = f"{entity_type.value}s"

        # Get current expiration
        entity = await db[collection_name].find_one({"_id": entity_id})
        if not entity:
            raise ValueError(f"{entity_type.value} not found: {entity_id}")

        current_expires = entity.get("expires_at") or datetime.utcnow()
        new_expires = current_expires + timedelta(days=additional_days)

        await db[collection_name].update_one(
            {"_id": entity_id},
            {"$set": {"expires_at": new_expires, "updated_at": datetime.utcnow()}},
        )

        # Audit log the extension
        await self.audit_service.log_action(
            actor=actor,
            action_type=AuditActionType.ACCESS_DENIED,  # Reusing for retention changes
            target_type=AuditTargetType(entity_type.value),
            target_id=entity_id,
            changes_before={"expires_at": current_expires.isoformat()},
            changes_after={"expires_at": new_expires.isoformat()},
            justification=reason,
            system_context={
                "action": "retention_extended",
                "additional_days": additional_days,
            },
        )

        logger.info(
            "Extended retention period",
            entity_type=entity_type.value,
            entity_id=str(entity_id),
            new_expires=new_expires.isoformat(),
            extended_by=str(actor.id),
        )

        return new_expires

    async def purge_expired_signals(
        self,
        dry_run: bool = False,
        batch_size: int = 1000,
    ) -> PurgeResult:
        """Purge signals that have passed their expiration date.

        Args:
            dry_run: If True, only count without deleting
            batch_size: Maximum records to delete per batch

        Returns:
            PurgeResult with deletion statistics
        """
        db = self._get_db()
        cutoff = datetime.utcnow()
        errors = []

        # Find expired signals
        query = {
            "expires_at": {"$ne": None, "$lte": cutoff}
        }

        if dry_run:
            count = await db.signals.count_documents(query)
            return PurgeResult(
                entity_type=RetentionEntityType.SIGNAL,
                deleted_count=count,
                cutoff_date=cutoff,
            )

        # Delete in batches
        total_deleted = 0
        while True:
            # Find batch of expired signals
            expired_ids = await db.signals.find(
                query,
                {"_id": 1},
            ).limit(batch_size).to_list(length=batch_size)

            if not expired_ids:
                break

            ids = [doc["_id"] for doc in expired_ids]

            try:
                # Also delete from vector store
                await self._purge_signal_embeddings(ids)

                # Delete from MongoDB
                result = await db.signals.delete_many({"_id": {"$in": ids}})
                total_deleted += result.deleted_count

                logger.info(
                    "Purged expired signals batch",
                    deleted_count=result.deleted_count,
                    total_deleted=total_deleted,
                )

            except Exception as e:
                error_msg = f"Error purging signal batch: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
                break

        return PurgeResult(
            entity_type=RetentionEntityType.SIGNAL,
            deleted_count=total_deleted,
            errors=errors,
            cutoff_date=cutoff,
        )

    async def _purge_signal_embeddings(self, signal_ids: list[ObjectId]) -> int:
        """Remove embeddings for purged signals from vector store.

        Args:
            signal_ids: IDs of signals to remove embeddings for

        Returns:
            Count of embeddings removed
        """
        # ChromaDB deletion - graceful handling if not available
        try:
            from integritykit.services.embedding import get_embedding_service
            embedding_service = get_embedding_service()

            # Delete by document IDs
            id_strings = [str(sid) for sid in signal_ids]
            await embedding_service.delete_embeddings(id_strings)

            return len(id_strings)
        except Exception as e:
            logger.warning(
                "Could not purge embeddings from vector store",
                error=str(e),
            )
            return 0

    async def purge_expired_clusters(
        self,
        dry_run: bool = False,
        batch_size: int = 100,
    ) -> PurgeResult:
        """Purge clusters that have no remaining signals.

        Clusters are purged when all their member signals have expired.

        Args:
            dry_run: If True, only count without deleting
            batch_size: Maximum records to delete per batch

        Returns:
            PurgeResult with deletion statistics
        """
        db = self._get_db()
        cutoff = datetime.utcnow()
        errors = []

        # Find clusters with no remaining signals
        # A cluster is orphaned if none of its signal_ids exist anymore
        pipeline = [
            # Lookup signals for each cluster
            {
                "$lookup": {
                    "from": "signals",
                    "localField": "signal_ids",
                    "foreignField": "_id",
                    "as": "remaining_signals",
                }
            },
            # Keep only clusters with no remaining signals
            {
                "$match": {
                    "remaining_signals": {"$size": 0}
                }
            },
            # Just get the IDs
            {
                "$project": {"_id": 1}
            },
            # Limit for batching
            {"$limit": batch_size},
        ]

        orphaned_clusters = await db.clusters.aggregate(pipeline).to_list(length=batch_size)

        if dry_run:
            return PurgeResult(
                entity_type=RetentionEntityType.CLUSTER,
                deleted_count=len(orphaned_clusters),
                cutoff_date=cutoff,
            )

        if not orphaned_clusters:
            return PurgeResult(
                entity_type=RetentionEntityType.CLUSTER,
                deleted_count=0,
                cutoff_date=cutoff,
            )

        try:
            ids = [doc["_id"] for doc in orphaned_clusters]
            result = await db.clusters.delete_many({"_id": {"$in": ids}})

            logger.info(
                "Purged orphaned clusters",
                deleted_count=result.deleted_count,
            )

            return PurgeResult(
                entity_type=RetentionEntityType.CLUSTER,
                deleted_count=result.deleted_count,
                cutoff_date=cutoff,
            )

        except Exception as e:
            error_msg = f"Error purging clusters: {str(e)}"
            errors.append(error_msg)
            logger.error(error_msg)
            return PurgeResult(
                entity_type=RetentionEntityType.CLUSTER,
                deleted_count=0,
                errors=errors,
                cutoff_date=cutoff,
            )

    async def purge_old_audit_logs(
        self,
        retention_days: int | None = None,
        dry_run: bool = False,
        batch_size: int = 1000,
    ) -> PurgeResult:
        """Purge audit logs older than retention period.

        Note: Audit logs use a longer retention period than signals.
        Default is 2x the signal retention period.

        Args:
            retention_days: Custom retention (default: 2x signal retention)
            dry_run: If True, only count without deleting
            batch_size: Maximum records to delete per batch

        Returns:
            PurgeResult with deletion statistics
        """
        db = self._get_db()

        # Audit logs have longer retention (2x by default)
        days = retention_days or (self.get_default_retention_days() * 2)
        cutoff = datetime.utcnow() - timedelta(days=days)
        errors = []

        query = {"created_at": {"$lte": cutoff}}

        if dry_run:
            count = await db.audit_logs.count_documents(query)
            return PurgeResult(
                entity_type=RetentionEntityType.AUDIT_LOG,
                deleted_count=count,
                cutoff_date=cutoff,
            )

        total_deleted = 0
        while True:
            try:
                result = await db.audit_logs.delete_many(query)
                if result.deleted_count == 0:
                    break

                total_deleted += result.deleted_count

                if result.deleted_count < batch_size:
                    break

                logger.info(
                    "Purged old audit logs batch",
                    deleted_count=result.deleted_count,
                    total_deleted=total_deleted,
                )

            except Exception as e:
                error_msg = f"Error purging audit logs: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
                break

        return PurgeResult(
            entity_type=RetentionEntityType.AUDIT_LOG,
            deleted_count=total_deleted,
            errors=errors,
            cutoff_date=cutoff,
        )

    async def run_full_purge(
        self,
        dry_run: bool = False,
    ) -> dict[str, PurgeResult]:
        """Run purge on all entity types.

        Args:
            dry_run: If True, only count without deleting

        Returns:
            Dict mapping entity type to purge result
        """
        results = {}

        # Purge in order: signals first, then orphaned clusters, then audit logs
        results["signals"] = await self.purge_expired_signals(dry_run=dry_run)
        results["clusters"] = await self.purge_expired_clusters(dry_run=dry_run)
        results["audit_logs"] = await self.purge_old_audit_logs(dry_run=dry_run)

        total_deleted = sum(r.deleted_count for r in results.values())
        total_errors = sum(len(r.errors) for r in results.values())

        logger.info(
            "Full purge completed",
            dry_run=dry_run,
            total_deleted=total_deleted,
            total_errors=total_errors,
            signals_deleted=results["signals"].deleted_count,
            clusters_deleted=results["clusters"].deleted_count,
            audit_logs_deleted=results["audit_logs"].deleted_count,
        )

        return results

    async def get_retention_stats(self) -> dict[str, Any]:
        """Get statistics about data retention.

        Returns:
            Dict with retention statistics
        """
        db = self._get_db()
        now = datetime.utcnow()

        # Count signals by expiration status
        total_signals = await db.signals.count_documents({})
        expired_signals = await db.signals.count_documents({
            "expires_at": {"$ne": None, "$lte": now}
        })
        expiring_soon = await db.signals.count_documents({
            "expires_at": {
                "$ne": None,
                "$gt": now,
                "$lte": now + timedelta(days=7),
            }
        })
        no_expiration = await db.signals.count_documents({
            "expires_at": None
        })

        # Oldest signal
        oldest = await db.signals.find_one(
            {},
            sort=[("created_at", 1)],
        )

        return {
            "default_retention_days": self.get_default_retention_days(),
            "signals": {
                "total": total_signals,
                "expired": expired_signals,
                "expiring_within_7_days": expiring_soon,
                "no_expiration_set": no_expiration,
            },
            "oldest_signal_date": oldest["created_at"].isoformat() if oldest else None,
        }


# Singleton instance
_data_retention_service: Optional[DataRetentionService] = None


def get_data_retention_service() -> DataRetentionService:
    """Get the data retention service singleton.

    Returns:
        DataRetentionService instance
    """
    global _data_retention_service
    if _data_retention_service is None:
        _data_retention_service = DataRetentionService()
    return _data_retention_service
