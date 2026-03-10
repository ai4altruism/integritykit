"""Unit tests for embedding service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from bson import ObjectId
from datetime import datetime

from integritykit.models.signal import Signal
from integritykit.services.embedding import EmbeddingService


@pytest.fixture
def mock_openai_client():
    """Provide mock OpenAI client."""
    mock = MagicMock()
    mock.embeddings.create = AsyncMock()
    return mock


@pytest.fixture
def mock_chroma_client():
    """Provide mock ChromaDB client."""
    mock = MagicMock()
    mock.get_or_create_collection = MagicMock()
    return mock


@pytest.fixture
def mock_collection():
    """Provide mock ChromaDB collection."""
    mock = MagicMock()
    mock.add = MagicMock()
    mock.query = MagicMock()
    mock.get = MagicMock()
    mock.delete = MagicMock()
    return mock


@pytest.fixture
def sample_signal():
    """Provide sample signal for testing."""
    return Signal(
        id=ObjectId(),
        slack_workspace_id="T01TEST",
        slack_channel_id="C01TEST",
        slack_message_ts="1234567890.123456",
        slack_user_id="U01TEST",
        slack_permalink="https://test.slack.com/archives/C01TEST/p1234567890123456",
        content="Shelter Alpha is closing at 6pm due to power outage",
        created_at=datetime(2024, 1, 1, 12, 0, 0),
    )


@pytest.fixture
def sample_embedding():
    """Provide sample embedding vector."""
    return [0.1] * 1536


@pytest.mark.unit
class TestEmbeddingServiceConstructor:
    """Test EmbeddingService initialization."""

    @patch("integritykit.services.embedding.chromadb.HttpClient")
    @patch("integritykit.services.embedding.AsyncOpenAI")
    def test_constructor_creates_http_client(self, mock_openai, mock_http_client):
        """Test constructor creates HTTP client when use_persistent=False."""
        # Execute
        service = EmbeddingService(
            openai_api_key="test-key",
            chromadb_host="test-host",
            chromadb_port=9000,
            embedding_model="text-embedding-3-small",
            use_persistent=False,
        )

        # Verify
        mock_openai.assert_called_once_with(api_key="test-key")
        mock_http_client.assert_called_once_with(host="test-host", port=9000)
        assert service.embedding_model == "text-embedding-3-small"

    @patch("integritykit.services.embedding.chromadb.PersistentClient")
    @patch("integritykit.services.embedding.AsyncOpenAI")
    def test_constructor_creates_persistent_client(
        self, mock_openai, mock_persistent_client
    ):
        """Test constructor creates PersistentClient when use_persistent=True."""
        # Execute
        service = EmbeddingService(
            openai_api_key="test-key",
            use_persistent=True,
            persist_directory="/tmp/test",
        )

        # Verify
        mock_openai.assert_called_once_with(api_key="test-key")
        mock_persistent_client.assert_called_once_with(path="/tmp/test")

    @patch("integritykit.services.embedding.AsyncOpenAI")
    def test_constructor_raises_error_without_persist_directory(self, mock_openai):
        """Test constructor raises ValueError when use_persistent=True without persist_directory."""
        # Execute & Verify
        with pytest.raises(
            ValueError, match="persist_directory required when use_persistent=True"
        ):
            EmbeddingService(
                openai_api_key="test-key",
                use_persistent=True,
                persist_directory=None,
            )

    @patch("integritykit.services.embedding.chromadb.HttpClient")
    @patch("integritykit.services.embedding.AsyncOpenAI")
    def test_constructor_default_values(self, mock_openai, mock_http_client):
        """Test constructor uses default values for optional parameters."""
        # Execute
        service = EmbeddingService(openai_api_key="test-key")

        # Verify defaults
        mock_http_client.assert_called_once_with(host="localhost", port=8000)
        assert service.embedding_model == "text-embedding-3-small"


@pytest.mark.unit
class TestCreateCollection:
    """Test ChromaDB collection creation."""

    @pytest.mark.asyncio
    async def test_create_collection_success(
        self, mock_chroma_client, mock_collection
    ):
        """Test creating collection successfully."""
        # Setup mocks
        mock_chroma_client.get_or_create_collection = MagicMock(
            return_value=mock_collection
        )

        with patch("integritykit.services.embedding.chromadb.HttpClient") as mock_http:
            mock_http.return_value = mock_chroma_client
            with patch("integritykit.services.embedding.AsyncOpenAI"):
                service = EmbeddingService(openai_api_key="test-key")

                # Execute
                result = await service.create_collection("test-collection")

                # Verify
                assert result == mock_collection
                mock_chroma_client.get_or_create_collection.assert_called_once_with(
                    name="test-collection",
                    metadata={"hnsw:space": "cosine"},
                )

    @pytest.mark.asyncio
    async def test_create_collection_error(self, mock_chroma_client):
        """Test create collection handles errors."""
        # Setup mocks
        mock_chroma_client.get_or_create_collection = MagicMock(
            side_effect=Exception("ChromaDB connection error")
        )

        with patch("integritykit.services.embedding.chromadb.HttpClient") as mock_http:
            mock_http.return_value = mock_chroma_client
            with patch("integritykit.services.embedding.AsyncOpenAI"):
                service = EmbeddingService(openai_api_key="test-key")

                # Execute & Verify
                with pytest.raises(Exception, match="ChromaDB connection error"):
                    await service.create_collection("test-collection")


@pytest.mark.unit
class TestAddSignal:
    """Test adding signal embeddings."""

    @pytest.mark.asyncio
    async def test_add_signal_success(
        self, sample_signal, sample_embedding, mock_collection
    ):
        """Test successfully adding signal with embedding."""
        # Setup mocks
        mock_embedding_response = Mock()
        mock_embedding_response.data = [Mock(embedding=sample_embedding)]

        with patch("integritykit.services.embedding.chromadb.HttpClient"):
            with patch("integritykit.services.embedding.AsyncOpenAI") as mock_openai:
                mock_client = MagicMock()
                mock_client.embeddings.create = AsyncMock(
                    return_value=mock_embedding_response
                )
                mock_openai.return_value = mock_client

                service = EmbeddingService(openai_api_key="test-key")
                service.create_collection = AsyncMock(return_value=mock_collection)

                # Execute
                result = await service.add_signal(sample_signal, "test-collection")

                # Verify
                assert result == str(sample_signal.id)

                # Verify OpenAI was called
                mock_client.embeddings.create.assert_called_once_with(
                    model="text-embedding-3-small",
                    input=sample_signal.content,
                )

                # Verify collection.add was called with correct data
                mock_collection.add.assert_called_once()
                call_args = mock_collection.add.call_args
                assert call_args[1]["ids"] == [str(sample_signal.id)]
                assert call_args[1]["embeddings"] == [sample_embedding]
                assert call_args[1]["documents"] == [sample_signal.content]

                # Verify metadata
                metadata = call_args[1]["metadatas"][0]
                assert metadata["slack_workspace_id"] == "T01TEST"
                assert metadata["slack_channel_id"] == "C01TEST"
                assert metadata["slack_message_ts"] == "1234567890.123456"
                assert metadata["created_at"] == "2024-01-01T12:00:00"
                assert metadata["ai_generated"] is True
                assert metadata["embedding_model"] == "text-embedding-3-small"
                assert "generated_at" in metadata

    @pytest.mark.asyncio
    async def test_add_signal_without_id_raises_error(self):
        """Test adding signal without ID raises ValueError."""
        signal_without_id = Signal(
            slack_workspace_id="T01TEST",
            slack_channel_id="C01TEST",
            slack_message_ts="1234567890.123456",
            slack_user_id="U01TEST",
            slack_permalink="https://test.slack.com",
            content="Test content",
        )

        with patch("integritykit.services.embedding.chromadb.HttpClient"):
            with patch("integritykit.services.embedding.AsyncOpenAI"):
                service = EmbeddingService(openai_api_key="test-key")

                # Execute & Verify
                with pytest.raises(ValueError, match="Signal must have an ID"):
                    await service.add_signal(signal_without_id)

    @pytest.mark.asyncio
    async def test_add_signal_openai_error(self, sample_signal):
        """Test add signal handles OpenAI errors."""
        with patch("integritykit.services.embedding.chromadb.HttpClient"):
            with patch("integritykit.services.embedding.AsyncOpenAI") as mock_openai:
                mock_client = MagicMock()
                mock_client.embeddings.create = AsyncMock(
                    side_effect=Exception("OpenAI API error")
                )
                mock_openai.return_value = mock_client

                service = EmbeddingService(openai_api_key="test-key")

                # Execute & Verify
                with pytest.raises(Exception, match="OpenAI API error"):
                    await service.add_signal(sample_signal)

    @pytest.mark.asyncio
    async def test_add_signal_chromadb_error(
        self, sample_signal, sample_embedding, mock_collection
    ):
        """Test add signal handles ChromaDB errors."""
        # Setup mocks
        mock_embedding_response = Mock()
        mock_embedding_response.data = [Mock(embedding=sample_embedding)]

        mock_collection.add = MagicMock(side_effect=Exception("ChromaDB add error"))

        with patch("integritykit.services.embedding.chromadb.HttpClient"):
            with patch("integritykit.services.embedding.AsyncOpenAI") as mock_openai:
                mock_client = MagicMock()
                mock_client.embeddings.create = AsyncMock(
                    return_value=mock_embedding_response
                )
                mock_openai.return_value = mock_client

                service = EmbeddingService(openai_api_key="test-key")
                service.create_collection = AsyncMock(return_value=mock_collection)

                # Execute & Verify
                with pytest.raises(Exception, match="ChromaDB add error"):
                    await service.add_signal(sample_signal)

    @pytest.mark.asyncio
    async def test_add_signal_uses_custom_collection_name(
        self, sample_signal, sample_embedding, mock_collection
    ):
        """Test add signal uses custom collection name."""
        # Setup mocks
        mock_embedding_response = Mock()
        mock_embedding_response.data = [Mock(embedding=sample_embedding)]

        with patch("integritykit.services.embedding.chromadb.HttpClient"):
            with patch("integritykit.services.embedding.AsyncOpenAI") as mock_openai:
                mock_client = MagicMock()
                mock_client.embeddings.create = AsyncMock(
                    return_value=mock_embedding_response
                )
                mock_openai.return_value = mock_client

                service = EmbeddingService(openai_api_key="test-key")
                service.create_collection = AsyncMock(return_value=mock_collection)

                # Execute
                await service.add_signal(sample_signal, "custom-collection")

                # Verify
                service.create_collection.assert_called_once_with("custom-collection")


@pytest.mark.unit
class TestFindSimilar:
    """Test finding similar signals."""

    @pytest.mark.asyncio
    async def test_find_similar_success(self, sample_embedding, mock_collection):
        """Test finding similar signals returns results with similarity scores."""
        # Setup mocks
        mock_embedding_response = Mock()
        mock_embedding_response.data = [Mock(embedding=sample_embedding)]

        signal_id_1 = str(ObjectId())
        signal_id_2 = str(ObjectId())

        mock_collection.query = MagicMock(
            return_value={
                "ids": [[signal_id_1, signal_id_2]],
                "distances": [[0.1, 0.25]],
            }
        )

        with patch("integritykit.services.embedding.chromadb.HttpClient"):
            with patch("integritykit.services.embedding.AsyncOpenAI") as mock_openai:
                mock_client = MagicMock()
                mock_client.embeddings.create = AsyncMock(
                    return_value=mock_embedding_response
                )
                mock_openai.return_value = mock_client

                service = EmbeddingService(openai_api_key="test-key")
                service.create_collection = AsyncMock(return_value=mock_collection)

                # Execute
                results = await service.find_similar(
                    text="test query", n=5, collection_name="test-collection"
                )

                # Verify
                assert len(results) == 2
                assert results[0] == (signal_id_1, 0.9)  # 1 - 0.1 = 0.9
                assert results[1] == (signal_id_2, 0.75)  # 1 - 0.25 = 0.75

                # Verify OpenAI was called
                mock_client.embeddings.create.assert_called_once_with(
                    model="text-embedding-3-small",
                    input="test query",
                )

                # Verify ChromaDB query was called
                mock_collection.query.assert_called_once_with(
                    query_embeddings=[sample_embedding],
                    n_results=5,
                    where=None,
                )

    @pytest.mark.asyncio
    async def test_find_similar_with_workspace_filter(
        self, sample_embedding, mock_collection
    ):
        """Test find similar with workspace ID filter."""
        # Setup mocks
        mock_embedding_response = Mock()
        mock_embedding_response.data = [Mock(embedding=sample_embedding)]

        mock_collection.query = MagicMock(
            return_value={
                "ids": [[str(ObjectId())]],
                "distances": [[0.15]],
            }
        )

        with patch("integritykit.services.embedding.chromadb.HttpClient"):
            with patch("integritykit.services.embedding.AsyncOpenAI") as mock_openai:
                mock_client = MagicMock()
                mock_client.embeddings.create = AsyncMock(
                    return_value=mock_embedding_response
                )
                mock_openai.return_value = mock_client

                service = EmbeddingService(openai_api_key="test-key")
                service.create_collection = AsyncMock(return_value=mock_collection)

                # Execute
                await service.find_similar(
                    text="test query",
                    n=10,
                    collection_name="test-collection",
                    workspace_id="T01WORKSPACE",
                )

                # Verify workspace filter was applied
                mock_collection.query.assert_called_once_with(
                    query_embeddings=[sample_embedding],
                    n_results=10,
                    where={"slack_workspace_id": "T01WORKSPACE"},
                )

    @pytest.mark.asyncio
    async def test_find_similar_empty_results(self, sample_embedding, mock_collection):
        """Test find similar returns empty list when no results."""
        # Setup mocks
        mock_embedding_response = Mock()
        mock_embedding_response.data = [Mock(embedding=sample_embedding)]

        mock_collection.query = MagicMock(
            return_value={
                "ids": [[]],
                "distances": [[]],
            }
        )

        with patch("integritykit.services.embedding.chromadb.HttpClient"):
            with patch("integritykit.services.embedding.AsyncOpenAI") as mock_openai:
                mock_client = MagicMock()
                mock_client.embeddings.create = AsyncMock(
                    return_value=mock_embedding_response
                )
                mock_openai.return_value = mock_client

                service = EmbeddingService(openai_api_key="test-key")
                service.create_collection = AsyncMock(return_value=mock_collection)

                # Execute
                results = await service.find_similar(text="test query")

                # Verify
                assert results == []

    @pytest.mark.asyncio
    async def test_find_similar_none_results(self, sample_embedding, mock_collection):
        """Test find similar handles None in results."""
        # Setup mocks
        mock_embedding_response = Mock()
        mock_embedding_response.data = [Mock(embedding=sample_embedding)]

        mock_collection.query = MagicMock(
            return_value={
                "ids": None,
                "distances": None,
            }
        )

        with patch("integritykit.services.embedding.chromadb.HttpClient"):
            with patch("integritykit.services.embedding.AsyncOpenAI") as mock_openai:
                mock_client = MagicMock()
                mock_client.embeddings.create = AsyncMock(
                    return_value=mock_embedding_response
                )
                mock_openai.return_value = mock_client

                service = EmbeddingService(openai_api_key="test-key")
                service.create_collection = AsyncMock(return_value=mock_collection)

                # Execute
                results = await service.find_similar(text="test query")

                # Verify
                assert results == []

    @pytest.mark.asyncio
    async def test_find_similar_openai_error(self):
        """Test find similar handles OpenAI errors."""
        with patch("integritykit.services.embedding.chromadb.HttpClient"):
            with patch("integritykit.services.embedding.AsyncOpenAI") as mock_openai:
                mock_client = MagicMock()
                mock_client.embeddings.create = AsyncMock(
                    side_effect=Exception("OpenAI API error")
                )
                mock_openai.return_value = mock_client

                service = EmbeddingService(openai_api_key="test-key")

                # Execute & Verify
                with pytest.raises(Exception, match="OpenAI API error"):
                    await service.find_similar(text="test query")


@pytest.mark.unit
class TestFindSimilarInCluster:
    """Test finding similar signals within a cluster."""

    @pytest.mark.asyncio
    async def test_find_similar_in_cluster_success(
        self, sample_embedding, mock_collection
    ):
        """Test finding similar signals in cluster returns filtered results."""
        signal_id = str(ObjectId())
        cluster_signal_1 = str(ObjectId())
        cluster_signal_2 = str(ObjectId())
        cluster_signal_3 = str(ObjectId())
        other_signal = str(ObjectId())  # Not in cluster

        cluster_signal_ids = [signal_id, cluster_signal_1, cluster_signal_2, cluster_signal_3]

        # Setup mocks
        mock_collection.get = MagicMock(
            return_value={"embeddings": [sample_embedding]}
        )

        mock_collection.query = MagicMock(
            return_value={
                "ids": [[signal_id, cluster_signal_1, other_signal, cluster_signal_2]],
                "distances": [[0.0, 0.1, 0.08, 0.2]],
            }
        )

        with patch("integritykit.services.embedding.chromadb.HttpClient"):
            with patch("integritykit.services.embedding.AsyncOpenAI"):
                service = EmbeddingService(openai_api_key="test-key")
                service.create_collection = AsyncMock(return_value=mock_collection)

                # Execute
                results = await service.find_similar_in_cluster(
                    signal_id=signal_id,
                    cluster_signal_ids=cluster_signal_ids,
                    threshold=0.85,
                    collection_name="test-collection",
                )

                # Verify
                # Should exclude:
                # - signal_id (self)
                # - other_signal (not in cluster)
                # - cluster_signal_2 (similarity 0.8 < threshold 0.85)
                # Should include:
                # - cluster_signal_1 (similarity 0.9 >= threshold 0.85)
                assert len(results) == 1
                assert results[0] == (cluster_signal_1, 0.9)

    @pytest.mark.asyncio
    async def test_find_similar_in_cluster_excludes_self(
        self, sample_embedding, mock_collection
    ):
        """Test find similar in cluster excludes the query signal itself."""
        signal_id = str(ObjectId())
        cluster_signal_ids = [signal_id]

        # Setup mocks
        mock_collection.get = MagicMock(
            return_value={"embeddings": [sample_embedding]}
        )

        mock_collection.query = MagicMock(
            return_value={
                "ids": [[signal_id]],  # Only returns self
                "distances": [[0.0]],  # Perfect match (self)
            }
        )

        with patch("integritykit.services.embedding.chromadb.HttpClient"):
            with patch("integritykit.services.embedding.AsyncOpenAI"):
                service = EmbeddingService(openai_api_key="test-key")
                service.create_collection = AsyncMock(return_value=mock_collection)

                # Execute
                results = await service.find_similar_in_cluster(
                    signal_id=signal_id,
                    cluster_signal_ids=cluster_signal_ids,
                    threshold=0.0,
                )

                # Verify - should be empty because self is excluded
                assert results == []

    @pytest.mark.asyncio
    async def test_find_similar_in_cluster_filters_by_threshold(
        self, sample_embedding, mock_collection
    ):
        """Test find similar in cluster filters results by threshold."""
        signal_id = str(ObjectId())
        cluster_signal_1 = str(ObjectId())
        cluster_signal_2 = str(ObjectId())

        cluster_signal_ids = [signal_id, cluster_signal_1, cluster_signal_2]

        # Setup mocks
        mock_collection.get = MagicMock(
            return_value={"embeddings": [sample_embedding]}
        )

        mock_collection.query = MagicMock(
            return_value={
                "ids": [[signal_id, cluster_signal_1, cluster_signal_2]],
                "distances": [[0.0, 0.05, 0.20]],  # Similarities: 1.0, 0.95, 0.80
            }
        )

        with patch("integritykit.services.embedding.chromadb.HttpClient"):
            with patch("integritykit.services.embedding.AsyncOpenAI"):
                service = EmbeddingService(openai_api_key="test-key")
                service.create_collection = AsyncMock(return_value=mock_collection)

                # Execute with high threshold
                results = await service.find_similar_in_cluster(
                    signal_id=signal_id,
                    cluster_signal_ids=cluster_signal_ids,
                    threshold=0.90,  # Only cluster_signal_1 should pass
                )

                # Verify
                assert len(results) == 1
                assert results[0] == (cluster_signal_1, 0.95)

    @pytest.mark.asyncio
    async def test_find_similar_in_cluster_filters_non_cluster_signals(
        self, sample_embedding, mock_collection
    ):
        """Test find similar in cluster excludes signals not in cluster."""
        signal_id = str(ObjectId())
        cluster_signal = str(ObjectId())
        non_cluster_signal_1 = str(ObjectId())
        non_cluster_signal_2 = str(ObjectId())

        cluster_signal_ids = [signal_id, cluster_signal]

        # Setup mocks
        mock_collection.get = MagicMock(
            return_value={"embeddings": [sample_embedding]}
        )

        # Query returns signals both in and out of cluster
        mock_collection.query = MagicMock(
            return_value={
                "ids": [[non_cluster_signal_1, cluster_signal, non_cluster_signal_2]],
                "distances": [[0.05, 0.08, 0.10]],
            }
        )

        with patch("integritykit.services.embedding.chromadb.HttpClient"):
            with patch("integritykit.services.embedding.AsyncOpenAI"):
                service = EmbeddingService(openai_api_key="test-key")
                service.create_collection = AsyncMock(return_value=mock_collection)

                # Execute
                results = await service.find_similar_in_cluster(
                    signal_id=signal_id,
                    cluster_signal_ids=cluster_signal_ids,
                    threshold=0.85,
                )

                # Verify - only cluster_signal should be included
                assert len(results) == 1
                assert results[0][0] == cluster_signal

    @pytest.mark.asyncio
    async def test_find_similar_in_cluster_signal_not_found(self, mock_collection):
        """Test find similar in cluster when signal not found in ChromaDB."""
        signal_id = str(ObjectId())
        cluster_signal_ids = [signal_id, str(ObjectId())]

        # Setup mocks - signal not found
        mock_collection.get = MagicMock(return_value={"embeddings": []})

        with patch("integritykit.services.embedding.chromadb.HttpClient"):
            with patch("integritykit.services.embedding.AsyncOpenAI"):
                service = EmbeddingService(openai_api_key="test-key")
                service.create_collection = AsyncMock(return_value=mock_collection)

                # Execute
                results = await service.find_similar_in_cluster(
                    signal_id=signal_id,
                    cluster_signal_ids=cluster_signal_ids,
                )

                # Verify - should return empty list
                assert results == []

    @pytest.mark.asyncio
    async def test_find_similar_in_cluster_chromadb_error(
        self, sample_embedding, mock_collection
    ):
        """Test find similar in cluster handles ChromaDB errors."""
        signal_id = str(ObjectId())
        cluster_signal_ids = [signal_id]

        # Setup mocks
        mock_collection.get = MagicMock(
            side_effect=Exception("ChromaDB connection error")
        )

        with patch("integritykit.services.embedding.chromadb.HttpClient"):
            with patch("integritykit.services.embedding.AsyncOpenAI"):
                service = EmbeddingService(openai_api_key="test-key")
                service.create_collection = AsyncMock(return_value=mock_collection)

                # Execute & Verify
                with pytest.raises(Exception, match="ChromaDB connection error"):
                    await service.find_similar_in_cluster(
                        signal_id=signal_id,
                        cluster_signal_ids=cluster_signal_ids,
                    )


@pytest.mark.unit
class TestDeleteSignal:
    """Test deleting signal embeddings."""

    @pytest.mark.asyncio
    async def test_delete_signal_success(self, mock_collection):
        """Test successfully deleting signal embedding."""
        signal_id = str(ObjectId())

        with patch("integritykit.services.embedding.chromadb.HttpClient"):
            with patch("integritykit.services.embedding.AsyncOpenAI"):
                service = EmbeddingService(openai_api_key="test-key")
                service.create_collection = AsyncMock(return_value=mock_collection)

                # Execute
                await service.delete_signal(signal_id, "test-collection")

                # Verify
                service.create_collection.assert_called_once_with("test-collection")
                mock_collection.delete.assert_called_once_with(ids=[signal_id])

    @pytest.mark.asyncio
    async def test_delete_signal_default_collection(self, mock_collection):
        """Test delete signal uses default collection name."""
        signal_id = str(ObjectId())

        with patch("integritykit.services.embedding.chromadb.HttpClient"):
            with patch("integritykit.services.embedding.AsyncOpenAI"):
                service = EmbeddingService(openai_api_key="test-key")
                service.create_collection = AsyncMock(return_value=mock_collection)

                # Execute without collection_name
                await service.delete_signal(signal_id)

                # Verify - should use default "signals" collection
                service.create_collection.assert_called_once_with("signals")

    @pytest.mark.asyncio
    async def test_delete_signal_chromadb_error(self, mock_collection):
        """Test delete signal handles ChromaDB errors."""
        signal_id = str(ObjectId())

        # Setup mock to raise error
        mock_collection.delete = MagicMock(side_effect=Exception("Delete failed"))

        with patch("integritykit.services.embedding.chromadb.HttpClient"):
            with patch("integritykit.services.embedding.AsyncOpenAI"):
                service = EmbeddingService(openai_api_key="test-key")
                service.create_collection = AsyncMock(return_value=mock_collection)

                # Execute & Verify
                with pytest.raises(Exception, match="Delete failed"):
                    await service.delete_signal(signal_id)
