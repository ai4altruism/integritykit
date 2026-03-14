"""
Script to simulate incoming Slack messages for the demonstration.
This injects simulated crisis reports into the IntegrityKit pipeline.
"""

import asyncio
import os
import time
from datetime import datetime, timezone

import structlog
from dotenv import load_dotenv

# Load demo environment
load_dotenv("demo/.env.demo", override=True)

from integritykit.config import settings
from integritykit.models.signal import Signal, SourceQuality, SourceQualityType
from integritykit.services.database import connect_to_mongodb, close_mongodb_connection, SignalRepository, ClusterRepository
from integritykit.services.embedding import EmbeddingService
from integritykit.services.llm import LLMService
from integritykit.services.clustering import ClusteringService

logger = structlog.get_logger(__name__)

async def create_and_process_signal(
    signal_repo: SignalRepository,
    clustering_service: ClusteringService,
    text: str,
    channel_id: str,
    user_id: str,
    is_firsthand: bool = False,
    external_links: list[str] = None
):
    """Create a signal, save it, and run it through the clustering pipeline."""
    timestamp = str(time.time())
    
    signal = Signal(
        slack_workspace_id="T01DEMO",
        slack_channel_id=channel_id,
        slack_message_ts=timestamp,
        slack_user_id=user_id,
        slack_permalink=f"https://demo.slack.com/archives/{channel_id}/p{timestamp.replace('.', '')}",
        content=text,
        source_quality=SourceQuality(
            type=SourceQualityType.PRIMARY if is_firsthand else SourceQualityType.SECONDARY,
            is_firsthand=is_firsthand,
            has_external_link=bool(external_links),
            external_links=external_links or []
        )
    )
    
    # 1. Save to MongoDB
    created_signal = await signal_repo.create(signal)
    logger.info(f"Inserted signal: {created_signal.id} - '{text[:30]}...'")
    
    # 2. Process through AI clustering
    # NOTE: Depending on how ClusteringService is implemented, we might need to catch exceptions 
    # if process_new_signal expects the caller to do embedding first.
    try:
        cluster = await clustering_service.process_new_signal(created_signal)
        logger.info(f"Clustered into: {cluster.id} (topic: {cluster.summary})")
    except Exception as e:
        logger.error(f"Failed to cluster signal: {e}")
        
    return created_signal

async def main():
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY is not set. Please set it in demo/.env.demo before running the scenario.")
        return

    logger.info("Connecting to MongoDB...")
    await connect_to_mongodb(
        uri=settings.mongodb_uri,
        database_name=settings.mongodb_database,
    )
    
    # Initialize Services
    signal_repo = SignalRepository()
    emb_service = EmbeddingService(
        openai_api_key=settings.openai_api_key,
        chromadb_host=settings.chromadb_host,
        chromadb_port=settings.chromadb_port,
    )
    llm_service = LLMService(api_key=settings.openai_api_key)
    clustering_service = ClusteringService(
        embedding_service=emb_service,
        llm_service=llm_service,
        signal_repository=signal_repo,
        cluster_repository=ClusterRepository(),
    )

    operations_channel = "C01OPS"
    
    messages = [
        # Bridge Damage sequence
        {
            "text": "Hearing reports that the Main Street Bridge sustained structural damage from the flood waters. Attempting to verify.",
            "user": "U01USER1",
            "firsthand": False
        },
        {
            "text": "I'm at the Main Street Bridge now. The center piling has a massive crack and the road surface is buckling. It is NOT safe for vehicle traffic.",
            "user": "U01USER2",
            "firsthand": True
        },
        {
            "text": "Main Street Bridge looks fine from my drone footage, no visible buckling on the surface.",
            "user": "U01USER3",
            "firsthand": False
        },  # This should trigger a conflict
        
        # Shelter sequence
        {
            "text": "Shelter Alpha is nearing capacity, currently at 85% full (approx 425 people). We need more cots.",
            "user": "U01USER4",
            "firsthand": True
        },
        {
            "text": "Just dropped off supplies at Shelter Alpha, they are completely full and turning people away.",
            "user": "U01USER5",
            "firsthand": True
        }
    ]

    logger.info("Injecting simulated scenario messages...")
    for msg in messages:
        await create_and_process_signal(
            signal_repo=signal_repo,
            clustering_service=clustering_service,
            text=msg["text"],
            channel_id=operations_channel,
            user_id=msg["user"],
            is_firsthand=msg["firsthand"]
        )
        # Add a small delay
        await asyncio.sleep(2)

    logger.info("Scenario simulation complete. Messages have been ingested and clustered.")
    await close_mongodb_connection()

if __name__ == "__main__":
    asyncio.run(main())
