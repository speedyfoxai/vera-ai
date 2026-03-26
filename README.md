<div align="center">

# Vera-AI

### *Vera* (Latin): **True** — *True AI*

**Persistent Memory Proxy for Ollama**

*A transparent proxy that gives your AI conversations lasting memory.*

[![Docker](https://img.shields.io/docker/pulls/vera-ai/latest?style=for-the-badge)](https://hub.docker.com/r/vera-ai/latest)
[![License](https://img.shields.io/badge/license-MIT-blue?style=for-the-badge)](LICENSE)
[![Gitea](https://img.shields.io/badge/repo-Gitea-orange?style=for-the-badge)](https://speedyfox.app/SpeedyFoxAi/vera-ai-v2)

---

**Vera-AI sits between your AI client and Ollama, automatically augmenting conversations with relevant context from previous sessions.**

Every conversation is stored in Qdrant vector database and retrieved contextually — giving your AI **true memory**.

</div>

---

## 🔄 How It Works

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

## 🌟 Features

| Feature | Description |
|---------|-------------|
| **🧠 Persistent Memory** | Conversations stored in Qdrant, retrieved contextually |
| **📅 Monthly Curation** | Daily + monthly cleanup of raw memories |
| **🔍 4-Layer Context** | System + semantic + recent + current messages |
| **👤 Configurable UID/GID** | Match container user to host for permissions |
| **🌍 Timezone Support** | Scheduler runs in your local timezone |
| **📝 Debug Logging** | Optional logs written to configurable directory |
| **🐳 Docker Ready** | One-command build and run |

## 📋 Prerequisites

### Required Services

| Service | Version | Description |
|---------|---------|-------------|
| **Ollama** | 0.1.x+ | LLM inference server |
| **Qdrant** | 1.6.x+ | Vector database |
| **Docker** | 20.x+ | Container runtime |

### System Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| **CPU** | 2 cores | 4+ cores |
| **RAM** | 2 GB | 4+ GB |
| **Disk** | 1 GB | 5+ GB |

---

## 🔧 Installing with Ollama

### Option A: All on Same Host (Recommended)

Install all services on a single machine:

```bash
# 1. Install Ollama
curl https://ollama.ai/install.sh | sh

# 2. Pull required models
ollama pull snowflake-arctic-embed2  # Embedding model (required)
ollama pull llama3.1                   # Chat model

# 3. Run Qdrant in Docker
docker run -d --name qdrant -p 6333:6333 qdrant/qdrant

# 4. Run Vera-AI
docker run -d \
  --name VeraAI \
  --restart unless-stopped \
  --network host \
  -e APP_UID=$(id -u) \
  -e APP_GID=$(id -g) \
  -e TZ=America/Chicago \
  -v ./config/config.toml:/app/config/config.toml:ro \
  -v ./prompts:/app/prompts:rw \
  -v ./logs:/app/logs:rw \
  mdkrushr/vera-ai:latest
```

**Config for same-host (config/config.toml):**
```toml
[general]
ollama_host = "http://127.0.0.1:11434"
qdrant_host = "http://127.0.0.1:6333"
qdrant_collection = "memories"
embedding_model = "snowflake-arctic-embed2"
```

### Option B: Docker Compose All-in-One

```yaml
services:
  ollama:
    image: ollama/ollama
    ports: ["11434:11434"]
    volumes: [ollama_data:/root/.ollama]

  qdrant:
    image: qdrant/qdrant
    ports: ["6333:6333"]
    volumes: [qdrant_data:/qdrant/storage]

  vera-ai:
    image: mdkrushr/vera-ai:latest
    network_mode: host
    volumes:
      - ./config/config.toml:/app/config/config.toml:ro
      - ./prompts:/app/prompts:rw
volumes:
  ollama_data:
  qdrant_data:
```

### Option C: Different Port

If Ollama uses port 11434, run Vera on port 8080:

```bash
docker run -d --name VeraAI -p 8080:11434 ...
# Connect client to: http://localhost:8080
```

---

## ✅ Pre-Flight Checklist

- [ ] Docker installed (`docker --version`)
- [ ] Ollama running (`curl http://localhost:11434/api/tags`)
- [ ] Qdrant running (`curl http://localhost:6333/collections`)
- [ ] Embedding model (`ollama pull snowflake-arctic-embed2`)
- [ ] Chat model (`ollama pull llama3.1`)

---
---

## 🐳 Docker Deployment

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
  mdkrushr/vera-ai:latest
```

### Option 2: Docker Compose

Create `docker-compose.yml`:

```yaml
services:
  vera-ai:
    image: mdkrushr/vera-ai:latest
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

### Docker Options Explained

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
| `-v ...:ro` | Config file (read-only) |
| `-v ...:rw` | Prompts and logs (read-write) |

---

## ⚙️ Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_UID` | `999` | Container user ID (match host) |
| `APP_GID` | `999` | Container group ID (match host) |
| `TZ` | `UTC` | Container timezone |
| `VERA_DEBUG` | `false` | Enable debug logging |
| `OPENROUTER_API_KEY` | - | Cloud model routing key |
| `VERA_CONFIG_DIR` | `/app/config` | Config directory |
| `VERA_PROMPTS_DIR` | `/app/prompts` | Prompts directory |
| `VERA_LOG_DIR` | `/app/logs` | Debug logs directory |

### config.toml

Create `config/config.toml` with all settings:

```toml
[general]
# ═══════════════════════════════════════════════════════════════
# General Settings
# ═══════════════════════════════════════════════════════════════

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
# ═══════════════════════════════════════════════════════════════
# Context Layer Settings
# ═══════════════════════════════════════════════════════════════

# Token budget for semantic memory layer
# Controls how much curated memory can be included
semantic_token_budget = 25000

# Token budget for recent context layer
# Controls how much recent conversation can be included
context_token_budget = 22000

# Number of recent turns to include in semantic search
# Higher = more context, but slower
semantic_search_turns = 2

# Minimum similarity score for semantic search (0.0-1.0)
# Higher = more relevant results, but fewer matches
semantic_score_threshold = 0.6

[curator]
# ═══════════════════════════════════════════════════════════════
# Curation Settings
# ═══════════════════════════════════════════════════════════════

# Time for daily curation (HH:MM format, 24-hour)
# Processes raw memories from last 24h
run_time = "02:00"

# Time for monthly full curation (HH:MM format, 24-hour)
# Processes ALL raw memories
full_run_time = "03:00"

# Day of month for full curation (1-28)
full_run_day = 1

# Model to use for curation
# Should be a capable model for summarization
curator_model = "gpt-oss:120b"
```

### prompts/ Directory

Create `prompts/` directory with:

**`prompts/curator_prompt.md`** - Prompt for memory curation:
```markdown
You are a memory curator. Your job is to summarize conversation turns 
into concise Q&A pairs that will be stored for future reference.

Extract the key information and create clear, searchable entries.
Focus on facts, decisions, and important context.
```

**`prompts/systemprompt.md`** - System context for Vera:
```markdown
You are Vera, an AI with persistent memory. You remember all previous 
conversations with this user and can reference them contextually.

Use the provided context to give informed, personalized responses.
```

---

## 🚀 Quick Start (From Source)

```bash
# 1. Clone
git clone https://speedyfox.app/SpeedyFoxAi/vera-ai-v2.git
cd vera-ai-v2

# 2. Configure
cp .env.example .env
nano .env                    # Set APP_UID, APP_GID, TZ

# 3. Create directories and config
mkdir -p config prompts logs
cp config.toml config/
nano config/config.toml     # Set ollama_host, qdrant_host

# 4. Create prompts
nano prompts/curator_prompt.md
nano prompts/systemprompt.md

# 5. Run
docker compose build
docker compose up -d

# 6. Test
curl http://localhost:11434/
# Expected: {"status":"ok","ollama":"reachable"}
```

---

## 📖 Full Setup Guide

### Step 1: Clone Repository

```bash
git clone https://speedyfox.app/SpeedyFoxAi/vera-ai-v2.git
cd vera-ai-v2
```

### Step 2: Environment Configuration

Create `.env` file:

```bash
# User/Group Configuration
APP_UID=1000    # Run: id -u  to get your UID
APP_GID=1000    # Run: id -g  to get your GID

# Timezone Configuration
TZ=America/Chicago

# Debug Logging
VERA_DEBUG=false
```

### Step 3: Directory Structure

```bash
# Create required directories
mkdir -p config prompts logs

# Copy default configuration
cp config.toml config/

# Verify prompts exist
ls -la prompts/
# Should show: curator_prompt.md, systemprompt.md
```

### Step 4: Configure Services

Edit `config/config.toml` (see full example above)

### Step 5: Build and Run

```bash
# Build with your UID/GID
APP_UID=$(id -u) APP_GID=$(id -g) docker compose build

# Start container
docker compose up -d

# Check status
docker ps
docker logs VeraAI --tail 20
```

### Step 6: Verify Installation

```bash
# Health check
curl http://localhost:11434/
# Expected: {"status":"ok","ollama":"reachable"}

# Container status
docker ps --format "table {{.Names}}\t{{.Status}}"
# Expected: VeraAI   Up X minutes (healthy)

# Timezone
docker exec VeraAI date
# Should show your timezone (e.g., CDT for America/Chicago)

# User permissions
docker exec VeraAI id
# Expected: uid=1000(appuser) gid=1000(appgroup)

# Directories
docker exec VeraAI ls -la /app/prompts/
# Should show: curator_prompt.md, systemprompt.md

# Test chat
curl -X POST http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3.5:397b-cloud","messages":[{"role":"user","content":"hello"}],"stream":false}'
```

---

## 📁 Volume Mappings

| Host Path | Container Path | Mode | Purpose |
|-----------|----------------|------|---------|
| `./config/config.toml` | `/app/config/config.toml` | `ro` | Configuration |
| `./prompts/` | `/app/prompts/` | `rw` | Curator prompts |
| `./logs/` | `/app/logs/` | `rw` | Debug logs |

### Directory Structure

```
vera-ai-v2/
├── config/
│   └── config.toml        # Main configuration
├── prompts/
│   ├── curator_prompt.md  # Memory curation prompt
│   └── systemprompt.md    # System context
├── logs/                  # Debug logs (when debug=true)
├── app/
│   ├── main.py            # FastAPI application
│   ├── config.py          # Configuration loader
│   ├── curator.py         # Memory curation
│   ├── proxy_handler.py   # Chat handling
│   ├── qdrant_service.py  # Vector operations
│   ├── singleton.py       # QdrantService singleton
│   └── utils.py           # Utilities
├── static/                # Legacy symlinks
├── .env.example           # Environment template
├── docker-compose.yml     # Docker Compose
├── Dockerfile             # Container definition
├── requirements.txt       # Python dependencies
└── README.md              # This file
```

---

## 🌍 Timezone Configuration

The `TZ` variable sets the container timezone for the scheduler:

```bash
# Common timezones
TZ=UTC                  # Coordinated Universal Time
TZ=America/New_York     # Eastern Time
TZ=America/Chicago      # Central Time
TZ=America/Los_Angeles  # Pacific Time
TZ=Europe/London        # GMT/BST
```

**Curation Schedule:**
| Schedule | Time | What | Frequency |
|----------|------|------|-----------|
| Daily | 02:00 | Recent 24h | Every day |
| Monthly | 03:00 on 1st | ALL raw memories | 1st of month |

---

## 🔌 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | `GET` | Health check |
| `/api/chat` | `POST` | Chat completion (with memory) |
| `/api/tags` | `GET` | List available models |
| `/api/generate` | `POST` | Generate completion |
| `/curator/run` | `POST` | Trigger curator manually |

### Manual Curation

```bash
# Daily curation (recent 24h)
curl -X POST http://localhost:11434/curator/run

# Full curation (all raw memories)
curl -X POST "http://localhost:11434/curator/run?full=true"
```

---

## 🧠 Memory System

### 4-Layer Context Build

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: System Prompt                                      │
│   • From prompts/systemprompt.md                            │
│   • Preserved unchanged, passed through                     │
├─────────────────────────────────────────────────────────────┤
│ Layer 2: Semantic Memory                                    │
│   • Query Qdrant with user question                         │
│   • Retrieve curated Q&A pairs by relevance                 │
│   • Limited by semantic_token_budget                        │
├─────────────────────────────────────────────────────────────┤
│ Layer 3: Recent Context                                     │
│   • Last N conversation turns from Qdrant                   │
│   • Chronological order, recent memories first              │
│   • Limited by context_token_budget                         │
├─────────────────────────────────────────────────────────────┤
│ Layer 4: Current Messages                                   │
│   • User message from current request                       │
│   • Passed through unchanged                                │
└─────────────────────────────────────────────────────────────┘
```

### Memory Types

| Type | Description | Retention |
|------|-------------|-----------|
| `raw` | Unprocessed conversation turns | Until curation |
| `curated` | Cleaned Q&A pairs | Permanent |
| `test` | Test entries | Can be ignored |

### Curation Process

1. **Daily (02:00)**: Processes raw memories from last 24h into curated Q&A pairs
2. **Monthly (03:00 on 1st)**: Processes ALL remaining raw memories for full cleanup

---

## 🔧 Troubleshooting

### Permission Denied

```bash
# Check your UID/GID
id

# Rebuild with correct values
APP_UID=$(id -u) APP_GID=$(id -g) docker compose build --no-cache
docker compose up -d
```

### Wrong Timezone

```bash
# Check container time
docker exec VeraAI date

# Fix in .env
TZ=America/Chicago
```

### Health Check Failing

```bash
# Check logs
docker logs VeraAI --tail 50

# Test Ollama connectivity
docker exec VeraAI python -c "
import urllib.request
print(urllib.request.urlopen('http://YOUR_OLLAMA_IP:11434/').read())
"

# Test Qdrant connectivity
docker exec VeraAI python -c "
import urllib.request
print(urllib.request.urlopen('http://YOUR_QDRANT_IP:6333/').read())
"
```

### Port Already in Use

```bash
# Check what's using port 11434
sudo lsof -i :11434

# Stop conflicting service or change port in config
```

---

## 🛠️ Development

### Build from Source

```bash
git clone https://speedyfox.app/SpeedyFoxAi/vera-ai-v2.git
cd vera-ai-v2
pip install -r requirements.txt
docker compose build
```

### Run Tests

```bash
# Health check
curl http://localhost:11434/

# Non-streaming chat
curl -X POST http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3.5:397b-cloud","messages":[{"role":"user","content":"test"}],"stream":false}'

# Trigger curation
curl -X POST http://localhost:11434/curator/run
```

---

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

---

## 🤝 Support

| Resource | Link |
|----------|------|
| **Repository** | https://speedyfox.app/SpeedyFoxAi/vera-ai-v2 |
| **Issues** | https://speedyfox.app/SpeedyFoxAi/vera-ai-v2/issues |

---

<div align="center">

**Vera-AI** — *True AI Memory*

Brought to you by SpeedyFoxAi

</div>