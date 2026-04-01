"""Shared test fixtures using production-realistic data."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.config import Config


@pytest.fixture
def production_config():
    """Config matching production deployment on deb8."""
    config = MagicMock(spec=Config)
    config.ollama_host = "http://10.0.0.10:11434"
    config.qdrant_host = "http://10.0.0.22:6333"
    config.qdrant_collection = "memories"
    config.embedding_model = "snowflake-arctic-embed2"
    config.semantic_token_budget = 25000
    config.context_token_budget = 22000
    config.semantic_search_turns = 2
    config.semantic_score_threshold = 0.6
    config.run_time = "02:00"
    config.curator_model = "gpt-oss:120b"
    config.debug = False
    config.vector_size = 1024
    config.cloud = MagicMock()
    config.cloud.enabled = False
    config.cloud.models = {}
    config.cloud.get_cloud_model.return_value = None
    return config


@pytest.fixture
def sample_qdrant_raw_payload():
    """Sample raw payload from production Qdrant."""
    return {
        "type": "raw",
        "text": "User: only change settings, not models\nAssistant: Changed semantic_token_budget from 25000 to 30000\nTimestamp: 2026-03-27T12:50:37.451593Z",
        "timestamp": "2026-03-27T12:50:37.451593Z",
        "role": "qa",
        "content": "User: only change settings, not models\nAssistant: Changed semantic_token_budget from 25000 to 30000\nTimestamp: 2026-03-27T12:50:37.451593Z"
    }


@pytest.fixture
def sample_ollama_models():
    """Model list from production Ollama."""
    return {
        "models": [
            {
                "name": "snowflake-arctic-embed2:latest",
                "model": "snowflake-arctic-embed2:latest",
                "modified_at": "2026-02-16T16:43:44Z",
                "size": 1160296718,
                "details": {"family": "bert", "parameter_size": "566.70M", "quantization_level": "F16"}
            },
            {
                "name": "gpt-oss:120b",
                "model": "gpt-oss:120b",
                "modified_at": "2026-03-11T12:45:48Z",
                "size": 65369818941,
                "details": {"family": "gptoss", "parameter_size": "116.8B", "quantization_level": "MXFP4"}
            }
        ]
    }
