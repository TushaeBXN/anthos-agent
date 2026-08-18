# Mem0 Memory Provider

Server-side LLM fact extraction with semantic search, reranking, and automatic deduplication.

Supports both [Mem0 Cloud](https://app.mem0.ai) and self-hosted instances.

## Requirements

- `pip install mem0ai`
- Mem0 Cloud API key **or** a self-hosted Mem0 server

## Setup

### Cloud

```bash
anthos memory setup    # select "mem0"
```

Or manually:

```bash
anthos config set memory.provider mem0
echo "MEM0_API_KEY=your-key" >> ~/.anthos/.env
```

### Self-Hosted

```bash
anthos config set memory.provider mem0
echo "MEM0_HOST=http://your-mem0-server:24220" >> ~/.anthos/.env
echo "MEM0_API_KEY=your-api-key" >> ~/.anthos/.env   # if auth is enabled
```

## Config

Config file: `$ANTHOS_HOME/mem0.json`

| Key | Default | Description |
|-----|---------|-------------|
| `api_key` | — | API key (required for cloud; optional for self-hosted without auth) |
| `host` | `https://api.mem0.ai` | Self-hosted Mem0 URL. When set, overrides the cloud endpoint. |
| `user_id` | `anthos-user` | User identifier |
| `agent_id` | `anthos` | Agent identifier |
| `rerank` | `true` | Enable reranking for recall |

## Tools

| Tool | Description |
|------|-------------|
| `mem0_profile` | All stored memories about the user |
| `mem0_search` | Semantic search with optional reranking |
| `mem0_conclude` | Store a fact verbatim (no LLM extraction) |
