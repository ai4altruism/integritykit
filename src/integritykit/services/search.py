"""Facilitator search service for signals, clusters, and COP candidates.

Implements:
- FR-SEARCH-001: Searchable index with keyword, time range, channel filters
"""

import re
from datetime import datetime
from typing import Any, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection

from integritykit.models.cluster import Cluster
from integritykit.models.cop_candidate import COPCandidate
from integritykit.models.signal import Signal
from integritykit.services.database import (
    ClusterRepository,
    COPCandidateRepository,
    SignalRepository,
    get_collection,
)


def escape_regex(query: str) -> str:
    """Escape special regex characters to prevent ReDoS attacks.

    Args:
        query: User-provided search query

    Returns:
        Escaped query safe for use in MongoDB $regex
    """
    return re.escape(query)


class SearchResult:
    """Individual search result with relevance score."""

    def __init__(
        self,
        result_type: str,
        entity_id: ObjectId,
        content: str,
        preview: str,
        relevance_score: float,
        slack_permalink: Optional[str] = None,
        cluster_ids: Optional[list[ObjectId]] = None,
        cluster_topics: Optional[list[str]] = None,
        cop_candidate_id: Optional[ObjectId] = None,
        cop_candidate_state: Optional[str] = None,
        channel_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ):
        """Initialize search result.

        Args:
            result_type: Type of result (signal, cluster, cop_candidate)
            entity_id: ID of the entity
            content: Full content text
            preview: Truncated preview (200 chars)
            relevance_score: Search relevance score
            slack_permalink: Link to Slack message
            cluster_ids: Clusters this signal belongs to
            cluster_topics: Topics of associated clusters
            cop_candidate_id: Associated COP candidate if any
            cop_candidate_state: COP candidate readiness state
            channel_id: Slack channel ID
            created_at: Creation timestamp
        """
        self.result_type = result_type
        self.entity_id = entity_id
        self.content = content
        self.preview = preview
        self.relevance_score = relevance_score
        self.slack_permalink = slack_permalink
        self.cluster_ids = cluster_ids or []
        self.cluster_topics = cluster_topics or []
        self.cop_candidate_id = cop_candidate_id
        self.cop_candidate_state = cop_candidate_state
        self.channel_id = channel_id
        self.created_at = created_at

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response.

        Returns:
            Dictionary representation
        """
        return {
            "type": self.result_type,
            "id": str(self.entity_id),
            "content": self.content,
            "preview": self.preview,
            "relevance_score": self.relevance_score,
            "slack_permalink": self.slack_permalink,
            "cluster_ids": [str(cid) for cid in self.cluster_ids],
            "cluster_topics": self.cluster_topics,
            "cop_candidate_id": str(self.cop_candidate_id) if self.cop_candidate_id else None,
            "cop_candidate_state": self.cop_candidate_state,
            "channel_id": self.channel_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SearchService:
    """Service for searching signals, clusters, and COP candidates (FR-SEARCH-001).

    Provides full-text search with filters for time range and channel.
    Access is restricted to facilitators and verifiers.
    """

    def __init__(
        self,
        signal_repo: Optional[SignalRepository] = None,
        cluster_repo: Optional[ClusterRepository] = None,
        candidate_repo: Optional[COPCandidateRepository] = None,
    ):
        """Initialize search service.

        Args:
            signal_repo: Signal repository (optional)
            cluster_repo: Cluster repository (optional)
            candidate_repo: COP candidate repository (optional)
        """
        self.signal_repo = signal_repo or SignalRepository()
        self.cluster_repo = cluster_repo or ClusterRepository()
        self.candidate_repo = candidate_repo or COPCandidateRepository()

    async def search(
        self,
        workspace_id: str,
        query: Optional[str] = None,
        channel_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        include_signals: bool = True,
        include_clusters: bool = True,
        include_candidates: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SearchResult]:
        """Search signals, clusters, and COP candidates.

        Args:
            workspace_id: Slack workspace ID
            query: Text search query (optional)
            channel_id: Filter by channel (optional)
            start_time: Filter signals after this time (optional)
            end_time: Filter signals before this time (optional)
            include_signals: Include signals in results
            include_clusters: Include clusters in results
            include_candidates: Include COP candidates in results
            limit: Maximum results to return
            offset: Number of results to skip

        Returns:
            List of SearchResult instances sorted by relevance
        """
        results: list[SearchResult] = []

        # Search signals
        if include_signals:
            signal_results = await self._search_signals(
                workspace_id=workspace_id,
                query=query,
                channel_id=channel_id,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
            )
            results.extend(signal_results)

        # Search clusters
        if include_clusters:
            cluster_results = await self._search_clusters(
                workspace_id=workspace_id,
                query=query,
                limit=limit,
            )
            results.extend(cluster_results)

        # Search COP candidates
        if include_candidates:
            candidate_results = await self._search_candidates(
                workspace_id=workspace_id,
                query=query,
                limit=limit,
            )
            results.extend(candidate_results)

        # Sort by relevance score
        results.sort(key=lambda x: x.relevance_score, reverse=True)

        # Apply pagination
        return results[offset : offset + limit]

    async def _search_signals(
        self,
        workspace_id: str,
        query: Optional[str] = None,
        channel_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 50,
    ) -> list[SearchResult]:
        """Search signals with text and time filters.

        Args:
            workspace_id: Slack workspace ID
            query: Text search query
            channel_id: Filter by channel
            start_time: Filter after this time
            end_time: Filter before this time
            limit: Maximum results

        Returns:
            List of SearchResult instances
        """
        collection = self.signal_repo.collection

        # Build query
        match_query: dict[str, Any] = {
            "slack_workspace_id": workspace_id,
        }

        if channel_id:
            match_query["slack_channel_id"] = channel_id

        if start_time or end_time:
            match_query["created_at"] = {}
            if start_time:
                match_query["created_at"]["$gte"] = start_time
            if end_time:
                match_query["created_at"]["$lte"] = end_time

        # Use text search if query provided
        if query:
            # MongoDB text search
            match_query["$text"] = {"$search": query}

            # Use aggregation for text score
            pipeline = [
                {"$match": match_query},
                {"$addFields": {"score": {"$meta": "textScore"}}},
                {"$sort": {"score": -1}},
                {"$limit": limit},
            ]

            signals = []
            async for doc in collection.aggregate(pipeline):
                signal = Signal(**{k: v for k, v in doc.items() if k != "score"})
                score = doc.get("score", 1.0)
                signals.append((signal, score))
        else:
            # No text search, just filter
            cursor = (
                collection.find(match_query)
                .sort("created_at", -1)
                .limit(limit)
            )
            signals = []
            async for doc in cursor:
                signal = Signal(**doc)
                signals.append((signal, 1.0))

        # Build results with cluster lookups
        results = []
        for signal, score in signals:
            # Look up cluster info
            cluster_topics = []
            cop_candidate_id = None
            cop_candidate_state = None

            if signal.cluster_ids:
                for cluster_id in signal.cluster_ids[:3]:  # Limit lookups
                    cluster = await self.cluster_repo.get_by_id(cluster_id)
                    if cluster:
                        cluster_topics.append(cluster.topic)
                        if cluster.cop_candidate_id and not cop_candidate_id:
                            cop_candidate_id = cluster.cop_candidate_id
                            candidate = await self.candidate_repo.get_by_id(cop_candidate_id)
                            if candidate:
                                cop_candidate_state = candidate.readiness_state

            # Create preview
            preview = signal.content[:200]
            if len(signal.content) > 200:
                preview += "..."

            results.append(
                SearchResult(
                    result_type="signal",
                    entity_id=signal.id,
                    content=signal.content,
                    preview=preview,
                    relevance_score=score,
                    slack_permalink=signal.slack_permalink,
                    cluster_ids=signal.cluster_ids,
                    cluster_topics=cluster_topics,
                    cop_candidate_id=cop_candidate_id,
                    cop_candidate_state=cop_candidate_state,
                    channel_id=signal.slack_channel_id,
                    created_at=signal.created_at,
                )
            )

        return results

    async def _search_clusters(
        self,
        workspace_id: str,
        query: Optional[str] = None,
        limit: int = 50,
    ) -> list[SearchResult]:
        """Search clusters by topic and summary.

        Args:
            workspace_id: Slack workspace ID
            query: Text search query
            limit: Maximum results

        Returns:
            List of SearchResult instances
        """
        collection = self.cluster_repo.collection

        # Build query
        match_query: dict[str, Any] = {
            "slack_workspace_id": workspace_id,
        }

        if query:
            # Search in topic and summary using regex (text index may not exist)
            # Escape special chars to prevent ReDoS attacks (S7-8)
            query_regex = {"$regex": escape_regex(query), "$options": "i"}
            match_query["$or"] = [
                {"topic": query_regex},
                {"summary": query_regex},
            ]

        cursor = (
            collection.find(match_query)
            .sort("updated_at", -1)
            .limit(limit)
        )

        results = []
        async for doc in cursor:
            cluster = Cluster(**doc)

            # Calculate relevance based on query match position
            score = 1.0
            if query:
                query_lower = query.lower()
                if query_lower in cluster.topic.lower():
                    score = 2.0  # Topic match is more relevant
                elif cluster.summary and query_lower in cluster.summary.lower():
                    score = 1.5  # Summary match is moderately relevant

            # Look up COP candidate status
            cop_candidate_id = cluster.cop_candidate_id
            cop_candidate_state = None
            if cop_candidate_id:
                candidate = await self.candidate_repo.get_by_id(cop_candidate_id)
                if candidate:
                    cop_candidate_state = candidate.readiness_state

            # Create content and preview
            content = f"{cluster.topic}: {cluster.summary}"
            preview = content[:200]
            if len(content) > 200:
                preview += "..."

            results.append(
                SearchResult(
                    result_type="cluster",
                    entity_id=cluster.id,
                    content=content,
                    preview=preview,
                    relevance_score=score,
                    slack_permalink=None,
                    cluster_ids=[cluster.id],
                    cluster_topics=[cluster.topic],
                    cop_candidate_id=cop_candidate_id,
                    cop_candidate_state=cop_candidate_state,
                    channel_id=None,
                    created_at=cluster.created_at,
                )
            )

        return results

    async def _search_candidates(
        self,
        workspace_id: str,
        query: Optional[str] = None,
        limit: int = 50,
    ) -> list[SearchResult]:
        """Search COP candidates.

        Args:
            workspace_id: Slack workspace ID
            query: Text search query
            limit: Maximum results

        Returns:
            List of SearchResult instances
        """
        # First get workspace cluster IDs
        cluster_collection = self.cluster_repo.collection
        cluster_ids = []
        async for doc in cluster_collection.find(
            {"slack_workspace_id": workspace_id},
            {"_id": 1},
        ):
            cluster_ids.append(doc["_id"])

        if not cluster_ids:
            return []

        # Search candidates
        collection = self.candidate_repo.collection

        match_query: dict[str, Any] = {
            "cluster_id": {"$in": cluster_ids},
        }

        cursor = (
            collection.find(match_query)
            .sort("updated_at", -1)
            .limit(limit)
        )

        results = []
        async for doc in cursor:
            candidate = COPCandidate(**doc)

            # Get cluster for topic
            cluster = await self.cluster_repo.get_by_id(candidate.cluster_id)
            cluster_topic = cluster.topic if cluster else "Unknown"

            # Build content from fields
            fields = candidate.fields
            content = f"{cluster_topic}: {fields.what}"
            if fields.where:
                content += f" ({fields.where})"

            # Calculate relevance
            score = 1.0
            if query:
                query_lower = query.lower()
                if query_lower in cluster_topic.lower():
                    score = 2.0
                elif query_lower in content.lower():
                    score = 1.5
                else:
                    # No match, skip this result
                    continue

            preview = content[:200]
            if len(content) > 200:
                preview += "..."

            results.append(
                SearchResult(
                    result_type="cop_candidate",
                    entity_id=candidate.id,
                    content=content,
                    preview=preview,
                    relevance_score=score,
                    slack_permalink=None,
                    cluster_ids=[candidate.cluster_id],
                    cluster_topics=[cluster_topic],
                    cop_candidate_id=candidate.id,
                    cop_candidate_state=candidate.readiness_state,
                    channel_id=None,
                    created_at=candidate.created_at,
                )
            )

        return results

    async def count_results(
        self,
        workspace_id: str,
        query: Optional[str] = None,
        channel_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> dict[str, int]:
        """Count search results by type.

        Args:
            workspace_id: Slack workspace ID
            query: Text search query
            channel_id: Filter by channel
            start_time: Filter after this time
            end_time: Filter before this time

        Returns:
            Dictionary with counts by type
        """
        signal_count = await self._count_signals(
            workspace_id, query, channel_id, start_time, end_time
        )
        cluster_count = await self._count_clusters(workspace_id, query)

        return {
            "signals": signal_count,
            "clusters": cluster_count,
            "total": signal_count + cluster_count,
        }

    async def _count_signals(
        self,
        workspace_id: str,
        query: Optional[str] = None,
        channel_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        """Count matching signals."""
        collection = self.signal_repo.collection

        match_query: dict[str, Any] = {
            "slack_workspace_id": workspace_id,
        }

        if channel_id:
            match_query["slack_channel_id"] = channel_id

        if start_time or end_time:
            match_query["created_at"] = {}
            if start_time:
                match_query["created_at"]["$gte"] = start_time
            if end_time:
                match_query["created_at"]["$lte"] = end_time

        if query:
            match_query["$text"] = {"$search": query}

        return await collection.count_documents(match_query)

    async def _count_clusters(
        self,
        workspace_id: str,
        query: Optional[str] = None,
    ) -> int:
        """Count matching clusters."""
        collection = self.cluster_repo.collection

        match_query: dict[str, Any] = {
            "slack_workspace_id": workspace_id,
        }

        if query:
            # Escape special chars to prevent ReDoS attacks (S7-8)
            query_regex = {"$regex": escape_regex(query), "$options": "i"}
            match_query["$or"] = [
                {"topic": query_regex},
                {"summary": query_regex},
            ]

        return await collection.count_documents(match_query)


# Global service instance
_search_service: Optional[SearchService] = None


def get_search_service() -> SearchService:
    """Get the global search service instance.

    Returns:
        SearchService singleton
    """
    global _search_service
    if _search_service is None:
        _search_service = SearchService()
    return _search_service
