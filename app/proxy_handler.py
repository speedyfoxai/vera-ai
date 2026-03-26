# app/proxy_handler.py
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse
import httpx
import json
import re
import logging
import os
from pathlib import Path
from .config import config
from .singleton import get_qdrant_service
from .utils import count_tokens, build_augmented_messages

logger = logging.getLogger(__name__)

# Debug log directory (configurable via environment)
# Logs are written to VERA_LOG_DIR or /app/logs by default
DEBUG_LOG_DIR = Path(os.environ.get("VERA_LOG_DIR", "/app/logs"))


def clean_message_content(content: str) -> str:
    """Strip [Memory context] wrapper and extract actual user message."""
    if not content:
        return content
    
    # Check for OpenJarvis/OpenClaw wrapper
    wrapper_match = re.search(
        r'\[Memory context\].*?- user_msg:\s*(.+?)(?:\n\n|\Z)',
        content, re.DOTALL
    )
    if wrapper_match:
        return wrapper_match.group(1).strip()
    
    # Also strip timestamp prefixes if present
    ts_match = re.match(r'\[\d{4}-\d{2}-\d{2}[^\]]*\]\s*', content)
    if ts_match:
        return content[ts_match.end():].strip()
    
    return content


def debug_log(category: str, message: str, data: dict = None):
    """Append a debug entry to the daily debug log if debug mode is enabled.
    
    Logs are written to VERA_LOG_DIR/debug_YYYY-MM-DD.log
    This ensures logs are persisted and easily accessible.
    """
    if not config.debug:
        return
    
    from datetime import datetime
    
    # Create logs directory
    log_dir = DEBUG_LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    
    today = datetime.utcnow().strftime("%Y-%m-%d")
    log_path = log_dir / f"debug_{today}.log"
    
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "category": category,
        "message": message
    }
    if data:
        entry["data"] = data
    
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")


async def handle_chat_non_streaming(body: dict):
    """Handle non-streaming chat request."""
    incoming_messages = body.get("messages", [])
    model = body.get("model", "")
    
    debug_log("INPUT", "Non-streaming chat request", {"messages": incoming_messages})
    
    # Clean messages
    cleaned_messages = []
    for msg in incoming_messages:
        if msg.get("role") == "user":
            cleaned_content = clean_message_content(msg.get("content", ""))
            cleaned_messages.append({"role": "user", "content": cleaned_content})
        else:
            cleaned_messages.append(msg)
    
    # Build augmented messages
    augmented_messages = await build_augmented_messages(cleaned_messages)
    
    debug_log("THOUGHT", "Built augmented messages", {"augmented_count": len(augmented_messages)})
    
    # Forward to Ollama
    forwarded_body = body.copy()
    forwarded_body["messages"] = augmented_messages
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(f"{config.ollama_host}/api/chat", json=forwarded_body)
        result = resp.json()
    
    debug_log("OUTPUT", "LLM non-streaming response", {"response": result})
    
    # Store the Q&A turn
    user_question = ""
    for msg in reversed(incoming_messages):
        if msg.get("role") == "user":
            user_question = clean_message_content(msg.get("content", ""))
            break
    
    assistant_answer = result.get("message", {}).get("content", "")
    
    if user_question and assistant_answer:
        qdrant_service = get_qdrant_service()
        try:
            result_id = await qdrant_service.store_qa_turn(user_question, assistant_answer)
            debug_log("STORAGE", "Non-streaming Q&A stored", {"question": user_question, "answer": assistant_answer})
        except Exception as e:
            logger.error(f"[STORE] FAILED: {e}")
    
    result["model"] = model
    return JSONResponse(content=result)


async def handle_chat(request: Request):
    """Handle streaming chat request."""
    body = await request.json()
    incoming_messages = body.get("messages", [])
    model = body.get("model", "")
    
    debug_log("INPUT", "Streaming chat request", {"messages": incoming_messages})
    
    # Clean messages
    cleaned_messages = []
    for msg in incoming_messages:
        if msg.get("role") == "user":
            cleaned_content = clean_message_content(msg.get("content", ""))
            cleaned_messages.append({"role": "user", "content": cleaned_content})
        else:
            cleaned_messages.append(msg)
    
    # Build augmented messages
    augmented_messages = await build_augmented_messages(cleaned_messages)
    
    debug_log("THOUGHT", "Built augmented messages for streaming", {
        "original_count": len(incoming_messages),
        "augmented_count": len(augmented_messages)
    })
    
    # Forward to Ollama with streaming
    forwarded_body = body.copy()
    forwarded_body["messages"] = augmented_messages
    
    headers = dict(request.headers)
    headers.pop("content-length", None)
    headers.pop("Content-Length", None)
    headers.pop("content-type", None)
    headers.pop("Content-Type", None)
    
    async def stream_response():
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                f"{config.ollama_host}/api/chat",
                json=forwarded_body,
                headers=headers
            )
            
            full_content = ""
            async for chunk in resp.aiter_bytes():
                yield chunk
                
                for line in chunk.decode().strip().splitlines():
                    try:
                        data = json.loads(line)
                        if "message" in data and "content" in data["message"]:
                            full_content += data["message"]["content"]
                    except json.JSONDecodeError:
                        pass
            
            debug_log("OUTPUT", "LLM streaming response complete", {
                "content_length": len(full_content)
            })
            
            # Store Q&A turn
            user_question = ""
            for msg in reversed(incoming_messages):
                if msg.get("role") == "user":
                    user_question = clean_message_content(msg.get("content", ""))
                    break
            
            if user_question and full_content:
                qdrant_service = get_qdrant_service()
                try:
                    result_id = await qdrant_service.store_qa_turn(user_question, full_content)
                    logger.info(f"[STORE] Success! ID={result_id[:8]}, Q={len(user_question)} chars")
                except Exception as e:
                    logger.error(f"[STORE] FAILED: {type(e).__name__}: {e}")
    
    return StreamingResponse(stream_response(), media_type="application/x-ndjson")


async def forward_to_ollama(request: Request, path: str):
    """Forward request to Ollama transparently."""
    body = await request.body()
    headers = dict(request.headers)
    headers.pop("content-length", None)
    headers.pop("Content-Length", None)
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.request(
            method=request.method,
            url=f"{config.ollama_host}{path}",
            content=body,
            headers=headers
        )
        return resp