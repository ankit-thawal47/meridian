from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest

from meridian.agent.task_state import TaskStatus
from meridian.observability.replay import (
    assert_same_sequence,
    replay_task,
)
from meridian.observability.tracing import SpanRecord
from meridian.tools.context import ToolContext

from .conftest import make_state


def _recorded_runner(tool_names: list[str]) -> Any:
    async def runner(**_: Any) -> AsyncIterator[Any]:
        for name in tool_names:
            yield SimpleNamespace(content=[SimpleNamespace(name=name, input={})])
        yield SimpleNamespace(
            total_cost_usd=0.1, num_turns=len(tool_names), is_error=False,
            subtype="success", result="done",
        )

    return runner


def test_replay_returns_same_status(tmp_path) -> None:
    ctx = ToolContext(workspace=tmp_path, state=make_state())
    spans = [SpanRecord("t1", "tool_call", "repo_read")]
    runner = _recorded_runner(["repo_read", "edit_apply"])
    result = asyncio.run(replay_task(ctx, spans, runner))
    assert result.status is TaskStatus.succeeded


def test_assert_same_sequence_passes_on_identical() -> None:
    a = [SpanRecord("t", "tool_call", "repo_read"), SpanRecord("t", "tool_call", "edit_apply")]
    b = [SpanRecord("t", "tool_call", "repo_read"), SpanRecord("t", "tool_call", "edit_apply")]
    assert_same_sequence(a, b)


def test_assert_same_sequence_fails_on_divergence() -> None:
    a = [SpanRecord("t", "tool_call", "repo_read")]
    b = [SpanRecord("t", "tool_call", "edit_apply")]
    with pytest.raises(AssertionError):
        assert_same_sequence(a, b)
