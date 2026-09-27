"""Minimal chat client for Ollama and OpenAI-compatible servers (stdlib only)."""

from __future__ import annotations

import json
import os
import re
import urllib.request

from .config import ModelEndpoint


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, endpoint: ModelEndpoint):
        self.ep = endpoint

    def chat(self, messages: list[dict], temperature: float | None = None) -> str:
        temp = self.ep.temperature if temperature is None else temperature
        if self.ep.backend == "ollama":
            url = self.ep.base_url.rstrip("/") + "/api/chat"
            body = {"model": self.ep.model, "messages": messages, "stream": False,
                    "options": {"temperature": temp, "num_predict": self.ep.max_tokens,
                                "num_ctx": self.ep.context_length}}
        elif self.ep.backend == "openai":
            url = self.ep.base_url.rstrip("/") + "/chat/completions"
            body = {"model": self.ep.model, "messages": messages, "temperature": temp,
                    "max_tokens": self.ep.max_tokens}
        else:
            raise LLMError(f"unknown backend {self.ep.backend!r}")

        headers = {"Content-Type": "application/json"}
        if self.ep.api_key_env:
            key = os.environ.get(self.ep.api_key_env, "")
            if not key:
                raise LLMError(f"environment variable {self.ep.api_key_env} is not set")
            headers["Authorization"] = f"Bearer {key}"

        req = urllib.request.Request(url, json.dumps(body).encode(), headers)
        try:
            with urllib.request.urlopen(req, timeout=self.ep.timeout) as resp:
                data = json.loads(resp.read())
        except Exception as exc:  # network errors, HTTP errors, bad JSON
            raise LLMError(f"{self.ep.model} at {url}: {exc}") from exc

        if self.ep.backend == "ollama":
            text = data.get("message", {}).get("content", "")
        else:
            text = data["choices"][0]["message"]["content"]
        return strip_thinking(text)

    def ask(self, system: str, user: str, temperature: float | None = None,
            think: bool = True) -> str:
        if not think and self.ep.no_think_suffix:
            user = user.rstrip() + " /no_think"
        return self.chat([{"role": "system", "content": system},
                          {"role": "user", "content": user}], temperature)

    def ask_json(self, system: str, user: str, think: bool = False) -> dict | list:
        """Ask for JSON; retry once with the parse error if the model fumbles it."""
        text = self.ask(system + "\nReply with JSON only.", user, temperature=0, think=think)
        try:
            return extract_json(text)
        except ValueError as exc:
            fixed = self.ask("You fix broken JSON. Reply with valid JSON only.",
                             f"Error: {exc}\n\nBroken JSON:\n{text}", temperature=0, think=False)
            return extract_json(fixed)


def strip_thinking(text: str) -> str:
    """Qwen reasoning models wrap their scratch work in <think> tags; drop it."""
    if "</think>" in text:
        # Some chat templates open <think> inside the prompt, so only the close shows up.
        text = text.rsplit("</think>", 1)[1]
    elif "<think>" in text:
        # Ran out of tokens mid-thought: there is no answer to keep.
        text = text.split("<think>", 1)[0]
    return text.strip()


def extract_json(text: str) -> dict | list:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        raise ValueError("no JSON object found")
    start = min(starts)
    closer = "}" if text[start] == "{" else "]"
    end = text.rfind(closer)
    if end < start:
        raise ValueError("unterminated JSON")
    return json.loads(text[start:end + 1])
