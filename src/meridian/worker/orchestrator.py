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

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from meridian.agent.task_state import TaskState, TaskStatus
from meridian.observability.tracing import SpanRecord, TraceSink
from meridian.reliability.retry import FailureKind, RetryPolicy, classify_exception, full_jitter
from meridian.security.quarantine import wrap_issue_text
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
        f"ISSUE:\n{wrap_issue_text(state.goal)}\n"
    )


def _is_result(msg: Any) -> bool:
    return type(msg).__name__ == "ResultMessage" or hasattr(msg, "total_cost_usd")


def _blocks(msg: Any) -> list[Any]:
    content = getattr(msg, "content", None)
    return content if isinstance(content, list) else []


def _args_preview(tool_input: dict[str, Any]) -> str:
    """Compact representation of tool args with actual values, not just keys."""
    parts = []
    for k, v in list((tool_input or {}).items())[:4]:
        v_str = str(v)
        parts.append(f"{k}={v_str[:80]!r}" if len(v_str) > 80 else f"{k}={v!r}")
    return ", ".join(parts)


async def _handle_message(
    state: TaskState, msg: Any, sink: TraceSink | None, settings: Any | None = None
) -> None:
    msg_type = type(msg).__name__

    # Assistant turn: tool selections + reasoning text.
    if msg_type == "AssistantMessage" or (msg_type not in ("ToolResultMessage",) and _blocks(msg)):
        state.turns += 1
        for block in _blocks(msg):
            name = getattr(block, "name", None)
            if name is not None:  # ToolUseBlock
                tool_input = getattr(block, "input", {}) or {}
                summary = f"{name}({_args_preview(tool_input)})"
                if sink:
                    attributes: dict[str, Any] = {
                        "gen_ai.operation.name": "execute_tool",
                        "tool.input": json.dumps(tool_input, default=str)[:800],
                    }
                    if settings is not None:
                        from meridian.agent.routing import route_model
                        attributes["gen_ai.request.model"] = route_model(str(name), settings)
                    await sink.record(
                        SpanRecord(
                            state.task_id,
                            "tool_call",
                            str(name),
                            summary,
                            attributes=attributes,
                            turn_num=state.turns,
                        )
                    )
            else:
                text = getattr(block, "text", None)
                if text and sink:
                    await sink.record(
                        SpanRecord(
                            state.task_id,
                            "model_turn",
                            "assistant",
                            text[:1000],
                            turn_num=state.turns,
                        )
                    )

    # Tool result turn: capture what each tool actually returned.
    elif msg_type == "ToolResultMessage" or (msg_type == "UserMessage" and _blocks(msg)):
        for block in _blocks(msg):
            tool_use_id = getattr(block, "tool_use_id", None)
            if tool_use_id is None:
                continue
            content = getattr(block, "content", "") or ""
            if isinstance(content, list):
                content = " ".join(getattr(b, "text", "") for b in content if hasattr(b, "text"))
            output_preview = str(content)[:800]
            if sink:
                await sink.record(
                    SpanRecord(
                        state.task_id,
                        "tool_result",
                        str(tool_use_id)[:64],
                        output_preview[:300],
                        attributes={"tool.output": output_preview},
                        turn_num=state.turns,
                    )
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


async def _run_with_retry(
    runner: Runner,
    prompt: str,
    options: Any,
    state: TaskState,
    sink: TraceSink | None,
    policy: RetryPolicy,
    settings: Any | None = None,
) -> Any:
    """Run the SDK loop with transient-only retry + Full Jitter backoff."""
    final: Any | None = None
    for attempt in range(policy.max_attempts):
        try:
            async for msg in runner(prompt=prompt, options=options):
                await _handle_message(state, msg, sink, settings)
                if _is_result(msg):
                    final = msg
            return final  # success
        except Exception as exc:
            kind = classify_exception(exc)
            if kind == FailureKind.terminal or attempt == policy.max_attempts - 1:
                raise
            delay = full_jitter(attempt, policy.base_s, policy.cap_s)
            await asyncio.sleep(delay)
    return final  # unreachable, but satisfies type checker


async def run_task(
    ctx: ToolContext,
    *,
    runner: Runner | None = None,
    sink: TraceSink | None = None,
    prompt: str | None = None,
    policy: RetryPolicy | None = None,
) -> OrchestratorResult:
    # SDK-dependent builders imported lazily so the orchestrator's pure message
    # handling (_handle_message/_finalize) stays importable/testable without the SDK.
    from meridian.agent.sdk_session import build_options
    from meridian.config import get_settings
    from meridian.tools.registry import build_registry

    runner = runner or _default_runner
    settings = get_settings()
    registry = build_registry(ctx)
    options = build_options(ctx, registry)

    if policy is None:
        policy = RetryPolicy(
            max_attempts=settings.retry_max_attempts,
            base_s=settings.retry_base_s,
            cap_s=settings.retry_cap_s,
        )

    ctx.state.status = TaskStatus.running
    final = await _run_with_retry(
        runner,
        prompt or _initial_prompt(ctx.state),
        options,
        ctx.state,
        sink,
        policy,
        settings,
    )

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
