# Vera-AI: Persistent Memory Proxy for Ollama

[![Docker](https://img.shields.io/docker/pulls/vera-ai/latest)](https://hub.docker.com/r/vera-ai/latest)

**Vera-AI** is a transparent proxy for Ollama that adds persistent memory using Qdrant vector storage.

## Quick Start

```bash
# Clone or copy the project
git clone https://github.com/your-org/vera-ai.git
cd vera-ai

# Create environment file
cp .env.example .env

# Edit .env with your settings
nano .env

# Build and run
docker compose build
docker compose up -d

# Test
curl http://localhost:11434/
```

## Configuration

### Environment Variables (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_UID` | `999` | User ID for container user (match your host UID) |
| `APP_GID` | `999` | Group ID for container group (match your host GID) |
| `TZ` | `UTC` | Timezone for scheduler (e.g., `America/Chicago`) |
| `OPENROUTER_API_KEY` | - | API key for cloud model routing (optional) |

### Getting UID/GID

```bash
# Get your UID and GID
id -u   # UID
id -g   # GID

# Set in .env
APP_UID=1000
APP_GID=1000
```

### Volume Mappings

| Host Path | Container Path | Mode | Purpose |
|-----------|---------------|------|---------|
| `./config/` | `/app/config/` | `ro` | Configuration files |
| `./prompts/` | `/app/prompts/` | `rw` | Curator and system prompts |

### Directory Structure

```
vera-ai/
├── config/
│   └── config.toml       # Main configuration
├── prompts/
│   ├── curator_prompt.md # Prompt for memory curator
│   └── systemprompt.md   # System context (curator can append)
├── app/
│   ├── main.py
│   ├── config.py
│   ├── curator.py
│   ├── proxy_handler.py
│   ├── qdrant_service.py
│   └── utils.py
├── static/               # Legacy (symlinks to prompts/)
├── .env.example          # Environment template
├── docker-compose.yml    # Docker Compose config
├── Dockerfile            # Container definition
└── requirements.txt      # Python dependencies
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
      - ./config:/app/config:ro
      - ./prompts:/app/prompts:rw
    network_mode: "host"
    restart: unless-stopped
```

## Build & Run

```bash
# Build with custom UID/GID
APP_UID=$(id -u) APP_GID=$(id -g) docker compose build

# Run with timezone
TZ=America/Chicago docker compose up -d

# Or use .env file
docker compose build
docker compose up -d
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

## Troubleshooting

### Permission Denied

If you see permission errors on `/app/prompts/`:

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
docker exec vera-ai python -c "import urllib.request; print(urllib.request.urlopen('http://10.0.0.10:11434/').read())"
```

## License

MIT License - see LICENSE file for details.