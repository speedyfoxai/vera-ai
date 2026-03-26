<div align="center">

# Vera-AI

### *Vera* (Latin): **True** — *True AI*

**Persistent Memory Proxy for Ollama**

*A transparent proxy that gives your AI conversations lasting memory.*

[![Docker](https://img.shields.io/docker/pulls/vera-ai/latest?style=for-the-badge)](https://hub.docker.com/r/vera-ai/latest)
[![License](https://img.shields.io/badge/license-MIT-blue?style=for-the-badge)](LICENSE)
[![Gitea](https://img.shields.io/badge/repo-Gitea-orange?style=for-the-badge)](http://10.0.0.61:3000/SpeedyFoxAi/vera-ai-v2)

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

| Requirement | Description |
|-------------|-------------|
| **Ollama** | LLM inference server (e.g., `http://10.0.0.10:11434`) |
| **Qdrant** | Vector database (e.g., `http://10.0.0.22:6333`) |
| **Docker** | Docker and Docker Compose installed |
| **Git** | For cloning the repository |

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

## 🚀 Quick Start (From Source)

```bash
# 1. Clone
git clone http://10.0.0.61:3000/SpeedyFoxAi/vera-ai-v2.git
cd vera-ai-v2

# 2. Configure
cp .env.example .env
nano .env                    # Set APP_UID, APP_GID, TZ

# 3. Create directories
mkdir -p config prompts logs
cp config.toml config/

# 4. Run
docker compose build
docker compose up -d

# 5. Test
curl http://localhost:11434/
# Expected: {"status":"ok","ollama":"reachable"}
```

---

## 📖 Full Setup Guide

### Step 1: Clone Repository

```bash
git clone http://10.0.0.61:3000/SpeedyFoxAi/vera-ai-v2.git
cd vera-ai-v2
```

### Step 2: Environment Configuration

Create `.env` file (or copy from `.env.example`):

```bash
# User/Group Configuration
# IMPORTANT: Match these to your host user for volume permissions

APP_UID=1000    # Run: id -u  to get your UID
APP_GID=1000    # Run: id -g  to get your GID

# Timezone Configuration
# Affects curator schedule (daily at 02:00, monthly on 1st at 03:00)

TZ=America/Chicago

# Debug Logging
VERA_DEBUG=false

# Optional: Cloud Model Routing
# OPENROUTER_API_KEY=your_api_key_here
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

Edit `config/config.toml`:

```toml
[general]
# Your Ollama server
ollama_host = "http://10.0.0.10:11434"

# Your Qdrant server  
qdrant_host = "http://10.0.0.22:6333"
qdrant_collection = "memories"

# Embedding model for semantic search
embedding_model = "snowflake-arctic-embed2"
debug = false

[layers]
# Token budgets for context layers
semantic_token_budget = 25000
context_token_budget = 22000
semantic_search_turns = 2
semantic_score_threshold = 0.6

[curator]
# Daily curator: processes recent 24h
run_time = "02:00"

# Monthly curator: processes ALL raw memories
full_run_time = "03:00"
full_run_day = 1    # Day of month (1st)

# Model for curation
curator_model = "gpt-oss:120b"
```

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

## ⚙️ Configuration Reference

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

### Volume Mappings

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
git clone http://10.0.0.61:3000/SpeedyFoxAi/vera-ai-v2.git
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
| **Repository** | http://10.0.0.61:3000/SpeedyFoxAi/vera-ai-v2 |
| **Issues** | http://10.0.0.61:3000/SpeedyFoxAi/vera-ai-v2/issues |

---

<div align="center">

**Vera-AI** — *True AI Memory*

Brought to you by SpeedyFoxAi

</div>