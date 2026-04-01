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


class TestDebugLog:
    """Tests for debug_log function."""

    def test_debug_log_writes_json_when_enabled(self, tmp_path):
        """Debug log appends valid JSON line to file when debug=True."""
        import json
        from unittest.mock import patch, MagicMock

        mock_config = MagicMock()
        mock_config.debug = True

        with patch("app.proxy_handler.config", mock_config), \
             patch("app.proxy_handler.DEBUG_LOG_DIR", tmp_path):
            from app.proxy_handler import debug_log
            debug_log("test_cat", "test message", {"key": "value"})

        log_files = list(tmp_path.glob("debug_*.log"))
        assert len(log_files) == 1
        content = log_files[0].read_text().strip()
        entry = json.loads(content)
        assert entry["category"] == "test_cat"
        assert entry["message"] == "test message"
        assert entry["data"]["key"] == "value"

    def test_debug_log_skips_when_disabled(self, tmp_path):
        """Debug log does nothing when debug=False."""
        from unittest.mock import patch, MagicMock

        mock_config = MagicMock()
        mock_config.debug = False

        with patch("app.proxy_handler.config", mock_config), \
             patch("app.proxy_handler.DEBUG_LOG_DIR", tmp_path):
            from app.proxy_handler import debug_log
            debug_log("test_cat", "test message")

        log_files = list(tmp_path.glob("debug_*.log"))
        assert len(log_files) == 0

    def test_debug_log_without_data(self, tmp_path):
        """Debug log works without optional data parameter."""
        import json
        from unittest.mock import patch, MagicMock

        mock_config = MagicMock()
        mock_config.debug = True

        with patch("app.proxy_handler.config", mock_config), \
             patch("app.proxy_handler.DEBUG_LOG_DIR", tmp_path):
            from app.proxy_handler import debug_log
            debug_log("simple_cat", "no data here")

        log_files = list(tmp_path.glob("debug_*.log"))
        assert len(log_files) == 1
        entry = json.loads(log_files[0].read_text().strip())
        assert "data" not in entry
        assert entry["category"] == "simple_cat"


class TestForwardToOllama:
    """Tests for forward_to_ollama function."""

    @pytest.mark.asyncio
    async def test_forwards_request_to_ollama(self):
        """forward_to_ollama proxies request to Ollama host."""
        from app.proxy_handler import forward_to_ollama
        from unittest.mock import patch, AsyncMock, MagicMock

        mock_request = AsyncMock()
        mock_request.body = AsyncMock(return_value=b'{"model": "llama3"}')
        mock_request.method = "POST"
        mock_request.headers = {"content-type": "application/json", "content-length": "20"}

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.request = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await forward_to_ollama(mock_request, "/api/show")

        assert result == mock_resp
        mock_client.request.assert_called_once()
        call_kwargs = mock_client.request.call_args
        assert call_kwargs[1]["method"] == "POST"
        assert "/api/show" in call_kwargs[1]["url"]
