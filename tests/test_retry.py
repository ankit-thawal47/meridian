from __future__ import annotations

import asyncio

import pytest
from claude_agent_sdk import CLIConnectionError, CLINotFoundError

from meridian.reliability.retry import (
    FailureKind,
    RetryPolicy,
    classify_exception,
    classify_outcome,
    full_jitter,
)
from meridian.tools.schemas import ToolOutcome, ToolStatus

# --- classify_outcome ---

def test_classify_outcome_deterministic_is_terminal() -> None:
    outcome = ToolOutcome(status=ToolStatus.error, deterministic=True, summary="compile error")
    assert classify_outcome(outcome) == FailureKind.terminal


def test_classify_outcome_non_deterministic_is_transient() -> None:
    outcome = ToolOutcome(status=ToolStatus.error, deterministic=False, summary="timeout")
    assert classify_outcome(outcome) == FailureKind.transient


def test_classify_outcome_ok_is_terminal() -> None:
    outcome = ToolOutcome(status=ToolStatus.ok)
    assert classify_outcome(outcome) == FailureKind.terminal


# --- classify_exception ---

def test_classify_exception_connection_error_is_transient() -> None:
    assert classify_exception(CLIConnectionError("pipe broken")) == FailureKind.transient


def test_classify_exception_not_found_is_terminal() -> None:
    assert classify_exception(CLINotFoundError("no claude binary")) == FailureKind.terminal


def test_classify_exception_timeout_is_transient() -> None:
    assert classify_exception(TimeoutError("timeout")) == FailureKind.transient


def test_classify_exception_runtime_is_terminal() -> None:
    assert classify_exception(RuntimeError("boom")) == FailureKind.terminal


# --- full_jitter ---

def test_full_jitter_always_within_bounds() -> None:
    for attempt in range(6):
        for _ in range(200):
            cap = 30.0
            base = 1.0
            val = full_jitter(attempt, base, cap)
            assert 0.0 <= val <= min(cap, base * (2**attempt))


def test_full_jitter_zero_attempt_bounded_by_base() -> None:
    for _ in range(100):
        assert full_jitter(0, base=1.0, cap=30.0) <= 1.0


# --- retry loop in orchestrator ---

def test_retry_succeeds_on_third_attempt() -> None:
    """Mock runner raises CLIConnectionError twice, succeeds on third call."""
    from types import SimpleNamespace

    from meridian.observability.tracing import InMemoryTraceSink
    from meridian.reliability.retry import FailureKind  # noqa: F401
    from meridian.worker import orchestrator
    from tests.conftest import make_state

    call_count = 0

    async def flaky_runner(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise CLIConnectionError("transient")
        # Yield a result message on the 3rd attempt.
        final = SimpleNamespace(
            total_cost_usd=0.01, num_turns=1, is_error=False, subtype="success", result="ok"
        )
        yield final

    policy = RetryPolicy(max_attempts=3, base_s=0.0, cap_s=0.0)

    async def run():
        import tempfile
        from pathlib import Path

        from meridian.tools.context import ToolContext

        with tempfile.TemporaryDirectory() as tmp:
            ctx = ToolContext(workspace=Path(tmp), state=make_state())
            return await orchestrator.run_task(
                ctx, runner=flaky_runner, sink=InMemoryTraceSink(), policy=policy
            )

    result = asyncio.run(run())
    assert call_count == 3
    from meridian.agent.task_state import TaskStatus
    assert result.status == TaskStatus.succeeded


def test_terminal_error_not_retried() -> None:
    """Mock runner raises CLINotFoundError (terminal) — must be called exactly once."""
    call_count = 0

    async def failing_runner(**kwargs):
        nonlocal call_count
        call_count += 1
        raise CLINotFoundError("no claude binary")
        yield  # make it an async generator

    policy = RetryPolicy(max_attempts=3, base_s=0.0, cap_s=0.0)

    async def run():
        import tempfile
        from pathlib import Path

        from meridian.observability.tracing import InMemoryTraceSink
        from meridian.tools.context import ToolContext
        from meridian.worker import orchestrator
        from tests.conftest import make_state

        with tempfile.TemporaryDirectory() as tmp:
            ctx = ToolContext(workspace=Path(tmp), state=make_state())
            with pytest.raises(CLINotFoundError):
                await orchestrator.run_task(
                    ctx, runner=failing_runner, sink=InMemoryTraceSink(), policy=policy
                )

    asyncio.run(run())
    assert call_count == 1
