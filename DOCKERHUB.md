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


┌─────────────────────────────────────────────────────────────────────────────────┐
│                           4-LAYER CONTEXT BUILD                                  │
└─────────────────────────────────────────────────────────────────────────────────┘

    Incoming Request (POST /api/chat)
              │
              ▼
    ┌─────────────────────────────────────────────────────────────────────────────┐
    │ Layer 1: System Prompt                                                      │
    │   • Static context from prompts/systemprompt.md                            │
    │   • Preserved unchanged, passed through                                      │
    └─────────────────────────────────────────────────────────────────────────────┘
              │
              ▼
    ┌─────────────────────────────────────────────────────────────────────────────┐
    │ Layer 2: Semantic Memory                                                    │
    │   • Query Qdrant with user question                                         │
    │   • Retrieve curated Q&A pairs by relevance                                 │
    │   • Limited by semantic_token_budget                                        │
    └─────────────────────────────────────────────────────────────────────────────┘
              │
              ▼
    ┌─────────────────────────────────────────────────────────────────────────────┐
    │ Layer 3: Recent Context                                                     │
    │   • Last N conversation turns from Qdrant                                   │
    │   • Chronological order, recent memories first                              │
    │   • Limited by context_token_budget                                         │
    └─────────────────────────────────────────────────────────────────────────────┘
              │
              ▼
    ┌─────────────────────────────────────────────────────────────────────────────┐
    │ Layer 4: Current Messages                                                    │
    │   • User message from current request                                       │
    │   • Passed through unchanged                                                │
    └─────────────────────────────────────────────────────────────────────────────┘
              │
              ▼
         [augmented request] ──▶ Ollama LLM ──▶ Response
```

---

## Quick Start

```bash
# Pull the image
docker pull YOUR_USERNAME/vera-ai:latest

# Create directories
mkdir -p config prompts logs

# Create environment file
cat > .env << EOF
APP_UID=$(id -u)
APP_GID=$(id -g)
TZ=America/Chicago
EOF

# Run
docker run -d \
  --name vera-ai \
  --env-file .env \
  -v ./config/config.toml:/app/config/config.toml:ro \
  -v ./prompts:/app/prompts:rw \
  -v ./logs:/app/logs:rw \
  --network host \
  YOUR_USERNAME/vera-ai:latest

# Test
curl http://localhost:11434/
```

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

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_UID` | `999` | Container user ID (match your host UID) |
| `APP_GID` | `999` | Container group ID (match your host GID) |
| `TZ` | `UTC` | Container timezone |
| `VERA_CONFIG_DIR` | `/app/config` | Config directory |
| `VERA_PROMPTS_DIR` | `/app/prompts` | Prompts directory |
| `VERA_LOG_DIR` | `/app/logs` | Debug logs directory |

### Required Services

- **Ollama**: LLM inference server
- **Qdrant**: Vector database for memory storage

### Example config.toml

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
run_time = "02:00"           # Daily curator
full_run_time = "03:00"      # Monthly curator
full_run_day = 1             # Day of month (1st)
curator_model = "gpt-oss:120b"
```

---

## Docker Compose

```yaml
services:
  vera-ai:
    image: YOUR_USERNAME/vera-ai:latest
    container_name: vera-ai
    env_file:
      - .env
    volumes:
      - ./config/config.toml:/app/config/config.toml:ro
      - ./prompts:/app/prompts:rw
      - ./logs:/app/logs:rw
    network_mode: "host"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:11434/')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
```

---

## Memory System

### 4-Layer Context

1. **System Prompt** - From `prompts/systemprompt.md`
2. **Semantic Memory** - Curated Q&A retrieved by relevance
3. **Recent Context** - Last N conversation turns
4. **Current Messages** - User/assistant from request

### Curation Schedule

| Schedule | Time | What |
|----------|------|------|
| Daily | 02:00 | Recent 24h raw memories |
| Monthly | 03:00 on 1st | ALL raw memories |

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | `GET` | Health check |
| `/api/chat` | `POST` | Chat completion (with memory) |
| `/api/tags` | `GET` | List models |
| `/curator/run` | `POST` | Trigger curator |

---

## Troubleshooting

### Permission Denied

```bash
# Get your UID/GID
id

# Set in .env
APP_UID=1000
APP_GID=1000

# Rebuild
docker compose build --no-cache
```

### Wrong Timezone

```bash
# Set in .env
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