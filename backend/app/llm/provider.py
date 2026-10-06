"""
provider.py

Provider-agnostic LLM interface for tool/function calling. The chatbot orchestrator talks
only to this interface, never to a specific vendor SDK, so the model/provider can be swapped
via environment variables (LLM_PROVIDER, LLM_API_KEY, LLM_MODEL, LLM_BASE_URL) without touching
chatbot code.

Two implementations:
  - OpenAIToolCallingProvider: calls an OpenAI-compatible /chat/completions endpoint with the
    `tools` parameter (OpenAI, and most self-hosted/OpenAI-compatible gateways implement this
    same schema). This is the real LLM integration path.
  - NullProvider: used when LLM_PROVIDER=none (or no API key is configured). It performs no
    network call and tells the orchestrator to fall back to the deterministic intent classifier
    in app/chatbot/nlu.py. This is NOT a fake LLM response generator -- it never answers a
    question itself; it only signals "no LLM available" so the orchestrator can use the
    deterministic tool-routing path instead (see docs/CHATBOT.md for what each path covers).

No API key is ever hard-coded; everything comes from Settings (see app/config.py).
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import httpx

from app.config import get_settings


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResult:
    """Either the model asked to call tool(s), or it produced a final text answer -- never both."""
    tool_calls: list = field(default_factory=list)   # list[ToolCall]
    text: Optional[str] = None
    raw_finish_reason: Optional[str] = None


class LLMProvider(ABC):
    @abstractmethod
    def available(self) -> bool:
        """True if this provider can actually be called (has credentials etc.)."""

    @abstractmethod
    def chat(self, messages: list, tools: list) -> LLMResult:
        """messages: OpenAI-style [{role, content, ...}]. tools: OpenAI-style tool schemas."""


class NullProvider(LLMProvider):
    """No LLM configured. Signals unavailability; never fabricates a response."""

    def available(self) -> bool:
        return False

    def chat(self, messages: list, tools: list) -> LLMResult:
        raise RuntimeError("NullProvider cannot be called -- check available() first.")


class OpenAIToolCallingProvider(LLMProvider):
    """Real LLM integration using an OpenAI-compatible Chat Completions API with `tools`."""

    def __init__(self, api_key: str, model: str, base_url: str):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")

    def available(self) -> bool:
        return bool(self._api_key)

    def chat(self, messages: list, tools: list) -> LLMResult:
        if not self.available():
            raise RuntimeError("OpenAIToolCallingProvider has no API key configured.")
        payload = {"model": self._model, "messages": messages, "temperature": 0.2}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        try:
            resp = httpx.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json=payload, timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            raise RuntimeError(f"LLM provider request failed: {e}") from e

        choice = data["choices"][0]
        msg = choice["message"]
        raw_calls = msg.get("tool_calls") or []
        if raw_calls:
            calls = []
            for c in raw_calls:
                try:
                    args = json.loads(c["function"]["arguments"] or "{}")
                except (ValueError, KeyError):
                    args = {}
                calls.append(ToolCall(id=c.get("id", ""), name=c["function"]["name"], arguments=args))
            return LLMResult(tool_calls=calls, raw_finish_reason=choice.get("finish_reason"))
        return LLMResult(text=msg.get("content") or "", raw_finish_reason=choice.get("finish_reason"))


_provider_singleton = None


def get_llm_provider() -> LLMProvider:
    global _provider_singleton
    if _provider_singleton is not None:
        return _provider_singleton
    s = get_settings()
    if s.llm_provider == "openai" and s.llm_api_key:
        _provider_singleton = OpenAIToolCallingProvider(s.llm_api_key, s.llm_model, s.llm_base_url)
    else:
        _provider_singleton = NullProvider()
    return _provider_singleton


def reset_provider_cache():
    """Test helper: forces get_llm_provider() to re-read settings on next call."""
    global _provider_singleton
    _provider_singleton = None
