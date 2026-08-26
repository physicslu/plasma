from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from plasma_core.errors import ErrorCode, PlasmaError

from .gateway_settings import GatewayCommunicationPolicy


T = TypeVar("T")
PPU_RETRY_BACKOFF_S = 1.0
PPU_RETRY_BACKOFF_CAP_MULTIPLIER = 4

RetryObserver = Callable[[int, int, float, PlasmaError], None]


def normalize_ppu_communication_error(error: Exception) -> PlasmaError | None:
    if isinstance(error, PlasmaError) and error.code in {
        ErrorCode.CONNECTION_TIMEOUT,
        ErrorCode.CONNECTION_FAILED,
    }:
        return error
    if isinstance(error, TimeoutError):
        return PlasmaError(
            ErrorCode.CONNECTION_TIMEOUT,
            "PPU request timed out",
            recoverable=True,
            original_exception=error,
        )
    if isinstance(error, (OSError, ConnectionError)):
        return PlasmaError(
            ErrorCode.CONNECTION_FAILED,
            f"PPU connection failed: {error}",
            recoverable=True,
            original_exception=error,
        )
    return None


def ppu_retry_delay_s(retry_index: int, *, base_s: float = PPU_RETRY_BACKOFF_S) -> float:
    if retry_index < 0:
        raise ValueError("retry_index must be non-negative")
    return base_s * min(2**retry_index, PPU_RETRY_BACKOFF_CAP_MULTIPLIER)


def ppu_response_budget_ms(
    policy: GatewayCommunicationPolicy,
    *,
    retry_backoff_s: float = PPU_RETRY_BACKOFF_S,
) -> int:
    attempts = policy.ppu_retry_count + 1
    backoff_ms = sum(
        int(ppu_retry_delay_s(index, base_s=retry_backoff_s) * 1000)
        for index in range(policy.ppu_retry_count)
    )
    return policy.ppu_request_timeout_ms * attempts + backoff_ms


async def request_with_gateway_policy(
    operation: Callable[[], Awaitable[T]],
    policy: GatewayCommunicationPolicy,
    *,
    retryable: bool = True,
    retry_backoff_s: float = PPU_RETRY_BACKOFF_S,
    on_retry: RetryObserver | None = None,
) -> T:
    retries = policy.ppu_retry_count if retryable else 0
    for attempt in range(retries + 1):
        try:
            return await asyncio.wait_for(operation(), timeout=policy.request_timeout_s)
        except Exception as error:
            communication_error = normalize_ppu_communication_error(error)
            if communication_error is None:
                raise
            if attempt >= retries:
                if communication_error is error:
                    raise
                raise communication_error from error
            delay_s = ppu_retry_delay_s(attempt, base_s=retry_backoff_s)
            if on_retry is not None:
                on_retry(attempt + 1, retries, delay_s, communication_error)
            await asyncio.sleep(delay_s)
    raise RuntimeError("Gateway PPU communication retry loop terminated unexpectedly")
