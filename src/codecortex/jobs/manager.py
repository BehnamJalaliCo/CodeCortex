"""In-process job executor backed by the durable job ledger."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from codecortex.jobs.store import JobRecord, JobStore


class JobManager:
    def __init__(self, store: JobStore, *, max_workers: int = 4) -> None:
        self.store = store
        self.executor = ThreadPoolExecutor(max_workers=max(1, max_workers), thread_name_prefix="cortex-job")
        self._futures: dict[str, Future[dict[str, Any]]] = {}

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
        future = self.executor.submit(self._run, job.job_id, operation)
        self._futures[job.job_id] = future
        return job

    def _run(self, job_id: str, operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        current = self.store.get(job_id)
        if current is None:
            raise KeyError(job_id)
        if current.status.value == "cancelled":
            return {}
        self.store.start(job_id)
        try:
            result = operation()
        except Exception as exc:
            self.store.fail(job_id, f"{type(exc).__name__}: {exc}")
            return {}
        self.store.complete(job_id, result)
        return result

    def cancel(self, job_id: str) -> JobRecord:
        future = self._futures.get(job_id)
        if future is not None:
            future.cancel()
        return self.store.cancel(job_id)

    def close(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)
