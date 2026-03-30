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