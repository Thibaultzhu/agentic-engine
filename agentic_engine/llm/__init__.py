"""LLM client for Bailian (DashScope) OpenAI-compatible API.

Also home of the multi-provider abstraction. Supported providers (via
OpenAI-compatible endpoints):
    - bailian (default, Qwen)
    - deepseek
    - openai
    - ollama (local)
    - anthropic-compat (any 3rd-party gateway exposing OpenAI shape)

Usage tracking is recorded into UsageTracker on every successful call.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from ..config import get_settings


@dataclass
class Provider:
    name: str
    base_url: str
    api_key_env: str
    default_model: str

    def client(self) -> OpenAI:
        key = os.getenv(self.api_key_env, "")
        if not key:
            raise RuntimeError(f"env var {self.api_key_env} not set")
        return OpenAI(api_key=key, base_url=self.base_url)


PROVIDERS: dict[str, Provider] = {
    "bailian-cn": Provider(
        name="bailian-cn",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="DASHSCOPE_API_KEY_CN",
        default_model="qwen-plus",
    ),
    "bailian-sg": Provider(
        name="bailian-sg",
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        api_key_env="DASHSCOPE_API_KEY_SG",
        default_model="qwen-plus",
    ),
    "deepseek": Provider(
        name="deepseek",
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
        default_model="deepseek-chat",
    ),
    "openai": Provider(
        name="openai",
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        default_model="gpt-4o-mini",
    ),
    "ollama": Provider(
        name="ollama",
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        api_key_env="OLLAMA_API_KEY",  # any non-empty value works for ollama
        default_model="qwen2.5:7b",
    ),
}


def make_client(api_key: str | None = None, base_url: str | None = None,
                provider: str | None = None) -> OpenAI:
    if provider:
        return PROVIDERS[provider].client()
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
    provider: str | None = None,
    agent_name: str = "anonymous",
    track_usage: bool = True,
) -> Any:
    """Single chat completion. Returns the raw OpenAI ChatCompletion response."""
    s = get_settings()
    if provider:
        prov = PROVIDERS[provider]
        client = prov.client()
        used_model = model or prov.default_model
    else:
        client = make_client()
        used_model = model or s.model_default
    kwargs: dict[str, Any] = {
        "model": used_model,
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    if extra_body:
        kwargs["extra_body"] = extra_body
    resp = client.chat.completions.create(**kwargs)

    if track_usage:
        try:
            from ..core.usage import default_tracker
            usage = getattr(resp, "usage", None)
            if usage:
                default_tracker().record(
                    agent=agent_name,
                    model=used_model,
                    prompt=getattr(usage, "prompt_tokens", 0) or 0,
                    completion=getattr(usage, "completion_tokens", 0) or 0,
                )
        except Exception:
            pass
    return resp
