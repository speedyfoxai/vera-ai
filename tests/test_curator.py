"""Tests for Curator class methods — no live LLM or Qdrant required."""
import pytest
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch


def make_curator(tmp_path):
    """Return a Curator instance with a dummy prompt file and mock QdrantService."""
    from app.curator import Curator

    # Create a minimal curator_prompt.md so Curator.__init__ can load it
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "curator_prompt.md").write_text("Curate memories. Date: {CURRENT_DATE}")

    mock_qdrant = MagicMock()

    with patch.dict(os.environ, {"VERA_PROMPTS_DIR": str(prompts_dir)}):
        curator = Curator(
            qdrant_service=mock_qdrant,
            model="test-model",
            ollama_host="http://localhost:11434",
        )

    return curator, mock_qdrant


class TestParseJsonResponse:
    """Tests for Curator._parse_json_response."""

    def test_direct_valid_json(self, tmp_path):
        """Valid JSON string parsed directly."""
        curator, _ = make_curator(tmp_path)
        payload = {"new_curated_turns": [], "deletions": []}
        result = curator._parse_json_response(json.dumps(payload))
        assert result == payload

    def test_json_in_code_block(self, tmp_path):
        """JSON wrapped in ```json ... ``` code fence is extracted."""
        curator, _ = make_curator(tmp_path)
        payload = {"summary": "done"}
        response = f"```json\n{json.dumps(payload)}\n```"
        result = curator._parse_json_response(response)
        assert result == payload

    def test_json_embedded_in_text(self, tmp_path):
        """JSON embedded after prose text is extracted via brace scan."""
        curator, _ = make_curator(tmp_path)
        payload = {"new_curated_turns": [{"content": "Q: hi\nA: there"}]}
        response = f"Here is the result:\n{json.dumps(payload)}\nThat's all."
        result = curator._parse_json_response(response)
        assert result is not None
        assert "new_curated_turns" in result

    def test_empty_string_returns_none(self, tmp_path):
        """Empty response returns None."""
        curator, _ = make_curator(tmp_path)
        result = curator._parse_json_response("")
        assert result is None

    def test_malformed_json_returns_none(self, tmp_path):
        """Completely invalid text returns None."""
        curator, _ = make_curator(tmp_path)
        result = curator._parse_json_response("this is not json at all !!!")
        assert result is None

    def test_json_in_plain_code_block(self, tmp_path):
        """JSON in ``` (no language tag) code fence is extracted."""
        curator, _ = make_curator(tmp_path)
        payload = {"permanent_rules": []}
        response = f"```\n{json.dumps(payload)}\n```"
        result = curator._parse_json_response(response)
        assert result == payload


class TestIsRecent:
    """Tests for Curator._is_recent."""

    def test_memory_within_window(self, tmp_path):
        """Memory timestamped 1 hour ago is recent (within 24h)."""
        curator, _ = make_curator(tmp_path)
        ts = (datetime.utcnow() - timedelta(hours=1)).isoformat() + "Z"
        memory = {"timestamp": ts}
        assert curator._is_recent(memory, hours=24) is True

    def test_memory_outside_window(self, tmp_path):
        """Memory timestamped 48 hours ago is not recent."""
        curator, _ = make_curator(tmp_path)
        ts = (datetime.utcnow() - timedelta(hours=48)).isoformat() + "Z"
        memory = {"timestamp": ts}
        assert curator._is_recent(memory, hours=24) is False

    def test_no_timestamp_returns_true(self, tmp_path):
        """Memory without timestamp is treated as recent (safe default)."""
        curator, _ = make_curator(tmp_path)
        memory = {}
        assert curator._is_recent(memory, hours=24) is True

    def test_empty_timestamp_returns_true(self, tmp_path):
        """Memory with empty timestamp string is treated as recent."""
        curator, _ = make_curator(tmp_path)
        memory = {"timestamp": ""}
        assert curator._is_recent(memory, hours=24) is True

    def test_unparseable_timestamp_returns_true(self, tmp_path):
        """Memory with garbage timestamp is treated as recent (safe default)."""
        curator, _ = make_curator(tmp_path)
        memory = {"timestamp": "not-a-date"}
        assert curator._is_recent(memory, hours=24) is True

    def test_boundary_edge_just_inside(self, tmp_path):
        """Memory at exactly hours-1 minutes ago should be recent."""
        curator, _ = make_curator(tmp_path)
        ts = (datetime.utcnow() - timedelta(hours=23, minutes=59)).isoformat() + "Z"
        memory = {"timestamp": ts}
        assert curator._is_recent(memory, hours=24) is True


class TestFormatRawTurns:
    """Tests for Curator._format_raw_turns."""

    def test_empty_list(self, tmp_path):
        """Empty input produces empty string."""
        curator, _ = make_curator(tmp_path)
        result = curator._format_raw_turns([])
        assert result == ""

    def test_single_turn_header(self, tmp_path):
        """Single turn has RAW TURN 1 header and turn ID."""
        curator, _ = make_curator(tmp_path)
        turns = [{"id": "abc123", "text": "User: hello\nAssistant: hi"}]
        result = curator._format_raw_turns(turns)
        assert "RAW TURN 1" in result
        assert "abc123" in result
        assert "hello" in result

    def test_multiple_turns_numbered(self, tmp_path):
        """Multiple turns are numbered sequentially."""
        curator, _ = make_curator(tmp_path)
        turns = [
            {"id": "id1", "text": "turn one"},
            {"id": "id2", "text": "turn two"},
            {"id": "id3", "text": "turn three"},
        ]
        result = curator._format_raw_turns(turns)
        assert "RAW TURN 1" in result
        assert "RAW TURN 2" in result
        assert "RAW TURN 3" in result

    def test_missing_id_uses_unknown(self, tmp_path):
        """Turn without id field shows 'unknown' placeholder."""
        curator, _ = make_curator(tmp_path)
        turns = [{"text": "some text"}]
        result = curator._format_raw_turns(turns)
        assert "unknown" in result


class TestAppendRuleToFile:
    """Tests for Curator._append_rule_to_file (filesystem I/O mocked via tmp_path)."""

    @pytest.mark.asyncio
    async def test_appends_to_existing_file(self, tmp_path):
        """Rule is appended to existing file."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        target = prompts_dir / "systemprompt.md"
        target.write_text("# Existing content\n")

        (prompts_dir / "curator_prompt.md").write_text("prompt {CURRENT_DATE}")

        from app.curator import Curator

        mock_qdrant = MagicMock()
        with patch.dict(os.environ, {"VERA_PROMPTS_DIR": str(prompts_dir)}):
            curator = Curator(mock_qdrant, model="m", ollama_host="http://x")
            await curator._append_rule_to_file("systemprompt.md", "Always be concise.")

        content = target.read_text()
        assert "Always be concise." in content
        assert "# Existing content" in content

    @pytest.mark.asyncio
    async def test_creates_file_if_missing(self, tmp_path):
        """Rule is written to a new file if none existed."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "curator_prompt.md").write_text("prompt {CURRENT_DATE}")

        from app.curator import Curator

        mock_qdrant = MagicMock()
        with patch.dict(os.environ, {"VERA_PROMPTS_DIR": str(prompts_dir)}):
            curator = Curator(mock_qdrant, model="m", ollama_host="http://x")
            await curator._append_rule_to_file("newfile.md", "New rule here.")

        target = prompts_dir / "newfile.md"
        assert target.exists()
        assert "New rule here." in target.read_text()
