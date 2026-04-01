"""Tests for QdrantService — all Qdrant and Ollama calls are mocked."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def make_qdrant_service():
    """Create a QdrantService with mocked AsyncQdrantClient."""
    with patch("app.qdrant_service.AsyncQdrantClient") as MockClient:
        mock_client = AsyncMock()
        MockClient.return_value = mock_client

        from app.qdrant_service import QdrantService
        svc = QdrantService(
            host="http://localhost:6333",
            collection="test_memories",
            embedding_model="snowflake-arctic-embed2",
            vector_size=1024,
            ollama_host="http://localhost:11434",
        )

    return svc, mock_client


class TestEnsureCollection:
    """Tests for _ensure_collection."""

    @pytest.mark.asyncio
    async def test_creates_collection_when_missing(self):
        """Creates collection if it does not exist."""
        svc, mock_client = make_qdrant_service()
        mock_client.get_collection = AsyncMock(side_effect=Exception("not found"))
        mock_client.create_collection = AsyncMock()

        await svc._ensure_collection()

        mock_client.create_collection.assert_called_once()
        assert svc._collection_ensured is True

    @pytest.mark.asyncio
    async def test_skips_if_collection_exists(self):
        """Does not create collection if it already exists."""
        svc, mock_client = make_qdrant_service()
        mock_client.get_collection = AsyncMock(return_value=MagicMock())
        mock_client.create_collection = AsyncMock()

        await svc._ensure_collection()

        mock_client.create_collection.assert_not_called()
        assert svc._collection_ensured is True

    @pytest.mark.asyncio
    async def test_skips_if_already_ensured(self):
        """Skips entirely if _collection_ensured is True."""
        svc, mock_client = make_qdrant_service()
        svc._collection_ensured = True
        mock_client.get_collection = AsyncMock()

        await svc._ensure_collection()

        mock_client.get_collection.assert_not_called()


class TestGetEmbedding:
    """Tests for get_embedding."""

    @pytest.mark.asyncio
    async def test_returns_embedding_vector(self):
        """Returns embedding from Ollama response."""
        svc, _ = make_qdrant_service()
        fake_embedding = [0.1] * 1024

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"embedding": fake_embedding}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await svc.get_embedding("test text")

        assert result == fake_embedding
        assert len(result) == 1024


class TestStoreTurn:
    """Tests for store_turn."""

    @pytest.mark.asyncio
    async def test_stores_raw_user_turn(self):
        """Stores a user turn with proper payload."""
        svc, mock_client = make_qdrant_service()
        svc._collection_ensured = True
        mock_client.upsert = AsyncMock()

        fake_embedding = [0.1] * 1024
        with patch.object(svc, "get_embedding", AsyncMock(return_value=fake_embedding)):
            point_id = await svc.store_turn(role="user", content="hello world")

        assert isinstance(point_id, str)
        mock_client.upsert.assert_called_once()
        call_args = mock_client.upsert.call_args
        point = call_args[1]["points"][0]
        assert point.payload["type"] == "raw"
        assert point.payload["role"] == "user"
        assert "User: hello world" in point.payload["text"]

    @pytest.mark.asyncio
    async def test_stores_curated_turn(self):
        """Stores a curated turn without role prefix in text."""
        svc, mock_client = make_qdrant_service()
        svc._collection_ensured = True
        mock_client.upsert = AsyncMock()

        fake_embedding = [0.1] * 1024
        with patch.object(svc, "get_embedding", AsyncMock(return_value=fake_embedding)):
            point_id = await svc.store_turn(
                role="curated",
                content="User: q\nAssistant: a",
                entry_type="curated"
            )

        call_args = mock_client.upsert.call_args
        point = call_args[1]["points"][0]
        assert point.payload["type"] == "curated"
        # Curated text should be the content directly, not prefixed
        assert point.payload["text"] == "User: q\nAssistant: a"

    @pytest.mark.asyncio
    async def test_stores_with_topic_and_metadata(self):
        """Stores turn with optional topic and metadata."""
        svc, mock_client = make_qdrant_service()
        svc._collection_ensured = True
        mock_client.upsert = AsyncMock()

        fake_embedding = [0.1] * 1024
        with patch.object(svc, "get_embedding", AsyncMock(return_value=fake_embedding)):
            await svc.store_turn(
                role="assistant",
                content="some response",
                topic="python",
                metadata={"source": "test"}
            )

        call_args = mock_client.upsert.call_args
        point = call_args[1]["points"][0]
        assert point.payload["topic"] == "python"
        assert point.payload["source"] == "test"


class TestStoreQaTurn:
    """Tests for store_qa_turn."""

    @pytest.mark.asyncio
    async def test_stores_qa_turn(self):
        """Stores a complete Q&A turn."""
        svc, mock_client = make_qdrant_service()
        svc._collection_ensured = True
        mock_client.upsert = AsyncMock()

        fake_embedding = [0.1] * 1024
        with patch.object(svc, "get_embedding", AsyncMock(return_value=fake_embedding)):
            point_id = await svc.store_qa_turn("What is Python?", "A programming language.")

        assert isinstance(point_id, str)
        call_args = mock_client.upsert.call_args
        point = call_args[1]["points"][0]
        assert point.payload["type"] == "raw"
        assert point.payload["role"] == "qa"
        assert "What is Python?" in point.payload["text"]
        assert "A programming language." in point.payload["text"]


class TestSemanticSearch:
    """Tests for semantic_search."""

    @pytest.mark.asyncio
    async def test_returns_matching_results(self):
        """Returns formatted search results."""
        svc, mock_client = make_qdrant_service()
        svc._collection_ensured = True

        mock_point = MagicMock()
        mock_point.id = "result-1"
        mock_point.score = 0.85
        mock_point.payload = {"text": "User: hello\nAssistant: hi", "type": "curated"}

        mock_query_result = MagicMock()
        mock_query_result.points = [mock_point]
        mock_client.query_points = AsyncMock(return_value=mock_query_result)

        fake_embedding = [0.1] * 1024
        with patch.object(svc, "get_embedding", AsyncMock(return_value=fake_embedding)):
            results = await svc.semantic_search("hello", limit=10, score_threshold=0.6)

        assert len(results) == 1
        assert results[0]["id"] == "result-1"
        assert results[0]["score"] == 0.85
        assert results[0]["payload"]["type"] == "curated"


class TestGetRecentTurns:
    """Tests for get_recent_turns."""

    @pytest.mark.asyncio
    async def test_returns_sorted_recent_turns(self):
        """Returns turns sorted by timestamp descending."""
        svc, mock_client = make_qdrant_service()
        svc._collection_ensured = True

        mock_point1 = MagicMock()
        mock_point1.id = "old"
        mock_point1.payload = {"timestamp": "2026-01-01T00:00:00Z", "text": "old turn"}

        mock_point2 = MagicMock()
        mock_point2.id = "new"
        mock_point2.payload = {"timestamp": "2026-03-01T00:00:00Z", "text": "new turn"}

        mock_client.scroll = AsyncMock(return_value=([mock_point1, mock_point2], None))

        results = await svc.get_recent_turns(limit=2)

        assert len(results) == 2
        # Newest first
        assert results[0]["id"] == "new"
        assert results[1]["id"] == "old"


class TestDeletePoints:
    """Tests for delete_points."""

    @pytest.mark.asyncio
    async def test_deletes_by_ids(self):
        """Deletes points by their IDs."""
        svc, mock_client = make_qdrant_service()
        mock_client.delete = AsyncMock()

        await svc.delete_points(["id1", "id2"])

        mock_client.delete.assert_called_once()


class TestClose:
    """Tests for close."""

    @pytest.mark.asyncio
    async def test_closes_client(self):
        """Closes the async Qdrant client."""
        svc, mock_client = make_qdrant_service()
        mock_client.close = AsyncMock()

        await svc.close()

        mock_client.close.assert_called_once()
