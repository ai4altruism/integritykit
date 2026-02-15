"""Database service for MongoDB operations using Motor (async)."""

from typing import Optional

from bson import ObjectId
from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorCollection,
    AsyncIOMotorDatabase,
)

from integritykit.models.cluster import Cluster, ClusterCreate
from integritykit.models.cop_candidate import COPCandidate, COPCandidateCreate
from integritykit.models.signal import Signal, SignalCreate
from integritykit.models.user import User, UserCreate, UserRole, RoleChange

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


class ClusterRepository:
    """Repository for cluster CRUD operations."""

    def __init__(self, collection: Optional[AsyncIOMotorCollection] = None):
        """Initialize cluster repository.

        Args:
            collection: Motor collection instance (optional, uses default if not provided)
        """
        self.collection = collection or get_collection("clusters")

    async def create(self, cluster_data: ClusterCreate) -> Cluster:
        """Create a new cluster document.

        Args:
            cluster_data: Cluster creation data

        Returns:
            Created Cluster instance with ID
        """
        cluster = Cluster(
            **cluster_data.model_dump(),
        )

        # Convert to dict for MongoDB insertion
        cluster_dict = cluster.model_dump(by_alias=True, exclude={"id"})

        result = await self.collection.insert_one(cluster_dict)
        cluster.id = result.inserted_id

        return cluster

    async def get_by_id(self, cluster_id: ObjectId) -> Optional[Cluster]:
        """Get cluster by MongoDB ObjectId.

        Args:
            cluster_id: Cluster ObjectId

        Returns:
            Cluster instance or None if not found
        """
        doc = await self.collection.find_one({"_id": cluster_id})
        if doc:
            return Cluster(**doc)
        return None

    async def update(
        self,
        cluster_id: ObjectId,
        updates: dict,
    ) -> Optional[Cluster]:
        """Update cluster by ID.

        Args:
            cluster_id: Cluster ObjectId
            updates: Dictionary of fields to update

        Returns:
            Updated Cluster instance or None if not found
        """
        result = await self.collection.find_one_and_update(
            {"_id": cluster_id},
            {"$set": updates},
            return_document=True,
        )
        if result:
            return Cluster(**result)
        return None

    async def add_signal(
        self,
        cluster_id: ObjectId,
        signal_id: ObjectId,
    ) -> Optional[Cluster]:
        """Add signal to a cluster.

        Args:
            cluster_id: Cluster ObjectId
            signal_id: Signal ObjectId to add

        Returns:
            Updated Cluster instance or None if not found
        """
        from datetime import datetime

        result = await self.collection.find_one_and_update(
            {"_id": cluster_id},
            {
                "$addToSet": {"signal_ids": signal_id},
                "$set": {"updated_at": datetime.utcnow()},
            },
            return_document=True,
        )
        if result:
            return Cluster(**result)
        return None

    async def list_by_workspace(
        self,
        workspace_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Cluster]:
        """List clusters by workspace with pagination.

        Args:
            workspace_id: Slack workspace ID
            limit: Maximum number of clusters to return
            offset: Number of clusters to skip

        Returns:
            List of Cluster instances
        """
        cursor = (
            self.collection.find({"slack_workspace_id": workspace_id})
            .sort("updated_at", -1)
            .skip(offset)
            .limit(limit)
        )

        clusters = []
        async for doc in cursor:
            clusters.append(Cluster(**doc))

        return clusters

    async def list_unpromoted_clusters(
        self,
        workspace_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Cluster]:
        """List unpromoted clusters for backlog, ordered by priority.

        Args:
            workspace_id: Slack workspace ID
            limit: Maximum number of clusters to return
            offset: Number of clusters to skip

        Returns:
            List of Cluster instances ordered by composite priority score descending
        """
        cursor = (
            self.collection.find(
                {
                    "slack_workspace_id": workspace_id,
                    "promoted_to_candidate": False,
                }
            )
            .sort(
                [
                    # Sort by composite priority (calculated from urgency, impact, risk)
                    ("priority_scores.urgency", -1),
                    ("priority_scores.impact", -1),
                    ("priority_scores.risk", -1),
                    ("updated_at", -1),
                ]
            )
            .skip(offset)
            .limit(limit)
        )

        clusters = []
        async for doc in cursor:
            clusters.append(Cluster(**doc))

        return clusters

    async def update_priority_scores(
        self,
        cluster_id: ObjectId,
        priority_scores: dict,
    ) -> Optional[Cluster]:
        """Update cluster priority scores.

        Args:
            cluster_id: Cluster ObjectId
            priority_scores: PriorityScores as dict

        Returns:
            Updated Cluster instance or None if not found
        """
        from datetime import datetime

        result = await self.collection.find_one_and_update(
            {"_id": cluster_id},
            {
                "$set": {
                    "priority_scores": priority_scores,
                    "updated_at": datetime.utcnow(),
                }
            },
            return_document=True,
        )
        if result:
            return Cluster(**result)
        return None


class UserRepository:
    """Repository for user CRUD operations (FR-ROLE-001, FR-ROLE-002)."""

    def __init__(self, collection: Optional[AsyncIOMotorCollection] = None):
        """Initialize user repository.

        Args:
            collection: Motor collection instance (optional, uses default if not provided)
        """
        self.collection = collection or get_collection("users")

    async def create(self, user_data: UserCreate) -> User:
        """Create a new user document.

        Args:
            user_data: User creation data

        Returns:
            Created User instance with ID
        """
        user = User(
            **user_data.model_dump(),
        )

        # Convert to dict for MongoDB insertion
        user_dict = user.model_dump(by_alias=True, exclude={"id"})

        result = await self.collection.insert_one(user_dict)
        user.id = result.inserted_id

        return user

    async def get_by_id(self, user_id: ObjectId) -> Optional[User]:
        """Get user by MongoDB ObjectId.

        Args:
            user_id: User ObjectId

        Returns:
            User instance or None if not found
        """
        doc = await self.collection.find_one({"_id": user_id})
        if doc:
            return User(**doc)
        return None

    async def get_by_slack_id(
        self,
        slack_user_id: str,
        slack_team_id: str,
    ) -> Optional[User]:
        """Get user by Slack user and team ID.

        Args:
            slack_user_id: Slack user ID
            slack_team_id: Slack workspace/team ID

        Returns:
            User instance or None if not found
        """
        doc = await self.collection.find_one(
            {
                "slack_user_id": slack_user_id,
                "slack_team_id": slack_team_id,
            }
        )
        if doc:
            return User(**doc)
        return None

    async def get_or_create_by_slack_id(
        self,
        slack_user_id: str,
        slack_team_id: str,
        slack_email: Optional[str] = None,
        slack_display_name: Optional[str] = None,
        slack_real_name: Optional[str] = None,
    ) -> tuple[User, bool]:
        """Get or create user by Slack ID.

        Args:
            slack_user_id: Slack user ID
            slack_team_id: Slack workspace/team ID
            slack_email: Optional email
            slack_display_name: Optional display name
            slack_real_name: Optional real name

        Returns:
            Tuple of (User, created) where created is True if new user
        """
        existing = await self.get_by_slack_id(slack_user_id, slack_team_id)
        if existing:
            return existing, False

        user_data = UserCreate(
            slack_user_id=slack_user_id,
            slack_team_id=slack_team_id,
            slack_email=slack_email,
            slack_display_name=slack_display_name,
            slack_real_name=slack_real_name,
        )
        user = await self.create(user_data)
        return user, True

    async def update(
        self,
        user_id: ObjectId,
        updates: dict,
    ) -> Optional[User]:
        """Update user by ID.

        Args:
            user_id: User ObjectId
            updates: Dictionary of fields to update

        Returns:
            Updated User instance or None if not found
        """
        from datetime import datetime

        updates["updated_at"] = datetime.utcnow()

        result = await self.collection.find_one_and_update(
            {"_id": user_id},
            {"$set": updates},
            return_document=True,
        )
        if result:
            return User(**result)
        return None

    async def save(self, user: User) -> User:
        """Save user document (full replacement).

        Args:
            user: User instance to save

        Returns:
            Saved User instance
        """
        from datetime import datetime

        user.updated_at = datetime.utcnow()

        user_dict = user.model_dump(by_alias=True, exclude={"id"})

        await self.collection.replace_one(
            {"_id": user.id},
            user_dict,
        )

        return user

    async def add_role(
        self,
        user_id: ObjectId,
        role: UserRole,
        changed_by: ObjectId,
        reason: Optional[str] = None,
    ) -> Optional[User]:
        """Add role to user with audit trail.

        Args:
            user_id: User ObjectId
            role: Role to add
            changed_by: User ID making the change
            reason: Reason for change

        Returns:
            Updated User instance or None if not found
        """
        from datetime import datetime

        now = datetime.utcnow()

        # First get the user to record old roles
        user = await self.get_by_id(user_id)
        if not user:
            return None

        # Create role change record
        role_change = {
            "changed_at": now,
            "changed_by": changed_by,
            "old_roles": user.roles,
            "new_roles": user.roles + [role.value],
            "reason": reason,
        }

        result = await self.collection.find_one_and_update(
            {"_id": user_id},
            {
                "$addToSet": {"roles": role.value},
                "$push": {"role_history": role_change},
                "$set": {"updated_at": now},
            },
            return_document=True,
        )

        if result:
            return User(**result)
        return None

    async def remove_role(
        self,
        user_id: ObjectId,
        role: UserRole,
        changed_by: ObjectId,
        reason: Optional[str] = None,
    ) -> Optional[User]:
        """Remove role from user with audit trail.

        Args:
            user_id: User ObjectId
            role: Role to remove
            changed_by: User ID making the change
            reason: Reason for change

        Returns:
            Updated User instance or None if not found
        """
        from datetime import datetime

        now = datetime.utcnow()

        # First get the user to record old roles
        user = await self.get_by_id(user_id)
        if not user:
            return None

        # Create role change record
        new_roles = [r for r in user.roles if r != role.value and r != role]
        role_change = {
            "changed_at": now,
            "changed_by": changed_by,
            "old_roles": user.roles,
            "new_roles": new_roles,
            "reason": reason,
        }

        result = await self.collection.find_one_and_update(
            {"_id": user_id},
            {
                "$pull": {"roles": role.value},
                "$push": {"role_history": role_change},
                "$set": {"updated_at": now},
            },
            return_document=True,
        )

        if result:
            return User(**result)
        return None

    async def suspend_user(
        self,
        user_id: ObjectId,
        suspended_by: ObjectId,
        reason: str,
    ) -> Optional[User]:
        """Suspend a user account (NFR-ABUSE-002).

        Args:
            user_id: User ObjectId
            suspended_by: Admin user ID
            reason: Suspension reason

        Returns:
            Updated User instance or None if not found
        """
        from datetime import datetime

        now = datetime.utcnow()

        suspension_record = {
            "suspended_at": now,
            "suspended_by": suspended_by,
            "suspension_reason": reason,
            "reinstated_at": None,
            "reinstated_by": None,
            "reinstatement_reason": None,
        }

        result = await self.collection.find_one_and_update(
            {"_id": user_id},
            {
                "$set": {
                    "is_suspended": True,
                    "updated_at": now,
                },
                "$push": {"suspension_history": suspension_record},
            },
            return_document=True,
        )

        if result:
            return User(**result)
        return None

    async def reinstate_user(
        self,
        user_id: ObjectId,
        reinstated_by: ObjectId,
        reason: Optional[str] = None,
    ) -> Optional[User]:
        """Reinstate a suspended user.

        Args:
            user_id: User ObjectId
            reinstated_by: Admin user ID
            reason: Reinstatement reason

        Returns:
            Updated User instance or None if not found
        """
        from datetime import datetime

        now = datetime.utcnow()

        # Update the most recent suspension record
        result = await self.collection.find_one_and_update(
            {
                "_id": user_id,
                "suspension_history.reinstated_at": None,
            },
            {
                "$set": {
                    "is_suspended": False,
                    "updated_at": now,
                    "suspension_history.$.reinstated_at": now,
                    "suspension_history.$.reinstated_by": reinstated_by,
                    "suspension_history.$.reinstatement_reason": reason,
                },
            },
            return_document=True,
        )

        if result:
            return User(**result)
        return None

    async def list_by_workspace(
        self,
        slack_team_id: str,
        role: Optional[UserRole] = None,
        is_suspended: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[User]:
        """List users by workspace with filters.

        Args:
            slack_team_id: Slack workspace ID
            role: Filter by role (optional)
            is_suspended: Filter by suspension status (optional)
            limit: Maximum number of users to return
            offset: Number of users to skip

        Returns:
            List of User instances
        """
        query: dict = {"slack_team_id": slack_team_id}

        if role is not None:
            query["roles"] = role.value

        if is_suspended is not None:
            query["is_suspended"] = is_suspended

        cursor = (
            self.collection.find(query)
            .sort("created_at", -1)
            .skip(offset)
            .limit(limit)
        )

        users = []
        async for doc in cursor:
            users.append(User(**doc))

        return users

    async def count_by_workspace(
        self,
        slack_team_id: str,
        role: Optional[UserRole] = None,
        is_suspended: Optional[bool] = None,
    ) -> int:
        """Count users by workspace with filters.

        Args:
            slack_team_id: Slack workspace ID
            role: Filter by role (optional)
            is_suspended: Filter by suspension status (optional)

        Returns:
            Count of matching users
        """
        query: dict = {"slack_team_id": slack_team_id}

        if role is not None:
            query["roles"] = role.value

        if is_suspended is not None:
            query["is_suspended"] = is_suspended

        return await self.collection.count_documents(query)

    async def update_activity_stats(
        self,
        user_id: ObjectId,
        increment_actions: bool = True,
        increment_publishes: bool = False,
        increment_overrides: bool = False,
    ) -> Optional[User]:
        """Update user activity stats.

        Args:
            user_id: User ObjectId
            increment_actions: Increment total actions
            increment_publishes: Increment publish count
            increment_overrides: Increment high-stakes override count

        Returns:
            Updated User instance or None if not found
        """
        from datetime import datetime

        now = datetime.utcnow()

        inc_updates = {}
        if increment_actions:
            inc_updates["activity_stats.total_actions"] = 1
        if increment_publishes:
            inc_updates["activity_stats.publish_count"] = 1
        if increment_overrides:
            inc_updates["activity_stats.high_stakes_overrides_count"] = 1

        update_query = {
            "$set": {
                "activity_stats.last_action_at": now,
                "updated_at": now,
            },
        }

        if inc_updates:
            update_query["$inc"] = inc_updates

        result = await self.collection.find_one_and_update(
            {"_id": user_id},
            update_query,
            return_document=True,
        )

        if result:
            return User(**result)
        return None


class COPCandidateRepository:
    """Repository for COP candidate CRUD operations (FR-BACKLOG-002)."""

    def __init__(self, collection: Optional[AsyncIOMotorCollection] = None):
        """Initialize COP candidate repository.

        Args:
            collection: Motor collection instance (optional, uses default if not provided)
        """
        self.collection = collection or get_collection("cop_candidates")

    async def create(self, candidate_data: COPCandidateCreate) -> COPCandidate:
        """Create a new COP candidate document.

        Args:
            candidate_data: COP candidate creation data

        Returns:
            Created COPCandidate instance with ID
        """
        from datetime import datetime

        candidate = COPCandidate(
            **candidate_data.model_dump(),
        )

        # Convert to dict for MongoDB insertion
        candidate_dict = candidate.model_dump(by_alias=True, exclude={"id"})

        result = await self.collection.insert_one(candidate_dict)
        candidate.id = result.inserted_id

        return candidate

    async def get_by_id(self, candidate_id: ObjectId) -> Optional[COPCandidate]:
        """Get COP candidate by MongoDB ObjectId.

        Args:
            candidate_id: COP candidate ObjectId

        Returns:
            COPCandidate instance or None if not found
        """
        doc = await self.collection.find_one({"_id": candidate_id})
        if doc:
            return COPCandidate(**doc)
        return None

    async def get_by_cluster_id(self, cluster_id: ObjectId) -> Optional[COPCandidate]:
        """Get COP candidate by source cluster ID.

        Args:
            cluster_id: Source cluster ObjectId

        Returns:
            COPCandidate instance or None if not found
        """
        doc = await self.collection.find_one({"cluster_id": cluster_id})
        if doc:
            return COPCandidate(**doc)
        return None

    async def update(
        self,
        candidate_id: ObjectId,
        updates: dict,
    ) -> Optional[COPCandidate]:
        """Update COP candidate by ID.

        Args:
            candidate_id: COP candidate ObjectId
            updates: Dictionary of fields to update

        Returns:
            Updated COPCandidate instance or None if not found
        """
        from datetime import datetime

        updates["updated_at"] = datetime.utcnow()

        result = await self.collection.find_one_and_update(
            {"_id": candidate_id},
            {"$set": updates},
            return_document=True,
        )
        if result:
            return COPCandidate(**result)
        return None

    async def update_readiness_state(
        self,
        candidate_id: ObjectId,
        new_state: str,
        updated_by: ObjectId,
    ) -> Optional[COPCandidate]:
        """Update COP candidate readiness state.

        Args:
            candidate_id: COP candidate ObjectId
            new_state: New readiness state
            updated_by: User making the change

        Returns:
            Updated COPCandidate instance or None if not found
        """
        from datetime import datetime

        now = datetime.utcnow()

        result = await self.collection.find_one_and_update(
            {"_id": candidate_id},
            {
                "$set": {
                    "readiness_state": new_state,
                    "readiness_updated_at": now,
                    "readiness_updated_by": updated_by,
                    "updated_at": now,
                }
            },
            return_document=True,
        )
        if result:
            return COPCandidate(**result)
        return None

    async def list_by_workspace(
        self,
        cluster_ids: list[ObjectId],
        readiness_state: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[COPCandidate]:
        """List COP candidates by cluster IDs (workspace scope).

        Args:
            cluster_ids: List of cluster IDs to filter by
            readiness_state: Filter by state (optional)
            limit: Maximum number of candidates to return
            offset: Number of candidates to skip

        Returns:
            List of COPCandidate instances
        """
        query: dict = {"cluster_id": {"$in": cluster_ids}}

        if readiness_state:
            query["readiness_state"] = readiness_state

        cursor = (
            self.collection.find(query)
            .sort("updated_at", -1)
            .skip(offset)
            .limit(limit)
        )

        candidates = []
        async for doc in cursor:
            candidates.append(COPCandidate(**doc))

        return candidates

    async def count_by_state(
        self,
        cluster_ids: list[ObjectId],
        readiness_state: str,
    ) -> int:
        """Count COP candidates by state.

        Args:
            cluster_ids: List of cluster IDs to filter by
            readiness_state: State to count

        Returns:
            Count of matching candidates
        """
        return await self.collection.count_documents(
            {
                "cluster_id": {"$in": cluster_ids},
                "readiness_state": readiness_state,
            }
        )
