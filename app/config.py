# app/config.py
import tomllib
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Optional

# Embedding model dimensions
EMBEDDING_DIMS = {
    "nomic-embed-text": 768,
    "snowflake-arctic-embed2": 1024,
    "mxbai-embed-large": 1024,
}

# Configurable paths (can be overridden via environment)
CONFIG_DIR = Path(os.environ.get("VERA_CONFIG_DIR", "/app/config"))
PROMPTS_DIR = Path(os.environ.get("VERA_PROMPTS_DIR", "/app/prompts"))
STATIC_DIR = Path(os.environ.get("VERA_STATIC_DIR", "/app/static"))

@dataclass
class CloudConfig:
    enabled: bool = False
    api_base: str = ""
    api_key_env: str = "OPENROUTER_API_KEY"
    models: Dict[str, str] = field(default_factory=dict)
    
    @property
    def api_key(self) -> Optional[str]:
        return os.environ.get(self.api_key_env)
    
    def get_cloud_model(self, local_name: str) -> Optional[str]:
        """Get cloud model ID for a local model name."""
        return self.models.get(local_name)
    
    def is_cloud_model(self, local_name: str) -> bool:
        """Check if a Model name should be routed to cloud."""
        return local_name in self.models

@dataclass
class Config:
    ollama_host: str = "http://10.0.0.10:11434"
    qdrant_host: str = "http://10.0.0.22:6333"
    qdrant_collection: str = "memories"
    embedding_model: str = "snowflake-arctic-embed2"
    # Removed system_token_budget - system prompt is never truncated
    semantic_token_budget: int = 25000
    context_token_budget: int = 22000
    semantic_search_turns: int = 2
    semantic_score_threshold: float = 0.6  # Score threshold for semantic search
    run_time: str = "02:00"  # Daily curator time
    # Monthly mode is detected by curator_prompt.md (day 01)
    curator_model: str = "gpt-oss:120b"
    debug: bool = False
    cloud: CloudConfig = field(default_factory=CloudConfig)
    
    @property
    def vector_size(self) -> int:
        """Get vector size based on embedding model."""
        for model_name, dims in EMBEDDING_DIMS.items():
            if model_name in self.embedding_model:
                return dims
        return 1024
    
    @classmethod
    def load(cls, config_path: str = None):
        """Load config from TOML file.
        
        Search order:
        1. Explicit config_path argument
        2. VERA_CONFIG_DIR/config.toml
        3. /app/config/config.toml
        4. config.toml in app root (backward compatibility)
        """
        if config_path is None:
            # Try config directory first
            config_path = CONFIG_DIR / "config.toml"
            if not config_path.exists():
                # Fall back to app root (backward compatibility)
                config_path = Path(__file__).parent.parent / "config.toml"
        else:
            config_path = Path(config_path)
        
        config = cls()
        
        if config_path.exists():
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
            
            if "general" in data:
                config.ollama_host = data["general"].get("ollama_host", config.ollama_host)
                config.qdrant_host = data["general"].get("qdrant_host", config.qdrant_host)
                config.qdrant_collection = data["general"].get("qdrant_collection", config.qdrant_collection)
                config.embedding_model = data["general"].get("embedding_model", config.embedding_model)
                config.debug = data["general"].get("debug", config.debug)
            
            if "layers" in data:
                # Note: system_token_budget is ignored (system prompt never truncated)
                config.semantic_token_budget = data["layers"].get("semantic_token_budget", config.semantic_token_budget)
                config.context_token_budget = data["layers"].get("context_token_budget", config.context_token_budget)
                config.semantic_search_turns = data["layers"].get("semantic_search_turns", config.semantic_search_turns)
                config.semantic_score_threshold = data["layers"].get("semantic_score_threshold", config.semantic_score_threshold)
            
            if "curator" in data:
                config.run_time = data["curator"].get("run_time", config.run_time)
                config.curator_model = data["curator"].get("curator_model", config.curator_model)
            
            if "cloud" in data:
                cloud_data = data["cloud"]
                config.cloud = CloudConfig(
                    enabled=cloud_data.get("enabled", False),
                    api_base=cloud_data.get("api_base", ""),
                    api_key_env=cloud_data.get("api_key_env", "OPENROUTER_API_KEY"),
                    models=cloud_data.get("models", {})
                )

        if config.cloud.enabled and not config.cloud.api_key:
            import logging
            logging.getLogger(__name__).warning(
                "Cloud is enabled but API key env var '%s' is not set",
                config.cloud.api_key_env
            )

        return config

config = Config.load()
