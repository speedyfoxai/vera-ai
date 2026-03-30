"""Tests for configuration."""
import pytest
from pathlib import Path
from app.config import Config, EMBEDDING_DIMS


class TestConfig:
    """Tests for Config class."""

    def test_default_values(self):
        """Config should have sensible defaults."""
        config = Config()
        assert config.ollama_host == "http://10.0.0.10:11434"
        assert config.qdrant_host == "http://10.0.0.22:6333"
        assert config.qdrant_collection == "memories"
        assert config.embedding_model == "snowflake-arctic-embed2"

    def test_vector_size_property(self):
        """Vector size should match embedding model."""
        config = Config(embedding_model="snowflake-arctic-embed2")
        assert config.vector_size == 1024

    def test_vector_size_fallback(self):
        """Unknown model should default to 1024."""
        config = Config(embedding_model="unknown-model")
        assert config.vector_size == 1024


class TestEmbeddingDims:
    """Tests for embedding dimensions mapping."""

    def test_snowflake_arctic_embed2(self):
        """snowflake-arctic-embed2 should have 1024 dimensions."""
        assert EMBEDDING_DIMS["snowflake-arctic-embed2"] == 1024

    def test_nomic_embed_text(self):
        """nomic-embed-text should have 768 dimensions."""
        assert EMBEDDING_DIMS["nomic-embed-text"] == 768

    def test_mxbai_embed_large(self):
        """mxbai-embed-large should have 1024 dimensions."""
        assert EMBEDDING_DIMS["mxbai-embed-large"] == 1024