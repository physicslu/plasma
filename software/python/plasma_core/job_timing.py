"""Per-Job stage timestamps.

Observation only: a timing record never gates, retries or changes a Job.
The Site Worker binds one sink per Job attempt; code running inside that Job
(including ``asyncio.to_thread`` workers, which copy the context) calls
``mark``/``span``/``in_thread`` without knowing about the Job logger.
"""
from __future__ import annotations

import asyncio
import contextvars
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator, TypeVar

T = TypeVar("T")
Sink = Callable[..., None]

_SINK: contextvars.ContextVar[Sink | None] = contextvars.ContextVar(
    "plasma_job_timing_sink", default=None)


def bind(sink: Sink | None) -> contextvars.Token:
    return _SINK.set(sink)


def unbind(token: contextvars.Token) -> None:
    _SINK.reset(token)


def mark(phase: str, **fields: Any) -> None:
    sink = _SINK.get()
    if sink is None:
        return
    try:
        sink(phase, **fields)
    except Exception:  # noqa: BLE001 - a timing write must never fail a Job
        pass


@contextmanager
def span(phase: str, **fields: Any) -> Iterator[None]:
    started = time.monotonic()
    try:
        yield
    finally:
        mark(phase, duration_ms=round((time.monotonic() - started) * 1000.0, 1), **fields)


async def in_thread(phase: str, fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Run blocking verification off the event loop and record its duration."""
    with span(phase, thread=True):
        return await asyncio.to_thread(fn, *args, **kwargs)
