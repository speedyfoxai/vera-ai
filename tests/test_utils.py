"""Tests for utility functions."""
import pytest
from app.utils import count_tokens, truncate_by_tokens, parse_curated_turn


class TestCountTokens:
    """Tests for count_tokens function."""

    def test_empty_string(self):
        """Empty string should return 0 tokens."""
        assert count_tokens("") == 0

    def test_simple_text(self):
        """Simple text should count tokens correctly."""
        text = "Hello, world!"
        assert count_tokens(text) > 0

    def test_longer_text(self):
        """Longer text should have more tokens."""
        short = "Hello"
        long = "Hello, this is a longer sentence with more words."
        assert count_tokens(long) > count_tokens(short)


class TestTruncateByTokens:
    """Tests for truncate_by_tokens function."""

    def test_no_truncation_needed(self):
        """Text shorter than limit should not be truncated."""
        text = "Short text"
        result = truncate_by_tokens(text, max_tokens=100)
        assert result == text

    def test_truncation_applied(self):
        """Text longer than limit should be truncated."""
        text = "This is a longer piece of text that will need to be truncated"
        result = truncate_by_tokens(text, max_tokens=5)
        assert count_tokens(result) <= 5

    def test_empty_string(self):
        """Empty string should return empty string."""
        assert truncate_by_tokens("", max_tokens=10) == ""


class TestParseCuratedTurn:
    """Tests for parse_curated_turn function."""

    def test_empty_string(self):
        """Empty string should return empty list."""
        assert parse_curated_turn("") == []

    def test_single_turn(self):
        """Single Q&A turn should parse correctly."""
        text = "User: What is Python?\nAssistant: A programming language."
        result = parse_curated_turn(text)
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "What is Python?"
        assert result[1]["role"] == "assistant"
        assert result[1]["content"] == "A programming language."

    def test_multiple_turns(self):
        """Multiple Q&A turns should parse correctly."""
        text = """User: What is Python?
Assistant: A programming language.
User: Is it popular?
Assistant: Yes, very popular."""
        result = parse_curated_turn(text)
        assert len(result) == 4

    def test_timestamp_ignored(self):
        """Timestamp lines should be ignored."""
        text = "User: Question?\nAssistant: Answer.\nTimestamp: 2024-01-01T00:00:00Z"
        result = parse_curated_turn(text)
        assert len(result) == 2
        for msg in result:
            assert "Timestamp" not in msg["content"]

    def test_multiline_content(self):
        """Multiline content should be preserved."""
        text = "User: Line 1\nLine 2\nLine 3\nAssistant: Response"
        result = parse_curated_turn(text)
        assert "Line 1" in result[0]["content"]
        assert "Line 2" in result[0]["content"]
        assert "Line 3" in result[0]["content"]


class TestFilterMemoriesByTime:
    """Tests for filter_memories_by_time function."""

    def test_includes_recent_memory(self):
        """Memory with timestamp in the last 24h should be included."""
        from datetime import datetime, timedelta, timezone
        from app.utils import filter_memories_by_time

        ts = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)).isoformat()
        memories = [{"timestamp": ts, "text": "recent"}]
        result = filter_memories_by_time(memories, hours=24)
        assert len(result) == 1

    def test_excludes_old_memory(self):
        """Memory older than cutoff should be excluded."""
        from datetime import datetime, timedelta, timezone
        from app.utils import filter_memories_by_time

        ts = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=48)).isoformat()
        memories = [{"timestamp": ts, "text": "old"}]
        result = filter_memories_by_time(memories, hours=24)
        assert len(result) == 0

    def test_includes_memory_without_timestamp(self):
        """Memory with no timestamp should always be included."""
        from app.utils import filter_memories_by_time

        memories = [{"text": "no ts"}]
        result = filter_memories_by_time(memories, hours=24)
        assert len(result) == 1

    def test_includes_memory_with_bad_timestamp(self):
        """Memory with unparseable timestamp should be included (safe default)."""
        from app.utils import filter_memories_by_time

        memories = [{"timestamp": "not-a-date", "text": "bad ts"}]
        result = filter_memories_by_time(memories, hours=24)
        assert len(result) == 1

    def test_empty_list(self):
        """Empty input returns empty list."""
        from app.utils import filter_memories_by_time

        assert filter_memories_by_time([], hours=24) == []

    def test_z_suffix_timestamp(self):
        """ISO timestamp with Z suffix should be handled correctly."""
        from datetime import datetime, timedelta, timezone
        from app.utils import filter_memories_by_time

        ts = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)).isoformat() + "Z"
        memories = [{"timestamp": ts, "text": "recent with Z"}]
        result = filter_memories_by_time(memories, hours=24)
        assert len(result) == 1


class TestMergeMemories:
    """Tests for merge_memories function."""

    def test_empty_list(self):
        """Empty list returns empty text and ids."""
        from app.utils import merge_memories

        result = merge_memories([])
        assert result == {"text": "", "ids": []}

    def test_single_memory_with_text(self):
        """Single memory with text field is merged."""
        from app.utils import merge_memories

        memories = [{"id": "abc", "text": "hello world", "role": ""}]
        result = merge_memories(memories)
        assert "hello world" in result["text"]
        assert "abc" in result["ids"]

    def test_memory_with_content_field(self):
        """Memory using content field (no text) is merged."""
        from app.utils import merge_memories

        memories = [{"id": "xyz", "content": "from content field"}]
        result = merge_memories(memories)
        assert "from content field" in result["text"]

    def test_role_included_in_output(self):
        """Role prefix should appear in merged text when role is set."""
        from app.utils import merge_memories

        memories = [{"id": "1", "text": "question", "role": "user"}]
        result = merge_memories(memories)
        assert "[user]:" in result["text"]

    def test_multiple_memories_joined(self):
        """Multiple memories are joined with double newline."""
        from app.utils import merge_memories

        memories = [
            {"id": "1", "text": "first"},
            {"id": "2", "text": "second"},
        ]
        result = merge_memories(memories)
        assert "first" in result["text"]
        assert "second" in result["text"]
        assert len(result["ids"]) == 2


class TestCalculateTokenBudget:
    """Tests for calculate_token_budget function."""

    def test_default_ratios_sum(self):
        """Default ratios should sum to 1.0 (system+semantic+context)."""
        from app.utils import calculate_token_budget

        result = calculate_token_budget(1000)
        assert result["system"] + result["semantic"] + result["context"] == 1000

    def test_custom_ratios(self):
        """Custom ratios should produce correct proportional budgets."""
        from app.utils import calculate_token_budget

        result = calculate_token_budget(
            100, system_ratio=0.1, semantic_ratio=0.6, context_ratio=0.3
        )
        assert result["system"] == 10
        assert result["semantic"] == 60
        assert result["context"] == 30

    def test_zero_budget(self):
        """Zero total budget yields all zeros."""
        from app.utils import calculate_token_budget

        result = calculate_token_budget(0)
        assert result["system"] == 0
        assert result["semantic"] == 0
        assert result["context"] == 0


class TestBuildAugmentedMessages:
    """Tests for build_augmented_messages function (mocked I/O)."""

    def _make_qdrant_mock(self):
        """Return an AsyncMock QdrantService."""
        from unittest.mock import AsyncMock, MagicMock

        mock_qdrant = MagicMock()
        mock_qdrant.semantic_search = AsyncMock(return_value=[])
        mock_qdrant.get_recent_turns = AsyncMock(return_value=[])
        return mock_qdrant

    def test_system_layer_prepended(self, monkeypatch, tmp_path):
        """System prompt from file should be prepended to messages."""
        import asyncio
        from unittest.mock import patch
        import app.utils as utils_module

        # Write a temp system prompt
        prompt_file = tmp_path / "systemprompt.md"
        prompt_file.write_text("You are Vera.")

        mock_qdrant = self._make_qdrant_mock()

        with patch.object(utils_module, "load_system_prompt", return_value="You are Vera."), \
             patch.object(utils_module, "get_qdrant_service", return_value=mock_qdrant):
            result = asyncio.get_event_loop().run_until_complete(
                utils_module.build_augmented_messages(
                    [{"role": "user", "content": "Hello"}]
                )
            )

        system_msgs = [m for m in result if m["role"] == "system"]
        assert len(system_msgs) == 1
        assert "You are Vera." in system_msgs[0]["content"]

    def test_incoming_user_message_preserved(self, monkeypatch):
        """Incoming user message should appear in output."""
        import asyncio
        from unittest.mock import patch
        import app.utils as utils_module

        mock_qdrant = self._make_qdrant_mock()

        with patch.object(utils_module, "load_system_prompt", return_value=""), \
             patch.object(utils_module, "get_qdrant_service", return_value=mock_qdrant):
            result = asyncio.get_event_loop().run_until_complete(
                utils_module.build_augmented_messages(
                    [{"role": "user", "content": "What is 2+2?"}]
                )
            )

        user_msgs = [m for m in result if m.get("role") == "user"]
        assert any("2+2" in m["content"] for m in user_msgs)

    def test_no_system_message_when_no_prompt(self, monkeypatch):
        """No system message added when both incoming and file prompt are empty."""
        import asyncio
        from unittest.mock import patch
        import app.utils as utils_module

        mock_qdrant = self._make_qdrant_mock()

        with patch.object(utils_module, "load_system_prompt", return_value=""), \
             patch.object(utils_module, "get_qdrant_service", return_value=mock_qdrant):
            result = asyncio.get_event_loop().run_until_complete(
                utils_module.build_augmented_messages(
                    [{"role": "user", "content": "Hi"}]
                )
            )

        system_msgs = [m for m in result if m.get("role") == "system"]
        assert len(system_msgs) == 0

    def test_semantic_results_injected(self, monkeypatch):
        """Curated memories from semantic search should appear in output."""
        import asyncio
        from unittest.mock import patch, AsyncMock, MagicMock
        import app.utils as utils_module

        mock_qdrant = MagicMock()
        mock_qdrant.semantic_search = AsyncMock(return_value=[
            {"payload": {"text": "User: Old question?\nAssistant: Old answer."}}
        ])
        mock_qdrant.get_recent_turns = AsyncMock(return_value=[])

        with patch.object(utils_module, "load_system_prompt", return_value=""), \
             patch.object(utils_module, "get_qdrant_service", return_value=mock_qdrant):
            result = asyncio.get_event_loop().run_until_complete(
                utils_module.build_augmented_messages(
                    [{"role": "user", "content": "Tell me"}]
                )
            )

        contents = [m["content"] for m in result]
        assert any("Old question" in c or "Old answer" in c for c in contents)