"""Utility functions for vera-ai."""
from .config import config
import tiktoken
import os
from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone
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
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)
    filtered = []
    for mem in memories:
        ts = mem.get("timestamp")
        if ts:
            try:
                # Parse ISO timestamp
                if isinstance(ts, str):
                    mem_time = datetime.fromisoformat(ts.replace("Z", "")).replace(tzinfo=None)
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


def parse_curated_turn(text: str) -> List[Dict]:
    """Parse a curated turn into alternating user/assistant messages.
    
    Input format:
        User: [question]
        Assistant: [answer]
        Timestamp: ISO datetime
    
    Returns list of message dicts with role and content.
    Returns empty list if parsing fails.
    """
    if not text:
        return []
    
    messages = []
    lines = text.strip().split("\n")
    
    current_role = None
    current_content = []
    
    for line in lines:
        line = line.strip()
        if line.startswith("User:"):
            # Save previous content if exists
            if current_role and current_content:
                messages.append({
                    "role": current_role,
                    "content": "\n".join(current_content).strip()
                })
            current_role = "user"
            current_content = [line[5:].strip()]  # Remove "User:" prefix
        elif line.startswith("Assistant:"):
            # Save previous content if exists
            if current_role and current_content:
                messages.append({
                    "role": current_role,
                    "content": "\n".join(current_content).strip()
                })
            current_role = "assistant"
            current_content = [line[10:].strip()]  # Remove "Assistant:" prefix
        elif line.startswith("Timestamp:"):
            # Ignore timestamp line
            continue
        elif current_role:
            # Continuation of current message
            current_content.append(line)
    
    # Save last message
    if current_role and current_content:
        messages.append({
            "role": current_role,
            "content": "\n".join(current_content).strip()
        })
    
    return messages


async def build_augmented_messages(incoming_messages: List[Dict]) -> List[Dict]:
    """Build 4-layer augmented messages from incoming messages.
    
    Layer 1: System prompt (preserved from incoming + vera context)
    Layer 2: Semantic memories (curated, parsed into proper roles)
    Layer 3: Recent context (raw turns, parsed into proper roles)
    Layer 4: Current conversation (passed through)
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
    token_budget = {
        "semantic": config.semantic_token_budget,
        "context": config.context_token_budget
    }
    
    # === LAYER 1: System Prompt ===
    # Caller's system message passes through; systemprompt.md appends if non-empty.
    caller_system = ""
    for msg in incoming_messages:
        if msg.get("role") == "system":
            caller_system = msg.get("content", "")
            break

    if caller_system and system_prompt:
        system_content = caller_system + "\n\n" + system_prompt
    elif caller_system:
        system_content = caller_system
    elif system_prompt:
        system_content = system_prompt
    else:
        system_content = ""

    if system_content:
        messages.append({"role": "system", "content": system_content})
        logger.info(f"Layer 1 (system): {count_tokens(system_content)} tokens")
    
    # === LAYER 2: Semantic (curated memories) ===
    qdrant = get_qdrant_service()
    semantic_results = await qdrant.semantic_search(
        query=search_context if search_context else user_question,
        limit=20,
        score_threshold=config.semantic_score_threshold,
        entry_type="curated"
    )
    
    semantic_messages = []
    semantic_tokens_used = 0
    
    for result in semantic_results:
        payload = result.get("payload", {})
        text = payload.get("text", "")
        if text:
            # Parse curated turn into proper user/assistant messages
            parsed = parse_curated_turn(text)
            for msg in parsed:
                msg_tokens = count_tokens(msg.get("content", ""))
                if semantic_tokens_used + msg_tokens <= token_budget["semantic"]:
                    semantic_messages.append(msg)
                    semantic_tokens_used += msg_tokens
                else:
                    break
        if semantic_tokens_used >= token_budget["semantic"]:
            break
    
    # Add parsed messages to context
    for msg in semantic_messages:
        messages.append(msg)
    
    if semantic_messages:
        logger.info(f"Layer 2 (semantic): {len(semantic_messages)} messages, ~{semantic_tokens_used} tokens")
    
    # === LAYER 3: Context (recent turns) ===
    recent_turns = await qdrant.get_recent_turns(limit=50)
    
    context_messages = []
    context_tokens_used = 0
    
    # Process oldest first for chronological order
    for turn in reversed(recent_turns):
        payload = turn.get("payload", {})
        text = payload.get("text", "")
        entry_type = payload.get("type", "raw")
        
        if text:
            # Parse turn into messages
            parsed = parse_curated_turn(text)
            
            for msg in parsed:
                msg_tokens = count_tokens(msg.get("content", ""))
                if context_tokens_used + msg_tokens <= token_budget["context"]:
                    context_messages.append(msg)
                    context_tokens_used += msg_tokens
                else:
                    break
        
        if context_tokens_used >= token_budget["context"]:
            break
    
    # Add context messages (oldest first maintains conversation order)
    for msg in context_messages:
        messages.append(msg)
    
    if context_messages:
        logger.info(f"Layer 3 (context): {len(context_messages)} messages, ~{context_tokens_used} tokens")
    
    # === LAYER 4: Current conversation ===
    for msg in incoming_messages:
        if msg.get("role") != "system":  # System already handled in Layer 1
            messages.append(msg)
    
    logger.info(f"Layer 4 (current): {len([m for m in incoming_messages if m.get('role') != 'system'])} messages")
    
    return messages
