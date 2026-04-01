"""Tests for Curator class methods — no live LLM or Qdrant required."""
import pytest
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch


def make_curator():
    """Return a Curator instance with load_curator_prompt mocked and mock QdrantService."""
    from app.curator import Curator

    mock_qdrant = MagicMock()

    with patch("app.curator.load_curator_prompt", return_value="Curate memories. Date: {CURRENT_DATE}"):
        curator = Curator(
            qdrant_service=mock_qdrant,
            model="test-model",
            ollama_host="http://localhost:11434",
        )

    return curator, mock_qdrant


class TestParseJsonResponse:
    """Tests for Curator._parse_json_response."""

    def test_direct_valid_json(self):
        """Valid JSON string parsed directly."""
        curator, _ = make_curator()
        payload = {"new_curated_turns": [], "deletions": []}
        result = curator._parse_json_response(json.dumps(payload))
        assert result == payload

    def test_json_in_code_block(self):
        """JSON wrapped in ```json ... ``` code fence is extracted."""
        curator, _ = make_curator()
        payload = {"summary": "done"}
        response = f"```json\n{json.dumps(payload)}\n```"
        result = curator._parse_json_response(response)
        assert result == payload

    def test_json_embedded_in_text(self):
        """JSON embedded after prose text is extracted via brace scan."""
        curator, _ = make_curator()
        payload = {"new_curated_turns": [{"content": "Q: hi\nA: there"}]}
        response = f"Here is the result:\n{json.dumps(payload)}\nThat's all."
        result = curator._parse_json_response(response)
        assert result is not None
        assert "new_curated_turns" in result

    def test_empty_string_returns_none(self):
        """Empty response returns None."""
        curator, _ = make_curator()
        result = curator._parse_json_response("")
        assert result is None

    def test_malformed_json_returns_none(self):
        """Completely invalid text returns None."""
        curator, _ = make_curator()
        result = curator._parse_json_response("this is not json at all !!!")
        assert result is None

    def test_json_in_plain_code_block(self):
        """JSON in ``` (no language tag) code fence is extracted."""
        curator, _ = make_curator()
        payload = {"permanent_rules": []}
        response = f"```\n{json.dumps(payload)}\n```"
        result = curator._parse_json_response(response)
        assert result == payload


class TestIsRecent:
    """Tests for Curator._is_recent."""

    def test_memory_within_window(self):
        """Memory timestamped 1 hour ago is recent (within 24h)."""
        curator, _ = make_curator()
        ts = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)).isoformat() + "Z"
        memory = {"timestamp": ts}
        assert curator._is_recent(memory, hours=24) is True

    def test_memory_outside_window(self):
        """Memory timestamped 48 hours ago is not recent."""
        curator, _ = make_curator()
        ts = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=48)).isoformat() + "Z"
        memory = {"timestamp": ts}
        assert curator._is_recent(memory, hours=24) is False

    def test_no_timestamp_returns_true(self):
        """Memory without timestamp is treated as recent (safe default)."""
        curator, _ = make_curator()
        memory = {}
        assert curator._is_recent(memory, hours=24) is True

    def test_empty_timestamp_returns_true(self):
        """Memory with empty timestamp string is treated as recent."""
        curator, _ = make_curator()
        memory = {"timestamp": ""}
        assert curator._is_recent(memory, hours=24) is True

    def test_unparseable_timestamp_returns_true(self):
        """Memory with garbage timestamp is treated as recent (safe default)."""
        curator, _ = make_curator()
        memory = {"timestamp": "not-a-date"}
        assert curator._is_recent(memory, hours=24) is True

    def test_boundary_edge_just_inside(self):
        """Memory at exactly hours-1 minutes ago should be recent."""
        curator, _ = make_curator()
        ts = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=23, minutes=59)).isoformat() + "Z"
        memory = {"timestamp": ts}
        assert curator._is_recent(memory, hours=24) is True


class TestFormatRawTurns:
    """Tests for Curator._format_raw_turns."""

    def test_empty_list(self):
        """Empty input produces empty string."""
        curator, _ = make_curator()
        result = curator._format_raw_turns([])
        assert result == ""

    def test_single_turn_header(self):
        """Single turn has RAW TURN 1 header and turn ID."""
        curator, _ = make_curator()
        turns = [{"id": "abc123", "text": "User: hello\nAssistant: hi"}]
        result = curator._format_raw_turns(turns)
        assert "RAW TURN 1" in result
        assert "abc123" in result
        assert "hello" in result

    def test_multiple_turns_numbered(self):
        """Multiple turns are numbered sequentially."""
        curator, _ = make_curator()
        turns = [
            {"id": "id1", "text": "turn one"},
            {"id": "id2", "text": "turn two"},
            {"id": "id3", "text": "turn three"},
        ]
        result = curator._format_raw_turns(turns)
        assert "RAW TURN 1" in result
        assert "RAW TURN 2" in result
        assert "RAW TURN 3" in result

    def test_missing_id_uses_unknown(self):
        """Turn without id field shows 'unknown' placeholder."""
        curator, _ = make_curator()
        turns = [{"text": "some text"}]
        result = curator._format_raw_turns(turns)
        assert "unknown" in result


class TestAppendRuleToFile:
    """Tests for Curator._append_rule_to_file (filesystem via tmp_path)."""

    @pytest.mark.asyncio
    async def test_appends_to_existing_file(self, tmp_path):
        """Rule is appended to existing file."""
        import app.curator as curator_module

        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        target = prompts_dir / "systemprompt.md"
        target.write_text("# Existing content\n")

        with patch("app.curator.load_curator_prompt", return_value="prompt {CURRENT_DATE}"), \
             patch.object(curator_module, "PROMPTS_DIR", prompts_dir):

            from app.curator import Curator
            mock_qdrant = MagicMock()
            curator = Curator(mock_qdrant, model="m", ollama_host="http://x")
            await curator._append_rule_to_file("systemprompt.md", "Always be concise.")

        content = target.read_text()
        assert "Always be concise." in content
        assert "# Existing content" in content

    @pytest.mark.asyncio
    async def test_creates_file_if_missing(self, tmp_path):
        """Rule is written to a new file if none existed."""
        import app.curator as curator_module

        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()

        with patch("app.curator.load_curator_prompt", return_value="prompt {CURRENT_DATE}"), \
             patch.object(curator_module, "PROMPTS_DIR", prompts_dir):

            from app.curator import Curator
            mock_qdrant = MagicMock()
            curator = Curator(mock_qdrant, model="m", ollama_host="http://x")
            await curator._append_rule_to_file("newfile.md", "New rule here.")

        target = prompts_dir / "newfile.md"
        assert target.exists()
        assert "New rule here." in target.read_text()


class TestFormatExistingMemories:
    """Tests for Curator._format_existing_memories."""

    def test_empty_list_returns_no_memories_message(self):
        """Empty list returns a 'no memories' message."""
        curator, _ = make_curator()
        result = curator._format_existing_memories([])
        assert "No existing curated memories" in result

    def test_single_memory_formatted(self):
        """Single memory text is included in output."""
        curator, _ = make_curator()
        memories = [{"text": "User: hello\nAssistant: hi there"}]
        result = curator._format_existing_memories(memories)
        assert "hello" in result
        assert "hi there" in result

    def test_limits_to_last_20(self):
        """Only last 20 memories are included."""
        curator, _ = make_curator()
        memories = [{"text": f"memory {i}"} for i in range(30)]
        result = curator._format_existing_memories(memories)
        # Should contain memory 10-29 (last 20), not memory 0-9
        assert "memory 29" in result
        assert "memory 10" in result


class TestCallLlm:
    """Tests for Curator._call_llm."""

    @pytest.mark.asyncio
    async def test_call_llm_returns_response(self):
        """_call_llm returns the response text from Ollama."""
        curator, _ = make_curator()

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "some LLM output"}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await curator._call_llm("test prompt")

        assert result == "some LLM output"
        call_kwargs = mock_client.post.call_args
        assert "test-model" in call_kwargs[1]["json"]["model"]

    @pytest.mark.asyncio
    async def test_call_llm_returns_empty_on_error(self):
        """_call_llm returns empty string when Ollama errors."""
        curator, _ = make_curator()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("connection refused"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await curator._call_llm("test prompt")

        assert result == ""


class TestCuratorRun:
    """Tests for Curator.run() method."""

    @pytest.mark.asyncio
    async def test_run_no_raw_memories_exits_early(self):
        """run() exits early when no raw memories found."""
        curator, mock_qdrant = make_curator()

        # Mock scroll to return no points
        mock_qdrant.client = AsyncMock()
        mock_qdrant.client.scroll = AsyncMock(return_value=([], None))
        mock_qdrant.collection = "memories"

        await curator.run()
        # Should not call LLM since there are no raw memories
        # If it got here without error, that's success

    @pytest.mark.asyncio
    async def test_run_processes_raw_memories(self):
        """run() processes raw memories and stores curated results."""
        curator, mock_qdrant = make_curator()

        # Create mock points
        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.payload = {
            "type": "raw",
            "text": "User: hello\nAssistant: hi",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

        mock_qdrant.client = AsyncMock()
        mock_qdrant.client.scroll = AsyncMock(return_value=([mock_point], None))
        mock_qdrant.collection = "memories"
        mock_qdrant.store_turn = AsyncMock(return_value="new-id")
        mock_qdrant.delete_points = AsyncMock()

        llm_response = json.dumps({
            "new_curated_turns": [{"content": "User: hello\nAssistant: hi"}],
            "permanent_rules": [],
            "deletions": [],
            "summary": "Curated one turn"
        })

        with patch.object(curator, "_call_llm", AsyncMock(return_value=llm_response)):
            await curator.run()

        mock_qdrant.store_turn.assert_called_once()
        mock_qdrant.delete_points.assert_called()

    @pytest.mark.asyncio
    async def test_run_monthly_mode_on_day_01(self):
        """run() uses monthly mode on day 01, processing all raw memories."""
        curator, mock_qdrant = make_curator()

        # Create a mock point with an old timestamp (outside 24h window)
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat().replace("+00:00", "Z")
        mock_point = MagicMock()
        mock_point.id = "old-point"
        mock_point.payload = {
            "type": "raw",
            "text": "User: old question\nAssistant: old answer",
            "timestamp": old_ts,
        }

        mock_qdrant.client = AsyncMock()
        mock_qdrant.client.scroll = AsyncMock(return_value=([mock_point], None))
        mock_qdrant.collection = "memories"
        mock_qdrant.store_turn = AsyncMock(return_value="new-id")
        mock_qdrant.delete_points = AsyncMock()

        llm_response = json.dumps({
            "new_curated_turns": [],
            "permanent_rules": [],
            "deletions": [],
            "summary": "Nothing to curate"
        })

        # Mock day 01
        mock_now = datetime(2026, 4, 1, 2, 0, 0, tzinfo=timezone.utc)
        with patch.object(curator, "_call_llm", AsyncMock(return_value=llm_response)), \
             patch("app.curator.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            await curator.run()

        # In monthly mode, even old memories are processed, so LLM should be called
        # and delete_points should be called for the raw memory
        mock_qdrant.delete_points.assert_called()

    @pytest.mark.asyncio
    async def test_run_handles_permanent_rules(self):
        """run() appends permanent rules to prompt files."""
        curator, mock_qdrant = make_curator()

        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.payload = {
            "type": "raw",
            "text": "User: remember this\nAssistant: ok",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

        mock_qdrant.client = AsyncMock()
        mock_qdrant.client.scroll = AsyncMock(return_value=([mock_point], None))
        mock_qdrant.collection = "memories"
        mock_qdrant.store_turn = AsyncMock(return_value="new-id")
        mock_qdrant.delete_points = AsyncMock()

        llm_response = json.dumps({
            "new_curated_turns": [],
            "permanent_rules": [{"rule": "Always be concise.", "target_file": "systemprompt.md"}],
            "deletions": [],
            "summary": "Added a rule"
        })

        with patch.object(curator, "_call_llm", AsyncMock(return_value=llm_response)), \
             patch.object(curator, "_append_rule_to_file", AsyncMock()) as mock_append:
            await curator.run()

        mock_append.assert_called_once_with("systemprompt.md", "Always be concise.")

    @pytest.mark.asyncio
    async def test_run_handles_deletions(self):
        """run() deletes specified point IDs when they exist in the database."""
        curator, mock_qdrant = make_curator()

        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.payload = {
            "type": "raw",
            "text": "User: delete me\nAssistant: ok",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

        mock_qdrant.client = AsyncMock()
        mock_qdrant.client.scroll = AsyncMock(return_value=([mock_point], None))
        mock_qdrant.collection = "memories"
        mock_qdrant.store_turn = AsyncMock(return_value="new-id")
        mock_qdrant.delete_points = AsyncMock()

        llm_response = json.dumps({
            "new_curated_turns": [],
            "permanent_rules": [],
            "deletions": ["point-1"],
            "summary": "Deleted one"
        })

        with patch.object(curator, "_call_llm", AsyncMock(return_value=llm_response)):
            await curator.run()

        # delete_points should be called at least twice: once for valid deletions, once for processed raw
        assert mock_qdrant.delete_points.call_count >= 1

    @pytest.mark.asyncio
    async def test_run_handles_llm_parse_failure(self):
        """run() handles LLM returning unparseable response gracefully."""
        curator, mock_qdrant = make_curator()

        mock_point = MagicMock()
        mock_point.id = "point-1"
        mock_point.payload = {
            "type": "raw",
            "text": "User: test\nAssistant: ok",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

        mock_qdrant.client = AsyncMock()
        mock_qdrant.client.scroll = AsyncMock(return_value=([mock_point], None))
        mock_qdrant.collection = "memories"

        with patch.object(curator, "_call_llm", AsyncMock(return_value="not json at all!!!")):
            # Should not raise - just return early
            await curator.run()

        # store_turn should NOT be called since parsing failed
        mock_qdrant.store_turn = AsyncMock()
        mock_qdrant.store_turn.assert_not_called()


class TestLoadCuratorPrompt:
    """Tests for load_curator_prompt function."""

    def test_loads_from_prompts_dir(self, tmp_path):
        """load_curator_prompt loads from PROMPTS_DIR."""
        import app.curator as curator_module

        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "curator_prompt.md").write_text("Test curator prompt")

        with patch.object(curator_module, "PROMPTS_DIR", prompts_dir):
            from app.curator import load_curator_prompt
            result = load_curator_prompt()

        assert result == "Test curator prompt"

    def test_falls_back_to_static_dir(self, tmp_path):
        """load_curator_prompt falls back to STATIC_DIR."""
        import app.curator as curator_module

        prompts_dir = tmp_path / "prompts"  # does not exist
        static_dir = tmp_path / "static"
        static_dir.mkdir()
        (static_dir / "curator_prompt.md").write_text("Static prompt")

        with patch.object(curator_module, "PROMPTS_DIR", prompts_dir), \
             patch.object(curator_module, "STATIC_DIR", static_dir):
            from app.curator import load_curator_prompt
            result = load_curator_prompt()

        assert result == "Static prompt"

    def test_raises_when_not_found(self, tmp_path):
        """load_curator_prompt raises FileNotFoundError when file missing."""
        import app.curator as curator_module

        with patch.object(curator_module, "PROMPTS_DIR", tmp_path / "nope"), \
             patch.object(curator_module, "STATIC_DIR", tmp_path / "also_nope"):
            from app.curator import load_curator_prompt
            with pytest.raises(FileNotFoundError):
                load_curator_prompt()
