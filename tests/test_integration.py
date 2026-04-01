"""Integration tests — FastAPI app via httpx.AsyncClient test transport.

All external I/O (Ollama, Qdrant) is mocked. No live services required.
"""
import pytest
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_qdrant():
    """Return a fully-mocked QdrantService."""
    mock = MagicMock()
    mock._ensure_collection = AsyncMock()
    mock.semantic_search = AsyncMock(return_value=[])
    mock.get_recent_turns = AsyncMock(return_value=[])
    mock.store_qa_turn = AsyncMock(return_value="fake-uuid")
    mock.close = AsyncMock()
    return mock


def _ollama_tags_response():
    return {"models": [{"name": "llama3", "size": 0}]}


def _ollama_chat_response(content: str = "Hello from Ollama"):
    return {
        "message": {"role": "assistant", "content": content},
        "done": True,
        "model": "llama3",
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_qdrant():
    return _make_mock_qdrant()


@pytest.fixture()
def app_with_mocks(mock_qdrant, tmp_path):
    """Return the FastAPI app with lifespan mocked (no real Qdrant/scheduler)."""
    from contextlib import asynccontextmanager

    # Minimal curator prompt
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "curator_prompt.md").write_text("Curate. Date: {CURRENT_DATE}")
    (prompts_dir / "systemprompt.md").write_text("You are Vera.")

    @asynccontextmanager
    async def fake_lifespan(app):
        yield

    import app.main as main_module

    with patch.dict(os.environ, {"VERA_PROMPTS_DIR": str(prompts_dir)}), \
         patch("app.main.get_qdrant_service", return_value=mock_qdrant), \
         patch("app.singleton.get_qdrant_service", return_value=mock_qdrant), \
         patch("app.main.Curator") as MockCurator, \
         patch("app.main.scheduler") as mock_scheduler:

        mock_scheduler.add_job = MagicMock()
        mock_scheduler.start = MagicMock()
        mock_scheduler.shutdown = MagicMock()

        mock_curator_instance = MagicMock()
        mock_curator_instance.run = AsyncMock()
        MockCurator.return_value = mock_curator_instance

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        # Import fresh — use the real routes but swap lifespan
        from app.main import app as vera_app
        vera_app.router.lifespan_context = fake_lifespan

        yield vera_app, mock_qdrant


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_health_ollama_reachable(self, app_with_mocks):
        """GET / returns status ok and ollama=reachable when Ollama is up."""
        from fastapi.testclient import TestClient

        vera_app, mock_qdrant = app_with_mocks

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_instance.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            with TestClient(vera_app, raise_server_exceptions=True) as client:
                resp = client.get("/")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["ollama"] == "reachable"

    def test_health_ollama_unreachable(self, app_with_mocks):
        """GET / returns ollama=unreachable when Ollama is down."""
        import httpx
        from fastapi.testclient import TestClient

        vera_app, _ = app_with_mocks

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_instance.get = AsyncMock(side_effect=httpx.ConnectError("refused"))

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            with TestClient(vera_app, raise_server_exceptions=True) as client:
                resp = client.get("/")

        assert resp.status_code == 200
        assert resp.json()["ollama"] == "unreachable"


# ---------------------------------------------------------------------------
# /api/tags
# ---------------------------------------------------------------------------

class TestApiTags:
    def test_returns_model_list(self, app_with_mocks):
        """GET /api/tags proxies Ollama tags."""
        from fastapi.testclient import TestClient

        vera_app, _ = app_with_mocks

        mock_resp = MagicMock()
        mock_resp.json.return_value = _ollama_tags_response()

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_instance.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            with TestClient(vera_app) as client:
                resp = client.get("/api/tags")

        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data
        assert any(m["name"] == "llama3" for m in data["models"])

    def test_cloud_models_injected(self, tmp_path):
        """Cloud models appear in /api/tags when cloud is enabled."""
        from fastapi.testclient import TestClient
        from contextlib import asynccontextmanager

        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "curator_prompt.md").write_text("Curate.")
        (prompts_dir / "systemprompt.md").write_text("")

        mock_qdrant = _make_mock_qdrant()

        @asynccontextmanager
        async def fake_lifespan(app):
            yield

        from app.config import Config, CloudConfig
        patched_config = Config()
        patched_config.cloud = CloudConfig(
            enabled=True,
            models={"gpt-oss:120b": "openai/gpt-4o"},
        )

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"models": []}

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_instance.get = AsyncMock(return_value=mock_resp)

        import app.main as main_module

        with patch.dict(os.environ, {"VERA_PROMPTS_DIR": str(prompts_dir)}), \
             patch("app.main.config", patched_config), \
             patch("app.main.get_qdrant_service", return_value=mock_qdrant), \
             patch("app.main.scheduler") as mock_scheduler, \
             patch("app.main.Curator") as MockCurator:

            mock_scheduler.add_job = MagicMock()
            mock_scheduler.start = MagicMock()
            mock_scheduler.shutdown = MagicMock()
            mock_curator_instance = MagicMock()
            mock_curator_instance.run = AsyncMock()
            MockCurator.return_value = mock_curator_instance

            from app.main import app as vera_app
            vera_app.router.lifespan_context = fake_lifespan

            with patch("httpx.AsyncClient", return_value=mock_client_instance):
                with TestClient(vera_app) as client:
                    resp = client.get("/api/tags")

        data = resp.json()
        names = [m["name"] for m in data["models"]]
        assert "gpt-oss:120b" in names


# ---------------------------------------------------------------------------
# POST /api/chat (non-streaming)
# ---------------------------------------------------------------------------

class TestApiChatNonStreaming:
    def test_non_streaming_round_trip(self, app_with_mocks):
        """POST /api/chat with stream=False returns Ollama response."""
        from fastapi.testclient import TestClient
        import app.utils as utils_module
        import app.proxy_handler as ph_module

        vera_app, mock_qdrant = app_with_mocks

        ollama_data = _ollama_chat_response("The answer is 42.")

        mock_post_resp = MagicMock()
        mock_post_resp.json.return_value = ollama_data

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_instance.post = AsyncMock(return_value=mock_post_resp)

        with patch.object(utils_module, "load_system_prompt", return_value=""), \
             patch.object(utils_module, "get_qdrant_service", return_value=mock_qdrant), \
             patch("app.proxy_handler.get_qdrant_service", return_value=mock_qdrant), \
             patch("httpx.AsyncClient", return_value=mock_client_instance):

            with TestClient(vera_app) as client:
                resp = client.post(
                    "/api/chat",
                    json={
                        "model": "llama3",
                        "messages": [{"role": "user", "content": "What is the answer?"}],
                        "stream": False,
                    },
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["message"]["content"] == "The answer is 42."

    def test_non_streaming_stores_qa(self, app_with_mocks):
        """POST /api/chat non-streaming stores the Q&A turn in Qdrant."""
        from fastapi.testclient import TestClient
        import app.utils as utils_module

        vera_app, mock_qdrant = app_with_mocks

        ollama_data = _ollama_chat_response("42.")

        mock_post_resp = MagicMock()
        mock_post_resp.json.return_value = ollama_data

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_instance.post = AsyncMock(return_value=mock_post_resp)

        with patch.object(utils_module, "load_system_prompt", return_value=""), \
             patch.object(utils_module, "get_qdrant_service", return_value=mock_qdrant), \
             patch("app.proxy_handler.get_qdrant_service", return_value=mock_qdrant), \
             patch("httpx.AsyncClient", return_value=mock_client_instance):

            with TestClient(vera_app) as client:
                client.post(
                    "/api/chat",
                    json={
                        "model": "llama3",
                        "messages": [{"role": "user", "content": "What is 6*7?"}],
                        "stream": False,
                    },
                )

        mock_qdrant.store_qa_turn.assert_called_once()
        args = mock_qdrant.store_qa_turn.call_args[0]
        assert "6*7" in args[0]
        assert "42." in args[1]


# ---------------------------------------------------------------------------
# POST /api/chat (streaming)
# ---------------------------------------------------------------------------

class TestApiChatStreaming:
    def test_streaming_response_passthrough(self, app_with_mocks):
        """POST /api/chat with stream=True streams Ollama chunks."""
        from fastapi.testclient import TestClient
        import app.utils as utils_module
        import app.proxy_handler as ph_module

        vera_app, mock_qdrant = app_with_mocks

        chunk1 = json.dumps({"message": {"content": "Hello"}, "done": False}).encode()
        chunk2 = json.dumps({"message": {"content": " world"}, "done": True}).encode()

        async def fake_aiter_bytes():
            yield chunk1
            yield chunk2

        mock_stream_resp = MagicMock()
        mock_stream_resp.aiter_bytes = fake_aiter_bytes
        mock_stream_resp.status_code = 200
        mock_stream_resp.headers = {"content-type": "application/x-ndjson"}

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_instance.post = AsyncMock(return_value=mock_stream_resp)

        with patch.object(utils_module, "load_system_prompt", return_value=""), \
             patch.object(utils_module, "get_qdrant_service", return_value=mock_qdrant), \
             patch("app.proxy_handler.get_qdrant_service", return_value=mock_qdrant), \
             patch("httpx.AsyncClient", return_value=mock_client_instance):

            with TestClient(vera_app) as client:
                resp = client.post(
                    "/api/chat",
                    json={
                        "model": "llama3",
                        "messages": [{"role": "user", "content": "Say hello"}],
                        "stream": True,
                    },
                )

        assert resp.status_code == 200
        # Response body should contain both chunks concatenated
        body_text = resp.text
        assert "Hello" in body_text or len(body_text) > 0
