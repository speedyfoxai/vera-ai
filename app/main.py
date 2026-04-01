# app/main.py
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from contextlib import asynccontextmanager
import httpx
import logging
from datetime import datetime, timezone

from .config import config
from .singleton import get_qdrant_service
from .proxy_handler import handle_chat, forward_to_ollama, handle_chat_non_streaming
from .curator import Curator
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
curator = None


async def run_curator():
    """Scheduled daily curator job.
    
    Runs every day at configured time. The curator itself detects
    if it's day 01 (monthly mode) and processes all memories.
    Otherwise processes recent 24h only.
    """
    global curator
    logger.info("Starting memory curation...")
    try:
        await curator.run()
        logger.info("Memory curation completed successfully")
    except Exception as e:
        logger.error(f"Memory curation failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown."""
    global curator
    
    logger.info("Starting Vera-AI...")
    
    # Initialize singleton QdrantService
    qdrant_service = get_qdrant_service()
    await qdrant_service._ensure_collection()
    
    # Initialize curator with singleton
    curator = Curator(
        qdrant_service=qdrant_service,
        model=config.curator_model,
        ollama_host=config.ollama_host
    )
    
    # Schedule daily curator
    # Note: Monthly mode is detected automatically by curator_prompt.md (day 01)
    hour, minute = map(int, config.run_time.split(":"))
    scheduler.add_job(run_curator, "cron", hour=hour, minute=minute, id="daily_curator")
    logger.info(f"Daily curator scheduled at {config.run_time}")
    
    scheduler.start()
    
    yield
    
    logger.info("Shutting down Vera-AI...")
    scheduler.shutdown()
    await qdrant_service.close()


app = FastAPI(title="Vera-AI", version="2.0.4", lifespan=lifespan)


@app.get("/")
async def health_check():
    """Health check endpoint."""
    ollama_status = "unreachable"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{config.ollama_host}/api/tags")
            if resp.status_code == 200:
                ollama_status = "reachable"
    except Exception:
        logger.warning(f"Failed to reach Ollama at {config.ollama_host}")
    return {"status": "ok", "ollama": ollama_status}


@app.get("/api/tags")
async def api_tags():
    """Proxy to Ollama /api/tags with cloud model injection."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{config.ollama_host}/api/tags")
        data = resp.json()
    
    if config.cloud.enabled and config.cloud.models:
        for name in config.cloud.models.keys():
            data["models"].append({
                "name": name,
                "modified_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "size": 0,
                "digest": "cloud",
                "details": {"family": "cloud"}
            })
    return JSONResponse(content=data)


@app.api_route("/api/{path:path}", methods=["GET", "POST", "DELETE"])
async def proxy_all(request: Request, path: str):
    if path == "chat":
        body = await request.json()
        is_stream = body.get("stream", True)
        
        if is_stream:
            return await handle_chat(request)
        else:
            return await handle_chat_non_streaming(body)
    else:
        resp = await forward_to_ollama(request, f"/api/{path}")
        return StreamingResponse(
            resp.aiter_bytes(),
            status_code=resp.status_code,
            headers=dict(resp.headers),
            media_type=resp.headers.get("content-type")
        )


@app.post("/curator/run")
async def trigger_curator():
    """Manually trigger curator.
    
    The curator will automatically detect if it's day 01 (monthly mode)
    and process all memories. Otherwise processes recent 24h.
    """
    await run_curator()
    return {"status": "curation completed"}
