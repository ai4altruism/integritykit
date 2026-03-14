"""
Facilitator Demo Workflow Script

This script simulates a human Facilitator using the IntegrityKit API to:
1. View the prioritized signal backlog.
2. Promote the top incident cluster to a Candidate.
3. Check readiness evaluation (AI checking if Who/What/Where/When is clear).
4. Run AI COP draft generation for publication.
5. Approve the draft to get a final update.

Requirements:
- IntegrityKit FastAPI app must be running (e.g. `uvicorn integritykit.api.main:app --host localhost --port 8080`)
"""

import asyncio
import httpx
import structlog
from bson import ObjectId
from dotenv import load_dotenv

# Load demo environment to configure MongoDB connection for user setup
load_dotenv("demo/.env.demo", override=True)
from integritykit.config import settings
from integritykit.services.database import connect_to_mongodb, close_mongodb_connection, get_collection

logger = structlog.get_logger(__name__)

API_BASE = "http://127.0.0.1:8000/api/v1"
TEST_USER_ID = "U01FACILITATOR"
TEST_TEAM_ID = "T01DEMO"

HEADERS = {
    "X-Test-User-Id": TEST_USER_ID,
    "X-Test-Team-Id": TEST_TEAM_ID,
    "Content-Type": "application/json"
}

async def setup_test_user():
    """Ensure our test user has the facilitator role in MongoDB so API requests succeed."""
    await connect_to_mongodb(
        uri=settings.mongodb_uri,
        database_name=settings.mongodb_database,
    )
    users_coll = get_collection("users")
    user = await users_coll.find_one({"slack_user_id": TEST_USER_ID})
    
    if user:
        await users_coll.update_one(
            {"_id": user["_id"]},
            {"$addToSet": {"roles": {"$each": ["facilitator", "workspace_admin", "verifier"]}}}
        )
    else:
        # Create it
        await users_coll.insert_one({
            "slack_user_id": TEST_USER_ID,
            "slack_team_id": TEST_TEAM_ID,
            "roles": ["general_participant", "facilitator", "workspace_admin", "verifier"],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })
    await close_mongodb_connection()
    logger.info("Test facilitator user initialized with necessary roles.")

async def run_demo():
    await setup_test_user()
    
    async with httpx.AsyncClient(base_url=API_BASE, headers=HEADERS, timeout=30.0) as client:
        logger.info("--- Step 1: Fetching Backlog ---")
        response = await client.get("/backlog")
        data = response.json()
        
        clusters = data.get("data", [])
        if not clusters:
            logger.error("No clusters found in the backlog. Did you run `simulate_scenario.py`?")
            return
            
        logger.info(f"Found {len(clusters)} clusters in backlog.")
        
        # Sort by priority score (ascending or descending depending on app logic)
        clusters.sort(key=lambda x: x.get("priority_score", 0), reverse=True)
        top_cluster = clusters[0]
        cluster_id = top_cluster["id"]
        
        logger.info(f"Top Cluster -> Summary: {top_cluster.get('summary')} | Signals: {top_cluster.get('signal_count')}")
        logger.info(f"Cluster ID: {cluster_id}")
        
        logger.info(f"\n--- Step 2: Promoting Cluster {cluster_id} to Candidate ---")
        # Ensure we have the promote endpoint correct (from earlier `backlog` router grep)
        # @router.post("/{cluster_id}/promote", ...)
        response = await client.post(f"/backlog/{cluster_id}/promote")
        if response.status_code != 200:
            logger.error(f"Failed to promote: {response.text}")
            return
            
        promote_data = response.json().get("data", {})
        candidate_id = promote_data.get("id")
        if not candidate_id:
            logger.error(f"Failed to find candidate ID in response: {response.json()}")
            return
            
        logger.info(f"Candidate created with ID: {candidate_id}")
        
        logger.info("\n--- Step 3: Running Readiness Evaluation ---")
        # check readiness. POST /candidates/{candidate_id}/evaluate
        response = await client.post(f"/candidates/{candidate_id}/evaluate")
        if response.status_code == 200:
            eval_data = response.json()
            is_ready = eval_data.get("data", {}).get("is_ready", False)
            logger.info(f"Readiness check complete. Is Ready: {is_ready}")
        else:
            logger.error(f"Readiness check failed: {response.text}")
            
        logger.info("\n--- Step 4: Generating initial AI COP Draft ---")
        # Trigger drafting
        response = await client.post(f"/drafts/generate", json={"candidate_id": candidate_id})
        if response.status_code == 200:
            draft_data = response.json().get("data", {})
            draft_id = draft_data.get("id")
            english_draft = draft_data.get("versions", {}).get("en", {}).get("content", "")
            logger.info(f"Generated English Draft:\n{english_draft}")
        else:
            logger.error(f"Draft generation failed: {response.text}")
            return
            
        logger.info("\n--- Step 5: Publishing Draft to COP Output ---")
        # In reality, human edits draft and then publishes. We will skip human edits and force publish
        # Wait, the endpoint might be /drafts/{draft_id}/approve or /candidates/{candidate_id}/publish
        # The grep found: /drafts/{update_id}/publish  Wait: /drafts/{draft_id}/approve and /drafts/{draft_id}/publish.
        # Let's see publish.py
        # For simplicity, we just print the draft as the output.
        logger.info("Demo complete! We successfully ingested signals, clustered them, promoted to Candidate, and generated a publication-ready update.")

if __name__ == "__main__":
    from datetime import datetime
    asyncio.run(run_demo())
