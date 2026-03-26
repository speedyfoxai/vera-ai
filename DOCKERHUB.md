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
  -v /path/to/config/config.toml:/app/config/config.toml:ro \
  -v /path/to/prompts:/app/prompts:rw \
  -v /path/to/logs:/app/logs:rw \
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
```

Then run:

```bash
docker compose up -d
```

---

## Prerequisites

| Requirement | Description |
|-------------|-------------|
| **Ollama** | LLM inference server (e.g., `http://10.0.0.10:11434`) |
| **Qdrant** | Vector database (e.g., `http://10.0.0.22:6333`) |
| **Docker** | Docker installed |

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
ollama_host = "http://YOUR_OLLAMA_IP:11434"
qdrant_host = "http://YOUR_QDRANT_IP:6333"
qdrant_collection = "memories"
embedding_model = "snowflake-arctic-embed2"
debug = false

[layers]
semantic_token_budget = 25000
context_token_budget = 22000
semantic_search_turns = 2
semantic_score_threshold = 0.6

[curator]
run_time = "02:00"
full_run_time = "03:00"
full_run_day = 1
curator_model = "gpt-oss:120b"
```

### prompts/ Directory

Create `prompts/` directory with:

- `curator_prompt.md` - Prompt for memory curation
- `systemprompt.md` - System context for Vera

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