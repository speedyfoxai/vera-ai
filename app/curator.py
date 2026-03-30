"""Memory curator - runs daily to clean and maintain memory database.

On day 01 of each month, processes ALL raw memories (monthly mode).
Otherwise, processes recent 24h of raw memories (daily mode).
The prompt determines behavior based on current date.
"""
import logging
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
import httpx
import json
import re

from .qdrant_service import QdrantService

logger = logging.getLogger(__name__)

# Configurable prompts directory (can be overridden via environment)
PROMPTS_DIR = Path(os.environ.get("VERA_PROMPTS_DIR", "/app/prompts"))
STATIC_DIR = Path(os.environ.get("VERA_STATIC_DIR", "/app/static"))


def load_curator_prompt() -> str:
    """Load curator prompt from prompts directory."""
    prompts_path = PROMPTS_DIR / "curator_prompt.md"
    static_path = STATIC_DIR / "curator_prompt.md"
    
    if prompts_path.exists():
        return prompts_path.read_text().strip()
    elif static_path.exists():
        return static_path.read_text().strip()
    else:
        raise FileNotFoundError(f"curator_prompt.md not found in {PROMPTS_DIR} or {STATIC_DIR}")


class Curator:
    def __init__(self, qdrant_service: QdrantService, model: str = "gpt-oss:120b", ollama_host: str = "http://10.0.0.10:11434"):
        self.qdrant = qdrant_service
        self.model = model
        self.ollama_host = ollama_host
        self.curator_prompt = load_curator_prompt()

    async def run(self):
        """Run the curation process.
        
        Automatically detects day 01 for monthly mode (processes ALL raw memories).
        Otherwise runs daily mode (processes recent 24h only).
        The prompt determines behavior based on current date.
        """
        current_date = datetime.utcnow()
        is_monthly = current_date.day == 1
        mode = "MONTHLY" if is_monthly else "DAILY"
        
        logger.info(f"Starting memory curation ({mode} mode)...")
        try:
            current_date_str = current_date.strftime("%Y-%m-%d")
            
            # Get all memories (async)
            points, _ = await self.qdrant.client.scroll(
                collection_name=self.qdrant.collection,
                limit=10000,
                with_payload=True,
                with_vectors=False
            )

            memories = []
            for point in points:
                payload = point.payload or {}
                memories.append({
                    "id": str(point.id),
                    "text": payload.get("text", ""),
                    "type": payload.get("type", "raw"),
                    "timestamp": payload.get("timestamp", ""),
                    "payload": payload
                })

            raw_memories = [m for m in memories if m["type"] == "raw"]
            curated_memories = [m for m in memories if m["type"] == "curated"]
            
            logger.info(f"Found {len(raw_memories)} raw, {len(curated_memories)} curated")

            # Filter by time for daily mode, process all for monthly mode
            if is_monthly:
                # Monthly full run: process ALL raw memories
                recent_raw = raw_memories
                logger.info(f"MONTHLY MODE: Processing all {len(recent_raw)} raw memories")
            else:
                # Daily run: process only recent 24h
                recent_raw = [m for m in raw_memories if self._is_recent(m, hours=24)]
                logger.info(f"DAILY MODE: Processing {len(recent_raw)} recent raw memories")

            existing_sample = curated_memories[-50:] if len(curated_memories) > 50 else curated_memories

            if not recent_raw:
                logger.info("No raw memories to process")
                return

            raw_turns_text = self._format_raw_turns(recent_raw)
            existing_text = self._format_existing_memories(existing_sample)

            prompt = self.curator_prompt.replace("{CURRENT_DATE}", current_date_str)
            full_prompt = f"""{prompt}

## {'All' if is_monthly else 'Recent'} Raw Turns ({'full database' if is_monthly else 'last 24 hours'}):
{raw_turns_text}

## Existing Memories (sample):
{existing_text}

Remember: Respond with ONLY valid JSON. No markdown, no explanations, just the JSON object."""

            logger.info(f"Sending {len(recent_raw)} raw turns to LLM...")
            response_text = await self._call_llm(full_prompt)
            
            result = self._parse_json_response(response_text)
            
            if not result:
                logger.error("Failed to parse JSON response from LLM")
                return

            new_turns = result.get("new_curated_turns", [])
            permanent_rules = result.get("permanent_rules", [])
            deletions = result.get("deletions", [])
            summary = result.get("summary", "")

            logger.info(f"Parsed: {len(new_turns)} turns, {len(permanent_rules)} rules, {len(deletions)} deletions")
            logger.info(f"Summary: {summary}")

            for turn in new_turns:
                content = turn.get("content", "")
                if content:
                    await self.qdrant.store_turn(
                        role="curated",
                        content=content,
                        entry_type="curated"
                    )
                    logger.info(f"Stored curated turn: {content[:100]}...")

            for rule in permanent_rules:
                rule_text = rule.get("rule", "")
                target_file = rule.get("target_file", "systemprompt.md")
                if rule_text:
                    await self._append_rule_to_file(target_file, rule_text)
                    logger.info(f"Appended rule to {target_file}: {rule_text[:80]}...")

            if deletions:
                valid_deletions = [d for d in deletions if d in [m["id"] for m in memories]]
                if valid_deletions:
                    await self.qdrant.delete_points(valid_deletions)
                    logger.info(f"Deleted {len(valid_deletions)} points")

            raw_ids_to_delete = [m["id"] for m in recent_raw]
            if raw_ids_to_delete:
                await self.qdrant.delete_points(raw_ids_to_delete)
                logger.info(f"Deleted {len(raw_ids_to_delete)} processed raw memories")

            logger.info(f"Memory curation completed successfully ({mode} mode)")

        except Exception as e:
            logger.error(f"Error during curation: {e}")
            raise

    def _is_recent(self, memory: Dict, hours: int = 24) -> bool:
        """Check if memory is within the specified hours."""
        timestamp = memory.get("timestamp", "")
        if not timestamp:
            return True
        try:
            mem_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            return mem_time.replace(tzinfo=None) > cutoff
        except (ValueError, TypeError):
            logger.debug(f"Could not parse timestamp: {timestamp}")
            return True

    def _format_raw_turns(self, turns: List[Dict]) -> str:
        """Format raw turns for the LLM prompt."""
        formatted = []
        for i, turn in enumerate(turns, 1):
            text = turn.get("text", "")
            formatted.append(f"--- RAW TURN {i} (ID: {turn.get('id', 'unknown')}) ---\n{text}\n")
        return "\n".join(formatted)

    def _format_existing_memories(self, memories: List[Dict]) -> str:
        """Format existing curated memories for the LLM prompt."""
        if not memories:
            return "No existing curated memories."
        formatted = []
        for i, mem in enumerate(memories[-20:], 1):
            text = mem.get("text", "")
            formatted.append(f"{text}\n")
        return "\n".join(formatted)

    async def _call_llm(self, prompt: str) -> str:
        """Call Ollama LLM with the prompt."""
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self.ollama_host}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.3,
                            "num_predict": 8192
                        }
                    }
                )
                result = response.json()
                return result.get("response", "")
        except Exception as e:
            logger.error(f"Failed to call LLM: {e}")
            return ""

    def _parse_json_response(self, response: str) -> Optional[Dict]:
        """Parse JSON from LLM response."""
        if not response:
            return None
        
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except json.JSONDecodeError:
            pass

        # Try to find JSON in code blocks
        pattern = r'```(?:json)?\s*([\s\S]*?)```'
        json_match = re.search(pattern, response)
        if json_match:
            try:
                return json.loads(json_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        logger.error(f"Could not parse JSON: {response[:500]}...")
        return None

    async def _append_rule_to_file(self, filename: str, rule: str):
        """Append a permanent rule to a prompts file."""
        prompts_path = PROMPTS_DIR / filename
        static_path = STATIC_DIR / filename
        
        # Use whichever directory is writable
        target_path = prompts_path if prompts_path.parent.exists() else static_path
        
        try:
            # Ensure parent directory exists
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(target_path, "a") as f:
                f.write(f"\n{rule}\n")
            logger.info(f"Appended rule to {target_path}")
        except Exception as e:
            logger.error(f"Failed to append rule to {filename}: {e}")