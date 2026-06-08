from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class JobRecord:
    id: str
    ticker: str
    date: str
    status: str = "pending"
    progress: list[str] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None


class JobManager:
    def __init__(self, *, max_running: int = 2) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()
        self._max_running = max(1, max_running)

    def _running_count_unlocked(self) -> int:
        return sum(1 for j in self._jobs.values() if j.status == "running")

    def running_count(self) -> int:
        with self._lock:
            return self._running_count_unlocked()

    def create(self, ticker: str, date: str) -> JobRecord:
        job_id = uuid.uuid4().hex[:12]
        job = JobRecord(id=job_id, ticker=ticker.upper(), date=date)
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def run_in_background(
        self,
        job: JobRecord,
        runner: Callable[[Callable[[str], None]], dict[str, Any]],
    ) -> None:
        with self._lock:
            if self._running_count_unlocked() >= self._max_running:
                raise RuntimeError(
                    f"동시 실행 한도({self._max_running})에 도달했습니다. 잠시 후 다시 시도하세요."
                )

        def _work() -> None:
            with self._lock:
                job.status = "running"

            def on_progress(msg: str) -> None:
                with self._lock:
                    job.progress.append(msg)

            try:
                result = runner(on_progress)
                with self._lock:
                    job.result = result
                    job.status = "done"
            except Exception as e:
                with self._lock:
                    job.error = f"{type(e).__name__}: {e}"
                    job.status = "error"

        threading.Thread(target=_work, daemon=True).start()

    def to_dict(self, job: JobRecord) -> dict[str, Any]:
        return {
            "id": job.id,
            "ticker": job.ticker,
            "date": job.date,
            "status": job.status,
            "progress": list(job.progress),
            "result": job.result,
            "error": job.error,
        }
