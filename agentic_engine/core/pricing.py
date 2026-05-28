"""Multi-region pricing and FX conversion for usage/cost reporting.

Wraps :mod:`core.usage` pricing with currency awareness:

- ``REGION_PRICING`` ships defaults for ``cn`` (CNY) and ``us`` (USD) and
  ``sg`` (SGD) per-1M tokens for popular Qwen / OpenAI / DeepSeek models.
- FX rates are read from ``${AGENTIC_HOME}/fx.json`` if present, else a
  static fallback table (``USD→CNY=7.20``, ``USD→SGD=1.35``).
- :func:`convert(amount, src, dst)` does cross-currency conversion via USD.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# (input_per_1M, output_per_1M) in the currency of the tuple's third item.
REGION_PRICING: dict[str, dict[str, tuple[float, float, str]]] = {
    "cn": {
        "qwen-plus": (4.0, 12.0, "CNY"),
        "qwen-max": (40.0, 120.0, "CNY"),
        "qwen-turbo": (1.0, 2.0, "CNY"),
        "deepseek-chat": (2.0, 8.0, "CNY"),
    },
    "sg": {
        "qwen-plus": (0.6, 1.7, "USD"),
        "qwen-max": (5.6, 16.8, "USD"),
        "qwen-turbo": (0.14, 0.28, "USD"),
    },
    "us": {
        "gpt-4o": (5.0, 15.0, "USD"),
        "gpt-4o-mini": (0.15, 0.60, "USD"),
        "deepseek-chat": (0.27, 1.10, "USD"),
    },
}

_FX_FALLBACK = {
    "USD": 1.0,
    "CNY": 1.0 / 7.20,  # 1 CNY ≈ 0.139 USD
    "SGD": 1.0 / 1.35,
    "EUR": 1.10,
}


def _fx_table() -> dict[str, float]:
    home = Path(os.environ.get("AGENTIC_HOME", str(Path.home() / ".agentic-engine")))
    p = home / "fx.json"
    if p.exists():
        try:
            data = json.loads(p.read_text())
            if isinstance(data, dict):
                return {k.upper(): float(v) for k, v in data.items()}
        except Exception:
            pass
    return dict(_FX_FALLBACK)


def convert(amount: float, src: str, dst: str) -> float:
    """Convert ``amount`` from ``src`` currency to ``dst``. Routes via USD."""
    src = src.upper()
    dst = dst.upper()
    if src == dst:
        return amount
    fx = _fx_table()
    if src not in fx or dst not in fx:
        raise ValueError(f"unknown currency: {src} or {dst}")
    in_usd = amount * fx[src]
    return in_usd / fx[dst]


def estimate(model: str, prompt_tokens: int, completion_tokens: int,
             region: str = "cn", target_currency: str | None = None) -> dict[str, Any]:
    """Cost estimate for one call.

    Returns ``{"model": ..., "region": ..., "currency": ..., "cost": ...}``.
    Falls back to zero cost if model unknown.
    """
    table = REGION_PRICING.get(region, {})
    triple = table.get(model)
    if not triple:
        return {"model": model, "region": region, "currency": target_currency or "CNY", "cost": 0.0}
    p_in, p_out, ccy = triple
    raw = (prompt_tokens / 1_000_000.0) * p_in + (completion_tokens / 1_000_000.0) * p_out
    if target_currency and target_currency.upper() != ccy:
        raw = convert(raw, ccy, target_currency)
        ccy = target_currency.upper()
    return {"model": model, "region": region, "currency": ccy, "cost": round(raw, 6)}


__all__ = ["REGION_PRICING", "convert", "estimate"]
