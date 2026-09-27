"""Settings. Defaults work out of the box with Ollama on a Mac; override in smart9b.json."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class ModelEndpoint:
    # "ollama" talks to Ollama's /api/chat. "openai" talks to any OpenAI-compatible
    # server (mlx_lm.server, LM Studio, vLLM, a hosted Muse Glimmer provider...).
    backend: str = "ollama"
    base_url: str = "http://localhost:11434"
    model: str = "qwen3.5:9b"
    # Name of the environment variable holding the API key (never the key itself).
    api_key_env: str = ""
    temperature: float = 0.3
    # Qwen3 / Qwen3.5 models think before answering unless the prompt ends in /no_think.
    # When true, quick steps (picking notes, planning searches, short lessons) skip
    # thinking for speed; solving, writing notes and grading still think.
    no_think_suffix: bool = False
    # Servers default to short replies / small context windows, which cut off thinking
    # and research notes. 16k context fits three web sources plus the skill notes.
    max_tokens: int = 4096
    context_length: int = 16384
    timeout: int = 600


@dataclass
class Config:
    home: Path = Path(".")
    worker: ModelEndpoint = field(default_factory=ModelEndpoint)
    # The teacher is optional. Point it at Muse Glimmer (or any stronger model)
    # when you have one running; until then stuck tasks wait in the queue.
    teacher: ModelEndpoint | None = None
    # Web search: "duckduckgo" needs no setup; "searxng" uses your own instance.
    search_backend: str = "duckduckgo"
    searxng_url: str = "http://localhost:8080"
    max_sources: int = 3
    max_attempts: int = 3
    # Model-written code only runs after you type "y", unless this is true.
    auto_run_code: bool = False
    code_timeout: int = 60

    @property
    def skills_dir(self) -> Path:
        return self.home / "skills"

    @property
    def journal_path(self) -> Path:
        return self.home / "journal.jsonl"

    @property
    def queue_dir(self) -> Path:
        return self.home / "teacher_queue"

    @property
    def sandbox_dir(self) -> Path:
        return self.home / "sandbox"

    @property
    def data_dir(self) -> Path:
        return self.home / "training_data"

    def ensure_dirs(self) -> None:
        for d in (self.skills_dir, self.queue_dir, self.sandbox_dir, self.data_dir):
            d.mkdir(parents=True, exist_ok=True)


def _endpoint(raw: dict | None, fallback: ModelEndpoint | None) -> ModelEndpoint | None:
    if raw is None:
        return fallback
    base = asdict(fallback) if fallback else asdict(ModelEndpoint())
    base.update(raw)
    return ModelEndpoint(**base)


def load_config(home: str | Path | None = None) -> Config:
    home = Path(home or os.environ.get("SMART9B_HOME", ".")).expanduser().resolve()
    cfg = Config(home=home)
    path = home / "smart9b.json"
    if path.exists():
        raw = json.loads(path.read_text())
        cfg.worker = _endpoint(raw.pop("worker", None), cfg.worker)
        cfg.teacher = _endpoint(raw.pop("teacher", None), None)
        for key, value in raw.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)
    cfg.ensure_dirs()
    return cfg
