"""Tests for Curator class methods — no live LLM or Qdrant required."""
import pytest
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch


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
