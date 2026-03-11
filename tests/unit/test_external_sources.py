"""
Unit tests for external verification source functionality.

Tests:
- FR-INT-003: External verification source integration
- Task S8-20: Inbound verification source API
"""

import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

# Set required environment variables before importing config
os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test-token")
os.environ.setdefault("SLACK_SIGNING_SECRET", "test-secret")
os.environ.setdefault("SLACK_WORKSPACE_ID", "T123TEST")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-key")

from integritykit.models.cop_candidate import COPCandidate, ReadinessState
from integritykit.models.external_source import (
    AuthConfig,
    AuthType,
    ExternalSource,
    ExternalSourceCreate,
    ExternalSourceUpdate,
    ImportRequest,
    ImportResult,
    ImportStatus,
    SourceType,
    TrustLevel,
)
from integritykit.services.external_sources import ExternalSourceService


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_sources_collection():
    """Mock MongoDB sources collection."""
    return AsyncMock()


@pytest.fixture
def mock_imports_collection():
    """Mock MongoDB imports collection."""
    return AsyncMock()


@pytest.fixture
def mock_candidates_collection():
    """Mock MongoDB candidates collection."""
    return AsyncMock()


@pytest.fixture
def external_source_service(
    mock_sources_collection,
    mock_imports_collection,
    mock_candidates_collection,
):
    """Create ExternalSourceService with mocked collections."""
    return ExternalSourceService(
        sources_collection=mock_sources_collection,
        imports_collection=mock_imports_collection,
        candidates_collection=mock_candidates_collection,
    )


@pytest.fixture
def sample_source_data():
    """Sample external source creation data."""
    return ExternalSourceCreate(
        source_id="fema-api",
        name="FEMA Incident API",
        description="Official FEMA incident reports",
        source_type=SourceType.GOVERNMENT_API,
        api_endpoint="https://api.fema.gov/incidents",
        auth_type=AuthType.BEARER,
        auth_config=AuthConfig(token="test_token_123"),
        trust_level=TrustLevel.HIGH,
        sync_interval_minutes=60,
        enabled=True,
    )


@pytest.fixture
def sample_external_source():
    """Sample external source instance."""
    return ExternalSource(
        id=ObjectId(),
        workspace_id="workspace-123",
        source_id="fema-api",
        name="FEMA Incident API",
        description="Official FEMA incident reports",
        source_type=SourceType.GOVERNMENT_API,
        api_endpoint="https://api.fema.gov/incidents",
        auth_type=AuthType.BEARER,
        auth_config=AuthConfig(token="test_token_123"),
        trust_level=TrustLevel.HIGH,
        sync_interval_minutes=60,
        enabled=True,
        created_by="user-123",
    )


# ============================================================================
# CRUD Operation Tests
# ============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
class TestExternalSourceCRUD:
    """Test CRUD operations for external sources."""

    async def test_create_source(
        self,
        external_source_service,
        mock_sources_collection,
        sample_source_data,
    ):
        """Create a new external source."""
        # Mock database operations
        mock_sources_collection.find_one.return_value = None  # No duplicate
        mock_sources_collection.insert_one.return_value = MagicMock(
            inserted_id=ObjectId()
        )

        # Create source
        source = await external_source_service.create_source(
            source_data=sample_source_data,
            workspace_id="workspace-123",
            created_by="user-123",
        )

        # Verify source created
        assert source.source_id == "fema-api"
        assert source.name == "FEMA Incident API"
        assert source.trust_level == TrustLevel.HIGH
        assert source.workspace_id == "workspace-123"
        assert source.created_by == "user-123"

        # Verify database calls
        mock_sources_collection.find_one.assert_called_once()
        mock_sources_collection.insert_one.assert_called_once()

    async def test_create_source_duplicate_source_id(
        self,
        external_source_service,
        mock_sources_collection,
        sample_source_data,
    ):
        """Cannot create source with duplicate source_id."""
        # Mock existing source
        mock_sources_collection.find_one.return_value = {
            "source_id": "fema-api",
            "workspace_id": "workspace-123",
        }

        # Attempt to create duplicate
        with pytest.raises(ValueError, match="already exists"):
            await external_source_service.create_source(
                source_data=sample_source_data,
                workspace_id="workspace-123",
                created_by="user-123",
            )

    async def test_create_source_invalid_url(
        self,
        external_source_service,
        sample_source_data,
    ):
        """Cannot create source with invalid URL."""
        # Modify to use HTTP in production mode
        sample_source_data.api_endpoint = "http://insecure.example.com"

        with patch("integritykit.services.external_sources.settings") as mock_settings:
            mock_settings.debug = False

            with pytest.raises(ValueError, match="must use HTTPS"):
                await external_source_service.create_source(
                    source_data=sample_source_data,
                    workspace_id="workspace-123",
                    created_by="user-123",
                )

    async def test_get_source(
        self,
        external_source_service,
        mock_sources_collection,
        sample_external_source,
    ):
        """Get external source by ID."""
        # Mock database query
        source_dict = sample_external_source.model_dump(by_alias=True)
        mock_sources_collection.find_one.return_value = source_dict

        # Get source
        source = await external_source_service.get_source(
            source_id=sample_external_source.id,
            workspace_id="workspace-123",
        )

        # Verify source retrieved
        assert source is not None
        assert source.source_id == "fema-api"
        # Auth config should be redacted
        assert source.auth_config.token == "***REDACTED***"

    async def test_get_source_not_found(
        self,
        external_source_service,
        mock_sources_collection,
    ):
        """Get source returns None if not found."""
        mock_sources_collection.find_one.return_value = None

        source = await external_source_service.get_source(
            source_id=ObjectId(),
            workspace_id="workspace-123",
        )

        assert source is None

    async def test_list_sources(
        self,
        external_source_service,
        mock_sources_collection,
        sample_external_source,
    ):
        """List external sources for workspace."""
        # Mock database query
        source_dict = sample_external_source.model_dump(by_alias=True)

        # Create async iterator for cursor
        async def async_iter():
            yield source_dict

        # Create mock cursor that supports chaining
        mock_cursor = MagicMock()
        mock_cursor.__aiter__ = lambda _: async_iter()
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor

        # Mock find() to return the cursor directly (not a coroutine)
        mock_sources_collection.find = MagicMock(return_value=mock_cursor)

        # List sources
        sources = await external_source_service.list_sources(
            workspace_id="workspace-123",
            skip=0,
            limit=50,
        )

        # Verify sources returned
        assert len(sources) == 1
        assert sources[0].source_id == "fema-api"

    async def test_list_sources_with_filters(
        self,
        external_source_service,
        mock_sources_collection,
    ):
        """List sources with filters."""
        # Create empty async iterator
        async def async_iter():
            return
            yield  # Make it a generator

        # Create mock cursor that supports chaining
        mock_cursor = MagicMock()
        mock_cursor.__aiter__ = lambda _: async_iter()
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor

        # Mock find() to return the cursor directly (not a coroutine)
        mock_sources_collection.find = MagicMock(return_value=mock_cursor)

        # List with filters
        await external_source_service.list_sources(
            workspace_id="workspace-123",
            source_type=SourceType.GOVERNMENT_API.value,
            trust_level=TrustLevel.HIGH,
            enabled=True,
            skip=0,
            limit=10,
        )

        # Verify query includes filters
        call_args = mock_sources_collection.find.call_args[0][0]
        assert call_args["workspace_id"] == "workspace-123"
        assert call_args["source_type"] == SourceType.GOVERNMENT_API.value
        assert call_args["trust_level"] == TrustLevel.HIGH
        assert call_args["enabled"] is True

    async def test_update_source(
        self,
        external_source_service,
        mock_sources_collection,
        sample_external_source,
    ):
        """Update external source configuration."""
        update_data = ExternalSourceUpdate(
            name="Updated FEMA API",
            enabled=False,
        )

        # Mock database update
        updated_dict = sample_external_source.model_dump(by_alias=True)
        updated_dict["name"] = "Updated FEMA API"
        updated_dict["enabled"] = False
        mock_sources_collection.find_one_and_update.return_value = updated_dict

        # Update source
        source = await external_source_service.update_source(
            source_id=sample_external_source.id,
            workspace_id="workspace-123",
            update_data=update_data,
        )

        # Verify update
        assert source is not None
        assert source.name == "Updated FEMA API"
        assert source.enabled is False

    async def test_delete_source(
        self,
        external_source_service,
        mock_sources_collection,
    ):
        """Delete external source."""
        mock_sources_collection.delete_one.return_value = MagicMock(deleted_count=1)

        deleted = await external_source_service.delete_source(
            source_id=ObjectId(),
            workspace_id="workspace-123",
        )

        assert deleted is True
        mock_sources_collection.delete_one.assert_called_once()


# ============================================================================
# Import Operation Tests
# ============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
class TestExternalSourceImport:
    """Test import operations."""

    async def test_import_verified_data_high_trust(
        self,
        external_source_service,
        mock_sources_collection,
        mock_imports_collection,
        mock_candidates_collection,
        sample_external_source,
    ):
        """Import data from high-trust source creates verified candidate."""
        # Mock source lookup
        source_dict = sample_external_source.model_dump(by_alias=True)
        mock_sources_collection.find_one.return_value = source_dict

        # Mock external API response
        mock_api_data = [
            {
                "id": "ext-001",
                "what": "Shelter Alpha closure",
                "where": "123 Main St",
                "when": "2026-03-10T14:00:00Z",
                "who": "Emergency Management",
                "so_what": "Redirecting to Shelter Bravo",
            }
        ]

        # Mock database operations
        mock_imports_collection.find_one.return_value = None  # Not duplicate
        mock_imports_collection.insert_one.return_value = MagicMock()
        mock_candidates_collection.insert_one.return_value = MagicMock(
            inserted_id=ObjectId()
        )
        mock_sources_collection.update_one.return_value = MagicMock()

        # Mock HTTP request
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json = MagicMock(return_value=mock_api_data)
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()

            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=mock_context)
            mock_context.__aexit__ = AsyncMock()
            mock_context.get = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_context

            # Import data
            result = await external_source_service.import_verified_data(
                source_id=sample_external_source.id,
                workspace_id="workspace-123",
                import_request=ImportRequest(auto_promote=True),
                imported_by="user-123",
            )

        # Verify import results
        assert result.status == ImportStatus.COMPLETED
        assert result.items_fetched == 1
        assert result.items_imported == 1
        assert result.candidates_created == 1
        assert result.errors == 0

        # Verify candidate was created
        mock_candidates_collection.insert_one.assert_called_once()

        # Verify candidate has correct readiness state (high trust + auto_promote)
        candidate_dict = mock_candidates_collection.insert_one.call_args[0][0]
        assert candidate_dict["readiness_state"] == ReadinessState.VERIFIED.value

    async def test_import_verified_data_medium_trust(
        self,
        external_source_service,
        mock_sources_collection,
        mock_imports_collection,
        mock_candidates_collection,
    ):
        """Import from medium-trust source creates in-review candidate."""
        # Create medium-trust source
        medium_source = ExternalSource(
            id=ObjectId(),
            workspace_id="workspace-123",
            source_id="ngo-feed",
            name="NGO Feed",
            description="NGO verified reports",
            source_type=SourceType.NGO_FEED,
            api_endpoint="https://api.ngo.org/reports",
            auth_type=AuthType.BEARER,
            auth_config=AuthConfig(token="ngo_token"),
            trust_level=TrustLevel.MEDIUM,
            sync_interval_minutes=60,
            enabled=True,
            created_by="user-123",
        )

        # Mock source lookup
        source_dict = medium_source.model_dump(by_alias=True)
        mock_sources_collection.find_one.return_value = source_dict

        # Mock API data
        mock_api_data = [{"id": "ngo-001", "what": "Supply shortage"}]

        # Mock database operations
        mock_imports_collection.find_one.return_value = None
        mock_imports_collection.insert_one.return_value = MagicMock()
        mock_candidates_collection.insert_one.return_value = MagicMock(
            inserted_id=ObjectId()
        )
        mock_sources_collection.update_one.return_value = MagicMock()

        # Mock HTTP request
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json = MagicMock(return_value=mock_api_data)
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()

            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=mock_context)
            mock_context.__aexit__ = AsyncMock()
            mock_context.get = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_context

            # Import data (no auto_promote)
            result = await external_source_service.import_verified_data(
                source_id=medium_source.id,
                workspace_id="workspace-123",
                import_request=ImportRequest(auto_promote=False),
                imported_by="user-123",
            )

        # Verify candidate has in_review state (medium trust)
        candidate_dict = mock_candidates_collection.insert_one.call_args[0][0]
        assert candidate_dict["readiness_state"] == ReadinessState.IN_REVIEW.value

    async def test_import_skips_duplicates(
        self,
        external_source_service,
        mock_sources_collection,
        mock_imports_collection,
        mock_candidates_collection,
        sample_external_source,
    ):
        """Import skips duplicate items."""
        # Mock source lookup
        source_dict = sample_external_source.model_dump(by_alias=True)
        mock_sources_collection.find_one.return_value = source_dict

        # Mock API data with duplicate
        mock_api_data = [
            {"id": "ext-001", "what": "Incident 1"},
            {"id": "ext-002", "what": "Incident 2"},
        ]

        # Mock duplicate check - first is duplicate, second is new
        mock_imports_collection.find_one.side_effect = [
            {"external_id": "ext-001"},  # Duplicate
            None,  # Not duplicate
        ]
        mock_imports_collection.insert_one.return_value = MagicMock()
        mock_candidates_collection.insert_one.return_value = MagicMock(
            inserted_id=ObjectId()
        )
        mock_sources_collection.update_one.return_value = MagicMock()

        # Mock HTTP request
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json = MagicMock(return_value=mock_api_data)
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()

            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=mock_context)
            mock_context.__aexit__ = AsyncMock()
            mock_context.get = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_context

            # Import data
            result = await external_source_service.import_verified_data(
                source_id=sample_external_source.id,
                workspace_id="workspace-123",
                import_request=ImportRequest(),
                imported_by="user-123",
            )

        # Verify results
        assert result.items_fetched == 2
        assert result.duplicates_skipped == 1
        assert result.items_imported == 1

    async def test_import_source_not_found(
        self,
        external_source_service,
        mock_sources_collection,
    ):
        """Import fails if source not found."""
        mock_sources_collection.find_one.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await external_source_service.import_verified_data(
                source_id=ObjectId(),
                workspace_id="workspace-123",
                import_request=ImportRequest(),
                imported_by="user-123",
            )

    async def test_import_source_disabled(
        self,
        external_source_service,
        mock_sources_collection,
        sample_external_source,
    ):
        """Import fails if source is disabled."""
        # Mock disabled source
        sample_external_source.enabled = False
        source_dict = sample_external_source.model_dump(by_alias=True)
        mock_sources_collection.find_one.return_value = source_dict

        with pytest.raises(ValueError, match="disabled"):
            await external_source_service.import_verified_data(
                source_id=sample_external_source.id,
                workspace_id="workspace-123",
                import_request=ImportRequest(),
                imported_by="user-123",
            )


# ============================================================================
# Helper Method Tests
# ============================================================================


@pytest.mark.unit
class TestHelperMethods:
    """Test helper methods."""

    def test_validate_endpoint_url_https(self, external_source_service):
        """Valid HTTPS URL passes validation."""
        # Should not raise
        external_source_service._validate_endpoint_url("https://api.example.com")

    def test_validate_endpoint_url_http_debug(self, external_source_service):
        """HTTP URL allowed in debug mode."""
        with patch("integritykit.services.external_sources.settings") as mock_settings:
            mock_settings.debug = True
            # Should not raise
            external_source_service._validate_endpoint_url("http://localhost:8000")

    def test_validate_endpoint_url_http_production(self, external_source_service):
        """HTTP URL rejected in production."""
        with patch("integritykit.services.external_sources.settings") as mock_settings:
            mock_settings.debug = False
            with pytest.raises(ValueError, match="must use HTTPS"):
                external_source_service._validate_endpoint_url(
                    "http://api.example.com"
                )

    def test_redact_auth_config(self, external_source_service):
        """Sensitive fields are redacted."""
        auth_config = {
            "token": "secret_token",
            "password": "secret_pass",
            "username": "user123",
        }

        redacted = external_source_service._redact_auth_config(auth_config)

        assert redacted["token"] == "***REDACTED***"
        assert redacted["password"] == "***REDACTED***"
        assert redacted["username"] == "user123"  # Not sensitive

    def test_build_auth_headers_bearer(self, external_source_service):
        """Build bearer token auth headers."""
        auth_config = AuthConfig(token="test_token")

        headers = external_source_service._build_auth_headers(
            AuthType.BEARER, auth_config
        )

        assert headers["Authorization"] == "Bearer test_token"

    def test_build_auth_headers_api_key(self, external_source_service):
        """Build API key auth headers."""
        auth_config = AuthConfig(key_name="X-API-Key", key_value="api_key_123")

        headers = external_source_service._build_auth_headers(
            AuthType.API_KEY, auth_config
        )

        assert headers["X-API-Key"] == "api_key_123"

    def test_extract_external_id(self, external_source_service):
        """Extract external ID from various formats."""
        # Standard id field
        assert external_source_service._extract_external_id({"id": "123"}) == "123"

        # Alternative field names
        assert (
            external_source_service._extract_external_id({"incident_id": "456"})
            == "456"
        )
        assert (
            external_source_service._extract_external_id({"external_id": "789"})
            == "789"
        )

        # No ID field
        assert external_source_service._extract_external_id({"name": "test"}) is None
