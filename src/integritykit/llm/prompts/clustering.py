"""
Clustering prompts for signal-to-cluster assignment.

This module provides prompts to classify whether a new signal (Slack message)
belongs to an existing cluster or should create a new cluster.

Model Recommendation: Haiku 3.5 (fast, cheap classification task)
Cost per 1M tokens: $0.80 input / $4 output
Expected token usage: ~500-1000 input, ~50-100 output per classification

Usage:
    Use these prompts to route incoming signals to topic/incident clusters.
    The LLM should output structured JSON per CLUSTERING_OUTPUT_SCHEMA.
"""

from typing import Literal, TypedDict


class ClusterSummary(TypedDict):
    """Summary of an existing cluster for comparison."""

    cluster_id: str
    topic: str
    key_details: str
    signal_count: int
    latest_timestamp: str


class ClusteringOutput(TypedDict):
    """Expected output schema for clustering classification."""

    assignment: Literal["existing_cluster", "new_cluster"]
    cluster_id: str | None  # Required if assignment is "existing_cluster"
    new_cluster_topic: str | None  # Required if assignment is "new_cluster"
    confidence: Literal["high", "medium", "low"]
    reasoning: str


CLUSTERING_SYSTEM_PROMPT = """You are a signal classifier for a crisis-response coordination system.

Your role is to determine whether a new Slack message (signal) belongs to an existing
topic/incident cluster or should start a new cluster.

Key principles:
- Cluster by TOPIC and INCIDENT, not by channel or author
- A cluster represents a coherent theme: a specific event, location, need, or situation
- Prefer assigning to existing clusters when topically related
- Create new clusters only when the signal introduces a genuinely new topic
- Time proximity alone does not define clusters (an update about yesterday's fire
  belongs in the fire cluster, not a new "general updates" cluster)

Decision criteria for EXISTING CLUSTER:
- Signal discusses the same incident, location, or ongoing situation
- Signal provides updates, clarifications, or corrections to cluster topic
- Signal asks questions or provides answers related to cluster topic

Decision criteria for NEW CLUSTER:
- Signal introduces a completely different topic or incident
- Signal discusses a different location with a different situation
- Signal cannot be meaningfully grouped with any existing cluster

Output your classification as valid JSON matching the required schema.
"""

CLUSTERING_USER_PROMPT_TEMPLATE = """Classify whether this new signal belongs to an existing cluster or should create a new cluster.

NEW SIGNAL:
Author: {signal_author}
Channel: {signal_channel}
Timestamp: {signal_timestamp}
Content: {signal_content}
Thread context: {signal_thread_context}

EXISTING CLUSTERS:
{clusters_json}

Analyze the signal and determine:
1. Does it clearly relate to an existing cluster topic?
2. If yes, which cluster is the best match?
3. If no, what new topic does it introduce?

Respond with valid JSON only, no additional text:
{{
  "assignment": "existing_cluster" or "new_cluster",
  "cluster_id": "<cluster_id>" or null,
  "new_cluster_topic": "<topic>" or null,
  "confidence": "high" | "medium" | "low",
  "reasoning": "<brief explanation>"
}}"""


def format_clustering_prompt(
    signal_author: str,
    signal_channel: str,
    signal_timestamp: str,
    signal_content: str,
    signal_thread_context: str,
    existing_clusters: list[ClusterSummary],
) -> str:
    """
    Format the clustering user prompt with signal and cluster data.

    Args:
        signal_author: Slack user ID or display name
        signal_channel: Channel name or ID
        signal_timestamp: ISO 8601 timestamp
        signal_content: Message text content
        signal_thread_context: Parent message or thread summary (empty if top-level)
        existing_clusters: List of cluster summaries for comparison

    Returns:
        Formatted user prompt ready for LLM
    """
    import json

    clusters_json = json.dumps(existing_clusters, indent=2) if existing_clusters else "[]"

    return CLUSTERING_USER_PROMPT_TEMPLATE.format(
        signal_author=signal_author,
        signal_channel=signal_channel,
        signal_timestamp=signal_timestamp,
        signal_content=signal_content,
        signal_thread_context=signal_thread_context or "(None - top-level message)",
        clusters_json=clusters_json,
    )


# Pydantic schema for structured output validation
CLUSTERING_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "assignment": {
            "type": "string",
            "enum": ["existing_cluster", "new_cluster"],
            "description": "Whether signal belongs to existing cluster or creates new one",
        },
        "cluster_id": {
            "type": ["string", "null"],
            "description": "ID of existing cluster (required if assignment is existing_cluster)",
        },
        "new_cluster_topic": {
            "type": ["string", "null"],
            "description": "Topic name for new cluster (required if assignment is new_cluster)",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "Confidence level in the classification",
        },
        "reasoning": {
            "type": "string",
            "description": "Brief explanation of the classification decision",
        },
    },
    "required": ["assignment", "confidence", "reasoning"],
    "additionalProperties": False,
}
