"""Configuration loader. Reads .env and exposes a typed Settings object."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Settings:
    region: str = "sg"
    api_key: str = ""
    base_url: str = ""
    model_default: str = "qwen-plus"
    model_fast: str = "qwen-turbo"
    model_strong: str = "qwen3-max"
    home: Path = field(default_factory=lambda: Path.home() / ".agentic-engine")

    @classmethod
    def load(cls, env_path: str | None = None) -> Settings:
        if env_path:
            load_dotenv(env_path)
        else:
            load_dotenv()
        region = (os.getenv("AGENTIC_REGION") or "sg").lower()
        if region == "cn":
            api_key = os.getenv("DASHSCOPE_API_KEY_CN", "")
            base_url = os.getenv(
                "DASHSCOPE_BASE_URL_CN",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
        else:
            api_key = os.getenv("DASHSCOPE_API_KEY_SG", "")
            base_url = os.getenv(
                "DASHSCOPE_BASE_URL_SG",
                "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            )
        home_raw = os.getenv("AGENTIC_HOME", "~/.agentic-engine")
        home = Path(os.path.expanduser(home_raw))
        home.mkdir(parents=True, exist_ok=True)
        return cls(
            region=region,
            api_key=api_key,
            base_url=base_url,
            model_default=os.getenv("AGENTIC_MODEL_DEFAULT", "qwen-plus"),
            model_fast=os.getenv("AGENTIC_MODEL_FAST", "qwen-turbo"),
            model_strong=os.getenv("AGENTIC_MODEL_STRONG", "qwen3-max"),
            home=home,
        )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.load()
    return _settings
