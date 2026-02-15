"""LLM service for cluster classification, summarization, and priority assessment."""

import json
from typing import Optional

import structlog
from openai import AsyncOpenAI

from integritykit.llm.prompts.clustering import (
    CLUSTERING_SYSTEM_PROMPT,
    CLUSTERING_USER_PROMPT_TEMPLATE,
    ClusterSummary,
    ClusteringOutput,
)
from integritykit.models.cluster import Cluster, PriorityScores
from integritykit.models.signal import Signal

logger = structlog.get_logger(__name__)


class LLMService:
    """Service for LLM-powered cluster operations."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        temperature: float = 0.3,
    ):
        """Initialize LLM service.

        Args:
            api_key: OpenAI API key
            model: Model to use for LLM operations
            temperature: Temperature for generation (0.0-1.0)
        """
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.temperature = temperature

    async def classify_cluster_assignment(
        self,
        signal: Signal,
        existing_clusters: list[Cluster],
        thread_context: str = "",
    ) -> ClusteringOutput:
        """Classify whether signal belongs to existing cluster or creates new one.

        Args:
            signal: Signal to classify
            existing_clusters: List of existing clusters to compare against
            thread_context: Optional thread context for the signal

        Returns:
            ClusteringOutput with assignment decision
        """
        # Convert clusters to summaries for prompt
        cluster_summaries: list[ClusterSummary] = []
        for cluster in existing_clusters:
            cluster_summaries.append(
                ClusterSummary(
                    cluster_id=str(cluster.id),
                    topic=cluster.topic,
                    key_details=cluster.summary[:200],  # Truncate for prompt
                    signal_count=cluster.signal_count,
                    latest_timestamp=cluster.updated_at.isoformat(),
                )
            )

        # Format prompt
        clusters_json = json.dumps(cluster_summaries, indent=2) if cluster_summaries else "[]"

        user_prompt = CLUSTERING_USER_PROMPT_TEMPLATE.format(
            signal_author=signal.slack_user_id,
            signal_channel=signal.slack_channel_id,
            signal_timestamp=signal.created_at.isoformat(),
            signal_content=signal.content,
            signal_thread_context=thread_context or "(None - top-level message)",
            clusters_json=clusters_json,
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": CLUSTERING_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )

            # Parse response
            content = response.content if hasattr(response, 'content') else response.choices[0].message.content
            result = json.loads(content)

            logger.info(
                "Classified cluster assignment",
                signal_id=str(signal.id),
                assignment=result.get("assignment"),
                confidence=result.get("confidence"),
                cluster_id=result.get("cluster_id"),
                model=self.model,
            )

            return ClusteringOutput(**result)

        except Exception as e:
            logger.error(
                "Failed to classify cluster assignment",
                signal_id=str(signal.id),
                error=str(e),
            )
            raise

    async def generate_cluster_summary(
        self,
        signals: list[Signal],
        topic: str,
    ) -> str:
        """Generate summary of cluster content from signals.

        Args:
            signals: List of signals in the cluster
            topic: Cluster topic

        Returns:
            Generated summary text
        """
        # Build signal context
        signal_texts = []
        for i, signal in enumerate(signals[:10], 1):  # Limit to 10 most recent
            signal_texts.append(
                f"{i}. [{signal.created_at.isoformat()}] {signal.content[:200]}"
            )

        signals_context = "\n".join(signal_texts)

        system_prompt = """You are a crisis response coordinator summarizing related signals into a coherent cluster summary.

Create a concise summary (2-3 sentences) that captures:
- The core topic/incident being discussed
- Key details (location, time, people affected, etc.)
- Current status or latest developments

Focus on facts mentioned in the signals. Do not speculate or add information not present."""

        user_prompt = f"""Topic: {topic}

Signals in this cluster:
{signals_context}

Generate a summary of this cluster (2-3 sentences):"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )

            summary = response.choices[0].message.content

            logger.info(
                "Generated cluster summary",
                topic=topic,
                signal_count=len(signals),
                summary_length=len(summary),
                model=self.model,
            )

            return summary

        except Exception as e:
            logger.error(
                "Failed to generate cluster summary",
                topic=topic,
                error=str(e),
            )
            raise

    async def assess_priority(
        self,
        cluster: Cluster,
        signals: list[Signal],
    ) -> PriorityScores:
        """Assess priority scores for a cluster.

        Args:
            cluster: Cluster to assess
            signals: Signals in the cluster

        Returns:
            PriorityScores with urgency, impact, and risk scores
        """
        # Build signal context
        signal_texts = []
        for signal in signals[:10]:  # Limit to 10 most recent
            signal_texts.append(f"- {signal.content[:200]}")

        signals_context = "\n".join(signal_texts)

        system_prompt = """You are a crisis response coordinator assessing the priority of incident clusters.

Evaluate the cluster on three dimensions (0-100 scale):

1. URGENCY (0-100): How time-sensitive is this? Does it require immediate action?
   - 0-25: Not time-sensitive, can wait days
   - 25-50: Should be addressed within 24 hours
   - 50-75: Should be addressed within hours
   - 75-100: Requires immediate action (minutes to 1 hour)

2. IMPACT (0-100): How many people are affected? How severe is the situation?
   - 0-25: Minimal impact, few people affected
   - 25-50: Moderate impact, specific group affected
   - 50-75: Significant impact, many people affected
   - 75-100: Critical impact, large population or severe consequences

3. RISK (0-100): What is the safety/harm risk if not addressed?
   - 0-25: Low risk, informational only
   - 25-50: Some risk, monitoring needed
   - 50-75: Elevated risk, safety concerns
   - 75-100: Critical risk, immediate safety threat

Respond with valid JSON only:
{
  "urgency": <0-100>,
  "urgency_reasoning": "<brief explanation>",
  "impact": <0-100>,
  "impact_reasoning": "<brief explanation>",
  "risk": <0-100>,
  "risk_reasoning": "<brief explanation>"
}"""

        user_prompt = f"""Topic: {cluster.topic}

Summary: {cluster.summary}

Recent signals:
{signals_context}

Assess the priority of this cluster:"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            result = json.loads(content)

            priority_scores = PriorityScores(**result)

            logger.info(
                "Assessed cluster priority",
                cluster_id=str(cluster.id),
                urgency=priority_scores.urgency,
                impact=priority_scores.impact,
                risk=priority_scores.risk,
                composite=priority_scores.composite_score,
                model=self.model,
            )

            return priority_scores

        except Exception as e:
            logger.error(
                "Failed to assess cluster priority",
                cluster_id=str(cluster.id),
                error=str(e),
            )
            raise

    async def generate_topic_from_signal(self, signal: Signal) -> str:
        """Generate a topic name for a new cluster from a signal.

        Args:
            signal: Signal to generate topic from

        Returns:
            Generated topic name (short, concise)
        """
        system_prompt = """You are a crisis response coordinator creating concise topic names for incident clusters.

Generate a short, descriptive topic name (5-10 words max) that captures the core subject of the message.

Examples:
- "Shelter Alpha Closure - Power Outage"
- "Water Distribution - Zone 3"
- "Road Closure - Highway 50 Bridge"
- "Medical Supplies Request - County Hospital"

Respond with ONLY the topic name, no additional text."""

        user_prompt = f"""Message: {signal.content}

Generate a topic name for this message:"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                temperature=0.5,  # Slightly higher for creativity
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )

            topic = response.choices[0].message.content.strip()

            logger.info(
                "Generated topic from signal",
                signal_id=str(signal.id),
                topic=topic,
                model=self.model,
            )

            return topic

        except Exception as e:
            logger.error(
                "Failed to generate topic",
                signal_id=str(signal.id),
                error=str(e),
            )
            raise
