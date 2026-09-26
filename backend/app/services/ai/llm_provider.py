"""LLM provider abstraction — plain httpx calls (no heavy SDKs).

`LLM_PROVIDER` env selects `anthropic` / `openai` / `none`. When unset,
missing a key, or unreachable, the copilot falls back to the deterministic
rule engine — the demo always works offline."""

import json
import re
from typing import Protocol

import httpx

from app.core.config import get_settings

settings = get_settings()


class LLMProvider(Protocol):
    name: str

    def complete_json(self, system: str, user_prompt: str) -> dict | None: ...


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


class OpenAIProvider:
    name = "openai"
    URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.key, self.model = api_key, model

    def complete_json(self, system: str, user_prompt: str) -> dict | None:
        with httpx.Client(timeout=25) as client:
            res = client.post(
                self.URL,
                headers={"Authorization": f"Bearer {self.key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0,
                    "max_tokens": 900,
                    "response_format": {"type": "json_object"},
                },
            )
            res.raise_for_status()
            text = res.json()["choices"][0]["message"]["content"]
            return _extract_json(text)


class AnthropicProvider:
    name = "anthropic"
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        self.key, self.model = api_key, model

    def complete_json(self, system: str, user_prompt: str) -> dict | None:
        with httpx.Client(timeout=25) as client:
            res = client.post(
                self.URL,
                headers={
                    "x-api-key": self.key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "system": system,
                    "messages": [{"role": "user", "content": user_prompt}],
                    "max_tokens": 900,
                    "temperature": 0,
                },
            )
            res.raise_for_status()
            text = "".join(
                b.get("text", "") for b in res.json().get("content", [])
            )
            return _extract_json(text)


def get_provider() -> LLMProvider | None:
    provider = (settings.LLM_PROVIDER or "none").lower()
    if provider == "openai" and settings.OPENAI_API_KEY:
        return OpenAIProvider(settings.OPENAI_API_KEY)
    if provider == "anthropic" and settings.ANTHROPIC_API_KEY:
        return AnthropicProvider(settings.ANTHROPIC_API_KEY)
    return None
