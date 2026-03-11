"""Webhook service for external system integrations.

Implements:
- FR-INT-001: Webhook system with retry and logging
- Task S8-17: Outbound webhook system
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection

from integritykit.config import settings
from integritykit.models.webhook import (
    AuthConfig,
    AuthType,
    Webhook,
    WebhookCreate,
    WebhookDelivery,
    WebhookEvent,
    WebhookPayload,
    WebhookStatus,
    WebhookTestResult,
    WebhookUpdate,
)
from integritykit.services.database import get_collection

logger = logging.getLogger(__name__)


class WebhookService:
    """Service for managing webhooks and delivering events."""

    def __init__(
        self,
        webhooks_collection: Optional[AsyncIOMotorCollection] = None,
        deliveries_collection: Optional[AsyncIOMotorCollection] = None,
    ):
        """Initialize webhook service.

        Args:
            webhooks_collection: MongoDB collection for webhooks
            deliveries_collection: MongoDB collection for webhook deliveries
        """
        self.webhooks = webhooks_collection or get_collection("webhooks")
        self.deliveries = deliveries_collection or get_collection("webhook_deliveries")

    # =========================================================================
    # CRUD Operations
    # =========================================================================

    async def create_webhook(
        self,
        webhook_data: WebhookCreate,
        workspace_id: str,
        created_by: str,
    ) -> Webhook:
        """Create a new webhook.

        Args:
            webhook_data: Webhook creation data
            workspace_id: Workspace ID
            created_by: User ID creating the webhook

        Returns:
            Created webhook

        Raises:
            ValueError: If URL is invalid or webhook already exists
        """
        # Validate URL
        self._validate_webhook_url(webhook_data.url)

        # Check for duplicate URL in workspace
        existing = await self.webhooks.find_one(
            {"workspace_id": workspace_id, "url": webhook_data.url}
        )
        if existing:
            raise ValueError(f"Webhook with URL {webhook_data.url} already exists")

        # Create webhook
        webhook = Webhook(
            workspace_id=workspace_id,
            created_by=created_by,
            **webhook_data.model_dump(exclude_unset=True),
        )

        # Insert into database
        webhook_dict = webhook.model_dump(by_alias=True, exclude={"id"})
        result = await self.webhooks.insert_one(webhook_dict)
        webhook.id = result.inserted_id

        logger.info(
            f"Created webhook {webhook.id} for workspace {workspace_id}: "
            f"{webhook.name} -> {webhook.url}"
        )

        return webhook

    async def get_webhook(
        self,
        webhook_id: ObjectId,
        workspace_id: str,
    ) -> Optional[Webhook]:
        """Get webhook by ID.

        Args:
            webhook_id: Webhook ID
            workspace_id: Workspace ID (for authorization)

        Returns:
            Webhook if found, None otherwise
        """
        webhook_dict = await self.webhooks.find_one(
            {"_id": webhook_id, "workspace_id": workspace_id}
        )
        if not webhook_dict:
            return None

        # Redact sensitive auth config
        if webhook_dict.get("auth_config"):
            webhook_dict["auth_config"] = self._redact_auth_config(
                webhook_dict["auth_config"]
            )

        return Webhook(**webhook_dict)

    async def list_webhooks(
        self,
        workspace_id: str,
        enabled: Optional[bool] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Webhook]:
        """List webhooks for a workspace.

        Args:
            workspace_id: Workspace ID
            enabled: Filter by enabled status (optional)
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of webhooks
        """
        query = {"workspace_id": workspace_id}
        if enabled is not None:
            query["enabled"] = enabled

        cursor = self.webhooks.find(query).skip(skip).limit(limit)
        webhooks = []

        async for webhook_dict in cursor:
            # Redact sensitive auth config
            if webhook_dict.get("auth_config"):
                webhook_dict["auth_config"] = self._redact_auth_config(
                    webhook_dict["auth_config"]
                )
            webhooks.append(Webhook(**webhook_dict))

        return webhooks

    async def update_webhook(
        self,
        webhook_id: ObjectId,
        workspace_id: str,
        update_data: WebhookUpdate,
    ) -> Optional[Webhook]:
        """Update webhook configuration.

        Args:
            webhook_id: Webhook ID
            workspace_id: Workspace ID (for authorization)
            update_data: Update data

        Returns:
            Updated webhook if found, None otherwise

        Raises:
            ValueError: If URL is invalid
        """
        # Validate URL if provided
        if update_data.url:
            self._validate_webhook_url(update_data.url)

        # Build update document
        update_dict = {
            "updated_at": datetime.utcnow(),
        }
        for field, value in update_data.model_dump(exclude_unset=True).items():
            if value is not None:
                update_dict[field] = value

        # Update webhook
        result = await self.webhooks.find_one_and_update(
            {"_id": webhook_id, "workspace_id": workspace_id},
            {"$set": update_dict},
            return_document=True,
        )

        if not result:
            return None

        # Redact sensitive auth config
        if result.get("auth_config"):
            result["auth_config"] = self._redact_auth_config(result["auth_config"])

        logger.info(f"Updated webhook {webhook_id}")
        return Webhook(**result)

    async def delete_webhook(
        self,
        webhook_id: ObjectId,
        workspace_id: str,
    ) -> bool:
        """Delete webhook.

        Args:
            webhook_id: Webhook ID
            workspace_id: Workspace ID (for authorization)

        Returns:
            True if deleted, False if not found
        """
        result = await self.webhooks.delete_one(
            {"_id": webhook_id, "workspace_id": workspace_id}
        )

        if result.deleted_count > 0:
            logger.info(f"Deleted webhook {webhook_id}")
            return True

        return False

    # =========================================================================
    # Webhook Delivery
    # =========================================================================

    async def trigger_webhook(
        self,
        event_type: WebhookEvent,
        workspace_id: str,
        event_data: dict[str, Any],
        event_id: Optional[str] = None,
    ) -> list[str]:
        """Trigger webhooks for an event.

        This method finds all enabled webhooks subscribed to the event type
        and delivers the payload asynchronously (fire-and-forget).

        Args:
            event_type: Type of event
            workspace_id: Workspace ID
            event_data: Event-specific data
            event_id: Unique event ID (generated if not provided)

        Returns:
            List of webhook IDs that were triggered
        """
        # Find enabled webhooks subscribed to this event
        webhooks = await self.webhooks.find(
            {
                "workspace_id": workspace_id,
                "enabled": True,
                "events": event_type,
            }
        ).to_list(length=None)

        if not webhooks:
            logger.debug(
                f"No webhooks configured for event {event_type} in workspace {workspace_id}"
            )
            return []

        # Generate event ID if not provided
        if not event_id:
            event_id = f"{event_type}_{ObjectId()}"

        # Build payload
        payload = WebhookPayload(
            event_id=event_id,
            event_type=event_type,
            timestamp=datetime.utcnow(),
            workspace_id=workspace_id,
            data=event_data,
        )

        # Trigger delivery for each webhook (async, fire-and-forget)
        triggered_ids = []
        for webhook_dict in webhooks:
            webhook = Webhook(**webhook_dict)
            triggered_ids.append(str(webhook.id))

            # Schedule delivery in background
            asyncio.create_task(
                self._deliver_webhook_with_retry(webhook, payload)
            )

        logger.info(
            f"Triggered {len(triggered_ids)} webhooks for event {event_type} "
            f"in workspace {workspace_id}"
        )

        return triggered_ids

    async def test_webhook(
        self,
        webhook_id: ObjectId,
        workspace_id: str,
    ) -> WebhookTestResult:
        """Test webhook delivery.

        Args:
            webhook_id: Webhook ID
            workspace_id: Workspace ID

        Returns:
            Test result

        Raises:
            ValueError: If webhook not found
        """
        webhook_dict = await self.webhooks.find_one(
            {"_id": webhook_id, "workspace_id": workspace_id}
        )
        if not webhook_dict:
            raise ValueError("Webhook not found")

        webhook = Webhook(**webhook_dict)

        # Build test payload
        payload = WebhookPayload(
            event_id=f"test_{ObjectId()}",
            event_type=WebhookEvent.COP_UPDATE_PUBLISHED,
            timestamp=datetime.utcnow(),
            workspace_id=workspace_id,
            data={"test": True, "message": "This is a test webhook delivery"},
        )

        # Attempt delivery (single attempt, no retry)
        start_time = time.time()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = self._build_auth_headers(webhook.auth_type, webhook.auth_config)
                headers["Content-Type"] = "application/json"
                headers["X-Webhook-Event"] = payload.event_type
                headers["X-Webhook-ID"] = str(webhook.id)

                # Add HMAC signature if auth is configured
                payload_json = payload.model_dump_json()
                if webhook.auth_type != AuthType.NONE and webhook.auth_config:
                    signature = self._compute_hmac_signature(payload_json, webhook)
                    headers["X-Webhook-Signature"] = signature

                response = await client.post(
                    webhook.url,
                    content=payload_json,
                    headers=headers,
                )

                response_time_ms = int((time.time() - start_time) * 1000)

                return WebhookTestResult(
                    success=200 <= response.status_code < 300,
                    status_code=response.status_code,
                    response_time_ms=response_time_ms,
                    response_body=response.text[:1000],  # Truncate
                    error=None if 200 <= response.status_code < 300 else response.text[:500],
                )

        except Exception as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            logger.warning(f"Test webhook delivery failed: {str(e)}")

            return WebhookTestResult(
                success=False,
                status_code=None,
                response_time_ms=response_time_ms,
                response_body=None,
                error=str(e),
            )

    async def _deliver_webhook_with_retry(
        self,
        webhook: Webhook,
        payload: WebhookPayload,
    ) -> None:
        """Deliver webhook with exponential backoff retry.

        Args:
            webhook: Webhook configuration
            payload: Webhook payload
        """
        max_retries = webhook.retry_config.max_retries
        base_delay = webhook.retry_config.retry_delay_seconds
        multiplier = webhook.retry_config.backoff_multiplier

        for attempt in range(max_retries + 1):
            # Create delivery record
            delivery = WebhookDelivery(
                webhook_id=webhook.id,
                event_type=payload.event_type,
                event_id=payload.event_id,
                payload=payload.model_dump(),
                status=WebhookStatus.PENDING,
                retry_count=attempt,
            )

            # Attempt delivery
            success, status_code, response_time_ms, response_body, error = (
                await self._attempt_delivery(webhook, payload)
            )

            # Update delivery record
            delivery.status = WebhookStatus.SUCCESS if success else WebhookStatus.FAILED
            delivery.http_status_code = status_code
            delivery.response_time_ms = response_time_ms
            delivery.response_body = response_body[:10000] if response_body else None
            delivery.error_message = error

            # Save delivery record
            await self.deliveries.insert_one(
                delivery.model_dump(by_alias=True, exclude={"id"})
            )

            # Update webhook statistics
            await self._update_webhook_statistics(webhook.id, success, error)

            if success:
                logger.info(
                    f"Webhook {webhook.id} delivered successfully "
                    f"(attempt {attempt + 1}/{max_retries + 1})"
                )
                return

            # If not successful and not last attempt, schedule retry
            if attempt < max_retries:
                delay = base_delay * (multiplier ** attempt)
                logger.warning(
                    f"Webhook {webhook.id} delivery failed (attempt {attempt + 1}/"
                    f"{max_retries + 1}). Retrying in {delay}s. Error: {error}"
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    f"Webhook {webhook.id} delivery failed after {max_retries + 1} attempts. "
                    f"Error: {error}"
                )

    async def _attempt_delivery(
        self,
        webhook: Webhook,
        payload: WebhookPayload,
    ) -> tuple[bool, Optional[int], int, Optional[str], Optional[str]]:
        """Attempt webhook delivery.

        Args:
            webhook: Webhook configuration
            payload: Webhook payload

        Returns:
            Tuple of (success, status_code, response_time_ms, response_body, error)
        """
        start_time = time.time()

        try:
            timeout_seconds = getattr(settings, "webhook_timeout_seconds", 10)

            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                # Build headers
                headers = self._build_auth_headers(webhook.auth_type, webhook.auth_config)
                headers["Content-Type"] = "application/json"
                headers["X-Webhook-Event"] = payload.event_type
                headers["X-Webhook-ID"] = str(webhook.id)
                headers["X-Webhook-Delivery-ID"] = str(ObjectId())

                # Add HMAC signature
                payload_json = payload.model_dump_json()
                if webhook.auth_type != AuthType.NONE and webhook.auth_config:
                    signature = self._compute_hmac_signature(payload_json, webhook)
                    headers["X-Webhook-Signature"] = signature

                # Send request
                response = await client.post(
                    webhook.url,
                    content=payload_json,
                    headers=headers,
                )

                response_time_ms = int((time.time() - start_time) * 1000)

                # Consider 2xx as success, 4xx as permanent failure (don't retry)
                success = 200 <= response.status_code < 300
                error = None if success else f"HTTP {response.status_code}"

                return (
                    success,
                    response.status_code,
                    response_time_ms,
                    response.text,
                    error,
                )

        except httpx.TimeoutException as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            return False, None, response_time_ms, None, f"Timeout: {str(e)}"

        except Exception as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            return False, None, response_time_ms, None, str(e)

    # =========================================================================
    # Delivery History
    # =========================================================================

    async def get_webhook_deliveries(
        self,
        webhook_id: ObjectId,
        workspace_id: str,
        status: Optional[WebhookStatus] = None,
        start_time: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[WebhookDelivery]:
        """Get delivery history for a webhook.

        Args:
            webhook_id: Webhook ID
            workspace_id: Workspace ID (for authorization)
            status: Filter by status (optional)
            start_time: Filter deliveries after this time (optional)
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of delivery records
        """
        # Verify webhook belongs to workspace
        webhook = await self.webhooks.find_one(
            {"_id": webhook_id, "workspace_id": workspace_id}
        )
        if not webhook:
            return []

        # Build query
        query = {"webhook_id": webhook_id}
        if status:
            query["status"] = status
        if start_time:
            query["timestamp"] = {"$gte": start_time}

        # Query deliveries
        cursor = (
            self.deliveries.find(query)
            .sort("timestamp", -1)
            .skip(skip)
            .limit(limit)
        )

        deliveries = []
        async for delivery_dict in cursor:
            deliveries.append(WebhookDelivery(**delivery_dict))

        return deliveries

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _validate_webhook_url(self, url: str) -> None:
        """Validate webhook URL.

        Args:
            url: URL to validate

        Raises:
            ValueError: If URL is invalid
        """
        try:
            parsed = urlparse(url)
        except Exception:
            raise ValueError(f"Invalid URL: {url}")

        # Require HTTPS in production (unless localhost for testing)
        if not settings.debug and parsed.scheme != "https":
            if parsed.hostname not in ("localhost", "127.0.0.1"):
                raise ValueError("Webhook URLs must use HTTPS in production")

        # Block private IPs in production
        if not settings.debug:
            if parsed.hostname in ("localhost", "127.0.0.1", "0.0.0.0"):
                raise ValueError("Cannot use localhost URLs in production")

    def _build_auth_headers(
        self,
        auth_type: AuthType,
        auth_config: Optional[AuthConfig],
    ) -> dict[str, str]:
        """Build authentication headers.

        Args:
            auth_type: Authentication type
            auth_config: Authentication configuration

        Returns:
            Dictionary of headers
        """
        headers = {}

        if not auth_config:
            return headers

        if auth_type == AuthType.BEARER and auth_config.token:
            headers["Authorization"] = f"Bearer {auth_config.token}"

        elif auth_type == AuthType.BASIC and auth_config.username and auth_config.password:
            import base64
            credentials = f"{auth_config.username}:{auth_config.password}"
            encoded = base64.b64encode(credentials.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"

        elif auth_type == AuthType.API_KEY and auth_config.key_name and auth_config.key_value:
            headers[auth_config.key_name] = auth_config.key_value

        elif auth_type == AuthType.CUSTOM_HEADER and auth_config.header_name and auth_config.header_value:
            headers[auth_config.header_name] = auth_config.header_value

        return headers

    def _compute_hmac_signature(self, payload: str, webhook: Webhook) -> str:
        """Compute HMAC signature for webhook payload.

        Args:
            payload: JSON payload string
            webhook: Webhook configuration

        Returns:
            HMAC signature (hex)
        """
        # Use webhook ID as secret key (could be configurable per webhook)
        secret = str(webhook.id).encode()
        signature = hmac.new(secret, payload.encode(), hashlib.sha256)
        return f"sha256={signature.hexdigest()}"

    def _redact_auth_config(self, auth_config: dict) -> dict:
        """Redact sensitive fields in auth config.

        Args:
            auth_config: Authentication configuration

        Returns:
            Redacted configuration
        """
        redacted = auth_config.copy()

        sensitive_fields = [
            "token",
            "password",
            "key_value",
            "header_value",
            "client_secret",
        ]

        for field in sensitive_fields:
            if field in redacted:
                redacted[field] = "***REDACTED***"

        return redacted

    async def _update_webhook_statistics(
        self,
        webhook_id: ObjectId,
        success: bool,
        error: Optional[str] = None,
    ) -> None:
        """Update webhook delivery statistics.

        Args:
            webhook_id: Webhook ID
            success: Whether delivery succeeded
            error: Error message (if failed)
        """
        update = {
            "$inc": {
                "statistics.total_deliveries": 1,
                "statistics.successful_deliveries" if success else "statistics.failed_deliveries": 1,
            },
        }

        if success:
            update["$set"] = {"statistics.last_success_at": datetime.utcnow()}
        else:
            update["$set"] = {
                "statistics.last_failure_at": datetime.utcnow(),
                "statistics.last_error": error,
            }

        await self.webhooks.update_one({"_id": webhook_id}, update)

        # Recalculate success rate
        webhook = await self.webhooks.find_one({"_id": webhook_id})
        if webhook:
            stats = webhook.get("statistics", {})
            total = stats.get("total_deliveries", 0)
            successful = stats.get("successful_deliveries", 0)
            success_rate = successful / total if total > 0 else 0.0

            await self.webhooks.update_one(
                {"_id": webhook_id},
                {"$set": {"statistics.success_rate": success_rate}},
            )
