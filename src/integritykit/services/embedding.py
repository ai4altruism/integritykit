"""Embedding service using ChromaDB for vector storage and OpenAI for embedding generation."""

from typing import Optional

import chromadb
import structlog
from chromadb.api.types import EmbeddingFunction
from openai import AsyncOpenAI

from integritykit.models.signal import Signal

logger = structlog.get_logger(__name__)


class OpenAIEmbeddingFunction(EmbeddingFunction):
    """OpenAI embedding function for ChromaDB."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        """Initialize OpenAI embedding function.

        Args:
            api_key: OpenAI API key
            model: OpenAI embedding model name
        """
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def __call__(self, input: list[str]) -> list[list[float]]:
        """Generate embeddings for input texts.

        Args:
            input: List of text strings to embed

        Returns:
            List of embedding vectors
        """
        response = await self.client.embeddings.create(
            model=self.model,
            input=input,
        )
        return [data.embedding for data in response.data]


class EmbeddingService:
    """Service for managing signal embeddings with ChromaDB."""

    def __init__(
        self,
        openai_api_key: str,
        chromadb_host: str = "localhost",
        chromadb_port: int = 8000,
        embedding_model: str = "text-embedding-3-small",
        use_persistent: bool = False,
        persist_directory: Optional[str] = None,
    ):
        """Initialize embedding service.

        Args:
            openai_api_key: OpenAI API key
            chromadb_host: ChromaDB server host
            chromadb_port: ChromaDB server port
            embedding_model: OpenAI embedding model to use
            use_persistent: Whether to use persistent storage
            persist_directory: Directory for persistent storage (required if use_persistent=True)
        """
        self.openai_api_key = openai_api_key
        self.embedding_model = embedding_model
        self.openai_client = AsyncOpenAI(api_key=openai_api_key)

        # Initialize ChromaDB client
        if use_persistent:
            if not persist_directory:
                raise ValueError("persist_directory required when use_persistent=True")
            self.chroma_client = chromadb.PersistentClient(path=persist_directory)
            logger.info(
                "Initialized ChromaDB persistent client",
                persist_directory=persist_directory,
            )
        else:
            # Use HTTP client for server mode
            self.chroma_client = chromadb.HttpClient(
                host=chromadb_host,
                port=chromadb_port,
            )
            logger.info(
                "Initialized ChromaDB HTTP client",
                host=chromadb_host,
                port=chromadb_port,
            )

    async def create_collection(self, name: str) -> chromadb.Collection:
        """Create or get a ChromaDB collection.

        Args:
            name: Collection name

        Returns:
            ChromaDB collection instance
        """
        try:
            collection = self.chroma_client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("Created/retrieved ChromaDB collection", collection_name=name)
            return collection
        except Exception as e:
            logger.error(
                "Failed to create ChromaDB collection",
                collection_name=name,
                error=str(e),
            )
            raise

    async def add_signal(
        self,
        signal: Signal,
        collection_name: str = "signals",
    ) -> str:
        """Generate embedding for signal and store in ChromaDB.

        Args:
            signal: Signal to embed
            collection_name: ChromaDB collection name

        Returns:
            Embedding ID (signal ID as string)

        Raises:
            ValueError: If signal has no ID
        """
        if not signal.id:
            raise ValueError("Signal must have an ID before embedding")

        signal_id = str(signal.id)

        try:
            # Generate embedding via OpenAI
            response = await self.openai_client.embeddings.create(
                model=self.embedding_model,
                input=signal.content,
            )
            embedding = response.data[0].embedding

            # Store in ChromaDB
            collection = await self.create_collection(collection_name)
            collection.add(
                ids=[signal_id],
                embeddings=[embedding],
                metadatas=[
                    {
                        "slack_workspace_id": signal.slack_workspace_id,
                        "slack_channel_id": signal.slack_channel_id,
                        "slack_message_ts": signal.slack_message_ts,
                        "created_at": signal.created_at.isoformat(),
                    }
                ],
                documents=[signal.content],
            )

            logger.info(
                "Added signal embedding to ChromaDB",
                signal_id=signal_id,
                collection=collection_name,
                embedding_dim=len(embedding),
            )

            return signal_id

        except Exception as e:
            logger.error(
                "Failed to add signal embedding",
                signal_id=signal_id,
                error=str(e),
            )
            raise

    async def find_similar(
        self,
        text: str,
        n: int = 10,
        collection_name: str = "signals",
        workspace_id: Optional[str] = None,
    ) -> list[tuple[str, float]]:
        """Find similar signals by text similarity.

        Args:
            text: Query text to find similar signals
            n: Number of results to return
            collection_name: ChromaDB collection name
            workspace_id: Optional workspace ID to filter results

        Returns:
            List of (signal_id, similarity_score) tuples, ordered by similarity descending
        """
        try:
            # Generate embedding for query text
            response = await self.openai_client.embeddings.create(
                model=self.embedding_model,
                input=text,
            )
            query_embedding = response.data[0].embedding

            # Query ChromaDB
            collection = await self.create_collection(collection_name)

            # Build metadata filter if workspace specified
            where = None
            if workspace_id:
                where = {"slack_workspace_id": workspace_id}

            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=n,
                where=where,
            )

            # Extract results
            similar_signals = []
            if results["ids"] and results["distances"]:
                for signal_id, distance in zip(results["ids"][0], results["distances"][0]):
                    # Convert distance to similarity (cosine distance -> similarity)
                    similarity = 1 - distance
                    similar_signals.append((signal_id, similarity))

            logger.info(
                "Found similar signals",
                query_text_length=len(text),
                n_results=len(similar_signals),
                collection=collection_name,
            )

            return similar_signals

        except Exception as e:
            logger.error(
                "Failed to find similar signals",
                error=str(e),
            )
            raise

    async def find_similar_in_cluster(
        self,
        signal_id: str,
        cluster_signal_ids: list[str],
        threshold: float = 0.85,
        collection_name: str = "signals",
    ) -> list[tuple[str, float]]:
        """Find similar signals within a specific cluster.

        Used for duplicate detection within clusters.

        Args:
            signal_id: Signal ID to compare
            cluster_signal_ids: List of signal IDs in the cluster
            threshold: Similarity threshold (0-1)
            collection_name: ChromaDB collection name

        Returns:
            List of (signal_id, similarity_score) tuples exceeding threshold
        """
        try:
            collection = await self.create_collection(collection_name)

            # Get the signal's embedding
            results = collection.get(
                ids=[signal_id],
                include=["embeddings"],
            )

            if not results["embeddings"]:
                logger.warning(
                    "Signal not found in ChromaDB",
                    signal_id=signal_id,
                )
                return []

            query_embedding = results["embeddings"][0]

            # Query against cluster signals
            cluster_results = collection.query(
                query_embeddings=[query_embedding],
                n_results=len(cluster_signal_ids),
                where=None,  # We'll filter manually
            )

            # Filter to cluster signals and apply threshold
            similar = []
            if cluster_results["ids"] and cluster_results["distances"]:
                for cid, distance in zip(
                    cluster_results["ids"][0], cluster_results["distances"][0]
                ):
                    # Skip self-comparison
                    if cid == signal_id:
                        continue

                    # Only include signals in the cluster
                    if cid not in cluster_signal_ids:
                        continue

                    similarity = 1 - distance
                    if similarity >= threshold:
                        similar.append((cid, similarity))

            logger.info(
                "Found similar signals in cluster",
                signal_id=signal_id,
                cluster_size=len(cluster_signal_ids),
                similar_count=len(similar),
                threshold=threshold,
            )

            return similar

        except Exception as e:
            logger.error(
                "Failed to find similar signals in cluster",
                signal_id=signal_id,
                error=str(e),
            )
            raise

    async def delete_signal(
        self,
        signal_id: str,
        collection_name: str = "signals",
    ) -> None:
        """Delete signal embedding from ChromaDB.

        Args:
            signal_id: Signal ID to delete
            collection_name: ChromaDB collection name
        """
        try:
            collection = await self.create_collection(collection_name)
            collection.delete(ids=[signal_id])

            logger.info(
                "Deleted signal embedding",
                signal_id=signal_id,
                collection=collection_name,
            )

        except Exception as e:
            logger.error(
                "Failed to delete signal embedding",
                signal_id=signal_id,
                error=str(e),
            )
            raise
