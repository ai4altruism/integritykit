"""External source service for inbound verification data.

Implements:
- FR-INT-003: External verification source integration
- Task S8-20: Inbound verification source API
"""

import hashlib
import logging
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection

from integritykit.config import settings
from integritykit.models.cop_candidate import COPCandidate, COPFields, COPWhen, ReadinessState, RiskTier
from integritykit.models.external_source import (
    AuthConfig,
    AuthType,
    ExternalSource,
    ExternalSourceCreate,
    ExternalSourceUpdate,
    ImportedVerification,
    ImportRequest,
    ImportResult,
    ImportStatus,
    TrustLevel,
)
from integritykit.services.database import get_collection

logger = logging.getLogger(__name__)


class ExternalSourceService:
    """Service for managing external verification sources and importing data."""

    def __init__(
        self,
        sources_collection: Optional[AsyncIOMotorCollection] = None,
        imports_collection: Optional[AsyncIOMotorCollection] = None,
        candidates_collection: Optional[AsyncIOMotorCollection] = None,
    ):
        """Initialize external source service.

        Args:
            sources_collection: MongoDB collection for external sources
            imports_collection: MongoDB collection for import records
            candidates_collection: MongoDB collection for COP candidates
        """
        self.sources = sources_collection or get_collection("external_sources")
        self.imports = imports_collection or get_collection("imported_verifications")
        self.candidates = candidates_collection or get_collection("cop_candidates")

    # =========================================================================
    # CRUD Operations
    # =========================================================================

    async def create_source(
        self,
        source_data: ExternalSourceCreate,
        workspace_id: str,
        created_by: str,
    ) -> ExternalSource:
        """Create a new external source.

        Args:
            source_data: Source creation data
            workspace_id: Workspace ID
            created_by: User ID creating the source

        Returns:
            Created external source

        Raises:
            ValueError: If source_id already exists or endpoint is invalid
        """
        # Validate endpoint URL
        self._validate_endpoint_url(source_data.api_endpoint)

        # Check for duplicate source_id in workspace
        existing = await self.sources.find_one(
            {"workspace_id": workspace_id, "source_id": source_data.source_id}
        )
        if existing:
            raise ValueError(
                f"Source with ID {source_data.source_id} already exists"
            )

        # Create source
        source = ExternalSource(
            workspace_id=workspace_id,
            created_by=created_by,
            **source_data.model_dump(exclude_unset=True),
        )

        # Insert into database
        source_dict = source.model_dump(by_alias=True, exclude={"id"})
        result = await self.sources.insert_one(source_dict)
        source.id = result.inserted_id

        logger.info(
            f"Created external source {source.id} for workspace {workspace_id}: "
            f"{source.name} (trust_level={source.trust_level})"
        )

        return source

    async def get_source(
        self,
        source_id: ObjectId,
        workspace_id: str,
    ) -> Optional[ExternalSource]:
        """Get external source by ID.

        Args:
            source_id: Source ID
            workspace_id: Workspace ID (for authorization)

        Returns:
            External source if found, None otherwise
        """
        source_dict = await self.sources.find_one(
            {"_id": source_id, "workspace_id": workspace_id}
        )
        if not source_dict:
            return None

        # Redact sensitive auth config
        if source_dict.get("auth_config"):
            source_dict["auth_config"] = self._redact_auth_config(
                source_dict["auth_config"]
            )

        return ExternalSource(**source_dict)

    async def get_source_by_source_id(
        self,
        source_id: str,
        workspace_id: str,
    ) -> Optional[ExternalSource]:
        """Get external source by source_id string.

        Args:
            source_id: Source ID string
            workspace_id: Workspace ID (for authorization)

        Returns:
            External source if found, None otherwise
        """
        source_dict = await self.sources.find_one(
            {"source_id": source_id, "workspace_id": workspace_id}
        )
        if not source_dict:
            return None

        # Redact sensitive auth config
        if source_dict.get("auth_config"):
            source_dict["auth_config"] = self._redact_auth_config(
                source_dict["auth_config"]
            )

        return ExternalSource(**source_dict)

    async def list_sources(
        self,
        workspace_id: str,
        source_type: Optional[str] = None,
        trust_level: Optional[TrustLevel] = None,
        enabled: Optional[bool] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ExternalSource]:
        """List external sources for a workspace.

        Args:
            workspace_id: Workspace ID
            source_type: Filter by source type (optional)
            trust_level: Filter by trust level (optional)
            enabled: Filter by enabled status (optional)
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of external sources
        """
        query = {"workspace_id": workspace_id}
        if source_type:
            query["source_type"] = source_type
        if trust_level:
            query["trust_level"] = trust_level
        if enabled is not None:
            query["enabled"] = enabled

        cursor = self.sources.find(query).skip(skip).limit(limit)
        sources = []

        async for source_dict in cursor:
            # Redact sensitive auth config
            if source_dict.get("auth_config"):
                source_dict["auth_config"] = self._redact_auth_config(
                    source_dict["auth_config"]
                )
            sources.append(ExternalSource(**source_dict))

        return sources

    async def update_source(
        self,
        source_id: ObjectId,
        workspace_id: str,
        update_data: ExternalSourceUpdate,
    ) -> Optional[ExternalSource]:
        """Update external source configuration.

        Args:
            source_id: Source ID
            workspace_id: Workspace ID (for authorization)
            update_data: Update data

        Returns:
            Updated source if found, None otherwise

        Raises:
            ValueError: If endpoint URL is invalid
        """
        # Validate endpoint URL if provided
        if update_data.api_endpoint:
            self._validate_endpoint_url(update_data.api_endpoint)

        # Build update document
        update_dict = {
            "updated_at": datetime.utcnow(),
        }
        for field, value in update_data.model_dump(exclude_unset=True).items():
            if value is not None:
                update_dict[field] = value

        # Update source
        result = await self.sources.find_one_and_update(
            {"_id": source_id, "workspace_id": workspace_id},
            {"$set": update_dict},
            return_document=True,
        )

        if not result:
            return None

        # Redact sensitive auth config
        if result.get("auth_config"):
            result["auth_config"] = self._redact_auth_config(result["auth_config"])

        logger.info(f"Updated external source {source_id}")
        return ExternalSource(**result)

    async def delete_source(
        self,
        source_id: ObjectId,
        workspace_id: str,
    ) -> bool:
        """Delete external source.

        Args:
            source_id: Source ID
            workspace_id: Workspace ID (for authorization)

        Returns:
            True if deleted, False if not found
        """
        result = await self.sources.delete_one(
            {"_id": source_id, "workspace_id": workspace_id}
        )

        if result.deleted_count > 0:
            logger.info(f"Deleted external source {source_id}")
            return True

        return False

    # =========================================================================
    # Import Operations
    # =========================================================================

    async def import_verified_data(
        self,
        source_id: ObjectId,
        workspace_id: str,
        import_request: ImportRequest,
        imported_by: str,
    ) -> ImportResult:
        """Import verified data from an external source.

        This method:
        1. Fetches data from the external API
        2. Transforms data to COP candidate schema
        3. Checks for duplicates
        4. Creates candidates with appropriate readiness state based on trust level
        5. Logs provenance to external source

        Args:
            source_id: External source ID
            workspace_id: Workspace ID
            import_request: Import request parameters
            imported_by: User ID triggering the import

        Returns:
            Import result with statistics

        Raises:
            ValueError: If source not found or disabled
        """
        # Get source configuration (with non-redacted auth)
        source_dict = await self.sources.find_one(
            {"_id": source_id, "workspace_id": workspace_id}
        )
        if not source_dict:
            raise ValueError("External source not found")

        source = ExternalSource(**source_dict)

        if not source.enabled:
            raise ValueError("External source is disabled")

        # Generate import job ID
        import_job_id = f"import_{ObjectId()}"

        # Initialize result
        result = ImportResult(
            import_id=import_job_id,
            status=ImportStatus.IN_PROGRESS,
            started_at=datetime.utcnow(),
        )

        try:
            # Fetch data from external API
            raw_items = await self._fetch_from_external_api(
                source=source,
                import_request=import_request,
            )

            result.items_fetched = len(raw_items)

            # Process each item
            for raw_item in raw_items:
                try:
                    # Check for duplicate
                    external_id = self._extract_external_id(raw_item)
                    if external_id and await self._is_duplicate(
                        source_id, external_id, workspace_id
                    ):
                        result.duplicates_skipped += 1
                        continue

                    # Transform to COP candidate fields
                    cop_fields = self._transform_to_cop_fields(raw_item, source)

                    # Create COP candidate based on trust level
                    candidate = await self._create_candidate_from_import(
                        workspace_id=workspace_id,
                        source=source,
                        cop_fields=cop_fields,
                        auto_promote=import_request.auto_promote,
                        imported_by=imported_by,
                    )

                    # Record import
                    import_record = ImportedVerification(
                        import_job_id=import_job_id,
                        source_id=source_id,
                        workspace_id=workspace_id,
                        external_id=external_id,
                        candidate_id=candidate.id,
                        status=ImportStatus.COMPLETED,
                        trust_level=source.trust_level,
                        raw_data=raw_item,
                        transformed_data=cop_fields.model_dump(),
                        imported_by=imported_by,
                    )
                    await self.imports.insert_one(
                        import_record.model_dump(by_alias=True, exclude={"id"})
                    )

                    result.items_imported += 1
                    result.candidates_created += 1

                except Exception as e:
                    logger.warning(f"Failed to import item: {str(e)}")
                    result.errors += 1

                    # Record failed import
                    import_record = ImportedVerification(
                        import_job_id=import_job_id,
                        source_id=source_id,
                        workspace_id=workspace_id,
                        external_id=self._extract_external_id(raw_item),
                        status=ImportStatus.FAILED,
                        trust_level=source.trust_level,
                        raw_data=raw_item,
                        error_message=str(e),
                        imported_by=imported_by,
                    )
                    await self.imports.insert_one(
                        import_record.model_dump(by_alias=True, exclude={"id"})
                    )

            # Update final status
            result.completed_at = datetime.utcnow()
            if result.errors == 0:
                result.status = ImportStatus.COMPLETED
            elif result.items_imported > 0:
                result.status = ImportStatus.PARTIAL
            else:
                result.status = ImportStatus.FAILED
                result.error_message = "No items successfully imported"

            # Update source statistics
            await self._update_source_statistics(
                source_id=source_id,
                success=result.status != ImportStatus.FAILED,
                items_imported=result.items_imported,
                duplicates_skipped=result.duplicates_skipped,
                error=result.error_message,
            )

            logger.info(
                f"Import {import_job_id} completed: "
                f"fetched={result.items_fetched}, "
                f"imported={result.items_imported}, "
                f"duplicates={result.duplicates_skipped}, "
                f"errors={result.errors}"
            )

            return result

        except Exception as e:
            logger.error(f"Import {import_job_id} failed: {str(e)}")
            result.status = ImportStatus.FAILED
            result.error_message = str(e)
            result.completed_at = datetime.utcnow()

            # Update source statistics
            await self._update_source_statistics(
                source_id=source_id,
                success=False,
                items_imported=0,
                duplicates_skipped=0,
                error=str(e),
            )

            return result

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _validate_endpoint_url(self, url: str) -> None:
        """Validate external API endpoint URL.

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
                raise ValueError("External API URLs must use HTTPS in production")

        # Block private IPs in production
        if not settings.debug:
            if parsed.hostname in ("localhost", "127.0.0.1", "0.0.0.0"):
                raise ValueError("Cannot use localhost URLs in production")

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
            "client_secret",
        ]

        for field in sensitive_fields:
            if field in redacted:
                redacted[field] = "***REDACTED***"

        return redacted

    def _build_auth_headers(
        self,
        auth_type: AuthType,
        auth_config: Optional[AuthConfig],
    ) -> dict[str, str]:
        """Build authentication headers for external API request.

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

        return headers

    async def _fetch_from_external_api(
        self,
        source: ExternalSource,
        import_request: ImportRequest,
    ) -> list[dict[str, Any]]:
        """Fetch data from external API.

        Args:
            source: External source configuration
            import_request: Import request parameters

        Returns:
            List of raw items from external API

        Raises:
            Exception: If API request fails
        """
        timeout_seconds = 30

        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            # Build headers
            headers = self._build_auth_headers(source.auth_type, source.auth_config)
            headers["Accept"] = "application/json"
            headers["User-Agent"] = "IntegrityKit/1.0"

            # Build query parameters
            params = {}
            if import_request.start_time:
                params["start_time"] = import_request.start_time.isoformat()
            if import_request.end_time:
                params["end_time"] = import_request.end_time.isoformat()
            if import_request.max_items:
                params["limit"] = import_request.max_items

            # Add custom filters
            params.update(import_request.filters)

            # Make request
            response = await client.get(
                source.api_endpoint,
                headers=headers,
                params=params,
            )

            response.raise_for_status()

            # Parse response
            data = response.json()

            # Handle different response formats
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                # Common patterns: {"items": [...]} or {"data": [...]}
                if "items" in data:
                    return data["items"]
                elif "data" in data:
                    return data["data"]
                elif "results" in data:
                    return data["results"]
                else:
                    # Single item response
                    return [data]
            else:
                raise ValueError(f"Unexpected response format: {type(data)}")

    def _extract_external_id(self, raw_item: dict[str, Any]) -> Optional[str]:
        """Extract external ID from raw item for deduplication.

        Args:
            raw_item: Raw item from external API

        Returns:
            External ID if found, None otherwise
        """
        # Try common ID field names
        for field in ["id", "external_id", "incident_id", "event_id", "uuid"]:
            if field in raw_item:
                return str(raw_item[field])
        return None

    async def _is_duplicate(
        self,
        source_id: ObjectId,
        external_id: str,
        workspace_id: str,
    ) -> bool:
        """Check if an item has already been imported.

        Args:
            source_id: External source ID
            external_id: External item ID
            workspace_id: Workspace ID

        Returns:
            True if duplicate, False otherwise
        """
        existing = await self.imports.find_one(
            {
                "source_id": source_id,
                "external_id": external_id,
                "workspace_id": workspace_id,
                "status": {"$in": [ImportStatus.COMPLETED, ImportStatus.IN_PROGRESS]},
            }
        )
        return existing is not None

    def _transform_to_cop_fields(
        self,
        raw_item: dict[str, Any],
        source: ExternalSource,
    ) -> COPFields:
        """Transform raw external data to COP fields.

        This is a basic transformation. In production, this would be
        customized per source type with configurable field mappings.

        Args:
            raw_item: Raw item from external API
            source: External source configuration

        Returns:
            Transformed COP fields
        """
        # Extract common fields with fallbacks
        what = raw_item.get("what") or raw_item.get("description") or raw_item.get("summary") or ""
        where = raw_item.get("where") or raw_item.get("location") or raw_item.get("address") or ""
        who = raw_item.get("who") or raw_item.get("affected") or raw_item.get("reporter") or ""
        so_what = raw_item.get("so_what") or raw_item.get("impact") or raw_item.get("implications") or ""

        # Extract temporal information
        when_timestamp = None
        when_desc = raw_item.get("when", "")

        if "timestamp" in raw_item:
            try:
                when_timestamp = datetime.fromisoformat(str(raw_item["timestamp"]))
            except Exception:
                pass

        when = COPWhen(
            timestamp=when_timestamp,
            description=when_desc,
            is_approximate=when_timestamp is None,
        )

        return COPFields(
            what=what,
            where=where,
            when=when,
            who=who,
            so_what=so_what,
        )

    async def _create_candidate_from_import(
        self,
        workspace_id: str,
        source: ExternalSource,
        cop_fields: COPFields,
        auto_promote: bool,
        imported_by: str,
    ) -> COPCandidate:
        """Create a COP candidate from imported data.

        Applies trust level rules:
        - HIGH: verified (if auto_promote=True)
        - MEDIUM: in_review
        - LOW: in_review (requires full verification)

        Args:
            workspace_id: Workspace ID
            source: External source
            cop_fields: Transformed COP fields
            auto_promote: Whether to auto-promote based on trust level
            imported_by: User ID triggering import

        Returns:
            Created COP candidate
        """
        # Determine readiness state based on trust level
        if auto_promote and source.trust_level == TrustLevel.HIGH:
            readiness_state = ReadinessState.VERIFIED
        else:
            readiness_state = ReadinessState.IN_REVIEW

        # Create candidate
        candidate = COPCandidate(
            cluster_id=ObjectId(),  # No cluster for external imports
            primary_signal_ids=[],  # No signals for external imports
            readiness_state=readiness_state,
            risk_tier=RiskTier.ROUTINE,  # Default, can be overridden
            fields=cop_fields,
            created_by=ObjectId(imported_by),
        )

        # Add metadata indicating external source
        candidate_dict = candidate.model_dump(by_alias=True, exclude={"id"})
        candidate_dict["source_type"] = "external_verified"
        candidate_dict["external_source_id"] = source.id
        candidate_dict["external_source_name"] = source.name

        # Insert into database
        result = await self.candidates.insert_one(candidate_dict)
        candidate.id = result.inserted_id

        logger.info(
            f"Created COP candidate {candidate.id} from external source {source.id} "
            f"(trust_level={source.trust_level}, readiness_state={readiness_state})"
        )

        return candidate

    async def _update_source_statistics(
        self,
        source_id: ObjectId,
        success: bool,
        items_imported: int,
        duplicates_skipped: int,
        error: Optional[str] = None,
    ) -> None:
        """Update external source statistics.

        Args:
            source_id: External source ID
            success: Whether sync succeeded
            items_imported: Number of items imported
            duplicates_skipped: Number of duplicates skipped
            error: Error message (if failed)
        """
        update = {
            "$inc": {
                "statistics.total_syncs": 1,
                "statistics.successful_syncs" if success else "statistics.failed_syncs": 1,
                "statistics.total_items_imported": items_imported,
                "statistics.duplicates_skipped": duplicates_skipped,
            },
            "$set": {
                "statistics.last_sync_at": datetime.utcnow(),
            },
        }

        if success:
            update["$set"]["statistics.last_success_at"] = datetime.utcnow()
        else:
            update["$set"]["statistics.last_failure_at"] = datetime.utcnow()
            if error:
                update["$set"]["statistics.last_error"] = error

        await self.sources.update_one({"_id": source_id}, update)
