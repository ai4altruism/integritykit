"""Clustering service for grouping related signals by topic/incident."""

from datetime import datetime
from typing import Optional

import structlog
from bson import ObjectId

from integritykit.models.cluster import Cluster, ClusterCreate, PriorityScores
from integritykit.models.signal import Signal
from integritykit.services.database import ClusterRepository, SignalRepository
from integritykit.services.embedding import EmbeddingService
from integritykit.services.llm import LLMService
from integritykit.utils.ai_metadata import (
    AIOperationType,
    create_ai_metadata,
    merge_ai_metadata,
)

logger = structlog.get_logger(__name__)

# Import DuplicateDetectionService and ConflictDetectionService only when needed to avoid circular dependency
try:
    from integritykit.services.duplicate_detection import DuplicateDetectionService
except ImportError:
    DuplicateDetectionService = None  # type: ignore

try:
    from integritykit.services.conflict_detection import ConflictDetectionService
except ImportError:
    ConflictDetectionService = None  # type: ignore


class ClusteringService:
    """Service for clustering signals by topic/incident."""

    def __init__(
        self,
        signal_repository: SignalRepository,
        cluster_repository: ClusterRepository,
        embedding_service: EmbeddingService,
        llm_service: LLMService,
        duplicate_detection_service: Optional["DuplicateDetectionService"] = None,
        conflict_detection_service: Optional["ConflictDetectionService"] = None,
        similarity_threshold: float = 0.75,
        max_clusters_to_compare: int = 10,
        enable_duplicate_detection: bool = True,
        enable_conflict_detection: bool = True,
    ):
        """Initialize clustering service.

        Args:
            signal_repository: Repository for signal operations
            cluster_repository: Repository for cluster operations
            embedding_service: Service for embedding generation and similarity search
            llm_service: Service for LLM-powered classification
            duplicate_detection_service: Optional service for duplicate detection
            conflict_detection_service: Optional service for conflict detection
            similarity_threshold: Minimum similarity score for cluster consideration
            max_clusters_to_compare: Maximum number of clusters to compare via LLM
            enable_duplicate_detection: Whether to run duplicate detection on cluster assignment
            enable_conflict_detection: Whether to run conflict detection on cluster assignment
        """
        self.signal_repo = signal_repository
        self.cluster_repo = cluster_repository
        self.embedding_service = embedding_service
        self.llm_service = llm_service
        self.duplicate_detection_service = duplicate_detection_service
        self.conflict_detection_service = conflict_detection_service
        self.similarity_threshold = similarity_threshold
        self.max_clusters_to_compare = max_clusters_to_compare
        self.enable_duplicate_detection = enable_duplicate_detection
        self.enable_conflict_detection = enable_conflict_detection

    async def process_new_signal(self, signal: Signal) -> Cluster:
        """Process a new signal and assign to cluster.

        This is the main entry point for clustering. It:
        1. Generates embedding for the signal
        2. Finds similar signals using vector search
        3. Uses LLM to classify cluster assignment
        4. Either assigns to existing cluster or creates new one
        5. Updates cluster summary/topic if needed

        Args:
            signal: Signal to process

        Returns:
            Cluster that signal was assigned to

        Raises:
            ValueError: If signal has no ID
        """
        if not signal.id:
            raise ValueError("Signal must be saved to database before clustering")

        logger.info(
            "Processing signal for clustering",
            signal_id=str(signal.id),
            workspace_id=signal.slack_workspace_id,
        )

        # Step 1: Generate and store embedding
        try:
            await self.embedding_service.add_signal(signal)
            logger.debug(
                "Generated embedding for signal",
                signal_id=str(signal.id),
            )
        except Exception as e:
            logger.error(
                "Failed to generate embedding, proceeding with cluster assignment",
                signal_id=str(signal.id),
                error=str(e),
            )

        # Step 2: Find similar signals via vector search
        similar_signals = await self.embedding_service.find_similar(
            text=signal.content,
            n=20,  # Get more than we need for filtering
            workspace_id=signal.slack_workspace_id,
        )

        logger.info(
            "Found similar signals",
            signal_id=str(signal.id),
            similar_count=len(similar_signals),
        )

        # Step 3: Get candidate clusters from similar signals
        candidate_clusters = await self._get_candidate_clusters(
            similar_signals,
            signal.slack_workspace_id,
        )

        logger.info(
            "Identified candidate clusters",
            signal_id=str(signal.id),
            candidate_count=len(candidate_clusters),
        )

        # Step 4: Use LLM to classify assignment
        if candidate_clusters:
            # Limit clusters sent to LLM to avoid context bloat
            clusters_to_compare = candidate_clusters[: self.max_clusters_to_compare]

            classification = await self.llm_service.classify_cluster_assignment(
                signal=signal,
                existing_clusters=clusters_to_compare,
            )

            logger.info(
                "LLM classification result",
                signal_id=str(signal.id),
                assignment=classification["assignment"],
                confidence=classification["confidence"],
            )

            # If LLM says assign to existing cluster
            if classification["assignment"] == "existing_cluster" and classification["cluster_id"]:
                cluster_id = ObjectId(classification["cluster_id"])
                cluster = await self.add_signal_to_cluster(
                    signal_id=signal.id,
                    cluster_id=cluster_id,
                )

                if cluster:
                    logger.info(
                        "Assigned signal to existing cluster",
                        signal_id=str(signal.id),
                        cluster_id=str(cluster_id),
                    )
                    return cluster

        # Step 5: Create new cluster if no match or LLM says new cluster
        logger.info(
            "Creating new cluster for signal",
            signal_id=str(signal.id),
        )

        cluster = await self.create_cluster(signal)
        return cluster

    async def _get_candidate_clusters(
        self,
        similar_signals: list[tuple[str, float]],
        workspace_id: str,
    ) -> list[Cluster]:
        """Get candidate clusters from similar signals.

        Args:
            similar_signals: List of (signal_id, similarity_score) tuples
            workspace_id: Workspace ID to filter clusters

        Returns:
            List of candidate Cluster instances, ordered by relevance
        """
        # Filter by similarity threshold
        relevant_signals = [
            (sid, score)
            for sid, score in similar_signals
            if score >= self.similarity_threshold
        ]

        if not relevant_signals:
            return []

        # Get clusters these signals belong to
        cluster_scores: dict[str, float] = {}

        for signal_id_str, similarity_score in relevant_signals:
            try:
                signal_id = ObjectId(signal_id_str)
                signal = await self.signal_repo.get_by_id(signal_id)

                if not signal or not signal.cluster_ids:
                    continue

                # Track clusters and aggregate similarity scores
                for cluster_id in signal.cluster_ids:
                    cluster_id_str = str(cluster_id)
                    if cluster_id_str not in cluster_scores:
                        cluster_scores[cluster_id_str] = 0.0
                    cluster_scores[cluster_id_str] = max(
                        cluster_scores[cluster_id_str], similarity_score
                    )

            except Exception as e:
                logger.warning(
                    "Failed to process similar signal",
                    signal_id=signal_id_str,
                    error=str(e),
                )
                continue

        # Sort clusters by relevance score
        sorted_cluster_ids = sorted(
            cluster_scores.keys(),
            key=lambda cid: cluster_scores[cid],
            reverse=True,
        )

        # Fetch cluster objects
        clusters = []
        for cluster_id_str in sorted_cluster_ids:
            try:
                cluster = await self.cluster_repo.get_by_id(ObjectId(cluster_id_str))
                if cluster and cluster.slack_workspace_id == workspace_id:
                    clusters.append(cluster)
            except Exception as e:
                logger.warning(
                    "Failed to fetch cluster",
                    cluster_id=cluster_id_str,
                    error=str(e),
                )
                continue

        return clusters

    async def create_cluster(self, signal: Signal) -> Cluster:
        """Create a new cluster from a seed signal.

        Args:
            signal: Seed signal for the cluster

        Returns:
            Created Cluster instance
        """
        # Generate topic from signal
        topic = await self.llm_service.generate_topic_from_signal(signal)

        # Generate initial summary
        summary = await self.llm_service.generate_cluster_summary(
            signals=[signal],
            topic=topic,
        )

        # Create cluster
        cluster_data = ClusterCreate(
            slack_workspace_id=signal.slack_workspace_id,
            signal_ids=[signal.id],
            topic=topic,
            summary=summary,
        )

        cluster = await self.cluster_repo.create(cluster_data)

        # Create AI metadata for cluster creation
        topic_metadata = create_ai_metadata(
            model=self.llm_service.model,
            operation=AIOperationType.TOPIC_GENERATION,
            seed_signal_id=str(signal.id),
        )

        summary_metadata = create_ai_metadata(
            model=self.llm_service.model,
            operation=AIOperationType.SUMMARY_GENERATION,
            signal_count=1,
        )

        # Merge AI metadata from topic and summary generation
        ai_metadata = merge_ai_metadata(topic_metadata, summary_metadata)

        # Update cluster metadata
        await self.cluster_repo.update(
            cluster.id,
            {"ai_generated_metadata": ai_metadata},
        )

        # Add signal to cluster
        await self.signal_repo.add_to_cluster(
            signal_id=signal.id,
            cluster_id=cluster.id,
        )

        # Assess initial priority
        priority_scores = await self.calculate_priority_scores(cluster)
        await self.cluster_repo.update_priority_scores(
            cluster.id,
            priority_scores.model_dump(),
        )

        # Update AI metadata to include priority assessment
        cluster_refreshed = await self.cluster_repo.get_by_id(cluster.id)
        if cluster_refreshed:
            priority_metadata = create_ai_metadata(
                model=self.llm_service.model,
                operation=AIOperationType.PRIORITY_ASSESSMENT,
                urgency=priority_scores.urgency,
                impact=priority_scores.impact,
                risk=priority_scores.risk,
                composite_score=priority_scores.composite_score,
            )
            updated_metadata = merge_ai_metadata(
                cluster_refreshed.ai_generated_metadata,
                priority_metadata,
            )
            await self.cluster_repo.update(
                cluster.id,
                {"ai_generated_metadata": updated_metadata},
            )

        logger.info(
            "AI-created new cluster",
            cluster_id=str(cluster.id),
            topic=topic,
            signal_id=str(signal.id),
            ai_generated=True,
        )

        # Refresh cluster from DB
        cluster = await self.cluster_repo.get_by_id(cluster.id)
        return cluster

    async def add_signal_to_cluster(
        self,
        signal_id: ObjectId,
        cluster_id: ObjectId,
    ) -> Optional[Cluster]:
        """Add a signal to an existing cluster and update summary.

        Args:
            signal_id: Signal ID to add
            cluster_id: Cluster ID to add signal to

        Returns:
            Updated Cluster instance or None if not found
        """
        # Add signal to cluster
        cluster = await self.cluster_repo.add_signal(
            cluster_id=cluster_id,
            signal_id=signal_id,
        )

        if not cluster:
            logger.warning(
                "Cluster not found when adding signal",
                cluster_id=str(cluster_id),
                signal_id=str(signal_id),
            )
            return None

        # Add cluster to signal
        await self.signal_repo.add_to_cluster(
            signal_id=signal_id,
            cluster_id=cluster_id,
        )

        # Check for duplicates within cluster
        if self.enable_duplicate_detection and self.duplicate_detection_service:
            try:
                signal = await self.signal_repo.get_by_id(signal_id)
                if signal:
                    duplicate_matches = await self.duplicate_detection_service.detect_duplicates_for_signal(
                        signal=signal,
                        cluster_id=cluster_id,
                    )

                    # Auto-mark high-confidence duplicates
                    if duplicate_matches:
                        await self.duplicate_detection_service.auto_mark_duplicates_for_signal(
                            signal=signal,
                            duplicate_matches=duplicate_matches,
                            confidence_threshold="high",
                        )

                        logger.info(
                            "AI-detected duplicates for signal",
                            signal_id=str(signal_id),
                            duplicate_count=len(duplicate_matches),
                            ai_generated=True,
                        )
            except Exception as e:
                logger.error(
                    "Failed to detect duplicates for signal",
                    signal_id=str(signal_id),
                    cluster_id=str(cluster_id),
                    error=str(e),
                )

        # Update cluster summary with new signal
        signals = await self.signal_repo.list_by_cluster(cluster_id)
        summary = await self.llm_service.generate_cluster_summary(
            signals=signals,
            topic=cluster.topic,
        )

        # Create AI metadata for summary update
        summary_metadata = create_ai_metadata(
            model=self.llm_service.model,
            operation=AIOperationType.SUMMARY_GENERATION,
            signal_count=len(signals),
            updated_signal_id=str(signal_id),
        )

        # Merge with existing metadata
        updated_metadata = merge_ai_metadata(
            cluster.ai_generated_metadata,
            summary_metadata,
        )

        await self.cluster_repo.update(
            cluster_id,
            {
                "summary": summary,
                "updated_at": datetime.utcnow(),
                "ai_generated_metadata": updated_metadata,
            },
        )

        # Re-assess priority with new signal
        priority_scores = await self.calculate_priority_scores(cluster)
        await self.cluster_repo.update_priority_scores(
            cluster_id,
            priority_scores.model_dump(),
        )

        # Detect conflicts with new signal if enabled
        if self.enable_conflict_detection and self.conflict_detection_service:
            try:
                signal = await self.signal_repo.get_by_id(signal_id)
                if signal:
                    # Refresh cluster to get latest state
                    cluster = await self.cluster_repo.get_by_id(cluster_id)

                    new_conflicts = await self.conflict_detection_service.detect_conflicts_for_new_signal(
                        signal=signal,
                        cluster=cluster,
                    )

                    if new_conflicts:
                        # Get existing conflicts
                        all_conflicts = cluster.conflicts + new_conflicts

                        # Update cluster with new conflicts
                        await self.cluster_repo.update(
                            cluster_id,
                            {
                                "conflicts": [c.model_dump() for c in all_conflicts],
                                "updated_at": datetime.utcnow(),
                            },
                        )

                        # Create AI metadata for conflict detection
                        conflict_metadata = create_ai_metadata(
                            model=self.llm_service.model,
                            operation=AIOperationType.CONFLICT_DETECTION,
                            conflicts_detected=len(new_conflicts),
                        )

                        # Merge with existing metadata
                        updated_metadata = merge_ai_metadata(
                            cluster.ai_generated_metadata,
                            conflict_metadata,
                        )

                        await self.cluster_repo.update(
                            cluster_id,
                            {"ai_generated_metadata": updated_metadata},
                        )

                        logger.info(
                            "AI-detected conflicts for new signal",
                            signal_id=str(signal_id),
                            cluster_id=str(cluster_id),
                            new_conflicts=len(new_conflicts),
                            ai_generated=True,
                        )
            except Exception as e:
                logger.error(
                    "Failed to detect conflicts for new signal",
                    signal_id=str(signal_id),
                    cluster_id=str(cluster_id),
                    error=str(e),
                )

        logger.info(
            "AI-updated cluster with new signal",
            signal_id=str(signal_id),
            cluster_id=str(cluster_id),
            signal_count=len(signals),
            ai_generated=True,
        )

        # Refresh cluster from DB
        cluster = await self.cluster_repo.get_by_id(cluster_id)
        return cluster

    async def get_cluster(self, cluster_id: ObjectId) -> Optional[Cluster]:
        """Get cluster by ID.

        Args:
            cluster_id: Cluster ID

        Returns:
            Cluster instance or None if not found
        """
        return await self.cluster_repo.get_by_id(cluster_id)

    async def list_clusters_for_backlog(
        self,
        workspace_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Cluster]:
        """List unpromoted clusters for backlog, prioritized by scores.

        Args:
            workspace_id: Slack workspace ID
            limit: Maximum number of clusters to return
            offset: Number of clusters to skip

        Returns:
            List of Cluster instances ordered by priority
        """
        return await self.cluster_repo.list_unpromoted_clusters(
            workspace_id=workspace_id,
            limit=limit,
            offset=offset,
        )

    async def calculate_priority_scores(self, cluster: Cluster) -> PriorityScores:
        """Calculate priority scores for a cluster using LLM.

        Args:
            cluster: Cluster to assess

        Returns:
            PriorityScores instance
        """
        # Get signals in cluster for context
        signals = await self.signal_repo.list_by_cluster(cluster.id)

        priority_scores = await self.llm_service.assess_priority(
            cluster=cluster,
            signals=signals,
        )

        logger.info(
            "AI-calculated priority scores",
            cluster_id=str(cluster.id),
            composite_score=priority_scores.composite_score,
            ai_generated=True,
        )

        return priority_scores
