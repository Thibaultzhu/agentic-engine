"""Token usage tracking — file-backed JSONL ledger with simple aggregation."""
from __future__ import annotations

import datetime as _dt
import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..config import get_settings


@dataclass
class UsageRecord:
    timestamp: str
    agent: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_cny: float = 0.0


# Rough CNY per 1M tokens (input, output). Update freely.
_PRICE = {
    "qwen-turbo": (0.3, 0.6),
    "qwen-plus": (0.8, 2.0),
    "qwen-max": (20.0, 60.0),
    "qwen3-max": (20.0, 60.0),
    "qwen3-plus": (0.8, 2.0),
}


def estimate_cost(model: str, prompt: int, completion: int) -> float:
    p_in, p_out = _PRICE.get(model, (0.0, 0.0))
    return (prompt / 1_000_000) * p_in + (completion / 1_000_000) * p_out


_FILE_LOCK = threading.Lock()


class UsageTracker:
    def __init__(self, path: Path | None = None):
        s = get_settings()
        self.path = path or (s.home / "usage.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, agent: str, model: str, prompt: int, completion: int) -> UsageRecord:
        rec = UsageRecord(
            timestamp=_dt.datetime.now().isoformat(timespec="seconds"),
            agent=agent,
            model=model,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
            cost_cny=round(estimate_cost(model, prompt, completion), 6),
        )
        line = json.dumps(asdict(rec), ensure_ascii=False) + "\n"
        with _FILE_LOCK:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line)
        return rec

    def all(self) -> list[UsageRecord]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text().splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            out.append(UsageRecord(**d))
        return out

    def summary(self, days: int | None = None) -> dict[str, Any]:
        records = self.all()
        if days is not None:
            cutoff = _dt.datetime.now() - _dt.timedelta(days=days)
            records = [r for r in records if _dt.datetime.fromisoformat(r.timestamp) >= cutoff]
        by_model: dict[str, dict[str, float]] = {}
        total_prompt = total_completion = 0
        total_cost = 0.0
        for r in records:
            slot = by_model.setdefault(r.model, {"prompt": 0, "completion": 0, "cost": 0.0, "calls": 0})
            slot["prompt"] += r.prompt_tokens
            slot["completion"] += r.completion_tokens
            slot["cost"] += r.cost_cny
            slot["calls"] += 1
            total_prompt += r.prompt_tokens
            total_completion += r.completion_tokens
            total_cost += r.cost_cny
        return {
            "calls": len(records),
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
            "cost_cny": round(total_cost, 4),
            "by_model": by_model,
        }


# Singleton helper
_default: UsageTracker | None = None


def default_tracker() -> UsageTracker:
    global _default
    if _default is None:
        _default = UsageTracker()
    return _default
