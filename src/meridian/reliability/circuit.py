"""Per-model circuit breaker (Property 4 — W2).

A single module-level registry keeps one CircuitBreaker per model name.
get_breaker(model) is the public entry point.

States: closed (normal) → open (failing fast) → half_open (probing recovery).
On open, the breaker either falls back to fallback_model or raises CircuitOpenError.
Research VIII.2.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class CircuitState(StrEnum):
    closed = "closed"
    open = "open"
    half_open = "half_open"


class CircuitOpenError(RuntimeError):
    def __init__(self, model: str) -> None:
        super().__init__(f"circuit open for model: {model}")
        self.model = model


@dataclass
class CircuitBreaker:
    model: str
    failure_threshold: int = 5
    reset_timeout_s: float = 60.0

    _state: CircuitState = field(default=CircuitState.closed, init=False, repr=False)
    _failures: int = field(default=0, init=False, repr=False)
    _opened_at: float | None = field(default=None, init=False, repr=False)

    @property
    def state(self) -> CircuitState:
        return self._state

    def _on_success(self) -> None:
        self._state = CircuitState.closed
        self._failures = 0
        self._opened_at = None

    def _on_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._state = CircuitState.open
            self._opened_at = time.monotonic()

    async def call(
        self,
        fn: Callable[..., Any],
        *args: Any,
        fallback_model: str | None = None,
        **kwargs: Any,
    ) -> Any:
        if self._state == CircuitState.open:
            elapsed = time.monotonic() - (self._opened_at or 0)
            if elapsed > self.reset_timeout_s:
                self._state = CircuitState.half_open
            elif fallback_model:
                kwargs["model"] = fallback_model
                return await _call(fn, *args, **kwargs)
            else:
                raise CircuitOpenError(self.model)

        try:
            result = await _call(fn, *args, **kwargs)
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise


async def _call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    result = fn(*args, **kwargs)
    # fn may be a coroutine factory or a plain async function.
    if hasattr(result, "__aiter__"):
        return result  # async generator — caller iterates
    return await result


# Module-level registry — one breaker per model, shared across tasks.
_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(model: str) -> CircuitBreaker:
    if model not in _breakers:
        _breakers[model] = CircuitBreaker(model=model)
    return _breakers[model]


def reset_all() -> None:
    """Reset all breakers — for use in tests only."""
    _breakers.clear()
