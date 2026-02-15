"""Database service for MongoDB operations using Motor (async)."""

from typing import Optional

from bson import ObjectId
from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorCollection,
    AsyncIOMotorDatabase,
)

from integritykit.models.signal import Signal, SignalCreate

# Global MongoDB client (initialized at startup)
_mongodb_client: Optional[AsyncIOMotorClient] = None
_mongodb_database: Optional[AsyncIOMotorDatabase] = None


async def connect_to_mongodb(uri: str, database_name: str) -> None:
    """Connect to MongoDB and initialize global client.

    Args:
        uri: MongoDB connection URI
        database_name: Database name to use
    """
    global _mongodb_client, _mongodb_database
    _mongodb_client = AsyncIOMotorClient(uri)
    _mongodb_database = _mongodb_client[database_name]


async def close_mongodb_connection() -> None:
    """Close MongoDB connection."""
    global _mongodb_client
    if _mongodb_client:
        _mongodb_client.close()


def get_database() -> AsyncIOMotorDatabase:
    """Get MongoDB database instance.

    Returns:
        AsyncIOMotorDatabase instance

    Raises:
        RuntimeError: If database not initialized
    """
    if _mongodb_database is None:
        raise RuntimeError("Database not initialized. Call connect_to_mongodb first.")
    return _mongodb_database


def get_collection(name: str) -> AsyncIOMotorCollection:
    """Get MongoDB collection by name.

    Args:
        name: Collection name

    Returns:
        AsyncIOMotorCollection instance
    """
    db = get_database()
    return db[name]


class SignalRepository:
    """Repository for signal CRUD operations."""

    def __init__(self, collection: Optional[AsyncIOMotorCollection] = None):
        """Initialize signal repository.

        Args:
            collection: Motor collection instance (optional, uses default if not provided)
        """
        self.collection = collection or get_collection("signals")

    async def create(self, signal_data: SignalCreate) -> Signal:
        """Create a new signal document.

        Args:
            signal_data: Signal creation data

        Returns:
            Created Signal instance with ID
        """
        signal = Signal(
            **signal_data.model_dump(),
        )

        # Convert to dict for MongoDB insertion
        signal_dict = signal.model_dump(by_alias=True, exclude={"id"})

        result = await self.collection.insert_one(signal_dict)
        signal.id = result.inserted_id

        return signal

    async def get_by_id(self, signal_id: ObjectId) -> Optional[Signal]:
        """Get signal by MongoDB ObjectId.

        Args:
            signal_id: Signal ObjectId

        Returns:
            Signal instance or None if not found
        """
        doc = await self.collection.find_one({"_id": signal_id})
        if doc:
            return Signal(**doc)
        return None

    async def get_by_slack_ts(
        self,
        workspace_id: str,
        channel_id: str,
        message_ts: str,
    ) -> Optional[Signal]:
        """Get signal by Slack message timestamp.

        Args:
            workspace_id: Slack workspace ID
            channel_id: Slack channel ID
            message_ts: Slack message timestamp

        Returns:
            Signal instance or None if not found
        """
        doc = await self.collection.find_one(
            {
                "slack_workspace_id": workspace_id,
                "slack_channel_id": channel_id,
                "slack_message_ts": message_ts,
            }
        )
        if doc:
            return Signal(**doc)
        return None

    async def update(
        self,
        signal_id: ObjectId,
        updates: dict,
    ) -> Optional[Signal]:
        """Update signal by ID.

        Args:
            signal_id: Signal ObjectId
            updates: Dictionary of fields to update

        Returns:
            Updated Signal instance or None if not found
        """
        result = await self.collection.find_one_and_update(
            {"_id": signal_id},
            {"$set": updates},
            return_document=True,
        )
        if result:
            return Signal(**result)
        return None

    async def add_to_cluster(
        self,
        signal_id: ObjectId,
        cluster_id: ObjectId,
    ) -> Optional[Signal]:
        """Add signal to a cluster.

        Args:
            signal_id: Signal ObjectId
            cluster_id: Cluster ObjectId to add

        Returns:
            Updated Signal instance or None if not found
        """
        result = await self.collection.find_one_and_update(
            {"_id": signal_id},
            {"$addToSet": {"cluster_ids": cluster_id}},
            return_document=True,
        )
        if result:
            return Signal(**result)
        return None

    async def list_by_channel(
        self,
        channel_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Signal]:
        """List signals by channel with pagination.

        Args:
            channel_id: Slack channel ID
            limit: Maximum number of signals to return
            offset: Number of signals to skip

        Returns:
            List of Signal instances
        """
        cursor = (
            self.collection.find({"slack_channel_id": channel_id})
            .sort("created_at", -1)
            .skip(offset)
            .limit(limit)
        )

        signals = []
        async for doc in cursor:
            signals.append(Signal(**doc))

        return signals

    async def list_by_cluster(self, cluster_id: ObjectId) -> list[Signal]:
        """List all signals in a cluster.

        Args:
            cluster_id: Cluster ObjectId

        Returns:
            List of Signal instances
        """
        cursor = self.collection.find({"cluster_ids": cluster_id}).sort(
            "created_at", -1
        )

        signals = []
        async for doc in cursor:
            signals.append(Signal(**doc))

        return signals
