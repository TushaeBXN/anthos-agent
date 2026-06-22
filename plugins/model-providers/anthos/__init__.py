"""Anthos model provider — local CPU inference or remote RunPod GPU.

Supports two modes:
  - Local: serves the Qwen2.5-1.5B LoRA model on localhost via the
    bundled anthos-serve server (CPU inference, ~tokens/sec).
  - Remote: connects to a RunPod serverless endpoint running the same
    model with GPU acceleration.

Both expose an OpenAI-compatible /v1/chat/completions API.
"""

from providers import register_provider
from providers.base import ProviderProfile


anthos = ProviderProfile(
    name="anthos",
    aliases=("anthos-local", "anthos-gpu"),
    display_name="Anthos AI",
    description="Anthos model by Brian Tushae Thomas — local CPU or remote GPU",
    env_vars=("ANTHOS_API_KEY",),
    base_url="http://localhost:8321/v1",
    auth_type="api_key",
    supports_health_check=True,
    supports_vision=False,
    fallback_models=(
        "anthos-qwen-1.5b",
    ),
    default_max_tokens=2048,
)

register_provider(anthos)
