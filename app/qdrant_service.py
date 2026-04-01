"""Qdrant service for memory storage - ASYNC VERSION."""
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import uuid
import logging
import httpx

logger = logging.getLogger(__name__)


class QdrantService:
    def __init__(self, host: str, collection: str, embedding_model: str, vector_size: int = 1024, ollama_host: str = "http://10.0.0.10:11434"):
        self.host = host
        self.collection = collection
        self.embedding_model = embedding_model
        self.vector_size = vector_size
        self.ollama_host = ollama_host
        # Use ASYNC client
        self.client = AsyncQdrantClient(url=host)
        self._collection_ensured = False

    async def _ensure_collection(self):
        """Ensure collection exists - lazy initialization."""
        if self._collection_ensured:
            return
        try:
            await self.client.get_collection(self.collection)
            logger.info(f"Collection {self.collection} exists")
        except Exception:
            await self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE)
            )
            logger.info(f"Created collection {self.collection} with vector size {self.vector_size}")
        self._collection_ensured = True

    async def get_embedding(self, text: str) -> List[float]:
        """Get embedding from Ollama."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.ollama_host}/api/embeddings",
                json={"model": self.embedding_model, "prompt": text},
                timeout=30.0
            )
            result = response.json()
            return result["embedding"]

    async def store_turn(self, role: str, content: str, entry_type: str = "raw", topic: Optional[str] = None, metadata: Optional[Dict] = None) -> str:
        """Store a turn in Qdrant with proper payload format."""
        await self._ensure_collection()
        
        point_id = str(uuid.uuid4())
        embedding = await self.get_embedding(content)
        
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        text = content
        if role == "user":
            text = f"User: {content}"
        elif role == "assistant":
            text = f"Assistant: {content}"
        elif role == "curated":
            text = content
        
        payload = {
            "type": entry_type,
            "text": text,
            "timestamp": timestamp,
            "role": role,
            "content": content
        }
        if topic:
            payload["topic"] = topic
        if metadata:
            payload.update(metadata)
        
        await self.client.upsert(
            collection_name=self.collection,
            points=[PointStruct(id=point_id, vector=embedding, payload=payload)]
        )
        return point_id

    async def store_qa_turn(self, user_question: str, assistant_answer: str) -> str:
        """Store a complete Q&A turn as one document."""
        await self._ensure_collection()
        
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        text = f"User: {user_question}\nAssistant: {assistant_answer}\nTimestamp: {timestamp}"
        
        point_id = str(uuid.uuid4())
        embedding = await self.get_embedding(text)
        
        payload = {
            "type": "raw",
            "text": text,
            "timestamp": timestamp,
            "role": "qa",
            "content": text
        }
        
        await self.client.upsert(
            collection_name=self.collection,
            points=[PointStruct(id=point_id, vector=embedding, payload=payload)]
        )
        return point_id

    async def semantic_search(self, query: str, limit: int = 10, score_threshold: float = 0.6, entry_type: str = "curated") -> List[Dict]:
        """Semantic search for relevant turns, filtered by type."""
        await self._ensure_collection()
        
        embedding = await self.get_embedding(query)
        
        results = await self.client.query_points(
            collection_name=self.collection,
            query=embedding,
            limit=limit,
            score_threshold=score_threshold,
            query_filter=Filter(
                must=[FieldCondition(key="type", match=MatchValue(value=entry_type))]
            )
        )
        
        return [{"id": str(r.id), "score": r.score, "payload": r.payload} for r in results.points]

    async def get_recent_turns(self, limit: int = 20) -> List[Dict]:
        """Get recent turns from Qdrant (both raw and curated)."""
        await self._ensure_collection()
        
        points, _ = await self.client.scroll(
            collection_name=self.collection,
            limit=limit * 2,
            with_payload=True
        )
        
        # Sort by timestamp descending
        sorted_points = sorted(
            points,
            key=lambda p: p.payload.get("timestamp", ""),
            reverse=True
        )
        
        return [{"id": str(p.id), "payload": p.payload} for p in sorted_points[:limit]]

    async def delete_points(self, point_ids: List[str]) -> None:
        """Delete points by ID."""
        from qdrant_client.models import PointIdsList
        await self.client.delete(
            collection_name=self.collection,
            points_selector=PointIdsList(points=point_ids)
        )
        logger.info(f"Deleted {len(point_ids)} points")

    async def close(self):
        """Close the async client."""
        await self.client.close()