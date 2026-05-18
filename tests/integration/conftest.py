"""Integration-test setup: stub required env vars before package import.

Several integration tests import `integritykit.api.*`, which transitively
constructs a `Settings()` instance at module-load time. Without these stubs,
collection fails with `ValidationError` for the required Slack and OpenAI
fields. Keep this file colocated with the integration tests so unit tests
remain unaffected.
"""

import os

os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test-token")
os.environ.setdefault("SLACK_SIGNING_SECRET", "test-signing-secret")
os.environ.setdefault("SLACK_WORKSPACE_ID", "T01TEST")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-key")
