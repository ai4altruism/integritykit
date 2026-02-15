"""Duplicate detection service for identifying signals reporting the same information."""

import json
from typing import Optional

import structlog
from bson import ObjectId

from integritykit.llm.prompts.duplicate_detection import (
    DUPLICATE_DETECTION_SYSTEM_PROMPT,
    DUPLICATE_DETECTION_USER_PROMPT_TEMPLATE,
    DuplicateDetectionOutput,
)
from integritykit.models.duplicate import DuplicateConfirmation, DuplicateMatch
from integritykit.models.signal import Signal
from integritykit.services.database import SignalRepository
from integritykit.services.embedding import EmbeddingService
from integritykit.services.llm import LLMService
from integritykit.utils.ai_metadata import AIOperationType, create_ai_metadata

logger = structlog.get_logger(__name__)


class DuplicateDetectionService:
    """Service for detecting duplicate signals within clusters."""

    def __init__(
        self,
        embedding_service: EmbeddingService,
        llm_service: LLMService,
        signal_repository: SignalRepository,
        similarity_threshold: float = 0.85,
    ):
        """Initialize duplicate detection service.

        Args:
            embedding_service: Service for embedding similarity search
            llm_service: Service for LLM-powered duplicate confirmation
            signal_repository: Repository for signal database operations
            similarity_threshold: Minimum similarity score to consider as duplicate candidate
        """
        self.embedding_service = embedding_service
        self.llm_service = llm_service
        self.signal_repo = signal_repository
        self.similarity_threshold = similarity_threshold

    async def detect_duplicates_for_signal(
        self,
        signal: Signal,
        cluster_id: ObjectId,
    ) -> list[DuplicateMatch]:
        """Detect duplicates for a signal within its cluster.

        This is the main entry point when a new signal joins a cluster.

        Args:
            signal: Signal to check for duplicates
            cluster_id: Cluster ID to search within

        Returns:
            List of confirmed duplicate matches

        Raises:
            ValueError: If signal has no ID
        """
        if not signal.id:
            raise ValueError("Signal must have an ID for duplicate detection")

        logger.info(
            "Detecting duplicates for signal",
            signal_id=str(signal.id),
            cluster_id=str(cluster_id),
        )

        # Step 1: Find candidate duplicates using embedding similarity
        candidates = await self.find_duplicate_candidates(
            signal=signal,
            cluster_id=cluster_id,
            threshold=self.similarity_threshold,
        )

        if not candidates:
            logger.info(
                "No duplicate candidates found",
                signal_id=str(signal.id),
                cluster_id=str(cluster_id),
            )
            return []

        logger.info(
            "Found duplicate candidates",
            signal_id=str(signal.id),
            candidate_count=len(candidates),
        )

        # Step 2: Confirm candidates using LLM
        confirmed_duplicates: list[DuplicateMatch] = []

        for candidate_signal, similarity_score in candidates:
            try:
                confirmation = await self.confirm_duplicate_with_llm(
                    signal1=signal,
                    signal2=candidate_signal,
                )

                if confirmation.is_duplicate:
                    duplicate_match = DuplicateMatch(
                        signal_id=candidate_signal.id,
                        similarity_score=similarity_score,
                        confidence=confirmation.confidence,
                        reasoning=confirmation.reasoning,
                        shared_facts=confirmation.shared_facts,
                    )
                    confirmed_duplicates.append(duplicate_match)

                    logger.info(
                        "AI-confirmed duplicate",
                        signal_id=str(signal.id),
                        duplicate_id=str(candidate_signal.id),
                        confidence=confirmation.confidence,
                        similarity_score=similarity_score,
                        ai_generated=True,
                        model=self.llm_service.model,
                    )

            except Exception as e:
                logger.error(
                    "Failed to confirm duplicate with LLM",
                    signal_id=str(signal.id),
                    candidate_id=str(candidate_signal.id),
                    error=str(e),
                )
                continue

        logger.info(
            "Duplicate detection complete",
            signal_id=str(signal.id),
            confirmed_count=len(confirmed_duplicates),
        )

        return confirmed_duplicates

    async def find_duplicate_candidates(
        self,
        signal: Signal,
        cluster_id: ObjectId,
        threshold: float = 0.85,
    ) -> list[tuple[Signal, float]]:
        """Find duplicate candidates using embedding similarity.

        Args:
            signal: Signal to compare
            cluster_id: Cluster ID to search within
            threshold: Similarity threshold (0-1)

        Returns:
            List of (Signal, similarity_score) tuples exceeding threshold
        """
        if not signal.id:
            logger.warning(
                "Cannot find duplicates for signal without ID",
            )
            return []

        try:
            # Get all signals in the cluster
            cluster_signals = await self.signal_repo.list_by_cluster(cluster_id)

            # Extract signal IDs
            cluster_signal_ids = [
                str(s.id) for s in cluster_signals if s.id and s.id != signal.id
            ]

            if not cluster_signal_ids:
                logger.debug(
                    "No other signals in cluster to compare",
                    signal_id=str(signal.id),
                    cluster_id=str(cluster_id),
                )
                return []

            # Find similar signals in cluster using ChromaDB
            similar_pairs = await self.embedding_service.find_similar_in_cluster(
                signal_id=str(signal.id),
                cluster_signal_ids=cluster_signal_ids,
                threshold=threshold,
            )

            # Convert to Signal objects with scores
            candidates: list[tuple[Signal, float]] = []
            for similar_signal_id, similarity_score in similar_pairs:
                try:
                    similar_signal = await self.signal_repo.get_by_id(
                        ObjectId(similar_signal_id)
                    )
                    if similar_signal:
                        candidates.append((similar_signal, similarity_score))
                except Exception as e:
                    logger.warning(
                        "Failed to fetch candidate signal",
                        signal_id=similar_signal_id,
                        error=str(e),
                    )
                    continue

            logger.info(
                "Found duplicate candidates via embedding similarity",
                signal_id=str(signal.id),
                candidate_count=len(candidates),
                threshold=threshold,
            )

            return candidates

        except Exception as e:
            logger.error(
                "Failed to find duplicate candidates",
                signal_id=str(signal.id),
                cluster_id=str(cluster_id),
                error=str(e),
            )
            raise

    async def confirm_duplicate_with_llm(
        self,
        signal1: Signal,
        signal2: Signal,
    ) -> DuplicateConfirmation:
        """Use LLM to confirm if two signals are duplicates.

        Args:
            signal1: First signal
            signal2: Second signal

        Returns:
            DuplicateConfirmation with LLM assessment
        """
        # Format prompt
        user_prompt = DUPLICATE_DETECTION_USER_PROMPT_TEMPLATE.format(
            signal1_author=signal1.slack_user_id,
            signal1_timestamp=signal1.created_at.isoformat(),
            signal1_content=signal1.content,
            signal2_author=signal2.slack_user_id,
            signal2_timestamp=signal2.created_at.isoformat(),
            signal2_content=signal2.content,
        )

        try:
            response = await self.llm_service.client.chat.completions.create(
                model=self.llm_service.model,
                temperature=self.llm_service.temperature,
                messages=[
                    {"role": "system", "content": DUPLICATE_DETECTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )

            # Parse response
            content = response.choices[0].message.content
            result: DuplicateDetectionOutput = json.loads(content)

            confirmation = DuplicateConfirmation(**result)

            logger.info(
                "AI-generated duplicate confirmation",
                signal1_id=str(signal1.id),
                signal2_id=str(signal2.id),
                is_duplicate=confirmation.is_duplicate,
                confidence=confirmation.confidence,
                model=self.llm_service.model,
                ai_generated=True,
            )

            return confirmation

        except Exception as e:
            logger.error(
                "Failed to confirm duplicate with LLM",
                signal1_id=str(signal1.id),
                signal2_id=str(signal2.id),
                error=str(e),
            )
            raise

    async def mark_duplicates(
        self,
        signal_ids: list[ObjectId],
        canonical_id: ObjectId,
    ) -> None:
        """Mark signals as duplicates of a canonical signal.

        Updates the AIFlags on each signal to indicate duplicate status.

        Args:
            signal_ids: List of signal IDs to mark as duplicates
            canonical_id: ID of the canonical (primary) signal
        """
        logger.info(
            "AI-marking signals as duplicates",
            canonical_id=str(canonical_id),
            duplicate_count=len(signal_ids),
            ai_generated=True,
        )

        # Create AI metadata for duplicate marking
        ai_metadata = create_ai_metadata(
            model=self.llm_service.model,
            operation=AIOperationType.DUPLICATE_DETECTION,
            canonical_id=str(canonical_id),
            marked_count=len(signal_ids),
        )

        for signal_id in signal_ids:
            try:
                await self.signal_repo.update(
                    signal_id,
                    {
                        "ai_flags.is_duplicate": True,
                        "ai_flags.duplicate_of": canonical_id,
                        "ai_generated_metadata": ai_metadata,
                    },
                )

                logger.debug(
                    "AI-marked signal as duplicate",
                    signal_id=str(signal_id),
                    canonical_id=str(canonical_id),
                    ai_generated=True,
                )

            except Exception as e:
                logger.error(
                    "Failed to mark signal as duplicate",
                    signal_id=str(signal_id),
                    canonical_id=str(canonical_id),
                    error=str(e),
                )
                continue

        logger.info(
            "Completed marking duplicates",
            canonical_id=str(canonical_id),
        )

    async def get_duplicate_group(
        self,
        signal_id: ObjectId,
    ) -> list[Signal]:
        """Get all signals in a duplicate group.

        If the signal is marked as a duplicate, returns the canonical signal
        and all other duplicates. If the signal is canonical, returns all
        its duplicates.

        Args:
            signal_id: Signal ID to get duplicate group for

        Returns:
            List of signals in the duplicate group (including the signal itself)
        """
        signal = await self.signal_repo.get_by_id(signal_id)
        if not signal:
            logger.warning(
                "Signal not found for duplicate group lookup",
                signal_id=str(signal_id),
            )
            return []

        # Determine canonical ID
        if signal.ai_flags.is_duplicate and signal.ai_flags.duplicate_of:
            canonical_id = signal.ai_flags.duplicate_of
        else:
            canonical_id = signal_id

        # Get all signals marked as duplicates of the canonical
        # Note: This requires a database query, which we'll need to add to the repository
        # For now, we'll return a simplified result
        duplicate_group = [signal]

        logger.info(
            "Retrieved duplicate group",
            signal_id=str(signal_id),
            canonical_id=str(canonical_id),
            group_size=len(duplicate_group),
        )

        return duplicate_group

    async def auto_mark_duplicates_for_signal(
        self,
        signal: Signal,
        duplicate_matches: list[DuplicateMatch],
        confidence_threshold: str = "medium",
    ) -> None:
        """Automatically mark duplicates based on detection results.

        Only marks duplicates that meet the confidence threshold.

        Args:
            signal: The signal being checked
            duplicate_matches: List of detected duplicates
            confidence_threshold: Minimum confidence level ("low", "medium", "high")
        """
        if not signal.id:
            logger.warning("Cannot mark duplicates for signal without ID")
            return

        confidence_order = {"low": 0, "medium": 1, "high": 2}
        min_confidence = confidence_order[confidence_threshold]

        # Filter by confidence
        high_confidence_duplicates = [
            match
            for match in duplicate_matches
            if confidence_order[match.confidence] >= min_confidence
        ]

        if not high_confidence_duplicates:
            logger.info(
                "No high-confidence duplicates to auto-mark",
                signal_id=str(signal.id),
                threshold=confidence_threshold,
            )
            return

        # Use the first duplicate as canonical (typically the oldest)
        canonical_id = high_confidence_duplicates[0].signal_id

        # Mark the new signal as duplicate
        duplicate_ids = [signal.id]

        await self.mark_duplicates(
            signal_ids=duplicate_ids,
            canonical_id=canonical_id,
        )

        logger.info(
            "Auto-marked duplicates",
            signal_id=str(signal.id),
            canonical_id=str(canonical_id),
            confidence_threshold=confidence_threshold,
        )
