"""AI metadata utilities for labeling system-generated content.

This module provides utilities for consistent AI metadata generation across all
AI-generated content (clusters, duplicates, conflicts, summaries, etc.).

Per NFR-TRANSPARENCY-001, all AI-generated content must be clearly labeled.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional


class AIOperationType(str, Enum):
    """Types of AI operations that generate content."""

    CLUSTERING = "clustering"
    DUPLICATE_DETECTION = "duplicate_detection"
    CONFLICT_DETECTION = "conflict_detection"
    SUMMARY_GENERATION = "summary_generation"
    PRIORITY_ASSESSMENT = "priority_assessment"
    TOPIC_GENERATION = "topic_generation"
    COP_DRAFT = "cop_draft"
    EMBEDDING_GENERATION = "embedding_generation"


def create_ai_metadata(
    model: str,
    operation: AIOperationType | str,
    confidence: Optional[float] = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Generate standard AI metadata structure.

    This ensures all AI-generated content includes consistent metadata
    for transparency and auditability.

    Args:
        model: Model identifier (e.g., "gpt-4o-mini", "text-embedding-3-small")
        operation: Type of AI operation performed
        confidence: Optional confidence score (0.0-1.0)
        **kwargs: Additional operation-specific metadata

    Returns:
        Dictionary with standardized AI metadata including:
        - ai_generated: True
        - model: Model identifier
        - operation: Operation type
        - generated_at: ISO timestamp
        - confidence: Optional confidence score
        - Additional kwargs merged in

    Examples:
        >>> create_ai_metadata(
        ...     model="gpt-4o-mini",
        ...     operation=AIOperationType.CLUSTERING,
        ...     confidence=0.92,
        ...     cluster_id="abc123"
        ... )
        {
            'ai_generated': True,
            'model': 'gpt-4o-mini',
            'operation': 'clustering',
            'generated_at': '2025-01-15T10:30:00.000000',
            'confidence': 0.92,
            'cluster_id': 'abc123'
        }
    """
    # Convert enum to string if needed
    operation_str = operation.value if isinstance(operation, AIOperationType) else operation

    metadata = {
        "ai_generated": True,
        "model": model,
        "operation": operation_str,
        "generated_at": datetime.utcnow().isoformat(),
    }

    # Add optional confidence
    if confidence is not None:
        metadata["confidence"] = confidence

    # Merge additional metadata
    metadata.update(kwargs)

    return metadata


def mark_ai_generated(
    document: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Add AI metadata to any document.

    Args:
        document: Document to mark (will be modified in place)
        metadata: AI metadata to add (from create_ai_metadata)

    Returns:
        Modified document with AI metadata

    Examples:
        >>> doc = {"topic": "Shelter Alpha", "summary": "..."}
        >>> metadata = create_ai_metadata("gpt-4o-mini", AIOperationType.SUMMARY_GENERATION)
        >>> mark_ai_generated(doc, metadata)
        {
            'topic': 'Shelter Alpha',
            'summary': '...',
            'ai_generated_metadata': {
                'ai_generated': True,
                'model': 'gpt-4o-mini',
                'operation': 'summary_generation',
                'generated_at': '2025-01-15T10:30:00.000000'
            }
        }
    """
    document["ai_generated_metadata"] = metadata
    return document


def merge_ai_metadata(
    existing: Optional[dict[str, Any]],
    new_metadata: dict[str, Any],
) -> dict[str, Any]:
    """Merge new AI metadata with existing metadata.

    Useful when a document undergoes multiple AI operations.

    Args:
        existing: Existing AI metadata (can be None)
        new_metadata: New AI metadata to merge

    Returns:
        Merged metadata with operation history

    Examples:
        >>> existing = {
        ...     "ai_generated": True,
        ...     "model": "gpt-4o-mini",
        ...     "operation": "clustering",
        ...     "generated_at": "2025-01-15T10:00:00.000000"
        ... }
        >>> new = create_ai_metadata("gpt-4o", AIOperationType.PRIORITY_ASSESSMENT)
        >>> merge_ai_metadata(existing, new)
        {
            'ai_generated': True,
            'model': 'gpt-4o',
            'operation': 'priority_assessment',
            'generated_at': '2025-01-15T10:30:00.000000',
            'operation_history': [
                {
                    'operation': 'clustering',
                    'model': 'gpt-4o-mini',
                    'generated_at': '2025-01-15T10:00:00.000000'
                },
                {
                    'operation': 'priority_assessment',
                    'model': 'gpt-4o',
                    'generated_at': '2025-01-15T10:30:00.000000'
                }
            ]
        }
    """
    if not existing:
        return new_metadata

    # Create operation history
    history = existing.get("operation_history", [])

    # Add previous operation to history
    history.append(
        {
            "operation": existing.get("operation"),
            "model": existing.get("model"),
            "generated_at": existing.get("generated_at"),
        }
    )

    # Add current operation to history
    history.append(
        {
            "operation": new_metadata.get("operation"),
            "model": new_metadata.get("model"),
            "generated_at": new_metadata.get("generated_at"),
        }
    )

    # Merge with new metadata taking precedence
    merged = {**existing, **new_metadata}
    merged["operation_history"] = history

    return merged


def get_ai_operation_label(operation: AIOperationType | str) -> str:
    """Get human-readable label for AI operation.

    Args:
        operation: AI operation type

    Returns:
        Human-readable operation label

    Examples:
        >>> get_ai_operation_label(AIOperationType.CLUSTERING)
        'AI-Generated Cluster'
        >>> get_ai_operation_label("duplicate_detection")
        'AI-Detected Duplicate'
    """
    operation_str = operation.value if isinstance(operation, AIOperationType) else operation

    labels = {
        "clustering": "AI-Generated Cluster",
        "duplicate_detection": "AI-Detected Duplicate",
        "conflict_detection": "AI-Detected Conflict",
        "summary_generation": "AI-Generated Summary",
        "priority_assessment": "AI-Generated Priority Score",
        "topic_generation": "AI-Generated Topic",
        "cop_draft": "AI-Generated COP Draft",
        "embedding_generation": "AI-Generated Embedding",
    }

    return labels.get(operation_str, f"AI-Generated ({operation_str})")
