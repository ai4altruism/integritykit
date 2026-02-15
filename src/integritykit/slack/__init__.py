"""Slack integration for event handling and message ingestion."""

from integritykit.slack.blocks import (
    build_candidate_detail_blocks,
    build_candidate_list_item_blocks,
    build_fields_checklist_blocks,
    build_next_action_blocks,
    build_readiness_summary_blocks,
)
from integritykit.slack.events import SlackEventHandler
from integritykit.slack.home import SlackAppHomeHandler

__all__ = [
    "SlackAppHomeHandler",
    "SlackEventHandler",
    "build_candidate_detail_blocks",
    "build_candidate_list_item_blocks",
    "build_fields_checklist_blocks",
    "build_next_action_blocks",
    "build_readiness_summary_blocks",
]
