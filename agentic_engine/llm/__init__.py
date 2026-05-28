"""LLM client for Bailian (DashScope) OpenAI-compatible API."""
from __future__ import annotations

from typing import Any

from openai import OpenAI

from ..config import get_settings


def make_client(api_key: str | None = None, base_url: str | None = None) -> OpenAI:
    s = get_settings()
    return OpenAI(
        api_key=api_key or s.api_key,
        base_url=base_url or s.base_url,
    )


def chat(
    messages: list[dict[str, Any]],
    model: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.7,
    extra_body: dict[str, Any] | None = None,
) -> Any:
    """Single chat completion. Returns the raw OpenAI ChatCompletion response."""
    s = get_settings()
    client = make_client()
    kwargs: dict[str, Any] = {
        "model": model or s.model_default,
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    if extra_body:
        kwargs["extra_body"] = extra_body
    return client.chat.completions.create(**kwargs)
