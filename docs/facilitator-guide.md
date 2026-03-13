# Facilitator Quick-Start Guide

This guide covers the end-to-end workflow for facilitators publishing COP updates.

## Overview

As a facilitator, you coordinate the transformation of Slack conversations into verified situational awareness updates. The system helps you:

1. Monitor the prioritized backlog of clustered signals
2. Promote important clusters to COP candidates
3. Review and verify candidate information
4. Generate draft COP updates with proper wording
5. Approve and publish updates to Slack

## Publish Workflow

The publish workflow ensures human approval at every step:

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   CREATE    │───▶│    EDIT     │───▶│   APPROVE   │───▶│   PUBLISH   │
│    DRAFT    │    │  (optional) │    │  (required) │    │  to Slack   │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

### Step 1: Create Draft

Select one or more verified COP candidates and generate a draft:

```http
POST /api/v1/publish/drafts
{
  "candidate_ids": ["candidate-id-1", "candidate-id-2"],
  "title": "Crisis Update #5"
}
```

The system generates line items with:
- **VERIFIED** status for confirmed information (direct factual wording)
- **IN REVIEW** status for unconfirmed reports (hedged wording: "Unconfirmed reports indicate...")

### Step 2: Edit Line Items (Optional)

Review the auto-generated text and edit if needed:

```http
PATCH /api/v1/publish/drafts/{update_id}/line-items
{
  "item_index": 0,
  "new_text": "Corrected text here"
}
```

All edits are logged with before/after snapshots for audit purposes.

### Step 3: Preview

View how the update will appear in Slack:

```http
GET /api/v1/publish/drafts/{update_id}/preview
```

Returns both markdown and Slack Block Kit format.

### Step 4: Approve (Required)

No update can be published without explicit human approval:

```http
POST /api/v1/publish/drafts/{update_id}/approve
{
  "notes": "Reviewed and verified all items"
}
```

This is the critical safety gate - the system will not post anything to Slack without this step.

### Step 5: Publish

After approval, publish to your designated Slack channel:

```http
POST /api/v1/publish/drafts/{update_id}/publish
{
  "channel_id": "C123456789"
}
```

The update is posted with:
- Formatted Block Kit sections for Verified/In Review/Rumor Control
- Clickable citation links to source messages
- IntegrityKit attribution and facilitator review notice

## Clarification Templates

When you need additional information from reporters, use pre-built templates:

```http
POST /api/v1/publish/clarification-template
{
  "template_type": "location",
  "topic": "shelter opening"
}
```

Available template types:

| Type | Purpose |
|------|---------|
| `location` | Request specific address or landmark details |
| `time` | Clarify when something occurred or is expected |
| `source` | Ask for verification source or eyewitness status |
| `status` | Request current status update |
| `impact` | Understand who/what is affected |
| `general` | General follow-up request |

## Audit Trail

Every action is logged for transparency and accountability:

```http
GET /api/v1/audit/logs?target_type=cop_update&target_id={update_id}
```

The audit log captures:
- Who performed each action (actor ID and role)
- What changed (before/after state)
- When it happened (immutable timestamp)
- Why (justification notes for approvals)

## Common Workflows

### Publishing a Single Verified Item

1. Navigate to COP Candidates list
2. Select a VERIFIED candidate
3. Create draft → Preview → Approve → Publish

### Handling Conflicting Information

1. Identify candidates with conflicts (🔴 indicator)
2. Use clarification templates to gather more info
3. Resolve conflict in the candidate workflow
4. Only then include in a COP draft

### Creating a Mixed Update

1. Select multiple candidates (some verified, some in-review)
2. System automatically sections them appropriately
3. Verified items get direct wording
4. In-review items get hedged wording ("Unconfirmed reports...")
5. Open questions appear in a separate section
