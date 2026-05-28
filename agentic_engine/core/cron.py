"""Cron — scheduled tasks via APScheduler (lazy-imported).

Stores job definitions in {home}/cron.json so they survive restarts.
Each job carries a payload `{type: "agent_turn", message, model}` that is
executed by spinning up an Agent on demand.

v0.3 additions:
    * ``max_retries``, ``retry_backoff_s`` per job
    * dead-letter queue at ``{home}/cron.dlq.jsonl``
    * ``runs(job_id)`` — recent run history (success/error/elapsed)

Install:  pip install apscheduler
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import json
import logging
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from ..config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class CronJob:
    id: str
    name: str
    schedule: dict[str, Any]
    payload: dict[str, Any]
    enabled: bool = True
    max_retries: int = 0
    retry_backoff_s: float = 5.0


@dataclass
class CronRun:
    job_id: str
    started_at: str
    elapsed_s: float
    ok: bool
    error: str = ""
    attempts: int = 1


class CronManager:
    def __init__(self, runner: Callable[[dict[str, Any]], Any] | None = None):
        s = get_settings()
        self.path = s.home / "cron.json"
        self.dlq_path = s.home / "cron.dlq.jsonl"
        self.runner = runner or self._default_runner
        self._scheduler = None
        self.jobs: list[CronJob] = self._load()
        self._runs: dict[str, deque[CronRun]] = {}

    def _load(self) -> list[CronJob]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text())
        out: list[CronJob] = []
        for j in data:
            # Tolerate older payloads that lack new optional fields.
            j.setdefault("max_retries", 0)
            j.setdefault("retry_backoff_s", 5.0)
            out.append(CronJob(**j))
        return out

    def _save(self) -> None:
        self.path.write_text(
            json.dumps([asdict(j) for j in self.jobs], ensure_ascii=False, indent=2),
        )

    # ---------- CRUD ----------
    def add(self, name: str, schedule: dict[str, Any], payload: dict[str, Any],
            max_retries: int = 0, retry_backoff_s: float = 5.0) -> CronJob:
        self._build_trigger(schedule)
        job = CronJob(
            id=uuid.uuid4().hex[:8], name=name, schedule=schedule, payload=payload,
            max_retries=max_retries, retry_backoff_s=retry_backoff_s,
        )
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
            with contextlib.suppress(Exception):
                self._scheduler.remove_job(job_id)
        return len(self.jobs) < before

    def enable(self, job_id: str) -> bool:
        for j in self.jobs:
            if j.id == job_id:
                if j.enabled:
                    return False
                j.enabled = True
                self._save()
                if self._scheduler:
                    self._add_to_scheduler(j)
                return True
        raise KeyError(f"cron job {job_id} not found")

    def disable(self, job_id: str) -> bool:
        for j in self.jobs:
            if j.id == job_id:
                if not j.enabled:
                    return False
                j.enabled = False
                self._save()
                if self._scheduler:
                    with contextlib.suppress(Exception):
                        self._scheduler.remove_job(job_id)
                return True
        raise KeyError(f"cron job {job_id} not found")

    def list(self) -> list[CronJob]:
        return list(self.jobs)

    def runs(self, job_id: str) -> list[CronRun]:
        return list(self._runs.get(job_id, []))

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
        trig = self._build_trigger(job.schedule)
        self._scheduler.add_job(  # type: ignore[union-attr]
            self._invoke_with_retry,
            trigger=trig,
            args=[job],
            id=job.id,
            replace_existing=True,
        )

    def _invoke_with_retry(self, job: CronJob) -> None:
        """Run ``self.runner(job.payload)`` with exponential-backoff retry.

        On terminal failure, append the (job, error) to the dead-letter
        JSONL file so a human can inspect.
        """
        attempts = 0
        last_err = ""
        started = _dt.datetime.now().isoformat(timespec="seconds")
        t0 = time.time()
        for attempts in range(job.max_retries + 1):
            try:
                self.runner(job.payload)
                self._record_run(CronRun(
                    job_id=job.id, started_at=started, elapsed_s=time.time() - t0,
                    ok=True, attempts=attempts + 1,
                ))
                return
            except Exception as e:  # noqa: BLE001
                last_err = f"{type(e).__name__}: {e}"
                logger.warning("[cron] %s attempt %d failed: %s", job.id, attempts + 1, last_err)
                if attempts < job.max_retries:
                    time.sleep(job.retry_backoff_s * (2 ** attempts))
        # Terminal failure → DLQ.
        self._dlq(job, last_err)
        self._record_run(CronRun(
            job_id=job.id, started_at=started, elapsed_s=time.time() - t0,
            ok=False, error=last_err, attempts=attempts + 1,
        ))

    def _record_run(self, run: CronRun) -> None:
        bucket = self._runs.setdefault(run.job_id, deque(maxlen=20))
        bucket.append(run)

    def _dlq(self, job: CronJob, error: str) -> None:
        line = json.dumps({
            "ts": _dt.datetime.now().isoformat(timespec="seconds"),
            "job_id": job.id, "name": job.name, "payload": job.payload, "error": error,
        }, ensure_ascii=False)
        self.dlq_path.parent.mkdir(parents=True, exist_ok=True)
        with self.dlq_path.open("a") as f:
            f.write(line + "\n")

    @staticmethod
    def _build_trigger(schedule: dict[str, Any]):
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.date import DateTrigger
        from apscheduler.triggers.interval import IntervalTrigger

        kind = schedule.get("kind")
        if kind == "cron":
            return CronTrigger.from_crontab(schedule["expr"])
        if kind == "interval":
            return IntervalTrigger(seconds=int(schedule["seconds"]))
        if kind == "date":
            return DateTrigger(run_date=schedule["run_at"])
        raise ValueError(f"unknown schedule kind: {kind}")

    # ---------- default runner ----------
    @staticmethod
    def _default_runner(payload: dict[str, Any]) -> Any:
        if payload.get("type") == "agent_turn":
            from ..tools import grep_text, list_dir, read_file, web_fetch
            from .agent import Agent
            a = Agent(
                name=payload.get("agent_name", "cron"),
                tools=[read_file, list_dir, grep_text, web_fetch],
                model=payload.get("model"),
            )
            return a.run(payload["message"], verbose=False).output
        return f"[cron] unknown payload: {payload}"
