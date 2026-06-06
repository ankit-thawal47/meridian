"""Orchestrator — wraps the SDK agent loop (Property 1 + 3 + 4).

The Claude Agent SDK runs the ``while not done`` loop internally. This module
*drives* one task through that loop: it builds the registry + options, streams
the messages, emits a trace span per model turn and tool call (Property 4),
keeps TaskState authoritative (Property 3), and computes a terminal status.

Message handling is duck-typed (no isinstance against SDK classes), so the
orchestrator is unit-testable by injecting a fake async ``runner`` that yields
plain stub objects.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from meridian.agent.task_state import TaskState, TaskStatus
from meridian.observability.tracing import SpanRecord, TraceSink
from meridian.tools.context import ToolContext

# Default runner is the real SDK query; injectable for tests.
Runner = Callable[..., AsyncIterator[Any]]


def _default_runner(**kwargs: Any) -> AsyncIterator[Any]:
    from claude_agent_sdk import query

    return query(**kwargs)


@dataclass
class OrchestratorResult:
    status: TaskStatus
    turns: int
    cost_usd: float
    summary: str
    state: TaskState


def _initial_prompt(state: TaskState) -> str:
    return (
        "Resolve the following issue. Current task state:\n\n"
        f"{state.render_context()}\n"
        f"ISSUE:\n{state.goal}\n"
    )


def _is_result(msg: Any) -> bool:
    return type(msg).__name__ == "ResultMessage" or hasattr(msg, "total_cost_usd")


def _blocks(msg: Any) -> list[Any]:
    content = getattr(msg, "content", None)
    return content if isinstance(content, list) else []


async def _handle_message(state: TaskState, msg: Any, sink: TraceSink | None) -> None:
    # Assistant turn: count it and emit spans for text + tool selections.
    if type(msg).__name__ == "AssistantMessage" or _blocks(msg):
        state.turns += 1
        for block in _blocks(msg):
            name = getattr(block, "name", None)
            if name is not None:  # ToolUseBlock — a tool selection
                tool_input = getattr(block, "input", {})
                summary = f"{name}({', '.join(map(str, (tool_input or {}).keys()))})"
                if sink:
                    await sink.record(SpanRecord(state.task_id, "tool_call", str(name), summary))
            else:
                text = getattr(block, "text", None)
                if text and sink:
                    await sink.record(
                        SpanRecord(state.task_id, "model_turn", "assistant", text[:200])
                    )


def _finalize(state: TaskState, final: Any | None) -> OrchestratorResult:
    cost = float(getattr(final, "total_cost_usd", None) or state.cost_usd)
    turns = int(getattr(final, "num_turns", None) or state.turns)
    is_error = bool(getattr(final, "is_error", False))
    subtype = str(getattr(final, "subtype", "") or "")
    summary = str(getattr(final, "result", "") or "")

    state.cost_usd = cost
    state.turns = turns
    if "budget" in subtype or "max_turns" in subtype:
        state.status = TaskStatus.budget_exceeded
    elif is_error:
        state.status = TaskStatus.failed
    else:
        state.status = TaskStatus.succeeded
    return OrchestratorResult(state.status, turns, cost, summary, state)


async def run_task(
    ctx: ToolContext,
    *,
    runner: Runner | None = None,
    sink: TraceSink | None = None,
    prompt: str | None = None,
) -> OrchestratorResult:
    # SDK-dependent builders imported lazily so the orchestrator's pure message
    # handling (_handle_message/_finalize) stays importable/testable without the SDK.
    from meridian.agent.sdk_session import build_options
    from meridian.tools.registry import build_registry

    runner = runner or _default_runner
    registry = build_registry(ctx)
    options = build_options(ctx, registry)

    ctx.state.status = TaskStatus.running
    final: Any | None = None
    async for msg in runner(prompt=prompt or _initial_prompt(ctx.state), options=options):
        await _handle_message(ctx.state, msg, sink)
        if _is_result(msg):
            final = msg

    result = _finalize(ctx.state, final)
    if sink:
        await sink.record(
            SpanRecord(
                ctx.state.task_id,
                "result",
                result.status.value,
                result.summary[:200],
                result.cost_usd,
                result.status.value,
            )
        )
    return result
