# Langfuse Observability Plugin

This plugin ships bundled with Anthos but is **opt-in** — it only loads when
you explicitly enable it.

## Enable

Pick one:

```bash
# Interactive: walks you through credentials + SDK install + enable
anthos tools  # → Langfuse Observability

# Manual
pip install langfuse
anthos plugins enable observability/langfuse
```

## Required credentials

Set these in `~/.anthos/.env` (or via `anthos tools`):

```bash
ANTHOS_LANGFUSE_PUBLIC_KEY=pk-lf-...
ANTHOS_LANGFUSE_SECRET_KEY=sk-lf-...
ANTHOS_LANGFUSE_BASE_URL=https://cloud.langfuse.com   # or your self-hosted URL
```

Without the SDK or credentials the hooks no-op silently — the plugin fails
open.

## Verify

```bash
anthos plugins list                 # observability/langfuse should show "enabled"
anthos chat -q "hello"              # then check Langfuse for a "Anthos turn" trace
```

## Optional tuning

```bash
ANTHOS_LANGFUSE_ENV=production       # environment tag
ANTHOS_LANGFUSE_RELEASE=v1.0.0       # release tag
ANTHOS_LANGFUSE_SAMPLE_RATE=0.5      # sample 50% of traces
ANTHOS_LANGFUSE_MAX_CHARS=12000      # max chars per field (default: 12000)
ANTHOS_LANGFUSE_DEBUG=true           # verbose plugin logging
```

## Disable

```bash
anthos plugins disable observability/langfuse
```
