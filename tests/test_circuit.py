from __future__ import annotations

import asyncio
import time

import pytest

from meridian.reliability.circuit import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    get_breaker,
    reset_all,
)


def setup_function() -> None:
    reset_all()


# --- basic state machine ---

def test_circuit_starts_closed() -> None:
    cb = CircuitBreaker(model="test-model", failure_threshold=3)
    assert cb.state == CircuitState.closed


def test_circuit_opens_after_threshold() -> None:
    cb = CircuitBreaker(model="test-model", failure_threshold=3)

    async def fail(**_):
        raise RuntimeError("boom")

    async def run():
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await cb.call(fail)

    asyncio.run(run())
    assert cb.state == CircuitState.open


def test_open_circuit_raises_without_fallback() -> None:
    cb = CircuitBreaker(model="m", failure_threshold=1)

    async def fail(**_):
        raise RuntimeError("x")

    async def run():
        with pytest.raises(RuntimeError):
            await cb.call(fail)
        with pytest.raises(CircuitOpenError):
            await cb.call(fail)

    asyncio.run(run())


def test_circuit_falls_back_to_fallback_model() -> None:
    cb = CircuitBreaker(model="expensive-model", failure_threshold=1)
    used_model: list[str] = []

    async def fail(**_):
        raise RuntimeError("x")

    async def succeed(**kwargs):
        used_model.append(kwargs.get("model", ""))
        return "ok"

    async def run():
        with pytest.raises(RuntimeError):
            await cb.call(fail)
        result = await cb.call(succeed, fallback_model="cheap-model")
        return result

    result = asyncio.run(run())
    assert result == "ok"
    assert used_model == ["cheap-model"]


def test_circuit_resets_after_timeout() -> None:
    cb = CircuitBreaker(model="m", failure_threshold=1, reset_timeout_s=0.0)

    async def fail(**_):
        raise RuntimeError("x")

    async def succeed(**_):
        return "ok"

    async def run():
        with pytest.raises(RuntimeError):
            await cb.call(fail)
        assert cb.state == CircuitState.open
        # Simulate timeout elapsed by setting _opened_at to the past.
        cb._opened_at = time.monotonic() - 1.0
        result = await cb.call(succeed)
        return result

    result = asyncio.run(run())
    assert result == "ok"
    assert cb.state == CircuitState.closed


# --- module registry ---

def test_get_breaker_returns_same_instance() -> None:
    b1 = get_breaker("model-a")
    b2 = get_breaker("model-a")
    assert b1 is b2


def test_get_breaker_different_models_are_different() -> None:
    assert get_breaker("model-a") is not get_breaker("model-b")
