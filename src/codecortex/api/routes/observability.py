"""API observability routes and request middleware."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from codecortex.observability import PlatformMetrics, StructuredRequestLog, clock_ms, request_id

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

#: Signature of the next handler in a Starlette/FastAPI middleware chain.
_CallNext = Callable[["Request"], Awaitable["Response"]]


if TYPE_CHECKING:
    from fastapi import FastAPI



def mount(app: FastAPI, ctx: Any) -> None:
    from fastapi import Depends
    from fastapi.responses import PlainTextResponse

    metrics = PlatformMetrics()
    log = StructuredRequestLog(ctx.state_root / "runtime" / "api.jsonl")
    app.state.platform_metrics = metrics

    @app.middleware("http")
    async def observe(request: Request, call_next: _CallNext) -> Response:
        rid = request.headers.get("x-request-id") or request_id()
        trace_id = request.headers.get("x-trace-id")
        started = clock_ms()
        metrics.begin()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            duration = clock_ms() - started
            metrics.finish(request.url.path, status, duration)
            log.write(
                request_id=rid,
                trace_id=trace_id,
                method=request.method,
                path=request.url.path,
                status=status,
                duration_ms=duration,
            )

    @app.get(f"{ctx.prefix}/observability")
    def observability(_actor: str = Depends(ctx.principal)) -> dict[str, Any]:
        jobs = ctx.jobs.store.list(limit=1000)
        return {
            "api": metrics.snapshot(),
            "jobs": {
                "total": len(jobs),
                "failed": sum(getattr(job.status, "value", job.status) == "failed" for job in jobs),
                "running": sum(
                    getattr(job.status, "value", job.status) == "running" for job in jobs
                ),
            },
            "repositories": len(ctx.database.repositories()),
        }

    @app.get(f"{ctx.prefix}/metrics", response_class=PlainTextResponse)
    def prometheus(_actor: str = Depends(ctx.principal)) -> str:
        return metrics.prometheus()
