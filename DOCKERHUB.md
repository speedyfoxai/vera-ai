# Vera-AI - Persistent Memory Proxy for Ollama

**Vera** (Latin): *True* — **True AI Memory**

---

## What is Vera-AI?

Vera-AI is a transparent proxy for Ollama that adds persistent memory using Qdrant vector storage. It sits between your AI client and Ollama, automatically augmenting conversations with relevant context from previous sessions.

**Every conversation is remembered.**

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              REQUEST FLOW                                        │
└─────────────────────────────────────────────────────────────────────────────────┘

    ┌──────────┐         ┌──────────┐         ┌──────────┐         ┌──────────┐
    │  Client  │ ──(1)──▶│ Vera-AI  │ ──(3)──▶│  Ollama  │ ──(5)──▶│ Response │
    │  (You)   │         │  Proxy   │         │   LLM    │         │  to User │
    └──────────┘         └────┬─────┘         └──────────┘         └──────────┘
                              │
                              │ (2) Query semantic memory
                              │
                              ▼
                       ┌──────────┐
                       │ Qdrant   │
                       │ Vector DB│
                       └──────────┘
                              │
                              │ (4) Store conversation turn
                              │
                              ▼
                       ┌──────────┐
                       │ Memory   │
                       │ Storage  │
                       └──────────┘
```

---

## Quick Start

### Option 1: Docker Run (Single Command)

```bash
docker run -d \
  --name VeraAI \
  --restart unless-stopped \
  --network host \
  -e APP_UID=1000 \
  -e APP_GID=1000 \
  -e TZ=America/Chicago \
  -e VERA_DEBUG=false \
  -v ./config/config.toml:/app/config/config.toml:ro \
  -v ./prompts:/app/prompts:rw \
  -v ./logs:/app/logs:rw \
  your-username/vera-ai:latest
```

### Option 2: Docker Compose

Create `docker-compose.yml`:

```yaml
services:
  vera-ai:
    image: your-username/vera-ai:latest
    container_name: VeraAI
    restart: unless-stopped
    network_mode: host
    environment:
      - APP_UID=1000
      - APP_GID=1000
      - TZ=America/Chicago
      - VERA_DEBUG=false
    volumes:
      - ./config/config.toml:/app/config/config.toml:ro
      - ./prompts:/app/prompts:rw
      - ./logs:/app/logs:rw
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:11434/')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
```

Run with:

```bash
docker compose up -d
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_UID` | `999` | Container user ID (match your host UID) |
| `APP_GID` | `999` | Container group ID (match your host GID) |
| `TZ` | `UTC` | Container timezone |
| `VERA_DEBUG` | `false` | Enable debug logging |

### config.toml

Create `config/config.toml`:

```toml
[general]
# Ollama server URL
ollama_host = "http://10.0.0.10:11434"

# Qdrant vector database URL
qdrant_host = "http://10.0.0.22:6333"

# Collection name for memories
qdrant_collection = "memories"

# Embedding model for semantic search
embedding_model = "snowflake-arctic-embed2"

# Enable debug logging (set to true for verbose logs)
debug = false

[layers]
# Token budget for semantic memory layer
semantic_token_budget = 25000

# Token budget for recent context layer
context_token_budget = 22000

# Number of recent turns to include in semantic search
semantic_search_turns = 2

# Minimum similarity score for semantic search (0.0-1.0)
semantic_score_threshold = 0.6

[curator]
# Time for daily curation (HH:MM format)
run_time = "02:00"

# Time for monthly full curation (HH:MM format)
full_run_time = "03:00"

# Day of month for full curation (1-28)
full_run_day = 1

# Model to use for curation
curator_model = "gpt-oss:120b"
```

### prompts/ Directory

Create `prompts/` directory with:

**`prompts/curator_prompt.md`** - Prompt for memory curation:
```markdown
You are a memory curator. Your job is to summarize conversation turns 
into concise Q&A pairs that will be stored for future reference.

Extract the key information and create clear, searchable entries.
```

**`prompts/systemprompt.md`** - System context for Vera:
```markdown
You are Vera, an AI with persistent memory. You remember all previous 
conversations with this user and can reference them contextually.
```

---

## Docker Options Explained

| Option | Description |
|--------|-------------|
| `-d` | Run detached (background) |
| `--name VeraAI` | Container name |
| `--restart unless-stopped` | Auto-start on boot, survive reboots |
| `--network host` | Use host network (port 11434) |
| `-e APP_UID=1000` | User ID (match your host UID) |
| `-e APP_GID=1000` | Group ID (match your host GID) |
| `-e TZ=America/Chicago` | Timezone for scheduler |
| `-e VERA_DEBUG=false` | Disable debug logging |
| `-v ...config.toml:ro` | Config file (read-only) |
| `-v ...prompts:rw` | Prompts directory (read-write) |
| `-v ...logs:rw` | Logs directory (read-write) |

---

## Prerequisites

| Requirement | Description |
|-------------|-------------|
| **Ollama** | LLM inference server (e.g., `http://10.0.0.10:11434`) |
| **Qdrant** | Vector database (e.g., `http://10.0.0.22:6333`) |
| **Docker** | Docker installed |

---

## Features

| Feature | Description |
|---------|-------------|
| 🧠 **Persistent Memory** | Conversations stored in Qdrant, retrieved contextually |
| 📅 **Monthly Curation** | Daily + monthly cleanup of raw memories |
| 🔍 **4-Layer Context** | System + semantic + recent + current messages |
| 👤 **Configurable UID/GID** | Match container user to host for permissions |
| 🌍 **Timezone Support** | Scheduler runs in your local timezone |
| 📝 **Debug Logging** | Optional logs written to configurable directory |

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | `GET` | Health check |
| `/api/chat` | `POST` | Chat completion (with memory) |
| `/api/tags` | `GET` | List models |
| `/curator/run` | `POST` | Trigger curator manually |

---

## Verify Installation

```bash
# Health check
curl http://localhost:11434/
# Expected: {"status":"ok","ollama":"reachable"}

# Check container
docker ps
# Expected: VeraAI running with (healthy) status

# Test chat
curl -X POST http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"your-model","messages":[{"role":"user","content":"hello"}],"stream":false}'
```

---

## Troubleshooting

### Permission Denied

```bash
# Get your UID/GID
id

# Set in environment
APP_UID=$(id -u)
APP_GID=$(id -g)
```

### Wrong Timezone

```bash
# Set correct timezone
TZ=America/Chicago
```

---

## Source Code

- **Gitea**: http://10.0.0.61:3000/SpeedyFoxAi/vera-ai-v2

---

## License

MIT License

---

Brought to you by SpeedyFoxAi