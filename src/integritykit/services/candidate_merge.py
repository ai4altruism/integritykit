"""Candidate merge service for duplicate COP candidate handling.

Implements FR-BACKLOG-003: Duplicate merge workflow for COP candidates.
"""

from datetime import datetime
from typing import Optional

import structlog
from bson import ObjectId

from integritykit.models.cop_candidate import COPCandidate, ReadinessState
from integritykit.models.user import User
from integritykit.services.database import COPCandidateRepository
from integritykit.services.embedding import EmbeddingService

logger = structlog.get_logger(__name__)


class DuplicateSuggestion:
    """A suggested duplicate candidate."""

    def __init__(
        self,
        candidate_id: ObjectId,
        headline: str,
        similarity_score: float,
        readiness_state: str,
    ):
        self.candidate_id = candidate_id
        self.headline = headline
        self.similarity_score = similarity_score
        self.readiness_state = readiness_state


class MergeResult:
    """Result of a merge operation."""

    def __init__(
        self,
        primary_candidate: COPCandidate,
        merged_candidate_ids: list[ObjectId],
        signals_added: int,
    ):
        self.primary_candidate = primary_candidate
        self.merged_candidate_ids = merged_candidate_ids
        self.signals_added = signals_added


class CandidateMergeService:
    """Service for detecting and merging duplicate COP candidates.

    This service:
    1. Finds potential duplicate candidates using embedding similarity
    2. Allows facilitators to merge duplicates into a canonical candidate
    3. Preserves evidence from all merged candidates
    """

    def __init__(
        self,
        candidate_repository: COPCandidateRepository,
        embedding_service: Optional[EmbeddingService] = None,
        similarity_threshold: float = 0.80,
    ):
        """Initialize candidate merge service.

        Args:
            candidate_repository: Repository for COP candidate operations
            embedding_service: Optional embedding service for similarity search
            similarity_threshold: Minimum similarity score for suggestions
        """
        self.candidate_repo = candidate_repository
        self.embedding_service = embedding_service
        self.similarity_threshold = similarity_threshold

    async def suggest_duplicates(
        self,
        candidate: COPCandidate,
        limit: int = 5,
    ) -> list[DuplicateSuggestion]:
        """Suggest potential duplicate candidates for a given candidate.

        Uses embedding similarity on candidate headlines/summaries to find
        potential duplicates.

        Args:
            candidate: The candidate to find duplicates for
            limit: Maximum number of suggestions to return

        Returns:
            List of duplicate suggestions sorted by similarity
        """
        if not candidate.id:
            raise ValueError("Candidate must have an ID")

        logger.info(
            "Finding duplicate suggestions for candidate",
            candidate_id=str(candidate.id),
        )

        suggestions: list[DuplicateSuggestion] = []

        # Get all active candidates (not archived or merged)
        all_candidates = await self.candidate_repo.find_all(
            query={
                "_id": {"$ne": candidate.id},
                "readiness_state": {
                    "$nin": [ReadinessState.ARCHIVED.value, "merged"]
                },
            }
        )

        if not all_candidates:
            return []

        # If we have embedding service, use semantic similarity
        if self.embedding_service and candidate.fields:
            candidate_text = self._get_candidate_text(candidate)

            for other in all_candidates:
                other_text = self._get_candidate_text(other)
                if not other_text:
                    continue

                # Calculate similarity
                similarity = await self._calculate_similarity(
                    candidate_text, other_text
                )

                if similarity >= self.similarity_threshold:
                    suggestions.append(
                        DuplicateSuggestion(
                            candidate_id=other.id,
                            headline=other.fields.what if other.fields else "",
                            similarity_score=similarity,
                            readiness_state=other.readiness_state,
                        )
                    )
        else:
            # Fall back to simple keyword matching
            for other in all_candidates:
                if self._has_keyword_overlap(candidate, other):
                    suggestions.append(
                        DuplicateSuggestion(
                            candidate_id=other.id,
                            headline=other.fields.what if other.fields else "",
                            similarity_score=0.75,  # Default score for keyword match
                            readiness_state=other.readiness_state,
                        )
                    )

        # Sort by similarity and limit
        suggestions.sort(key=lambda x: x.similarity_score, reverse=True)
        return suggestions[:limit]

    def _get_candidate_text(self, candidate: COPCandidate) -> str:
        """Extract text content from a candidate for similarity comparison."""
        parts = []
        if candidate.fields:
            if candidate.fields.what:
                parts.append(candidate.fields.what)
            if candidate.fields.where:
                parts.append(candidate.fields.where)
            if candidate.fields.so_what:
                parts.append(candidate.fields.so_what)
        return " ".join(parts)

    def _has_keyword_overlap(
        self, candidate1: COPCandidate, candidate2: COPCandidate
    ) -> bool:
        """Check if two candidates have significant keyword overlap."""
        text1 = self._get_candidate_text(candidate1).lower()
        text2 = self._get_candidate_text(candidate2).lower()

        if not text1 or not text2:
            return False

        # Simple word overlap check
        words1 = set(text1.split())
        words2 = set(text2.split())

        # Remove common stop words
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at"}
        words1 -= stop_words
        words2 -= stop_words

        if not words1 or not words2:
            return False

        overlap = len(words1 & words2)
        min_words = min(len(words1), len(words2))

        return overlap / min_words >= 0.5

    async def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate semantic similarity between two texts."""
        if not self.embedding_service:
            return 0.0

        try:
            embedding1 = await self.embedding_service.embed_text(text1)
            embedding2 = await self.embedding_service.embed_text(text2)

            # Cosine similarity
            dot_product = sum(a * b for a, b in zip(embedding1, embedding2))
            norm1 = sum(a * a for a in embedding1) ** 0.5
            norm2 = sum(b * b for b in embedding2) ** 0.5

            if norm1 == 0 or norm2 == 0:
                return 0.0

            return dot_product / (norm1 * norm2)
        except Exception as e:
            logger.warning("Failed to calculate similarity", error=str(e))
            return 0.0

    async def merge_candidates(
        self,
        primary_candidate_id: ObjectId,
        secondary_candidate_ids: list[ObjectId],
        user: User,
        merge_reason: Optional[str] = None,
    ) -> MergeResult:
        """Merge secondary candidates into a primary candidate.

        This operation:
        1. Collects all signal IDs from secondary candidates
        2. Adds them to the primary candidate
        3. Archives the secondary candidates with merge metadata
        4. Records the merge action

        Args:
            primary_candidate_id: ID of the candidate to keep
            secondary_candidate_ids: IDs of candidates to merge into primary
            user: User performing the merge
            merge_reason: Optional reason for the merge

        Returns:
            MergeResult with the updated primary and merge statistics

        Raises:
            ValueError: If primary candidate not found or invalid merge
        """
        if not secondary_candidate_ids:
            raise ValueError("Must provide at least one secondary candidate to merge")

        logger.info(
            "Merging candidates",
            primary_id=str(primary_candidate_id),
            secondary_ids=[str(sid) for sid in secondary_candidate_ids],
            user_id=str(user.id),
        )

        # Load primary candidate
        primary = await self.candidate_repo.get_by_id(primary_candidate_id)
        if not primary:
            raise ValueError(f"Primary candidate not found: {primary_candidate_id}")

        # Collect signals from all secondary candidates
        signals_to_add: set[ObjectId] = set()
        merged_ids: list[ObjectId] = []

        for secondary_id in secondary_candidate_ids:
            if secondary_id == primary_candidate_id:
                continue  # Skip if same as primary

            secondary = await self.candidate_repo.get_by_id(secondary_id)
            if not secondary:
                logger.warning(
                    "Secondary candidate not found, skipping",
                    secondary_id=str(secondary_id),
                )
                continue

            # Add signals from secondary to primary
            for signal_id in secondary.primary_signal_ids:
                if signal_id not in primary.primary_signal_ids:
                    signals_to_add.add(signal_id)

            # Archive the secondary candidate
            await self.candidate_repo.update(
                secondary_id,
                {
                    "readiness_state": "merged",
                    "merged_into": primary_candidate_id,
                    "merged_at": datetime.utcnow(),
                    "merged_by": user.id,
                    "merge_reason": merge_reason,
                },
            )

            merged_ids.append(secondary_id)

        # Update primary with additional signals
        if signals_to_add:
            updated_signals = list(primary.primary_signal_ids) + list(signals_to_add)
            await self.candidate_repo.update(
                primary_candidate_id,
                {
                    "primary_signal_ids": updated_signals,
                    "merged_candidate_ids": merged_ids,
                    "last_merge_at": datetime.utcnow(),
                    "last_merge_by": user.id,
                },
            )
            primary.primary_signal_ids = updated_signals

        logger.info(
            "Candidates merged successfully",
            primary_id=str(primary_candidate_id),
            merged_count=len(merged_ids),
            signals_added=len(signals_to_add),
        )

        return MergeResult(
            primary_candidate=primary,
            merged_candidate_ids=merged_ids,
            signals_added=len(signals_to_add),
        )

    async def unmerge_candidate(
        self,
        merged_candidate_id: ObjectId,
        user: User,
    ) -> COPCandidate:
        """Restore a previously merged candidate.

        Args:
            merged_candidate_id: ID of the merged candidate to restore
            user: User performing the unmerge

        Returns:
            The restored candidate

        Raises:
            ValueError: If candidate not found or not merged
        """
        candidate = await self.candidate_repo.get_by_id(merged_candidate_id)
        if not candidate:
            raise ValueError(f"Candidate not found: {merged_candidate_id}")

        if candidate.readiness_state != "merged":
            raise ValueError("Candidate is not in merged state")

        logger.info(
            "Unmerging candidate",
            candidate_id=str(merged_candidate_id),
            user_id=str(user.id),
        )

        # Restore to IN_REVIEW state
        await self.candidate_repo.update(
            merged_candidate_id,
            {
                "readiness_state": ReadinessState.IN_REVIEW.value,
                "merged_into": None,
                "merged_at": None,
                "merged_by": None,
                "merge_reason": None,
                "unmerged_at": datetime.utcnow(),
                "unmerged_by": user.id,
            },
        )

        return await self.candidate_repo.get_by_id(merged_candidate_id)
