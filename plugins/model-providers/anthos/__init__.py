"""Anthos model provider — local CPU inference or remote RunPod GPU.

Supports two modes:
  - Local: serves the Qwen2.5-1.5B LoRA model on localhost via the
    bundled anthos-serve server (CPU inference, ~tokens/sec).
  - Remote: connects to a RunPod serverless endpoint running the same
    model with GPU acceleration.

Both expose an OpenAI-compatible /v1/chat/completions API.

Environment variables:
  ANTHOS_API_KEY      API key for authentication (local or RunPod).
  ANTHOS_REMOTE_URL   RunPod (or any OpenAI-compatible) endpoint URL.
                      When set, the provider routes all requests to this
                      URL instead of localhost. Example:
                        https://api.runpod.ai/v2/<endpoint-id>/openai/v1
  ANTHOS_PORT         Local server port (default: 8321). Only used when
                      ANTHOS_REMOTE_URL is not set.
"""

import os
import logging

from providers import register_provider
from providers.base import ProviderProfile

log = logging.getLogger(__name__)

_remote_url = os.getenv("ANTHOS_REMOTE_URL", "").strip()
_local_port = os.getenv("ANTHOS_PORT", "8321").strip()

if _remote_url:
    _base_url = _remote_url.rstrip("/")
    if not _base_url.endswith("/v1"):
        _base_url += "/v1"
    _mode = "remote"
    _env_vars = ("ANTHOS_API_KEY", "ANTHOS_REMOTE_URL")
    log.info("Anthos provider: remote mode → %s", _base_url)
else:
    _base_url = f"http://localhost:{_local_port}/v1"
    _mode = "local"
    _env_vars = ("ANTHOS_API_KEY",)

anthos = ProviderProfile(
    name="anthos",
    aliases=("anthos-local", "anthos-gpu"),
    display_name="Anthos AI",
    description=f"Anthos model by Brian Tushae Thomas — {_mode} ({_base_url})",
    env_vars=_env_vars,
    base_url=_base_url,
    auth_type="api_key",
    supports_health_check=True,
    supports_vision=False,
    fallback_models=(
        "anthos-qwen-1.5b",
    ),
    default_max_tokens=2048,
)

register_provider(anthos)
