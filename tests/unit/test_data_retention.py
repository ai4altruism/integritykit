"""Unit tests for data retention service.

Tests:
- S7-5: Data-retention TTL and purge mechanism
- NFR-PRIVACY-001: Data retention policies
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

from integritykit.models.user import User, UserRole
from integritykit.services.data_retention import (
    DataRetentionService,
    PurgeResult,
    RetentionEntityType,
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
        roles=roles or [UserRole.WORKSPACE_ADMIN],
        created_at=datetime.now(timezone.utc),
    )


def make_mock_settings(retention_days: int = 90):
    """Create mock settings."""
    mock = MagicMock()
    mock.default_retention_days = retention_days
    return mock


def make_mock_db():
    """Create mock database."""
    db = MagicMock()
    db.signals = MagicMock()
    db.clusters = MagicMock()
    db.audit_logs = MagicMock()
    # Make item access work like attribute access
    db.__getitem__ = lambda self, key: getattr(db, key)
    return db


def make_mock_audit_service():
    """Create mock audit service."""
    service = MagicMock()
    service.log_action = AsyncMock()
    return service


# ============================================================================
# PurgeResult Tests
# ============================================================================


@pytest.mark.unit
class TestPurgeResult:
    """Test PurgeResult data class."""

    def test_purge_result_creation(self) -> None:
        """PurgeResult stores all data correctly."""
        cutoff = datetime.utcnow()
        result = PurgeResult(
            entity_type=RetentionEntityType.SIGNAL,
            deleted_count=42,
            errors=["error 1"],
            cutoff_date=cutoff,
        )

        assert result.entity_type == RetentionEntityType.SIGNAL
        assert result.deleted_count == 42
        assert len(result.errors) == 1
        assert result.cutoff_date == cutoff

    def test_purge_result_to_dict(self) -> None:
        """PurgeResult can be serialized."""
        cutoff = datetime.utcnow()
        result = PurgeResult(
            entity_type=RetentionEntityType.SIGNAL,
            deleted_count=10,
            cutoff_date=cutoff,
        )

        result_dict = result.to_dict()

        assert result_dict["entity_type"] == "signal"
        assert result_dict["deleted_count"] == 10
        assert result_dict["errors"] == []


# ============================================================================
# DataRetentionService Tests
# ============================================================================


@pytest.mark.unit
class TestExpirationCalculation:
    """Test expiration date calculation."""

    def test_calculate_expiration_default(self) -> None:
        """Default expiration uses config setting."""
        with patch(
            "integritykit.services.data_retention._get_settings",
            return_value=make_mock_settings(retention_days=90),
        ):
            service = DataRetentionService(
                db=make_mock_db(),
                audit_service=make_mock_audit_service(),
            )
            now = datetime.utcnow()

            expires = service.calculate_expiration_date()

            # Should be approximately 90 days from now
            expected = now + timedelta(days=90)
            assert abs((expires - expected).total_seconds()) < 1

    def test_calculate_expiration_custom_days(self) -> None:
        """Custom retention days override default."""
        with patch(
            "integritykit.services.data_retention._get_settings",
            return_value=make_mock_settings(retention_days=90),
        ):
            service = DataRetentionService(
                db=make_mock_db(),
                audit_service=make_mock_audit_service(),
            )
            now = datetime.utcnow()

            expires = service.calculate_expiration_date(retention_days=30)

            expected = now + timedelta(days=30)
            assert abs((expires - expected).total_seconds()) < 1

    def test_calculate_expiration_from_specific_date(self) -> None:
        """Expiration calculated from specific base date."""
        with patch(
            "integritykit.services.data_retention._get_settings",
            return_value=make_mock_settings(retention_days=90),
        ):
            service = DataRetentionService(
                db=make_mock_db(),
                audit_service=make_mock_audit_service(),
            )
            base_date = datetime(2024, 1, 1, 12, 0, 0)

            expires = service.calculate_expiration_date(
                retention_days=30,
                from_date=base_date,
            )

            expected = datetime(2024, 1, 31, 12, 0, 0)
            assert expires == expected


@pytest.mark.unit
class TestSignalExpiration:
    """Test signal expiration setting."""

    @pytest.mark.asyncio
    async def test_set_signal_expiration(self) -> None:
        """Can set expiration date on a signal."""
        mock_db = make_mock_db()
        mock_db.signals.update_one = AsyncMock()

        with patch(
            "integritykit.services.data_retention._get_settings",
            return_value=make_mock_settings(retention_days=90),
        ):
            service = DataRetentionService(
                db=mock_db,
                audit_service=make_mock_audit_service(),
            )
            signal_id = ObjectId()

            expires = await service.set_signal_expiration(signal_id)

            # Verify update was called
            mock_db.signals.update_one.assert_called_once()
            call_args = mock_db.signals.update_one.call_args
            assert call_args[0][0] == {"_id": signal_id}
            assert "expires_at" in call_args[0][1]["$set"]

    @pytest.mark.asyncio
    async def test_set_signal_expiration_custom_days(self) -> None:
        """Can set custom retention period on a signal."""
        mock_db = make_mock_db()
        mock_db.signals.update_one = AsyncMock()

        with patch(
            "integritykit.services.data_retention._get_settings",
            return_value=make_mock_settings(retention_days=90),
        ):
            service = DataRetentionService(
                db=mock_db,
                audit_service=make_mock_audit_service(),
            )
            signal_id = ObjectId()
            now = datetime.utcnow()

            expires = await service.set_signal_expiration(
                signal_id,
                retention_days=7,
            )

            # Should be 7 days, not 90
            expected = now + timedelta(days=7)
            assert abs((expires - expected).total_seconds()) < 1


@pytest.mark.unit
class TestSignalPurge:
    """Test signal purge functionality."""

    @pytest.mark.asyncio
    async def test_purge_expired_signals_dry_run(self) -> None:
        """Dry run counts but doesn't delete."""
        mock_db = make_mock_db()
        mock_db.signals.count_documents = AsyncMock(return_value=42)
        mock_db.signals.delete_many = AsyncMock()

        with patch(
            "integritykit.services.data_retention._get_settings",
            return_value=make_mock_settings(),
        ):
            service = DataRetentionService(
                db=mock_db,
                audit_service=make_mock_audit_service(),
            )

            result = await service.purge_expired_signals(dry_run=True)

            assert result.deleted_count == 42
            mock_db.signals.delete_many.assert_not_called()

    @pytest.mark.asyncio
    async def test_purge_expired_signals(self) -> None:
        """Actually purges expired signals."""
        mock_db = make_mock_db()

        # Mock finding expired signals
        expired_signal = {"_id": ObjectId()}
        mock_cursor = MagicMock()
        mock_cursor.limit = MagicMock(return_value=mock_cursor)
        mock_cursor.to_list = AsyncMock(side_effect=[[expired_signal], []])
        mock_db.signals.find = MagicMock(return_value=mock_cursor)

        # Mock deletion
        delete_result = MagicMock()
        delete_result.deleted_count = 1
        mock_db.signals.delete_many = AsyncMock(return_value=delete_result)

        with patch(
            "integritykit.services.data_retention._get_settings",
            return_value=make_mock_settings(),
        ):
            with patch.object(
                DataRetentionService,
                "_purge_signal_embeddings",
                new_callable=AsyncMock,
                return_value=1,
            ):
                service = DataRetentionService(
                    db=mock_db,
                    audit_service=make_mock_audit_service(),
                )

                result = await service.purge_expired_signals(dry_run=False)

                assert result.deleted_count == 1
                mock_db.signals.delete_many.assert_called()

    @pytest.mark.asyncio
    async def test_purge_no_expired_signals(self) -> None:
        """No deletion when no expired signals exist."""
        mock_db = make_mock_db()

        # Mock finding no expired signals
        mock_cursor = MagicMock()
        mock_cursor.limit = MagicMock(return_value=mock_cursor)
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_db.signals.find = MagicMock(return_value=mock_cursor)

        with patch(
            "integritykit.services.data_retention._get_settings",
            return_value=make_mock_settings(),
        ):
            service = DataRetentionService(
                db=mock_db,
                audit_service=make_mock_audit_service(),
            )

            result = await service.purge_expired_signals(dry_run=False)

            assert result.deleted_count == 0


@pytest.mark.unit
class TestClusterPurge:
    """Test orphaned cluster purge functionality."""

    @pytest.mark.asyncio
    async def test_purge_orphaned_clusters(self) -> None:
        """Purges clusters with no remaining signals."""
        mock_db = make_mock_db()

        # Mock aggregation finding orphaned cluster
        orphaned_cluster = {"_id": ObjectId()}
        mock_db.clusters.aggregate = MagicMock()
        mock_db.clusters.aggregate.return_value.to_list = AsyncMock(
            return_value=[orphaned_cluster]
        )

        # Mock deletion
        delete_result = MagicMock()
        delete_result.deleted_count = 1
        mock_db.clusters.delete_many = AsyncMock(return_value=delete_result)

        with patch(
            "integritykit.services.data_retention._get_settings",
            return_value=make_mock_settings(),
        ):
            service = DataRetentionService(
                db=mock_db,
                audit_service=make_mock_audit_service(),
            )

            result = await service.purge_expired_clusters(dry_run=False)

            assert result.deleted_count == 1

    @pytest.mark.asyncio
    async def test_purge_clusters_dry_run(self) -> None:
        """Cluster dry run counts without deleting."""
        mock_db = make_mock_db()

        orphaned_clusters = [{"_id": ObjectId()}, {"_id": ObjectId()}]
        mock_db.clusters.aggregate = MagicMock()
        mock_db.clusters.aggregate.return_value.to_list = AsyncMock(
            return_value=orphaned_clusters
        )
        mock_db.clusters.delete_many = AsyncMock()

        with patch(
            "integritykit.services.data_retention._get_settings",
            return_value=make_mock_settings(),
        ):
            service = DataRetentionService(
                db=mock_db,
                audit_service=make_mock_audit_service(),
            )

            result = await service.purge_expired_clusters(dry_run=True)

            assert result.deleted_count == 2
            mock_db.clusters.delete_many.assert_not_called()


@pytest.mark.unit
class TestAuditLogPurge:
    """Test audit log purge functionality."""

    @pytest.mark.asyncio
    async def test_audit_logs_have_longer_retention(self) -> None:
        """Audit logs default to 2x signal retention."""
        mock_db = make_mock_db()
        mock_db.audit_logs.count_documents = AsyncMock(return_value=0)

        with patch(
            "integritykit.services.data_retention._get_settings",
            return_value=make_mock_settings(retention_days=90),
        ):
            service = DataRetentionService(
                db=mock_db,
                audit_service=make_mock_audit_service(),
            )

            result = await service.purge_old_audit_logs(dry_run=True)

            # Cutoff should be 180 days ago (2x 90)
            expected_cutoff = datetime.utcnow() - timedelta(days=180)
            assert result.cutoff_date is not None
            diff = abs((result.cutoff_date - expected_cutoff).total_seconds())
            assert diff < 5  # Within 5 seconds

    @pytest.mark.asyncio
    async def test_audit_logs_custom_retention(self) -> None:
        """Can specify custom retention for audit logs."""
        mock_db = make_mock_db()
        mock_db.audit_logs.count_documents = AsyncMock(return_value=10)

        with patch(
            "integritykit.services.data_retention._get_settings",
            return_value=make_mock_settings(),
        ):
            service = DataRetentionService(
                db=mock_db,
                audit_service=make_mock_audit_service(),
            )

            result = await service.purge_old_audit_logs(
                retention_days=365,
                dry_run=True,
            )

            # Cutoff should be 365 days ago
            expected_cutoff = datetime.utcnow() - timedelta(days=365)
            diff = abs((result.cutoff_date - expected_cutoff).total_seconds())
            assert diff < 5


@pytest.mark.unit
class TestFullPurge:
    """Test full purge operation."""

    @pytest.mark.asyncio
    async def test_full_purge_runs_all_types(self) -> None:
        """Full purge runs signals, clusters, and audit logs."""
        mock_db = make_mock_db()

        # Mock all operations
        mock_db.signals.count_documents = AsyncMock(return_value=5)
        mock_db.clusters.aggregate = MagicMock()
        mock_db.clusters.aggregate.return_value.to_list = AsyncMock(return_value=[])
        mock_db.audit_logs.count_documents = AsyncMock(return_value=3)

        with patch(
            "integritykit.services.data_retention._get_settings",
            return_value=make_mock_settings(),
        ):
            service = DataRetentionService(
                db=mock_db,
                audit_service=make_mock_audit_service(),
            )

            results = await service.run_full_purge(dry_run=True)

            assert "signals" in results
            assert "clusters" in results
            assert "audit_logs" in results
            assert results["signals"].deleted_count == 5
            assert results["audit_logs"].deleted_count == 3


@pytest.mark.unit
class TestRetentionExtension:
    """Test retention period extension."""

    @pytest.mark.asyncio
    async def test_extend_retention(self) -> None:
        """Can extend retention period for an entity."""
        mock_db = make_mock_db()
        mock_audit = make_mock_audit_service()

        signal_id = ObjectId()
        current_expires = datetime.utcnow() + timedelta(days=30)

        mock_db.signals.find_one = AsyncMock(
            return_value={"_id": signal_id, "expires_at": current_expires}
        )
        mock_db.signals.update_one = AsyncMock()

        with patch(
            "integritykit.services.data_retention._get_settings",
            return_value=make_mock_settings(),
        ):
            service = DataRetentionService(
                db=mock_db,
                audit_service=mock_audit,
            )
            user = make_user()

            new_expires = await service.extend_retention(
                entity_type=RetentionEntityType.SIGNAL,
                entity_id=signal_id,
                additional_days=60,
                reason="Investigation ongoing",
                actor=user,
            )

            # Should be 60 days beyond current expiration
            expected = current_expires + timedelta(days=60)
            assert abs((new_expires - expected).total_seconds()) < 1

            # Audit should be logged
            mock_audit.log_action.assert_called_once()

    @pytest.mark.asyncio
    async def test_extend_retention_not_found(self) -> None:
        """Extension fails if entity not found."""
        mock_db = make_mock_db()
        mock_db.signals.find_one = AsyncMock(return_value=None)

        with patch(
            "integritykit.services.data_retention._get_settings",
            return_value=make_mock_settings(),
        ):
            service = DataRetentionService(
                db=mock_db,
                audit_service=make_mock_audit_service(),
            )
            user = make_user()

            with pytest.raises(ValueError, match="not found"):
                await service.extend_retention(
                    entity_type=RetentionEntityType.SIGNAL,
                    entity_id=ObjectId(),
                    additional_days=30,
                    reason="Test",
                    actor=user,
                )


@pytest.mark.unit
class TestRetentionStats:
    """Test retention statistics gathering."""

    @pytest.mark.asyncio
    async def test_get_retention_stats(self) -> None:
        """Can get retention statistics."""
        mock_db = make_mock_db()

        oldest_signal = {
            "_id": ObjectId(),
            "created_at": datetime(2024, 1, 1, 12, 0, 0),
        }

        mock_db.signals.count_documents = AsyncMock(side_effect=[100, 5, 10, 20])
        mock_db.signals.find_one = AsyncMock(return_value=oldest_signal)

        with patch(
            "integritykit.services.data_retention._get_settings",
            return_value=make_mock_settings(retention_days=90),
        ):
            service = DataRetentionService(
                db=mock_db,
                audit_service=make_mock_audit_service(),
            )

            stats = await service.get_retention_stats()

            assert stats["default_retention_days"] == 90
            assert stats["signals"]["total"] == 100
            assert stats["signals"]["expired"] == 5
            assert stats["signals"]["expiring_within_7_days"] == 10
            assert stats["signals"]["no_expiration_set"] == 20
            assert "2024-01-01" in stats["oldest_signal_date"]
