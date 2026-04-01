"""Tests for proxy_handler — no live Ollama or Qdrant required."""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch


class TestCleanMessageContent:
    """Tests for clean_message_content."""

    def test_passthrough_plain_message(self):
        """Plain text without wrapper is returned unchanged."""
        from app.proxy_handler import clean_message_content

        content = "What is the capital of France?"
        assert clean_message_content(content) == content

    def test_strips_memory_context_wrapper(self):
        """[Memory context] wrapper is stripped, actual user_msg returned."""
        from app.proxy_handler import clean_message_content

        content = (
            "[Memory context]\n"
            "some context here\n"
            "- user_msg: What is the capital of France?\n\n"
        )
        result = clean_message_content(content)
        assert result == "What is the capital of France?"

    def test_strips_timestamp_prefix(self):
        """ISO timestamp prefix like [2024-01-01T00:00:00] is removed."""
        from app.proxy_handler import clean_message_content

        content = "[2024-01-01T12:34:56] Tell me a joke"
        result = clean_message_content(content)
        assert result == "Tell me a joke"

    def test_empty_string_returned_as_is(self):
        """Empty string input returns empty string."""
        from app.proxy_handler import clean_message_content

        assert clean_message_content("") == ""

    def test_none_input_returned_as_is(self):
        """None/falsy input is returned unchanged."""
        from app.proxy_handler import clean_message_content

        assert clean_message_content(None) is None

    def test_list_content_raises_type_error(self):
        """Non-string content (list) causes TypeError — the function expects strings."""
        import pytest
        from app.proxy_handler import clean_message_content

        # The function passes lists to re.search which requires str/bytes.
        # Document this behavior so we know it's a known limitation.
        content = [{"type": "text", "text": "hello"}]
        with pytest.raises(TypeError):
            clean_message_content(content)


class TestHandleChatNonStreaming:
    """Tests for handle_chat_non_streaming — fully mocked external I/O."""

    @pytest.mark.asyncio
    async def test_returns_json_response(self):
        """Should return a JSONResponse with Ollama result merged with model field."""
        from app.proxy_handler import handle_chat_non_streaming

        ollama_resp_data = {
            "message": {"role": "assistant", "content": "Paris."},
            "done": True,
        }

        mock_httpx_resp = MagicMock()
        mock_httpx_resp.json.return_value = ollama_resp_data

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_httpx_resp)

        mock_qdrant = MagicMock()
        mock_qdrant.store_qa_turn = AsyncMock(return_value="fake-uuid")

        augmented = [{"role": "user", "content": "What is the capital of France?"}]

        with patch("app.proxy_handler.build_augmented_messages", AsyncMock(return_value=augmented)), \
             patch("app.proxy_handler.get_qdrant_service", return_value=mock_qdrant), \
             patch("httpx.AsyncClient", return_value=mock_client):

            body = {
                "model": "llama3",
                "messages": [{"role": "user", "content": "What is the capital of France?"}],
                "stream": False,
            }
            response = await handle_chat_non_streaming(body)

        # FastAPI JSONResponse
        from fastapi.responses import JSONResponse
        assert isinstance(response, JSONResponse)
        response_body = json.loads(response.body)
        assert response_body["message"]["content"] == "Paris."
        assert response_body["model"] == "llama3"

    @pytest.mark.asyncio
    async def test_stores_qa_turn_when_answer_present(self):
        """store_qa_turn should be called with user question and assistant answer."""
        from app.proxy_handler import handle_chat_non_streaming

        ollama_resp_data = {
            "message": {"role": "assistant", "content": "Berlin."},
            "done": True,
        }

        mock_httpx_resp = MagicMock()
        mock_httpx_resp.json.return_value = ollama_resp_data

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_httpx_resp)

        mock_qdrant = MagicMock()
        mock_qdrant.store_qa_turn = AsyncMock(return_value="fake-uuid")

        augmented = [{"role": "user", "content": "Capital of Germany?"}]

        with patch("app.proxy_handler.build_augmented_messages", AsyncMock(return_value=augmented)), \
             patch("app.proxy_handler.get_qdrant_service", return_value=mock_qdrant), \
             patch("httpx.AsyncClient", return_value=mock_client):

            body = {
                "model": "llama3",
                "messages": [{"role": "user", "content": "Capital of Germany?"}],
                "stream": False,
            }
            await handle_chat_non_streaming(body)

        mock_qdrant.store_qa_turn.assert_called_once()
        call_args = mock_qdrant.store_qa_turn.call_args
        assert "Capital of Germany?" in call_args[0][0]
        assert "Berlin." in call_args[0][1]

    @pytest.mark.asyncio
    async def test_no_store_when_empty_answer(self):
        """store_qa_turn should NOT be called when the assistant answer is empty."""
        from app.proxy_handler import handle_chat_non_streaming

        ollama_resp_data = {
            "message": {"role": "assistant", "content": ""},
            "done": True,
        }

        mock_httpx_resp = MagicMock()
        mock_httpx_resp.json.return_value = ollama_resp_data

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_httpx_resp)

        mock_qdrant = MagicMock()
        mock_qdrant.store_qa_turn = AsyncMock(return_value="fake-uuid")

        augmented = [{"role": "user", "content": "Hello?"}]

        with patch("app.proxy_handler.build_augmented_messages", AsyncMock(return_value=augmented)), \
             patch("app.proxy_handler.get_qdrant_service", return_value=mock_qdrant), \
             patch("httpx.AsyncClient", return_value=mock_client):

            body = {
                "model": "llama3",
                "messages": [{"role": "user", "content": "Hello?"}],
                "stream": False,
            }
            await handle_chat_non_streaming(body)

        mock_qdrant.store_qa_turn.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleans_memory_context_from_user_message(self):
        """User message with [Memory context] wrapper should be cleaned before storing."""
        from app.proxy_handler import handle_chat_non_streaming

        ollama_resp_data = {
            "message": {"role": "assistant", "content": "42."},
            "done": True,
        }

        mock_httpx_resp = MagicMock()
        mock_httpx_resp.json.return_value = ollama_resp_data

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_httpx_resp)

        mock_qdrant = MagicMock()
        mock_qdrant.store_qa_turn = AsyncMock(return_value="fake-uuid")

        raw_content = (
            "[Memory context]\nsome ctx\n- user_msg: What is the answer?\n\n"
        )
        augmented = [{"role": "user", "content": "What is the answer?"}]

        with patch("app.proxy_handler.build_augmented_messages", AsyncMock(return_value=augmented)), \
             patch("app.proxy_handler.get_qdrant_service", return_value=mock_qdrant), \
             patch("httpx.AsyncClient", return_value=mock_client):

            body = {
                "model": "llama3",
                "messages": [{"role": "user", "content": raw_content}],
                "stream": False,
            }
            await handle_chat_non_streaming(body)

        call_args = mock_qdrant.store_qa_turn.call_args
        stored_question = call_args[0][0]
        # The wrapper should be stripped
        assert "Memory context" not in stored_question
        assert "What is the answer?" in stored_question
