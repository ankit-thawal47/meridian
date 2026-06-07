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
    """Above RETRIEVAL_THRESHOLD the registry returns the retrieved top-k, and
    every returned name is a valid, namespaced Meridian tool. tool_names must
    stay in lock-step with what the MCP server exposes."""
    from meridian.tools.analysis_tools import ANALYSIS_TOOL_NAMES
    from meridian.tools.core_tools import CORE_TOOL_NAMES
    from meridian.tools.doc_tools import DOC_TOOL_NAMES
    from meridian.tools.issue_tools import ISSUE_TOOL_NAMES
    from meridian.tools.retrieval import TOP_K

    all_names = (
        CORE_TOOL_NAMES + ANALYSIS_TOOL_NAMES + DOC_TOOL_NAMES + ISSUE_TOOL_NAMES
    )
    # The assignment requires 50+ tools across 4 namespaces.
    assert len(all_names) == 50
    assert len(set(all_names)) == 50  # no duplicate/near-identical names

    ctx = ToolContext(workspace=tmp_path, state=make_state())
    reg = build_registry(ctx)

    # Retrieval is active: exactly TOP_K tools are loaded this task.
    assert len(reg.tool_names) == TOP_K
    valid = {f"mcp__meridian__{n}" for n in all_names}
    assert set(reg.tool_names) <= valid
    assert reg.server is not None


def test_registry_eager_loads_below_threshold(monkeypatch: Any, tmp_path: Any) -> None:
    """Below the threshold every tool is eager-loaded (no retrieval)."""
    import meridian.tools.registry as registry_mod

    monkeypatch.setattr(registry_mod, "RETRIEVAL_THRESHOLD", 1000)
    ctx = ToolContext(workspace=tmp_path, state=make_state())
    reg = build_registry(ctx)
    assert len(reg.tool_names) == 50


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
