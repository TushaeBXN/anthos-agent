#!/usr/bin/env python3
"""
anthos_serve.py — OpenAI-compatible API server for the Anthos Qwen LoRA model.

Serves the Anthos model (Qwen2.5-1.5B + LoRA) as an OpenAI-compatible
/v1/chat/completions endpoint. Designed to work with Anthos Agent's
provider system.

Two deployment modes:
  - Local (CPU):  python anthos_serve.py --local
  - Remote (GPU): python anthos_serve.py --remote (bfloat16, CUDA)

Usage:
  # Local CPU inference (default)
  python anthos_serve.py

  # With custom checkpoint path
  python anthos_serve.py --checkpoint /path/to/checkpoints/anthos-qwen-lora/final

  # GPU mode (RunPod, cloud VM, etc.)
  python anthos_serve.py --remote --device cuda

  # Custom port
  python anthos_serve.py --port 8321

Environment variables:
  ANTHOS_CHECKPOINT    Path to LoRA checkpoint (default: auto-detect)
  ANTHOS_DEVICE        "cpu" or "cuda" (default: auto)
  ANTHOS_PORT          Server port (default: 8321)
  ANTHOS_API_KEY       Optional API key for authentication
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [anthos-serve] %(message)s",
)
log = logging.getLogger(__name__)

# Lazy-loaded globals
_model = None
_tokenizer = None
_device = None

DEFAULT_PORT = 8321
DEFAULT_BASE_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"

CANDIDATE_CHECKPOINT_PATHS = [
    Path.home() / "Desktop" / "anthos-repo" / "checkpoints" / "anthos-qwen-lora" / "final",
    Path.home() / "anthos" / "checkpoints" / "anthos-qwen-lora" / "final",
    Path("checkpoints") / "anthos-qwen-lora" / "final",
]


def _find_checkpoint() -> Optional[Path]:
    env = os.getenv("ANTHOS_CHECKPOINT", "").strip()
    if env:
        p = Path(env)
        if p.exists():
            return p
        log.warning("ANTHOS_CHECKPOINT=%s does not exist", env)

    for candidate in CANDIDATE_CHECKPOINT_PATHS:
        if candidate.exists() and (candidate / "adapter_config.json").exists():
            return candidate
    return None


def _load_model(checkpoint: str | Path | None = None, device: str = "cpu"):
    global _model, _tokenizer, _device
    if _model is not None:
        return

    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import PeftModel

    checkpoint = Path(checkpoint) if checkpoint else _find_checkpoint()
    if not checkpoint or not checkpoint.exists():
        log.error(
            "No Anthos checkpoint found. Set ANTHOS_CHECKPOINT or place "
            "checkpoints at one of: %s",
            [str(p) for p in CANDIDATE_CHECKPOINT_PATHS],
        )
        sys.exit(1)

    _device = device
    dtype = torch.bfloat16 if device == "cuda" else torch.float32

    log.info("Loading tokenizer from %s", checkpoint)
    _tokenizer = AutoTokenizer.from_pretrained(
        str(checkpoint), trust_remote_code=True
    )
    _tokenizer.pad_token = _tokenizer.eos_token

    log.info("Loading base model %s (dtype=%s, device=%s)", DEFAULT_BASE_MODEL, dtype, device)
    base = AutoModelForCausalLM.from_pretrained(
        DEFAULT_BASE_MODEL,
        torch_dtype=dtype,
        device_map=device,
        trust_remote_code=True,
    )

    log.info("Loading LoRA adapters from %s", checkpoint)
    _model = PeftModel.from_pretrained(base, str(checkpoint))
    _model.eval()
    log.info("Model loaded successfully on %s", device)


def _generate(messages: list[dict], **kwargs) -> dict:
    """Run chat completion and return an OpenAI-compatible response."""
    import torch

    max_tokens = kwargs.get("max_tokens", 512)
    temperature = kwargs.get("temperature", 0.7)
    top_p = kwargs.get("top_p", 0.9)
    top_k = kwargs.get("top_k", 40)

    text = _tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = _tokenizer(text, return_tensors="pt")
    if _device == "cuda":
        inputs = {k: v.cuda() for k, v in inputs.items()}

    prompt_tokens = inputs["input_ids"].shape[1]
    t0 = time.time()

    with torch.no_grad():
        output = _model.generate(
            **inputs,
            max_new_tokens=max_tokens,
            temperature=max(temperature, 0.01),
            top_k=top_k,
            top_p=top_p,
            repetition_penalty=1.2,
            do_sample=temperature > 0,
            pad_token_id=_tokenizer.eos_token_id,
        )

    elapsed = time.time() - t0
    new_tokens = output[0][prompt_tokens:]
    completion_tokens = len(new_tokens)
    reply = _tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
    tok_per_s = completion_tokens / elapsed if elapsed > 0 else 0

    log.info(
        "Generated %d tokens in %.2fs (%.1f tok/s)",
        completion_tokens, elapsed, tok_per_s,
    )

    return {
        "id": f"chatcmpl-anthos-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "anthos-qwen-1.5b",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": reply},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def _build_app(api_key: str | None = None):
    """Build the FastAPI app with OpenAI-compatible endpoints."""
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import JSONResponse

    app = FastAPI(title="Anthos Model Server", version="0.1.0")

    def _check_auth(request: Request):
        if not api_key:
            return
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing Bearer token")
        if auth[7:] != api_key:
            raise HTTPException(status_code=401, detail="Invalid API key")

    @app.get("/v1/models")
    async def list_models(request: Request):
        _check_auth(request)
        return {
            "object": "list",
            "data": [
                {
                    "id": "anthos-qwen-1.5b",
                    "object": "model",
                    "created": 1719000000,
                    "owned_by": "brian-tushae-thomas",
                }
            ],
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        _check_auth(request)
        body = await request.json()

        messages = body.get("messages", [])
        if not messages:
            raise HTTPException(status_code=400, detail="messages is required")

        result = _generate(
            messages,
            max_tokens=body.get("max_tokens", 512),
            temperature=body.get("temperature", 0.7),
            top_p=body.get("top_p", 0.9),
            top_k=body.get("top_k", 40),
        )
        return JSONResponse(content=result)

    @app.get("/health")
    async def health():
        return {"status": "ok", "model_loaded": _model is not None}

    return app


def main():
    parser = argparse.ArgumentParser(description="Anthos Model Server")
    parser.add_argument(
        "--checkpoint", type=str, default=None,
        help="Path to LoRA checkpoint directory",
    )
    parser.add_argument(
        "--port", type=int,
        default=int(os.getenv("ANTHOS_PORT", str(DEFAULT_PORT))),
        help=f"Server port (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--device", type=str,
        default=os.getenv("ANTHOS_DEVICE", "auto"),
        help="Device: cpu, cuda, or auto (default: auto)",
    )
    parser.add_argument(
        "--remote", action="store_true",
        help="GPU mode — uses bfloat16 and CUDA",
    )
    parser.add_argument(
        "--local", action="store_true", default=True,
        help="CPU mode (default)",
    )
    parser.add_argument(
        "--api-key", type=str,
        default=os.getenv("ANTHOS_API_KEY"),
        help="Optional API key for authentication",
    )
    args = parser.parse_args()

    device = args.device
    if device == "auto":
        import torch
        device = "cuda" if (args.remote and torch.cuda.is_available()) else "cpu"

    log.info("Starting Anthos Model Server on port %d (device=%s)", args.port, device)
    _load_model(checkpoint=args.checkpoint, device=device)

    app = _build_app(api_key=args.api_key)

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
