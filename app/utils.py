"""Utility functions for vera-ai."""
from .config import config
import tiktoken
import os
from typing import List, Dict
from datetime import datetime, timedelta
from pathlib import Path

# Use cl100k_base encoding (GPT-4 compatible)
ENCODING = tiktoken.get_encoding("cl100k_base")

# Configurable paths (can be overridden via environment)
PROMPTS_DIR = Path(os.environ.get("VERA_PROMPTS_DIR", "/app/prompts"))
STATIC_DIR = Path(os.environ.get("VERA_STATIC_DIR", "/app/static"))

# Global qdrant_service instance for utils
_qdrant_service = None

def get_qdrant_service():
    """Get or create the QdrantService singleton."""
    global _qdrant_service
    if _qdrant_service is None:
        from .config import config
        from .qdrant_service import QdrantService
        _qdrant_service = QdrantService(
            host=config.qdrant_host,
            collection=config.qdrant_collection,
            embedding_model=config.embedding_model,
            vector_size=config.vector_size,
            ollama_host=config.ollama_host
        )
    return _qdrant_service

def count_tokens(text: str) -> int:
    """Count tokens in text."""
    if not text:
        return 0
    return len(ENCODING.encode(text))

def count_messages_tokens(messages: List[dict]) -> int:
    """Count total tokens in messages."""
    total = 0
    for msg in messages:
        if "content" in msg:
            total += count_tokens(msg["content"])
    return total

def truncate_by_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to fit within token budget."""
    if not text:
        return text
    tokens = ENCODING.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return ENCODING.decode(tokens[:max_tokens])

def filter_memories_by_time(memories: List[Dict], hours: int = 24) -> List[Dict]:
    """Filter memories from the last N hours."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    filtered = []
    for mem in memories:
        ts = mem.get("timestamp")
        if ts:
            try:
                # Parse ISO timestamp
                if isinstance(ts, str):
                    mem_time = datetime.fromisoformat(ts.replace("Z", "+00:00").replace("+00:00", ""))
                else:
                    mem_time = ts
                if mem_time > cutoff:
                    filtered.append(mem)
            except Exception:
                # If timestamp parsing fails, include the memory
                filtered.append(mem)
        else:
            # Include memories without timestamp
            filtered.append(mem)
    return filtered

def merge_memories(memories: List[Dict]) -> Dict:
    """Merge multiple memories into one combined text."""
    if not memories:
        return {"text": "", "ids": []}
    
    texts = []
    ids = []
    for mem in memories:
        text = mem.get("text", "") or mem.get("content", "")
        if text:
            # Include role if available
            role = mem.get("role", "")
            if role:
                texts.append(f"[{role}]: {text}")
            else:
                texts.append(text)
        ids.append(mem.get("id"))
    
    return {
        "text": "\n\n".join(texts),
        "ids": ids
    }

def calculate_token_budget(total_budget: int, system_ratio: float = 0.2, 
                           semantic_ratio: float = 0.5, context_ratio: float = 0.3) -> Dict[int, int]:
    """Calculate token budgets for each layer."""
    return {
        "system": int(total_budget * system_ratio),
        "semantic": int(total_budget * semantic_ratio),
        "context": int(total_budget * context_ratio)
    }

def load_system_prompt() -> str:
    """Load system prompt from prompts directory."""
    import logging
    logger = logging.getLogger(__name__)
    
    # Try prompts directory first, then static for backward compatibility
    prompts_path = PROMPTS_DIR / "systemprompt.md"
    static_path = STATIC_DIR / "systemprompt.md"
    
    if prompts_path.exists():
        return prompts_path.read_text().strip()
    elif static_path.exists():
        return static_path.read_text().strip()
    else:
        logger.warning("systemprompt.md not found")
        return ""


async def build_augmented_messages(incoming_messages: List[Dict]) -> List[Dict]:
    """Build 4-layer augmented messages from incoming messages.
    
    This is a standalone version that can be used by proxy_handler.py.
    """
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Load system prompt
    system_prompt = load_system_prompt()
    
    # Get user question (last user message)
    user_question = ""
    for msg in reversed(incoming_messages):
        if msg.get("role") == "user":
            user_question = msg.get("content", "")
            break
    
    # Get search context (last few turns)
    search_context = ""
    for msg in incoming_messages[-6:]:
        if msg.get("role") in ("user", "assistant"):
            search_context += msg.get("content", "") + " "
    
    messages = []
    
    # === LAYER 1: System Prompt ===
    system_content = ""
    for msg in incoming_messages:
        if msg.get("role") == "system":
            system_content = msg.get("content", "")
            break
    
    if system_prompt:
        system_content += "\n\n" + system_prompt
    
    if system_content:
        messages.append({"role": "system", "content": system_content})
    
    # === LAYER 2: Semantic (curated memories) ===
    qdrant = get_qdrant_service()
    semantic_results = await qdrant.semantic_search(
        query=search_context if search_context else user_question,
        limit=20,
        score_threshold=config.semantic_score_threshold,
        entry_type="curated"
    )
    
    semantic_tokens = 0
    for result in semantic_results:
        payload = result.get("payload", {})
        text = payload.get("text", "")
        if text and semantic_tokens < config.semantic_token_budget:
            messages.append({"role": "user", "content": text})  # Add as context
            semantic_tokens += count_tokens(text)
    
    # === LAYER 3: Context (recent turns) ===
    recent_turns = await qdrant.get_recent_turns(limit=20)
    
    context_tokens = 0
    for turn in reversed(recent_turns):
        payload = turn.get("payload", {})
        text = payload.get("text", "")
        if text and context_tokens < config.context_token_budget:
            messages.append({"role": "user", "content": text})  # Add as context
            context_tokens += count_tokens(text)
    
    # === LAYER 4: Current messages (passed through) ===
    for msg in incoming_messages:
        if msg.get("role") != "system":  # Do not duplicate system
            messages.append(msg)
    
    return messages