"""Context handler - builds 4-layer context for every request."""
import httpx
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from .config import Config
from .qdrant_service import QdrantService
from .utils import count_tokens, truncate_by_tokens

logger = logging.getLogger(__name__)


class ContextHandler:
    def __init__(self, config: Config):
        self.config = config
        self.qdrant = QdrantService(
            host=config.qdrant_host,
            collection=config.qdrant_collection,
            embedding_model=config.embedding_model,
            ollama_host=config.ollama_host
        )
        self.system_prompt = self._load_system_prompt()
    
    def _load_system_prompt(self) -> str:
        """Load system prompt from static/systemprompt.md."""
        try:
            path = Path(__file__).parent.parent / "static" / "systemprompt.md"
            return path.read_text().strip()
        except FileNotFoundError:
            logger.error("systemprompt.md not found - required file")
            raise
    
    async def process(self, messages: List[Dict], model: str, stream: bool = False) -> Dict:
        """Process chat request through 4-layer context."""
        # Get user question (last user message)
        user_question = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_question = msg.get("content", "")
                break
        
        # Get messages for semantic search (last N turns)
        search_messages = []
        for msg in messages[-self.config.semantic_search_turns:]:
            if msg.get("role") in ("user", "assistant"):
                search_messages.append(msg.get("content", ""))
        
        # Build the 4-layer context messages
        context_messages = await self.build_context_messages(
            incoming_system=next((m for m in messages if m.get("role") == "system"), None),
            user_question=user_question,
            search_context=" ".join(search_messages)
        )
        
        # Forward to Ollama
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.config.ollama_host}/api/chat",
                json={"model": model, "messages": context_messages, "stream": stream}
            )
            result = response.json()
        
        # Store the Q&A turn in Qdrant
        assistant_msg = result.get("message", {}).get("content", "")
        await self.qdrant.store_qa_turn(user_question, assistant_msg)
        
        return result
    
    def _parse_curated_turn(self, text: str) -> List[Dict]:
        """Parse a curated turn into alternating user/assistant messages.
        
        Input format:
            User: [question]
            Assistant: [answer]
            Timestamp: ISO datetime
        
        Returns list of message dicts with role and content.
        """
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
    
    async def build_context_messages(self, incoming_system: Optional[Dict], user_question: str, search_context: str) -> List[Dict]:
        """Build 4-layer context messages array."""
        messages = []
        token_budget = {
            "semantic": self.config.semantic_token_budget,
            "context": self.config.context_token_budget
        }
        
        # === LAYER 1: System Prompt (pass through unchanged) ===
        # DO NOT truncate - preserve system prompt entirely
        system_content = ""
        if incoming_system:
            system_content = incoming_system.get("content", "")
            logger.info(f"System layer: preserved incoming system {len(system_content)} chars, {count_tokens(system_content)} tokens")
        
        # Add Vera context info if present (small, just metadata)
        if self.system_prompt.strip():
            system_content += "\n\n" + self.system_prompt
            logger.info(f"System layer: added vera context {len(self.system_prompt)} chars")
        
        messages.append({"role": "system", "content": system_content})
        
        # === LAYER 2: Semantic Layer (curated memories) ===
        # Search for curated blocks only
        semantic_results = await self.qdrant.semantic_search(
            query=search_context if search_context else user_question,
            limit=20,
            score_threshold=self.config.semantic_score_threshold,
            entry_type="curated"
        )
        
        # Parse curated turns into alternating user/assistant messages
        semantic_messages = []
        semantic_tokens_used = 0
        
        for result in semantic_results:
            payload = result.get("payload", {})
            text = payload.get("text", "")
            if text:
                parsed = self._parse_curated_turn(text)
                for msg in parsed:
                    msg_tokens = count_tokens(msg.get("content", ""))
                    if semantic_tokens_used + msg_tokens <= token_budget["semantic"]:
                        semantic_messages.append(msg)
                        semantic_tokens_used += msg_tokens
                    else:
                        break
        
        # Add parsed messages to context
        for msg in semantic_messages:
            messages.append(msg)
        
        if semantic_messages:
            logger.info(f"Semantic layer: {len(semantic_messages)} messages, ~{semantic_tokens_used} tokens")
        
        # === LAYER 3: Context Layer (recent turns) ===
        recent_turns = await self.qdrant.get_recent_turns(limit=50)
        
        context_messages_parsed = []
        context_tokens_used = 0
        
        for turn in reversed(recent_turns):  # Oldest first
            payload = turn.get("payload", {})
            text = payload.get("text", "")
            entry_type = payload.get("type", "raw")
            
            if text:
                # Parse turn into messages
                parsed = self._parse_curated_turn(text)
                
                for msg in parsed:
                    msg_tokens = count_tokens(msg.get("content", ""))
                    if context_tokens_used + msg_tokens <= token_budget["context"]:
                        context_messages_parsed.append(msg)
                        context_tokens_used += msg_tokens
                    else:
                        break
        
        for msg in context_messages_parsed:
            messages.append(msg)
        
        if context_messages_parsed:
            logger.info(f"Context layer: {len(context_messages_parsed)} messages, ~{context_tokens_used} tokens")
        
        # === LAYER 4: Current Question ===
        messages.append({"role": "user", "content": user_question})
        
        return messages