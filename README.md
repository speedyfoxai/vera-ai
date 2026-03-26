# Vera-AI: Persistent Memory Proxy for Ollama

[![Docker](https://img.shields.io/docker/pulls/vera-ai/latest)](https://hub.docker.com/r/vera-ai/latest)

**Vera-AI** is a transparent proxy for Ollama that adds persistent memory using Qdrant vector storage. It sits between your AI client and Ollama, automatically augmenting conversations with relevant context from previous sessions.

## Features

- **Persistent Memory**: Conversations are stored in Qdrant and retrieved contextually
- **Monthly Curation**: Daily and monthly cleanup of raw memories
- **4-Layer Context**: System prompt + semantic memory + recent context + current messages
- **Configurable UID/GID**: Match container user to host user for volume permissions
- **Timezone Support**: Scheduler runs in your local timezone
- **Debug Logging**: Optional debug logs written to configurable directory

## Prerequisites

- **Ollama**: Running LLM inference server (e.g., `http://10.0.0.10:11434`)
- **Qdrant**: Running vector database (e.g., `http://10.0.0.22:6333`)
- **Docker**: Docker and Docker Compose installed
- **Git**: For cloning the repository

## Quick Start

```bash
# Clone the repository
git clone http://10.0.0.61:3000/SpeedyFoxAi/vera-ai-v2.git
cd vera-ai-v2

# Create environment file from template
cp .env.example .env

# Edit .env with your settings
nano .env

# Create required directories
mkdir -p config prompts logs

# Copy default config (or create your own)
cp config.toml config/

# Build and run
docker compose build
docker compose up -d

# Test
curl http://localhost:11434/
```

## Full Setup Instructions

### 1. Clone Repository

```bash
git clone http://10.0.0.61:3000/SpeedyFoxAi/vera-ai-v2.git
cd vera-ai-v2
```

### 2. Create Environment File

Create `.env` file (or copy from `.env.example`):

```bash
# User/Group Configuration (match your host user)
APP_UID=1000
APP_GID=1000

# Timezone Configuration
TZ=America/Chicago

# API Keys (optional)
# OPENROUTER_API_KEY=your_api_key_here
```

**Important:** `APP_UID` and `APP_GID` must match your host user's UID/GID for volume permissions:

```bash
# Get your UID and GID
id -u   # UID
id -g   # GID

# Set in .env
APP_UID=1000  # Replace with your UID
APP_GID=1000  # Replace with your GID
```

### 3. Create Required Directories

```bash
# Create directories
mkdir -p config prompts logs

# Copy default configuration
cp config.toml config/

# Verify prompts exist (should be in the repo)
ls -la prompts/
# Should show: curator_prompt.md, systemprompt.md
```

### 4. Configure Ollama and Qdrant

Edit `config/config.toml`:

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
run_time = "02:00"           # Daily curator time
full_run_time = "03:00"      # Monthly full curator time
full_run_day = 1             # Day of month (1st)
curator_model = "gpt-oss:120b"
```

### 5. Build and Run

```bash
# Build with your UID/GID
APP_UID=$(id -u) APP_GID=$(id -g) docker compose build

# Run with timezone
docker compose up -d

# Check status
docker ps
docker logs vera-ai --tail 20

# Test health endpoint
curl http://localhost:11434/
# Expected: {"status":"ok","ollama":"reachable"}
```

### 6. Verify Installation

```bash
# Check container is healthy
docker ps --format "table {{.Names}}\t{{.Status}}"
# Expected: vera-ai   Up X minutes (healthy)

# Check timezone
docker exec vera-ai date
# Should show your timezone (e.g., CDT for America/Chicago)

# Check user
docker exec vera-ai id
# Expected: uid=1000(appuser) gid=1000(appgroup)

# Check directories
docker exec vera-ai ls -la /app/prompts/
# Should show: curator_prompt.md, systemprompt.md

docker exec vera-ai ls -la /app/logs/
# Should be writable

# Test chat
curl -X POST http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"YOUR_MODEL","messages":[{"role":"user","content":"hello"}],"stream":false}'
```

## Configuration

### Environment Variables (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_UID` | `999` | User ID for container user (match your host UID) |
| `APP_GID` | `999` | Group ID for container group (match your host GID) |
| `TZ` | `UTC` | Timezone for scheduler |
| `OPENROUTER_API_KEY` | - | API key for cloud model routing (optional) |
| `VERA_CONFIG_DIR` | `/app/config` | Configuration directory (optional) |
| `VERA_PROMPTS_DIR` | `/app/prompts` | Prompts directory (optional) |
| `VERA_LOG_DIR` | `/app/logs` | Debug log directory (optional) |

### Volume Mappings

| Host Path | Container Path | Mode | Purpose |
|-----------|---------------|------|---------|
| `./config/config.toml` | `/app/config/config.toml` | `ro` | Configuration file |
| `./prompts/` | `/app/prompts/` | `rw` | Curator and system prompts |
| `./logs/` | `/app/logs/` | `rw` | Debug logs (when debug=true) |

### Directory Structure

```
vera-ai-v2/
├── config/
│   └── config.toml       # Main configuration (mounted read-only)
├── prompts/
│   ├── curator_prompt.md # Prompt for memory curator
│   └── systemprompt.md   # System context (curator can append)
├── logs/                 # Debug logs (when debug=true)
├── app/
│   ├── main.py           # FastAPI application
│   ├── config.py         # Configuration loading
│   ├── curator.py        # Memory curation
│   ├── proxy_handler.py  # Chat request handling
│   ├── qdrant_service.py # Qdrant operations
│   ├── singleton.py      # QdrantService singleton
│   └── utils.py          # Utilities
├── static/               # Legacy (symlinks to prompts/)
├── .env.example          # Environment template
├── docker-compose.yml    # Docker Compose config
├── Dockerfile            # Container definition
├── requirements.txt      # Python dependencies
└── README.md             # This file
```

## Docker Compose

```yaml
services:
  vera-ai:
    build:
      context: .
      dockerfile: Dockerfile
      args:
        APP_UID: ${APP_UID:-999}
        APP_GID: ${APP_GID:-999}
    image: vera-ai:latest
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

## Timezone Configuration

The `TZ` environment variable sets the container timezone, which affects the scheduler:

```bash
# .env file
TZ=America/Chicago

# Scheduler runs at:
# - Daily curator: 02:00 Chicago time
# - Monthly curator: 03:00 Chicago time on 1st
```

Common timezones:
- `UTC` - Coordinated Universal Time
- `America/New_York` - Eastern Time
- `America/Chicago` - Central Time
- `America/Los_Angeles` - Pacific Time
- `Europe/London` - GMT/BST

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/api/chat` | POST | Chat completion (augmented with memory) |
| `/api/tags` | GET | List models |
| `/api/generate` | POST | Generate completion |
| `/curator/run` | POST | Trigger curator manually |

## Manual Curator Trigger

```bash
# Daily curation (recent 24h)
curl -X POST http://localhost:11434/curator/run

# Full curation (all raw memories)
curl -X POST "http://localhost:11434/curator/run?full=true"
```

## Memory System

### 4-Layer Context

1. **System Prompt**: From `prompts/systemprompt.md`
2. **Semantic Memory**: Curated Q&A pairs retrieved by relevance
3. **Recent Context**: Last N conversation turns
4. **Current Messages**: User/assistant messages from request

### Curation Schedule

| Schedule | Time | What | Frequency |
|----------|------|------|-----------|
| Daily | 02:00 | Recent 24h raw memories | Every day |
| Monthly | 03:00 on 1st | ALL raw memories | 1st of month |

### Memory Types

- **raw**: Unprocessed conversation turns
- **curated**: Cleaned, summarized Q&A pairs
- **test**: Test entries (can be ignored)

## Troubleshooting

### Permission Denied

If you see permission errors on `/app/prompts/` or `/app/logs/`:

```bash
# Check your UID/GID
id

# Rebuild with correct UID/GID
APP_UID=$(id -u) APP_GID=$(id -g) docker compose build --no-cache
docker compose up -d
```

### Timezone Issues

If curator runs at wrong time:

```bash
# Check container timezone
docker exec vera-ai date

# Set correct timezone in .env
TZ=America/Chicago
```

### Health Check Failing

```bash
# Check container logs
docker logs vera-ai --tail 50

# Check Ollama connectivity
docker exec vera-ai python -c "import urllib.request; print(urllib.request.urlopen('http://YOUR_OLLAMA_IP:11434/').read())"

# Check Qdrant connectivity
docker exec vera-ai python -c "import urllib.request; print(urllib.request.urlopen('http://YOUR_QDRANT_IP:6333/').read())"
```

### Container Not Starting

```bash
# Check if port is in use
sudo lsof -i :11434

# Check Docker logs
docker compose logs

# Rebuild from scratch
docker compose down
docker compose build --no-cache
docker compose up -d
```

## Development

### Building from Source

```bash
# Clone repository
git clone http://10.0.0.61:3000/SpeedyFoxAi/vera-ai-v2.git
cd vera-ai-v2

# Install dependencies locally (optional)
pip install -r requirements.txt

# Build Docker image
docker compose build
```

### Running Tests

```bash
# Test health endpoint
curl http://localhost:11434/

# Test chat endpoint
curl -X POST http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3.5:397b-cloud","messages":[{"role":"user","content":"test"}],"stream":false}'

# Test curator
curl -X POST http://localhost:11434/curator/run
```

## License

MIT License - see LICENSE file for details.

## Support

- **Issues**: http://10.0.0.61:3000/SpeedyFoxAi/vera-ai-v2/issues
- **Repository**: http://10.0.0.61:3000/SpeedyFoxAi/vera-ai-v2