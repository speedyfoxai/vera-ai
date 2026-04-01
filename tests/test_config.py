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


class TestConfigLoad:
    """Tests for Config.load() with real TOML content."""

    def test_load_from_explicit_path(self, tmp_path):
        """Config.load() should parse a TOML file at an explicit path."""
        from app.config import Config

        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[general]\n'
            'ollama_host = "http://localhost:11434"\n'
            'qdrant_host = "http://localhost:6333"\n'
            'qdrant_collection = "test_memories"\n'
        )
        cfg = Config.load(str(config_file))
        assert cfg.ollama_host == "http://localhost:11434"
        assert cfg.qdrant_host == "http://localhost:6333"
        assert cfg.qdrant_collection == "test_memories"

    def test_load_layers_section(self, tmp_path):
        """Config.load() should parse [layers] section correctly."""
        from app.config import Config

        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[layers]\n'
            'semantic_token_budget = 5000\n'
            'context_token_budget = 3000\n'
            'semantic_score_threshold = 0.75\n'
        )
        cfg = Config.load(str(config_file))
        assert cfg.semantic_token_budget == 5000
        assert cfg.context_token_budget == 3000
        assert cfg.semantic_score_threshold == 0.75

    def test_load_curator_section(self, tmp_path):
        """Config.load() should parse [curator] section correctly."""
        from app.config import Config

        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[curator]\n'
            'run_time = "03:30"\n'
            'curator_model = "mixtral:8x22b"\n'
        )
        cfg = Config.load(str(config_file))
        assert cfg.run_time == "03:30"
        assert cfg.curator_model == "mixtral:8x22b"

    def test_load_cloud_section(self, tmp_path):
        """Config.load() should parse [cloud] section correctly."""
        from app.config import Config

        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[cloud]\n'
            'enabled = true\n'
            'api_base = "https://openrouter.ai/api/v1"\n'
            'api_key_env = "MY_API_KEY"\n'
            '\n'
            '[cloud.models]\n'
            '"gpt-oss:120b" = "openai/gpt-4o"\n'
        )
        cfg = Config.load(str(config_file))
        assert cfg.cloud.enabled is True
        assert cfg.cloud.api_base == "https://openrouter.ai/api/v1"
        assert cfg.cloud.api_key_env == "MY_API_KEY"
        assert "gpt-oss:120b" in cfg.cloud.models

    def test_load_nonexistent_file_returns_defaults(self, tmp_path):
        """Config.load() with missing file should fall back to defaults."""
        from app.config import Config
        import os

        # Point config dir to a place with no config.toml
        os.environ["VERA_CONFIG_DIR"] = str(tmp_path / "noconfig")
        try:
            cfg = Config.load(str(tmp_path / "nonexistent.toml"))
        finally:
            del os.environ["VERA_CONFIG_DIR"]

        assert cfg.ollama_host == "http://10.0.0.10:11434"


class TestCloudConfig:
    """Tests for CloudConfig helper methods."""

    def test_is_cloud_model_true(self):
        """is_cloud_model returns True for registered model name."""
        from app.config import CloudConfig

        cc = CloudConfig(enabled=True, models={"gpt-oss:120b": "openai/gpt-4o"})
        assert cc.is_cloud_model("gpt-oss:120b") is True

    def test_is_cloud_model_false(self):
        """is_cloud_model returns False for unknown model name."""
        from app.config import CloudConfig

        cc = CloudConfig(enabled=True, models={"gpt-oss:120b": "openai/gpt-4o"})
        assert cc.is_cloud_model("llama3:70b") is False

    def test_get_cloud_model_existing(self):
        """get_cloud_model returns mapped cloud model ID."""
        from app.config import CloudConfig

        cc = CloudConfig(enabled=True, models={"gpt-oss:120b": "openai/gpt-4o"})
        assert cc.get_cloud_model("gpt-oss:120b") == "openai/gpt-4o"

    def test_get_cloud_model_missing(self):
        """get_cloud_model returns None for unknown name."""
        from app.config import CloudConfig

        cc = CloudConfig(enabled=True, models={})
        assert cc.get_cloud_model("unknown") is None

    def test_api_key_from_env(self, monkeypatch):
        """api_key property reads from environment variable."""
        from app.config import CloudConfig

        monkeypatch.setenv("MY_TEST_KEY", "sk-secret")
        cc = CloudConfig(api_key_env="MY_TEST_KEY")
        assert cc.api_key == "sk-secret"

    def test_api_key_missing_from_env(self, monkeypatch):
        """api_key returns None when env var is not set."""
        from app.config import CloudConfig

        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        cc = CloudConfig(api_key_env="OPENROUTER_API_KEY")
        assert cc.api_key is None