# Vera-AI Project

**Persistent Memory Proxy for Ollama**

> **Status:** Built and running on deb8. Goal: Validate and improve.

Vera-AI sits between AI clients and Ollama, storing conversations in Qdrant and retrieving context semantically — giving AI **true memory**.

## Architecture

```
Client → Vera-AI (port 11434) → Ollama
              ↓
           Qdrant (vector DB)
              ↓
           Memory Storage
```

## Key Components

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI application entry point |
| `app/proxy_handler.py` | Chat request handling |
| `app/qdrant_service.py` | Vector DB operations |
| `app/curator.py` | Memory curation (daily/monthly) |
| `app/config.py` | Configuration loader |
| `config/config.toml` | Main configuration file |

## 4-Layer Context System

1. **System Prompt** — From `prompts/systemprompt.md`
2. **Semantic Memory** — Curated Q&A from Qdrant (relevance search)
3. **Recent Context** — Last N conversation turns
4. **Current Messages** — User's current request

## Configuration

Key settings in `config/config.toml`:

```toml
[general]
ollama_host = "http://10.0.0.10:11434"
qdrant_host = "http://10.0.0.22:6333"
qdrant_collection = "memories"
embedding_model = "snowflake-arctic-embed2"

[layers]
semantic_token_budget = 25000
context_token_budget = 22000
semantic_search_turns = 2
semantic_score_threshold = 0.6

[curator]
run_time = "02:00"  # Daily curation time
curator_model = "gpt-oss:120b"
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_UID` | `999` | Container user ID |
| `APP_GID` | `999` | Container group ID |
| `TZ` | `UTC` | Timezone |
| `VERA_DEBUG` | `false` | Enable debug logging |

## Running

```bash
# Build and start
docker compose build
docker compose up -d

# Check status
docker ps
docker logs VeraAI --tail 20

# Health check
curl http://localhost:11434/
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/api/chat` | POST | Chat completion (with memory) |
| `/api/tags` | GET | List models |
| `/api/generate` | POST | Generate completion |
| `/curator/run` | POST | Trigger curation manually |

## Development Workflow

This project is synced with **deb9** (10.0.0.48). To sync changes:

```bash
# Pull from deb9
sshpass -p 'passw0rd' scp -r -o StrictHostKeyChecking=no n8n@10.0.0.48:/home/n8n/vera-ai/* /home/n8n/vera-ai/

# Push to deb9 (after local changes)
sshpass -p 'passw0rd' scp -r -o StrictHostKeyChecking=no /home/n8n/vera-ai/* n8n@10.0.0.48:/home/n8n/vera-ai/
```

## Memory System

- **raw** memories — Unprocessed conversation turns (until curation)
- **curated** memories — Cleaned Q&A pairs (permanent)
- **test** memories — Test entries (can be ignored)

Curation runs daily at 02:00 and monthly on the 1st at 03:00.

## Related Infrastructure

| Service | Host | Port |
|---------|------|------|
| Qdrant | 10.0.0.22 | 6333 |
| Ollama | 10.0.0.10 | 11434 |
| deb9 | 10.0.0.48 | Source project (SSH) |
| deb8 | 10.0.0.46 | Docker runtime |

## Qdrant Collections

| Collection | Purpose |
|------------|---------|
| `python_kb` | Python code patterns reference for this project |
| `memories` | Conversation memory storage (default) |
| `vera_memories` | Alternative memory collection |