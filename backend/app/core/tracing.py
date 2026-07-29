"""MLflow run/span helpers: `@traced(node_name)` decorator and `run_context` (§17).

A no-op when `MLFLOW_ENABLED=false`, so tests and the deployed instance can
run without an MLflow backend.

Metrics are always accumulated in-process on a run-scoped `RunMetrics` held in
a `ContextVar`, so tests can assert node path and `llm_calls_total` regardless
of whether an MLflow backend is configured. Only the *export* of those metrics
(params, metrics, artifacts) is gated on `MLFLOW_ENABLED`.
"""

import contextlib
import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, TypeVar

from app.config import settings
from app.schemas.chapters import VerificationReport

# Params that are safe to log. NEVER api_key, NEVER a credentialed base_url.
_SAFE_PARAM_KEYS = frozenset(
    {
        "provider",
        "model",
        "video_id",
        "duration",
        "transcript_source",
        "embedding_backend",
        "analysis_version",
        "request_id",
        "embedding_model",
        "embedding_dim",
    }
)


@dataclass
class RunMetrics:
    """Run-scoped, in-process metrics accumulator (§17)."""

    node_path: list[str] = field(default_factory=list)
    node_latency_ms: dict[str, float] = field(default_factory=dict)
    llm_calls_total: int = 0
    segmentation_attempts: int = 0
    verification_issues: int = 0
    chapters_final: int = 0
    dropped_citations: int = 0
    params: dict[str, Any] = field(default_factory=dict)
    verification_report: VerificationReport | None = None


_current: ContextVar[RunMetrics | None] = ContextVar("videomind_run_metrics", default=None)


def current_metrics() -> RunMetrics | None:
    return _current.get()


def record_llm_call() -> None:
    """Increment the run's LLM-call counter. Called from `core/llm._complete`
    and from the `FakeLLM` test double so the metric is accurate in both real
    and faked runs."""
    metrics = _current.get()
    if metrics is not None:
        metrics.llm_calls_total += 1


F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def traced(node_name: str) -> Callable[[F], F]:
    """Record a graph node's visit and latency onto the current `RunMetrics`.
    Pure in-process bookkeeping — MLflow export happens once, at `run_context`
    exit."""

    def decorator(fn: F) -> F:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            metrics = _current.get()
            start = time.perf_counter()
            try:
                return await fn(*args, **kwargs)
            finally:
                if metrics is not None:
                    elapsed_ms = (time.perf_counter() - start) * 1000.0
                    metrics.node_path.append(node_name)
                    metrics.node_latency_ms[node_name] = (
                        metrics.node_latency_ms.get(node_name, 0.0) + elapsed_ms
                    )

        return wrapper  # type: ignore[return-value]

    return decorator


@contextlib.asynccontextmanager
async def run_context(experiment: str, params: dict[str, Any]) -> AsyncIterator[RunMetrics]:
    """One MLflow run per graph execution (§17). Yields the `RunMetrics` the
    caller and graph nodes populate; exports it on exit when MLflow is enabled."""
    metrics = RunMetrics(params=dict(params))
    token = _current.set(metrics)
    if not settings.MLFLOW_ENABLED:
        try:
            yield metrics
        finally:
            _current.reset(token)
        return

    import mlflow

    # The plan (§17, §19) pins a `file:` tracking backend for the free tier;
    # mlflow 3.x gates that behind an opt-in env var.
    os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
    mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
    mlflow.set_experiment(experiment)
    with mlflow.start_run():
        try:
            yield metrics
        finally:
            _export(mlflow, metrics)
            _current.reset(token)


def _export(mlflow: Any, metrics: RunMetrics) -> None:
    safe_params = {
        k: v for k, v in metrics.params.items() if k in _SAFE_PARAM_KEYS and v is not None
    }
    if safe_params:
        mlflow.log_params(safe_params)
    mlflow.log_metric("llm_calls_total", metrics.llm_calls_total)
    mlflow.log_metric("segmentation_attempts", metrics.segmentation_attempts)
    mlflow.log_metric("verification_issues", metrics.verification_issues)
    mlflow.log_metric("chapters_final", metrics.chapters_final)
    mlflow.log_metric("dropped_citations", metrics.dropped_citations)
    for node_name, latency_ms in metrics.node_latency_ms.items():
        mlflow.log_metric(f"node.{node_name}.latency_ms", latency_ms)
    mlflow.log_text("\n".join(metrics.node_path), "node_path.txt")
    if metrics.verification_report is not None:
        mlflow.log_text(
            metrics.verification_report.model_dump_json(indent=2), "verification_report.json"
        )
