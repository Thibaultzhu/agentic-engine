"""Cron — scheduled tasks via APScheduler (lazy-imported).

Stores job definitions in {home}/cron.json so they survive restarts.
Each job carries a payload `{type: "agent_turn", message, model}` that is
executed by spinning up an Agent on demand.

Install:  pip install apscheduler
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable

from ..config import get_settings


@dataclass
class CronJob:
    id: str
    name: str
    schedule: dict[str, Any]   # {"kind":"cron","expr":"0 9 * * *"} | {"kind":"interval","seconds":N} | {"kind":"date","run_at":"ISO"}
    payload: dict[str, Any]    # {"type":"agent_turn","message":"...","model":None}
    enabled: bool = True


class CronManager:
    def __init__(self, runner: Callable[[dict[str, Any]], Any] | None = None):
        s = get_settings()
        self.path = s.home / "cron.json"
        self.runner = runner or self._default_runner
        self._scheduler = None
        self.jobs: list[CronJob] = self._load()

    def _load(self) -> list[CronJob]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text())
        return [CronJob(**j) for j in data]

    def _save(self) -> None:
        self.path.write_text(
            json.dumps([asdict(j) for j in self.jobs], ensure_ascii=False, indent=2),
        )

    # ---------- CRUD ----------
    def add(self, name: str, schedule: dict[str, Any], payload: dict[str, Any]) -> CronJob:
        job = CronJob(id=uuid.uuid4().hex[:8], name=name, schedule=schedule, payload=payload)
        self.jobs.append(job)
        self._save()
        if self._scheduler:
            self._add_to_scheduler(job)
        return job

    def remove(self, job_id: str) -> bool:
        before = len(self.jobs)
        self.jobs = [j for j in self.jobs if j.id != job_id]
        self._save()
        if self._scheduler:
            try:
                self._scheduler.remove_job(job_id)
            except Exception:
                pass
        return len(self.jobs) < before

    def list(self) -> list[CronJob]:
        return list(self.jobs)

    # ---------- runtime ----------
    def start(self) -> None:
        from apscheduler.schedulers.background import BackgroundScheduler
        self._scheduler = BackgroundScheduler()
        for job in self.jobs:
            if job.enabled:
                self._add_to_scheduler(job)
        self._scheduler.start()

    def stop(self) -> None:
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None

    def _add_to_scheduler(self, job: CronJob) -> None:
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger
        from apscheduler.triggers.date import DateTrigger

        kind = job.schedule.get("kind")
        if kind == "cron":
            trig = CronTrigger.from_crontab(job.schedule["expr"])
        elif kind == "interval":
            trig = IntervalTrigger(seconds=int(job.schedule["seconds"]))
        elif kind == "date":
            trig = DateTrigger(run_date=job.schedule["run_at"])
        else:
            raise ValueError(f"unknown schedule kind: {kind}")

        self._scheduler.add_job(self.runner, trigger=trig, args=[job.payload], id=job.id, replace_existing=True)

    # ---------- default runner ----------
    @staticmethod
    def _default_runner(payload: dict[str, Any]) -> Any:
        if payload.get("type") == "agent_turn":
            from .agent import Agent
            from ..tools import read_file, list_dir, grep_text, web_fetch
            a = Agent(
                name=payload.get("agent_name", "cron"),
                tools=[read_file, list_dir, grep_text, web_fetch],
                model=payload.get("model"),
            )
            return a.run(payload["message"], verbose=False).output
        return f"[cron] unknown payload: {payload}"
