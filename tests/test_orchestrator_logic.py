from __future__ import annotations

import asyncio
from types import SimpleNamespace

from meridian.agent.task_state import TaskStatus
from meridian.observability.tracing import InMemoryTraceSink
from meridian.reliability.retry import RetryPolicy
from meridian.worker import orchestrator

from .conftest import make_state


def test_tool_use_block_records_span_and_turn() -> None:
    st = make_state()
    sink = InMemoryTraceSink()
    block = SimpleNamespace(name="mcp__meridian__repo_read", input={"path": "a"})
    msg = SimpleNamespace(content=[block])
    asyncio.run(orchestrator._handle_message(st, msg, sink))
    assert st.turns == 1
    assert [s.kind for s in sink.spans] == ["tool_call"]
    assert sink.spans[0].name == "mcp__meridian__repo_read"


def test_text_block_records_model_turn() -> None:
    st = make_state()
    sink = InMemoryTraceSink()
    msg = SimpleNamespace(content=[SimpleNamespace(text="reasoning about the fix")])
    asyncio.run(orchestrator._handle_message(st, msg, sink))
    assert any(s.kind == "model_turn" for s in sink.spans)


def test_finalize_success() -> None:
    final = SimpleNamespace(
        total_cost_usd=0.12, num_turns=5, is_error=False, subtype="success", result="done"
    )
    res = orchestrator._finalize(make_state(), final)
    assert res.status is TaskStatus.succeeded
    assert res.cost_usd == 0.12 and res.turns == 5


def test_finalize_budget_exceeded() -> None:
    final = SimpleNamespace(
        total_cost_usd=5.0, num_turns=80, is_error=True, subtype="error_max_turns", result=""
    )
    res = orchestrator._finalize(make_state(), final)
    assert res.status is TaskStatus.budget_exceeded


def test_finalize_failure() -> None:
    final = SimpleNamespace(
        total_cost_usd=0.01, num_turns=2, is_error=True, subtype="error", result="boom"
    )
    res = orchestrator._finalize(make_state(), final)
    assert res.status is TaskStatus.failed


def test_run_with_retry_records_50_plus_tool_calls() -> None:
    async def fake_runner(**_kwargs):
        for i in range(60):
            yield SimpleNamespace(
                content=[
                    SimpleNamespace(
                        name="mcp__meridian__repo_search",
                        input={"query": f"symbol_{i}", "max_results": 5},
                    )
                ]
            )
        yield SimpleNamespace(
            total_cost_usd=0.42,
            num_turns=60,
            is_error=False,
            subtype="success",
            result="done",
        )

    st = make_state()
    sink = InMemoryTraceSink()
    final = asyncio.run(
        orchestrator._run_with_retry(
            fake_runner,
            "prompt",
            options=None,
            state=st,
            sink=sink,
            policy=RetryPolicy(max_attempts=1, base_s=0, cap_s=0),
        )
    )

    tool_spans = [s for s in sink.spans if s.kind == "tool_call"]
    assert len(tool_spans) == 60
    assert st.turns == 60
    assert final.total_cost_usd == 0.42
    assert tool_spans[0].summary == "mcp__meridian__repo_search(query, max_results)"
    assert tool_spans[-1].summary == "mcp__meridian__repo_search(query, max_results)"
