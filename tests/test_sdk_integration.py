"""SDK-gated tests: registry wiring + a full orchestrator run with a fake stream.

Skipped automatically when claude-agent-sdk is not installed, so the rest of the
suite stays runnable in minimal environments.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("claude_agent_sdk")

from meridian.observability.tracing import InMemoryTraceSink  # noqa: E402
from meridian.tools.context import ToolContext  # noqa: E402
from meridian.tools.registry import build_registry  # noqa: E402
from meridian.worker.orchestrator import run_task  # noqa: E402

from .conftest import make_state  # noqa: E402


def test_registry_builds_expected_names(tmp_path: Any) -> None:
    ctx = ToolContext(workspace=tmp_path, state=make_state())
    reg = build_registry(ctx)
    assert reg.tool_names == [
        f"mcp__meridian__{n}"
        for n in ["repo_read", "repo_search", "edit_apply", "exec_test", "state_update"]
    ]
    assert reg.server is not None


def _fake_runner(**_kwargs: Any):
    async def gen():
        # model selects a tool, then the SDK emits a terminal result message
        yield SimpleNamespace(
            content=[SimpleNamespace(name="mcp__meridian__state_update", input={"plan": ["x"]})]
        )
        yield SimpleNamespace(
            total_cost_usd=0.05, num_turns=1, is_error=False, subtype="success", result="done"
        )

    return gen()


def test_run_task_with_fake_stream(tmp_path: Any) -> None:
    (tmp_path / "x.txt").write_text("hi")
    ctx = ToolContext(workspace=tmp_path, state=make_state())
    sink = InMemoryTraceSink()
    res = asyncio.run(run_task(ctx, runner=_fake_runner, sink=sink))
    assert res.status.value == "succeeded"
    assert res.cost_usd == 0.05
    assert any(s.kind == "result" for s in sink.spans)
    assert any(s.kind == "tool_call" for s in sink.spans)
