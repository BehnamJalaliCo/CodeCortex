"""In-process job executor backed by the durable job ledger."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from codecortex.jobs.store import JobRecord, JobStore

EventSink = Callable[[str, dict[str, Any]], object]


class JobManager:
    def __init__(
        self,
        store: JobStore,
        *,
        max_workers: int = 4,
        event_sink: EventSink | None = None,
    ) -> None:
        self.store = store
        self.executor = ThreadPoolExecutor(
            max_workers=max(1, max_workers), thread_name_prefix="cortex-job"
        )
        self._futures: dict[str, Future[dict[str, Any]]] = {}
        self.event_sink = event_sink

    def _emit(self, event_type: str, job: JobRecord) -> None:
        if self.event_sink is None:
            return
        self.event_sink(
            event_type,
            {
                "job_id": job.job_id,
                "kind": job.kind,
                "status": job.status.value,
                "progress": job.progress,
                "workspace": job.workspace,
                "repository_id": job.repository_id,
            },
        )

    def submit(
        self,
        kind: str,
        payload: dict[str, Any],
        operation: Callable[[], dict[str, Any]],
        *,
        actor: str,
        workspace: str | None = None,
        repository_id: str | None = None,
    ) -> JobRecord:
        job = self.store.create(
            kind,
            payload,
            actor=actor,
            workspace=workspace,
            repository_id=repository_id,
        )
        self._emit("job.queued", job)
        future = self.executor.submit(self._run, job.job_id, operation)
        self._futures[job.job_id] = future
        return job

    def _run(self, job_id: str, operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        current = self.store.get(job_id)
        if current is None:
            raise KeyError(job_id)
        if current.status.value == "cancelled":
            return {}
        running = self.store.start(job_id)
        self._emit("job.started", running)
        try:
            result = operation()
        except Exception as exc:
            failed = self.store.fail(job_id, f"{type(exc).__name__}: {exc}")
            self._emit("job.failed", failed)
            return {}
        completed = self.store.complete(job_id, result)
        self._emit("job.completed", completed)
        return result

    def cancel(self, job_id: str) -> JobRecord:
        future = self._futures.get(job_id)
        if future is not None:
            future.cancel()
        cancelled = self.store.cancel(job_id)
        self._emit("job.cancelled", cancelled)
        return cancelled

    def close(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)
