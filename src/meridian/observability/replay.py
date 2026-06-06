"""Deterministic task replay from recorded spans (FR4.5).

Feeds recorded tool I/O back through the orchestrator's pure message loop with
an injected runner, so a recorded task can be re-executed and its decision
sequence asserted identical — observability that is also a regression test.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from meridian.observability.tracing import InMemoryTraceSink, SpanRecord, TraceSink
from meridian.tools.context import ToolContext
from meridian.worker.orchestrator import (
    OrchestratorResult,
    _finalize,
    _handle_message,
)

TaskOutcome = OrchestratorResult


@dataclass
class ReplayAssertion:
    tool_name: str
    expected_outcome: str  # "ok" | "error"


async def replay_task(
    ctx: ToolContext,
    recorded_spans: list[SpanRecord],
    runner: Any,
    sink: TraceSink | None = None,
) -> TaskOutcome:
    """Re-run a task using a runner pre-loaded with recorded I/O.

    Returns the TaskOutcome; the caller asserts the decision sequence matches
    via assert_same_sequence().
    """
    sink = sink or InMemoryTraceSink()
    final: Any | None = None
    async for msg in runner(prompt="", options=None):
        await _handle_message(ctx.state, msg, sink)
        if type(msg).__name__ == "ResultMessage" or hasattr(msg, "total_cost_usd"):
            final = msg
    result = _finalize(ctx.state, final)
    return result


def assert_same_sequence(
    original: list[SpanRecord],
    replayed: list[SpanRecord],
) -> None:
    """Assert tool_call spans appear in the same order in both runs."""
    orig = [s.name for s in original if s.kind == "tool_call"]
    new = [s.name for s in replayed if s.kind == "tool_call"]
    if orig != new:
        raise AssertionError(
            f"decision sequence diverged:\n  original: {orig}\n  replayed: {new}"
        )
