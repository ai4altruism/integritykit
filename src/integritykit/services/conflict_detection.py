"""Conflict detection service for identifying contradictory claims within clusters."""

import json
import uuid
from datetime import datetime
from itertools import combinations
from typing import Optional

import structlog
from bson import ObjectId

from integritykit.llm.prompts.conflict_detection import (
    CONFLICT_DETECTION_OUTPUT_SCHEMA,
    CONFLICT_DETECTION_SYSTEM_PROMPT,
    format_conflict_detection_prompt,
    SignalSummary,
    ConflictOutput,
)
from integritykit.models.cluster import (
    Cluster,
    ConflictRecord,
    ConflictResolution,
    ConflictResolutionType,
    ConflictSeverity,
)
from integritykit.models.signal import Signal
from integritykit.services.database import ClusterRepository, SignalRepository
from integritykit.services.llm import LLMService
from integritykit.utils.ai_metadata import AIOperationType, create_ai_metadata

logger = structlog.get_logger(__name__)


class ConflictDetectionService:
    """Service for detecting conflicts between signals in clusters."""

    def __init__(
        self,
        llm_service: LLMService,
        signal_repository: SignalRepository,
        cluster_repository: ClusterRepository,
    ):
        """Initialize conflict detection service.

        Args:
            llm_service: LLM service for conflict analysis
            signal_repository: Repository for signal operations
            cluster_repository: Repository for cluster operations
        """
        self.llm_service = llm_service
        self.signal_repo = signal_repository
        self.cluster_repo = cluster_repository

    async def detect_conflicts_in_cluster(
        self,
        cluster_id: ObjectId,
    ) -> list[ConflictRecord]:
        """Analyze all signals in a cluster for contradictions.

        This method performs pairwise comparison of signals in the cluster
        to detect conflicts. It's more comprehensive but may be slower for
        large clusters.

        Args:
            cluster_id: Cluster ID to analyze

        Returns:
            List of detected conflicts
        """
        # Get cluster
        cluster = await self.cluster_repo.get_by_id(cluster_id)
        if not cluster:
            logger.warning(
                "Cluster not found for conflict detection",
                cluster_id=str(cluster_id),
            )
            return []

        # Get all signals in cluster
        signals = await self.signal_repo.list_by_cluster(cluster_id)

        if len(signals) < 2:
            logger.debug(
                "Cluster has fewer than 2 signals, skipping conflict detection",
                cluster_id=str(cluster_id),
                signal_count=len(signals),
            )
            return []

        logger.info(
            "AI-detecting conflicts in cluster",
            cluster_id=str(cluster_id),
            signal_count=len(signals),
            ai_generated=True,
        )

        conflicts = []

        # For small clusters, do pairwise comparison
        if len(signals) <= 5:
            # Compare signals pairwise
            for signal1, signal2 in combinations(signals, 2):
                conflict = await self.analyze_signal_pair(
                    signal1=signal1,
                    signal2=signal2,
                    cluster_topic=cluster.topic,
                )
                if conflict:
                    conflicts.append(conflict)
        else:
            # For larger clusters, batch analyze all signals together
            # This is more efficient and allows the LLM to see all signals at once
            batch_conflicts = await self._batch_analyze_signals(
                signals=signals,
                cluster_topic=cluster.topic,
            )
            conflicts.extend(batch_conflicts)

        logger.info(
            "AI conflict detection complete",
            cluster_id=str(cluster_id),
            conflicts_found=len(conflicts),
            ai_generated=True,
        )

        # Add AI metadata to each conflict if conflicts were found
        if conflicts:
            ai_metadata = create_ai_metadata(
                model=self.llm_service.model,
                operation=AIOperationType.CONFLICT_DETECTION,
                cluster_id=str(cluster_id),
                signal_count=len(signals),
            )
            # Note: ConflictRecord needs an ai_metadata field to store this
            # For now, we log that conflicts are AI-generated

        return conflicts

    async def detect_conflicts_for_new_signal(
        self,
        signal: Signal,
        cluster: Cluster,
    ) -> list[ConflictRecord]:
        """Check if new signal conflicts with existing cluster signals.

        This is more efficient than re-checking the entire cluster.

        Args:
            signal: New signal being added to cluster
            cluster: Cluster to check against

        Returns:
            List of detected conflicts involving the new signal
        """
        # Get existing signals in cluster
        existing_signals = await self.signal_repo.list_by_cluster(cluster.id)

        if not existing_signals:
            logger.debug(
                "No existing signals in cluster, skipping conflict detection",
                cluster_id=str(cluster.id),
            )
            return []

        logger.info(
            "AI-detecting conflicts for new signal",
            signal_id=str(signal.id),
            cluster_id=str(cluster.id),
            existing_signal_count=len(existing_signals),
            ai_generated=True,
        )

        conflicts = []

        # Compare new signal with each existing signal
        for existing_signal in existing_signals:
            conflict = await self.analyze_signal_pair(
                signal1=signal,
                signal2=existing_signal,
                cluster_topic=cluster.topic,
            )
            if conflict:
                conflicts.append(conflict)

        logger.info(
            "AI conflict detection for new signal complete",
            signal_id=str(signal.id),
            cluster_id=str(cluster.id),
            conflicts_found=len(conflicts),
            ai_generated=True,
        )

        return conflicts

    async def analyze_signal_pair(
        self,
        signal1: Signal,
        signal2: Signal,
        cluster_topic: str,
    ) -> Optional[ConflictRecord]:
        """Use LLM to check if two signals conflict.

        Args:
            signal1: First signal
            signal2: Second signal
            cluster_topic: Topic of the cluster containing these signals

        Returns:
            ConflictRecord if conflict found, None otherwise
        """
        # Prepare signal summaries
        signals = [
            SignalSummary(
                signal_id=str(signal1.id),
                author=signal1.slack_user_id,
                timestamp=signal1.created_at.isoformat(),
                content=signal1.content,
                source_type="slack",
            ),
            SignalSummary(
                signal_id=str(signal2.id),
                author=signal2.slack_user_id,
                timestamp=signal2.created_at.isoformat(),
                content=signal2.content,
                source_type="slack",
            ),
        ]

        # Format prompt
        user_prompt = format_conflict_detection_prompt(
            cluster_topic=cluster_topic,
            signals=signals,
        )

        try:
            # Call LLM
            response = await self.llm_service.client.chat.completions.create(
                model=self.llm_service.model,
                temperature=0.2,  # Lower temperature for consistency
                messages=[
                    {"role": "system", "content": CONFLICT_DETECTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )

            # Parse response
            content = response.choices[0].message.content
            result: ConflictOutput = json.loads(content)

            # If no conflict detected, return None
            if not result.get("conflict_detected"):
                logger.debug(
                    "No conflict detected between signals",
                    signal1_id=str(signal1.id),
                    signal2_id=str(signal2.id),
                )
                return None

            # Map severity from LLM output to our enum
            severity_mapping = {
                "high": ConflictSeverity.HIGH,
                "medium": ConflictSeverity.MEDIUM,
                "low": ConflictSeverity.LOW,
                "none": ConflictSeverity.LOW,
            }
            severity = severity_mapping.get(
                result.get("severity", "low"),
                ConflictSeverity.LOW,
            )

            # Extract conflicting values
            values = {}
            for field_info in result.get("conflicting_fields", []):
                values[str(signal1.id)] = field_info.get("signal_1_value", "")
                values[str(signal2.id)] = field_info.get("signal_2_value", "")

            # Create conflict record
            conflict = ConflictRecord(
                id=str(uuid.uuid4()),
                signal_ids=[signal1.id, signal2.id],
                field=result.get("conflicting_fields", [{}])[0].get("field", "other") if result.get("conflicting_fields") else "other",
                severity=severity,
                description=result.get("explanation", ""),
                values=values,
                detected_at=datetime.utcnow(),
                resolved=False,
            )

            logger.info(
                "AI-detected conflict between signals",
                signal1_id=str(signal1.id),
                signal2_id=str(signal2.id),
                conflict_id=conflict.id,
                severity=conflict.severity,
                field=conflict.field,
                model=self.llm_service.model,
                ai_generated=True,
            )

            # Store AI metadata on the signal's ai_flags for conflicts
            ai_metadata = create_ai_metadata(
                model=self.llm_service.model,
                operation=AIOperationType.CONFLICT_DETECTION,
                confidence=None,  # Conflict detection doesn't provide confidence
                severity=conflict.severity,
                field=conflict.field,
            )

            # Update both signals to mark conflict detected
            for sig in [signal1, signal2]:
                try:
                    await self.signal_repo.update(
                        sig.id,
                        {
                            "ai_flags.has_conflict": True,
                            "ai_flags.conflict_ids": [conflict.id],
                        },
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to update signal conflict flags",
                        signal_id=str(sig.id),
                        error=str(e),
                    )

            return conflict

        except Exception as e:
            logger.error(
                "Failed to analyze signal pair for conflicts",
                signal1_id=str(signal1.id),
                signal2_id=str(signal2.id),
                error=str(e),
            )
            return None

    async def _batch_analyze_signals(
        self,
        signals: list[Signal],
        cluster_topic: str,
    ) -> list[ConflictRecord]:
        """Analyze multiple signals at once for conflicts.

        More efficient for larger clusters than pairwise comparison.

        Args:
            signals: List of signals to analyze
            cluster_topic: Topic of the cluster

        Returns:
            List of detected conflicts
        """
        # Prepare signal summaries
        signal_summaries = [
            SignalSummary(
                signal_id=str(signal.id),
                author=signal.slack_user_id,
                timestamp=signal.created_at.isoformat(),
                content=signal.content,
                source_type="slack",
            )
            for signal in signals
        ]

        # Format prompt
        user_prompt = format_conflict_detection_prompt(
            cluster_topic=cluster_topic,
            signals=signal_summaries,
        )

        try:
            # Call LLM
            response = await self.llm_service.client.chat.completions.create(
                model=self.llm_service.model,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": CONFLICT_DETECTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )

            # Parse response
            content = response.choices[0].message.content
            result: ConflictOutput = json.loads(content)

            # If no conflict detected, return empty list
            if not result.get("conflict_detected"):
                logger.debug(
                    "No conflicts detected in batch analysis",
                    signal_count=len(signals),
                )
                return []

            # Map severity
            severity_mapping = {
                "high": ConflictSeverity.HIGH,
                "medium": ConflictSeverity.MEDIUM,
                "low": ConflictSeverity.LOW,
                "none": ConflictSeverity.LOW,
            }
            severity = severity_mapping.get(
                result.get("severity", "low"),
                ConflictSeverity.LOW,
            )

            # Extract conflicting signal IDs
            conflicting_signal_ids = result.get("conflicting_signal_ids", [])
            signal_ids = [ObjectId(sid) for sid in conflicting_signal_ids if ObjectId.is_valid(sid)]

            # Extract conflicting values
            values = {}
            for field_info in result.get("conflicting_fields", []):
                values[field_info.get("signal_1_value", "")] = field_info.get("signal_1_value", "")
                values[field_info.get("signal_2_value", "")] = field_info.get("signal_2_value", "")

            # Create single conflict record for the batch
            conflict = ConflictRecord(
                id=str(uuid.uuid4()),
                signal_ids=signal_ids if signal_ids else [s.id for s in signals[:2]],
                field=result.get("conflicting_fields", [{}])[0].get("field", "other") if result.get("conflicting_fields") else "other",
                severity=severity,
                description=result.get("explanation", ""),
                values=values,
                detected_at=datetime.utcnow(),
                resolved=False,
            )

            logger.info(
                "AI batch conflict detection complete",
                signal_count=len(signals),
                conflict_id=conflict.id,
                severity=conflict.severity,
                model=self.llm_service.model,
                ai_generated=True,
            )

            # Update signals to mark conflicts detected
            for signal in signals:
                if signal.id in signal_ids:
                    try:
                        await self.signal_repo.update(
                            signal.id,
                            {
                                "ai_flags.has_conflict": True,
                                "ai_flags.conflict_ids": [conflict.id],
                            },
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to update signal conflict flags",
                            signal_id=str(signal.id),
                            error=str(e),
                        )

            return [conflict]

        except Exception as e:
            logger.error(
                "Failed to batch analyze signals for conflicts",
                signal_count=len(signals),
                error=str(e),
            )
            return []

    async def resolve_conflict(
        self,
        cluster_id: ObjectId,
        conflict_id: str,
        resolution: ConflictResolution,
        resolved_by: str,
    ) -> bool:
        """Mark conflict as resolved.

        Args:
            cluster_id: Cluster containing the conflict
            conflict_id: Conflict ID to resolve
            resolution: Resolution details
            resolved_by: User who resolved the conflict

        Returns:
            True if successfully resolved
        """
        # Get cluster
        cluster = await self.cluster_repo.get_by_id(cluster_id)
        if not cluster:
            logger.warning(
                "Cluster not found for conflict resolution",
                cluster_id=str(cluster_id),
            )
            return False

        # Find conflict in cluster
        conflict_index = None
        for i, conflict in enumerate(cluster.conflicts):
            if conflict.id == conflict_id:
                conflict_index = i
                break

        if conflict_index is None:
            logger.warning(
                "Conflict not found in cluster",
                cluster_id=str(cluster_id),
                conflict_id=conflict_id,
            )
            return False

        # Update conflict
        cluster.conflicts[conflict_index].resolved = True
        cluster.conflicts[conflict_index].resolution = resolution
        cluster.conflicts[conflict_index].resolved_by = resolved_by
        cluster.conflicts[conflict_index].resolved_at = datetime.utcnow()

        # Save to database
        await self.cluster_repo.update(
            cluster_id,
            {
                "conflicts": [c.model_dump() for c in cluster.conflicts],
                "updated_at": datetime.utcnow(),
            },
        )

        logger.info(
            "Conflict resolved",
            cluster_id=str(cluster_id),
            conflict_id=conflict_id,
            resolution_type=resolution.type,
            resolved_by=resolved_by,
        )

        return True

    async def get_unresolved_conflicts(
        self,
        cluster_id: ObjectId,
    ) -> list[ConflictRecord]:
        """Get unresolved conflicts for a cluster.

        Args:
            cluster_id: Cluster ID

        Returns:
            List of unresolved conflicts
        """
        cluster = await self.cluster_repo.get_by_id(cluster_id)
        if not cluster:
            return []

        unresolved = [c for c in cluster.conflicts if not c.resolved]

        logger.debug(
            "Retrieved unresolved conflicts",
            cluster_id=str(cluster_id),
            unresolved_count=len(unresolved),
            total_conflicts=len(cluster.conflicts),
        )

        return unresolved
