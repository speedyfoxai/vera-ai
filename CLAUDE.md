# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Infrastructure

| Role | Host | Access |
|------|------|--------|
| Source (deb9) | 10.0.0.48 | `ssh deb9` — `/home/n8n/vera-ai/` |
| Production (deb8) | 10.0.0.46 | `ssh deb8` — runs vera-ai in Docker |
| Gitea | 10.0.0.61:3000 | `SpeedyFoxAi/vera-ai-v2`, HTTPS only (SSH disabled) |

User `n8n` on deb8/deb9. SSH key `~/.ssh/vera-ai`. Gitea credentials in `~/.netrc`.

## Git Workflow

Three locations — all point to `origin` on Gitea:

```
local (/home/adm1n/claude/vera-ai)  ←→  Gitea (10.0.0.61:3000)  ←→  deb9 (/home/n8n/vera-ai)
        ↓                                                                   ↓
  github/gitlab                                                  deb8 (scp files + docker build)
  (mirrors)
```

```bash
# Edit on deb9, commit, push
ssh deb9
cd /home/n8n/vera-ai
git pull origin main              # sync first
git add -p && git commit -m "..."
git push origin main

# Pull to local working copy
cd /home/adm1n/claude/vera-ai
git pull origin main

# Deploy to production (deb8 has no git repo — scp files then build)
scp app/*.py n8n@10.0.0.46:/home/n8n/vera-ai/app/
ssh deb8 'cd /home/n8n/vera-ai && docker compose build && docker compose up -d'
```

## Publishing (Docker Hub + Git Mirrors)

Image: `mdkrushr/vera-ai` on Docker Hub. Build and push from deb8:

```bash
ssh deb8
cd /home/n8n/vera-ai
docker build -t mdkrushr/vera-ai:2.0.4 -t mdkrushr/vera-ai:latest .
docker push mdkrushr/vera-ai:2.0.4
docker push mdkrushr/vera-ai:latest
```

The local repo has two mirror remotes for public distribution. After committing and pushing to `origin` (Gitea), mirror with:

```bash
git push github main --tags
git push gitlab main --tags
```

| Remote | URL |
|--------|-----|
| `origin` | `10.0.0.61:3000/SpeedyFoxAi/vera-ai-v2` (Gitea, primary) |
| `github` | `github.com/speedyfoxai/vera-ai` |
| `gitlab` | `gitlab.com/mdkrush/vera-ai` |

## Build & Run (deb8, production)

```bash
ssh deb8
cd /home/n8n/vera-ai
docker compose build
docker compose up -d
docker logs vera-ai --tail 30
curl http://localhost:11434/                   # health check
curl -X POST http://localhost:11434/curator/run  # trigger curation
```

## Tests (deb9, source)

```bash
ssh deb9
cd /home/n8n/vera-ai
python3 -m pytest tests/                                          # all tests
python3 -m pytest tests/test_utils.py                             # single file
python3 -m pytest tests/test_utils.py::TestParseCuratedTurn::test_single_turn  # single test
python3 -m pytest tests/ --cov=app --cov-report=term-missing      # with coverage
```

Tests are unit-only — no live Qdrant/Ollama required. `pytest.ini` sets `asyncio_mode=auto`. Shared fixtures with production-realistic data in `tests/conftest.py`.

Test files and what they cover:

| File | Covers |
|------|--------|
| `tests/test_utils.py` | Token counting, truncation, memory filtering/merging, `parse_curated_turn`, `load_system_prompt`, `build_augmented_messages` |
| `tests/test_config.py` | Config defaults, TOML loading, `CloudConfig`, env var overrides |
| `tests/test_curator.py` | JSON parsing, `_is_recent`, `_format_raw_turns`, `_format_existing_memories`, `_call_llm`, `_append_rule_to_file`, `load_curator_prompt`, full `run()` scenarios |
| `tests/test_proxy_handler.py` | `clean_message_content`, `handle_chat_non_streaming`, `debug_log`, `forward_to_ollama` |
| `tests/test_integration.py` | FastAPI health check, `/api/tags` (with cloud models), `/api/chat` round-trips (streaming + non-streaming), curator trigger, proxy passthrough |
| `tests/test_qdrant_service.py` | `_ensure_collection`, `get_embedding`, `store_turn`, `store_qa_turn`, `semantic_search`, `get_recent_turns`, `delete_points`, `close` |

## Architecture

```
Client → Vera-AI :11434 → Ollama :11434
               ↓↑
          Qdrant :6333
```

Vera-AI is a FastAPI proxy. Every `/api/chat` request is intercepted, augmented with memory context, forwarded to Ollama, and the response Q&A is stored back in Qdrant.

### 4-Layer Context System (`app/utils.py:build_augmented_messages`)

Each chat request builds an augmented message list in this order:

1. **System** — caller's system prompt passed through; `prompts/systemprompt.md` appended if non-empty (if empty, caller's prompt passes through unchanged; if no caller system prompt, vera's prompt used alone)
2. **Semantic** — curated AND raw Q&A pairs from Qdrant matching the query (score ≥ `semantic_score_threshold`, up to `semantic_token_budget` tokens). Searches both types to avoid a blind spot where raw turns fall off the recent window before curation runs.
3. **Recent context** — last 50 turns from Qdrant (server-sorted by timestamp via payload index), oldest first, up to `context_token_budget` tokens. Deduplicates against Layer 2 results to avoid wasting token budget.
4. **Current** — the incoming messages (non-system) passed through unchanged

The system prompt is **never truncated**. Semantic and context layers are budget-limited and drop excess entries silently.

### Memory Types in Qdrant

| Type | When created | Retention |
|------|-------------|-----------|
| `raw` | After each chat turn | Until curation runs |
| `curated` | After curator processes `raw` | Permanent |

Payload format: `{type, text, timestamp, role, content}`. Curated entries use `role="curated"` with text formatted as `User: ...\nAssistant: ...\nTimestamp: ...`, which `parse_curated_turn()` deserializes back into proper message role pairs at retrieval time.

### Curator (`app/curator.py`)

Scheduled via APScheduler at `config.run_time` (default 02:00). Automatically detects day 01 of month for monthly mode (processes ALL raw) vs. daily mode (last 24h only). Sends raw memories to `curator_model` LLM with `prompts/curator_prompt.md`, expects JSON response:

```json
{
  "new_curated_turns": [{"content": "User: ...\nAssistant: ..."}],
  "permanent_rules": [{"rule": "...", "target_file": "systemprompt.md"}],
  "deletions": ["uuid1", "uuid2"],
  "summary": "..."
}
```

`permanent_rules` are appended to the named file in `prompts/`. After curation, all processed raw entries are deleted.

### Cloud Model Routing

Optional `[cloud]` section in `config.toml` routes specific model names to an OpenRouter-compatible API instead of Ollama. Cloud models are injected into `/api/tags` so clients see them alongside local models.

```toml
[cloud]
enabled = true
api_base = "https://openrouter.ai/api/v1"
api_key_env = "OPENROUTER_API_KEY"
[cloud.models]
"gpt-oss:120b" = "openai/gpt-4o"
```

### Key Implementation Details

- **Config loading** uses stdlib `tomllib` (read-only, Python 3.11+). No third-party TOML dependency.
- **QdrantService singleton** lives in `app/singleton.py`. All modules import from there — `app/utils.py` re-exports via `from .singleton import get_qdrant_service`.
- **Datetime handling** uses `datetime.now(timezone.utc)` throughout. No `utcnow()` calls. Stored timestamps are naive UTC with "Z" suffix; comparison code strips tzinfo for naive-vs-naive matching.
- **Debug logging** in `proxy_handler.py` uses `portalocker` for file locking under concurrent requests. Controlled by `config.debug`.

## Configuration

All settings in `config/config.toml`. Key tuning knobs:

- `semantic_token_budget` / `context_token_budget` — controls how much memory gets injected
- `semantic_score_threshold` — lower = more (but less relevant) memories returned
- `curator_model` — model used for daily curation (needs strong reasoning)
- `debug = true` — enables per-request JSON logs written to `logs/debug_YYYY-MM-DD.log`

Environment variable overrides: `VERA_CONFIG_DIR`, `VERA_PROMPTS_DIR`, `VERA_LOG_DIR`.

## Related Services

| Service | Host | Port |
|---------|------|------|
| Ollama | 10.0.0.10 | 11434 |
| Qdrant | 10.0.0.22 | 6333 |

Qdrant collections: `memories` (default), `vera_memories` (alternative), `python_kb` (reference patterns).
